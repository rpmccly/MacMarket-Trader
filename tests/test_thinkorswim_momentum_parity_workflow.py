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
    PARITY_MODES,
    ParityFixtureError,
    RECOMMENDED_VISUAL_FIELDS,
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
        "hilo_slowd",
        "hilo_slowd_x",
        "tos_hilo_elite_scalar",
        "hilo_score",
        "true_momentum_score",
        "atr_bias",
        "macd_bias",
        "ma_bias",
    )
    assert "total_label" in LABEL_FIELDS
    assert "pullback_signal" in LABEL_FIELDS
    assert "reversal_warning" in LABEL_FIELDS
    assert "no_trade_warning" in LABEL_FIELDS
    assert "hilo_thrust_state" in LABEL_FIELDS


def test_default_tolerances_explicit_and_conservative() -> None:
    for field in ("total_score", "trend_score", "momo_score"):
        assert DEFAULT_TOLERANCES[field] > 0
    assert DEFAULT_TOLERANCES["true_momentum"] <= 1.0
    assert DEFAULT_TOLERANCES["true_momentum_ema"] <= 1.0


# ── visual_observation parity mode ─────────────────────────────────────────


def _write_visual_manifest(
    tmp_path: Path,
    *,
    observed_latest: dict | None = None,
    expected_latest: dict | None = None,
    tolerances: dict | None = None,
    label_must_match: bool = False,
    observed_bar_date: str | None = None,
    screenshot: str | None = None,
    screenshot_notes: str | None = None,
    reviewer: str | None = None,
    reviewed_at: str | None = None,
    notes: str | None = None,
    parity_mode: str | None = "visual_observation",
    extra_fixture_overrides: dict | None = None,
) -> Path:
    """Write a synthetic visual_observation manifest using the shared
    bars-CSV helper. Returns the manifest path. The default visual
    observation is intentionally wide so the deterministic synthetic
    bars pass without arguing with the score gate.
    """
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars)

    fixture: dict = {
        "name": "AAPL_1D_visual",
        "symbol": "AAPL",
        "timeframe": "1D",
        "bars_csv": "AAPL_1D_bars.csv",
        "tolerances": tolerances or {"total_score": 1000},
        "label_must_match": label_must_match,
    }
    if parity_mode is not None:
        fixture["parity_mode"] = parity_mode
    if observed_latest is not None:
        fixture["observed_latest"] = observed_latest
    if expected_latest is not None:
        fixture["expected_latest"] = expected_latest
    if observed_bar_date is not None:
        fixture["observed_bar_date"] = observed_bar_date
    if screenshot is not None:
        fixture["screenshot"] = screenshot
    if screenshot_notes is not None:
        fixture["screenshot_notes"] = screenshot_notes
    if reviewer is not None:
        fixture["reviewer"] = reviewer
    if reviewed_at is not None:
        fixture["reviewed_at"] = reviewed_at
    if notes is not None:
        fixture["notes"] = notes
    if extra_fixture_overrides:
        fixture.update(extra_fixture_overrides)

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "schema_version": "thinkorswim_momentum_parity.v1",
            "source": "thinkorswim",
            "fixtures": [fixture],
        }),
        encoding="utf-8",
    )
    return manifest_path


def test_visual_observation_fixture_loads_without_study_csv(tmp_path: Path) -> None:
    """A visual_observation fixture is valid without a study CSV — ToS
    does not export the Momentum study rows."""
    manifest_path = _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50},
        reviewer="qa-operator",
        reviewed_at="2026-05-13T13:30:00Z",
        observed_bar_date="2026-01-28",
        screenshot="AAPL_1D_2026-01-28.png",
        screenshot_notes="placeholder screenshot",
    )
    manifest = load_thinkorswim_manifest(manifest_path)
    assert len(manifest.fixtures) == 1
    spec = manifest.fixtures[0]
    assert spec.parity_mode == "visual_observation"
    assert spec.is_visual is True
    assert spec.is_exported_study_csv is False
    assert spec.study_csv is None
    assert spec.observed_bar_date is not None
    assert spec.reviewer == "qa-operator"
    assert spec.screenshot == "AAPL_1D_2026-01-28.png"
    assert spec.screenshot_notes == "placeholder screenshot"
    assert spec.reviewed_at is not None
    assert spec.expected_latest == {"total_score": 50.0}


def test_visual_observation_passes_within_tolerance(tmp_path: Path) -> None:
    """Visual observation within tolerance returns status=passed and
    surfaces the visual-mode reason code."""
    manifest_path = _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50},
        tolerances={"total_score": 1000},
        reviewer="qa",
        observed_bar_date="2026-01-28",
        screenshot="AAPL_1D.png",
        reviewed_at="2026-05-13T13:30:00Z",
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert isinstance(result, FixtureComparisonResult)
    assert result.parity_mode == "visual_observation"
    assert result.is_visual is True
    assert result.status == "passed"
    assert "thinkorswim_parity_passed" in result.reason_codes
    assert "thinkorswim_visual_parity_passed" in result.reason_codes
    # Visual metadata propagates into the result for the report.
    assert result.reviewer == "qa"
    assert result.observed_bar_date == "2026-01-28"
    assert result.screenshot == "AAPL_1D.png"
    assert result.reviewed_at is not None
    # The diagnostics announce the visual basis.
    assert result.diagnostics.get("mode") == "visual_observation"
    assert "operator-read" in str(result.diagnostics.get("source", ""))


def test_visual_observation_fails_on_numeric_mismatch(tmp_path: Path) -> None:
    """A numeric mismatch flips visual_observation to status=failed."""
    manifest_path = _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 999},
        tolerances={"total_score": 0.0001},
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.parity_mode == "visual_observation"
    assert result.status == "failed"
    assert "thinkorswim_parity_failed" in result.reason_codes
    assert "thinkorswim_visual_parity_failed" in result.reason_codes


def test_visual_observation_label_must_match_true_fails_on_mismatch(tmp_path: Path) -> None:
    manifest_path = _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50, "total_label": "Strong Bull"},
        tolerances={"total_score": 1000},
        label_must_match=True,
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "failed"
    assert any("total_label" in msg for msg in result.label_mismatches)


