# Integration evidence

Recorded **2026-10-26**. Commands are run from the repository root.
Vocabulary: **DOCUMENTED** · **IMPLEMENTED** · **VERIFIED_CONNECTED** ·
**VERIFIED_FIXTURE** · **SIMULATED** · **BLOCKED** · **DEFERRED**.

Connected evidence (touching a real vendor) is kept strictly separate from
fixtures. Nothing below claims a vendor integration from key presence.

## 1. PayPal — configuration and readiness

| Check | Command | Outcome | Class |
|---|---|---|---|
| Static preflight, simulated mode | `.venv/bin/python -m app.preflight` (from `backend/`) | `paypal_mode: SIMULATED`, `paypal_base_url: OK`, `paypal_webhooks: DISABLED`, `optional_*: DEFERRED` ×6 | VERIFIED_FIXTURE |
| Preflight secret hygiene | `PAYPAL_CLIENT_ID=AbC123SecretLookingValue PAYPAL_CLIENT_SECRET=SuperSecret987 PAYPAL_MERCHANT_ID=MERCHANTXYZ … -m app.preflight` | Output contains none of those values (grep-scanned). Reported only `OK (both present)` | VERIFIED_FIXTURE |
| Sandbox mode with missing credentials | same, `PAYPAL_CLIENT_ID=` | exit 1, `paypal_auth_config: MISSING (PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET)` — names only | VERIFIED_FIXTURE |
| Live mode refused | `PAYPAL_MODE=live` | `ConfigError` at startup | VERIFIED_FIXTURE |
| Non-sandbox base URL refused | `PAYPAL_BASE_URL=https://api-m.paypal.com` | `ConfigError` mentioning sandbox | VERIFIED_FIXTURE |
| **OAuth exchange against real PayPal** | `../.venv/bin/python -m app.preflight --network` with configured sandbox credentials | **`paypal_oauth: AUTHENTICATED (http 200, 26 scope(s), token not stored)`** | **VERIFIED_CONNECTED** (2026-10-26) |
| **Real sandbox order creation** | UI → hold → *Pay with PayPal* | HTTP 201, `provider_mode: sandbox`, `amount_cents: 7500 USD`, real `https://www.sandbox.paypal.com/checkoutnow?token=...` approval URL | **VERIFIED_CONNECTED** (2026-10-26) |
| **Order read back from PayPal** | `PayPalProvider.get_order(order_id)` | PayPal reports the same order id, state `CREATED`, `custom_id` set | **VERIFIED_CONNECTED** (2026-10-26) |
| **Capture refused before buyer approval** | `POST /api/payments/{id}/capture` | HTTP **409** `ORDER_NOT_CAPTURABLE` — PayPal itself refuses; no booking confirmed | **VERIFIED_CONNECTED** (2026-10-26) |
| **Browser buyer approval + confirmed capture** | real sandbox buyer approved the checkout page; then `POST /api/payments/{id}/capture` | **`200 reconciled_ok`, captured `7500 USD`, booking `confirmed` (`SA-LNRXNS`)**; PayPal itself reports order `COMPLETED`, capture `0JT80823PB148054X`, `$75.00 USD`, `final_capture: true`, with `custom_id` = our attempt id and `invoice_id` = our booking reference | **VERIFIED_CONNECTED** (2026-10-26) |
| **Capture is idempotent** | repeat the capture call | `200`, same `reconciled_ok`, `captured_amount_cents` still `7500` — no second charge | **VERIFIED_CONNECTED** (2026-10-26) |
| **Confirmed booking survives a restart** | stop uvicorn, restart, re-read payment + booking | `reconciled_ok`, `7500 USD`, booking `confirmed` `SA-LNRXNS` — read from SQLite, not memory | **VERIFIED_CONNECTED** (2026-10-26) |
| **Live webhook delivery + verification** | needs a registered public HTTPS subscription | **NOT RUN** — no public listener or subscription id | NOT RUN |

Tests covering the above: `backend/tests/test_paypal_integration.py` (39) and
`backend/tests/test_paypal_adapter.py` (11).

### 1b. The buyer step initially failed on a seller-account currency mismatch

