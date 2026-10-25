# Integration configuration mapping

How the proposed `slotsaver-integrations.env.example` maps onto this repository's
actual settings loader (`backend/app/config.py`). **Working names are preserved**;
proposed aliases are accepted in one place and documented here. No vendor reads
these names automatically.

## Boundary rules enforced by code

| Class | Examples here | Handling |
|---|---|---|
| Application config | `DATABASE_URL`, `DEMO_DATE`, `BUSINESS_TZ`, `HOLD_TTL_MINUTES` | Read by `load_settings()`; type/mode validated |
| Public client config | nothing vendor-issued is currently exposed to the browser | `/api/config` returns only business name, timezone, currency, demo date, hold TTL, the two mode strings and the demo account list. A test asserts it contains no credential words |
| Server secrets | `PAYPAL_CLIENT_SECRET`, `LLM_API_KEY`, `SIMULATED_WEBHOOK_SECRET` | Backend only; never serialised; excluded from logs and audit |
| User/account state | sandbox buyer login, webhook registration, Bryntum licence | Manual; `.env` cannot create these |

Angular does **not** read `.env`. `frontend/src/environments.ts` holds only
compile-time public values (`apiBase`), and contains a comment forbidding secrets.

## Mapping table

| Proposed name | Accepted by this repo | Notes |
|---|---|---|
| `DATABASE_URL` | `DATABASE_URL` | same |
| `PUBLIC_APP_ORIGIN` | **alias →** `APP_ORIGIN` | `APP_ORIGIN` is the existing name and is used for CSRF `Origin` checks, so it is preserved. Set `APP_ORIGIN`. |
| `APP_SESSION_SECRET` | — | **Not used.** Sessions are opaque random tokens stored as SHA-256 hashes (`auth_sessions.token_hash`), so no signing secret exists. Documented rather than invented. |
| `PAYMENTS_MODE` | **alias →** `PAYPAL_MODE` | `PAYPAL_MODE` preserved. Only `simulated`/`sandbox`; `live` raises at startup |
| `PAYPAL_BASE_URL` | `PAYPAL_BASE_URL` | Validated: must equal `https://api-m.sandbox.paypal.com` (trailing slash tolerated). Any other host raises `ConfigError` |
| `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` | same | Required when `PAYPAL_MODE=sandbox` (placeholder values are rejected) |
| `PAYPAL_EXPECTED_MERCHANT_ID` | **alias →** `PAYPAL_MERCHANT_ID` | Existing name preserved. Enables the payee check in capture validation |
| `PAYPAL_CURRENCY` | — | Currency is a **catalogue** property (`services.currency`), not an env switch, so a deployment cannot silently re-denominate stored prices |
| `PAYPAL_RETURN_URL` / `PAYPAL_CANCEL_URL` | same | Optional. When both set, order creation uses `payment_source.paypal.experience_context`; otherwise the existing approve-link flow is kept |
| `PAYPAL_HTTP_TIMEOUT_SECONDS` | **alias →** `PAYPAL_TIMEOUT_SECONDS` | Existing name wins; the alias is read when the primary is absent |
| `PAYPAL_WEBHOOKS_ENABLED` | same | Defaults to `true` only when `PAYPAL_WEBHOOK_ID` is present, else `false` |
| `PAYPAL_WEBHOOK_ID` | same | Subscription id, required for verification |
| `PAYPAL_WEBHOOK_URL` | same | Optional; defaults to `{APP_ORIGIN}/api/webhooks/paypal` for the preflight display only |
| `SLOTSAVER_ENABLE_BRYNTUM` | same | Reported by preflight; the component ships enabled on the trial build |
| `SLOTSAVER_AGENT_RUNTIME` | — | The runtime is `ASSISTANT_MODE=scripted\|llm`; no second naming layer added |
| `SLOTSAVER_ENABLE_ASTROPODS`, `SLOTSAVER_ENABLE_AG_STUDIO`, `SLOTSAVER_ENABLE_CHANNEL3`, `SLOTSAVER_ENABLE_ELASTIC`, `SLOTSAVER_BROWSER_SMOKE_ENABLED`, `SLOTSAVER_ENABLE_ZAPIER` | — | **Not implemented.** Preflight reports each as `DEFERRED`. Supplying a key does not enable anything and is never treated as integration evidence |
| `AG_STUDIO_LICENSE_KEY`, `STUDIO_LLM_*`, `CHANNEL3_API_KEY`, `ELASTIC*`, `KERNEL_API_KEY`, `ZAPIER_MCP_TOKEN`, `RENDER_API_KEY`, `POSTMAN_API_KEY` | — | Unused by this build. Absent from `.env.example` so they cannot imply support |

## Preflight

```bash
cd backend
../.venv/bin/python -m app.preflight            # static, no network
../.venv/bin/python -m app.preflight --network   # + OAuth-only check
../.venv/bin/python -m app.preflight --json      # machine-readable
```

Prints statuses and missing variable **names** only. Guarantees, asserted by tests:

- no secret value, prefix or hash appears in output (`test_preflight_never_prints_secret_values`)
- a failed OAuth exchange reports the HTTP status, never the response body
  (`test_preflight_network_auth_failure_reports_status_not_body`)
- a successful exchange reports `AUTHENTICATED` and *never* the token
  (`test_preflight_network_success_reports_authenticated`)
- `--network` is an OAuth exchange only: it does not create/capture an order or
  register a webhook

`load_settings(strict=False)` is used by preflight so it can *report* missing
credentials instead of aborting. The application itself always uses strict mode.

## What `.env` alone cannot do

Sandbox REST app creation, the personal-buyer browser approval, a reachable HTTPS
listener, webhook registration and event selection, database creation/migration,
and any actual purchase. Presence of a string is never treated as verification.

## Setup steps for the user

1. **PayPal** — Developer Dashboard → Sandbox → Apps & Credentials → REST app →
   copy Client ID and secret privately. Copy the intended seller's merchant id into
   `PAYPAL_MERCHANT_ID`. Set `PAYPAL_MODE=sandbox`.
2. Verify app authentication only: `../.venv/bin/python -m app.preflight --network`.
3. **Webhooks** (optional but needed for async evidence) — expose
   `https://<host>/api/webhooks/paypal` on port 443, subscribe it in the same
   sandbox app, copy the **subscription id** into `PAYPAL_WEBHOOK_ID`, set
   `PAYPAL_WEBHOOKS_ENABLED=true`. Re-register if the public URL changes.
4. **Bryntum** — the repo uses the public trial package via an npm alias. For a
   licensed build, configure the private registry and update the alias/version; no
   invented licence env var is used.
5. Leave the deferred flags unset. They do nothing.

Never paste secrets into chat, commit them, or place them in frontend config.