def test_visual_observation_label_must_match_false_warns_only(tmp_path: Path) -> None:
    manifest_path = _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50, "total_label": "Strong Bull"},
        tolerances={"total_score": 1000},
        label_must_match=False,
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    # The label mismatch is recorded as a warning but the status remains passed.
    assert result.status == "passed"
    assert result.label_mismatches  # still reported as diagnostics


def test_visual_observation_observed_bar_date_alignment(tmp_path: Path) -> None:
    """When observed_bar_date does not match the last bar in the bars
    CSV, the validator records an alignment diagnostic rather than
    silently switching which bar it evaluates."""
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars, rows=200)
    fixture = {
        "name": "AAPL_1D_visual",
        "symbol": "AAPL",
        "timeframe": "1D",
        "parity_mode": "visual_observation",
        "bars_csv": "AAPL_1D_bars.csv",
        "observed_bar_date": "2025-12-31",  # not the last bar
        "observed_latest": {"total_score": 50},
        "tolerances": {"total_score": 1000},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"fixtures": [fixture]}), encoding="utf-8")
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.diagnostics.get("observed_bar_date") == "2025-12-31"
    assert "observed_bar_date_alignment" in result.diagnostics


def test_visual_observation_skipped_when_no_observed_values(tmp_path: Path) -> None:
    """A visual_observation fixture with no observed_latest/expected_latest
    block reports status=skipped_missing_observation."""
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars)
    fixture = {
        "name": "AAPL_1D_visual",
        "symbol": "AAPL",
        "timeframe": "1D",
        "parity_mode": "visual_observation",
        "bars_csv": "AAPL_1D_bars.csv",
        "tolerances": {"total_score": 1000},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"fixtures": [fixture]}), encoding="utf-8")
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    assert spec.parity_mode == "visual_observation"
    assert spec.expected_latest == {}
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "skipped_missing_observation"
    assert "thinkorswim_visual_observation_missing" in result.reason_codes


def test_visual_observation_recommended_field_reason_codes(tmp_path: Path) -> None:
    """Missing recommended fields should add reason codes but not flip
    status to failed."""
    manifest_path = _write_visual_manifest(
        tmp_path,
        # Only total_score provided — total_label, true_momentum, and
        # true_momentum_ema are still strongly recommended.
        observed_latest={"total_score": 50},
        tolerances={"total_score": 1000},
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "passed"
    for missing in ("total_label", "true_momentum", "true_momentum_ema"):
        if missing not in RECOMMENDED_VISUAL_FIELDS:
            continue
        assert f"thinkorswim_visual_observation_missing_{missing}" in result.reason_codes


def test_manifest_rejects_observed_latest_with_expected_latest(tmp_path: Path) -> None:
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "fixtures": [{
                "name": "AAPL_1D",
                "symbol": "AAPL",
                "timeframe": "1D",
                "bars_csv": "AAPL_1D_bars.csv",
                "expected_latest": {"total_score": 50},
                "observed_latest": {"total_score": 50},
                "tolerances": {"total_score": 1000},
            }]
        }),
        encoding="utf-8",
    )
    with pytest.raises(ParityFixtureError):
        load_thinkorswim_manifest(manifest_path)


def test_manifest_infers_visual_observation_when_observed_latest_present(tmp_path: Path) -> None:
    """When parity_mode is absent and observed_latest is present, the
    manifest loader infers visual_observation mode for backward compat."""
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "fixtures": [{
                "name": "AAPL_1D",
                "symbol": "AAPL",
                "timeframe": "1D",
                "bars_csv": "AAPL_1D_bars.csv",
                "observed_latest": {"total_score": 50},
                "tolerances": {"total_score": 1000},
            }]
        }),
        encoding="utf-8",
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    assert spec.parity_mode == "visual_observation"


def test_manifest_infers_exported_study_csv_when_only_expected_latest(tmp_path: Path) -> None:
    """Legacy manifests with only expected_latest stay in exported_study_csv mode."""
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "fixtures": [{
                "name": "AAPL_1D",
                "symbol": "AAPL",
                "timeframe": "1D",
                "bars_csv": "AAPL_1D_bars.csv",
                "expected_latest": {"total_score": 50},
                "tolerances": {"total_score": 1000},
            }]
        }),
        encoding="utf-8",
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    assert spec.parity_mode == "exported_study_csv"


def test_manifest_rejects_invalid_parity_mode(tmp_path: Path) -> None:
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "fixtures": [{
                "name": "AAPL_1D",
                "symbol": "AAPL",
                "timeframe": "1D",
                "bars_csv": "AAPL_1D_bars.csv",
                "parity_mode": "not_a_real_mode",
                "observed_latest": {"total_score": 50},
                "tolerances": {"total_score": 1000},
            }]
        }),
        encoding="utf-8",
    )
    with pytest.raises(ParityFixtureError):
        load_thinkorswim_manifest(manifest_path)


def test_visual_observation_does_not_load_study_csv(tmp_path: Path) -> None:
    """Visual observations skip study-CSV cross-checks even when a stray
    study CSV exists next to the bars CSV."""
    manifest_path = _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50},
        tolerances={"total_score": 1000},
    )
    # Drop a deliberately-wrong study CSV next to the bars to confirm
    # it does NOT get auto-loaded in visual_observation mode.
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    assert spec.study_csv is None  # manifest did not declare one
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "passed"
    assert result.diagnostics.get("study_rows_loaded", 0) == 0


# ── report generation in visual mode ───────────────────────────────────────


def test_report_records_visual_observation_in_markdown(tmp_path: Path) -> None:
    _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50},
        tolerances={"total_score": 1000},
        reviewer="qa-operator",
        observed_bar_date="2026-01-28",
        screenshot="AAPL_1D_2026-01-28.png",
        reviewed_at="2026-05-13T13:30:00Z",
    )
    summary = build_thinkorswim_parity_report(tmp_path, write=True)
    assert summary.overall_status == "passed"
    md = (tmp_path / REPORT_FILENAME_MD).read_text(encoding="utf-8")
    assert "Mode: visual observation" in md
    assert "operator-read Thinkorswim rendered chart labels" in md
    assert "manual visual parity, not exported study-row parity" in md
    assert "visual_observation" in md
    assert "AAPL_1D_2026-01-28.png" in md
    assert "qa-operator" in md
    # Visual observations are auditable but not row-level CSV exports.
    assert "auditable but not row-level CSV exports" in md


