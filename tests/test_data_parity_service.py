from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from macmarket_trader.config import Settings
from macmarket_trader.data_parity.service import ProviderParityService, _compare_bars
from macmarket_trader.domain.models import AppUserModel, ProviderParitySnapshotModel
from macmarket_trader.domain.schemas import Bar
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import ProviderOAuthRepository, ProviderParitySnapshotRepository


def _bars(*, close_shift: float = 0.0, count: int = 80) -> list[Bar]:
    start = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    return [
        Bar(
            date=(date(2026, 1, 2) + timedelta(days=index)),
            timestamp=start + timedelta(days=index),
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100.5 + index + close_shift,
            volume=1_000_000 + index,
            session_policy="regular_hours",
            source_session_policy="provider_regular_hours",
            source_timeframe="1D",
            provider="polygon",
        )
        for index in range(count)
    ]


def _intraday_bars(*, count: int = 320) -> list[Bar]:
    bars: list[Bar] = []
    session_day = date(2026, 1, 2)
    while len(bars) < count:
        if session_day.weekday() < 5:
            session_start = datetime.combine(session_day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=14, minutes=30)
            for slot in range(13):
                if len(bars) >= count:
                    break
                index = len(bars)
                timestamp = session_start + timedelta(minutes=30 * slot)
                bars.append(
                    Bar(
                        date=session_day,
                        timestamp=timestamp,
                        open=100 + index * 0.1,
                        high=100.5 + index * 0.1,
                        low=99.5 + index * 0.1,
                        close=100.2 + index * 0.1,
                        volume=1_000_000 + index,
                        session_policy="regular_hours",
                        source_session_policy="provider_regular_hours",
                        source_timeframe="30M",
                        provider="polygon",
                    )
                )
        session_day += timedelta(days=1)
    return bars


def _bars_at(timestamps: list[datetime], *, provider: str = "polygon") -> list[Bar]:
    return [
        Bar(
            date=timestamp.date(),
            timestamp=timestamp,
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100.5 + index,
            volume=1_000_000 + index,
            session_policy="regular_hours",
            source_session_policy="provider_regular_hours",
            source_timeframe="30M",
            provider=provider,
        )
        for index, timestamp in enumerate(timestamps)
    ]


def _anchored_session_bars(timestamps: list[datetime], *, provider: str, source_timeframe: str) -> list[Bar]:
    return [
        Bar(
            date=timestamp.date(),
            timestamp=timestamp,
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100.5 + index,
            volume=1_000_000 + index,
            session_policy="regular_hours",
            source_session_policy="provider_regular_hours",
            source_timeframe=source_timeframe,
            provider=provider,
        )
        for index, timestamp in enumerate(timestamps)
    ]


class StubProvider:
    name = "polygon"

    def __init__(self, bars: list[Bar]) -> None:
        self.bars = bars
        self.last_aggregate_request_metadata = {
            "provider": "polygon",
            "source_timeframe": "1D",
            "session_policy": "regular_hours",
            "fallback_mode": False,
        }

    def fetch_historical_bars(self, *, symbol: str, timeframe: str, limit: int) -> list[Bar]:
        del symbol, timeframe
        return self.bars[-limit:]


class StubMarketDataService:
    def __init__(self, bars: list[Bar]) -> None:
        self._provider = StubProvider(bars)

    def provider_health(self, sample_symbol: str):
        del sample_symbol
        return SimpleNamespace(status="ok")


class StubSchwabMarketDataService:
    def __init__(self) -> None:
        self._provider = SimpleNamespace(name="schwab")

    def provider_health(self, sample_symbol: str):
        del sample_symbol
        return SimpleNamespace(status="ok")


class StubSchwabProvider:
    def __init__(self, raw_bars: list[Bar], canonical_bars: list[Bar] | None = None) -> None:
        self.raw_bars = raw_bars
        self.canonical_bars = canonical_bars or raw_bars

    def fetch_raw_historical_bars(self, *, symbol: str, timeframe: str, limit: int):
        del symbol
        source_timeframe = "30M" if timeframe in {"4H", "1H", "30M"} else timeframe
        selected_limit = min(len(self.raw_bars), max(limit, 300 if timeframe == "4H" else limit))
        return self.raw_bars[-selected_limit:], {
            "provider": "schwab",
            "source_timeframe": source_timeframe,
            "session_policy": "provider_regular_hours",
            "fallback_mode": False,
            "raw_selection_limit": selected_limit,
        }

    def normalize_bars(self, bars: list[Bar], *, timeframe: str, limit: int):
        del bars
        return self.canonical_bars[-limit:], {
            "provider": "schwab",
            "source_timeframe": timeframe,
            "session_policy": "regular_hours",
            "fallback_mode": False,
        }


