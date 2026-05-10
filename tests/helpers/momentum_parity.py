"""Helpers for Thinkorswim Momentum Intelligence parity fixtures.

This module contains the deterministic parsing/loading layer used by the
parity test in ``tests/test_momentum_thinkorswim_parity_scaffold.py``. It is
intentionally pure (no I/O beyond the file paths it is handed) and forgiving
about Thinkorswim CSV column casing/underscores.

Real fixture data does **not** ship in the repo — operators drop CSVs and a
``manifest.json`` into ``tests/fixtures/thinkorswim_momentum/``. See that
directory's README.md for the workflow.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, date as date_cls, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from macmarket_trader.domain.schemas import Bar


# ── column-name normalization ───────────────────────────────────────────────


def _normalize_key(value: str) -> str:
    """Lowercase a column header and strip non-alphanumeric characters.

    ``Total Score`` → ``totalscore``; ``HLP_Output`` → ``hlpoutput``.
    """
    return re.sub(r"[^a-z0-9]+", "", value.lower())


# Map normalized header → canonical study field.
_STUDY_FIELD_BY_KEY: dict[str, str] = {
    # total score
    "totalscore": "total_score",
    # true momentum
    "truemomentum": "true_momentum",
    # true momentum EMA — accept several common variants. ``EMA`` is what the
    # source ST_TrueMomentumSTUDY plot is actually called; operators often
    # rename it on export.
    "truemomentumema": "true_momentum_ema",
    "ema": "true_momentum_ema",
    # HiLo thrust
    "hilothrust": "hilo_thrust",
    # HLP composite output
    "hlpoutput": "hilo_output",
    # Trend / Momo
    "trend": "trend_score",
    "trendscore": "trend_score",
    "momo": "momo_score",
    "momoscore": "momo_score",
}

_BAR_FIELDS_BY_KEY: dict[str, str] = {
    "date": "date",
    "datetime": "datetime",
    "time": "datetime",
    "timestamp": "datetime",
    "open": "open",
    "o": "open",
    "high": "high",
    "h": "high",
    "low": "low",
    "l": "low",
    "close": "close",
    "c": "close",
    "last": "close",
    "volume": "volume",
    "vol": "volume",
    "v": "volume",
}


# Canonical study fields the parity test understands.
STUDY_FIELDS: tuple[str, ...] = (
    "total_score",
    "true_momentum",
    "true_momentum_ema",
    "hilo_thrust",
    "hilo_output",
    "trend_score",
    "momo_score",
)


class ParityFixtureError(AssertionError):
    """Raised when a fixture's data is missing or malformed.

    Inherits from ``AssertionError`` so pytest surfaces it as a normal test
    failure rather than an unexpected exception.
    """


# ── primitive parsers ───────────────────────────────────────────────────────


def parse_float(value: Any) -> float | None:
    """Best-effort float parser.

    Returns ``None`` for ``None``/empty/`"NaN"`/``"#N/A"``/whitespace-only
    strings. Strips commas, percent signs, and surrounding whitespace.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {"nan", "n/a", "#n/a", "na", "null", "none", "-"}:
        return None
    cleaned = text.replace(",", "").replace("%", "").replace("$", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    flt = parse_float(value)
    if flt is None:
        return None
    return int(round(flt))


def parse_datetime(value: Any) -> datetime | None:
    """Parse a Thinkorswim-style date/time string into a UTC datetime.

    Accepts ISO 8601 (with or without ``T`` and ``Z``), ``YYYY-MM-DD``,
    ``MM/DD/YYYY``, ``MM/DD/YY``, and the common ``MM/DD/YY HH:MM`` shape.
    Returns ``None`` if the value can't be parsed.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date_cls):
        return datetime.combine(value, datetime.min.time(), tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    iso_text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        pass
    fmts = (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%y %H:%M",
        "%m/%d/%y %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    )
    for fmt in fmts:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_date(value: Any) -> date_cls | None:
    dt = parse_datetime(value)
    if dt is None:
        return None
    return dt.date()


# ── manifest loader ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParityFixtureSpec:
    name: str
    symbol: str
    timeframe: str
    bars_csv: Path
    study_csv: Path | None
    higher_timeframe_bars_csv: Path | None
    expected_latest: Mapping[str, float]
    tolerances: Mapping[str, float]
    raw: Mapping[str, Any]


def load_manifest(manifest_path: Path) -> list[ParityFixtureSpec]:
    """Load and validate a ``manifest.json`` next to the fixture CSVs."""
    if not manifest_path.exists():
        raise ParityFixtureError(f"manifest not found: {manifest_path}")

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ParityFixtureError(f"manifest is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict) or "fixtures" not in raw:
        raise ParityFixtureError(
            "manifest must be a JSON object with a top-level 'fixtures' array"
        )

    fixtures_raw = raw.get("fixtures")
    if not isinstance(fixtures_raw, list) or not fixtures_raw:
        raise ParityFixtureError("'fixtures' must be a non-empty list")

    base_dir = manifest_path.parent
    specs: list[ParityFixtureSpec] = []
    for index, entry in enumerate(fixtures_raw):
        if not isinstance(entry, dict):
            raise ParityFixtureError(f"fixture[{index}] must be an object")
        for required in ("name", "symbol", "timeframe", "bars_csv"):
            if required not in entry:
                raise ParityFixtureError(
                    f"fixture[{index}] missing required field: {required}"
                )

        timeframe = str(entry["timeframe"]).strip().upper()
        if timeframe not in {"1D", "4H", "1H"}:
            raise ParityFixtureError(
                f"fixture {entry['name']!r} timeframe must be one of 1D, 4H, 1H (got {timeframe!r})"
            )

        expected = entry.get("expected_latest", {})
        tolerances = entry.get("tolerances", {})
        if not isinstance(expected, dict) or not expected:
            raise ParityFixtureError(
                f"fixture {entry['name']!r} must include a non-empty expected_latest mapping"
            )
        if not isinstance(tolerances, dict):
            raise ParityFixtureError(
                f"fixture {entry['name']!r} tolerances must be a mapping"
            )
        for key in expected:
            if key not in STUDY_FIELDS:
                raise ParityFixtureError(
                    f"fixture {entry['name']!r} expected_latest key {key!r} is not a known study field"
                )

        study_csv = entry.get("study_csv")
        htf_csv = entry.get("higher_timeframe_bars_csv")
        specs.append(
            ParityFixtureSpec(
                name=str(entry["name"]),
                symbol=str(entry["symbol"]).strip().upper(),
                timeframe=timeframe,
                bars_csv=(base_dir / str(entry["bars_csv"])).resolve(),
                study_csv=(base_dir / str(study_csv)).resolve() if study_csv else None,
                higher_timeframe_bars_csv=(base_dir / str(htf_csv)).resolve() if htf_csv else None,
                expected_latest={k: float(v) for k, v in expected.items()},
                tolerances={k: float(v) for k, v in tolerances.items()},
                raw=entry,
            )
        )
    return specs


# ── CSV parsers ─────────────────────────────────────────────────────────────


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ParityFixtureError(f"CSV file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


def _normalize_row(row: Mapping[str, Any], key_map: Mapping[str, str]) -> dict[str, Any]:
    """Return a dict keyed by canonical names, picking the first matching column."""
    canonical: dict[str, Any] = {}
    for header, value in row.items():
        if header is None:
            continue
        normalized = _normalize_key(str(header))
        canonical_key = key_map.get(normalized)
        if canonical_key is None:
            continue
        # Prefer the first occurrence of a canonical key (e.g., ``Date`` wins
        # over a later ``Datetime`` if both are present).
        canonical.setdefault(canonical_key, value)
    return canonical


def load_bars_csv(path: Path) -> list[Bar]:
    """Parse a Thinkorswim-style OHLCV CSV into a list of ``Bar`` rows.

    Sort order matches CSV order; the indicator services re-sort by timestamp
    or date as needed.
    """
    rows = _read_csv_rows(path)
    if not rows:
        raise ParityFixtureError(f"bars CSV is empty: {path}")

    bars: list[Bar] = []
    for line_no, raw_row in enumerate(rows, start=2):  # +1 for header, +1 for 1-indexed
        row = _normalize_row(raw_row, _BAR_FIELDS_BY_KEY)
        when = parse_datetime(row.get("datetime"))
        when_date = parse_date(row.get("date")) if "date" in row else (when.date() if when else None)
        if when_date is None and when is not None:
            when_date = when.date()
        if when_date is None:
            raise ParityFixtureError(f"{path}: row {line_no} is missing a parseable date/datetime column")

        open_ = parse_float(row.get("open"))
        high = parse_float(row.get("high"))
        low = parse_float(row.get("low"))
        close = parse_float(row.get("close"))
        volume = parse_int(row.get("volume")) or 0
        if open_ is None or high is None or low is None or close is None:
            raise ParityFixtureError(
                f"{path}: row {line_no} is missing one of open/high/low/close (got {row!r})"
            )

        bars.append(
            Bar(
                date=when_date,
                timestamp=when,
                open=float(open_),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=int(volume),
            )
        )
    return bars


def load_study_csv(path: Path) -> list[dict[str, Any]]:
    """Parse a Thinkorswim study export into normalized rows.

    Each returned dict carries any of the canonical fields in ``STUDY_FIELDS``
    that the CSV provided, plus ``date``/``datetime`` if those columns were
    present. Numeric values are parsed via :func:`parse_float` so they are
    either ``float`` or ``None``.
    """
    rows = _read_csv_rows(path)
    if not rows:
        raise ParityFixtureError(f"study CSV is empty: {path}")

    combined_keys = {**_BAR_FIELDS_BY_KEY, **_STUDY_FIELD_BY_KEY}
    out: list[dict[str, Any]] = []
    for raw_row in rows:
        canonical = _normalize_row(raw_row, combined_keys)
        record: dict[str, Any] = {}
        # Numeric study values
        for field in STUDY_FIELDS:
            if field in canonical:
                record[field] = parse_float(canonical.get(field))
        # Optional date/datetime
        when = parse_datetime(canonical.get("datetime"))
        when_date = parse_date(canonical.get("date")) if "date" in canonical else (when.date() if when else None)
        if when_date is not None:
            record["date"] = when_date
        if when is not None:
            record["datetime"] = when
        out.append(record)
    return out


def latest_study_row(study_rows: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Return the row with the largest parseable date/datetime, or the last row."""
    rows = list(study_rows)
    if not rows:
        raise ParityFixtureError("study CSV produced zero rows")
    keyed = [(row.get("datetime") or row.get("date"), row) for row in rows]
    if any(when is not None for when, _ in keyed):
        keyed.sort(key=lambda item: (item[0] is not None, item[0] or 0))
        return keyed[-1][1]
    return rows[-1]


# ── tolerance comparison ────────────────────────────────────────────────────


def compare_with_tolerance(
    expected: Mapping[str, float],
    actual: Mapping[str, float | int | None],
    tolerances: Mapping[str, float],
    *,
    label: str,
    default_tolerance: float = 1.0,
) -> list[str]:
    """Return a list of human-readable mismatches, empty when within tolerance.

    Fields in ``expected`` that are missing from ``actual`` are reported.
    Fields not in ``expected`` are skipped (so partial fixtures only assert
    what the operator has exported).
    """
    mismatches: list[str] = []
    for key, expected_value in expected.items():
        if key not in STUDY_FIELDS:
            mismatches.append(f"{label}: unknown field {key!r}")
            continue
        actual_value = actual.get(key) if isinstance(actual, Mapping) else None
        if actual_value is None:
            mismatches.append(f"{label}: missing actual value for {key!r}")
            continue
        try:
            actual_float = float(actual_value)
        except (TypeError, ValueError):
            mismatches.append(f"{label}: non-numeric actual {key!r}={actual_value!r}")
            continue
        tol = float(tolerances.get(key, default_tolerance))
        if abs(actual_float - float(expected_value)) > tol:
            mismatches.append(
                f"{label}: {key} expected {expected_value} ± {tol}, actual {actual_float:.4f}"
            )
    return mismatches


__all__ = [
    "ParityFixtureError",
    "ParityFixtureSpec",
    "STUDY_FIELDS",
    "compare_with_tolerance",
    "latest_study_row",
    "load_bars_csv",
    "load_manifest",
    "load_study_csv",
    "parse_date",
    "parse_datetime",
    "parse_float",
    "parse_int",
]