def test_report_json_includes_parity_mode_and_mode_counts(tmp_path: Path) -> None:
    _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50},
        tolerances={"total_score": 1000},
        reviewer="qa-operator",
    )
    summary = build_thinkorswim_parity_report(tmp_path, write=True)
    payload = json.loads((tmp_path / REPORT_FILENAME_JSON).read_text(encoding="utf-8"))
    assert payload["overall_status"] == "passed"
    assert payload["visual_observation_count"] == 1
    assert payload["exported_study_csv_count"] == 0
    assert payload["visual_observation_passed_count"] == 1
    assert payload["visual_observation_failed_count"] == 0
    assert payload["visual_reviewed"] is True
    mode_counts = payload["parity_mode_counts"]
    assert mode_counts["visual_observation"]["total"] == 1
    assert mode_counts["visual_observation"]["passed"] == 1
    assert mode_counts["exported_study_csv"]["total"] == 0
    assert payload["results"][0]["parity_mode"] == "visual_observation"
    assert payload["results"][0]["reviewer"] == "qa-operator"


# ── status builder mode counts ─────────────────────────────────────────────


def test_status_builder_surfaces_visual_observation_counts(tmp_path: Path) -> None:
    _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50},
        tolerances={"total_score": 1000},
        reviewer="qa",
    )
    build_thinkorswim_parity_report(tmp_path, write=True)
    status = build_thinkorswim_momentum_parity_status(tmp_path)
    assert status["status"] == "passed"
    assert status["visual_observation_count"] == 1
    assert status["exported_study_csv_count"] == 0
    assert status["visual_observation_passed_count"] == 1
    assert status["visual_observation_failed_count"] == 0
    assert status["visual_reviewed"] is True
    assert status["exported_study_csv_available"] is False
    mode_counts = status["parity_mode_counts"]
    assert mode_counts["visual_observation"]["total"] == 1
    assert mode_counts["visual_observation"]["passed"] == 1
    assert "thinkorswim_visual_parity_passed" in status["reason_codes"]
    assert "thinkorswim_visual_parity_observations_available" in status["reason_codes"]
    assert "thinkorswim_exported_study_csv_unavailable" in status["reason_codes"]
    # Summary explicitly names the parity basis as visual / manual.
    assert "visual / manual observation" in (status["summary"] or "")


def test_status_builder_visual_observation_failure_surfaces_failed_count(tmp_path: Path) -> None:
    _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 999},
        tolerances={"total_score": 0.0001},
        reviewer="qa",
    )
    build_thinkorswim_parity_report(tmp_path, write=True)
    status = build_thinkorswim_momentum_parity_status(tmp_path)
    assert status["status"] == "failed"
    assert status["visual_observation_count"] == 1
    assert status["visual_observation_failed_count"] == 1
    assert "thinkorswim_visual_parity_failed" in status["reason_codes"]


def test_status_builder_mode_counts_when_only_manifest_present(tmp_path: Path) -> None:
    """Before a parity report is generated, status mode counts come
    from the manifest scan."""
    _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50},
        tolerances={"total_score": 1000},
    )
    status = build_thinkorswim_momentum_parity_status(tmp_path)
    assert status["status"] == "ready"
    assert status["visual_observation_count"] == 1
    assert status["exported_study_csv_count"] == 0
    # No report yet, so visual_passed/failed are zero.
    assert status["visual_observation_passed_count"] == 0
    assert status["visual_observation_failed_count"] == 0


# ── CLI script in visual mode ──────────────────────────────────────────────


def test_cli_strict_visual_observation_pass_exits_zero(tmp_path: Path) -> None:
    _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50},
        tolerances={"total_score": 1000},
        reviewer="qa",
    )
    completed = _run_cli(
        "--fixture-dir", str(tmp_path), "--write-report", "--strict"
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "visual_observation" in completed.stdout
    assert "Mode summary" in completed.stdout


def test_cli_strict_visual_observation_failure_exits_nonzero(tmp_path: Path) -> None:
    _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 999},
        tolerances={"total_score": 0.0001},
    )
    completed = _run_cli(
        "--fixture-dir", str(tmp_path), "--write-report", "--strict"
    )
    assert completed.returncode != 0, completed.stdout + completed.stderr


def test_parity_modes_constant_is_stable() -> None:
    assert set(PARITY_MODES) == {
        "exported_study_csv",
        "visual_observation",
        "visual_attestation",
    }


# ── HiLo field discipline (Part A cleanup) ─────────────────────────────────


def test_visual_observation_supports_hilo_slowd_separately(tmp_path: Path) -> None:
    """A visual_observation fixture may compare hilo_slowd against
    MacMarket's existing SlowD value — passing when MM SlowD is within
    tolerance of the operator's reading."""
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars, rows=200)
    # Compute the SlowD we expect MM to produce, then build a manifest
    # that asks the validator to compare it. We don't precompute the
    # number — instead use a very wide tolerance so the test stays green
    # regardless of the synthetic bars' deterministic output.
    fixture = {
        "name": "AAPL_1D_visual_slowd",
        "symbol": "AAPL",
        "timeframe": "1D",
        "parity_mode": "visual_observation",
        "bars_csv": "AAPL_1D_bars.csv",
        "observed_latest": {"total_score": 50, "hilo_slowd": 0.0},
        "tolerances": {"total_score": 1000, "hilo_slowd": 1000.0},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"fixtures": [fixture]}), encoding="utf-8")
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    assert spec.parity_mode == "visual_observation"
    assert "hilo_slowd" in spec.expected_latest
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "passed"
    # The hilo_slowd delta lands in field_deltas — separate from
    # hilo_thrust / hilo_output / hilo_score.
    fields = {d.field for d in result.field_deltas}
    assert "hilo_slowd" in fields