def _cfg() -> Settings:
    return Settings(
        environment="test",
        auth_provider="mock",
        database_url="sqlite://",
        data_parity_save_snapshots=True,
        data_parity_default_lookback_bars=40,
        data_parity_max_lookback_bars=500,
    )


def _service(monkeypatch, *, current: list[Bar], schwab_raw: list[Bar], schwab_canonical: list[Bar] | None = None) -> ProviderParityService:
    monkeypatch.setattr(
        "macmarket_trader.data_parity.service.schwab_market_data_status",
        lambda *, repo, cfg, include_probe=True, sample_symbol="SPY": {
            "provider": "schwab_market_data",
            "mode": "diagnostic",
            "status": "ok",
            "configured": True,
            "oauth_connected": True,
            "token_status": "connected",
            "live_probe_status": "ok",
            "probe_state": "ok",
            "details": "connected",
        },
    )
    return ProviderParityService(
        current_market_data_service=StubMarketDataService(current),
        schwab_provider=StubSchwabProvider(schwab_raw, schwab_canonical),
        oauth_repo=ProviderOAuthRepository(SessionLocal),
        snapshot_repo=ProviderParitySnapshotRepository(SessionLocal),
        cfg=_cfg(),
    )


def _request(**overrides) -> dict[str, object]:
    payload: dict[str, object] = {
        "symbols": ["SPY"],
        "timeframes": ["1D"],
        "lookbackBars": 40,
        "sessionPolicy": "regular_hours",
        "includeExtendedHours": False,
        "saveSnapshot": False,
        "tosReferences": [],
    }
    payload.update(overrides)
    return payload


