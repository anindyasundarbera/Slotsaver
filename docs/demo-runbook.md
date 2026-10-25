# Demo runbook

Two separate deliverables:

| Recording | Length | Audience | Purpose |
|---|---|---|---|
| **Internal walkthrough** | 5:00 | Engineering / team | Explain the design and prove the invariants |
| **Submission cut** | **2:45** (hard limit 3:00) | Judges | Show user value and visible outcomes only |

## Setup (2 minutes, before anyone is watching)

```bash
./scripts/setup.sh                 # once
./scripts/reset-demo.sh            # clean synthetic data
./scripts/dev.sh                   # API :8000 + UI :4200
```

Then verify, in this order:

1. `curl -s localhost:4200/api/health` → `"status":"ok"`.
2. Open `http://localhost:4200` and confirm the badge says either
   **"Offline rehearsal — simulated payments"** or **"PayPal Sandbox"**.
   **Decide now which mode you are presenting.** The app never switches silently.
3. Confirm the header shows `UTC-5` (November) — if it shows `UTC-4` the demo date
   drifted into daylight saving time; reset with `./scripts/reset-demo.sh`.

### Demo accounts

| Email | Role | Use |
|---|---|---|
| `maya@example.com` | customer | The main customer journey |
| `diego@example.com` | customer | Proves one customer cannot see another's booking |
| `owner@northline.example` | owner | Timeline, analytics, disruption |

### Mode note

- **Connected sandbox:** set `PAYPAL_MODE=sandbox` + credentials in `backend/.env`,
  restart. List which smoke checks passed before you claim it.
- **Offline rehearsal:** everything below works with no network. Payments are
  **simulated** and every screen says so. Do not describe this as PayPal Sandbox
  evidence.

---

## Five-minute internal walkthrough

State the expected screen after each cue. Recovery is in the right column.

| Time | Cue | What you say | Expected state | If it goes wrong |
|---|---|---|---|---|
| 0:00–0:30 | Landing page | "Appliance repair businesses lose money on phone tag. Watch a customer book and pay in one conversation, and watch what happens when a technician drops out." | Three demo accounts visible; mode badge visible | If the page is blank → API is down; run `curl localhost:8000/api/health` |
| 0:30–1:30 | Sign in as Maya → paste/keep the demo request → **Ask the assistant** | "The model does not invent times. It calls one read-only tool and shows exactly what it did." Click **Tool activity (redacted)** open. | 2–3 options, each with technician, local time, `UTC-5`, price, "Within budget" | If zero options → the demo DB drifted; `./scripts/reset-demo.sh` and restart |
| 1:30–2:00 | Select the first option → **Hold this slot** | "The hold is a real reservation claimed inside a database transaction, with a 15-minute expiry." | Amber "Your hold" card, live countdown, booking appears as **Held** | If 409 → someone took it, which is the point; pick another |
| 2:00–2:30 | **Pay (simulated)** → **Approve** → **Capture payment** | Sandbox: "This creates a real PayPal order server-side; the amount comes from the catalogue, never the browser." Simulated: "This is the labelled offline substitute." | Green "you are booked", reference, captured amount | If capture fails → read the correlation ID and retry once; otherwise switch to the recorded fallback clip |
| 2:30–3:45 | Sign out → sign in as Priya → owner page → day **2026-11-05** → **Mark unavailable** Ana 13:00–18:00 | "A paid booking is never silently moved. The owner only raises a proposal." | "1 booking affected, 1 proposal raised"; SA-D4E5F6 shows **Needs reassignment** on the timeline | If 0 affected → wrong date; navigate to the day with the red bar |
| 3:45–4:15 | Sign out → sign in as Maya → **approve a replacement?** → pick Ben → **Approve replacement** | "Only the customer can accept. The replacement is re-validated atomically at the same time and the same price." | "Booking SA-D4E5F6 is now confirmed", technician becomes Ben | If declined by the API → the slot was taken; show the honest error |
| 4:15–4:45 | Back to owner → analytics | "Totals come from the same rows in this table. Exceptions are excluded from service revenue and shown separately." Click a service bar to cross-filter. | KPI row, bars, filtered table | If numbers look stale → **Refresh from server** |
| 4:45–5:00 | Audit trail | "Every transition is recorded. The AI never wrote to the database." | Recent actions with actor roles | — |

### One visible proof of trust (say it out loud)

Open two browser profiles as two customers and hold the **same** slot at the same
moment. One gets the slot; the other gets `SLOT_UNAVAILABLE`. Or show the owner
trying to open `/customer` and the customer trying `/api/owner/analytics` → 403.
Either is a five-second demonstration that the browser is not the authority.

---

## 2:45 submission cut (judges)

Timings include pauses. **Total 2:45.**

| Time | Picture | Voiceover |
|---|---|---|
| 0:00–0:15 | Title card: SlotSaver, the problem sentence | "Appliance repair runs on phone tag. SlotSaver turns one message into a paid, confirmed appointment." |
| 0:15–0:35 | Landing → sign in as Maya | "I'm a customer. I describe the job the way I'd say it out loud." |
| 0:35–1:05 | Type the demo request, send, options appear | "The assistant reads real availability through one read-only tool. It cannot book, cannot pay, and cannot invent a time." |
| 1:05–1:30 | Select → hold → countdown | "The slot is claimed inside a database transaction with a fifteen-minute expiry. Two customers racing for it: exactly one wins." |
| 1:30–2:00 | PayPal Sandbox approve → capture → confirmation | "Payment is created and captured server-side. The booking only confirms when the capture amount, currency, order and merchant all match what we stored." |
| 2:00–2:20 | Owner timeline, mark Ana unavailable | "Now the technician drops out. Her paid booking is never silently moved — the owner only raises a proposal." |
| 2:20–2:40 | Customer approves replacement, timeline updates | "The customer approves. The replacement is re-validated atomically at the same time and price." |
| 2:40–2:45 | Analytics + audit, close on the mode badge | "Bryntum shows the schedule, PayPal moves the money, and the backend enforces every rule. Open source, runnable in two commands." |

**Do not** narrate implementation detail into the video. That belongs in the
internal walkthrough.

---

## Recovery card (tape this to the monitor)

| Symptom | Cause | Fix |
|---|---|---|
| Blank page / spinner forever | API not running | `curl localhost:8000/api/health`; restart `./scripts/dev.sh` |
| "Cannot reach the server" | Dev-server proxy lost the API | restart both; confirm `/api/health` on **port 4200**, not just 8000 |
| Options list empty | Wrong date / capacity consumed by earlier rehearsals | `./scripts/reset-demo.sh`, restart API, reload |
| Everything says "expired" | Laptop slept past the 15-minute TTL | reselect a slot; holds are intentionally short |
| Timeline empty or shows "fallback" | Bryntum trial did not initialise | the fallback view is equivalent — keep presenting, mention it honestly |
| Timezone shows `UTC-4` | Date drifted into DST | reset; the demo date pins November |
| Payment step errors | Sandbox credentials/permissions | switch to the recorded clip; state that connected mode was blocked |

## What not to claim

- Do not call the trial Bryntum build licensed.
- Do not call a simulated payment a sandbox payment.
- Do not call the POC production-ready; refunds, real money and multi-tenancy
  are explicitly out of scope.
- Do not claim AG Studio, Astropods or APIMatic integrations — they are not built.
