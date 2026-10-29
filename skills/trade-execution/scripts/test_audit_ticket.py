#!/usr/bin/env python3
"""Tests for audit_ticket.py using synthetic service-shaped `state` exports only.

No database, broker, network, or local config is read. The fixtures mirror what
`python -m zradar.trade_lifecycle state` prints for schema v6: decimal TEXT, upper-case controlled
states, `human:<name>` approval, a `terms_sha256`, the persisted `approval` record, and the frozen
parsed `profile`. Expected amounts are written out by hand.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import audit_ticket as audit

NOW = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)
TERMS = "a" * 64
AUDIT_OK = {"available": True, "ok": True, "tickets": 1, "issues": []}
VETO_PASS = {dim: {"veto": False, "evidence": f"{dim} clean on the closed daily chart"}
             for dim in audit.VETO_DIMENSIONS}


US_PROFILE = {
    "market": "US", "currency": "USD", "lot_size": 1, "min_sessions_before_exit": 0,
    "odd_lot_exit_closes_only": False,
    "price_limit": {"convention": "no_exchange_wide_daily_band", "validated": False, "note": "n/a"},
    "fee_components": ["commission", "sec_fee_sell", "taf_sell", "other"],
    "calendar": {"kind": "ndx", "tz": "America/New_York", "sessions": ["09:30-16:00"],
                 "source": "synthetic"},
    "tdx": {"label": "US", "data_source": "synthetic", "role": "chart evidence only"}}
A_PROFILE = {
    "market": "A", "currency": "CNY", "lot_size": 100, "min_sessions_before_exit": 1,
    "odd_lot_exit_closes_only": True,
    "price_limit": {"convention": "daily_band_per_board", "validated": False, "note": "n/a"},
    "fee_components": ["commission", "stamp_duty_sell", "transfer_fee"],
    "calendar": {"kind": "a_share", "tz": "Asia/Shanghai",
                 "sessions": ["09:30-11:30", "13:00-15:00"], "source": "synthetic"},
    "tdx": {"label": "A", "data_source": "synthetic", "role": "chart evidence only"}}


def stop_semantics(**overrides: object) -> dict:
    """Valid persisted `review.stop_semantics`; INTRADAY_HARD at the ticket's 95.00 stop_trigger."""
    base = {"basis": {"kind": "PRIOR_B1_N_LOW", "level": "95.00",
                      "evidence": "below the prior N low named in the thesis"},
            "activation": "INTRADAY_HARD",
            "broker_implementation": "sell stop-limit 95.00/94.50 after the entry fill"}
    base.update(overrides)
    return base


def with_stop(t: dict, sem: object) -> dict:
    """Copy of ticket `t` whose review carries `sem` (None drops the key)."""
    t = copy.deepcopy(t)
    if sem is None:
        t["review"].pop("stop_semantics", None)
    else:
        t["review"]["stop_semantics"] = sem
    return t


def profile_fields(profile: dict) -> dict:
    """`profile` + `profile_sha256` as the service prints them (hash of the sorted-key JSON)."""
    text = json.dumps(profile, ensure_ascii=False, sort_keys=True)
    return {"profile": copy.deepcopy(profile),
            "profile_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def approval(**overrides: object) -> dict:
    """`state.approval`: the persisted APPROVED-event facts (read-only evidence, not an input)."""
    base = {"event_seq": 2, "approved_by": "human:alice", "approved_at": "2026-10-27T13:00:00+00:00",
            "terms_sha256": TERMS, "matches_ticket_terms": True, "note": None}
    base.update(overrides)
    return base


def events(*, approved_by: str = "human:alice") -> list[dict]:
    return [
        {"seq": 1, "event_type": "DRAFTED", "state_after": "DRAFT", "actor": "review:codex",
         "occurred_at": "2026-10-27T12:00:00+00:00", "ref_kind": None, "ref_id": None},
        {"seq": 2, "event_type": "APPROVED", "state_after": "APPROVED", "actor": approved_by,
         "occurred_at": "2026-10-27T13:00:00+00:00", "ref_kind": None, "ref_id": None},
    ]


def ticket(**overrides: object) -> dict:
    """US PASSIVE_LIMIT PRACTICE ticket: 100 sh, entry 100, stop 95/94.50, target 110, fee 0.

    risk 500.00, max loss 550.00, reward 1000.00, R 2.00, worst cost 10000.00.
    """
    base = {
        "ticket_id": "T-1", "market": "US", "symbol": "AAA", "episode_id": "E-1", "plan_id": "P-1",
        "source_decision_id": "D-1", "strategy": "b1", "execution_mode": "PASSIVE_LIMIT",
        "thesis": "white-line pullback holds", "trigger_text": "touch 100.00 on shrinking volume",
        "invalidation": "close below 95.00", "entry_planned": "100.00", "entry_max": "100.00",
        "stop_kind": "stop_limit", "stop_trigger": "95.00", "stop_limit": "94.50",
        "targets": [{"price": "110.00"}], "expiry_date": "20261028",
        "capital_budget": "10000.00", "quantity": 100, "fee_estimate": "0.00",
        "risk_amount": "500.00", "max_loss_amount": "550.00", "reward_amount": "1000.00",
        "r_multiple": "2.00", "currency": "USD", "setup_quality": "VALID",
        "decision_lane": "PRACTICE", "capital_stage": "PRACTICE", "risk_budget": "550.00",
        "min_reward_risk": "2.00", **profile_fields(US_PROFILE), "terms_sha256": TERMS,
        "approval": approval(),
        "created_by": "review:codex", "created_at": "2026-10-27T12:00:00+00:00",
        "review": {"source": {}, "veto_review": None, "mode_hint": "PASSIVE_LIMIT",
                   "capital_contract": {"stage_changes_setup_validity": False},
                   "stop_semantics": stop_semantics()},
        "order_template": {"order_type": "LIMIT", "tif": "DAY"}, "fee_assumption": {},
        "state": "APPROVED", "journal_state": "APPROVED", "state_at": "2026-10-27T13:00:00+00:00",
        "approved_by": "human:alice", "approved_at": "2026-10-27T13:00:00+00:00",
        "orders": [], "position": None, "outcome": None, "events": events(),
    }
    base.update(overrides)
    return base


def a_circle(**overrides: object) -> dict:
    fields = dict(decision_lane="A_CIRCLE", setup_quality="A", min_reward_risk=None)
    fields.update(overrides)
    return ticket(**fields)


def marketable(**overrides: object) -> dict:
    """entry 100 (planned) / 101 (max), stop 95/94.50, target 112, 100 sh: loss 650, R 2.40."""
    fields = dict(
        execution_mode="MARKETABLE_LIMIT", entry_max="101.00", targets=[{"price": "112.00"}],
        capital_budget="10100.00", risk_amount="500.00", max_loss_amount="650.00",
        reward_amount="1200.00", r_multiple="2.40", risk_budget="650.00")
    fields.update(overrides)
    t = ticket(**fields)
    t["review"] = {**t["review"], "veto_review": copy.deepcopy(VETO_PASS)}
    return t


def a_share(**overrides: object) -> dict:
    """A-share: 100 sh at 10.00, stop 9.50/9.40, target 11.00: loss 60, R 2.00."""
    fields = dict(
        market="A", currency="CNY", entry_planned="10.00", entry_max="10.00", stop_trigger="9.50",
        stop_limit="9.40", targets=[{"price": "11.00"}], capital_budget="1000.00",
        risk_amount="50.00", max_loss_amount="60.00", reward_amount="100.00", r_multiple="2.00",
        risk_budget="60.00", **profile_fields(A_PROFILE))
    fields.update(overrides)
    t = ticket(**fields)
    t["review"]["stop_semantics"] = stop_semantics(
        basis={"kind": "WHITE_LINE", "level": fields["stop_trigger"], "evidence": "white line per thesis"})
    return t


def check(t: object = None, *, svc: object = AUDIT_OK,
          session: object = "20261027", bid: str = "100.10", ask: str = "100.20",
          now: datetime = NOW, cfg: dict | None = None, prev_close: object = None) -> dict:
    t = ticket() if t is None else t
    return audit.pre_submit(t, svc, session, bid, ask, now, lambda _m: dict(cfg or {}),
                            None, prev_close)


class Blocks(unittest.TestCase):
    def assert_blocked(self, result: dict, fragment: str) -> None:
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertTrue(any(fragment in b for b in result["blockers"]),
                        f"{fragment!r} not in {result['blockers']}")


class PreSubmitReady(unittest.TestCase):
    def test_practice_passive_ticket_is_ready_with_exact_numbers(self) -> None:
        result = check()
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["verdict"], "READY_FOR_HUMAN_CONFIRMATION")
        form = result["order_form"]
        self.assertEqual((form["side"], form["order_type"], form["quantity"], form["limit_price"]),
                         ("BUY", "LIMIT", 100, "100.00"))
        calc = result["calculation"]
        self.assertEqual(calc["max_cash_needed"], "10000.00")
        self.assertEqual(calc["max_loss_if_stop_fills_at_limit"], "550.00")
        self.assertEqual(calc["reward_risk_at_reference"], "2.00")
        self.assertEqual(result["approved_by"], "human:alice")
        self.assertEqual(result["terms_sha256"], TERMS)
        self.assertEqual(result["protective_plan"]["description"],
                         "SELL stop-limit: trigger 95.00 >= limit 94.50")
        self.assertTrue(any("gap-through" in w for w in result["warnings"]))

    def test_a_circle_is_ready_without_a_reward_risk_floor(self) -> None:
        t = a_circle(r_multiple="2.00")
        self.assertEqual(check(t)["blockers"], [])

    def test_marketable_limit_uses_entry_max_as_ceiling_and_warns_on_worst_fill(self) -> None:
        result = check(marketable(), bid="100.40", ask="100.50")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["order_form"]["limit_price"], "101.00")
        calc = result["calculation"]
        self.assertEqual(calc["reward_risk_at_reference"], "2.09")
        self.assertEqual(calc["reward_risk_at_worst_fill"], "1.83")
        self.assertTrue(any("worst-case fill" in w for w in result["warnings"]))

    def test_a_share_is_ready_with_t_plus_one_and_band_notes(self) -> None:
        result = check(a_share(), bid="10.05", ask="10.10")
        self.assertEqual(result["blockers"], [])
        self.assertTrue(any("T+1" in w for w in result["warnings"]))
        self.assertTrue(any("price-limit band not verified" in w for w in result["warnings"]))
        self.assertEqual(result["protective_plan"]["min_sessions_before_exit"], 1)


