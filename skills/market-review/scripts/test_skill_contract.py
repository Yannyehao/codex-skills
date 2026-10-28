#!/usr/bin/env python3
"""Contract tests for the market-review documents and the shared repository hygiene.

The review rules live in Markdown, so these tests read the committed skill files and prove that
each frozen-contract behaviour is stated where the model will read it, that the market profiles stay
thin, that the legacy alias stays explicit-only, and that configs are public-safe. They read only
files inside this repository: never a `*.local.json`, a database, a network, or a broker.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]
REPO = SKILLS.parent
MR = SKILLS / "market-review"

# Matches a drive path, a user-profile path, or a home path: machine-specific content.
MACHINE_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|/home/|\\\\[A-Za-z0-9_.-]+\\")
PLACEHOLDER = re.compile(r"^(PATH_TO_[A-Z_]+|NOTION_DATABASE_URL|collection://[A-Z_]*ID|"
                         r"(review|human|import):NAME)$")
# Canonical-grammar facet names belong to the service contract, never to a skill file.
FACETS = ("yellow_white_relation_slope", "price_location", "rising_n", "macd_zero_environment",
          "post_rise_pullback_days_amplitude", "volume_contraction_time_for_space",
          "structural_low_held", "anchor_touch_or_reclaim", "first_strong_red_inc_first_brick",
          "kdj_golden_cross_confirmation_k", "high_position_third_wave_risk")


def read(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def skill_text_files(skill: Path) -> list[Path]:
    wanted = {".md", ".json", ".yaml", ".yml", ".py", ".ps1"}
    return [p for p in skill.rglob("*") if p.is_file() and p.suffix in wanted
            and "__pycache__" not in p.parts and not p.name.endswith(".local.json")]


class CanonicalCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = read(MR / "references" / "review-contract.md")
        cls.skill = read(MR / "SKILL.md")

    def assertAll(self, text: str, *fragments: str) -> None:
        for fragment in fragments:
            self.assertIn(fragment, text)

    def test_routes_to_lifecycle_service_cards_as_the_canonical_representation(self) -> None:
        self.assertAll(self.contract, "Canonical representation: lifecycle cards",
                       "canonical record", "opportunity_episode_flow cards",
                       "projections of it", "the service wins")
        self.assertAll(self.skill, "lifecycle cards", "`cards`", "`audit`", "`hierarchy`")
        self.assertIn("never a reason to reconstruct one from a screenshot or from chat", self.contract)

    def test_scanner_is_high_recall_or_and_shows_fresh_raw_plus_every_active_episode(self) -> None:
        self.assertAll(self.contract, "high-recall OR", "fresh raw signals of the session",
                       "every active episode that is not terminated",
                       "whether or not it was reselected today",
                       "A failed gate never removes a card or an audit row")

    def test_six_gates_are_readable_evidence_not_an_and_filter_or_score(self) -> None:
        self.assertAll(self.contract, "The six gates are readable evidence, not a filter or a score",
                       "`PASS`, `WAIT`, or `FAIL`", "not an AND recall filter",
                       "do not hide, rank, or drop a card", "invent a score",
                       "authorizes nothing")

    def test_trend_alive_is_the_sole_broad_exclusion_and_warnings_stay_visible(self) -> None:
        self.assertAll(self.contract, "TrendAlive is the only broad exclusion from the active workset",
                       "`CONFIRMED_TERMINATED`", "is a warning: the card stays active",
                       "the warning stays visible", "does not revive a terminated parent trend")
        self.assertEqual(self.contract.count("only broad exclusion"), 1)

    def test_single_needle_is_discovery_watch_and_never_acts_alone(self) -> None:
        self.assertAll(self.contract, "A single needle is discovery / watch",
                       "cannot become `ACTIONABLE` by itself")

    def test_trigger_never_auto_actionable_and_review_never_sets_stage(self) -> None:
        self.assertAll(self.contract, "A trigger never creates `ACTIONABLE`",
                       "authorizes nothing", "never infers, writes, or upgrades a stage")
        draft = read(MR / "references" / "ticket-draft.md")
        self.assertAll(draft, "Stage and `ACTIONABLE` are never yours to set",
                       "a trigger, a single needle, or `eligible_review` alone is not that")

    def test_human_review_may_create_only_a_draft(self) -> None:
        self.assertAll(self.contract, "Human review may create only a DRAFT")
        self.assertAll(self.skill, "persists one DRAFT trade ticket", "never approves, submits")
        draft = read(MR / "references" / "ticket-draft.md")
        self.assertAll(draft, "writes exactly one DRAFT", "Do not run `approve`")

    def test_every_evidence_statement_keeps_its_knowledge_class(self) -> None:
        self.assertAll(self.contract, "Every evidence statement keeps its `knowledge_class`",
                       "stays `WAIT`, never promoted", "case-derived induction")

    def test_review_runs_only_read_only_service_commands(self) -> None:
        self.assertAll(self.skill, "read-only `list`, `state`, and the episode flow's `cards`, `audit`, and `hierarchy`")
        self.assertAll(self.contract, "the service's `list`, `state`, `cards`, `audit`, `hierarchy` only")


class ThinProfiles(unittest.TestCase):
    def test_profiles_hold_market_facts_only(self) -> None:
        for name in ("us-profile.md", "a-profile.md"):
            text = read(MR / "references" / name)
            for banned in ("TrendAlive", "PASS", "WAIT", "FAIL", "eligible_review", "knowledge_class",
                           *FACETS):
                self.assertNotIn(banned, text, f"{name} must not restate the shared grammar: {banned}")
            self.assertIn("review-contract.md", text)

    def test_grammar_facets_are_not_copied_into_any_skill_file(self) -> None:
        for skill in ("market-review", "trade-execution", "us-market-review"):
            for path in skill_text_files(SKILLS / skill):
                if path.name.startswith("test_"):
                    continue
                text = path.read_text(encoding="utf-8")
                for facet in FACETS:
                    self.assertNotIn(facet, text, f"{path.name} copies service grammar: {facet}")

    def test_gate_vocabulary_lives_only_in_the_shared_contract(self) -> None:
        for path in skill_text_files(MR):
            if path.suffix != ".md" or path.name == "review-contract.md":
                continue
            self.assertNotIn("TrendAlive", path.read_text(encoding="utf-8"), path.name)

    def test_no_a_share_duplicate_skill(self) -> None:
        names = sorted(p.name for p in SKILLS.iterdir() if p.is_dir())
        self.assertEqual([n for n in names if re.search(r"(^a[-_]|a[-_]?share|cn[-_]|china)", n)], [])
        skill = read(MR / "SKILL.md")
        self.assertIn("references/a-profile.md", skill)
        self.assertIn("references/us-profile.md", skill)
        self.assertTrue((MR / "references" / "a-profile.md").is_file())


class LegacyAlias(unittest.TestCase):
    def test_us_market_review_is_an_explicit_only_alias_with_no_logic_of_its_own(self) -> None:
        alias = SKILLS / "us-market-review"
        yaml = (alias / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertRegex(yaml, r"allow_implicit_invocation:\s*false")
        text = read(alias / "SKILL.md")
        self.assertIn("Explicit-only compatibility alias", text)
        self.assertIn("generic phrases such as 美股复盘 route to market-review, not here", text)
        self.assertIn("holds no review contract, script, or ledger logic of its own", text)
        files = sorted(str(p.relative_to(alias)).replace("\\", "/") for p in alias.rglob("*")
                       if p.is_file() and not p.name.endswith(".local.json"))
        self.assertEqual(files, ["SKILL.md", "agents/openai.yaml"])

    def test_market_review_itself_triggers_implicitly(self) -> None:
        yaml = (MR / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertNotIn("allow_implicit_invocation: false", yaml)


class PublicSafeConfig(unittest.TestCase):
    def test_example_config_has_only_placeholders(self) -> None:
        def walk(node: object, trail: str = "") -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{trail}.{key}")
            elif isinstance(node, str):
                if trail.startswith(".profiles.us.viewpoint_symbols"):
                    self.assertRegex(node, r"^[A-Z0-9]+(\.[A-Z]+)?$", trail)
                else:
                    self.assertRegex(node, PLACEHOLDER, trail)
            else:
                self.assertIsNone(node, trail)

        walk(json.loads((MR / "config.example.json").read_text(encoding="utf-8")))

    def test_no_machine_specific_path_in_any_skill_file(self) -> None:
        for skill in ("market-review", "trade-execution", "us-market-review", "ste-fr", "lexicon-ingest"):
            for path in skill_text_files(SKILLS / skill):
                if path.name.startswith("test_"):
                    continue
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    self.assertIsNone(MACHINE_PATH.search(line), f"{path.name}:{number}: {line.strip()}")

    def test_local_configs_are_ignored_and_not_shipped(self) -> None:
        ignore = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertTrue({"**/config.local.json", "**/*.local.json"} & set(ignore))
        self.assertIn("never holds real values", read(MR / "SKILL.md"))
        for skill in ("market-review", "trade-execution"):
            self.assertTrue((SKILLS / skill / "config.example.json").is_file())


if __name__ == "__main__":
    unittest.main()
