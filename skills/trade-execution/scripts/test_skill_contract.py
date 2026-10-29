#!/usr/bin/env python3
"""Contract tests for the trade-execution documents and its public-safe configuration.

Behaviour of the auditor is proven in test_audit_ticket.py; these tests prove the documents the
model reads say the same thing: persisted approved tickets only, the approval hash and profile come
from service state (no human-typed hash), fail closed, no inferring or approving, no broker
automation. They read only files inside this repository, never a `*.local.json`.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import audit_ticket as audit

TE = Path(__file__).resolve().parents[1]
REPO = TE.parents[1]
MACHINE_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|/home/|\\\\[A-Za-z0-9_.-]+\\")
PLACEHOLDER = re.compile(r"^(PATH_TO_[A-Z_]+|(review|human|import):NAME)$")


def read(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def shipped_files() -> list[Path]:
    wanted = {".md", ".json", ".yaml", ".py"}
    return [p for p in TE.rglob("*") if p.is_file() and p.suffix in wanted
            and "__pycache__" not in p.parts and not p.name.endswith(".local.json")
            and not p.name.startswith("test_")]


class ApprovalFromServiceState(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = read(TE / "SKILL.md")
        cls.cli = read(TE / "references" / "service-cli.md")
        cls.contract = read(TE / "references" / "ticket-contract.md")

    def test_no_document_or_script_asks_the_human_to_supply_a_terms_hash(self) -> None:
        for path in shipped_files():
            self.assertNotIn("--approved-terms-sha256", path.read_text(encoding="utf-8"), path.name)
        self.assertIn("Nobody types a hash", self.skill)
        self.assertIn("you never ask the user for one", self.skill)
        self.assertIn("There is no hash argument", self.cli)
        self.assertIn("do not ask the user for a hash", self.cli)

    def test_documents_read_approval_and_profile_straight_from_state(self) -> None:
        self.assertIn("persisted `approval` record", self.skill)
        self.assertIn("frozen parsed `profile`", self.skill)
        self.assertIn("`state.approval.terms_sha256`", self.cli)
        self.assertIn("{event_seq, approved_by, approved_at, terms_sha256, matches_ticket_terms, note}",
                      self.cli)
        self.assertIn("`approval` is `null` until a human approves", self.cli)
        self.assertIn("must hash to `profile_sha256`", self.cli)
        self.assertIn("matches_ticket_terms", self.contract)
        self.assertIn("lot size and T+N are read from it", self.contract)

    def test_missing_or_mismatched_approval_fails_closed_in_the_docs_and_the_gate(self) -> None:
        self.assertIn("a missing or mismatched `approval` is a block, not something to supply", self.skill)
        self.assertIn("the result is `BLOCKED`", self.cli)
        self.assertIn("A missing `approval` or a different hash means different or no approved terms: stop",
                      self.contract)
        for flag in ("approval", "profile", "profile_sha256"):
            self.assertIn(flag, audit.REQUIRED_KEYS)

    def test_reading_state_approval_is_evidence_not_an_approval_input(self) -> None:
        self.assertIn("reading `state.approval` is evidence, never an approval input", self.skill)
        self.assertIn("this skill never infers or performs it", self.skill)
        self.assertIn("do not approve on their behalf", self.cli)
        for forbidden in ("approve", "create_draft", "mark_reviewed"):
            self.assertIn(forbidden, audit.FORBIDDEN_OPS)
            self.assertNotIn(forbidden, audit.OP_SPECS)


class BoundariesStayClosed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = read(TE / "SKILL.md")

    def test_reads_only_persisted_tickets_and_never_infers_one(self) -> None:
        self.assertIn("already-persisted, human-approved trade ticket", self.skill)
        self.assertIn("Never reconstruct a ticket from chat, a screenshot, a review paragraph, or Notion",
                      self.skill)
        self.assertIn("a file that is not service output is rejected", self.skill)
        self.assertIn("never builds an executable plan from chat", self.skill)

    def test_never_automates_a_broker_or_submits(self) -> None:
        self.assertIn("never clicks a broker's submit, cancel, or modify button", self.skill)
        self.assertIn("automates a broker", self.skill)
        self.assertIn("The human places every order", self.skill)

    def test_no_live_write_is_authorized_by_creating_or_testing_the_skill(self) -> None:
        self.assertIn("Creating or testing this skill authorizes no live write", self.skill)


class StopSemanticsContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = read(TE / "SKILL.md")
        cls.stop = read(TE / "references" / "stop-semantics.md")
        cls.order = read(TE / "references" / "order-semantics.md")
        cls.contract = read(TE / "references" / "ticket-contract.md")
        cls.cli = read(TE / "references" / "service-cli.md")

    def test_basis_and_activation_are_separate_required_concepts(self) -> None:
        for term in ("**basis**", "**activation**", "ENTRY_CANDLE_LOW", "PRIOR_B1_N_LOW", "WHITE_LINE",
                     "YELLOW_LINE", "KEY_K_OR_PLATFORM", "INTRADAY_HARD", "CLOSE_CONFIRM",
                     "NEXT_SESSION_FAILURE_TO_RECLAIM", "reclaim_by", "broker_implementation"):
            self.assertIn(term, self.stop)
        self.assertIn("A price alone", self.stop)

    def test_close_confirmed_stop_is_never_rendered_as_a_live_intraday_stop(self) -> None:
        self.assertIn("Execution must not turn a `CLOSE_CONFIRM` or `NEXT_SESSION_FAILURE_TO_RECLAIM` rule "
                      "into an intraday hard stop", self.stop)
        self.assertIn("Do not render that level as a STOP_LIMIT form, do not offer `attach_stop` for it",
                      self.stop)
        self.assertIn("A `CLOSE_CONFIRM` or `NEXT_SESSION_FAILURE_TO_RECLAIM` stop is never shown or "
                      "attached as a live intraday stop", self.skill)
        self.assertIn("Only a stop whose persisted `stop_semantics.activation` is `INTRADAY_HARD` becomes "
                      "a live stop-limit", self.order)
        self.assertIn("`attach_stop` needs a successful state-aware `protective` result first", self.cli)
        self.assertIn("`check-args --op attach_stop` validates only the shape of the args file and has no "
                      "ticket state", self.cli)
        self.assertIn("`protective` blocks unless it is `INTRADAY_HARD`", self.cli)
        self.assertIn("`check-args` has no ticket state and cannot see the activation", self.stop)
        self.assertIn("never authorizes `attach_stop`", self.stop)
        self.assertIn("(`check-args` cannot see ticket state and never authorizes `attach_stop` by itself)",
                      self.skill)
        self.assertIn("`protective` BLOCKS", self.skill)
        self.assertIn("`pre-submit` then prints only the human-only monitoring/exit procedure", self.skill)

    def test_too_wide_risk_is_fixed_by_quantity_not_by_tightening(self) -> None:
        self.assertIn("handled by smaller quantity in a new draft and a new human approval", self.stop)
        self.assertIn("never by moving the level, tightening it to an unrelated intraday trigger", self.stop)

    def test_missing_or_unimplementable_semantics_block_before_any_protective_order(self) -> None:
        workflow = self.skill.split("## Workflow")[1].split("## Post-trade review mode")[0]
        self.assertLess(workflow.index("**Audit stop semantics.**"), workflow.index("**Show the order.**"))
        for phrase in ("absent, ambiguous, unsupported, or the broker order cannot implement them",
                       "BLOCK and require a new draft and a new human approval",
                       "never improvise from chat"):
            self.assertIn(phrase, workflow)
        self.assertIn("repeat the stop-semantics audit", workflow)
        self.assertIn("Any failure: BLOCK", self.stop)
        self.assertIn("review.stop_semantics", self.contract)
        self.assertIn("Never fill it from chat", self.stop)

    def test_persisted_schema_is_documented_exactly_as_the_audit_enforces_it(self) -> None:
        for kind in audit.STOP_BASIS_KINDS + audit.STOP_ACTIVATIONS + audit.STOP_KEYS:
            self.assertIn(kind, self.stop)
        self.assertEqual(audit.STOP_BASIS_KINDS, ("ENTRY_CANDLE_LOW", "PRIOR_B1_N_LOW", "WHITE_LINE",
                                                  "YELLOW_LINE", "KEY_K_OR_PLATFORM"))
        self.assertEqual(audit.STOP_ACTIVATIONS, ("INTRADAY_HARD", "CLOSE_CONFIRM",
                                                  "NEXT_SESSION_FAILURE_TO_RECLAIM"))
        self.assertIn("every execution audit (`pre-submit`, `protective`) returns BLOCKED", self.stop)
        self.assertIn("`basis.level` is decimal TEXT", self.stop)
        self.assertIn("For every activation the ticket's `stop_trigger` must equal `basis.level`", self.stop)
        self.assertIn("allowed only there", self.stop)
        self.assertIn("Unknown keys BLOCK", self.stop)
        self.assertIn("`human_only_stop_plan`", self.stop)
        self.assertIn("is required on every executable ticket and validated by `audit_ticket.py`",
                      self.contract)

    def test_no_instrument_or_number_is_hard_coded_as_law(self) -> None:
        for text in (self.stop, self.skill):
            self.assertNotIn("MSFT", text)
            self.assertNotIn("527", text)
            self.assertNotIn("532", text)
        self.assertIn("never as defaults to apply", self.stop)


class PostTradeReviewScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = read(TE / "SKILL.md")
        cls.mode = cls.skill.split("## Post-trade review mode")[1].split("Creating or testing")[0]

    def test_mark_reviewed_is_not_generally_permitted(self) -> None:
        self.assertIn("`mark_reviewed` only through post-trade review mode below (it is not in "
                      "`check-args`)", self.skill)
        self.assertNotRegex(self.skill, r"Allowed `apply` operations:[^.]*mark_reviewed")
        self.assertIn("mark_reviewed", audit.FORBIDDEN_OPS)
        self.assertNotIn("mark_reviewed", audit.OP_SPECS)

    def test_scope_is_terminal_state_and_explicit_user_request(self) -> None:
        for state in ("`CLOSED`", "`CANCELLED`", "`EXPIRED`", "`REJECTED`"):
            self.assertIn(state, self.mode)
        self.assertIn("the user explicitly asks to review it or write the review back", self.mode)
        self.assertIn("human post-trade judgment, never an automatic step of execution", self.mode)
        self.assertIn("never a follow-on to a fill or exit", self.mode)
        self.assertIn("only from an outcome and note the user states explicitly", self.mode)
        self.assertIn("then read `state` back", self.mode)

    def test_review_never_infers_or_rewrites(self) -> None:
        for phrase in ("Never infer the outcome or the teaching", "never change thresholds or stop semantics",
                       "never rewrite the historical plan or ticket", "ask and write nothing",
                       "Live broker actions stay human-only"):
            self.assertIn(phrase, self.mode)


class PostTradeReviewGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = read(TE / "SKILL.md")
        cls.cli = read(TE / "references" / "service-cli.md")

    def test_dedicated_subcommand_exists_and_generic_check_args_stays_closed(self) -> None:
        self.assertIn("post-trade-review", self.skill)
        self.assertIn("audit_ticket.py post-trade-review", self.cli)
        self.assertIn("`mark_reviewed` and `mark_historical_reviewed` stay forbidden in `check-args`", self.cli)
        self.assertIn("mark_reviewed", audit.FORBIDDEN_OPS)
        self.assertNotIn("mark_reviewed", audit.OP_SPECS)

    def test_gate_conditions_and_handoff_to_the_service_are_documented(self) -> None:
        for phrase in ("exactly `CLOSED`, `CANCELLED`, `EXPIRED`, or `REJECTED` (not `REVIEWED`",
                       "`reviewed_by` `human:<name>`", "`note` (non-empty)",
                       "`机会识别成功、执行完成`", "`机会识别失败`", "`机会识别成功、执行未覆盖`",
                       "never writes", "never infers or fills them",
                       "`apply --op mark_reviewed --args-json <file>`"):
            self.assertIn(phrase, self.cli)
        for phrase in ("it prints `ARGS_OK` and never writes", "only on `ARGS_OK` run the lifecycle service",
                       "a matching `ticket_id`"):
            self.assertIn(phrase, self.skill)

    def test_documented_outcomes_are_the_audits_outcomes(self) -> None:
        for outcome in (audit.OUTCOME_DONE, audit.OUTCOME_MISSED, audit.OUTCOME_WRONG):
            self.assertIn(outcome, self.cli)
        self.assertEqual(set(audit.REVIEW_OUTCOMES_BY_STATE), set(audit.TERMINAL_STATES))


class HistoricalReviewDocs(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = read(TE / "SKILL.md")
        cls.cli = read(TE / "references" / "service-cli.md")
        cls.stop = read(TE / "references" / "stop-semantics.md")

    def test_historical_subcommand_is_documented_and_separate(self) -> None:
        for text in (self.skill, self.cli):
            self.assertIn("historical-post-trade-review", text)
            self.assertIn("mark_historical_reviewed", text)
        for phrase in ("never writes", "mandatory `state` readback", "`historical_id`",
                       "`机会识别成功、执行完成` or `机会识别失败`", "blocks any state carrying historical-import"):
            self.assertIn(phrase, self.cli)
        self.assertIn("then read `state` back", self.skill)
        self.assertIn("mark_historical_reviewed", audit.FORBIDDEN_OPS)
        self.assertNotIn("mark_historical_reviewed", audit.OP_SPECS)

    def test_broker_implementation_rule_is_documented(self) -> None:
        self.assertIn("optional for `INTRADAY_HARD`", self.stop)
        self.assertIn("required non-empty text for `CLOSE_CONFIRM` and `NEXT_SESSION_FAILURE_TO_RECLAIM`",
                      self.stop)


class ExistingBoundariesSurviveStopWork(unittest.TestCase):
    def test_approval_and_side_effect_boundaries_remain(self) -> None:
        skill = read(TE / "SKILL.md")
        for phrase in ("Never `approve`, `create_draft`, or `migrate`",
                       "Without a fresh, explicit yes, do nothing further",
                       "A live `apply` needs the user's evidence for that exact fact",
                       "Drafting is `$market-review` on an explicit 固化",
                       "Report a service rejection verbatim and do not retry it under a new key"):
            self.assertIn(phrase, skill)
        for op in ("approve", "create_draft"):
            self.assertIn(op, audit.FORBIDDEN_OPS)


class PublicSafeConfig(unittest.TestCase):
    def test_example_config_has_only_placeholders_or_null(self) -> None:
        config = json.loads((TE / "config.example.json").read_text(encoding="utf-8"))

        def walk(node: object, trail: str = "") -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{trail}.{key}")
            elif isinstance(node, str):
                self.assertRegex(node, PLACEHOLDER, trail)
            else:
                self.assertIsNone(node, trail)

        walk(config)
        self.assertEqual(set(config), {"lifecycle_service", "profiles"})

    def test_example_config_has_no_approval_hash_setting(self) -> None:
        text = (TE / "config.example.json").read_text(encoding="utf-8")
        for banned in ("sha256", "terms", "approved"):
            self.assertNotIn(banned, text)

    def test_no_machine_specific_path_in_any_shipped_file(self) -> None:
        for path in shipped_files():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                self.assertIsNone(MACHINE_PATH.search(line), f"{path.name}:{number}: {line.strip()}")

    def test_local_config_is_ignored_and_only_the_example_ships(self) -> None:
        ignore = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertTrue({"**/config.local.json", "**/*.local.json"} & set(ignore))
        self.assertTrue((TE / "config.example.json").is_file())
        self.assertIn("real values stay local", read(TE / "SKILL.md"))


if __name__ == "__main__":
    unittest.main()
