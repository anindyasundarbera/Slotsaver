# SlotSaver

> **Describe what you need, find a workable appointment, pay to confirm it, and recover when plans change.**

SlotSaver is a **proof of concept** for a fictional US appliance-repair business
("Northline Appliance Care", USD). A customer asks in plain language, receives
**validated, real appointment options** from the backend, holds one, pays through
**PayPal Sandbox**, and gets a persistent booking. The owner sees a technician
timeline, operational analytics, and can flag a technician — which raises a
reassignment proposal that **only the customer can approve**.

This is a tested demo, not a production system. Scope boundaries are listed in
[§8](#8-what-this-deliberately-does-not-do).

---

## 1. Quick start

Requires **Python 3.12+** and **Node 20+**.

```bash
git clone <this repo> && cd Slotsaver
./scripts/setup.sh          # venv, pip install, npm ci, backend/.env
./scripts/dev.sh            # API on :8000, UI on :4200
```

To use **real PayPal Sandbox** instead of the offline rehearsal, paste your
credentials into `backend/.env` and set `PAYPAL_MODE=sandbox` — the app reads that
file at startup. See [`docs/going-live-sandbox.md`](docs/going-live-sandbox.md).

Open **http://localhost:4200** and pick a demo account.

| Email | Role |
|---|---|
| `maya@example.com` | customer |
| `diego@example.com` | customer (second identity, for isolation demos) |
| `owner@northline.example` | owner |

Paste the demo request into the assistant box:

> *I need washing-machine service tomorrow after 4 PM. My budget is $80, and it must finish before 6.*

### Verify it is healthy

```bash
curl -s localhost:8000/api/health          # {"status":"ok",...}
curl -s localhost:4200/api/health          # same, through the dev-server proxy
```

### Run everything

```bash
./scripts/test.sh            # backend tests + frontend typecheck + production build
cd backend && ../.venv/bin/python -m app.preflight   # capability report
./scripts/reset-demo.sh      # rebuild only the synthetic demo database
.venv/bin/python scripts/e2e_sandbox.py   # full sandbox journey, headless
```

---

## 2. The two modes (never switched silently)

| Mode | `PAYPAL_MODE` | What happens | How it is labelled |
|---|---|---|---|
| **Offline rehearsal** | `simulated` (default) | No network, no real money. A clearly-named `SimulatedProvider` creates/approves/captures orders and signs webhooks with HMAC. | Amber **"Offline rehearsal — simulated payments"** badge in the header and on every checkout screen |
| **Connected sandbox** | `sandbox` | Real PayPal Orders v2 calls and real webhook signature verification. Requires `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET`. | Blue **"PayPal Sandbox"** badge |

The same assistant also has two runtimes: `scripted` (deterministic, offline, labelled
"Scripted assistant (offline)") and `llm` (OpenAI-compatible endpoint, labelled
"Live AI assistant"). A provider failure **falls back visibly**, never silently.

---

## 3. Architecture at a glance

```
Angular 20 SPA ──/api──▶ FastAPI ──▶ SQLAlchemy ──▶ SQLite (local) / Postgres
                            │
                            ├──▶ PayPal Orders v2  (sandbox only, server-side)
                            └──▶ orders + webhooks, signature-verified
```

Full detail: [`docs/architecture.md`](docs/architecture.md) ·
[`docs/state-model.md`](docs/state-model.md)

**Compact version of who decides what:**

| Question | Answered by |
|---|---|
| What appointments exist? | Backend (the assistant may only *read* them) |
| Can this slot be held? | A **partial unique index** in the database — not a pre-check |
| What does it cost? | The service catalogue row (client-supplied prices are rejected) |
| Did the customer pay? | A verified capture, or a signature-verified webhook. Never a redirect or model prose |
| Does a reassignment apply? | The customer, and the backend re-validates capacity atomically |

### The concurrency primitive

Calendar overlap cannot be a unique constraint, so every reservation claims
discrete 30-minute capacity cells:

```sql
CREATE UNIQUE INDEX ux_slot_blocks_active
  ON slot_blocks(technician_id, slot_start_utc)
  WHERE active = 1;
```

A lost race raises `IntegrityError` → `409 SLOT_UNAVAILABLE`. That is why
"two customers race for one slot, exactly one wins" is a test, not a hope.

---

## 4. What is verified

```bash
cd backend && ../.venv/bin/python -m pytest -q
```

| Suite | Covers |
|---|---|
| `test_happy_path.py` | Request → options → hold → checkout → verified capture → persistent confirmation (and after a refresh) |
| `test_hold_lifecycle.py` | Cancelled checkout does not confirm; expiry releases capacity; offset overlap rejected |
| `test_concurrency_http.py` | **Real parallel HTTP race** between two sessions for one slot → exactly one winner; the partial unique index itself rejects a duplicate claim (mutation-checked) |
| `test_payment_integrity.py` | Amount/currency tampering, foreign order, duplicate capture, duplicate checkout, capture-after-expiry, forged webhook, replayed webhook, new-id replay, unknown order, unapproved order |
| `test_authorization.py` | Cross-customer 404s, role separation, CSRF, cross-origin writes, `extra="forbid"`, naive datetimes, business hours, skill match |
| `test_reassignment.py` | Disruption preserves the paid booking; approval persists atomically; decline; foreign approval blocked; un-offered technician; **unresolved when no alternative exists** |
| `test_assistant_abuse.py` | 5 prompt-injection payloads, cross-customer lookup, no invented availability, malformed model output, provider outage, rate limit |
| `test_durability.py` | App restart preserves state; analytics equal the rows they summarise; timeline/analytics agree after mutation; owner-only reset |
| `test_paypal_adapter.py` | Real PayPal request shape, idempotency header, capture parsing, error mapping, webhook verification, live-mode refusal |
| `test_dotenv.py` | `.env` is read at import, a real env var wins over it, the skip flag works, and a populated `.env` cannot break the suite |
| `test_paypal_integration.py` | Operation-key separation, approved base origin, experience-context order body, webhook enable gate, and preflight secret hygiene |
| `test_regressions.py` | Unaligned-start rejection, retry after a failed attempt, late-capture capacity release, force-confirm capacity claim, rollback safety |

Exact commands, counts and skipped checks: [`docs/test-evidence.md`](docs/test-evidence.md).

---

## 5. Sponsor usage — honestly

| Integration | Status |
|---|---|
| **PayPal Orders v2 + Webhooks** | **IMPLEMENTED**, hermetically **VERIFIED**, live sandbox **NOT RUN** (no credentials in this environment). `python -m app.preflight` reports readiness without leaking secrets |
| **APIMatic Context Plugin** | **VERIFIED_CONNECTED** as a development tool (installer doctor + plugin loaded and used); not a runtime dependency |
| **Postman** | **VERIFIED_CONNECTED** — committed 27-request / 53-assertion collection, run twice with 0 failures |
| **Bryntum Scheduler** | **IMPLEMENTED** on the public **trial** build (watermarked, evaluation-only). Licensed registry access **BLOCKED** (HTTP 401). A functional fallback timeline ships so the demo cannot fail |
| AG Studio | **NOT INTEGRATED** — commercial, and the rules allow only one sponsor prize |
| Astropods | **NOT INTEGRATED** — not selected as the runtime (prompt requires one) |
| Channel3 | **OUT OF SCOPE** by design |

Full matrix with evidence and limits: [`docs/integration-status.md`](docs/integration-status.md) ·
[`docs/vendor-verification.md`](docs/vendor-verification.md).

---

## 6. Documentation

| Document | Purpose |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Topology, data model, state machines, failure behaviour |
| [`docs/state-model.md`](docs/state-model.md) | Every endpoint, status vocabulary, permitted transitions |
| [`docs/threat-model.md`](docs/threat-model.md) | STRIDE table, prompt-injection defence, known gaps |
| [`docs/security-review.md`](docs/security-review.md) | Independent review findings and fixes |
| [`docs/test-evidence.md`](docs/test-evidence.md) | Commands, outcomes, skips |
| [`docs/integration-status.md`](docs/integration-status.md) | Sponsor matrix, LIVE/SIMULATED/BLOCKED |
| [`docs/integration-gap-matrix.md`](docs/integration-gap-matrix.md) | Gap analysis per sponsor with decisions |
| [`docs/integration-config.md`](docs/integration-config.md) | Env-name mapping, public/server boundary, preflight |
| [`docs/integration-evidence.md`](docs/integration-evidence.md) | Exact commands and connected evidence |
| [`docs/vendor-verification.md`](docs/vendor-verification.md) | Rules and vendor claims with sources |
| [`docs/demo-runbook.md`](docs/demo-runbook.md) | 5-minute walkthrough + **2:45 submission cut** + recovery card |
| [`docs/going-live-sandbox.md`](docs/going-live-sandbox.md) | Step-by-step to paste sandbox keys and run the real journey |
| [`docs/e2e-sandbox.md`](docs/e2e-sandbox.md) | Automated headless end-to-end journey incl. buyer approval |
| [`docs/deployment.md`](docs/deployment.md) | Postgres, Render caveats, prepared-but-unverified config |
| [`docs/task-board.md`](docs/task-board.md) | Task ownership, dependencies, blockers |

---

## 7. Configuration

Copy `backend/.env.example` to `backend/.env`. Key settings:

```bash
PAYPAL_MODE=simulated          # or sandbox; "live" is refused at startup
DATABASE_URL=sqlite:///./data/slotsaver.db
DEMO_DATE=2026-11-03           # all seeded dates are relative to this
BUSINESS_TZ=America/New_York
HOLD_TTL_MINUTES=15
ASSISTANT_MODE=scripted        # or llm (needs LLM_API_KEY)
COOKIE_SECURE=false            # set true behind HTTPS
APP_ORIGIN=http://localhost:4200
```

`PAYPAL_MODE=live` raises at startup. This POC cannot be pointed at real money.

---

## 8. What this deliberately does *not* do

- No refunds. A `payment_exception` is resolved manually by the owner and audited.
- No marketplace, multi-tenancy, subscriptions, route optimisation or CRM.
- No production hardening: rate limiting is in-process; SQLite is local-demo only.
- Not deployed. [`docs/deployment.md`](docs/deployment.md) has prepared config and
  the free-tier caveats that would bite (ephemeral disk, 30-day Postgres expiry).
- AG Studio, Astropods, APIMatic and Channel3 are **not** integrated — see §5.

## 9. Licence

Original project code is MIT-licensed (see [`LICENSE`](LICENSE)).
**Third-party obligations:** Bryntum Scheduler is used under its *trial* terms via
`@bryntum/scheduler-trial`; no licensed Bryntum assets are redistributed here, and a
licence is required for production use. Angular, FastAPI and the other dependencies
retain their own licences. Do not commit vendor trial keys or credentials.