def _seed_user() -> int:
    with SessionLocal() as session:
        existing = session.execute(select(AppUserModel).where(AppUserModel.external_auth_user_id == "parity-admin")).scalar_one_or_none()
        if existing is not None:
            return existing.id
        user = AppUserModel(
            external_auth_user_id="parity-admin",
            email="admin@example.com",
            display_name="Parity Admin",
            approval_status="approved",
            app_role="admin",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id


def test_data_parity_blocks_schwab_when_live_probe_is_degraded(monkeypatch) -> None:
    monkeypatch.setattr(
        "macmarket_trader.data_parity.service.schwab_market_data_status",
        lambda *, repo, cfg, include_probe=True, sample_symbol="SPY": {
            "provider": "schwab_market_data",
            "mode": "primary_market_data",
            "status": "degraded",
            "configured": True,
            "oauth_connected": True,
            "token_status": "connected",
            "live_probe_status": "degraded",
            "probe_state": "degraded",
            "requires_reconnect": True,
            "action": "reconnect_schwab",
            "details": "Schwab/Thinkorswim market-data probe failed: reconnect_required",
        },
    )
    service = ProviderParityService(
        current_market_data_service=StubMarketDataService(_bars()),
        schwab_provider=StubSchwabProvider(_bars()),
        oauth_repo=ProviderOAuthRepository(SessionLocal),
        snapshot_repo=ProviderParitySnapshotRepository(SessionLocal),
        cfg=_cfg(),
    )

    response = service.run(_request(lookbackBars=5), app_user_id=1)

    assert response["providers"]["candidate"]["live_probe_status"] == "degraded"
    assert response["providers"]["candidate"]["action"] == "reconnect_schwab"
    assert response["summary"]["provider_unavailable"] == 1
    assert response["results"][0]["rootCause"] == "provider_unavailable"
    assert "reconnect_required" in response["results"][0]["errors"][0]


def test_raw_provider_mismatch_classification(monkeypatch) -> None:
    service = _service(monkeypatch, current=_bars(close_shift=1.0), schwab_raw=_bars())

    response = service.run(_request(completedBarsOnly=False), app_user_id=1)

    assert response["summary"]["comparable_raw_mismatch"] == 1
    assert response["results"][0]["rootCause"] == "comparable_raw_mismatch"
    assert response["results"][0]["rawBars"]["verdict"] == "comparable_raw_mismatch"


def test_normalization_mismatch_classification(monkeypatch) -> None:
    raw = _bars()
    schwab_canonical = _bars(close_shift=1.0)
    service = _service(monkeypatch, current=raw, schwab_raw=raw, schwab_canonical=schwab_canonical)

    response = service.run(_request(), app_user_id=1)

    assert response["summary"]["comparable_normalized_mismatch"] == 1
    assert response["results"][0]["rootCause"] == "comparable_normalized_mismatch"
    assert response["results"][0]["rawBars"]["verdict"] == "match"
    assert response["results"][0]["canonicalBars"]["verdict"] == "comparable_normalized_mismatch"
    assert response["results"][0]["indicators"]["verdict"] == "not_compared"


def test_indicator_component_missing_returns_available_false(monkeypatch) -> None:
    def missing_bundle(bars, *, symbol: str, timeframe: str):
        del bars, symbol, timeframe
        component = {"available": False, "reason": "component_not_found"}
        return {
            "trueMomentum": component,
            "haco": component,
            "hacolt": component,
            "hiLo": component,
            "squeeze": component,
        }

    monkeypatch.setattr("macmarket_trader.data_parity.service._compute_indicator_bundle", missing_bundle)
    service = _service(monkeypatch, current=_bars(), schwab_raw=_bars())

    response = service.run(_request(), app_user_id=1)
    indicator = response["results"][0]["indicators"]["current"]["trueMomentum"]

    assert indicator == {"available": False, "reason": "component_not_found"}
    assert response["results"][0]["indicators"]["verdict"] == "match"


def test_no_indicator_mismatch_when_aligned_bars_are_zero(monkeypatch) -> None:
    current = _bars()
    schwab = [
        Bar(
            date=bar.date + timedelta(days=180),
            timestamp=bar.timestamp + timedelta(days=180) if bar.timestamp else None,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close + 10,
            volume=bar.volume,
            session_policy=bar.session_policy,
            source_session_policy=bar.source_session_policy,
            source_timeframe=bar.source_timeframe,
            provider="schwab",
        )
        for bar in _bars()
    ]
    service = _service(monkeypatch, current=current, schwab_raw=schwab)

    response = service.run(_request(completedBarsOnly=False), app_user_id=1)
    result = response["results"][0]

    assert result["canonicalBars"]["aligned_timestamps"] == 0
    assert result["rootCause"] in {"no_aligned_bars", "stale_source"}
    assert result["rootCause"] != "comparable_indicator_mismatch"
    assert result["indicators"]["verdict"] == "not_compared"


def test_stale_provider_data_classifies_before_indicator_compare(monkeypatch) -> None:
    current = _bars(count=80)
    schwab = _bars(count=75)
    service = _service(monkeypatch, current=current, schwab_raw=schwab)

    response = service.run(_request(), app_user_id=1)
    result = response["results"][0]

    assert result["rootCause"] == "stale_source"
    assert result["canonicalBars"]["verdict"] == "stale_source"
    assert result["canonicalBars"]["latest_timestamp_delta_seconds"] > result["canonicalBars"]["latest_timestamp_tolerance_seconds"]
    assert result["indicators"]["verdict"] == "not_compared"


def test_freshness_classifies_delay_from_measured_timestamps(monkeypatch) -> None:
    monkeypatch.setattr(
        "macmarket_trader.data_parity.service._utc_now",
        lambda: datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
    )
    timestamps = [
        datetime(2026, 1, 2, 13, 45, tzinfo=UTC),
        datetime(2026, 1, 2, 14, 15, tzinfo=UTC),
        datetime(2026, 1, 2, 14, 45, tzinfo=UTC),
    ]
    current = _bars_at(timestamps, provider="polygon")
    schwab = _bars_at(timestamps, provider="schwab")
    service = _service(monkeypatch, current=current, schwab_raw=schwab)

    response = service.run(_request(timeframes=["30M"], lookbackBars=5), app_user_id=1)
    freshness = response["results"][0]["freshness"]

    assert freshness["market_session_state"] == "regular"
    assert freshness["expected_latest_market_bar"]["utc"] == "2026-01-02T15:00:00+00:00"
    assert freshness["current"]["latest_bar_timestamp"]["utc"] == "2026-01-02T14:45:00+00:00"
    assert freshness["current"]["latest_bar_timestamp"]["new_york"].startswith("2026-01-02T09:45:00")
    assert freshness["current"]["provider_lag_minutes_vs_expected_latest_market_bar"] == 15.0
    assert freshness["current"]["classification"] == "delayed_15_min_like"
    assert freshness["candidate"]["classification"] == "delayed_15_min_like"
    assert freshness["timestamp_delta_minutes"] == 0.0


def test_freshness_uses_sorted_latest_timestamp_from_provider_bars(monkeypatch) -> None:
    monkeypatch.setattr(
        "macmarket_trader.data_parity.service._utc_now",
        lambda: datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
    )
    timestamps = [
        datetime(2026, 1, 2, 13, 45, tzinfo=UTC),
        datetime(2026, 1, 2, 14, 15, tzinfo=UTC),
        datetime(2026, 1, 2, 14, 45, tzinfo=UTC),
    ]
    current = list(reversed(_bars_at(timestamps, provider="polygon")))
    schwab = list(reversed(_bars_at(timestamps, provider="schwab")))
    service = _service(monkeypatch, current=current, schwab_raw=schwab)

    response = service.run(_request(timeframes=["30M"], lookbackBars=5), app_user_id=1)
    raw = response["results"][0]["rawBars"]
    freshness = response["results"][0]["freshness"]

    assert raw["first_timestamp_current"] == "2026-01-02T13:45:00+00:00"
    assert raw["last_timestamp_current"] == "2026-01-02T14:45:00+00:00"
    assert freshness["current"]["latest_bar_timestamp"]["utc"] == "2026-01-02T14:45:00+00:00"
    assert freshness["current"]["classification"] == "delayed_15_min_like"


def test_weekly_sunday_and_monday_provider_anchors_align_to_canonical_trading_week(monkeypatch) -> None:
    polygon = _anchored_session_bars(
        [
            datetime(2026, 5, 17, 4, tzinfo=UTC),
            datetime(2026, 5, 24, 4, tzinfo=UTC),
            datetime(2026, 5, 31, 4, tzinfo=UTC),
        ],
        provider="polygon",
        source_timeframe="1W",
    )
    schwab = _anchored_session_bars(
        [
            datetime(2026, 5, 18, 5, tzinfo=UTC),
            datetime(2026, 5, 25, 5, tzinfo=UTC),
            datetime(2026, 6, 1, 5, tzinfo=UTC),
        ],
        provider="schwab",
        source_timeframe="1W",
    )
    service = _service(monkeypatch, current=polygon, schwab_raw=schwab)

    response = service.run(_request(timeframes=["1W"], lookbackBars=5, completedBarsOnly=False), app_user_id=1)
    result = response["results"][0]

    assert result["rootCause"] == "match"
    assert result["rawBars"]["verdict"] == "match"
    assert result["canonicalBars"]["verdict"] == "match"
    assert result["canonicalBars"]["alignment_mode"] == "normalized_trading_week"
    assert result["canonicalBars"]["aligned_timestamps"] == 3
    assert result["canonicalBars"]["latest_timestamp_match"] is False
    assert result["canonicalBars"]["latest_alignment_key_match"] is True
    assert result["canonicalBars"]["latest_common_alignment_label"] == "2026-06-01/2026-06-05"
    assert result["canonicalBars"]["latest_common_current_raw_timestamp"] == "2026-05-31T04:00:00+00:00"
    assert result["canonicalBars"]["latest_common_candidate_raw_timestamp"] == "2026-06-01T05:00:00+00:00"
    assert result["indicators"]["alignment_mode"] == "normalized_trading_week"
    assert result["indicators"]["compared_on_alignment_key"] is True


def test_daily_different_utc_provider_anchors_align_to_market_session_date(monkeypatch) -> None:
    session_dates = [date(2026, 5, 28), date(2026, 5, 29), date(2026, 6, 1)]
    polygon = _anchored_session_bars(
        [datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=4) for day in session_dates],
        provider="polygon",
        source_timeframe="1D",
    )
    schwab = _anchored_session_bars(
        [datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=5) for day in session_dates],
        provider="schwab",
        source_timeframe="1D",
    )
    service = _service(monkeypatch, current=polygon, schwab_raw=schwab)

    response = service.run(_request(timeframes=["1D"], lookbackBars=5), app_user_id=1)
    result = response["results"][0]

    assert result["rootCause"] == "match"
    assert result["rawBars"]["verdict"] == "match"
    assert result["canonicalBars"]["alignment_mode"] == "normalized_session_date"
    assert result["canonicalBars"]["aligned_timestamps"] == 3
    assert result["canonicalBars"]["latest_timestamp_match"] is False
    assert result["canonicalBars"]["latest_alignment_key_match"] is True
    assert result["canonicalBars"]["latest_common_alignment_label"] == "2026-06-01"
    assert result["canonicalBars"]["latest_common_current_raw_timestamp"] == "2026-06-01T04:00:00+00:00"
    assert result["canonicalBars"]["latest_common_candidate_raw_timestamp"] == "2026-06-01T05:00:00+00:00"
    assert result["rawBars"]["latest_current_alignment"]["canonical_session_date"] == "2026-06-01"


