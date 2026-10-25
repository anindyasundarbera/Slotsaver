# Test evidence

Recorded **2026-10-25**, updated **2026-10-26** after connected sandbox and live-LLM
verification. Commands are run from the repository root unless noted.

## Hermetic test suite

```bash
.venv/bin/python -m pytest backend/tests -q
```

```
126 passed, 1 warning in 11.85s
```

Everything below runs with **no network access** and no real credentials.

| File | Tests | What it actually proves |
|---|---|---|
| `tests/test_happy_path.py` | 4 | Conversational request → real options honouring *after 4 PM / before 6 PM / ≤ $80* → hold → checkout → approve → verified capture → persistent `confirmed`. Plus a "refresh" that re-reads authoritative state, and a direct DB read after the request. |
| `tests/test_hold_lifecycle.py` | 4 | Cancelled checkout does **not** confirm and frees capacity for re-booking; an expired hold cannot be confirmed and its cells are released; **two customers race for one slot and exactly one wins**; an offset-but-overlapping slot is rejected. |
| `tests/test_payment_integrity.py` | 10 | Altered amount → `AMOUNT_MISMATCH` → `payment_exception`; altered currency → `CURRENCY_MISMATCH`; foreign attempt → 404; duplicate capture ×3 → one attempt, one amount; duplicate checkout → same order; capture after expiry → recorded money **and** a visible exception; forged webhook → 401 and no state change; signed webhook confirms; replay with the same id is deduped; replay with a **new id** still cannot double-charge; webhook for an unknown order is ignored; unapproved order cannot be captured. |
| `tests/test_authorization.py` | 13 | Unauthenticated access rejected; cross-customer read/pay/cancel all 404; listings never leak; customer blocked from every owner route **and** from creating a block; owner blocked from customer routes; CSRF header required and value-matched; cross-origin write rejected; unknown email rejected; `extra="forbid"` rejects a client-supplied price; oversized input rejected; naive datetime rejected; logout kills the session; unqualified technician rejected; outside-business-hours rejected. |
| `tests/test_reassignment.py` | 6 | Disruption preserves the paid booking and its price while raising a proposal; customer approval persists the new technician and clears the warning; decline keeps `needs_reassignment`; another customer cannot approve (404); an un-offered technician is refused; **when every alternative is busy the proposal is `unresolved`** and no replacement is invented. |
| `tests/test_assistant_abuse.py` | 20 | 5 injection payloads create no payment attempt and no booking, and every tool call stays inside the allow-list; cross-customer lookup leaks nothing; offered options never overlap an active reservation; missing service yields a clarifying question; no availability is reported honestly; the demo sentence parses to the right constraints; 5 malformed model outputs rejected by `_strict_json`; provider outage → labelled fallback **with real options**; malformed LLM output → fallback; assistant endpoint rate-limited (429). |
| `tests/test_durability.py` | 4 | State survives a full app restart (engines disposed, caches reset, same SQLite file) and is verified by reading the DB directly; analytics totals equal the sum of the rows they summarise, and bucket totals match the headline; timeline and analytics agree after a mutation; demo reset is owner-only and restores fixtures. |
| `tests/test_paypal_integration.py` | 39 | Operation-key separation, approved sandbox origin enforcement, experience-context vs application-context order body, webhook enable gate returning 503, preflight output never containing a secret value, prefix or response body, and rejection of mis-shaped `PAYPAL_MERCHANT_ID` / wrong host values (e.g. `sandbox.paypal.com`) at config load. |
| `tests/test_concurrency_http.py` | 2 | **Real parallel HTTP race:** two independent sessions released by a thread barrier against one slot → exactly `[201, 409]`, the loser gets `SLOT_UNAVAILABLE` and holds no booking, and the database shows exactly one active cell. Plus a direct test that the **partial unique index itself** rejects a duplicate claim and still allows re-claiming a released cell. |
| `tests/test_regressions.py` | 9 | Unaligned `start_utc` rejected; retry after a failed attempt; late capture releases capacity instead of orphaning it; force-confirm must win the capacity claim; a losing racer leaves no dangling cells. |
| `tests/test_dotenv.py` | 4 | `backend/.env` is actually loaded at startup; an exported environment variable overrides the file value; `SLOTSAVER_SKIP_DOTENV=1` disables loading so fixtures cannot leak; a missing file is not an error. |
| `tests/test_paypal_adapter.py` | 11 | Real adapter request shape: `/v2/checkout/orders` with server-derived `75.00`, `PayPal-Request-Id`, `custom_id`/`invoice_id`, merchant payee, and **no client-supplied price**; capture parsing of the settled amount; 422 → `ORDER_NOT_CAPTURABLE`; transport failure → ambiguous capture flag; bad credentials → provider unavailable; webhook verification requires all five headers and calls PayPal's endpoint with the right body; `FAILURE` is rejected; `PAYPAL_MODE=live` raises at config load; sandbox without credentials raises; provider selection respects mode. |

