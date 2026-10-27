#!/usr/bin/env python3
"""Read-only dry-run audit for an approved trade ticket.

Input is the JSON printed by `python -m zradar.trade_lifecycle state` (schema v6) plus the JSON
printed by `python -m zradar.trade_lifecycle audit --ticket-id <id>`; nothing is renamed or mapped
(see references/ticket-contract.md and references/service-cli.md). The approval terms hash and the
frozen market profile are read from that state (`approval`, `profile`); no hash is ever typed in. This script never opens the
database, never contacts a broker, and never records anything. It fails closed: any missing,
malformed, legacy-shaped, unapproved, expired, or inconsistent input yields verdict BLOCKED and
exit code 2. It contains no dollar, R, or sample-size threshold; every number it enforces was
persisted on the ticket or supplied by the caller's policy.

Subcommands
  pre-submit         approval gate + show the exact entry order form from a fresh broker quote
  protective         approval gate + validate protective stop-limit fields after an entry fill
  check-args         validate an `apply --args-json` file for one allowed service operation
  idempotency-key    derive a stable key for one lifecycle write from its evidence
  scale-up-proposal  verify a `scale-up` result before it may be shown as a proposal
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable

SKILL_ROOT = Path(__file__).resolve().parents[1]

# Controlled vocabularies of lifecycle contract schema v6. Exact match; no case or synonym repair.
MARKETS = ("US", "A")
MODES = ("MARKETABLE_LIMIT", "PASSIVE_LIMIT")
SETUP_QUALITIES = ("A", "VALID", "AMBIGUOUS", "REJECT")
DECISION_LANES = ("A_CIRCLE", "PRACTICE", "AMBIGUOUS", "REJECT")
APPROVABLE_LANES = ("A_CIRCLE", "PRACTICE")
LANE_QUALITY = {"A_CIRCLE": "A", "PRACTICE": "VALID"}
TICKET_STATES = ("DRAFT", "APPROVED", "ORDER_SUBMITTED", "PARTIALLY_FILLED", "POSITION_OPEN",
                 "CLOSED", "CANCELLED", "EXPIRED", "REJECTED", "REVIEWED")
POSITION_STATES = ("PARTIALLY_FILLED", "POSITION_OPEN")
LIVE_ORDER = ("OPEN", "PARTIALLY_FILLED")
VETO_DIMENSIONS = ("n_pattern", "trend", "volume", "macd")
# Keys of the frozen MarketProfile that `state` exposes as `profile`; the audit reads lot size and
# T+N from it, never from a table of its own.
PROFILE_KEYS = ("market", "currency", "lot_size", "min_sessions_before_exit",
                "odd_lot_exit_closes_only", "price_limit", "fee_components", "calendar", "tdx")
APPROVAL_KEYS = ("event_seq", "approved_by", "approved_at", "terms_sha256", "matches_ticket_terms",
                 "note")
STAGE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
YMD_RE = re.compile(r"^\d{8}$")
MONEY_Q = Decimal("0.01")
PRICE_DP = 4

REQUIRED_KEYS = (
    "ticket_id", "market", "symbol", "strategy", "execution_mode", "thesis", "trigger_text",
    "invalidation", "entry_planned", "entry_max", "stop_kind", "stop_trigger", "stop_limit",
    "targets", "expiry_date", "capital_budget", "quantity", "fee_estimate", "risk_amount",
    "max_loss_amount", "reward_amount", "r_multiple", "currency", "setup_quality",
    "decision_lane", "capital_stage", "risk_budget", "min_reward_risk", "profile_sha256",
    "terms_sha256", "profile", "approval", "review", "state", "journal_state", "approved_by",
    "approved_at", "orders", "position", "events")
# Field names of an invented export shape; seeing any of them means this is not service output.
LEGACY_KEYS = ("status", "expires_at", "entry", "protective", "target_price", "risk",
               "portfolio", "constraints", "side")

ENTRY_ORDER_TYPES = {"ENTRY": ("LIMIT",), "PROTECTIVE_STOP": ("STOP_LIMIT",),
                     "TAKE_PROFIT": ("LIMIT",), "MANUAL_EXIT": ("LIMIT", "MARKET")}

# `apply --op` operations this skill may prepare. Keys are the service function's keyword names;
# `ident` is the positional id the CLI takes out of the JSON. Actors follow contract section 3.
OP_SPECS: dict[str, dict[str, Any]] = {
    "submit_order": {
        "ident": "ticket_id", "actor_key": "submitted_by", "actors": ("human",),
        "required": ("order_type", "quantity", "session_date", "submitted_by", "occurred_at",
                     "idempotency_key"),
        "optional": ("role", "limit_price", "stop_trigger", "max_price", "tif", "expiry_date",
                     "broker_ref", "evidence")},
    "attach_stop": {
        "ident": "ticket_id", "actor_key": "submitted_by", "actors": ("human",),
        "required": ("session_date", "submitted_by", "occurred_at", "idempotency_key"),
        "optional": ("expiry_date", "stop_trigger", "stop_limit", "quantity", "broker_ref",
                     "evidence")},
    "amend_order": {
        "ident": "order_id", "actor_key": "amended_by", "actors": ("human",),
        "required": ("session_date", "amended_by", "occurred_at", "reason", "idempotency_key"),
        "optional": ("quantity", "limit_price", "stop_trigger", "max_price", "expiry_date",
                     "evidence")},
    "cancel_order": {
        "ident": "order_id", "actor_key": "recorded_by", "actors": ("human", "import"),
        "required": ("session_date", "recorded_by", "occurred_at", "reason", "idempotency_key"),
        "optional": ("evidence",)},
    "expire_order": {
        "ident": "order_id", "actor_key": "recorded_by", "actors": ("human", "import"),
        "required": ("session_date", "recorded_by", "occurred_at", "reason", "idempotency_key"),
        "optional": ("evidence",)},
    "reject_order": {
        "ident": "order_id", "actor_key": "recorded_by", "actors": ("human", "import"),
        "required": ("session_date", "recorded_by", "occurred_at", "reason", "idempotency_key"),
        "optional": ("evidence",)},
    "record_fill": {
        "ident": "order_id", "actor_key": "recorded_by", "actors": ("human", "import"),
        "required": ("quantity", "price", "session_date", "occurred_at", "recorded_by",
                     "idempotency_key"),
        "optional": ("external_ref", "fee", "evidence")},
    "record_exit_fill": {
        "ident": "order_id", "actor_key": "recorded_by", "actors": ("human", "import"),
        "required": ("quantity", "price", "session_date", "occurred_at", "recorded_by",
                     "idempotency_key"),
        "optional": ("external_ref", "fee", "evidence")},
    "expire_ticket": {
        "ident": "ticket_id", "actor_key": "recorded_by", "actors": ("human",),
        "required": ("as_of_date", "recorded_by", "occurred_at", "idempotency_key"),
        "optional": ()},
    "cancel_ticket": {
        "ident": "ticket_id", "actor_key": "cancelled_by", "actors": ("human",),
        "required": ("cancelled_by", "occurred_at", "reason", "idempotency_key"),
        "optional": ()},
}
FORBIDDEN_OPS = {
    "approve": "approval is the human's own act (human:<name> + human_confirmed + the reviewed "
               "terms_sha256); this skill never prepares or runs it",
    "create_draft": "drafting belongs to $market-review and only on an explicit 固化 instruction",
    "mark_reviewed": "a review conclusion is a human judgment and is not part of execution",
}
PRICE_ARGS = ("limit_price", "stop_trigger", "max_price", "stop_limit", "price")
DATE_ARGS = ("session_date", "expiry_date", "as_of_date")
TEXT_ARGS = ("reason", "broker_ref", "external_ref", "tif", "role", "order_type")
EVENT_OPS = tuple(OP_SPECS)


# ----------------------------------------------------------------------------- helpers


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle, parse_float=Decimal)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def money(value: Decimal) -> str:
    return str(value.quantize(MONEY_Q, rounding=ROUND_HALF_UP))


def money_or_none(value: Decimal | None) -> str | None:
    return None if value is None else money(value)


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def valid_ymd(value: Any) -> bool:
    if not isinstance(value, str) or not YMD_RE.match(value):
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return False
    return True


def text_decimal(value: Any, *, dp: int = PRICE_DP, zero: bool = False) -> Decimal | None:
    """Parse a decimal that the service exports as TEXT. JSON numbers, booleans, junk -> None.

    Mirrors the service: finite, positive (or non-negative with zero=True), at most `dp` places.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = Decimal(value.strip())
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed < 0 or (parsed == 0 and not zero):
        return None
    if -parsed.normalize().as_tuple().exponent > dp:
        return None
    return parsed


