"""Thinkorswim Momentum Intelligence parity workflow.

Production-side module that owns the operator-supplied Thinkorswim CSV
fixture contract for the Momentum Intelligence Layer. Splits cleanly
into three concerns:

1. **Parsing / normalization.** ``parse_thinkorswim_bars_csv`` and
   ``parse_thinkorswim_study_csv`` read the operator's Thinkorswim
   exports with case- / whitespace- / underscore-insensitive column
   matching. ``normalize_thinkorswim_columns`` is the underlying
   header normalizer.
2. **Manifest + folder validation.** ``load_thinkorswim_manifest`` and
   ``validate_thinkorswim_fixture_folder`` enforce the
   ``manifest.json`` contract documented in
   ``docs/thinkorswim-momentum-parity.md`` *without* running the
   indicator math.
3. **Comparison + status.** ``compare_momentum_to_thinkorswim`` runs
   :class:`MomentumChartService` against a fixture's bars and compares
   the deterministic payload to the operator-supplied
   ``expected_latest`` values (and to the study CSV's last row when
   available). ``build_thinkorswim_parity_report`` aggregates results
   into Markdown / JSON.
   ``build_thinkorswim_momentum_parity_status`` is the cheap,
   read-only status helper consumed by the Settings card — it never
   runs indicator math, only inspects the manifest / report files on
   disk.

The module is intentionally **research-only**:

- it never approves, rejects, sizes, routes, opens, closes, or settles
  trades,
- it never creates recommendations / paper orders,
- it never mutates settings, the database, or third-party services,
- and it never calls an LLM.

A failing parity report is loud diagnostic evidence; it does not
"deactivate" any production switch automatically.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, date as date_cls, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from macmarket_trader.domain.schemas import Bar


# ── canonical study field names ─────────────────────────────────────────────


STUDY_FIELDS: tuple[str, ...] = (
    "total_score",
    "true_momentum",
    "true_momentum_ema",
    "hilo_thrust",
    "hilo_output",
    "trend_score",
    "momo_score",
    # HiLo field-label cleanup (visual parity work). ``hilo_slowd`` and
    # ``hilo_slowd_x`` are the rendered stochastic SlowD / SlowD_X
    # values MacMarket currently surfaces on the HiLo panel.
    # ``tos_hilo_elite_scalar`` is the operator-read ToS ST_HiLoElite
    # scalar — MacMarket does not compute a ToS-comparable scalar today,
    # so the field is recorded for the audit trail but never
    # auto-compared against a MacMarket value (see
    # ``_REFERENCE_ONLY_FIELDS`` below).
    "hilo_slowd",
    "hilo_slowd_x",
    "tos_hilo_elite_scalar",
    # ``hilo_score`` is the composite -30/0/+30 HiLo thrust component
    # the operator reads off MacMarket's HiLo panel. It is distinct from
    # ``hilo_output`` (legacy alias) and from the categorical
    # ``hilo_thrust_state`` label.
    "hilo_score",
    # Composite component fields the operator reads off MacMarket's
    # MomentumScoreSnapshot when diagnosing visual_attestation
    # discrepancies. These are the building blocks of the composite
    # total score (true_momentum_score + hilo_score + atr_bias +
    # macd_bias + ma_bias = MM component sum). Compared per-field on
    # visual_attestation only when both sides supply them.
    "true_momentum_score",
    "atr_bias",
    "macd_bias",
    "ma_bias",
)

# Canonical MacMarket composite-score components. The validator sums
# these on the MacMarket side (when all are present in
# ``macmarket_observed_latest``) to surface a composite-attribution
# diagnostic. Order matches the Phase A1 composite formula in
# ``docs/momentum-intelligence-layer.md``.
MM_COMPOSITE_COMPONENT_FIELDS: tuple[str, ...] = (
    "true_momentum_score",
    "hilo_score",
    "atr_bias",
    "macd_bias",
    "ma_bias",
)

# Default visual_attestation close-price tolerance. Operator overrides
# via ``tolerances.close`` per fixture. The default is intentionally
# conservative — visual reads off a chart can drift by a few cents per
# pixel; a price-context mismatch beyond this default flags the fixture
# as not apples-to-apples (warning by default; a strict fail only fires
# when ``strict_price_context`` is set on the fixture).
DEFAULT_PRICE_CLOSE_TOLERANCE: float = 0.10

# Reference-only study fields: operators can record observed values
# for these (so the audit trail captures the rendered ToS reading),
# but the validator never asserts a MacMarket equivalent because
# MacMarket does not currently compute one. The fixture report
# surfaces the observed value alongside a clear "MacMarket has no
# equivalent" diagnostic rather than failing parity.
_REFERENCE_ONLY_FIELDS: frozenset[str] = frozenset({"tos_hilo_elite_scalar"})

# Optional categorical / flag fields. The numeric study fields above are
# compared with per-field absolute tolerances; the fields below are
# compared by equality (after canonical normalization). Operators may
# omit any of them.
LABEL_FIELDS: tuple[str, ...] = (
    "total_label",
    "pullback_signal",
    "reversal_warning",
    "no_trade_warning",
    # HiLo thrust state — categorical (bullish / bearish / neutral /
    # confirmed / deconfirmed). Operators record this string directly
    # when capturing a visual attestation.
    "hilo_thrust_state",
)


# ── column-name normalization ───────────────────────────────────────────────


def _normalize_key(value: str) -> str:
    """Lowercase a column header and strip non-alphanumeric characters.

    ``Total Score`` → ``totalscore``; ``HLP_Output`` → ``hlpoutput``.
    """
    return re.sub(r"[^a-z0-9]+", "", value.lower())


_STUDY_FIELD_BY_KEY: dict[str, str] = {
    # total score
    "totalscore": "total_score",
    "dailyscore": "total_score",
    # total label (Strong Bull / Bull / Neutral / Bear / Strong Bear / etc.)
    "totallabel": "total_label",
    "label": "total_label",
    # true momentum
    "truemomentum": "true_momentum",
    # true momentum EMA — accept several common variants. ``EMA`` is what the
    # source ST_TrueMomentumSTUDY plot is actually called; operators often
    # rename it on export.
    "truemomentumema": "true_momentum_ema",
    "ema": "true_momentum_ema",
    # HiLo thrust
    "hilothrust": "hilo_thrust",
    # HLP composite output / HiLo Score
    "hlpoutput": "hilo_output",
    "hilooutput": "hilo_output",
    "hiloscore": "hilo_output",
    # SlowD / SlowD_X — rendered stochastic values MacMarket already
    # surfaces. Accept a handful of common operator labels.
    "hiloslowd": "hilo_slowd",
    "slowd": "hilo_slowd",
    "hiloslowdx": "hilo_slowd_x",
    "slowdx": "hilo_slowd_x",
    "hiloslowdxline": "hilo_slowd_x",
    # ToS-comparable ST_HiLoElite scalar (operator-read only).
    "hiloelite": "tos_hilo_elite_scalar",
    "hiloelitescalar": "tos_hilo_elite_scalar",
    "stoshiloelite": "tos_hilo_elite_scalar",
    "toshiloelite": "tos_hilo_elite_scalar",
    "toshiloelitescalar": "tos_hilo_elite_scalar",
    # Trend / Momo
    "trend": "trend_score",
    "trendscore": "trend_score",
    "momo": "momo_score",
    "momoscore": "momo_score",
    # Signal flags
    "pullbacksignal": "pullback_signal",
    "pullback": "pullback_signal",
    "reversalwarning": "reversal_warning",
    "notradewarning": "no_trade_warning",
    "notrade": "no_trade_warning",
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


class ParityFixtureError(AssertionError):
    """Raised when a fixture's data is missing or malformed.

    Inherits from ``AssertionError`` so pytest surfaces it as a normal
    test failure rather than an unexpected exception. Carrying the
    original file path / column in the message is required.
    """


# ── primitive parsers ───────────────────────────────────────────────────────


def parse_float(value: Any) -> float | None:
    """Best-effort float parser.

    Returns ``None`` for ``None``/empty/``"NaN"``/``"#N/A"``/whitespace-only
    strings. Strips commas, percent signs, and surrounding whitespace.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # Avoid treating True/False as 1/0 silently — they are flags, not numbers.
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


