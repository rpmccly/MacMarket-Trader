"""Provider parity diagnostics for raw bars, canonical bars, and indicators."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from macmarket_trader.config import Settings, settings
from macmarket_trader.data.providers.market_data import (
    DataNotEntitledError,
    MarketDataService,
    ProviderUnavailableError,
    RTH_BUCKETS_BY_TIMEFRAME,
    RTH_SOURCE_TIMEFRAME,
    SymbolNotFoundError,
    _aggregate_regular_hours_intraday_bars,
    _format_rth_bucket_boundaries,
    _rth_source_page_target_count,
)
from macmarket_trader.data.providers.registry import build_market_data_service
from macmarket_trader.data.providers.schwab import (
    SchwabAuthRequiredError,
    SchwabConfigurationError,
    SchwabMarketDataProvider,
    redact_schwab_text,
    schwab_connection_status,
)
from macmarket_trader.domain.schemas import Bar
from macmarket_trader.domain.timeframes import SUPPORTED_CHART_TIMEFRAMES, validate_chart_timeframe
from macmarket_trader.indicators.haco_ha import compute_haco_from_ha
from macmarket_trader.indicators.hacolt import compute_hacolt_direction
from macmarket_trader.indicators.hilo_elite import compute_hilo_elite
from macmarket_trader.indicators.squeeze_pro import compute_squeeze_pro
from macmarket_trader.indicators.true_momentum import compute_true_momentum
from macmarket_trader.indicators.true_momentum_score import compute_true_momentum_score
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import ProviderOAuthRepository, ProviderParitySnapshotRepository


PRICE_ABS_TOLERANCE = 0.01
PRICE_REL_TOLERANCE = 0.0005
VOLUME_REL_TOLERANCE = 0.01
SENSITIVE_SNAPSHOT_KEYWORDS = ("authorization", "access_token", "refresh_token", "client_secret", "token_secret")


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass(frozen=True)
class ProviderBars:
    bars: list[Bar]
    provider: str
    fallback_mode: bool
    metadata: dict[str, object]
    warnings: list[str]


def _bar_time_key(bar: Bar) -> str:
    if bar.timestamp is not None:
        return bar.timestamp.astimezone(UTC).isoformat()
    return bar.date.isoformat()


def _bar_sort_key(bar: Bar) -> tuple[datetime, str]:
    if bar.timestamp is not None:
        return bar.timestamp.astimezone(UTC), bar.date.isoformat()
    return datetime.combine(bar.date, datetime.min.time(), tzinfo=UTC), bar.date.isoformat()


def _json_safe_bar(bar: Bar | None) -> dict[str, object] | None:
    if bar is None:
        return None
    return {
        "date": bar.date.isoformat(),
        "timestamp": bar.timestamp.astimezone(UTC).isoformat() if bar.timestamp else None,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "session_policy": bar.session_policy,
        "source_session_policy": bar.source_session_policy,
        "source_timeframe": bar.source_timeframe,
        "provider": bar.provider,
    }


def _metadata_from_bars(bars: list[Bar], *, provider: str, timeframe: str, fallback_mode: bool) -> dict[str, object]:
    ordered = sorted(bars, key=_bar_sort_key)
    first = ordered[0] if ordered else None
    last = ordered[-1] if ordered else None
    return {
        "provider": provider,
        "output_timeframe": timeframe.upper(),
        "fallback_mode": fallback_mode,
        "session_policy": first.session_policy if first else None,
        "source_session_policy": first.source_session_policy if first else None,
        "source_timeframe": first.source_timeframe if first else None,
        "regular_hours_timezone": "America/New_York" if timeframe.upper() in RTH_BUCKETS_BY_TIMEFRAME else None,
        "weekly_anchor": "provider_weekly_frequency" if timeframe.upper() == "1W" else None,
        "rth_bucket_boundaries": _format_rth_bucket_boundaries(timeframe) if timeframe.upper() in RTH_BUCKETS_BY_TIMEFRAME else [],
        "first_bar_timestamp": first.timestamp.astimezone(UTC).isoformat() if first and first.timestamp else None,
        "last_bar_timestamp": last.timestamp.astimezone(UTC).isoformat() if last and last.timestamp else None,
    }


def _canonicalize_bars(
    bars: list[Bar],
    *,
    provider: str,
    timeframe: str,
    limit: int,
    fallback_mode: bool,
) -> tuple[list[Bar], dict[str, object]]:
    tf = validate_chart_timeframe(timeframe)
    ordered = sorted(bars, key=_bar_sort_key)
    if tf in RTH_BUCKETS_BY_TIMEFRAME and any(bar.timestamp is not None for bar in ordered):
        selected, metadata = _aggregate_regular_hours_intraday_bars(
            ordered,
            output_timeframe=tf,
            limit=limit,
            provider=provider,
            source_timeframe=str(ordered[0].source_timeframe or tf) if ordered else tf,
            source_session_policy=str(ordered[0].source_session_policy or "provider_session") if ordered else "provider_session",
        )
        metadata["fallback_mode"] = fallback_mode
        return selected, metadata
    selected = ordered[-limit:]
    for bar in selected:
        bar.provider = bar.provider or provider
        bar.session_policy = bar.session_policy or "regular_hours"
        bar.source_session_policy = bar.source_session_policy or bar.session_policy
        bar.source_timeframe = bar.source_timeframe or tf
    return selected, _metadata_from_bars(selected, provider=provider, timeframe=tf, fallback_mode=fallback_mode)


def _max_price_allowed(reference: float) -> float:
    return max(PRICE_ABS_TOLERANCE, abs(reference) * PRICE_REL_TOLERANCE)


def _numeric_delta(a: object, b: object) -> float | None:
    try:
        left = float(a)
        right = float(b)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(left) or not math.isfinite(right):
        return None
    return abs(left - right)


def _compare_bars(
    current: list[Bar],
    candidate: list[Bar],
    *,
    current_metadata: dict[str, object],
    candidate_metadata: dict[str, object],
) -> dict[str, object]:
    current_by_time = {_bar_time_key(bar): bar for bar in current}
    candidate_by_time = {_bar_time_key(bar): bar for bar in candidate}
    current_keys = set(current_by_time)
    candidate_keys = set(candidate_by_time)
    aligned = sorted(current_keys & candidate_keys)
    missing_on_current = sorted(candidate_keys - current_keys)
    missing_on_candidate = sorted(current_keys - candidate_keys)
    latest_current = current[-1] if current else None
    latest_candidate = candidate[-1] if candidate else None

    max_price_delta = 0.0
    max_price_field: str | None = None
    max_volume_delta = 0.0
    for key in aligned:
        left = current_by_time[key]
        right = candidate_by_time[key]
        for field in ("open", "high", "low", "close"):
            delta = abs(float(getattr(left, field)) - float(getattr(right, field)))
            if delta > max_price_delta:
                max_price_delta = delta
                max_price_field = field
        volume_delta = abs(float(left.volume) - float(right.volume))
        max_volume_delta = max(max_volume_delta, volume_delta)

    latest_timestamp_match = bool(latest_current and latest_candidate and _bar_time_key(latest_current) == _bar_time_key(latest_candidate))
    material_price = False
    material_volume = False
    if aligned:
        for key in aligned:
            left = current_by_time[key]
            right = candidate_by_time[key]
            for field in ("open", "high", "low", "close"):
                delta = abs(float(getattr(left, field)) - float(getattr(right, field)))
                if delta > _max_price_allowed(float(getattr(left, field))):
                    material_price = True
            allowed_volume_delta = max(0.0, abs(float(left.volume)) * VOLUME_REL_TOLERANCE)
            if abs(float(left.volume) - float(right.volume)) > allowed_volume_delta:
                material_volume = True
    if not current or not candidate or len(aligned) < 2:
        verdict = "insufficient_data"
    elif material_price or material_volume or missing_on_current or missing_on_candidate or not latest_timestamp_match:
        verdict = "mismatch"
    else:
        verdict = "match"

    return {
        "verdict": verdict,
        "bars_current": len(current),
        "bars_candidate": len(candidate),
        "aligned_timestamps": len(aligned),
        "first_timestamp_current": _bar_time_key(current[0]) if current else None,
        "first_timestamp_candidate": _bar_time_key(candidate[0]) if candidate else None,
        "last_timestamp_current": _bar_time_key(latest_current) if latest_current else None,
        "last_timestamp_candidate": _bar_time_key(latest_candidate) if latest_candidate else None,
        "latest_timestamp_match": latest_timestamp_match,
        "latest_current": _json_safe_bar(latest_current),
        "latest_candidate": _json_safe_bar(latest_candidate),
        "max_price_delta": round(max_price_delta, 6),
        "max_price_delta_field": max_price_field,
        "max_volume_delta": round(max_volume_delta, 6),
        "missing_timestamps_current": missing_on_current[:50],
        "extra_timestamps_current": missing_on_candidate[:50],
        "missing_timestamps_current_count": len(missing_on_current),
        "extra_timestamps_current_count": len(missing_on_candidate),
        "current_metadata": current_metadata,
        "candidate_metadata": candidate_metadata,
    }


def _raw_source_timeframe(timeframe: str) -> str:
    tf = validate_chart_timeframe(timeframe)
    return RTH_SOURCE_TIMEFRAME if tf in RTH_BUCKETS_BY_TIMEFRAME else tf


def _raw_source_limit(timeframe: str, limit: int) -> int:
    tf = validate_chart_timeframe(timeframe)
    bounded = max(1, int(limit or 1))
    if tf in RTH_BUCKETS_BY_TIMEFRAME:
        return _rth_source_page_target_count(tf, bounded)
    return bounded


def _annotate_raw_metadata(
    metadata: dict[str, object],
    *,
    requested_timeframe: str,
    source_timeframe: str,
    source_limit: int,
) -> dict[str, object]:
    annotated = dict(metadata)
    annotated["comparison_layer"] = "raw_provider_bars"
    annotated["requested_output_timeframe"] = validate_chart_timeframe(requested_timeframe)
    annotated["raw_source_timeframe"] = source_timeframe
    annotated["raw_source_limit"] = source_limit
    if requested_timeframe.upper() in RTH_BUCKETS_BY_TIMEFRAME:
        annotated.setdefault("regular_hours_timezone", "America/New_York")
        annotated.setdefault("rth_bucket_boundaries", _format_rth_bucket_boundaries(requested_timeframe))
    if requested_timeframe.upper() == "1W":
        annotated.setdefault("weekly_anchor", "provider_weekly_frequency")
    return annotated


def _sanitize_snapshot_payload(value: object) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if any(part in normalized_key for part in SENSITIVE_SNAPSHOT_KEYWORDS):
                sanitized[str(key)] = "[redacted]"
            else:
                sanitized[str(key)] = _sanitize_snapshot_payload(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_snapshot_payload(item) for item in value]
    if isinstance(value, str) and ("Bearer " in value or "Authorization:" in value):
        return "[redacted]"
    return value


def _last_or_none(values: list[Any]) -> Any | None:
    return values[-1] if values else None


def _haco_direction(state: str | None) -> str | None:
    normalized = str(state or "").lower()
    if normalized == "green":
        return "LONG"
    if normalized == "red":
        return "SHORT"
    return None


def _hacolt_direction(direction: str | None) -> str | None:
    normalized = str(direction or "").lower()
    if normalized == "up":
        return "LONG"
    if normalized == "down":
        return "SHORT"
    if normalized == "neutral":
        return "NEUTRAL"
    return None


def _compute_indicator_bundle(bars: list[Bar], *, symbol: str, timeframe: str) -> dict[str, object]:
    tf = validate_chart_timeframe(timeframe)
    canonical = sorted(bars, key=_bar_sort_key)
    if not canonical:
        unavailable = {"available": False, "reason": "insufficient_data"}
        return {
            "trueMomentum": unavailable,
            "haco": unavailable,
            "hacolt": unavailable,
            "hiLo": unavailable,
            "squeeze": unavailable,
        }
    opens = [bar.open for bar in canonical]
    highs = [bar.high for bar in canonical]
    lows = [bar.low for bar in canonical]
    closes = [bar.close for bar in canonical]
    as_of = _bar_time_key(canonical[-1])

    try:
        tm_series = compute_true_momentum(canonical, timeframe=tf)
        hilo_series = compute_hilo_elite(canonical, timeframe=tf)
        score_series = compute_true_momentum_score(canonical, timeframe=tf, true_momentum_series=tm_series, hilo_series=hilo_series)
        tm_point = _last_or_none(tm_series.points)
        score_point = _last_or_none(score_series.points)
        true_momentum = {
            "available": bool(tm_point and score_point),
            "asOf": as_of,
            "symbol": symbol,
            "timeframe": tf,
            "trueMomentum": round(tm_point.true_momentum, 6) if tm_point else None,
            "trueMomentumEma": round(tm_point.true_momentum_ema, 6) if tm_point else None,
            "trueMomentumScore": score_point.component_breakdown.true_momentum_score if score_point else None,
            "totalScore": score_point.total_score if score_point else None,
            "totalLabel": score_point.total_label if score_point else None,
            "trendDirection": tm_point.trend_direction if tm_point else None,
            "higherTimeframeSource": tm_series.higher_timeframe_source,
            "notes": list(tm_series.notes) + list(score_series.notes),
        }
    except Exception as exc:  # noqa: BLE001 - diagnostic should degrade per component
        true_momentum = {"available": False, "reason": "component_error", "error": str(exc)[:160]}
        hilo_series = None

    try:
        _ha_open, _ha_high, _ha_low, _ha_close, haco_points = compute_haco_from_ha(opens, highs, lows, closes)
        haco_point = _last_or_none(haco_points)
        latest_flip = next((point.flip for point in reversed(haco_points) if point.flip), None)
        haco = {
            "available": bool(haco_point),
            "asOf": as_of,
            "state": haco_point.state if haco_point else None,
            "direction": _haco_direction(haco_point.state if haco_point else None),
            "latestFlip": latest_flip,
            "stateValue": haco_point.state_value if haco_point else None,
            "momentum": round(haco_point.momentum, 6) if haco_point else None,
        }
    except Exception as exc:  # noqa: BLE001
        haco = {"available": False, "reason": "component_error", "error": str(exc)[:160]}

    try:
        hacolt_points = compute_hacolt_direction(opens, highs, lows, closes)
        hacolt_point = _last_or_none(hacolt_points)
        hacolt = {
            "available": bool(hacolt_point),
            "asOf": as_of,
            "direction": _hacolt_direction(hacolt_point.direction if hacolt_point else None),
            "rawDirection": hacolt_point.direction if hacolt_point else None,
            "stripValue": hacolt_point.strip_value if hacolt_point else None,
            "spread": round(hacolt_point.spread, 6) if hacolt_point else None,
        }
    except Exception as exc:  # noqa: BLE001
        hacolt = {"available": False, "reason": "component_error", "error": str(exc)[:160]}

    try:
        if hilo_series is None:
            hilo_series = compute_hilo_elite(canonical, timeframe=tf)
        hilo_point = _last_or_none(hilo_series.points)
        thrust_state = "bullish" if hilo_point and hilo_point.thrust == 1 else ("bearish" if hilo_point and hilo_point.thrust == -1 else "neutral")
        hilo = {
            "available": bool(hilo_point),
            "asOf": as_of,
            "state": thrust_state,
            "slowD": round(hilo_point.slow_d, 6) if hilo_point else None,
            "slowDX": round(hilo_point.slow_d_x, 6) if hilo_point else None,
            "thrust": hilo_point.thrust if hilo_point else None,
            "hiLoScore": hilo_point.hlp_output if hilo_point else None,
        }
    except Exception as exc:  # noqa: BLE001
        hilo = {"available": False, "reason": "component_error", "error": str(exc)[:160]}

    try:
        squeeze_series = compute_squeeze_pro(canonical)
        squeeze_point = _last_or_none(squeeze_series.points)
        squeeze = {
            "available": bool(squeeze_point),
            "asOf": as_of,
            "state": squeeze_point.squeeze_state if squeeze_point else None,
            "histogram": squeeze_point.oscillator_value if squeeze_point else None,
            "oscillatorState": squeeze_point.oscillator_state if squeeze_point else None,
            "status": squeeze_point.status if squeeze_point else "unavailable",
            "reason": squeeze_point.reason if squeeze_point else None,
            "histogramMode": squeeze_series.config.histogram_mode,
        }
    except Exception as exc:  # noqa: BLE001
        squeeze = {"available": False, "reason": "component_error", "error": str(exc)[:160]}

    return {
        "trueMomentum": true_momentum,
        "haco": haco,
        "hacolt": hacolt,
        "hiLo": hilo,
        "squeeze": squeeze,
    }


def _component_values(bundle: dict[str, object]) -> dict[str, object]:
    def as_dict(name: str) -> dict[str, object]:
        value = bundle.get(name)
        return value if isinstance(value, dict) else {}

    true_momentum = as_dict("trueMomentum")
    haco = as_dict("haco")
    hacolt = as_dict("hacolt")
    hilo = as_dict("hiLo")
    squeeze = as_dict("squeeze")
    return {
        "trueMomentumScore": true_momentum.get("trueMomentumScore"),
        "trueMomentum": true_momentum.get("trueMomentum"),
        "trueMomentumEma": true_momentum.get("trueMomentumEma"),
        "hacoDirection": haco.get("direction"),
        "hacoLatestFlip": haco.get("latestFlip"),
        "hacoltDirection": hacolt.get("direction"),
        "hiLoState": hilo.get("state"),
        "hiLoValue": hilo.get("slowD"),
        "hiLoScore": hilo.get("hiLoScore"),
        "squeezeState": squeeze.get("state"),
        "squeezeHistogram": squeeze.get("histogram"),
    }


def _compare_indicator_bundles(current: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    current_values = _component_values(current)
    candidate_values = _component_values(candidate)
    mismatches: list[dict[str, object]] = []
    for field, current_value in current_values.items():
        candidate_value = candidate_values.get(field)
        if current_value is None and candidate_value is None:
            continue
        delta = _numeric_delta(current_value, candidate_value)
        if delta is not None:
            if delta > _max_price_allowed(float(current_value or 0.0)):
                mismatches.append({"field": field, "current": current_value, "candidate": candidate_value, "delta": round(delta, 6)})
        elif str(current_value or "").upper() != str(candidate_value or "").upper():
            mismatches.append({"field": field, "current": current_value, "candidate": candidate_value})
    return {
        "verdict": "mismatch" if mismatches else "match",
        "mismatches": mismatches,
        "current": current,
        "candidate": candidate,
    }


def _read_ref(ref: dict[str, object], *keys: str) -> object:
    for key in keys:
        if key in ref:
            return ref[key]
    return None


def _compare_tos_reference(ref: dict[str, object] | None, current_bundle: dict[str, object], candidate_bundle: dict[str, object]) -> dict[str, object]:
    if not ref:
        return {"provided": False, "verdict": "not_provided", "mismatches": []}
    current = _component_values(current_bundle)
    candidate = _component_values(candidate_bundle)
    fields = {
        "trueMomentumScore": _read_ref(ref, "trueMomentumScore", "true_momentum_score"),
        "hacoDirection": _read_ref(ref, "hacoDirection", "haco_direction"),
        "hacoLatestFlip": _read_ref(ref, "hacoLatestFlip", "haco_latest_flip"),
        "hacoltDirection": _read_ref(ref, "hacoltDirection", "hacolt_direction"),
        "hiLoState": _read_ref(ref, "hiLoState", "hi_lo_state", "hiloState"),
        "hiLoValue": _read_ref(ref, "hiLoValue", "hi_lo_value", "hiloValue"),
        "squeezeState": _read_ref(ref, "squeezeState", "squeeze_state"),
        "squeezeHistogram": _read_ref(ref, "squeezeHistogram", "squeeze_histogram"),
    }
    mismatches: list[dict[str, object]] = []
    for field, reference_value in fields.items():
        if reference_value is None or reference_value == "":
            continue
        current_value = current.get(field)
        candidate_value = candidate.get(field)
        delta_current = _numeric_delta(reference_value, current_value)
        delta_candidate = _numeric_delta(reference_value, candidate_value)
        if delta_current is not None or delta_candidate is not None:
            current_ok = delta_current is not None and delta_current <= _max_price_allowed(float(reference_value))
            candidate_ok = delta_candidate is not None and delta_candidate <= _max_price_allowed(float(reference_value))
            if not (current_ok or candidate_ok):
                mismatches.append(
                    {
                        "field": field,
                        "tos": reference_value,
                        "current": current_value,
                        "candidate": candidate_value,
                        "deltaCurrent": round(delta_current, 6) if delta_current is not None else None,
                        "deltaCandidate": round(delta_candidate, 6) if delta_candidate is not None else None,
                    }
                )
            continue
        reference_text = str(reference_value).strip().upper()
        if reference_text not in {str(current_value or "").strip().upper(), str(candidate_value or "").strip().upper()}:
            mismatches.append({"field": field, "tos": reference_value, "current": current_value, "candidate": candidate_value})
    return {
        "provided": True,
        "verdict": "mismatch" if mismatches else "match",
        "mismatches": mismatches,
        "notes": str(_read_ref(ref, "notes") or "")[:500],
    }


class ProviderParityService:
    def __init__(
        self,
        *,
        current_market_data_service: MarketDataService | None = None,
        schwab_provider: SchwabMarketDataProvider | None = None,
        oauth_repo: ProviderOAuthRepository | None = None,
        snapshot_repo: ProviderParitySnapshotRepository | None = None,
        cfg: Settings = settings,
    ) -> None:
        self.cfg = cfg
        self.current_market_data_service = current_market_data_service or build_market_data_service()
        self.oauth_repo = oauth_repo or ProviderOAuthRepository(SessionLocal)
        self.schwab_provider = schwab_provider or SchwabMarketDataProvider(repo=self.oauth_repo, cfg=cfg)
        self.snapshot_repo = snapshot_repo or ProviderParitySnapshotRepository(SessionLocal)

    def _current_provider_name(self) -> str:
        provider = getattr(self.current_market_data_service, "_provider", None)
        return str(getattr(provider, "name", None) or "market_data")

    def _fetch_current_raw(self, *, symbol: str, timeframe: str, limit: int) -> ProviderBars:
        provider = getattr(self.current_market_data_service, "_provider", None)
        warnings: list[str] = []
        source_timeframe = _raw_source_timeframe(timeframe)
        source_limit = _raw_source_limit(timeframe, limit)
        if provider is not None and callable(getattr(provider, "fetch_historical_bars", None)):
            bars = provider.fetch_historical_bars(symbol=symbol, timeframe=source_timeframe, limit=source_limit)
            provider_name = str(getattr(provider, "name", "market_data"))
            metadata = getattr(provider, "last_aggregate_request_metadata", None)
            if source_timeframe != validate_chart_timeframe(timeframe):
                warnings.append("current_provider_raw_uses_30m_source_for_intraday_resampling")
            else:
                warnings.append("current_provider_raw_uses_existing_adapter_output")
            return ProviderBars(
                bars=sorted(bars, key=_bar_sort_key),
                provider=provider_name,
                fallback_mode=provider_name == "fallback",
                metadata=_annotate_raw_metadata(
                    dict(metadata) if isinstance(metadata, dict) else _metadata_from_bars(bars, provider=provider_name, timeframe=source_timeframe, fallback_mode=provider_name == "fallback"),
                    requested_timeframe=timeframe,
                    source_timeframe=source_timeframe,
                    source_limit=source_limit,
                ),
                warnings=warnings,
            )
        bars, source, fallback_mode = self.current_market_data_service.historical_bars(symbol=symbol, timeframe=source_timeframe, limit=source_limit)
        metadata = getattr(self.current_market_data_service, "last_historical_metadata", None)
        warnings.append("current_provider_raw_uses_market_data_service_output")
        return ProviderBars(
            bars=sorted(bars, key=_bar_sort_key),
            provider=source,
            fallback_mode=fallback_mode,
            metadata=_annotate_raw_metadata(
                dict(metadata) if isinstance(metadata, dict) else _metadata_from_bars(bars, provider=source, timeframe=source_timeframe, fallback_mode=fallback_mode),
                requested_timeframe=timeframe,
                source_timeframe=source_timeframe,
                source_limit=source_limit,
            ),
            warnings=warnings,
        )

    def _fetch_schwab_raw(self, *, symbol: str, timeframe: str, limit: int) -> ProviderBars:
        bars, metadata = self.schwab_provider.fetch_raw_historical_bars(symbol=symbol, timeframe=timeframe, limit=limit)
        source_timeframe = str(metadata.get("source_timeframe") or _raw_source_timeframe(timeframe))
        source_limit = int(metadata.get("raw_selection_limit") or _raw_source_limit(timeframe, limit))
        return ProviderBars(
            bars=sorted(bars, key=_bar_sort_key),
            provider="schwab",
            fallback_mode=False,
            metadata=_annotate_raw_metadata(
                dict(metadata),
                requested_timeframe=timeframe,
                source_timeframe=source_timeframe,
                source_limit=source_limit,
            ),
            warnings=[],
        )

    @staticmethod
    def _root_cause(
        *,
        schwab_status: dict[str, object],
        raw: dict[str, object] | None,
        canonical: dict[str, object] | None,
        indicators: dict[str, object] | None,
        tos: dict[str, object] | None,
        error: str | None,
    ) -> str:
        token_status = str(schwab_status.get("token_status") or "")
        if token_status != "connected":
            return "schwab_not_connected"
        if error:
            return "error"
        if raw is None or canonical is None or indicators is None:
            return "insufficient_data"
        if raw.get("verdict") == "insufficient_data" or canonical.get("verdict") == "insufficient_data":
            return "insufficient_data"
        if raw.get("verdict") == "mismatch":
            return "raw_provider_mismatch"
        if canonical.get("verdict") == "mismatch":
            return "normalization_mismatch"
        if indicators.get("verdict") == "mismatch":
            return "indicator_mismatch"
        if tos and tos.get("provided") and tos.get("verdict") == "mismatch":
            return "tos_reference_mismatch"
        return "match"

    def run(self, request: dict[str, object], *, app_user_id: int) -> dict[str, object]:
        symbols = [str(item).strip().upper() for item in request.get("symbols", []) if str(item).strip()]
        timeframes = [validate_chart_timeframe(item) for item in request.get("timeframes", [])] or list(SUPPORTED_CHART_TIMEFRAMES)
        lookback = int(request.get("lookbackBars") or self.cfg.data_parity_default_lookback_bars)
        lookback = max(5, min(lookback, self.cfg.data_parity_max_lookback_bars))
        session_policy = str(request.get("sessionPolicy") or "regular_hours")
        include_extended = bool(request.get("includeExtendedHours") or False)
        save_snapshot = bool(request.get("saveSnapshot", self.cfg.data_parity_save_snapshots)) and self.cfg.data_parity_save_snapshots
        tos_refs = request.get("tosReferences") if isinstance(request.get("tosReferences"), list) else []
        tos_by_key: dict[tuple[str, str], dict[str, object]] = {}
        for ref in tos_refs:
            if not isinstance(ref, dict):
                continue
            symbol = str(_read_ref(ref, "symbol") or "").strip().upper()
            timeframe = str(_read_ref(ref, "timeframe") or "").strip().upper()
            if symbol and timeframe:
                tos_by_key[(symbol, timeframe)] = ref

        run_id = f"dpar_{uuid4().hex[:16]}"
        as_of = _utc_now().isoformat()
        status_payload = _sanitize_snapshot_payload(schwab_connection_status(repo=self.oauth_repo, cfg=self.cfg))
        schwab_status = status_payload if isinstance(status_payload, dict) else {}
        results: list[dict[str, object]] = []
        summary: dict[str, int] = {
            "total": 0,
            "match": 0,
            "raw_provider_mismatch": 0,
            "normalization_mismatch": 0,
            "indicator_mismatch": 0,
            "tos_reference_mismatch": 0,
            "schwab_not_connected": 0,
            "insufficient_data": 0,
            "error": 0,
        }
        warnings: list[str] = []
        errors: list[dict[str, object]] = []

        for symbol in symbols:
            for timeframe in timeframes:
                summary["total"] += 1
                item_error: str | None = None
                raw_comparison: dict[str, object] | None = None
                canonical_comparison: dict[str, object] | None = None
                indicators_comparison: dict[str, object] | None = None
                tos_comparison: dict[str, object] | None = None
                result_warnings: list[str] = []
                try:
                    if str(schwab_status.get("token_status") or "") != "connected":
                        raise SchwabAuthRequiredError("schwab_not_connected")
                    current_raw = self._fetch_current_raw(symbol=symbol, timeframe=timeframe, limit=lookback)
                    schwab_raw = self._fetch_schwab_raw(symbol=symbol, timeframe=timeframe, limit=lookback)
                    result_warnings.extend(current_raw.warnings)
                    result_warnings.extend(schwab_raw.warnings)
                    raw_comparison = _compare_bars(
                        current_raw.bars,
                        schwab_raw.bars,
                        current_metadata=current_raw.metadata,
                        candidate_metadata=schwab_raw.metadata,
                    )
                    current_canonical, current_metadata = _canonicalize_bars(
                        current_raw.bars,
                        provider=current_raw.provider,
                        timeframe=timeframe,
                        limit=lookback,
                        fallback_mode=current_raw.fallback_mode,
                    )
                    schwab_canonical, schwab_metadata = self.schwab_provider.normalize_bars(
                        schwab_raw.bars,
                        timeframe=timeframe,
                        limit=lookback,
                    )
                    canonical_comparison = _compare_bars(
                        current_canonical,
                        schwab_canonical,
                        current_metadata=current_metadata,
                        candidate_metadata=schwab_metadata,
                    )
                    current_bundle = _compute_indicator_bundle(current_canonical, symbol=symbol, timeframe=timeframe)
                    schwab_bundle = _compute_indicator_bundle(schwab_canonical, symbol=symbol, timeframe=timeframe)
                    indicators_comparison = _compare_indicator_bundles(current_bundle, schwab_bundle)
                    tos_comparison = _compare_tos_reference(tos_by_key.get((symbol, timeframe)), current_bundle, schwab_bundle)
                except SchwabAuthRequiredError as exc:
                    item_error = str(exc)
                    tos_comparison = {"provided": (symbol, timeframe) in tos_by_key, "verdict": "not_compared", "mismatches": []}
                except (SchwabConfigurationError, DataNotEntitledError, ProviderUnavailableError, SymbolNotFoundError, ValueError, OSError, KeyError) as exc:
                    item_error = redact_schwab_text(exc)
                    errors.append({"symbol": symbol, "timeframe": timeframe, "error": item_error})

                root_cause = self._root_cause(
                    schwab_status=schwab_status,
                    raw=raw_comparison,
                    canonical=canonical_comparison,
                    indicators=indicators_comparison,
                    tos=tos_comparison,
                    error=item_error,
                )
                summary[root_cause] = summary.get(root_cause, 0) + 1
                results.append(
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "rawBars": raw_comparison,
                        "canonicalBars": canonical_comparison,
                        "indicators": indicators_comparison,
                        "tosReference": tos_comparison or {"provided": False, "verdict": "not_provided", "mismatches": []},
                        "rootCause": root_cause,
                        "warnings": result_warnings,
                        "errors": [item_error] if item_error else [],
                    }
                )
                warnings.extend(result_warnings)

        response: dict[str, object] = {
            "runId": run_id,
            "asOf": as_of,
            "providers": {
                "current": {
                    "provider": self._current_provider_name(),
                    "status": getattr(self.current_market_data_service.provider_health(sample_symbol="SPY"), "status", "unknown"),
                    "productionProviderUnchanged": True,
                },
                "candidate": schwab_status,
            },
            "request": {
                "symbols": symbols,
                "timeframes": timeframes,
                "lookbackBars": lookback,
                "sessionPolicy": session_policy,
                "includeExtendedHours": include_extended,
                "saveSnapshot": save_snapshot,
                "tosReferencesProvided": len(tos_by_key),
            },
            "summary": summary,
            "results": results,
            "warnings": sorted(set(warnings)),
            "errors": errors,
            "readOnly": True,
            "brokerRoutingEnabled": False,
            "productionProviderUnchanged": True,
        }

        sanitized_response = _sanitize_snapshot_payload(response)
        response = dict(sanitized_response) if isinstance(sanitized_response, dict) else response

        if save_snapshot and symbols:
            snapshot_request = _sanitize_snapshot_payload(response["request"])
            snapshot_response = _sanitize_snapshot_payload(response)
            self.snapshot_repo.create(
                app_user_id=app_user_id,
                run_id=run_id,
                request_json=dict(snapshot_request) if isinstance(snapshot_request, dict) else {},  # type: ignore[arg-type]
                response_json=dict(snapshot_response) if isinstance(snapshot_response, dict) else {},
                provider_current=self._current_provider_name(),
                provider_candidate="schwab",
            )
        return response


def snapshot_to_summary(row) -> dict[str, object]:  # noqa: ANN001
    response = row.response_json if isinstance(row.response_json, dict) else {}
    summary = response.get("summary") if isinstance(response.get("summary"), dict) else {}
    request = row.request_json if isinstance(row.request_json, dict) else {}
    return {
        "runId": row.run_id,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "providerCurrent": row.provider_current,
        "providerCandidate": row.provider_candidate,
        "symbols": request.get("symbols") or [],
        "timeframes": request.get("timeframes") or [],
        "summary": summary,
    }


__all__ = [
    "ProviderParityService",
    "snapshot_to_summary",
]
