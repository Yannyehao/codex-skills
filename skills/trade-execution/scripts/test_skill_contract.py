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
