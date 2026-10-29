# Ticket contract

The ticket and every state change live in one local SQLite ledger owned by the lifecycle service (`zradar.trade_lifecycle`, schema v6). Skills reach it only through that service's CLI ([service-cli.md](service-cli.md)). This file states what the skills rely on; the service's own contract document is the authority and wins on any conflict. The service records facts: it does not place orders, connect to a broker, read quotes, or contain trading thresholds.

## Raw ticket fields (as printed by `state`, no renaming)

| Field | Meaning |
|---|---|
| `ticket_id`, `market` (`US` or `A`), `symbol`, `strategy` | identity and market; the market selects the frozen profile |
| `execution_mode` | `MARKETABLE_LIMIT` or `PASSIVE_LIMIT`, explicit data, never inferred from the strategy |
| `entry_planned`, `entry_max` | entry reference price and the pre-approved ceiling; `PASSIVE_LIMIT` has `entry_max == entry_planned` |
| `stop_kind`, `stop_trigger`, `stop_limit` | explicit stop; `stop_limit <= stop_trigger < entry_planned <= entry_max` |
| `targets` | `[{"price": "..."}]`, strictly ascending, first above `entry_planned` |
| `quantity`, `expiry_date` (`YYYYMMDD`) | approved maximum whole shares; last valid session |
| `capital_budget`, `risk_budget`, `fee_estimate` | notional ruler (`entry_max × qty + fee`), worst-loss ruler (`max_loss_amount`), fee assumption |
| `risk_amount`, `max_loss_amount`, `reward_amount`, `r_multiple` | service-computed, recomputed by the audit |
| `setup_quality`, `decision_lane`, `capital_stage`, `min_reward_risk` | maturity/capital contract, see [capital-maturity.md](capital-maturity.md) |
| `thesis`, `trigger_text`, `invalidation`, `review` | logic and review evidence; `review.veto_review` holds `n_pattern`, `trend`, `volume`, `macd` each as `{veto, evidence}`; `review.stop_semantics` holds the stop's basis and activation ([stop-semantics.md](stop-semantics.md)) and is required on every executable ticket and validated by `audit_ticket.py`; without it every execution audit is BLOCKED |
| `terms_sha256` | hash of all terms; approval is bound to it |
| `profile`, `profile_sha256` | the market profile frozen at drafting, parsed (lot size, T+N, ...); the hash must recompute from it |
| `approval` | persisted approval fact from the `APPROVED` event: `{event_seq, approved_by, approved_at, terms_sha256, matches_ticket_terms, note}`; `null` until approved |
| `state`, `journal_state`, `approved_by`, `approved_at`, `events`, `orders`, `position` | derived facts |

Amounts follow the service: `risk_amount = (entry_planned − stop_trigger) × qty + fee`; `max_loss_amount = (entry_max − stop_limit) × qty + fee`; `reward_amount = (first target − entry_planned) × qty − fee`; `r_multiple = reward / risk`; each rounded half-up to 0.01.

## Approval gate (fail closed)

Execution proceeds only if all hold, checked by `audit_ticket.py` on the unedited service output:

- `state` is `APPROVED` (entry) or `PARTIALLY_FILLED` / `POSITION_OPEN` (management), and `journal_state` equals it.
- Exactly one `APPROVED` event exists, its actor is `human:<name>`, and `approved_by` / `approved_at` equal it. An agent, `review:`, `system:`, bare `human`, or machine approval is not approval.
- `terms_sha256` is a 64-hex digest and equals the persisted `approval.terms_sha256` read from the service state, which must also report `matches_ticket_terms` and agree with the `APPROVED` event (actor, time, sequence). Nothing is typed in by the user. A missing `approval` or a different hash means different or no approved terms: stop; draft and approve a new ticket.
- `review.stop_semantics` is present and valid (`basis.kind`, decimal-text `basis.level` with non-empty `basis.evidence`, `activation`, `reclaim_by` required for and allowed only with `NEXT_SESSION_FAILURE_TO_RECLAIM`, `broker_implementation` required for `CLOSE_CONFIRM` / `NEXT_SESSION_FAILURE_TO_RECLAIM`, optional but nonempty if present for `INTRADAY_HARD`, unknown keys rejected); `basis.evidence` carries exactly one `canonical_trade_type=<TYPE>` and `policy=zge-stop-v1` marker, and the type must match `basis.kind` and `activation` exactly (missing, unknown, duplicate, or mismatched marker BLOCKS execution); every activation needs `stop_trigger == basis.level`. See [stop-semantics.md](stop-semantics.md).
- `profile` is the service's frozen profile for the ticket's market and hashes to `profile_sha256`; lot size and T+N are read from it.
- `audit --ticket-id` reports `available`, `ok`, one ticket, no issues (`terms_hash_mismatch`, `lane_gate_violation`, `approved_non_approvable_lane` and the rest are blockers).
- The ticket is read from the service. A ticket rebuilt from chat, a screenshot, a review paragraph, or Notion does not exist for this skill.

The audit adds no number of its own. It re-derives the lane gate and the amounts from the persisted terms, and the quote/order checks use only persisted ticket fields plus the user's broker screenshot (bid, ask).

## Lifecycle

```
DRAFT → APPROVED → ORDER_SUBMITTED → PARTIALLY_FILLED → POSITION_OPEN → CLOSED → REVIEWED
        (human only)                  (position exists)
DRAFT/APPROVED → CANCELLED | EXPIRED;  ORDER_SUBMITTED (no fill) → CANCELLED | EXPIRED | REJECTED
```

Terminal: `CLOSED CANCELLED EXPIRED REJECTED REVIEWED`. One ENTRY order per ticket; a new attempt is a new draft and a new approval. A position exists only from an entry fill; a cancelled, expired, or rejected unfilled entry creates none. Episodes and tickets have independent lifecycles; a fill does not close the opportunity record.

| Evidence | Service operation (see [service-cli.md](service-cli.md)) |
|---|---|
| live entry order | `submit_order` |
| protective stop-limit live | `attach_stop` |
| order modified | `amend_order` |
| cancel / expiry / rejection | `cancel_order` / `expire_order` / `reject_order` |
| entry / exit execution | `record_fill` / `record_exit_fill` |
| unused approved ticket past expiry | `expire_ticket` |

## Projection

Notion pages mirror the ledger after the fact. Never read Notion as the source of ticket or position state, and never record a transition only in Notion or only in chat.
