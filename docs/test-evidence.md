# Test evidence

Recorded **2026-10-25**. Commands are run from the repository root unless noted.

## Hermetic test suite

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

```
70 passed in 8.62s
```

Everything below runs with **no network access** and no real credentials.

| File | Tests | What it actually proves |
|---|---|---|
| `tests/test_happy_path.py` | 4 | Conversational request → real options honouring *after 4 PM / before 6 PM / ≤ $80* → hold → checkout → approve → verified capture → persistent `confirmed`. Plus a "refresh" that re-reads authoritative state, and a direct DB read after the request. |
| `tests/test_hold_lifecycle.py` | 4 | Cancelled checkout does **not** confirm and frees capacity for re-booking; an expired hold cannot be confirmed and its cells are released; **two customers race for one slot and exactly one wins**; an offset-but-overlapping slot is rejected. |
| `tests/test_payment_integrity.py` | 10 | Altered amount → `AMOUNT_MISMATCH` → `payment_exception`; altered currency → `CURRENCY_MISMATCH`; foreign attempt → 404; duplicate capture ×3 → one attempt, one amount; duplicate checkout → same order; capture after expiry → recorded money **and** a visible exception; forged webhook → 401 and no state change; signed webhook confirms; replay with the same id is deduped; replay with a **new id** still cannot double-charge; webhook for an unknown order is ignored; unapproved order cannot be captured. |
| `tests/test_authorization.py` | 13 | Unauthenticated access rejected; cross-customer read/pay/cancel all 404; listings never leak; customer blocked from every owner route **and** from creating a block; owner blocked from customer routes; CSRF header required and value-matched; cross-origin write rejected; unknown email rejected; `extra="forbid"` rejects a client-supplied price; oversized input rejected; naive datetime rejected; logout kills the session; unqualified technician rejected; outside-business-hours rejected. |
| `tests/test_reassignment.py` | 6 | Disruption preserves the paid booking and its price while raising a proposal; customer approval persists the new technician and clears the warning; decline keeps `needs_reassignment`; another customer cannot approve (404); an un-offered technician is refused; **when every alternative is busy the proposal is `unresolved`** and no replacement is invented. |
| `tests/test_assistant_abuse.py` | 15 | 5 injection payloads create no payment attempt and no booking, and every tool call stays inside the allow-list; cross-customer lookup leaks nothing; offered options never overlap an active reservation; missing service yields a clarifying question; no availability is reported honestly; the demo sentence parses to the right constraints; 5 malformed model outputs rejected by `_strict_json`; provider outage → labelled fallback **with real options**; malformed LLM output → fallback; assistant endpoint rate-limited (429). |
| `tests/test_durability.py` | 4 | State survives a full app restart (engines disposed, caches reset, same SQLite file) and is verified by reading the DB directly; analytics totals equal the sum of the rows they summarise, and bucket totals match the headline; timeline and analytics agree after a mutation; demo reset is owner-only and restores fixtures. |
| `tests/test_paypal_adapter.py` | 11 | Real adapter request shape: `/v2/checkout/orders` with server-derived `75.00`, `PayPal-Request-Id`, `custom_id`/`invoice_id`, merchant payee, and **no client-supplied price**; capture parsing of the settled amount; 422 → `ORDER_NOT_CAPTURABLE`; transport failure → ambiguous capture flag; bad credentials → provider unavailable; webhook verification requires all five headers and calls PayPal's endpoint with the right body; `FAILURE` is rejected; `PAYPAL_MODE=live` raises at config load; sandbox without credentials raises; provider selection respects mode. |

### Notes on test design

- Assertions are behavioural (state, counts, amounts, HTTP codes), not
  implementation-shaped. Each race/dedup test asserts on the **database** after the
  request, not just on the response body.
- The rate-limiter fixture resets process-global buckets between tests; without it
  the limiter (correctly) leaks across tests.
- Concurrency is proven through the database constraint directly
  (`pytest.raises(Conflict)` after a committed competing claim), which is the same
  path two real requests take. A threaded HTTP race was not run: SQLite serialises
  writers, so it would test the lock, not the invariant.

## Frontend

_(filled in after the frontend build completes — see below)_

## What is deliberately **NOT RUN**

| Item | Reason | Where it is recorded |
|---|---|---|
| Live PayPal Sandbox order + capture | No sandbox credentials in this environment | [`integration-status.md`](./integration-status.md) |
| Live PayPal webhook delivery | Needs a public URL | [`integration-status.md`](./integration-status.md) |
| Real LLM assistant (`ASSISTANT_MODE=llm`) | No `LLM_API_KEY` | [`integration-status.md`](./integration-status.md) |
| Bryntum licensed build | Private registry returned HTTP 401 | [`vendor-verification.md`](./vendor-verification.md) |
| Hosted deployment | Not attempted | [`deployment.md`](./deployment.md) |
| Real-browser E2E (Playwright) | No browser automation in this environment | this table |

A simulated payment is never presented as sandbox evidence. The offline
rehearsal mode is labelled as such in the API (`provider_mode: "simulated"`), in
the UI badge, and in every document.