### Added 2026-10-26 (defects found against the real providers)

| Test | Proves |
|---|---|
| Prose-after-tool-call fallback | When a real provider answers tool results in prose instead of strict JSON, the **real tool-derived options are kept** rather than discarded. Regression for the live-LLM defect. |
| Mutation-claim guard | Assistant output claiming it held, confirmed, charged or refunded is rejected; no state change occurs. |
| Payee / merchant validation | A malformed merchant id or a buyer-facing host is refused at startup with an actionable message instead of an opaque 400/503 at checkout. |

### Proving the concurrency test is real

A test that passes for the wrong reason is worse than no test. Both concurrency
tests were **mutation-checked**:

1. `test_capacity_index_itself_rejects_a_duplicate_claim` was added because the
   end-to-end HTTP race can be satisfied by the service layer's pre-check rather
   than by the index.
2. Temporarily flipping the index to `unique=False` in `app/models.py` makes
   `test_capacity_index_itself_rejects_a_duplicate_claim` **fail**, and restoring
   it makes it pass. `app/models.py` is unmodified in the committed tree.

The HTTP race test is stable across five consecutive runs.

### Notes on test design

- Assertions are behavioural (state, counts, amounts, HTTP codes), not
  implementation-shaped. Each race/dedup test asserts on the **database** after the
  request, not just on the response body.
- The rate-limiter fixture resets process-global buckets between tests; without it
  the limiter (correctly) leaks across tests.
- Concurrency is proven three ways: the database constraint directly
  (`pytest.raises(Conflict)` after a committed competing claim), a real threaded
  HTTP race between two sessions, and a direct index assertion that survives
  removal of the service-layer pre-check.

## Frontend

```bash
cd frontend && npm run build
```

```
Application bundle generation complete. [9.595 seconds] — dist/frontend emitted
```

Production build succeeds (Angular 20, no errors). Browser behaviour verified in a
real Chromium session: the Bryntum timeline renders 3 technician rows on the correct
8 AM–6 PM axis with 5 events on the demo day and no CSS fallback engaged; day
navigation rebuilds with the correct events. Recorded in
[`integration-evidence.md`](./integration-evidence.md) §4.

## What is deliberately **NOT RUN**

| Item | Reason | Where it is recorded |
|---|---|---|
| Live PayPal **buyer approval + capture** | Requires an interactive sandbox *personal* buyer login; no human was present to approve the checkout page | [`integration-status.md`](./integration-status.md), [`e2e-sandbox.md`](./e2e-sandbox.md) |
| Live PayPal webhook delivery | Needs a public HTTPS callback and a registered subscription; no tunnel was authorised | [`integration-status.md`](./integration-status.md) |
| Bryntum licensed build | Private registry returned HTTP 401 | [`vendor-verification.md`](./vendor-verification.md) |
| Hosted deployment | Not attempted; deployment is a separate authorisation | [`deployment.md`](./deployment.md) |

**No longer NOT RUN** (was listed here on 2026-10-25, now connected):

| Item | Now | Evidence |
|---|---|---|
| PayPal OAuth + real sandbox order create/read | **VERIFIED_CONNECTED** | [`integration-evidence.md`](./integration-evidence.md) §1 |
| Real LLM assistant (`ASSISTANT_MODE=llm`) | **VERIFIED_CONNECTED** | [`integration-evidence.md`](./integration-evidence.md) §2b |
| Real-browser widget check | **VERIFIED_CONNECTED** (local Chromium via Playwright) | [`integration-evidence.md`](./integration-evidence.md) §4 |

A simulated payment is never presented as sandbox evidence. The offline
rehearsal mode is labelled as such in the API (`provider_mode: "simulated"`), in
the UI badge, and in every document.
