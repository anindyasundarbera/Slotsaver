from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import utcnow
from ..errors import ProviderUnavailable
from ..models import Booking, BookingStatus, Service, User
from ..schemas import AssistantReply, OptionOut, ToolTrace
from ..timeutil import OPENING_HOURS, local_instant
from . import availability
from .serializers import build_option

log = logging.getLogger("slotsaver.assistant")

MAX_OPTIONS = 3
MAX_MESSAGE_CHARS = 1000

SERVICE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "washer-repair": ("washing machine", "washer", "laundry machine", "front loader", "spin"),
    "dryer-repair": ("dryer", "tumble dryer", "drying machine", "lint"),
    "dishwasher-install": ("dishwasher", "dish washer", "install dishwasher"),
}

DAY_WORDS = {
    "today": 0,
    "tomorrow": 1,
    "day after tomorrow": 2,
}

TOOL_DEFINITIONS = [
    {
        "name": "search_availability",
        "description": (
            "Return real bookable appointment options for one service on one business day. "
            "Never invent options; only present what this tool returns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_code": {"type": "string", "enum": list(SERVICE_KEYWORDS)},
                "day": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "after_local": {"type": "string", "description": "Earliest local start HH:MM"},
                "before_local": {"type": "string", "description": "Latest local end HH:MM"},
                "max_price_cents": {"type": "integer"},
            },
            "required": ["service_code", "day"],
        },
    },
    {
        "name": "lookup_booking",
        "description": "Look up the signed-in customer's own booking by reference.",
        "parameters": {
            "type": "object",
            "properties": {"reference": {"type": "string"}},
            "required": ["reference"],
        },
    },
]

SYSTEM_PROMPT = """You are the SlotSaver booking assistant for Northline Appliance Care.
Rules you must follow:
- Call search_availability before mentioning any appointment time. Never invent availability.
- You cannot hold, pay for, or confirm a booking. The customer does that in the UI.
- Never state that a payment succeeded. Payment truth comes only from the payment service.
- Ask at most one short clarifying question per turn.
- Keep replies under 60 words, factual, and mention the timezone when quoting times.
- If the request is out of scope, say so briefly and offer the form instead.
Return strict JSON: {"reply": str, "constraints": {...}, "needs_clarification": bool,
"clarification_question": str|null}
"""


@dataclass
class Constraints:
    service_code: str | None = None
    day: date | None = None
    after: str | None = None
    before: str | None = None
    max_price_cents: int | None = None
    confidence_notes: list[str] = field(default_factory=list)

    def missing(self) -> list[str]:
        missing = []
        if not self.service_code:
            missing.append("service")
        if not self.day:
            missing.append("day")
        return missing

    def as_dict(self) -> dict:
        return {
            "service_code": self.service_code,
            "day": self.day.isoformat() if self.day else None,
            "after": self.after,
            "before": self.before,
            "max_price_cents": self.max_price_cents,
        }


def _parse_time(raw: str) -> str | None:
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", raw, re.IGNORECASE)
    if not match:
        return None
    hh = int(match.group(1))
    mm = int(match.group(2) or 0)
    suffix = (match.group(3) or "").lower()
    if suffix == "pm" and hh < 12:
        hh += 12
    if suffix == "am" and hh == 12:
        hh = 0
    if suffix == "" and 1 <= hh <= 7:
        hh += 12  # "after 4" in a business context means 4 PM
    if not (0 <= hh <= 23 and mm in (0, 30)):
        return None
    return f"{hh:02d}:{mm:02d}"


def normalise(text: str) -> str:
    """Lowercase and flatten punctuation so 'washing-machine' matches 'washing machine'."""
    lowered = text.lower()
    for char in "-_/":
        lowered = lowered.replace(char, " ")
    return " ".join(lowered.split())