class Report:
    def __init__(self) -> None:
        self.blockers: list[str] = []
        self.warnings: list[str] = []

    def block(self, message: str) -> None:
        if message not in self.blockers:
            self.blockers.append(message)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def finish(self, extra: dict[str, Any], ok: str = "READY_FOR_HUMAN_CONFIRMATION") -> dict[str, Any]:
        verdict = "BLOCKED" if self.blockers else ok
        return {"verdict": verdict, "blockers": self.blockers, "warnings": self.warnings, **extra}


def profile_config(config_path: Path | None, market: str) -> dict[str, Any]:
    """Optional execution-fact settings (`tick`, `price_limit_pct`) for one market."""
    path = config_path or (SKILL_ROOT / "config.local.json")
    if not path.is_file():
        return {}
    data = load_json(path)
    section = data.get("profiles", {}).get(market.lower()) if isinstance(data, dict) else None
    return {k: v for k, v in section.items() if v is not None} if isinstance(section, dict) else {}


# --------------------------------------------------------------------- ticket shape/terms


def parse_terms(report: Report, t: Any) -> dict[str, Any] | None:
    """Validate the service `state` export and return parsed Decimals, or None when unusable."""
    if not isinstance(t, dict):
        report.block("ticket is not a JSON object")
        return None
    legacy = [k for k in LEGACY_KEYS if k in t]
    missing = [k for k in REQUIRED_KEYS if k not in t]
    if legacy or missing:
        report.block(
            "not the output of `python -m zradar.trade_lifecycle state` "
            f"(missing keys: {missing or 'none'}; legacy-shaped keys: {legacy or 'none'}); "
            "reload the ticket from the lifecycle service, never from chat or a hand-made export")
        return None
    before = len(report.blockers)

    for key, allowed in (("market", MARKETS), ("execution_mode", MODES),
                         ("setup_quality", SETUP_QUALITIES), ("decision_lane", DECISION_LANES),
                         ("state", TICKET_STATES), ("journal_state", TICKET_STATES)):
        if t[key] not in allowed:
            report.block(f"{key} {t[key]!r} must be exactly one of {list(allowed)}")
    if not isinstance(t["ticket_id"], str) or not t["ticket_id"]:
        report.block("ticket_id is missing")
    profile = check_profile(report, t)
    if not isinstance(t["symbol"], str) or not t["symbol"].strip():
        report.block("symbol is missing")
    stage = t["capital_stage"]
    if stage is not None and not (isinstance(stage, str) and STAGE_RE.match(stage)):
        report.block(f"capital_stage {stage!r} must be an upper-case account label like PRACTICE")
    if not valid_ymd(t["expiry_date"]):
        report.block(f"expiry_date {t['expiry_date']!r} must be YYYYMMDD")
    qty = t["quantity"]
    if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
        report.block("quantity must be a positive integer number of shares")
    elif profile is not None and qty % profile["lot_size"]:
        report.block(f"quantity {qty} is not a multiple of the {t['market']} lot "
                     f"{profile['lot_size']}")

    parsed: dict[str, Any] = {"quantity": qty if isinstance(qty, int) else 0}
    for key in ("entry_planned", "entry_max", "stop_trigger", "stop_limit", "capital_budget",
                "risk_amount", "max_loss_amount", "reward_amount", "r_multiple"):
        parsed[key] = text_decimal(t[key])
        if parsed[key] is None:
            report.block(f"{key} must be a positive decimal TEXT as exported by the service "
                         f"(<= {PRICE_DP} places); got {t[key]!r}")
    parsed["fee_estimate"] = text_decimal(t["fee_estimate"], zero=True)
    if parsed["fee_estimate"] is None:
        report.block(f"fee_estimate must be non-negative decimal TEXT; got {t['fee_estimate']!r}")
    for key, dp in (("risk_budget", 2), ("min_reward_risk", PRICE_DP)):
        if t[key] is None:
            parsed[key] = None
        else:
            parsed[key] = text_decimal(t[key], dp=dp)
            if parsed[key] is None:
                report.block(f"{key} must be positive decimal TEXT (<= {dp} places) or null; "
                             f"got {t[key]!r}")

    targets = t["targets"]
    prices: list[Decimal] = []
    if isinstance(targets, list):
        for item in targets:
            price = text_decimal(item.get("price")) if isinstance(item, dict) else None
            if price is None:
                prices = []
                break
            prices.append(price)
    parsed["targets"] = prices
    if not prices:
        report.block("targets must be a non-empty list of {price: decimal text}")
    elif any(a >= b for a, b in zip(prices, prices[1:])):
        report.block("targets must be strictly ascending")
    for key in ("review", "orders", "events"):
        if not isinstance(t[key], (dict if key == "review" else list)):
            report.block(f"{key} has the wrong type for a service export")
    return parsed if len(report.blockers) == before else None


