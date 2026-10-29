#!/usr/bin/env python3
"""Tests for the deterministic stop-template helper. Offline; reads only repository files."""

from __future__ import annotations

import itertools
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parents[1]
sys.path.insert(0, str(HERE))
import stop_template as st  # noqa: E402

sys.path.insert(0, str(SKILLS / "trade-execution" / "scripts"))
import audit_ticket as auditor  # noqa: E402

PLAYBOOK = (HERE.parent / "references" / "strategy-stop-playbook.md").read_text(encoding="utf-8")
MACHINE_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|/home/")


def run(template_id, setup=None, state=None, regime=None, kind=None, **over):
    t = st.TEMPLATES.get(template_id)
    args = dict(setup=setup or t["setup"], position_state=state or t["position_states"][0],
                regime=regime or t["regimes"][0], template_id=template_id,
                basis_kind=kind or t["basis_kinds"][0], basis_level="12.3400", evidence="chart reading",
                broker_mode=t["broker_mode"], broker_implementation="human procedure")
    args.update(over)
    return st.select(**args)


class Templates(unittest.TestCase):
    def test_required_templates_exist(self) -> None:
        self.assertEqual(sorted(st.TEMPLATES), sorted([
            "B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM", "B1_FRESH_ENTRY_LOW_INTRADAY_HARD",
            "B1_FLOWN_N_LOW_WHITE_LINE_CLOSE_CONFIRM", "B1_FLOWN_YELLOW_LINE_CLOSE_CONFIRM",
            "B2_YELLOW_LINE_CLOSE_CONFIRM", "B2_FRESH_PRIOR_LOW_TWO_SESSION_CLOSE_CONFIRM",
            "B2_RISEN_PRIOR_LOW_CLOSE_CONFIRM",
            "B2_TIGHT_ENTRY_LOW_INTRADAY_HARD", "B2_KEY_K_PLATFORM_CLOSE_CONFIRM",
            "BRICK_FRESH_FAILURE_DISASTER", "BRICK_MATURE_DISASTER"]))
        for template_id in st.TEMPLATES:
            self.assertIn(template_id, PLAYBOOK)

    def test_every_allowed_combination_is_ok_and_everything_else_blocks(self) -> None:
        for template_id, t in st.TEMPLATES.items():
            for setup, state, regime, kind in itertools.product(
                    st.SETUPS, st.POSITION_STATES, st.REGIMES, auditor.STOP_BASIS_KINDS):
                allowed = (setup == t["setup"] and state in t["position_states"]
                           and regime in t["regimes"] and kind in t["basis_kinds"])
                out = run(template_id, setup, state, regime, kind)
                self.assertEqual(out["status"], "OK" if allowed else "BLOCKED",
                                 (template_id, setup, state, regime, kind))
                if not allowed:
                    self.assertNotIn("stop_semantics", out)
                    self.assertTrue(out["errors"])

    def test_distinct_variants_are_not_collapsed(self) -> None:
        fresh = run("B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM")["stop_semantics"]
        tight = run("B1_FRESH_ENTRY_LOW_INTRADAY_HARD")["stop_semantics"]
        flown = run("B1_FLOWN_N_LOW_WHITE_LINE_CLOSE_CONFIRM")["stop_semantics"]
        self.assertEqual((fresh["activation"], tight["activation"]), ("CLOSE_CONFIRM", "INTRADAY_HARD"))
        self.assertEqual(flown["basis"]["kind"], "PRIOR_B1_N_LOW")
        self.assertEqual(run("B1_FLOWN_N_LOW_WHITE_LINE_CLOSE_CONFIRM", kind="WHITE_LINE")["status"], "OK")
        # flown wider level is not valid for fresh unflown, and a fresh template is not valid for flown
        self.assertEqual(run("B1_FLOWN_N_LOW_WHITE_LINE_CLOSE_CONFIRM", state="FRESH_UNFLOWN")["status"], "BLOCKED")
        self.assertEqual(run("B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM", state="FLOWN")["status"], "BLOCKED")
        for regime in st.REGIMES:  # B1 is preferred in TIGHT; the normal close-confirm stop fits both
            self.assertEqual(run("B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM", regime=regime)["status"], "OK")
        # the hand-tight B1 override is sourced for TIGHT only and is never selectable in LOOSE
        self.assertEqual(run("B1_FRESH_ENTRY_LOW_INTRADAY_HARD", regime="TIGHT")["status"], "OK")
        loose = run("B1_FRESH_ENTRY_LOW_INTRADAY_HARD", regime="LOOSE")
        self.assertEqual(loose["status"], "BLOCKED")
        self.assertNotIn("stop_semantics", loose)
        self.assertIn("does not allow regime LOOSE", " ".join(loose["errors"]))
        self.assertEqual(st.TEMPLATES["B1_FRESH_ENTRY_LOW_INTRADAY_HARD"]["regimes"], ("TIGHT",))
        for template_id in ("B2_FRESH_PRIOR_LOW_TWO_SESSION_CLOSE_CONFIRM", "B2_RISEN_PRIOR_LOW_CLOSE_CONFIRM"):
            self.assertEqual(run(template_id, regime="TIGHT")["status"], "BLOCKED")
        self.assertEqual(run("B2_YELLOW_LINE_CLOSE_CONFIRM", regime="TIGHT")["status"], "BLOCKED")
        self.assertEqual(run("B1_FLOWN_YELLOW_LINE_CLOSE_CONFIRM", state="FRESH_UNFLOWN")["status"], "BLOCKED")
        self.assertEqual(run("B2_YELLOW_LINE_CLOSE_CONFIRM", state="FLOWN")["status"], "BLOCKED")
        for template_id in st.TEMPLATES:  # no generic B2 FLOWN mapping
            self.assertEqual(run(template_id, setup="B2", state="FLOWN")["status"], "BLOCKED")
        for template_id in ("B1_FLOWN_YELLOW_LINE_CLOSE_CONFIRM", "B2_YELLOW_LINE_CLOSE_CONFIRM"):
            out = run(template_id)
            self.assertEqual(out["stop_semantics"]["basis"]["kind"], "YELLOW_LINE")
            self.assertEqual(out["stop_semantics"]["activation"], "CLOSE_CONFIRM")
            self.assertIn("2025-12-03", out["source_ref"])
            self.assertIn("2026-01-21", out["source_ref"])
        self.assertEqual(run("B2_TIGHT_ENTRY_LOW_INTRADAY_HARD", regime="LOOSE")["status"], "BLOCKED")

    def test_b2_prior_low_is_split_by_position_state(self) -> None:
        fresh_id, risen_id = "B2_FRESH_PRIOR_LOW_TWO_SESSION_CLOSE_CONFIRM", "B2_RISEN_PRIOR_LOW_CLOSE_CONFIRM"
        self.assertEqual(run(fresh_id, state="FRESH_UNFLOWN")["status"], "OK")
        self.assertEqual(run(fresh_id, state="ALREADY_RISEN")["status"], "BLOCKED")
        self.assertEqual(run(risen_id, state="ALREADY_RISEN")["status"], "OK")
        self.assertEqual(run(risen_id, state="FRESH_UNFLOWN")["status"], "BLOCKED")
        fresh, risen = run(fresh_id), run(risen_id)
        for out in (fresh, risen):
            self.assertEqual(out["stop_semantics"]["basis"]["kind"], "PRIOR_B1_N_LOW")
            self.assertEqual(out["stop_semantics"]["activation"], "CLOSE_CONFIRM")
            self.assertEqual(out["holding_exit_rules"], [])
        # fresh carries the two-session failure-to-explode clock; the risen pullback must not inherit it
        fresh_text = " ".join(fresh["draft_text"].values())
        self.assertIn("two-session failure-to-explode clock", fresh_text)
        self.assertIn("2025-10-06", fresh["source_ref"])
        risen_text = " ".join(risen["draft_text"].values())
        self.assertIn("does not apply to an already-risen B2 pullback", risen_text)
        self.assertIn("prior B1/N low", risen_text)
        self.assertIn("no-S1", risen_text)
        self.assertNotIn("two-session rule", risen_text)
        self.assertNotIn("two-session rule", risen["source_ref"])
        self.assertIn("2026-01-21", risen["source_ref"])
        # the other shared B2 templates never mention the fresh-entry clock
        for template_id in ("B2_KEY_K_PLATFORM_CLOSE_CONFIRM", "B2_YELLOW_LINE_CLOSE_CONFIRM"):
            text = " ".join(run(template_id, state="ALREADY_RISEN")["draft_text"].values())
            self.assertNotIn("two-session", text)

    def test_cross_setup_template_blocks(self) -> None:
        self.assertEqual(run("B2_KEY_K_PLATFORM_CLOSE_CONFIRM", setup="B1")["status"], "BLOCKED")
        self.assertEqual(run("BRICK_MATURE_DISASTER", setup="B2")["status"], "BLOCKED")