def test_intraday_bar_start_and_bar_end_labels_align_to_same_interval(monkeypatch) -> None:
    polygon = _bars_at(
        [
            datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 15, 30, tzinfo=UTC),
        ],
        provider="polygon",
    )
    schwab = _bars_at(
        [
            datetime(2026, 1, 2, 15, 30, tzinfo=UTC),
            datetime(2026, 1, 2, 16, 0, tzinfo=UTC),
        ],
        provider="schwab",
    )
    service = _service(monkeypatch, current=polygon, schwab_raw=schwab)

    response = service.run(_request(timeframes=["30M"], lookbackBars=5), app_user_id=1)
    result = response["results"][0]
    raw = result["rawBars"]

    assert raw["alignment_mode"] == "canonical_intraday_interval"
    assert raw["aligned_timestamps"] == 2
    assert raw["verdict"] == "match"
    assert raw["latest_common_alignment_label"] == "2026-01-02 10:30-11:00 ET"
    assert raw["latest_common_current_raw_timestamp"] == "2026-01-02T15:30:00+00:00"
    assert raw["latest_common_candidate_raw_timestamp"] == "2026-01-02T16:00:00+00:00"
    assert raw["aligned_rows"][-1]["current_timestamp_convention"] == "bar_start"
    assert raw["aligned_rows"][-1]["candidate_timestamp_convention"] == "bar_end"


