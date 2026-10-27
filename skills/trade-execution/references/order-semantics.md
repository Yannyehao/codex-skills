# Order and position semantics

Terms are the service's (`zradar.trade_lifecycle`). The ticket's persisted fields decide; nothing here introduces a threshold.

## Execution mode is ticket data

- **`MARKETABLE_LIMIT`** (breakout, opening burst, 搬砖): a limit order that can fill at the open or trigger, with a **pre-approved ceiling `entry_max`** (at least `entry_planned`). Entry orders are always limit orders; market entries are not allowed. The ticket carries a persisted `review.veto_review` with `n_pattern`, `trend`, `volume`, `macd`, each `{veto, evidence}`; any `veto: true` or a missing dimension blocks. Vetoes are not re-entered from chat at execution time; if conditions changed, the ticket is stale and needs a new draft. If the ask is above `entry_max`, do not chase, do not raise the limit, do not substitute a new plan.
- **`PASSIVE_LIMIT`** (pullback, B1, B2, white or yellow line): a passive limit at `entry_planned` (`entry_max` equals it). If the limit is at or above the ask it would fill at once and is no longer the approved structure entry; stop and discuss.
- An arrow, signal, or review verdict alone never means execute. A missing or unrecognized mode blocks; never infer it from the setup name or from chat. The service's mode hint is a hint only.

## Entry form and numbers

Show the fields the way a broker form asks for them: side, symbol, order type (`LIMIT`), quantity, limit price, time in force. The audit prints them from the ticket: `MARKETABLE_LIMIT` shows `entry_max` as the ceiling (the human may set a lower limit, never a higher one); `PASSIVE_LIMIT` shows `entry_planned`. Time in force comes from the ticket's `order_template`; confirm it on the form. The order quantity is at most the approved `quantity`; the human may place fewer, never more, and the fills record what actually happened.

Numbers come from the ticket, not from a fresh sizing: worst-case cost `entry_max × qty + fee_estimate` against `capital_budget`; worst loss `max_loss_amount` against `risk_budget`; `r_multiple`. The audit adds reward/risk at the current reference (ask for a marketable limit, `entry_planned` for a passive one) and at the worst-case fill (`entry_max`). A reference below a persisted `min_reward_risk` blocks. Fees: `fee_estimate` is the ticket's assumption; actual fees go on each fill (`fee`). No portfolio or concentration rule is applied here because the ticket persists none; do not invent one.

## Protective stop-limit

A sell stop-limit has two prices: the **trigger** activates the order, the **limit** is the lowest price it may fill at. The service requires `limit <= trigger` and rejects a limit below the ticket's approved `stop_limit` (looser). Always display it as `trigger 95.00 >= limit 94.50`, never a bare "stop 95". Warn every time: if price gaps or runs through the limit, the order triggers but does not fill and the position stays open, so the loss at the limit is not a ceiling. Also report the loss if the stop fills at its limit.

The protective order is placed after an entry fill (`attach_stop`), for at most the open quantity. A position is "protected" only for the quantity of live protective orders whose trigger, limit, and quantity are evidenced. Do not stack a second protective order over the same shares; amend the first.

## Recording rules

- Cancel with no fill ends the ticket with no position. Expiry is recorded as expiry (only on or after the order's expiry session), not as cancel; a rejection keeps the broker's reason.
- A partial fill creates a position for the filled quantity only. Say whether the remainder is still working; it needs its own cancel or expiry evidence.
- Fill price, quantity, and fee come from the fill evidence, not from the limit or the ticket. A fill price above an entry limit or below a sell limit is an input error the service rejects; check the evidence rather than adjusting it. A fill that arrives after the order's terminal event is accepted only if it happened earlier.
- If the evidence conflicts with the ticket (price, quantity, symbol, order type, account), record nothing; show the conflict and ask. Never edit evidence to fit the ticket.
- Orders, fills, and cancels are facts the human or a broker export reports. This skill never submits, cancels, or modifies anything at the broker.

## Position management

When the user asks about stop, target, or holding, read `state` and answer from recorded fills plus a fresh broker screenshot of the live orders and quote. Changing the stop, target, or size is an amendment: state its effect on risk and R against the approved plan, require the human's explicit instruction, and record it as an event with evidence (`amend_order`, or a new protective order). The service refuses terms looser than the approved ones; raising risk beyond the approved `max_loss_amount` or `risk_budget` is not an amendment but a new draft and a new human approval. Chart-structure judgment for the holding question follows the review profile (`$market-review`); this skill owns the order and ledger facts.
