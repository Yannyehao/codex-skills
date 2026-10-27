# U.S. profile

Adds U.S.-specific facts to [review-contract.md](review-contract.md). Config section: `profiles.us`.

## Artifact gate

The bundled `scripts/audit_review.py --profile us` applies the shared session gate to the zAI nightly bundle. A date's bundle is complete only if all of these exist and agree on the date:

- `zradar/out/us_nightly_report_YYYYMMDD.json` with `complete=true`;
- `zradar/out/us_b1_review_YYYYMMDD.json` with `complete=true`;
- `zradar/out/charts/us_b1/YYYYMMDD/` with a verified capture manifest and no failed captures.

For each B1 review image the audit then requires: the PNG exists; its SHA-256 matches the report and the manifest; `read_evidence` shows an image result for that file; the answer says `image_read=true`; the answer's `image_token` equals the manifest's `render_metadata.check_token`. Non-B1 candidates (搬砖, 单针, and similar) may carry another source's chart; they need the same file, hash, and read-evidence checks but not a B1 review result.

The audit proves integrity, not interpretation: still open the pixels.

## Ledger

The candidate ledger is the configured live database for the current calendar month, queried with full pagination. A symbol selected more than once keeps all its dates.

## Viewpoint-account candidates (XDV / BNC)

When the configured `XDV.TO` and `NA.TO` (the user's BNC) are in scope, keep them in a separate "观点仓候选" section. They never replace the U.S. universe, and XDV is never described as cash parking.

Read the latest daily and weekly bars, volume, and KDJ. Report current price; daily and weekly white/yellow positions; weekly K, D, J and cross state; current-week low; and the effective pit edge and pit bottom.

Only Friday's completed bar confirms a weekly cross; during the week call it projected or provisional.

When a stable pit is identifiable, `first target = 2 × pit edge − pit bottom`, with about 5% artistic tolerance. A prior high that is also the pit edge is a breakout/retest observation level, not an automatic exit. Do not invent a second target. If the pit is unstable or its edge/bottom cannot be identified reliably, write `暂不出目标价`.

For an executable weekly signal, standard stop = signal-week low − 2%; also show the sensitivity at the signal-week low. Compute per-share risk = entry − stop, reward = first target − entry, reward/risk = reward / risk. Near 1:1 or lower is not worth it; below 3:1 is not a z哥-style high-reward/risk opportunity. Recalculate after a fast confirmation rally; "确认但不追" requires price already too close to the target or a stop too far for adequate odds, not merely proximity to the pit edge.

XDV and BNC share one CAD 20,000 viewpoint-account opportunity pool. BNC's maximum planned allocation is CAD 15,000; the other CAD 5,000 stays flexible cash. XDV is one possible use of that cash, not a default allocation. No fixed tranches, no averaging down because price fell, no buying merely to fill the allocation.

Only after an independent qualified signal may a ticket be discussed: zero commission, integer shares, combined cost at most CAD 20,000, with actual contemporaneous entry/stop/target inputs. Before a BNC ticket, remind the user to check employee personal-trading pre-clearance or blackout restrictions.

After entry the question becomes holding the second half: price still on the white line/BBI, pit-edge breakout/retest valid, distance to the first target, volume health, and invalidation signs (high-volume kill candle, huge-volume bearish candle, two consecutive closes below BBI). Reaching an old high alone is not an exit. Hand holding and order management to `$trade-execution`.