class NoDefaults(unittest.TestCase):
    def test_missing_or_unknown_template_id_blocks(self) -> None:
        for template_id in (None, "", "B1", "UNIVERSAL", "b1_fresh_entry_low_close_confirm"):
            out = st.select("B1", "FRESH_UNFLOWN", "LOOSE", template_id, "ENTRY_CANDLE_LOW", "10",
                            "x", "HUMAN_ONLY_ALERT", "y")
            self.assertEqual(out["status"], "BLOCKED")
            self.assertIn("no default", " ".join(out["errors"]))

    def test_missing_selectors_block(self) -> None:
        base = dict(setup="B1", position_state="FRESH_UNFLOWN", regime="LOOSE",
                    template_id="B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM", basis_kind="ENTRY_CANDLE_LOW",
                    basis_level="10", evidence="x", broker_mode="HUMAN_ONLY_ALERT", broker_implementation="y")
        self.assertEqual(st.select(**base)["status"], "OK")
        for key in base:
            self.assertEqual(st.select(**{**base, key: None})["status"], "BLOCKED", key)

    def test_bad_level_evidence_and_broker_block(self) -> None:
        for bad in (None, 10, 10.5, "", "0", "0.00", "-1", "1e3", "abc", "10.12345", " ", "NaN", "1,000"):
            self.assertEqual(run("B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM", basis_level=bad)["status"], "BLOCKED", bad)
        for key in ("evidence", "broker_implementation"):
            for bad in (None, "", "   ", 5):
                self.assertEqual(run("B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM", **{key: bad})["status"], "BLOCKED")

    def test_broker_implementation_is_optional_only_for_intraday_hard(self) -> None:
        for template_id, t in st.TEMPLATES.items():
            result = run(template_id, broker_implementation=None)
            if t["activation"] == "INTRADAY_HARD":
                self.assertEqual(result["status"], "OK", template_id)
                ss = result["stop_semantics"]
                self.assertNotIn("broker_implementation", ss)
                report = auditor.Report()
                ticket = {"review": {"stop_semantics": ss}, "stop_trigger": "12.3400"}
                self.assertIsNotNone(auditor.parse_stop_semantics(report, ticket), template_id)
                for bad in ("", "   ", 5):
                    self.assertEqual(run(template_id, broker_implementation=bad)["status"], "BLOCKED")
                self.assertEqual(run(template_id)["stop_semantics"]["broker_implementation"],
                                 "human procedure")
            else:
                self.assertEqual(result["status"], "BLOCKED", template_id)
                self.assertIn("broker_implementation", " ".join(result["errors"]))

    def test_broker_mode_must_match_activation(self) -> None:
        self.assertEqual(run("B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM", broker_mode="LIVE_STOP_LIMIT")["status"], "BLOCKED")
        self.assertEqual(run("B2_TIGHT_ENTRY_LOW_INTRADAY_HARD", broker_mode="HUMAN_ONLY_ALERT")["status"], "BLOCKED")
        self.assertEqual(run("B2_TIGHT_ENTRY_LOW_INTRADAY_HARD", broker_mode="OTHER")["status"], "BLOCKED")

    def test_deterministic(self) -> None:
        for template_id in st.TEMPLATES:
            self.assertEqual(json.dumps(run(template_id)), json.dumps(run(template_id)))

    def test_unsupported_basis_kind_blocks(self) -> None:
        self.assertEqual(run("B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM", kind="YELLOW_LINE")["status"], "BLOCKED")
        for template_id in ("B2_FRESH_PRIOR_LOW_TWO_SESSION_CLOSE_CONFIRM", "B2_RISEN_PRIOR_LOW_CLOSE_CONFIRM"):
            self.assertEqual(run(template_id, kind="YELLOW_LINE")["status"], "BLOCKED")
        self.assertEqual(run("B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM", kind="NOPE")["status"], "BLOCKED")


