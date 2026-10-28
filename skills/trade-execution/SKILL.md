---
name: trade-execution
description: Guide Yehao through executing an already-persisted, human-approved trade ticket and recording the resulting order, fill, cancel, and position facts for U.S. or A-share trades through the configured lifecycle service. Trigger on 执行/怎么下单 for an existing ticket, an order, fill, or cancel screenshot, stop/target/holding management, "成交了/撤了", or a scale-up question. Never submits to a broker and never builds an executable plan from chat; market reviews, new ideas, and drafting belong to market-review.
---

# Trade execution

This skill checks and records. It never clicks a broker's submit, cancel, or modify button, automates a broker, or creates an executable plan from chat. The human places every order. Chat is not the ledger: the local lifecycle service (`python -m zradar.trade_lifecycle`) is the single source of truth, and Notion is only a projection of it.

## Setup and fail-closed loading

Read `config.local.json` beside this file (`config.example.json` shows the shape; real values stay local). Load the ticket only with the service's read-only `state` and `audit` commands, using the exact commands in [references/service-cli.md](references/service-cli.md). Feed their unedited output to `scripts/audit_ticket.py`. Stop and say exactly what is missing if the service is unavailable, the ticket is absent, or any approval-gate condition fails. Never reconstruct a ticket from chat, a screenshot, a review paragraph, or Notion, and never rename fields to fit an old export: a file that is not service output is rejected.

Read [references/ticket-contract.md](references/ticket-contract.md) for the raw fields, approval gate, and lifecycle. Read [references/capital-maturity.md](references/capital-maturity.md) for lane/quality/stage rules and scale-up. Read [references/order-semantics.md](references/order-semantics.md) before showing any order form or recording any broker event, and [references/profiles.md](references/profiles.md) for the ticket's market (`US` or `A`).

## Workflow

1. **Load and audit (dry run).** Export `state` and `audit --ticket-id` to temporary files outside the repository, then run, with the Python this machine requires:

   ```powershell
   & <configured-python> -X utf8 scripts\audit_ticket.py pre-submit --state <state.json> --service-audit <audit.json> --session-date <YYYYMMDD> --bid <bid> --ask <ask> --quote-evidence <screenshot> [--prev-close <A-share>]
   ```

   Bid and ask come from the user's current broker screenshot, which is the execution authority. Any `BLOCKED` verdict stops the flow; state the cause and fix it with the user. The gate reads the approval straight from the service state: the persisted `approval` record (the `terms_sha256` stored with the human's `APPROVED` event, which must equal the ticket's `terms_sha256` and be flagged `matches_ticket_terms`) and the frozen parsed `profile` (lot size, T+N), whose hash must equal `profile_sha256`. Nobody types a hash: you never ask the user for one, and a missing or mismatched `approval` is a block, not something to supply. The gate also requires a named `human:` approver, a clean service audit, `A_CIRCLE`/quality `A` or `PRACTICE`/quality `VALID`, and the persisted budgets and floors. `AMBIGUOUS` and `REJECT` are never executable. Do not argue past a block, relabel a setup, or tweak a persisted number.
2. **Show the order.** Present the exact broker form fields, quantity (at most the approved), worst-case cost, max loss against `risk_budget`, reward/risk, the planned protective stop-limit (`trigger >= limit`), the market constraints, and every warning.
3. **Final human confirmation.** Ask the user to confirm the exact fields. Without a fresh, explicit yes, do nothing further.
4. **Record only on evidence.** After the user places an order, record it only from a screenshot or export showing it; record fills, partial fills, cancels, expiries, and rejections only from matching evidence. Build the args file per [references/service-cli.md](references/service-cli.md), derive the key with `audit_ticket.py idempotency-key`, validate with `audit_ticket.py check-args --op <op>`, then run `apply --op <op> --args-json <file>` once. Re-reading the same evidence never creates a second event. Record one transition at a time.
5. **After a fill.** Re-read `state`; for management run `audit_ticket.py protective` with the stop fields the user is placing, then record `attach_stop` only from evidence of the live order. A cancel or expiry with no fill creates no position.
6. **Verify.** Read `state` and `audit` back and report the stored state, order status, open quantity, and audit result, not what you intended to write.

Allowed `apply` operations: `submit_order`, `attach_stop`, `amend_order`, `cancel_order`, `expire_order`, `reject_order`, `record_fill`, `record_exit_fill`, `expire_ticket`, and `cancel_ticket` on the human's explicit instruction. Never `approve`, `create_draft`, `mark_reviewed`, or `migrate`. Approval is the human's own act with the `terms_sha256` they reviewed, in the service; reading `state.approval` is evidence, never an approval input, and this skill never infers or performs it. Drafting is `$market-review` on an explicit 固化.

Creating or testing this skill authorizes no live write. A live `apply` needs the user's evidence for that exact fact.

## Scale-up

Only a proposal, from the service's same-strategy real-fill metrics and a policy the user supplies; never after one trade or on excitement. Run `scale-up` then `audit_ticket.py scale-up-proposal` (details in [references/capital-maturity.md](references/capital-maturity.md)). Present eligibility with metrics, change nothing, and send any larger size through a new draft and a new human approval.

## Stop conditions

Stop and ask when evidence is ambiguous (unreadable fill price, quantity mismatch, wrong symbol or account), when the broker's actual order differs from the ticket, when the service rejects a write, or when the user wants to change an approved field. A change within the approved bounds is an amendment recorded through the service on the human's explicit instruction; anything wider is a new ticket. Report a service rejection verbatim and do not retry it under a new key.