def test_intraday_strict_mismatch_when_canonical_intervals_differ(monkeypatch) -> None:
    base = [
        datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
        datetime(2026, 1, 2, 15, 30, tzinfo=UTC),
    ]
    polygon = _bars_at(base, provider="polygon")
    schwab = _bars_at([stamp + timedelta(hours=2) for stamp in base], provider="schwab")
    service = _service(monkeypatch, current=polygon, schwab_raw=schwab)

    response = service.run(_request(timeframes=["30M"], lookbackBars=5), app_user_id=1)
    result = response["results"][0]

    assert result["rawBars"]["alignment_mode"] == "canonical_intraday_interval"
    assert result["rawBars"]["aligned_timestamps"] == 0
    assert result["rawBars"]["verdict"] in {"no_aligned_bars", "stale_source"}
    assert "no_common_alignment_keys_for_canonical_intraday_interval" in result["rawBars"]["alignment_failure_reason"]
    assert result["rootCause"] in {"no_aligned_bars", "stale_source"}
    assert result["indicators"]["verdict"] == "not_compared"


def test_completed_bars_only_excludes_current_in_progress_bars() -> None:
    run_at = datetime(2026, 1, 2, 16, 15, tzinfo=UTC)
    current_meta = {"provider": "polygon", "timestamp_convention": "bar_start", "adjusted": True, "needExtendedHoursData": "false"}
    schwab_meta = {"provider": "schwab", "timestamp_convention": "bar_end", "adjusted": "provider_default", "needExtendedHoursData": "false"}

    intraday_current = _bars_at(
        [
            datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
            datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 15, 30, tzinfo=UTC),
            datetime(2026, 1, 2, 16, 0, tzinfo=UTC),
        ],
        provider="polygon",
    )
    intraday_schwab = _bars_at(
        [
            datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 15, 30, tzinfo=UTC),
            datetime(2026, 1, 2, 16, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 16, 30, tzinfo=UTC),
        ],
        provider="schwab",
    )
    intraday = _compare_bars(
        intraday_current,
        intraday_schwab,
        current_metadata=current_meta,
        candidate_metadata=schwab_meta,
        timeframe="30M",
        mismatch_verdict="comparable_raw_mismatch",
        server_run_at=run_at,
        completed_bars_only=True,
    )

    assert intraday["filtered_in_progress_current_count"] == 1
    assert intraday["filtered_in_progress_candidate_count"] == 1
    assert intraday["latest_common_alignment_label"] == "2026-01-02 10:30-11:00 ET"
    assert intraday["latest_input_current_alignment"]["bar_in_progress"] is True
    assert intraday["latest_current_alignment"]["bar_completed"] is True

    daily_bars = _anchored_session_bars(
        [
            datetime(2025, 12, 31, 5, tzinfo=UTC),
            datetime(2026, 1, 1, 5, tzinfo=UTC),
            datetime(2026, 1, 2, 5, tzinfo=UTC),
        ],
        provider="polygon",
        source_timeframe="1D",
    )
    daily = _compare_bars(
        daily_bars,
        _anchored_session_bars([bar.timestamp for bar in daily_bars], provider="schwab", source_timeframe="1D"),
        current_metadata={"provider": "polygon", "timestamp_convention": "session_anchor"},
        candidate_metadata={"provider": "schwab", "timestamp_convention": "session_anchor"},
        timeframe="1D",
        mismatch_verdict="comparable_raw_mismatch",
        server_run_at=run_at,
        completed_bars_only=True,
    )

    assert daily["filtered_in_progress_current_count"] == 1
    assert daily["latest_common_alignment_label"] == "2026-01-01"
    assert daily["latest_input_current_alignment"]["canonical_session_date"] == "2026-01-02"
    assert daily["latest_current_alignment"]["canonical_session_date"] == "2026-01-01"

    weekly_bars = _anchored_session_bars(
        [
            datetime(2025, 12, 15, 5, tzinfo=UTC),
            datetime(2025, 12, 22, 5, tzinfo=UTC),
            datetime(2025, 12, 29, 5, tzinfo=UTC),
        ],
        provider="polygon",
        source_timeframe="1W",
    )
    weekly = _compare_bars(
        weekly_bars,
        _anchored_session_bars([bar.timestamp for bar in weekly_bars], provider="schwab", source_timeframe="1W"),
        current_metadata={"provider": "polygon", "timestamp_convention": "session_anchor"},
        candidate_metadata={"provider": "schwab", "timestamp_convention": "session_anchor"},
        timeframe="1W",
        mismatch_verdict="comparable_raw_mismatch",
        server_run_at=run_at,
        completed_bars_only=True,
    )

    assert weekly["filtered_in_progress_current_count"] == 1
    assert weekly["latest_common_alignment_label"] == "2025-12-22/2025-12-26"
    assert weekly["latest_input_current_alignment"]["canonical_trading_week"] == "2025-12-29/2026-01-02"
    assert weekly["latest_current_alignment"]["canonical_trading_week"] == "2025-12-22/2025-12-26"


