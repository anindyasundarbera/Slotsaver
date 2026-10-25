# SlotSaver — sponsor integration continuation handbook

**Research date: 25 October 2026 · Implementation handoff for an existing codebase**

This handbook supplements the implementation prompt already running. **Continue the current project; do not generate a replacement application.** Six subagents researched concrete integration paths for all ten optional sponsors and the required PayPal payment layer; the coordinator curated scope, configuration boundaries and verification gates.

The actual codebase being generated was not supplied in this session. Repository paths, application endpoints, adapter names and feature flags proposed here are design contracts to reconcile with the running project, not facts about its current implementation. Official example APIs and commands are separately labelled in the detailed sections. Examples were checked against documentation but were not installed or executed here. No credentials were supplied or used.

## Read this first: continuation protocol

1. Read repository instructions, task board and current implementation status. Inspect Git status and preserve uncommitted work. Identify actual frontend/backend versions, database, payment adapter, assistant runtime, API contracts, existing environment schema and tests. Do not run commands that print `.env`, environment values, authentication headers or tokens.
2. Produce `docs/integration-gap-matrix.md` using the project's actual paths. For each sponsor record **existing implementation → useful capability → smallest change → credentials/manual setup → verification → decision**. Do not replace working code because an example uses a different framework or configuration name.
3. Map the companion environment template to the project's current schema. Preserve existing names when they already work; document aliases in a single configuration layer. Proposed flags are not vendor-recognized settings and do nothing until implemented. Add only required missing entries to `.env.example`; never overwrite the populated local `.env`.
4. Select an integration slice and implement it through current abstractions. Prioritize working PayPal Sandbox, durable bookings and Bryntum. Add APIMatic development evidence and Postman verification. Keep the existing model/runtime unless a verified reason supports a change. Consider Studio, deployment or extra tools only where they improve this product.
5. Delegate bounded implementation work after shared contracts are agreed. Use separate owned paths/worktrees as appropriate; independent review covers payment, authorization, concurrency and secret handling. Keep integration of shared configuration sequential.
6. Run the baseline and change-relevant checks. Report real connected checks separately from fixtures. Update source/dependency lockfiles and documentation; leave no claim of successful vendor integration without observed evidence.

The handbook's selection advice is engineering judgment. It covers how every sponsor can be used; it does not require integrating every sponsor. Original team allocation remains our first five and **Aritra's** other five.

## Recommended implementation order

| Stage | Scope | Exit evidence |
| --- | --- | --- |
| 0 — inventory | Current code and configuration, migrations, tests, dependency versions | Gap matrix tied to actual files; baseline status |
| 1 — core | PayPal Sandbox, transactional holds, persisted booking/payment state | Actual approved capture, persistent confirmation, negative/conflict tests |
| 2 — schedule | Bryntum resource timeline through existing APIs | Server-validated hold/reassignment; failed drag reverts |
| 3 — assistant | Existing runtime or selected Astropods/Elastic path | Actual typed tool calls; approval enforced; failure preserves state |
| 4 — delivery evidence | APIMatic use record, Postman collection, independent review | Reproducible tests and redacted evidence |
| 5 — selected extensions | Studio, Render, retrieval or legacy/SaaS integration | Each extension has a user-visible purpose and its own smoke result |

Stages are adaptive: retain and verify stages the coding agent has already implemented rather than rebuilding them.

## Where each tool can fit

| Sponsor | Meaningful SlotSaver use | Configuration/setup boundary | Default approach |
| --- | --- | --- | --- |
| AG Grid / AG Studio | Operator explores affected bookings; custom recovery widget; actual dashboard-agent interaction | Frontend package/licence plus separately secured model/backend runner | Conditional; version-check before adding |
| APIMatic | PayPal Context Plugin informs coding-agent implementation | Install into coding environment; retain honest evidence; no invented runtime APIMatic key | Development support |
| Astropods | Host bounded assistant; inspect tool traces | Agent project/deployment, model configuration, external chat authentication and backend connectivity | Runtime alternative; do not silently replace current runtime |
| Bryntum | Technician timeline, holds, paid status and approved recovery | Trial/package access, Angular wrapper, licence and backend persistence | Core showcase |
| Channel3 | Product/parts discovery for a separately justified extension | Server-side product API key or authenticated product MCP; locale/fulfilment decisions | Optional; initial booking flow does not need it |
| Elastic | Retrieve service/qualification policies with evidence IDs | Cluster, scoped data/inference access, ingestion; optional agent features need matching tier | Optional retrieval or runtime alternative |
| KERNEL | Work with a controlled legacy portal lacking an API | Browser infrastructure account/key and authorized target; session cleanup | Add only for real legacy workflow |
| Postman | Share repeatable API checks and failure evidence | Collection/environment mapping; local runs can differ from cloud-authenticated CLI needs | Development/testing support |
| Render | Host current app with durable storage; optional recovery jobs | Service/database/provisioning; hosted env values and secrets configured separately | Delivery choice |
| Zapier | Customer-approved operational follow-up in a connected test app | MCP server, app OAuth/connections and scoped tools; key alone is insufficient | Optional after core is stable |

Detailed sections below cite current official setup sources and distinguish source examples from application glue. The companion earlier research report covers awards and comparative selection; this handbook focuses on implementation.

## Configuration and secrets contract

The supplied `slotsaver-integrations.env.example` contains **empty placeholders**, not credentials or a drop-in configuration for an unseen repository. Keep real `.env` local and ignored by Git; publish only safe examples. A licence string or PayPal client ID can be intended for browser use, but backend API keys, PayPal client secret, session/bearer tokens, deployment tokens and MCP connection tokens must not enter the browser bundle or generated frontend config.

Angular does not automatically consume a root `.env`. Implement a deliberate public-only build/runtime configuration mapping using the project's existing convention. The backend's config loader must read only the relevant values. Never serialize the entire environment into frontend config, health endpoints, traces or error messages.

Distinguish four classes:

| Class | Examples | Correct handling |
| --- | --- | --- |
| Application configuration | Proposed feature flags, backend URL, database URL, selected model | Reconcile with existing schema; validate types and modes |
| Public client configuration | PayPal client ID, approved licence strings | Explicit allowlist before frontend exposure; follow vendor licence conditions |
| Server/automation secrets | PayPal secret, search key, database credentials, CLI/deploy API key, MCP token | Backend/CI/secret store only; never include values in logs |
| User/account state | App OAuth grants, trial activation, sandbox buyer account, service deployment, installed coding plugin | Manual/account workflow; `.env` cannot manufacture it |

### Preflight the coding agent should implement

- Check enabled features only. Report **configured / missing / unsupported**, with variable names and non-sensitive next steps; never print values, token prefixes, URLs containing tokens or secret-bearing exception bodies.
- Reject obvious placeholders (`YOUR_…`, `REPLACE_…`, `changeme`) and invalid modes. PayPal must remain sandbox for this POC; missing credentials must not trigger a silent simulated or live switch.
- Validate endpoint roles: distinguish public application URL, private backend tools, model gateway, deployment-management API and user-authenticated chat API. Do not reuse one vendor token across unrelated endpoints.
- For a disabled optional integration, do not require its key or install/start its SDK. Keep fixture mode explicit. Missing optional access is a scoped blocker, not a reason to rebuild the application.
- Validate adapter/package capabilities and required account setup after key presence; a filled variable alone is not proof of a working connection.
- Run paid/network-mutating smoke tests deliberately on synthetic/sandbox data, bound retries/spend and clean up temporary sessions/resources. Never replay an ambiguous capture blindly.

## Repository deliverables after continuation

Use the existing structure; proposed document paths can be adapted. Preserve the original security/test requirements.

- `docs/integration-gap-matrix.md`: selected/deferred tool decisions and actual code paths.
- `docs/integration-config.md`: variable mapping, public/server boundary, manual setup, account limits and no secret values.
- `docs/integration-evidence.md`: exact commands, timestamps, sanitized outcomes and NOT RUN/BLOCKED cases. Use **DOCUMENTED, IMPLEMENTED, VERIFIED_CONNECTED, VERIFIED_FIXTURE, BLOCKED, DEFERRED** consistently.
- One reviewed adapter per selected external service; migrations and idempotency/concurrency tests remain in the existing backend.
- Reproducible setup and sponsor-use evidence, plus the five-minute team runbook and separate under-three-minute submission script already requested.

The following research modules are deliberately reference material. Read the modules for selected integrations first; defer unrelated modules without deleting working functionality or fabricating sponsor usage.

## What the user needs to configure

Fill only the selected integration's entries, after the coding agent confirms its actual schema. Existing working values do not need replacement. Credentials are entered locally or in the relevant host secret store, not into this report.

| Tool | User/account preparation | Key/config to supply locally | Not solved by `.env` |
| --- | --- | --- | --- |
| PayPal | Sandbox REST app, business seller, personal buyer | Client ID/secret; intended seller identity; webhook ID if enabled | Browser approval and actual webhook registration/HTTPS |
| AG Studio | Trial/licence for selected features/deployment | Licence string; existing model-provider config if AI selected | Package compatibility, frontend licence mapping and model adapter |
| APIMatic | Install plugin in the actual coding assistant | No runtime key for pre-enabled PayPal plugin | Assistant activation/reload and proof of real use |
| Astropods | Account, CLI login, project and deployment | Actual deployment locator; approved backend-tool auth as needed | External chat caller authentication lifecycle remains a validation gate |
| Bryntum | Trial or licensed package access and demo rights | Follow vendor/package setup; no invented universal licence env key | Installing a compatible component/wrapper |
| Channel3 | Developer account/key, applicable sponsor credits | CHANNEL3_API_KEY | Actual locale/results/offer and product-fit validation |
| Elastic | Cluster/project and scoped index key; separate setup writer | Elasticsearch URL and read key; ingestion key only for setup | Index/mappings/ingestion and any inference/agent entitlement |
| KERNEL | Account and suitably scoped project key | KERNEL_API_KEY | Authorized target, network reachability and resource cleanup |
| Postman | Installed compatible client/CLI; optional account auth | POSTMAN_API_KEY only for the selected API-key login path | Collection scripts, private environment mapping and test execution |
| Render | Existing repo connection, persistent DB/service, optional registered workflow | API key only if needed; actual task slug for workflow calls | Service provisioning, migrations, hosted secrets and deployment authorization |
| Zapier | Dedicated MCP server, app connection, restricted selected action | ZAPIER_MCP_TOKEN; actual allowed tool identifier | App OAuth/permissions, action configuration and write approval |

These names follow the companion template's explicit mapping rules. In particular, do not create an APIMatic runtime key or invent a Bryntum `.env` licence setting just to fill a table.

Shell examples in the reference modules assume only their required variables have been made available through a trusted configuration mechanism. A backend dotenv loader does not automatically export values to an unrelated shell. Do not `source` an untrusted `.env`, enable shell tracing or print secret-bearing commands/responses. Adapt source examples into the existing HTTP/configuration layer where that is safer and more reproducible.

Secret interpolation in a shell command does not hide expanded `curl` headers or CLI login arguments from process inspection. Prefer the application HTTP client and interactive desktop login where supported; reserve secret-bearing CLI arguments for an isolated trusted runner. No source-checked command below was executed by the research agents.

## Reference module index

