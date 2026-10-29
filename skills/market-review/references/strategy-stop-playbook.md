# Canonical stop policy `zge-stop-v1` (one trade type, one stop; not a menu)

z哥's stop is fixed by the trade type. The review selects exactly one canonical `trade_type`, and that type uniquely determines the stop **basis kind**, **activation**, **broker mode**, and the holding/time exits. `scripts/stop_template.py` derives all of them; nobody chooses a template, a basis kind, an activation, or a broker mode, and no trade type has an alternative. The only caller inputs are the chart-derived `basis_level` (decimal text; the script never calculates it or derives it from a chart) and the chart `evidence`.

Regime (`TIGHT` / `LOOSE`) and position state are not stop inputs. Regime affects eligibility and size elsewhere in the review, never which stop applies.

## Trade types

| `trade_type` | basis kind | activation | broker mode | extra holding/time rules | source anchors |
|---|---|---|---|---|---|
| `B1_KLINE_REVERSAL` | `ENTRY_CANDLE_LOW` | `CLOSE_CONFIRM` | `HUMAN_ONLY_ALERT` | `B1_THREE_SESSION_RECOVERY` (recover and rise within three sessions) | 2025-05-07 (stop below the entry K low by 2-3 ticks / 1-2%, lose only one K), 2025-10-06 |
| `B1_WHITE_LINE_SHORT` | `WHITE_LINE` | `CLOSE_CONFIRM` | `HUMAN_ONLY_ALERT` | none | 2026-02-11 (short-term stop at white), 2026-04-22 (white-line B1 is the cautious variant; not a fallback) |
| `B1_YELLOW_LINE_SWING` | `YELLOW_LINE` | `CLOSE_CONFIRM` | `HUMAN_ONLY_ALERT` | `YELLOW_SUPPORT_SECOND_SESSION_CONFIRM` (yellow is the last support; second session must confirm resistance is overcome) | 2026-02-11 (swing stop at yellow) |
| `B2_FRESH_CONFIRMATION` | `PRIOR_B1_N_LOW` | `CLOSE_CONFIRM` | `HUMAN_ONLY_ALERT` | `B2_TWO_SESSION_EXPLOSION` (must explode within two sessions) | 2025-10-06 |
| `B2_RISEN_PULLBACK` | `PRIOR_B1_N_LOW` | `CLOSE_CONFIRM` | `HUMAN_ONLY_ALERT` | `B2_RISEN_STRUCTURE_HOLD` (no fresh two-session clock; hold while the prior N low is intact and there is no S1) | 2026-01-21 |
| `BRICK_ZERO_DAY` | `ENTRY_CANDLE_LOW` | `INTRADAY_HARD` | `LIVE_STOP_LIMIT` (disaster stop) | `BRICK_NEXT_OPEN_NO_EXPLOSION` (no lift at the next open, checked 9:33 / 9:37, exits), `BRICK_RED_TO_GREEN` | 2026-02-20 (entry-K low, two-bar gamble), 2026-03-29 (brick state, next open) |

Every type also cites 2026-04-22, the close-versus-intraday meta-rule. There is no mature-brick new-entry type.

## Activation semantics

- `CLOSE_CONFIRM`: acts only if the regular-session close is beyond the level; an intraday print through it is not a violation. The helper never produces a live broker stop for it: its `broker_implementation` is a deterministic human-only close alert and manual exit after the close.
- `INTRADAY_HARD`: used only by `BRICK_ZERO_DAY`; any trade through the level exits, implemented as a live protective stop-limit after the entry fill.
- `NEXT_SESSION_FAILURE_TO_RECLAIM` is never emitted.

## Separate non-price rules

Holding/time rules are emitted as `holding_exit_rules` (`is_price_stop: false`) and never become a stop price, a `stop_trigger`, or a broker order. Every type also carries `PROFIT_TO_LOSS_INTRADAY` (2026-04-22): only a position that was already profitable and turns into a loss is an intraday exit. It is a holding rule, not a structural stop.

## Not types (BLOCK)

`B1`, `B2`, `BRICK` alone, `COMPOSITE`, and any other name; regime, position state, and custom `template_id`, `basis_kind`, `broker_mode`, or `activation`. If two theses apply, the review chooses one primary `trade_type` and records why; there is no combined stop and nothing is chosen at execution time. A stop too wide for `risk_budget` is solved by a smaller `quantity` the user chooses, never by moving the level or the activation.

## Marker

The helper writes `canonical_trade_type=<TYPE>; policy=zge-stop-v1` at the start of `basis.evidence`. `trade-execution/scripts/audit_ticket.py` checks that exact marker: for `policy=zge-stop-v1` the type must be known, appear once, and match the persisted `basis.kind` and `activation`; anything else BLOCKS. No `stop_semantics` key is added.

## Source status

The course notes were locally verified outside this public repository, and the portable date and section anchors for each type are included in the table above (with the 2026-04-22 meta-rule). The notes themselves, and any transcript wording, are not copied here. Anything the table does not list is unsupported and blocks.