class CapitalMaturity(Blocks):
    def test_ambiguous_and_reject_lanes_are_never_executable(self) -> None:
        for lane in ("AMBIGUOUS", "REJECT"):
            for quality in audit.SETUP_QUALITIES:
                result = check(ticket(decision_lane=lane, setup_quality=quality))
                self.assert_blocked(result, "never executable")

    def test_lane_and_quality_must_agree(self) -> None:
        self.assert_blocked(check(ticket(decision_lane="A_CIRCLE", setup_quality="VALID")),
                            "needs setup_quality A")
        self.assert_blocked(check(ticket(decision_lane="PRACTICE", setup_quality="A")),
                            "needs setup_quality VALID")
        self.assert_blocked(check(ticket(setup_quality="AMBIGUOUS")), "needs setup_quality VALID")

    def test_practice_needs_persisted_min_reward_risk_and_budget_and_stage(self) -> None:
        self.assert_blocked(check(ticket(min_reward_risk=None)), "needs a persisted min_reward_risk")
        self.assert_blocked(check(ticket(risk_budget=None)), "needs a persisted risk_budget")
        self.assert_blocked(check(ticket(capital_stage=None)), "needs a persisted capital_stage")
        self.assert_blocked(check(a_circle(risk_budget=None)), "needs a persisted risk_budget")

    def test_practice_needs_complete_logic_and_explicit_stop(self) -> None:
        self.assert_blocked(check(ticket(thesis="  ")), "complete logic")
        self.assert_blocked(check(ticket(invalidation="")), "complete logic")
        self.assert_blocked(check(ticket(trigger_text="")), "complete logic")
        self.assert_blocked(check(ticket(stop_kind="")), "explicit stop")

    def test_max_loss_over_risk_budget_blocks_every_lane(self) -> None:
        self.assert_blocked(check(ticket(risk_budget="549.99")), "exceeds risk_budget")
        self.assert_blocked(check(a_circle(risk_budget="549.99")), "exceeds risk_budget")

    def test_capital_budget_is_a_separate_ruler(self) -> None:
        self.assert_blocked(check(ticket(capital_budget="9999.99")), "exceeds capital_budget")

    def test_persisted_min_reward_risk_is_enforced_even_for_a_circle(self) -> None:
        self.assert_blocked(check(ticket(min_reward_risk="2.01")), "below the persisted min_reward_risk")
        self.assert_blocked(check(a_circle(min_reward_risk="2.01")), "below the persisted min_reward_risk")

    def test_current_reference_below_min_reward_risk_blocks(self) -> None:
        t = marketable(min_reward_risk="2.30")        # ticket R 2.40 passes; ask 101.00 gives 1.83
        self.assert_blocked(check(t, bid="100.90", ask="101.00"), "at the current reference")

    def test_capital_stage_and_smaller_size_never_change_setup_validity(self) -> None:
        baseline = check()["blockers"]
        smaller = ticket(quantity=50, capital_stage="STAGE_ONE_SMALL", capital_budget="5000.00",
                         risk_amount="250.00", max_loss_amount="275.00", reward_amount="500.00",
                         risk_budget="275.00")
        for t in (ticket(capital_stage="STAGE_TWO"), smaller):
            result = check(t)
            self.assertEqual(result["blockers"], baseline)
            self.assertEqual(result["verdict"], "READY_FOR_HUMAN_CONFIRMATION")
        # A stage name cannot rescue a mislabelled setup.
        self.assert_blocked(check(ticket(setup_quality="AMBIGUOUS", capital_stage="PRACTICE")),
                            "never relabels a setup")

    def test_capital_stage_must_be_an_account_label(self) -> None:
        self.assert_blocked(check(ticket(capital_stage="practice")), "capital_stage")


