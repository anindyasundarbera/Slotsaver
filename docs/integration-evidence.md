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
| **OAuth exchange against real PayPal** | `.venv/bin/python -m app.preflight --network` with real sandbox credentials | **NOT RUN** — no sandbox REST app credentials exist in this environment | NOT RUN |
| **Browser buyer approval + real capture** | manual | **NOT RUN** — same blocker | NOT RUN |
| **Live webhook delivery + verification** | manual, needs public HTTPS | **NOT RUN** — no public listener, no registered subscription | NOT RUN |

Tests covering the above: `backend/tests/test_paypal_integration.py` (28) and
`backend/tests/test_paypal_adapter.py` (11).

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

## 3. Payment integrity (fixtures)

`backend/tests/test_payment_integrity.py`, `test_hold_lifecycle.py`,
`test_regressions.py`:

- two customers race one slot → exactly one winner (DB constraint decides)
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
| Collection executes | `npx --yes newman run postman/SlotSaver.postman_collection.json -e postman/SlotSaver.local.postman_environment.json` | 27 requests, 53 assertions, **0 failures** | VERIFIED_CONNECTED (local stack) |
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
- Verified: clean state → **27 requests / 53 assertions / 0 failures**; capacity
  exhausted → **one** clear failure; rate limited → **one** clear failure.

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
