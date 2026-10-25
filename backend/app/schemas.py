from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import BookingStatus

BoundedText = str


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------- auth
class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=200)

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str) -> str:
        if "@" not in value or " " in value:
            raise ValueError("must be an email address")
        return value.lower()


class UserOut(StrictModel):
    id: str
    email: str
    display_name: str
    role: Literal["customer", "owner"]


class DemoUser(StrictModel):
    email: str
    display_name: str
    role: str
    hint: str


class ConfigOut(StrictModel):
    business_name: str
    timezone: str
    timezone_label: str
    currency: str
    demo_date: date
    hold_ttl_minutes: int
    paypal_mode: Literal["simulated", "sandbox"]
    assistant_mode: Literal["scripted", "llm"]
    demo_users: list[DemoUser]
    supports_webhooks: bool


# ---------------------------------------------------------------- catalogue
class ServiceOut(StrictModel):
    id: str
    code: str
    name: str
    duration_minutes: int
    price_cents: int
    currency: str
    required_skill: str
    description: str


class TechnicianOut(StrictModel):
    id: str
    name: str
    initials: str
    skills: list[str]
    color: str


# ---------------------------------------------------------------- availability
class OptionOut(StrictModel):
    option_id: str
    technician_id: str
    technician_name: str
    technician_color: str
    service_id: str
    service_code: str
    service_name: str
    start_utc: datetime
    end_utc: datetime
    start_local: str
    end_local: str
    timezone_label: str
    price_cents: int
    currency: str
    duration_minutes: int
    within_budget: bool


class AvailabilityQuery(StrictModel):
    service_code: str = Field(min_length=2, max_length=40)
    day: date
    after_local: str | None = Field(default=None, max_length=5)
    before_local: str | None = Field(default=None, max_length=5)
    max_price_cents: int | None = Field(default=None, ge=0, le=100_000)


# ---------------------------------------------------------------- holds
class HoldCreate(StrictModel):
    service_code: str = Field(min_length=2, max_length=40)
    technician_id: str = Field(min_length=2, max_length=40)
    start_utc: datetime
    notes: str = Field(default="", max_length=500)

    @field_validator("start_utc")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("start_utc must include a timezone offset")
        return value


class HoldOut(StrictModel):
    id: str
    status: str
    technician_id: str
    technician_name: str
    service_name: str
    start_utc: datetime
    end_utc: datetime
    start_local: str
    end_local: str
    timezone_label: str
    price_cents: int
    currency: str
    expires_at: datetime
    seconds_remaining: int
    booking_id: str


# ---------------------------------------------------------------- payment
class CheckoutOut(StrictModel):
    attempt_id: str
    booking_id: str
    status: str
    provider_mode: Literal["simulated", "sandbox"]
    amount_cents: int
    currency: str
    approve_url: str | None = None
    simulated_token: str | None = None
    order_reference: str | None = None
    expires_at: datetime


class CaptureIn(StrictModel):
    provider_order_id: str | None = Field(default=None, max_length=64)


class PaymentOut(StrictModel):
    attempt_id: str
    booking_id: str
    status: str
    provider_mode: str
    amount_cents: int
    captured_amount_cents: int | None
    currency: str
    failure_reason: str
    booking_status: str


# ---------------------------------------------------------------- bookings
class BookingOut(StrictModel):
    id: str
    reference: str
    status: BookingStatus
    status_label: str
    technician_id: str
    technician_name: str
    technician_color: str
    service_name: str
    service_code: str
    start_utc: datetime
    end_utc: datetime
    start_local: str
    end_local: str
    timezone_label: str
    price_cents: int
    currency: str
    notes: str
    customer_name: str = ""
    needs_attention: bool
    exception_reason: str
    created_at: datetime
    confirmed_at: datetime | None
    payment_status: str | None
    proposal: ProposalOut | None = None


class ProposalCandidate(StrictModel):
    technician_id: str
    technician_name: str
    technician_color: str
    available: bool
    note: str


class ProposalOut(StrictModel):
    id: str
    status: str
    reason: str
    original_technician_id: str
    created_at: datetime
    candidates: list[ProposalCandidate]


class ReassignmentApprove(StrictModel):
    proposal_id: str = Field(min_length=3, max_length=40)
    technician_id: str = Field(min_length=2, max_length=40)


class ReassignmentDecline(StrictModel):
    proposal_id: str = Field(min_length=3, max_length=40)


# ---------------------------------------------------------------- assistant
class AssistantMessage(StrictModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = Field(default=None, max_length=60)


class ToolTrace(StrictModel):
    tool: str
    summary: str
    ok: bool
    redacted: bool = True


class AssistantReply(StrictModel):
    reply: str
    conversation_id: str
    constraints: dict
    options: list[OptionOut] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    tool_trace: list[ToolTrace] = Field(default_factory=list)
    fallback_required: bool = False
    fallback_reason: str | None = None
    mode: Literal["scripted", "llm"] = "scripted"


# ---------------------------------------------------------------- owner
class TimelineEvent(StrictModel):
    id: str
    kind: Literal["hold", "booking", "block"]
    technician_id: str
    title: str
    start_utc: datetime
    end_utc: datetime
    status: str
    status_label: str
    color: str
    customer_name: str | None = None
    service_name: str | None = None
    reference: str | None = None
    price_cents: int | None = None
    needs_attention: bool = False


class TimelineOut(StrictModel):
    day: date
    timezone_label: str
    technicians: list[TechnicianOut]
    events: list[TimelineEvent]
    generated_at: datetime


class AnalyticsBucket(StrictModel):
    key: str
    label: str
    booking_count: int
    revenue_cents: int


class AnalyticsRow(StrictModel):
    booking_id: str
    reference: str
    status: str
    status_label: str
    service_name: str
    technician_name: str
    customer_name: str
    day: date
    start_local: str
    price_cents: int
    currency: str
    counted_as_revenue: bool
    needs_attention: bool
    exception_reason: str


class AnalyticsOut(StrictModel):
    date_from: date
    date_to: date
    currency: str
    confirmed_count: int
    confirmed_revenue_cents: int
    captured_all_cents: int
    exception_cents: int
    exception_count: int
    needs_reassignment_count: int
    by_service: list[AnalyticsBucket]
    by_technician: list[AnalyticsBucket]
    by_status: list[AnalyticsBucket]
    rows: list[AnalyticsRow]
    notes: list[str]


class UnavailableIn(StrictModel):
    start_utc: datetime
    end_utc: datetime
    reason: str = Field(default="Unavailable", max_length=200)

    @field_validator("end_utc")
    @classmethod
    def _order(cls, value: datetime, info):
        start = info.data.get("start_utc")
        if start and value <= start:
            raise ValueError("end_utc must be after start_utc")
        return value


class UnavailableOut(StrictModel):
    block_id: str
    technician_id: str
    affected_booking_ids: list[str]
    proposals_created: int
    unresolved: int


class DisruptionResult(StrictModel):
    block_id: str
    technician_id: str
    technician_name: str
    affected_booking_ids: list[str]
    proposals_created: list[str]
    unresolved_booking_ids: list[str]


class ResolveExceptionIn(StrictModel):
    resolution: Literal["cancelled", "confirmed_manually"]
    note: str = Field(default="", max_length=300)


class HealthOut(StrictModel):
    status: Literal["ok", "degraded"]
    database: str
    paypal_mode: str
    assistant_mode: str
    demo_date: date
    version: str


BookingOut.model_rebuild()
