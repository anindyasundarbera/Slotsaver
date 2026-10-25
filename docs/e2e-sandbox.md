# Automated sandbox journey

`scripts/e2e_sandbox.py` drives the **whole** real flow headlessly and stops at the
first step it cannot complete, telling you exactly what is missing. It replaces the
manual clicking that otherwise blocks "confirmed capture" evidence.

```
reset fixtures -> customer login -> (live) assistant -> hold
  -> real PayPal order -> sandbox PERSONAL buyer approves
  -> capture -> booking confirmed -> survives a refresh
```

## Prerequisites

```bash
cd backend && ../.venv/bin/python -m app.preflight --network   # must say AUTHENTICATED
.venv/bin/python -m playwright install chromium                # once, from the repo root
```

The API must be in `PAYPAL_MODE=sandbox` (the harness refuses otherwise).

## Buyer credentials

The harness needs a **PERSONAL** sandbox account — not your real PayPal login, and
not the business/seller account:

1. Go to <https://developer.paypal.com/dashboard/accounts> (Sandbox → Accounts).
2. Create or open a **Personal** sandbox account and copy its **email** and
   **password** (these are fake test credentials, separate from your real account).
3. Put them in `backend/.env`:

```dotenv
PAYPAL_SANDBOX_BUYER_EMAIL=...
PAYPAL_SANDBOX_BUYER_PASSWORD=...
```

These two lines are read **only** by the harness. The running application never
touches them, and they are never exposed through the API, the UI or the logs.

No buyer credentials? Run with `--headed` and log in yourself in the visible window:

```bash
.venv/bin/python scripts/e2e_sandbox.py --headed
```

## Run

```bash
# from the repository root
.venv/bin/python scripts/e2e_sandbox.py                 # headless, uses .env
.venv/bin/python scripts/e2e_sandbox.py --headed        # manual login
.venv/bin/python scripts/e2e_sandbox.py --slow 0.5      # easier to watch
```

It prints one line per step and a summary:

```
[PASS] real PayPal order created — approve URL obtained from PayPal's own link
[PASS] buyer logged in — sandbox personal account
[PASS] buyer approved the payment
[PASS] payment captured
[PASS] confirmation survives a refresh
```

On failure it saves a screenshot to `/tmp/e2e-*.png` and exits non-zero, saying
whether the cause is configuration or code.

## What it proves, and what it does not

Proves: the real buyer-approval and capture path, the authoritative capture
validation, and durable persistence.

Does **not** prove: webhook delivery (that needs a registered public HTTPS
subscription), or anything about real money.

## Sandbox flow variants

PayPal's sandbox checkout has changed layout several times. The harness tries
`Pay Now`, `Complete Purchase`, `Agree & Continue` and `Continue`. If none match,
it reports the failure and the URL it was on rather than guessing — a layout change
is a harness bug, not an application bug.
