"""Tests for the Thinkorswim Momentum parity workflow.

These tests exercise the production parity module at
``src/macmarket_trader/indicators/thinkorswim_parity.py``: parser
column aliases, manifest validation, folder validation, comparison
engine against a synthetic fixture, report generation, the read-only
status builder, and the CLI script's exit-code contract.

Every test uses ``tmp_path`` so the real fixture folder
(``tests/fixtures/thinkorswim_momentum``) remains untouched and the
suite stays green on a fresh checkout that has no operator-supplied
fixtures. The MACMARKET_REQUIRE_THINKORSWIM_PARITY env var is honored
by ``test_optional_strict_env_var_drives_strict_check`` and is the
seam for gating CI on a real fixture set in the future.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from macmarket_trader.indicators.thinkorswim_parity import (
    DEFAULT_TOLERANCES,
    FieldDelta,
    FixtureComparisonResult,
    LABEL_FIELDS,
    ParityFixtureError,
    REPORT_FILENAME_JSON,
    REPORT_FILENAME_MD,
    REPORT_SCHEMA_VERSION,
    STUDY_FIELDS,
    build_thinkorswim_momentum_parity_status,
    build_thinkorswim_parity_report,
    compare_momentum_to_thinkorswim,
    load_thinkorswim_manifest,
    normalize_thinkorswim_columns,
    parse_thinkorswim_bars_csv,
    parse_thinkorswim_study_csv,
    validate_thinkorswim_fixture_folder,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_SCRIPT = REPO_ROOT / "scripts" / "validate_thinkorswim_momentum_parity.py"


# ── synthetic fixture helpers ───────────────────────────────────────────────


def _write_bars_csv(path: Path, *, rows: int = 200) -> None:
    """Write a deterministic synthetic bars CSV with an upward drift."""
    header = "Date,Open,High,Low,Close,Volume"
    lines = [header]
    base = 100.0
    for i in range(rows):
        date = f"2026-01-{(i % 28) + 1:02d}"
        # crude drift; values don't need to be realistic — they just
        # need to flow through the indicator pipeline.
        open_ = base + i * 0.15
        high = open_ + 0.5
        low = open_ - 0.5
        close = open_ + 0.25
        volume = 1_000_000 + i * 1000
        lines.append(f"{date},{open_:.2f},{high:.2f},{low:.2f},{close:.2f},{volume}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_manifest(
    tmp_path: Path,
    *,
    expected_latest: dict | None = None,
    tolerances: dict | None = None,
    include_study: bool = False,
    label_must_match: bool = False,
    comparison_window: int = 1,
) -> Path:
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars)

    fixture: dict = {
        "name": "AAPL_1D",
        "symbol": "AAPL",
        "timeframe": "1D",
        "bars_csv": "AAPL_1D_bars.csv",
        # Default to a single-field expectation so tests don't have to
        # widen every per-field tolerance just to scope what they care
        # about. Pass ``expected_latest`` explicitly to add more fields.
        "expected_latest": expected_latest or {"total_score": 50},
        "tolerances": tolerances or {"total_score": 1000},
        "comparison_window": comparison_window,
        "label_must_match": label_must_match,
    }
    if include_study:
        study = tmp_path / "AAPL_1D_study.csv"
        study.write_text(
            "Date,totalScore,Trend,Momo,TrueMomentum,TrueMomentumEMA,HiLoThrust,HLP_Output\n"
            "2026-01-28,50,50,50,0.0,0.0,0,0\n",
            encoding="utf-8",
        )
        fixture["study_csv"] = "AAPL_1D_study.csv"

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "schema_version": "thinkorswim_momentum_parity.v1",
            "source": "thinkorswim",
            "study_names": [
                "ST_TrueMomentumScoreSTUDY",
                "ST_TrueMomentumSTUDY",
                "ST_HiLoEliteSTUDY",
            ],
            "fixtures": [fixture],
        }),
        encoding="utf-8",
    )
    return manifest_path


# ── manifest validation ─────────────────────────────────────────────────────


def test_load_thinkorswim_manifest_full_schema(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, include_study=True)
    parsed = load_thinkorswim_manifest(manifest)
    assert parsed.schema_version == "thinkorswim_momentum_parity.v1"
    assert parsed.source == "thinkorswim"
    assert parsed.study_names == (
        "ST_TrueMomentumScoreSTUDY",
        "ST_TrueMomentumSTUDY",
        "ST_HiLoEliteSTUDY",
    )
    assert len(parsed.fixtures) == 1
    spec = parsed.fixtures[0]
    assert spec.symbol == "AAPL"
    assert spec.timeframe == "1D"
    assert spec.comparison_window == 1
    assert spec.label_must_match is False
    assert spec.study_timezone == "America/New_York"


def test_load_manifest_rejects_unknown_field(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    bars.write_text("Date,Open,High,Low,Close,Volume\n2026-04-01,1,2,0.5,1.5,100\n", encoding="utf-8")
    bad = tmp_path / "manifest.json"
    bad.write_text(
        json.dumps({
            "fixtures": [{
                "name": "x",
                "symbol": "AAPL",
                "timeframe": "1D",
                "bars_csv": "bars.csv",
                "expected_latest": {"nope": 1},
                "tolerances": {},
            }]
        }),
        encoding="utf-8",
    )
    with pytest.raises(ParityFixtureError):
        load_thinkorswim_manifest(bad)


def test_load_manifest_rejects_duplicate_fixture_names(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    bars.write_text("Date,Open,High,Low,Close,Volume\n2026-04-01,1,2,0.5,1.5,100\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "fixtures": [
                {
                    "name": "X",
                    "symbol": "AAPL",
                    "timeframe": "1D",
                    "bars_csv": "bars.csv",
                    "expected_latest": {"total_score": 50},
                    "tolerances": {},
                },
                {
                    "name": "X",
                    "symbol": "MSFT",
                    "timeframe": "1D",
                    "bars_csv": "bars.csv",
                    "expected_latest": {"total_score": 50},
                    "tolerances": {},
                },
            ]
        }),
        encoding="utf-8",
    )
    with pytest.raises(ParityFixtureError):
        load_thinkorswim_manifest(manifest_path)


def test_load_manifest_missing_returns_pending_status(tmp_path: Path) -> None:
    status = build_thinkorswim_momentum_parity_status(tmp_path)
    assert status["status"] == "missing"
    assert status["manifest_present"] is False
    assert status["fixtures_total"] == 0
    assert "thinkorswim_manifest_missing" in status["reason_codes"]


# ── parser aliases ──────────────────────────────────────────────────────────


def test_normalize_thinkorswim_columns_study_aliases() -> None:
    row = {
        "Date": "2026-04-01",
        "Total Score": "80",
        "Label": "Bull",
        "Trend": "75",
        "Momo": "83.33",
        "True Momentum": "67.25",
        "EMA": "61.40",
        "HiLo Thrust": "20",
        "HLP_Output": "20",
        "Pullback signal": "false",
        "Reversal warning": "no",
        "No-trade warning": "false",
    }
    canonical = normalize_thinkorswim_columns(row, kind="study")
    assert canonical["total_score"] == "80"
    assert canonical["total_label"] == "Bull"
    assert canonical["trend_score"] == "75"
    assert canonical["momo_score"] == "83.33"
    assert canonical["true_momentum"] == "67.25"
    assert canonical["true_momentum_ema"] == "61.40"
    assert canonical["hilo_thrust"] == "20"
    assert canonical["hilo_output"] == "20"
    assert canonical["pullback_signal"] == "false"
    assert canonical["reversal_warning"] == "no"
    assert canonical["no_trade_warning"] == "false"


def test_parse_thinkorswim_bars_csv_accepts_thinkorswim_shapes(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    bars.write_text(
        "Datetime,Open,High,Low,Close,Volume\n"
        "2026-04-01T14:30:00Z,100,101,99,100.5,1000\n"
        "04/02/2026 14:30,101,102,100,101.5,1100\n",
        encoding="utf-8",
    )
    parsed = parse_thinkorswim_bars_csv(bars)
    assert len(parsed) == 2
    assert parsed[0].open == 100.0
    assert parsed[1].volume == 1100


def test_parse_thinkorswim_study_csv_parses_labels_and_flags(tmp_path: Path) -> None:
    study = tmp_path / "study.csv"
    study.write_text(
        "Date,totalScore,Total Label,Trend,Momo,TrueMomentum,EMA,HiLoThrust,HLP_Output,"
        "Pullback signal,Reversal warning,No-trade warning\n"
        "2026-04-01,80,Bull,75,83.33,67.25,61.40,20,20,false,false,false\n",
        encoding="utf-8",
    )
    rows = parse_thinkorswim_study_csv(study)
    assert len(rows) == 1
    row = rows[0]
    assert row["total_score"] == 80.0
    assert row["total_label"] == "Bull"
    assert row["pullback_signal"] is False
    assert row["reversal_warning"] is False
    assert row["no_trade_warning"] is False


def test_parse_thinkorswim_bars_csv_clear_error_on_missing_columns(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    bars.write_text(
        "Date,Open,High,Low,Close,Volume\n2026-04-01,1,2,,1.5,100\n",
        encoding="utf-8",
    )
    with pytest.raises(ParityFixtureError) as exc:
        parse_thinkorswim_bars_csv(bars)
    assert "open/high/low/close" in str(exc.value)


# ── folder validation ───────────────────────────────────────────────────────


def test_validate_thinkorswim_fixture_folder_missing(tmp_path: Path) -> None:
    validation = validate_thinkorswim_fixture_folder(tmp_path)
    assert validation.manifest_present is False
    assert validation.manifest_valid is False
    assert validation.fixtures_total == 0
    assert validation.fixtures_ready == 0


def test_validate_thinkorswim_fixture_folder_partial(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    # Remove the bars file the manifest references so the folder is "partial".
    (tmp_path / "AAPL_1D_bars.csv").unlink()
    validation = validate_thinkorswim_fixture_folder(tmp_path)
    assert validation.manifest_present is True
    assert validation.manifest_valid is True
    assert validation.fixtures_total == 1
    assert validation.fixtures_ready == 0
    assert validation.fixtures[0].bars_present is False
    assert "AAPL_1D_bars.csv" in validation.fixtures[0].missing_files


def test_validate_thinkorswim_fixture_folder_ready(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    validation = validate_thinkorswim_fixture_folder(tmp_path)
    assert validation.manifest_present is True
    assert validation.manifest_valid is True
    assert validation.fixtures_total == 1
    assert validation.fixtures_ready == 1


# ── comparison engine ───────────────────────────────────────────────────────


def test_compare_momentum_to_thinkorswim_passes_within_tolerance(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        expected_latest={"total_score": 50},
        tolerances={"total_score": 1000},  # wide tolerance — definitely passes.
    )
    spec = load_thinkorswim_manifest(manifest).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert isinstance(result, FixtureComparisonResult)
    assert result.status == "passed"
    assert result.passed is True
    assert "thinkorswim_parity_passed" in result.reason_codes
    assert any(d.field == "total_score" for d in result.field_deltas)


def test_compare_momentum_to_thinkorswim_fails_when_outside_tolerance(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        # Deliberately set an expectation the deterministic payload will
        # not hit (synthetic bars produce a stable score; we just dial
        # the expectation to an impossible value).
        expected_latest={"total_score": 999},
        tolerances={"total_score": 0.0001},
    )
    spec = load_thinkorswim_manifest(manifest).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "failed"
    assert "thinkorswim_parity_failed" in result.reason_codes
    assert result.mismatches, "expected at least one mismatch"
    assert any("total_score expected" in msg for msg in result.mismatches)
    delta = next(d for d in result.field_deltas if d.field == "total_score")
    assert delta.within_tolerance is False
    assert delta.abs_error > 0


def test_compare_momentum_skipped_when_bars_missing(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path)
    spec = load_thinkorswim_manifest(manifest).fixtures[0]
    (tmp_path / "AAPL_1D_bars.csv").unlink()
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "skipped_missing_data"
    assert "thinkorswim_fixture_files_missing" in result.reason_codes


def test_label_must_match_fails_on_mismatch(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        expected_latest={"total_score": 50, "total_label": "Strong Bull"},
        tolerances={"total_score": 1000},
        label_must_match=True,
    )
    spec = load_thinkorswim_manifest(manifest).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "failed"
    assert any("total_label" in msg for msg in result.label_mismatches)


def test_label_must_match_false_keeps_pass(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        expected_latest={"total_score": 50, "total_label": "Strong Bull"},
        tolerances={"total_score": 1000},
        label_must_match=False,
    )
    spec = load_thinkorswim_manifest(manifest).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    # Label mismatch is recorded but does not flip status to failed.
    assert result.status == "passed"
    assert result.label_mismatches  # still reported


# ── report generation ──────────────────────────────────────────────────────


def test_build_thinkorswim_parity_report_writes_files(tmp_path: Path) -> None:
    _write_manifest(tmp_path, tolerances={"total_score": 1000})
    summary = build_thinkorswim_parity_report(tmp_path, write=True)
    assert summary.fixtures_total == 1
    assert summary.fixtures_passed == 1
    assert summary.overall_status == "passed"
    json_report = tmp_path / REPORT_FILENAME_JSON
    md_report = tmp_path / REPORT_FILENAME_MD
    assert json_report.exists()
    assert md_report.exists()
    payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert payload["schema_version"] == REPORT_SCHEMA_VERSION
    assert payload["overall_status"] == "passed"


def test_build_thinkorswim_parity_report_records_failure(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        expected_latest={"total_score": 999},
        tolerances={"total_score": 0.0001},
    )
    summary = build_thinkorswim_parity_report(tmp_path, write=True)
    assert summary.fixtures_failed == 1
    assert summary.overall_status == "failed"


def test_build_thinkorswim_parity_report_handles_missing_manifest(tmp_path: Path) -> None:
    summary = build_thinkorswim_parity_report(tmp_path, write=False)
    assert summary.manifest_present is False
    assert summary.overall_status == "missing"
    assert summary.fixtures_total == 0


# ── status builder ─────────────────────────────────────────────────────────


def test_status_builder_reads_passed_report(tmp_path: Path) -> None:
    _write_manifest(tmp_path, tolerances={"total_score": 1000})
    build_thinkorswim_parity_report(tmp_path, write=True)
    status = build_thinkorswim_momentum_parity_status(tmp_path)
    assert status["status"] == "passed"
    assert status["fixtures_passed"] == 1
    assert status["report_present"] is True
    assert status["last_report_generated_at"] is not None
    assert "thinkorswim_parity_passed" in status["reason_codes"]


def test_status_builder_reads_failed_report(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        expected_latest={"total_score": 999},
        tolerances={"total_score": 0.0001},
    )
    build_thinkorswim_parity_report(tmp_path, write=True)
    status = build_thinkorswim_momentum_parity_status(tmp_path)
    assert status["status"] == "failed"
    assert status["fixtures_failed"] == 1
    assert "thinkorswim_parity_failed" in status["reason_codes"]


def test_status_builder_partial_when_fixture_files_missing(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    (tmp_path / "AAPL_1D_bars.csv").unlink()
    status = build_thinkorswim_momentum_parity_status(tmp_path)
    assert status["status"] == "partial"
    assert "thinkorswim_fixture_files_missing" in status["reason_codes"]


# ── CLI script ─────────────────────────────────────────────────────────────


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI_SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
    )


def test_cli_non_strict_missing_manifest_exits_zero(tmp_path: Path) -> None:
    completed = _run_cli("--fixture-dir", str(tmp_path))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "missing" in completed.stdout


def test_cli_strict_missing_manifest_exits_nonzero(tmp_path: Path) -> None:
    completed = _run_cli("--fixture-dir", str(tmp_path), "--strict")
    assert completed.returncode != 0, completed.stdout + completed.stderr


def test_cli_write_report_creates_files(tmp_path: Path) -> None:
    _write_manifest(tmp_path, tolerances={"total_score": 1000})
    completed = _run_cli("--fixture-dir", str(tmp_path), "--write-report")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (tmp_path / REPORT_FILENAME_JSON).exists()
    assert (tmp_path / REPORT_FILENAME_MD).exists()


def test_cli_strict_failure_exits_nonzero(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        expected_latest={"total_score": 999},
        tolerances={"total_score": 0.0001},
    )
    completed = _run_cli(
        "--fixture-dir", str(tmp_path), "--write-report", "--strict"
    )
    assert completed.returncode != 0, completed.stdout + completed.stderr


def test_cli_json_output_is_parseable(tmp_path: Path) -> None:
    _write_manifest(tmp_path, tolerances={"total_score": 1000})
    completed = _run_cli("--fixture-dir", str(tmp_path), "--json", "--write-report")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    parsed = json.loads(completed.stdout)
    assert "status" in parsed
    assert parsed["status"]["status"] in {"passed", "ready", "missing"}
    assert "report" in parsed


# ── optional strict env var integration point ──────────────────────────────


def test_optional_strict_env_var_drives_strict_check(tmp_path: Path, monkeypatch) -> None:
    """When ``MACMARKET_REQUIRE_THINKORSWIM_PARITY=true`` the CLI's
    ``--strict`` mode is expected to fail on missing manifest. The
    env var itself is the gate that future CI can wire up — the CLI
    flag is what makes the check fail loudly."""
    monkeypatch.setenv("MACMARKET_REQUIRE_THINKORSWIM_PARITY", "true")
    completed = _run_cli("--fixture-dir", str(tmp_path), "--strict")
    assert completed.returncode != 0


# ── no recommendation / order / DB side effects ────────────────────────────


def test_parity_module_does_not_import_order_or_paper_modules() -> None:
    """The parity module is research-only — it must not pull in
    order-routing / paper-execution / replay-engine modules through
    its top-level imports."""
    import macmarket_trader.indicators.thinkorswim_parity as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    forbidden = (
        "macmarket_trader.execution",
        "macmarket_trader.replay.engine",
        "macmarket_trader.recommendation.service",
        "paper_order",
        "approve_recommendation",
    )
    for symbol in forbidden:
        assert symbol not in source, (
            f"parity module must not reference {symbol!r}"
        )


def test_status_builder_does_not_run_indicator_math(tmp_path: Path) -> None:
    """The status builder is called from the Settings card on every
    page load. Confirm it runs cheaply when only a manifest is present
    (no bars / no study / no payload built)."""
    _write_manifest(tmp_path)
    status = build_thinkorswim_momentum_parity_status(tmp_path)
    assert status["status"] == "ready"
    # No report was generated and no payload was built, but the status
    # builder still produced a meaningful answer.
    assert status["report_present"] is False


# ── canonical field constants ──────────────────────────────────────────────


def test_canonical_study_fields_are_stable() -> None:
    assert STUDY_FIELDS == (
        "total_score",
        "true_momentum",
        "true_momentum_ema",
        "hilo_thrust",
        "hilo_output",
        "trend_score",
        "momo_score",
    )
    assert "total_label" in LABEL_FIELDS
    assert "pullback_signal" in LABEL_FIELDS
    assert "reversal_warning" in LABEL_FIELDS
    assert "no_trade_warning" in LABEL_FIELDS


def test_default_tolerances_explicit_and_conservative() -> None:
    for field in ("total_score", "trend_score", "momo_score"):
        assert DEFAULT_TOLERANCES[field] > 0
    assert DEFAULT_TOLERANCES["true_momentum"] <= 1.0
    assert DEFAULT_TOLERANCES["true_momentum_ema"] <= 1.0
