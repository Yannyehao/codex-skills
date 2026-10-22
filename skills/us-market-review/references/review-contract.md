# Full review contract

## Source precedence

1. Latest same-date, complete local artifacts establish today's machine universe and visual-review evidence.
2. The live candidate database establishes current human status and the full monthly history.
3. Fresh chart reading establishes today's discretionary judgment.
4. Earlier chat conclusions are context only. They cannot replace current data, database state, or current charts.

If sources disagree, expose the symbol and both values before interpreting it. Do not silently choose the convenient source. If the live database cannot be queried, say that the full current-status review is unavailable. A local reconstruction or prior export may be labelled provisional, never complete.

## Artifact gate

The latest close date must match across:

- `zradar/out/us_nightly_report_YYYYMMDD.json`
- `zradar/out/us_b1_review_YYYYMMDD.json`
- `zradar/out/charts/us_b1/YYYYMMDD/`

Both reports must be `complete=true`. For every B1 review image, require:

- the PNG exists;
- its SHA-256 matches the report and capture manifest;
- `read_evidence` proves an image result was opened;
- the review answer says `image_read=true`;
- the answer's `image_token` matches the manifest's `render_metadata.check_token`;
- the manifest result is successful and covers the same symbol/date.

The audit script proves integrity, not interpretation. The reviewer must still open the pixels.

## Daily judgment vocabulary

- **重点关注:** structure is clean enough that a specific nearby trigger could create an executable plan.
- **继续观察:** the idea remains alive, but a named structural condition is still missing.
- **待复盘:** unresolved human review; never promote it automatically.
- **不再观察:** current structure has failed, matured too far, or no longer deserves daily chart work. Keep it in the monthly ledger.

Every active verdict needs one observable waiting condition. Prefer “日线重新站回白线且回踩缩量” to vague language such as “看看后面表现”. Apply z哥-specific rules only when supported by the project's current evidence; distinguish them from public technical-analysis knowledge and implementation hypotheses.

## Monthly table semantics

Aggregate repeated selections by symbol but show all selection dates and the count. Use the latest verified close. Show both returns only when their bases are available:

- since first selection = latest close / first selection close - 1;
- since latest selection = latest close / latest selection close - 1.

Label missing inputs as unavailable. Never call either return realized profit, missed profit, or proof that an entry existed.

## XDV and BNC/NA rules

Read the latest daily and weekly bars, volume, and KDJ. Report current price; daily and weekly white/yellow positions; weekly K, D, J and cross state; current-week low; and the effective pit edge and pit bottom.

Only Friday's completed bar can confirm a weekly cross. During the week, call it projected or provisional. Do not convert a fast intrweek move into a confirmed weekly signal.

When a stable pit is identifiable:

`first target = 2 × pit edge - pit bottom`

State that the target has about 5% artistic tolerance. A prior high that is also the pit edge is a breakout/retest observation level, not an automatic exit. Do not invent a second target. If the pit is not stable or its edge/bottom cannot be identified reliably, write `暂不出目标价`.

For an executable weekly signal, use signal-week low minus 2% as the standard stop and also show the sensitivity using the signal-week low directly. Calculate:

- per-share risk = entry - stop;
- potential reward = first target - entry;
- reward/risk = potential reward / potential risk.

Near 1:1 or lower is not worth it. Below 3:1 is not a z哥-style high-reward/risk opportunity. Recalculate after a fast confirmation rally; “确认但不追” requires price already too close to the target or a stop too distant for adequate odds, not merely proximity to the pit edge.

XDV and BNC share one CAD 20,000 viewpoint-account opportunity pool. BNC has a maximum planned allocation of CAD 15,000; the other CAD 5,000 stays flexible cash. XDV is one possible use of that cash, not a default allocation or cash substitute. Do not create fixed tranches, average down because price fell, or buy merely to fill the allocation.

Only after an independent qualified signal may a ticket be discussed: zero commission, integer shares, combined cost at most CAD 20,000, and actual contemporaneous entry/stop/target inputs. Before a BNC ticket, remind the user to check employee personal-trading pre-clearance or blackout restrictions. The skill never places an order.

After entry, change the question to holding the second half: whether price still follows the white line/BBI, whether the pit edge breakout/retest is valid, remaining distance to the first target, volume health, and invalidation signs such as a high-volume kill candle, huge-volume bearish candle, or two consecutive closes below BBI. Reaching an old high alone is not an exit.
