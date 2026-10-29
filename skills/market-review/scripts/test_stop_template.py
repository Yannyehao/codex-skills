#!/usr/bin/env python3
"""Tests for the canonical stop-policy helper (zge-stop-v1). Offline; reads only repository files."""

from __future__ import annotations

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

TYPES = ("B1_KLINE_REVERSAL", "B1_WHITE_LINE_SHORT", "B1_YELLOW_LINE_SWING", "B2_FRESH_CONFIRMATION",
         "B2_RISEN_PULLBACK", "BRICK_ZERO_DAY")
EXPECTED = {  # trade_type -> (basis kind, activation, broker mode, extra exit rule ids, source dates)
    "B1_KLINE_REVERSAL": ("ENTRY_CANDLE_LOW", "CLOSE_CONFIRM", "HUMAN_ONLY_ALERT",
                          ["B1_THREE_SESSION_RECOVERY"], ("2025-05-07", "2025-10-06")),
    "B1_WHITE_LINE_SHORT": ("WHITE_LINE", "CLOSE_CONFIRM", "HUMAN_ONLY_ALERT", [],
                            ("2026-02-11", "2026-04-22")),
    "B1_YELLOW_LINE_SWING": ("YELLOW_LINE", "CLOSE_CONFIRM", "HUMAN_ONLY_ALERT",
                             ["YELLOW_SUPPORT_SECOND_SESSION_CONFIRM"], ("2026-02-11",)),
    "B2_FRESH_CONFIRMATION": ("PRIOR_B1_N_LOW", "CLOSE_CONFIRM", "HUMAN_ONLY_ALERT",
                              ["B2_TWO_SESSION_EXPLOSION"], ("2025-10-06",)),
    "B2_RISEN_PULLBACK": ("PRIOR_B1_N_LOW", "CLOSE_CONFIRM", "HUMAN_ONLY_ALERT",
                          ["B2_RISEN_STRUCTURE_HOLD"], ("2026-01-21",)),
    "BRICK_ZERO_DAY": ("ENTRY_CANDLE_LOW", "INTRADAY_HARD", "LIVE_STOP_LIMIT",
                       ["BRICK_NEXT_OPEN_NO_EXPLOSION", "BRICK_RED_TO_GREEN"], ("2026-02-20", "2026-03-29")),
}


def run(trade_type, level="12.3400", evidence="chart reading"):
    return st.select(trade_type, level, evidence)


