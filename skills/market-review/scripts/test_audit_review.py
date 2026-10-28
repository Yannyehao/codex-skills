#!/usr/bin/env python3
"""Synthetic-fixture tests for audit_review.py. They never read a real project tree."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import audit_review as audit


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_bundle(root: Path, date: str, *, complete: bool = True, with_b1: bool = True,
                with_charts: bool = True) -> Path:
    """Write one internally consistent bundle: AAA has a B1 chart, BBB a non-B1 chart."""
    out = root / "zradar" / "out"
    iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    chart_dir = out / "charts" / "us_b1" / date
    chart_dir.mkdir(parents=True, exist_ok=True)

    def image(symbol: str) -> tuple[Path, str]:
        path = chart_dir / f"{symbol}.png"
        path.write_bytes(f"png-{symbol}-{date}".encode())
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def evidence(path: Path) -> dict:
        return {"tool_result_types": ["image"], "file_path": str(path)}

    aaa, aaa_sha = image("AAA")
    bbb, bbb_sha = image("BBB")
    write_json(out / f"us_nightly_report_{date}.json", {
        "complete": complete, "as_of_date": iso,
        "rows": [
            {"symbol": "AAA", "fresh": True, "image": {
                "source": "b1", "image_path": str(aaa), "image_sha256": aaa_sha,
                "read_evidence": evidence(aaa)}},
            {"symbol": "BBB", "fresh": False, "image": {
                "source": "tdx", "image_path": str(bbb), "image_sha256": bbb_sha,
                "read_evidence": evidence(bbb)}},
        ],
    })
    if with_b1:
        write_json(out / f"us_b1_review_{date}.json", {
            "complete": complete, "as_of_date": iso,
            "results": [{
                "symbol": "AAA", "image_path": str(aaa), "image_sha256": aaa_sha,
                "read_evidence": evidence(aaa),
                "answer": {"image_read": True, "image_token": "tok"}}],
        })
    if with_charts:
        write_json(chart_dir / "_capture_manifest.json", {
            "date": date, "period_verified": True, "n_ok": 1, "n_total": 1,
            "results": [{"code": "AAA", "ok": True, "render_metadata": {
                "date": date, "png_sha256": aaa_sha, "check_token": "tok"}}],
        })
    return out


def run(root: Path, require_date: str | None = None) -> dict:
    return audit.audit_us({"project_root": str(root)}, require_date)


class SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_newest_complete_bundle_is_selected(self) -> None:
        make_bundle(self.root, "20261023")
        make_bundle(self.root, "20261026")
        result = run(self.root)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["date"], "20261026")
        self.assertTrue(result["selected_is_newest_present"])
        self.assertEqual(result["non_b1_symbols"], ["BBB"])
        self.assertEqual(result["fresh_symbols"], ["AAA"])

    def test_partial_newer_nightly_does_not_shadow_complete_date(self) -> None:
        make_bundle(self.root, "20261023")
        # Newest date: nightly is still running, so no B1 report or manifest exists yet.
        make_bundle(self.root, "20261026", complete=False, with_b1=False, with_charts=False)
        result = run(self.root)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["date"], "20261023")
        self.assertFalse(result["selected_is_newest_present"])
        self.assertEqual(result["newest_date_present"], "20261026")
        skipped = result["skipped_newer_dates"]
        self.assertEqual([item["date"] for item in skipped], ["20261026"])
        self.assertIn("B1 review report missing", skipped[0]["problems"])

    def test_declared_incomplete_newer_bundle_is_skipped(self) -> None:
        make_bundle(self.root, "20261023")
        make_bundle(self.root, "20261026", complete=False)
        result = run(self.root)
        self.assertEqual(result["date"], "20261023")
        problems = result["skipped_newer_dates"][0]["problems"]
        self.assertIn("nightly report complete is not true", problems)

    def test_chart_only_directory_for_newer_date_is_skipped(self) -> None:
        make_bundle(self.root, "20261023")
        (self.root / "zradar" / "out" / "charts" / "us_b1" / "20261027").mkdir(parents=True)
        result = run(self.root)
        self.assertEqual(result["date"], "20261023")
        self.assertEqual(result["skipped_newer_dates"][0]["date"], "20261027")

    def test_require_date_does_not_fall_back(self) -> None:
        make_bundle(self.root, "20261023")
        make_bundle(self.root, "20261026", complete=False)
        result = run(self.root, "20261026")
        self.assertIsNone(result.get("date"))
        self.assertTrue(result["errors"])

    def test_no_complete_bundle_is_an_error(self) -> None:
        make_bundle(self.root, "20261026", complete=False)
        result = run(self.root)
        self.assertIn("no complete artifact bundle found", result["errors"])

    def test_missing_artifact_directory_is_an_error(self) -> None:
        result = run(self.root)
        self.assertTrue(result["errors"])


class IntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_hash_mismatch_in_selected_bundle_is_error_not_fallback(self) -> None:
        make_bundle(self.root, "20261023")
        out = make_bundle(self.root, "20261026")
        (out / "charts" / "us_b1" / "20261026" / "AAA.png").write_bytes(b"tampered")
        result = run(self.root)
        self.assertEqual(result["date"], "20261026")
        self.assertTrue(any("SHA differs" in e for e in result["errors"]))

    def test_wrong_image_token_is_error(self) -> None:
        out = make_bundle(self.root, "20261026")
        path = out / "us_b1_review_20261026.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["results"][0]["answer"]["image_token"] = "other"
        write_json(path, data)
        result = run(self.root)
        self.assertTrue(any("token" in e for e in result["errors"]))

    def test_missing_read_evidence_is_error(self) -> None:
        out = make_bundle(self.root, "20261026")
        path = out / "us_nightly_report_20261026.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["rows"][1]["image"]["read_evidence"] = {"tool_result_types": ["text"]}
        write_json(path, data)
        result = run(self.root)
        self.assertTrue(any("BBB" in e and "read evidence" in e for e in result["errors"]))


class ConfigTests(unittest.TestCase):
    def test_legacy_flat_config_is_the_us_profile(self) -> None:
        section = audit.profile_config({"project_root": "x"}, "us")
        self.assertEqual(section, {"project_root": "x"})

    def test_profiles_layout_and_unknown_profile(self) -> None:
        data = {"profiles": {"us": {"project_root": "x"}}}
        self.assertEqual(audit.profile_config(data, "us"), {"project_root": "x"})
        self.assertIsNone(audit.profile_config(data, "a"))

    def test_placeholder_project_root_is_rejected(self) -> None:
        result = audit.audit_us({"project_root": "PATH_TO_ZAI_REPOSITORY"}, None)
        self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