def test_intraday_aligned_ohlcv_mismatch_reports_diagnostic_axes(monkeypatch) -> None:
    timestamps = [
        datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
        datetime(2026, 1, 2, 15, 30, tzinfo=UTC),
    ]
    polygon = _bars_at(timestamps, provider="polygon")
    schwab = [
        Bar(
            date=(bar.timestamp + timedelta(minutes=30)).date(),
            timestamp=bar.timestamp + timedelta(minutes=30),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close + 1.0,
            volume=bar.volume,
            session_policy=bar.session_policy,
            source_session_policy=bar.source_session_policy,
            source_timeframe=bar.source_timeframe,
            provider="schwab",
        )
        for bar in polygon
    ]
    service = _service(monkeypatch, current=polygon, schwab_raw=schwab)

    response = service.run(_request(timeframes=["30M"], lookbackBars=5), app_user_id=1)
    raw = response["results"][0]["rawBars"]
    diagnostics = raw["comparison_diagnostics"]

    assert raw["alignment_mode"] == "canonical_intraday_interval"
    assert raw["verdict"] == "comparable_raw_mismatch"
    assert diagnostics["current_rth_bucket_boundaries"] == ["09:30-10:00", "10:00-10:30", "10:30-11:00", "11:00-11:30", "11:30-12:00", "12:00-12:30", "12:30-13:00", "13:00-13:30", "13:30-14:00", "14:00-14:30", "14:30-15:00", "15:00-15:30", "15:30-16:00"]
    assert diagnostics["candidate_rth_bucket_boundaries"] == diagnostics["current_rth_bucket_boundaries"]
    assert "macmarket_regular_hours_bucket_boundaries_match" in diagnostics["notes"]
    assert "adjusted_mode_difference_possible" in diagnostics["notes"]
    assert "canonical_intervals_align_so_remaining_ohlcv_difference_is_provider_data_or_adjustment_related" in diagnostics["notes"]
    assert raw["aligned_rows"][-1]["canonical_interval_start"]["new_york"].endswith("10:30:00-05:00")
    assert raw["aligned_rows"][-1]["canonical_interval_end"]["new_york"].endswith("11:00:00-05:00")