class Catalogue(unittest.TestCase):
    def test_exactly_six_trade_types_each_in_the_playbook(self) -> None:
        self.assertEqual(sorted(st.TRADE_TYPES), sorted(TYPES))
        self.assertEqual(len(st.TRADE_TYPES), 6)
        for trade_type in TYPES:
            self.assertIn(trade_type, PLAYBOOK)
        for retired in ("B1", "B2", "BRICK", "COMPOSITE", "BRICK_MATURE_DISASTER", "BRICK_FRESH_FAILURE_DISASTER",
                        "B2_TIGHT_ENTRY_LOW_INTRADAY_HARD", "B1_FRESH_ENTRY_LOW_CLOSE_CONFIRM"):
            self.assertNotIn(retired, st.TRADE_TYPES)

    def test_mapping_is_unique_and_semantics_are_derived(self) -> None:
        for trade_type, (kind, activation, broker, rule_ids, dates) in EXPECTED.items():
            spec = st.TRADE_TYPES[trade_type]
            self.assertEqual((spec["basis_kind"], spec["activation"], spec["broker_mode"]),
                             (kind, activation, broker), trade_type)
            self.assertEqual([r[0] for r in spec["exit_rules"]], rule_ids + ["PROFIT_TO_LOSS_INTRADAY"])
            for date in dates:
                self.assertIn(date, "; ".join(spec["sources"]), trade_type)
        # not a free choice: no single trade type tuple repeats except the two prior-low B2 types, which differ
        # only in their separate holding rule, never in basis or activation
        shapes = {(s["basis_kind"], s["activation"], tuple(r[0] for r in s["exit_rules"]))
                  for s in st.TRADE_TYPES.values()}
        self.assertEqual(len(shapes), 6)

    def test_only_brick_zero_day_is_intraday_hard_and_live(self) -> None:
        for trade_type in TYPES:
            out = run(trade_type)
            hard = trade_type == "BRICK_ZERO_DAY"
            self.assertEqual(out["stop_semantics"]["activation"] == "INTRADAY_HARD", hard, trade_type)
            self.assertEqual(out["live_broker_stop"], hard, trade_type)
            self.assertEqual(st.TRADE_TYPES[trade_type]["broker_mode"],
                             "LIVE_STOP_LIMIT" if hard else "HUMAN_ONLY_ALERT")

    def test_close_confirm_never_creates_a_protective_order(self) -> None:
        for trade_type in TYPES:
            if trade_type == "BRICK_ZERO_DAY":
                continue
            out = run(trade_type)
            self.assertEqual(out["stop_semantics"]["activation"], "CLOSE_CONFIRM")
            self.assertFalse(out["live_broker_stop"])
            text = out["draft_text"]["invalidation"]
            self.assertIn("regular-session close", text)
            self.assertIn("No live intraday stop", text)
            self.assertNotIn("live protective stop-limit", text)
            procedure = out["stop_semantics"]["broker_implementation"]
            self.assertIn("Human only", procedure)
            self.assertIn("No live broker stop", procedure)
            self.assertIn("12.3400", procedure)
        self.assertIn("live protective stop-limit", run("BRICK_ZERO_DAY")["draft_text"]["invalidation"])

    def test_non_price_rules_are_separate_and_never_stops(self) -> None:
        for trade_type, (_, _, _, rule_ids, _) in EXPECTED.items():
            out = run(trade_type)
            self.assertEqual([r["id"] for r in out["holding_exit_rules"]], rule_ids + ["PROFIT_TO_LOSS_INTRADAY"])
            blob = json.dumps(out["stop_semantics"])
            for rule in out["holding_exit_rules"]:
                self.assertIs(rule["is_price_stop"], False)
                self.assertIn(rule["kind"], ("STATE", "TIME"))
                self.assertNotIn(rule["id"], blob)
            self.assertTrue(out["holding_exit_rules_note"])
        profit = run("B2_RISEN_PULLBACK")["holding_exit_rules"][-1]
        self.assertIn("already profitable", profit["text"])
        self.assertIn("not a structural stop", profit["text"])
        brick = " ".join(r["text"] for r in run("BRICK_ZERO_DAY")["holding_exit_rules"])
        self.assertIn("9:33", brick)
        self.assertIn("9:37", brick)
        self.assertIn("red to green", brick)

    def test_b2_types_differ_by_clock_not_by_stop(self) -> None:
        fresh, risen = run("B2_FRESH_CONFIRMATION"), run("B2_RISEN_PULLBACK")
        self.assertEqual(fresh["stop_semantics"]["basis"]["kind"], risen["stop_semantics"]["basis"]["kind"])
        fresh_text = fresh["draft_text"]["trigger_text_append"]
        risen_text = risen["draft_text"]["trigger_text_append"]
        self.assertIn("two sessions", fresh_text)
        self.assertIn("No fresh two-session clock", risen_text)
        self.assertIn("S1", risen_text)


class NoChoices(unittest.TestCase):
    def test_unknown_missing_or_combined_trade_type_blocks(self) -> None:
        for bad in (None, "", "B1", "B2", "BRICK", "COMPOSITE", "UNIVERSAL", "b1_kline_reversal",
                    "B1_KLINE_REVERSAL+B2_RISEN_PULLBACK", "BRICK_MATURE_DISASTER", 5):
            out = run(bad)
            self.assertEqual(out["status"], "BLOCKED", bad)
            self.assertNotIn("stop_semantics", out)
            self.assertIn("no default", " ".join(out["errors"]))

    def test_bad_level_and_evidence_block(self) -> None:
        for bad in (None, 10, 10.5, "", "0", "0.00", "-1", "1e3", "abc", "10.12345", " ", "NaN", "1,000"):
            self.assertEqual(run("B1_KLINE_REVERSAL", level=bad)["status"], "BLOCKED", bad)
        for bad in (None, "", "   ", 5):
            self.assertEqual(run("B1_KLINE_REVERSAL", evidence=bad)["status"], "BLOCKED", bad)

    def test_caller_evidence_cannot_carry_a_marker(self) -> None:
        for bad in ("canonical_trade_type=B2_RISEN_PULLBACK", "x policy=zge-stop-v1", "policy=other"):
            out = run("B1_KLINE_REVERSAL", evidence=bad)
            self.assertEqual(out["status"], "BLOCKED", bad)
            self.assertNotIn("stop_semantics", out)

    def test_policy_selectors_are_not_parameters(self) -> None:
        import inspect
        self.assertEqual(list(inspect.signature(st.select).parameters), ["trade_type", "basis_level", "evidence"])
        for old in ("template_id", "basis_kind", "broker_mode", "activation", "regime", "position_state", "setup"):
            self.assertNotIn(old, inspect.signature(st.select).parameters)

    def test_deterministic(self) -> None:
        for trade_type in TYPES:
            self.assertEqual(json.dumps(run(trade_type)), json.dumps(run(trade_type)))

    def test_level_text_is_preserved_exactly(self) -> None:
        for level in ("12.3400", "12.34", "7", "0.5"):
            out = run("B2_FRESH_CONFIRMATION", level=level)
            self.assertEqual(out["stop_semantics"]["basis"]["level"], level)
            self.assertIn(level, out["draft_text"]["invalidation"])


