# Architecture

Status vocabulary used throughout the docs: **IMPLEMENTED** · **VERIFIED_CONNECTED** ·
**VERIFIED_FIXTURE** · **SIMULATED** · **BLOCKED** · **NOT RUN**.

This document describes the POC as built. It is not a production design review.
Known deployment limits are in [`deployment.md`](./deployment.md); sponsor status is in
[`integration-status.md`](./integration-status.md).

---

## 1. Topology

```
┌──────────────────────────┐
│ Angular 20 SPA           │  customer flow, owner console, Bryntum timeline
│ :4200 (dev proxy → /api) │  no business rules, no secrets
└────────────┬─────────────┘
             │ HTTP, session cookie or bearer token
┌────────────▼─────────────┐
│ FastAPI                  │  the only component that decides anything
│ :8000                    │
│  api/         routes     │
│  services/    rules      │  ← validation, state machines, money
│  models.py    SQLAlchemy │
└───┬───────────┬──────────┘
    │           │
    │           ├──▶ SQLite (local) / Postgres — system of record
    │           │
    │           └──▶ PayPal Orders v2 + Webhooks (sandbox only, server-side)
    │                 client secret never leaves the backend
    │
    └──▶ OpenAI-compatible chat endpoint (assistant, optional)
          tools are backend-validated; the model cannot write state
```

**Layer rules that are actually enforced:**

| Rule | Where |
|---|---|
| Routes validate shape and identity, then call a service | `backend/app/api/*.py` |
| Services own every business decision | `backend/app/services/*.py` |
| The model never mutates state directly | `assistant.py` exposes read tools + explicit user-confirmed actions |
| Price and currency are server-calculated | `bookings.py` from `Service.price_cents` |
| Money is integer minor units | `price_cents`, `amount_cents` everywhere |

The frontend is a client, not an authority. Every screen can be refetched from the
canonical backend state; nothing is held only in browser memory.

---

## 2. Persistence model

`backend/app/models.py`. All timestamps are stored UTC via a `UtcDateTime` type and
converted for display with the configured business timezone.

| Table | Purpose | Key invariant |
|---|---|---|
| `users` | synthetic demo identities + role | `role ∈ {customer, owner}` |
| `auth_sessions` | server-side sessions | hashed token, TTL |
| `demo_clock` | demo "now" | keeps seeded dates stable |
| `services` | 3 fixed-price services | `price_cents`, `duration_minutes` |
| `technicians` | 3 technicians + skills | skill must match service category |
| `technician_blocks` | owner-declared unavailability | half-open `[start, end)` |
| `holds` | temporary slot reservation | `status`, `expires_at_utc` |
| `bookings` | the appointment | `status`, unique `reference` |
| `slot_blocks` | **race-safe slot claim** | partial unique index, see §4 |
| `payment_attempts` | one row per PayPal order attempt | `provider_order_id`, idempotency keys |
| `processed_payment_events` | webhook/callback dedupe | primary key on `event_id` |
| `reassignment_proposals` | disruption handling | `status`, `proposed_start_utc` |
| `audit_events` | redacted operational trail | never holds secrets or PANs |

`slot_blocks` is the concurrency control. It is deliberately separate from
`bookings` so that a slot can be claimed before a booking row is final, and so that
releasing capacity is a single indexed update.

---

## 3. State machines

Enforced centrally by `ALLOWED_TRANSITIONS` in
[`backend/app/services/bookings.py`](../backend/app/services/bookings.py); any other
move raises `VALIDATION_ERROR`. Every transition writes an `audit_events` row.

### Booking

```
held ──▶ awaiting_payment ──▶ confirmed ──▶ needs_reassignment ──▶ confirmed
 │              │                  │                  │
 │              ├──▶ payment_exception ──▶ confirmed (owner resolves)
 │              │                  │
 │              └──▶ cancelled     └──▶ cancelled
 └──▶ expired
```

| From | Allowed to |
|---|---|
| `held` | `awaiting_payment`, `expired`, `cancelled` |
| `awaiting_payment` | `confirmed`, `cancelled`, `expired`, `payment_exception` |
| `confirmed` | `needs_reassignment`, `cancelled` |
| `needs_reassignment` | `confirmed`, `needs_reassignment`, `cancelled` |
| `payment_exception` | `cancelled`, `confirmed` |
| `cancelled` | — terminal |
| `expired` | — terminal |

### Payment attempt

```
created ──▶ approved ──▶ captured ──▶ reconciled_ok
   │            │            └──────▶ reconciled_exception
   │            └──▶ cancelled
   └──▶ failed
```

`reconciled_ok` is the **only** state that may confirm a booking. A browser redirect,
a screenshot, or an assistant statement is never accepted as payment evidence — only a
capture response read back from PayPal and validated field by field.

### Hold

`active` → `consumed` (paid) | `released` (customer cancelled) | `expired` (TTL).

TTL comes from `HOLD_TTL_MINUTES` and is evaluated against **server time** only. Every
availability query and hold attempt first runs the expiry reaper, so an abandoned hold
returns capacity without a background worker.

### Reassignment proposal

`proposed` → `accepted` | `declined` | `unresolved` | `superseded`.

Acceptance re-validates availability *and* re-claims the slot inside one transaction, so
a proposal that looked valid when created cannot confirm a slot taken in the meantime.

---

## 4. Concurrency and transactional guarantees

The rule: **"check then insert" is not enough.** Slot acquisition is protected by a
partial unique index, not by an application-level read.

