# Historical execution replay

Replay answers a different question from live execution: “using only what was knowable at the
decision cutoff, what would this approved simulation have done as later stages were revealed?” It is
training and case evidence, not a lifecycle ticket, broker instruction, order, fill, or position.
Version 1 replays exactly one execution session: `OPEN` then that session's `CLOSE`. Later sessions,
multi-day holding management, targets, and exits belong to a future version and must not be inferred
from this journal.

## Hard boundary

- Replay never reads `config.local.json`, never opens the lifecycle database, never calls
  `zradar.trade_lifecycle`, and has no `apply` operation.
- `--output` accepts only a new `.json` path and uses exclusive creation. An existing JSON, database,
  or any other file is never overwritten; failure details fall back to stdout when the requested
  destination is unsafe or already exists.
- Its human approval approves only the simulation terms. It is not the lifecycle service's
  `APPROVED` event and cannot be converted into one.
- Keep scenario, event, and journal files in a temporary directory or a case-evidence directory,
  never in the lifecycle database or a production pipeline output directory.
- A replay result may be attached later by `trade-case-logger`; it never records itself as a real
  trade and never changes a setup threshold.
- If the user wants to place a real order, leave replay mode. `$market-review` must first persist a
  new draft on explicit 固化, the human must approve it in the service, and live execution starts
  again from the normal state/audit gate.

## Why stages are separate files

One file containing the entire future path defeats historical practice even if later fields are
hidden in the answer. Replay therefore accepts information in this order only:

1. `prepare`: cutoff-safe setup evidence and human-approved simulation terms;
2. `OPEN`: only an opening bid/ask snapshot or an explicitly labelled OHLC-open proxy;
3. `CLOSE`: the complete bar after the regular-session close.

The open event and its evidence JSON reject `high`, `low`, `close`, and `volume`. Close cannot be
submitted before open. Every input is hashed into an immutable `replay_id`; altering the plan makes
the next stage fail. These checks prove file hashes, declared `last_bar_date`, exact stage order, and
the limited JSON fields used at OPEN/CLOSE. They cannot prove that free text is honest or that an
image contains no later annotation. The human must inspect `source.decision_statement`,
`basis_evidence`, and cutoff images for hindsight before approving the replay.

## Prepare a scenario

Run the pure helper from the skill folder:

```powershell
& <python> -X utf8 scripts\replay_execution.py prepare `
  --plan <replay-plan.json> --output <replay-prepared.json>
