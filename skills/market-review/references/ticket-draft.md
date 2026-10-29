# Persisting a DRAFT ticket (only on an explicit 固化 / 生成交易单)

A review reads; this step writes exactly one DRAFT through the lifecycle service (`python -m zradar.trade_lifecycle`, schema v6) and nothing else. The service records facts and contains no trading thresholds; so does this file. Field names below are the service's own, passed through unchanged.

## Preconditions (any miss → say so, write nothing)

- The user's instruction names the action and the symbol.
- `config.local.json` → `lifecycle_service` is configured (`python`, `project_root`, `database`, `review_actor`). Run commands with `project_root` as the working directory.
- The ledger already holds an open plan with `kind = trade` for that symbol; `create_draft` takes its `plan_id` and reads entry condition, invalidation, and plan stop from it. Reviews do not create plans or episodes. Look it up with the read-only `list`/`state` or the ledger tools the project already uses; if there is no such plan, report that and stop.
- A previous live ticket on the same plan blocks a new draft; the service refuses.
- Stage and `ACTIONABLE` are never yours to set. The episode's latest assessment must already be an explicit review or human `ACTIONABLE` without a veto, as the service records it; a trigger, a single needle, or `eligible_review` alone is not that. If it is not, say so and write nothing.

## Classify the setup (from this review's chart reading)

| `setup_quality` | Meaning | `decision_lane` |
|---|---|---|
| `A` | A-grade setup inside the circle of competence; "做错也要做" | `A_CIRCLE` |
| `VALID` | ordinary but valid setup; complete logic and a clear stop | `PRACTICE` |
| `AMBIGUOUS` | cannot be classified yet | `AMBIGUOUS` (or omit; the service defaults to it) |
| `REJECT` | judged no | `REJECT` |

Rules:

- Quality is a judgment of the setup itself, from the evidence you actually read. Practice or a small account stage reduces **size only**; it never lowers the standard for `VALID` and never turns `AMBIGUOUS` into `VALID`. Do not upgrade a quality because the position is small, because it feels exciting, or because a lane is the only one that could be approved.
- `A_CIRCLE` requires quality `A`; `PRACTICE` requires `VALID`. `AMBIGUOUS` and `REJECT` can be drafted for the record but can never be approved or executed; tell the user so in the same message.
- Do not draft `REJECT` unless the user wants the rejection archived.

## Inputs the user or account policy must supply (never invent, default, or round)

`quantity`, `capital_budget`, `risk_budget` (≠ `capital_budget`; the worst loss `max_loss_amount` must not exceed it), `capital_stage` (an account label such as `PRACTICE`), `expiry_date`, `fee_estimate`, `stop_limit`, and for `PRACTICE` a `min_reward_risk` that the account policy chooses. Also required: `strategy`, `thesis`, `execution_mode`, `entry_planned`, `targets`; `stop_trigger` defaults to the plan stop (a different value needs `deviation_note`); `trigger_text` defaults to the plan entry condition.

- `PRACTICE` additionally needs complete logic (strategy, thesis, trigger, invalidation, at least one target) and an explicit stop (`stop_kind`, `stop_trigger`, `stop_limit`), plus the persisted `min_reward_risk` the ticket's `r_multiple` must meet.
- `execution_mode` is stated explicitly: `MARKETABLE_LIMIT` (with a pre-approved `entry_max` and a `veto_review` of `n_pattern`, `trend`, `volume`, `macd` each `{veto: bool, evidence: text}` taken from this review's chart reading) or `PASSIVE_LIMIT` (`entry_max` omitted or equal to `entry_planned`). A strategy name never selects the mode for the user.
- Prices and amounts are decimal strings (prices up to 4 places, `risk_budget` up to 2); `quantity` an integer; `expiry_date` `YYYYMMDD`; timestamps with a UTC offset. Ask for anything missing; the service rejects an incomplete or over-budget A/PRACTICE draft and writes nothing.

## Stop semantics (required in every executable draft)

A price is not a stop rule. Every new draft's args carry a top-level `stop_semantics`, the object below, exactly; the service stores it at `review.stop_semantics`. You do not choose, tighten, or translate it: it records the stop plan the human approved for this setup (the user's stated basis and activation, or the plan already on the ledger). If the user has not stated both a basis and an activation, ask and write nothing; do not default them from the setup name, and do not copy a number from chat that the plan does not support.

```json
{"basis": {"kind": "<ENTRY_CANDLE_LOW | PRIOR_B1_N_LOW | WHITE_LINE | YELLOW_LINE | KEY_K_OR_PLATFORM>",
           "level": "<decimal text, at most 4 places>", "evidence": "<why this level, from this review's chart reading and the thesis>"},
 "activation": "<INTRADAY_HARD | CLOSE_CONFIRM | NEXT_SESSION_FAILURE_TO_RECLAIM>",
 "reclaim_by": "<required for NEXT_SESSION_FAILURE_TO_RECLAIM, otherwise optional>",
 "broker_implementation": "<how the human implements it at the broker; required for CLOSE_CONFIRM and NEXT_SESSION_FAILURE_TO_RECLAIM, optional for INTRADAY_HARD but non-empty if present>"}
```