class ApprovalGate(Blocks):
    def test_terms_hash_comes_from_the_persisted_approval_record(self) -> None:
        # No hash argument exists anywhere: the persisted record alone is compared with the terms.
        self.assertEqual(check()["blockers"], [])
        self.assert_blocked(check(ticket(approval=approval(terms_sha256="b" * 64))), "does not match")
        self.assert_blocked(check(ticket(approval=approval(terms_sha256="A" * 64))), "64-hex")
        self.assert_blocked(check(ticket(approval=approval(terms_sha256=None))), "64-hex")
        self.assert_blocked(check(ticket(terms_sha256="short")), "terms_sha256 is not a 64-hex")

    def test_service_flag_must_confirm_the_approval_matches_current_terms(self) -> None:
        self.assert_blocked(check(ticket(approval=approval(matches_ticket_terms=False))),
                            "matches_ticket_terms")
        self.assert_blocked(check(ticket(approval=approval(matches_ticket_terms="true"))),
                            "matches_ticket_terms")

    def test_missing_or_malformed_approval_record_fails_closed(self) -> None:
        # An APPROVED-looking state with approval null is never completed from chat or inferred.
        self.assert_blocked(check(ticket(approval=None)), "state.approval is missing")
        self.assert_blocked(check(ticket(approval={"terms_sha256": TERMS})), "state.approval is missing")
        self.assert_blocked(check(ticket(approval="human:alice")), "state.approval is missing")
        draft = ticket(state="DRAFT", journal_state="DRAFT", approval=None, approved_by=None,
                       approved_at=None, events=events()[:1])
        self.assert_blocked(check(draft), "needs ['APPROVED']")

    def test_approval_record_must_agree_with_the_approved_event(self) -> None:
        for bad in (approval(approved_by="human:bob"), approval(event_seq=3),
                    approval(approved_at="2026-10-27T13:00:01+00:00")):
            self.assert_blocked(check(ticket(approval=bad)), "approval record")

    def test_approval_hash_cannot_be_typed_on_the_command_line(self) -> None:
        for command in ("pre-submit", "protective"):
            argv = ["audit_ticket.py", command, "--state", "s", "--service-audit", "a",
                    "--approved-terms-sha256", TERMS]
            saved, saved_err = sys.argv, sys.stderr
            sys.argv, sys.stderr = argv, io.StringIO()
            try:
                with self.assertRaises(SystemExit):
                    audit.main()
            finally:
                sys.argv, sys.stderr = saved, saved_err

    def test_approver_must_be_a_named_human_in_the_event_log(self) -> None:
        for actor in ("agent:codex", "review:codex", "system:cron", "human:", "human", ""):
            t = ticket(approved_by=actor, events=events(approved_by=actor))
            self.assert_blocked(check(t), "not 'human:<name>'")
        self.assert_blocked(check(ticket(approved_by="human:someone-else")), "differs from")

    def test_missing_or_duplicate_approval_event_blocks(self) -> None:
        self.assert_blocked(check(ticket(events=events()[:1])), "exactly one APPROVED")
        self.assert_blocked(check(ticket(events=events() + events())), "exactly one APPROVED")

    def test_approved_at_must_match_the_event(self) -> None:
        self.assert_blocked(check(ticket(approved_at="2026-10-27T13:00:01+00:00")), "approved_at")
        self.assert_blocked(check(ticket(approved_at=None)), "approved_at")

    def test_state_must_be_approved_and_journal_must_agree(self) -> None:
        self.assert_blocked(check(ticket(state="DRAFT", journal_state="DRAFT")), "needs ['APPROVED']")
        self.assert_blocked(check(ticket(journal_state="DRAFT")), "state journal")
        self.assert_blocked(check(ticket(state="approved")), "state")

    def test_service_audit_must_be_clean_for_exactly_this_ticket(self) -> None:
        self.assert_blocked(check(svc=None), "service audit JSON")
        dirty = {"available": True, "ok": False, "tickets": 1,
                 "issues": [{"ticket_id": "T-1", "code": "terms_hash_mismatch", "detail": "x"}]}
        self.assert_blocked(check(svc=dirty), "terms_hash_mismatch")
        self.assert_blocked(check(svc={**AUDIT_OK, "tickets": 2}), "service audit")
        self.assert_blocked(check(svc={**AUDIT_OK, "available": False}), "service audit")

    def test_expired_ticket_and_stale_session(self) -> None:
        self.assert_blocked(check(session="20261029"), "expired on 20261028")
        self.assert_blocked(check(session="20261101", t=ticket(expiry_date="20261231")), "more than a day")
        self.assert_blocked(check(session="2026-10-27"), "YYYYMMDD")
        self.assert_blocked(check(now=datetime(2026, 10, 27, 12, 59, tzinfo=timezone.utc)),
                            "before the approval")


class ShapeAndVocabulary(Blocks):
    def test_legacy_invented_export_is_rejected_not_mapped(self) -> None:
        legacy = {"ticket_id": "T-1", "profile": "us", "symbol": "AAA", "side": "buy",
                  "status": "approved", "approval": {"approved": True, "approved_by": "human"},
                  "expires_at": "2026-10-28T00:00:00+00:00", "entry": {"limit_price": 100},
                  "protective": {"stop_trigger": 95, "stop_limit": 94.5}, "target_price": 110,
                  "risk": {"max_loss": 500}, "portfolio": {}}
        result = check(legacy)
        self.assert_blocked(result, "not the output of `python -m zradar.trade_lifecycle state`")
        self.assertIn("legacy-shaped keys", " ".join(result["blockers"]))

    def test_controlled_vocabulary_has_no_case_or_synonym_repair(self) -> None:
        self.assert_blocked(check(ticket(market="us")), "market")
        self.assert_blocked(check(ticket(execution_mode="opening_burst")), "execution_mode")
        self.assert_blocked(check(ticket(execution_mode="marketable_limit")), "execution_mode")
        self.assert_blocked(check(ticket(decision_lane="a_circle")), "decision_lane")
        self.assert_blocked(check(ticket(setup_quality="valid")), "setup_quality")

    def test_money_must_be_service_text_not_json_numbers(self) -> None:
        self.assert_blocked(check(ticket(entry_planned=Decimal("100.00"))), "decimal TEXT")
        self.assert_blocked(check(ticket(stop_trigger=95.0)), "decimal TEXT")
        self.assert_blocked(check(ticket(entry_max="100.00001")), "entry_max")
        self.assert_blocked(check(ticket(risk_budget="550.001")), "risk_budget")

    def test_tampered_economics_are_detected(self) -> None:
        self.assert_blocked(check(ticket(risk_amount="400.00")), "do not recompute")
        self.assert_blocked(check(ticket(r_multiple="3.00")), "do not recompute")
        self.assert_blocked(check(ticket(max_loss_amount="1.00")), "do not recompute")

    def test_price_order_and_targets(self) -> None:
        self.assert_blocked(check(ticket(stop_limit="95.50")), "price order")
        self.assert_blocked(check(ticket(targets=[{"price": "110.00"}, {"price": "109.00"}])),
                            "strictly ascending")
        self.assert_blocked(check(ticket(targets=[])), "targets")

    def test_passive_limit_entry_max_must_equal_entry_planned(self) -> None:
        self.assert_blocked(check(ticket(entry_max="101.00")), "entry_max must equal")

    def test_lot_and_non_object(self) -> None:
        self.assert_blocked(check(a_share(quantity=150), bid="10.05", ask="10.10"), "lot 100")
        self.assertEqual(check([1, 2])["verdict"], "BLOCKED")

    def test_profile_is_required_and_must_be_the_services_frozen_profile(self) -> None:
        self.assert_blocked(check(ticket(profile="us")), "parsed market profile")
        self.assert_blocked(check(ticket(profile={"market": "US"})), "parsed market profile")
        shape = "not the output of `python -m zradar.trade_lifecycle state`"
        bare = ticket()
        del bare["profile"]
        self.assert_blocked(check(bare), shape)
        no_approval = ticket()
        del no_approval["approval"]
        self.assert_blocked(check(no_approval), shape)
        self.assert_blocked(check(ticket(**profile_fields(A_PROFILE))), "not the ticket market")

    def test_profile_must_hash_to_profile_sha256(self) -> None:
        altered = {**US_PROFILE, "lot_size": 5}
        self.assert_blocked(check(ticket(profile=altered)), "profile_sha256")
        self.assert_blocked(check(ticket(profile_sha256="short")), "profile_sha256 is not a 64-hex")

    def test_lot_size_and_t_plus_n_come_from_the_profile_not_the_market_code(self) -> None:
        lot10 = profile_fields({**US_PROFILE, "lot_size": 10})
        self.assert_blocked(check(ticket(quantity=105, **lot10)), "lot 10")
        t_plus_one = profile_fields({**US_PROFILE, "min_sessions_before_exit": 1})
        result = check(ticket(**t_plus_one))
        self.assertEqual(result["blockers"], [])
        self.assertTrue(any("T+1" in w for w in result["warnings"]))
        self.assertEqual(result["protective_plan"]["min_sessions_before_exit"], 1)
        bad = profile_fields({**US_PROFILE, "lot_size": 0})
        self.assert_blocked(check(ticket(**bad)), "lot_size")


