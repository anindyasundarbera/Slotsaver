# Switching to real PayPal Sandbox

Everything you need is in `backend/.env` (created for you, mode `600`, git-ignored).
The app **reads it automatically at startup**; a real exported environment variable
always wins over a file value, so you can override any line per-run.

## 0. Before you paste anything

```bash
cd backend
../.venv/bin/python -m app.preflight
```

This prints statuses only — never a value. It currently reports `SIMULATED` with
`paypal_auth_config: DISABLED`, which is correct until you switch modes.

## 1. Get sandbox credentials

PayPal Developer Dashboard → **Sandbox** → **Apps & Credentials** → create/select a
REST app → copy the **Client ID** and **Secret**.

For the seller identity: **Testing Tools → Sandbox Accounts** → open the *business*
account you want to be paid → copy its merchant id.

For browser approval you must log in as a **personal** sandbox account, not the
seller.

## 2. Fill these five lines in `backend/.env`

```dotenv
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=<paste>
PAYPAL_CLIENT_SECRET=<paste>
PAYPAL_MERCHANT_ID=<business account merchant id>
PAYPAL_BASE_URL=            # leave blank
```

`PAYPAL_BASE_URL` must stay blank or be exactly `https://api-m.sandbox.paypal.com`;
anything else is refused at startup. `PAYPAL_MODE=live` is also refused.

## 3. Prove authentication without moving money

```bash
cd backend
../.venv/bin/python -m app.preflight --network
```

Expect `paypal_oauth: AUTHENTICATED (http 200, N scope(s), token not stored)`.

- `FAILED (http 401)` → wrong client id/secret, or the app is not a *sandbox* app
- `BLOCKED`/transport error → network or proxy
- A successful token proves **app authentication only** — not seller identity,
  buyer approval, webhook delivery or capture

## 4. Run the connected journey

```bash
./scripts/reset-demo.sh          # clean fixtures
./scripts/dev.sh                 # API :8000 + UI :4200
```

Then in the browser: sign in as `maya@example.com`, use the demo request, hold a
slot, **Pay with PayPal** (a real sandbox approve link opens — log in as the
*personal* sandbox buyer), then **I've approved — capture payment**.

The badge in the header must read **PayPal Sandbox**, not "Offline rehearsal".

## Common configuration mistakes (now detected at startup)

| Mistake | What happens |
|---|---|
| `PAYPAL_BASE_URL=https://sandbox.paypal.com` | `ConfigError`: that is the **buyer-facing web host**, not the API. Leave blank or use `https://api-m.sandbox.paypal.com` |
| `PAYPAL_BASE_URL=https://api-m.paypal.com` | `ConfigError`: that is **LIVE** PayPal; this POC refuses live mode |
| Client **secret** pasted into `PAYPAL_MERCHANT_ID` | `ConfigError`: a merchant id is 13 uppercase alphanumerics. A wrong value previously made every order fail with 400 → `503`. Leave blank to skip the payee check |
| `PAYPAL_MODE` still `simulated` | App runs offline; the badge says so |

## 4b. Verified so far (2026-10-26), and what remains

With the configured credentials, these steps are **confirmed against real PayPal**:

| Step | Result |
|---|---|
| `preflight --network` | `AUTHENTICATED (http 200, 26 scope(s))` |
| Order creation via the UI | 201, `provider_mode: sandbox`, real `sandbox.paypal.com` approval URL |
| Order read back | PayPal reports the same id in state `CREATED` with our `custom_id` |
| Order creation after fixing the merchant id | 201 with live order `8NS97838AK251145S`, shown in the UI as "PayPal order …" |
| Capture before approval | 409 `ORDER_NOT_CAPTURABLE` — refused by PayPal, no booking confirmed |

Postman verification passes in **both** modes (simulated 27/53/0, sandbox 25/45/0);
the collection reads `paypal_mode` and asserts the correct outcome for each.

Still **not run**, because they need interactive sandbox-buyer credentials:

1. Log in as the sandbox **personal** buyer on the approval URL and approve.
2. Return to SlotSaver and click **Capture payment**; the booking should become
   **Confirmed** with the captured amount.
3. Restart the API and confirm the booking survives.

Everything is wired for those three steps; they are blocked on a human login, not
on code.

## 5. Optional — webhooks

1. Expose `https://<your-host>/api/webhooks/paypal` on port 443 (a tunnel is fine
   for a demo).
2. Subscribe that URL in the **same** sandbox app and select at least
   `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.CAPTURE.DENIED`, `PAYMENT.CAPTURE.PENDING`.
