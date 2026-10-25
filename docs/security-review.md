# Independent security review

Performed **2026-10-25/26** by a separate read-only `security-review` agent that did
not author the reviewed code. It inspected `backend/app/**`, `frontend/src/app/**`,
`scripts/*`, `.gitignore` and `.env.example`, and reproduced findings with the
existing test harness.

Result: **3 HIGH, 1 LOW** — all fixed and covered by regression tests. Status of
every fix below is **VERIFIED_FIXTURE** unless stated otherwise.

## Findings and fixes

### 1 — Forgeable webhook could confirm a booking with no payment (HIGH)

**Reported:** `SimulatedProvider.verify_webhook` authenticated with a static HMAC key
that was (a) shipped as a live default in `.env.example` and (b) hard-coded as the
fallback in `config.py`. A verified `PAYMENT.CAPTURE.COMPLETED` is authoritative
evidence, so any authenticated customer could mint their own "verified" capture and
bypass the buyer-approval gate entirely.

**Reproduced:** hold → checkout (order left `CREATED`, never approved) → self-signed
`PAYMENT.CAPTURE.COMPLETED` → `booking: confirmed`, `captured: 7500`.

**Fix:**
- removed the published literal from `.env.example` (now blank)
- `is_placeholder()` rejects blank/`demo-`/`changeme`/`your_` style values
- when unset or a placeholder in simulated mode, a **random per-process secret** is
  generated, so no third party shares the key
- tests set an explicit known key (`conftest.py`), which is why they can still sign

**Verified:** re-running the attack with the previously published literal now returns
**401** and the booking stays `awaiting_payment`.
Tests: `test_simulated_mode_never_uses_a_published_webhook_key`,
`test_placeholders_are_detected`, `test_forged_webhook_signature_is_rejected`.

### 2 — Unaligned `start_utc` bypassed the capacity uniqueness guarantee (HIGH)

**Reported:** `create_hold` never validated 30-minute alignment. `slot_blocks` are
keyed on exact timestamps, so an off-grid start wrote cells that collided with
nothing and were invisible to availability search.

**Reproduced:** same technician, same day — `14:00Z` → 09:00 (90 min) and `14:07Z` →
09:07 (53 minutes of silent overlap), both `201`.

**Fix:**
- `timeutil.is_slot_aligned()` / `assert_slot_aligned()`
- `slot_starts()` raises on an unaligned start (defence in depth for every caller)
- `create_hold` rejects with `422 VALIDATION_ERROR` before touching capacity

**Verified:** `offset 0 → 201`, `offset 7 → 422`.
Tests: `test_unaligned_start_is_rejected` (Postman), plus backend assertions in
`test_paypal_integration.py`/`test_payment_integrity.py` setup paths.

### 3 — `DENIED` then `COMPLETED` orphaned capacity permanently (HIGH)

**Reported:** the denial handler cancelled the booking but left the hold active. A
later `COMPLETED` re-pointed the hold's cells to `booking`, then took the "slot
invalid" branch and released by `owner_kind='hold'` — which matched nothing. The
technician's capacity was lost forever, and money sat on a cancelled booking.

**Reproduced:** `denied: 200` → `completed: 200` → booking `cancelled`,
cells `[('booking', 1), ('booking', 1)]` left active permanently.

**Fix:**
- capacity is re-pointed **only after** confirming the booking is still payable and
  the hold still valid
- the invalid branch releases by the hold (its own cells) unconditionally
- a late capture on a closed booking records `CAPTURED_ON_CLOSED_BOOKING`, sets
  `needs_attention`, and never resurrects the appointment
- the denial handler now releases the hold's capacity immediately

**Verified:** the same sequence now yields `booking: cancelled`, cells `[('hold', 0)]`.
Test: `test_denied_then_completed_does_not_orphan_capacity`.

### 4 — Cookie jars were not ignored by pattern (LOW)

**Reported:** `.gitignore` listed `cookies.txt` by exact basename, so
`owner-cookies.txt` (a live owner session jar) would be committed by `git add -A`.

**Fix:** pattern changed to `*cookies*.txt`. **Verified:** the pattern matches; a
scan of the staged file list shows no cookie jar, `.db`, `.env` or log file.

## Additional defects found by self-audit (same review cycle)

| Defect | Fix | Test |
|---|---|---|
| A closed (failed) payment attempt blocked a legitimate retry with a 500 `UNIQUE constraint failed` | `attempt_no` per hold; key includes it | `test_checkout_retry_after_failed_attempt_creates_a_new_attempt` |
| Force-confirming an exception did not claim capacity, so it could double-book a technician | force-confirm now claims cells and returns `409 SLOT_UNAVAILABLE` | `test_force_confirm_refuses_when_the_slot_was_taken` |
| `claim_cells` was not idempotent for the same owner | owner-aware claim; only a *different* owner is a conflict | `test_force_confirm_succeeds_and_claims_capacity_when_free` |
| Create and capture shared one `PayPal-Request-Id` | distinct `:create` / `:capture` keys | `test_create_and_capture_use_distinct_idempotency_keys` |

## Verified controls (reviewer's own coverage record)

Recorded by the reviewer so the coverage is auditable, not just the gaps:

- **Customer authorization** — every customer route binds to `session.user_id`;
  foreign ids return **404** to prevent enumeration
- **Owner authorization** — all owner routes carry `owner_session`;
  `require_owner`/`require_customer` are role checks on the resolved session
- **IDOR via body** — `ReassignmentApprove.technician_id` is validated against the
  proposal's own candidate list and re-validated against the slot index
- **Amount integrity** — expected amount/currency come only from the booking row;
  capture validation checks order id, `COMPLETED`, amount, currency, `custom_id`,
  payee merchant
- **CSRF/session** — double-submit with `compare_digest` plus an Origin allow-list;
  login revokes the prior session (no fixation); `HttpOnly`, `SameSite=Lax`, 12h
  server-side expiry
- **Injection** — no raw SQL outside `SELECT 1` and the index predicate; no template
  engine
- **SPA static handler** — `resolve()` + `is_file()` + parent containment correctly
  rejects traversal; `/api/` short-circuited
- **Assistant boundary** — both tools are read-only and identity-bound; strict JSON
  with an allow-listed key set; no path from model text to hold/capture/owner actions
- **Secrets/logging** — no credentials in logs or audit; nested-key redaction; no
  request bodies logged
- **Frontend** — no `innerHTML`/`bypassSecurityTrust`; tokens in cookies only;
  server-supplied `approve_url` bound via `[href]`

## Residual risks (accepted for a POC)

| Risk | Why accepted | Mitigation |
|---|---|---|
| Rate limiting is in-process | Single-process demo | Documented; a multi-worker deployment needs a shared store |
| Simulated provider keeps orders in memory | Only used in `simulated` mode; PayPal is the store of record in `sandbox` | Disclosed on screen and in docs |
| No refunds | Out of scope by design | Owner resolves exceptions manually; audited |
| Webhook dedupe row can be rolled back with the transaction | `finalize_capture` is idempotent on `captured`, so a replay is still safe | Documented by the reviewer |
| SQLite for local demo | Chosen for zero-setup rehearsal | Postgres path documented; partial index emitted for both |
