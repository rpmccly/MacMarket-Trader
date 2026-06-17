"""Provider parity diagnostics for raw bars, canonical bars, and indicators."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

from macmarket_trader.config import Settings, settings
from macmarket_trader.data.providers.market_data import (
    DataNotEntitledError,
    MarketDataService,
    PolygonMarketDataProvider,
    ProviderUnavailableError,
    RTH_BUCKETS_BY_TIMEFRAME,
    RTH_SOURCE_TIMEFRAME,
    SymbolNotFoundError,
    US_EQUITY_TIMEZONE,
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
PREMARKET_START_MINUTE = 4 * 60
REGULAR_OPEN_MINUTE = 9 * 60 + 30
REGULAR_CLOSE_MINUTE = 16 * 60
AFTER_HOURS_END_MINUTE = 20 * 60
FRESHNESS_REAL_TIME_TOLERANCE_MINUTES = {
    "30M": 5.0,
    "1H": 7.0,
    "4H": 10.0,
    "1D": 60.0,
    "1W": 24.0 * 60.0,
}
FRESHNESS_DELAY_TARGET_MINUTES = 15.0
FRESHNESS_DELAY_TOLERANCE_MINUTES = 5.0
LATEST_TIMESTAMP_TOLERANCE_SECONDS = {
    "30M": 45 * 60,
    "1H": 90 * 60,
    "4H": 5 * 60 * 60,
    "1D": 60 * 60 * 60,
    "1W": 10 * 24 * 60 * 60,
}
NOT_COMPARABLE_VERDICTS = {
    "provider_unavailable",
    "auth_unavailable",
    "no_bars",
    "insufficient_data",
    "stale_source",
    "no_aligned_bars",
}


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


def _bar_session_date(bar: Bar) -> date:
    return bar.date


def _canonical_week_bounds(day: date) -> tuple[date, date]:
    # Polygon weekly aggregates can be timestamped at the Sunday boundary before
    # the trading week that Schwab/TOS labels with Monday. Normalize that
    # boundary to the following Monday for parity diagnostics only.
    if day.weekday() == 6:
        week_start = day + timedelta(days=1)
    else:
        week_start = day - timedelta(days=day.weekday())
    return week_start, week_start + timedelta(days=4)


def _bar_alignment_mode(timeframe: str) -> str:
    tf = validate_chart_timeframe(timeframe)
    if tf == "1D":
        return "normalized_session_date"
    if tf == "1W":
        return "normalized_trading_week"
    if tf in RTH_BUCKETS_BY_TIMEFRAME:
        return "canonical_intraday_interval"
    return "exact_timestamp"


def _bar_alignment_key(bar: Bar, *, timeframe: str) -> str:
    tf = validate_chart_timeframe(timeframe)
    if tf == "1D":
        return f"session:{_bar_session_date(bar).isoformat()}"
    if tf == "1W":
        week_start, week_end = _canonical_week_bounds(_bar_session_date(bar))
        return f"week:{week_start.isoformat()}/{week_end.isoformat()}"
    if tf in RTH_BUCKETS_BY_TIMEFRAME:
        return _bar_interval_key(bar, timeframe=tf, metadata={})
    return _bar_time_key(bar)


def _bar_alignment_label(bar: Bar, *, timeframe: str) -> str:
    tf = validate_chart_timeframe(timeframe)
    if tf == "1D":
        return _bar_session_date(bar).isoformat()
    if tf == "1W":
        week_start, week_end = _canonical_week_bounds(_bar_session_date(bar))
        return f"{week_start.isoformat()}/{week_end.isoformat()}"
    if tf in RTH_BUCKETS_BY_TIMEFRAME:
        return _bar_interval_label(bar, timeframe=tf, metadata={})
    return _bar_time_key(bar)


def _bar_alignment_diagnostics(
    bar: Bar | None,
    *,
    timeframe: str,
    metadata: dict[str, object] | None = None,
    server_run_at: datetime | None = None,
) -> dict[str, object]:
    provider_metadata = metadata or {}
    if bar is None:
        return {
            "raw_provider_timestamp": None,
            "canonical_session_date": None,
            "canonical_trading_week": None,
            "timestamp_convention": None,
            "canonical_interval_start": None,
            "canonical_interval_end": None,
            "bar_completed": None,
            "bar_in_progress": None,
            "adjusted": None,
            "extended_hours": None,
            "aggregation_multiplier": None,
            "aggregation_timespan": None,
            "alignment_key": None,
            "alignment_label": None,
        }
    tf = validate_chart_timeframe(timeframe)
    session_date = _bar_session_date(bar)
    week_label = None
    if tf == "1W":
        week_start, week_end = _canonical_week_bounds(session_date)
        week_label = f"{week_start.isoformat()}/{week_end.isoformat()}"
    interval_start, interval_end, convention = _bar_interval_bounds(bar, timeframe=tf, metadata=provider_metadata)
    completed = _bar_is_completed(bar, timeframe=tf, metadata=provider_metadata, server_run_at=server_run_at)
    return {
        "raw_provider_timestamp": _bar_time_key(bar),
        "canonical_session_date": session_date.isoformat() if tf == "1D" else None,
        "canonical_trading_week": week_label,
        "timestamp_convention": convention,
        "canonical_interval_start": _timestamp_payload(interval_start),
        "canonical_interval_end": _timestamp_payload(interval_end),
        "bar_completed": completed,
        "bar_in_progress": None if completed is None else not completed,
        "adjusted": _metadata_value(provider_metadata, "adjusted", "not_reported"),
        "extended_hours": _metadata_value(provider_metadata, "needExtendedHoursData", "not_reported"),
        "aggregation_multiplier": _aggregation_multiplier(provider_metadata, timeframe=tf),
        "aggregation_timespan": _aggregation_timespan(provider_metadata, timeframe=tf),
        "alignment_key": _bar_comparison_key(bar, timeframe=tf, metadata=provider_metadata),
        "alignment_label": _bar_comparison_label(bar, timeframe=tf, metadata=provider_metadata),
    }


def _bar_sort_key(bar: Bar) -> tuple[datetime, str]:
    if bar.timestamp is not None:
        return bar.timestamp.astimezone(UTC), bar.date.isoformat()
    return datetime.combine(bar.date, datetime.min.time(), tzinfo=UTC), bar.date.isoformat()


def _bar_datetime(bar: Bar | None) -> datetime | None:
    if bar is None:
        return None
    return _bar_sort_key(bar)[0]


def _minute_of_day(value: datetime) -> int:
    local = value.astimezone(US_EQUITY_TIMEZONE)
    return local.hour * 60 + local.minute


def _market_session_state(value: datetime) -> str:
    local = value.astimezone(US_EQUITY_TIMEZONE)
    if local.weekday() >= 5:
        return "closed"
    minute = _minute_of_day(value)
    if PREMARKET_START_MINUTE <= minute < REGULAR_OPEN_MINUTE:
        return "premarket"
    if REGULAR_OPEN_MINUTE <= minute < REGULAR_CLOSE_MINUTE:
        return "regular"
    if REGULAR_CLOSE_MINUTE <= minute < AFTER_HOURS_END_MINUTE:
        return "after-hours"
    return "closed"


def _previous_weekday(day: date) -> date:
    candidate = day
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _expected_regular_session_day(run_time: datetime) -> date:
    local = run_time.astimezone(US_EQUITY_TIMEZONE)
    minute = _minute_of_day(run_time)
    if local.weekday() < 5 and minute >= REGULAR_OPEN_MINUTE:
        return local.date()
    return _previous_weekday(local.date() - timedelta(days=1))


def _session_timestamp(session_day: date, minute_of_day: int) -> datetime:
    local = datetime.combine(
        session_day,
        time(hour=minute_of_day // 60, minute=minute_of_day % 60),
        tzinfo=US_EQUITY_TIMEZONE,
    )
    return local.astimezone(UTC)


def _provider_name_from_metadata(metadata: dict[str, object], bar: Bar | None = None) -> str:
    provider = str(metadata.get("provider") or "").strip().lower()
    if provider:
        return provider
    if bar is not None:
        return str(bar.provider or "").strip().lower()
    return ""


def _inferred_timestamp_convention(bar: Bar | None, *, timeframe: str, metadata: dict[str, object]) -> str:
    tf = validate_chart_timeframe(timeframe)
    explicit = str(metadata.get("timestamp_convention") or "").strip().lower()
    if explicit in {"bar_start", "bar_end", "session_anchor", "unknown"}:
        return explicit
    if tf in {"1D", "1W"}:
        return "session_anchor"
    provider = _provider_name_from_metadata(metadata, bar)
    if tf in RTH_BUCKETS_BY_TIMEFRAME:
        if "schwab" in provider:
            return "bar_end"
        if "polygon" in provider or "massive" in provider:
            return "bar_start"
    return "unknown"


def _bucket_bounds_for_timestamp(
    timestamp: datetime,
    *,
    timeframe: str,
    convention_hint: str,
) -> tuple[date, int, int, str] | None:
    tf = validate_chart_timeframe(timeframe)
    buckets = RTH_BUCKETS_BY_TIMEFRAME.get(tf)
    if not buckets:
        return None
    local = timestamp.astimezone(US_EQUITY_TIMEZONE)
    minute = local.hour * 60 + local.minute
    start_matches = [(start, end) for start, end in buckets if minute == start]
    end_matches = [(start, end) for start, end in buckets if minute == end]
    interior_matches = [(start, end) for start, end in buckets if start < minute < end]

    if convention_hint == "bar_end" and end_matches:
        start, end = end_matches[0]
        return local.date(), start, end, "bar_end"
    if convention_hint == "bar_start" and start_matches:
        start, end = start_matches[-1]
        return local.date(), start, end, "bar_start"
    if start_matches and not end_matches:
        start, end = start_matches[-1]
        return local.date(), start, end, "bar_start"
    if end_matches and not start_matches:
        start, end = end_matches[0]
        return local.date(), start, end, "bar_end"
    if convention_hint == "bar_end" and interior_matches:
        start, end = interior_matches[0]
        return local.date(), start, end, "unknown"
    if interior_matches:
        start, end = interior_matches[0]
        return local.date(), start, end, "unknown"
    if start_matches:
        start, end = start_matches[-1]
        return local.date(), start, end, "bar_start"
    if end_matches:
        start, end = end_matches[0]
        return local.date(), start, end, "bar_end"
    return None


def _nominal_intraday_minutes(timeframe: str) -> int:
    tf = validate_chart_timeframe(timeframe)
    if tf == "30M":
        return 30
    if tf == "1H":
        return 60
    if tf == "4H":
        return 240
    return 0


def _bar_interval_bounds(
    bar: Bar,
    *,
    timeframe: str,
    metadata: dict[str, object],
) -> tuple[datetime | None, datetime | None, str]:
    tf = validate_chart_timeframe(timeframe)
    timestamp = _bar_datetime(bar)
    convention = _inferred_timestamp_convention(bar, timeframe=tf, metadata=metadata)
    if tf == "1D":
        session_day = _bar_session_date(bar)
        return _session_timestamp(session_day, REGULAR_OPEN_MINUTE), _session_timestamp(session_day, REGULAR_CLOSE_MINUTE), "session_anchor"
    if tf == "1W":
        week_start, week_end = _canonical_week_bounds(_bar_session_date(bar))
        return _session_timestamp(week_start, REGULAR_OPEN_MINUTE), _session_timestamp(week_end, REGULAR_CLOSE_MINUTE), "session_anchor"
    if timestamp is None:
        return None, None, convention
    if tf in RTH_BUCKETS_BY_TIMEFRAME:
        bucket = _bucket_bounds_for_timestamp(timestamp, timeframe=tf, convention_hint=convention)
        if bucket is not None:
            session_day, start_minute, end_minute, inferred = bucket
            return _session_timestamp(session_day, start_minute), _session_timestamp(session_day, end_minute), inferred
        duration = _nominal_intraday_minutes(tf)
        if duration > 0 and convention == "bar_end":
            return timestamp - timedelta(minutes=duration), timestamp, convention
        if duration > 0:
            return timestamp, timestamp + timedelta(minutes=duration), convention
    return timestamp, timestamp, convention


def _bar_interval_key(bar: Bar, *, timeframe: str, metadata: dict[str, object]) -> str:
    start, end, _convention = _bar_interval_bounds(bar, timeframe=timeframe, metadata=metadata)
    if start is None or end is None:
        return _bar_time_key(bar)
    return f"interval:{start.astimezone(UTC).isoformat()}/{end.astimezone(UTC).isoformat()}"


def _bar_interval_label(bar: Bar, *, timeframe: str, metadata: dict[str, object]) -> str:
    start, end, _convention = _bar_interval_bounds(bar, timeframe=timeframe, metadata=metadata)
    if start is None or end is None:
        return _bar_time_key(bar)
    start_local = start.astimezone(US_EQUITY_TIMEZONE)
    end_local = end.astimezone(US_EQUITY_TIMEZONE)
    if start_local.date() == end_local.date():
        return (
            f"{start_local.date().isoformat()} "
            f"{start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')} ET"
        )
    return f"{start_local.isoformat()}/{end_local.isoformat()}"


def _bar_comparison_key(bar: Bar, *, timeframe: str, metadata: dict[str, object]) -> str:
    tf = validate_chart_timeframe(timeframe)
    if tf == "1D":
        return f"session:{_bar_session_date(bar).isoformat()}"
    if tf == "1W":
        week_start, week_end = _canonical_week_bounds(_bar_session_date(bar))
        return f"week:{week_start.isoformat()}/{week_end.isoformat()}"
    if tf in RTH_BUCKETS_BY_TIMEFRAME:
        return _bar_interval_key(bar, timeframe=tf, metadata=metadata)
    return _bar_time_key(bar)


def _bar_comparison_label(bar: Bar, *, timeframe: str, metadata: dict[str, object]) -> str:
    tf = validate_chart_timeframe(timeframe)
    if tf == "1D":
        return _bar_session_date(bar).isoformat()
    if tf == "1W":
        week_start, week_end = _canonical_week_bounds(_bar_session_date(bar))
        return f"{week_start.isoformat()}/{week_end.isoformat()}"
    if tf in RTH_BUCKETS_BY_TIMEFRAME:
        return _bar_interval_label(bar, timeframe=tf, metadata=metadata)
    return _bar_time_key(bar)


def _bar_is_completed(
    bar: Bar | None,
    *,
    timeframe: str,
    metadata: dict[str, object],
    server_run_at: datetime | None,
) -> bool | None:
    if bar is None:
        return None
    if server_run_at is None:
        return None
    _start, end, _convention = _bar_interval_bounds(bar, timeframe=timeframe, metadata=metadata)
    if end is None:
        return None
    return end.astimezone(UTC) <= server_run_at.astimezone(UTC)


def _filter_completed_bars(
    bars: list[Bar],
    *,
    timeframe: str,
    metadata: dict[str, object],
    server_run_at: datetime,
    completed_bars_only: bool,
) -> tuple[list[Bar], int]:
    if not completed_bars_only:
        return bars, 0
    completed: list[Bar] = []
    filtered = 0
    for bar in bars:
        is_completed = _bar_is_completed(bar, timeframe=timeframe, metadata=metadata, server_run_at=server_run_at)
        if is_completed is False:
            filtered += 1
            continue
        completed.append(bar)
    return completed, filtered


def _aggregation_multiplier(metadata: dict[str, object], *, timeframe: str) -> object:
    multiplier = _metadata_value(metadata, "request_multiplier")
    if multiplier is not None:
        return multiplier
    frequency = _metadata_value(metadata, "request_frequency")
    if frequency is not None:
        return frequency
    tf = validate_chart_timeframe(timeframe)
    if tf == "30M":
        return 30
    if tf == "1H":
        return 1
    if tf == "4H":
        return 4
    return 1


def _aggregation_timespan(metadata: dict[str, object], *, timeframe: str) -> object:
    timespan = _metadata_value(metadata, "request_timespan")
    if timespan is not None:
        return timespan
    frequency_type = _metadata_value(metadata, "request_frequency_type")
    if frequency_type is not None:
        return frequency_type
    tf = validate_chart_timeframe(timeframe)
    if tf in RTH_BUCKETS_BY_TIMEFRAME:
        return "minute"
    if tf == "1D":
        return "day"
    if tf == "1W":
        return "week"
    return "unknown"


def _expected_latest_market_bar_timestamp(timeframe: str, run_time: datetime) -> datetime | None:
    tf = validate_chart_timeframe(timeframe)
    local = run_time.astimezone(US_EQUITY_TIMEZONE)
    minute = _minute_of_day(run_time)
    session_state = _market_session_state(run_time)
    if tf in RTH_BUCKETS_BY_TIMEFRAME:
        buckets = RTH_BUCKETS_BY_TIMEFRAME[tf]
        if not buckets:
            return None
        if session_state == "regular":
            start_minute = buckets[0][0]
            for bucket_start, bucket_end in buckets:
                if bucket_start <= minute < bucket_end:
                    start_minute = bucket_start
                    break
            return _session_timestamp(local.date(), start_minute)
        if local.weekday() < 5 and minute >= REGULAR_CLOSE_MINUTE:
            return _session_timestamp(local.date(), buckets[-1][0])
        return _session_timestamp(_previous_weekday(local.date() - timedelta(days=1)), buckets[-1][0])
    expected_day = _expected_regular_session_day(run_time)
    if tf == "1W":
        expected_day -= timedelta(days=expected_day.weekday())
    return datetime.combine(expected_day, datetime.min.time(), tzinfo=UTC)


def _timestamp_payload(value: datetime | None) -> dict[str, object]:
    if value is None:
        return {
            "utc": None,
            "new_york": None,
            "market_session_state": None,
        }
    utc_value = value.astimezone(UTC)
    return {
        "utc": utc_value.isoformat(),
        "new_york": utc_value.astimezone(US_EQUITY_TIMEZONE).isoformat(),
        "market_session_state": _market_session_state(utc_value),
    }


def _minutes_delta(start: datetime | None, end: datetime | None, *, absolute: bool = False) -> float | None:
    if start is None or end is None:
        return None
    delta = (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds() / 60.0
    if absolute:
        delta = abs(delta)
    return round(delta, 3)


def _freshness_classification(
    latest: datetime | None,
    *,
    expected_latest: datetime | None,
    timeframe: str,
    session_state: str,
) -> tuple[str, str]:
    if latest is None or expected_latest is None:
        return "not_comparable", "missing_latest_or_expected_timestamp"
    lag_minutes = _minutes_delta(latest, expected_latest)
    if lag_minutes is None:
        return "not_comparable", "missing_lag_measure"
    tolerance = FRESHNESS_REAL_TIME_TOLERANCE_MINUTES.get(validate_chart_timeframe(timeframe), 5.0)
    if abs(lag_minutes) <= tolerance:
        return "real_time_like", "latest_bar_within_expected_market_bar_tolerance"
    if lag_minutes < -tolerance:
        return "not_comparable", "provider_timestamp_is_ahead_of_expected_market_bar"
    if (
        session_state == "regular"
        and abs(lag_minutes - FRESHNESS_DELAY_TARGET_MINUTES) <= FRESHNESS_DELAY_TOLERANCE_MINUTES
    ):
        return "delayed_15_min_like", "latest_bar_lags_expected_market_bar_by_about_15_minutes"
    return "stale", "latest_bar_outside_expected_market_bar_tolerance"


def _provider_freshness_payload(
    latest: datetime | None,
    *,
    expected_latest: datetime | None,
    server_run_at: datetime,
    timeframe: str,
    session_state: str,
) -> dict[str, object]:
    classification, reason = _freshness_classification(
        latest,
        expected_latest=expected_latest,
        timeframe=timeframe,
        session_state=session_state,
    )
    return {
        "latest_bar_timestamp": _timestamp_payload(latest),
        "provider_lag_minutes_vs_server_run_time": _minutes_delta(latest, server_run_at),
        "provider_lag_minutes_vs_expected_latest_market_bar": _minutes_delta(latest, expected_latest),
        "classification": classification,
        "reason": reason,
    }


def _verdict_reason(
    verdict: str,
    *,
    aligned_count: int,
    latest_timestamp_delta_seconds: float | None,
    latest_timestamp_tolerance_seconds: int,
    material_price: bool,
    material_volume: bool,
    alignment_mode: str,
) -> str:
    if verdict == "match":
        return "bars_aligned_and_values_within_tolerance"
    if verdict == "no_bars":
        return "one_or_both_providers_returned_no_bars"
    if verdict == "no_aligned_bars":
        if alignment_mode == "normalized_session_date":
            return "providers_returned_bars_but_no_session_dates_overlap"
        if alignment_mode == "normalized_trading_week":
            return "providers_returned_bars_but_no_canonical_trading_weeks_overlap"
        if alignment_mode == "canonical_intraday_interval":
            return "providers_returned_bars_but_no_canonical_intraday_intervals_overlap"
        return "providers_returned_bars_but_no_timestamps_overlap"
    if verdict == "stale_source":
        delta_minutes = latest_timestamp_delta_seconds / 60.0 if latest_timestamp_delta_seconds is not None else None
        tolerance_minutes = latest_timestamp_tolerance_seconds / 60.0
        return (
            f"provider_latest_timestamps_differ_by_{round(delta_minutes, 3)}_minutes_beyond_{round(tolerance_minutes, 3)}_minute_tolerance"
            if delta_minutes is not None
            else "provider_latest_timestamp_unavailable_for_stale_source_check"
        )
    if verdict == "insufficient_data":
        return f"only_{aligned_count}_aligned_timestamps_available"
    if verdict in {"comparable_raw_mismatch", "comparable_normalized_mismatch"}:
        reasons: list[str] = []
        if material_price:
            reasons.append("price_delta_exceeded_tolerance")
        if material_volume:
            reasons.append("volume_delta_exceeded_tolerance")
        return ",".join(reasons) or "aligned_values_exceeded_tolerance"
    return verdict


def _comparison_freshness(
    *,
    latest_current: Bar | None,
    latest_candidate: Bar | None,
    latest_common_current: Bar | None,
    latest_common_alignment_key: str | None,
    latest_common_alignment_label: str | None,
    alignment_mode: str,
    timeframe: str,
    server_run_at: datetime,
    verdict: str,
    verdict_reason: str,
) -> dict[str, object]:
    session_state = _market_session_state(server_run_at)
    expected_latest = _expected_latest_market_bar_timestamp(timeframe, server_run_at)
    current_latest = _bar_datetime(latest_current)
    candidate_latest = _bar_datetime(latest_candidate)
    latest_common = _bar_datetime(latest_common_current)
    current = _provider_freshness_payload(
        current_latest,
        expected_latest=expected_latest,
        server_run_at=server_run_at,
        timeframe=timeframe,
        session_state=session_state,
    )
    candidate = _provider_freshness_payload(
        candidate_latest,
        expected_latest=expected_latest,
        server_run_at=server_run_at,
        timeframe=timeframe,
        session_state=session_state,
    )
    classifications = {str(current.get("classification")), str(candidate.get("classification"))}
    if "not_comparable" in classifications:
        classification = "not_comparable"
    elif "stale" in classifications:
        classification = "stale"
    elif "delayed_15_min_like" in classifications:
        classification = "delayed_15_min_like"
    else:
        classification = "real_time_like"
    return {
        "server_run_time": _timestamp_payload(server_run_at),
        "market_session_state": session_state,
        "expected_latest_market_bar": _timestamp_payload(expected_latest),
        "current": current,
        "candidate": candidate,
        "latest_bar_timestamp_current": _timestamp_payload(current_latest),
        "latest_bar_timestamp_candidate": _timestamp_payload(candidate_latest),
        "latest_common_aligned_timestamp": _timestamp_payload(latest_common),
        "latest_common_alignment_key": latest_common_alignment_key,
        "latest_common_alignment_label": latest_common_alignment_label,
        "alignment_mode": alignment_mode,
        "timestamp_delta_minutes": _minutes_delta(current_latest, candidate_latest, absolute=True),
        "classification": classification,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "delay_measurement_basis": "timestamp_only_regular_hours_weekday_model",
    }


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
        "timestamp_convention": "bar_start" if timeframe.upper() in RTH_BUCKETS_BY_TIMEFRAME else "session_anchor",
        "aggregation_multiplier": _aggregation_multiplier({"provider": provider}, timeframe=timeframe),
        "aggregation_timespan": _aggregation_timespan({"provider": provider}, timeframe=timeframe),
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


def _latest_timestamp_delta_seconds(current: Bar | None, candidate: Bar | None) -> float | None:
    if current is None or candidate is None:
        return None
    current_time = _bar_sort_key(current)[0]
    candidate_time = _bar_sort_key(candidate)[0]
    return abs((current_time - candidate_time).total_seconds())


def _latest_timestamp_tolerance_seconds(timeframe: str) -> int:
    return LATEST_TIMESTAMP_TOLERANCE_SECONDS.get(validate_chart_timeframe(timeframe), 60 * 60)


def _bar_delta_payload(
    current: Bar,
    candidate: Bar,
    *,
    timeframe: str,
    alignment_key: str,
    alignment_mode: str,
    current_metadata: dict[str, object],
    candidate_metadata: dict[str, object],
    server_run_at: datetime,
) -> dict[str, object]:
    deltas = {
        "open": round(abs(float(current.open) - float(candidate.open)), 6),
        "high": round(abs(float(current.high) - float(candidate.high)), 6),
        "low": round(abs(float(current.low) - float(candidate.low)), 6),
        "close": round(abs(float(current.close) - float(candidate.close)), 6),
        "volume": round(abs(float(current.volume) - float(candidate.volume)), 6),
    }
    current_interval_start, current_interval_end, current_convention = _bar_interval_bounds(
        current,
        timeframe=timeframe,
        metadata=current_metadata,
    )
    candidate_interval_start, candidate_interval_end, candidate_convention = _bar_interval_bounds(
        candidate,
        timeframe=timeframe,
        metadata=candidate_metadata,
    )
    return {
        "timestamp": _bar_time_key(current),
        "alignment_key": alignment_key,
        "alignment_label": _bar_comparison_label(current, timeframe=timeframe, metadata=current_metadata),
        "alignment_mode": alignment_mode,
        "canonical_interval_start": _timestamp_payload(current_interval_start),
        "canonical_interval_end": _timestamp_payload(current_interval_end),
        "current_timestamp_convention": current_convention,
        "candidate_timestamp_convention": candidate_convention,
        "current_bar_completed": _bar_is_completed(
            current,
            timeframe=timeframe,
            metadata=current_metadata,
            server_run_at=server_run_at,
        ),
        "candidate_bar_completed": _bar_is_completed(
            candidate,
            timeframe=timeframe,
            metadata=candidate_metadata,
            server_run_at=server_run_at,
        ),
        "current_raw_provider_timestamp": _bar_time_key(current),
        "candidate_raw_provider_timestamp": _bar_time_key(candidate),
        "current_alignment": _bar_alignment_diagnostics(
            current,
            timeframe=timeframe,
            metadata=current_metadata,
            server_run_at=server_run_at,
        ),
        "candidate_alignment": _bar_alignment_diagnostics(
            candidate,
            timeframe=timeframe,
            metadata=candidate_metadata,
            server_run_at=server_run_at,
        ),
        "current": _json_safe_bar(current),
        "candidate": _json_safe_bar(candidate),
        "deltas": deltas,
    }


def _filter_bars_to_alignment_keys(
    bars: list[Bar],
    keys: set[str],
    *,
    timeframe: str,
    metadata: dict[str, object],
) -> list[Bar]:
    return [
        bar
        for bar in sorted(bars, key=_bar_sort_key)
        if _bar_comparison_key(bar, timeframe=timeframe, metadata=metadata) in keys
    ]


def _normalize_indicator_bars_for_alignment(
    bars: list[Bar],
    *,
    timeframe: str,
    metadata: dict[str, object],
) -> list[Bar]:
    tf = validate_chart_timeframe(timeframe)
    if _bar_alignment_mode(tf) == "exact_timestamp":
        return sorted(bars, key=_bar_sort_key)

    normalized: list[Bar] = []
    for bar in sorted(bars, key=_bar_sort_key):
        if tf == "1W":
            canonical_date, _week_end = _canonical_week_bounds(_bar_session_date(bar))
            timestamp = datetime.combine(canonical_date, time.min, tzinfo=UTC)
        elif tf in RTH_BUCKETS_BY_TIMEFRAME:
            interval_start, _interval_end, _convention = _bar_interval_bounds(bar, timeframe=tf, metadata=metadata)
            timestamp = interval_start or _bar_datetime(bar) or datetime.combine(_bar_session_date(bar), time.min, tzinfo=UTC)
            canonical_date = timestamp.astimezone(US_EQUITY_TIMEZONE).date()
        else:
            canonical_date = _bar_session_date(bar)
            timestamp = datetime.combine(canonical_date, time.min, tzinfo=UTC)
        normalized.append(
            Bar(
                date=canonical_date,
                timestamp=timestamp.astimezone(UTC),
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                rel_volume=bar.rel_volume,
                session_policy=bar.session_policy,
                source_session_policy=bar.source_session_policy,
                source_timeframe=bar.source_timeframe,
                provider=bar.provider,
            )
        )
    return normalized


def _metadata_value(metadata: dict[str, object], key: str, default: object = None) -> object:
    if key in metadata:
        return metadata.get(key)
    request_query = metadata.get("request_query")
    if isinstance(request_query, dict) and key in request_query:
        return request_query.get(key)
    return default


def _comparison_diagnostics(
    *,
    timeframe: str,
    alignment_mode: str,
    latest_alignment_key_match: bool,
    current_metadata: dict[str, object],
    candidate_metadata: dict[str, object],
    material_price: bool,
    material_volume: bool,
) -> dict[str, object]:
    tf = validate_chart_timeframe(timeframe)
    current_adjusted = _metadata_value(current_metadata, "adjusted", "not_reported")
    candidate_adjusted = _metadata_value(candidate_metadata, "adjusted", "provider_default")
    current_extended = _metadata_value(current_metadata, "needExtendedHoursData", "not_reported")
    candidate_extended = _metadata_value(candidate_metadata, "needExtendedHoursData", "false")
    current_boundaries = list(current_metadata.get("rth_bucket_boundaries") or [])
    candidate_boundaries = list(candidate_metadata.get("rth_bucket_boundaries") or [])
    notes: list[str] = []
    if tf in RTH_BUCKETS_BY_TIMEFRAME:
        if current_boundaries and candidate_boundaries and current_boundaries == candidate_boundaries:
            notes.append("macmarket_regular_hours_bucket_boundaries_match")
        elif current_boundaries or candidate_boundaries:
            notes.append("aggregation_window_boundary_difference_possible")
        if str(current_extended).lower() in {"false", "0", "no"} and str(candidate_extended).lower() in {"false", "0", "no"}:
            notes.append("extended_hours_not_an_obvious_cause")
        if str(current_adjusted).lower() != str(candidate_adjusted).lower():
            notes.append("adjusted_mode_difference_possible")
        if latest_alignment_key_match and (material_price or material_volume):
            notes.append("canonical_intervals_align_so_remaining_ohlcv_difference_is_provider_data_or_adjustment_related")
    return {
        "alignment_mode": alignment_mode,
        "latest_alignment_key_match": latest_alignment_key_match,
        "current_adjusted": current_adjusted,
        "candidate_adjusted": candidate_adjusted,
        "current_extended_hours_flag": current_extended,
        "candidate_extended_hours_flag": candidate_extended,
        "current_timestamp_convention": _metadata_value(current_metadata, "timestamp_convention", "inferred_from_provider"),
        "candidate_timestamp_convention": _metadata_value(candidate_metadata, "timestamp_convention", "inferred_from_provider"),
        "current_aggregation_multiplier": _aggregation_multiplier(current_metadata, timeframe=tf),
        "candidate_aggregation_multiplier": _aggregation_multiplier(candidate_metadata, timeframe=tf),
        "current_aggregation_timespan": _aggregation_timespan(current_metadata, timeframe=tf),
        "candidate_aggregation_timespan": _aggregation_timespan(candidate_metadata, timeframe=tf),
        "current_session_policy": current_metadata.get("session_policy"),
        "candidate_session_policy": candidate_metadata.get("session_policy"),
        "current_source_timeframe": current_metadata.get("source_timeframe"),
        "candidate_source_timeframe": candidate_metadata.get("source_timeframe"),
        "current_rth_bucket_boundaries": current_boundaries,
        "candidate_rth_bucket_boundaries": candidate_boundaries,
        "notes": notes,
    }


def _compare_bars(
    current: list[Bar],
    candidate: list[Bar],
    *,
    current_metadata: dict[str, object],
    candidate_metadata: dict[str, object],
    timeframe: str,
    mismatch_verdict: str,
    server_run_at: datetime,
    completed_bars_only: bool,
) -> dict[str, object]:
    tf = validate_chart_timeframe(timeframe)
    alignment_mode = _bar_alignment_mode(tf)
    input_ordered_current = sorted(current, key=_bar_sort_key)
    input_ordered_candidate = sorted(candidate, key=_bar_sort_key)
    ordered_current, filtered_current = _filter_completed_bars(
        input_ordered_current,
        timeframe=tf,
        metadata=current_metadata,
        server_run_at=server_run_at,
        completed_bars_only=completed_bars_only,
    )
    ordered_candidate, filtered_candidate = _filter_completed_bars(
        input_ordered_candidate,
        timeframe=tf,
        metadata=candidate_metadata,
        server_run_at=server_run_at,
        completed_bars_only=completed_bars_only,
    )
    current_by_key = {_bar_comparison_key(bar, timeframe=tf, metadata=current_metadata): bar for bar in ordered_current}
    candidate_by_key = {_bar_comparison_key(bar, timeframe=tf, metadata=candidate_metadata): bar for bar in ordered_candidate}
    current_keys = set(current_by_key)
    candidate_keys = set(candidate_by_key)
    aligned = sorted(current_keys & candidate_keys)
    missing_on_current = sorted(candidate_keys - current_keys)
    missing_on_candidate = sorted(current_keys - candidate_keys)
    latest_input_current = input_ordered_current[-1] if input_ordered_current else None
    latest_input_candidate = input_ordered_candidate[-1] if input_ordered_candidate else None
    latest_current = ordered_current[-1] if ordered_current else None
    latest_candidate = ordered_candidate[-1] if ordered_candidate else None
    latest_timestamp_delta_seconds = _latest_timestamp_delta_seconds(latest_current, latest_candidate)
    latest_timestamp_tolerance_seconds = _latest_timestamp_tolerance_seconds(timeframe)
    latest_is_stale = (
        latest_timestamp_delta_seconds is not None
        and latest_timestamp_delta_seconds > latest_timestamp_tolerance_seconds
    )
    latest_current_alignment_key = _bar_comparison_key(latest_current, timeframe=tf, metadata=current_metadata) if latest_current else None
    latest_candidate_alignment_key = _bar_comparison_key(latest_candidate, timeframe=tf, metadata=candidate_metadata) if latest_candidate else None
    latest_alignment_key_match = bool(
        latest_current_alignment_key
        and latest_candidate_alignment_key
        and latest_current_alignment_key == latest_candidate_alignment_key
    )

    max_price_delta = 0.0
    max_price_field: str | None = None
    max_volume_delta = 0.0
    for key in aligned:
        left = current_by_key[key]
        right = candidate_by_key[key]
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
            left = current_by_key[key]
            right = candidate_by_key[key]
            for field in ("open", "high", "low", "close"):
                delta = abs(float(getattr(left, field)) - float(getattr(right, field)))
                if delta > _max_price_allowed(float(getattr(left, field))):
                    material_price = True
            allowed_volume_delta = max(0.0, abs(float(left.volume)) * VOLUME_REL_TOLERANCE)
            if abs(float(left.volume) - float(right.volume)) > allowed_volume_delta:
                material_volume = True
    if not ordered_current or not ordered_candidate:
        verdict = "no_bars"
    elif not aligned:
        verdict = "stale_source" if latest_is_stale else "no_aligned_bars"
    elif latest_is_stale:
        verdict = "stale_source"
    elif len(aligned) < 2:
        verdict = "insufficient_data"
    elif material_price or material_volume:
        verdict = mismatch_verdict
    else:
        verdict = "match"
    verdict_reason = _verdict_reason(
        verdict,
        aligned_count=len(aligned),
        latest_timestamp_delta_seconds=latest_timestamp_delta_seconds,
        latest_timestamp_tolerance_seconds=latest_timestamp_tolerance_seconds,
        material_price=material_price,
        material_volume=material_volume,
        alignment_mode=alignment_mode,
    )
    latest_common_key = aligned[-1] if aligned else None
    latest_common_current = current_by_key[latest_common_key] if latest_common_key else None
    latest_common_candidate = candidate_by_key[latest_common_key] if latest_common_key else None
    latest_common_alignment_label = (
        _bar_comparison_label(latest_common_current, timeframe=tf, metadata=current_metadata)
        if latest_common_current is not None
        else None
    )
    latest_delta = (
        _bar_delta_payload(
            latest_common_current,
            latest_common_candidate,
            timeframe=tf,
            alignment_key=latest_common_key,
            alignment_mode=alignment_mode,
            current_metadata=current_metadata,
            candidate_metadata=candidate_metadata,
            server_run_at=server_run_at,
        )["deltas"]
        if latest_common_current and latest_common_candidate
        else {}
    )
    aligned_rows = [
        _bar_delta_payload(
            current_by_key[key],
            candidate_by_key[key],
            timeframe=tf,
            alignment_key=key,
            alignment_mode=alignment_mode,
            current_metadata=current_metadata,
            candidate_metadata=candidate_metadata,
            server_run_at=server_run_at,
        )
        for key in aligned[-25:]
    ]
    freshness = _comparison_freshness(
        latest_current=latest_current,
        latest_candidate=latest_candidate,
        latest_common_current=latest_common_current,
        latest_common_alignment_key=latest_common_key,
        latest_common_alignment_label=latest_common_alignment_label,
        alignment_mode=alignment_mode,
        timeframe=timeframe,
        server_run_at=server_run_at,
        verdict=verdict,
        verdict_reason=verdict_reason,
    )
    freshness["latest_input_bar_timestamp_current"] = _timestamp_payload(_bar_datetime(latest_input_current))
    freshness["latest_input_bar_timestamp_candidate"] = _timestamp_payload(_bar_datetime(latest_input_candidate))
    freshness["latest_input_current_alignment"] = _bar_alignment_diagnostics(
        latest_input_current,
        timeframe=tf,
        metadata=current_metadata,
        server_run_at=server_run_at,
    )
    freshness["latest_input_candidate_alignment"] = _bar_alignment_diagnostics(
        latest_input_candidate,
        timeframe=tf,
        metadata=candidate_metadata,
        server_run_at=server_run_at,
    )
    freshness["latest_compared_current_alignment"] = _bar_alignment_diagnostics(
        latest_current,
        timeframe=tf,
        metadata=current_metadata,
        server_run_at=server_run_at,
    )
    freshness["latest_compared_candidate_alignment"] = _bar_alignment_diagnostics(
        latest_candidate,
        timeframe=tf,
        metadata=candidate_metadata,
        server_run_at=server_run_at,
    )
    comparison_diagnostics = _comparison_diagnostics(
        timeframe=tf,
        alignment_mode=alignment_mode,
        latest_alignment_key_match=latest_alignment_key_match,
        current_metadata=current_metadata,
        candidate_metadata=candidate_metadata,
        material_price=material_price,
        material_volume=material_volume,
    )
    alignment_failure_reason = None
    if not aligned and ordered_current and ordered_candidate:
        alignment_failure_reason = (
            f"no_common_alignment_keys_for_{alignment_mode};"
            f"latest_current={latest_current_alignment_key};latest_candidate={latest_candidate_alignment_key}"
        )

    return {
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "is_comparable": verdict not in NOT_COMPARABLE_VERDICTS,
        "not_comparable_reason": verdict if verdict in NOT_COMPARABLE_VERDICTS else None,
        "alignment_mode": alignment_mode,
        "alignment_key_type": alignment_mode,
        "comparison_scope": "completed_bars_only" if completed_bars_only else "all_returned_bars",
        "completed_bars_only": completed_bars_only,
        "alignment_failure_reason": alignment_failure_reason,
        "input_bars_current": len(input_ordered_current),
        "input_bars_candidate": len(input_ordered_candidate),
        "filtered_in_progress_current_count": filtered_current,
        "filtered_in_progress_candidate_count": filtered_candidate,
        "bars_current": len(ordered_current),
        "bars_candidate": len(ordered_candidate),
        "aligned_timestamps": len(aligned),
        "aligned_timestamp_keys": aligned,
        "aligned_alignment_keys": aligned,
        "latest_common_timestamp": latest_common_key,
        "latest_common_alignment_key": latest_common_key,
        "latest_common_alignment_label": latest_common_alignment_label,
        "latest_common_current_raw_timestamp": _bar_time_key(latest_common_current) if latest_common_current else None,
        "latest_common_candidate_raw_timestamp": _bar_time_key(latest_common_candidate) if latest_common_candidate else None,
        "latest_input_current_raw_timestamp": _bar_time_key(latest_input_current) if latest_input_current else None,
        "latest_input_candidate_raw_timestamp": _bar_time_key(latest_input_candidate) if latest_input_candidate else None,
        "first_timestamp_current": _bar_time_key(ordered_current[0]) if ordered_current else None,
        "first_timestamp_candidate": _bar_time_key(ordered_candidate[0]) if ordered_candidate else None,
        "last_timestamp_current": _bar_time_key(latest_current) if latest_current else None,
        "last_timestamp_candidate": _bar_time_key(latest_candidate) if latest_candidate else None,
        "latest_timestamp_match": latest_timestamp_match,
        "latest_alignment_key_match": latest_alignment_key_match,
        "latest_input_current_alignment": _bar_alignment_diagnostics(
            latest_input_current,
            timeframe=tf,
            metadata=current_metadata,
            server_run_at=server_run_at,
        ),
        "latest_input_candidate_alignment": _bar_alignment_diagnostics(
            latest_input_candidate,
            timeframe=tf,
            metadata=candidate_metadata,
            server_run_at=server_run_at,
        ),
        "latest_current_alignment": _bar_alignment_diagnostics(
            latest_current,
            timeframe=tf,
            metadata=current_metadata,
            server_run_at=server_run_at,
        ),
        "latest_candidate_alignment": _bar_alignment_diagnostics(
            latest_candidate,
            timeframe=tf,
            metadata=candidate_metadata,
            server_run_at=server_run_at,
        ),
        "latest_timestamp_delta_seconds": round(latest_timestamp_delta_seconds, 3) if latest_timestamp_delta_seconds is not None else None,
        "latest_timestamp_tolerance_seconds": latest_timestamp_tolerance_seconds,
        "latest_input_current": _json_safe_bar(latest_input_current),
        "latest_input_candidate": _json_safe_bar(latest_input_candidate),
        "latest_current": _json_safe_bar(latest_current),
        "latest_candidate": _json_safe_bar(latest_candidate),
        "latest_common_current": _json_safe_bar(latest_common_current),
        "latest_common_candidate": _json_safe_bar(latest_common_candidate),
        "latest_delta": latest_delta,
        "aligned_rows": aligned_rows,
        "freshness": freshness,
        "current_as_of": freshness["current"],
        "candidate_as_of": freshness["candidate"],
        "max_price_delta": round(max_price_delta, 6),
        "max_price_delta_field": max_price_field,
        "price_absolute_tolerance": PRICE_ABS_TOLERANCE,
        "price_relative_tolerance": PRICE_REL_TOLERANCE,
        "max_volume_delta": round(max_volume_delta, 6),
        "volume_relative_tolerance": VOLUME_REL_TOLERANCE,
        "missing_timestamps_current": missing_on_current[:50],
        "extra_timestamps_current": missing_on_candidate[:50],
        "missing_alignment_keys_current": missing_on_current[:50],
        "extra_alignment_keys_current": missing_on_candidate[:50],
        "missing_timestamps_current_count": len(missing_on_current),
        "extra_timestamps_current_count": len(missing_on_candidate),
        "comparison_diagnostics": comparison_diagnostics,
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
        provider = str(annotated.get("provider") or "").lower()
        if "schwab" in provider:
            annotated.setdefault("timestamp_convention", "bar_end")
        elif "polygon" in provider or "massive" in provider:
            annotated.setdefault("timestamp_convention", "bar_start")
        else:
            annotated.setdefault("timestamp_convention", "unknown")
        annotated.setdefault("aggregation_multiplier", _aggregation_multiplier(annotated, timeframe=source_timeframe))
        annotated.setdefault("aggregation_timespan", _aggregation_timespan(annotated, timeframe=source_timeframe))
    if requested_timeframe.upper() == "1W":
        annotated.setdefault("weekly_anchor", "provider_weekly_frequency")
        annotated.setdefault("timestamp_convention", "session_anchor")
        annotated.setdefault("aggregation_multiplier", _aggregation_multiplier(annotated, timeframe=source_timeframe))
        annotated.setdefault("aggregation_timespan", _aggregation_timespan(annotated, timeframe=source_timeframe))
    if requested_timeframe.upper() == "1D":
        annotated.setdefault("timestamp_convention", "session_anchor")
        annotated.setdefault("aggregation_multiplier", _aggregation_multiplier(annotated, timeframe=source_timeframe))
        annotated.setdefault("aggregation_timespan", _aggregation_timespan(annotated, timeframe=source_timeframe))
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
    rows: list[dict[str, object]] = []
    for field, current_value in current_values.items():
        candidate_value = candidate_values.get(field)
        if current_value is None and candidate_value is None:
            continue
        delta = _numeric_delta(current_value, candidate_value)
        if delta is not None:
            tolerance = _max_price_allowed(float(current_value or 0.0))
            row_verdict = "match" if delta <= tolerance else "comparable_indicator_mismatch"
            row = {
                "field": field,
                "current": current_value,
                "candidate": candidate_value,
                "delta": round(delta, 6),
                "tolerance": round(tolerance, 6),
                "verdict": row_verdict,
            }
            rows.append(row)
            if row_verdict != "match":
                mismatches.append(row)
        elif str(current_value or "").upper() != str(candidate_value or "").upper():
            row = {
                "field": field,
                "current": current_value,
                "candidate": candidate_value,
                "delta": None,
                "tolerance": "exact",
                "verdict": "comparable_indicator_mismatch",
            }
            rows.append(row)
            mismatches.append(row)
        else:
            rows.append(
                {
                    "field": field,
                    "current": current_value,
                    "candidate": candidate_value,
                    "delta": 0,
                    "tolerance": "exact",
                    "verdict": "match",
                }
            )
    return {
        "verdict": "comparable_indicator_mismatch" if mismatches else "match",
        "is_comparable": True,
        "mismatches": mismatches,
        "rows": rows,
        "current": current,
        "candidate": candidate,
    }


def _indicators_not_compared(reason: str) -> dict[str, object]:
    return {
        "verdict": "not_compared",
        "is_comparable": False,
        "not_comparable_reason": reason,
        "mismatches": [],
        "rows": [],
        "current": {},
        "candidate": {},
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
        self.legacy_polygon_provider = PolygonMarketDataProvider() if cfg.polygon_api_key.strip() else None

    def _current_provider_name(self) -> str:
        if self._current_provider_is_schwab() and self.legacy_polygon_provider is not None:
            return "polygon_legacy"
        provider = getattr(self.current_market_data_service, "_provider", None)
        return str(getattr(provider, "name", None) or "market_data")

    def _current_provider_is_schwab(self) -> bool:
        provider = getattr(self.current_market_data_service, "_provider", None)
        return str(getattr(provider, "name", "")).lower() == "schwab"

    def _schwab_primary_without_legacy_payload(
        self,
        *,
        symbols: list[str],
        timeframes: list[str],
        lookback: int,
        session_policy: str,
        include_extended: bool,
        completed_bars_only: bool,
        save_snapshot: bool,
        tos_reference_count: int,
        as_of: str,
        run_id: str,
        schwab_status: dict[str, object],
        app_user_id: int,
    ) -> dict[str, object]:
        message = (
            "Schwab/Thinkorswim is the primary market-data provider and no legacy "
            "Polygon/Massive API key is configured for cutover comparison."
        )
        response: dict[str, object] = {
            "runId": run_id,
            "asOf": as_of,
            "providers": {
                "current": {
                    "provider": "schwab_primary",
                    "status": getattr(self.current_market_data_service.provider_health(sample_symbol="SPY"), "status", "unknown"),
                    "productionProviderUnchanged": True,
                    "comparison_mode": "schwab_primary_no_legacy",
                },
                "candidate": schwab_status,
            },
            "request": {
                "symbols": symbols,
                "timeframes": timeframes,
                "lookbackBars": lookback,
                "sessionPolicy": session_policy,
                "includeExtendedHours": include_extended,
                "completedBarsOnly": completed_bars_only,
                "saveSnapshot": save_snapshot,
                "tosReferencesProvided": tos_reference_count,
            },
            "summary": {"total": 0, "match": 0},
            "results": [],
            "warnings": [message],
            "errors": [],
            "readOnly": True,
            "brokerRoutingEnabled": False,
            "productionProviderUnchanged": True,
            "comparisonMode": "schwab_primary_no_legacy",
        }
        sanitized_response = _sanitize_snapshot_payload(response)
        response = dict(sanitized_response) if isinstance(sanitized_response, dict) else response
        if save_snapshot and symbols:
            snapshot_request = _sanitize_snapshot_payload(response["request"])
            snapshot_response = _sanitize_snapshot_payload(response)
            self.snapshot_repo.create(
                app_user_id=app_user_id,
                run_id=run_id,
                request_json=dict(snapshot_request) if isinstance(snapshot_request, dict) else {},
                response_json=dict(snapshot_response) if isinstance(snapshot_response, dict) else {},
                provider_current="schwab_primary",
                provider_candidate="schwab",
            )
        return response

    def _fetch_current_raw(self, *, symbol: str, timeframe: str, limit: int) -> ProviderBars:
        provider = getattr(self.current_market_data_service, "_provider", None)
        warnings: list[str] = []
        source_timeframe = _raw_source_timeframe(timeframe)
        source_limit = _raw_source_limit(timeframe, limit)
        if self._current_provider_is_schwab() and self.legacy_polygon_provider is not None:
            provider = self.legacy_polygon_provider
            bars = provider.fetch_historical_bars(symbol=symbol, timeframe=source_timeframe, limit=source_limit)
            metadata = getattr(provider, "last_aggregate_request_metadata", None)
            warnings.append("primary_provider_is_schwab_using_legacy_polygon_for_cutover_comparison")
            return ProviderBars(
                bars=sorted(bars, key=_bar_sort_key),
                provider="polygon_legacy",
                fallback_mode=False,
                metadata=_annotate_raw_metadata(
                    dict(metadata) if isinstance(metadata, dict) else _metadata_from_bars(bars, provider="polygon_legacy", timeframe=source_timeframe, fallback_mode=False),
                    requested_timeframe=timeframe,
                    source_timeframe=source_timeframe,
                    source_limit=source_limit,
                ),
                warnings=warnings,
            )
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
        error_kind: str | None,
    ) -> str:
        token_status = str(schwab_status.get("token_status") or "")
        if token_status != "connected":
            return "auth_unavailable"
        if error:
            return "auth_unavailable" if error_kind == "auth" else "provider_unavailable"
        if raw is None or canonical is None or indicators is None:
            return "insufficient_data"
        for comparison in (raw, canonical):
            verdict = str(comparison.get("verdict") or "")
            if verdict in NOT_COMPARABLE_VERDICTS:
                return verdict
        if raw.get("verdict") == "comparable_raw_mismatch":
            return "comparable_raw_mismatch"
        if canonical.get("verdict") == "comparable_normalized_mismatch":
            return "comparable_normalized_mismatch"
        if indicators.get("verdict") == "comparable_indicator_mismatch":
            return "comparable_indicator_mismatch"
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
        completed_bars_only = bool(request.get("completedBarsOnly", True))
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
        run_at = _utc_now()
        as_of = run_at.isoformat()
        status_payload = _sanitize_snapshot_payload(schwab_connection_status(repo=self.oauth_repo, cfg=self.cfg))
        schwab_status = status_payload if isinstance(status_payload, dict) else {}
        if self._current_provider_is_schwab() and self.legacy_polygon_provider is None:
            return self._schwab_primary_without_legacy_payload(
                symbols=symbols,
                timeframes=timeframes,
                lookback=lookback,
                session_policy=session_policy,
                include_extended=include_extended,
                completed_bars_only=completed_bars_only,
                save_snapshot=save_snapshot,
                tos_reference_count=len(tos_by_key),
                as_of=as_of,
                run_id=run_id,
                schwab_status=schwab_status,
                app_user_id=app_user_id,
            )
        results: list[dict[str, object]] = []
        summary: dict[str, int] = {
            "total": 0,
            "match": 0,
            "provider_unavailable": 0,
            "auth_unavailable": 0,
            "no_bars": 0,
            "insufficient_data": 0,
            "stale_source": 0,
            "no_aligned_bars": 0,
            "comparable_raw_mismatch": 0,
            "comparable_normalized_mismatch": 0,
            "comparable_indicator_mismatch": 0,
            "tos_reference_mismatch": 0,
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
                item_error_kind: str | None = None
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
                        timeframe=_raw_source_timeframe(timeframe),
                        mismatch_verdict="comparable_raw_mismatch",
                        server_run_at=run_at,
                        completed_bars_only=completed_bars_only,
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
                        timeframe=timeframe,
                        mismatch_verdict="comparable_normalized_mismatch",
                        server_run_at=run_at,
                        completed_bars_only=completed_bars_only,
                    )
                    if canonical_comparison.get("verdict") == "match":
                        aligned_keys = set(str(key) for key in canonical_comparison.get("aligned_timestamp_keys", []) if key)
                        current_indicator_bars = _filter_bars_to_alignment_keys(
                            current_canonical,
                            aligned_keys,
                            timeframe=timeframe,
                            metadata=current_metadata,
                        )
                        schwab_indicator_bars = _filter_bars_to_alignment_keys(
                            schwab_canonical,
                            aligned_keys,
                            timeframe=timeframe,
                            metadata=schwab_metadata,
                        )
                        current_indicator_bars = _normalize_indicator_bars_for_alignment(
                            current_indicator_bars,
                            timeframe=timeframe,
                            metadata=current_metadata,
                        )
                        schwab_indicator_bars = _normalize_indicator_bars_for_alignment(
                            schwab_indicator_bars,
                            timeframe=timeframe,
                            metadata=schwab_metadata,
                        )
                        current_bundle = _compute_indicator_bundle(current_indicator_bars, symbol=symbol, timeframe=timeframe)
                        schwab_bundle = _compute_indicator_bundle(schwab_indicator_bars, symbol=symbol, timeframe=timeframe)
                        indicators_comparison = _compare_indicator_bundles(current_bundle, schwab_bundle)
                        indicators_comparison["latest_common_aligned_timestamp"] = canonical_comparison.get("latest_common_timestamp")
                        indicators_comparison["latest_common_alignment_label"] = canonical_comparison.get("latest_common_alignment_label")
                        indicators_comparison["alignment_mode"] = canonical_comparison.get("alignment_mode")
                        indicators_comparison["compared_on_aligned_timestamp"] = (
                            canonical_comparison.get("alignment_mode") == "exact_timestamp"
                            and bool(canonical_comparison.get("latest_common_timestamp"))
                        )
                        indicators_comparison["compared_on_alignment_key"] = bool(canonical_comparison.get("latest_common_alignment_key"))
                        indicators_comparison["indicator_input_alignment"] = {
                            "mode": canonical_comparison.get("alignment_mode"),
                            "normalized": canonical_comparison.get("alignment_mode") != "exact_timestamp",
                            "latest_common_alignment_label": canonical_comparison.get("latest_common_alignment_label"),
                            "reason": "indicator_inputs_use_canonical_session_or_interval_labels"
                            if canonical_comparison.get("alignment_mode") != "exact_timestamp"
                            else "intraday_indicator_inputs_preserve_exact_provider_timestamps",
                        }
                        tos_comparison = _compare_tos_reference(tos_by_key.get((symbol, timeframe)), current_bundle, schwab_bundle)
                    else:
                        reason = str(canonical_comparison.get("verdict") or "canonical_bars_not_comparable")
                        indicators_comparison = _indicators_not_compared(reason)
                        tos_comparison = {"provided": (symbol, timeframe) in tos_by_key, "verdict": "not_compared", "mismatches": [], "reason": reason}
                except SchwabAuthRequiredError as exc:
                    item_error = str(exc)
                    item_error_kind = "auth"
                    indicators_comparison = _indicators_not_compared("auth_unavailable")
                    tos_comparison = {"provided": (symbol, timeframe) in tos_by_key, "verdict": "not_compared", "mismatches": []}
                except (SchwabConfigurationError, DataNotEntitledError, ProviderUnavailableError, SymbolNotFoundError, ValueError, OSError, KeyError) as exc:
                    item_error = redact_schwab_text(exc)
                    item_error_kind = "provider"
                    indicators_comparison = _indicators_not_compared("provider_unavailable")
                    errors.append({"symbol": symbol, "timeframe": timeframe, "error": item_error})

                root_cause = self._root_cause(
                    schwab_status=schwab_status,
                    raw=raw_comparison,
                    canonical=canonical_comparison,
                    indicators=indicators_comparison,
                    tos=tos_comparison,
                    error=item_error,
                    error_kind=item_error_kind,
                )
                summary[root_cause] = summary.get(root_cause, 0) + 1
                results.append(
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "rawBars": raw_comparison,
                        "canonicalBars": canonical_comparison,
                        "freshness": raw_comparison.get("freshness") if isinstance(raw_comparison, dict) else None,
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
                    "comparison_mode": "legacy_polygon_vs_schwab" if self._current_provider_is_schwab() else "current_vs_schwab",
                },
                "candidate": schwab_status,
            },
            "request": {
                "symbols": symbols,
                "timeframes": timeframes,
                "lookbackBars": lookback,
                "sessionPolicy": session_policy,
                "includeExtendedHours": include_extended,
                "completedBarsOnly": completed_bars_only,
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
            "comparisonMode": "legacy_polygon_vs_schwab" if self._current_provider_is_schwab() else "current_vs_schwab",
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
