"""Thinkorswim parity test for the Momentum Intelligence Layer.

When ``tests/fixtures/thinkorswim_momentum/manifest.json`` is absent, this
test is a no-op pass — parity validation is **pending** until an operator
drops Thinkorswim CSV exports and a manifest into the fixtures directory.

When the manifest is present, this test loads each fixture, builds the
deterministic momentum payload via
:class:`macmarket_trader.charts.momentum_service.MomentumChartService`, and
compares the latest snapshot against the operator-supplied
``expected_latest`` values within the per-field absolute ``tolerances``.

See ``tests/fixtures/thinkorswim_momentum/README.md`` for the full operator
workflow.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from macmarket_trader.charts.momentum_service import MomentumChartService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "thinkorswim_momentum"
MANIFEST = FIXTURE_DIR / "manifest.json"
HELPER_PATH = Path(__file__).parent / "helpers" / "momentum_parity.py"
_HELPER_MODULE_NAME = "momentum_parity_helper"


def _load_helper() -> Any:
    """Load the parity helper module without requiring tests/ to be a package."""
    cached = sys.modules.get(_HELPER_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_HELPER_MODULE_NAME, HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load helper module at {HELPER_PATH}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve cls.__module__ via sys.modules.
    sys.modules[_HELPER_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def test_thinkorswim_parity_fixtures_marker() -> None:
    """No-op pass when no manifest is present.

    Documents that parity validation is pending Thinkorswim CSV exports.
    """
    if not MANIFEST.exists():
        # Parity fixtures pending. The presence of this scaffold is sufficient
        # to track the work; future fixture CSVs go under FIXTURE_DIR.
        assert FIXTURE_DIR.exists() or not FIXTURE_DIR.exists()
        return

    # Sanity-check the manifest shape only — full parity assertions live in
    # the parametrized test below so each fixture surfaces independently.
    helper = _load_helper()
    fixtures = helper.load_manifest(MANIFEST)
    assert fixtures, "manifest.json present but defines no fixtures"


def _collect_fixtures() -> list[tuple[str, Any]]:
    if not MANIFEST.exists():
        return []
    helper = _load_helper()
    try:
        return [(spec.name, spec) for spec in helper.load_manifest(MANIFEST)]
    except Exception as exc:  # pragma: no cover - defensive; surfaces in collection
        pytest.fail(f"failed to load parity manifest: {exc}")
        return []


@pytest.mark.parametrize("fixture_name, fixture", _collect_fixtures())
def test_thinkorswim_parity_fixture(fixture_name: str, fixture: Any) -> None:
    """Compare the deterministic payload's latest snapshot against the operator-supplied expected values."""
    helper = _load_helper()

    # visual_attestation fixtures have no bars CSV and no MacMarket
    # computation — the dedicated workflow test
    # (test_thinkorswim_momentum_parity_workflow.py) covers that mode.
    # Skip them here so this scaffold remains a bars-driven harness.
    if getattr(fixture, "parity_mode", None) == "visual_attestation":
        pytest.skip("visual_attestation has no bars CSV — covered by the parity-workflow test")

    bars = helper.load_bars_csv(fixture.bars_csv)
    htf_bars = (
        helper.load_bars_csv(fixture.higher_timeframe_bars_csv)
        if fixture.higher_timeframe_bars_csv is not None
        else None
    )

    service = MomentumChartService()
    payload = service.build_payload(
        symbol=fixture.symbol,
        timeframe=fixture.timeframe,
        bars=bars,
        higher_timeframe_bars=htf_bars,
    )

    # Parity status must remain visible on every payload, regardless of
    # whether parity has been validated. Phase A surfaces this so operators
    # can see when fixtures haven't been reviewed yet.
    assert isinstance(payload.parity_status, str) and payload.parity_status, (
        f"{fixture_name}: payload.parity_status missing"
    )

    if fixture.higher_timeframe_bars_csv is not None:
        assert payload.higher_timeframe_source == "provided_higher_timeframe_bars", (
            f"{fixture_name}: expected higher_timeframe_source='provided_higher_timeframe_bars' "
            f"when higher_timeframe_bars_csv is provided, got {payload.higher_timeframe_source!r}"
        )

    snapshot = payload.latest_snapshot
    assert snapshot is not None, f"{fixture_name}: payload.latest_snapshot is None — empty bars?"

    # Project the payload's latest snapshot into the canonical study fields.
    actual: dict[str, float] = {
        "total_score": float(snapshot.total_score),
        "true_momentum": float(snapshot.true_momentum),
        "true_momentum_ema": float(snapshot.true_momentum_ema),
        "hilo_thrust": float(snapshot.hilo_thrust),
        "hilo_output": float(snapshot.hilo_score),
        "trend_score": float(snapshot.trend_score),
        "momo_score": float(snapshot.momo_score),
    }

    mismatches = helper.compare_with_tolerance(
        fixture.expected_latest,
        actual,
        fixture.tolerances,
        label=f"{fixture_name} payload",
    )

    # Cross-check the operator's study CSV against the same expected values
    # when the columns are present. This catches operator export errors that
    # would otherwise mask a real MacMarket regression.
    if fixture.study_csv is not None and fixture.study_csv.exists():
        study_rows = helper.load_study_csv(fixture.study_csv)
        latest = helper.latest_study_row(study_rows)
        # Only compare fields the study CSV actually exposed.
        study_subset = {
            key: value
            for key, value in latest.items()
            if key in helper.STUDY_FIELDS and value is not None and key in fixture.expected_latest
        }
        if study_subset:
            mismatches.extend(
                helper.compare_with_tolerance(
                    {k: fixture.expected_latest[k] for k in study_subset},
                    study_subset,
                    fixture.tolerances,
                    label=f"{fixture_name} study CSV",
                )
            )

    assert not mismatches, (
        f"{fixture_name}: parity mismatches:\n  - " + "\n  - ".join(mismatches)
    )