class AuditorVocabulary(unittest.TestCase):
    def test_vocabulary_matches_trade_execution_auditor(self) -> None:
        self.assertEqual(st.STOP_KEYS, tuple(k for k in auditor.STOP_KEYS if k != "reclaim_by"))
        for t in st.TEMPLATES.values():
            self.assertIn(t["activation"], auditor.STOP_ACTIVATIONS)
            self.assertNotEqual(t["activation"], "NEXT_SESSION_FAILURE_TO_RECLAIM")
            for kind in t["basis_kinds"]:
                self.assertIn(kind, auditor.STOP_BASIS_KINDS)

    def test_emitted_fragment_has_exactly_the_audited_shape(self) -> None:
        for template_id in st.TEMPLATES:
            ss = run(template_id)["stop_semantics"]
            self.assertEqual(set(ss), set(st.STOP_KEYS))
            self.assertEqual(set(ss["basis"]), set(auditor.STOP_BASIS_KEYS))
            self.assertIn(ss["activation"], auditor.STOP_ACTIVATIONS)
            self.assertIsInstance(ss["basis"]["level"], str)
            self.assertEqual(auditor.text_decimal(ss["basis"]["level"]), auditor.text_decimal("12.3400"))
            self.assertTrue(ss["basis"]["evidence"].strip() and ss["broker_implementation"].strip())

    def test_emitted_fragment_passes_the_auditor_parser(self) -> None:
        for template_id in st.TEMPLATES:
            ss = run(template_id)["stop_semantics"]
            ticket = {"review": {"stop_semantics": ss}, "stop_trigger": "12.3400"}
            report = auditor.Report()
            self.assertIsNotNone(auditor.parse_stop_semantics(report, ticket), template_id)
            self.assertEqual(report.blockers, [])