Before the successful capture above, the buyer step failed with a PayPal error page. That
failure and its resolution are recorded because it is the most likely thing to bite a
team re-running this:

| Step | Outcome | Class |
|---|---|---|
| Open the real approval URL in a browser | `checkoutnow?token=…` loaded PayPal's live sign-in for the order | **VERIFIED_CONNECTED** |
| Enter the sandbox **personal** buyer email | accepted; page advanced to the password step | **VERIFIED_CONNECTED** |
| Buyer approves the payment | PayPal redirected to `checkoutweb/genericError?code=VU5TVVBQT1JURURfUEFZRUVfQ1VSUkVOQ1k` = **`UNSUPPORTED_PAYEE_CURRENCY`** | **BLOCKED (account config)** |
| Capture after the failed approval | still `409 ORDER_NOT_CAPTURABLE`; attempt `created`, booking `awaiting_payment` — no fabricated confirmation | VERIFIED_CONNECTED |
| Abandon the failed attempt | `POST /payments/{id}/cancel` → `200`; attempt `cancelled`, booking `cancelled`, slot released | VERIFIED_CONNECTED |
| **New US sandbox seller account, `PAYPAL_MERCHANT_ID` updated, backend restarted** | checkout rendered a real funding source and **`Complete Purchase`**; `UNSUPPORTED_PAYEE_CURRENCY` no longer occurred | **VERIFIED_CONNECTED** |

**Root cause.** The order is created `intent: CAPTURE` in `USD` with
`purchase_units[0].payee.merchant_id = PAYPAL_MERCHANT_ID`. The *first* sandbox business
account was India-based and did not support `USD` as a receiving currency, so PayPal
accepted order creation (`201`) and refused the order only when the buyer opened it. It is
not detectable from the create-order response, which is why it presented as a buyer-side
failure.

Contributing factor worth knowing: an India-context buyer session also forces an INR
display/conversion path (`PayPal's conversion rate: 1 INR = …`), which makes the symptom
look like a buyer problem. Clearing the session is not sufficient on its own — the
receiving account has to accept `USD`.

**Fix.** Point `PAYPAL_MERCHANT_ID` at a sandbox **business** account that settles in
`USD`, then **restart the API** (settings are cached at import, so an edit to
`backend/.env` alone does not take effect). Procedure:
[`going-live-sandbox.md`](./going-live-sandbox.md) § Troubleshooting.

**Guard added.** `python -m app.preflight` prints a `paypal_payee_currency` line pairing
the order currency with `PAYPAL_MERCHANT_ID`, so the mismatch is visible before a demo.
The merchant id value is deliberately not printed; the existing
`test_preflight_never_prints_secret_values` test caught an earlier version that leaked it
and now guards the new check.

## 2. PayPal — protocol conformance (fixtures)

Hermetic tests assert the real wire contract against a stubbed transport:

- create order posts to `/v2/checkout/orders` with `intent: CAPTURE`,
  `PayPal-Request-Id`, server-derived `75.00` from `7500` cents, and no
  client-supplied price
- `payment_source.paypal.experience_context` is used when return/cancel URLs are
  configured; the deprecated `application_context` block is *not* also sent
- capture posts to `/v2/checkout/orders/{id}/capture` and parses
  `purchase_units[].payments.captures[]` amount/currency/payee/custom_id
- 422 maps to `ORDER_NOT_CAPTURABLE`; 404 maps to `ORDER_NOT_FOUND`; transport
  failure raises `ProviderUnavailable(details.ambiguous=True)`
- webhook verification posts the five signature headers plus `webhook_id` and the
  parsed event to `/v1/notifications/verify-webhook-signature`, and accepts only
  `verification_status == "SUCCESS"`

## 2b. Assistant runtime — live provider (VERIFIED_CONNECTED, 2026-10-26)

An OpenAI-compatible endpoint was configured and exercised:

