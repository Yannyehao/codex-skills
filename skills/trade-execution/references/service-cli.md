# Lifecycle service CLI (concrete mapping)

The service is the module `zradar.trade_lifecycle` of the zAI repository (contract schema v6). There is no adapter and no field mapping: the JSON it prints is what `scripts/audit_ticket.py` reads. If a file does not look like service output, the audit blocks; reload from the service, never edit.

Settings come from `config.local.json` → `lifecycle_service` (`python`, `project_root`, `database`, `human_actor`, `import_actor`, optional `scale_up_policy_file`). Run every command with `project_root` as the working directory and keep temp files outside the repository (for example under `$env:TEMP`).

```powershell
$svc = @('-X','utf8','-m','zradar.trade_lifecycle')
& <python> @svc list    --db <database> [--market US|A] [--state APPROVED]   # read-only
& <python> @svc state   --db <database> --ticket-id <id>   > $env:TEMP\state.json    # read-only
& <python> @svc audit   --db <database> --ticket-id <id>   > $env:TEMP\audit.json    # read-only
& <python> @svc scale-up --db <database> --strategy <exact strategy text> [--market US|A] --policy-json <policy file>  # read-only
& <python> @svc apply   --db <database> --op <op> --args-json <args file>            # the only write
```

- `state`, `list`, `audit`, `scale-up` open the ledger read-only. `apply` is the only write path, writes only the `--db` path, and first upgrades a pre-v6 ledger to v6; back the ledger up before the first `apply`. This skill never runs `migrate`.
- Exit codes: `0` ok · `3` business rejection (`{"error": "LifecycleRejected: ..."}`, nothing written) · `2` `audit` found issues (JSON is still printed; save it, the audit script blocks on it) · `1` other error. After a `3`, report the service's message verbatim; never retry the same fact under a new key to get around it.
- `audit` needs `--ticket-id` so it covers exactly the ticket in hand (`tickets == 1`).
- Never pass `now`. The service stamps its own write clock.

## What `state` prints (the fields the audit relies on)

Ticket columns, unchanged: `ticket_id market symbol episode_id plan_id source_decision_id strategy execution_mode thesis trigger_text invalidation entry_planned entry_max stop_kind stop_trigger stop_limit expiry_date capital_budget quantity fee_estimate risk_amount max_loss_amount reward_amount r_multiple currency setup_quality decision_lane capital_stage risk_budget min_reward_risk profile_sha256 terms_sha256 created_by created_at`.
Parsed JSON columns: `review` (source evidence, `veto_review`, `mode_hint`, `deviation_note`, `capital_contract`, and the persisted `stop_semantics` that every execution audit requires), `order_template`, `targets` (`[{"price": "..."}]`), `fee_assumption`, `profile` (the market profile frozen at drafting, parsed: `market currency lot_size min_sessions_before_exit odd_lot_exit_closes_only price_limit fee_components calendar tdx`; it must hash to `profile_sha256`).
Persisted approval: `approval` is `null` until a human approves, then `{event_seq, approved_by, approved_at, terms_sha256, matches_ticket_terms, note}` taken from the stored `APPROVED` event. It is read-only evidence of what was approved, not an approval input.
Derived: `state`, `journal_state`, `state_at`, `approved_by`, `approved_at`, `orders[]` (`order_id role side status filled_qty terms{order_type quantity limit_price stop_trigger max_price tif expiry_date} events`), `position` (`open_qty entry_qty exit_qty avg_entry_price fees_total closed fills[]` or `null`), `outcome`, `events[]` (`seq event_type state_after actor occurred_at ref_kind ref_id`).

Vocabulary is exact: `market` `US`/`A`; `execution_mode` `MARKETABLE_LIMIT`/`PASSIVE_LIMIT`; `setup_quality` `A`/`VALID`/`AMBIGUOUS`/`REJECT`; `decision_lane` `A_CIRCLE`/`PRACTICE`/`AMBIGUOUS`/`REJECT`; states `DRAFT APPROVED ORDER_SUBMITTED PARTIALLY_FILLED POSITION_OPEN CLOSED CANCELLED EXPIRED REJECTED REVIEWED`. Prices and amounts are decimal text; `quantity` is an integer; `expiry_date` is `YYYYMMDD`; timestamps carry a UTC offset; actors are `kind:name`. The audit takes lot size and T+N from `profile`, never from a table of its own.

## The audit commands

