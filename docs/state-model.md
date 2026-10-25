# API and state model

Base URL: `/api`. All payloads JSON. Money is **integer cents**; currency is a
3-letter code. Instants are ISO-8601 **with an offset** (naive timestamps are
rejected with 422). Display strings (`start_local`, `timezone_label`) are provided
by the server so the UI never has to guess the business timezone.

Errors are always:

```json
{"error": {"code": "SLOT_UNAVAILABLE", "message": "...", "correlation_id": "a1b2c3", "details": {}}}
```

`correlation_id` also comes back in the `X-Correlation-Id` response header and in
the server log line for the same request.

## Authentication

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/login` | `{email}`; must be a seeded demo account. Sets `ss_session` (HttpOnly) + `ss_csrf` cookies. Rate-limited 10/min/IP. |
| POST | `/api/auth/logout` | Revokes the server-side session row. Requires CSRF. |
| GET | `/api/auth/me` | 401 when signed out (the UI treats that as "signed out"). |

Every non-GET request needs `X-CSRF-Token` equal to the `ss_csrf` cookie value,
and a non-matching `Origin` (when present) is rejected.

## Public

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{status, database, paypal_mode, assistant_mode, demo_date, version}` |
| GET | `/api/config` | Business name, timezone + label, currency, demo date, hold TTL, provider modes, demo accounts |
| GET | `/api/services` | Catalogue with `price_cents`, `duration_minutes`, `required_skill` |
| GET | `/api/technicians` | Resource list with skills and colour |

## Customer (role `customer`)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/availability` | `?service_code&day&after_local&before_local&max_price_cents` → real options only |
| POST | `/api/holds` | `{service_code, technician_id, start_utc, notes}` → 201 hold. **409** `SLOT_UNAVAILABLE` on a lost race. |
| GET | `/api/holds/{id}` | Owner-only read |
| DELETE | `/api/holds/{id}` | Releases capacity, booking → `cancelled` |
| POST | `/api/holds/{id}/checkout` | Creates/reuses the provider order. Idempotent per hold. |
| POST | `/api/payments/{attemptId}/capture` | Validates the authoritative capture. Idempotent. |
| POST | `/api/payments/{attemptId}/cancel` | Only while not captured |
| GET | `/api/payments/{attemptId}` | Authoritative status for refresh recovery |
| GET | `/api/bookings` | The caller's bookings only |
| GET | `/api/bookings/{id}` | Foreign ids return **404**, not 403 |
| POST | `/api/bookings/{id}/reassignment/approve` | `{proposal_id, technician_id}` |
| POST | `/api/bookings/{id}/reassignment/decline` | `{proposal_id}` |
| POST | `/api/assistant/message` | `{message, conversation_id}` → reply + options + redacted trace. Rate-limited 20/min/user. |

Simulated-mode only (404 in sandbox mode):

| Method | Path |
|---|---|
| POST | `/api/simulated-checkout/{orderId}/approve` |
| POST | `/api/simulated-checkout/{orderId}/decline` |

## Owner (role `owner`)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/owner/timeline?day=` | Technicians + events (`hold`, `booking`, `block`) for one business day |
| GET | `/api/owner/analytics?date_from=&date_to=` | KPIs, buckets and the **full backing rows** |
| GET | `/api/owner/bookings?status=` | All bookings, filterable by status |
| POST | `/api/owner/technicians/{id}/unavailable` | `{start_utc, end_utc, reason}` → affected bookings + proposals |
| POST | `/api/owner/bookings/{id}/resolve-exception` | `{resolution: "cancelled"\|"confirmed_manually", note}` |
| GET | `/api/owner/audit?limit=` | Redacted audit trail |
| POST | `/api/owner/demo/reset` | Restores synthetic fixtures. Refused when `ALLOW_DEMO_RESET=false`. |

## Webhooks

| Method | Path | Notes |
|---|---|---|
| POST | `/api/webhooks/paypal` | Signature-verified before any state change. 401 on failure. Duplicate event ids are ignored. |

## Booking state machine

```
            POST /holds             checkout created            verified capture
 (none) ─────────────▶ held ───────────────────▶ awaiting_payment ────────────────▶ confirmed
                         │                              │                                │
                    expiry│                     cancel/expiry│                  owner: tech unavailable
                         ▼                              ▼                                ▼
                      expired                        cancelled                    needs_reassignment
                                                                                        │
                                                          customer approves a re-validated ◀┘
                                                                   replacement →
                                                                     confirmed
 verified capture whose slot is gone ──▶ payment_exception ──owner resolves──▶ cancelled | confirmed
```

Enforced in `ALLOWED_TRANSITIONS` (`backend/app/services/bookings.py`); any other
move raises `VALIDATION_ERROR`. Every transition writes an `audit_events` row.

## Payment attempt state machine

```
created ──▶ approved ──▶ captured ──▶ reconciled_ok
   │            │            └──────▶ reconciled_exception
   │            └──▶ cancelled
   └──▶ failed
```

`reconciled_ok` is the only state that can confirm a booking.

## Hold state machine

`active` → `consumed` (paid) | `released` (customer cancelled) | `expired` (TTL).

The TTL is configured by `HOLD_TTL_MINUTES` and evaluated against **server time**
only. Every availability query and hold attempt first runs the expiry reaper, so
capacity from an abandoned hold becomes bookable again without a background job.