class ExecutionModes(Blocks):
    def test_marketable_needs_persisted_clean_veto_review(self) -> None:
        t = marketable()
        t["review"]["veto_review"] = None
        self.assert_blocked(check(t, bid="100.40", ask="100.50"), "persisted veto_review")
        t = marketable()
        t["review"]["veto_review"]["volume"]["veto"] = True
        self.assert_blocked(check(t, bid="100.40", ask="100.50"), "vetoes volume")
        t = marketable()
        del t["review"]["veto_review"]["macd"]
        self.assert_blocked(check(t, bid="100.40", ask="100.50"), "veto_review.macd")

    def test_ask_above_entry_max_blocks_chasing(self) -> None:
        self.assert_blocked(check(marketable(), bid="101.10", ask="101.50"), "do not chase")

    def test_passive_limit_at_or_above_ask_is_not_passive(self) -> None:
        self.assert_blocked(check(bid="99.50", ask="100.00"), "would fill immediately")

    def test_stop_must_be_below_bid(self) -> None:
        self.assert_blocked(check(bid="94.00", ask="100.20"), "not below bid")

    def test_quote_problems(self) -> None:
        self.assert_blocked(check(bid="101", ask="100"), "crossed")
        self.assert_blocked(check(bid="", ask="100.2"), "broker bid")

    def test_existing_order_or_position_blocks_a_second_entry(self) -> None:
        order = {"order_id": "O-1", "role": "ENTRY", "status": "OPEN", "filled_qty": 0,
                 "terms": {"quantity": 100}}
        self.assert_blocked(check(ticket(orders=[order])), "already has an order")


class AShare(Blocks):
    def test_price_limit_band_and_limit_up_ask(self) -> None:
        cfg = {"price_limit_pct": 10}
        up = check(a_share(), bid="11.20", ask="11.22", cfg=cfg, prev_close="10.20")
        self.assert_blocked(up, "limit-up")
        out = check(a_share(entry_planned="12.00", entry_max="12.00", targets=[{"price": "13.00"}],
                            capital_budget="1200.00", risk_amount="250.00",
                            max_loss_amount="260.00", reward_amount="100.00", r_multiple="0.40",
                            risk_budget="260.00", min_reward_risk=None, decision_lane="A_CIRCLE", setup_quality="A"),
                    bid="10.05", ask="12.10", cfg=cfg, prev_close="10.20")
        self.assert_blocked(out, "price-limit band")

    def test_tick_check(self) -> None:
        self.assert_blocked(check(a_share(), bid="10.05", ask="10.10", cfg={"tick": "0.03"}),
                            "tick")


# ------------------------------------------------------------------------------ protective


def open_position(**overrides: object) -> dict:
    base = ticket(
        state="POSITION_OPEN", journal_state="POSITION_OPEN",
        position={"position_id": "X-1", "ticket_id": "T-1", "market": "US", "symbol": "AAA",
                  "entry_qty": 100, "exit_qty": 0, "open_qty": 100, "closed": False,
                  "avg_entry_price": "100.0000", "fees_total": "0.00", "fills": []},
        orders=[{"order_id": "O-1", "role": "ENTRY", "status": "FILLED", "filled_qty": 100,
                 "terms": {"quantity": 100}}])
    base.update(overrides)
    return base


class StopSemantics(Blocks):
    CONFIRM = dict(activation="CLOSE_CONFIRM",
                   basis={"kind": "ENTRY_CANDLE_LOW", "level": "95.00",
                          "evidence": "buy candle low from the thesis"},
                   broker_implementation="close alert at 95.00; after the close, sell manually")
    RECLAIM = dict(activation="NEXT_SESSION_FAILURE_TO_RECLAIM", reclaim_by="next session 10:00",
                   basis={"kind": "WHITE_LINE", "level": "95.00", "evidence": "white line"},
                   broker_implementation="check at 10:00; if not reclaimed, sell manually")

    def test_missing_stop_semantics_blocks_every_execution_audit(self) -> None:
        self.assert_blocked(check(with_stop(ticket(), None)), "review.stop_semantics is missing")
        self.assert_blocked(audit.protective(with_stop(open_position(), None), AUDIT_OK, "95.00",
                                             "94.50", "100"), "review.stop_semantics is missing")
        self.assert_blocked(check(with_stop(ticket(), "INTRADAY_HARD")), "must be a JSON object")

    def test_malformed_or_unsupported_semantics_block(self) -> None:
        good = stop_semantics()
        cases = {
            "unsupported keys": {**good, "extra": 1},
            "exactly": {**good, "basis": {"kind": "WHITE_LINE", "level": "95.00"}},
            "basis.kind": {**good, "basis": {**good["basis"], "kind": "MOVING_AVERAGE"}},
            "basis.level must": {**good, "basis": {**good["basis"], "level": 95.0}},
            "positive decimal TEXT": {**good, "basis": {**good["basis"], "level": "abc"}},
            "basis.evidence": {**good, "basis": {**good["basis"], "evidence": "  "}},
            "stop_semantics.activation": {**good, "activation": "intraday_hard"},
            "broker_implementation": {**good, "broker_implementation": ""},
            "reclaim_by": {**good, "reclaim_by": 5},
        }
        for fragment, sem in cases.items():
            self.assert_blocked(check(with_stop(ticket(), sem)), fragment)
        self.assert_blocked(check(with_stop(ticket(), {k: v for k, v in good.items()
                                                       if k != "activation"})),
                            "stop_semantics.activation")

    def test_broker_implementation_is_optional_only_for_intraday_hard(self) -> None:
        hard = stop_semantics()
        del hard["broker_implementation"]
        self.assertEqual(check(with_stop(ticket(), hard))["blockers"], [])
        self.assert_blocked(check(with_stop(ticket(), {**hard, "broker_implementation": " "})),
                            "broker_implementation must be non-empty text when present")
        for base in (self.CONFIRM, self.RECLAIM):
            for value in ("missing", "", "  ", 5):
                sem = stop_semantics(**base)
                if value == "missing":
                    del sem["broker_implementation"]
                else:
                    sem["broker_implementation"] = value
                self.assert_blocked(check(with_stop(ticket(), sem)),
                                    f"{base['activation']} needs a non-empty "
                                    "stop_semantics.broker_implementation")

    def test_intraday_hard_stop_trigger_must_equal_basis_level(self) -> None:
        sem = stop_semantics(basis={"kind": "WHITE_LINE", "level": "95.50", "evidence": "x"})
        self.assert_blocked(check(with_stop(ticket(), sem)), "must equal the persisted stop_trigger")

    def test_intraday_hard_pre_submit_shows_the_live_protective_stop_limit(self) -> None:
        result = check()
        self.assertEqual(result["verdict"], "READY_FOR_HUMAN_CONFIRMATION")
        self.assertEqual(result["stop_semantics"]["activation"], "INTRADAY_HARD")
        self.assertEqual(result["protective_plan"]["description"],
                         "SELL stop-limit: trigger 95.00 >= limit 94.50")
        self.assertNotIn("human_only_stop_plan", result)

    def test_non_hard_pre_submit_renders_no_live_stop_only_a_human_procedure(self) -> None:
        for extra in (self.CONFIRM, self.RECLAIM):
            result = check(with_stop(ticket(), stop_semantics(**extra)))
            self.assertEqual(result["blockers"], [])
            self.assertEqual(result["verdict"], "READY_FOR_HUMAN_CONFIRMATION")
            self.assertNotIn("protective_plan", result)
            plan = result["human_only_stop_plan"]
            self.assertIs(plan["live_broker_stop"], False)
            self.assertEqual(plan["human_only_procedure"], extra["broker_implementation"])
            self.assertEqual(plan["activation"], extra["activation"])
            text = json.dumps(result, ensure_ascii=False)
            self.assertNotIn("SELL stop-limit", text)
            self.assertNotIn("gap-through", text)
            self.assertTrue(any(extra["activation"] in w for w in result["warnings"]))

    def test_reclaim_deadline_is_required_for_next_session_failure(self) -> None:
        for reclaim in (None, "", "  "):
            sem = stop_semantics(**{**self.RECLAIM, "reclaim_by": reclaim})
            self.assert_blocked(check(with_stop(ticket(), sem)), "needs a non-empty")
        no_key = stop_semantics(**self.RECLAIM)
        del no_key["reclaim_by"]
        self.assert_blocked(check(with_stop(ticket(), no_key)), "reclaim_by")
        self.assertEqual(check(with_stop(ticket(), stop_semantics(**self.CONFIRM)))["blockers"], [])
        self.assertEqual(check(with_stop(ticket(), stop_semantics(**self.RECLAIM)))["blockers"], [])

    def test_reclaim_by_is_allowed_only_for_next_session_failure_to_reclaim(self) -> None:
        for base in (stop_semantics(), stop_semantics(**self.CONFIRM)):
            for value in ("next session 10:00", None, "", 5):
                self.assert_blocked(check(with_stop(ticket(), {**base, "reclaim_by": value})),
                                    "reclaim_by is allowed only for NEXT_SESSION_FAILURE_TO_RECLAIM")

    def test_basis_level_must_equal_stop_trigger_for_every_activation(self) -> None:
        for base in (stop_semantics(), stop_semantics(**self.CONFIRM), stop_semantics(**self.RECLAIM)):
            self.assertEqual(check(with_stop(ticket(), base))["blockers"], [], base["activation"])
            for other in ("95.50", "94.99", "96.00"):
                sem = {**base, "basis": {**base["basis"], "level": other}}
                self.assert_blocked(check(with_stop(ticket(), sem)),
                                    "must equal the persisted stop_trigger 95.00 for every activation")
            same_value = {**base, "basis": {**base["basis"], "level": "95.0000"}}
            self.assertEqual(check(with_stop(ticket(), same_value))["blockers"], [], base["activation"])

    def test_protective_blocks_when_activation_is_not_intraday_hard(self) -> None:
        for extra in (self.CONFIRM, self.RECLAIM):
            t = with_stop(open_position(), stop_semantics(**extra))
            result = audit.protective(t, AUDIT_OK, "95.00", "94.50", "100")
            self.assert_blocked(result, "not INTRADAY_HARD")
            self.assertNotIn("protective_order", result)
            self.assertIs(result["human_only_stop_plan"]["live_broker_stop"], False)

    def test_protective_passes_for_intraday_hard(self) -> None:
        result = audit.protective(open_position(), AUDIT_OK, "95.00", "94.50", "100")
        self.assertEqual(result["verdict"], "READY_FOR_HUMAN_CONFIRMATION")

    def test_check_args_alone_cannot_gate_attach_stop(self) -> None:
        # check-args has no ticket state; the state-aware stop gate is `protective`.
        args = {"ticket_id": "T-1", "session_date": "20261027", "submitted_by": "human:alice",
                "occurred_at": "2026-10-27T09:33:00-04:00", "idempotency_key": "k" * 32}
        self.assertEqual(audit.check_args("attach_stop", args)["verdict"], "ARGS_OK")


