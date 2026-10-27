#!/usr/bin/env python3
"""Read-only audit of the latest COMPLETE machine-artifact bundle for a market profile.

The newest dated file is not necessarily the newest usable session: a nightly run that is
still in progress, failed, or half-written leaves a newer but incomplete date. This script
selects the latest date whose whole bundle is complete, reports every newer date it skipped,
and then audits the selected bundle's integrity. It proves integrity, not interpretation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

SKILL_ROOT = Path(__file__).resolve().parents[1]
LEGACY_US_CONFIG = SKILL_ROOT.parent / "us-market-review" / "config.local.json"
DATE_RE = re.compile(r"\d{8}")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_date(value: Any) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits[:8] if len(digits) >= 8 else None


def answer_object(result: dict[str, Any]) -> dict[str, Any]:
    answer = result.get("answer")
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except json.JSONDecodeError:
            return {}
    return answer if isinstance(answer, dict) else {}


def evidence_matches_image(value: Any, image_path: Path) -> bool:
    if not isinstance(value, dict):
        return False
    types = value.get("tool_result_types")
    if not isinstance(types, list) or "image" not in types:
        return False
    evidence_path = value.get("file_path")
    return bool(evidence_path) and Path(str(evidence_path)).resolve() == image_path.resolve()


def resolve_image(path_value: Any, chart_dir: Path, symbol: str) -> Path:
    if path_value:
        supplied = Path(str(path_value))
        if supplied.exists():
            return supplied
    return chart_dir / f"{symbol}.png"


def select_latest_complete(
    dates: list[str], problems_for: Callable[[str], list[str]]
) -> tuple[str | None, list[dict[str, Any]]]:
    """Return the newest date with no problems, plus every newer date that was skipped."""
    skipped: list[dict[str, Any]] = []
    for date in sorted(dates, reverse=True):
        problems = problems_for(date)
        if not problems:
            return date, skipped
        skipped.append({"date": date, "problems": problems})
    return None, skipped


# --------------------------------------------------------------------------- US profile


class UsBundle:
    """Path layout of one zAI U.S. nightly bundle."""

    def __init__(self, output_root: Path, date: str) -> None:
        self.date = date
        self.nightly = output_root / f"us_nightly_report_{date}.json"
        self.review = output_root / f"us_b1_review_{date}.json"
        self.chart_dir = output_root / "charts" / "us_b1" / date
        self.manifest = self.chart_dir / "_capture_manifest.json"


def us_dates(output_root: Path) -> list[str]:
    found: set[str] = set()
    for pattern in ("us_nightly_report_*.json", "us_b1_review_*.json"):
        for path in output_root.glob(pattern):
            match = re.search(r"_(\d{8})\.json$", path.name)
            if match:
                found.add(match.group(1))
    chart_root = output_root / "charts" / "us_b1"
    if chart_root.is_dir():
        found.update(
            p.name for p in chart_root.iterdir() if p.is_dir() and DATE_RE.fullmatch(p.name)
        )
    return sorted(found)


def us_completeness_problems(output_root: Path, date: str) -> list[str]:
    """Structural and declared completeness only; hash and read-evidence checks come later."""
    bundle = UsBundle(output_root, date)
    problems: list[str] = []
    for label, path in (
        ("nightly report", bundle.nightly),
        ("B1 review report", bundle.review),
        ("capture manifest", bundle.manifest),
    ):
        if not path.is_file():
            problems.append(f"{label} missing")
    if problems:
        return problems

    try:
        nightly = load_json(bundle.nightly)
        review = load_json(bundle.review)
        manifest = load_json(bundle.manifest)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"unreadable artifact: {exc}"]
    if not all(isinstance(item, dict) for item in (nightly, review, manifest)):
        return ["artifact root is not a JSON object"]

    for label, payload in (("nightly", nightly), ("B1 review", review)):
        if payload.get("complete") is not True:
            problems.append(f"{label} report complete is not true")
        payload_date = normalized_date(payload.get("as_of_date") or payload.get("date"))
        if payload_date != date:
            problems.append(f"{label} payload date {payload_date!r} != filename date {date}")
    if normalized_date(manifest.get("date")) != date:
        problems.append("capture manifest date differs from bundle date")
    if manifest.get("period_verified") is not True:
        problems.append("capture manifest period_verified is not true")
    if manifest.get("n_ok") != manifest.get("n_total"):
        problems.append(
            f"capture manifest has failed captures: n_ok={manifest.get('n_ok')} "
            f"n_total={manifest.get('n_total')}"
        )
    if manifest.get("n_total") != len(manifest.get("results", [])):
        problems.append("capture manifest n_total does not equal its result count")
    return problems


def us_integrity_errors(bundle: UsBundle) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    nightly = load_json(bundle.nightly)
    review = load_json(bundle.review)
    manifest = load_json(bundle.manifest)
    chart_dir = bundle.chart_dir

    manifest_results = {
        str(item.get("code", "")).upper(): item
        for item in manifest.get("results", [])
        if isinstance(item, dict) and item.get("code")
    }
    review_results = {
        str(item.get("symbol", "")).upper(): item
        for item in review.get("results", [])
        if isinstance(item, dict) and item.get("symbol")
    }
    for symbol in sorted(set(manifest_results) - set(review_results)):
        errors.append(f"{symbol}: captured image has no B1 review result")

    checked: list[str] = []
    for symbol, result in sorted(review_results.items()):
        image_value = result.get("image_path")
        if not image_value:
            continue
        checked.append(symbol)
        image_path = resolve_image(image_value, chart_dir, symbol)
        if not image_path.is_file():
            errors.append(f"{symbol}: image missing: {image_path}")
            continue
        if image_path.resolve().parent != chart_dir.resolve():
            errors.append(f"{symbol}: B1 image is outside the selected chart directory")

        actual_sha = sha256(image_path)
        if actual_sha != result.get("image_sha256"):
            errors.append(f"{symbol}: image SHA differs from B1 report")
        if not evidence_matches_image(result.get("read_evidence"), image_path):
            errors.append(f"{symbol}: B1 result lacks matching image read evidence")
        answer = answer_object(result)
        if answer.get("image_read") is not True:
            errors.append(f"{symbol}: answer.image_read is not true")

        captured = manifest_results.get(symbol)
        if not captured:
            errors.append(f"{symbol}: absent from capture manifest")
            continue
        if captured.get("ok") is not True:
            errors.append(f"{symbol}: capture manifest result is not ok")
        metadata = captured.get("render_metadata") or {}
        if normalized_date(metadata.get("date")) != bundle.date:
            errors.append(f"{symbol}: render date does not match bundle date")
        if actual_sha != metadata.get("png_sha256"):
            errors.append(f"{symbol}: image SHA differs from capture manifest")
        if answer.get("image_token") != metadata.get("check_token"):
            errors.append(f"{symbol}: answer image token differs from rendered token")

    rows = [row for row in nightly.get("rows", []) if isinstance(row, dict)]
    for row in rows:
        symbol = str(row.get("symbol", "")).upper()
        image = row.get("image")
        if not symbol or not isinstance(image, dict):
            continue
        if str(image.get("source", "")).lower() == "b1" and symbol not in review_results:
            errors.append(f"{symbol}: nightly row has B1 image but no B1 review result")
            continue
        image_path = resolve_image(image.get("image_path"), chart_dir, symbol)
        if not image_path.is_file():
            errors.append(f"{symbol}: nightly image is missing")
            continue
        if sha256(image_path) != image.get("image_sha256"):
            errors.append(f"{symbol}: image SHA differs from nightly report")
        if not evidence_matches_image(image.get("read_evidence"), image_path):
            errors.append(f"{symbol}: nightly row lacks matching image read evidence")

    report_symbols = sorted(str(r.get("symbol", "")).upper() for r in rows if r.get("symbol"))
    fresh = sorted(
        str(r.get("symbol", "")).upper() for r in rows if r.get("symbol") and r.get("fresh") is True
    )
    summary = {
        "nightly_report": str(bundle.nightly),
        "b1_review": str(bundle.review),
        "chart_directory": str(chart_dir),
        "report_symbols": report_symbols,
        "fresh_symbols": fresh,
        "continuing_symbols": sorted(set(report_symbols) - set(fresh)),
        "verified_image_evidence_symbols": checked,
        "non_b1_symbols": sorted(set(report_symbols) - set(review_results)),
    }
    return summary, errors


def audit_us(profile_config: dict[str, Any], require_date: str | None) -> dict[str, Any]:
    project_value = profile_config.get("project_root")
    if not project_value or str(project_value).startswith("PATH_TO_"):
        return {"errors": ["profile project_root is missing or still a placeholder"]}
    output_root = Path(str(project_value)).expanduser().resolve() / "zradar" / "out"
    if not output_root.is_dir():
        return {"errors": [f"artifact directory not found: {output_root}"]}

    all_dates = us_dates(output_root)
    if require_date:
        candidates = [require_date]
    else:
        candidates = all_dates
    selected, skipped = select_latest_complete(
        candidates, lambda d: us_completeness_problems(output_root, d)
    )
    result: dict[str, Any] = {
        "newest_date_present": all_dates[-1] if all_dates else None,
        "skipped_newer_dates": skipped,
    }
    if selected is None:
        result["errors"] = ["no complete artifact bundle found"]
        return result

    summary, errors = us_integrity_errors(UsBundle(output_root, selected))
    result.update(summary)
    result["date"] = selected
    result["selected_is_newest_present"] = selected == result["newest_date_present"]
    result["errors"] = errors
    return result


PROFILES: dict[str, Callable[[dict[str, Any], str | None], dict[str, Any]]] = {"us": audit_us}


# ------------------------------------------------------------------------------ config


def default_config(profile: str) -> Path:
    local = SKILL_ROOT / "config.local.json"
    if local.is_file():
        return local
    if profile == "us" and LEGACY_US_CONFIG.is_file():
        return LEGACY_US_CONFIG
    return local


def profile_config(data: Any, profile: str) -> dict[str, Any] | None:
    """Accept the `profiles` layout, or the legacy flat layout for the U.S. profile."""
    if not isinstance(data, dict):
        return None
    profiles = data.get("profiles")
    if isinstance(profiles, dict):
        section = profiles.get(profile)
        return section if isinstance(section, dict) else None
    if profile == "us" and "project_root" in data:
        return data
    return None


def fail(profile: str, message: str) -> int:
    print(json.dumps({"profile": profile, "complete": False, "errors": [message]},
                     ensure_ascii=False, indent=2))
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="us")
    parser.add_argument("--config", type=Path, help="Ignored local configuration file.")
    parser.add_argument("--require-date", metavar="YYYYMMDD",
                        help="Audit only this session; fail instead of falling back to an older one.")
    args = parser.parse_args()
    if args.require_date and not DATE_RE.fullmatch(args.require_date):
        return fail(args.profile, "--require-date must be YYYYMMDD")

    config_path = args.config or default_config(args.profile)
    if not config_path.is_file():
        return fail(args.profile, f"config missing: {config_path}")
    try:
        section = profile_config(load_json(config_path), args.profile)
    except (OSError, json.JSONDecodeError) as exc:
        return fail(args.profile, f"config unreadable: {exc}")
    if section is None:
        return fail(args.profile, f"config has no usable '{args.profile}' profile")

    result = PROFILES[args.profile](section, args.require_date)
    errors = result.setdefault("errors", [])
    result = {"profile": args.profile, "complete": not errors, **result}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