- `basis.evidence` must be non-empty and tie `basis.level` to the thesis, trigger, or invalidation; `basis.level` is decimal text, never a JSON number.
- `INTRADAY_HARD`: `stop_trigger` must equal `basis.level`. Any other activation keeps `stop_trigger` / `stop_limit` as the economic reference that prices the plan's risk; no live broker stop is placed at that level, and `$trade-execution` shows only the human-only procedure from the required `broker_implementation`.
- A stop too wide for `risk_budget` is solved by a smaller `quantity` the user chooses, never by moving the level or changing the activation.
- Without a valid `stop_semantics`, `$trade-execution` blocks every execution audit, so a draft without it is not executable. The schema is audited by `trade-execution/scripts/audit_ticket.py`; the field list is the same in [../../trade-execution/references/stop-semantics.md](../../trade-execution/references/stop-semantics.md).

## Select the stop template (before `create_draft`, every executable draft)

Read [strategy-stop-playbook.md](strategy-stop-playbook.md). The user (or the ledger plan) states `setup`, `position_state`, `regime`, the `template_id`, `basis_kind`, the `basis_level` as decimal text, the chart `evidence`, `broker_mode`, and `broker_implementation` (required for `CLOSE_CONFIRM` and `NEXT_SESSION_FAILURE_TO_RECLAIM`, optional for `INTRADAY_HARD`, never empty when given). If any other is missing, ask and write nothing; never pick a template or level from the setup name, and never calculate the level. Then run the pure helper (no writes; it reads nothing):

```powershell
& <python> -X utf8 scripts\stop_template.py --setup B2 --position-state FRESH_UNFLOWN --regime TIGHT --template-id <template_id> --basis-kind <kind> --basis-level <decimal text> --evidence "<chart reading>" --broker-mode <mode> --broker-implementation "<human text>"
```

- Exit `2` / `BLOCKED` means an unsupported or contradictory combination: report its errors, ask the user, write nothing.
- On `OK`, pass `stop_semantics` unchanged as the top-level `stop_semantics` argument (stored as `review.stop_semantics`). Append `draft_text.trigger_text_append` to the args `trigger_text` (it carries the deterministic invalidation and holding guidance), and report `draft_text.invalidation` against the plan's invalidation; if the plan's differs, say so and stop rather than editing the plan.
- `holding_exit_rules` (brick state/time exits) are not prices: keep them in `trigger_text`, never in `stop_trigger` / `stop_limit`. For `INTRADAY_HARD`, `stop_trigger` must equal `basis.level`.
- `$trade-execution` only audits what is persisted; it never selects a template.

## Command and args

```powershell
& <python> -X utf8 -m zradar.trade_lifecycle apply --db <database> --op create_draft --args-json <args file>
```

Args file (keyword arguments of the service's `create_draft_from_plan`; temp file outside the repository):

```json
{"plan_id": "<plan id>", "strategy": "<exact strategy text>", "execution_mode": "PASSIVE_LIMIT",
 "thesis": "...", "entry_planned": "100.00", "targets": [{"price": "110.00"}], "stop_limit": "94.50",
 "stop_trigger": "95.00", "stop_kind": "stop_limit", "trigger_text": "...", "expiry_date": "20261028",
 "capital_budget": "10000.00", "quantity": 100, "fee_estimate": "0.00", "review_dimensions": {},
 "stop_semantics": {"basis": {"kind": "PRIOR_B1_N_LOW", "level": "95.00", "evidence": "<from this review>"},
                    "activation": "INTRADAY_HARD", "broker_implementation": "<human-stated>"},
 "setup_quality": "VALID", "decision_lane": "PRACTICE", "capital_stage": "PRACTICE",
 "risk_budget": "550.00", "min_reward_risk": "<account policy value>",
 "created_by": "review:NAME", "created_at": "2026-10-27T18:00:00-04:00", "idempotency_key": "<stable key>"}
```

`stop_semantics` is a top-level keyword argument of `create_draft_from_plan`; never pass a caller-built `review` object. The service stores it at `state.review.stop_semantics`, which is where the execution audit reads it. If the service rejects the argument or the read-back (below) shows no `review.stop_semantics`, report that verbatim and stop: do not retry it under another key or field name, and do not tell the user the draft is executable.

The shown numbers are illustrative; every real value comes from the user or account policy. Use `created_by` from `review_actor` (the service lets `review` create only DRAFTs). Derive `idempotency_key` deterministically from plan id, review session date, and strategy, so a retry replays instead of duplicating. Never pass `now`. Business rejection exits `3` with the reason; report it verbatim and fix the input rather than retrying a variant under a new key.

## Read back and hand over

Read `state --ticket-id <id>` and confirm `review.stop_semantics` is present and equals what the user approved, then report the stored `state` (`DRAFT`), `market`, `decision_lane`, `setup_quality`, `capital_stage`, `risk_budget`, the computed `max_loss_amount`, `r_multiple`, and `terms_sha256`. Tell the user the hash they would approve and that approval is theirs alone. Do not run `approve`; do not submit orders; do not edit the draft (changes are a new draft). Execution and recording go to `$trade-execution`.
