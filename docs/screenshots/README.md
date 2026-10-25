# Screenshots

Captured **2026-10-26** from the running stack (`PAYPAL_MODE=sandbox`,
`ASSISTANT_MODE=llm`) by [`scripts/capture_screenshots.py`](../../scripts/capture_screenshots.py).
Nothing is mocked: the script drives the real Angular app through Chromium against the
real FastAPI backend, so every image reflects canonical backend state.

Reproduce:

```bash
./scripts/dev.sh                # backend :8000, frontend :4200
.venv/bin/python scripts/capture_screenshots.py
```

The script resets nothing. If the demo slots are exhausted from earlier runs, call the
owner reset first (`POST /api/owner/demo/reset` as the owner account).

All data is **synthetic**. No real customer, payment card, or credential appears in any
image.

| File | Shows |
|---|---|
| `01-landing.png` | Pitch, the demo request, and the three synthetic accounts |
| `02-customer-validated-options.png` | Live assistant turn with 2 real backend options, the redacted tool trace, and the guided-search fallback |
| `03-hold-created.png` | A held slot with its server-side expiry and the "no charge yet" state |
| `04-checkout-paypal-sandbox.png` | Held booking plus a **real PayPal Sandbox order id** (`9AT9…`, `$75.00 USD`) awaiting buyer approval |
| `09-confirmed-sandbox-payment.png` | **After a real sandbox capture** — `SA-LNRXNS` shows `Confirmed`, $75.00 USD, verified against PayPal (`COMPLETED`, `final_capture: true`) |
| `05-owner-timeline.png` | Bryntum technician timeline (held / confirmed / affected), disruption form, payment exceptions |
| `06-owner-analytics.png` | Revenue vs all captured money, per-service/per-technician buckets, and the underlying rows behind the totals |
| `07-owner-disruption.png` | The reassignment workflow as the owner sees it |
| `08-mobile-landing.png` | Customer layout at 390×844 |

## What these images are not

- `04` is a **created order awaiting approval** — not a captured payment. Use `09` when
  you need evidence of a confirmed capture: that booking was paid through the real
  sandbox checkout and verified server-side, then re-confirmed directly against PayPal
  (`COMPLETED`, `final_capture: true`).
- The timeline carries a visible **Bryntum trial watermark**; the licence status is
  disclosed in [`../integration-status.md`](../integration-status.md).

The presenter should say both of these out loud rather than let an image imply more than
it shows.
