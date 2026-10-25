# Integration gap matrix

Recorded **2026-10-26** against the code in this repository. Vocabulary:
**DOCUMENTED** · **IMPLEMENTED** · **VERIFIED_CONNECTED** · **VERIFIED_FIXTURE** ·
**SIMULATED** · **BLOCKED** · **DEFERRED**.

The companion `slotsaver-integrations.env.example` is a *proposal*. It is mapped onto
the settings loader in [`integration-config.md`](./integration-config.md); working
variable names are preserved and aliases are accepted in one place
(`backend/app/config.py`). No vendor reads these names automatically.

## Baseline (before this continuation)

| Capability | State at start | Evidence |
|---|---|---|
| PayPal Orders v2 create/capture/read | IMPLEMENTED, VERIFIED_FIXTURE | `backend/app/services/payments.py::PayPalProvider`; `backend/tests/test_paypal_adapter.py` (11 tests, stubbed transport) |
| PayPal webhook signature verification | IMPLEMENTED, VERIFIED_FIXTURE | `PayPalProvider.verify_webhook` → `/v1/notifications/verify-webhook-signature` |
| PayPal connected journey | BLOCKED | No sandbox credentials or registered webhook URL in this environment |
| Durable hold/booking/payment state | IMPLEMENTED, VERIFIED_FIXTURE | `backend/tests/test_durability.py`, `test_payment_integrity.py`, `test_regressions.py` |
| Race-safe slot acquisition | IMPLEMENTED, VERIFIED_FIXTURE | partial unique index `ux_slot_blocks_active` |
| Bryntum timeline | SIMULATED→IMPLEMENTED on trial build | `frontend/src/app/owner/timeline.component.ts`; trial watermark disclosed |
| Assistant runtime | IMPLEMENTED (`scripted` + `llm`), VERIFIED_FIXTURE | `backend/app/services/assistant.py` |
| Config preflight | **absent** | — |
| Distinct create/capture idempotency keys | **defect** — capture reused the create key | `bookings.py:510` |
| Postman collection | **absent** | — |
| APIMatic Context Plugin | NOT RUN | — |

## Gaps closed in this continuation

| # | Sponsor | Existing implementation | Useful capability | Smallest change | Credentials / manual setup | Verification | Decision |
|---|---|---|---|---|---|---|---|
| 1 | **PayPal** | Hardcoded sandbox base URL; `application_context` only; one idempotency key shared by create **and** capture | Correct idempotency semantics per logical operation; redirect/cancel return path; validated base origin | Separate `create` and `capture` keys derived from the attempt; add `payment_source.paypal.experience_context` with configured return/cancel URLs; make base URL configurable but refuse anything except the approved sandbox origin | Sandbox REST app (client id/secret), intended seller id, webhook subscription id + public HTTPS URL | `tests/test_paypal_integration.py` + existing adapter tests | **SELECTED** |
| 2 | **PayPal** | No operator-facing readiness check | Distinguish *configured* from *authenticated* without leaking secrets | New `python -m app.preflight [--network]` printing only statuses and missing variable **names** | Same as above | `tests/test_preflight.py` (asserts no secret ever appears in output) | **SELECTED** |
| 3 | **PayPal** | Webhook path always active | Explicit switch, so an unregistered listener is not silently trusted | `PAYPAL_WEBHOOKS_ENABLED`; disabled ⇒ intake returns 503 *and* reports NOT RUN (never bypasses signature checks) | Webhook registration in the sandbox app | `tests/test_paypal_integration.py` | **SELECTED** |
| 4 | **Bryntum** | Trial package aliased in `package.json`; component with CSS fallback | Licence handling and honest packaging | `SLOTSAVER_ENABLE_BRYNTUM` build-time flag + documented licensed-install path | Trial/licensed registry access (currently **BLOCKED**, HTTP 401) | `npm run build`; browser check | **SELECTED (trial)** |
| 5 | **APIMatic** | Nothing | Development-time PayPal grounding | Run `npx context-plugins doctor/install/installed` and record the real outcome | Installed into this coding environment | Command output recorded verbatim as evidence | **ATTEMPTED** |
| 6 | **Postman** | Nothing | Repeatable API verification against the live local stack | Generated collection + environment, covering happy path and the negative cases; fail-fast on exhausted capacity or rate limiting | None for local runs; reset fixtures first | `newman` run: 27 requests / 53 assertions / 0 failures; collection committed | **SELECTED** |
| 7 | AG Studio | Nothing | Operator exploration | Would need a commercial licence and a second analytics surface | Licence key | — | **DEFERRED** — commercial, and the rules permit one sponsor prize |
| 8 | Astropods | Current runtime works and is fixture-verified | Hosted agent | Would replace or duplicate a working runtime; external chat auth unresolved | Account, CLI login, deployment, chat auth | — | **DEFERRED** — no verified benefit; runtime change unproven |
| 9 | Channel3 | Nothing | Parts discovery | Adapter boundary only; no product value in this flow | `CHANNEL3_API_KEY` | — | **DEFERRED** (boundary documented) |
| 10 | Elastic | Nothing | Policy retrieval | Adapter boundary only | Cluster + scoped key | — | **DEFERRED** (boundary documented) |
| 11 | KERNEL | Nothing | Legacy-portal browser work | No legacy portal exists in this product | Account + authorised target | — | **DEFERRED** — no target to automate |
| 12 | Render | Prepared `render.yaml` in docs | Hosting with durable DB | No code change needed | Account, service, persistent DB | — | **DEFERRED** — deployment is a separate authorisation |
| 13 | Zapier | Nothing | Approved cross-app follow-up | MCP server + OAuth connections; a token alone cannot do it | `ZAPIER_MCP_TOKEN`, allowed tool, OAuth | — | **DEFERRED** |

## Why the deferred five are not "integration theatre"

Each deferred sponsor either (a) needs a commercial licence that changes the
award story, (b) would replace a runtime that is already verified, or (c) has no
real subject matter in this product (there is no legacy portal to automate, no
parts catalogue in the booking flow). Building an adapter with no live path would
produce code that cannot be honestly described as integrated. The prompt requires
honesty over breadth, and the rules allow only one sponsor prize.

## Ordering actually followed

1. PayPal configuration + idempotency + preflight (payment integrity first).
2. Webhook enable-flag and intake behaviour.
3. Bryntum licence/build flag.
4. APIMatic evidence, then Postman collection.
5. Documentation, tests, review, runbooks.
