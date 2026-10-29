# Stop semantics

A protective stop is two separate required concepts: **basis** (what level, and why) and **activation** (when it acts). A price alone (`stop_trigger`, `stop_limit`) is not a stop rule; a stop with no persisted semantics is not executable. This skill never chooses, tightens, or translates semantics: it audits what the approved ticket persisted and blocks otherwise.

## Where it lives

Every new executable ticket draft carries a `stop_semantics` object in its persisted `review` evidence (`review.stop_semantics`), written by `$market-review` from the stop plan the human approved (it persists that plan; it does not invent it), and covered by `terms_sha256` like every other term. If the service state shows no such object, or it is malformed or unsupported, there are no stop semantics for this skill: every execution audit (`pre-submit`, `protective`) returns BLOCKED, and the fix is a new draft and a new human approval. Never fill it from chat, a screenshot, a review paragraph, Notion, or the setup name. A historical ticket without it can only be handled in the explicit post-trade review mode (SKILL.md), never executed.

```json
{"basis": {"kind": "<BASIS>", "level": "<price>", "evidence": "<why this level, from the thesis/setup>"},
 "activation": "<ACTIVATION>",
 "reclaim_by": "<session; required for NEXT_SESSION_FAILURE_TO_RECLAIM>",
 "broker_implementation": "<how the human implements it at the broker; optional for INTRADAY_HARD>"}
```

Exact schema, enforced by `scripts/audit_ticket.py`: `basis` has exactly `kind`, `level`, `evidence`; `basis.level` is decimal TEXT (at most 4 places) and `basis.evidence` is non-empty text supporting it; `activation` is exactly one of the three values below; `reclaim_by` is non-empty text and required for `NEXT_SESSION_FAILURE_TO_RECLAIM`; `broker_implementation` is optional for `INTRADAY_HARD` but non-empty text if present, and required non-empty text for `CLOSE_CONFIRM` and `NEXT_SESSION_FAILURE_TO_RECLAIM`. No other keys. For `INTRADAY_HARD` the ticket's `stop_trigger` must equal `basis.level`.

## Basis: what level, and why

`basis.kind` is one of `ENTRY_CANDLE_LOW` (buy or post-entry candle low), `PRIOR_B1_N_LOW` (the prior B1 or N-pattern low), `WHITE_LINE`, `YELLOW_LINE`, `KEY_K_OR_PLATFORM` (key candle or platform low). `basis.level` is the price and `basis.evidence` ties it to the ticket's `thesis`, `trigger_text`, or `invalidation`. A level the thesis never supports is unsupported: BLOCK.

Which basis fits which setup is drafting guidance owned by `$market-review` (its stop-template helper selects a named template before the draft); this skill assigns none, never selects or re-runs a template, and only audits the persisted object. For reference only, as examples of what a ticket may state and never as defaults to apply: for B1 the structural stop sits below the buy candle or the prior N low; for B2 the first defense is the entry candle low on a closing basis, and the full structural stop can be the prior B1/N low.

## Activation: when the stop acts

| `activation` | Meaning | Broker order it permits |
|---|---|---|
| `INTRADAY_HARD` | any trade through the level during the session exits | a live protective STOP_LIMIT (`trigger >= limit`) |
| `CLOSE_CONFIRM` | acts only if the regular-session close is beyond the level; an intraday print through it is not a violation | no live intraday stop at that level. Human-only: a close-based alert and a manual exit after the close, or a next-session order the ticket spells out |
| `NEXT_SESSION_FAILURE_TO_RECLAIM` | a break is tolerated until `reclaim_by`; exit follows if price has not reclaimed the level by then | no live intraday stop at that level. Human-only: a check at the stated time, then a manual exit order |

A ticket may carry a separate, explicitly different disaster stop under `INTRADAY_HARD` with its own basis. That is its own persisted stop, not a rewrite of a close-confirmed one.

## Invariant

The audit enforces this: `pre-submit` prints a `protective_plan` (the live stop-limit) only for `INTRADAY_HARD`; for the other two it prints `human_only_stop_plan` (the persisted `broker_implementation` procedure, `live_broker_stop: false`) and treats the ticket's numeric `stop_trigger` / `stop_limit` as economic reference fields that price the plan's risk. `audit_ticket.py protective` returns BLOCKED unless the activation is `INTRADAY_HARD`. `check-args` has no ticket state and cannot see the activation, so a valid `check-args --op attach_stop` result alone never authorizes `attach_stop`: it requires a successful `protective` result on the current `state` for exactly the order being recorded.

Execution must not turn a `CLOSE_CONFIRM` or `NEXT_SESSION_FAILURE_TO_RECLAIM` rule into an intraday hard stop. Do not render that level as a STOP_LIMIT form, do not offer `attach_stop` for it, and do not run `audit_ticket.py protective` on it as if it were a live order. A stop too wide for the risk budget is handled by smaller quantity in a new draft and a new human approval, never by moving the level, tightening it to an unrelated intraday trigger, or changing its activation.

## Audit before showing or attaching any protective order

1. `stop_semantics` is present and valid per the schema above; `basis.evidence` ties the level to the thesis/setup (the audit checks it is non-empty; the human reads that it fits).
2. `NEXT_SESSION_FAILURE_TO_RECLAIM` has `reclaim_by`.
3. For `INTRADAY_HARD`, the ticket's `stop_trigger` / `stop_limit` agree with `basis.level`. For the other activations they are the reference level, not a live order.
4. The broker order can implement the activation. `INTRADAY_HARD` maps to a STOP_LIMIT. For the other two a broker stop order cannot express it: show the human-only procedure persisted in `broker_implementation` and no live stop form.

Any failure: BLOCK, name the missing or conflicting item, and require a new or amended ticket. Do not improvise from chat.

## Reading a historical outcome

A stop fill alone does not show the rule was followed. If a ticket said `CLOSE_CONFIRM` and the stop filled intraday while the regular close stayed on the safe side of the level, report that as a semantics mismatch fact for the human's post-trade review (SKILL.md, post-trade review mode). This skill does not correct, reinterpret, or rewrite the plan.