def parse_constraints(message: str, settings: Settings, demo_day: date) -> Constraints:
    text = normalise(message)
    out = Constraints()

    for code, words in SERVICE_KEYWORDS.items():
        if any(word in text for word in words):
            out.service_code = code
            break

    for word, offset in sorted(DAY_WORDS.items(), key=lambda kv: -len(kv[0])):
        if word in text:
            out.day = _shift_business(demo_day, offset)
            break
    if out.day is None:
        iso = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if iso:
            try:
                out.day = date.fromisoformat(iso.group(1))
            except ValueError:
                out.confidence_notes.append("unparseable date")
        else:
            weekday = re.search(
                r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text
            )
            if weekday:
                target = [
                    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
                ].index(weekday.group(1))
                cursor = demo_day
                for _ in range(8):
                    cursor += timedelta(days=1)
                    if cursor.weekday() == target and cursor.weekday() in OPENING_HOURS:
                        out.day = cursor
                        break

    after_match = re.search(
        r"(?:after|from|not before|starting at)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", text
    )
    if after_match:
        out.after = _parse_time(after_match.group(1))

    before_match = re.search(
        r"(?:before|by|finish before|finish by|ending by|ends by|until)\s+"
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        text,
    )
    if before_match:
        out.before = _parse_time(before_match.group(1))

    budget = re.search(r"\$\s?(\d{1,5})(?:\.(\d{2}))?", text)
    if budget:
        dollars = int(budget.group(1))
        cents = int(budget.group(2) or 0)
        out.max_price_cents = dollars * 100 + cents
    else:
        budget_word = re.search(r"budget(?:\s+is)?\s+(\d{1,5})", text)
        if budget_word:
            out.max_price_cents = int(budget_word.group(1)) * 100

    return out


def human_time(hhmm: str) -> str:
    """'18:00' -> '6:00 PM' for user-facing text."""
    hh, mm = (int(part) for part in hhmm.split(":"))
    suffix = "AM" if hh < 12 else "PM"
    hour12 = hh % 12 or 12
    return f"{hour12}:{mm:02d} {suffix}"


def _shift_business(start: date, offset: int) -> date:
    if offset == 0:
        return start
    cursor = start
    remaining = offset
    while remaining:
        cursor += timedelta(days=1)
        if cursor.weekday() in OPENING_HOURS:
            remaining -= 1
    return cursor


