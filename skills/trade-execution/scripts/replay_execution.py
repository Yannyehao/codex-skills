#!/usr/bin/env python3
"""Offline historical execution replay; never reads or writes the lifecycle service.

The replay has two explicit phases so future bars cannot leak into the decision:

  prepare --plan plan.json --output journal.json
  advance --journal journal.json --event open.json --output journal-open.json
  advance --journal journal-open.json --event close.json --output journal-close.json

All outputs are labelled REPLAY and are deterministic functions of their input files.  The caller
must keep them outside production data directories.  This module imports the canonical
``zge-stop-v1`` selector from the sibling market-review skill; it does not copy or reinterpret the
policy and has no database, network, broker, or lifecycle-service code.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

SCHEMA = "trade-execution-replay-v1"
JOURNAL_SCHEMA = "trade-execution-replay-journal-v1"
EVENT_SCHEMA = "trade-execution-replay-event-v1"
STAGES = ("PREPARED", "OPEN_REVEALED", "CLOSE_REVEALED")
MARKETS = ("US", "A")
EXECUTION_MODES = ("MARKETABLE_LIMIT", "PASSIVE_LIMIT")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DECIMAL = re.compile(r"^\d+(?:\.\d+)?$")

PLAN_KEYS = {
    "schema", "mode", "market", "symbol", "decision_cutoff", "execution_date",
    "source", "simulation_approval", "trade_type", "basis_level", "basis_evidence",
    "execution_mode", "entry_planned", "entry_max", "quantity", "stop_limit",
    "target", "fee_estimate", "risk_budget", "assume_fill_if_eligible", "evidence",
}
APPROVAL_KEYS = {"approved_by", "approved_at", "note"}
EVIDENCE_KEYS = {"role", "kind", "path", "sha256", "last_bar_date"}
SOURCE_KEYS = {"kind", "reference", "decision_statement"}
COMMON_EVENT_KEYS = {"schema", "mode", "replay_id", "stage", "session_date", "evidence"}
OPEN_EVENT_KEYS = COMMON_EVENT_KEYS | {"quote_kind", "bid", "ask", "open"}
CLOSE_EVENT_KEYS = COMMON_EVENT_KEYS | {"open", "high", "low", "close", "volume"}


class ReplayBlocked(ValueError):
    pass


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(payload: dict[str, Any], path: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(text)
    else:
        if path.suffix.lower() != ".json":
            raise ReplayBlocked("--output must end in .json; replay never writes databases or other file types")
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(text)
        except FileExistsError as exc:
            raise ReplayBlocked(f"output already exists and will not be overwritten: {path}") from exc


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _ymd(value: Any, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{8}", value):
        raise ReplayBlocked(f"{name} must be YYYYMMDD")
    try:
        date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError as exc:
        raise ReplayBlocked(f"{name} is not a real date: {value}") from exc
    return value


def _price(value: Any, name: str, *, zero: bool = False) -> Decimal:
    if not isinstance(value, str) or not DECIMAL.fullmatch(value):
        raise ReplayBlocked(f"{name} must be decimal TEXT")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ReplayBlocked(f"{name} is not decimal TEXT") from exc
    if parsed < 0 or (parsed == 0 and not zero) or -parsed.normalize().as_tuple().exponent > 4:
        raise ReplayBlocked(f"{name} must be {'non-negative' if zero else 'positive'} with <= 4 decimals")
    return parsed


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayBlocked(f"{name} must be non-empty text")
    return value.strip()


def _keys(obj: Any, allowed: set[str], name: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ReplayBlocked(f"{name} must be an object")
    extra = set(obj) - allowed
    if extra:
        raise ReplayBlocked(f"{name} has unexpected keys: {sorted(extra)}")
    return obj


def _iso(value: Any, name: str) -> str:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayBlocked(f"{name} must be ISO-8601 with a UTC offset") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReplayBlocked(f"{name} must carry a UTC offset")
    return text


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _evidence(item: Any, *, cutoff: str, role: str) -> dict[str, Any]:
    ev = _keys(item, EVIDENCE_KEYS, "evidence item")
    if ev.get("role") != role:
        raise ReplayBlocked(f"evidence role must be {role!r}")
    _text(ev.get("kind"), "evidence.kind")
    path_text = _text(ev.get("path"), "evidence.path")
    expected = _text(ev.get("sha256"), "evidence.sha256")
    if not HEX64.fullmatch(expected):
        raise ReplayBlocked("evidence.sha256 must be 64 lowercase hex characters")
    path = Path(path_text)
    if not path.is_file():
        raise ReplayBlocked(f"evidence file not found: {path_text}")
    actual = _sha256_file(path)
    if actual != expected:
        raise ReplayBlocked(f"evidence sha256 mismatch for {path_text}")
    last = _ymd(ev.get("last_bar_date"), "evidence.last_bar_date")
    if last > cutoff:
        raise ReplayBlocked(f"future leakage: evidence last_bar_date {last} exceeds cutoff {cutoff}")
    return {"role": role, "kind": ev["kind"], "sha256": actual, "last_bar_date": last,
            "file": path.name}


def _stop_selector() -> Any:
    path = Path(__file__).resolve().parents[2] / "market-review" / "scripts" / "stop_template.py"
    if not path.is_file():
        raise ReplayBlocked("canonical zge-stop-v1 selector is unavailable; install market-review beside trade-execution")
    spec = importlib.util.spec_from_file_location("market_review_stop_template", path)
    if spec is None or spec.loader is None:
        raise ReplayBlocked("cannot load canonical zge-stop-v1 selector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(plan: Any) -> dict[str, Any]:
    plan = _keys(plan, PLAN_KEYS, "plan")
    required = PLAN_KEYS - {"target"}
    missing = required - set(plan)
    if missing:
        raise ReplayBlocked(f"plan is missing required keys: {sorted(missing)}")
    if plan.get("schema") != SCHEMA or plan.get("mode") != "REPLAY":
        raise ReplayBlocked(f"plan must declare schema={SCHEMA!r} and mode='REPLAY'")
    market = plan.get("market")
    if market not in MARKETS:
        raise ReplayBlocked(f"market must be one of {list(MARKETS)}")
    symbol = _text(plan.get("symbol"), "symbol").upper()
    cutoff = _ymd(plan.get("decision_cutoff"), "decision_cutoff")
    execution_date = _ymd(plan.get("execution_date"), "execution_date")
    if execution_date <= cutoff:
        raise ReplayBlocked("execution_date must be after decision_cutoff")

    source = _keys(plan.get("source"), SOURCE_KEYS, "source")
    if set(source) != SOURCE_KEYS:
        raise ReplayBlocked(f"source needs exactly {sorted(SOURCE_KEYS)}")
    for key in SOURCE_KEYS:
        _text(source.get(key), f"source.{key}")
    approval = _keys(plan.get("simulation_approval"), APPROVAL_KEYS, "simulation_approval")
    if set(approval) != APPROVAL_KEYS:
        raise ReplayBlocked(f"simulation_approval needs exactly {sorted(APPROVAL_KEYS)}")
    actor = _text(approval.get("approved_by"), "simulation_approval.approved_by")
    if not actor.startswith("human:") or not actor.partition(":")[2].strip():
        raise ReplayBlocked("simulation_approval.approved_by must be human:<name>")
    _iso(approval.get("approved_at"), "simulation_approval.approved_at")
    _text(approval.get("note"), "simulation_approval.note")

    raw_evidence = plan.get("evidence")
    if not isinstance(raw_evidence, list) or not raw_evidence:
        raise ReplayBlocked("plan needs at least one cutoff_safe evidence item")
    evidence = [_evidence(x, cutoff=cutoff, role="cutoff_safe") for x in raw_evidence]

    trade_type = _text(plan.get("trade_type"), "trade_type")
    basis_level = _text(plan.get("basis_level"), "basis_level")
    basis_evidence = _text(plan.get("basis_evidence"), "basis_evidence")
    stop = _stop_selector().select(trade_type, basis_level, basis_evidence)
    if stop.get("status") != "OK":
        raise ReplayBlocked("canonical stop policy blocked: " + "; ".join(stop.get("errors", [])))

    mode = plan.get("execution_mode")
    if mode not in EXECUTION_MODES:
        raise ReplayBlocked(f"execution_mode must be one of {list(EXECUTION_MODES)}")
    entry = _price(plan.get("entry_planned"), "entry_planned")
    entry_max = _price(plan.get("entry_max"), "entry_max")
    if entry_max < entry:
        raise ReplayBlocked("entry_max must be >= entry_planned")
    if mode == "PASSIVE_LIMIT" and entry_max != entry:
        raise ReplayBlocked("PASSIVE_LIMIT requires entry_max == entry_planned")
    stop_level = _price(basis_level, "basis_level")
    stop_limit = _price(plan.get("stop_limit"), "stop_limit")
    if stop_limit > stop_level or stop_level >= entry:
        raise ReplayBlocked("stop_limit <= basis_level < entry_planned is required")
    target_raw = plan.get("target")
    target = _price(target_raw, "target") if target_raw is not None else None
    if target is not None and target <= entry:
        raise ReplayBlocked("target must be above entry_planned")
    qty = plan.get("quantity")
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        raise ReplayBlocked("quantity must be a positive integer")
    fee = _price(plan.get("fee_estimate"), "fee_estimate", zero=True)
    risk_budget = _price(plan.get("risk_budget"), "risk_budget", zero=True)
    if not isinstance(plan.get("assume_fill_if_eligible"), bool):
        raise ReplayBlocked("assume_fill_if_eligible must be boolean")
    max_loss = ((entry_max - stop_limit) * qty + fee).quantize(Decimal("0.01"), ROUND_HALF_UP)
    if max_loss > risk_budget:
        raise ReplayBlocked(f"max loss {max_loss} exceeds replay risk_budget {risk_budget}")

    normalized = {
        "schema": SCHEMA, "mode": "REPLAY", "market": market, "symbol": symbol,
        "decision_cutoff": cutoff, "execution_date": execution_date, "source": source,
        "simulation_approval": approval, "trade_type": trade_type,
        "stop_policy": {k: stop[k] for k in ("policy", "trade_type", "stop_semantics",
                                               "live_broker_stop", "holding_exit_rules")},
        "execution_mode": mode, "entry_planned": str(entry), "entry_max": str(entry_max),
        "quantity": qty, "stop_limit": str(stop_limit),
        "target": str(target) if target is not None else None, "fee_estimate": str(fee),
        "risk_budget": str(risk_budget), "max_loss_at_entry_max": str(max_loss),
        "assume_fill_if_eligible": plan["assume_fill_if_eligible"], "evidence": evidence,
    }
    replay_id = _hash(normalized)[:32]
    return {
        "schema": JOURNAL_SCHEMA, "mode": "REPLAY", "replay_id": replay_id,
        "stage": "PREPARED", "production_writes": False, "broker_actions": False,
        "plan": normalized, "events": [], "replay_state": {
            "entry": "NOT_EVALUATED", "hypothetical_fill": None,
            "stop": "NOT_EVALUATED", "holding_rules": "NOT_EVALUATED"},
        "warnings": ["REPLAY ONLY: not a lifecycle ticket, broker order, fill, or position."],
    }


def _event_evidence(raw: Any, session: str, stage: str, event: dict[str, Any]) -> dict[str, Any]:
    """Validate a stage-limited JSON snapshot, not a full bar hidden behind a hash.

    This is deliberately stricter than plan evidence.  At OPEN the evidence file itself may contain
    only the open quote fields, so a caller cannot point at an end-of-day bar and claim that the
    close was not visible yet.
    """
    expected_kind = "replay_open_snapshot" if stage == "OPEN" else "replay_close_snapshot"
    if not isinstance(raw, dict) or raw.get("kind") != expected_kind:
        raise ReplayBlocked(f"{stage} evidence.kind must be {expected_kind!r}")
    normalized = _evidence(raw, cutoff=session, role="replay_event")
    path = Path(raw["path"])
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayBlocked(f"{stage} evidence must be a stage-limited UTF-8 JSON snapshot") from exc
    visible = ({"stage", "session_date", "quote_kind", "bid", "ask", "open"}
               if stage == "OPEN" else
               {"stage", "session_date", "open", "high", "low", "close", "volume"})
    if not isinstance(snapshot, dict) or set(snapshot) != visible:
        raise ReplayBlocked(f"future leakage: {stage} evidence JSON needs exactly {sorted(visible)}")
    expected = {key: event[key] for key in visible}
    if snapshot != expected:
        raise ReplayBlocked(f"{stage} evidence JSON does not exactly match the event")
    return normalized


def _number(value: Any, name: str, *, zero: bool = False) -> Decimal:
    return _price(value, name, zero=zero)


def advance(journal: Any, event: Any) -> dict[str, Any]:
    if not isinstance(journal, dict) or journal.get("schema") != JOURNAL_SCHEMA \
            or journal.get("mode") != "REPLAY":
        raise ReplayBlocked("journal is not a replay journal")
    if journal.get("production_writes") is not False or journal.get("broker_actions") is not False:
        raise ReplayBlocked("journal safety flags are missing or unsafe")
    if _hash(journal["plan"])[:32] != journal.get("replay_id"):
        raise ReplayBlocked("journal replay_id does not match its immutable plan")
    event = _keys(event, OPEN_EVENT_KEYS | CLOSE_EVENT_KEYS, "event")
    if event.get("schema") != EVENT_SCHEMA or event.get("mode") != "REPLAY_EVENT":
        raise ReplayBlocked(f"event must declare schema={EVENT_SCHEMA!r} and mode='REPLAY_EVENT'")
    if event.get("replay_id") != journal["replay_id"]:
        raise ReplayBlocked("event replay_id does not match journal")
    stage = event.get("stage")
    current = journal.get("stage")
    expected = "OPEN" if current == "PREPARED" else "CLOSE" if current == "OPEN_REVEALED" else None
    if stage != expected:
        raise ReplayBlocked(f"next event must be {expected!r}; got {stage!r} from journal stage {current!r}")
    allowed = OPEN_EVENT_KEYS if stage == "OPEN" else CLOSE_EVENT_KEYS
    extra = set(event) - allowed
    if extra:
        raise ReplayBlocked(f"future leakage: {stage} event contains unavailable keys {sorted(extra)}")
    required = allowed
    if set(event) != required:
        raise ReplayBlocked(f"{stage} event needs exactly {sorted(required)}")
    session = _ymd(event.get("session_date"), "event.session_date")
    plan = journal["plan"]
    if session != plan["execution_date"]:
        raise ReplayBlocked("event.session_date must equal the replay execution_date")
    evidence = _event_evidence(event.get("evidence"), session, stage, event)
    updated = json.loads(json.dumps(journal))
    recorded = {k: v for k, v in event.items() if k != "evidence"}
    recorded["evidence"] = evidence

    if stage == "OPEN":
        kind = event.get("quote_kind")
        if kind not in ("BROKER_BID_ASK", "OHLC_OPEN_PROXY"):
            raise ReplayBlocked("quote_kind must be BROKER_BID_ASK or OHLC_OPEN_PROXY")
        opened = _number(event.get("open"), "event.open")
        bid = _number(event.get("bid"), "event.bid")
        ask = _number(event.get("ask"), "event.ask")
        if bid > ask:
            raise ReplayBlocked("event.bid must be <= event.ask")
        if kind == "OHLC_OPEN_PROXY" and not (bid == ask == opened):
            raise ReplayBlocked("OHLC_OPEN_PROXY requires bid == ask == open and is labelled approximate")
        limit = Decimal(plan["entry_max"] if plan["execution_mode"] == "MARKETABLE_LIMIT"
                        else plan["entry_planned"])
        eligible = ask <= limit if plan["execution_mode"] == "MARKETABLE_LIMIT" else ask > limit
        state = "ELIGIBLE" if eligible else "BLOCKED_BY_PRICE"
        fill = None
        if eligible and plan["assume_fill_if_eligible"] and plan["execution_mode"] == "MARKETABLE_LIMIT":
            fill = {"price": str(ask), "quantity": plan["quantity"], "assumption": kind}
            state = "HYPOTHETICALLY_FILLED"
        elif eligible and plan["execution_mode"] == "PASSIVE_LIMIT":
            state = "WORKING_PASSIVE_LIMIT"
        updated["replay_state"]["entry"] = state
        updated["replay_state"]["hypothetical_fill"] = fill
        if kind == "OHLC_OPEN_PROXY":
            updated["warnings"].append("Open OHLC is only a quote proxy; no historical spread or actual fill is proven.")
        updated["stage"] = "OPEN_REVEALED"
    else:
        o = _number(event.get("open"), "event.open")
        h = _number(event.get("high"), "event.high")
        lo = _number(event.get("low"), "event.low")
        c = _number(event.get("close"), "event.close")
        volume = event.get("volume")
        if (isinstance(volume, bool) or not isinstance(volume, (int, float))
                or not math.isfinite(volume) or volume < 0):
            raise ReplayBlocked("event.volume must be a non-negative JSON number")
        if not lo <= min(o, c) <= max(o, c) <= h:
            raise ReplayBlocked("OHLC values are inconsistent")
        fill = updated["replay_state"].get("hypothetical_fill")
        if updated["replay_state"]["entry"] == "WORKING_PASSIVE_LIMIT":
            limit = Decimal(plan["entry_planned"])
            if lo <= limit:
                fill = {"price": str(limit), "quantity": plan["quantity"],
                        "assumption": "OHLC_LOW_TOUCHED_LIMIT; sequence and actual fill unproven"}
                updated["replay_state"]["entry"] = "HYPOTHETICALLY_FILLED"
                updated["replay_state"]["hypothetical_fill"] = fill
            else:
                updated["replay_state"]["entry"] = "PASSIVE_LIMIT_NOT_TOUCHED"
        activation = plan["stop_policy"]["stop_semantics"]["activation"]
        level = Decimal(plan["stop_policy"]["stop_semantics"]["basis"]["level"])
        if fill is None:
            stop_state = "NO_HYPOTHETICAL_POSITION"
        elif activation == "CLOSE_CONFIRM":
            stop_state = "EXIT_AFTER_CLOSE" if c < level else "HOLD_CLOSE_ABOVE_LEVEL"
        elif activation == "INTRADAY_HARD":
            stop_state = "TRIGGERED_FILL_UNKNOWN" if lo <= level else "NOT_TRIGGERED"
        else:
            stop_state = "HUMAN_CHECK_REQUIRED"
        updated["replay_state"]["stop"] = stop_state
        updated["replay_state"]["holding_rules"] = {
            "status": "HUMAN_JUDGMENT_REQUIRED",
            "rules": plan["stop_policy"]["holding_exit_rules"],
        }
        updated["stage"] = "CLOSE_REVEALED"
    updated["events"].append(recorded)
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", allow_abbrev=False)
    prep.add_argument("--plan", type=Path, required=True)
    prep.add_argument("--output", type=Path)
    step = sub.add_parser("advance", allow_abbrev=False)
    step.add_argument("--journal", type=Path, required=True)
    step.add_argument("--event", type=Path, required=True)
    step.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = prepare(_load(args.plan)) if args.command == "prepare" \
            else advance(_load(args.journal), _load(args.event))
        _write(result, args.output)
        return 0
    except (OSError, json.JSONDecodeError, ReplayBlocked) as exc:
        blocked = {"schema": JOURNAL_SCHEMA, "mode": "REPLAY", "verdict": "BLOCKED",
                   "production_writes": False, "broker_actions": False,
                   "blockers": [str(exc)]}
        try:
            _write(blocked, args.output)
        except (OSError, ReplayBlocked):
            # The requested destination is unsafe or already exists.  Report on stdout only; a
            # failure path must never turn into an overwrite attempt.
            _write(blocked, None)
        return 2


if __name__ == "__main__":
    sys.exit(main())
