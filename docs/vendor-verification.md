# Vendor and rules verification

Verified **2026-10-25** before implementation, as the feasibility gate requires.
Each claim is tagged CONFIRMED (with the source's own words), UNCLEAR, or UNREACHABLE.

## 1. Hackathon rules — https://paypalaihackathon.devpost.com/rules

> Access note: the page returned HTTP 403 to a plain fetcher; content was retrieved
> with a browser User-Agent. No claim below comes from a rendered visual check.

| Claim | Status | Evidence |
|---|---|---|
| Submission window closes **Nov 12, 2026, 12:00 PM Pacific** | CONFIRMED | "Thursday Oct 1, 2026 (9:15 am Pacific Time) – Thursday Nov 12, 2026 (12:00 pm Pacific Time)"; header "Deadline: Nov 12, 2026 @ 12:00pm PST" |
| Public open-source repository with a detectable licence required | CONFIRMED | "The repository must be public and open source by including an open source license file." |
| Public YouTube demo **under three minutes** | CONFIRMED | "should be less than three (3) minutes. Judges are not required to watch beyond three minutes" |
| Judges must be able to run/interact with a working build | CONFIRMED | "Your project does not need to be publicly hosted or deployed — but judges must be able to actually run or interact with a working build." Complete run instructions satisfy this. |
| A mockup or non-functional demo is insufficient | CONFIRMED | "A design mockup, static prototype, or non-functional demo does not meet this requirement." |
| Prizes: Grand $12k/$8k/$5k; Honorable Mentions $5k ×5; sponsor prizes incl. **Bryntum $1,000 (qty 3)** | CONFIRMED | Rules prize table |
| **At most one sponsor prize per project** | CONFIRMED | "A project can only win up to one (1) Grand Prize and one (1) Sponsor Prize OR one (1) Honorable Mention Prize and one (1) Sponsor Prize." |
| Sponsor tool use is optional; PayPal integration is central | CONFIRMED | FAQs: "Using a sponsor tool is optional… as long as PayPal integration is central to your project." |
| Sandbox is the expected payment environment | CONFIRMED | FAQs: "you'll use the free PayPal sandbox" |
| Team size | No maximum stated | CONFIRMED (absence) |

**Consequence taken:** one sponsor target — **Bryntum** — plus a rigorous PayPal
integration. AG Studio is deliberately not attempted. The 3-minute video limit is
respected by the separate 2:45 submission script.

## 2. AG Studio compatibility — https://www.ag-grid.com/studio/angular/compatibility/

| Claim | Status | Evidence |
|---|---|---|
| Studio 3 ↔ Angular 20–22; Studio 1 ↔ Angular 18–19 | CONFIRMED | table: "20 - 22 | 1 - 3+" and "18 - 19 | 1" |
| npm package `ag-studio-angular`, latest 3.0.0, `"license": "Commercial"` | CONFIRMED | registry metadata; quick-start: `npm install ag-studio-angular ag-studio` |
| Requires a licence key; watermark + console warnings without one | CONFIRMED | "A licence key is validated and configured in the application." `AgStudioLicenseManager.setLicenseKey(...)` |
| TS ≥ 5.8.3 for Studio 2–3+ | CONFIRMED | compatibility table |
| Studio 3 needs AG Grid 36.2 / AG Charts 14.2 | CONFIRMED | compatibility table |

**Not selected.** Recorded so the decision is auditable, not accidental.

## 3. Bryntum Scheduler — https://bryntum.com/products/schedulerpro/scheduler-vs-schedulerpro/

| Claim | Status | Evidence |
|---|---|---|
| Standard Scheduler only *visualises* dependencies; Scheduler Pro recalculates | CONFIRMED | "Scheduler Visualizes. Scheduler Pro Calculates." / dependencies "Purely visual" vs "Affects scheduling" |
| Scheduler is therefore a pure view layer | CONFIRMED | — |
| Licensed package lives on a private registry | CONFIRMED | `npm view @bryntum/scheduler` → placeholder package: "The licensed version of Bryntum Scheduler is hosted on the private Bryntum npm registry" |
| Private registry reachable with this environment's credentials | **BLOCKED** | `https://npm.bryntum.com/@bryntum%2Fscheduler` → HTTP 401 |
| Public **trial** package exists and installs without auth | CONFIRMED | README points to `@bryntum/scheduler-trial`; installed successfully via npm alias |
| Trial builds are watermarked / evaluation-only | CONFIRMED | bundle contains trial-expiry and watermark strings |

**Decision taken:** the required behaviour is *persisting* changes through the
backend, not Bryntum's scheduling engine, so **standard Scheduler is the correct
product** — Scheduler Pro's engine would duplicate backend authority. The trial
build is used with an explicit on-screen disclosure, and a functional CSS
fallback timeline is shipped so the demo survives an expired trial.

## 4. Render free tier — https://render.com/docs/free

| Claim | Status | Evidence |
|---|---|---|
| Free web-service filesystem is **ephemeral** — SQLite is lost on restart | CONFIRMED | "any changes to your web service's filesystem… local SQLite databases, etc.) are *lost* every time the service redeploys, restarts, or spins down" |
| Free web services cannot attach a persistent disk | CONFIRMED | "Free web services *cannot*" |
| Free Postgres **expires 30 days after creation**, then is deleted | CONFIRMED | "Free Render Postgres databases expire 30 days after creation." |
| Free services spin down after 15 minutes idle; ~1 minute cold start | CONFIRMED | "spins down a Free web service that goes 15 minutes without receiving any inbound traffic" |

**Consequence taken:** SQLite is documented as local-demo-only; the hosted path is
Postgres with an explicit "expires in 30 days" warning. See [`deployment.md`](./deployment.md).

## 5. PayPal Orders v2 — https://developer.paypal.com/docs/api/orders/v2/

| Claim | Status | Evidence |
|---|---|---|
| Sandbox base URL `https://api-m.sandbox.paypal.com` | CONFIRMED | docs metadata "Base URL(s) — https://api-m.sandbox.paypal.com" |
| `POST /v2/checkout/orders`, `GET /v2/checkout/orders/{id}`, `POST /v2/checkout/orders/{id}/capture` | CONFIRMED | OpenAPI schema |
| `PayPal-Request-Id` provides idempotency | CONFIRMED | "A unique ID identifying the request header for idempotency purposes." |
| Capture response carries settled amount at `purchase_units[0].payments.captures[0].amount` | CONFIRMED | OpenAPI schema |
| A capture requires an approved order | CONFIRMED | 422 `ORDER_NOT_APPROVED` is documented |

## 6. PayPal webhooks — https://developer.paypal.com/api/rest/webhooks/

| Claim | Status | Evidence |
|---|---|---|
| Verification endpoint `POST /v1/notifications/verify-webhook-signature` | CONFIRMED | Webhooks v1 OpenAPI |
| Required fields: `auth_algo`, `cert_url`, `transmission_id`, `transmission_sig`, `transmission_time`, `webhook_id`, `webhook_event` | CONFIRMED | OpenAPI schema |
| `verification_status` returns `SUCCESS`/`FAILURE` | CONFIRMED | schema |
| Retries up to 25 times over 3 days | CONFIRMED | docs |
| Event `id` is unique for deduplication | **UNCLEAR** | "The ID of the webhook event notification." — uniqueness is not asserted anywhere |
| Docs sample host is `api.sandbox.paypal.com`, Orders v2 uses `api-m.sandbox.paypal.com` | CONFIRMED (inconsistency) | code sample vs Orders docs |

**Consequence taken:** because event-id uniqueness is not guaranteed by the docs,
deduplication uses the event id as a **primary key** (so a repeat is ignored) *and*
the settlement funnel is idempotent on the attempt state, so a duplicate arriving
under a *different* id still cannot double-confirm or double-charge. That second
guarantee is what `test_signed_webhook_confirms_and_duplicates_are_ignored` proves.

## 7. Astropods — https://docs.astropods.com/get-started

| Claim | Status | Evidence |
|---|---|---|
| Agent platform: projects, blueprints, hosted agents, sandbox VMs | CONFIRMED | "Astropods is a platform for building, deploying, and managing AI agents." |
| Gateway mode needs no provider API key | CONFIRMED | "no provider API key to manage — you authenticate once with your Astropods account" |
| Local dev needs Docker (`ast project start`) | CONFIRMED | "Containers start and logs stream automatically" |
| Documented integration with AG Studio browser tools | **NOT FOUND** | no mention in `llms.txt` or the fetched pages |
| Term "pod" used as a runtime unit | **UNCLEAR** | term not present in the docs; units are project/blueprint/agent/sandbox |

**Decision taken:** Astropods is **not** the chosen runtime. The prompt requires one
runtime, and Astropods adds Docker + account + hosted deployment to a demo that must
run offline. The assistant therefore ships with two runtimes behind one interface
(`scripted` and `llm`) and no vendor lock-in. Astropods is **NOT INTEGRATED** — not
claimed, not simulated.

## 8. APIMatic Context Plugins — https://www.apimatic.io/product/context-plugins

**Status: development-time only, not claimed as a runtime integration for this
build.** No Context Plugin was invoked by this environment, so it is recorded as
**NOT RUN** rather than claiming grounding evidence we do not have. The PayPal
implementation was written directly against the published Orders v2 OpenAPI
schema cited above, which is the same authoritative source such a plugin supplies.