def profile_sha256(profile: dict[str, Any]) -> str:
    """Service hash of a profile: sha256 of its sorted-key JSON (`MarketProfile.sha256`)."""
    text = json.dumps(profile, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_profile(report: Report, t: dict[str, Any]) -> dict[str, Any] | None:
    """The market profile frozen into the ticket, exactly as `state` prints it."""
    profile = t["profile"]
    if not isinstance(profile, dict) or set(profile) != set(PROFILE_KEYS):
        report.block("profile must be the service's parsed market profile "
                     f"(keys {list(PROFILE_KEYS)}); reload the ticket from `state`")
        return None
    before = len(report.blockers)
    if profile["market"] != t["market"]:
        report.block(f"profile market {profile['market']!r} is not the ticket market {t['market']!r}")
    lot, sessions = profile["lot_size"], profile["min_sessions_before_exit"]
    if isinstance(lot, bool) or not isinstance(lot, int) or lot <= 0:
        report.block("profile.lot_size must be a positive integer")
    if isinstance(sessions, bool) or not isinstance(sessions, int) or sessions < 0:
        report.block("profile.min_sessions_before_exit must be a non-negative integer")
    if not isinstance(profile["odd_lot_exit_closes_only"], bool):
        report.block("profile.odd_lot_exit_closes_only must be a boolean")
    if not (isinstance(t["profile_sha256"], str) and HEX64_RE.match(t["profile_sha256"])):
        report.block("profile_sha256 is not a 64-hex digest")
    elif profile_sha256(profile) != t["profile_sha256"]:
        report.block("profile does not hash to profile_sha256: the frozen profile was altered or is "
                     "not service output")
    return profile if len(report.blockers) == before else None


def lane_gate(report: Report, t: dict[str, Any], p: dict[str, Any]) -> None:
    """Re-run the contract's lane gate on persisted terms. Same rules as the service, no numbers.

    capital_stage is only checked for presence; it never changes setup validity (practice sizes
    down, it does not relabel the setup).
    """
    lane, quality = t["decision_lane"], t["setup_quality"]
    if lane not in APPROVABLE_LANES:
        report.block(f"decision_lane {lane} is never executable (only {list(APPROVABLE_LANES)})")
        return
    if quality != LANE_QUALITY[lane]:
        report.block(f"decision_lane {lane} needs setup_quality {LANE_QUALITY[lane]}, got "
                     f"{quality!r}; a smaller capital stage reduces size, it never relabels a setup")
    for need in ("capital_stage", "risk_budget") + (("min_reward_risk",) if lane == "PRACTICE" else ()):
        if not t[need]:
            report.block(f"decision_lane {lane} needs a persisted {need}")
    if lane == "PRACTICE":
        absent = [k for k in ("strategy", "thesis", "trigger_text", "invalidation")
                  if not str(t[k] or "").strip()]
        if absent or not p["targets"]:
            report.block("PRACTICE needs complete logic (missing "
                         f"{absent + ([] if p['targets'] else ['targets'])})")
        absent = [k for k in ("stop_kind", "stop_trigger", "stop_limit") if not str(t[k] or "").strip()]
        if absent:
            report.block(f"PRACTICE needs an explicit stop (missing {absent})")


def economics(p: dict[str, Any], entry: Decimal) -> dict[str, Decimal | None]:
    """Service formulas (contract 4): risk/reward at `entry`, all amounts HALF_UP to 0.01."""
    qty, fee = Decimal(p["quantity"]), p["fee_estimate"]
    risk = ((entry - p["stop_trigger"]) * qty + fee).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
    reward = ((p["targets"][0] - entry) * qty - fee).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
    ratio = (reward / risk).quantize(MONEY_Q, rounding=ROUND_HALF_UP) if risk > 0 else None
    return {"risk": risk, "reward": reward, "r": ratio}


def check_terms_math(report: Report, t: dict[str, Any], p: dict[str, Any]) -> None:
    e0, e1, st, sl = p["entry_planned"], p["entry_max"], p["stop_trigger"], p["stop_limit"]
    if not sl <= st < e0 <= e1:
        report.block(f"price order must satisfy stop_limit <= stop_trigger < entry_planned <= "
                     f"entry_max (got {sl}, {st}, {e0}, {e1})")
        return
    if not p["targets"][0] > e0:
        report.block(f"first target {p['targets'][0]} must be above entry_planned {e0}")
        return
    if t["execution_mode"] == "PASSIVE_LIMIT" and e1 != e0:
        report.block("PASSIVE_LIMIT is a limit at entry_planned: entry_max must equal it")
    qty, fee = Decimal(p["quantity"]), p["fee_estimate"]
    base = economics(p, e0)
    loss = ((e1 - sl) * qty + fee).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
    worst_cost = (e1 * qty + fee).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
    stored = (p["risk_amount"], p["max_loss_amount"], p["reward_amount"], p["r_multiple"])
    if stored != (base["risk"], loss, base["reward"], base["r"]):
        report.block("stored risk_amount/max_loss_amount/reward_amount/r_multiple do not recompute "
                     "from the stored terms (ticket altered or not a service export)")
    if worst_cost > p["capital_budget"]:
        report.block(f"worst-case cost {worst_cost} (entry_max x qty + fee) exceeds "
                     f"capital_budget {p['capital_budget']}")
    if p["risk_budget"] is not None and loss > p["risk_budget"]:
        report.block(f"max_loss_amount {loss} exceeds risk_budget {p['risk_budget']}")
    if p["min_reward_risk"] is not None and (base["r"] is None or base["r"] < p["min_reward_risk"]):
        report.block(f"r_multiple {money_or_none(base['r'])} is below the persisted "
                     f"min_reward_risk {p['min_reward_risk']}")


def check_veto_review(report: Report, t: dict[str, Any]) -> None:
    if t["execution_mode"] != "MARKETABLE_LIMIT":
        return
    veto = t["review"].get("veto_review")
    if not isinstance(veto, dict):
        report.block("MARKETABLE_LIMIT needs the persisted veto_review (n_pattern, trend, volume, "
                     "macd); it cannot be supplied from chat now")
        return
    vetoed = []
    for dim in VETO_DIMENSIONS:
        item = veto.get(dim)
        if not (isinstance(item, dict) and isinstance(item.get("veto"), bool)
                and str(item.get("evidence") or "").strip()):
            report.block(f"veto_review.{dim} needs {{veto: bool, evidence: text}}")
        elif item["veto"]:
            vetoed.append(dim)
    if vetoed:
        report.block(f"persisted veto_review vetoes {', '.join(vetoed)}: not executable")


def approval_gate(report: Report, t: dict[str, Any], service_audit: Any,
                  allowed_states: tuple[str, ...]) -> None:
    """Human approval linked to these exact terms, read from the persisted service record.

    The approved hash is `state.approval.terms_sha256`, stored with the APPROVED event when the human
    approved. Nothing here comes from chat, and the user is never asked to type a hash: reading the
    record is evidence, not an approval input.
    """
    if t["state"] not in allowed_states:
        report.block(f"ticket state is {t['state']!r}; this step needs {list(allowed_states)}")
    if t["journal_state"] != t["state"]:
        report.block(f"state journal says {t['journal_state']} but facts derive {t['state']}")
    terms_hash = t["terms_sha256"]
    if not (isinstance(terms_hash, str) and HEX64_RE.match(terms_hash)):
        report.block("ticket terms_sha256 is not a 64-hex digest")
    approval = t["approval"]
    if not isinstance(approval, dict) or set(approval) != set(APPROVAL_KEYS):
        report.block("state.approval is missing: no persisted human approval record for this ticket "
                     "(it is never inferred, supplied from chat, or approved here)")
        approval = None
    else:
        approved_hash = approval["terms_sha256"]
        if not (isinstance(approved_hash, str) and HEX64_RE.match(approved_hash)):
            report.block("persisted approval.terms_sha256 is not a 64-hex digest")
        elif approved_hash != terms_hash:
            report.block("persisted approval.terms_sha256 does not match the ticket's terms_sha256: "
                         "the approval was for different terms; draft and approve a new ticket")
        if approval["matches_ticket_terms"] is not True:
            report.block("service says the persisted approval does not match the current terms "
                         "(approval.matches_ticket_terms is not true)")

    approvals = [e for e in t["events"] if isinstance(e, dict) and e.get("event_type") == "APPROVED"]
    actor = approvals[0].get("actor") if len(approvals) == 1 else None
    if len(approvals) != 1:
        report.block(f"expected exactly one APPROVED event, found {len(approvals)}")
    kind, _, name = (actor if isinstance(actor, str) else "").partition(":")
    if len(approvals) == 1 and not (kind == "human" and name.strip()):
        report.block(f"APPROVED event actor {actor!r} is not 'human:<name>'")
    if len(approvals) == 1:
        if t["approved_by"] != actor:
            report.block(f"approved_by {t['approved_by']!r} differs from the APPROVED event actor")
        if t["approved_at"] != approvals[0].get("occurred_at") or not parse_time(t["approved_at"]):
            report.block("approved_at is missing, naive, or differs from the APPROVED event")
        if approval is not None and (approval["approved_by"] != actor
                                     or approval["approved_at"] != approvals[0].get("occurred_at")
                                     or approval["event_seq"] != approvals[0].get("seq")):
            report.block("approval record (approved_by/approved_at/event_seq) differs from the "
                         "APPROVED event")
    seqs = [e.get("seq") for e in t["events"] if isinstance(e, dict)]
    first = t["events"][0] if t["events"] else None
    if not isinstance(first, dict) or first.get("event_type") != "DRAFTED" \
            or seqs != list(range(1, len(seqs) + 1)):
        report.block("ticket event log must start with DRAFTED and have contiguous seq")

    if not isinstance(service_audit, dict):
        report.block("service audit JSON (`audit --ticket-id`) is missing")
    elif not (service_audit.get("available") is True and service_audit.get("ok") is True
              and service_audit.get("tickets") == 1 and service_audit.get("issues") == []):
        codes = sorted({str(i.get("code")) for i in service_audit.get("issues", [])
                        if isinstance(i, dict)})
        report.block("lifecycle service audit is not clean for exactly this ticket "
                     f"(available/ok/tickets/issues; codes: {codes or 'n/a'})")


def check_ticket(report: Report, t: Any, service_audit: Any,
                 allowed_states: tuple[str, ...]) -> dict[str, Any] | None:
    p = parse_terms(report, t)
    if p is None:
        return None
    lane_gate(report, t, p)
    check_terms_math(report, t, p)
    check_veto_review(report, t)
    approval_gate(report, t, service_audit, allowed_states)
    return p


# --------------------------------------------------------------------------- pre-submit


def pre_submit(
    ticket: Any, service_audit: Any, session_date: Any, bid_raw: Any,
    ask_raw: Any, now: datetime, cfg_loader: Callable[[str], dict[str, Any]],
    quote_evidence: Path | None, prev_close_raw: Any = None,
) -> dict[str, Any]:
    report = Report()
    p = check_ticket(report, ticket, service_audit, ("APPROVED",))
    if p is None:
        ident = ticket.get("ticket_id") if isinstance(ticket, dict) else None
        return report.finish({"ticket_id": ident})
    t, market = ticket, ticket["market"]
    cfg = cfg_loader(market)
    prof = ticket["profile"]

    if t["orders"] or t["position"] is not None:
        report.block("the ticket already has an order or position: an approved ticket carries one "
                     "entry order; use amend/cancel for it, never a second submit")
    if not valid_ymd(session_date):
        report.block("--session-date must be the market's trading date as YYYYMMDD")
    else:
        if session_date > t["expiry_date"]:
            report.block(f"ticket expired on {t['expiry_date']} (session {session_date})")
        if abs(datetime.strptime(session_date, "%Y%m%d").date() - now.astimezone(timezone.utc).date()) \
                > timedelta(days=1):
            report.block(f"--session-date {session_date} is more than a day from now "
                         f"({now.isoformat()})")
    approved_at = parse_time(t["approved_at"])
    if approved_at is not None and now < approved_at:
        report.block(f"now {now.isoformat()} is before the approval at {approved_at.isoformat()}")

    bid = text_decimal(str(bid_raw)) if bid_raw not in (None, "") else None
    ask = text_decimal(str(ask_raw)) if ask_raw not in (None, "") else None
    if bid is None:
        report.block("broker bid is missing or not a valid positive number")
    if ask is None:
        report.block("broker ask is missing or not a valid positive number")
    if bid is not None and ask is not None and bid > ask:
        report.block(f"quote is crossed: bid {bid} > ask {ask}")
    if quote_evidence is None:
        report.warn("no quote evidence file attached; the bid/ask must come from the user's "
                    "current broker screenshot")
    elif not quote_evidence.is_file():
        report.block(f"quote evidence file not found: {quote_evidence}")
    if report.blockers:
        return report.finish({"ticket_id": t["ticket_id"], "market": market})
    assert bid is not None and ask is not None

    e0, e1, st, sl = p["entry_planned"], p["entry_max"], p["stop_trigger"], p["stop_limit"]
    if st >= bid:
        report.block(f"stop trigger {st} is not below bid {bid}: it would trigger at once")
    if t["execution_mode"] == "MARKETABLE_LIMIT":
        if ask > e1:
            report.block(f"ask {ask} is above the approved entry_max {e1}: do not chase, do not "
                         "raise the limit, do not substitute a new plan")
        reference, limit = ask, e1
        order_note = "marketable limit; the limit may be lower than entry_max, never higher"
    else:
        if e0 >= ask:
            report.block(f"passive limit {e0} is at or above ask {ask}: it would fill immediately, "
                         "which is not the approved passive structure entry")
        reference, limit = e0, e0
        order_note = "passive limit at the approved structure price"
    if reference <= st:
        report.block(f"entry reference {reference} is not above the stop trigger {st}")

    tick = text_decimal(str(cfg["tick"])) if cfg.get("tick") is not None else None
    if tick:
        for label, price in (("order limit", limit), ("stop trigger", st), ("stop limit", sl)):
            if price % tick:
                report.block(f"{label} {price} is not a multiple of tick {tick}")
    pct = text_decimal(str(cfg["price_limit_pct"]), zero=True) if cfg.get("price_limit_pct") else None
    prev_close = text_decimal(str(prev_close_raw)) if prev_close_raw not in (None, "") else None
    if market == "A":
        if prev_close is None or pct is None:
            report.warn("price-limit band not verified: provide --prev-close and price_limit_pct "
                        "(the service does not validate the band)")
        else:
            upper = (prev_close * (1 + pct / 100)).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
            lower = (prev_close * (1 - pct / 100)).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
            if not lower <= limit <= upper:
                report.block(f"order limit {limit} is outside the price-limit band {lower}-{upper}")
            if ask >= upper:
                report.block(f"ask {ask} is at the limit-up price {upper}; a buy is unlikely to fill")
    if prof["min_sessions_before_exit"]:
        report.warn("T+1: shares bought today cannot be sold today; no same-day protective sell can "
                    "fill, and a gap-down next session may skip the stop")
    else:
        report.warn("U.S. same-day sale is allowed at the contract level; margin and day-trade "
                    "restrictions are the broker's, check the broker screen")
    report.warn("gap-through risk: if price opens or falls past the stop limit, the stop-limit does "
                "not fill and the position stays open; the loss at the limit is not a ceiling")

    at_reference, at_worst = economics(p, reference), economics(p, e1)
    min_r = p["min_reward_risk"]
    if min_r is not None:
        if at_reference["r"] is None or at_reference["r"] < min_r:
            report.block(f"reward/risk at the current reference {reference} is "
                         f"{money_or_none(at_reference['r'])}, below the persisted min_reward_risk "
                         f"{min_r}")
        elif at_worst["r"] is not None and at_worst["r"] < min_r:
            report.warn(f"reward/risk at the worst-case fill {e1} falls below {min_r}")
    if report.blockers:
        return report.finish({"ticket_id": t["ticket_id"], "market": market})

    template = t["order_template"] if isinstance(t.get("order_template"), dict) else {}
    order_form = {"side": "BUY", "symbol": t["symbol"], "order_type": "LIMIT",
                  "quantity": p["quantity"], "limit_price": str(limit), "max_price": str(limit),
                  "tif": template.get("tif") or "DAY", "note": order_note}
    qty = Decimal(p["quantity"])
    return report.finish({
        "ticket_id": t["ticket_id"], "market": market, "symbol": t["symbol"],
        "execution_mode": t["execution_mode"], "decision_lane": t["decision_lane"],
        "setup_quality": t["setup_quality"], "capital_stage": t["capital_stage"],
        "evaluated_at": now.isoformat(), "session_date": session_date,
        "approved_by": t["approved_by"], "approved_at": t["approved_at"],
        "terms_sha256": t["terms_sha256"],
        "quote": {"bid": str(bid), "ask": str(ask), "spread": str(ask - bid),
                  "evidence_sha256": sha256_file(quote_evidence)
                  if quote_evidence and quote_evidence.is_file() else None},
        "order_form": order_form,
        "protective_plan": {"description": stop_limit_text(st, sl), "stop_trigger": str(st),
                            "stop_limit": str(sl), "place_after_fill_only": True,
                            "min_sessions_before_exit": prof["min_sessions_before_exit"]},
        "calculation": {
            "quantity": p["quantity"], "max_cash_needed": money(e1 * qty + p["fee_estimate"]),
            "capital_budget": str(p["capital_budget"]), "risk_budget": money_or_none(p["risk_budget"]),
            "max_loss_if_stop_fills_at_limit": str(p["max_loss_amount"]),
            "risk_at_stop_trigger": str(p["risk_amount"]), "reward_to_first_target": str(p["reward_amount"]),
            "ticket_r_multiple": str(p["r_multiple"]), "min_reward_risk": money_or_none(min_r),
            "reward_risk_at_reference": money_or_none(at_reference["r"]),
            "reward_risk_at_worst_fill": money_or_none(at_worst["r"]),
            "fee_estimate_included": str(p["fee_estimate"])},
    })


def stop_limit_text(trigger: Decimal, limit: Decimal) -> str:
    return f"SELL stop-limit: trigger {trigger} >= limit {limit}"


# ------------------------------------------------------------------------- protective


def protective(ticket: Any, service_audit: Any, trigger_raw: Any, limit_raw: Any,
               shares_raw: Any) -> dict[str, Any]:
    report = Report()
    p = check_ticket(report, ticket, service_audit, POSITION_STATES)
    if p is None:
        ident = ticket.get("ticket_id") if isinstance(ticket, dict) else None
        return report.finish({"ticket_id": ident})
    t, market = ticket, ticket["market"]
    prof = t["profile"]
    pos = t["position"]
    trigger = text_decimal(str(trigger_raw)) if trigger_raw not in (None, "") else None
    limit = text_decimal(str(limit_raw)) if limit_raw not in (None, "") else None
    if trigger is None or limit is None:
        report.block("stop trigger and stop limit must be positive decimals (<= 4 places)")
    try:
        shares = int(str(shares_raw))
    except ValueError:
        shares = 0
    if shares <= 0:
        report.block("protective shares must be a positive whole number")
    open_qty = pos.get("open_qty") if isinstance(pos, dict) else None
    if isinstance(open_qty, bool) or not isinstance(open_qty, int) or open_qty <= 0:
        report.block("the service state shows no open position to protect")
    avg = text_decimal(pos.get("avg_entry_price")) if isinstance(pos, dict) else None
    if avg is None:
        report.block("position.avg_entry_price is missing from the service state")
    if report.blockers:
        return report.finish({"ticket_id": t["ticket_id"], "market": market})
    assert trigger is not None and limit is not None and avg is not None and open_qty is not None

    if limit > trigger:
        report.block(f"sell stop-limit orientation wrong: limit {limit} must not be above trigger "
                     f"{trigger}")
    elif limit == trigger:
        report.warn("trigger equals limit: there is no fill slack below the trigger")
    if limit < p["stop_limit"]:
        report.block(f"protective limit {limit} is looser than the approved stop_limit "
                     f"{p['stop_limit']}")
    if trigger != p["stop_trigger"]:
        report.warn(f"stop trigger {trigger} differs from the approved stop_trigger "
                    f"{p['stop_trigger']}; the human must accept the difference before recording it")
    if trigger >= avg:
        report.block(f"stop trigger {trigger} is not below the average entry {avg}; this is not a "
                     "loss-side protective stop")
    if shares > open_qty:
        report.block(f"protective shares {shares} exceed the open position {open_qty}")
    elif shares % prof["lot_size"] and not (prof["odd_lot_exit_closes_only"] and shares == open_qty):
        report.block(f"protective shares {shares} must be a {prof['lot_size']}-share multiple unless "
                     "the profile lets an odd lot close the whole position")
    live_cover = 0
    for order in t["orders"]:
        if isinstance(order, dict) and order.get("role") == "PROTECTIVE_STOP" \
                and order.get("status") in LIVE_ORDER:
            terms, filled = order.get("terms") or {}, order.get("filled_qty") or 0
            live_cover += int(terms.get("quantity") or 0) - int(filled)
    if live_cover + shares > open_qty:
        report.block(f"live protective orders already cover {live_cover} of {open_qty} shares; "
                     "amend the existing order instead of stacking another")
    covered = min(live_cover + shares, open_qty)
    if covered < open_qty:
        report.warn(f"after this order {open_qty - covered} of {open_qty} open shares stay "
                    "unprotected")
    report.warn("gap-through risk: if price opens or falls past the limit, the stop-limit does not "
                "fill and the position stays open; the loss at the limit is not a ceiling")
    if prof["min_sessions_before_exit"]:
        report.warn("T+1: the protective sell cannot fill on the buy-fill day; record the real "
                    "mechanism (monitored alert or next-session order), not a live stop that cannot fill")
    fees = text_decimal(pos.get("fees_total"), zero=True) or Decimal(0)
    loss_at_limit = (avg - limit) * shares + fees
    if loss_at_limit > p["max_loss_amount"]:
        report.warn(f"loss if the stop fills at its limit is about {money(loss_at_limit)} (entry "
                    f"fees included), above the approved max_loss_amount {p['max_loss_amount']}")
    return report.finish({
        "ticket_id": t["ticket_id"], "market": market, "terms_sha256": t["terms_sha256"],
        "protective_order": {"description": stop_limit_text(trigger, limit), "shares": shares,
                             "stop_trigger": str(trigger), "stop_limit": str(limit)},
        "open_qty": open_qty, "protected_shares_after": covered,
        "loss_at_stop_trigger_before_exit_fee": money((avg - trigger) * shares + fees),
        "loss_if_stop_fills_at_limit_before_exit_fee": money(loss_at_limit),
    })


# ----------------------------------------------------------------------------- check-args


def check_args(op: str, args: Any) -> dict[str, Any]:
    report = Report()
    if op in FORBIDDEN_OPS:
        report.block(f"operation {op!r} is not available to this skill: {FORBIDDEN_OPS[op]}")
        return report.finish({"op": op}, ok="ARGS_OK")
    spec = OP_SPECS.get(op)
    if spec is None:
        report.block(f"unknown operation {op!r}; allowed: {list(OP_SPECS)}")
        return report.finish({"op": op}, ok="ARGS_OK")
    if not isinstance(args, dict):
        report.block("args JSON must be an object of the service function's keyword arguments")
        return report.finish({"op": op}, ok="ARGS_OK")
    allowed = {spec["ident"], *spec["required"], *spec["optional"]}
    for key in args:
        if key in ("now", "human_confirmed", "terms_sha256"):
            report.block(f"{key!r} must never be passed by this skill")
        elif key not in allowed:
            report.block(f"unexpected key {key!r} for {op}; allowed: {sorted(allowed)}")
    for key in (spec["ident"], *spec["required"]):
        if key not in args:
            report.block(f"missing required key {key!r}")
    for key in args:
        value = args[key]
        if key in PRICE_ARGS or key == "fee":
            if value is not None and text_decimal(value, zero=key == "fee") is None:
                report.block(f"{key} must be a decimal TEXT (<= 4 places), never a JSON number")
        elif key in DATE_ARGS:
            if value is not None and not valid_ymd(value):
                report.block(f"{key} must be a real date written YYYYMMDD")
        elif key == "occurred_at":
            if not parse_time(value):
                report.block("occurred_at must be ISO-8601 with a UTC offset, e.g. "
                             "2026-10-27T09:31:00-04:00")
        elif key == "quantity":
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                report.block("quantity must be a positive integer (not a decimal, not text)")
        elif key == "evidence":
            if value is not None and not isinstance(value, dict):
                report.block("evidence must be a JSON object (for example file name + sha256)")
        elif key in ("idempotency_key", spec["ident"], *TEXT_ARGS):
            if value is not None and not (isinstance(value, str) and value.strip()):
                report.block(f"{key} must be non-empty text")
    actor = args.get(spec["actor_key"])
    kind, _, name = (actor if isinstance(actor, str) else "").partition(":")
    if actor is not None and not (kind in spec["actors"] and name.strip()):
        report.block(f"{spec['actor_key']} must be '<kind>:<name>' with kind in "
                     f"{list(spec['actors'])}; got {actor!r}")
    if op == "submit_order":
        role = args.get("role", "ENTRY")
        otype = args.get("order_type")
        if role not in ENTRY_ORDER_TYPES:
            report.block(f"role must be one of {list(ENTRY_ORDER_TYPES)}")
        elif otype not in ENTRY_ORDER_TYPES[role]:
            report.block(f"{role} order_type must be one of {list(ENTRY_ORDER_TYPES[role])}")
        if role == "ENTRY" and not args.get("limit_price"):
            report.block("an ENTRY order needs limit_price (market entries are not allowed)")
        if args.get("tif") not in (None, "DAY", "GTC", "GTD"):
            report.block("tif must be DAY, GTC, or GTD")
        if (args.get("tif") == "GTD") != bool(args.get("expiry_date")):
            report.block("tif GTD and expiry_date go together")
    return report.finish({"op": op, "service_command": f"apply --op {op} --args-json <file>"},
                         ok="ARGS_OK")


# --------------------------------------------------------------------- idempotency key


def idempotency_key(ticket_id: str, op: str, broker_ref: str | None, evidence: Path | None) -> dict[str, Any]:
    if op not in EVENT_OPS:
        raise ValueError(f"op must be one of {list(EVENT_OPS)}")
    if not broker_ref and evidence is None:
        raise ValueError("provide --broker-ref (broker order id / execution id) and/or --evidence")
    evidence_hash = None
    if evidence is not None:
        if not evidence.is_file():
            raise ValueError(f"evidence file not found: {evidence}")
        evidence_hash = sha256_file(evidence)
    material = "\x1f".join([ticket_id, op, broker_ref or "", evidence_hash or ""])
    return {"ticket_id": ticket_id, "op": op, "evidence_sha256": evidence_hash,
            "idempotency_key": hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]}


