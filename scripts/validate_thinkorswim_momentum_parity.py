"""Validate the Thinkorswim Momentum Intelligence parity fixture folder.

Run from the repo root:

    python scripts/validate_thinkorswim_momentum_parity.py \\
        --fixture-dir tests/fixtures/thinkorswim_momentum

    # Write parity-report.json + parity-report.md next to the manifest.
    python scripts/validate_thinkorswim_momentum_parity.py \\
        --fixture-dir tests/fixtures/thinkorswim_momentum --write-report

    # Exit non-zero on any parity miss / missing fixture / bad manifest.
    python scripts/validate_thinkorswim_momentum_parity.py \\
        --fixture-dir tests/fixtures/thinkorswim_momentum --strict

Behavior:

- Without ``--strict`` the script always exits 0 and prints a status
  banner ("missing", "partial", "ready", "passed", or "failed"). This
  is the default so the deploy pipeline can run it as a smoke check
  without breaking on a still-pending fixture set.
- With ``--strict`` the script exits non-zero when the manifest is
  missing/invalid, a fixture file is missing, or any parity
  comparison fails.

The script never approves, rejects, sizes, or routes trades. It
never creates recommendations, paper orders, or modifies any database
state. It only reads the manifest + CSV fixtures and (when
``--write-report``) writes parity-report.json / parity-report.md next
to the manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "thinkorswim_momentum"

# Allow running from a clean checkout without `pip install -e .`.
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from macmarket_trader.indicators.thinkorswim_parity import (  # noqa: E402
    build_thinkorswim_momentum_parity_status,
    build_thinkorswim_parity_report,
)


# Exit codes (kept stable so CI / deploy scripts can map them).
EXIT_OK = 0
EXIT_MISSING = 10
EXIT_PARTIAL = 11
EXIT_FAILED = 12
EXIT_INVALID_MANIFEST = 13


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Thinkorswim Momentum Intelligence parity fixtures.",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=DEFAULT_FIXTURE_DIR,
        help="Directory holding manifest.json + the Thinkorswim CSV exports.",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write parity-report.json + parity-report.md next to the manifest.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit non-zero when the manifest is missing, invalid, or when "
            "any parity comparison fails."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report summary as JSON instead of human-readable text.",
    )
    return parser.parse_args(argv)


def _print_human_summary(status: dict, summary) -> None:
    print(f"Thinkorswim Momentum parity — {status['status']!r}")
    print(f"  fixture_dir       : {status['fixture_dir']}")
    print(f"  manifest_present  : {status['manifest_present']}")
    print(f"  manifest_valid    : {status['manifest_valid']}")
    print(f"  fixtures_total    : {status['fixtures_total']}")
    print(f"  fixtures_ready    : {status['fixtures_ready']}")
    if status.get("fixtures_passed") is not None:
        print(f"  fixtures_passed   : {status['fixtures_passed']}")
    if status.get("fixtures_failed") is not None:
        print(f"  fixtures_failed   : {status['fixtures_failed']}")
    if status.get("fixtures_skipped") is not None:
        print(f"  fixtures_skipped  : {status['fixtures_skipped']}")
    if status.get("last_report_generated_at"):
        print(f"  last_report_at    : {status['last_report_generated_at']}")
    if status.get("report_path"):
        print(f"  report (JSON)     : {status['report_path']}")
    if status.get("report_markdown_path"):
        print(f"  report (Markdown) : {status['report_markdown_path']}")
    if status.get("summary"):
        print(f"  summary           : {status['summary']}")

    # Mode summary (visual observations vs exported study CSVs).
    parity_mode_counts = status.get("parity_mode_counts") or {}
    visual_count = status.get("visual_observation_count", 0)
    exported_count = status.get("exported_study_csv_count", 0)
    visual_passed = status.get("visual_observation_passed_count", 0)
    visual_failed = status.get("visual_observation_failed_count", 0)
    exported_bucket = (
        parity_mode_counts.get("exported_study_csv", {})
        if isinstance(parity_mode_counts, dict) else {}
    )
    exported_passed = exported_bucket.get("passed", 0)
    exported_failed = exported_bucket.get("failed", 0)
    print("Mode summary:")
    print(
        f"  visual_observation: {visual_count} "
        f"({visual_passed} passed / {visual_failed} failed)"
    )
    print(
        f"  exported_study_csv: {exported_count} "
        f"({exported_passed} passed / {exported_failed} failed)"
    )
    if visual_count > 0 and exported_count == 0:
        print(
            "  parity basis      : visual / manual ToS observations "
            "(exported study CSV parity unavailable)"
        )

    if summary is not None:
        for result in summary.results:
            marker = {
                "passed": "PASS",
                "failed": "FAIL",
            }.get(result.status, result.status.upper())
            mode_label = (
                "VISUAL" if result.parity_mode == "visual_observation" else "STUDYCSV"
            )
            print(
                f"  - {result.fixture_name} [{result.symbol} {result.timeframe}] "
                f"({mode_label}) {marker}"
            )
            if result.is_visual:
                if result.reviewer:
                    print(f"      reviewer: {result.reviewer}")
                if result.observed_bar_date:
                    print(f"      observed_bar_date: {result.observed_bar_date}")
                if result.screenshot:
                    print(f"      screenshot: {result.screenshot}")
                print(
                    "      basis: manual visual parity — Thinkorswim does not export "
                    "the Momentum study rows"
                )
            for delta in result.field_deltas:
                ok = "ok" if delta.within_tolerance else "MISS"
                # ASCII-only to keep the Windows cp1252 console happy.
                print(
                    f"      {delta.field:>20s} expected={delta.expected:>10.4f} "
                    f"actual={delta.actual:>10.4f} abs_err={delta.abs_error:>8.4f} "
                    f"tol={delta.tolerance:.2f}  [{ok}]"
                )
            for msg in result.mismatches:
                print(f"      mismatch: {msg}")
            for msg in result.label_mismatches:
                print(f"      label:    {msg}")
    print(
        "\nThis validator is research-only. A parity pass does not approve trades, "
        "auto-activate Phase C, or change any ranking math."
    )
    if visual_count > 0:
        print(
            "Visual observations are operator-entered from rendered Thinkorswim chart "
            "labels. They are auditable but not row-level CSV exports."
        )


def _resolve_exit_code(status: dict, *, strict: bool) -> int:
    workflow = status["status"]
    if not strict:
        return EXIT_OK
    if workflow == "missing":
        if not status.get("manifest_present"):
            return EXIT_MISSING
        return EXIT_INVALID_MANIFEST
    if workflow == "partial":
        return EXIT_PARTIAL
    if workflow == "failed":
        return EXIT_FAILED
    # "ready" and "passed" are both fine under --strict.
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    fixture_dir = args.fixture_dir.resolve()

    summary = None
    if args.write_report or (fixture_dir / "manifest.json").exists():
        summary = build_thinkorswim_parity_report(fixture_dir, write=args.write_report)

    status = build_thinkorswim_momentum_parity_status(fixture_dir)

    if args.json:
        payload: dict = {"status": status}
        if summary is not None:
            payload["report"] = summary.to_dict()
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print_human_summary(status, summary)

    return _resolve_exit_code(status, strict=args.strict)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
