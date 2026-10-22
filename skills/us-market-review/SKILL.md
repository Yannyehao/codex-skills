---
name: us-market-review
description: Complete Yehao's full U.S. stock review from the latest zAI artifacts and the live candidate-tracking database. Trigger on $us-market-review, 美股复盘, 今晚/今天的美股, 看看今天选出来的美股, 总览本月或十月的票, or requests to revisit all selected and watched U.S. stocks. Reconcile today's selections, every active watch, status changes, and the full monthly ledger; do not reduce a full review to only today's shortlist. Exclude isolated single-chart questions and A-share reviews.
---

# U.S. market review

Treat “美股复盘” as a full review, not a synonym for reading today's shortlist. The deliverable must reconcile the latest machine output with the live human-maintained candidate database and preserve continuity across days.

## Before reviewing

Read [references/review-contract.md](references/review-contract.md) completely. Read `config.local.json` beside this file for the local zAI project and private database targets. If it is missing or still contains placeholders, state which live source is unavailable; never guess a database or silently substitute an old snapshot.

Run the bundled artifact audit before drawing conclusions:

```powershell
& <configured-python> -X utf8 scripts\audit_us_review.py
```

Use the Python interpreter required by the current machine instructions; the placeholder is not a literal executable name. When invoked outside the installed skill folder, pass `--config <absolute-config.local.json>`. Stop the review if the audit reports a date mismatch, incomplete report, missing image, hash mismatch, missing visual-read evidence, or mismatched image token. Name the exact gap instead of filling it from memory.

## Build the review universe

Query the configured live candidate database for the current calendar month with full pagination. Preserve every selection date for symbols selected more than once.

Form four explicit sets:

1. **Today's selections:** every symbol in the latest nightly report, including non-B1 candidates without a B1 chart.
2. **Active watches:** every database row whose current human status is `重点关注`, `继续观察`, or unresolved `待复盘`.
3. **Status changes:** additions, upgrades, downgrades, eliminations, invalidated plans, and re-selections since the previous review.
4. **Monthly ledger:** every symbol selected during the month, including `不再观察` rows.

Use the human `当前状态` as authoritative over a stale machine conclusion. Reconcile the sets before delivery. A symbol present in the database's active set but absent from today's carried list is a coverage conflict, not evidence that it stopped being active.

## Read the charts

Actually open every current-day chart for today's selections and every active watch. Check position, white/yellow lines, N structure, pullback volume, J/KDJ, prior distribution, and whether a multi-wave move is already too mature. Do not call file existence, JSON text, price change, or an earlier chart “看过图”.

If an active watch is absent from today's report, render its latest daily/weekly chart from current local bars with the project's established renderer into temporary output, then open it. Do not modify production reports merely to obtain the missing view. A previously eliminated monthly row does not require a new chart unless it was selected again, its status changed, or the user names it.

For a non-B1 candidate with no standard B1 image, use its available source evidence and say that no B1 chart was produced. Never pretend its chart passed the B1 visual checks.

## Deliver one readable report

Lead with the actionable conclusion: execute, keep watching, or no setup worth forcing. Then include:

- one concise paragraph for every symbol selected today and every active watch: current judgment, the one decisive reason, and one observable waiting condition;
- an explicit status-change section, including “无变化” when appropriate;
- a complete monthly table with symbol, all selection dates, selection count, latest close, return since first/latest selection as clearly labelled, and current human status;
- tomorrow's shortest useful checklist.

Do not invent a “first attention” ranking, equate alphabetical order with priority, or upgrade `WAIT` without new evidence. A screening return is not trading P&L and does not prove the stock should have been bought. When there is no clean opportunity, say so directly.

Keep backend hashes, raw state-machine fields, and audit detail out of the reader-facing report unless a failure needs diagnosis. The chat answer and any saved review must express the same conclusions; do not create competing versions.

## Writes require a separate instruction

Reviewing is read-only. Write back to Notion, change candidate status, or generate a trade ticket only when the user explicitly asks to “写回”, “固化”, or equivalent. After an authorized write, read the affected records/page back and verify them. Never place orders.

## Viewpoint-account candidates

When the configured symbols `XDV.TO` and `NA.TO` (the user's BNC) are in scope, keep them in a separate “观点仓候选” section and follow the exact rules in the reference. They do not replace the U.S. review universe, and XDV is never described as cash parking.