class Assistant:
    """Bounded tool-using assistant. Tools are read-only and identity-bound."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # -------------------------------------------------- tool execution
    def _search_availability(
        self, db: Session, customer: User, args: dict
    ) -> tuple[list[OptionOut], str]:
        service_code = str(args.get("service_code", ""))
        if service_code not in SERVICE_KEYWORDS:
            raise ValueError("unsupported service_code")
        service = db.execute(select(Service).where(Service.code == service_code)).scalar_one_or_none()
        if service is None:
            raise ValueError("unknown service")
        raw_day = args.get("day")
        try:
            day = date.fromisoformat(str(raw_day))
        except (TypeError, ValueError) as exc:
            raise ValueError("day must be YYYY-MM-DD") from exc

        after = args.get("after_local")
        before = args.get("before_local")
        budget = args.get("max_price_cents")
        if budget is not None:
            budget = int(budget)

        candidates = availability.find_candidates(
            db, self.settings, service, day, after=after, before=before
        )
        options = [
            build_option(
                service=service,
                technician=c.technician,
                start_utc=c.start_utc,
                end_utc=c.end_utc,
                settings=self.settings,
                budget_cents=budget,
            )
            for c in candidates
        ]
        if budget is not None:
            options = [o for o in options if o.within_budget]
        options = options[:MAX_OPTIONS]
        summary = (
            f"found {len(options)} option(s) for {service.name} on {day.isoformat()}"
            if options
            else f"no options for {service.name} on {day.isoformat()}"
        )
        return options, summary

    def _lookup_booking(self, db: Session, customer: User, args: dict) -> tuple[str, str]:
        reference = str(args.get("reference", "")).strip().upper()
        booking = db.execute(
            select(Booking).where(
                Booking.reference == reference, Booking.customer_id == customer.id
            )
        ).scalar_one_or_none()
        if booking is None:
            # Never disclose whether the reference belongs to someone else.
            return "No booking with that reference on your account.", "booking not found"
        return (
            f"{booking.reference}: {booking.service.name} on "
            f"{booking.start_utc.astimezone(self.settings.tz):%a %d %b %H:%M} "
            f"({booking.status.replace('_', ' ')})",
            f"booking {booking.reference} status={booking.status}",
        )

    # -------------------------------------------------- runtimes
    def run(self, db: Session, customer: User, message: str, demo_day: date) -> AssistantReply:
        if len(message) > MAX_MESSAGE_CHARS:
            message = message[:MAX_MESSAGE_CHARS]
        if self.settings.assistant_mode == "llm":
            try:
                return self._run_llm(db, customer, message, demo_day)
            except ProviderUnavailable as exc:
                log.warning("assistant fallback: %s", exc.code)
                reply = self._fallback(db, customer, message, demo_day)
                reply.fallback_required = True
                reply.fallback_reason = "The AI service is unavailable. Use the guided form instead."
                return reply
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                log.warning("assistant produced unusable output: %s", type(exc).__name__)
                reply = self._fallback(db, customer, message, demo_day)
                reply.fallback_required = True
                reply.fallback_reason = "The AI response was unusable. Use the guided form instead."
                return reply
        return self._fallback(db, customer, message, demo_day)

    def _fallback(self, db: Session, customer: User, message: str, demo_day: date) -> AssistantReply:
        """Deterministic parser + real tools. Clearly labelled scripted, not live AI."""
        constraints = parse_constraints(message, self.settings, demo_day)
        trace: list[ToolTrace] = []
        options: list[OptionOut] = []

        missing = constraints.missing()
        if missing:
            question = (
                "Which appliance needs service?"
                if "service" in missing
                else "Which day works best for you?"
            )
            return AssistantReply(
                reply=f"I can help. {question}",
                conversation_id="scripted",
                constraints=constraints.as_dict(),
                needs_clarification=True,
                clarification_question=question,
                tool_trace=trace,
                mode="scripted",
            )

        try:
            options, summary = self._search_availability(
                db,
                customer,
                {
                    "service_code": constraints.service_code,
                    "day": constraints.day.isoformat() if constraints.day else None,
                    "after_local": constraints.after,
                    "before_local": constraints.before,
                    "max_price_cents": constraints.max_price_cents,
                },
            )
            trace.append(ToolTrace(tool="search_availability", summary=summary, ok=True))
        except ValueError as exc:
            trace.append(
                ToolTrace(tool="search_availability", summary=f"rejected: {exc}", ok=False)
            )
            return AssistantReply(
                reply="I could not search availability with those details. Try the guided form.",
                conversation_id="scripted",
                constraints=constraints.as_dict(),
                tool_trace=trace,
                fallback_required=True,
                fallback_reason="Invalid search parameters.",
                mode="scripted",
            )

        if not options:
            reason = []
            if constraints.max_price_cents:
                reason.append(f"the ${constraints.max_price_cents / 100:.0f} budget")
            if constraints.before:
                reason.append(f"the {human_time(constraints.before)} finish time")
            extra = f" within {' and '.join(reason)}" if reason else ""
            return AssistantReply(
                reply=(
                    f"I found no {self._service_name(db, constraints.service_code)}{extra} "
                    f"on {constraints.day:%a %d %b}. Try a later start or a different day."
                ),
                conversation_id="scripted",
                constraints=constraints.as_dict(),
                tool_trace=trace,
                mode="scripted",
            )

        first = options[0]
        window = []
        if constraints.after:
            window.append(f"after {first.start_local.split(', ')[1]}")
        if constraints.before:
            window.append(f"finishing before {human_time(constraints.before)}")
        window_text = f" ({' and '.join(window)})" if window else ""
        price = first.price_cents / 100
        reply = (
            f"I found {len(options)} option{'s' if len(options) > 1 else ''} for "
            f"{first.service_name} on {first.start_local.split(', ')[0]}{window_text}. "
            f"Earliest is {first.start_local.split(', ')[1]} with {first.technician_name} "
            f"at ${price:.0f} {first.currency} ({first.timezone_label}). "
            "Pick one to hold it for 15 minutes."
        )
        return AssistantReply(
            reply=reply,
            conversation_id="scripted",
            constraints=constraints.as_dict(),
            options=options,
            tool_trace=trace,
            mode="scripted",
        )

    def _service_name(self, db: Session, code: str | None) -> str:
        if not code:
            return "service"
        service = db.execute(select(Service).where(Service.code == code)).scalar_one_or_none()
        return service.name.lower() if service else "service"

    def _completion_body(self, messages: list[dict], *, tools_already_used: bool) -> dict:
        """Request body. After a tool round, force a text answer.

        Leaving `tool_choice: auto` lets some providers loop or answer in prose; a
        known tool result means the model has what it needs to answer.
        """
        body: dict = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        }
        if tools_already_used:
            body["tool_choice"] = "none"
        else:
            body["tools"] = [{"type": "function", "function": t} for t in TOOL_DEFINITIONS]
            body["tool_choice"] = "auto"
        return body

    def _run_llm(self, db: Session, customer: User, message: str, demo_day: date) -> AssistantReply:
        trace: list[ToolTrace] = []
        options: list[OptionOut] = []
        constraints_payload: dict = {}
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "system",
                "content": (
                    f"Today is {demo_day.isoformat()} in {self.settings.business_tz}. "
                    f"Business hours Mon-Fri 08:00-18:00, Sat 09:00-14:00, closed Sunday."
                ),
            },
            {"role": "user", "content": message},
        ]

        with httpx.Client(timeout=self.settings.llm_timeout_seconds) as client:
            for iteration in range(self.settings.llm_max_tool_iterations):
                try:
                    resp = client.post(
                        f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.settings.llm_api_key}",
                            "Content-Type": "application/json",
                        },
                        json=self._completion_body(messages, tools_already_used=bool(trace)),
                    )
                except httpx.HTTPError as exc:
                    raise ProviderUnavailable("The AI service is unreachable.") from exc
                if resp.status_code >= 500:
                    raise ProviderUnavailable("The AI service returned a server error.")
                if resp.status_code != 200:
                    raise ValueError(f"llm status {resp.status_code}")

                payload = resp.json()
                choice = (payload.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                tool_calls = msg.get("tool_calls") or []

                if tool_calls:
                    messages.append(msg)
                    for call in tool_calls[:3]:
                        fn = (call.get("function") or {})
                        name = fn.get("name")
                        try:
                            args = json.loads(fn.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            trace.append(
                                ToolTrace(tool=str(name), summary="malformed arguments", ok=False)
                            )
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call.get("id"),
                                    "content": json.dumps({"error": "malformed arguments"}),
                                }
                            )
                            continue
                        try:
                            if name == "search_availability":
                                found, summary = self._search_availability(db, customer, args)
                                options = found or options
                                trace.append(
                                    ToolTrace(tool=name, summary=summary, ok=True)
                                )
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": call.get("id"),
                                        "content": json.dumps(
                                            {
                                                "options": [
                                                    {
                                                        "technician": o.technician_name,
                                                        "start_local": o.start_local,
                                                        "end_local": o.end_local,
                                                        "price_cents": o.price_cents,
                                                        "timezone": o.timezone_label,
                                                    }
                                                    for o in found
                                                ]
                                            }
                                        ),
                                    }
                                )
                            elif name == "lookup_booking":
                                text, summary = self._lookup_booking(db, customer, args)
                                trace.append(ToolTrace(tool=name, summary=summary, ok=True))
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": call.get("id"),
                                        "content": json.dumps({"result": text}),
                                    }
                                )
                            else:
                                trace.append(
                                    ToolTrace(tool=str(name), summary="unsupported tool", ok=False)
                                )
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": call.get("id"),
                                        "content": json.dumps({"error": "unsupported tool"}),
                                    }
                                )
                        except ValueError as exc:
                            trace.append(ToolTrace(tool=str(name), summary=f"rejected: {exc}", ok=False))
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call.get("id"),
                                    "content": json.dumps({"error": str(exc)}),
                                }
                            )
                    continue

                content = (msg.get("content") or "").strip()
                parsed = _try_json(content)

                if parsed is not None:
                    reply_text = str(parsed.get("reply", "")).strip()
                    constraints_payload = parsed.get("constraints") or {}
                    needs_clarification = bool(parsed.get("needs_clarification"))
                    question = parsed.get("clarification_question")
                    if reply_text:
                        return AssistantReply(
                            reply=reply_text[:600],
                            conversation_id="llm",
                            constraints=constraints_payload
                            if isinstance(constraints_payload, dict)
                            else {},
                            options=options,
                            needs_clarification=needs_clarification,
                            clarification_question=str(question)[:200] if question else None,
                            tool_trace=trace,
                            mode="llm",
                        )

                # Many OpenAI-compatible providers ignore `response_format` once a
                # tool call has happened and answer in prose. The options are still
                # real (they came from the tool), so keep the answer instead of
                # discarding a successful call — but never invent structure from it.
                prose = _strip_fences(content)
                if prose:
                    if claims_mutation(prose):
                        # Never relay a false claim of a state change. Replace it
                        # with a server-authored correction and send the user to
                        # the form.
                        log.warning("llm claimed a mutation it cannot perform; correcting")
                        return AssistantReply(
                            reply=SERVER_CORRECTION,
                            conversation_id="llm",
                            constraints={},
                            options=options,
                            needs_clarification=not options,
                            tool_trace=trace,
                            fallback_required=True,
                            fallback_reason=(
                                "The assistant described an action it cannot perform. "
                                "Nothing was changed."
                            ),
                            mode="llm",
                        )
                    log.info("llm answered in prose, not JSON; keeping tool-derived options")
                    return AssistantReply(
                        reply=prose[:600],
                        conversation_id="llm",
                        constraints={},
                        options=options,
                        needs_clarification=not options,
                        tool_trace=trace,
                        mode="llm",
                    )

                raise ValueError("assistant returned no usable content")

        raise ValueError("tool iteration budget exhausted")


# Phrases that assert a completed state change. The assistant has no write tool, so
# any such claim is false by construction and must never be relayed as fact.
_MUTATION_CLAIMS = (
    "i booked",
    "i have booked",
    "i've booked",
    "booked it for you",
    "i confirmed",
    "i have confirmed",
    "i've confirmed",
    "i charged",
    "i have charged",
    "i captured",
    "i refunded",
    "i cancelled your",
    "i canceled your",
    "payment succeeded",
    "payment is complete",
    "you are booked",
    "has been booked",
    "has been confirmed",
    "has been charged",
)


def claims_mutation(text: str) -> bool:
    lowered = (text or "").lower()
    return any(phrase in lowered for phrase in _MUTATION_CLAIMS)


SERVER_CORRECTION = (
    "I can only look up availability and your own bookings — I cannot hold, book, "
    "charge or refund anything. Nothing has been changed. Choose an appointment in "
    "the options list to hold it, then pay to confirm."
)


def _strip_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"```$", "", text).strip()
    return text


def _try_json(raw: str) -> dict | None:
    """Return the parsed object when it satisfies the reply contract, else None."""
    try:
        return _strict_json(raw)
    except (ValueError, json.JSONDecodeError):
        return None


def _strict_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"```$", "", raw).strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    allowed = {"reply", "constraints", "needs_clarification", "clarification_question"}
    if set(data) - allowed:
        raise ValueError("unexpected keys in assistant output")
    return data
