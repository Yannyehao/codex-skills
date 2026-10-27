# Shared review contract

Applies to every market profile. Profile references add only facts specific to that market.

## Source precedence

1. The lifecycle service's review cards (next section) are the canonical representation of today's machine universe and of every active episode; the latest complete local artifacts supply the visual-review evidence behind them.
2. The live candidate ledger establishes current human status and the full monthly history.
3. Fresh chart reading establishes today's discretionary judgment.
4. Earlier chat conclusions are context only; they cannot replace current data, ledger state, or current charts.

If sources disagree, show the symbol and both values before interpreting. Never silently choose the convenient source. If the live ledger cannot be queried, the full status review is unavailable; a local reconstruction or old export may be labelled provisional, never complete.

## Canonical representation: lifecycle cards

The zAI lifecycle service is the canonical record; Notion pages and the human ledger are projections of it. Its own contract (`zradar/docs/opportunity_episode_contract.md`, sections on cards, the setup grammar, and TrendAlive) is the authority for every field and rule; this skill states only the reading rules below and never copies the grammar, thresholds, or facet lists. If this file and the service disagree, the service wins; say so.

Read the cards with the service's read-only commands, `python -m zradar.opportunity_episode_flow cards` and `audit` (add `hierarchy` for one symbol's parent trend), run with the `lifecycle_service` settings of `config.local.json` (`python`, `project_root`, `database`; `project_root` as the working directory). A card that cannot be loaded is a named unavailable source, never a reason to reconstruct one from a screenshot or from chat.

- **The scanner is a high-recall OR.** Any single raw signal is enough to appear. A review shows the fresh raw signals of the session **and** every active episode that is not terminated, one card per episode, whether or not it was reselected today. A failed gate never removes a card or an audit row.
- **The six gates are readable evidence, not a filter or a score.** Show each gate's `PASS`, `WAIT`, or `FAIL` with the evidence statements the service printed. The gates are not an AND recall filter: do not hide, rank, or drop a card because some gate is not `PASS`, and do not add up or invent a score. `eligible_review` is an explanation for the human; it authorizes nothing.
- **TrendAlive is the only broad exclusion from the active workset**, and only when the service reports the parent trend `CONFIRMED_TERMINATED`. A one-day anchor breach or a weak MACD is a warning: the card stays active and the warning stays visible with its raw values. Terminated episodes move to history (`non_card`); report them under status changes with the service's reason. A later raw signal does not revive a terminated parent trend; only a new parent trend and child setup do.
- **A single needle is discovery / watch.** It is shown as a scout, never as a candidate to act on, and cannot become `ACTIONABLE` by itself.
- **A trigger never creates `ACTIONABLE`.** A trigger signal alone authorizes nothing; stage and `ACTIONABLE` come only from the service's explicit review or human assessment. A review never infers, writes, or upgrades a stage, and never relabels `WAIT` as `PASS` without new evidence.
- **Human review may create only a DRAFT** ticket, and only on an explicit instruction ([ticket-draft.md](ticket-draft.md)). Approval is a separate human act in the service.
- **Every evidence statement keeps its `knowledge_class`** (and `source`). Quote the class next to the claim; a statement printed without one is shown as unclassed and stays `WAIT`, never promoted. Do not merge classes or present a case-derived induction as an original rule.

## Session gate

Review the latest **complete, closed** trading session. Never take the maximum filename or date: a newer date may be a partial, running, or failed run, or a session that has not closed yet. Choose the newest date whose artifacts are all present and declared complete, and tell the user the review date. If newer dates exist but were incomplete, say which and why. If the user names a date, review that date and state it differs from the latest, or fail if it is incomplete; do not fall back silently.

Integrity audits prove hashes, dates, and read evidence, not interpretation. Integrity failures in the selected session stop the review; they do not trigger a fallback to an older session.

## Review universe

Form four explicit sets and reconcile them before delivery:

1. **Fresh candidates:** every symbol in the session's machine output, including candidates without a standard chart.
2. **Active lifecycle rows:** every card the service marks active (not terminated by TrendAlive) and every ledger row whose human status is `重点关注`, `继续观察`, or unresolved `待复盘`, plus any row with an open ticket or position. Read tickets and positions only from the lifecycle service's read-only `list` / `state` (a ticket whose `state` is not `CLOSED`, `CANCELLED`, `EXPIRED`, `REJECTED`, or `REVIEWED` is open); if it is unavailable, name it as an unavailable source instead of inferring from chat or Notion. A card or row present in one source and absent in the other is a coverage conflict to expose, not to resolve silently.
3. **Status changes:** additions, upgrades, downgrades, eliminations, invalidated plans, and re-selections since the previous review.
4. **Monthly ledger:** every symbol selected during the month, including `不再观察` rows. Query with full pagination and preserve every selection date for repeated symbols.

The human `当前状态` is authoritative over a stale machine conclusion. An active item cannot disappear because it was not reselected today; one that is in the active set but absent from the carried machine list is a coverage conflict, not evidence that it stopped being active.

## Reading charts

Actually open the chart pixels for every fresh candidate and every active item. Check position against the white and yellow lines, N structure, pullback volume, J/KDJ, prior distribution, and whether a multi-wave move is already too mature. File existence, JSON text, price change, or an earlier chart is not "看过图".

Render an active item that is absent from the machine output from current local bars with the project's established renderer into temporary output, then open it. Do not modify production reports to obtain a view. An eliminated monthly row needs no new chart unless it was reselected, changed status, or the user names it.

For a candidate with no standard chart, use its available source evidence and say no standard chart was produced; never claim it passed that chart's checks. Apply z哥-specific rules only where the project's current evidence supports them, and keep them distinct from public technical-analysis knowledge and implementation hypotheses.

## Judgment vocabulary

- **重点关注:** structure is clean enough that a specific nearby trigger could create an executable plan.
- **继续观察:** alive, but a named structural condition is missing.
- **待复盘:** unresolved human review; never promote it automatically.
- **不再观察:** structure failed, matured too far, or no longer deserves daily chart work. Keep it in the monthly ledger.

Every active item carries exactly one observable blocker with a deadline: the single condition that must appear, and the session or date after which the idea is downgraded if it has not. Prefer "日线重新站回白线且回踩缩量，三个交易日内" to "看看后面表现". Do not upgrade `WAIT` without new evidence. When nothing is clean, say there is no setup worth forcing; do not manufacture one.

## Monthly table semantics

Aggregate repeated selections by symbol but show every selection date and the count. Use the latest verified close. Show a return only when its basis exists, labelled:

- since first selection = latest close / first selection close − 1;
- since latest selection = latest close / latest selection close − 1.

Mark missing inputs unavailable. A screening return is not trading P&L, realized or missed profit, or proof that an entry existed.

## Deliverable

Lead with the actionable conclusion: execute, keep watching, or nothing worth forcing. Then:

- one concise paragraph per fresh candidate and active item: current judgment, the one decisive reason, and the one blocker with its deadline;
- a status-change section, saying "无变化" when true;
- the complete monthly table;
- the shortest useful checklist for the next session.

Do not invent a "first attention" ranking or equate alphabetical order with priority. Keep hashes, raw state-machine fields, and audit detail out of the reader-facing report unless a failure needs diagnosis. The chat answer and any saved review must state the same conclusions.

## Boundary

Reviewing is read-only (the service's `list`, `state`, `cards`, `audit`, `hierarchy` only). Ledger write-back and persisting a DRAFT trade ticket (`create_draft` only, per [ticket-draft.md](ticket-draft.md)) each need the user's explicit instruction naming that action; approving, submitting, filling, cancelling, amending, and placing orders are never part of a review. A review classifies a setup's own quality; it never sizes a position from a capital stage, never invents a risk budget or reward/risk floor, and never proposes scaling up.