def test_tos_reference_mismatch_classification(monkeypatch) -> None:
    service = _service(monkeypatch, current=_bars(), schwab_raw=_bars())

    response = service.run(
        _request(
            tosReferences=[
                {
                    "symbol": "SPY",
                    "timeframe": "1D",
                    "trueMomentumScore": 999,
                    "notes": "manual TOS value",
                }
            ]
        ),
        app_user_id=1,
    )

    assert response["summary"]["tos_reference_mismatch"] == 1
    assert response["results"][0]["rootCause"] == "tos_reference_mismatch"
    assert response["results"][0]["tosReference"]["provided"] is True
    assert response["results"][0]["tosReference"]["verdict"] == "mismatch"


def test_save_snapshot_persists_request_and_response(monkeypatch) -> None:
    app_user_id = _seed_user()
    service = _service(monkeypatch, current=_bars(), schwab_raw=_bars())

    response = service.run(_request(saveSnapshot=True), app_user_id=app_user_id)

    with SessionLocal() as session:
        row = session.execute(select(ProviderParitySnapshotModel).where(ProviderParitySnapshotModel.run_id == response["runId"])).scalar_one()
        assert row.app_user_id == app_user_id
        assert row.provider_candidate == "schwab"
        assert row.request_json["symbols"] == ["SPY"]
        assert row.response_json["runId"] == response["runId"]


def test_intraday_raw_layer_uses_shared_30m_source_for_current_and_schwab(monkeypatch) -> None:
    source_bars = _intraday_bars()
    captured: dict[str, object] = {}

    class CapturingProvider:
        name = "polygon"
        last_aggregate_request_metadata = {
            "provider": "polygon",
            "source_timeframe": "30M",
            "session_policy": "regular_hours",
            "fallback_mode": False,
        }

        def fetch_historical_bars(self, *, symbol: str, timeframe: str, limit: int) -> list[Bar]:
            del symbol
            captured["timeframe"] = timeframe
            captured["limit"] = limit
            return source_bars[-limit:]

    class CapturingMarketDataService:
        _provider = CapturingProvider()

        def provider_health(self, sample_symbol: str):
            del sample_symbol
            return SimpleNamespace(status="ok")

    monkeypatch.setattr(
        "macmarket_trader.data_parity.service.schwab_market_data_status",
        lambda *, repo, cfg, include_probe=True, sample_symbol="SPY": {
            "provider": "schwab_market_data",
            "mode": "diagnostic",
            "status": "ok",
            "configured": True,
            "oauth_connected": True,
            "token_status": "connected",
            "live_probe_status": "ok",
            "probe_state": "ok",
            "details": "connected",
        },
    )
    service = ProviderParityService(
        current_market_data_service=CapturingMarketDataService(),
        schwab_provider=StubSchwabProvider(source_bars),
        oauth_repo=ProviderOAuthRepository(SessionLocal),
        snapshot_repo=ProviderParitySnapshotRepository(SessionLocal),
        cfg=_cfg(),
    )

    response = service.run(_request(timeframes=["4H"], lookbackBars=40), app_user_id=1)

    raw = response["results"][0]["rawBars"]
    assert captured["timeframe"] == "30M"
    assert captured["limit"] > 40
    assert raw["current_metadata"]["raw_source_timeframe"] == "30M"
    assert raw["candidate_metadata"]["raw_source_timeframe"] == "30M"
    assert raw["current_metadata"]["requested_output_timeframe"] == "4H"
    assert raw["current_metadata"]["rth_bucket_boundaries"] == ["09:30-13:30", "13:30-16:00"]
    assert response["results"][0]["canonicalBars"]["current_metadata"]["output_timeframe"] == "4H"