class Marker(unittest.TestCase):
    def test_every_draft_carries_exactly_one_machine_checkable_marker(self) -> None:
        for trade_type in TYPES:
            evidence = run(trade_type)["stop_semantics"]["basis"]["evidence"]
            self.assertTrue(evidence.startswith(f"canonical_trade_type={trade_type}; policy=zge-stop-v1 |"))
            self.assertEqual(auditor.MARKER_TYPE_RE.findall(evidence), [trade_type])
            self.assertEqual(auditor.MARKER_POLICY_RE.findall(evidence), ["zge-stop-v1"])
            self.assertEqual(st.marker(trade_type), f"canonical_trade_type={trade_type}; policy=zge-stop-v1")

    def test_no_stop_semantics_keys_were_added(self) -> None:
        self.assertEqual(st.STOP_KEYS, tuple(k for k in auditor.STOP_KEYS if k != "reclaim_by"))
        for trade_type in TYPES:
            ss = run(trade_type)["stop_semantics"]
            self.assertEqual(set(ss), set(st.STOP_KEYS))
            self.assertEqual(set(ss["basis"]), set(auditor.STOP_BASIS_KEYS))


class AuditorAgreement(unittest.TestCase):
    @staticmethod
    def audited(ss, stop_trigger="12.3400"):
        report = auditor.Report()
        parsed = auditor.parse_stop_semantics(report, {"review": {"stop_semantics": ss}, "stop_trigger": stop_trigger})
        return parsed, report.blockers

    def test_auditor_table_equals_helper_table(self) -> None:
        self.assertEqual(auditor.STOP_POLICY, st.POLICY)
        self.assertEqual(auditor.CANONICAL_STOPS,
                         {k: (v["basis_kind"], v["activation"]) for k, v in st.TRADE_TYPES.items()})
        for spec in st.TRADE_TYPES.values():
            self.assertIn(spec["basis_kind"], auditor.STOP_BASIS_KINDS)
            self.assertIn(spec["activation"], auditor.STOP_ACTIVATIONS)
            self.assertNotEqual(spec["activation"], "NEXT_SESSION_FAILURE_TO_RECLAIM")

    def test_emitted_fragment_passes_the_auditor_and_equals_stop_trigger(self) -> None:
        for trade_type in TYPES:
            ss = run(trade_type)["stop_semantics"]
            for trigger in ("12.3400", "12.34"):  # same decimal value
                parsed, blockers = self.audited(ss, trigger)
                self.assertIsNotNone(parsed, trade_type)
                self.assertEqual(blockers, [])
            parsed, blockers = self.audited(ss, "12.3500")
            self.assertIsNone(parsed)
            self.assertTrue(any("must equal the persisted stop_trigger" in b for b in blockers))
            self.assertIsInstance(ss["basis"]["level"], str)

    def test_mismatched_kind_or_activation_blocks(self) -> None:
        for trade_type in TYPES:
            ss = run(trade_type)["stop_semantics"]
            for kind in auditor.STOP_BASIS_KINDS:
                if kind != ss["basis"]["kind"]:
                    parsed, blockers = self.audited({**ss, "basis": {**ss["basis"], "kind": kind}})
                    self.assertIsNone(parsed, (trade_type, kind))
                    self.assertTrue(any("requires basis.kind" in b for b in blockers))
            for activation in auditor.STOP_ACTIVATIONS:
                if activation != ss["activation"] and activation != "NEXT_SESSION_FAILURE_TO_RECLAIM":
                    parsed, blockers = self.audited({**ss, "activation": activation})
                    self.assertIsNone(parsed, (trade_type, activation))
                    self.assertTrue(any("requires basis.kind" in b for b in blockers))

    def test_unknown_or_ambiguous_marker_blocks(self) -> None:
        ss = run("B2_RISEN_PULLBACK")["stop_semantics"]
        good = ss["basis"]["evidence"]

        def with_evidence(text):
            return self.audited({**ss, "basis": {**ss["basis"], "evidence": text}})

        for bad in (good.replace("B2_RISEN_PULLBACK", "B2"), good.replace("B2_RISEN_PULLBACK", "COMPOSITE"),
                    good.replace("B2_RISEN_PULLBACK", ""), good.replace("zge-stop-v1", "zge-stop-v2"),
                    good + " canonical_trade_type=B2_RISEN_PULLBACK",
                    good + " canonical_trade_type=B1_KLINE_REVERSAL",
                    good + " policy=zge-stop-v1",
                    "canonical_trade_type=B2_RISEN_PULLBACK only",
                    "policy=zge-stop-v1 only"):
            parsed, blockers = with_evidence(bad)
            self.assertIsNone(parsed, bad)
            self.assertTrue(blockers, bad)
        self.assertIsNotNone(with_evidence(good)[0])
        # evidence without any marker is not executable: the auditor BLOCKS
        parsed, blockers = with_evidence("hand-written chart reading")
        self.assertIsNone(parsed)
        self.assertTrue(any("exactly one canonical_trade_type" in b for b in blockers))