```python
Index(
    "ux_slot_blocks_active",
    "technician_id",
    "slot_start_utc",
    unique=True,
    sqlite_where=text("active = 1"),
    postgresql_where=text("active = 1"),
)
```

Two concurrent customers targeting one slot both attempt the insert; exactly one
commits, the loser gets a constraint violation translated into
`409 SLOT_UNAVAILABLE`. Proven by `tests/test_concurrency_http.py`.

| Guarantee | Mechanism | Test |
|---|---|---|
| One winner per slot | partial unique index | `test_concurrency_http.py` |
| No double booking on retry | unique hold/booking coupling + reaper | `test_durability.py` |
| No duplicate charge | distinct `PayPal-Request-Id` per logical op | `test_paypal_adapter.py` |
| No duplicate booking from repeated callbacks | `processed_payment_events` PK | `test_payment_integrity.py` |
| Expired hold cannot confirm | status check inside the confirm transaction | `test_hold_lifecycle.py` |

### Payment/hold race — the documented behaviour

If money is captured after the slot is no longer valid, the system **does not** fabricate
a confirmed appointment and **does not** lose the money record. It moves the booking to
`payment_exception` with a reason and surfaces it in the owner console for manual
resolution. Refunds are explicitly out of scope for this POC and documented as manual.

---

## 5. Payment flow

```
customer            backend                         PayPal
   │  select slot        │                              │
   ├────────────────────▶│ hold + booking(held)          │
   │                     ├── create order ─────────────▶│
   │  approval URL       │◀──────── order id ────────────┤
   │◀────────────────────┤ booking(awaiting_payment)     │
   ├── approve ──────────────────────────────────────────▶│
   │                     │◀── capture / webhook ─────────┤
   │                     │ verify signature + amounts    │
   │                     ├── reconcile ─────────────────▶│
   │                     │ booking(confirmed)            │
   │◀── confirmed ───────┤                              │
```

Security properties:

- Client id is public; **client secret and access tokens stay server-side**.
- The order is bound to the authenticated booking owner, the hold, the expected amount,
  and the configured merchant.
- Capture validation checks completion state and amount/currency against the stored
  intent — not against the client's claim.
- Webhooks are verified with PayPal's signature endpoint before processing, then
  deduplicated by event id; duplicate and out-of-order events are safe.
- Ambiguous capture timeouts are **reconciled before retrying**; the code never blindly
  creates a second charge.

Detail: [`state-model.md`](./state-model.md) · [`security-review.md`](./security-review.md).

---

## 6. Assistant boundary — what AI decides vs what the backend enforces

| Question | Answered by |
|---|---|
| What appointments exist? | Backend — the assistant may only *read* them |
| What does a service cost? | Backend (`services.price_cents`) |
| Is this slot actually free? | Backend, under the unique index |
| Did the customer pay? | Backend, from a validated PayPal capture |
| Which constraints did the user imply? | **Assistant** — an interpretation, not a fact |
| Which option to pick? | **Customer** — explicit selection required |
| Whether to accept a reassignment? | **Customer** — explicit approval required |

The assistant exposes a small typed tool set (service lookup, availability search,
booking-status lookup, reassignment proposal). Identity is bound server-side, so a tool
call cannot address another customer's object. Mutating steps require an explicit user
action in the UI; the model cannot hold, confirm, charge, or reassign on its own.

Failure behaviour is a visible fallback: if the provider errors, times out, or returns
malformed output, the UI offers a form-based continuation and says so. The assistant
never invents availability, never asserts a payment succeeded, and never claims a state
change it did not perform.

Detail: [`threat-model.md`](./threat-model.md).

---

## 7. Disruption and reassignment

Owner-only action: mark a technician unavailable for a window.

1. The service finds bookings that intersect the block.
2. For each, it proposes a qualified alternative at the **same time and price**.
3. The existing paid booking is preserved — `needs_reassignment`, never deleted.
4. The customer sees the proposal and must explicitly approve.
5. On approval, availability is re-validated and the replacement slot is claimed
   atomically.
6. If nothing remains, the proposal is `unresolved` and the UI says so honestly rather
   than showing a confident state that the backend cannot back up.

Customers cannot invoke the disruption action; this is enforced by role check on the
route, demonstrated in `tests/test_authorization.py`.

---

## 8. Request lifecycle and failure surfaces

- Every mutating route is idempotent or explicitly non-retryable. Read tools retry with
  a bounded budget; writes do not retry blindly.
- Errors return an actionable message plus a correlation id, never a provider payload
  or credential.
- Rate limits apply to the assistant and payment endpoints.
- CORS is restricted to `APP_ORIGIN`; cookies are `HttpOnly`, `SameSite=Lax`, and
  `Secure` when `COOKIE_SECURE=true`.
- Logs and audit rows are redacted at the key level; the test suite asserts no secret
  appears in preflight or error output.

---

## 9. Modes

| Mode | Payment | Assistant | Use |
|---|---|---|---|
| `simulated` | labelled simulated provider | `scripted` or `llm` | offline rehearsal, no network required |
| `sandbox` | **real** PayPal Sandbox | `scripted` or `llm` | connected verification and demo |

Mode is chosen explicitly in configuration and shown in the UI. The app **never**
silently switches modes after a provider failure, and simulated records are never mixed
into connected ones. `PAYPAL_MODE=live` is refused at startup.

---

## 10. Deliberate non-goals

Not built, and not claimed: marketplace, real payments, subscriptions, route
optimization, full CRM, autonomous refunds, multi-tenant auth, horizontal scaling, or
hosted deployment. See [`deployment.md`](./deployment.md) for what a real deployment
would additionally require.