def test_visual_observation_records_tos_hilo_elite_scalar_without_failing(tmp_path: Path) -> None:
    """tos_hilo_elite_scalar is a reference-only field — MacMarket does
    not compute it, so the validator records the operator's reading in
    diagnostics but never fails parity on it."""
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars, rows=200)
    fixture = {
        "name": "AAPL_1D_visual_tos_scalar",
        "symbol": "AAPL",
        "timeframe": "1D",
        "parity_mode": "visual_observation",
        "bars_csv": "AAPL_1D_bars.csv",
        # Record the ToS scalar (98.18-ish from operator) plus a
        # tractable numeric the validator will actually assert.
        "observed_latest": {
            "total_score": 50,
            "tos_hilo_elite_scalar": 98.18,
        },
        "tolerances": {"total_score": 1000},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"fixtures": [fixture]}), encoding="utf-8")
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "passed"
    # Reference-only observation is captured in diagnostics — not in
    # field_deltas or mismatches.
    ref = result.diagnostics.get("reference_only_observations") or {}
    assert ref.get("tos_hilo_elite_scalar") == 98.18
    assert any(d.field == "tos_hilo_elite_scalar" for d in result.field_deltas) is False
    assert "reference_only_note" in result.diagnostics


def test_visual_observation_hilo_slowd_mismatch_fails(tmp_path: Path) -> None:
    """A genuinely-out-of-tolerance hilo_slowd reading flips the result
    to failed (proves the new field is asserted, not silently skipped)."""
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars, rows=200)
    fixture = {
        "name": "AAPL_1D_visual_slowd_miss",
        "symbol": "AAPL",
        "timeframe": "1D",
        "parity_mode": "visual_observation",
        "bars_csv": "AAPL_1D_bars.csv",
        "observed_latest": {"total_score": 50, "hilo_slowd": 9999.0},
        "tolerances": {"total_score": 1000, "hilo_slowd": 0.001},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"fixtures": [fixture]}), encoding="utf-8")
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "failed"
    assert any("hilo_slowd" in msg for msg in result.mismatches)


def test_visual_observation_emits_missing_hilo_field_reason_code_when_no_hilo_capture(
    tmp_path: Path,
) -> None:
    """A visual fixture that captured no HiLo field at all gets an
    advisory reason code — but does not hard-fail."""
    manifest_path = _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50},
        tolerances={"total_score": 1000},
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "passed"
    assert "thinkorswim_visual_observation_missing_hilo_field" in result.reason_codes


def test_normalize_thinkorswim_columns_recognizes_new_hilo_aliases() -> None:
    row = {
        "Date": "2026-05-10",
        "HiLo SlowD": "78.91",
        "SlowD_X": "76.42",
        "ToS HiLo Elite": "98.18",
    }
    canonical = normalize_thinkorswim_columns(row, kind="study")
    assert canonical["hilo_slowd"] == "78.91"
    assert canonical["hilo_slowd_x"] == "76.42"
    assert canonical["tos_hilo_elite_scalar"] == "98.18"


def test_recommended_hilo_visual_fields_imported_clean() -> None:
    from macmarket_trader.indicators.thinkorswim_parity import (
        RECOMMENDED_HILO_VISUAL_FIELDS,
        REFERENCE_ONLY_FIELDS,
    )
    # tos_hilo_elite_scalar must be flagged reference-only because
    # MacMarket does not compute it.
    assert "tos_hilo_elite_scalar" in REFERENCE_ONLY_FIELDS
    # The "at least one HiLo field" recommendation should include both
    # SlowD-derived options and the ToS scalar so any HiLo capture
    # satisfies it.
    assert "hilo_slowd" in RECOMMENDED_HILO_VISUAL_FIELDS
    assert "hilo_slowd_x" in RECOMMENDED_HILO_VISUAL_FIELDS
    assert "tos_hilo_elite_scalar" in RECOMMENDED_HILO_VISUAL_FIELDS


def test_visual_observation_screenshot_metadata_includes_macmarket_screenshot(tmp_path: Path) -> None:
    """The fixture spec accepts a ``screenshot`` reference; an optional
    ``macmarket_screenshot`` and ``screenshot_notes`` are also recorded
    so the parity audit trail can carry both sides."""
    manifest_path = _write_visual_manifest(
        tmp_path,
        observed_latest={"total_score": 50},
        tolerances={"total_score": 1000},
        screenshot="SPY_1D_2026-05-10_tos.png",
        screenshot_notes="ToS chart cropped to True Momentum Score panel.",
        reviewer="ops",
        reviewed_at="2026-05-14T13:30:00Z",
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "passed"
    assert result.screenshot == "SPY_1D_2026-05-10_tos.png"
    assert result.screenshot_notes == "ToS chart cropped to True Momentum Score panel."
    assert result.reviewer == "ops"


# ── visual_attestation (no-bars) parity ─────────────────────────────────────


def _write_visual_attestation_manifest(
    tmp_path: Path,
    *,
    tos_observed_latest: dict | None = None,
    macmarket_observed_latest: dict | None = None,
    tolerances: dict | None = None,
    label_must_match: bool = False,
    reviewer: str | None = "operator",
    reviewed_at: str | None = "2026-05-14T13:30:00Z",
    tos_screenshot: str | None = "visual/SPY_1D_ToS_2026_5_13.png",
    macmarket_screenshot: str | None = "visual/SPY_1D_MM_2026_5_13.png",
    observed_bar_date: str | None = "2026-05-13",
    extra_fixture_overrides: dict | None = None,
) -> Path:
    """Write a synthetic visual_attestation manifest (no bars_csv).

    Defaults match the operator's SPY 2026-05-13 capture for easy use
    in tests. Pass ``tos_observed_latest`` / ``macmarket_observed_latest``
    to override either side independently.
    """
    fixture: dict = {
        "name": "SPY_1D_visual_attestation_test",
        "symbol": "SPY",
        "timeframe": "1D",
        "parity_mode": "visual_attestation",
        "label_must_match": label_must_match,
    }
    if tos_observed_latest is not None:
        fixture["tos_observed_latest"] = tos_observed_latest
    if macmarket_observed_latest is not None:
        fixture["macmarket_observed_latest"] = macmarket_observed_latest
    if tolerances is not None:
        fixture["tolerances"] = tolerances
    if reviewer is not None:
        fixture["reviewer"] = reviewer
    if reviewed_at is not None:
        fixture["reviewed_at"] = reviewed_at
    if tos_screenshot is not None:
        fixture["tos_screenshot"] = tos_screenshot
    if macmarket_screenshot is not None:
        fixture["macmarket_screenshot"] = macmarket_screenshot
    if observed_bar_date is not None:
        fixture["observed_bar_date"] = observed_bar_date
    if extra_fixture_overrides:
        fixture.update(extra_fixture_overrides)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"schema_version": "thinkorswim_momentum_parity.v1", "fixtures": [fixture]}),
        encoding="utf-8",
    )
    return manifest_path


