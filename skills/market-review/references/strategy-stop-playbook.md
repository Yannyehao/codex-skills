# Strategy stop playbook (controlled templates, not a universal stop)

z哥's stop rules differ by setup, position state, and regime. A draft applies exactly one named template through `scripts/stop_template.py`; it never improvises a stop and never collapses these into one default. The template fixes the **vocabulary** (basis kind, activation, text). The **level** is decimal text the user or the ledger plan supplies from the chart reading; the script never calculates it or derives it from a chart.

## Selectors (all explicit; none is inferred or defaulted)

- `setup`: `B1`, `B2`, `BRICK`.
- `position_state`: `FRESH_UNFLOWN` (entry just formed), `FLOWN` (already moved away, wider structure), `ALREADY_RISEN` (risen before this entry, pullback).
- `regime`: `TIGHT` or `LOOSE` (user states it; anchor 2025-11-26). TIGHT prefers B1 and normally avoids structural B2/B3, but that is a preference, not a market-wide ban; a regime with no source-backed template for the setup BLOCKS. There is no generic B2 FLOWN template (no source evidence), so B2 / FLOWN blocks.
- `template_id`, `basis_kind`, `basis_level`, `evidence`, `broker_mode` (`LIVE_STOP_LIMIT` only for `INTRADAY_HARD`, else `HUMAN_ONLY_ALERT`), `broker_implementation` (required non-empty for `CLOSE_CONFIRM` and `NEXT_SESSION_FAILURE_TO_RECLAIM`; optional for `INTRADAY_HARD`, but never empty when given; the service and the auditor accept a hard stop without it, and the helper then omits the key).

## Templates

| `template_id` | setup / state / regime | basis kind | activation | source anchors |
|---|---|---|---|---|
| `B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM` | B1 / FRESH_UNFLOWN / TIGHT or LOOSE (normal fresh B1; B1 is preferred in TIGHT) | `ENTRY_CANDLE_LOW` | `CLOSE_CONFIRM` | 2025-11-12, 2025-11-26 |
| `B1_FRESH_ENTRY_LOW_INTRADAY_HARD` | B1 / FRESH_UNFLOWN / either (explicit hand-tight override only) | `ENTRY_CANDLE_LOW` | `INTRADAY_HARD` | 2025-11-12, 2025-11-26 |
| `B1_FLOWN_N_LOW_WHITE_LINE_CLOSE_CONFIRM` | B1 / FLOWN / either (invalid for fresh unflown) | `PRIOR_B1_N_LOW` or `WHITE_LINE` | `CLOSE_CONFIRM` | 2025-11-12 |
| `B1_FLOWN_YELLOW_LINE_CLOSE_CONFIRM` | B1 / FLOWN / either (explicit alternative, no default) | `YELLOW_LINE` | `CLOSE_CONFIRM` | 2025-12-03, 2026-01-21 |
| `B2_STRUCTURAL_PRIOR_LOW_CLOSE_CONFIRM` | B2 / FRESH_UNFLOWN or ALREADY_RISEN / LOOSE | `PRIOR_B1_N_LOW` | `CLOSE_CONFIRM` | 2025-10-06 (two-session rule), 2026-01-21 |
| `B2_TIGHT_ENTRY_LOW_INTRADAY_HARD` | B2 / FRESH_UNFLOWN / TIGHT (tight variant) | `ENTRY_CANDLE_LOW` | `INTRADAY_HARD` | 2026-01-14, 2026-01-07 |
| `B2_KEY_K_PLATFORM_CLOSE_CONFIRM` | B2 / FRESH_UNFLOWN or ALREADY_RISEN / LOOSE | `KEY_K_OR_PLATFORM` | `CLOSE_CONFIRM` | 2025-10-06, 2026-01-21 |
| `B2_YELLOW_LINE_CLOSE_CONFIRM` | B2 / FRESH_UNFLOWN or ALREADY_RISEN / LOOSE (explicit alternative, no default) | `YELLOW_LINE` | `CLOSE_CONFIRM` | 2025-12-03, 2026-01-21 |
| `BRICK_FRESH_FAILURE_DISASTER` | BRICK / FRESH_UNFLOWN / either | `ENTRY_CANDLE_LOW` or `KEY_K_OR_PLATFORM` | `INTRADAY_HARD` (disaster) | 2026-03-18 |
| `BRICK_MATURE_DISASTER` | BRICK / FLOWN or ALREADY_RISEN / either | `ENTRY_CANDLE_LOW` or `KEY_K_OR_PLATFORM` | `INTRADAY_HARD` (disaster) | 2026-03-18 |

Every template also cites 2026-04-22, the close-versus-intraday meta-rule: only profit-to-loss is a general intraday exit; otherwise wait for the tail/close, except an explicitly selected setup-specific `INTRADAY_HARD` override (the B1 hand-tight override, the B2 tight variant, the brick disaster stop). Which activation applies is fixed by the template, never swapped to fit a broker or a wide stop. A stop too wide for `risk_budget` is solved by a smaller `quantity` the user chooses.

## Brick: price stop and holding rules are separate

Brick rules are state/time exits distinct from the price disaster stop, and both regimes may use them provided the trend, N, volume and MACD gates are satisfied elsewhere; regime alone is not a veto. A brick always keeps a valid price basis for its disaster stop. State and time exits are emitted separately as `holding_exit_rules` (`is_price_stop: false`) and never become a stop price or a broker order:

- Fresh failure: `BRICK_NEXT_OPEN_NO_EXPLOSION` (time/behavior): no rise after the next open → manual exit.
- Mature: `BRICK_RED_TO_GREEN` and `BRICK_FOUR_RED_BRICKS` (state), `BRICK_LAST_THREE_MINUTES` (A-share red->green evaluation in the last three minutes, the closing call auction).

## Source status

The course notes were locally verified outside this public repository, and the portable date and section anchors for each template are included in the table above (with the 2026-04-22 meta-rule). The notes themselves, and any transcript wording, are not copied here. Anything the table does not list is unsupported and blocks.
