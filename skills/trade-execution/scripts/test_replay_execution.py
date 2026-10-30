#!/usr/bin/env python3
"""Behavioural tests for the offline historical replay lane."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import replay_execution as replay


class ReplayFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cutoff = self.evidence("cutoff.json", "20261028")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def evidence(self, name: str, last: str, role: str = "cutoff_safe") -> dict:
        path = self.root / name
        path.write_text(json.dumps({"last_bar_date": last}), encoding="utf-8")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"role": role, "kind": "cutoff_data", "path": str(path), "sha256": sha,
                "last_bar_date": last}

    def plan(self, trade_type: str = "B1_YELLOW_LINE_SWING") -> dict:
        return {
            "schema": replay.SCHEMA,
            "mode": "REPLAY",
            "market": "US",
            "symbol": "TEST",
            "decision_cutoff": "20261028",
            "execution_date": "20261029",
            "source": {"kind": "case_annotation", "reference": "case:abc",
                       "decision_statement": "截至28日决定：29日若价格符合上限则模拟执行"},
            "simulation_approval": {"approved_by": "human:tester",
                                    "approved_at": "2026-10-30T12:00:00-04:00",
                                    "note": "批准历史复盘条款，不是实盘授权"},
            "trade_type": trade_type,
            "basis_level": "61.87",
            "basis_evidence": "截至28日，白黄金叉后首次缩量回踩黄线",
            "execution_mode": "MARKETABLE_LIMIT",
            "entry_planned": "62.00",
            "entry_max": "62.50",
            "quantity": 10,
            "stop_limit": "61.80",
            "target": "65.50",
            "fee_estimate": "1.00",
            "risk_budget": "20.00",
            "assume_fill_if_eligible": True,
            "evidence": [self.cutoff],
        }

    def event(self, stage: str, rid: str, **prices) -> dict:
        snapshot = {"stage": stage, "session_date": "20261029", **prices}
        evidence_path = self.root / f"{stage.lower()}-snapshot.json"
        evidence_path.write_text(json.dumps(snapshot), encoding="utf-8")
        evidence = {"role": "replay_event",
                    "kind": "replay_open_snapshot" if stage == "OPEN" else "replay_close_snapshot",
                    "path": str(evidence_path),
                    "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                    "last_bar_date": "20261029"}
        ev = {"schema": replay.EVENT_SCHEMA, "mode": "REPLAY_EVENT", "replay_id": rid,
              "stage": stage, "session_date": "20261029", "evidence": evidence}
        ev.update(prices)
        return ev


class PrepareTests(ReplayFixture):
    def test_prepare_is_deterministic_and_uses_canonical_policy(self) -> None:
        first = replay.prepare(self.plan())
        second = replay.prepare(self.plan())
        self.assertEqual(first, second)
        self.assertEqual(first["mode"], "REPLAY")
        self.assertFalse(first["production_writes"])
        self.assertFalse(first["broker_actions"])
        policy = first["plan"]["stop_policy"]
        self.assertEqual(policy["policy"], "zge-stop-v1")
        self.assertEqual(policy["stop_semantics"]["basis"]["kind"], "YELLOW_LINE")
        self.assertEqual(policy["stop_semantics"]["activation"], "CLOSE_CONFIRM")
        self.assertFalse(policy["live_broker_stop"])

    def test_future_cutoff_evidence_is_blocked(self) -> None:
        plan = self.plan()
        plan["evidence"] = [self.evidence("future.json", "20261029")]
        with self.assertRaisesRegex(replay.ReplayBlocked, "future leakage"):
            replay.prepare(plan)

    def test_unknown_or_generic_trade_type_is_blocked_by_canonical_selector(self) -> None:
        with self.assertRaisesRegex(replay.ReplayBlocked, "canonical stop policy blocked"):
            replay.prepare(self.plan("B1"))

    def test_human_simulation_approval_is_required_but_is_not_live_approval(self) -> None:
        plan = self.plan()
        plan["simulation_approval"]["approved_by"] = "agent:codex"
        with self.assertRaisesRegex(replay.ReplayBlocked, "human:<name>"):
            replay.prepare(plan)

    def test_risk_budget_is_enforced_without_moving_the_stop(self) -> None:
        plan = self.plan()
        plan["risk_budget"] = "1.00"
        with self.assertRaisesRegex(replay.ReplayBlocked, "exceeds replay risk_budget"):
            replay.prepare(plan)


class StageTests(ReplayFixture):
    def prepared(self, trade_type: str = "B1_YELLOW_LINE_SWING") -> dict:
        return replay.prepare(self.plan(trade_type))

    def open(self, journal: dict, value: str = "62.18") -> dict:
        ev = self.event("OPEN", journal["replay_id"], quote_kind="OHLC_OPEN_PROXY",
                        bid=value, ask=value, open=value)
        return replay.advance(journal, ev)

    def close(self, journal: dict, low: str, close: str) -> dict:
        ev = self.event("CLOSE", journal["replay_id"], open="62.18", high="65.60",
                        low=low, close=close, volume=7_800_000)
        return replay.advance(journal, ev)

    def test_open_reveal_can_hypothetically_fill_but_never_claims_a_real_fill(self) -> None:
        opened = self.open(self.prepared())
        self.assertEqual(opened["stage"], "OPEN_REVEALED")
        self.assertEqual(opened["replay_state"]["entry"], "HYPOTHETICALLY_FILLED")
        self.assertEqual(opened["replay_state"]["hypothetical_fill"]["price"], "62.18")
        self.assertTrue(any("proxy" in warning.lower() for warning in opened["warnings"]))
        self.assertFalse(opened["production_writes"])

    def test_open_event_rejects_close_fields_as_future_leakage(self) -> None:
        journal = self.prepared()
        ev = self.event("OPEN", journal["replay_id"], quote_kind="OHLC_OPEN_PROXY",
                        bid="62.18", ask="62.18", open="62.18")
        ev["close"] = "65.59"
        with self.assertRaisesRegex(replay.ReplayBlocked, "future leakage"):
            replay.advance(journal, ev)

    def test_open_evidence_file_itself_cannot_hide_end_of_day_fields(self) -> None:
        journal = self.prepared()
        ev = self.event("OPEN", journal["replay_id"], quote_kind="OHLC_OPEN_PROXY",
                        bid="62.18", ask="62.18", open="62.18")
        path = Path(ev["evidence"]["path"])
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        snapshot["close"] = "65.59"
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        ev["evidence"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(replay.ReplayBlocked, "future leakage"):
            replay.advance(journal, ev)

    def test_yellow_b1_intraday_break_does_not_trigger_close_confirmed_stop(self) -> None:
        # The low crosses the yellow line, but the close finishes above it.
        closed = self.close(self.open(self.prepared()), low="61.50", close="65.59")
        self.assertEqual(closed["replay_state"]["stop"], "HOLD_CLOSE_ABOVE_LEVEL")
        self.assertEqual(closed["plan"]["stop_policy"]["stop_semantics"]["activation"],
                         "CLOSE_CONFIRM")

    def test_yellow_b1_close_below_level_exits_only_after_close(self) -> None:
        closed = self.close(self.open(self.prepared()), low="61.20", close="61.50")
        self.assertEqual(closed["replay_state"]["stop"], "EXIT_AFTER_CLOSE")

    def test_passive_limit_stays_working_at_open_and_only_assumes_fill_after_low_touches(self) -> None:
        plan = self.plan()
        plan["execution_mode"] = "PASSIVE_LIMIT"
        plan["entry_planned"] = plan["entry_max"] = "62.00"
        prepared = replay.prepare(plan)
        opened = self.open(prepared, "62.18")
        self.assertEqual(opened["replay_state"]["entry"], "WORKING_PASSIVE_LIMIT")
        closed = self.close(opened, low="61.90", close="65.59")
        self.assertEqual(closed["replay_state"]["entry"], "HYPOTHETICALLY_FILLED")
        self.assertIn("sequence", closed["replay_state"]["hypothetical_fill"]["assumption"])

    def test_brick_zero_day_uses_intraday_hard_trigger_but_does_not_invent_fill(self) -> None:
        plan = self.plan("BRICK_ZERO_DAY")
        # BRICK maps to entry-candle low but the generic fixture level is still a valid supplied level.
        prepared = replay.prepare(plan)
        closed = self.close(self.open(prepared), low="61.50", close="65.59")
        self.assertEqual(closed["plan"]["stop_policy"]["stop_semantics"]["activation"],
                         "INTRADAY_HARD")
        self.assertEqual(closed["replay_state"]["stop"], "TRIGGERED_FILL_UNKNOWN")

    def test_stages_are_strictly_monotonic(self) -> None:
        journal = self.prepared()
        close = self.event("CLOSE", journal["replay_id"], open="62", high="63", low="61",
                           close="62", volume=1)
        with self.assertRaisesRegex(replay.ReplayBlocked, "next event must be 'OPEN'"):
            replay.advance(journal, close)

    def test_tampered_plan_is_rejected_before_next_stage(self) -> None:
        journal = self.prepared()
        journal["plan"]["entry_max"] = "99.00"
        ev = self.event("OPEN", journal["replay_id"], quote_kind="OHLC_OPEN_PROXY",
                        bid="62.18", ask="62.18", open="62.18")
        with self.assertRaisesRegex(replay.ReplayBlocked, "replay_id"):
            replay.advance(journal, ev)


class SafetySurfaceTests(unittest.TestCase):
    def test_replay_module_has_no_lifecycle_database_or_apply_surface(self) -> None:
        text = Path(replay.__file__).read_text(encoding="utf-8")
        self.assertNotIn("sqlite3", text)
        self.assertNotIn("zradar.trade_lifecycle", text)
        self.assertNotIn("apply --op", text)


class ExclusiveOutputTests(ReplayFixture):
    def write_plan(self) -> Path:
        path = self.root / "plan.json"
        path.write_text(json.dumps(self.plan()), encoding="utf-8")
        return path

    def call_prepare(self, output: Path) -> tuple[int, dict]:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = replay.main(["prepare", "--plan", str(self.write_plan()),
                              "--output", str(output)])
        return rc, json.loads(stdout.getvalue())

    def test_existing_json_is_never_overwritten_even_by_blocked_failure_output(self) -> None:
        output = self.root / "existing.json"
        original = b'{"important":"keep me"}\n'
        output.write_bytes(original)
        rc, report = self.call_prepare(output)
        self.assertEqual(rc, 2)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(report["verdict"], "BLOCKED")
        self.assertIn("will not be overwritten", report["blockers"][0])

    def test_non_json_database_path_is_never_touched(self) -> None:
        output = self.root / "ledger.sqlite3"
        original = b"SQLite format 3\x00important-production-bytes"
        output.write_bytes(original)
        rc, report = self.call_prepare(output)
        self.assertEqual(rc, 2)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(report["verdict"], "BLOCKED")
        self.assertIn("must end in .json", report["blockers"][0])

    def test_new_json_is_created_once_and_second_run_cannot_replace_it(self) -> None:
        output = self.root / "new.json"
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            first = replay.main(["prepare", "--plan", str(self.write_plan()),
                                 "--output", str(output)])
        self.assertEqual(first, 0)
        original = output.read_bytes()
        second, report = self.call_prepare(output)
        self.assertEqual(second, 2)
        self.assertEqual(output.read_bytes(), original)
        self.assertIn("will not be overwritten", report["blockers"][0])


if __name__ == "__main__":
    unittest.main()