class Protective(Blocks):
    def run_protective(self, t: dict | None = None, *, trigger: str = "95.00",
                       limit: str = "94.50", shares: str = "100",
                       svc: object = AUDIT_OK) -> dict:
        return audit.protective(open_position() if t is None else t, svc, trigger, limit, shares)

    def test_matching_plan_passes_with_gap_warning(self) -> None:
        result = self.run_protective()
        self.assertEqual(result["verdict"], "READY_FOR_HUMAN_CONFIRMATION")
        self.assertEqual(result["loss_at_stop_trigger_before_exit_fee"], "500.00")
        self.assertEqual(result["loss_if_stop_fills_at_limit_before_exit_fee"], "550.00")
        self.assertEqual(result["protected_shares_after"], 100)
        self.assertTrue(any("gap-through" in w for w in result["warnings"]))

    def test_approval_gate_applies_after_the_fill_too(self) -> None:
        self.assert_blocked(self.run_protective(open_position(approval=approval(terms_sha256="b" * 64))),
                            "does not match")
        self.assert_blocked(self.run_protective(open_position(approval=None)),
                            "state.approval is missing")
        t = open_position(approved_by="agent:x", events=events(approved_by="agent:x"))
        self.assert_blocked(self.run_protective(t), "not 'human:<name>'")
        self.assert_blocked(self.run_protective(open_position(state="APPROVED",
                                                              journal_state="APPROVED")),
                            "needs ['PARTIALLY_FILLED', 'POSITION_OPEN']")

    def test_orientation_looser_limit_and_stop_above_entry_block(self) -> None:
        self.assert_blocked(self.run_protective(trigger="94.00", limit="95.00"), "orientation wrong")
        self.assert_blocked(self.run_protective(trigger="95.00", limit="94.00"), "looser")
        self.assert_blocked(self.run_protective(trigger="101.00", limit="100.50"), "loss-side")

    def test_oversize_partial_cover_and_stacking(self) -> None:
        self.assert_blocked(self.run_protective(shares="101"), "exceed the open position")
        partial = self.run_protective(shares="60")
        self.assertEqual(partial["verdict"], "READY_FOR_HUMAN_CONFIRMATION")
        self.assertTrue(any("unprotected" in w for w in partial["warnings"]))
        live = {"order_id": "O-2", "role": "PROTECTIVE_STOP", "status": "OPEN", "filled_qty": 0,
                "terms": {"quantity": 60}}
        stacked = open_position()
        stacked["orders"].append(live)
        self.assert_blocked(self.run_protective(stacked, shares="60"), "already cover 60")

    def test_plan_drift_and_no_position(self) -> None:
        result = self.run_protective(trigger="96.00", limit="95.50")
        self.assertTrue(any("differs from the approved stop_trigger" in w for w in result["warnings"]))
        self.assert_blocked(self.run_protective(open_position(position=None)), "no open position")

    def test_a_share_lot_and_t_plus_one(self) -> None:
        t = a_share(state="POSITION_OPEN", journal_state="POSITION_OPEN",
                    position={"open_qty": 200, "entry_qty": 200, "exit_qty": 0, "closed": False,
                              "avg_entry_price": "10.0000", "fees_total": "0.00", "fills": []},
                    orders=[], quantity=200, capital_budget="2000.00", risk_amount="100.00",
                    max_loss_amount="120.00", reward_amount="200.00", risk_budget="120.00")
        ok = audit.protective(t, AUDIT_OK, "9.50", "9.40", "200")
        self.assertEqual(ok["blockers"], [])
        self.assertTrue(any("T+1" in w for w in ok["warnings"]))
        self.assert_blocked(audit.protective(t, AUDIT_OK, "9.50", "9.40", "150"), "100-share")


# -------------------------------------------------------------------------------- operations


def submit_args(**overrides: object) -> dict:
    base = {"ticket_id": "T-1", "order_type": "LIMIT", "quantity": 100, "limit_price": "100.00",
            "tif": "DAY", "session_date": "20261027", "submitted_by": "human:alice",
            "occurred_at": "2026-10-27T09:31:00-04:00", "idempotency_key": "k" * 32,
            "broker_ref": "BR-1", "evidence": {"file": "order.png", "sha256": "e" * 64}}
    base.update(overrides)
    return base


