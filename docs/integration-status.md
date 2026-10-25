# Sponsor and integration status

Vocabulary: **IMPLEMENTED** (code exists), **VERIFIED** (proven by a test/command
in this repo), **SIMULATED** (deliberate labelled substitute, never presented as
the real thing), **BLOCKED** (attempted, cannot proceed here), **NOT RUN**
(implemented but never exercised against the real service in this environment).

| Integration | Intended role | What actually exists | Status | Verified on | Evidence | Limits |
|---|---|---|---|---|---|---|
| **PayPal Orders v2** | Create order, capture, verify capture server-side | `backend/app/services/payments.py::PayPalProvider` — real endpoints, `PayPal-Request-Id`, amount derived from integer cents, capture validation on 6 fields | **IMPLEMENTED + VERIFIED_CONNECTED (create/read/approval-page)** / **BLOCKED (capture: seller currency)** | 2026-10-26 | OAuth authenticated (200, 26 scopes); real sandbox order created (201, `75.00 USD`) and read back; capture correctly refused pre-approval (409); real buyer checkout page reached the password step, then PayPal returned `UNSUPPORTED_PAYEE_CURRENCY` — a seller-account currency mismatch, not a code defect. [`integration-evidence.md`](./integration-evidence.md) §1, §1b | Needs the sandbox **business** account to support `USD`. Diagnosis and fix in [`going-live-sandbox.md`](./going-live-sandbox.md). Nothing is presented as sandbox evidence that did not come from PayPal. |
| **PayPal Webhooks** | Authoritative, deduplicated payment events | `verify_webhook` → `/v1/notifications/verify-webhook-signature`; `handle_payment_event` with primary-key dedupe + idempotent settlement funnel | **IMPLEMENTED + VERIFIED (hermetic)** / **NOT RUN (live delivery)** | 2026-10-25 | `tests/test_paypal_adapter.py::test_webhook_verification_calls_paypals_endpoint`; `tests/test_payment_integrity.py` (forged, replayed, duplicate-id) | Live delivery needs a public HTTPS callback + registered subscription; no tunnel authorised. |
| **Simulated payment provider** | Offline rehearsal without network | `SimulatedProvider` — creates/approves/voids/captures orders, HMAC-signed webhooks | **SIMULATED** | 2026-10-25 | `tests/test_happy_path.py`, `tests/test_payment_integrity.py` | Clearly labelled in API (`provider_mode: "simulated"`), UI badge, and docs. Never called "PayPal". |
| **Bryntum Scheduler** | Owner technician timeline | `frontend` timeline component on `@bryntum/scheduler-trial@7.3.7` (npm alias), plus a functional CSS fallback | **IMPLEMENTED (trial) / BLOCKED (licensed)** | 2026-10-25 | `npm view @bryntum/scheduler` → placeholder; `https://npm.bryntum.com/...` → HTTP 401 | Trial build is watermarked and evaluation-only. Licensed registry needs credentials we do not have. Trial + public-demo licensing must be confirmed with Bryntum before submission. |
| **AG Studio** | Owner analytics with AI exploration | Nothing | **NOT INTEGRATED (deliberate)** | 2026-10-25 | [`vendor-verification.md`](./vendor-verification.md) §2 | Commercial licence. Rules allow only **one** sponsor prize, so building both would create an unclaimable integration. Bryntum chosen instead. |
| **Astropods** | Agent runtime + trace monitoring | Nothing. Runtime is our own bounded tool loop with two modes (`scripted`, `llm`) | **NOT INTEGRATED (deliberate)** | 2026-10-25 | [`vendor-verification.md`](./vendor-verification.md) §7 | Requires Docker + account; no documented AG Studio integration. Prompt requires **one** runtime. |
| **APIMatic Context Plugin** | Development-time grounding for PayPal | Nothing invoked | **NOT RUN** | 2026-10-25 | [`vendor-verification.md`](./vendor-verification.md) §8 | Not claimed. Implementation was written against the published Orders v2 OpenAPI schema directly. |
| **Channel3** | Retail product discovery | Nothing | **OUT OF SCOPE (deliberate)** | 2026-10-25 | — | Product discovery does not help an appointment/payment flow; adding it would be decoration. |
| **LLM assistant (`llm` mode)** | Natural-language understanding | OpenAI-compatible chat endpoint with tool calling, tolerant JSON handling, prose safety guard, iteration cap | **VERIFIED_CONNECTED** (2026-10-26) | 2026-10-26 | Live tool call + 3 real options + injection and cross-customer refusals; `tests/test_assistant_abuse.py` | Configured endpoint is Ollama-hosted `deepseek-v4.1-flash`. Provider may answer in prose after a tool call; handled explicitly. |
| **Scripted assistant** | Offline NL understanding | Deterministic parser + the same real availability tool | **IMPLEMENTED + VERIFIED** | 2026-10-25 | `tests/test_happy_path.py` | Keyword-based; honest label "Scripted assistant (offline)" in the UI. |
| **Render hosting** | Optional deployment | `render.yaml` + docs | **NOT RUN (not deployed)** | 2026-10-25 | [`deployment.md`](./deployment.md) | No hosted runtime was exercised. Free-tier caveats documented. |

