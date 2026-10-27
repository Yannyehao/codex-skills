---
name: us-market-review
description: Explicit-only compatibility alias for the legacy $us-market-review command. Delegates entirely to $market-review with the U.S. profile; generic phrases such as 美股复盘 route to market-review, not here.
---

# U.S. market review (compatibility alias)

Use only when the user invokes `$us-market-review` explicitly. Load and follow `$market-review` with the U.S. profile, and do the whole review through it. Resolve it from the available Skills catalog, or from the sibling `../market-review/SKILL.md` when installed together.

**Dependency:** this alias requires `market-review`, installed from this same repository (`scripts/install.ps1` installs both). If it is unavailable, say it must be installed; do not review from memory or substitute a copy of its rules.

This alias holds no review contract, script, or ledger logic of its own. Its legacy `config.local.json`, if present, remains the U.S. profile configuration that `market-review` falls back to when it has no local config; do not read, copy, or rewrite it here beyond what `market-review` itself does.