class Sources(unittest.TestCase):
    def test_source_ref_is_portable_dated_and_in_evidence(self) -> None:
        for trade_type, (_, _, _, _, dates) in EXPECTED.items():
            out = run(trade_type)
            self.assertIn(out["source_ref"], out["stop_semantics"]["basis"]["evidence"])
            self.assertIn("2026-04-22", out["source_ref"])
            for date in dates:
                self.assertIn(date, out["source_ref"])
            self.assertIsNone(MACHINE_PATH.search(json.dumps(out)))

    def test_draft_text_carries_level_and_policy(self) -> None:
        for trade_type in TYPES:
            text = run(trade_type)["draft_text"]
            self.assertIn("12.3400", text["invalidation"])
            self.assertIn(trade_type, text["trigger_text_append"])
            self.assertIn("zge-stop-v1", text["trigger_text_append"])

    def test_script_and_playbook_have_no_machine_paths(self) -> None:
        for text in (PLAYBOOK, (HERE / "stop_template.py").read_text(encoding="utf-8")):
            for line in text.splitlines():
                self.assertIsNone(MACHINE_PATH.search(line), line)

    def test_script_has_no_old_choice_vocabulary(self) -> None:
        source = (HERE / "stop_template.py").read_text(encoding="utf-8")
        for old in ("TEMPLATES", "POSITION_STATES", "REGIMES", "BROKER_MODES", "--template-id", "--basis-kind",
                    "--broker-mode", "--regime", "--position-state", "--setup"):
            self.assertNotIn(old, source)


class Cli(unittest.TestCase):
    def call(self, *args: str):
        return subprocess.run([sys.executable, "-I", "-X", "utf8", str(HERE / "stop_template.py"), *args],
                              capture_output=True, text=True, encoding="utf-8")

    def test_cli_ok_blocked_and_list(self) -> None:
        ok = self.call("--trade-type", "BRICK_ZERO_DAY", "--basis-level", "10.25", "--evidence", "e")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["status"], "OK")
        self.assertEqual(ok.stdout, self.call("--trade-type", "BRICK_ZERO_DAY", "--basis-level", "10.25",
                                              "--evidence", "e").stdout)
        for args in (("--trade-type", "B2"), ("--trade-type", "B2_RISEN_PULLBACK"), ()):
            blocked = self.call(*args)
            self.assertEqual(blocked.returncode, 2, args)
            self.assertEqual(json.loads(blocked.stdout)["status"], "BLOCKED")
        listing = self.call("--list-trade-types")
        self.assertEqual(listing.returncode, 0)
        data = json.loads(listing.stdout)
        self.assertEqual(sorted(data["trade_types"]), sorted(TYPES))
        self.assertEqual(data["policy"], "zge-stop-v1")

    def test_old_selectors_are_usage_errors(self) -> None:
        base = ("--trade-type", "B2_RISEN_PULLBACK", "--basis-level", "10.25", "--evidence", "e")
        for old in (("--setup", "B2"), ("--position-state", "ALREADY_RISEN"), ("--regime", "LOOSE"),
                    ("--template-id", "X"), ("--basis-kind", "WHITE_LINE"), ("--broker-mode", "LIVE_STOP_LIMIT"),
                    ("--activation", "INTRADAY_HARD"), ("--broker-implementation", "x"), ("--list-templates",),
                    ("--basis", "10")):  # abbreviations of known options are also rejected
            out = self.call(*base, *old)
            self.assertEqual(out.returncode, 64, old)
            self.assertEqual(out.stdout, "", old)
        self.assertEqual(self.call("--list-trade-types", "--trade-type", "B1_KLINE_REVERSAL").returncode, 64)
        self.assertEqual(self.call("--list-trade-types", "--basis-level", "1").returncode, 64)


if __name__ == "__main__":
    unittest.main()
