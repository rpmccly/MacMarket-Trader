from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from macmarket_trader.config import Settings
from macmarket_trader.data_parity.service import ProviderParityService
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
        "macmarket_trader.data_parity.service.schwab_connection_status",
        lambda *, repo, cfg: {
            "provider": "schwab_market_data",
            "mode": "diagnostic",
            "status": "ok",
            "configured": True,
            "oauth_connected": True,
            "token_status": "connected",
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


def test_raw_provider_mismatch_classification(monkeypatch) -> None:
    service = _service(monkeypatch, current=_bars(close_shift=1.0), schwab_raw=_bars())

    response = service.run(_request(), app_user_id=1)

    assert response["summary"]["raw_provider_mismatch"] == 1
    assert response["results"][0]["rootCause"] == "raw_provider_mismatch"
    assert response["results"][0]["rawBars"]["verdict"] == "mismatch"


def test_normalization_mismatch_classification(monkeypatch) -> None:
    raw = _bars()
    schwab_canonical = _bars(close_shift=1.0)
    service = _service(monkeypatch, current=raw, schwab_raw=raw, schwab_canonical=schwab_canonical)

    response = service.run(_request(), app_user_id=1)

    assert response["summary"]["normalization_mismatch"] == 1
    assert response["results"][0]["rootCause"] == "normalization_mismatch"
    assert response["results"][0]["rawBars"]["verdict"] == "match"
    assert response["results"][0]["canonicalBars"]["verdict"] == "mismatch"


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
        "macmarket_trader.data_parity.service.schwab_connection_status",
        lambda *, repo, cfg: {
            "provider": "schwab_market_data",
            "mode": "diagnostic",
            "status": "ok",
            "configured": True,
            "oauth_connected": True,
            "token_status": "connected",
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


def test_parity_response_and_snapshot_redact_sensitive_keys(monkeypatch) -> None:
    app_user_id = _seed_user()
    monkeypatch.setattr(
        "macmarket_trader.data_parity.service.schwab_connection_status",
        lambda *, repo, cfg: {
            "provider": "schwab_market_data",
            "mode": "diagnostic",
            "status": "ok",
            "configured": True,
            "oauth_connected": True,
            "token_status": "connected",
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
