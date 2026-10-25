# Sponsor and integration status

Vocabulary: **IMPLEMENTED** (code exists), **VERIFIED** (proven by a test/command
in this repo), **SIMULATED** (deliberate labelled substitute, never presented as
the real thing), **BLOCKED** (attempted, cannot proceed here), **NOT RUN**
(implemented but never exercised against the real service in this environment).

| Integration | Intended role | What actually exists | Status | Verified on | Evidence | Limits |
|---|---|---|---|---|---|---|
| **PayPal Orders v2** | Create order, capture, verify capture server-side | `backend/app/services/payments.py::PayPalProvider` — real endpoints, `PayPal-Request-Id`, amount derived from integer cents, capture validation on 6 fields | **IMPLEMENTED + VERIFIED (hermetic)** / **NOT RUN (live)** | 2026-10-25 | `tests/test_paypal_adapter.py` (11 tests, stubbed transport) | No sandbox credentials in this environment, so no live order exists. Nothing here is presented as sandbox evidence. |
| **PayPal Webhooks** | Authoritative, deduplicated payment events | `verify_webhook` → `/v1/notifications/verify-webhook-signature`; `handle_payment_event` with primary-key dedupe + idempotent settlement funnel | **IMPLEMENTED + VERIFIED (hermetic)** / **NOT RUN (live)** | 2026-10-25 | `tests/test_paypal_adapter.py::test_webhook_verification_calls_paypals_endpoint`; `tests/test_payment_integrity.py` (forged, replayed, duplicate-id) | A live webhook needs a public URL; not attempted. |
| **Simulated payment provider** | Offline rehearsal without network | `SimulatedProvider` — creates/approves/voids/captures orders, HMAC-signed webhooks | **SIMULATED** | 2026-10-25 | `tests/test_happy_path.py`, `tests/test_payment_integrity.py` | Clearly labelled in API (`provider_mode: "simulated"`), UI badge, and docs. Never called "PayPal". |
| **Bryntum Scheduler** | Owner technician timeline | `frontend` timeline component on `@bryntum/scheduler-trial@7.3.7` (npm alias), plus a functional CSS fallback | **IMPLEMENTED (trial) / BLOCKED (licensed)** | 2026-10-25 | `npm view @bryntum/scheduler` → placeholder; `https://npm.bryntum.com/...` → HTTP 401 | Trial build is watermarked and evaluation-only. Licensed registry needs credentials we do not have. Trial + public-demo licensing must be confirmed with Bryntum before submission. |
| **AG Studio** | Owner analytics with AI exploration | Nothing | **NOT INTEGRATED (deliberate)** | 2026-10-25 | [`vendor-verification.md`](./vendor-verification.md) §2 | Commercial licence. Rules allow only **one** sponsor prize, so building both would create an unclaimable integration. Bryntum chosen instead. |
| **Astropods** | Agent runtime + trace monitoring | Nothing. Runtime is our own bounded tool loop with two modes (`scripted`, `llm`) | **NOT INTEGRATED (deliberate)** | 2026-10-25 | [`vendor-verification.md`](./vendor-verification.md) §7 | Requires Docker + account; no documented AG Studio integration. Prompt requires **one** runtime. |
| **APIMatic Context Plugin** | Development-time grounding for PayPal | Nothing invoked | **NOT RUN** | 2026-10-25 | [`vendor-verification.md`](./vendor-verification.md) §8 | Not claimed. Implementation was written against the published Orders v2 OpenAPI schema directly. |
| **Channel3** | Retail product discovery | Nothing | **OUT OF SCOPE (deliberate)** | 2026-10-25 | — | Product discovery does not help an appointment/payment flow; adding it would be decoration. |
| **LLM assistant (`llm` mode)** | Natural-language understanding | OpenAI-compatible chat endpoint with tool calling, strict JSON validation, iteration cap | **IMPLEMENTED + VERIFIED (fallback paths)** / **NOT RUN (real model)** | 2026-10-25 | `tests/test_assistant_abuse.py` | No `LLM_API_KEY` here; the deterministic `scripted` runtime is what the demo runs. |
| **Scripted assistant** | Offline NL understanding | Deterministic parser + the same real availability tool | **IMPLEMENTED + VERIFIED** | 2026-10-25 | `tests/test_happy_path.py` | Keyword-based; honest label "Scripted assistant (offline)" in the UI. |
| **Render hosting** | Optional deployment | `render.yaml` + docs | **NOT RUN (not deployed)** | 2026-10-25 | [`deployment.md`](./deployment.md) | No hosted runtime was exercised. Free-tier caveats documented. |

## What this means for the submission

The PayPal integration is the core of the entry and is **real code against the real
API**. It is hermetic-tested, and its connected journey is explicitly **NOT RUN**
here. When sandbox credentials are supplied via `backend/.env`
(`PAYPAL_MODE=sandbox`), the same code path runs with no changes — that is the
first thing to do before recording the submission video.

The one sponsor target is **Bryntum**, whose timeline is genuinely load-bearing in
the owner experience (it is how the presenter *shows* holds, confirmed bookings and
disruptions). Its trial watermark is disclosed on screen rather than hidden.