def test_visual_attestation_does_not_require_bars_csv(tmp_path: Path) -> None:
    """A visual_attestation fixture loads cleanly with no bars_csv."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100, "true_momentum": 72.5563},
        macmarket_observed_latest={"total_score": 100, "true_momentum": 73.51},
    )
    manifest = load_thinkorswim_manifest(manifest_path)
    assert len(manifest.fixtures) == 1
    spec = manifest.fixtures[0]
    assert spec.parity_mode == "visual_attestation"
    assert spec.is_visual_attestation is True
    assert spec.bars_csv is None
    # ToS observation pair is parsed into numeric vs label buckets.
    assert "total_score" in spec.tos_observed_latest
    assert spec.tos_observed_latest["true_momentum"] == 72.5563
    assert spec.macmarket_observed_latest["true_momentum"] == 73.51


def test_visual_attestation_exact_match_passes(tmp_path: Path) -> None:
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 100,
            "total_label": "Max Bull",
            "true_momentum": 72.5563,
            "true_momentum_ema": 59.2084,
        },
        macmarket_observed_latest={
            "total_score": 100,
            "total_label": "Max Bull",
            "true_momentum": 73.51,
            "true_momentum_ema": 60.04,
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_attested"
    assert "thinkorswim_visual_attested" in result.reason_codes
    fields = {d.field for d in result.field_deltas}
    assert "total_score" in fields
    assert "true_momentum" in fields
    assert "true_momentum_ema" in fields


def test_visual_attestation_numeric_mismatch_fails(tmp_path: Path) -> None:
    """An out-of-tolerance numeric mismatch flips status to visual_failed."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 35, "true_momentum": 57.0},
        macmarket_observed_latest={"total_score": 65, "true_momentum": 58.0},
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_failed"
    assert "thinkorswim_visual_attestation_failed" in result.reason_codes
    assert any("total_score" in m for m in result.mismatches)


def test_visual_attestation_label_must_match_true_fails_on_label_mismatch(
    tmp_path: Path,
) -> None:
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100, "total_label": "Max Bull"},
        macmarket_observed_latest={"total_score": 100, "total_label": "Bull"},
        label_must_match=True,
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_failed"
    assert any("total_label" in m for m in result.label_mismatches)


def test_visual_attestation_label_must_match_false_warns_only(tmp_path: Path) -> None:
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100, "total_label": "Max Bull"},
        macmarket_observed_latest={"total_score": 100, "total_label": "Bull"},
        label_must_match=False,
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_attested"
    assert result.label_mismatches  # warning recorded
    assert not result.mismatches  # numeric mismatches block — label only warns


def test_visual_attestation_records_tos_hilo_elite_scalar_but_does_not_compare_to_slowd(
    tmp_path: Path,
) -> None:
    """tos_hilo_elite_scalar is recorded in the report's reference_only
    block when it appears only on the ToS side — never auto-compared
    against MacMarket's hilo_slowd."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 100,
            "tos_hilo_elite_scalar": 98.1805,
        },
        macmarket_observed_latest={
            "total_score": 100,
            "hilo_slowd": 79.15,
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_attested"
    fields = {d.field for d in result.field_deltas}
    assert "tos_hilo_elite_scalar" not in fields
    assert "hilo_slowd" not in fields  # only on MM side, no ToS counterpart
    ref = result.diagnostics.get("reference_only_observations") or {}
    assert "tos_only" in ref
    assert ref["tos_only"]["tos_hilo_elite_scalar"] == 98.1805


def test_visual_attestation_comparing_tos_hilo_elite_to_itself_works(tmp_path: Path) -> None:
    """When both sides provide tos_hilo_elite_scalar, the validator
    compares them symmetrically using the configured tolerance."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 100,
            "tos_hilo_elite_scalar": 98.1805,
        },
        macmarket_observed_latest={
            "total_score": 100,
            "tos_hilo_elite_scalar": 98.20,
        },
        tolerances={"tos_hilo_elite_scalar": 1.0},
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_attested"
    fields = {d.field for d in result.field_deltas}
    assert "tos_hilo_elite_scalar" in fields