def test_schwab_primary_without_legacy_provider_returns_clear_no_comparison(monkeypatch) -> None:
    app_user_id = _seed_user()
    monkeypatch.setattr(
        "macmarket_trader.data_parity.service.schwab_market_data_status",
        lambda *, repo, cfg, include_probe=True, sample_symbol="SPY": {
            "provider": "schwab_market_data",
            "mode": "primary_market_data",
            "status": "ok",
            "configured": True,
            "oauth_connected": True,
            "token_status": "connected",
            "live_probe_status": "ok",
            "probe_state": "ok",
            "details": "connected",
        },
    )
    cfg = _cfg()
    cfg.polygon_api_key = ""
    service = ProviderParityService(
        current_market_data_service=StubSchwabMarketDataService(),
        schwab_provider=StubSchwabProvider(_bars()),
        oauth_repo=ProviderOAuthRepository(SessionLocal),
        snapshot_repo=ProviderParitySnapshotRepository(SessionLocal),
        cfg=cfg,
    )

    response = service.run(_request(saveSnapshot=True), app_user_id=app_user_id)

    assert response["comparisonMode"] == "schwab_primary_no_legacy"
    assert response["providers"]["current"]["provider"] == "schwab_primary"
    assert response["results"] == []
    assert "no legacy Polygon/Massive API key" in response["warnings"][0]
    with SessionLocal() as session:
        row = session.execute(select(ProviderParitySnapshotModel).where(ProviderParitySnapshotModel.run_id == response["runId"])).scalar_one()
        assert row.provider_current == "schwab_primary"
        assert row.provider_candidate == "schwab"


def test_schwab_primary_uses_legacy_polygon_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        "macmarket_trader.data_parity.service.schwab_market_data_status",
        lambda *, repo, cfg, include_probe=True, sample_symbol="SPY": {
            "provider": "schwab_market_data",
            "mode": "primary_market_data",
            "status": "ok",
            "configured": True,
            "oauth_connected": True,
            "token_status": "connected",
            "live_probe_status": "ok",
            "probe_state": "ok",
            "details": "connected",
        },
    )
    captured: dict[str, object] = {}

    class LegacyPolygonProvider(StubProvider):
        name = "polygon"

        def fetch_historical_bars(self, *, symbol: str, timeframe: str, limit: int) -> list[Bar]:
            captured["provider_called"] = "legacy_polygon"
            return super().fetch_historical_bars(symbol=symbol, timeframe=timeframe, limit=limit)

    cfg = _cfg()
    cfg.polygon_api_key = "legacy-key"
    service = ProviderParityService(
        current_market_data_service=StubSchwabMarketDataService(),
        schwab_provider=StubSchwabProvider(_bars()),
        oauth_repo=ProviderOAuthRepository(SessionLocal),
        snapshot_repo=ProviderParitySnapshotRepository(SessionLocal),
        cfg=cfg,
    )
    service.legacy_polygon_provider = LegacyPolygonProvider(_bars())

    response = service.run(_request(saveSnapshot=False), app_user_id=1)

    assert captured["provider_called"] == "legacy_polygon"
    assert response["comparisonMode"] == "legacy_polygon_vs_schwab"
    assert response["providers"]["current"]["provider"] == "polygon_legacy"
    assert "primary_provider_is_schwab_using_legacy_polygon_for_cutover_comparison" in response["results"][0]["warnings"]


def test_parity_response_and_snapshot_redact_sensitive_keys(monkeypatch) -> None:
    app_user_id = _seed_user()
    monkeypatch.setattr(
        "macmarket_trader.data_parity.service.schwab_market_data_status",
        lambda *, repo, cfg, include_probe=True, sample_symbol="SPY": {
            "provider": "schwab_market_data",
            "mode": "diagnostic",
            "status": "ok",
            "configured": True,
            "oauth_connected": True,
            "token_status": "connected",
            "live_probe_status": "ok",
            "probe_state": "ok",
            "access_token": "unit-test-raw-access-token-placeholder",
            "last_error": "Authorization: Bearer unit-test-raw-access-token-placeholder",
            "details": "connected",
        },
    )
    service = ProviderParityService(
        current_market_data_service=StubMarketDataService(_bars()),
        schwab_provider=StubSchwabProvider(_bars()),
        oauth_repo=ProviderOAuthRepository(SessionLocal),
        snapshot_repo=ProviderParitySnapshotRepository(SessionLocal),
        cfg=_cfg(),
    )

    response = service.run(_request(saveSnapshot=True), app_user_id=app_user_id)

    assert response["providers"]["candidate"]["access_token"] == "[redacted]"
    assert response["providers"]["candidate"]["last_error"] == "[redacted]"
    with SessionLocal() as session:
        row = session.execute(select(ProviderParitySnapshotModel).where(ProviderParitySnapshotModel.run_id == response["runId"])).scalar_one()
        assert row.response_json["providers"]["candidate"]["access_token"] == "[redacted]"
        assert row.response_json["providers"]["candidate"]["last_error"] == "[redacted]"
        assert "unit-test-raw-access-token-placeholder" not in str(row.response_json)
