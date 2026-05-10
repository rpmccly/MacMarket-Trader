"""Tests for the Thinkorswim parity helper module.

These tests exercise the parser/loader independent of any operator-supplied
fixture data. They use ``tmp_path`` so they remain green even when no real
``manifest.json`` is present in ``tests/fixtures/thinkorswim_momentum/``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

HELPER_PATH = Path(__file__).parent / "helpers" / "momentum_parity.py"
_HELPER_MODULE_NAME = "momentum_parity_helper_test"


def _load_helper():
    spec = importlib.util.spec_from_file_location(_HELPER_MODULE_NAME, HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve cls.__module__ via sys.modules.
    sys.modules[_HELPER_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


helper = _load_helper()


# ── primitive parsers ───────────────────────────────────────────────────────


def test_parse_float_handles_common_thinkorswim_styles() -> None:
    assert helper.parse_float("1,234.50") == 1234.50
    assert helper.parse_float("75%") == 75.0
    assert helper.parse_float("$101.25") == 101.25
    assert helper.parse_float(" 42 ") == 42.0
    assert helper.parse_float(0) == 0.0
    assert helper.parse_float(0.5) == 0.5


def test_parse_float_returns_none_for_missing_or_unparseable() -> None:
    assert helper.parse_float(None) is None
    assert helper.parse_float("") is None
    assert helper.parse_float("  ") is None
    assert helper.parse_float("N/A") is None
    assert helper.parse_float("#N/A") is None
    assert helper.parse_float("nan") is None
    assert helper.parse_float("not-a-number") is None


def test_parse_datetime_accepts_iso_and_thinkorswim_shapes() -> None:
    expected_utc = datetime(2026, 4, 1, 14, 30, tzinfo=UTC)
    assert helper.parse_datetime("2026-04-01T14:30:00Z") == expected_utc
    assert helper.parse_datetime("2026-04-01 14:30") == expected_utc
    assert helper.parse_datetime("04/01/2026 14:30") == expected_utc
    assert helper.parse_datetime("4/1/26 14:30") == expected_utc
    assert helper.parse_datetime("2026-04-01") == datetime(2026, 4, 1, tzinfo=UTC)
    assert helper.parse_datetime("garbage") is None


def test_parse_date_returns_none_for_unparseable() -> None:
    assert helper.parse_date("2026-04-01") == date(2026, 4, 1)
    assert helper.parse_date("") is None


# ── manifest loader ─────────────────────────────────────────────────────────


def _write_manifest(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_manifest_validates_required_fields(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    bars.write_text("Date,Open,High,Low,Close,Volume\n2026-04-01,1,2,0.5,1.5,100\n", encoding="utf-8")
    manifest_path = _write_manifest(tmp_path, {
        "fixtures": [
            {
                "name": "AAPL_1D",
                "symbol": "aapl",
                "timeframe": "1d",
                "bars_csv": "bars.csv",
                "expected_latest": {"total_score": 80},
                "tolerances": {"total_score": 2},
            }
        ]
    })

    specs = helper.load_manifest(manifest_path)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "AAPL_1D"
    assert spec.symbol == "AAPL"  # uppercased
    assert spec.timeframe == "1D"  # uppercased
    assert spec.bars_csv == bars.resolve()
    assert spec.study_csv is None
    assert spec.higher_timeframe_bars_csv is None
    assert spec.expected_latest == {"total_score": 80.0}
    assert spec.tolerances == {"total_score": 2.0}


def test_load_manifest_rejects_unknown_expected_field(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    bars.write_text("Date,Open,High,Low,Close,Volume\n2026-04-01,1,2,0.5,1.5,100\n", encoding="utf-8")
    manifest_path = _write_manifest(tmp_path, {
        "fixtures": [
            {
                "name": "AAPL_1D",
                "symbol": "AAPL",
                "timeframe": "1D",
                "bars_csv": "bars.csv",
                "expected_latest": {"made_up_field": 99},
                "tolerances": {},
            }
        ]
    })
    with pytest.raises(helper.ParityFixtureError):
        helper.load_manifest(manifest_path)


def test_load_manifest_rejects_invalid_timeframe(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    bars.write_text("Date,Open,High,Low,Close,Volume\n2026-04-01,1,2,0.5,1.5,100\n", encoding="utf-8")
    manifest_path = _write_manifest(tmp_path, {
        "fixtures": [
            {
                "name": "x",
                "symbol": "AAPL",
                "timeframe": "5m",
                "bars_csv": "bars.csv",
                "expected_latest": {"total_score": 0},
                "tolerances": {},
            }
        ]
    })
    with pytest.raises(helper.ParityFixtureError):
        helper.load_manifest(manifest_path)


def test_load_manifest_rejects_missing_required_field(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, {"fixtures": [{"name": "x"}]})
    with pytest.raises(helper.ParityFixtureError):
        helper.load_manifest(manifest_path)


def test_load_manifest_rejects_empty_or_missing_fixtures(tmp_path: Path) -> None:
    with pytest.raises(helper.ParityFixtureError):
        helper.load_manifest(tmp_path / "missing.json")
    bad = _write_manifest(tmp_path, {"fixtures": []})
    with pytest.raises(helper.ParityFixtureError):
        helper.load_manifest(bad)


# ── CSV parsers ─────────────────────────────────────────────────────────────


def test_load_bars_csv_accepts_thinkorswim_column_variants(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    bars.write_text(
        "Datetime,Open,High,Low,Close,Volume\n"
        "2026-04-01T14:30:00Z,100,101,99,100.5,1000\n"
        "04/02/2026 14:30,101,102,100,101.5,1100\n",
        encoding="utf-8",
    )
    parsed = helper.load_bars_csv(bars)
    assert len(parsed) == 2
    assert parsed[0].date == date(2026, 4, 1)
    assert parsed[0].timestamp == datetime(2026, 4, 1, 14, 30, tzinfo=UTC)
    assert parsed[0].open == 100.0
    assert parsed[1].volume == 1100


def test_load_bars_csv_uses_date_column_when_no_time(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    bars.write_text("Date,Open,High,Low,Close,Volume\n2026-04-01,1,2,0.5,1.5,100\n", encoding="utf-8")
    parsed = helper.load_bars_csv(bars)
    assert parsed[0].date == date(2026, 4, 1)
    assert parsed[0].timestamp is None


def test_load_bars_csv_fails_clearly_on_bad_row(tmp_path: Path) -> None:
    bars = tmp_path / "bars.csv"
    bars.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-04-01,1,2,,1.5,100\n",  # missing Low
        encoding="utf-8",
    )
    with pytest.raises(helper.ParityFixtureError) as exc:
        helper.load_bars_csv(bars)
    assert "open/high/low/close" in str(exc.value)


def test_load_study_csv_normalizes_column_casing(tmp_path: Path) -> None:
    study = tmp_path / "study.csv"
    study.write_text(
        "Date,totalScore,TrueMomentum,TrueMomentumEMA,HiLoThrust,HLP_Output,Trend,Momo\n"
        "2026-03-31,75,65.0,60.0,15,15,72.5,80.0\n"
        "2026-04-01,80,67.25,61.40,20,20,75.0,83.33\n",
        encoding="utf-8",
    )
    rows = helper.load_study_csv(study)
    assert len(rows) == 2
    latest = helper.latest_study_row(rows)
    assert latest["total_score"] == 80.0
    assert latest["true_momentum"] == 67.25
    assert latest["true_momentum_ema"] == 61.40
    assert latest["hilo_thrust"] == 20.0
    assert latest["hilo_output"] == 20.0
    assert latest["trend_score"] == 75.0
    assert latest["momo_score"] == 83.33
    assert latest["date"] == date(2026, 4, 1)


def test_load_study_csv_falls_back_to_last_row_without_dates(tmp_path: Path) -> None:
    study = tmp_path / "study.csv"
    study.write_text(
        "TotalScore,TrueMomentum\n70,55.0\n95,70.0\n",
        encoding="utf-8",
    )
    rows = helper.load_study_csv(study)
    assert helper.latest_study_row(rows)["total_score"] == 95.0


# ── compare_with_tolerance ──────────────────────────────────────────────────


def test_compare_with_tolerance_returns_no_mismatches_when_within_tolerance() -> None:
    mismatches = helper.compare_with_tolerance(
        expected={"total_score": 80, "true_momentum": 67.25},
        actual={"total_score": 81, "true_momentum": 67.5},
        tolerances={"total_score": 2, "true_momentum": 0.5},
        label="payload",
    )
    assert mismatches == []


def test_compare_with_tolerance_flags_out_of_band_values() -> None:
    mismatches = helper.compare_with_tolerance(
        expected={"total_score": 80},
        actual={"total_score": 95},
        tolerances={"total_score": 2},
        label="payload",
    )
    assert mismatches and "total_score" in mismatches[0]


def test_compare_with_tolerance_flags_missing_actual() -> None:
    mismatches = helper.compare_with_tolerance(
        expected={"total_score": 80},
        actual={},
        tolerances={"total_score": 2},
        label="payload",
    )
    assert mismatches and "missing" in mismatches[0].lower()