```powershell
& <python> -X utf8 scripts\audit_ticket.py pre-submit --state $env:TEMP\state.json --service-audit $env:TEMP\audit.json `
    --session-date <YYYYMMDD> --bid <bid> --ask <ask> `
    --quote-evidence <broker quote screenshot> [--prev-close <A-share prev close>]
& <python> -X utf8 scripts\audit_ticket.py protective --state ... --service-audit ... --stop-trigger <t> --stop-limit <l> --shares <n>
& <python> -X utf8 scripts\audit_ticket.py post-trade-review --state ... --service-audit ... --args-json <mark_reviewed args file>
& <python> -X utf8 scripts\audit_ticket.py historical-post-trade-review --state ... --service-audit ... --args-json <mark_historical_reviewed args file>
& <python> -X utf8 scripts\audit_ticket.py check-args --op <op> --args-json <args file>
& <python> -X utf8 scripts\audit_ticket.py idempotency-key --ticket-id <id> --op <op> [--broker-ref <id>] [--evidence <file>]
& <python> -X utf8 scripts\audit_ticket.py scale-up-proposal --result <scale-up output> --strategy <exact strategy text>
```

There is no hash argument. The approved hash is `state.approval.terms_sha256`, persisted by the service when the human approved; the audit requires it to equal `state.terms_sha256` and `matches_ticket_terms` to be true, and requires `approval` to agree with the single `APPROVED` event. If `approval` is `null` or does not match, the result is `BLOCKED`; do not ask the user for a hash, do not copy one from chat, and do not approve on their behalf.

## Event → operation → args

`apply --op` takes a JSON object of the service function's keyword arguments; `ticket_id` / `order_id` ride inside it. Validate every file with `check-args` first. Actors: the user reporting from a screenshot is `human_actor`; a broker export file is `import_actor`. `session_date` is the market's trading date (`YYYYMMDD`).

