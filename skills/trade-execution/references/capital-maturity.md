# Capital maturity and scale-up

Mirrors the lifecycle contract (sections 4a and 4b). The contract requires inputs and states rules; it embeds no number. This skill embeds none either: every budget, floor, and policy value below is persisted on the ticket or supplied by the caller.

## Isolated validation capital

The trading capital is isolated validation capital: it does not affect living expenses, does not assume the current stage is profitable, and a smaller stage does not change whether a setup is valid. Practice reduces size; it never lowers the standard of the setup.

## Setup quality, lane, stage

| Lane (`decision_lane`) | Approvable | Required `setup_quality` | Required persisted inputs |
|---|---|---|---|
| `A_CIRCLE` | yes | `A` | `capital_stage`, `risk_budget` |
| `PRACTICE` | yes | `VALID` | `capital_stage`, `risk_budget`, `min_reward_risk`, complete logic (`strategy`, `thesis`, `trigger_text`, `invalidation`, at least one target), explicit stop (`stop_kind`, `stop_trigger`, `stop_limit`) |
| `AMBIGUOUS` | never | any | none: drafts only |
| `REJECT` | never | any | none: archive only |

- `AMBIGUOUS` and `REJECT` are never executable, whatever the quality or stage says. A ticket created without a lane lands on `AMBIGUOUS`.
- `capital_stage` is an account-defined label (`[A-Z][A-Z0-9_]{0,31}`). It is only checked for presence. The same setup in any stage, at any smaller quantity, gets the same validity verdict.
- Floors apply to every lane when persisted: `max_loss_amount <= risk_budget`; `entry_max × qty + fee <= capital_budget`; `r_multiple >= min_reward_risk`. `capital_budget` (notional) and `risk_budget` (worst loss) are independent rulers; both must pass. A-circle is not exempt from either.
- `min_reward_risk` is supplied by the caller or account policy at drafting and then frozen into `terms_sha256`. The execution audit never supplies or lowers it; it also checks the live reference price against it (`BLOCKED` below, warning at the worst-case fill).

## Reading a blocked lane

State the cause in one line (for example "lane AMBIGUOUS: not executable", "max_loss_amount 650.00 exceeds risk_budget 550.00"). Do not suggest relabelling the setup, shrinking the stage label, or loosening a persisted number to make a ticket pass. A different judgment or size is a new draft and a new human approval.

## Scale-up is a proposal, nothing more

Raising single-trade risk or the capital stage can only be proposed, from the service's same-strategy real-fill metrics and a policy the caller supplies. It is never triggered by one trade, a recent win, or excitement.

```powershell
& <python> @svc scale-up --db <database> --strategy "<exact strategy text>" [--market US|A] --policy-json <scale_up_policy_file>
& <python> -X utf8 scripts\audit_ticket.py scale-up-proposal --result <that output> --strategy "<exact strategy text>"
```

- The policy file holds exactly `min_sample_size` (integer above 1), `max_drawdown_r` (in R), `min_plan_adherence` (share in (0, 1]), optionally `source`. These values are the caller's; do not suggest, default, or round them. A missing policy file means no proposal.
- The service metrics come from fully closed positions of tickets whose `strategy` text is identical (no pooling across strategies): `sample_size`, `expectancy_r` (must be strictly positive), `max_drawdown_r`, `plan_adherence` (protective stop placed, loss within `max_loss_amount`, fills within approved terms). Judge by these, with `policy_sha256` and `sample_sha256` for reproducibility.
- The result always carries `proposal_only`, `mutates_tickets: false`, `auto_approve: false`. The audit script additionally requires `eligible`, every gate passed, a sample of more than one real trade, the exact strategy, and the echoed policy.
- If eligible, say so as a proposal to the human with the metrics. The next step is a new draft (`$market-review` on 固化) and a new human approval. This skill changes no ticket, size, or stage and never approves.
- If not eligible, or the service has no lifecycle layer or closed fills, report the gate reasons and stop. Subjective inputs (a feeling of confidence, a single large win) are not data and are not accepted.
