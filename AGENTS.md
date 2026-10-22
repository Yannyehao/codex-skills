# Repository workflow

This repository is the source of truth for personally authored reusable Skills. Maintain them under `skills/<skill-name>/`; install copies with `scripts/install.ps1`. Do not copy third-party or system Skills here without an explicit request.

Keep PLAN.md, DEVLOG.md, and README.md current. Validate changed Skills with the system skill-creator validator, install them, compare source and installed files, then commit and push meaningful changes. Do not claim a push succeeded without checking the remote.

This repository is public. Keep private database targets in ignored `config.local.json` files. Do not commit tokens, database snapshots, ingestion batch originals, audit records, or machine-specific paths. Preserve local configuration during installation.

Language conversation Skills delegate approved Lexicon ingestion to lexicon-ingest. Do not duplicate its counting or mutation workflow. Creating or testing a Skill does not authorize live vocabulary writes.
