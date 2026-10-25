# Threat model

Scope: the POC as built. Out of scope: production hardening, live money movement,
multi-tenant isolation beyond the single demo business.

Assets: booking integrity, payment truth, other customers' booking data, the PayPal
client secret, the LLM key, provider access tokens.

## STRIDE summary

| Threat | Vector | Control | Test |
|---|---|---|---|
| **Spoofing** | Attacker logs in as another demo user | Only seeded emails are accepted; sessions are server-side rows with a hashed token; the cookie is `HttpOnly`+`SameSite=Lax` | `test_unknown_email_cannot_log_in`, `test_logout_invalidates_the_session` |
| **Spoofing** | Forged PayPal webhook | `verify-webhook-signature` must return `SUCCESS` before any state change | `test_forged_webhook_signature_is_rejected` |
| **Tampering** | Client sends its own price | `HoldCreate` has `extra="forbid"`; price comes from the catalogue row | `test_request_schema_rejects_unknown_and_oversized_fields` |
| **Tampering** | Amount/currency changed mid-flight | Capture validated against the **persisted** expected amount, currency, order id, custom id, merchant | `test_altered_amount_is_refused_and_flagged`, `test_altered_currency_is_refused` |
| **Tampering** | Forged "success" redirect | The redirect is never read. Only the capture API / a verified webhook settles a booking | `test_unapproved_order_cannot_be_captured` |
| **Repudiation** | "I never booked that" | `audit_events` records every transition with actor, role, subject, correlation id | `test_timeline_and_analytics_agree_after_a_mutation` |
| **Information disclosure** | Enumerate other customers' bookings | Foreign objects return **404**; listings are filtered by `customer_id` on the server | `test_one_customer_cannot_read_another_customers_booking` |
| **Information disclosure** | Assistant leaks another customer's data | Tools bind the session identity; the lookup is scoped by `customer_id` | `test_assistant_cannot_read_another_customers_booking` |
| **Information disclosure** | Secrets in logs | Audit payloads are redacted by key; PayPal bodies are never logged; auth headers excluded | `app/services/audit.py::redact` |
| **Denial of service** | Brute-force login / assistant spam / payment hammering | Per-key token buckets: login 10/min/IP, assistant 20/min/user, payment 15/min/user | `test_rate_limit_applies_to_assistant` |
| **Elevation of privilege** | Customer calls owner endpoints | `require_owner` on the server; the UI guard is cosmetic only | `test_customer_cannot_use_owner_endpoints` |
| **Elevation of privilege** | Owner acts as a customer | `require_customer` on customer routes | `test_owner_cannot_act_as_customer` |
| **CSRF** | Cross-site POST from a malicious page | Double-submit token header **and** `Origin` check | `test_csrf_header_is_required_for_writes`, `test_cross_origin_write_is_rejected` |

## Prompt injection

The assistant is treated as an **untrusted planner**. Its output is data.

1. **Tool allow-list.** Only `search_availability` and `lookup_booking` exist. There
   is no write tool, no SQL tool, no shell, no secret access.
2. **Schema validation.** Tool arguments are validated (`service_code` must be in
   the catalogue enum, `day` must parse as ISO, budget is coerced to int).
3. **Server-side policy.** Authorisation is re-derived from the session, never from
   model output. The model cannot name a `customer_id`.
4. **No trust in prose.** A reply is never used to change state. A sentence saying
   "payment succeeded" has no effect; only `finalize_capture` can confirm.
5. **Bounded loops.** `LLM_MAX_TOOL_ITERATIONS` (default 4), per-call timeout, and
   a strict JSON contract with `extra="forbid"`-style key checking.
6. **Fail closed to a form.** Malformed output or a provider outage returns
   `fallback_required` and the UI switches to the guided form.

Evidence: 5 injection payloads × (no new payment attempt, no new confirmed booking,
no tool outside the allow-list) in `tests/test_assistant_abuse.py`.

## Race conditions and unsafe retries

| Case | Behaviour |
|---|---|
| Two customers, one slot | Partial unique index on `(technician_id, slot_start_utc) WHERE active=1` — the DB decides, not a pre-check |
| Duplicate capture | `finalize_capture` short-circuits when the attempt is already settled; only one attempt row exists per hold |
| Duplicate webhook (same id) | Primary-key insert fails → `duplicate`, no effect |
| Duplicate webhook (new id, same order) | Settlement funnel is idempotent on the attempt → still one capture |
| Capture timeout | `ProviderUnavailable(details.ambiguous=true)`; the attempt stays `approved` and is reconciled by reading the order |
| Retrying writes | Customer-initiated only. Nothing auto-retries a capture. |
| Capture lands after the hold expired | Money is recorded; booking → `payment_exception`; owner task raised. Never a fabricated confirmation. |

## Accidental live-payment configuration

`load_settings()` raises `ConfigError` if `PAYPAL_MODE` is anything other than
`simulated` or `sandbox`. Live mode cannot be enabled by environment variable, and
`PayPalProvider` asserts the sandbox base URL is the only one it uses.

## Known gaps (deliberate, documented)

- **No refunds.** A `payment_exception` is resolved manually (owner marks it
  cancelled or confirmed). Money movement back to the customer is out of scope.
- **In-process rate limiting.** Single-process only; a multi-worker deployment needs
  a shared store (Redis) or an edge limiter.
- **In-process simulated provider.** Its order store is memory-resident by design;
  in `sandbox` mode PayPal is the store of record, so this does not affect the real path.
- **`confirmed_manually` is an owner override** and does not create a payment record.
  It is audited and must not be used to launder an unverified capture.
