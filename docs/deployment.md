# Deployment notes

> **No hosted runtime was exercised as part of this POC.** Everything below is
> prepared-but-unverified configuration. Status: **NOT RUN**.

## Why a database is not optional

From [Render's free-tier docs](https://render.com/docs/free) (verified 2026-10-25):

> "any changes to your web service's filesystem (uploaded images, local SQLite
> databases, etc.) are *lost* every time the service redeploys, restarts, or spins down"

> "Free Render Postgres databases expire 30 days after creation."

> "Render **spins down** a Free web service that goes 15 minutes without receiving
> any inbound traffic."

So the SQLite default in this repo is **local demo only**. A hosted demo must use
Postgres, and a free Postgres instance dies 30 days after creation — which may be
*after* judging begins but *before* it ends. Plan for that:

| Option | Cost | Durability | Recommendation |
|---|---|---|---|
| Render free web + **free Postgres** | $0 | DB deleted 30 days after creation; cold start ~1 min | Acceptable for judging **only** if you create the DB as late as safely possible and re-check dates |
| Render Starter web + **paid Postgres** | ~$7 + ~$7/mo | Persistent | Best if you want the demo alive throughout judging |
| Fly.io / Railway with a volume | varies | Persistent | Viable alternative |
| **No hosting at all** | $0 | n/a | Fully allowed: the rules say complete run instructions in the repo satisfy "working build" |

Given the rules explicitly accept runnable instructions in place of a hosted URL,
**the lowest-risk submission is a public repo with a tested `./scripts/setup.sh`**
plus a short screen recording. Hosting is a bonus, not a requirement.

## Postgres switch

1. `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/slotsaver`
2. `pip install "psycopg[binary]==3.2.3"` (add to `requirements.txt`).
3. Create the schema: `.venv/bin/python -m app.migrate` from `backend/`.

The partial unique index that enforces slot exclusivity is emitted for Postgres
too (`postgresql_where=text("active = 1")`), so the concurrency guarantee survives
the switch. **Before any real deployment, add Alembic** — this POC uses
`create_all` plus a `verify_schema` check, which is enough for an empty database
but cannot perform an in-place migration.

## Serving the SPA from FastAPI (single origin)

`backend/app/main.py` mounts `frontend/dist/frontend/browser` when it exists and
falls back to `index.html` for client-side routes. Build first:

```bash
cd frontend && npm run build
cd ../backend && ../.venv/bin/python -m uvicorn app.main:app --port 8000
```

Then `http://127.0.0.1:8000` serves the whole app with no CORS at all. This is the
shape you want behind HTTPS, because the session cookie uses `SameSite=Lax` and
CSRF relies on a same-origin `Origin` check.

## Required production environment

```bash
ENVIRONMENT=production
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYPAL_MERCHANT_ID=...        # enables the payee check
PAYPAL_WEBHOOK_ID=...         # required for signature verification
DATABASE_URL=postgresql+psycopg://...
COOKIE_SECURE=true            # required behind HTTPS
APP_ORIGIN=https://your-host  # must match exactly; non-matching Origins are refused
SEED_DEMO_DATA=false
ALLOW_DEMO_RESET=false        # never expose reset on a public deployment
DEMO_DATE=2026-11-12          # pin so the demo does not drift
```

`PAYPAL_MODE=live` is rejected at startup. Do not attempt to patch around it for
this POC.

## render.yaml (prepared, not exercised)

```yaml
services:
  - type: web
    name: slotsaver
    runtime: python
    plan: free
    buildCommand: |
      cd frontend && npm ci && npm run build
      cd ../backend && pip install -r requirements.txt
    startCommand: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: ENVIRONMENT
        value: production
      - key: COOKIE_SECURE
        value: "true"
      - key: SEED_DEMO_DATA
        value: "false"
      - key: ALLOW_DEMO_RESET
        value: "false"
      - key: DATABASE_URL
        fromDatabase: { name: slotsaver-db, property: connectionString }
      - key: PAYPAL_MODE
        value: simulated
  - type: pserv
    name: slotsaver-db
    plan: free
    ipAllowList: []
databases:
  - name: slotsaver-db
    plan: free
```

Free web services cannot attach a disk, which is exactly why `DATABASE_URL` points
at Postgres. A cold start of ~1 minute means the first request after idling may
time out in a browser tab — open the health URL first, then start the demo.

## Pre-demo checklist

```bash
curl -s https://your-host/api/health   # status must be "ok"
```
If it reports `degraded`, the database is unreachable (free Postgres expired, or
the connection string changed). Switch the presenter to **offline rehearsal** mode
explicitly — do not silently continue in a broken connected state.
