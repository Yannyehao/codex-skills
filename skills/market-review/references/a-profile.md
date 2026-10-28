# A-share profile

Uses the same ledger and lifecycle as [review-contract.md](review-contract.md); only the market facts below differ. Config section: `profiles.a`.

## Session gate (manual)

No bundled artifact audit exists for this profile. Establish the review date yourself:

- Use the SSE/SZSE trading calendar, including holidays and make-up workdays; never weekday arithmetic.
- The latest closed session is the most recent trading day whose close (15:00 China time) has passed and whose data source shows a finished daily bar. A source still showing intraday data for today is partial: use the prior session or say the data is not final.
- State the review date and the data source's own last-bar date. If they differ, stop and expose both.

Fresh candidates, chart evidence, and the ledger come from the user's configured sources. If a source is unavailable, name it; do not reuse an old export as complete.

## Chart verdict versus execution facts

Chart verdicts are judged by structure alone. These market rules are **execution facts**: report them on a separate "执行可行性" line, never as a reason to change the chart verdict, upgrade, or downgrade:

- buy orders in 100-share lots (check the board's actual rule with the broker rather than assuming);
- T+1: shares bought today cannot be sold today, so a same-day protective sell is impossible and a gap-down next session may skip the stop;
- daily price limits (they differ by board and for ST or newly listed stocks; verify the current rule): a limit-up open may be unbuyable and a limit-down may be unsellable;
- suspensions and other status flags.

A clean chart that cannot be executed today stays a clean chart; the execution line says why. Fees and exact limit percentages come from configuration or the broker; do not state them from memory.

## Lifecycle hand-off

When the user asks for a ticket (固化), follow [ticket-draft.md](ticket-draft.md): the service ledger uses `market` `A`, and the lot size, T+1, and band notes above stay execution facts, not chart verdicts. Placing orders and managing a position go to `$trade-execution`.