class ServiceContractMismatch(unittest.TestCase):
    """The helper's fragment must be accepted only by the exact lifecycle-service contract."""

    @staticmethod
    def audited(ss, stop_trigger="12.3400"):
        report = auditor.Report()
        parsed = auditor.parse_stop_semantics(report, {"review": {"stop_semantics": ss}, "stop_trigger": stop_trigger})
        return parsed, report.blockers

    def test_basis_level_must_equal_stop_trigger_for_every_activation(self) -> None:
        for template_id in st.TEMPLATES:
            ss = run(template_id)["stop_semantics"]
            self.assertIsNotNone(self.audited(ss)[0], template_id)
            self.assertIsNotNone(self.audited(ss, "12.34")[0], template_id)  # same decimal value
            parsed, blockers = self.audited(ss, "12.3500")
            self.assertIsNone(parsed, template_id)
            self.assertTrue(any("must equal the persisted stop_trigger" in b for b in blockers), template_id)

    def test_reclaim_by_is_rejected_on_every_template_activation(self) -> None:
        for template_id in st.TEMPLATES:
            ss = run(template_id)["stop_semantics"]
            self.assertNotIn("reclaim_by", ss)
            for value in ("next session 10:00", None, ""):
                parsed, blockers = self.audited({**ss, "reclaim_by": value})
                self.assertIsNone(parsed, (template_id, value))
                self.assertTrue(any("reclaim_by is allowed only for NEXT_SESSION_FAILURE_TO_RECLAIM" in b
                                    for b in blockers), template_id)

    def test_missing_broker_implementation_and_unknown_keys_fail(self) -> None:
        for template_id, t in st.TEMPLATES.items():
            ss = run(template_id)["stop_semantics"]
            parsed, blockers = self.audited({**ss, "extra": "x"})
            self.assertIsNone(parsed, template_id)
            self.assertTrue(any("unsupported keys" in b for b in blockers), template_id)
            bare = {k: v for k, v in ss.items() if k != "broker_implementation"}
            self.assertEqual(self.audited(bare)[0] is not None, t["activation"] == "INTRADAY_HARD", template_id)


class BrickSeparation(unittest.TestCase):
    def test_brick_has_price_disaster_stop_plus_separate_non_price_rules(self) -> None:
        fresh, mature = run("BRICK_FRESH_FAILURE_DISASTER"), run("BRICK_MATURE_DISASTER")
        for out in (fresh, mature):
            self.assertEqual(out["stop_semantics"]["activation"], "INTRADAY_HARD")
            self.assertIn(out["stop_semantics"]["basis"]["kind"], ("ENTRY_CANDLE_LOW", "KEY_K_OR_PLATFORM"))
            self.assertTrue(out["live_broker_stop"])
            self.assertTrue(out["holding_exit_rules"])
            self.assertTrue(out["holding_exit_rules_note"])
            for rule in out["holding_exit_rules"]:
                self.assertIs(rule["is_price_stop"], False)
                self.assertIn(rule["kind"], ("STATE", "TIME"))
            blob = json.dumps(out["stop_semantics"])
            for rule in out["holding_exit_rules"]:
                self.assertNotIn(rule["id"], blob)
        self.assertEqual([r["id"] for r in fresh["holding_exit_rules"]], ["BRICK_NEXT_OPEN_NO_EXPLOSION"])
        self.assertEqual([r["id"] for r in mature["holding_exit_rules"]],
                         ["BRICK_RED_TO_GREEN", "BRICK_FOUR_RED_BRICKS", "BRICK_LAST_THREE_MINUTES"])
        self.assertIn("three minutes", mature["holding_exit_rules"][2]["text"])
        for template_id in ("BRICK_FRESH_FAILURE_DISASTER", "BRICK_MATURE_DISASTER"):
            for regime in st.REGIMES:
                self.assertEqual(run(template_id, regime=regime)["status"], "OK")
        self.assertIn("neither allows nor vetoes", fresh["holding_exit_rules_note"])

    def test_brick_requires_a_price_basis_even_with_state_rules(self) -> None:
        self.assertEqual(run("BRICK_FRESH_FAILURE_DISASTER", kind="WHITE_LINE")["status"], "BLOCKED")
        self.assertEqual(run("BRICK_MATURE_DISASTER", basis_level=None)["status"], "BLOCKED")

    def test_non_brick_templates_have_no_exit_rules(self) -> None:
        for template_id, t in st.TEMPLATES.items():
            if t["setup"] != "BRICK":
                self.assertEqual(run(template_id)["holding_exit_rules"], [])