def test_visual_attestation_no_comparable_fields_is_visual_partial(tmp_path: Path) -> None:
    """When neither side shares any field, the result is visual_partial
    (strict CLI treats this as non-pass)."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100},
        macmarket_observed_latest={"hilo_slowd": 79.15},
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_partial"
    assert "thinkorswim_visual_attestation_no_comparable_fields" in result.reason_codes


def test_visual_attestation_missing_observation_skips(tmp_path: Path) -> None:
    """Both observation maps are required — a manifest that declares
    only the ToS side is rejected at load time."""
    fixture = {
        "name": "skip_case",
        "symbol": "SPY",
        "timeframe": "1D",
        "parity_mode": "visual_attestation",
        "tos_observed_latest": {"total_score": 100},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"fixtures": [fixture]}), encoding="utf-8")
    with pytest.raises(ParityFixtureError):
        load_thinkorswim_manifest(manifest_path)


def test_visual_attestation_screenshot_metadata_in_result(tmp_path: Path) -> None:
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100},
        macmarket_observed_latest={"total_score": 100},
        reviewer="Ry",
        reviewed_at="2026-05-14T13:30:00Z",
        tos_screenshot="visual/SPY_1D_ToS_2026_5_13.png",
        macmarket_screenshot="visual/SPY_1D_MM_2026_5_13.png",
        observed_bar_date="2026-05-13",
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_attested"
    assert result.reviewer == "Ry"
    assert result.observed_bar_date == "2026-05-13"
    assert result.screenshot == "visual/SPY_1D_ToS_2026_5_13.png"
    assert result.macmarket_screenshot == "visual/SPY_1D_MM_2026_5_13.png"


def test_visual_attestation_markdown_report_includes_screenshots_and_caveat(
    tmp_path: Path,
) -> None:
    _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100, "total_label": "Max Bull"},
        macmarket_observed_latest={"total_score": 100, "total_label": "Max Bull"},
        reviewer="Ry",
        tos_screenshot="visual/SPY_1D_ToS_2026_5_13.png",
        macmarket_screenshot="visual/SPY_1D_MM_2026_5_13.png",
    )
    summary = build_thinkorswim_parity_report(tmp_path, write=True)
    md = (tmp_path / REPORT_FILENAME_MD).read_text(encoding="utf-8")
    assert "visual_attestation" in md
    assert "visual/SPY_1D_ToS_2026_5_13.png" in md
    assert "visual/SPY_1D_MM_2026_5_13.png" in md
    # Caveat phrasing from prompt section 6.
    assert "Visual attestation compares operator-entered ToS and MacMarket" in md
    # Mode summary line lists visual_attestation explicitly.
    assert "visual_attestation:" in md
    assert summary.visual_attestation_count == 1
    assert summary.visual_attestation_passed_count == 1


def test_visual_attestation_json_report_carries_mode_summary(tmp_path: Path) -> None:
    _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100},
        macmarket_observed_latest={"total_score": 100},
    )
    summary = build_thinkorswim_parity_report(tmp_path, write=True)
    payload = json.loads((tmp_path / REPORT_FILENAME_JSON).read_text(encoding="utf-8"))
    assert payload["visual_attestation_count"] == 1
    assert payload["visual_attestation_passed_count"] == 1
    assert payload["visual_attestation_failed_count"] == 0
    assert payload["visual_attestation_status"] == "visual_attested"
    mode_counts = payload["parity_mode_counts"]["visual_attestation"]
    assert mode_counts["total"] == 1
    assert mode_counts["passed"] == 1
    result0 = payload["results"][0]
    assert result0["parity_mode"] == "visual_attestation"


def test_visual_attestation_status_builder_mode_counts(tmp_path: Path) -> None:
    _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100},
        macmarket_observed_latest={"total_score": 100},
    )
    build_thinkorswim_parity_report(tmp_path, write=True)
    status = build_thinkorswim_momentum_parity_status(tmp_path)
    assert status["visual_attestation_count"] == 1
    assert status["visual_attestation_passed_count"] == 1
    assert status["visual_attestation_status"] == "visual_attested"
    assert "thinkorswim_visual_attestation_observations_available" in status["reason_codes"]
    assert "thinkorswim_visual_attested" in status["reason_codes"]


def test_cli_strict_passes_for_passing_visual_attestation(tmp_path: Path) -> None:
    _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 100,
            "true_momentum": 72.5563,
            "true_momentum_ema": 59.2084,
        },
        macmarket_observed_latest={
            "total_score": 100,
            "true_momentum": 73.51,
            "true_momentum_ema": 60.04,
        },
    )
    completed = _run_cli(
        "--fixture-dir", str(tmp_path), "--write-report", "--strict"
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "visual_attestation:" in completed.stdout


def test_cli_strict_fails_for_failing_visual_attestation(tmp_path: Path) -> None:
    _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 35, "total_label": "Neutral"},
        macmarket_observed_latest={"total_score": 65, "total_label": "Neutral Up"},
    )
    completed = _run_cli(
        "--fixture-dir", str(tmp_path), "--write-report", "--strict"
    )
    assert completed.returncode != 0, completed.stdout + completed.stderr


def test_cli_non_strict_does_not_exit_nonzero_for_visual_partial(tmp_path: Path) -> None:
    _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100},
        macmarket_observed_latest={"hilo_slowd": 79.15},
    )
    completed = _run_cli("--fixture-dir", str(tmp_path), "--write-report")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "visual_attestation" in completed.stdout


def test_cli_strict_fails_for_visual_partial(tmp_path: Path) -> None:
    _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100},
        macmarket_observed_latest={"hilo_slowd": 79.15},
    )
    completed = _run_cli(
        "--fixture-dir", str(tmp_path), "--write-report", "--strict"
    )
    assert completed.returncode != 0, completed.stdout + completed.stderr


def test_visual_attestation_module_has_no_provider_or_order_imports() -> None:
    """The parity module must not pull provider, DB, or order modules."""
    import macmarket_trader.indicators.thinkorswim_parity as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    for symbol in (
        "macmarket_trader.execution",
        "macmarket_trader.replay.engine",
        "macmarket_trader.recommendation.service",
        "macmarket_trader.data.providers",
        "paper_order",
        "approve_recommendation",
    ):
        assert symbol not in source, (
            f"parity module must not reference {symbol!r}"
        )


# ── visual_attestation price + composite diagnostics ───────────────────────


def test_visual_attestation_close_price_within_tolerance_does_not_flag(tmp_path: Path) -> None:
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 100,
            "true_momentum": 72.5563,
            "true_momentum_ema": 59.2084,
        },
        macmarket_observed_latest={
            "total_score": 100,
            "true_momentum": 73.51,
            "true_momentum_ema": 60.04,
        },
        extra_fixture_overrides={
            "tos_observed_price": {"open": 587.10, "high": 590.05, "low": 585.40, "close": 588.72},
            "macmarket_observed_price": {"open": 587.10, "high": 590.05, "low": 585.40, "close": 588.73},
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_attested"
    assert result.price_close_delta is not None
    assert result.price_close_delta <= result.price_close_tolerance
    assert result.diagnostic_flags["price_context_mismatch"] is False
    assert "visual_attestation_price_context_mismatch" not in result.reason_codes


def test_visual_attestation_close_price_mismatch_emits_price_context_reason_code(
    tmp_path: Path,
) -> None:
    """When ToS / MacMarket close prices differ beyond tolerance, the
    validator emits the price_context_mismatch reason code but keeps
    the result attested when oscillator + composite pass."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 100,
            "true_momentum": 72.5563,
            "true_momentum_ema": 59.2084,
        },
        macmarket_observed_latest={
            "total_score": 100,
            "true_momentum": 73.51,
            "true_momentum_ema": 60.04,
        },
        extra_fixture_overrides={
            "tos_observed_price": {"close": 84.72},
            "macmarket_observed_price": {"close": 84.96},
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_attested"
    assert result.diagnostic_flags["price_context_mismatch"] is True
    assert "visual_attestation_price_context_mismatch" in result.reason_codes
    assert "bar_context_mismatch" in result.diagnostic_classification


def test_visual_attestation_close_price_tolerance_override_via_manifest(tmp_path: Path) -> None:
    """Operators can widen the close-price tolerance via tolerances.close."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100},
        macmarket_observed_latest={"total_score": 100},
        tolerances={"close": 1.0},
        extra_fixture_overrides={
            "tos_observed_price": {"close": 84.72},
            "macmarket_observed_price": {"close": 84.96},
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.price_close_tolerance == 1.0
    assert result.diagnostic_flags["price_context_mismatch"] is False


def test_visual_attestation_oscillator_aligned_composite_mismatch_xlp_pattern(
    tmp_path: Path,
) -> None:
    """The XLP-style pattern: True Momentum oscillator agrees but the
    composite total_score does not. The diagnostic classification
    captures ``oscillator_aligned`` and ``composite_mismatch``."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 35,
            "true_momentum": 57.1283,
            "true_momentum_ema": 54.4013,
        },
        macmarket_observed_latest={
            "total_score": 65,
            "true_momentum": 58.0,
            "true_momentum_ema": 54.45,
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_failed"
    assert result.diagnostic_flags["oscillator_aligned"] is True
    assert result.diagnostic_flags["oscillator_failed"] is False
    assert result.diagnostic_flags["composite_score_failed"] is True
    assert "oscillator_aligned" in result.diagnostic_classification
    assert "composite_mismatch" in result.diagnostic_classification
    # The composite-mismatch diagnostic note surfaces in diagnostics.
    note = result.diagnostics.get("composite_mismatch_note", "")
    assert "Oscillator fields passed" in note


def test_visual_attestation_mm_component_sum_is_reported(tmp_path: Path) -> None:
    """When all five MM composite components are provided, the
    validator reports their sum and the ToS - MM-sum delta."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100, "true_momentum": 70.0, "true_momentum_ema": 60.0},
        macmarket_observed_latest={
            "total_score": 100,
            "true_momentum": 70.5,
            "true_momentum_ema": 60.3,
            "true_momentum_score": 35,
            "hilo_score": 20,
            "atr_bias": 10,
            "macd_bias": 5,
            "ma_bias": 30,
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_attested"
    # 35 + 20 + 10 + 5 + 30 = 100
    assert result.mm_component_sum == 100.0
    attr = result.composite_score_attribution
    assert attr["mm_component_sum"] == 100.0
    assert attr["mm_total_score"] == 100.0
    assert attr["tos_total_score"] == 100.0
    assert attr["mm_total_score_minus_component_sum"] == 0.0
    assert attr["tos_total_score_minus_mm_component_sum"] == 0.0


def test_visual_attestation_tos_missing_components_does_not_fail(tmp_path: Path) -> None:
    """ToS missing component fields is fine — the validator records
    them as 'not observed' instead of assuming a formula."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 35,
            "true_momentum": 57.1283,
            "true_momentum_ema": 54.4013,
        },
        macmarket_observed_latest={
            "total_score": 35,
            "true_momentum": 57.5,
            "true_momentum_ema": 54.4,
            "true_momentum_score": 5,
            "hilo_score": 0,
            "atr_bias": 0,
            "macd_bias": 0,
            "ma_bias": 30,
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_attested"
    # ToS did not supply component fields — recorded as "not observed".
    assert "tos_total_score" in result.composite_score_attribution
    # MacMarket components sum to 35.
    assert result.mm_component_sum == 35.0


def test_visual_attestation_tos_hilo_elite_scalar_remains_reference_only(tmp_path: Path) -> None:
    """tos_hilo_elite_scalar present only on ToS side is recorded in
    reference_only_observations and never compared to MM HiLo SlowD."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 100,
            "tos_hilo_elite_scalar": 98.1805,
        },
        macmarket_observed_latest={
            "total_score": 100,
            "hilo_slowd": 79.15,
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_attested"
    ref = result.diagnostics.get("reference_only_observations") or {}
    assert ref["tos_only"]["tos_hilo_elite_scalar"] == 98.1805
    fields = {d.field for d in result.field_deltas}
    assert "tos_hilo_elite_scalar" not in fields
    assert "hilo_slowd" not in fields
    assert result.diagnostic_flags["reference_only_hilo_scalar_present"] is True


def test_visual_attestation_report_markdown_includes_composite_attribution_section(
    tmp_path: Path,
) -> None:
    _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 35,
            "true_momentum": 57.1283,
            "true_momentum_ema": 54.4013,
        },
        macmarket_observed_latest={
            "total_score": 65,
            "true_momentum": 58.0,
            "true_momentum_ema": 54.45,
            "true_momentum_score": 15,
            "hilo_score": -5,
            "atr_bias": 5,
            "macd_bias": 5,
            "ma_bias": 25,
        },
        extra_fixture_overrides={
            "tos_observed_price": {"close": 84.72},
            "macmarket_observed_price": {"close": 84.96},
        },
    )
    build_thinkorswim_parity_report(tmp_path, write=True)
    md = (tmp_path / REPORT_FILENAME_MD).read_text(encoding="utf-8")
    assert "### Composite score attribution" in md
    assert "MacMarket composite components" in md
    assert "MM component sum" in md
    assert "Price context" in md
    assert "Diagnostic flags" in md
    assert "oscillator_aligned" in md
    assert "composite_mismatch" in md
    assert "bar_context_mismatch" in md


def test_visual_attestation_report_json_includes_diagnostics(tmp_path: Path) -> None:
    _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 35,
            "true_momentum": 57.1283,
            "true_momentum_ema": 54.4013,
        },
        macmarket_observed_latest={
            "total_score": 65,
            "true_momentum": 58.0,
            "true_momentum_ema": 54.45,
            "true_momentum_score": 15,
            "hilo_score": -5,
            "atr_bias": 5,
            "macd_bias": 5,
            "ma_bias": 25,
        },
        extra_fixture_overrides={
            "tos_observed_price": {"close": 84.72},
            "macmarket_observed_price": {"close": 84.96},
        },
    )
    build_thinkorswim_parity_report(tmp_path, write=True)
    payload = json.loads((tmp_path / REPORT_FILENAME_JSON).read_text(encoding="utf-8"))
    result0 = payload["results"][0]
    assert result0["mm_component_sum"] == 45.0
    assert result0["tos_total_score"] == 35.0
    assert result0["mm_total_score"] == 65.0
    assert result0["tos_observed_price"] == {"close": 84.72}
    assert result0["macmarket_observed_price"] == {"close": 84.96}
    assert result0["price_close_delta"] is not None
    assert result0["price_close_tolerance"] is not None
    assert result0["diagnostic_flags"]["oscillator_aligned"] is True
    assert result0["diagnostic_flags"]["oscillator_failed"] is False
    assert result0["diagnostic_flags"]["composite_score_failed"] is True
    assert result0["diagnostic_flags"]["price_context_mismatch"] is True
    assert "oscillator_aligned" in result0["diagnostic_classification"]
    assert "composite_mismatch" in result0["diagnostic_classification"]
    assert "bar_context_mismatch" in result0["diagnostic_classification"]


def test_visual_attestation_strict_still_fails_when_total_score_fails(tmp_path: Path) -> None:
    """Even with oscillator aligned + composite attribution diagnostic,
    strict mode still exits non-zero when total_score fails."""
    _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 35,
            "true_momentum": 57.1283,
            "true_momentum_ema": 54.4013,
        },
        macmarket_observed_latest={
            "total_score": 65,
            "true_momentum": 58.0,
            "true_momentum_ema": 54.45,
        },
    )
    completed = _run_cli(
        "--fixture-dir", str(tmp_path), "--write-report", "--strict"
    )
    assert completed.returncode != 0, completed.stdout + completed.stderr


def test_visual_attestation_default_close_tolerance_is_010(tmp_path: Path) -> None:
    """The default close-price tolerance is 0.10 (not 0.05).

    Drives the prompt's "Default close tolerance: 0.10 unless fixture
    overrides" contract — 0.08 delta lands inside the default and the
    fixture must NOT flag price context mismatch.
    """
    from macmarket_trader.indicators.thinkorswim_parity import (
        DEFAULT_PRICE_CLOSE_TOLERANCE,
    )

    assert DEFAULT_PRICE_CLOSE_TOLERANCE == 0.10
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100},
        macmarket_observed_latest={"total_score": 100},
        extra_fixture_overrides={
            "tos_observed_price": {"close": 84.72},
            "macmarket_observed_price": {"close": 84.80},
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.price_close_tolerance == 0.10
    assert result.diagnostic_flags["price_context_mismatch"] is False


def test_visual_attestation_strict_price_context_fails_on_close_mismatch(
    tmp_path: Path,
) -> None:
    """When ``strict_price_context: true`` is set on the fixture, a
    close-price mismatch flips the result to visual_failed even if the
    oscillator + composite fields agree."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 100,
            "true_momentum": 72.5563,
            "true_momentum_ema": 59.2084,
        },
        macmarket_observed_latest={
            "total_score": 100,
            "true_momentum": 73.51,
            "true_momentum_ema": 60.04,
        },
        extra_fixture_overrides={
            "tos_observed_price": {"close": 84.72},
            "macmarket_observed_price": {"close": 84.96},
            "strict_price_context": True,
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    assert spec.strict_price_context is True
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_failed"
    assert result.diagnostic_flags["price_context_mismatch"] is True
    assert "visual_attestation_price_context_mismatch" in result.reason_codes
    assert "thinkorswim_visual_attestation_failed" in result.reason_codes
    # The strict-price mismatch surfaces as an explicit mismatch entry.
    assert any("strict_price_context" in m for m in result.mismatches)


def test_visual_attestation_oscillator_failed_flag_when_oscillator_diverges(
    tmp_path: Path,
) -> None:
    """When the True Momentum oscillator fields are compared but fail
    tolerance, the flag pair surfaces as
    ``oscillator_aligned: False`` + ``oscillator_failed: True``."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 100,
            "true_momentum": 30.0,
            "true_momentum_ema": 30.0,
        },
        macmarket_observed_latest={
            "total_score": 100,
            "true_momentum": 90.0,
            "true_momentum_ema": 90.0,
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.status == "visual_failed"
    assert result.diagnostic_flags["oscillator_aligned"] is False
    assert result.diagnostic_flags["oscillator_failed"] is True
    assert "oscillator_mismatch" in result.diagnostic_classification


def test_visual_attestation_oscillator_flags_false_when_not_compared(tmp_path: Path) -> None:
    """If neither true_momentum nor true_momentum_ema is on both sides,
    both oscillator flags remain False (not compared)."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100},
        macmarket_observed_latest={"total_score": 100},
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    assert result.diagnostic_flags["oscillator_aligned"] is False
    assert result.diagnostic_flags["oscillator_failed"] is False


def test_visual_attestation_composite_mismatch_note_mentions_ma_bias(
    tmp_path: Path,
) -> None:
    """The composite-mismatch operator note must mention
    'MA bias inclusion' so the operator immediately knows where to
    look first when oscillator passes but total_score diverges."""
    manifest_path = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={
            "total_score": 35,
            "true_momentum": 57.1283,
            "true_momentum_ema": 54.4013,
        },
        macmarket_observed_latest={
            "total_score": 65,
            "true_momentum": 58.0,
            "true_momentum_ema": 54.45,
        },
    )
    spec = load_thinkorswim_manifest(manifest_path).fixtures[0]
    result = compare_momentum_to_thinkorswim(spec)
    note = result.diagnostics.get("composite_mismatch_note", "")
    assert "MA bias inclusion" in note