# ----------------------------------------------------------------------- scale-up proposal


def scale_up_proposal(result: Any, strategy: str) -> dict[str, Any]:
    """Verify a service `scale-up` result; the audit adds no threshold of its own."""
    report = Report()
    if not isinstance(result, dict):
        report.block("scale-up result is not a JSON object")
        return report.finish({}, ok="PROPOSAL_ONLY_FOR_HUMAN_DECISION")
    if result.get("strategy") != strategy.strip() or not strategy.strip():
        report.block(f"result strategy {result.get('strategy')!r} is not the exact strategy "
                     f"{strategy!r}; scale-up is judged per strategy, never pooled")
    if result.get("proposal_only") is not True or result.get("mutates_tickets") is not False \
            or result.get("auto_approve") is not False:
        report.block("result is not a proposal-only service verdict (proposal_only/mutates_tickets/"
                     "auto_approve flags wrong or missing)")
    if result.get("eligible") is not True or result.get("reasons"):
        report.block(f"service says not eligible: {result.get('reasons')}")
    gates = result.get("gates")
    if not isinstance(gates, dict) or not gates \
            or not all(isinstance(g, dict) and g.get("passed") is True for g in gates.values()):
        report.block("not every service gate passed")
    metrics, policy = result.get("metrics"), result.get("policy")
    n = metrics.get("sample_size") if isinstance(metrics, dict) else None
    if isinstance(n, bool) or not isinstance(n, int) or n <= 1:
        report.block(f"sample_size {n!r} is not a same-strategy sample of more than one real trade")
    elif isinstance(metrics.get("ticket_ids"), list) and len(metrics["ticket_ids"]) != n:
        report.block("metrics.ticket_ids does not match sample_size")
    if not (isinstance(policy, dict) and all(k in policy for k in
                                             ("min_sample_size", "max_drawdown_r", "min_plan_adherence"))):
        report.block("caller policy (min_sample_size, max_drawdown_r, min_plan_adherence) is not "
                     "echoed in the result")
    for key in ("policy_sha256", "sample_sha256"):
        if not (isinstance(result.get(key), str) and HEX64_RE.match(result[key])):
            report.block(f"{key} is missing; the proposal must be reproducible")
    return report.finish({
        "strategy": strategy, "sample_size": n, "policy_sha256": result.get("policy_sha256"),
        "sample_sha256": result.get("sample_sha256"),
        "next_step": "show to the human as a proposal; any larger size needs a NEW draft ticket "
                     "(via $market-review on 固化) and a NEW human approval"},
        ok="PROPOSAL_ONLY_FOR_HUMAN_DECISION")


