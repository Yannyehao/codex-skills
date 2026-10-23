#!/usr/bin/env python3
"""Audit the integrity of the latest zAI U.S. nightly review artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


DATE_RE = re.compile(r"(\d{8})")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dated_files(folder: Path, pattern: str) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    for path in folder.glob(pattern):
        match = DATE_RE.search(path.name)
        if match:
            found.append((match.group(1), path))
    return sorted(found)


def normalized_date(value: Any) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits[:8] if len(digits) >= 8 else None


def answer_object(result: dict[str, Any]) -> dict[str, Any]:
    answer = result.get("answer")
    if isinstance(answer, dict):
        return answer
    if isinstance(answer, str):
        try:
            parsed = json.loads(answer)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def evidence_reads_image(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    types = value.get("tool_result_types")
    return isinstance(types, list) and "image" in types


def evidence_matches_image(value: Any, image_path: Path) -> bool:
    if not evidence_reads_image(value):
        return False
    evidence_path = value.get("file_path")
    if not evidence_path:
        return False
    return Path(str(evidence_path)).resolve() == image_path.resolve()


def resolve_image(path_value: Any, chart_dir: Path, symbol: str) -> Path:
    if path_value:
        supplied = Path(str(path_value))
        if supplied.exists():
            return supplied
    return chart_dir / f"{symbol}.png"


def audit(config_path: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    config = load_json(config_path)
    project_value = config.get("project_root") if isinstance(config, dict) else None
    if not project_value or str(project_value).startswith("PATH_TO_"):
        return {}, ["config.project_root is missing or still a placeholder"]

    project_root = Path(str(project_value)).expanduser().resolve()
    output_root = project_root / "zradar" / "out"
    nightly_files = dated_files(output_root, "us_nightly_report_*.json")
    review_files = dated_files(output_root, "us_b1_review_*.json")
    if not nightly_files:
        errors.append(f"no nightly reports under {output_root}")
    if not review_files:
        errors.append(f"no B1 review reports under {output_root}")
    if errors:
        return {"project_root": str(project_root)}, errors

    nightly_date, nightly_path = nightly_files[-1]
    review_date, review_path = review_files[-1]
    if nightly_date != review_date:
        errors.append(
            f"latest report dates differ: nightly={nightly_date}, b1={review_date}"
        )
    audit_date = nightly_date
    chart_root = output_root / "charts" / "us_b1"
    chart_dates = sorted(
        path.name
        for path in chart_root.glob("*")
        if path.is_dir() and re.fullmatch(r"\d{8}", path.name)
    ) if chart_root.is_dir() else []
    if not chart_dates:
        errors.append(f"no dated chart directories under {chart_root}")
    elif chart_dates[-1] != audit_date:
        errors.append(
            f"latest chart date differs: charts={chart_dates[-1]}, nightly={audit_date}"
        )
    chart_dir = output_root / "charts" / "us_b1" / audit_date
    manifest_path = chart_dir / "_capture_manifest.json"
    if not chart_dir.is_dir():
        errors.append(f"chart directory missing: {chart_dir}")
    if not manifest_path.is_file():
        errors.append(f"capture manifest missing: {manifest_path}")
    if errors:
        return {
            "date": audit_date,
            "nightly_report": str(nightly_path),
            "b1_review": str(review_path),
        }, errors

    nightly = load_json(nightly_path)
    review = load_json(review_path)
    manifest = load_json(manifest_path)

    for label, payload in (("nightly", nightly), ("b1", review)):
        if payload.get("complete") is not True:
            errors.append(f"{label} report complete is not true")
        payload_date = normalized_date(payload.get("as_of_date") or payload.get("date"))
        expected = nightly_date if label == "nightly" else review_date
        if payload_date != expected:
            errors.append(f"{label} payload date {payload_date!r} != filename date {expected}")

    if normalized_date(manifest.get("date")) != audit_date:
        errors.append("manifest date does not match latest nightly date")
    if manifest.get("period_verified") is not True:
        errors.append("manifest period_verified is not true")
    if manifest.get("n_ok") != manifest.get("n_total"):
        errors.append(
            f"manifest has failed captures: n_ok={manifest.get('n_ok')} n_total={manifest.get('n_total')}"
        )
    if manifest.get("n_total") != len(manifest.get("results", [])):
        errors.append("manifest n_total does not equal its result count")

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
    missing_reviews = sorted(set(manifest_results) - set(review_results))
    for symbol in missing_reviews:
        errors.append(f"{symbol}: captured image has no B1 review result")

    checked_symbols: list[str] = []
    for symbol, result in sorted(review_results.items()):
        image_value = result.get("image_path")
        if not image_value:
            continue
        checked_symbols.append(symbol)
        image_path = resolve_image(image_value, chart_dir, symbol)
        if not image_path.is_file():
            errors.append(f"{symbol}: image missing: {image_path}")
            continue
        if image_path.resolve().parent != chart_dir.resolve():
            errors.append(f"{symbol}: B1 image is outside the latest chart directory")

        actual_sha = sha256(image_path)
        report_sha = result.get("image_sha256")
        if actual_sha != report_sha:
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
        if normalized_date(metadata.get("date")) != audit_date:
            errors.append(f"{symbol}: render date does not match report date")
        manifest_sha = metadata.get("png_sha256")
        if actual_sha != manifest_sha:
            errors.append(f"{symbol}: image SHA differs from capture manifest")
        if answer.get("image_token") != metadata.get("check_token"):
            errors.append(f"{symbol}: answer image token differs from rendered token")

    nightly_rows = [row for row in nightly.get("rows", []) if isinstance(row, dict)]
    for row in nightly_rows:
        symbol = str(row.get("symbol", "")).upper()
        image = row.get("image")
        if not symbol or not isinstance(image, dict):
            continue
        image_source = str(image.get("source", "")).lower()
        if image_source == "b1" and symbol not in review_results:
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

    report_symbols = sorted(
        str(row.get("symbol", "")).upper() for row in nightly_rows if row.get("symbol")
    )
    fresh_symbols = sorted(
        str(row.get("symbol", "")).upper()
        for row in nightly_rows
        if row.get("symbol") and row.get("fresh") is True
    )
    continuing_symbols = sorted(set(report_symbols) - set(fresh_symbols))
    summary = {
        "date": audit_date,
        "complete": not errors,
        "nightly_report": str(nightly_path),
        "b1_review": str(review_path),
        "chart_directory": str(chart_dir),
        "report_symbols": report_symbols,
        "fresh_symbols": fresh_symbols,
        "continuing_symbols": continuing_symbols,
        "verified_image_evidence_symbols": checked_symbols,
        "non_b1_symbols": sorted(set(report_symbols) - set(review_results)),
    }
    return summary, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config.local.json",
        help="Path to the ignored local configuration file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.config.is_file():
        print(
            json.dumps(
                {"complete": False, "errors": [f"config missing: {args.config}"]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    summary, errors = audit(args.config)
    summary["errors"] = errors
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