def fill_args(**overrides: object) -> dict:
    base = {"order_id": "O-1", "quantity": 100, "price": "100.00", "fee": "1.00",
            "session_date": "20261027", "occurred_at": "2026-10-27T09:32:00-04:00",
            "recorded_by": "human:alice", "idempotency_key": "k" * 32, "external_ref": "EX-1"}
    base.update(overrides)
    return base


class CheckArgs(Blocks):
    def test_valid_submit_and_fill_arguments(self) -> None:
        self.assertEqual(audit.check_args("submit_order", submit_args())["verdict"], "ARGS_OK")
        self.assertEqual(audit.check_args("record_fill", fill_args())["verdict"], "ARGS_OK")
        self.assertEqual(audit.check_args("record_exit_fill", fill_args(recorded_by="import:ibkr"))
                         ["verdict"], "ARGS_OK")
        self.assertEqual(audit.check_args("attach_stop", {
            "ticket_id": "T-1", "session_date": "20261027", "submitted_by": "human:alice",
            "occurred_at": "2026-10-27T09:33:00-04:00", "idempotency_key": "k" * 32,
            "stop_trigger": "95.00", "stop_limit": "94.50", "quantity": 100})["verdict"], "ARGS_OK")

    def test_approve_draft_and_review_are_not_available(self) -> None:
        for op in ("approve", "create_draft", "mark_reviewed"):
            self.assert_blocked(audit.check_args(op, {}), "not available to this skill")
        self.assert_blocked(audit.check_args("migrate", {}), "unknown operation")

    def test_unknown_missing_and_forbidden_keys(self) -> None:
        self.assert_blocked(audit.check_args("submit_order", submit_args(status="approved")),
                            "unexpected key")
        args = submit_args()
        del args["idempotency_key"]
        self.assert_blocked(audit.check_args("submit_order", args), "missing required key")
        self.assert_blocked(audit.check_args("submit_order", submit_args(now="2026-10-27")),
                            "must never be passed")
        self.assert_blocked(audit.check_args("submit_order", submit_args(human_confirmed=True)),
                            "must never be passed")

    def test_types_follow_the_service_not_the_chat(self) -> None:
        self.assert_blocked(audit.check_args("submit_order", submit_args(limit_price=100.0)),
                            "decimal TEXT")
        self.assert_blocked(audit.check_args("submit_order", submit_args(quantity="100")), "quantity")
        self.assert_blocked(audit.check_args("submit_order", submit_args(quantity=True)), "quantity")
        self.assert_blocked(audit.check_args("submit_order", submit_args(session_date="2026-10-27")),
                            "YYYYMMDD")
        self.assert_blocked(audit.check_args("submit_order", submit_args(occurred_at="2026-10-27T09:31:00")),
                            "UTC offset")
        self.assert_blocked(audit.check_args("record_fill", fill_args(fee=1.5)), "decimal TEXT")

    def test_actor_kinds_match_the_permission_table(self) -> None:
        self.assert_blocked(audit.check_args("submit_order", submit_args(submitted_by="import:x")),
                            "kind in ['human']")
        self.assert_blocked(audit.check_args("submit_order", submit_args(submitted_by="review:x")),
                            "kind in ['human']")
        self.assert_blocked(audit.check_args("record_fill", fill_args(recorded_by="review:x")),
                            "kind in ['human', 'import']")
        self.assert_blocked(audit.check_args("record_fill", fill_args(recorded_by="human:")),
                            "recorded_by")

    def test_entry_must_be_a_limit_order(self) -> None:
        self.assert_blocked(audit.check_args("submit_order", submit_args(order_type="MARKET")),
                            "order_type must be")
        args = submit_args()
        del args["limit_price"]
        self.assert_blocked(audit.check_args("submit_order", args), "limit_price")
        self.assert_blocked(audit.check_args("submit_order", submit_args(tif="GTD")), "GTD")


def terminal(state: str = "CLOSED", **overrides: object) -> dict:
    """A terminal ticket in the historical shape: no stop_semantics."""
    fields: dict = dict(state=state, journal_state=state)
    if state == "CLOSED":
        fields["position"] = {"open_qty": 0, "entry_qty": 100, "exit_qty": 100, "closed": True,
                              "avg_entry_price": "100.0000", "fees_total": "0.00", "fills": []}
    fields.update(overrides)
    return with_stop(ticket(**fields), None)


def review_args(**overrides: object) -> dict:
    base = {"ticket_id": "T-1", "reviewed_by": "human:alice", "outcome": audit.OUTCOME_DONE,
            "note": "followed the plan", "occurred_at": "2026-10-28T09:00:00-04:00",
            "idempotency_key": "r" * 32}
    base.update(overrides)
    return base


class PostTradeReview(Blocks):
    def run_review(self, t: object = None, args: object = None, svc: object = AUDIT_OK) -> dict:
        return audit.post_trade_review(terminal() if t is None else t, svc,
                                       review_args() if args is None else args)

    def test_historical_closed_ticket_without_stop_semantics_is_reviewable(self) -> None:
        result = self.run_review()
        self.assertEqual((result["verdict"], result["blockers"]), ("ARGS_OK", []))
        self.assert_blocked(check(terminal()), "needs ['APPROVED']")

    def test_outcome_vocabulary_is_the_services(self) -> None:
        self.assertEqual((audit.OUTCOME_MISSED, audit.OUTCOME_DONE, audit.OUTCOME_WRONG),
                         ("机会识别成功、执行未覆盖", "机会识别成功、执行完成", "机会识别失败"))

    def test_state_must_be_exactly_terminal_and_not_reviewed(self) -> None:
        for state in ("DRAFT", "APPROVED", "ORDER_SUBMITTED", "PARTIALLY_FILLED", "POSITION_OPEN"):
            self.assert_blocked(self.run_review(terminal(state=state, journal_state=state)),
                                "needs exactly one of")
        self.assert_blocked(self.run_review(terminal(state="REVIEWED", journal_state="REVIEWED")),
                            "already REVIEWED")
        self.assert_blocked(self.run_review(terminal(state="closed", journal_state="closed")), "state")
        self.assert_blocked(self.run_review(terminal(journal_state="POSITION_OPEN")), "state journal")

    def test_service_audit_must_be_clean(self) -> None:
        self.assert_blocked(self.run_review(svc=None), "service audit")
        self.assert_blocked(self.run_review(svc={**AUDIT_OK, "ok": False}), "service audit")

    def test_ticket_id_must_match_the_state(self) -> None:
        self.assert_blocked(self.run_review(args=review_args(ticket_id="T-2")), "not the state's")

    def test_actor_must_be_a_named_human(self) -> None:
        for actor in ("review:codex", "import:x", "human:", "human", None):
            self.assert_blocked(self.run_review(args=review_args(reviewed_by=actor)), "human:<name>")

    def test_outcome_must_be_service_supported_and_compatible_with_state(self) -> None:
        done, missed, wrong = audit.OUTCOME_DONE, audit.OUTCOME_MISSED, audit.OUTCOME_WRONG
        for outcome in (done, wrong):
            self.assertEqual(self.run_review(args=review_args(outcome=outcome))["verdict"], "ARGS_OK")
        self.assert_blocked(self.run_review(args=review_args(outcome=missed)),
                            "not allowed for state CLOSED")
        self.assert_blocked(self.run_review(args=review_args(outcome="success")), "not allowed")
        for state in ("CANCELLED", "EXPIRED", "REJECTED"):
            t = terminal(state=state)
            for outcome in (missed, wrong):
                self.assertEqual(self.run_review(t, review_args(outcome=outcome))["verdict"], "ARGS_OK")
            self.assert_blocked(self.run_review(t, review_args(outcome=done)), f"state {state}")
        with_position = terminal(state="CANCELLED", position={"open_qty": 50})
        self.assert_blocked(self.run_review(with_position, review_args(outcome=wrong)), "has a position")

    def test_note_is_required_and_never_inferred(self) -> None:
        for note in ("", "   ", None, 5):
            self.assert_blocked(self.run_review(args=review_args(note=note)), "note")
        for key in ("note", "outcome"):
            args = review_args()
            del args[key]
            self.assert_blocked(self.run_review(args=args), f"missing required key '{key}'")

    def test_time_key_and_annotation_rules(self) -> None:
        self.assert_blocked(self.run_review(args=review_args(occurred_at="2026-10-28T09:00:00")),
                            "UTC offset")
        self.assert_blocked(self.run_review(args=review_args(idempotency_key=" ")), "idempotency_key")
        self.assert_blocked(self.run_review(args=review_args(annotation_id="")), "annotation_id")
        self.assertEqual(self.run_review(args=review_args(annotation_id="A-1"))["verdict"], "ARGS_OK")
        self.assert_blocked(self.run_review(args=review_args(now="2026-10-28")), "unexpected key")
        self.assert_blocked(self.run_review(args=[1]), "args JSON must be an object")

    def test_mark_reviewed_stays_out_of_generic_check_args(self) -> None:
        self.assertNotIn("mark_reviewed", audit.OP_SPECS)
        self.assert_blocked(audit.check_args("mark_reviewed", review_args()), "post-trade-review")

    def test_cli_prints_args_ok_and_never_writes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            files = {n: Path(folder, n + ".json") for n in ("state", "audit", "args")}
            files["state"].write_text(json.dumps(terminal()), encoding="utf-8")
            files["audit"].write_text(json.dumps(AUDIT_OK), encoding="utf-8")
            files["args"].write_text(json.dumps(review_args()), encoding="utf-8")
            before = sorted(p.name for p in Path(folder).iterdir())
            saved, out = sys.argv, io.StringIO()
            sys.argv = ["audit_ticket.py", "post-trade-review", "--state", str(files["state"]),
                        "--service-audit", str(files["audit"]), "--args-json", str(files["args"])]
            try:
                with contextlib.redirect_stdout(out):
                    code = audit.main()
            finally:
                sys.argv = saved
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), before)
        payload = json.loads(out.getvalue())
        self.assertEqual((code, payload["verdict"]), (0, "ARGS_OK"))