def parse_bool(value: Any) -> bool | None:
    """Parse a Thinkorswim-style flag value to ``bool`` or ``None``."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if math.isnan(value) if isinstance(value, float) else False:
            return None
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"true", "yes", "y", "1", "on"}:
        return True
    if text in {"false", "no", "n", "0", "off"}:
        return False
    return None


def parse_datetime(value: Any) -> datetime | None:
    """Parse a Thinkorswim-style date/time string into a UTC datetime."""
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


# ── manifest schema ─────────────────────────────────────────────────────────


PARITY_MODES: tuple[str, ...] = (
    "exported_study_csv",
    "visual_observation",
    "visual_attestation",
)

# Subset of canonical study/label fields the operator is *strongly
# recommended* to capture from a Thinkorswim rendered chart label when
# they record a visual observation. The validator does not fail the
# fixture when these are missing — it surfaces reason codes so the
# operator can decide whether to widen their visual capture or accept
# the partial review.
RECOMMENDED_VISUAL_FIELDS: tuple[str, ...] = (
    "total_score",
    "total_label",
    "true_momentum",
    "true_momentum_ema",
)

# "At least one HiLo field" recommendation — the validator emits a
# reason code when none of these were captured for a visual fixture.
RECOMMENDED_HILO_VISUAL_FIELDS: tuple[str, ...] = (
    "hilo_slowd",
    "hilo_slowd_x",
    "tos_hilo_elite_scalar",
    "hilo_thrust",
    "hilo_output",
)


@dataclass(frozen=True)
class ParityFixtureSpec:
    """Validated single-fixture entry from ``manifest.json``.

    ``bars_csv`` is ``None`` only when ``parity_mode ==
    "visual_attestation"``. The visual-attestation mode does not need a
    bars CSV because no MacMarket computation runs — the validator
    compares the operator-entered ToS reading against the
    operator-entered MM reading directly.
    """

    name: str
    symbol: str
    timeframe: str
    parity_mode: str
    bars_csv: Path | None
    study_csv: Path | None
    higher_timeframe_bars_csv: Path | None
    expected_latest: Mapping[str, float]
    expected_labels: Mapping[str, str]
    tolerances: Mapping[str, float]
    label_must_match: bool
    comparison_window: int
    study_timezone: str
    notes: str | None
    # ── visual_observation mode fields ────────────────────────────────
    # Operators capture ToS values manually from a rendered chart. The
    # validator never falls back to the study CSV in visual mode — the
    # observation is the source of truth.
    observed_bar_date: date_cls | None
    screenshot: str | None
    macmarket_screenshot: str | None
    screenshot_notes: str | None
    reviewer: str | None
    reviewed_at: datetime | None
    # ── visual_attestation mode fields ────────────────────────────────
    # No bars / no study / no computation. Both sides are operator-
    # entered. ``tos_observed_latest`` / ``macmarket_observed_latest``
    # are numeric maps; ``tos_observed_labels`` / ``macmarket_observed_labels``
    # carry the label fields (total_label, pullback_signal, etc).
    tos_observed_latest: Mapping[str, float]
    tos_observed_labels: Mapping[str, str]
    macmarket_observed_latest: Mapping[str, float]
    macmarket_observed_labels: Mapping[str, str]
    # Optional OHLC price context for visual_attestation diagnostics.
    # Each mapping carries any subset of {open, high, low, close}.
    # When both sides supply ``close``, the validator compares with
    # tolerance ``tolerances.close`` (default
    # :data:`DEFAULT_PRICE_CLOSE_TOLERANCE`).
    tos_observed_price: Mapping[str, float]
    macmarket_observed_price: Mapping[str, float]
    # When True, a close-price mismatch flips the visual_attestation
    # result to ``visual_failed`` even if every other field passed.
    # Default False — most operators want price context surfaced as a
    # warning while the oscillator / composite parity comparison still
    # makes the call.
    strict_price_context: bool
    raw: Mapping[str, Any]

    @property
    def is_visual(self) -> bool:
        return self.parity_mode == "visual_observation"

    @property
    def is_exported_study_csv(self) -> bool:
        return self.parity_mode == "exported_study_csv"

    @property
    def is_visual_attestation(self) -> bool:
        return self.parity_mode == "visual_attestation"


@dataclass(frozen=True)
class ParityManifest:
    """Top-level manifest container exposing fixture-list metadata."""

    schema_version: str
    generated_at: datetime | None
    source: str
    study_names: tuple[str, ...]
    fixtures: tuple[ParityFixtureSpec, ...]
    raw: Mapping[str, Any]


# Default per-field absolute tolerances. Conservative starting values
# documented in the operator workflow.
DEFAULT_TOLERANCES: Mapping[str, float] = {
    "total_score": 2.0,
    "trend_score": 2.5,
    "momo_score": 2.5,
    "true_momentum": 1.0,
    "true_momentum_ema": 1.0,
    "hilo_thrust": 5.0,
    "hilo_output": 5.0,
    # SlowD / SlowD_X (range 0..100). Start conservative; tighten once
    # multiple symbols agree.
    "hilo_slowd": 2.0,
    "hilo_slowd_x": 2.0,
    # ToS-comparable ST_HiLoElite scalar is reference-only in
    # visual_observation mode (MacMarket does not compute one). In
    # visual_attestation mode it CAN be compared if both ToS and MM
    # observations include it — the tolerance is honored there.
    "tos_hilo_elite_scalar": 5.0,
}

# Visual-attestation default tolerances. These match the prompt's
# specification — wider than the legacy CSV-derived defaults because
# operator readings carry one to two pixels of visual error per side.
DEFAULT_VISUAL_ATTESTATION_TOLERANCES: Mapping[str, float] = {
    "total_score": 2.0,
    "trend_score": 2.0,
    "momo_score": 2.0,
    "true_momentum": 1.5,
    "true_momentum_ema": 1.5,
    "hilo_slowd": 2.0,
    "hilo_slowd_x": 2.0,
    "hilo_score": 5.0,
    # tos_hilo_elite_scalar is compared symmetrically when both sides
    # populated; keep the same width as the SlowD readings.
    "tos_hilo_elite_scalar": 2.0,
    "hilo_thrust": 5.0,
    "hilo_output": 5.0,
    # Composite component defaults (each is an integer-ish weighted
    # contribution). Operators may tighten via ``tolerances`` per
    # fixture.
    "true_momentum_score": 5.0,
    "atr_bias": 5.0,
    "macd_bias": 5.0,
    "ma_bias": 5.0,
}

# Allowed timeframe tokens.
_ALLOWED_TIMEFRAMES = {"1D", "1W", "4H", "1H"}

# Recommended Thinkorswim study script names. Used for documentation /
# validation only — the parity comparison itself does not care which
# studies produced the values.
RECOMMENDED_STUDY_NAMES: tuple[str, ...] = (
    "ST_TrueMomentumScoreSTUDY",
    "ST_TrueMomentumSTUDY",
    "ST_HiLoEliteSTUDY",
)


def _coerce_tolerances(raw: Any, fixture_name: str) -> dict[str, float]:
    """Validate the per-fixture tolerances mapping.

    Returns only what the operator supplied. Defaults from
    :data:`DEFAULT_TOLERANCES` are applied lazily at comparison time
    (see :func:`compare_with_tolerance`) so the manifest round-trips
    cleanly and operators see only their own tolerances in the spec.
    """
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ParityFixtureError(
            f"fixture {fixture_name!r} tolerances must be a mapping"
        )
    # Price-context tolerance keys accepted alongside the canonical
    # study fields. ``close`` is the primary one (default 0.05 for
    # ETFs/equities); the OHLC siblings are accepted so operators can
    # tighten any of them per fixture without splitting the tolerances
    # block.
    price_tolerance_keys = {"close", "open", "high", "low"}
    out: dict[str, float] = {}
    for key, value in raw.items():
        if key not in STUDY_FIELDS and key not in price_tolerance_keys:
            raise ParityFixtureError(
                f"fixture {fixture_name!r} tolerance for unknown field {key!r}"
            )
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError) as exc:
            raise ParityFixtureError(
                f"fixture {fixture_name!r} tolerance for {key!r} is not numeric: {value!r}"
            ) from exc
    return out


def resolve_tolerance(
    tolerances: Mapping[str, float],
    field: str,
    *,
    default_tolerance: float = 1.0,
) -> float:
    """Return the per-field tolerance, falling back to defaults."""
    if field in tolerances:
        return float(tolerances[field])
    if field in DEFAULT_TOLERANCES:
        return float(DEFAULT_TOLERANCES[field])
    return float(default_tolerance)


_PRICE_CONTEXT_FIELDS: frozenset[str] = frozenset({"open", "high", "low", "close"})


def _coerce_price_context(
    raw: Any, fixture_name: str, side: str
) -> dict[str, float]:
    """Validate a ``tos_observed_price`` / ``macmarket_observed_price``
    block. Returns ``{}`` when the manifest does not supply one; raises
    :class:`ParityFixtureError` when the operator provided a malformed
    block (unknown key, non-numeric value, etc).
    """
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ParityFixtureError(
            f"fixture {fixture_name!r} {side} must be an object with OHLC fields"
        )
    out: dict[str, float] = {}
    for key, value in raw.items():
        if key not in _PRICE_CONTEXT_FIELDS:
            raise ParityFixtureError(
                f"fixture {fixture_name!r} {side} key {key!r} is not "
                "one of open / high / low / close"
            )
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError) as exc:
            raise ParityFixtureError(
                f"fixture {fixture_name!r} {side}.{key} is not numeric: {value!r}"
            ) from exc
    return out


def _split_expected(raw: Mapping[str, Any], fixture_name: str) -> tuple[dict[str, float], dict[str, str]]:
    """Split ``expected_latest`` into numeric vs label/flag buckets."""
    numeric: dict[str, float] = {}
    labels: dict[str, str] = {}
    for key, value in raw.items():
        if key in STUDY_FIELDS:
            try:
                numeric[str(key)] = float(value)
            except (TypeError, ValueError) as exc:
                raise ParityFixtureError(
                    f"fixture {fixture_name!r} expected_latest {key!r} is not numeric: {value!r}"
                ) from exc
        elif key in LABEL_FIELDS:
            labels[str(key)] = str(value).strip()
        else:
            raise ParityFixtureError(
                f"fixture {fixture_name!r} expected_latest key {key!r} is not a known study field"
            )
    return numeric, labels


def load_thinkorswim_manifest(manifest_path: Path) -> ParityManifest:
    """Load and validate ``manifest.json``.

    Returns the full :class:`ParityManifest` (top-level metadata + the
    validated fixture list). Use :func:`load_manifest` for the legacy
    "just give me the fixture list" entrypoint.
    """
    manifest_path = Path(manifest_path)
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

    schema_version = str(raw.get("schema_version", "thinkorswim_momentum_parity.v1"))
    source = str(raw.get("source", "thinkorswim"))
    generated_at = parse_datetime(raw.get("generated_at") or raw.get("exported_at"))
    study_names_raw = raw.get("study_names") or list(RECOMMENDED_STUDY_NAMES)
    if not isinstance(study_names_raw, list) or any(not isinstance(s, str) for s in study_names_raw):
        raise ParityFixtureError("'study_names' must be a list of strings")
    study_names = tuple(str(s) for s in study_names_raw)

    base_dir = manifest_path.parent
    specs: list[ParityFixtureSpec] = []
    seen_names: set[str] = set()
    for index, entry in enumerate(fixtures_raw):
        if not isinstance(entry, dict):
            raise ParityFixtureError(f"fixture[{index}] must be an object")
        # ``bars_csv`` is now mode-dependent; check the always-required
        # fields first and validate ``bars_csv`` after we resolve mode.
        for required in ("name", "symbol", "timeframe"):
            if required not in entry:
                raise ParityFixtureError(
                    f"fixture[{index}] missing required field: {required}"
                )

        name = str(entry["name"]).strip()
        if not name:
            raise ParityFixtureError(f"fixture[{index}] name must be non-empty")
        if name in seen_names:
            raise ParityFixtureError(f"duplicate fixture name in manifest: {name}")
        seen_names.add(name)

        timeframe = str(entry["timeframe"]).strip().upper()
        if timeframe not in _ALLOWED_TIMEFRAMES:
            raise ParityFixtureError(
                f"fixture {name!r} timeframe must be one of "
                f"{sorted(_ALLOWED_TIMEFRAMES)} (got {timeframe!r})"
            )

        # ``observed_latest`` is the canonical key for visual_observation
        # mode; ``expected_latest`` is the legacy/exported-study-csv key.
        # When both are present, prefer ``observed_latest`` and report it
        # as a manifest validation error so operators don't double-source.
        observed_raw = entry.get("observed_latest")
        expected_raw = entry.get("expected_latest")
        if observed_raw is not None and expected_raw is not None:
            raise ParityFixtureError(
                f"fixture {name!r} declares both 'expected_latest' and "
                "'observed_latest' — use one (observed_latest for visual_observation)"
            )
        captured_raw = observed_raw if observed_raw is not None else expected_raw

        # ``visual_attestation``-mode observation pair. Both sides are
        # operator-entered readings — no MacMarket computation runs.
        tos_observed_raw = entry.get("tos_observed_latest")
        macmarket_observed_raw = entry.get("macmarket_observed_latest")

        # Resolve parity_mode. Explicit value wins; otherwise infer from
        # the manifest shape (backward compatible).
        explicit_mode_raw = entry.get("parity_mode")
        if explicit_mode_raw is not None:
            parity_mode = str(explicit_mode_raw).strip().lower()
            if parity_mode not in PARITY_MODES:
                raise ParityFixtureError(
                    f"fixture {name!r} parity_mode must be one of "
                    f"{list(PARITY_MODES)} (got {explicit_mode_raw!r})"
                )
        else:
            study_csv_present = entry.get("study_csv") is not None
            bars_csv_present = entry.get("bars_csv") is not None
            attestation_present = (
                tos_observed_raw is not None and macmarket_observed_raw is not None
            )
            observed_present = observed_raw is not None
            if attestation_present:
                parity_mode = "visual_attestation"
            elif observed_present and bars_csv_present:
                parity_mode = "visual_observation"
            elif observed_present:
                # No bars and only single-sided ``observed_latest`` — treat
                # as visual_observation (legacy shape) and let the loader
                # require bars_csv below.
                parity_mode = "visual_observation"
            elif study_csv_present:
                parity_mode = "exported_study_csv"
            else:
                # Backward compatibility: legacy manifests that only
                # carry ``expected_latest`` and no study CSV still load
                # as exported_study_csv mode. The validator simply has
                # no row-level study CSV to cross-check.
                parity_mode = "exported_study_csv"

        if not isinstance(captured_raw, dict):
            captured_raw = {}

        if parity_mode == "exported_study_csv" and not captured_raw:
            raise ParityFixtureError(
                f"fixture {name!r} (exported_study_csv) must include a "
                "non-empty expected_latest mapping"
            )

        # bars_csv requirement — required for all modes EXCEPT
        # visual_attestation. The attestation mode does no computation,
        # so a bars CSV is not needed and not requested from the
        # operator.
        if parity_mode != "visual_attestation" and "bars_csv" not in entry:
            raise ParityFixtureError(
                f"fixture {name!r} ({parity_mode}) missing required field: bars_csv"
            )

        numeric_expected, label_expected = _split_expected(captured_raw, name)

        # Parse the visual_attestation observation pair when the mode
        # uses them. Either side may omit fields; the comparison engine
        # skips fields not present in both observations.
        tos_price_raw = entry.get("tos_observed_price")
        macmarket_price_raw = entry.get("macmarket_observed_price")
        strict_price_context = bool(entry.get("strict_price_context", False))
        if parity_mode == "visual_attestation":
            if not isinstance(tos_observed_raw, dict) or not tos_observed_raw:
                raise ParityFixtureError(
                    f"fixture {name!r} (visual_attestation) must include a "
                    "non-empty 'tos_observed_latest' mapping"
                )
            if not isinstance(macmarket_observed_raw, dict) or not macmarket_observed_raw:
                raise ParityFixtureError(
                    f"fixture {name!r} (visual_attestation) must include a "
                    "non-empty 'macmarket_observed_latest' mapping"
                )
            tos_numeric, tos_labels = _split_expected(tos_observed_raw, name)
            mm_numeric, mm_labels = _split_expected(macmarket_observed_raw, name)
            tos_price = _coerce_price_context(tos_price_raw, name, "tos_observed_price")
            mm_price = _coerce_price_context(
                macmarket_price_raw, name, "macmarket_observed_price"
            )
        else:
            tos_numeric = {}
            tos_labels = {}
            mm_numeric = {}
            mm_labels = {}
            tos_price = {}
            mm_price = {}
            if tos_observed_raw is not None or macmarket_observed_raw is not None:
                raise ParityFixtureError(
                    f"fixture {name!r} declares tos_observed_latest / "
                    "macmarket_observed_latest but parity_mode is not "
                    "'visual_attestation'"
                )
            if tos_price_raw is not None or macmarket_price_raw is not None:
                raise ParityFixtureError(
                    f"fixture {name!r} declares tos_observed_price / "
                    "macmarket_observed_price but parity_mode is not "
                    "'visual_attestation'"
                )

        tolerances = _coerce_tolerances(entry.get("tolerances"), name)

        study_csv = entry.get("study_csv")
        htf_csv = entry.get("higher_timeframe_bars_csv")
        notes_raw = entry.get("notes")
        notes = str(notes_raw).strip() if isinstance(notes_raw, str) and notes_raw.strip() else None

        comparison_window_raw = entry.get("comparison_window", 1)
        try:
            comparison_window = max(1, int(comparison_window_raw))
        except (TypeError, ValueError) as exc:
            raise ParityFixtureError(
                f"fixture {name!r} comparison_window must be a positive integer "
                f"(got {comparison_window_raw!r})"
            ) from exc

        label_must_match = bool(entry.get("label_must_match", False))
        study_timezone = str(entry.get("study_timezone", "America/New_York"))

        # Visual observation metadata fields (optional in all modes; the
        # report only renders them when present).
        observed_bar_date_raw = entry.get("observed_bar_date") or entry.get("bar_date")
        observed_bar_date = parse_date(observed_bar_date_raw) if observed_bar_date_raw is not None else None
        if observed_bar_date_raw is not None and observed_bar_date is None:
            raise ParityFixtureError(
                f"fixture {name!r} observed_bar_date {observed_bar_date_raw!r} is not parseable"
            )

        # ``tos_screenshot`` is the canonical name in visual_attestation
        # mode (paired with ``macmarket_screenshot``). ``screenshot`` is
        # the legacy single-screenshot field — accepted as an alias so
        # older manifests continue to load.
        screenshot_raw = entry.get("tos_screenshot") or entry.get("screenshot")
        screenshot = str(screenshot_raw).strip() if isinstance(screenshot_raw, str) and screenshot_raw.strip() else None
        macmarket_screenshot_raw = entry.get("macmarket_screenshot")
        macmarket_screenshot = (
            str(macmarket_screenshot_raw).strip()
            if isinstance(macmarket_screenshot_raw, str) and macmarket_screenshot_raw.strip()
            else None
        )
        screenshot_notes_raw = entry.get("screenshot_notes")
        screenshot_notes = (
            str(screenshot_notes_raw).strip()
            if isinstance(screenshot_notes_raw, str) and screenshot_notes_raw.strip()
            else None
        )
        reviewer_raw = entry.get("reviewer")
        reviewer = str(reviewer_raw).strip() if isinstance(reviewer_raw, str) and reviewer_raw.strip() else None
        reviewed_at_raw = entry.get("reviewed_at")
        reviewed_at = parse_datetime(reviewed_at_raw) if reviewed_at_raw is not None else None
        if reviewed_at_raw is not None and reviewed_at is None:
            raise ParityFixtureError(
                f"fixture {name!r} reviewed_at {reviewed_at_raw!r} is not parseable"
            )

        bars_csv_raw = entry.get("bars_csv")
        bars_csv_path: Path | None
        if bars_csv_raw is not None:
            bars_csv_path = (base_dir / str(bars_csv_raw)).resolve()
        else:
            bars_csv_path = None

        specs.append(
            ParityFixtureSpec(
                name=name,
                symbol=str(entry["symbol"]).strip().upper(),
                timeframe=timeframe,
                parity_mode=parity_mode,
                bars_csv=bars_csv_path,
                study_csv=(base_dir / str(study_csv)).resolve() if study_csv else None,
                higher_timeframe_bars_csv=(
                    (base_dir / str(htf_csv)).resolve() if htf_csv else None
                ),
                expected_latest=numeric_expected,
                expected_labels=label_expected,
                tolerances=tolerances,
                label_must_match=label_must_match,
                comparison_window=comparison_window,
                study_timezone=study_timezone,
                notes=notes,
                observed_bar_date=observed_bar_date,
                screenshot=screenshot,
                macmarket_screenshot=macmarket_screenshot,
                screenshot_notes=screenshot_notes,
                reviewer=reviewer,
                reviewed_at=reviewed_at,
                tos_observed_latest=tos_numeric,
                tos_observed_labels=tos_labels,
                macmarket_observed_latest=mm_numeric,
                macmarket_observed_labels=mm_labels,
                tos_observed_price=tos_price,
                macmarket_observed_price=mm_price,
                strict_price_context=strict_price_context,
                raw=entry,
            )
        )

    return ParityManifest(
        schema_version=schema_version,
        generated_at=generated_at,
        source=source,
        study_names=study_names,
        fixtures=tuple(specs),
        raw=raw,
    )


def load_manifest(manifest_path: Path) -> list[ParityFixtureSpec]:
    """Backward-compat shim: return just the fixture list."""
    return list(load_thinkorswim_manifest(manifest_path).fixtures)


# ── CSV parsers ─────────────────────────────────────────────────────────────


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ParityFixtureError(f"CSV file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


def normalize_thinkorswim_columns(
    row: Mapping[str, Any],
    *,
    kind: str = "study",
) -> dict[str, Any]:
    """Normalize Thinkorswim CSV headers to canonical keys.

    ``kind`` selects which key map to use:

    - ``"bars"``  → OHLCV / date / volume columns only,
    - ``"study"`` → study output columns (also accepts bar date columns).

    Returns a new dict keyed by canonical names, picking the *first*
    occurrence of each canonical key. Unknown columns are dropped.
    """
    if kind == "bars":
        key_map = _BAR_FIELDS_BY_KEY
    elif kind == "study":
        key_map = {**_BAR_FIELDS_BY_KEY, **_STUDY_FIELD_BY_KEY}
    else:
        raise ParityFixtureError(f"normalize_thinkorswim_columns: unknown kind {kind!r}")
    canonical: dict[str, Any] = {}
    for header, value in row.items():
        if header is None:
            continue
        normalized = _normalize_key(str(header))
        canonical_key = key_map.get(normalized)
        if canonical_key is None:
            continue
        canonical.setdefault(canonical_key, value)
    return canonical


def parse_thinkorswim_bars_csv(path: Path) -> list[Bar]:
    """Parse a Thinkorswim-style OHLCV CSV into a list of ``Bar`` rows.

    Sort order matches CSV order; the indicator services re-sort by
    timestamp or date as needed.
    """
    rows = _read_csv_rows(path)
    if not rows:
        raise ParityFixtureError(f"bars CSV is empty: {path}")

    bars: list[Bar] = []
    for line_no, raw_row in enumerate(rows, start=2):  # +1 for header, +1 for 1-indexed
        row = normalize_thinkorswim_columns(raw_row, kind="bars")
        when = parse_datetime(row.get("datetime"))
        when_date = parse_date(row.get("date")) if "date" in row else (when.date() if when else None)
        if when_date is None and when is not None:
            when_date = when.date()
        if when_date is None:
            raise ParityFixtureError(
                f"{path}: row {line_no} is missing a parseable date/datetime column "
                f"(seen headers: {sorted(raw_row.keys())})"
            )

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


# Legacy alias kept for the existing tests that import via the path-based
# helper loader.
load_bars_csv = parse_thinkorswim_bars_csv


def parse_thinkorswim_study_csv(path: Path) -> list[dict[str, Any]]:
    """Parse a Thinkorswim study export into normalized rows.

    Each returned dict carries any of the canonical fields in
    ``STUDY_FIELDS`` / ``LABEL_FIELDS`` that the CSV provided, plus
    ``date`` / ``datetime`` if those columns were present. Numeric
    values are parsed via :func:`parse_float` so they are either
    ``float`` or ``None``. Flag fields are parsed via :func:`parse_bool`.
    """
    rows = _read_csv_rows(path)
    if not rows:
        raise ParityFixtureError(f"study CSV is empty: {path}")

    out: list[dict[str, Any]] = []
    for raw_row in rows:
        canonical = normalize_thinkorswim_columns(raw_row, kind="study")
        record: dict[str, Any] = {}
        for field in STUDY_FIELDS:
            if field in canonical:
                record[field] = parse_float(canonical.get(field))
        for field in LABEL_FIELDS:
            if field in canonical:
                value = canonical.get(field)
                if field == "total_label":
                    record[field] = (
                        str(value).strip() if value is not None and str(value).strip() else None
                    )
                else:
                    record[field] = parse_bool(value)
        when = parse_datetime(canonical.get("datetime"))
        when_date = parse_date(canonical.get("date")) if "date" in canonical else (when.date() if when else None)
        if when_date is not None:
            record["date"] = when_date
        if when is not None:
            record["datetime"] = when
        out.append(record)
    return out


# Legacy alias.
load_study_csv = parse_thinkorswim_study_csv


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

    When a field is missing from ``tolerances`` the function falls back
    to :data:`DEFAULT_TOLERANCES`, then to ``default_tolerance``.
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
        if key in tolerances:
            tol = float(tolerances[key])
        elif key in DEFAULT_TOLERANCES:
            tol = float(DEFAULT_TOLERANCES[key])
        else:
            tol = float(default_tolerance)
        if abs(actual_float - float(expected_value)) > tol:
            mismatches.append(
                f"{label}: {key} expected {expected_value} ± {tol}, actual {actual_float:.4f}"
            )
    return mismatches


# ── comparison engine ───────────────────────────────────────────────────────


@dataclass
class FieldDelta:
    field: str
    expected: float
    actual: float
    abs_error: float
    tolerance: float
    within_tolerance: bool


@dataclass
class FixtureComparisonResult:
    """Result of running MacMarket Momentum against a single fixture.

    ``parity_mode`` records which fixture mode the result came from:

    - ``exported_study_csv`` — operator supplied a Thinkorswim study CSV
      (or an ``expected_latest`` block derived from one). Numeric deltas
      are validated against tolerances; the study CSV last row is used
      as an optional cross-check.
    - ``visual_observation`` — operator manually transcribed values from
      a rendered Thinkorswim chart label. The validator never auto-loads
      a study CSV in this mode; the observation is the source of truth.
    """

    fixture_name: str
    symbol: str
    timeframe: str
    parity_mode: str
    status: str
    rows_compared: int
    higher_timeframe_source: str | None
    parity_status: str | None
    derived_higher_timeframe: bool
    field_deltas: list[FieldDelta] = field(default_factory=list)
    label_mismatches: list[str] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    # Optional visual-observation metadata. Echoed into the report so
    # the audit trail records the operator + screenshot + observed bar.
    observed_bar_date: str | None = None
    screenshot: str | None = None
    macmarket_screenshot: str | None = None
    screenshot_notes: str | None = None
    reviewer: str | None = None
    reviewed_at: str | None = None
    # ── visual_attestation price + composite diagnostics ────────────
    # Operator-entered OHLC blocks (when supplied).
    tos_observed_price: dict[str, float] = field(default_factory=dict)
    macmarket_observed_price: dict[str, float] = field(default_factory=dict)
    # Close-price comparison. ``price_close_delta`` is the absolute
    # difference; ``price_close_tolerance`` is the tolerance used.
    price_close_delta: float | None = None
    price_close_tolerance: float | None = None
    # MacMarket composite-component sum (when all components present)
    # alongside the ToS total_score reading. ``mm_total_score_minus_sum``
    # captures the bookkeeping difference between MM's reported
    # ``total_score`` and its component sum (should be ~0 unless the
    # operator misread one component or an intraday penalty applies).
    mm_component_sum: float | None = None
    tos_total_score: float | None = None
    mm_total_score: float | None = None
    composite_score_attribution: dict[str, Any] = field(default_factory=dict)
    # Diagnostic surfaces operators can read at a glance.
    # ``diagnostic_flags`` is the boolean matrix
    # (oscillator_passed / composite_score_failed / price_context_mismatch
    # / label_mismatch / reference_only_hilo_scalar_present).
    # ``diagnostic_classification`` is the human-friendly bucket list
    # (oscillator_aligned / composite_mismatch / bar_context_mismatch /
    # label_mismatch_only).
    diagnostic_flags: dict[str, bool] = field(default_factory=dict)
    diagnostic_classification: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def is_visual(self) -> bool:
        return self.parity_mode == "visual_observation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_name": self.fixture_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "parity_mode": self.parity_mode,
            "status": self.status,
            "rows_compared": self.rows_compared,
            "higher_timeframe_source": self.higher_timeframe_source,
            "parity_status": self.parity_status,
            "derived_higher_timeframe": self.derived_higher_timeframe,
            "field_deltas": [
                {
                    "field": delta.field,
                    "expected": delta.expected,
                    "actual": delta.actual,
                    "abs_error": delta.abs_error,
                    "tolerance": delta.tolerance,
                    "within_tolerance": delta.within_tolerance,
                }
                for delta in self.field_deltas
            ],
            "label_mismatches": list(self.label_mismatches),
            "mismatches": list(self.mismatches),
            "reason_codes": list(self.reason_codes),
            "diagnostics": dict(self.diagnostics),
            "observed_bar_date": self.observed_bar_date,
            "screenshot": self.screenshot,
            "macmarket_screenshot": self.macmarket_screenshot,
            "screenshot_notes": self.screenshot_notes,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at,
            "tos_observed_price": dict(self.tos_observed_price),
            "macmarket_observed_price": dict(self.macmarket_observed_price),
            "price_close_delta": self.price_close_delta,
            "price_close_tolerance": self.price_close_tolerance,
            "mm_component_sum": self.mm_component_sum,
            "mm_total_score": self.mm_total_score,
            "tos_total_score": self.tos_total_score,
            "composite_score_attribution": dict(self.composite_score_attribution),
            "diagnostic_flags": dict(self.diagnostic_flags),
            "diagnostic_classification": list(self.diagnostic_classification),
        }


def compare_momentum_to_thinkorswim(
    fixture: ParityFixtureSpec,
    *,
    bars: Sequence[Bar] | None = None,
    study_rows: Sequence[Mapping[str, Any]] | None = None,
    higher_timeframe_bars: Sequence[Bar] | None = None,
) -> FixtureComparisonResult:
    """Run MacMarket Momentum against a fixture and produce a parity result.

    Parameters
    ----------
    fixture:
        Validated :class:`ParityFixtureSpec` from the manifest.
    bars / study_rows / higher_timeframe_bars:
        Optional pre-loaded inputs (used by the tests). When omitted
        the function loads the fixture's CSVs from disk.

    The function never approves, sizes, routes, opens, closes, or
    settles trades. It only computes the deterministic Momentum
    payload and reports whether it agrees with the operator-supplied
    Thinkorswim values within tolerance.

    Three modes are supported:

    - ``exported_study_csv`` — the operator dropped a Thinkorswim study
      CSV. The validator parses the CSV's last row and cross-checks it
      against the manifest's ``expected_latest`` block.
    - ``visual_observation`` — the operator manually transcribed
      Thinkorswim's rendered chart labels into the manifest's
      ``observed_latest``/``expected_latest`` block. The validator never
      auto-loads a study CSV in this mode (Thinkorswim does not export
      the Momentum study rows) and surfaces explicit reason codes
      labelling the comparison basis as visual/manual.
    - ``visual_attestation`` — the operator manually transcribed both
      Thinkorswim AND MacMarket rendered chart labels. No bars / study
      CSV is required (Thinkorswim cannot export usable bars for this
      workflow). The validator compares ``tos_observed_latest`` against
      ``macmarket_observed_latest`` directly. Status values are
      ``visual_attested`` / ``visual_failed`` / ``visual_partial``.
    """
    visual_metadata = _visual_metadata_for_result(fixture)

    if fixture.is_visual_attestation:
        return _compare_visual_attestation(fixture, visual_metadata)

    if fixture.is_visual and not fixture.expected_latest and not fixture.expected_labels:
        return FixtureComparisonResult(
            fixture_name=fixture.name,
            symbol=fixture.symbol,
            timeframe=fixture.timeframe,
            parity_mode=fixture.parity_mode,
            status="skipped_missing_observation",
            rows_compared=0,
            higher_timeframe_source=None,
            parity_status=None,
            derived_higher_timeframe=False,
            reason_codes=[
                "thinkorswim_visual_observation_missing",
                "thinkorswim_parity_pending",
            ],
            diagnostics={
                "mode": "visual_observation",
                "source": "operator-read Thinkorswim rendered chart labels",
                "note": "no observed values recorded yet",
            },
            **visual_metadata,
        )

    if bars is None:
        try:
            bars = parse_thinkorswim_bars_csv(fixture.bars_csv)
        except ParityFixtureError as exc:
            return FixtureComparisonResult(
                fixture_name=fixture.name,
                symbol=fixture.symbol,
                timeframe=fixture.timeframe,
                parity_mode=fixture.parity_mode,
                status="skipped_missing_data",
                rows_compared=0,
                higher_timeframe_source=None,
                parity_status=None,
                derived_higher_timeframe=False,
                reason_codes=["thinkorswim_fixture_files_missing"],
                diagnostics={"error": str(exc)},
                **visual_metadata,
            )

    htf_bars = higher_timeframe_bars
    if htf_bars is None and fixture.higher_timeframe_bars_csv is not None:
        try:
            htf_bars = parse_thinkorswim_bars_csv(fixture.higher_timeframe_bars_csv)
        except ParityFixtureError as exc:
            return FixtureComparisonResult(
                fixture_name=fixture.name,
                symbol=fixture.symbol,
                timeframe=fixture.timeframe,
                parity_mode=fixture.parity_mode,
                status="skipped_missing_data",
                rows_compared=0,
                higher_timeframe_source=None,
                parity_status=None,
                derived_higher_timeframe=False,
                reason_codes=["thinkorswim_fixture_files_missing"],
                diagnostics={"error": str(exc)},
                **visual_metadata,
            )

    if not bars:
        return FixtureComparisonResult(
            fixture_name=fixture.name,
            symbol=fixture.symbol,
            timeframe=fixture.timeframe,
            parity_mode=fixture.parity_mode,
            status="skipped_not_enough_history",
            rows_compared=0,
            higher_timeframe_source=None,
            parity_status=None,
            derived_higher_timeframe=False,
            reason_codes=["thinkorswim_fixture_validation_failed"],
            diagnostics={"error": "bars CSV produced zero rows"},
            **visual_metadata,
        )

    # Lazy import to keep the module light when called purely for status.
    from macmarket_trader.charts.momentum_service import MomentumChartService

    service = MomentumChartService()
    payload = service.build_payload(
        symbol=fixture.symbol,
        timeframe=fixture.timeframe,
        bars=list(bars),
        higher_timeframe_bars=list(htf_bars) if htf_bars else None,
    )

    snapshot = payload.latest_snapshot
    if snapshot is None:
        return FixtureComparisonResult(
            fixture_name=fixture.name,
            symbol=fixture.symbol,
            timeframe=fixture.timeframe,
            parity_mode=fixture.parity_mode,
            status="skipped_not_enough_history",
            rows_compared=0,
            higher_timeframe_source=payload.higher_timeframe_source,
            parity_status=payload.parity_status,
            derived_higher_timeframe=payload.higher_timeframe_source != "provided_higher_timeframe_bars",
            reason_codes=["thinkorswim_fixture_validation_failed"],
            diagnostics={"error": "payload.latest_snapshot is None"},
            **visual_metadata,
        )

    actual: dict[str, float] = {
        "total_score": float(snapshot.total_score),
        "true_momentum": float(snapshot.true_momentum),
        "true_momentum_ema": float(snapshot.true_momentum_ema),
        "hilo_thrust": float(snapshot.hilo_thrust),
        "hilo_output": float(snapshot.hilo_score),
        "trend_score": float(snapshot.trend_score),
        "momo_score": float(snapshot.momo_score),
    }

    # Source SlowD / SlowD_X from the visual parity snapshot when
    # available (same surface the chart frontend uses). MacMarket does
    # not currently compute a ToS-comparable ST_HiLoElite scalar, so
    # ``tos_hilo_elite_scalar`` is intentionally absent from ``actual``
    # and handled below as reference-only.
    parity_snapshot = payload.visual_parity_snapshot
    if parity_snapshot is not None:
        if parity_snapshot.hilo_slowd is not None:
            actual["hilo_slowd"] = float(parity_snapshot.hilo_slowd)
        if parity_snapshot.hilo_slowd_x is not None:
            actual["hilo_slowd_x"] = float(parity_snapshot.hilo_slowd_x)

    diagnostics: dict[str, Any] = {
        "bars_loaded": len(list(bars)),
        "comparison_window_requested": fixture.comparison_window,
        "mode": fixture.parity_mode,
    }
    if fixture.is_visual:
        diagnostics["source"] = "operator-read Thinkorswim rendered chart labels"
        diagnostics["parity_basis"] = (
            "manual visual parity — Thinkorswim does not export the Momentum study rows"
        )

    # Align to observed_bar_date when provided. We always compare the
    # latest snapshot; an aligned bar that does not match the operator's
    # observed bar surfaces as a diagnostic so the operator can re-slice
    # the bars CSV. We never silently switch which bar we evaluate.
    bars_sorted = sorted(bars, key=lambda b: b.date)
    latest_bar_date = bars_sorted[-1].date if bars_sorted else None
    if fixture.observed_bar_date is not None and latest_bar_date is not None:
        diagnostics["observed_bar_date"] = fixture.observed_bar_date.isoformat()
        diagnostics["latest_bar_date"] = latest_bar_date.isoformat()
        if latest_bar_date != fixture.observed_bar_date:
            diagnostics["observed_bar_date_alignment"] = (
                "observed_bar_date does not match the bars CSV last row — "
                "re-slice the bars CSV so the last row matches the visually "
                "observed Thinkorswim bar"
            )

    deltas: list[FieldDelta] = []
    mismatches: list[str] = []
    reference_only_observations: dict[str, float] = {}
    for key, expected_value in fixture.expected_latest.items():
        # Reference-only fields (e.g. ``tos_hilo_elite_scalar``) are
        # recorded into diagnostics for the audit trail but never
        # asserted against a MacMarket equivalent because MacMarket does
        # not currently compute one. This preserves the operator's
        # visual reading without fabricating a MacMarket value.
        if key in _REFERENCE_ONLY_FIELDS:
            reference_only_observations[key] = float(expected_value)
            continue
        if key not in actual:
            mismatches.append(
                f"{fixture.name}: MacMarket payload missing field {key!r}"
            )
            continue
        actual_value = actual[key]
        tol = resolve_tolerance(fixture.tolerances, key)
        abs_error = abs(actual_value - float(expected_value))
        within = abs_error <= tol
        deltas.append(
            FieldDelta(
                field=key,
                expected=float(expected_value),
                actual=actual_value,
                abs_error=abs_error,
                tolerance=tol,
                within_tolerance=within,
            )
        )
        if not within:
            mismatches.append(
                f"{fixture.name} payload: {key} expected {expected_value} ± {tol}, "
                f"actual {actual_value:.4f} (Δ={abs_error:.4f})"
            )
    if reference_only_observations:
        diagnostics["reference_only_observations"] = reference_only_observations
        diagnostics["reference_only_note"] = (
            "tos_hilo_elite_scalar is recorded for operator review but not "
            "auto-compared because MacMarket does not currently compute a "
            "ToS-comparable ST_HiLoElite scalar"
        )

    label_mismatches: list[str] = []
    if fixture.expected_labels:
        snapshot_label = getattr(snapshot, "total_label", None)
        snapshot_flags = {
            "total_label": snapshot_label,
            "pullback_signal": bool(getattr(snapshot, "pullback_signal", False)),
            "reversal_warning": bool(getattr(snapshot, "reversal_warning", False)),
            "no_trade_warning": bool(getattr(snapshot, "no_trade_warning", False)),
        }
        for key, expected_label in fixture.expected_labels.items():
            actual_label = snapshot_flags.get(key)
            actual_norm = str(actual_label).strip().lower() if actual_label is not None else ""
            expected_norm = expected_label.strip().lower()
            if actual_norm != expected_norm:
                msg = (
                    f"{fixture.name} payload: {key} expected {expected_label!r}, "
                    f"actual {actual_label!r}"
                )
                label_mismatches.append(msg)
                if fixture.label_must_match:
                    mismatches.append(msg)

    # Optional cross-check against the operator's study CSV last row.
    # Only honored in ``exported_study_csv`` mode. Visual observations
    # do not consult a study CSV because Thinkorswim does not export the
    # Momentum study output.
    study_rows_loaded: list[Mapping[str, Any]] = list(study_rows) if study_rows is not None else []
    if (
        fixture.is_exported_study_csv
        and not study_rows_loaded
        and fixture.study_csv is not None
        and fixture.study_csv.exists()
    ):
        try:
            study_rows_loaded = parse_thinkorswim_study_csv(fixture.study_csv)
        except ParityFixtureError as exc:
            mismatches.append(f"{fixture.name} study CSV: {exc}")

    if fixture.is_exported_study_csv and study_rows_loaded:
        latest = latest_study_row(study_rows_loaded)
        study_subset = {
            key: float(value)
            for key, value in latest.items()
            if key in STUDY_FIELDS and value is not None and key in fixture.expected_latest
        }
        if study_subset:
            mismatches.extend(
                compare_with_tolerance(
                    {k: fixture.expected_latest[k] for k in study_subset},
                    study_subset,
                    fixture.tolerances,
                    label=f"{fixture.name} study CSV",
                )
            )

    derived_htf = payload.higher_timeframe_source != "provided_higher_timeframe_bars"

    rows_compared = max(1, fixture.comparison_window)
    status = "passed" if not mismatches else "failed"
    reason_codes: list[str]
    if status == "passed":
        reason_codes = ["thinkorswim_parity_passed"]
        if fixture.is_visual:
            reason_codes.append("thinkorswim_visual_parity_passed")
    else:
        reason_codes = ["thinkorswim_parity_failed"]
        if fixture.is_visual:
            reason_codes.append("thinkorswim_visual_parity_failed")

    # Recommended-field reason codes for visual mode (advisory only —
    # they never flip the status to failed).
    if fixture.is_visual:
        provided_fields = set(fixture.expected_latest) | set(fixture.expected_labels)
        for recommended in RECOMMENDED_VISUAL_FIELDS:
            if recommended not in provided_fields:
                code = f"thinkorswim_visual_observation_missing_{recommended}"
                if code not in reason_codes:
                    reason_codes.append(code)
        # "At least one HiLo field" recommendation.
        if not (provided_fields & set(RECOMMENDED_HILO_VISUAL_FIELDS)):
            code = "thinkorswim_visual_observation_missing_hilo_field"
            if code not in reason_codes:
                reason_codes.append(code)

    diagnostics["study_rows_loaded"] = len(study_rows_loaded)
    if fixture.notes:
        diagnostics["notes"] = fixture.notes
    if derived_htf and fixture.timeframe == "1W":
        diagnostics["caveat"] = (
            "higher timeframe was derived from daily bars rather than supplied as a "
            "separate weekly Thinkorswim export"
        )

    return FixtureComparisonResult(
        fixture_name=fixture.name,
        symbol=fixture.symbol,
        timeframe=fixture.timeframe,
        parity_mode=fixture.parity_mode,
        status=status,
        rows_compared=rows_compared,
        higher_timeframe_source=payload.higher_timeframe_source,
        parity_status=payload.parity_status,
        derived_higher_timeframe=derived_htf,
        field_deltas=deltas,
        label_mismatches=label_mismatches,
        mismatches=mismatches,
        reason_codes=reason_codes,
        diagnostics=diagnostics,
        **visual_metadata,
    )


def _visual_metadata_for_result(fixture: ParityFixtureSpec) -> dict[str, Any]:
    """Return the visual-observation metadata kwargs for a result.

    Always returns string-or-None values so the dict can be unpacked
    into :class:`FixtureComparisonResult` regardless of mode.
    """
    return {
        "observed_bar_date": (
            fixture.observed_bar_date.isoformat() if fixture.observed_bar_date else None
        ),
        "screenshot": fixture.screenshot,
        "macmarket_screenshot": fixture.macmarket_screenshot,
        "screenshot_notes": fixture.screenshot_notes,
        "reviewer": fixture.reviewer,
        "reviewed_at": (
            fixture.reviewed_at.isoformat() if fixture.reviewed_at else None
        ),
    }


# ── visual_attestation comparison ──────────────────────────────────────────


def _resolve_visual_attestation_tolerance(
    tolerances: Mapping[str, float],
    field: str,
) -> float:
    """Return the per-field tolerance for visual_attestation.

    Operator-supplied ``tolerances`` win; otherwise the wider
    visual-attestation defaults apply (because eye-read precision is
    coarser than CSV-derived precision).
    """
    if field in tolerances:
        return float(tolerances[field])
    if field in DEFAULT_VISUAL_ATTESTATION_TOLERANCES:
        return float(DEFAULT_VISUAL_ATTESTATION_TOLERANCES[field])
    if field in DEFAULT_TOLERANCES:
        return float(DEFAULT_TOLERANCES[field])
    return 1.0


def _compare_visual_attestation(
    fixture: ParityFixtureSpec,
    visual_metadata: dict[str, Any],
) -> FixtureComparisonResult:
    """Compare operator-entered ToS readings against operator-entered
    MacMarket readings — no bars, no study CSV, no MacMarket computation.

    Result statuses:

    - ``visual_attested`` — every field present in both observations is
      within tolerance and label rules pass.
    - ``visual_failed`` — at least one numeric mismatch or, when
      ``label_must_match`` is true, a label mismatch.
    - ``visual_partial`` — observations exist but no field is present in
      both sides (nothing to compare). Strict CLI treats this as
      non-pass.
    - ``skipped_missing_observation`` — one or both observation maps are
      empty.

    The function never approves, sizes, routes, opens, closes, or
    settles trades.
    """
    diagnostics: dict[str, Any] = {
        "mode": "visual_attestation",
        "source": "operator-read Thinkorswim and MacMarket rendered chart labels",
        "parity_basis": (
            "manual visual attestation — both ToS and MacMarket values are "
            "operator-entered from rendered charts"
        ),
    }
    if fixture.observed_bar_date is not None:
        diagnostics["observed_bar_date"] = fixture.observed_bar_date.isoformat()

    has_tos = bool(fixture.tos_observed_latest or fixture.tos_observed_labels)
    has_mm = bool(
        fixture.macmarket_observed_latest or fixture.macmarket_observed_labels
    )
    if not has_tos or not has_mm:
        return FixtureComparisonResult(
            fixture_name=fixture.name,
            symbol=fixture.symbol,
            timeframe=fixture.timeframe,
            parity_mode=fixture.parity_mode,
            status="skipped_missing_observation",
            rows_compared=0,
            higher_timeframe_source=None,
            parity_status=None,
            derived_higher_timeframe=False,
            reason_codes=[
                "thinkorswim_visual_attestation_missing_observation",
                "thinkorswim_parity_pending",
            ],
            diagnostics={
                **diagnostics,
                "note": (
                    "tos_observed_latest and macmarket_observed_latest are "
                    "both required to compare visual attestation"
                ),
            },
            **visual_metadata,
        )

    # Numeric field comparison — only compare fields present on BOTH
    # sides. Missing fields are recorded as skipped (advisory).
    tos_numeric = dict(fixture.tos_observed_latest)
    mm_numeric = dict(fixture.macmarket_observed_latest)
    common_numeric_fields = sorted(set(tos_numeric) & set(mm_numeric))
    skipped_fields: list[str] = []
    deltas: list[FieldDelta] = []
    mismatches: list[str] = []
    reference_only_observations: dict[str, dict[str, float]] = {}

    for field_name in set(tos_numeric) | set(mm_numeric):
        if field_name in common_numeric_fields:
            continue
        # tos_hilo_elite_scalar declared only on the ToS side is a
        # reference-only observation — there is no MM equivalent to
        # compare against (MacMarket does not compute it). Record it
        # in diagnostics so the audit trail preserves the reading.
        if field_name == "tos_hilo_elite_scalar" and field_name in tos_numeric:
            reference_only_observations.setdefault("tos_only", {})[field_name] = (
                float(tos_numeric[field_name])
            )
        else:
            skipped_fields.append(field_name)

    for field_name in common_numeric_fields:
        tos_value = float(tos_numeric[field_name])
        mm_value = float(mm_numeric[field_name])
        tol = _resolve_visual_attestation_tolerance(fixture.tolerances, field_name)
        abs_error = abs(tos_value - mm_value)
        within = abs_error <= tol
        deltas.append(
            FieldDelta(
                field=field_name,
                expected=tos_value,
                actual=mm_value,
                abs_error=abs_error,
                tolerance=tol,
                within_tolerance=within,
            )
        )
        if not within:
            mismatches.append(
                f"{fixture.name} attestation: {field_name} ToS {tos_value} vs "
                f"MM {mm_value:.4f} differ by {abs_error:.4f} (tol {tol})"
            )

    # Label field comparison.
    label_mismatches: list[str] = []
    tos_labels = dict(fixture.tos_observed_labels)
    mm_labels = dict(fixture.macmarket_observed_labels)
    common_label_fields = sorted(set(tos_labels) & set(mm_labels))
    for field_name in set(tos_labels) | set(mm_labels):
        if field_name not in common_label_fields:
            skipped_fields.append(field_name)
    for field_name in common_label_fields:
        tos_value = tos_labels[field_name]
        mm_value = mm_labels[field_name]
        tos_norm = str(tos_value).strip().lower()
        mm_norm = str(mm_value).strip().lower()
        if tos_norm == mm_norm:
            continue
        msg = (
            f"{fixture.name} attestation: {field_name} ToS {tos_value!r} vs "
            f"MM {mm_value!r}"
        )
        label_mismatches.append(msg)
        if fixture.label_must_match:
            mismatches.append(msg)

    # No comparable fields at all → visual_partial.
    if not common_numeric_fields and not common_label_fields:
        reason_codes = [
            "thinkorswim_visual_attestation_no_comparable_fields",
            "thinkorswim_parity_pending",
        ]
        if reference_only_observations:
            diagnostics["reference_only_observations"] = reference_only_observations
            diagnostics["reference_only_note"] = (
                "tos_hilo_elite_scalar recorded for operator review; no "
                "comparable MacMarket field was provided"
            )
        if skipped_fields:
            diagnostics["skipped_fields"] = sorted(set(skipped_fields))
        return FixtureComparisonResult(
            fixture_name=fixture.name,
            symbol=fixture.symbol,
            timeframe=fixture.timeframe,
            parity_mode=fixture.parity_mode,
            status="visual_partial",
            rows_compared=0,
            higher_timeframe_source=None,
            parity_status=None,
            derived_higher_timeframe=False,
            field_deltas=deltas,
            label_mismatches=label_mismatches,
            mismatches=mismatches,
            reason_codes=reason_codes,
            diagnostics=diagnostics,
            **visual_metadata,
        )

    status = "visual_attested" if not mismatches else "visual_failed"
    reason_codes: list[str] = []
    if status == "visual_attested":
        reason_codes.append("thinkorswim_visual_attested")
    else:
        reason_codes.append("thinkorswim_visual_attestation_failed")

    # Recommended-field advisory codes (don't flip status).
    provided_fields = set(common_numeric_fields) | set(common_label_fields)
    for recommended in RECOMMENDED_VISUAL_FIELDS:
        if recommended not in provided_fields:
            code = f"thinkorswim_visual_attestation_missing_{recommended}"
            if code not in reason_codes:
                reason_codes.append(code)
    if not (provided_fields & set(RECOMMENDED_HILO_VISUAL_FIELDS)):
        code = "thinkorswim_visual_attestation_missing_hilo_field"
        if code not in reason_codes:
            reason_codes.append(code)

    if reference_only_observations:
        diagnostics["reference_only_observations"] = reference_only_observations
        diagnostics["reference_only_note"] = (
            "tos_hilo_elite_scalar present on the ToS side only — "
            "recorded for audit, not compared (MacMarket has no "
            "equivalent unless the MM side declares the same field)"
        )
    if skipped_fields:
        diagnostics["skipped_fields"] = sorted(set(skipped_fields))
    diagnostics["fields_compared"] = sorted(
        set(common_numeric_fields) | set(common_label_fields)
    )

    # ── Price context + composite attribution diagnostics ───────────
    tos_price = dict(fixture.tos_observed_price)
    mm_price = dict(fixture.macmarket_observed_price)
    price_close_delta: float | None = None
    price_close_tolerance: float | None = None
    price_context_mismatch = False
    if "close" in tos_price and "close" in mm_price:
        price_close_tolerance = float(
            fixture.tolerances.get("close", DEFAULT_PRICE_CLOSE_TOLERANCE)
        )
        price_close_delta = abs(float(tos_price["close"]) - float(mm_price["close"]))
        if price_close_delta > price_close_tolerance:
            price_context_mismatch = True
            reason_codes.append("visual_attestation_price_context_mismatch")

    # MacMarket component sum (when every component is present on the
    # MM side). ToS top-level total_score is recorded as-is; the
    # validator does NOT assume ToS's component formula.
    mm_components_present = all(
        component in mm_numeric for component in MM_COMPOSITE_COMPONENT_FIELDS
    )
    mm_component_sum: float | None = None
    if mm_components_present:
        mm_component_sum = float(
            sum(mm_numeric[component] for component in MM_COMPOSITE_COMPONENT_FIELDS)
        )

    mm_total_score = (
        float(mm_numeric["total_score"]) if "total_score" in mm_numeric else None
    )
    tos_total_score = (
        float(tos_numeric["total_score"]) if "total_score" in tos_numeric else None
    )

    composite_attribution: dict[str, Any] = {}
    if mm_components_present:
        composite_attribution["mm_components"] = {
            component: float(mm_numeric[component])
            for component in MM_COMPOSITE_COMPONENT_FIELDS
        }
        composite_attribution["mm_component_sum"] = mm_component_sum
    elif "macmarket_observed_latest" in fixture.raw:
        composite_attribution["mm_components"] = "not observed"
    if tos_total_score is not None:
        composite_attribution["tos_total_score"] = tos_total_score
    else:
        composite_attribution["tos_total_score"] = "not observed"
    if mm_total_score is not None:
        composite_attribution["mm_total_score"] = mm_total_score
    if (
        mm_component_sum is not None
        and mm_total_score is not None
    ):
        composite_attribution["mm_total_score_minus_component_sum"] = (
            mm_total_score - mm_component_sum
        )
    if (
        mm_component_sum is not None
        and tos_total_score is not None
    ):
        composite_attribution["tos_total_score_minus_mm_component_sum"] = (
            tos_total_score - mm_component_sum
        )

    # Diagnostic flags + classification — operator-readable summary of
    # why a visual_attestation comparison succeeded or failed.
    oscillator_fields = {"true_momentum", "true_momentum_ema"}
    oscillator_deltas = [d for d in deltas if d.field in oscillator_fields]
    oscillator_compared = bool(oscillator_deltas)
    oscillator_within_tol = oscillator_compared and all(
        d.within_tolerance for d in oscillator_deltas
    )
    oscillator_failed_flag = oscillator_compared and not oscillator_within_tol
    total_score_delta = next(
        (d for d in deltas if d.field == "total_score"), None
    )
    composite_score_failed = bool(
        total_score_delta is not None
        and not total_score_delta.within_tolerance
    )
    label_mismatch_flag = bool(label_mismatches)
    reference_only_hilo_scalar_present = "tos_only" in reference_only_observations

    diagnostic_flags: dict[str, bool] = {
        # ``oscillator_aligned`` is True only when both oscillator
        # fields (true_momentum + true_momentum_ema) were compared and
        # both fell inside tolerance. ``oscillator_failed`` is True when
        # the oscillator fields were compared and at least one failed
        # — kept as a separate flag so callers don't have to read False
        # as "compared but failed" vs "not compared at all".
        "oscillator_aligned": oscillator_within_tol,
        "oscillator_failed": oscillator_failed_flag,
        "composite_score_failed": composite_score_failed,
        "price_context_mismatch": price_context_mismatch,
        "label_mismatch": label_mismatch_flag,
        "reference_only_hilo_scalar_present": reference_only_hilo_scalar_present,
    }

    classification: list[str] = []
    if oscillator_within_tol:
        classification.append("oscillator_aligned")
    if oscillator_failed_flag:
        classification.append("oscillator_mismatch")
    if composite_score_failed:
        classification.append("composite_mismatch")
    if price_context_mismatch:
        classification.append("bar_context_mismatch")
    if (
        label_mismatch_flag
        and not composite_score_failed
        and oscillator_within_tol
        and not fixture.label_must_match
    ):
        classification.append("label_mismatch_only")

    diagnostics["diagnostic_flags"] = diagnostic_flags
    diagnostics["diagnostic_classification"] = classification
    diagnostics["composite_score_attribution"] = composite_attribution
    if tos_price or mm_price:
        diagnostics["price_context"] = {
            "tos_observed_price": tos_price,
            "macmarket_observed_price": mm_price,
            "close_delta": price_close_delta,
            "close_tolerance": price_close_tolerance,
            "strict_price_context": fixture.strict_price_context,
        }
    if oscillator_within_tol and composite_score_failed:
        diagnostics["composite_mismatch_note"] = (
            "Oscillator fields passed, but total score differs. Review "
            "composite component weights, MA bias inclusion, or observed "
            "score source."
        )

    # Strict price context: when set on the fixture and the close
    # prices differ beyond tolerance, the result flips to visual_failed
    # even if every other field passed. Default behavior keeps the
    # warning surfaced via reason_codes / classification only.
    if (
        price_context_mismatch
        and fixture.strict_price_context
        and status == "visual_attested"
    ):
        status = "visual_failed"
        if "thinkorswim_visual_attested" in reason_codes:
            reason_codes.remove("thinkorswim_visual_attested")
        if "thinkorswim_visual_attestation_failed" not in reason_codes:
            reason_codes.append("thinkorswim_visual_attestation_failed")
        mismatches.append(
            f"{fixture.name} attestation: close ToS "
            f"{tos_price.get('close')} vs MM {mm_price.get('close')} "
            f"differ by {price_close_delta} (tol {price_close_tolerance}) "
            "and strict_price_context is set"
        )

    return FixtureComparisonResult(
        fixture_name=fixture.name,
        symbol=fixture.symbol,
        timeframe=fixture.timeframe,
        parity_mode=fixture.parity_mode,
        status=status,
        rows_compared=1,
        higher_timeframe_source=None,
        parity_status=None,
        derived_higher_timeframe=False,
        field_deltas=deltas,
        label_mismatches=label_mismatches,
        mismatches=mismatches,
        reason_codes=reason_codes,
        diagnostics=diagnostics,
        tos_observed_price=tos_price,
        macmarket_observed_price=mm_price,
        price_close_delta=price_close_delta,
        price_close_tolerance=price_close_tolerance,
        mm_component_sum=mm_component_sum,
        mm_total_score=mm_total_score,
        tos_total_score=tos_total_score,
        composite_score_attribution=composite_attribution,
        diagnostic_flags=diagnostic_flags,
        diagnostic_classification=classification,
        **visual_metadata,
    )


# ── folder validation ──────────────────────────────────────────────────────


@dataclass
class FixtureReadiness:
    fixture_name: str
    symbol: str
    timeframe: str
    bars_present: bool
    study_present: bool
    higher_timeframe_bars_present: bool | None
    ready: bool
    missing_files: list[str] = field(default_factory=list)


@dataclass
class FixtureFolderValidation:
    fixture_dir: Path
    manifest_present: bool
    manifest_valid: bool
    fixtures_total: int
    fixtures_ready: int
    errors: list[str]
    fixtures: list[FixtureReadiness]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_dir": str(self.fixture_dir),
            "manifest_present": self.manifest_present,
            "manifest_valid": self.manifest_valid,
            "fixtures_total": self.fixtures_total,
            "fixtures_ready": self.fixtures_ready,
            "errors": list(self.errors),
            "fixtures": [
                {
                    "fixture_name": f.fixture_name,
                    "symbol": f.symbol,
                    "timeframe": f.timeframe,
                    "bars_present": f.bars_present,
                    "study_present": f.study_present,
                    "higher_timeframe_bars_present": f.higher_timeframe_bars_present,
                    "ready": f.ready,
                    "missing_files": list(f.missing_files),
                }
                for f in self.fixtures
            ],
        }


def validate_thinkorswim_fixture_folder(fixture_dir: Path) -> FixtureFolderValidation:
    """Inspect ``fixture_dir`` without running any indicator math.

    Returns a structured :class:`FixtureFolderValidation` describing
    whether ``manifest.json`` is present and valid, plus per-fixture
    file-readiness for the bars / study / higher-timeframe CSVs.
    Errors are collected, never raised.
    """
    fixture_dir = Path(fixture_dir)
    manifest_path = fixture_dir / "manifest.json"
    errors: list[str] = []
    fixtures_readiness: list[FixtureReadiness] = []
    fixtures_total = 0
    fixtures_ready = 0

    if not manifest_path.exists():
        return FixtureFolderValidation(
            fixture_dir=fixture_dir,
            manifest_present=False,
            manifest_valid=False,
            fixtures_total=0,
            fixtures_ready=0,
            errors=[],
            fixtures=[],
        )

    try:
        manifest = load_thinkorswim_manifest(manifest_path)
    except ParityFixtureError as exc:
        return FixtureFolderValidation(
            fixture_dir=fixture_dir,
            manifest_present=True,
            manifest_valid=False,
            fixtures_total=0,
            fixtures_ready=0,
            errors=[str(exc)],
            fixtures=[],
        )

    fixtures_total = len(manifest.fixtures)
    for spec in manifest.fixtures:
        # visual_attestation fixtures never need bars / study CSVs — the
        # operator-entered ToS vs MM observation pair is the source of
        # truth. They are always "ready" once the manifest validates.
        if spec.is_visual_attestation:
            fixtures_ready += 1
            fixtures_readiness.append(
                FixtureReadiness(
                    fixture_name=spec.name,
                    symbol=spec.symbol,
                    timeframe=spec.timeframe,
                    bars_present=False,
                    study_present=False,
                    higher_timeframe_bars_present=None,
                    ready=True,
                    missing_files=[],
                )
            )
            continue

        bars_present = spec.bars_csv.exists() if spec.bars_csv is not None else False
        study_present = spec.study_csv.exists() if spec.study_csv is not None else False
        htf_present: bool | None = None
        if spec.higher_timeframe_bars_csv is not None:
            htf_present = spec.higher_timeframe_bars_csv.exists()
        missing: list[str] = []
        if spec.bars_csv is not None and not bars_present:
            missing.append(str(spec.bars_csv.name))
        if spec.study_csv is not None and not study_present:
            missing.append(str(spec.study_csv.name))
        if spec.higher_timeframe_bars_csv is not None and not htf_present:
            missing.append(str(spec.higher_timeframe_bars_csv.name))
        ready = not missing
        if ready:
            fixtures_ready += 1
        fixtures_readiness.append(
            FixtureReadiness(
                fixture_name=spec.name,
                symbol=spec.symbol,
                timeframe=spec.timeframe,
                bars_present=bars_present,
                study_present=study_present,
                higher_timeframe_bars_present=htf_present,
                ready=ready,
                missing_files=missing,
            )
        )

    return FixtureFolderValidation(
        fixture_dir=fixture_dir,
        manifest_present=True,
        manifest_valid=True,
        fixtures_total=fixtures_total,
        fixtures_ready=fixtures_ready,
        errors=errors,
        fixtures=fixtures_readiness,
    )


# ── report generation ──────────────────────────────────────────────────────


REPORT_FILENAME_JSON = "parity-report.json"
REPORT_FILENAME_MD = "parity-report.md"
REPORT_SCHEMA_VERSION = "thinkorswim_momentum_parity_report.v1"


@dataclass
class ParityReportSummary:
    fixture_dir: Path
    generated_at: datetime
    fixtures_total: int
    fixtures_passed: int
    fixtures_failed: int
    fixtures_skipped: int
    results: list[FixtureComparisonResult]
    manifest_present: bool
    manifest_valid: bool

    @property
    def overall_status(self) -> str:
        if not self.manifest_present:
            return "missing"
        if not self.manifest_valid:
            return "missing"
        if self.fixtures_total == 0:
            return "missing"
        if self.fixtures_failed > 0:
            return "failed"
        if self.fixtures_passed == 0:
            return "ready"
        if self.fixtures_passed < self.fixtures_total:
            return "partial"
        return "passed"

    @property
    def mode_counts(self) -> dict[str, dict[str, int]]:
        """Return per-mode pass/fail/skipped/partial counts.

        ``passed`` collects ``passed`` and ``visual_attested`` so a
        callers summing ``passed`` see the canonical "all comparable
        fields agree" tally regardless of mode. ``partial`` collects
        the ``visual_partial`` status. ``skipped`` collects every
        other skipped/missing status.
        """
        counts: dict[str, dict[str, int]] = {
            mode: {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "partial": 0,
            }
            for mode in PARITY_MODES
        }
        for result in self.results:
            bucket = counts.setdefault(
                result.parity_mode,
                {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "partial": 0},
            )
            bucket["total"] += 1
            if result.status in ("passed", "visual_attested"):
                bucket["passed"] += 1
            elif result.status in ("failed", "visual_failed"):
                bucket["failed"] += 1
            elif result.status == "visual_partial":
                bucket["partial"] = bucket.get("partial", 0) + 1
            else:
                bucket["skipped"] += 1
        return counts

    @property
    def visual_observation_count(self) -> int:
        return self.mode_counts.get("visual_observation", {}).get("total", 0)

    @property
    def exported_study_csv_count(self) -> int:
        return self.mode_counts.get("exported_study_csv", {}).get("total", 0)

    @property
    def visual_observation_passed_count(self) -> int:
        return self.mode_counts.get("visual_observation", {}).get("passed", 0)

    @property
    def visual_observation_failed_count(self) -> int:
        return self.mode_counts.get("visual_observation", {}).get("failed", 0)

    @property
    def visual_reviewed(self) -> bool:
        return self.visual_observation_count > 0 or self.visual_attestation_count > 0

    # ── visual_attestation counts ────────────────────────────────────
    @property
    def visual_attestation_count(self) -> int:
        return self.mode_counts.get("visual_attestation", {}).get("total", 0)

    @property
    def visual_attestation_passed_count(self) -> int:
        return self.mode_counts.get("visual_attestation", {}).get("passed", 0)

    @property
    def visual_attestation_failed_count(self) -> int:
        return self.mode_counts.get("visual_attestation", {}).get("failed", 0)

    @property
    def visual_attestation_partial_count(self) -> int:
        return self.mode_counts.get("visual_attestation", {}).get("partial", 0)

    @property
    def visual_attestation_status(self) -> str | None:
        """Mode-level status string for the Settings card.

        - ``visual_attested`` — every visual_attestation fixture passed.
        - ``visual_failed`` — at least one fixture failed.
        - ``visual_partial`` — any fixture is partial (no comparable
          fields) but none failed.
        - ``None`` — no visual_attestation fixtures present.
        """
        if self.visual_attestation_count == 0:
            return None
        if self.visual_attestation_failed_count > 0:
            return "visual_failed"
        if self.visual_attestation_partial_count > 0:
            return "visual_partial"
        if self.visual_attestation_passed_count == self.visual_attestation_count:
            return "visual_attested"
        return "visual_partial"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "fixture_dir": str(self.fixture_dir),
            "generated_at": self.generated_at.isoformat(),
            "manifest_present": self.manifest_present,
            "manifest_valid": self.manifest_valid,
            "fixtures_total": self.fixtures_total,
            "fixtures_passed": self.fixtures_passed,
            "fixtures_failed": self.fixtures_failed,
            "fixtures_skipped": self.fixtures_skipped,
            "overall_status": self.overall_status,
            "parity_mode_counts": self.mode_counts,
            "visual_observation_count": self.visual_observation_count,
            "exported_study_csv_count": self.exported_study_csv_count,
            "visual_observation_passed_count": self.visual_observation_passed_count,
            "visual_observation_failed_count": self.visual_observation_failed_count,
            "visual_attestation_count": self.visual_attestation_count,
            "visual_attestation_passed_count": self.visual_attestation_passed_count,
            "visual_attestation_failed_count": self.visual_attestation_failed_count,
            "visual_attestation_partial_count": self.visual_attestation_partial_count,
            "visual_attestation_status": self.visual_attestation_status,
            "visual_reviewed": self.visual_reviewed,
            "results": [r.to_dict() for r in self.results],
        }


_MODE_LABEL: dict[str, str] = {
    "exported_study_csv": "exported study CSV",
    "visual_observation": "visual observation",
    "visual_attestation": "visual attestation (no bars)",
}


def _mode_label(parity_mode: str) -> str:
    return _MODE_LABEL.get(parity_mode, parity_mode)


def _render_report_markdown(summary: ParityReportSummary) -> str:
    lines: list[str] = []
    lines.append("# Thinkorswim Momentum parity report")
    lines.append("")
    lines.append(f"- Fixture directory: `{summary.fixture_dir}`")
    lines.append(f"- Generated at: `{summary.generated_at.isoformat()}`")
    lines.append(f"- Manifest present: `{summary.manifest_present}`")
    lines.append(f"- Manifest valid: `{summary.manifest_valid}`")
    lines.append(f"- Fixtures total: {summary.fixtures_total}")
    lines.append(f"- Fixtures passed: {summary.fixtures_passed}")
    lines.append(f"- Fixtures failed: {summary.fixtures_failed}")
    lines.append(f"- Fixtures skipped: {summary.fixtures_skipped}")
    lines.append(f"- Overall status: `{summary.overall_status}`")
    lines.append("")
    lines.append("## Mode summary")
    lines.append("")
    visual_counts = summary.mode_counts.get("visual_observation", {})
    attestation_counts = summary.mode_counts.get("visual_attestation", {})
    exported_counts = summary.mode_counts.get("exported_study_csv", {})
    lines.append(
        f"- visual_attestation: {attestation_counts.get('total', 0)} "
        f"({attestation_counts.get('passed', 0)} passed / "
        f"{attestation_counts.get('failed', 0)} failed / "
        f"{attestation_counts.get('partial', 0)} partial)"
    )
    lines.append(
        f"- visual_observation: {visual_counts.get('total', 0)} "
        f"({visual_counts.get('passed', 0)} passed / "
        f"{visual_counts.get('failed', 0)} failed / "
        f"{visual_counts.get('skipped', 0)} skipped)"
    )
    lines.append(
        f"- exported_study_csv: {exported_counts.get('total', 0)} "
        f"({exported_counts.get('passed', 0)} passed / "
        f"{exported_counts.get('failed', 0)} failed / "
        f"{exported_counts.get('skipped', 0)} skipped)"
    )
    lines.append("")
    lines.append(
        "_Visual attestation compares operator-entered ToS and MacMarket rendered chart "
        "values. It is not exported study-row parity._"
    )
    lines.append(
        "_Visual observations are operator-entered from rendered Thinkorswim chart labels. "
        "They are auditable but not row-level CSV exports — Thinkorswim does not export "
        "the Momentum study output._"
    )
    lines.append("")
    lines.append(
        "_This report is operator readiness context only. It does not approve, "
        "reject, size, or route trades, and a parity pass does not auto-activate "
        "Phase C strategy families._"
    )
    lines.append("")
    if not summary.results:
        lines.append("No fixture results — drop Thinkorswim CSV exports and rerun.")
        return "\n".join(lines) + "\n"

    # Fixture summary table.
    lines.append("## Fixture summary")
    lines.append("")
    lines.append("| Fixture | Symbol | Timeframe | Mode | Bar | Status |")
    lines.append("|---|---|---|---|---|---|")
    for result in summary.results:
        bar_cell = result.observed_bar_date or "—"
        lines.append(
            f"| `{result.fixture_name}` | `{result.symbol}` | `{result.timeframe}` | "
            f"`{result.parity_mode}` | `{bar_cell}` | `{result.status}` |"
        )
    lines.append("")

    for result in summary.results:
        lines.append(f"## {result.fixture_name} — `{result.status}`")
        lines.append("")
        lines.append(f"- Mode: {_mode_label(result.parity_mode)}")
        if result.parity_mode == "visual_attestation":
            lines.append(
                "- Source: operator-entered ToS and MacMarket rendered chart values"
            )
            lines.append(
                "- This is manual visual attestation, not exported study-row parity "
                "and not computed bars parity."
            )
        elif result.is_visual:
            lines.append(
                "- Source: operator-read Thinkorswim rendered chart labels"
            )
            lines.append(
                "- This is manual visual parity, not exported study-row parity."
            )
        lines.append(f"- Symbol: `{result.symbol}`")
        lines.append(f"- Timeframe: `{result.timeframe}`")
        lines.append(f"- Rows compared: {result.rows_compared}")
        lines.append(f"- Higher timeframe source: `{result.higher_timeframe_source}`")
        if result.derived_higher_timeframe and result.timeframe in {"1W"}:
            lines.append(
                "- **Caveat:** higher timeframe series was derived from daily bars "
                "rather than supplied as a separate weekly Thinkorswim export."
            )
        lines.append(f"- Parity status: `{result.parity_status}`")
        if result.observed_bar_date:
            lines.append(f"- Observed bar date: `{result.observed_bar_date}`")
        if result.reviewer:
            lines.append(f"- Reviewer: {result.reviewer}")
        if result.reviewed_at:
            lines.append(f"- Reviewed at: `{result.reviewed_at}`")
        if result.screenshot:
            lines.append(f"- Screenshot (ToS): `{result.screenshot}`")
        if result.macmarket_screenshot:
            lines.append(f"- Screenshot (MacMarket): `{result.macmarket_screenshot}`")
        if result.screenshot_notes:
            lines.append(f"- Screenshot notes: {result.screenshot_notes}")
        lines.append("")
        if result.field_deltas:
            if result.parity_mode == "visual_attestation":
                lines.append(
                    "| Field | ToS observed | MacMarket observed | abs_error | Tolerance | OK? |"
                )
            else:
                label = "Observed" if result.is_visual else "Expected"
                lines.append(
                    f"| Field | {label} | MacMarket | abs_error | Tolerance | OK? |"
                )
            lines.append("|---|---:|---:|---:|---:|:---:|")
            for delta in result.field_deltas:
                ok = "ok" if delta.within_tolerance else "MISS"
                lines.append(
                    f"| `{delta.field}` | {delta.expected} | {delta.actual:.4f} | "
                    f"{delta.abs_error:.4f} | {delta.tolerance} | {ok} |"
                )
            lines.append("")
        if result.label_mismatches:
            lines.append("Label / flag mismatches:")
            for msg in result.label_mismatches:
                lines.append(f"- {msg}")
            lines.append("")
        if result.mismatches:
            lines.append("Numeric mismatches:")
            for msg in result.mismatches:
                lines.append(f"- {msg}")
            lines.append("")
        if result.parity_mode == "visual_attestation":
            lines.extend(_render_visual_attestation_attribution(result))
        if result.diagnostics:
            lines.append("Diagnostics:")
            for k, v in result.diagnostics.items():
                lines.append(f"- `{k}`: {v}")
            lines.append("")
    return "\n".join(lines) + "\n"


def _render_visual_attestation_attribution(
    result: FixtureComparisonResult,
) -> list[str]:
    """Render the visual_attestation Composite score attribution
    section (Markdown). Always returns a list of lines suitable to
    extend the report builder's output — possibly empty when neither
    price context nor composite components were captured.
    """
    has_price = bool(result.tos_observed_price or result.macmarket_observed_price)
    has_components = bool(
        result.composite_score_attribution
        or result.mm_component_sum is not None
        or result.tos_total_score is not None
    )
    if not has_price and not has_components and not result.diagnostic_flags:
        return []
    lines: list[str] = ["### Composite score attribution"]
    lines.append("")
    if has_price:
        tos = result.tos_observed_price or {}
        mm = result.macmarket_observed_price or {}
        lines.append("Price context:")
        lines.append("")
        lines.append("| Field | ToS observed | MacMarket observed |")
        lines.append("|---|---:|---:|")
        for ohlc in ("open", "high", "low", "close"):
            if ohlc in tos or ohlc in mm:
                tos_v = f"{tos[ohlc]:.4f}" if ohlc in tos else "—"
                mm_v = f"{mm[ohlc]:.4f}" if ohlc in mm else "—"
                lines.append(f"| `{ohlc}` | {tos_v} | {mm_v} |")
        if result.price_close_delta is not None:
            lines.append(
                f"| `close_delta` | {result.price_close_delta:.4f} | "
                f"tolerance {result.price_close_tolerance} |"
            )
        lines.append("")
        if result.diagnostic_flags.get("price_context_mismatch"):
            lines.append(
                "_Price context mismatch: ToS close and MacMarket close differ by "
                "more than the configured tolerance. Parity may not be "
                "apples-to-apples until the same bar/price is captured._"
            )
            lines.append("")

    if has_components:
        attr = result.composite_score_attribution or {}
        components = attr.get("mm_components")
        if isinstance(components, dict):
            lines.append("MacMarket composite components:")
            lines.append("")
            lines.append("| Component | MM value |")
            lines.append("|---|---:|")
            for component in MM_COMPOSITE_COMPONENT_FIELDS:
                value = components.get(component)
                if isinstance(value, (int, float)):
                    lines.append(f"| `{component}` | {value} |")
                else:
                    lines.append(f"| `{component}` | not observed |")
            if result.mm_component_sum is not None:
                lines.append(
                    f"| **MM component sum** | **{result.mm_component_sum}** |"
                )
            lines.append("")
        elif components == "not observed":
            lines.append(
                "_MacMarket composite components were not provided; "
                "component-sum attribution skipped._"
            )
            lines.append("")
        if result.tos_total_score is not None or result.mm_total_score is not None:
            lines.append("Total score reconciliation:")
            lines.append("")
            lines.append("| Source | total_score |")
            lines.append("|---|---:|")
            if result.tos_total_score is not None:
                lines.append(f"| ToS observed | {result.tos_total_score} |")
            else:
                lines.append("| ToS observed | not observed |")
            if result.mm_total_score is not None:
                lines.append(f"| MacMarket observed | {result.mm_total_score} |")
            if result.mm_component_sum is not None:
                lines.append(
                    f"| MacMarket component sum | {result.mm_component_sum} |"
                )
                if result.tos_total_score is not None:
                    lines.append(
                        f"| Δ (ToS − MM sum) | "
                        f"{result.tos_total_score - result.mm_component_sum} |"
                    )
            lines.append("")
        if result.diagnostic_flags.get(
            "oscillator_passed"
        ) and result.diagnostic_flags.get("composite_score_failed"):
            lines.append(
                "_Oscillator fields passed, but total score differs. Review "
                "composite component weights or observed score source._"
            )
            lines.append("")

    if result.diagnostic_flags:
        lines.append("Diagnostic flags:")
        for flag, value in sorted(result.diagnostic_flags.items()):
            lines.append(f"- `{flag}`: {bool(value)}")
        lines.append("")
    if result.diagnostic_classification:
        lines.append(
            "Classification: "
            + ", ".join(f"`{c}`" for c in result.diagnostic_classification)
        )
        lines.append("")
    return lines


def build_thinkorswim_parity_report(
    fixture_dir: Path,
    *,
    write: bool = False,
) -> ParityReportSummary:
    """Run parity for every fixture in ``fixture_dir`` and return a summary.

    When ``write`` is True the JSON + Markdown reports are written next
    to the manifest. The summary is always returned to the caller.

    Never runs when no manifest is present — instead returns a
    summary with ``manifest_present=False`` and ``overall_status='missing'``
    so the operator can rerun after dropping fixtures.
    """
    fixture_dir = Path(fixture_dir)
    manifest_path = fixture_dir / "manifest.json"
    now = datetime.now(UTC)

    if not manifest_path.exists():
        summary = ParityReportSummary(
            fixture_dir=fixture_dir,
            generated_at=now,
            fixtures_total=0,
            fixtures_passed=0,
            fixtures_failed=0,
            fixtures_skipped=0,
            results=[],
            manifest_present=False,
            manifest_valid=False,
        )
        if write:
            _write_report_files(fixture_dir, summary)
        return summary

    try:
        manifest = load_thinkorswim_manifest(manifest_path)
    except ParityFixtureError as exc:
        summary = ParityReportSummary(
            fixture_dir=fixture_dir,
            generated_at=now,
            fixtures_total=0,
            fixtures_passed=0,
            fixtures_failed=0,
            fixtures_skipped=0,
            results=[
                FixtureComparisonResult(
                    fixture_name="<manifest>",
                    symbol="",
                    timeframe="",
                    parity_mode="exported_study_csv",
                    status="skipped_manifest_missing",
                    rows_compared=0,
                    higher_timeframe_source=None,
                    parity_status=None,
                    derived_higher_timeframe=False,
                    reason_codes=["thinkorswim_fixture_validation_failed"],
                    diagnostics={"error": str(exc)},
                )
            ],
            manifest_present=True,
            manifest_valid=False,
        )
        if write:
            _write_report_files(fixture_dir, summary)
        return summary

    results: list[FixtureComparisonResult] = []
    passed = failed = skipped = 0
    for spec in manifest.fixtures:
        result = compare_momentum_to_thinkorswim(spec)
        results.append(result)
        if result.status in ("passed", "visual_attested"):
            passed += 1
        elif result.status in ("failed", "visual_failed"):
            failed += 1
        else:
            # visual_partial and every skipped_* status lands here.
            skipped += 1

    summary = ParityReportSummary(
        fixture_dir=fixture_dir,
        generated_at=now,
        fixtures_total=len(manifest.fixtures),
        fixtures_passed=passed,
        fixtures_failed=failed,
        fixtures_skipped=skipped,
        results=results,
        manifest_present=True,
        manifest_valid=True,
    )
    if write:
        _write_report_files(fixture_dir, summary)
    return summary


def _write_report_files(fixture_dir: Path, summary: ParityReportSummary) -> tuple[Path, Path]:
    json_path = fixture_dir / REPORT_FILENAME_JSON
    md_path = fixture_dir / REPORT_FILENAME_MD
    fixture_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary.to_dict(), indent=2, default=str), encoding="utf-8")
    md_path.write_text(_render_report_markdown(summary), encoding="utf-8")
    return json_path, md_path


# ── status builder ─────────────────────────────────────────────────────────


def _scan_manifest_mode_counts(manifest_path: Path) -> dict[str, int]:
    """Cheap helper: count declared parity_mode per fixture without
    running indicator math. Returns zeros when the manifest is missing
    or invalid — callers fall back to the report payload counts when
    a parity report is available.
    """
    counts = {
        "visual_observation": 0,
        "exported_study_csv": 0,
        "visual_attestation": 0,
    }
    if not manifest_path.exists():
        return counts
    try:
        manifest = load_thinkorswim_manifest(manifest_path)
    except ParityFixtureError:
        return counts
    for spec in manifest.fixtures:
        if spec.parity_mode in counts:
            counts[spec.parity_mode] += 1
        else:
            counts[spec.parity_mode] = counts.get(spec.parity_mode, 0) + 1
    return counts


def build_thinkorswim_momentum_parity_status(fixture_dir: Path) -> dict[str, Any]:
    """Read-only status helper for the Settings card.

    Inspects ``manifest.json`` + ``parity-report.json`` in
    ``fixture_dir`` without running indicator math. Returns a plain
    dict that callers serialize alongside the existing
    ``MomentumRankingStatus`` payload.

    Status values:

    - ``missing`` — no manifest, or manifest invalid.
    - ``partial`` — manifest present but some fixture files are missing.
    - ``ready``   — manifest present, files present, no parity report yet.
    - ``passed``  — last parity report says every fixture passed.
    - ``failed``  — last parity report flagged at least one failure.
    - ``pending`` — legacy fallback when none of the above apply.

    Visual-observation fields surfaced for the Settings card:

    - ``parity_mode_counts``                 — per-mode pass/fail/skipped totals.
    - ``visual_observation_count``           — total visual-observation fixtures.
    - ``exported_study_csv_count``           — total exported-study-CSV fixtures.
    - ``visual_observation_passed_count``    — visual fixtures that passed.
    - ``visual_observation_failed_count``    — visual fixtures that failed.
    - ``visual_reviewed``                    — at least one visual observation declared.
    """
    fixture_dir = Path(fixture_dir)
    validation = validate_thinkorswim_fixture_folder(fixture_dir)
    report_path = fixture_dir / REPORT_FILENAME_JSON
    md_path = fixture_dir / REPORT_FILENAME_MD

    report_present = report_path.exists()
    report_md_present = md_path.exists()
    report_payload: dict[str, Any] | None = None
    report_generated_at: str | None = None
    fixtures_passed: int | None = None
    fixtures_failed: int | None = None
    fixtures_skipped: int | None = None
    overall_status_from_report: str | None = None
    summary_text: str | None = None

    if report_present:
        try:
            report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report_payload = None
        if isinstance(report_payload, dict):
            report_generated_at = report_payload.get("generated_at") or None
            fixtures_passed = report_payload.get("fixtures_passed")
            fixtures_failed = report_payload.get("fixtures_failed")
            fixtures_skipped = report_payload.get("fixtures_skipped")
            overall_status_from_report = report_payload.get("overall_status")

    # Resolve per-mode counts. Prefer the report (post-run, authoritative)
    # over the manifest scan (pre-run, declared mode only). When neither
    # is available, fall back to zeros so the Settings card can still
    # render a coherent shape.
    manifest_path = fixture_dir / "manifest.json"
    manifest_mode_counts = _scan_manifest_mode_counts(manifest_path)
    report_mode_counts: dict[str, dict[str, int]] | None = None
    visual_count = manifest_mode_counts.get("visual_observation", 0)
    exported_count = manifest_mode_counts.get("exported_study_csv", 0)
    attestation_count = manifest_mode_counts.get("visual_attestation", 0)
    visual_passed = 0
    visual_failed = 0
    attestation_passed = 0
    attestation_failed = 0
    attestation_partial = 0
    attestation_status_from_report: str | None = None
    if isinstance(report_payload, dict):
        raw_mode_counts = report_payload.get("parity_mode_counts")
        if isinstance(raw_mode_counts, dict):
            normalized: dict[str, dict[str, int]] = {}
            for mode, bucket in raw_mode_counts.items():
                if not isinstance(bucket, dict):
                    continue
                normalized[str(mode)] = {
                    "total": int(bucket.get("total") or 0),
                    "passed": int(bucket.get("passed") or 0),
                    "failed": int(bucket.get("failed") or 0),
                    "skipped": int(bucket.get("skipped") or 0),
                    "partial": int(bucket.get("partial") or 0),
                }
            report_mode_counts = normalized or None
        if report_mode_counts is not None:
            visual_bucket = report_mode_counts.get("visual_observation", {})
            exported_bucket = report_mode_counts.get("exported_study_csv", {})
            attestation_bucket = report_mode_counts.get("visual_attestation", {})
            visual_count = visual_bucket.get("total", visual_count)
            exported_count = exported_bucket.get("total", exported_count)
            attestation_count = attestation_bucket.get("total", attestation_count)
            visual_passed = visual_bucket.get("passed", 0)
            visual_failed = visual_bucket.get("failed", 0)
            attestation_passed = attestation_bucket.get("passed", 0)
            attestation_failed = attestation_bucket.get("failed", 0)
            attestation_partial = attestation_bucket.get("partial", 0)
        else:
            visual_count = report_payload.get("visual_observation_count", visual_count)
            exported_count = report_payload.get("exported_study_csv_count", exported_count)
            visual_passed = int(report_payload.get("visual_observation_passed_count") or 0)
            visual_failed = int(report_payload.get("visual_observation_failed_count") or 0)
            attestation_count = int(
                report_payload.get("visual_attestation_count") or attestation_count
            )
            attestation_passed = int(
                report_payload.get("visual_attestation_passed_count") or 0
            )
            attestation_failed = int(
                report_payload.get("visual_attestation_failed_count") or 0
            )
            attestation_partial = int(
                report_payload.get("visual_attestation_partial_count") or 0
            )
        attestation_status_from_report = report_payload.get(
            "visual_attestation_status"
        ) or None
    parity_mode_counts: dict[str, dict[str, int]] = report_mode_counts or {
        "visual_observation": {
            "total": manifest_mode_counts.get("visual_observation", 0),
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "partial": 0,
        },
        "exported_study_csv": {
            "total": manifest_mode_counts.get("exported_study_csv", 0),
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "partial": 0,
        },
        "visual_attestation": {
            "total": manifest_mode_counts.get("visual_attestation", 0),
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "partial": 0,
        },
    }

    # Resolve visual_attestation_status from counts when the report
    # didn't supply it (e.g. pre-report runs).
    if attestation_status_from_report is None and attestation_count > 0:
        if attestation_failed > 0:
            attestation_status_from_report = "visual_failed"
        elif attestation_partial > 0:
            attestation_status_from_report = "visual_partial"
        elif attestation_passed == attestation_count:
            attestation_status_from_report = "visual_attested"
        else:
            attestation_status_from_report = "visual_partial"

    visual_only = visual_count > 0 and exported_count == 0
    attestation_only = (
        attestation_count > 0 and visual_count == 0 and exported_count == 0
    )

    # Derive workflow status.
    reason_codes: list[str] = []
    if not validation.manifest_present:
        status = "missing"
        reason_codes.append("thinkorswim_manifest_missing")
    elif not validation.manifest_valid:
        status = "missing"
        reason_codes.append("thinkorswim_fixture_validation_failed")
    elif validation.fixtures_total == 0:
        status = "missing"
        reason_codes.append("thinkorswim_manifest_missing")
    elif validation.fixtures_ready < validation.fixtures_total:
        status = "partial"
        reason_codes.append("thinkorswim_fixture_files_missing")
    elif report_payload and overall_status_from_report in {"passed", "failed", "partial"}:
        if overall_status_from_report == "passed":
            status = "passed"
            reason_codes.append("thinkorswim_parity_passed")
            if visual_passed > 0:
                reason_codes.append("thinkorswim_visual_parity_passed")
        elif overall_status_from_report == "failed":
            status = "failed"
            reason_codes.append("thinkorswim_parity_failed")
            if visual_failed > 0:
                reason_codes.append("thinkorswim_visual_parity_failed")
        else:
            status = "partial"
            reason_codes.append("thinkorswim_parity_partial")
    else:
        status = "ready"
        reason_codes.append("thinkorswim_parity_pending")

    if visual_count > 0:
        reason_codes.append("thinkorswim_visual_parity_observations_available")
    if attestation_count > 0:
        reason_codes.append("thinkorswim_visual_attestation_observations_available")
    if visual_only or attestation_only or (
        attestation_count > 0 and exported_count == 0
    ):
        reason_codes.append("thinkorswim_exported_study_csv_unavailable")
    if attestation_status_from_report == "visual_attested":
        reason_codes.append("thinkorswim_visual_attested")
    elif attestation_status_from_report == "visual_failed":
        reason_codes.append("thinkorswim_visual_attestation_failed")
    elif attestation_status_from_report == "visual_partial":
        reason_codes.append("thinkorswim_visual_attestation_partial")

    if status == "missing":
        summary_text = "Drop Thinkorswim CSV exports and a manifest.json to begin parity validation."
    elif status == "partial":
        summary_text = (
            f"{validation.fixtures_ready}/{validation.fixtures_total} fixtures have all required "
            "CSV files. Add the missing files and rerun the validator."
        )
    elif status == "ready":
        summary_text = (
            f"{validation.fixtures_total} fixture(s) staged. Run the parity validator to produce a report."
        )
    elif status == "passed":
        if attestation_only:
            basis = "visual attestation (no bars)"
        elif visual_only:
            basis = "visual / manual observation"
        elif attestation_count > 0 and visual_count > 0:
            basis = "mixed visual attestation + visual observation"
        elif attestation_count > 0:
            basis = "mixed visual attestation + exported study CSV"
        elif visual_count > 0:
            basis = "mixed visual observation + exported study CSV"
        else:
            basis = "exported study CSV"
        summary_text = (
            f"Parity passed for {fixtures_passed}/{validation.fixtures_total} fixtures "
            f"(basis: {basis})."
        )
    elif status == "failed":
        summary_text = (
            f"Parity failed for {fixtures_failed} fixture(s). Review {REPORT_FILENAME_MD}."
        )

    return {
        "status": status,
        "fixture_dir": str(fixture_dir),
        "manifest_present": validation.manifest_present,
        "manifest_valid": validation.manifest_valid,
        "fixtures_total": validation.fixtures_total,
        "fixtures_ready": validation.fixtures_ready,
        "fixtures_passed": fixtures_passed,
        "fixtures_failed": fixtures_failed,
        "fixtures_skipped": fixtures_skipped,
        "last_report_generated_at": report_generated_at,
        "report_path": str(report_path) if report_present else None,
        "report_markdown_path": str(md_path) if report_md_present else None,
        "report_present": report_present,
        "reason_codes": reason_codes,
        "summary": summary_text,
        "overall_status_from_report": overall_status_from_report,
        "parity_mode_counts": parity_mode_counts,
        "visual_observation_count": visual_count,
        "exported_study_csv_count": exported_count,
        "visual_observation_passed_count": visual_passed,
        "visual_observation_failed_count": visual_failed,
        "visual_attestation_count": attestation_count,
        "visual_attestation_passed_count": attestation_passed,
        "visual_attestation_failed_count": attestation_failed,
        "visual_attestation_partial_count": attestation_partial,
        "visual_attestation_status": attestation_status_from_report,
        "visual_reviewed": visual_count > 0 or attestation_count > 0,
        "exported_study_csv_available": exported_count > 0,
    }


REFERENCE_ONLY_FIELDS: frozenset[str] = _REFERENCE_ONLY_FIELDS


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
    "RECOMMENDED_HILO_VISUAL_FIELDS",
    "RECOMMENDED_STUDY_NAMES",
    "RECOMMENDED_VISUAL_FIELDS",
    "REFERENCE_ONLY_FIELDS",
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
