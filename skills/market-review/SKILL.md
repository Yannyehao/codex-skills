---
name: market-review
description: Complete Yehao's full closed-session stock review for the U.S. or A-share market, reconciling fresh candidates, every active watch, status changes, and the complete monthly ledger. Trigger on 美股复盘, A股复盘, 总览本月的票, full monthly review, or 今天选出来的票 together with all active watches. Exclude isolated single-chart questions, and order placement or position management (use trade-execution).
---

# Market review

"复盘" means a full review, not a read of today's shortlist. Reconcile the latest machine output with the SQLite ledger read through the lifecycle service and keep continuity across days.

## Choose the profile

- 美股 / U.S. stocks → read [references/us-profile.md](references/us-profile.md).
- A股 / A-share → read [references/a-profile.md](references/a-profile.md).
- If the market is ambiguous, ask once. Reviewing both means two separate reviews.

## Before reviewing

Read [references/review-contract.md](references/review-contract.md) completely, then the profile reference. Read `config.local.json` beside this file for the profile's local project and the `lifecycle_service` that serves the review cards and the SQLite ledger (`config.example.json` shows the shape; it never holds real values). `lifecycle_service.database` is the only status and history source; ignore any leftover Notion keys in an older local config. If the file is missing or still has placeholders, name the unavailable live source; never guess a database or substitute an old snapshot. The U.S. profile also accepts the legacy `../us-market-review/config.local.json` when no local config exists here.

For the U.S. profile, run the artifact audit with the Python interpreter this machine requires; `--config <absolute path>` is needed when running outside the installed folder:

```powershell
& <configured-python> -X utf8 scripts\audit_review.py --profile us
```

It selects the latest complete bundle, lists newer incomplete dates it skipped, and audits integrity. Stop on any reported error and name the exact gap. The A profile has no bundled audit; follow its manual gate.

## Review and deliver

Follow the contract for the lifecycle cards (the canonical representation; its reading rules are stated once, in the contract), the session gate, the four-set review universe, reading actual chart pixels, the one blocker/deadline per active item, the monthly table, and the report layout. Do not restate those rules from memory; the contract is the single source.

## Writes need a separate instruction

Reviewing is read-only by default; the only lifecycle-service commands a review runs are the read-only ones listed under "Read-only ledger commands" in the contract. During discussion and sealing, before 写回, `manual_review prepare-review` is also allowed: it opens the ledger read-only and changes nothing. `manual_review write-review` stays forbidden until the user explicitly says 写回. After the user explicitly says 固化, 生成交易单, 写回, or equivalent, you may do only what was named:

- **写回** saves exactly one reviewed packet. The user supplies the trading judgment; the agent builds the packet and the user never fills JSON. Flow: discuss → write a draft JSON (`schema: review-packet/2`, market, review_date, source, audit, items with symbol, lifecycle_intent, verbatim wording, and optional wait_condition, review_horizon_sessions or review_by, close_fact; `PLANNED` is rejected in a packet) → from `lifecycle_service.project_root`, with its `python` and `database`, run `python -m zradar.manual_review prepare-review --db <db> --draft-json <draft>` (read-only; fills episode and latest-decision anchors and seals) → show the packet → on 写回 run `python -m zradar.manual_review write-review --db <db> --packet-json <packet>`. If it reports drift, rebuild and show it again. Keep draft and packet files outside the repository. SQLite is the source of truth; the automatic Notion candidate projection is retired. Show the whole packet once (symbol, intent, verbatim wording, deadline), then write on 写回 without re-asking. It never creates a case annotation, collection membership, plan, ticket, or order. Report the receipt in four parts: writes read back, human decisions missing tonight, next exchange-calendar dates, and system debt. Cases do not affect completion, and 复盘完成，系统证据待补 is a valid result. Recover date, chart, and earlier wording yourself; ask only when two materially different trading meanings remain. Ordinary review comments stay in the audit trail and do not authorize a case. Saving a case is `trade-case-logger`, only on the user's explicit authorization scoped to that symbol and date.
- **生成交易单 / 固化** persists one DRAFT trade ticket with the service operation `create_draft`, following [references/ticket-draft.md](references/ticket-draft.md) (the review classifies the setup; budgets, size, floors, and stage come from the user or account policy, never from you). Every new draft's args must carry the top-level `stop_semantics` (basis and activation; the service stores it at `review.stop_semantics`) exactly as that file defines it; you persist it and never invent it. The stop is system-generated, not chosen: before `create_draft`, run `scripts/compile_trade_policy.py --facts <chart-facts.json>` per [references/strategy-stop-playbook.md](references/strategy-stop-playbook.md). Only observable chart facts go in; the compiler derives one canonical `trade_type` (policy `zge-stop-v1`) and renders through `scripts/stop_template.py`. Only `COMPLETE` may be drafted; on `BLOCKED`, `ENTRY_GATE_ONLY`, or `STOP_BASIS_ONLY`, ask and write nothing. There is no default trade type and no combined stop. Regime affects eligibility and size, never the stop. The human approves the complete ticket, not its ingredients. The raw ticket fields and approval gate are in [../trade-execution/references/ticket-contract.md](../trade-execution/references/ticket-contract.md). If that sibling skill is not installed, say so and write nothing.

A DRAFT is not approved, not executable, and not filled. A review never approves, submits, fills, cancels, or places an order, never runs `approve`, and never edits a persisted ticket; approval is the human's separate act (`human:<name>`, explicit confirmation, the exact `terms_sha256` they reviewed). `AMBIGUOUS` and `REJECT` tickets can never be approved. After the user places or fills an order, switch to `$trade-execution`; scale-up questions go there too, since a larger size can only ever be a proposal from real-fill metrics.