- [Module 1: PayPal Sandbox core](#module-1-paypal-sandbox-core)
- [Module 2: AG Studio and APIMatic](#module-2-ag-studio-and-apimatic)
- [Module 3: Bryntum and Astropods](#module-3-bryntum-and-astropods)
- [Module 4: Channel3 and Elastic](#module-4-channel3-and-elastic)
- [Module 5: KERNEL and Postman](#module-5-kernel-and-postman)
- [Module 6: Render and Zapier](#module-6-render-and-zapier)

---

## Module 1: PayPal Sandbox core


**Checked against official documentation: 25 October 2026.** Continue the existing repository and its working vertical slice. Do not recreate the app, rename working configuration gratuitously, or replace a reviewed SDK solely because this handoff uses REST templates. No account actions or network integration tests were performed. Examples below are **source-checked HTTP contracts, unexecuted**, not tested application code.

### 1. Establish what already exists

Inspect repository instructions, git status, payment adapter, settings loader, migrations, hold/payment model, frontend callbacks and tests. Record IMPLEMENTED / VERIFIED / SIMULATED / BLOCKED / NOT RUN per capability. Retain existing variable names and map the proposed schema below into them. Keep unrelated changes. Start from the smallest missing step: configuration validation, authentication, create, approval, capture, reconciliation, then webhooks and failure evidence.

### 2. Manual account and browser setup

In the Developer Dashboard, select **Sandbox**, open **Apps & Credentials**, use/create a REST app, and copy its Client ID and secret privately. Get personal buyer and business seller test-account credentials from **Testing Tools > Sandbox Accounts > View/Edit Account**. Browser approval uses the personal sandbox account, not the seller login. Confirm the selected app belongs to the intended seller. Configuration cannot create these accounts or grant product permissions. PayPal notes that account requirements vary for testing outside the US. [Get started](https://developer.paypal.com/api/rest/), [sandbox account roles](https://developer.paypal.com/sandbox-testing/accounts).

For webhooks, deploy or forward a reachable HTTPS listener on port 443, then subscribe its URL under that same Sandbox app (or use the management API). Record the resulting **webhook subscription ID**, not an event ID, client ID or merchant ID. Configure a new subscription/update whenever the externally reachable URL changes. PayPal retries unsuccessful deliveries; the listener needs durable intake and idempotency. [Webhook setup](https://developer.paypal.com/api/rest/webhooks/rest/).

**What .env alone cannot do:** account/app creation, buyer browser login/consent, public HTTPS forwarding, webhook registration/event selection, installation of the frontend SDK, creation/migration of the application DB, or verification of an actual purchase. Do not mark these complete because strings are present.

### 3. Proposed environment schema

These names are **SlotSaver configuration proposals**, not guaranteed names automatically consumed by PayPal SDKs. An existing SDK receives explicit constructor/configuration values using its installed-version API. The official protocol uses OAuth Basic/Bearer authentication and JSON fields; it does not read a universal .env schema.

```dotenv
## Project mode: do not confuse this with real/live payments.
PAYMENTS_MODE=sandbox
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
PAYPAL_EXPECTED_MERCHANT_ID=
PAYPAL_CURRENCY=USD
## Project-selected frontend callback routes; adapt to existing routes.
PAYPAL_RETURN_URL=http://localhost:4200/checkout/return
PAYPAL_CANCEL_URL=http://localhost:4200/checkout/cancel
## blank is allowed only until real webhook intake is enabled
PAYPAL_WEBHOOKS_ENABLED=false
PAYPAL_WEBHOOK_ID=
PAYPAL_WEBHOOK_URL=
PAYPAL_HTTP_TIMEOUT_SECONDS=15
## Project-owned public origin; authenticated API routes still enforce ownership.
PUBLIC_APP_ORIGIN=http://localhost:4200
```

- Required for connected order/capture: client ID, secret, sandbox mode/base URL, configured currency and merchant-identity validation strategy. `PAYPAL_EXPECTED_MERCHANT_ID` is the configured intended seller, **not an API credential**; reconcile it with the app's actual seller and provider order/payee data. Do not guess it from an email address or treat an OAuth token's `app_id` as the merchant ID.
- Required when webhooks enabled: webhook ID and registered reachable HTTPS URL. If disabled, report asynchronous webhook coverage NOT RUN and retain server-side capture/reconciliation. Never bypass signature checks when ID is missing.
- Return/cancel settings are required for the redirect integration shown below; a working SDK-button flow may manage navigation differently. Keep its reviewed integration rather than adding two competing checkout flows.
- Client ID can be intentionally exposed to a browser SDK. Secret, access token and DB credentials stay server-side. Buyer passwords are manual test credentials, not application environment requirements.
- Load .env with the project's parser; do not execute it as shell code. Keep `.env` ignored, a placeholder-only `.env.example` tracked, and deployment secrets in the host secret store. Never ask the user to paste secrets into a chat.

### 4. Secrets-safe configuration and preflight

Implement a command using the existing settings loader. Static validation is the default: check required names, nonblank/nonplaceholder values, allowed modes, URL formats and compatible options. Refuse live mode or a base URL other than the exact approved Sandbox origin for this POC. Validate callback origins against configured application origins; permit localhost HTTP only in explicit local development. Webhook public URLs must be HTTPS.

Print only capability statuses and missing variable **names**, for example `paypal_auth: NOT_RUN`, `webhook_config: MISSING(PAYPAL_WEBHOOK_ID)`. Never print values, partial secrets, hashes, Authorization headers, full HTTP payloads or `.env` contents. Scrub exception messages and HTTP debug logs. Checking presence is not verification.

A separately invoked `--network` preflight may perform an OAuth exchange and report AUTHENTICATED with HTTP status/time and a sanitized diagnostic ID. It must not create/capture orders or register webhooks automatically. Token success proves app authentication only, not seller identity, buyer approval, webhook delivery, payment capture, or all account entitlements. Do not persist the token in .env.

### 5. Exact HTTP contracts

`BASE` below is the approved Sandbox origin. Placeholder substitution happens in application memory. These are not commands to paste into a shell containing secrets.

#### Authenticate

```http
POST https://api-m.sandbox.paypal.com/v1/oauth2/token
Authorization: Basic BASE64(CLIENT_ID:CLIENT_SECRET)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
```

Use the HTTP client's Basic-auth support so encoding is correct; do not log the header. Read `access_token`, `token_type` and `expires_in`; cache server-side with an expiry margin and send `Authorization: Bearer <token>` on REST calls. Refresh on expiry using the same exchange. [Official authentication](https://developer.paypal.com/api/rest/authentication/).

#### Create order — redirect example

```http
POST BASE/v2/checkout/orders
Authorization: Bearer <access_token>
Content-Type: application/json
PayPal-Request-Id: <persisted-create-operation-uuid>
Prefer: return=representation

{
  "intent": "CAPTURE",
  "purchase_units": [{
    "reference_id": "<server-booking-reference>",
    "custom_id": "<server-payment-attempt-reference>",
    "amount": {"currency_code": "USD", "value": "80.00"}
  }],
  "payment_source": {
    "paypal": {
      "experience_context": {
        "return_url": "<configured-return-url>",
        "cancel_url": "<configured-cancel-url>"
      }
    }
  }
}
```

Derive price/reference fields from the authenticated held booking, persist returned order ID, and return only needed checkout data. Use returned `payer-action`/`approve` link appropriate to the response; do not fabricate checkout URLs. `application_context.return_url` is deprecated in favor of payment-source experience context. [Create-order schema](https://developer.paypal.com/api/orders/v2/orders-create).

#### Buyer approval and capture

Browser approval is required for this wallet flow. After return/SDK approval, ask the authenticated backend to capture its **stored** order, then call:

```http
POST BASE/v2/checkout/orders/<stored-order-id>/capture
Authorization: Bearer <access_token>
Content-Type: application/json
PayPal-Request-Id: <persisted-capture-operation-uuid>
Prefer: return=representation

{}
```

Inspect order and capture results, including `purchase_units[].payments.captures[]`, capture ID/status, gross amount/currency and payee context; a `COMPLETED` capture is the payment event needed here, not buyer approval alone. Pending states remain pending. [Capture-order schema](https://developer.paypal.com/api/orders/v2/orders-capture).

**Application requirements:** recheck owner, stored order/payment-attempt association, expected seller, fixed price and capacity rules. Persist unique capture ID and booking effect transactionally. Return/cancel query parameters are untrusted navigation signals. A failed browser callback cannot erase a capture; a successful one cannot invent it.

#### Reconcile uncertain outcomes and retries

Persist **distinct stable UUIDs** for logical create and capture operations before sending. Retry the same operation with the same ID and payload after a timeout/eligible transient failure; never generate a new ID merely because the response was lost. Concurrent requests using one ID may still fail; serialize application writes. PayPal's retention is finite/API-specific, so local durable uniqueness remains necessary. [Idempotency](https://developer.paypal.com/api/rest/reference/idempotency/).

Use `GET BASE/v2/checkout/orders/<stored-order-id>` to inspect order state when the result is ambiguous; investigate provider evidence before another effectful operation. [Order API endpoints](https://developer.paypal.com/api/orders/v2). Do not hardcode a universal retention period or indiscriminately retry business validation errors. Preserve payment-exception state when capacity expired; never confirm unavailable capacity.

### 6. Webhook verification and durable processing

Read the incoming raw body and required headers with bounded size. Retain raw bytes if self-verification is used. For the simpler reviewed postback method, submit the received event object and header mapping below using the app's bearer token:

The verified endpoint is `POST BASE/v1/notifications/verify-webhook-signature` with the app Bearer token and JSON content type. Build the payload from the actual incoming headers and parsed object. **Application-adapted Python sketch, not an executed HTTP client:**

```python
## request_headers comes from the existing framework's case-insensitive header map.
## parsed_event is the actual parsed incoming webhook object, not a JSON string.
if not isinstance(parsed_event, dict):
    raise ValueError("Expected webhook object")
payload = {
    "auth_algo": request_headers["PAYPAL-AUTH-ALGO"],
    "cert_url": request_headers["PAYPAL-CERT-URL"],
    "transmission_id": request_headers["PAYPAL-TRANSMISSION-ID"],
    "transmission_sig": request_headers["PAYPAL-TRANSMISSION-SIG"],
    "transmission_time": request_headers["PAYPAL-TRANSMISSION-TIME"],
    "webhook_id": configured_subscription_id,
    "webhook_event": parsed_event,
}
## POST payload with the existing HTTP client's JSON-body option and app Bearer auth.
## Never log payload or authorization. Handle missing headers as verification failure.
```

Accept only a successful verification response whose `verification_status` equals `SUCCESS`. Missing headers, verification FAILURE, timeout or unexpected response never authorize business processing. [Verify-signature contract](https://developer.paypal.com/api/webhooks/v1/verify-webhook-signature-post).

Mock simulator events are not app-associated and do **not** support postback verification. Test this method with actual app Sandbox transaction events. Self-verification requires the original raw body/CRC32 and certificate signature checks; adding it is a separate security-reviewed implementation. Do not copy documentation debug logging into the app or fetch arbitrary certificate URLs without validation. [Verification methods and simulator limitation](https://developer.paypal.com/api/rest/webhooks/rest/).

Select `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.PENDING`, `PAYMENT.CAPTURE.DECLINED`, and other lifecycle events the application actually handles. `CHECKOUT.ORDER.APPROVED` signals approval, not completed capture. Add refunded/reversed handling if tracking those states; do not mistake Payments-v1 `DENIED` for the Payments-v2 event name without checking the integration. [Official event catalogue](https://developer.paypal.com/api/rest/webhooks/event-names/).

**Application requirements:** unique event-ID intake, capture-ID uniqueness, out-of-order state protection and idempotent replay. Persist verified intake before acknowledging success; duplicates already durably handled may return 2xx. Verification failure never mutates booking/payment state. Verification/provider or persistence outages need an explicit retryable response and redacted operations record. Signature validity does not replace matching event order/capture/seller/amount to a known payment attempt. The webhook route does not use customer-session authentication; signature verification supplies provider authenticity. Do not expose a public business-mutation endpoint merely to simplify callbacks.

### 7. Completion evidence for the existing agent

1. Static preflight passes with no secret output; missing optional integrations are separately reported.
2. OAuth-only network check authenticates; capture remains untouched.
3. Actual browser Sandbox buyer approval, backend capture and durable booking confirmation survive refresh/restart.
4. Cancel/expiry never confirms unpaid bookings; competing holds yield one winner.
5. Duplicate requests/events and a capture timeout produce one capture effect; altered amount, foreign order, missing signature and invalid signature are rejected.
6. Actual Sandbox webhook is verified, durably deduplicated and linked to the payment attempt. Simulator delivery alone is not this evidence.
7. Redacted evidence records commands, dates, outcomes and explicit skips. Keep live records separate from offline fixtures. Continue remaining sponsor adapters only after payment invariants pass; credentials do not justify restarting the app.

---

## Module 2: AG Studio and APIMatic


Checked against official sources on 25 October 2026. **Source examples were read; commands and snippets below were not installed, compiled or executed against SlotSaver.** No application repository was present in this research workspace. These notes therefore require the existing coding agent to inspect its actual repository before applying anything. Preserve its code, framework, endpoint names, authentication, tests and lockfile. Do not scaffold a replacement app.

### 1. Inspect the existing implementation first

From the actual checkout, read AGENTS.md and repository instructions, package.json/lockfile, Angular configuration, owner dashboard, API client, model adapter, configuration loading and environment templates. Run its baseline build/tests. Inventory implemented booking/payment APIs before adding endpoints. Record whether AG Studio is already installed, its exact version, and whether analytics uses actual or fixture data. Never print populated .env values.

The compatibility decision is blocking: current docs support Angular 20–22 with Studio 1–3+, but Angular 18–19 with Studio 1 only. Studio 2–3+ needs TypeScript >=5.8.3; Studio 1 needs >=5.4.5. Studio 3.0 matches Grid36.2/Charts14.2; Studio1.1 matches Grid35.3/Charts13.3. Existing standalone grids must align. For Angular18/19, use archived Studio1 documentation or explicitly plan a reviewed framework upgrade; do not silently force-install Studio3. [Official matrix](https://www.ag-grid.com/studio/angular/compatibility/)

### 2. AG Studio: install and initialize the smallest slice

After selecting versions compatible with the checkout, use its existing package manager. Official npm install syntax is:

```bash
npm install ag-studio-angular
```

The Angular wrapper brings in `ag-studio`; versions of both packages must be identical. Pin the selected version in the lockfile. If importing AI APIs, register `AgStudioAiModule` with `AgStudioModuleRegistry`. Enable development validations before constructing Studio using the repository's build-mode mechanism; do not assume Angular exposes Node's `process.env`. [Installation](https://www.ag-grid.com/studio/angular/installation/)

Official quick-start APIs, expressed as a small **adapted integration sketch, not a complete tested component**:

```ts
// Inside the existing standalone owner-dashboard component:
// import { AgStudio } from 'ag-studio-angular';
// add AgStudio to that component's imports.
const studioInput = {sources: [{id: 'bookings', data: authorizedBookingRows}]};
// Template binding: <ag-studio [data]="studioInput" mode="edit" />
```

`authorizedBookingRows` is a project variable loaded through the existing API client; do not create it as a permanent fixture. Give Studio a parent with explicit nonzero height and width. The component accepts record arrays in named sources. [Angular quick start](https://www.ag-grid.com/studio/angular/quick-start/)

**Project integration proposal:** begin with one owner-authorized analytics response, adapted from the existing backend. Return immutable row snapshots with stable booking IDs, service, technician, booking status, payment status, start/end instants, captured minor units and currency. Preserve integer money in backend logic; avoid summing currencies together. Add a display value only at the UI boundary. Refresh analytics and schedule after successful writes using the same canonical backend records. No vendor endpoint is implied by this proposed shape.

For report persistence, store the Studio-generated full state including its version, rather than handcrafting complex widget state. Official APIs include `getState()`/`setState()`; initial load uses `initialState`; ongoing changes emit `stateUpdated`. Saving view-mode changes is an application policy choice. Handle invalid/fatal state with a useful recovery screen. [State and events](https://www.ag-grid.com/studio/angular/state/)

### 3. Trial licence is separate from model credentials

Request a 45-day trial at [AG Studio trial form](https://www.ag-grid.com/studio/license-pricing/?tab=trial). The form asks for company/name/email. Check the supplied licence includes the AI capabilities and intended demo deployment.

The checked licence API is:

```ts
import {AgStudioLicenseManager} from 'ag-studio';
AgStudioLicenseManager.setLicenseKey(studioLicenseFromProjectConfig);
```

`studioLicenseFromProjectConfig` is an application variable. Configure before creating the component. Local evaluation can run without a licence with watermark/warnings; production evaluation/support/removal require the trial. [Licence installation](https://www.ag-grid.com/studio/angular/licence-install/)

Studio's built-in grid/chart widgets are covered by its licence; standalone Enterprise grid/chart instances—including custom widgets using them—require separate licences. A repository's open-source licence does not change commercial dependency rights. [Licence coverage](https://www.ag-grid.com/studio/angular/enterprise-licence/)

A Studio licence is validated in browser JavaScript, so do not misclassify it as a backend API credential. Keep it out of public source where licensing terms require, but do not promise it can remain invisible to a user while used client-side. Model API keys and PayPal secrets must never enter browser configuration.

### 4. Add AI through the existing backend

AG Studio supplies neither a model nor a server. Its AI module is opt-in; the application chooses the model endpoint and pays the model provider. [Framework overview](https://www.ag-grid.com/studio/angular/ai/)

Checked initialization concept:

```ts
// Imported from ag-studio; adapter is application-owned, not a shipped import.
const setup = ({api}) => createAiHarness(api, {adapter: projectAdapter});
```

In the real component, type `setup` as `AgAiHarnessSetup` and bind it to `[ai]`. The docs' `openaiAdapter` is example source to copy/adapt, **not an npm API to import from an assumed `ag-studio-harness/example-shared` installation**. Do not copy the docs' demo proxy endpoint or model IDs. Route requests through the existing authenticated backend. [Agent quick start](https://www.ag-grid.com/studio/angular/ai-quickstart/)

Choose one route:

| Route | Use when | Actual work needed |
| --- | --- | --- |
| Direct LLM Runner + application adapter | Studio owns the browser-side agent loop | Implement `AgLlmAdapter` against the existing backend, preserving streamed text and tool calls; backend authenticates, restricts models and holds provider secret. |
| Client Tool Runner | Existing backend/agent emits turns needing browser tools | Translate backend events to Studio events and feed results back; list only intended browser tools. |
| Custom Runner | Existing agent already owns its complete loop | Implement the documented run contract; do not add a second agent loop around it. |

The Direct LLM adapter passes declared schemas and relays tool-call events; it does not execute business operations. Preserve tool IDs, argument deltas, completion/failure and cancellation. Plain text streaming without tool-call mapping can produce chat that never updates a dashboard. [Direct runner/adapter contract](https://www.ag-grid.com/studio/angular/ai-direct-llm-runner/)

Client Tool Runner accepts an async event stream, executes only listed unresolved client tools, then supplies their results on the next turn. It brackets run boundaries itself. Its AG-UI-shaped events do not require an additional AG-UI dependency. Integrating Astropods requires an actual protocol bridge; endpoint compatibility alone is insufficient. [Client runner](https://www.ag-grid.com/studio/angular/ai-client-tool-runner/)

**Recommended continuation:** initially give the owner analyst read/query/chart operations. Retain the existing booking agent for scheduling/reassignment. If connecting them later, expose bounded application tools through backend authorization. Explicit approval, race-safe slot validation and payment truth remain backend invariants.

### 5. Configuration contract for the coding agent

These are **proposed project environment names**, not variables automatically recognized by AG Studio:

```dotenv
AG_STUDIO_LICENSE_KEY=
SLOTSAVER_ENABLE_AG_STUDIO=false
SLOTSAVER_ENABLE_STUDIO_AI=false
STUDIO_LLM_PROVIDER=
STUDIO_LLM_MODEL=
STUDIO_LLM_BASE_URL=
STUDIO_LLM_API_KEY=
```

Map existing equivalent variables instead of duplicating them. `AG_STUDIO_LICENSE_KEY` feeds the browser licence manager through the project's configuration mechanism. `SLOTSAVER_ENABLE_AG_STUDIO` and `SLOTSAVER_ENABLE_STUDIO_AI` are project feature switches. Provider/model/base URL configure the backend adapter. `STUDIO_LLM_API_KEY` is backend-only; the user obtains it from the chosen model provider, not AG Grid. Do not prefix secrets with frontend-public conventions. The backend should reject enabled AI with missing required settings and return a redacted readiness result. Angular does not automatically read a root .env; use the checkout's established config-generation or runtime-config mechanism.

No universally required AG Studio API key exists. A licence key is used for licensing; model authentication depends on the selected provider. If using an existing shared model adapter, reuse it and its actual environment names.

For strict CSP, Studio supports a per-page style nonce, data-image assets and optional Google font settings; adapt existing policy without loosening it indiscriminately. [Security/CSP](https://www.ag-grid.com/studio/angular/security/)

### 6. APIMatic: enable context in the running coding environment

The PayPal Context Plugin helps the developer agent implement/review PayPal. It is not a browser/runtime dependency. Its sponsor page says the pre-enabled plugin needs no additional APIMatic account credentials. No `APIMATIC_API_KEY` is required for this path. [Sponsor setup](https://paypalaihackathon.devpost.com/details/apimatic)

The official product command is:

```bash
npx context-plugins install paypal
```

Run on the machine/container where the actual coding assistant is installed, after inspecting the installer and checking repository policy. The product page advertises VS Code/Copilot, Claude Code, Cursor and Codex targets. [Product installation](https://www.apimatic.io/product/context-plugins)

The installer requires Node18+, assistant detection and writable user configuration. Use explicit target to avoid changing unrelated assistants. For VS Code:

```bash
npx context-plugins doctor --json
npx context-plugins install paypal --targets vscode
npx context-plugins installed --targets vscode --json
```

Then reload the editor window. For Claude use target `claude` and reload plugins/new session; for Codex use target `codex` and start a new session. VS Code installation registers a local folder in `chat.pluginLocations`. If detection fails, check actual assistant location/CLI, then the installer's diagnostic output; do not fabricate success. [Installer commands and diagnostics](https://github.com/apimatic/context-plugins-installer)

The linked marketplace includes .NET, TypeScript and Python PayPal packs. A language-specific skills alternative exists, but do not install both mechanisms blindly or replace existing project guidance. [Marketplace](https://github.com/context-plugins/plugin-marketplace)

**Continuation task for the coding agent:** load the installed PayPal context, inspect the current payment module, identify unsupported SDK calls or incomplete error/idempotency handling, and make the smallest reviewed changes. Use actual SDK signatures from installed context/source. Do not rewrite working REST code merely to manufacture SDK usage. Retain redacted plugin version/date, loaded skill/source paths, the concrete integration task and test evidence. The sponsor claim form requires a project/repo showing plugin use; subscription claims are manually verified. [Claim form](https://docs.google.com/forms/d/e/1FAIpQLScc2oCgAFACm7d6H3R4mgzv-O34DdyVnLIBNiwmUNggr_-hhA/viewform)

### 7. Smoke checks and failure diagnosis

The following are proposed acceptance checks, not results already achieved.

| Check | Expected evidence | Failure diagnosis |
| --- | --- | --- |
| Package/build | Existing production build passes with a supported version matrix | Inspect peer dependencies and duplicate mismatched `ag-studio` versions; do not bypass with force flags. |
| Owner analytics | Real authenticated API rows appear; known totals reconcile | Check authorization, field names, currencies and nonzero container size. |
| Report reload | A changed widget/filter reloads from saved full versioned state | Ensure stateUpdated is persisted and initialState applied during construction; preserve source IDs. |
| Licence/AI readiness | Correct trial entitlement; owner chat can query schema and create one chart | Missing chat: module/ai binding. Unavailable AI: primary agent configuration. Licence error: key/AI entitlement. Text-only response: lost tool-call mapping. |
| Secret isolation | Browser assets/network do not contain model/PayPal secret | Inspect frontend config generation and server proxy; never log full values. |
| Permission | Customer cannot obtain owner dataset or invoke owner tools | Enforce server roles/object ownership; hiding the Studio route is insufficient. |
| Model failure | Visible useful error; bookings/payments unchanged | Bound retries/timeouts and cancellation; never switch to fixtures silently. |
| APIMatic readiness | Installed plugin loaded by the actual assistant; payment review references context | Editor reload, target detection, user settings and installed record. |
| PayPal regression | Existing success/cancel/duplicate/tamper/reconciliation tests pass | Plugin presence alone provides no correctness proof. |

Complete this slice before adding a custom recovery widget or advanced multi-agent delegation. Record actual command results and distinguish IMPLEMENTED, VERIFIED, BLOCKED and NOT RUN. Never label source-inspected examples as executed integrations.

---

## Module 3: Bryntum and Astropods


Verified against official documentation on 25 October 2026. This is continuation guidance for an already running coding agent. **Preserve the existing application, migrations, data, authentication and working payment flow.** No SlotSaver source tree was available in this shared research workspace, so repository paths, existing interfaces and completed checks could not be inspected. Application glue below is explicitly pseudocode; vendor calls are distinguished from proposed project conventions. No integration was executed.

### 1. Inspect and continue

In the existing repository, inspect AGENTS.md, git status, package manifests/lockfiles, Angular bootstrap style, backend API/OpenAPI, booking models, payment state transitions, adapter interfaces, environment loading and existing tests. Record what already works. Locate the current schedule screen and assistant adapter; replace only their integration seams. Do not run `ng new` in the repository or scaffold an entire application over it.

Use these **project-proposed flags**, translating them to the existing configuration system rather than introducing a second one:

```dotenv
SLOTSAVER_ENABLE_BRYNTUM=true
SLOTSAVER_ENABLE_ASTROPODS=false
SLOTSAVER_AGENT_RUNTIME=existing
```

These are not vendor-required variables. Keep the current runtime until the Astropods smoke path passes. Angular does not automatically read `.env`: expose non-secret flags through the project's existing build-time environment or public runtime-config endpoint. Never expose platform tokens, gateway keys or backend service credentials in Angular bundles.

### 2. Bryntum: install the component, then connect existing data

#### Access and package selection

The hackathon offers a 45-day trial at [Bryntum download](https://bryntum.com/download). Public trial npm packages do not require private-registry credentials. Licensed package access is a separate npm configuration step. A licence string in `.env` does not grant registry/package access or public redistribution rights. The inspected official setup does not establish a required `BRYNTUM_LICENSE_KEY` variable; do not invent one. See [sponsor setup](https://paypalaihackathon.devpost.com/details/bryntum) and [trial Angular quickstart](https://bryntum.com/products/scheduler/docs-llm/guide/Scheduler/quick-start/angular.md).

Source-verified trial command shape, using a published example version rather than an instruction to upgrade the whole application:

```sh
npm install @bryntum/scheduler@npm:@bryntum/scheduler-trial@7.3.7 @bryntum/scheduler-angular@7.3.7
```

Use a mutually compatible, identical core/wrapper version and retain the lockfile. Check the existing repository before selecting it. Angular 12+ uses `@bryntum/scheduler-angular`; the legacy View Engine wrapper is a separate deprecated package. [Angular wrapper guide](https://www.bryntum.com/products/scheduler/docs/guide/Scheduler/integration/angular/guide)

For licensed use, follow the vendor's private npm instructions instead of swapping in an unverified registry token. Bryntum distinguishes end-user and OEM terms and individual developer licensing; confirm trial public-demo and judge-install rights. Keep proprietary distribution files and credentials out of Git. [Licensing](https://bryntum.com/products/license/)

Scheduler is sufficient for a backend-controlled technician timeline. Scheduler Pro adds an engine for rules/calendar/dependency recalculation; do not install plain Scheduler and promise Pro behavior. [Product comparison](https://bryntum.com/products/schedulerpro/scheduler-vs-schedulerpro/)

#### Angular integration seam

Verified symbols/styles from the official Angular integration/tutorial:

```ts
import { BryntumSchedulerComponent } from '@bryntum/scheduler-angular';
// NgModule applications can instead import the documented BryntumSchedulerModule.
```

```css
/* Global stylesheet; confirm these files exist in the pinned installed package. */
@import "@bryntum/scheduler/scheduler.css";
@import "@bryntum/scheduler/material3-light.css";
```

The tutorial supports inline `events`/`resources` bindings or remote loading through CrudManager. Reuse existing application services when analytics and schedule already share fetched records. [Angular tutorial](https://bryntum.com/products/scheduler/docs-llm/guide/Scheduler/tutorial/tutorial-angular.md)

**Application-adapted pseudocode, not a guaranteed drop-in wrapper signature:**

```html
<bryntum-scheduler
  [resources]="scheduleResources"
  [events]="scheduleEvents"
  [columns]="scheduleColumns"
  [startDate]="visibleStart"
  [endDate]="visibleEnd"
  [viewPreset]="'hourAndDay'"
  [listeners]="scheduleListeners">
</bryntum-scheduler>
```

Compile against the pinned wrapper typings and its bundled framework example. Add the wrapper to the existing standalone component imports or NgModule as appropriate. Use a fixed container height initially; a blank schedule often reflects missing layout height or styles.

Vendor data fields shown in the [Scheduler introductory example](https://bryntum.com/products/scheduler/docs/) include resource `id`/`name` and event `resourceId`, `startDate`, `endDate`, `name`. Map canonical technician and booking IDs into these fields; include explicit booking status and row version in your own DTO. Dates must denote the correct instants, with one consistent display timezone. Read data only through the already authorized owner endpoint; avoid putting customer payment details into event tooltips.

#### Load/save and conflict handling

Choose one write owner: existing HTTP service with refreshed inline arrays, or a deliberately implemented CrudManager transport. Do not turn on both autosync and custom save hooks, which can duplicate writes. Existing APIs are usually the smaller continuation path. Do not invent a Bryntum-specific server endpoint merely to make a screenshot work.

The documented `beforeEventDropFinalize` hook supports asynchronous validation using `context.async = true` and `context.finalize(true|false)`; synchronous validation uses `context.valid`. [Scheduler EventDrag API](https://bryntum.com/products/scheduler/docs-llm/api/Scheduler/feature/EventDrag.md) / [Scheduler event documentation](https://www.bryntum.com/products/scheduler/docs/guide/Scheduler/quick-start/data/Core/images/examples/api/Scheduler/view/Scheduler)

**Pseudocode adapting that documented hook to the existing backend:**

```ts
beforeEventDropFinalize({ context }) {
  context.async = true;
  void (async () => {
    let saved = false;
    let saveError;
    try {
      await persistCandidateUsingExistingBookingAPI(context);
      saved = true;
    } catch (error) {
      saveError = error;
    }
    // Settle from persistence outcome exactly once, before any refresh.
    context.finalize(saved);
    if (!saved) showActionableError(saveError);
    try {
      await reloadCanonicalScheduleAndAnalytics();
    } catch (refreshError) {
      // A refresh failure never undoes a committed write or finalizes again.
      showRefreshError(refreshError, { mutationSaved: saved });
    }
  })();
}
```

Do not guess candidate IDs/date fields from this pseudocode: inspect the installed event context type and verify drag and resize paths separately. Always settle an async finalization exactly once, including cancellation and network errors. A server timeout is ambiguous: reload state before retrying a mutation.

Backend requirements below are SlotSaver design requirements, not Bryntum features:

- Authorize the operator and booking object, enforce skill/business-hour/availability rules and validate expected booking version.
- Perform reservation/reassignment atomically. A prior availability GET cannot prevent two concurrent writes.
- Reject overlaps with the repository's existing documented conflict response (commonly HTTP 409); show the response reason and reload.
- Customer-approved reassignment remains a proposal until acceptance. An owner dragging a paid booking must not bypass that workflow.
- Browser changes never establish payment completion. Display the server's verified status after capture/webhook reconciliation.
- Keep booking and financial totals from the same canonical data; do not increment captured revenue in a UI event listener.

#### Bryntum minimum proof

Load three technicians and seeded bookings; confirm correct dates/status after refresh. Persist one permitted change. Attempt a conflict from UI and direct API; both must fail without modifying canonical state. Race two requests for the same slot; exactly one succeeds. Reject unauthorized edits. Simulate save timeout, reload, and confirm no duplicated mutation. Complete a real PayPal Sandbox booking and verify the refreshed timeline. Run the existing frontend build and targeted scheduling integration tests.

Diagnostics: inspect core/wrapper version mismatch and duplicate bundles; verify actual stylesheet files and container height; verify listeners are bound in the Angular template; distinguish a 401/private-registry problem from a licence right. Do not broadly wipe caches or regenerate lockfiles as the first response. The [Angular troubleshooting guide](https://bryntum.com/products/scheduler/docs-llm/guide/Scheduler/integration/angular/troubleshooting.md) notes that adding a property to a config object alone has no effect if its corresponding Angular input was never bound.

### 3. Astropods: preserve the existing assistant behind an adapter

#### Account, CLI and authentication

Get the advertised free account from [Astropods](https://astropods.com/) via the [hackathon sponsor page](https://paypalaihackathon.devpost.com/details/astropods). Free access is not an unlimited hosted-runtime allowance: account signup credits and spend caps must be checked before a live demo. [Usage limits](https://docs.astropods.com/usage-limits)

The official Linux/macOS installer command is shown below for reference. Inspect the downloaded installer before executing it in your actual development environment; this handbook has not run it:

```sh
installer_dir="$(mktemp -d)"
curl -fsSL https://astropods.com/install -o "$installer_dir/ast-install.sh"
## Inspect the downloaded script and its verification/download behavior first.
## Only after review, run this as a separate deliberate step:
## sh "$installer_dir/ast-install.sh"
## Then verify the installed command:
## ast --version
## ast --help
```

The installer documents checksum verification, `~/.ast/bin` installation and PATH setup. [CLI installation](https://docs.astropods.com/install-cli)

```sh
ast login
ast whoami
```

This is a device authorization flow. Access tokens last roughly one hour; the CLI refreshes them. Credentials use the system keyring or a restricted local credentials file. Do not scrape that file into the app, copy browser cookies, or assume that `ast login` automatically supplies a long-lived production backend credential. [Authentication](https://docs.astropods.com/authentication)

#### Local harness without replacing SlotSaver

If a harness already exists, keep it. If absent, generate a **separate integration subdirectory** and adapt only the existing assistant implementation into it after checking repository conventions:

```sh
ast project create slotsaver-agent --model gateway
ast project configure
ast project start
```

Docker must be running. The scaffold includes `astropods.yml` and coding-agent instructions; configuration prompts are driven by declared inputs. Gateway mode uses account authentication; BYOK modes exist for Anthropic/OpenAI. Do not create a second independent booking database in the harness. [Local quickstart](https://docs.astropods.com/get-started)

For a Python assistant, a documented integration surface is:

```sh
pip install astropods-adapter-core
```

```py
from astropods_adapter_core import StreamHooks, StreamOptions, serve
```

Implement the documented adapter `stream(prompt, hooks, options)` and `get_config()`, call existing assistant logic, and emit chunks followed by exactly one finish/error. Configure `agent.interfaces.messaging: true`. Local web testing uses the documented messaging adapter and chat at `http://localhost:3100`; `serve()` connects to `localhost:9090` unless `GRPC_SERVER_ADDR` overrides it. Treat options.user_id as an Astropods identity, not automatically as a SlotSaver customer ID; explicitly map identities. [Python custom adapter](https://docs.astropods.com/adapters/python/custom-adapter)

#### Model call versus deployed-agent invocation

These are separate APIs and credentials.

**Agent → managed model:** the runtime injects `ASTRO_GATEWAY_URL`, `ASTRO_GATEWAY_API_KEY` and `MODEL_<NAME>` for declared gateway models. Do not ask users to manually invent those values or reuse that key as a platform management token. [Gateway configuration](https://docs.astropods.com/ai-gateway)

Source-verified Python SDK pattern, adapted to the selected runtime model:

```py
import os
from openai import OpenAI
client = OpenAI(
    api_key=os.environ["ASTRO_GATEWAY_API_KEY"],
    base_url=f"{os.environ['ASTRO_GATEWAY_URL'].rstrip('/')}/v1",
)
result = client.chat.completions.create(
    model=os.environ["MODEL_DEFAULT"],
    messages=[{"role": "user", "content": "Return a short greeting."}],
)
```

Use the already installed compatible OpenAI SDK or add it through the repository's normal dependency process. This smoke call has no booking tools. The `/v1` suffix is required. Model calls succeeding do not prove agent deployment/chat works. [Gateway chat completions](https://docs.astropods.com/ai-gateway/chat)

**SlotSaver backend → deployed agent:** the official REST chat API is documented, so do not invent `/invoke`, `/agent/chat` or an OpenAI-compatible URL for the deployed agent:

| Step | Official endpoint | Credential |
| --- | --- | --- |
| Optional create conversation | `POST https://astropods.com/api/v1/deployments/{deploymentId}/messaging/conversations` | User OAuth device-flow or platform session bearer token |
| Send user message | `POST https://astropods.com/api/v1/deployments/{deploymentId}/messaging/conversations/{conversationId}/messages` | Same authorized caller |
| Receive reply | `GET https://astropods.com/api/v1/deployments/{deploymentId}/messaging/conversations/{conversationId}/stream` | Same caller; SSE |

Creation returns `conversation_id`; a caller can alternatively choose UUID v4 on first send. [Create API](https://docs.astropods.com/api-reference/astropods-api/chat/create-chat-conversation)

Send accepts JSON `content`; the acceptance response is a message ID/timestamp, **not the assistant response**. An optional `parent_id` catches stale branches with HTTP 409. Conversation ownership is scoped to caller identity. [Send API](https://docs.astropods.com/api-reference/astropods-api/chat/send-chat-message)

Subscribe after send. SSE includes `connected`, incremental content and terminal `finish` or `error`. Preserve framing across chunk boundaries. Do not implement browser `EventSource` with an assumed bearer header; it cannot set arbitrary headers. Use an authenticated backend relay or a verified suitable client. [Stream API](https://docs.astropods.com/api-reference/astropods-api/chat/stream-chat-conversation)

**Authentication blocker:** the inspected docs establish user device/session auth, not a service-account/client-credentials grant or a production token-export workflow. A backend relay must have an approved supported credential lifecycle and per-user conversation mapping. Obtain vendor confirmation if unattended server-to-server auth is required. Do not ship a copied developer access token, disable authentication, or silently use one person's conversation for all customers. Until resolved, retain the existing assistant and label Astropods external integration BLOCKED; the authenticated built-in chat can still validate the deployed harness independently.

#### Configuration ownership

| Name | Owner / usage | Safe placement |
| --- | --- | --- |
| `ASTRO_GATEWAY_URL`, `ASTRO_GATEWAY_API_KEY`, `MODEL_DEFAULT` | Vendor runtime-injected gateway config for a declared `default` model | Agent container; key secret |
| `GRPC_SERVER_ADDR` | Vendor adapter override; default localhost:9090 | Agent container configuration |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Optional provider BYOK, obtained from selected provider | Local agent config/account vault, never frontend |
| `OTEL_EXPORTER_OTLP_ENDPOINT`, `ASTRO_AGENT_NAME`, `ASTRO_AGENT_BUILD` | Vendor-injected deployed telemetry context | Agent instrumentation; do not fabricate endpoint |
| `SLOTSAVER_ASTROPODS_DEPLOYMENT_ID` | Proposed SlotSaver locator, copied from actual deployment output | Backend configuration |
| `SLOTSAVER_ASTROPODS_API_BASE_URL` | Proposed backend API origin; default official host only if applicable | Backend configuration |
| `SLOTSAVER_BACKEND_BASE_URL` | Proposed agent tool target | Non-secret config; network-reachable deployed API |
| `SLOTSAVER_BACKEND_SERVICE_TOKEN` | Proposed scoped tool credential, if existing auth supports it | Vault/runtime secret; separate from platform/gateway keys |

Proposed variables are not automatically consumed by Astropods; wire them deliberately through the existing app config and valid spec inputs. An agent reaching a laptop's `localhost` will reach its own container, not the developer backend. Expose an authenticated reachable test backend or use a vendor-supported network arrangement.

Account vault creation prompts mask secret input:

```sh
ast secrets create SLOTSAVER_BACKEND_SERVICE_TOKEN
```

The name above is project-proposed, while the CLI command and vault reference syntax are vendor documented. Deployment `--var KEY=@SECRET_NAME` resolves a vault entry. Avoid literal secret arguments/history and avoid bulk-importing unrelated `.env` entries. [Secrets guide](https://docs.astropods.com/secrets)

After validating the existing spec and actual CLI help, build/push the harness blueprint using the documented workflow and deploy that blueprint. Confirm the real name from `ast blueprint list`:

```sh
ast blueprint push slotsaver-agent
ast blueprint deploy slotsaver-agent --dry-run
ast blueprint deploy slotsaver-agent
ast agent list
```

Default web access is authenticated; do not choose `insecure-web` to work around auth. Dedicated frontend-agent mode has different behavior and is unnecessary for adapting the current Angular app. [Deployment guide](https://docs.astropods.com/deploy-agent) / [Blueprint guide](https://docs.astropods.com/blueprints)

#### Astropods smoke checks and diagnostics

1. Record CLI/SDK versions and run `ast whoami` without printing tokens.
2. Start the existing harness locally; send a greeting through its documented local chat.
3. Exercise an actual read-only SlotSaver tool; compare its returned availability with the direct backend result.
4. Push/deploy, observe running status, and repeat through authenticated built-in web chat.
5. With a supported caller credential, test create → send → SSE, timeout, ownership denial and terminal error.
6. Verify the assistant cannot bypass booking authorization, price validation or customer reassignment approval.
7. Inspect redacted tool/model traces; custom raw adapters need deliberate tracing. The deployed OTLP endpoint is absent locally, so guard instrumentation. [Monitoring](https://docs.astropods.com/monitor-agents)
8. Only then switch the proposed runtime flag; retain an explicit tested rollback to the existing runtime.

Model `404`: check gateway base `/v1`. Model `401`: distinguish gateway credentials from platform login and reload injected config. `429`: inspect budget/rate limits and back off boundedly. Chat `401/403`: caller auth/access; chat `404`: deployment ID or conversation ownership; `409`: stale branch, not a reason to silently resend. Endless spinner: confirm the adapter emitted a terminal finish/error and SSE parser preserved events. Gateway model success with no chat reply: inspect messaging interface/sidecar/adapter wiring. None of these errors justifies retrying payment capture or mutating a booking again.

### 4. Completion evidence and unresolved items

Report independently: installed packages, rendered scheduler, persisted/rejected schedule writes, local harness, deployed harness, gateway model smoke and external chat API smoke. Use VERIFIED only for executed checks, DOCUMENTED for this research, BLOCKED for missing rights/auth and NOT RUN for remaining checks. No live smoke tests were executed while preparing this handbook.

Unresolved: actual repository layout/versions; precise installed Bryntum wrapper types and resize context; licence/trial distribution rights; actual Astropods account credits; unattended external-API credential lifecycle; identity mapping; deployed backend reachability; account-specific model availability. Resolve these narrow seams while preserving all working SlotSaver code.

---

## Module 4: Channel3 and Elastic


Verified against official documentation on 25 October 2026. **All snippets below are unexecuted integration examples, not evidence of a working connection.** No credentials were used. There is no SlotSaver source checkout in the inspected workspace: only proposal/prompt documents were found. Therefore exact existing modules, dependencies, routes and test commands remain unknown.

### Start with the existing project

The coding agent must first locate the actual checkout, read its `AGENTS.md` and README, inspect Git status, dependency/lock files, settings, API routes, adapters, agent tools and tests. Record the working baseline before editing. Reuse existing HTTP/client lifecycle, settings, authentication, error handling and UI components. Do not create a replacement app or restart implementation from the earlier prompt. Suggested route and environment names in this handoff are application proposals, not claims about existing code.

### Channel3: optional product-discovery adapter

#### Fit and account setup

Use only if SlotSaver has a meaningful customer need for product discovery. A small optional “care accessories” search is more bounded than replacement-part compatibility; it must not invent appliance compatibility or fold third-party goods into the service booking charge. Keep Channel3 disabled if it adds no useful outcome.

Create a developer account, retrieve the API key from its dashboard, and apply `PAYPAL-HACKATHON-2026` for the sponsor's advertised 20,000 credits. No card is required according to the sponsor. **Meaningful actual API/MCP use is required for the Channel3 sponsor category.** [Official sponsor setup](https://paypalaihackathon.devpost.com/details/channel3).

#### Minimal HTTP smoke call

No Channel3 SDK dependency is necessary for this HTTP route; reuse the project's HTTP library. The documented endpoint is `POST https://api.trychannel3.com/v1/search`, authenticated using `x-api-key`. `CHANNEL3_API_KEY` follows the documentation example's shell name; HTTP itself does not mandate an environment-variable name. Example adapted from the [official search guide](https://docs.trychannel3.com/guides/make-a-search):

```bash
## UNEXECUTED. Load a real key privately; never paste it into source or logs.
curl --fail-with-body --max-time 20 \
  -X POST https://api.trychannel3.com/v1/search \
  -H "x-api-key: ${CHANNEL3_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"query":"washing machine cleaning accessories","filters":{"price":{"max_price":30},"availability":["InStock"]},"limit":3}'
```

Expected **schema fragment, not an observed response**: `products[]` contains `id`, `title`, `images[]` and `offers[]`; each offer has `url`, `domain`, `availability` and nested `price` with `price` and `currency`. Prices and buy links belong to offers, not the product root. `next_page_token` may be null. Validate optional images and empty offers. [Official response schema](https://docs.trychannel3.com/guides/response-overview).

```json
{
  "products": [{
    "id": "example-product-id",
    "title": "Synthetic example only",
    "images": [],
    "offers": [{
      "url": "https://example.com/product",
      "domain": "example.com",
      "price": {"price": 19.99, "currency": "USD"},
      "availability": "InStock"
    }]
  }],
  "next_page_token": null
}
```

#### Application seam and checks

**Proposed application contract/pseudocode:** add a read-only `search_accessories(query, budget, locale)` adapter and optionally expose `GET /api/accessories/search` through the existing backend. The route validates bounded input, applies the demo locale, calls Channel3, normalizes each retailer offer, and returns source links plus retrieval time. Backend owns the key; the browser never calls Channel3 with it. Preserve the existing booking/PayPal flow.

Do not confuse product MCP `https://mcp.trychannel3.com` ([official setup](https://trychannel3.com/mcp)) with `https://docs.trychannel3.com/mcp`, which exposes documentation-search tools ([descriptor](https://docs.trychannel3.com/mcp)). For HTTP integration, no MCP installation is needed. If using MCP, inspect actual advertised tool names/schemas after authenticated connection rather than inventing them.

Published default quota is 10,000 calls/day; most/search endpoints allow 10/sec and lookup 5/sec. Handle 429 using the documented `Retry-After: 5`, bounded retries and cancellation; do not retry indefinitely. [Rate limits](https://docs.trychannel3.com/faq/rate-limits). India/INR are absent from documented locales, so a USD US demo is safer pending direct market confirmation. [Coverage](https://docs.trychannel3.com/faq/catalog-and-coverage).

Smoke evidence: real query returns parseable products/offers; every displayed price has matching currency and stock; missing key fails clearly; invalid key, timeout, 429 and empty results yield usable errors; no products are presented as verified-compatible spare parts. Verify no secret appears in frontend bundles or logs. Mock failures in tests rather than deliberately exhausting production quota.

### Elastic: optional policy retrieval, preserving transaction authority

#### Setup and credentials

Create an Elastic Cloud Serverless Search project or use an existing deployment. New users can use a 14-day trial; existing Cloud users require an admin role or equivalent to create a project. [Deployment guide](https://www.elastic.co/docs/solutions/search/get-started). The hackathon page links an additional 30-day extension. [Sponsor setup](https://paypalaihackathon.devpost.com/details/elastic).

Copy the **Elasticsearch endpoint**, not Kibana URL. Generate a scoped API key in Management → Security. The official Python quick start requires Python 3.10+ and documents `python -m pip install elasticsearch` (or `"elasticsearch[async]"`) and `Elasticsearch(endpoint, api_key=...)`. Check the existing cluster/client compatibility and lock the resolved package version rather than upgrading a working dependency indiscriminately. [Python quick start](https://www.elastic.co/docs/reference/elasticsearch/clients/python/getting-started).

`ELASTIC_API_KEY` is used by the official example, but the constructor argument is what authenticates; it does not automatically discover arbitrary settings. `ELASTICSEARCH_URL`, `ELASTIC_INDEX` and separate ingestion variable described below are **our proposed application settings**. Reuse equivalent existing names.

```dotenv
## Placeholders for .env.example only; never real keys.
CHANNEL3_API_KEY=
SLOTSAVER_ENABLE_CHANNEL3=false
ELASTICSEARCH_URL=https://YOUR-ELASTICSEARCH-ENDPOINT
ELASTICSEARCH_API_KEY=
SLOTSAVER_ENABLE_ELASTIC=false
```

Create keys using an appropriately authorized human/admin session; creating privileged child keys from another API key is restricted. `manage_own_api_key` is required to create keys, and supplied role descriptors constrain privileges to the creator's authority. Scope runtime reads to the one index; use a separate short-lived ingestion/setup key. [API-key authorization](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-security-create-api-key).

For setup-only commands below, `ELASTIC_INGEST_API_KEY` and `ELASTIC_INDEX=slotsaver-policies-v1` are temporary shell variables proposed for the operator; they are not required application runtime settings. Keep the runtime `ELASTICSEARCH_API_KEY` read-only. The enable flags are our application conventions, default false, not vendor settings.

#### Minimal HTTP ingestion and search

This avoids adding a Python dependency solely for a first smoke check. `Authorization: ApiKey <encoded-key>` is the documented header; use the returned encoded API key, not a Cloud management key. [Authentication](https://www.elastic.co/docs/api/doc/elasticsearch/authentication).

**UNEXECUTED setup example:** create a dedicated synthetic policy index with `create_index` or equivalent privileges. If the index already exists, inspect its mappings and reuse it rather than deleting/recreating it. [Create-index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-indices-create).

```bash
curl --fail-with-body --max-time 20 -X PUT \
  "${ELASTICSEARCH_URL}/${ELASTIC_INDEX}" \
  -H "Authorization: ApiKey ${ELASTIC_INGEST_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"mappings":{"properties":{"title":{"type":"text"},"body":{"type":"text"},"service_id":{"type":"keyword"}}}}'
```

**UNEXECUTED document example:** use stable IDs and an ingestion key with document-writing privilege; `refresh=wait_for` makes this smoke document searchable before the response completes. Treat this as test setup, not a per-request production ingestion design. [Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index).

```bash
curl --fail-with-body --max-time 20 -X PUT \
  "${ELASTICSEARCH_URL}/${ELASTIC_INDEX}/_doc/reassignment-policy?refresh=wait_for" \
  -H "Authorization: ApiKey ${ELASTIC_INGEST_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Reassignment","body":"Customer approval is required before assigning a replacement technician.","service_id":"washer-service"}'
```

**UNEXECUTED query example:** runtime key needs `read` on the target index. Search returns hits in `hits.hits[]`, with `_id`, `_score` and `_source`; examine timeout/shard failure fields before claiming a complete result. [Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search).

```bash
curl --fail-with-body --max-time 20 -X POST \
  "${ELASTICSEARCH_URL}/${ELASTIC_INDEX}/_search" \
  -H "Authorization: ApiKey ${ELASTICSEARCH_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"size":3,"query":{"match":{"body":"replacement technician approval"}}}'
```

This is **lexical retrieval, not vector/Jina or a completed RAG integration**. Add an embedding/inference route only after a measured retrieval need and actual cluster/model support are confirmed. Agent Builder has a separate required subscription/tier and MCP/A2A/REST surfaces; do not install another orchestration runtime merely to list Elastic. [Agent Builder](https://www.elastic.co/docs/explore-analyze/ai-features/elastic-agent-builder).

#### Application seam and smoke evidence

**Proposed pseudocode:** existing assistant → `retrieve_policy(question, service_id)` → backend query with fixed index and server-enforced service/user scope → `{document_id, title, excerpt}` → cited explanation. Never let user text choose arbitrary indices or supply raw DSL. No Elasticsearch results may confirm payments or acquire slots: existing transactional database and payment reconciliation remain authoritative.

Smoke checks: ingest synthetic record once; retrieve it with exact ID/source; missing index is actionable; read key cannot write; another index is inaccessible; timeout/429/503 returns a controlled unavailable state; stale/empty retrieval never invents a rule; booking and checkout still function with Elastic disabled. Rate limits depend on deployment/capacity; there is no universal numeric quota established here. Bound request duration and read retries; inspect observed headers/errors.

### Unknowns and handoff gates

- Actual repository path, languages/versions, current HTTP/SDK dependencies, settings naming and test commands.
- Existing slot/payment implementations, assistant runtime and tool schemas; inspect before selecting adapter seams.
- Account/key availability, promo activation, cloud region, endpoint reachability, key scope and feature tiers.
- Whether product discovery improves SlotSaver enough to justify Channel3; valid market and compatibility requirements.
- Whether Elastic retrieval outperforms the current service/policy lookup; embeddings/Jina model availability and incremental cost.

Keep these integrations optional until a real smoke check passes. Record IMPLEMENTED separately from VERIFIED and label offline fixtures as SIMULATED. No source code or dependency files were changed by this research handoff.

---

## Module 5: KERNEL and Postman


Verified against official documentation on 25 October 2026. This is an implementation guide, not evidence that either integration has run. No credentials are included.

### Start with the existing project

Before changing code, inspect repository instructions, Git status, README, dependency manifests/lockfiles, application routes/OpenAPI, current payment adapter, authentication and test setup. Preserve working code. Map the examples below to actual routes and the existing dependency manager; proposed paths and configuration names are not vendor requirements. Record installed CLI/SDK versions and retain lockfiles. Do not introduce another backend or test framework merely to match these examples.

Both tools may remain development-only. Postman is useful for reproducible API evidence. KERNEL is optional: use it only for an essential browser workflow or a deliberate end-to-end browser smoke test. SlotSaver already owns availability APIs, so an external browser layer is not required for its core booking flow.

### 1. KERNEL setup

#### Account, key and scope

Create/sign into the [KERNEL dashboard](https://dashboard.onkernel.com), claim any applicable hackathon offer separately, and create an API key. `KERNEL_API_KEY` is the vendor-documented SDK environment variable. Do not place it in Angular configuration, a browser bundle, a public collection or a recording. The [official quickstart](https://www.kernel.sh/docs/start/quickstart) documents the dashboard setup and packages.

KERNEL returns a new key's plaintext once. Keys can be scoped to a project; policies restrict actions/resources and deny unlisted actions. A key without a policy has broad authority within its scope. Prefer a short-lived project key; keep administrative provisioning credentials outside the agent. Source: [API keys and policies](https://www.kernel.sh/docs/info/api-keys).

For the smoke test, the operator must ensure the selected key can create, control and clean up a browser in the intended project. Do not copy a fictional project ID or guess a permission name for deletion: consult the current [API-key permission reference](https://www.kernel.sh/docs/info/api-key-permissions) and dashboard policy controls before issuing the key. That permissions page was not retrievable in this research session, so an exact complete least-privilege policy is intentionally not asserted here.

#### Minimal Python smoke

Use the project's existing Python environment. The source-verified install command is `pip install kernel`; TypeScript alternative: `npm install @onkernel/sdk`. Adapted from the [official quickstart](https://www.kernel.sh/docs/start/quickstart):

```python
from kernel import Kernel

client = Kernel()  # reads KERNEL_API_KEY
browser = client.browsers.create(timeout_seconds=60)
try:
    response = client.browsers.playwright.execute(
        browser.session_id,
        code="await page.goto('https://example.com'); return await page.title();",
    )
    assert response.result == "Example Domain"
finally:
    client.browsers.delete_by_id(browser.session_id)
```

The assertion and target URL are proposed smoke-test choices. The SDK creates the remote browser; no local Chromium is required for this execution method. Avoid logging the live-view URL in shared CI logs. Keep browser execution code fixed and reviewed; do not interpolate arbitrary customer text into JavaScript.

#### Proposed project configuration

| Setting | Origin | Intended use |
| --- | --- | --- |
| `KERNEL_API_KEY` | Vendor-required SDK convention | Server/job secret, supplied by operator |
| `SLOTSAVER_BROWSER_SMOKE_ENABLED` | Proposed application flag | Default false; explicit opt-in for a billable connected smoke |
| `SLOTSAVER_BROWSER_SMOKE_BASE_URL` | Proposed application setting | Controlled, reachable synthetic demo URL |

A remote browser cannot reach the developer's `localhost` as if it were local. For an application smoke, use an authorized reachable deployment or an existing approved tunnel, with synthetic identities. Do not expose the developer machine merely to complete an optional integration.

#### What counts as verified

First run the neutral page smoke; then, only if justified, run the existing booking UI against a synthetic environment. Retain date, SDK version, test outcome and confirmed resource cleanup. Replays are useful diagnostic evidence but can contain sensitive data. Never infer payment success from browser text, a filled field or a checkout redirect: KERNEL's own [payment guidance](https://www.kernel.sh/docs/browsers/payments) requires independent merchant/order reconciliation and warns against retrying indeterminate purchases.

### 2. Postman setup and compatibility

The current official CLI supports installation with `npm install -g postman-cli`; inspect the existing installation first with `postman --version`. Choose the repository's established installation method and pin the verified version in CI rather than silently upgrading it. Source: [CLI overview](https://learning.postman.com/docs/postman-cli/postman-cli-overview/).

Interactive account login is `postman login`. Current authentication documentation uses `postman login --with-api-key <api-key>` for CI; **do not assume older `login --api-key` examples apply**. Use a CI-secret reference rather than literal key text, disable shell tracing, and avoid exposing the expanded argument in logs. `POSTMAN_API_KEY` below is a proposed shell variable holding the secret, not a documented automatic CLI environment lookup. Use `postman whoami` to verify the intended identity and `postman logout` on disposable runners. Source: [authentication commands](https://learning.postman.com/docs/postman-cli/postman-cli-auth/).

API-key interpolation still places the expanded value in the process argument list. Prefer interactive login on a developer machine; use this API-key form only in an isolated trusted CI context with restricted process/log access. Masking logs does not hide process arguments.

```bash
## Run only in isolated trusted CI, without command tracing.
postman login --with-api-key "$POSTMAN_API_KEY"
postman whoami
```

#### Import and local execution

Keep the existing collection format if it works. Current app imports accept collection/environment files or OpenAPI; drag files into Import and verify the resulting requests before running them. Collection v1 is unsupported. Importing an API specification generates request structure, not meaningful assertions or a correct authentication flow. Source: [data import](https://learning.postman.com/docs/getting-started/importing-and-exporting/importing-data/).

The current CLI supports HTTP collection runs, `-e` for an environment path/UID, request/run timeouts and `--no-report-events`. New local collection management uses v3 YAML; `postman collection migrate <v2.1-file>` creates a v3 folder. V3 runs currently support only the CLI reporter, so do not promise JUnit/JSON reporters for that format. Source: [collection commands](https://learning.postman.com/docs/postman-cli/postman-cli-collections/).

```bash
## Proposed filenames; create/adapt these to actual API contracts first.
postman collection run postman/slotsaver.postman_collection.json \
  -e .private/slotsaver.local.postman_environment.json \
  --timeout 60000 --timeout-request 10000 --no-report-events

## Only if choosing migration; review the generated folder before adoption.
postman collection migrate postman/slotsaver.postman_collection.json
```

Do not run `postman init` blindly over an existing setup. Do not push collections/environments or make a workspace public as part of local verification. CLI global options and plan-dependent commands are documented in [commands/options](https://learning.postman.com/docs/postman-cli/postman-cli-options/).

#### Secrets-safe environments

Commit a sanitized environment **template** containing only synthetic/nonsecret defaults such as `base_url`. Keep real access tokens, cookies, sandbox secrets and environment files in ignored private paths. Postman documents local versus shared values and recommends Vault for sensitive data; cloud-backed features can use shared values, so a desktop local value does not guarantee the CLI sees it. Use an explicit private environment file for the verified run and inspect the effective nonsecret target. Source: [variables and sharing](https://learning.postman.com/docs/use/send-requests/variables/variables/).

Do not assume Vault works in every runner/version. Validate the chosen secret mechanism once, then document it. Never place PayPal client secrets in frontend requests merely to make a collection convenient; the application backend should own the payment credentials.

### 3. Verification plan for SlotSaver

These cases are proposed application tests, mapped to the actual existing routes. Postman scripts support `pm.test`/`pm.expect` response assertions and request chaining, documented in [response tests](https://learning.postman.com/docs/tests-and-scripts/write-scripts/test-scripts/).

| Run | Inputs and checks | Evidence label |
| --- | --- | --- |
| Deterministic local | Seeded customers, fixed clock and stub payment provider; hold conflict, expiry, duplicate events, ownership rejection, capture timeout reconciliation, approved reassignment | Fixture-backed API verification |
| Connected PayPal Sandbox | Actual sandbox credentials supplied server-side; real order/capture; match authoritative amount, currency and booking ownership; refresh/restart persistence | Real sandbox smoke, separate from fixtures |
| Optional KERNEL | Neutral page first, then authorized synthetic UI journey; assert DOM outcome and backend state; always close browser | Connected browser smoke |

Keep fixture and real-payment records separate. A simulated capture is not sandbox evidence. Record provider failures as BLOCKED/FAILED rather than substituting fixtures and calling the same run live. Ordinary sequential collection runs do not establish concurrency safety: retain an actual concurrent integration test for competing holds. Verify negative tests leave the booking/payment state intact, not merely that a status code appears.

### 4. Diagnostics and stop conditions

| Symptom | Check next | Safe response |
| --- | --- | --- |
| KERNEL authentication/authorization failure | Missing/expired secret, key's project and policy, account entitlement | Report redacted error/correlation ID; never print or broaden the key automatically |
| Remote browser cannot load SlotSaver | Public reachability, DNS/TLS, deployment access, cloud-browser network location | Use the neutral smoke to isolate infrastructure; mark app browser test blocked |
| Browser created, action fails | SDK method/version, fixed Playwright code, page selectors, session timeout | Preserve redacted diagnostics; cleanup in `finally`; reconcile any pending payment before retry |
| Cleanup fails | Permission or transient provider failure | Report orphan session ID privately; operator cleanup; do not hide it behind the original test failure |
| Postman invalid option | Installed version versus current docs | Capture version and `--help`; adapt commands; do not change test assertions to hide failure |
| Variable unresolved/wrong target | Explicit environment file, variable scope, shared/local distinction | Abort before mutating requests; never default to production |
| Collection unsupported/report option fails | Collection schema and CLI reporter compatibility | Keep supported format or review migration; preserve plain CLI evidence |
| Payment test times out | Backend/provider state, existing order/capture identifiers | Reconcile first; avoid a second capture or order created solely to get a green run |

Finish with exact commands and versions, date, passed/failed/not-run cases, whether each dependency is dev-only or runtime, and outstanding credentials/access blockers. Do not claim either sponsor integrated merely because its package is installed.

---

## Module 6: Render and Zapier


**Verified documentation:** 25 October 2026. **Audience:** Coding agent extending an existing SlotSaver application. **Status:** Documentation-verified recipes; no credentials entered, deployments made or live smoke checks run. Names marked **proposed** are application conventions, not vendor requirements. Keep existing repository paths, authentication and business rules; adapt these recipes rather than rebuilding the app. Neither integration is mandatory.

### 1. Render: select the smallest deployment

Use Render to host the existing backend and a persistent database. Add Workflows only for a demonstrable asynchronous job, such as computing recovery proposals after a technician disruption. A job may propose options; the booking service must still atomically validate an approved reassignment. Keep payment capture in the existing reviewed adapter.

#### Account and service setup

1. Create/sign in to Render and authorize access to the existing Git repository.
2. Create a Postgres database in the backend's region. Use its **internal connection URL** from Render-hosted services in that region; the external URL is for outside connections. The Database/User fields can be generated by Render. Do not create database passwords in application code. [Create/connect Postgres](https://render.com/docs/postgresql-creating-connecting)
3. Create a Python Web Service against the existing backend directory. The official FastAPI recipe uses build `pip install -r requirements.txt` and start `uvicorn main:app --host 0.0.0.0 --port $PORT`. Replace `main:app` only with the module/object actually present. [FastAPI deployment](https://render.com/docs/deploy-fastapi)
4. Set the existing app's database configuration to that persistent connection. Implement a real migration if the app only supports SQLite; do not change a URL and assume schema, driver, concurrency or SQL compatibility.

#### Blueprint: optional minimal backend wiring

This **proposed** `render.yaml` assumes a same-workspace Postgres service already exists with Render name `slotsaver-db`. It does not create one. Adjust names/root directory/import target to the inspected repository. `healthCheckPath`, `fromDatabase`, `connectionString` and `sync: false` are documented Blueprint fields. `DATABASE_URL` and `APP_SESSION_SECRET` are proposed app keys. The free service plan is explicit for a cost-contained preview; review its limitations before deployment. Validate the file against the current Blueprint schema before use. [Blueprint reference](https://render.com/docs/blueprint-spec)

```yaml
services:
  - type: web
    name: slotsaver-api
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health/ready
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: slotsaver-db
          property: connectionString
      - key: APP_SESSION_SECRET
        sync: false
```

`/health/ready` is a proposed route; implement it or use an existing suitable endpoint. Keep external-provider calls out of readiness so a PayPal outage does not repeatedly restart an otherwise healthy process. Test database connectivity with a bounded query and return an unhealthy status if required storage is unavailable.

#### Environment and credential inventory

| Key | Origin / requirement | Sensitivity / handling |
| --- | --- | --- |
| `PORT` | Render-managed; used by the documented web start command | Non-secret. Bind `0.0.0.0`; do not hardcode localhost. |
| `RENDER_EXTERNAL_URL`, `RENDER_SERVICE_ID`, `RENDER_GIT_COMMIT` | Render automatically supplies these where applicable | Non-secret metadata; useful for deployment diagnostics. |
| `DATABASE_URL` | Proposed app key populated from Render Postgres internal connection property | Secret because credentials are embedded. Restrict access; never log it. |
| `RENDER_API_KEY` | Vendor-documented SDK environment key, needed when application code triggers Workflows | Secret; manually create it in Render, inject only where needed. Merely hosting a web app does not require this key in the app. |
| `RENDER_TASK_SLUG` | Proposed app key holding the actual registered task slug | Non-secret. Copy from the task page; never infer an existing ID. |
| `APP_SESSION_SECRET` | Proposed app key, replace with the repository's actual setting | Secret; independently generated, stable between deploys. |
| PayPal/model variables | Existing app's configuration, not Render-generated | Preserve names; enter sandbox/provider credentials through service secrets. Never put private keys in Angular build variables. |

Render supplies metadata automatically; it does **not** magically inject external provider credentials. Default environment variables are strings. [Render defaults](https://render.com/docs/environment-variables)

Configure secret values on the service's Environment page. Saving without deployment postpones activation until the next deploy. Blueprint placeholders avoid committing secrets; add newly required secrets to existing services manually rather than expecting an old placeholder to prompt again. [Environment/secrets](https://render.com/docs/configure-environment-variables)

#### Migrations and durability

Reuse the repository's migration tool and exact existing command. `alembic upgrade head` is only appropriate if Alembic is actually installed/configured; it is not a Render requirement. Paid web services support a separate pre-deploy command, suitable for migrations. It runs on a separate instance without the service's attached disk. For a free preview without that feature, document a deliberate migration step; do not race multiple application instances performing schema edits. [Deploy lifecycle](https://render.com/docs/deploys)

Use Postgres for bookings, holds, capture records, idempotency and processed event IDs. Free services lose local filesystem changes on restarts/redeploys/sleep; local SQLite is unsuitable for durable hosted booking state. Free web services sleep after 15 idle minutes. Free Postgres expires 30 days after creation. Confirm capacity and judging-window availability before choosing Free. [Free-tier limits](https://render.com/docs/free)

### 2. Render Workflows: add a job without rewriting the backend

#### Register one task

Use the official CLI starter in a **temporary reference directory**, not over the application: `render workflows init`. Select Python or TypeScript, inspect the generated dependency versions and entry point, then bring the minimum task module into the existing repo. Register a workflow through Dashboard **New > Workflow**, linking the existing repo and appropriate directory. The starter is the canonical source for currently supported build/start commands. A Python task uses a `Workflows` app, `@app.task`, a first `TaskContext` argument and `app.start()`; TypeScript uses `task(...)` with context first. [First Workflow](https://render.com/docs/workflows-tutorial)

**Documentation inconsistency:** The current tutorial describes Dashboard Docker workflow support, while parts of the Blueprint reference still say workflows support only Node/Python and exclude Docker fields. Use the native Python/TypeScript route for this POC; do not promise Docker Blueprint support without a fresh verification.

Recommended proposed task: `propose_recovery(booking_id, disruption_id)`. Load authorized synthetic records from the backend/data layer, compute options, persist a proposal with an idempotency constraint, return only proposal IDs and redacted facts. Do not pass credentials or entire payment payloads as task input/output. Task registration names and exact module imports must come from the generated starter/versioned SDK, not memory.

#### Trigger from the existing backend

The current REST endpoint is **POST `https://api.render.com/v1/task-runs`**, authenticated using Bearer credentials. Its body accepts `task` (actual slug), `input` (positional array or named object), and optional `idempotencyKey`. Reusing that key within 24 hours returns the original run; it is scoped to the workflow, and different input on a repeat is ignored. Successful creation returns 202. [Run-task API](https://api-docs.render.com/reference/createtask)

The following is **proposed application code using those documented REST fields**, not a vendor SDK example. Run it only from trusted backend code after authorization. It is blocking, so use the app's async HTTP client in an async FastAPI route, or run it outside the event loop.

```python
import json
import os
from urllib.request import Request, urlopen

def enqueue_recovery(booking_id: str, disruption_id: str):
    payload = {
        "task": os.environ["RENDER_TASK_SLUG"],
        "input": {"booking_id": booking_id, "disruption_id": disruption_id},
        "idempotencyKey": f"recovery:{disruption_id}:{booking_id}",
    }
    request = Request(
        "https://api.render.com/v1/task-runs",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": "Bearer " + os.environ["RENDER_API_KEY"],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        return json.load(response)
```

A Render API key is needed to trigger runs from code. The documented SDK alternatives are Python `render>=1.0.1` and TypeScript `@renderinc/sdk` version `^1.0` or later. Use its current async client in FastAPI; inspect the current reference before copying method names. Persist the returned run identifier and reconcile ambiguous submission timeouts using the same logical idempotency key. [Triggering runs](https://render.com/docs/workflows-running)

#### Smoke checks and diagnostics

These are proposed acceptance checks, all **NOT RUN**:

1. Run local migrations against a disposable Postgres instance, seed synthetic records and execute the existing conflict/payment tests.
2. Deploy; check readiness and the deployed commit. Create a test booking, restart/redeploy, and prove it persists.
3. Submit one read-only recovery task. Check registered input schema, run status, logs and redacted return.
4. Resubmit the same logical event: one proposal effect. Fail a task intentionally and verify retries cannot duplicate writes.
5. API 401: missing/invalid key; 403: resource permission; 404: wrong task identifier; 429: respect rate limits. Never print authorization headers. These status meanings are documented in the [run API](https://api-docs.render.com/reference/createtask).
6. Startup failure: inspect working directory/module path, installed dependencies, `$PORT` binding and DB connectivity before changing infrastructure.

Compute is billed per run duration/resources; task input/output retention and outgoing bandwidth can also cost money. Limit task payloads, runtime, retries and concurrency; record actual usage. Do not assume a hosting free plan makes Workflows free. [Workflow pricing](https://render.com/docs/workflows-limits)

### 3. Zapier MCP: one narrow operational action

Use Zapier for an approved cross-app follow-up, such as recording a confirmed booking in a dedicated test operations sheet. Do not replace the working PayPal sandbox adapter merely to show another sponsor. PayPal's catalogue presence does not verify that MCP exposes the required sandbox create-order/capture operation.

#### Create the connection

For application code, create a dedicated server at **https://mcp.zapier.com**, select Python or TypeScript, then **Settings > API token > Generate token**. Store the token immediately; it is shown once. The Python guide uses the environment variable **`ZAPIER_MCP_TOKEN`**, Python 3.10+ and `fastmcp`. [Python setup](https://docs.zapier.com/mcp/get-started/connect/python)

Zapier's current common endpoint is **`https://mcp.zapier.com/api/v1/connect`** over **Streamable HTTP**, not SSE. Prefer an **Authorization Bearer header** to a token-bearing query URL. The token grants access to this server's tools and returned data; rotating it invalidates all clients using the old token. OAuth-based supported chat clients use a different onboarding route and manage their own OAuth credential. [Connection model](https://docs.zapier.com/mcp/overview/how-connections-work)

#### Source-verified Python client shape

Install the official guide's dependency with `pip install fastmcp`, lock the successfully tested version in the existing project's lockfile, and keep this smoke script outside the browser bundle. This reduced, adapted shape uses the guide's verified imports/transport. It only lists tool names; it performs no app write. [Python setup](https://docs.zapier.com/mcp/get-started/connect/python)

```python
import asyncio
import os
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

async def inspect_tools():
    channel = StreamableHttpTransport(
        "https://mcp.zapier.com/api/v1/connect",
        headers={"Authorization": "Bearer " + os.environ["ZAPIER_MCP_TOKEN"]},
    )
    async with Client(transport=channel) as connection:
        available = await connection.list_tools()
        return [entry.name for entry in available]

if __name__ == "__main__":
    print(asyncio.run(inspect_tools()))
```

For a TypeScript backend, the verified guide uses `@modelcontextprotocol/sdk`, `Client` from `@modelcontextprotocol/sdk/client/index.js`, `StreamableHTTPClientTransport` from `.../client/streamableHttp.js`, `requestInit.headers.Authorization`, `client.connect(transport)` and `client.listTools()`. Use the exact current guide rather than inventing a generic `mcpServers` config shared across clients. [TypeScript setup](https://docs.zapier.com/mcp/get-started/connect/typescript)

#### Restrict and discover actual actions

Prefer **Managed mode** for SlotSaver: the operator selects a fixed set of actions; the client sees one tool per configured action. Agentic mode instead exposes discovery/meta-tools and lets the agent add actions. Capture the actual discovered tool schema at integration time; do not hardcode recalled app/action keys. [Tool modes](https://docs.zapier.com/mcp/overview/how-tools-work)

Connect only a dedicated test app/account. In the action configuration, select the intended connection and constrain fields such as spreadsheet/document/destination wherever possible. Store the allowed discovered tool name and input schema in the adapter. Add a backend allowlist and require customer/operator approval before external writes. Reject unexpected tool names or destinations even if the model suggests them. Configuration controls are described in [Configure actions](https://docs.zapier.com/mcp/manage/configure-your-actions); the application allowlist/approval policy is a proposed extra control.

| Configuration | Type | Requirement |
| --- | --- | --- |
| `ZAPIER_MCP_TOKEN` | Secret, documented example env key | Generated by Zapier; backend/secret manager only. Never commit, log or expose through Angular. |
| MCP endpoint | Public verified constant | Use Streamable HTTP endpoint above. Do not derive an endpoint from a server ID. |
| `ZAPIER_ALLOWED_TOOL` | Proposed app key, non-secret | Fill only after discovering/configuring the real action. |
| App credentials | Managed in Zapier app connection | No need to copy the connected app's API key into SlotSaver. |
| Approval/idempotency record | Proposed backend state | Bind approved action, destination, booking and logical event before execution. |

#### Smoke checks and diagnostics

Proposed checks, **NOT RUN**:

1. Load the token from secrets, connect and list available tools. Record only names/schema, never token or private app data.
2. Verify the expected action appears in Managed mode; a connection with no configured actions is not a completed integration.
3. Perform a read against synthetic data, then one explicitly approved write to the fixed test destination. Show the created record and a redacted audit entry.
4. Reject an unapproved destination/tool and a repeated event. Do not retry a timed-out external write without checking whether it already happened.
5. Rotate the token and confirm old credentials fail; update the secret everywhere before reconnecting.
6. Missing tools: inspect server mode, configured actions and selected app connection. Authentication failure: verify secret presence, rotation and Bearer header; avoid token query strings. Wrong transport: use Streamable HTTP rather than SSE.

Each successful app call consumes **two Zapier tasks**, including tests; failed calls do not. Reaching the allowance stops calls or incurs usage charges when pay-per-task is enabled. Monitor account usage during rehearsal. [MCP usage](https://docs.zapier.com/mcp/overview/usage)

### 4. Handoff to the coding agent

Inspect the existing app, choose only justified integrations, fill its actual paths/settings, and record `IMPLEMENTED`, `VERIFIED`, `BLOCKED` or `NOT RUN` separately. Add no real credentials to examples. Preserve the payment and booking invariants. Deployments, app sign-ins and external writes are not performed by this handbook.

The completion evidence should include: reviewed configuration diff; migrated persistent DB; readiness and restart test; one idempotent workflow run if selected; one scoped approved MCP action if selected; cost/limit observations; redacted logs; and explicit unresolved vendor access or sandbox-support gaps.

## Curation and review record

Five sponsor-pair research agents and one PayPal/core reviewer contributed the technical modules. Independent review spot-checked critical SDK/API contracts, configuration mappings and continuation scope. It corrected a Bryntum double-finalization sketch, separated installer inspection from execution, and replaced a string webhook placeholder with actual object assembly. Python snippets passed syntax parsing; Markdown fences and environment key uniqueness/placeholder format were checked. No dependencies were installed, SDK snippets compiled against the real project, account entitlements verified, credentials used, deployments performed or network integration tests executed.

The coding agent must provide that execution evidence from the actual repository. Source-checked guidance is **DOCUMENTED**, not **VERIFIED_CONNECTED**.
