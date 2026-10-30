#!/usr/bin/env python3
"""Behavioural tests for the trade-policy compiler. Offline."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stop_template as st  # noqa: E402
import trade_policy_core as core  # noqa: E402

CUTOFF, NEXT = "20261028", "20261029"
B1_OFF = {"reversal_k": "ABSENT", "white_line_support": "ABSENT", "yellow_line_support": "ABSENT"}
B2_OK = {"prior_low_intact": "PRESENT", "already_risen": "ABSENT", "pullback_after_rise": "ABSENT",
         "s1_present": "ABSENT"}
BRICK = {"first_red_brick": "PRESENT"}


def cand(role, level="10.00", bar=CUTOFF, **extra):
    return {"role": role, "level": level, "bar_date": bar, "evidence": "chart level", **extra}


def key(role, level="10.00", bar="20261026", confirmed="20261027"):
    return cand(role, level, bar, confirmed_on=confirmed, confirmation_evidence="later bar held the low")


def facts(family, states, candidates, timing="SIGNAL_CLOSE", **entry):
    near = timing == "SIGNAL_CLOSE"
    return {"cutoff_date": CUTOFF, "cutoff_phase": "NEAR_CLOSE" if near else "AFTER_CLOSE",
            "observed_families": [family], "states": states, "evidence": "reading",
            "entry": {"timing": timing, "session_date": CUTOFF if near else NEXT, "entry_max": "11.00", **entry},
            "basis_candidates": candidates}


def code(payload):
    result = core.compile_policy(payload)
    return result.get("code", result["status"])


class SixTypes(unittest.TestCase):
    def test_each_type_is_derived_with_its_canonical_kind(self) -> None:
        cases = {
            "B1_KLINE_REVERSAL": facts("B1", {**B1_OFF, "reversal_k": "PRESENT"}, [cand(core.BUY)]),
            "B1_WHITE_LINE_SHORT": facts("B1", {**B1_OFF, "white_line_support": "PRESENT"}, [cand(core.WHITE)]),
            "B1_YELLOW_LINE_SWING": facts("B1", {**B1_OFF, "yellow_line_support": "PRESENT"}, [cand(core.YELLOW)]),
            "B2_FRESH_CONFIRMATION": facts("B2", B2_OK, [cand(core.PRIOR_LOW, bar="20261020")]),
            "B2_RISEN_PULLBACK": facts("B2", {**B2_OK, "already_risen": "PRESENT", "pullback_after_rise": "PRESENT"},
                                       [cand(core.PRIOR_LOW, bar="20261020")]),
            "BRICK_ZERO_DAY": facts("BRICK", BRICK, [cand(core.BUY)]),
        }
        self.assertEqual(sorted(cases), sorted(st.TRADE_TYPES))
        for trade_type, payload in cases.items():
            result = core.compile_policy(payload)
            self.assertEqual((result["status"], result["trade_type"]), (core.COMPLETE, trade_type))
            self.assertEqual(result["stop_semantics"]["basis"]["kind"], st.TRADE_TYPES[trade_type]["basis_kind"])
            self.assertEqual(result["stop_semantics"]["activation"], st.TRADE_TYPES[trade_type]["activation"])


class Ambiguity(unittest.TestCase):
    def test_ambiguous_or_incomplete_facts_block_with_stable_codes(self) -> None:
        two = {**B1_OFF, "white_line_support": "PRESENT", "yellow_line_support": "PRESENT"}
        self.assertEqual(code(facts("B1", two, [])), "CLASSIFICATION_AMBIGUOUS")
        self.assertEqual(code(facts("B1", B1_OFF, [])), "CLASSIFICATION_NONE")
        self.assertEqual(code(facts("B1", {**B1_OFF, "reversal_k": "UNCLEAR"}, [])), "EVIDENCE_AMBIGUOUS")
        mixed = facts("B1", {**B1_OFF, "reversal_k": "PRESENT"}, [cand(core.BUY)])
        mixed["observed_families"] = ["B1", "BRICK"]
        self.assertEqual(code(mixed), "CLASSIFICATION_AMBIGUOUS")
        self.assertEqual(code(facts("B2", {**B2_OK, "s1_present": "PRESENT"}, [])), "B2_S1_PRESENT")
        self.assertEqual(code(facts("B2", {**B2_OK, "prior_low_intact": "ABSENT"}, [])), "B2_PRIOR_LOW_BROKEN")
        self.assertEqual(code(facts("B2", {**B2_OK, "already_risen": "PRESENT"}, [])), "CLASSIFICATION_NONE")
        self.assertEqual(code(facts("B2", {**B2_OK, "pullback_after_rise": "PRESENT"}, [])), "STATE_CONTRADICTION")
        white = {**B1_OFF, "white_line_support": "PRESENT"}
        self.assertEqual(code(facts("B1", white, [cand(core.YELLOW)])), "BASIS_ROLE_INVALID_FOR_TYPE")
        self.assertEqual(code(facts("B1", white, [cand("PRIOR_SIGNAL_CANDLE_LOW")])), "BASIS_ROLE_UNKNOWN")
        self.assertEqual(code(facts("B1", white, [])), "BASIS_MISSING")


class Timing(unittest.TestCase):
    def test_future_bars_and_future_confirmation_block(self) -> None:
        self.assertEqual(code(facts("BRICK", BRICK, [cand(core.BUY, bar=NEXT)], "NEXT_OPEN")), "BASIS_AFTER_CUTOFF")
        late = key(core.FRACTAL, confirmed=NEXT)
        self.assertEqual(code(facts("BRICK", BRICK, [late], "NEXT_OPEN")), "BASIS_NOT_CONFIRMED_AT_CUTOFF")
        same_day = key(core.REVERSAL_K, bar=CUTOFF, confirmed=CUTOFF)
        self.assertEqual(code(facts("BRICK", BRICK, [cand(core.BUY), same_day])), "BASIS_NOT_CONFIRMED_AT_CUTOFF")

    def test_entry_timing_must_match_the_cutoff(self) -> None:
        payload = facts("BRICK", BRICK, [cand(core.BUY)])
        payload["cutoff_phase"] = "AFTER_CLOSE"
        self.assertEqual(code(payload), "ENTRY_CUTOFF_MISMATCH")
        self.assertEqual(code(facts("BRICK", BRICK, [], "NEXT_OPEN", entry_max=None)), "ENTRY_MAX_NOT_FROZEN")

    def test_impossible_calendar_dates_block(self) -> None:
        for bad in ("20260230", "20261301", "20261032"):
            payload = facts("BRICK", BRICK, [cand(core.BUY)])
            payload["cutoff_date"] = bad
            self.assertEqual(code(payload), "FACT_VALUE_INVALID")
        self.assertEqual(code(facts("BRICK", BRICK, [cand(core.BUY, bar="20260230")])), "FACT_VALUE_INVALID")

    def test_next_session_is_not_a_calendar_rule(self) -> None:
        payload = facts("BRICK", BRICK, [], "NEXT_OPEN")
        payload["entry"]["session_date"] = "20261102"
        self.assertEqual(code(payload), core.ENTRY_GATE_ONLY)

    def test_prior_candle_cannot_pose_as_the_buy_candle(self) -> None:
        self.assertEqual(code(facts("BRICK", BRICK, [cand(core.BUY)], "NEXT_OPEN")), "BUY_CANDLE_DATE_MISMATCH")

    def test_fractal_needs_a_later_bar(self) -> None:
        early = key(core.FRACTAL, confirmed="20261026")
        self.assertEqual(code(facts("BRICK", BRICK, [early], "NEXT_OPEN")), "BOTTOM_FRACTAL_NOT_COMPLETE")


class BrickBasis(unittest.TestCase):
    def test_signal_close_requires_and_uses_buy_candle_low(self) -> None:
        self.assertEqual(code(facts("BRICK", BRICK, [])), "BASIS_MISSING")
        self.assertEqual(code(facts("BRICK", BRICK, [key(core.REVERSAL_K)])), "BASIS_MISSING")
        result = core.compile_policy(facts("BRICK", BRICK, [key(core.REVERSAL_K), cand(core.BUY, "10.0")]))
        self.assertEqual((result["status"], result["basis"]["role"]), (core.COMPLETE, core.BUY))

    def test_next_open_without_key_k_is_gate_only(self) -> None:
        result = core.compile_policy(facts("BRICK", BRICK, [], "NEXT_OPEN"))
        self.assertEqual((result["status"], result["basis"], result["stop_semantics"]),
                         (core.ENTRY_GATE_ONLY, None, None))
        self.assertEqual(result["entry"]["entry_max"], "11.00")

    def test_course_provenance_separates_versions_and_keeps_exits_manual(self) -> None:
        for payload in (facts("BRICK", BRICK, [cand(core.BUY)]), facts("BRICK", BRICK, [], "NEXT_OPEN")):
            provenance = core.compile_policy(payload)["course_provenance"]
            self.assertIn("Price basis", provenance["20260220"])
            self.assertNotIn("red to green", provenance["20260220"])
            self.assertIn("red to green", provenance["20260329"])
            self.assertIn("not automatic gates", provenance["disputed_exits"])
        white = facts("B1", {**B1_OFF, "white_line_support": "PRESENT"}, [cand(core.WHITE)])
        self.assertIsNone(core.compile_policy(white)["course_provenance"])

    def test_key_k_stop_is_not_mislabelled_entry_candle_low(self) -> None:
        both = [key(core.REVERSAL_K), key(core.FRACTAL, "10.0000")]
        result = core.compile_policy(facts("BRICK", BRICK, both, "NEXT_OPEN"))
        self.assertEqual((result["status"], result["stop_semantics"]), (core.STOP_BASIS_ONLY, None))
        self.assertEqual(Decimal_(result["basis"]["level"]), Decimal_("10"))

    def test_conflicts_block(self) -> None:
        keys = [key(core.REVERSAL_K), key(core.FRACTAL, "9.90")]
        self.assertEqual(code(facts("BRICK", BRICK, keys, "NEXT_OPEN")), "BASIS_CONFLICT")
        self.assertEqual(code(facts("BRICK", BRICK, [cand(core.BUY), keys[1]])), "BASIS_CONFLICT")

    def test_confirmation_must_be_independent_and_basis_below_entry_max(self) -> None:
        echoed = key(core.REVERSAL_K)
        echoed["confirmation_evidence"] = echoed["evidence"]
        self.assertEqual(code(facts("BRICK", BRICK, [echoed], "NEXT_OPEN")), "BASIS_CONFIRMATION_MISSING")
        self.assertEqual(code(facts("BRICK", BRICK, [key(core.REVERSAL_K, "11.00")], "NEXT_OPEN")),
                         "BASIS_NOT_BELOW_ENTRY_MAX")


class Selectors(unittest.TestCase):
    def test_selector_inputs_reject_at_any_depth_and_spelling(self) -> None:
        for name in ("trade_type", "basis_kind", "activation", "broker_mode", "template_id", "tradeType", "Basis-Kind"):
            top = facts("BRICK", BRICK, [cand(core.BUY)])
            top[name] = "x"
            self.assertEqual(code(top), "SELECTOR_INPUT_FORBIDDEN")
            nested = facts("BRICK", BRICK, [cand(core.BUY, **{name: "x"})])
            self.assertEqual(code(nested), "SELECTOR_INPUT_FORBIDDEN")

    def test_policy_marker_and_bad_shapes_block_without_raising(self) -> None:
        payload = facts("BRICK", BRICK, [cand(core.BUY)])
        payload["evidence"] = "policy=forged"
        self.assertEqual(code(payload), "EVIDENCE_MARKER_FORBIDDEN")
        self.assertEqual(code([]), "FACTS_NOT_OBJECT")
        self.assertEqual(code({"gap_pct": "2"}), "UNKNOWN_FIELD")


Decimal_ = core.Decimal

if __name__ == "__main__":
    unittest.main()