```

The plan is JSON. Prices and amounts are decimal strings; quantity is an integer. `target` alone is
optional. Every other field below is required:

```json
{
  "schema": "trade-execution-replay-v1",
  "mode": "REPLAY",
  "market": "US",
  "symbol": "TICKER",
  "decision_cutoff": "YYYYMMDD",
  "execution_date": "YYYYMMDD",
  "source": {
    "kind": "case_annotation",
    "reference": "case:<stable reference>",
    "decision_statement": "the decision being simulated using cutoff knowledge only"
  },
  "simulation_approval": {
    "approved_by": "human:NAME",
    "approved_at": "ISO-8601 timestamp with offset",
    "note": "approval of replay terms only; not live authorization"
  },
  "trade_type": "B1_YELLOW_LINE_SWING",
  "basis_level": "10.00",
  "basis_evidence": "what the cutoff-safe chart shows about this level",
  "execution_mode": "MARKETABLE_LIMIT",
  "entry_planned": "10.10",
  "entry_max": "10.20",
  "quantity": 10,
  "stop_limit": "9.95",
  "target": "11.00",
  "fee_estimate": "1.00",
  "risk_budget": "10.00",
  "assume_fill_if_eligible": true,
  "evidence": [{
    "role": "cutoff_safe",
    "kind": "cutoff_chart",
    "path": "<local evidence file>",
    "sha256": "<64 lowercase hex>",
    "last_bar_date": "YYYYMMDD"
  }]
}
```

`source.reference` may point to a later case annotation for provenance, but
`source.decision_statement` states only what the simulated decision maker decides at the cutoff. Do
not paste the case's later outcome or hindsight verdict into the prepared plan; results enter only
through subsequent event stages. This is a semantic human-review requirement, not something a
free-text validator can prove automatically.

The helper loads the canonical selector from the sibling `market-review` skill. `trade_type` must be
one exact `zge-stop-v1` type; the helper derives basis kind, activation, broker mode, and holding
rules from that selector. It blocks generic `B1` / `B2`, a future-dated evidence file, hash mismatch,
unsupported execution mode, stop/entry inconsistency, or risk above the simulation budget.

`MARKETABLE_LIMIT` can be tested against the open ask or proxy up to `entry_max`.
`PASSIVE_LIMIT` has `entry_max == entry_planned`; at open it remains working only when the ask is
above the limit, and a later daily low touching the limit is labelled a hypothetical fill whose
sequence and actual execution are unproven.

## `BRICK_ZERO_DAY` entry timing

`BRICK_ZERO_DAY` is the first-red-brick signal state, not a same-day entry rule. Entry may be near
the signal-day close or on the next trading-day morning (`market-review`'s
`strategy-stop-playbook.md` owns the rule). Version 1 has no near-close stage, and `prepare` requires
`execution_date` after `decision_cutoff`, so a signal-day near-close entry cannot be replayed here.

A next-morning exercise has the signal day as `decision_cutoff` and the next trading day as
`execution_date`. The buy candle is then the execution session, so its low is unknown at `OPEN`. When
the compiler returns `ENTRY_GATE_ONLY`, use a gate-only plan: the common plan fields plus `entry_max`
and `chart_facts`, with no `trade_type`, basis, stop, quantity, fill, or risk field.

- A full plan with `trade_type: BRICK_ZERO_DAY` is rejected, so a brick cannot bypass the compiler.
- `prepare` runs `market-review`'s `trade_policy_core.py` and refuses any other status. `entry_max`
  must equal the compiled value. It, `chart_facts`, and the compiler's status and policy are frozen by `replay_id`.
- `OPEN` yields `BLOCKED_BY_PRICE` (ask above `entry_max`) or `PRICE_ELIGIBLE_STOP_PENDING`. Neither
  is a fill, ticket, or validated stop.
- The journal ends at `OPEN`: a `CLOSE` event is blocked, so no later low can backfill a stop.
- The helper derives no gap percentage and reads no volume ratio. It checks real dates and order, not a
  trading calendar: replay evidence and the outer workflow establish the next observed session.

The one-session limit still applies: nothing here extends replay past that session's `CLOSE`.

## Reveal the open

Create a small stage-limited evidence JSON with exactly these keys:

```json
{"stage":"OPEN","session_date":"YYYYMMDD","quote_kind":"OHLC_OPEN_PROXY","bid":"10.12","ask":"10.12","open":"10.12"}
```

Use `BROKER_BID_ASK` for a genuine archived quote. Use `OHLC_OPEN_PROXY` only when bid, ask, and open
are the same proxy value; the result warns that no spread or real fill is proven. Hash that file and
put it in the event:

```json
{
  "schema": "trade-execution-replay-event-v1",
  "mode": "REPLAY_EVENT",
  "replay_id": "<prepared replay_id>",
  "stage": "OPEN",
  "session_date": "YYYYMMDD",
  "quote_kind": "OHLC_OPEN_PROXY",
  "bid": "10.12",
  "ask": "10.12",
  "open": "10.12",
  "evidence": {
    "role": "replay_event",
    "kind": "replay_open_snapshot",
    "path": "<the stage-limited JSON above>",
    "sha256": "<64 lowercase hex>",
    "last_bar_date": "YYYYMMDD"
  }
}
```

Advance once:

```powershell
& <python> -X utf8 scripts\replay_execution.py advance `
  --journal <replay-prepared.json> --event <open-event.json> --output <replay-open.json>
```

Results say `HYPOTHETICALLY_FILLED`, `WORKING_PASSIVE_LIMIT`, or `BLOCKED_BY_PRICE`; none is a broker
fact.

## Reveal the close

The close evidence JSON has exactly `stage`, `session_date`, `open`, `high`, `low`, `close`, and
`volume`. The event repeats those values and cites the JSON as `kind: replay_close_snapshot`. Advance
from the open journal, never from the prepared journal.

The stop result preserves canonical semantics:

- `CLOSE_CONFIRM`: an intraday low through the level does nothing by itself; only a close below it
  yields `EXIT_AFTER_CLOSE`.
- `INTRADAY_HARD`: no current full plan reaches this, because `BRICK_ZERO_DAY` is rejected there. A low through the level would yield `TRIGGERED_FILL_UNKNOWN`, not an invented stop
  fill—the daily bar cannot prove price sequence or execution.
- holding/time rules are returned as `HUMAN_JUDGMENT_REQUIRED`; the script does not infer a chart
  verdict from OHLC.

The final single-session journal is deterministic, carries every evidence hash, retains
`production_writes: false` and `broker_actions: false`, and is suitable as a cutoff-aware artifact
for a later case annotation. It does not say what happens on the next session and does not manage a
hypothetical holding beyond the recorded close.

## Stop conditions

Block rather than repair when a stage is skipped, a plan is edited after prepare, an evidence hash
does not match, an open snapshot contains end-of-day fields, the canonical selector is missing, a
simulation term is absent, a gate-only journal receives `CLOSE`, or the
output path is not a new `.json` file. Never fall back from replay
to the live service, overwrite an artifact, or make replay approval look like live approval.
