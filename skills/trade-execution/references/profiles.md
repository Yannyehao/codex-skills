# Market profiles

`market` on the ticket (`US` or `A`) names the profile; the service froze it into the ticket when drafted and `state` prints it parsed as `profile` (hash `profile_sha256`). The audit reads lot size and T+N from that `profile`; the facts below describe the service's standard profiles for orientation and are not an override. Optional execution settings live in `config.local.json` under `profiles.us` / `profiles.a`; anything unset is reported as unverified, never filled in from memory.

## U.S. (`US`)

- Whole shares; lot size 1.
- Same-day sale is allowed at the contract level (`min_sessions_before_exit` 0), so a protective stop-limit can be placed right after the fill. Account-level rules (margin, day-trade restrictions) are the broker's; check the broker screen rather than asserting them.
- Currency USD. Fee components named by the service: commission, SEC fee (sell), TAF (sell), other. Rates are not in the skill; fees come from `fee_estimate` and the fill evidence.
- A viewpoint-account ticket (XDV, BNC) follows the cost and pre-clearance rules in `$market-review`'s U.S. profile before it reaches approval.

## A-share (`A`)

- Entry and normal exit quantities are multiples of 100; an odd lot may be sold only when it closes the whole position. Verify any board-specific rule with the broker rather than assuming it.
- **T+1** (`min_sessions_before_exit` 1): shares bought today cannot be sold today, counted on the A-share trading calendar. A same-day protective sell cannot fill; record the real mechanism (a monitored alert or a next-session order), never a live stop that cannot execute. A gap-down at the next open may pass the stop.
- **Price limits:** the service does not validate the band (board and ST dependent). Provide `--prev-close` from the broker screen and `price_limit_pct` in config for the board concerned; the audit then blocks an order limit outside the band and an ask already at limit-up. Without them the band is reported unverified. Limit-down may make a sell unfillable.
- Currency CNY. Fee components: commission, stamp duty (sell), transfer fee; amounts come from `fee_estimate`, fill evidence, or the broker confirmation, not memory. A broker may not offer a native stop-limit; record exactly what order type exists.
- Suspensions and other status flags are execution facts shown on the order screen; they stop execution but do not change a chart verdict.

## Both

Order, fill, and cancel `session_date` must be a trading day of the ticket's market and within a day of `occurred_at`. `tick` (optional config) is checked against the order limit, stop trigger, and stop limit when set.
