#!/usr/bin/env python3
"""Deterministic stop-template selector for ticket drafting (references/strategy-stop-playbook.md).

Pure and offline: no database, network, broker, clock, chart, or file access. Every selector is
explicit and there is no default template; unsupported or contradictory input is BLOCKED and emits no
`stop_semantics`. The level is decimal TEXT supplied by the caller from the human's chart reading; this script never reads
or derives a price from a chart.

  python -X utf8 stop_template.py --setup B2 --position-state FRESH_UNFLOWN --regime TIGHT \
      --template-id B2_TIGHT_ENTRY_LOW_INTRADAY_HARD --basis-kind ENTRY_CANDLE_LOW --basis-level 10.25 \
      --evidence "<chart reading>" --broker-mode LIVE_STOP_LIMIT [--broker-implementation "<human text>"]
  python -X utf8 stop_template.py --list-templates

Exit 0 = OK (JSON fragment on stdout), 2 = BLOCKED (JSON with errors), 64 = usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any

SETUPS = ("B1", "B2", "BRICK")
POSITION_STATES = ("FRESH_UNFLOWN", "FLOWN", "ALREADY_RISEN")
REGIMES = ("TIGHT", "LOOSE")
BROKER_MODES = ("LIVE_STOP_LIMIT", "HUMAN_ONLY_ALERT")
PRICE_DP = 4
# Persisted shape; must equal trade-execution/scripts/audit_ticket.py (checked by the tests).
STOP_KEYS = ("basis", "activation", "broker_implementation")

CLOSE_RULE = ("Act only if the regular-session close is beyond {level}; an intraday print through it is "
              "not a violation. No live intraday stop is placed at this level.")
HARD_RULE = "Any trade through {level} during the session exits; implement as a live protective stop-limit."
NOT_STOPS = ("These are holding/exit rules judged by the human at the stated time. They are not prices "
             "and are never turned into a stop level or a live broker order. Trend, N, volume and MACD gates are "
             "checked elsewhere; the regime alone neither allows nor vetoes them.")

SRC_B1 = "2025-11-12 B1 fresh entry candle vs flown wider N/white-line"
SRC_YELLOW = "2025-12-03 / 2026-01-21 yellow-line structural stop alternative for B1/B2"
SRC_B2 = "2025-10-06 B2 prior B1/N low and two-session rule"
SRC_B2_LOW = "2025-10-06 B2 prior B1/N low"
SRC_B2_TIGHT = "2026-01-14 / 2026-01-07 B2 tight entry-low intraday variant"
SRC_RISEN = "2026-01-21 already-risen B2 pullback rule"
SRC_BRICK = "2026-03-18 brick next-open no-rise and red->green / four-brick rules"
SRC_REGIME = "2025-11-26 tight/loose regime context"
SRC_META = "2026-04-22 close-vs-intraday meta-rule"


def _t(setup, states, regimes, kinds, activation, broker, sources, invalidation, holding, rules=()):
    return {"setup": setup, "position_states": states, "regimes": regimes, "basis_kinds": kinds,
            "activation": activation, "broker_mode": broker, "sources": sources,
            "invalidation": invalidation, "holding": holding, "exit_rules": rules}


TEMPLATES: dict[str, dict[str, Any]] = {
    "B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM": _t(
        "B1", ("FRESH_UNFLOWN",), ("TIGHT", "LOOSE"), ("ENTRY_CANDLE_LOW",), "CLOSE_CONFIRM",
        "HUMAN_ONLY_ALERT",
        (SRC_B1, SRC_REGIME, SRC_META),
        "Fresh B1 is invalidated when the regular-session close is below the entry-candle low {level}. "
        + CLOSE_RULE,
        "Hold while closes stay at or above {level}; set a close-based alert and exit manually after the "
        "close if it triggers."),
    "B1_FRESH_ENTRY_LOW_INTRADAY_HARD": _t(
        "B1", ("FRESH_UNFLOWN",), ("TIGHT",), ("ENTRY_CANDLE_LOW",), "INTRADAY_HARD",
        "LIVE_STOP_LIMIT", (SRC_B1, SRC_REGIME, SRC_META),
        "Explicit hand-tight override (TIGHT regime only; not the normal B1 stop): fresh B1 is invalidated by any trade through the entry-candle "
        "low {level}. " + HARD_RULE,
        "Hold only while price stays above {level} intraday; the live stop-limit does the exit."),
    "B1_FLOWN_N_LOW_WHITE_LINE_CLOSE_CONFIRM": _t(
        "B1", ("FLOWN",), ("TIGHT", "LOOSE"), ("PRIOR_B1_N_LOW", "WHITE_LINE"), "CLOSE_CONFIRM",
        "HUMAN_ONLY_ALERT",
        (SRC_B1, SRC_REGIME, SRC_META),
        "Flown B1 uses the wider prior N-low or white-line level {level}; it is not valid for a fresh "
        "unflown entry. " + CLOSE_RULE,
        "Hold while closes stay at or above {level}; set a close-based alert and exit manually after the "
        "close if it triggers."),
    "B1_FLOWN_YELLOW_LINE_CLOSE_CONFIRM": _t(
        "B1", ("FLOWN",), ("TIGHT", "LOOSE"), ("YELLOW_LINE",), "CLOSE_CONFIRM", "HUMAN_ONLY_ALERT",
        (SRC_B1, SRC_YELLOW, SRC_REGIME, SRC_META),
        "Flown B1 explicit yellow-line structural stop at {level}; an alternative to the N-low/white-line "
        "template, chosen by the human, never a default. " + CLOSE_RULE,
        "Hold while closes stay at or above {level}; set a close-based alert and exit manually after the "
        "close if it triggers."),
    "B2_FRESH_PRIOR_LOW_TWO_SESSION_CLOSE_CONFIRM": _t(
        "B2", ("FRESH_UNFLOWN",), ("LOOSE",), ("PRIOR_B1_N_LOW",), "CLOSE_CONFIRM",
        "HUMAN_ONLY_ALERT", (SRC_B2, SRC_REGIME, SRC_META),
        "Fresh B2 structural stop at the prior B1/N low {level}. " + CLOSE_RULE,
        "Hold while closes stay at or above {level}; set a close-based alert and exit manually after the "
        "close if it triggers. A fresh B2 entry also carries the two-session failure-to-explode clock: "
        "apply the two-session rule of the cited course date as the human has confirmed it."),
    "B2_RISEN_PRIOR_LOW_CLOSE_CONFIRM": _t(
        "B2", ("ALREADY_RISEN",), ("LOOSE",), ("PRIOR_B1_N_LOW",), "CLOSE_CONFIRM",
        "HUMAN_ONLY_ALERT", (SRC_B2_LOW, SRC_RISEN, SRC_REGIME, SRC_META),
        "Already-risen B2 pullback structural stop at the prior B1/N low {level}. " + CLOSE_RULE,
        "Hold while closes stay at or above {level} and the human-stated no-S1 context still holds; set a "
        "close-based alert and exit manually after the close if it triggers. The fresh-entry two-session "
        "failure-to-explode exit does not apply to an already-risen B2 pullback."),
    "B2_TIGHT_ENTRY_LOW_INTRADAY_HARD": _t(
        "B2", ("FRESH_UNFLOWN",), ("TIGHT",), ("ENTRY_CANDLE_LOW",), "INTRADAY_HARD", "LIVE_STOP_LIMIT",
        (SRC_B2_TIGHT, SRC_REGIME, SRC_META),
        "Tight B2 variant: invalidated by any trade through the entry-candle low {level}. " + HARD_RULE,
        "Hold only while price stays above {level} intraday; the live stop-limit does the exit."),
    "B2_KEY_K_PLATFORM_CLOSE_CONFIRM": _t(
        "B2", ("FRESH_UNFLOWN", "ALREADY_RISEN"), ("LOOSE",), ("KEY_K_OR_PLATFORM",), "CLOSE_CONFIRM",
        "HUMAN_ONLY_ALERT", (SRC_B2, SRC_RISEN, SRC_REGIME, SRC_META),
        "B2 key-candle/platform stop at {level}. " + CLOSE_RULE,
        "Hold while closes stay at or above {level}; set a close-based alert and exit manually after the "
        "close if it triggers."),
    "B2_YELLOW_LINE_CLOSE_CONFIRM": _t(
        "B2", ("FRESH_UNFLOWN", "ALREADY_RISEN"), ("LOOSE",), ("YELLOW_LINE",), "CLOSE_CONFIRM",
        "HUMAN_ONLY_ALERT", (SRC_B2, SRC_YELLOW, SRC_REGIME, SRC_META),
        "B2 explicit yellow-line structural stop at {level}; an alternative to the prior-low and "
        "key-K/platform templates, chosen by the human, never a default. " + CLOSE_RULE,
        "Hold while closes stay at or above {level}; set a close-based alert and exit manually after the "
        "close if it triggers."),
    "BRICK_FRESH_FAILURE_DISASTER": _t(
        "BRICK", ("FRESH_UNFLOWN",), ("TIGHT", "LOOSE"), ("ENTRY_CANDLE_LOW", "KEY_K_OR_PLATFORM"),
        "INTRADAY_HARD", "LIVE_STOP_LIMIT", (SRC_BRICK, SRC_REGIME, SRC_META),
        "Brick disaster stop (price only) at {level}. " + HARD_RULE,
        "A fresh brick must show strength at the next open; the price stop alone does not decide the hold.",
        (("BRICK_NEXT_OPEN_NO_EXPLOSION", "TIME",
          "If the stock does not rise/explode after the next session's open, exit by manual order even "
          "though the price stop was not touched."),)),
    "BRICK_MATURE_DISASTER": _t(
        "BRICK", ("FLOWN", "ALREADY_RISEN"), ("TIGHT", "LOOSE"), ("ENTRY_CANDLE_LOW", "KEY_K_OR_PLATFORM"),
        "INTRADAY_HARD", "LIVE_STOP_LIMIT", (SRC_BRICK, SRC_REGIME, SRC_META),
        "Brick disaster stop (price only) at {level}. " + HARD_RULE,
        "A mature brick is held by its brick state, not by the price stop alone.",
        (("BRICK_RED_TO_GREEN", "STATE", "A brick turning from red to green is a state exit signal."),
         ("BRICK_FOUR_RED_BRICKS", "STATE", "Four red bricks is a state exit signal."),
         ("BRICK_LAST_THREE_MINUTES", "TIME",
          "On A-share, decide a state exit in the last three minutes of the session (the closing "
          "call-auction window, 14:57-15:00); check the broker's cancel rules for that window."))),
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


def select(setup: Any, position_state: Any, regime: Any, template_id: Any, basis_kind: Any,
           basis_level: Any, evidence: Any, broker_mode: Any, broker_implementation: Any) -> dict[str, Any]:
    """Return {"status": "OK", ...fragment} or {"status": "BLOCKED", "errors": [...]}. Never raises."""
    errors: list[str] = []

    def need(name: str, value: Any, allowed: tuple[str, ...]) -> bool:
        if value not in allowed:
            errors.append(f"{name} {value!r} must be exactly one of {list(allowed)}")
            return False
        return True

    ok = [need("setup", setup, SETUPS), need("position_state", position_state, POSITION_STATES),
          need("regime", regime, REGIMES), need("broker_mode", broker_mode, BROKER_MODES)]
    template = TEMPLATES.get(template_id) if isinstance(template_id, str) else None
    if template is None:
        errors.append(f"template_id {template_id!r} is required and must be one of {sorted(TEMPLATES)}; "
                      "there is no default")
    level, note, impl = _level(basis_level), _text(evidence), _text(broker_implementation)
    if level is None:
        errors.append(f"basis_level must be positive decimal TEXT with at most {PRICE_DP} places, "
                      f"supplied by the caller; got {basis_level!r}")
    if note is None:
        errors.append("evidence must be non-empty text from this review's chart reading")
    hard = template is not None and template["activation"] == "INTRADAY_HARD"
    if impl is None and (broker_implementation is not None or not hard):
        errors.append("broker_implementation must be non-empty text stating how the human implements it"
                      + ("" if template is None or not hard else " (optional for INTRADAY_HARD, "
                         "but never empty when given)"))
    if template is not None:
        if ok[0] and setup != template["setup"]:
            errors.append(f"template {template_id} is for setup {template['setup']}, not {setup}")
        if ok[1] and position_state not in template["position_states"]:
            errors.append(f"template {template_id} does not allow position_state {position_state}; "
                          f"allowed {list(template['position_states'])}")
        if ok[2] and regime not in template["regimes"]:
            errors.append(f"template {template_id} does not allow regime {regime}; "
                          f"allowed {list(template['regimes'])}")
        if basis_kind not in template["basis_kinds"]:
            errors.append(f"basis_kind {basis_kind!r} is not allowed for {template_id}; "
                          f"allowed {list(template['basis_kinds'])}")
        if ok[3] and broker_mode != template["broker_mode"]:
            errors.append(f"broker_mode {broker_mode} is incompatible with activation "
                          f"{template['activation']}; this template needs {template['broker_mode']}")
    if errors or template is None or level is None or note is None:
        return {"status": "BLOCKED", "errors": errors,
                "note": "No stop_semantics emitted. Ask the user for the missing or contradictory item "
                        "and write nothing."}
    source_ref = "; ".join(template["sources"])
    fill = {"level": level}
    invalidation = template["invalidation"].format(**fill)
    holding = template["holding"].format(**fill)
    rules = [{"id": i, "kind": k, "is_price_stop": False, "text": x} for i, k, x in template["exit_rules"]]
    clause = f"STOP PLAN {template_id}: {invalidation} HOLDING: {holding}"
    if rules:
        clause += " EXIT RULES (not price stops): " + " ".join(f"[{r['id']}] {r['text']}" for r in rules)
    return {
        "status": "OK",
        "template_id": template_id,
        "selectors": {"setup": setup, "position_state": position_state, "regime": regime,
                      "broker_mode": broker_mode},
        "source_ref": source_ref,
        "stop_semantics": {
            "basis": {"kind": basis_kind, "level": level,
                      "evidence": f"{note} | template {template_id} | source {source_ref}"},
            "activation": template["activation"],
            **({"broker_implementation": impl} if impl is not None else {})},
        "live_broker_stop": template["activation"] == "INTRADAY_HARD",
        "draft_text": {"invalidation": invalidation, "holding": holding, "trigger_text_append": clause},
        "holding_exit_rules": rules,
        "holding_exit_rules_note": NOT_STOPS if rules else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list-templates", action="store_true")
    for name in ("setup", "position-state", "regime", "template-id", "basis-kind", "basis-level",
                 "evidence", "broker-mode", "broker-implementation"):
        parser.add_argument(f"--{name}")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.list_templates:
        listing = {k: {f: v[f] for f in ("setup", "position_states", "regimes", "basis_kinds", "activation",
                                         "broker_mode", "sources")} for k, v in TEMPLATES.items()}
        print(json.dumps(listing, ensure_ascii=False, indent=2))
        return 0
    result = select(args.setup, args.position_state, args.regime, args.template_id, args.basis_kind,
                    args.basis_level, args.evidence, args.broker_mode, args.broker_implementation)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "OK" else 2


if __name__ == "__main__":
    sys.exit(main())
