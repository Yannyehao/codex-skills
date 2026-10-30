#!/usr/bin/env python3
"""Canonical stop policy zge-stop-v1 for ticket drafting (references/strategy-stop-playbook.md).

Pure and offline: no database, network, broker, clock, chart, or file access. The review selects one
canonical `trade_type`; it alone determines the stop basis kind, activation, broker mode and the
holding/time exits. The caller supplies only the chart-derived `basis_level` (decimal TEXT) and the
chart `evidence`; this script never reads or derives a price from a chart. Regime, position state,
template ids, basis kinds, activations and broker modes are not inputs and are never choices.
Unsupported input is BLOCKED and emits no `stop_semantics`.

  python -X utf8 stop_template.py --trade-type B2_RISEN_PULLBACK --basis-level 10.25 \
      --evidence "<chart reading>"
  python -X utf8 stop_template.py --list-trade-types

Exit 0 = OK (JSON fragment on stdout), 2 = BLOCKED (JSON with errors), 64 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

POLICY = "zge-stop-v1"
MARKER_TYPE_KEY = "canonical_trade_type"
MARKER_POLICY_KEY = "policy"
PRICE_DP = 4
# Persisted shape; must equal trade-execution/scripts/audit_ticket.py (checked by the tests).
STOP_KEYS = ("basis", "activation", "broker_implementation")

CLOSE_RULE = ("Act only if the regular-session close is beyond {level}; an intraday print through it is "
              "not a violation. No live intraday stop is placed at this level.")
HARD_RULE = "Any trade through {level} during the session exits; implement as a live protective stop-limit."
CLOSE_HOLD = ("Hold while closes stay at or above {level}; set a close-based alert and exit manually after "
              "the close if it triggers.")
CLOSE_PROCEDURE = ("Human only: set a close-based alert at {level} and, if the regular-session close is "
                   "beyond it, exit manually after the close. No live broker stop.")
HARD_PROCEDURE = "Place a live protective stop-limit at {level} after the entry fill."
NOT_STOPS = ("These are holding/exit rules judged by the human at the stated time. They are not prices "
             "and are never turned into a stop level or a live broker order.")

SRC_META = "2026-04-22 close-vs-intraday meta-rule"

# Separate non-price rule attached to every trade type; never a structural stop.
PROFIT_TO_LOSS = ("PROFIT_TO_LOSS_INTRADAY", "STATE",
                  "Only a position that was already profitable and turns into a loss is an intraday exit; "
                  "this is a holding rule, not a structural stop and not a price level.")


def _t(kind, activation, broker, sources, invalidation, holding, rules=()):
    return {"basis_kind": kind, "activation": activation, "broker_mode": broker,
            "sources": sources + (SRC_META,), "invalidation": invalidation, "holding": holding,
            "exit_rules": tuple(rules) + (PROFIT_TO_LOSS,)}


TRADE_TYPES: dict[str, dict[str, Any]] = {
    "B1_KLINE_REVERSAL": _t(
        "ENTRY_CANDLE_LOW", "CLOSE_CONFIRM", "HUMAN_ONLY_ALERT",
        ("2025-05-07 B1 stop below the entry K low (2-3 ticks / 1-2%, lose only one K)",
         "2025-10-06 B1 recover-and-rise within three sessions"),
        "B1 K-line reversal is invalidated when the regular-session close is below the entry-candle low "
        "{level}. " + CLOSE_RULE,
        CLOSE_HOLD,
        (("B1_THREE_SESSION_RECOVERY", "TIME",
          "If the position has not recovered and risen within three sessions of entry, exit manually."),)),
    "B1_WHITE_LINE_SHORT": _t(
        "WHITE_LINE", "CLOSE_CONFIRM", "HUMAN_ONLY_ALERT",
        ("2026-02-11 short-term B1 stop at the white line",
         "2026-04-22 white-line B1 is the cautious variant"),
        "White-line short B1 is invalidated when the regular-session close is below the white line "
        "{level}. It is its own trade type, not a fallback of another. " + CLOSE_RULE,
        CLOSE_HOLD),
    "B1_YELLOW_LINE_SWING": _t(
        "YELLOW_LINE", "CLOSE_CONFIRM", "HUMAN_ONLY_ALERT",
        ("2026-02-11 swing B1 stop at the yellow line; yellow is the last support",),
        "Yellow-line swing B1 is invalidated when the regular-session close is below the yellow line "
        "{level}, the last support. " + CLOSE_RULE,
        CLOSE_HOLD,
        (("YELLOW_SUPPORT_SECOND_SESSION_CONFIRM", "STATE",
          "Yellow is the last support: the second session must confirm that resistance is overcome; "
          "judge it by the human at the stated time."),)),
    "B2_FRESH_CONFIRMATION": _t(
        "PRIOR_B1_N_LOW", "CLOSE_CONFIRM", "HUMAN_ONLY_ALERT",
        ("2025-10-06 B2 stop at the prior B1/N low with a two-session explosion requirement",),
        "Fresh B2 confirmation is invalidated when the regular-session close is below the prior B1/N low "
        "{level}. " + CLOSE_RULE,
        CLOSE_HOLD,
        (("B2_TWO_SESSION_EXPLOSION", "TIME",
          "A fresh B2 must explode within two sessions of entry; if it has not, exit manually."),)),
    "B2_RISEN_PULLBACK": _t(
        "PRIOR_B1_N_LOW", "CLOSE_CONFIRM", "HUMAN_ONLY_ALERT",
        ("2026-01-21 risen-B2 pullback with no fresh two-session clock; prior N low intact, no S1",),
        "Risen B2 pullback is invalidated when the regular-session close is below the prior B1/N low "
        "{level}. " + CLOSE_RULE,
        CLOSE_HOLD,
        (("B2_RISEN_STRUCTURE_HOLD", "STATE",
          "No fresh two-session clock applies. Hold only while the prior N low is intact and no S1 has "
          "appeared; judge it by the human at the stated time."),)),
    "BRICK_ZERO_DAY": _t(
        "ENTRY_CANDLE_LOW", "INTRADAY_HARD", "LIVE_STOP_LIMIT",
        ("2026-02-20 brick entry-K low, two-bar gamble",
         "2026-03-29 brick state and next-open rule"),
        "Brick zero-day disaster stop (price only) at the entry-candle low {level}. " + HARD_RULE,
        "A brick must show strength at the next open; the price stop alone does not decide the hold.",
        (("BRICK_NEXT_OPEN_NO_EXPLOSION", "TIME",
          "If the stock does not lift after the next session's open, exit by manual order even though "
          "the price stop was not touched. The course leaves the check time unresolved between 9:33 "
          "and 9:37 (2026-02-20); no single time is fixed."),
         ("BRICK_RED_TO_GREEN", "STATE",
          "Later version (2026-03-29): trust a brick turning from red to green as a state exit signal "
          "for a brick-origin entry. The early version (2026-02-20) did not treat it as an exit."))),
}

DECIMAL_RE = re.compile(r"^\d+(\.\d+)?$")


def _level(value: Any) -> str | None:
    if not isinstance(value, str) or not DECIMAL_RE.match(value.strip()):
        return None
    try:
        parsed = Decimal(value.strip())
    except InvalidOperation:
        return None
    if parsed <= 0 or -parsed.normalize().as_tuple().exponent > PRICE_DP:
        return None
    return value.strip()


def _text(value: Any) -> str | None:
    return " ".join(value.split()) if isinstance(value, str) and value.strip() else None


def marker(trade_type: str) -> str:
    """The exact machine-checkable marker audited by trade-execution/scripts/audit_ticket.py."""
    return f"{MARKER_TYPE_KEY}={trade_type}; {MARKER_POLICY_KEY}={POLICY}"


def select(trade_type: Any, basis_level: Any, evidence: Any) -> dict[str, Any]:
    """Return {"status": "OK", ...fragment} or {"status": "BLOCKED", "errors": [...]}. Never raises."""
    errors: list[str] = []
    spec = TRADE_TYPES.get(trade_type) if isinstance(trade_type, str) else None
    if spec is None:
        errors.append(f"trade_type {trade_type!r} is required and must be exactly one of "
                      f"{sorted(TRADE_TYPES)}; there is no default and no combined or generic type")
    level, note = _level(basis_level), _text(evidence)
    if level is None:
        errors.append(f"basis_level must be positive decimal TEXT with at most {PRICE_DP} places, "
                      f"supplied by the caller; got {basis_level!r}")
    if note is None:
        errors.append("evidence must be non-empty text from this review's chart reading")
    elif f"{MARKER_TYPE_KEY}=" in note or f"{MARKER_POLICY_KEY}=" in note:
        errors.append("evidence must not contain a policy marker; the helper writes it")
    if errors or spec is None or level is None or note is None:
        return {"status": "BLOCKED", "errors": errors,
                "note": "No stop_semantics emitted. Ask the user for the missing or contradictory item "
                        "and write nothing."}
    source_ref = "; ".join(spec["sources"])
    invalidation = spec["invalidation"].format(level=level)
    holding = spec["holding"].format(level=level)
    rules = [{"id": i, "kind": k, "is_price_stop": False, "text": x} for i, k, x in spec["exit_rules"]]
    live = spec["activation"] == "INTRADAY_HARD"
    procedure = (HARD_PROCEDURE if live else CLOSE_PROCEDURE).format(level=level)
    clause = (f"STOP PLAN {trade_type} ({POLICY}): {invalidation} HOLDING: {holding} "
              "EXIT RULES (not price stops): " + " ".join(f"[{r['id']}] {r['text']}" for r in rules))
    return {
        "status": "OK",
        "policy": POLICY,
        "trade_type": trade_type,
        "source_ref": source_ref,
        "stop_semantics": {
            "basis": {"kind": spec["basis_kind"], "level": level,
                      "evidence": f"{marker(trade_type)} | {note} | source {source_ref}"},
            "activation": spec["activation"],
            "broker_implementation": procedure},
        "live_broker_stop": live,
        "draft_text": {"invalidation": invalidation, "holding": holding, "trigger_text_append": clause},
        "holding_exit_rules": rules,
        "holding_exit_rules_note": NOT_STOPS,
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # usage errors exit 64, never 2 (2 means BLOCKED)
        self.print_usage(sys.stderr)
        self.exit(64, f"{self.prog}: usage error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                     allow_abbrev=False)
    parser.add_argument("--list-trade-types", action="store_true")
    for name in ("trade-type", "basis-level", "evidence"):
        parser.add_argument(f"--{name}")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.list_trade_types:
        if args.trade_type is not None or args.basis_level is not None or args.evidence is not None:
            parser.error("--list-trade-types takes no other option")
        listing = {k: {"basis_kind": v["basis_kind"], "activation": v["activation"],
                       "broker_mode": v["broker_mode"], "sources": list(v["sources"]),
                       "exit_rules": [r[0] for r in v["exit_rules"]]} for k, v in TRADE_TYPES.items()}
        print(json.dumps({"policy": POLICY, "trade_types": listing}, ensure_ascii=False, indent=2))
        return 0
    result = select(args.trade_type, args.basis_level, args.evidence)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "OK" else 2


if __name__ == "__main__":
    sys.exit(main())