class SourceRefAndText(unittest.TestCase):
    def test_source_ref_is_portable_and_dated(self) -> None:
        for template_id in st.TEMPLATES:
            out = run(template_id)
            self.assertRegex(out["source_ref"], r"20\d\d-\d\d-\d\d")
            self.assertIn(out["source_ref"], out["stop_semantics"]["basis"]["evidence"])
            self.assertIsNone(MACHINE_PATH.search(json.dumps(out)))
            self.assertIn("2026-04-22", out["source_ref"])
        anchors = {"B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM": "2025-11-12", "B2_FRESH_PRIOR_LOW_TWO_SESSION_CLOSE_CONFIRM": "2025-10-06",
                   "B2_RISEN_PRIOR_LOW_CLOSE_CONFIRM": "2026-01-21",
                   "B2_TIGHT_ENTRY_LOW_INTRADAY_HARD": "2026-01-14", "BRICK_MATURE_DISASTER": "2026-03-18"}
        for template_id, date in anchors.items():
            self.assertIn(date, run(template_id)["source_ref"])
        self.assertIn("2026-01-21", run("B2_KEY_K_PLATFORM_CLOSE_CONFIRM")["source_ref"])
        self.assertIn("2025-11-26", run("B1_FRESH_ENTRY_LOW_INTRADAY_HARD")["source_ref"])

    def test_draft_text_carries_level_and_matches_activation(self) -> None:
        for template_id, t in st.TEMPLATES.items():
            out = run(template_id)
            text = out["draft_text"]
            self.assertIn("12.3400", text["invalidation"])
            self.assertIn(template_id, text["trigger_text_append"])
            if t["activation"] == "CLOSE_CONFIRM":
                self.assertIn("regular-session close", text["invalidation"])
                self.assertIn("No live intraday stop", text["invalidation"])
                self.assertFalse(out["live_broker_stop"])
            else:
                self.assertIn("live protective stop-limit", text["invalidation"])

    def test_script_and_playbook_have_no_machine_paths(self) -> None:
        for text in (PLAYBOOK, (HERE / "stop_template.py").read_text(encoding="utf-8")):
            for line in text.splitlines():
                self.assertIsNone(MACHINE_PATH.search(line), line)


class Cli(unittest.TestCase):
    def call(self, *args: str):
        return subprocess.run([sys.executable, "-I", "-X", "utf8", str(HERE / "stop_template.py"), *args],
                              capture_output=True, text=True, encoding="utf-8")

    def test_cli_ok_blocked_and_list(self) -> None:
        ok = self.call("--setup", "B2", "--position-state", "FRESH_UNFLOWN", "--regime", "TIGHT",
                       "--template-id", "B2_TIGHT_ENTRY_LOW_INTRADAY_HARD", "--basis-kind", "ENTRY_CANDLE_LOW",
                       "--basis-level", "10.25", "--evidence", "e", "--broker-mode", "LIVE_STOP_LIMIT",
                       "--broker-implementation", "b")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["status"], "OK")
        blocked = self.call("--setup", "B2")
        self.assertEqual(blocked.returncode, 2)
        self.assertEqual(json.loads(blocked.stdout)["status"], "BLOCKED")
        listing = self.call("--list-templates")
        self.assertEqual(sorted(json.loads(listing.stdout)), sorted(st.TEMPLATES))


if __name__ == "__main__":
    unittest.main()