3. Copy the **subscription id** (not an event id) into `PAYPAL_WEBHOOK_ID` and set
   `PAYPAL_WEBHOOKS_ENABLED=true`.
4. Re-register if the public URL changes.

With intake disabled the endpoint returns `503 WEBHOOKS_DISABLED`; it never skips
signature verification.

## What to expect, and what to check

| Step | Expected |
|---|---|
| Preflight `--network` | `AUTHENTICATED` |
| Order creation | browser opens a real sandbox approve URL |
| Capture | booking becomes **confirmed**; amount equals the catalogue price |
| Duplicate capture | same attempt returned; no second charge |
| Altered amount/currency | `payment_exception`, never a confirmation |
| Capture after the 15-minute hold expires | money recorded, booking `payment_exception`, capacity released, owner task raised |
| Refresh / restart the API | the confirmed booking is still there |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Starts in simulated despite the file | `PAYPAL_MODE=simulated` still set, or an exported `PAYPAL_MODE` overriding it | check the last `PAYPAL_MODE=` line; unset the shell variable |
| `ConfigError: sandbox requires PAYPAL_CLIENT_ID…` | missing/placeholder credentials | fill both; `YOUR_…`/`changeme` are rejected on purpose |
| `ConfigError: PAYPAL_BASE_URL must be…` | wrong host | blank it |
| `ORDER_NOT_APPROVED` on capture | buyer has not approved in the sandbox tab | complete approval, then capture |
| `ORDER_NOT_CAPTURABLE` (422) | order already captured or voided | re-read the payment status instead of retrying |
| Webhook `401` | signature invalid, or `PAYPAL_WEBHOOK_ID` is an event id | paste the **subscription** id |
| Webhook `503` | intake disabled | set `PAYPAL_WEBHOOKS_ENABLED=true` |
| **Checkout page shows "Things don't appear to be working at the moment"** with `code=VU5TVVBQT1JURURfUEFZRUVfQ1VSUkVOQ1k` | That code is base64 for **`UNSUPPORTED_PAYEE_CURRENCY`**: the seller account's primary currency does not match the `USD` the order was created in. The order is created fine (`201`) — it fails only when the buyer opens it, which is why it looks like a buyer problem. | See below. |

### `UNSUPPORTED_PAYEE_CURRENCY`

This is an **account** mismatch, not an application defect. Confirm the mechanism in
seconds:

```bash
.venv/bin/python -c "
import base64; print(base64.b64decode('VU5TVVBQT1JURURfUEFZRUVfQ1VSUkVOQ1k=').decode())"
# UNSUPPORTED_PAYEE_CURRENCY
```

The order is created with `payee.merchant_id = PAYPAL_MERCHANT_ID` in `USD`. If the
sandbox **business** account behind that merchant id settles in something else (INR is
the usual cause, since sandbox business accounts created with country = India default
to INR), PayPal accepts the order and then refuses it at the buyer step.

Two supported fixes — pick one:

1. **Preferred: make the seller account USD.** In
   <https://developer.paypal.com/dashboard/accounts>, open the **Business** account whose
   merchant id is `PAYPAL_MERCHANT_ID`, and add/set a **USD** currency balance (or simply
   use a business account created with country = **US**). Then create a fresh order.
2. **Match the app to the account.** Only if you have decided to demo in that currency:
   set `CURRENCY` and the catalogue prices to the seller's primary currency. The seeded
   prices are integer cents in `USD`, so this means re-seeding, and the POC's `$80`
   budget story in the demo script changes with it.

The buyer (personal) account currency does **not** fix this — the restriction is on the
receiving side. Creating more personal accounts will not help.

Quick check of which merchant id the app is sending:

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'backend')
from app.config import get_settings; s=get_settings()
print('merchant:', s.paypal_merchant_id, '| currency:', s.currency)"
```

A failed approval attempt is safe to abandon: cancel the checkout so the slot is released
without confirming anything.

```bash
curl -X POST localhost:8000/api/payments/<attempt_id>/cancel \
  -H "X-CSRF-Token: $CSRF" -b cookies.txt
```

## Do not

- Commit `backend/.env`, paste secrets into chat, or put the client secret in
  frontend config. Only the client ID is browser-safe.
- Call a simulated capture sandbox evidence. The two are labelled differently
  everywhere in the app.
- Enable live mode. It is refused at startup by design.

## Recording evidence

When the connected run succeeds, add a `docs/integration-evidence.md` entry with the
date, the commands, and the sanitized outcome — and keep it separate from the
fixture-backed rows.
