#!/usr/bin/env python3
"""Offline CLI: compile one chart-facts JSON file (or `-` for stdin). Exit 0 COMPLETE, 2 BLOCKED,
3 ENTRY_GATE_ONLY, 4 STOP_BASIS_ONLY, 64 usage error. Selectors are never options."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trade_policy_core as core  # noqa: E402

EXIT_CODES = {core.COMPLETE: 0, core.BLOCKED: 2, core.ENTRY_GATE_ONLY: 3, core.STOP_BASIS_ONLY: 4}


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(64, f"{self.prog}: usage error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--facts", required=True)
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.read() if args.facts == "-" else Path(args.facts).read_text(encoding="utf-8-sig")
        result = core.compile_policy(json.loads(text))
    except (OSError, ValueError, RecursionError) as exc:
        result = core.blocked_result("FACTS_UNREADABLE", f"cannot read JSON facts: {exc}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_CODES[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
