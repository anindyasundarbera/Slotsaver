# SlotSaver — Task board

Owner column names the accountable role. Status uses the repo vocabulary:
**DONE**, **IN PROGRESS**, **BLOCKED**, **NOT RUN**.

> Delegation mechanism actually used in this environment: VS Code Copilot custom
> `research` and `general-purpose` sub-agents with isolated task scopes. Two ran:
> `rules-research` (vendor/rule verification) and `frontend-dev` (Angular UI).
> Everything else was executed sequentially by the lead, and the security review
> was performed as an independent read-only pass by a separate agent
> (`security-review`) that did not author the reviewed code.

| # | Task | Owner | Depends on | Status | Acceptance evidence |
|---|---|---|---|---|---|
| 1 | Verify hackathon rules, vendor compatibility, PayPal endpoints | Architecture (research agent) | — | DONE | [`vendor-verification.md`](./vendor-verification.md) — every claim tagged CONFIRMED/UNCLEAR with a source |
| 2 | Contracts: OpenAPI-shaped schemas, state machine, data model, invariants | Architecture | 1 | DONE | [`architecture.md`](./architecture.md); `backend/app/schemas.py` |
| 3 | Race-safe slot acquisition (partial unique index) | Backend | 2 | DONE | `tests/test_hold_lifecycle.py::test_two_customers_racing_for_one_slot_exactly_one_wins` |
| 4 | Hold lifecycle, expiry reaper, cancelled checkout | Backend | 3 | DONE | `tests/test_hold_lifecycle.py` |
| 5 | PayPal adapter (Orders v2 + webhook verify) behind a typed protocol | Backend | 2 | DONE (hermetic) / BLOCKED (live) | `tests/test_paypal_adapter.py` (stubbed transport); live sandbox NOT RUN — no credentials |
| 6 | Capture validation, dedupe, reconciliation, payment exceptions | Backend | 5 | DONE | `tests/test_payment_integrity.py` |
| 7 | Reassignment: disruption → proposal → approval → atomic re-validation | Backend | 4 | DONE | `tests/test_reassignment.py` |
| 8 | Owner timeline + analytics with backing rows | Backend | 4 | DONE | `tests/test_durability.py::test_analytics_agree_with_seeded_and_mutated_records` |
| 9 | Bounded assistant with real tool calls, scripted + LLM runtimes | Agent/runtime | 2 | DONE | `tests/test_assistant_abuse.py` |
| 10 | Auth, object ownership, CSRF, rate limits | Backend + Security | 2 | DONE | `tests/test_authorization.py` |
| 11 | Angular customer flow (chat, options, hold, checkout, confirmation) | Frontend | 2 | DONE | verified in a real browser; `npm run build` |
| 12 | Angular owner workspace (Bryntum timeline, analytics, disruption) | Frontend | 8, 11 | DONE | verified in a real browser: timeline renders 3 rows/5 events, day nav rebuilds, disruption + approval round-trip |
| 13 | Deterministic seed + reset | Backend | 2 | DONE | `tests/test_durability.py::test_demo_reset_endpoint_is_owner_only_and_restores_fixtures` |
| 14 | Independent security review | Security (separate agent) | 10, 11, 12 | DONE | [`security-review.md`](./security-review.md) — 3 HIGH + 1 LOW, all fixed and regression-tested |
| 15 | Test evidence log with exact commands | QA | 3–13 | DONE | [`test-evidence.md`](./test-evidence.md); [`integration-evidence.md`](./integration-evidence.md) |
| 16 | Sponsor matrix with honest status | Architecture | 1 | DONE | [`integration-status.md`](./integration-status.md) |
| 17 | Demo runbook (5 min) + 2:45 submission script | QA | 11, 12 | DONE | [`demo-runbook.md`](./demo-runbook.md) |
| 18 | Deployment notes (Render/Postgres caveats) | Architecture | 1 | DONE | [`deployment.md`](./deployment.md) |

## Blockers

| Blocker | Impact | Mitigation in place |
|---|---|---|
| No PayPal Sandbox credentials in this environment | Connected-mode journey NOT RUN | Entire flow is implemented against the real Orders v2 API behind a typed adapter; hermetic tests cover request/response shape, idempotency header, signature verification. Runs unchanged once `PAYPAL_*` is set. |
| Bryntum Scheduler is commercial; only the **trial** build is public | Timeline shows an evaluation watermark | Trial is pinned and used as-is with a visible disclosure; a functional CSS fallback timeline ships so the demo cannot die. Licensed registry access is BLOCKED (401). |
| AG Studio is commercial and not selected as the primary award target | Not integrated | Deliberately out of scope; Bryntum is the single sponsor target (rules allow one sponsor prize). |
| Astropods not selected as the runtime | Not integrated | One runtime chosen by design; provider-agnostic LLM path retained and documented. |

| 19 | PayPal config validation, operation keys, webhook gate, preflight | Backend | 5 | DONE | [`integration-evidence.md`](./integration-evidence.md) §1–2 |
| 20 | APIMatic Context Plugin installation + real use record | Architecture | — | DONE | [`integration-evidence.md`](./integration-evidence.md) §5 |
| 21 | Postman collection executed against the local stack | QA | 19 | DONE | 27 requests / 53 assertions, 0 failures, twice |
| 22 | Gap matrix + config mapping + evidence docs | Architecture | 19–21 | DONE | `/docs/integration-*.md` |