# ------------------------------------------------------------------------------- CLI


def emit(payload: dict[str, Any], ok: bool) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 2


def add_gate_args(sub: argparse.ArgumentParser) -> None:
    sub.add_argument("--state", type=Path, required=True,
                     help="Output of `trade_lifecycle state --ticket-id <id>`, unedited; its "
                          "`approval` and `profile` are the only approval/profile source.")
    sub.add_argument("--service-audit", type=Path, required=True,
                     help="Output of `trade_lifecycle audit --ticket-id <id>`, unedited.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    pre = sub.add_parser("pre-submit")
    add_gate_args(pre)
    pre.add_argument("--session-date", required=True, help="Market trading date, YYYYMMDD.")
    pre.add_argument("--bid", required=True)
    pre.add_argument("--ask", required=True)
    pre.add_argument("--quote-evidence", type=Path, help="Broker quote screenshot file.")
    pre.add_argument("--prev-close", help="A-share previous close from the broker screen.")
    pre.add_argument("--now", help="ISO-8601 time with offset; defaults to the current time.")
    pre.add_argument("--config", type=Path, help="Ignored local config with profile settings.")

    prot = sub.add_parser("protective")
    add_gate_args(prot)
    prot.add_argument("--stop-trigger", required=True)
    prot.add_argument("--stop-limit", required=True)
    prot.add_argument("--shares", required=True, help="Shares the protective order covers.")

    chk = sub.add_parser("check-args")
    chk.add_argument("--op", required=True)
    chk.add_argument("--args-json", type=Path, required=True)

    key = sub.add_parser("idempotency-key")
    key.add_argument("--ticket-id", required=True)
    key.add_argument("--op", required=True)
    key.add_argument("--broker-ref", help="Broker order id or execution id.")
    key.add_argument("--evidence", type=Path, help="Screenshot or export proving the event.")

    scale = sub.add_parser("scale-up-proposal")
    scale.add_argument("--result", type=Path, required=True,
                       help="Output of `trade_lifecycle scale-up`, unedited.")
    scale.add_argument("--strategy", required=True)

    args = parser.parse_args()
    try:
        if args.command == "idempotency-key":
            return emit(idempotency_key(args.ticket_id, args.op, args.broker_ref, args.evidence), True)
        if args.command == "check-args":
            result = check_args(args.op, load_json(args.args_json))
        elif args.command == "scale-up-proposal":
            result = scale_up_proposal(load_json(args.result), args.strategy)
        elif args.command == "protective":
            result = protective(load_json(args.state), load_json(args.service_audit),
                                args.stop_trigger, args.stop_limit, args.shares)
        else:
            now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
            if now is None:
                raise ValueError("--now must be ISO-8601 with a timezone offset")
            result = pre_submit(load_json(args.state), load_json(args.service_audit),
                                args.session_date, args.bid, args.ask,
                                now, lambda market: profile_config(args.config, market),
                                args.quote_evidence, args.prev_close)
        return emit(result, result["verdict"] != "BLOCKED")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit({"verdict": "BLOCKED", "blockers": [f"fail closed: {exc}"], "warnings": []},
                    False)


if __name__ == "__main__":
    sys.exit(main())