def historical_state(**overrides: object) -> dict:
    base = {"ticket_id": "H-1", "historical_id": "H-1", "historical_import": True,
            "pre_system_trade": True, "state": "CLOSED", "journal_state": "CLOSED",
            "execution_state": "CLOSED"}
    base.update(overrides)
    return base


def historical_args(**overrides: object) -> dict:
    base = {"historical_id": "H-1", "reviewed_by": "human:alice", "outcome": audit.OUTCOME_DONE,
            "note": "followed the plan", "occurred_at": "2026-10-28T09:00:00-04:00",
            "idempotency_key": "h" * 32}
    base.update(overrides)
    return base


HIST_AUDIT_OK = {"available": True, "ok": True, "tickets": 0, "historical_trades": 1, "issues": []}


class HistoricalPostTradeReview(Blocks):
    def run_review(self, state: object = None, args: object = None, svc: object = HIST_AUDIT_OK) -> dict:
        return audit.historical_post_trade_review(
            historical_state() if state is None else state, svc,
            historical_args() if args is None else args)

    def test_closed_historical_import_is_reviewable(self) -> None:
        result = self.run_review()
        self.assertEqual((result["verdict"], result["blockers"], result["op"]),
                         ("ARGS_OK", [], "mark_historical_reviewed"))
        self.assertEqual(result["historical_id"], "H-1")
        for outcome in (audit.OUTCOME_DONE, audit.OUTCOME_WRONG):
            self.assertEqual(self.run_review(args=historical_args(outcome=outcome))["verdict"], "ARGS_OK")

    def test_markers_and_state_are_required(self) -> None:
        for key in ("historical_import", "pre_system_trade"):
            self.assert_blocked(self.run_review(historical_state(**{key: False})), f"state.{key}")
            state = historical_state()
            del state[key]
            self.assert_blocked(self.run_review(state), f"state.{key}")
        self.assert_blocked(self.run_review(historical_state(state="REVIEWED", journal_state="REVIEWED")),
                            "already REVIEWED")
        for current in ("POSITION_OPEN", "CANCELLED", "EXPIRED", "REJECTED", "closed", None):
            self.assert_blocked(self.run_review(historical_state(state=current, journal_state=current)),
                                "exactly 'CLOSED'")
        self.assert_blocked(self.run_review(historical_state(journal_state="POSITION_OPEN")),
                            "state journal")
        self.assert_blocked(self.run_review([1]), "not a JSON object")

    def test_service_audit_must_be_clean(self) -> None:
        self.assert_blocked(self.run_review(svc=None), "service audit")

    def test_service_audit_must_be_scoped_to_exactly_this_historical_trade(self) -> None:
        self.assertEqual(self.run_review(svc=HIST_AUDIT_OK)["verdict"], "ARGS_OK")
        unscoped = {"available": True, "ok": True, "tickets": 0, "issues": []}  # no historical_trades key
        bad = {"missing historical_trades (unscoped clean audit)": unscoped,
               "all-database audit (many tickets)": {**HIST_AUDIT_OK, "tickets": 7, "historical_trades": 3},
               "tickets present": {**HIST_AUDIT_OK, "tickets": 1},
               "two historical trades": {**HIST_AUDIT_OK, "historical_trades": 2},
               "zero historical trades": {**HIST_AUDIT_OK, "historical_trades": 0},
               "string count": {**HIST_AUDIT_OK, "historical_trades": "1"},
               "bool count": {**HIST_AUDIT_OK, "historical_trades": True},
               "missing tickets": {k: v for k, v in HIST_AUDIT_OK.items() if k != "tickets"},
               "unavailable": {**HIST_AUDIT_OK, "available": False}}
        for label, svc in bad.items():
            result = self.run_review(svc=svc)
            self.assertEqual(result["verdict"], "BLOCKED", label)
            self.assertTrue(any("scoped to exactly this historical trade" in b for b in result["blockers"]), label)
        self.assert_blocked(self.run_review(svc={**HIST_AUDIT_OK, "ok": False}), "service audit")
        self.assert_blocked(self.run_review(svc={**HIST_AUDIT_OK, "issues": ["x"]}), "service audit")

    def test_args_rules(self) -> None:
        self.assert_blocked(self.run_review(args=historical_args(historical_id="H-2")), "not the state's")
        for actor in ("review:codex", "import:x", "human:", "human", None):
            self.assert_blocked(self.run_review(args=historical_args(reviewed_by=actor)), "human:<name>")
        for outcome in (audit.OUTCOME_MISSED, "success", None):
            self.assert_blocked(self.run_review(args=historical_args(outcome=outcome)), "not allowed")
        for key in ("note", "idempotency_key"):
            for value in ("", "  ", None, 5):
                self.assert_blocked(self.run_review(args=historical_args(**{key: value})), key)
        for key in ("historical_id", "reviewed_by", "outcome", "note", "occurred_at", "idempotency_key"):
            args = historical_args()
            del args[key]
            self.assert_blocked(self.run_review(args=args), f"missing required key '{key}'")
        self.assert_blocked(self.run_review(args=historical_args(occurred_at="2026-10-28T09:00:00")),
                            "UTC offset")
        self.assert_blocked(self.run_review(args=historical_args(annotation_id="")), "annotation_id")
        self.assert_blocked(self.run_review(args=historical_args(annotation_id=None)), "annotation_id")
        self.assertEqual(self.run_review(args=historical_args(annotation_id="A-1"))["verdict"], "ARGS_OK")
        self.assert_blocked(self.run_review(args=historical_args(ticket_id="H-1")), "unexpected key")
        self.assert_blocked(self.run_review(args=historical_args(now="2026-10-28")), "unexpected key")
        self.assert_blocked(self.run_review(args=[1]), "args JSON must be an object")

    def test_generic_review_and_check_args_block_historical_imports(self) -> None:
        self.assert_blocked(audit.post_trade_review(historical_state(), AUDIT_OK, review_args(ticket_id="H-1")),
                            "historical import")
        self.assert_blocked(audit.post_trade_review(dict(terminal(), historical_import=True), AUDIT_OK,
                                                    review_args()), "historical import")
        self.assertIn("mark_historical_reviewed", audit.FORBIDDEN_OPS)
        self.assertNotIn("mark_historical_reviewed", audit.OP_SPECS)
        self.assert_blocked(audit.check_args("mark_historical_reviewed", historical_args()),
                            "historical-post-trade-review")

    def test_cli_prints_args_ok_and_never_writes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            files = {n: Path(folder, n + ".json") for n in ("state", "audit", "args")}
            files["state"].write_text(json.dumps(historical_state()), encoding="utf-8")
            files["audit"].write_text(json.dumps(HIST_AUDIT_OK), encoding="utf-8")
            files["args"].write_text(json.dumps(historical_args()), encoding="utf-8")
            before = sorted(p.name for p in Path(folder).iterdir())
            saved, out = sys.argv, io.StringIO()
            sys.argv = ["audit_ticket.py", "historical-post-trade-review", "--state", str(files["state"]),
                        "--service-audit", str(files["audit"]), "--args-json", str(files["args"])]
            try:
                with contextlib.redirect_stdout(out):
                    code = audit.main()
            finally:
                sys.argv = saved
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), before)
        payload = json.loads(out.getvalue())
        self.assertEqual((code, payload["verdict"]), (0, "ARGS_OK"))


