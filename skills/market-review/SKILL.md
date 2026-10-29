---
name: market-review
description: Complete Yehao's full closed-session stock review for the U.S. or A-share market, reconciling fresh candidates, every active watch, status changes, and the complete monthly ledger. Trigger on 美股复盘, A股复盘, 总览本月的票, full monthly review, or 今天选出来的票 together with all active watches. Exclude isolated single-chart questions, and order placement or position management (use trade-execution).
---

# Market review

"复盘" means a full review, not a read of today's shortlist. Reconcile the latest machine output with the live human-maintained candidate ledger and keep continuity across days.

## Choose the profile

- 美股 / U.S. stocks → read [references/us-profile.md](references/us-profile.md).
- A股 / A-share → read [references/a-profile.md](references/a-profile.md).
- If the market is ambiguous, ask once. Reviewing both means two separate reviews.

## Before reviewing

Read [references/review-contract.md](references/review-contract.md) completely, then the profile reference. Read `config.local.json` beside this file for the profile's local project and private ledger targets and the `lifecycle_service` that serves the review cards (`config.example.json` shows the shape; it never holds real values). If the file is missing or still has placeholders, name the unavailable live source; never guess a database or substitute an old snapshot. The U.S. profile also accepts the legacy `../us-market-review/config.local.json` when no local config exists here.

For the U.S. profile, run the artifact audit with the Python interpreter this machine requires; `--config <absolute path>` is needed when running outside the installed folder:

```powershell
& <configured-python> -X utf8 scripts\audit_review.py --profile us
```

It selects the latest complete bundle, lists newer incomplete dates it skipped, and audits integrity. Stop on any reported error and name the exact gap. The A profile has no bundled audit; follow its manual gate.

## Review and deliver

Follow the contract for the lifecycle cards (the canonical representation; its reading rules are stated once, in the contract), the session gate, the four-set review universe, reading actual chart pixels, the one blocker/deadline per active item, the monthly table, and the report layout. Do not restate those rules from memory; the contract is the single source.

## Writes need a separate instruction

Reviewing is read-only by default; the only lifecycle-service commands a review runs are the read-only `list`, `state`, and the episode flow's `cards`, `audit`, and `hierarchy`. After the user explicitly says 固化, 生成交易单, 写回, or equivalent, you may do only what was named:

- **写回** updates the candidate ledger or review page. Read the affected records back to verify.
- **生成交易单 / 固化** persists one DRAFT trade ticket with the service operation `create_draft`, following [references/ticket-draft.md](references/ticket-draft.md) (the review classifies the setup; budgets, size, floors, and stage come from the user or account policy, never from you). Every new draft's args must carry the top-level `stop_semantics` (basis and activation; the service stores it at `review.stop_semantics`) exactly as that file defines it; you persist it and never invent it. The stop is system-generated, not chosen: the review selects one canonical `trade_type` (policy `zge-stop-v1`), which uniquely determines basis kind, activation, broker mode and the holding/time exits, and records why if two theses apply. Before `create_draft`, run `scripts/stop_template.py --trade-type <TYPE> --basis-level <decimal> --evidence <chart reading>` per [references/strategy-stop-playbook.md](references/strategy-stop-playbook.md); only the chart-derived level and evidence come from the user, a missing one means ask and write nothing, and there is no default trade type and no combined stop. Regime affects eligibility and size, never the stop. The human approves the complete ticket, not its ingredients. The raw ticket fields and approval gate are in [../trade-execution/references/ticket-contract.md](../trade-execution/references/ticket-contract.md). If that sibling skill is not installed, say so and write nothing.

A DRAFT is not approved, not executable, and not filled. A review never approves, submits, fills, cancels, or places an order, never runs `approve`, and never edits a persisted ticket; approval is the human's separate act (`human:<name>`, explicit confirmation, the exact `terms_sha256` they reviewed). `AMBIGUOUS` and `REJECT` tickets can never be approved. After the user places or fills an order, switch to `$trade-execution`; scale-up questions go there too, since a larger size can only ever be a proposal from real-fill metrics.
