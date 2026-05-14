"""Compatibility shim for the legacy parity helper module path.

The canonical implementation now lives at
``src/macmarket_trader/indicators/thinkorswim_parity.py``. The original
``tests.helpers.momentum_parity`` module was loaded via importlib by
the parity scaffold so it didn't need to be a real package — those
loaders still import this file, so we re-export every public name from
the production module to keep them working.

Existing callers should migrate to::

    from macmarket_trader.indicators.thinkorswim_parity import ...
"""

from __future__ import annotations

from macmarket_trader.indicators.thinkorswim_parity import (  # noqa: F401
    DEFAULT_TOLERANCES,
    FieldDelta,
    FixtureComparisonResult,
    FixtureFolderValidation,
    FixtureReadiness,
    LABEL_FIELDS,
    PARITY_MODES,
    ParityFixtureError,
    ParityFixtureSpec,
    ParityManifest,
    ParityReportSummary,
    RECOMMENDED_STUDY_NAMES,
    RECOMMENDED_VISUAL_FIELDS,
    REPORT_FILENAME_JSON,
    REPORT_FILENAME_MD,
    REPORT_SCHEMA_VERSION,
    STUDY_FIELDS,
    build_thinkorswim_momentum_parity_status,
    build_thinkorswim_parity_report,
    compare_momentum_to_thinkorswim,
    compare_with_tolerance,
    latest_study_row,
    load_bars_csv,
    load_manifest,
    load_study_csv,
    load_thinkorswim_manifest,
    normalize_thinkorswim_columns,
    parse_bool,
    parse_date,
    parse_datetime,
    parse_float,
    parse_int,
    parse_thinkorswim_bars_csv,
    parse_thinkorswim_study_csv,
    validate_thinkorswim_fixture_folder,
)


__all__ = [
    "DEFAULT_TOLERANCES",
    "FieldDelta",
    "FixtureComparisonResult",
    "FixtureFolderValidation",
    "FixtureReadiness",
    "LABEL_FIELDS",
    "PARITY_MODES",
    "ParityFixtureError",
    "ParityFixtureSpec",
    "ParityManifest",
    "ParityReportSummary",
    "RECOMMENDED_STUDY_NAMES",
    "RECOMMENDED_VISUAL_FIELDS",
    "REPORT_FILENAME_JSON",
    "REPORT_FILENAME_MD",
    "REPORT_SCHEMA_VERSION",
    "STUDY_FIELDS",
    "build_thinkorswim_momentum_parity_status",
    "build_thinkorswim_parity_report",
    "compare_momentum_to_thinkorswim",
    "compare_with_tolerance",
    "latest_study_row",
    "load_bars_csv",
    "load_manifest",
    "load_study_csv",
    "load_thinkorswim_manifest",
    "normalize_thinkorswim_columns",
    "parse_bool",
    "parse_date",
    "parse_datetime",
    "parse_float",
    "parse_int",
    "parse_thinkorswim_bars_csv",
    "parse_thinkorswim_study_csv",
    "validate_thinkorswim_fixture_folder",
]