class IdempotencyKey(unittest.TestCase):
    def test_same_evidence_same_key_different_op_or_evidence_differs(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder, "a.png"), Path(folder, "b.png")
            a.write_bytes(b"fill-1")
            b.write_bytes(b"fill-2")
            first = audit.idempotency_key("T-1", "record_fill", None, a)
            again = audit.idempotency_key("T-1", "record_fill", None, a)
            other_op = audit.idempotency_key("T-1", "record_exit_fill", None, a)
            other_file = audit.idempotency_key("T-1", "record_fill", None, b)
        self.assertEqual(first["idempotency_key"], again["idempotency_key"])
        self.assertNotEqual(first["idempotency_key"], other_op["idempotency_key"])
        self.assertNotEqual(first["idempotency_key"], other_file["idempotency_key"])

    def test_requires_evidence_and_an_allowed_op(self) -> None:
        with self.assertRaises(ValueError):
            audit.idempotency_key("T-1", "record_fill", None, None)
        with self.assertRaises(ValueError):
            audit.idempotency_key("T-1", "approve", "ORD-1", None)


# ----------------------------------------------------------------------------- scale-up


def scale_result(**overrides: object) -> dict:
    base = {
        "eligible": True, "proposal_only": True, "mutates_tickets": False, "auto_approve": False,
        "reasons": [], "strategy": "b1", "market": None,
        "gates": {name: {"value": "x", "required": "y", "passed": True}
                  for name in ("sample_size", "expectancy", "drawdown", "plan_adherence")},
        "policy": {"min_sample_size": 5, "max_drawdown_r": "3", "min_plan_adherence": "0.8",
                   "source": "account policy"},
        "metrics": {"sample_size": 6, "expectancy_r": "0.4", "max_drawdown_r": "1.5",
                    "plan_adherence": "1.0", "ticket_ids": [f"T-{i}" for i in range(6)]},
        "policy_sha256": "b" * 64, "sample_sha256": "c" * 64}
    base.update(overrides)
    return base


class ScaleUpProposal(Blocks):
    def test_eligible_result_is_only_a_proposal(self) -> None:
        result = audit.scale_up_proposal(scale_result(), "b1")
        self.assertEqual(result["verdict"], "PROPOSAL_ONLY_FOR_HUMAN_DECISION")
        self.assertIn("NEW draft ticket", result["next_step"])

    def test_not_eligible_single_trade_and_wrong_strategy_block(self) -> None:
        self.assert_blocked(audit.scale_up_proposal(scale_result(eligible=False, reasons=["x"]), "b1"),
                            "not eligible")
        one = scale_result()
        one["metrics"] = {**one["metrics"], "sample_size": 1, "ticket_ids": ["T-0"]}
        self.assert_blocked(audit.scale_up_proposal(one, "b1"), "more than one real trade")
        self.assert_blocked(audit.scale_up_proposal(scale_result(), "b2"), "exact strategy")

    def test_flags_gates_and_reproducibility_are_required(self) -> None:
        self.assert_blocked(audit.scale_up_proposal(scale_result(auto_approve=True), "b1"),
                            "proposal-only")
        failed = scale_result()
        failed["gates"]["drawdown"]["passed"] = False
        self.assert_blocked(audit.scale_up_proposal(failed, "b1"), "gate")
        self.assert_blocked(audit.scale_up_proposal(scale_result(policy_sha256=None), "b1"),
                            "policy_sha256")
        no_policy = scale_result()
        del no_policy["policy"]
        self.assert_blocked(audit.scale_up_proposal(no_policy, "b1"), "caller policy")


class CommandLine(unittest.TestCase):
    def run_main(self, *argv: str) -> tuple[int, dict]:
        saved, out = sys.argv, io.StringIO()
        sys.argv = ["audit_ticket.py", *argv]
        try:
            with contextlib.redirect_stdout(out):
                code = audit.main()
        finally:
            sys.argv = saved
        return code, json.loads(out.getvalue())

    def test_bad_json_fails_closed_with_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "t.json")
            path.write_text("{not json", encoding="utf-8")
            code, payload = self.run_main("pre-submit", "--state", str(path), "--service-audit",
                                          str(path), "--session-date", "20261027", "--bid", "1",
                                          "--ask", "2")
        self.assertEqual(code, 2)
        self.assertEqual(payload["verdict"], "BLOCKED")

    def test_service_state_file_round_trips_through_the_cli(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            state, svc = Path(folder, "state.json"), Path(folder, "audit.json")
            state.write_text(json.dumps(ticket()), encoding="utf-8")
            svc.write_text(json.dumps(AUDIT_OK), encoding="utf-8")
            missing_cfg = str(Path(folder, "absent.json"))
            code, payload = self.run_main(
                "pre-submit", "--state", str(state), "--service-audit", str(svc),
                "--session-date", "20261027", "--bid", "100.10",
                "--ask", "100.20", "--now", "2026-10-27T14:00:00+00:00", "--config", missing_cfg)
            self.assertEqual((code, payload["verdict"]), (0, "READY_FOR_HUMAN_CONFIRMATION"))
            state.write_text(json.dumps(ticket(approval=None)), encoding="utf-8")
            code, payload = self.run_main(
                "pre-submit", "--state", str(state), "--service-audit", str(svc),
                "--session-date", "20261027", "--bid",
                "100.10", "--ask", "100.20", "--now", "2026-10-27T14:00:00+00:00",
                "--config", missing_cfg)
            self.assertEqual((code, payload["verdict"]), (2, "BLOCKED"))
            self.assertTrue(any("state.approval is missing" in b for b in payload["blockers"]))


if __name__ == "__main__":
    unittest.main()
