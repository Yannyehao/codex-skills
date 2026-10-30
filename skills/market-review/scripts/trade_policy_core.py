#!/usr/bin/env python3
"""Deterministic trade-policy compiler (references/strategy-stop-playbook.md).

Observable chart facts go in; one of four results comes out:

  COMPLETE         one trade type, one basis, and zge-stop-v1 stop_semantics
  STOP_BASIS_ONLY  a brick stop from a confirmed key K; zge-stop-v1 has no honest label, so no stop_semantics
  ENTRY_GATE_ONLY  a next-open brick with no pre-entry stop: a frozen entry_max only
  BLOCKED          one stable code

Pure: no file, network, database, broker, clock, or chart access. The first failed check blocks, so the
code is deterministic. There is no gap percentage or volume rule.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any

import stop_template as st

COMPLETE, STOP_BASIS_ONLY, ENTRY_GATE_ONLY, BLOCKED = "COMPLETE", "STOP_BASIS_ONLY", "ENTRY_GATE_ONLY", "BLOCKED"
SELECTORS = {"tradetype", "basiskind", "activation", "brokermode", "templateid"}
SIGNAL_CLOSE, NEXT_OPEN = "SIGNAL_CLOSE", "NEXT_OPEN"
NEAR_CLOSE, AFTER_CLOSE = "NEAR_CLOSE", "AFTER_CLOSE"
PRESENT, ABSENT = "PRESENT", "ABSENT"

TOP_KEYS = {"cutoff_date", "cutoff_phase", "observed_families", "states", "entry", "basis_candidates", "evidence"}
ENTRY_KEYS = {"timing", "session_date", "entry_max"}
CANDIDATE_KEYS = {"role", "level", "bar_date", "confirmed_on", "evidence", "confirmation_evidence"}
FAMILY_STATES = {
    "B1": {"reversal_k", "white_line_support", "yellow_line_support"},
    "B2": {"prior_low_intact", "already_risen", "pullback_after_rise", "s1_present"},
    "BRICK": {"first_red_brick"},
}
B1_TYPES = {"reversal_k": "B1_KLINE_REVERSAL", "white_line_support": "B1_WHITE_LINE_SHORT",
            "yellow_line_support": "B1_YELLOW_LINE_SWING"}

BUY, REVERSAL_K, FRACTAL = "BUY_CANDLE_LOW", "CONFIRMED_REVERSAL_K_LOW", "BOTTOM_FRACTAL_LOW"
WHITE, YELLOW, PRIOR_LOW = "WHITE_LINE", "YELLOW_LINE", "PRIOR_B1_N_LOW"
KEY_ROLES = (REVERSAL_K, FRACTAL)
BASIS_ROLES = {
    "B1_KLINE_REVERSAL": (BUY,), "B1_WHITE_LINE_SHORT": (WHITE,), "B1_YELLOW_LINE_SWING": (YELLOW,),
    "B2_FRESH_CONFIRMATION": (PRIOR_LOW,), "B2_RISEN_PULLBACK": (PRIOR_LOW,),
    "BRICK_ZERO_DAY": (BUY, REVERSAL_K, FRACTAL),
}
ALL_ROLES = {role for roles in BASIS_ROLES.values() for role in roles}
BRICK_PROVENANCE = {
    "20260220": "Price basis and time guidance: buy-candle low; next-open lift check, time unresolved 9:33 to 9:37.",
    "20260329": "State guidance: a brick turning red to green is a state exit; the 20260220 version did not use it.",
    "disputed_exits": "Timing and state exits stay manual non-price monitoring, not automatic gates.",
}


class Blocked(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


def blocked_result(code: str, message: str) -> dict[str, Any]:
    return {"status": BLOCKED, "code": code, "message": message, "stop_semantics": None}


def _scan_selectors(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if re.sub(r"[^a-z]", "", str(key).lower()) in SELECTORS:
                raise Blocked("SELECTOR_INPUT_FORBIDDEN", f"{key} is derived, never an input")
            _scan_selectors(item)
    elif isinstance(value, list):
        for item in value:
            _scan_selectors(item)


def _object(value: Any, allowed: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Blocked("FACTS_NOT_OBJECT", f"{name} must be an object")
    if set(value) - allowed:
        raise Blocked("UNKNOWN_FIELD", f"{name} has unknown fields {sorted(set(value) - allowed)}")
    return value


def _date(value: Any, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{8}", value):
        raise Blocked("FACT_VALUE_INVALID", f"{name} must be YYYYMMDD")
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise Blocked("FACT_VALUE_INVALID", f"{name} is not a real date: {value}") from exc
    return value


def _note(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Blocked("REQUIRED_FACT_MISSING", f"{name} must be non-empty text")
    return " ".join(value.split())


def _price(value: Any, name: str) -> str:
    level = st._level(value)
    if level is None:
        raise Blocked("FACT_VALUE_INVALID", f"{name} must be positive decimal TEXT")
    return level


def _classify(facts: dict[str, Any]) -> str:
    families = facts.get("observed_families")
    if not isinstance(families, list) or not families or any(f not in FAMILY_STATES for f in families):
        raise Blocked("CLASSIFICATION_NONE", "observed_families must name B1, B2 or BRICK")
    if len(set(families)) != 1:
        raise Blocked("CLASSIFICATION_AMBIGUOUS", "more than one family observed")
    family, states = families[0], facts.get("states")
    if not isinstance(states, dict) or set(states) != FAMILY_STATES[family]:
        raise Blocked("REQUIRED_FACT_MISSING", f"{family} states need exactly {sorted(FAMILY_STATES[family])}")
    if any(v not in (PRESENT, ABSENT) for v in states.values()):
        raise Blocked("EVIDENCE_AMBIGUOUS", "every state must be observed PRESENT or ABSENT")
    on = {key for key, value in states.items() if value == PRESENT}
    if family == "B1":
        if len(on) != 1:
            raise Blocked("CLASSIFICATION_NONE" if not on else "CLASSIFICATION_AMBIGUOUS",
                          "B1 needs exactly one of reversal K, white-line or yellow-line support")
        return B1_TYPES[on.pop()]
    if family == "BRICK":
        if not on:
            raise Blocked("CLASSIFICATION_NONE", "no first red brick")
        return "BRICK_ZERO_DAY"
    if "prior_low_intact" not in on:
        raise Blocked("B2_PRIOR_LOW_BROKEN", "B2 needs the prior low intact")
    if "s1_present" in on:
        raise Blocked("B2_S1_PRESENT", "S1 is present")
    if "pullback_after_rise" in on and "already_risen" not in on:
        raise Blocked("STATE_CONTRADICTION", "a pullback after rise needs a prior rise")
    if "already_risen" in on and "pullback_after_rise" not in on:
        raise Blocked("CLASSIFICATION_NONE", "risen B2 without a pullback is not an entry type")
    return "B2_RISEN_PULLBACK" if "already_risen" in on else "B2_FRESH_CONFIRMATION"


def _entry(facts: dict[str, Any], cutoff: str) -> dict[str, Any]:
    entry = _object(facts.get("entry"), ENTRY_KEYS, "entry")
    timing, session = entry.get("timing"), _date(entry.get("session_date"), "entry.session_date")
    phase = facts.get("cutoff_phase")
    valid = ((timing == SIGNAL_CLOSE and phase == NEAR_CLOSE and session == cutoff)
             or (timing == NEXT_OPEN and phase == AFTER_CLOSE and session > cutoff))
    if not valid:
        raise Blocked("ENTRY_CUTOFF_MISMATCH", "SIGNAL_CLOSE is NEAR_CLOSE on the cutoff date; "
                      "NEXT_OPEN is AFTER_CLOSE with a later session")
    entry_max = entry.get("entry_max")
    if entry_max is None and timing == NEXT_OPEN:
        raise Blocked("ENTRY_MAX_NOT_FROZEN", "NEXT_OPEN needs entry_max frozen before the open")
    return {"timing": timing, "session_date": session,
            "entry_max": None if entry_max is None else _price(entry_max, "entry.entry_max")}


def _candidate(raw: Any, allowed: tuple[str, ...], cutoff: str, phase: str, entry: dict[str, Any]) -> dict[str, Any]:
    item = _object(raw, CANDIDATE_KEYS, "basis candidate")
    role = item.get("role")
    if role not in ALL_ROLES:
        raise Blocked("BASIS_ROLE_UNKNOWN", f"unknown basis role {role!r}")
    if role not in allowed:
        raise Blocked("BASIS_ROLE_INVALID_FOR_TYPE", f"{role} is not valid here; allowed {list(allowed)}")
    level, bar = _price(item.get("level"), "level"), _date(item.get("bar_date"), "bar_date")
    note = _note(item.get("evidence"), "candidate evidence")
    if bar > cutoff:
        raise Blocked("BASIS_AFTER_CUTOFF", f"{role} bar {bar} is after cutoff {cutoff}")
    if role == BUY and bar != entry["session_date"]:
        raise Blocked("BUY_CANDLE_DATE_MISMATCH", "the buy candle is the entry session's own candle")
    if role == PRIOR_LOW and bar >= entry["session_date"]:
        raise Blocked("BASIS_AFTER_CUTOFF", "the prior low must predate the entry session")
    if role in KEY_ROLES:
        if item.get("confirmed_on") is None or not item.get("confirmation_evidence"):
            raise Blocked("BASIS_CONFIRMATION_MISSING", f"{role} needs confirmed_on and confirmation_evidence")
        confirmed = _date(item["confirmed_on"], "confirmed_on")
        if " ".join(str(item["confirmation_evidence"]).split()) == note:
            raise Blocked("BASIS_CONFIRMATION_MISSING", "confirmation must be independent of the level evidence")
        if confirmed < bar or (role == FRACTAL and confirmed == bar):
            raise Blocked("BOTTOM_FRACTAL_NOT_COMPLETE" if role == FRACTAL else "BASIS_DATES_CONTRADICTORY",
                          f"{role} confirmation date is too early for its bar")
        if confirmed > cutoff or (confirmed == cutoff and phase != AFTER_CLOSE):
            raise Blocked("BASIS_NOT_CONFIRMED_AT_CUTOFF", f"{role} is not confirmed by the cutoff")
    elif item.get("confirmed_on") is not None or item.get("confirmation_evidence") is not None:
        raise Blocked("UNKNOWN_FIELD", f"{role} takes no confirmation fields")
    return {"role": role, "level": level, "bar_date": bar, "evidence": note}


def _basis(trade_type: str, facts: dict[str, Any], cutoff: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    raw = facts.get("basis_candidates")
    if not isinstance(raw, list):
        raise Blocked("REQUIRED_FACT_MISSING", "basis_candidates must be a list")
    found = [_candidate(c, BASIS_ROLES[trade_type], cutoff, facts["cutoff_phase"], entry) for c in raw]
    if len({Decimal(c["level"]) for c in found}) > 1:
        raise Blocked("BASIS_CONFLICT", "candidates disagree on the level")
    found.sort(key=lambda c: (c["role"] != BUY, c["role"], c["bar_date"]))
    needs_stop = trade_type != "BRICK_ZERO_DAY" or entry["timing"] == SIGNAL_CLOSE
    if needs_stop and (not found or (trade_type == "BRICK_ZERO_DAY" and found[0]["role"] != BUY)):
        raise Blocked("BASIS_MISSING", "no valid cutoff-known basis for this type and timing")
    basis = found[0] if found else None
    if basis and entry["entry_max"] and Decimal(basis["level"]) >= Decimal(entry["entry_max"]):
        raise Blocked("BASIS_NOT_BELOW_ENTRY_MAX", "the stop basis must be below entry_max")
    return basis


def compile_policy(facts: Any) -> dict[str, Any]:
    try:
        _scan_selectors(facts)
        facts = _object(facts, TOP_KEYS, "facts")
        cutoff = _date(facts.get("cutoff_date"), "cutoff_date")
        note = _note(facts.get("evidence"), "evidence")
        trade_type = _classify(facts)
        entry = _entry(facts, cutoff)
        basis = _basis(trade_type, facts, cutoff, entry)
        result = {"trade_type": trade_type, "entry": entry, "basis": basis, "policy": st.POLICY,
                  "course_provenance": BRICK_PROVENANCE if trade_type == "BRICK_ZERO_DAY" else None}
        if basis is None:
            return {**result, "status": ENTRY_GATE_ONLY, "stop_semantics": None,
                    "note": "Entry-price gate only: no ticket, stop, or fill. A later bar cannot backfill a stop."}
        if basis["role"] in KEY_ROLES:
            return {**result, "status": STOP_BASIS_ONLY, "stop_semantics": None,
                    "note": "zge-stop-v1 labels the brick basis ENTRY_CANDLE_LOW, so this level cannot render as it."}
        rendered = st.select(trade_type, basis["level"], f"{note} | {basis['role']}: {basis['evidence']}")
        if rendered["status"] != "OK":
            raise Blocked("EVIDENCE_MARKER_FORBIDDEN", "; ".join(rendered["errors"]))
        return {**rendered, **result, "status": COMPLETE}
    except Blocked as exc:
        return blocked_result(exc.code, exc.message)