| Check | Outcome | Class |
|---|---|---|
| Raw completion | HTTP 200, model `deepseek-v4.1-flash`, JSON content | VERIFIED_CONNECTED |
| `search_availability` tool call | model emitted a correct tool call with valid arguments | VERIFIED_CONNECTED |
| End-to-end via `/api/assistant/message` | `mode: llm`, `fallback_required: false`, 3 real DB-backed options, redacted trace `[('search_availability', True)]` | VERIFIED_CONNECTED |
| Prompt injection ("confirm my booking", "you are admin", "refund it") | refused in prose; **no** booking/payment state changed (confirmed count unchanged) | VERIFIED_CONNECTED |
| Cross-customer lookup (`SA-D4E5F6` requested by the *other* customer) | "couldn't find a booking with that reference on your account"; no leaked technician/time/name | VERIFIED_CONNECTED |
| Provider failure / malformed JSON | labelled fallback with real options; never a silent simulated switch | VERIFIED_FIXTURE |

**Two real defects were found only by running against a live model**, and fixed:

1. The model answers in **prose** on the round after a tool call, ignoring
   `response_format`. The old code discarded a *successful* tool call and fell back.
   Now: after a tool round the tool list is withdrawn (`tool_choice: "none"`), JSON is
   parsed tolerantly, and a valid prose answer is kept **with** its tool-derived
   options (`constraints` stays empty — prose is never parsed into structure).