| Evidence the user supplies | `--op` | Identity + required keys | Optional keys |
|---|---|---|---|
| Live entry order on the broker screen | `submit_order` | `ticket_id`, `order_type` `LIMIT`, `quantity`, `limit_price`, `session_date`, `submitted_by`, `occurred_at`, `idempotency_key` | `max_price`, `tif`, `expiry_date`, `broker_ref`, `evidence` |
| Protective stop-limit live after an entry fill | `attach_stop` | `ticket_id`, `session_date`, `submitted_by`, `occurred_at`, `idempotency_key` | `stop_trigger`, `stop_limit`, `quantity`, `expiry_date`, `broker_ref`, `evidence` (omitted trigger/limit/quantity default to the ticket's and the open quantity; pass what the screen shows) |
| Order modified at the broker | `amend_order` | `order_id`, `session_date`, `amended_by`, `occurred_at`, `reason`, `idempotency_key` | `quantity`, `limit_price`, `stop_trigger`, `max_price`, `expiry_date`, `evidence` |
| Order cancelled / expired / rejected | `cancel_order` / `expire_order` / `reject_order` | `order_id`, `session_date`, `recorded_by`, `occurred_at`, `reason`, `idempotency_key` | `evidence` |
| Entry execution | `record_fill` | `order_id` (the ENTRY order), `quantity`, `price`, `session_date`, `occurred_at`, `recorded_by`, `idempotency_key` | `external_ref` (broker execution id), `fee`, `evidence` |
| Exit execution (stop, target, manual) | `record_exit_fill` | same as `record_fill`, `order_id` of the exit order | same |
| Approved ticket past `expiry_date`, no order ever submitted | `expire_ticket` | `ticket_id`, `as_of_date`, `recorded_by`, `occurred_at`, `idempotency_key` | |
| The human withdraws an approved ticket before any order | `cancel_ticket` | `ticket_id`, `cancelled_by`, `occurred_at`, `reason`, `idempotency_key` | |

Value rules enforced by `check-args` (and by the service): prices, `fee`, `max_price` as decimal strings with at most 4 places; `quantity` a positive integer; dates `YYYYMMDD`; `occurred_at` ISO-8601 with an offset (`2026-10-27T09:31:00-04:00`); `evidence` a JSON object (file name and SHA-256, never a machine path); `submitted_by` / `amended_by` / `cancelled_by` / `recorded_by` of `expire_ticket` are `human:<name>`; fills, cancel/expire/reject use `human:` or `import:`.

Never prepared by this skill: `approve` (the human's own act, with the terms hash they reviewed), `create_draft` (only `$market-review` on an explicit 固化), `migrate`.

`attach_stop` needs a successful state-aware `protective` result first. `check-args --op attach_stop` validates only the shape of the args file and has no ticket state, so it cannot know the persisted `stop_semantics.activation`; `protective` blocks unless it is `INTRADAY_HARD`, and any other activation is never attached ([stop-semantics.md](stop-semantics.md)). Every execution audit also blocks when `review.stop_semantics` is missing or malformed.

`mark_reviewed` and `mark_historical_reviewed` stay forbidden in `check-args`. In SKILL.md's post-trade review mode `mark_reviewed` is prepared only through the dedicated `post-trade-review` gate, then run with the lifecycle service `apply --op mark_reviewed --args-json <file>`. The generic gate explicitly blocks any state carrying historical-import markers (`historical_import`, `pre_system_trade`, `historical_id`) before it parses a normal ticket. A historical import uses the separate gate below.

- Inputs: the unedited `state` and `audit --ticket-id` output plus the args file. It prints `ARGS_OK` or `BLOCKED` and never writes.
- Requires the current `state` to be exactly `CLOSED`, `CANCELLED`, `EXPIRED`, or `REJECTED` (not `REVIEWED`, not anything open), `journal_state` equal to it, and a clean service audit.
- Args: `ticket_id` (equal to the state's), `reviewed_by` `human:<name>`, `outcome`, `note` (non-empty), `occurred_at` (with a UTC offset), `idempotency_key` (non-empty), optional non-empty `annotation_id`; no other keys.
- `outcome` is one of the service's: `CLOSED` takes `机会识别成功、执行完成` or `机会识别失败`; `CANCELLED`/`EXPIRED`/`REJECTED` with no position takes `机会识别成功、执行未覆盖` or `机会识别失败`.
- `outcome` and `note` are the user's explicit words; this skill never infers or fills them. The gate does not require execution-time stop semantics, so historical tickets stay reviewable.

```json
{"ticket_id": "<id>", "reviewed_by": "human:NAME", "outcome": "<user-stated outcome>", "note": "<user-stated note>",
 "occurred_at": "2026-10-28T09:00:00-04:00", "idempotency_key": "<stable key>"}
```

Then read `state` back and report the stored state.

### Historical import review

A pre-system historical import (state shows `historical_import` and `pre_system_trade` true, with a `historical_id`) is reviewed only through `audit_ticket.py historical-post-trade-review --state <state.json> --service-audit <audit.json> --args-json <file>`. It prints `ARGS_OK` or `BLOCKED` and never writes.

- Inputs: the unedited historical `state`, the service `audit`, and the args file.
- Requires `historical_import` and `pre_system_trade` both true, a current `state` of exactly `CLOSED` (not `REVIEWED`), and a clean service audit.
- Args: `historical_id` (equal to the state's), `reviewed_by` `human:<name>`, `outcome` (`机会识别成功、执行完成` or `机会识别失败`), `note` (non-empty), `occurred_at` (with a UTC offset), `idempotency_key` (non-empty), optional non-empty `annotation_id`; no other keys.
- `outcome` and `note` are the user's explicit words; never inferred.
- After `ARGS_OK`, run the lifecycle service `apply --op mark_historical_reviewed --args-json <file>` (it identifies the trade by `historical_id`), then the mandatory `state` readback, and report the stored state.

```json
{"historical_id": "<historical_id>", "reviewed_by": "human:NAME", "outcome": "<user-stated outcome>", "note": "<user-stated note>",
 "occurred_at": "2026-10-28T09:00:00-04:00", "idempotency_key": "<stable key>"}
```

Example `submit_order` args (the ENTRY limit is at most the approved `entry_max`; a PASSIVE_LIMIT is at most `entry_planned`; the quantity is at most the approved quantity):

```json
{"ticket_id": "<id>", "order_type": "LIMIT", "quantity": 100, "limit_price": "100.00", "tif": "DAY",
 "session_date": "20261027", "submitted_by": "human:NAME", "occurred_at": "2026-10-27T09:31:00-04:00",
 "idempotency_key": "<audit_ticket idempotency-key>", "broker_ref": "<broker order id>",
 "evidence": {"file": "order.png", "sha256": "<hash>"}}
```

Example `record_fill` args:

```json
{"order_id": "<order id from submit_order output or state.orders[]>", "quantity": 100, "price": "100.00", "fee": "1.00",
 "session_date": "20261027", "occurred_at": "2026-10-27T09:32:00-04:00", "recorded_by": "human:NAME",
 "idempotency_key": "<key>", "external_ref": "<broker execution id>", "evidence": {"file": "fill.png", "sha256": "<hash>"}}
```

## Idempotency and read-back

Every write needs an `idempotency_key`; derive it with `idempotency-key` from the ticket, the operation, the broker reference, and the SHA-256 of the evidence. Same key and same content → the service returns the original with `replay: true` and writes nothing; same key with different content → rejected. Fills are also unique per `(order, external_ref)`.

After each write run `state` (and `audit`) again and report the stored `state`, `orders[].status`, `position.open_qty`, and audit result, not what you meant to write. A cancel or expiry with no fill ends the ticket with no position; a partial fill followed by a cancel keeps the filled position.