def test_visual_attestation_price_block_rejects_unknown_keys(tmp_path: Path) -> None:
    """Price-context blocks must contain only open/high/low/close keys."""
    bars_required_off_attestation = _write_visual_attestation_manifest(
        tmp_path,
        tos_observed_latest={"total_score": 100},
        macmarket_observed_latest={"total_score": 100},
        extra_fixture_overrides={
            "tos_observed_price": {"close": 84.72, "wat": 1.0},
        },
    )
    with pytest.raises(ParityFixtureError):
        load_thinkorswim_manifest(bars_required_off_attestation)


def test_visual_attestation_price_block_rejects_outside_attestation_mode(tmp_path: Path) -> None:
    """tos_observed_price / macmarket_observed_price only valid in
    visual_attestation mode."""
    bars = tmp_path / "AAPL_1D_bars.csv"
    _write_bars_csv(bars)
    fixture = {
        "name": "AAPL_1D",
        "symbol": "AAPL",
        "timeframe": "1D",
        "parity_mode": "visual_observation",
        "bars_csv": "AAPL_1D_bars.csv",
        "observed_latest": {"total_score": 50},
        "tolerances": {"total_score": 1000},
        "tos_observed_price": {"close": 100.0},
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"fixtures": [fixture]}), encoding="utf-8")
    with pytest.raises(ParityFixtureError):
        load_thinkorswim_manifest(manifest_path)