## What this means for the submission

The PayPal integration is the core of the entry and is **real code against the real
API**. Its connected journey is **verified for OAuth, order creation and order read**;
buyer approval and capture are explicitly **NOT RUN** because they need an interactive
sandbox personal-account login. When a buyer approves, the same code path completes with
no changes — see [`e2e-sandbox.md`](./e2e-sandbox.md).

Credentials live only in the git-ignored `backend/.env`, which the app loads at startup
(an exported variable always wins). [`going-live-sandbox.md`](./going-live-sandbox.md)
walks through the switch from `simulated` to `sandbox`.

The one sponsor target is **Bryntum**, whose timeline is genuinely load-bearing in
the owner experience (it is how the presenter *shows* holds, confirmed bookings and
disruptions). Its trial watermark is disclosed on screen rather than hidden.


---

## Continuation update — 2026-10-26

Selected slice implemented after reading the sponsor handbook. Full detail in
[`integration-gap-matrix.md`](./integration-gap-matrix.md),
[`integration-config.md`](./integration-config.md) and
[`integration-evidence.md`](./integration-evidence.md).

| Integration | Change in this continuation | New status |
|---|---|---|
| **PayPal** | Configurable-but-validated sandbox base URL; separate create/capture idempotency keys; `payment_source.paypal.experience_context` when return/cancel URLs are set; webhook intake behind `PAYPAL_WEBHOOKS_ENABLED` (disabled ⇒ `503 WEBHOOKS_DISABLED`, never a bypass); merchant-id and host shape validation at startup | IMPLEMENTED + VERIFIED_CONNECTED (create/read); capture **NOT RUN** (buyer approval) |
| **PayPal** | New `python -m app.preflight` (`--network`, `--json`) reporting capability status and missing variable *names* only | IMPLEMENTED + VERIFIED_FIXTURE |
| **APIMatic** | Installer doctor + installed-plugin listing run; plugin skills loaded and used for PayPal grounding | **VERIFIED_CONNECTED** (development-time) |
| **Postman** | 27-request / 53-assertion collection, committed and executed twice (clean and after reset), 0 failures | **VERIFIED_CONNECTED** (local stack) |
| **Bryntum** | Unchanged (trial build, disclosed); preflight reports its flag | IMPLEMENTED on trial; licensed access **BLOCKED** (HTTP 401) |
| AG Studio, Astropods, Channel3, Elastic, KERNEL, Render, Zapier | Not implemented; reported as `DEFERRED` by preflight | **DEFERRED** |

Three HIGH and one LOW security findings from the independent review were fixed and
regression-tested; see [`security-review.md`](./security-review.md).