2. Relaying prose introduced a safety hole: a model saying *"I booked it for you"*
   would be shown as fact. A server-side **mutation-claim guard** now replaces any
   such claim with a correction ("I cannot hold, book, charge or refund…nothing has
   been changed") and sets `fallback_required`.

Tests: `test_prose_answer_after_tool_call_is_kept_with_real_options`,
`test_tools_are_withdrawn_after_a_tool_round`,
`test_llm_mode_falls_back_on_malformed_output` (now asserts the claim is corrected).

## 3. Payment integrity (fixtures)

`backend/tests/test_payment_integrity.py`, `test_hold_lifecycle.py`,
`test_regressions.py`:

- two customers race one slot → exactly one winner, proven three ways: service-level,
  a **real threaded HTTP race**, and a direct index assertion that is mutation-checked
- **unaligned `start_utc` is rejected** (regression: it bypassed the index)
- duplicate capture ×3 → one attempt, one captured amount
- duplicate checkout → same attempt; a *failed* attempt no longer blocks a retry
- capture after hold expiry → money recorded, booking `payment_exception`, capacity released
- `DENIED` then late `COMPLETED` → money recorded on a closed booking, **no orphaned capacity**
- force-confirm must win the capacity claim (409 if the slot was taken)
- create and capture use **distinct** idempotency keys
- forged/replayed/duplicate-id webhooks change nothing

## 4. Bryntum

| Check | Outcome | Class |
|---|---|---|
| Trial package installable from public npm via alias | `@bryntum/scheduler` → `@bryntum/scheduler-trial@7.3.7` | VERIFIED_FIXTURE |
| Licensed private registry | `https://npm.bryntum.com/@bryntum%2Fscheduler` → **HTTP 401** | BLOCKED |
| Widget renders technician rows and events in a real browser | verified: 3 rows, correct 8 AM–6 PM axis, 5 events on the demo day, no fallback engaged | VERIFIED_CONNECTED (local browser) |
| Day navigation updates the widget | verified: 2026-11-03 → 11-04 rebuilds with the new events | VERIFIED_CONNECTED (local browser) |
| CSS fallback if the widget fails | present and functional; shows a disclosure | IMPLEMENTED |
| Trial watermark | visible in the widget; disclosed in the UI and docs | DOCUMENTED |

## 5. APIMatic — PayPal Context Plugin

| Check | Command | Outcome | Class |
|---|---|---|---|
| Installer diagnostics | `npx --yes context-plugins doctor --json` | `ok: true`, 0 failures; detects Node 24.21.0, VS Code at `~/.config/Code/User`, Claude Code, Cursor, Codex; registry reachable (43 plugins) | VERIFIED_CONNECTED |
| Installed plugin list | `npx --yes context-plugins installed --targets vscode --json` | `plugin: paypal`, `repo: github:paypaldev/server-sdk-context-plugin-preview`, targets `claude`, `vscode`, installed 2026-10-25T16:13:27Z | VERIFIED_CONNECTED |
| Plugin actually consulted during implementation | Loaded `python-getting-started`; it resolved the real SDK coordinates (`paypal-server-sdk` `2.4.0`, import package `paypalserversdk`, client `PaypalServersdkClient`, `ApiException` base, `ApiResponse.body` envelope) and the companion `python-error-handling` skill's ambiguity rule | Used for this build's PayPal work | VERIFIED_CONNECTED (knowledge loaded and applied) |

**Honest limitation:** the plugin teaches the APIMatic-generated *SDK*. This
repository calls the PayPal REST API directly through `httpx` rather than
installing `paypal-server-sdk`, so the skills informed the protocol work
(idempotency per logical operation, treating a transport error on capture as
*outcome unknown*, verifying the settled capture rather than buyer approval) but
the SDK itself is not a dependency. No APIMatic runtime key exists or is needed.

## 6. Postman

| Check | Command | Outcome | Class |
|---|---|---|---|
| Collection executes — **simulated** mode | `npx --yes newman run postman/SlotSaver.postman_collection.json -e postman/SlotSaver.local.postman_environment.json` | 27 requests, 53 assertions, **0 failures** | VERIFIED_CONNECTED (local stack) |
| Collection executes — **sandbox** mode | same command, `PAYPAL_MODE=sandbox` + real credentials | 25 requests, 45 assertions, **0 failures** (capture-dependent steps correctly skipped) | VERIFIED_CONNECTED (local stack + live PayPal for order creation) |
| Repeatable from a clean state | `POST /api/owner/demo/reset`, then re-run | same result, 0 failures | VERIFIED_CONNECTED |
| Collection is committed | `postman/SlotSaver.postman_collection.json` + `SlotSaver.local.postman_environment.json` | yes | IMPLEMENTED |

**Operating notes (learned by running it repeatedly):**

- Reset the fixtures first (`./scripts/reset-demo.sh` + restart, or
  `POST /api/owner/demo/reset`). Each full run consumes the demo day's capacity, so
  a second run without a reset correctly reports *"has bookable capacity"* as
  failed. The collection then short-circuits the dependent requests so one
  precondition failure does not masquerade as twenty defects.
- Login is rate-limited at 10/min/IP. Running the collection more than about four
  times in a minute engages the limiter; the collection then fails with a single
  labelled assertion (`login rate limited - wait 60s`) and stops. That is the
  control working, not a defect.
- The collection is **mode-aware**: it reads `paypal_mode` from `/api/config`. In
  sandbox mode the simulated-approve route does not exist and capture cannot
  succeed without a human buyer, so those two steps assert the correct refusal
  (`ORDER_NOT_APPROVED` **or** PayPal's `ORDER_NOT_CAPTURABLE`) and skip forward to
  the remaining negative suites instead of ending the run.
- Verified: simulated mode → **27 / 53 / 0**; sandbox mode → **25 / 45 / 0**;
  capacity exhausted → **one** clear failure; rate limited → **one** clear failure.

Coverage: health/config/services/technicians, unauthenticated refusal, login,
assistant options (budget honoured), hold, **duplicate hold → 409**, checkout,
**capture-before-approval → 409**, approve, capture, **duplicate capture idempotent**,
persistence, customer→owner **403**, **CSRF stripped → 403**, client-supplied price
**422**, unaligned start **422**, naive datetime **422**, foreign booking **404**,
unsigned webhook **never 200**, owner timeline, analytics reconciliation (totals ==
rows == buckets), audit.

## 7. Deferred sponsors

| Sponsor | Why not selected | Where recorded |
|---|---|---|
| AG Studio | Commercial licence; UI already has owner analytics; rules allow one sponsor prize | gap matrix |
| Astropods | Would replace a verified runtime; external chat auth unresolved | gap matrix |
| Channel3 | No parts catalogue in this flow | gap matrix |
| Elastic | No policy corpus; adapter boundary only | gap matrix |
| KERNEL | No legacy portal to automate | gap matrix |
| Render | Deployment is a separate authorisation | `deployment.md` |
| Zapier | MCP server + OAuth cannot be created from a key | gap matrix |

No adapter, flag or document in this repo claims these are integrated.

## 8. Full check run

```bash
./scripts/test.sh
# 104 backend tests passed
# frontend typecheck passed
# frontend production build passed
```
