import json
from datetime import UTC, date, datetime, timedelta
from urllib.error import HTTPError

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from macmarket_trader.config import Settings
from macmarket_trader.data.providers.market_data import DataNotEntitledError, SymbolNotFoundError
from macmarket_trader.data.providers.schwab import (
    SchwabMarketDataProvider,
    SchwabTokenBundle,
    parse_schwab_token_payload,
    redact_schwab_text,
    save_schwab_token_bundle,
    schwab_market_data_status,
)
from macmarket_trader.domain.models import ProviderOAuthTokenModel
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import ProviderOAuthRepository


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _cfg() -> Settings:
    return Settings(
        environment="test",
        auth_provider="mock",
        database_url="sqlite://",
        schwab_enabled=True,
        schwab_client_id="test-client-id",
        schwab_client_secret="unit-test-client-secret-placeholder",
        schwab_redirect_uri="https://api.macmarket.io/auth/schwab/callback",
        schwab_auth_url="https://api.schwabapi.com/v1/oauth/authorize",
        schwab_token_url="https://api.schwabapi.com/v1/oauth/token",
        schwab_market_data_base_url="https://api.schwabapi.com/marketdata/v1",
        schwab_token_encryption_key=Fernet.generate_key().decode("utf-8"),
    )


def _repo() -> ProviderOAuthRepository:
    return ProviderOAuthRepository(SessionLocal)


def _seed_token(repo: ProviderOAuthRepository, cfg: Settings, *, expires_at: datetime | None = None) -> None:
    bundle = SchwabTokenBundle(
        access_token="unit-test-access-token-placeholder",
        refresh_token="unit-test-refresh-token-placeholder",
        token_type="Bearer",
        scope="read",
        access_token_expires_at=expires_at or datetime.now(tz=UTC) + timedelta(minutes=30),
        refresh_token_expires_at=datetime.now(tz=UTC) + timedelta(days=1),
    )
    save_schwab_token_bundle(repo=repo, bundle=bundle, app_user_id=1, cfg=cfg)


def _candles() -> list[dict[str, object]]:
    base = datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    return [
        {
            "datetime": int((base + timedelta(days=index)).timestamp() * 1000),
            "open": 100 + index,
            "high": 101 + index,
            "low": 99 + index,
            "close": 100.5 + index,
            "volume": 1_000_000 + index,
        }
        for index in range(3)
    ]


def _intraday_end_candles() -> list[dict[str, object]]:
    stamps = [
        datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
        datetime(2026, 1, 2, 15, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 16, 0, tzinfo=UTC),
        datetime(2026, 1, 2, 16, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 19, 0, tzinfo=UTC),
        datetime(2026, 1, 2, 19, 30, tzinfo=UTC),
    ]
    return [
        {
            "datetime": int(stamp.timestamp() * 1000),
            "open": 100 + index,
            "high": 101 + index,
            "low": 99 + index,
            "close": 100.5 + index,
            "volume": 1000 + index,
        }
        for index, stamp in enumerate(stamps)
    ]


def test_parses_pricehistory_payload_into_bars(monkeypatch) -> None:
    cfg = _cfg()
    repo = _repo()
    _seed_token(repo, cfg)

    monkeypatch.setattr(
        "macmarket_trader.data.providers.schwab.urlopen",
        lambda request, timeout: FakeResponse({"candles": _candles()}),
    )

    provider = SchwabMarketDataProvider(repo=repo, cfg=cfg)
    bars, metadata = provider.fetch_raw_historical_bars("spy", "1D", 2)

    assert [bar.provider for bar in bars] == ["schwab", "schwab"]
    assert bars[-1].close == 102.5
    assert bars[-1].timestamp.tzinfo is not None
    assert metadata["provider"] == "schwab"
    assert metadata["fallback_mode"] is False
    assert metadata["source_timeframe"] == "1D"


def test_schwab_historical_bars_normalize_supported_timeframes(monkeypatch) -> None:
    cfg = _cfg()
    repo = _repo()
    _seed_token(repo, cfg)

    def fake_urlopen(request, timeout):  # noqa: ANN001
        if "frequencyType=minute" in request.full_url:
            return FakeResponse({"candles": _intraday_end_candles()})
        return FakeResponse({"candles": _candles()})

    monkeypatch.setattr("macmarket_trader.data.providers.schwab.urlopen", fake_urlopen)

    provider = SchwabMarketDataProvider(repo=repo, cfg=cfg)

    daily = provider.fetch_historical_bars("SPY", "1D", 2)
    weekly = provider.fetch_historical_bars("SPY", "1W", 2)
    half_hour = provider.fetch_historical_bars("SPY", "30M", 2)
    hourly = provider.fetch_historical_bars("SPY", "1H", 2)
    four_hour = provider.fetch_historical_bars("SPY", "4H", 2)

    assert len(daily) == 2
    assert len(weekly) == 2
    assert [bar.source_timeframe for bar in half_hour] == ["30M", "30M"]
    assert [bar.timestamp for bar in half_hour] == [
        datetime(2026, 1, 2, 18, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 19, 0, tzinfo=UTC),
    ]
    assert [bar.timestamp for bar in hourly] == [
        datetime(2026, 1, 2, 15, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 18, 30, tzinfo=UTC),
    ]
    assert [bar.timestamp for bar in four_hour] == [
        datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
        datetime(2026, 1, 2, 18, 30, tzinfo=UTC),
    ]
    assert all(
        bar.session_policy == "regular_hours"
        for bar in [*daily, *weekly, *half_hour, *hourly, *four_hour]
    )


def test_parses_quotes_payload(monkeypatch) -> None:
    cfg = _cfg()
    repo = _repo()
    _seed_token(repo, cfg)

    monkeypatch.setattr(
        "macmarket_trader.data.providers.schwab.urlopen",
        lambda request, timeout: FakeResponse({"SPY": {"quote": {"lastPrice": 500.25}}}),
    )

    provider = SchwabMarketDataProvider(repo=repo, cfg=cfg)
    assert provider.quotes(["spy"]) == {"SPY": {"quote": {"lastPrice": 500.25}}}


def test_latest_snapshot_uses_complete_schwab_quote(monkeypatch) -> None:
    cfg = _cfg()
    repo = _repo()
    _seed_token(repo, cfg)
    quote_time = int(datetime(2026, 1, 2, 20, 30, tzinfo=UTC).timestamp() * 1000)

    monkeypatch.setattr(
        "macmarket_trader.data.providers.schwab.urlopen",
        lambda request, timeout: FakeResponse(
            {
                "SPY": {
                    "quote": {
                        "lastPrice": 501.25,
                        "openPrice": 499.0,
                        "highPrice": 502.0,
                        "lowPrice": 498.5,
                        "totalVolume": 1234567,
                        "quoteTime": quote_time,
                    }
                }
            }
        ),
    )

    provider = SchwabMarketDataProvider(repo=repo, cfg=cfg)
    snapshot = provider.fetch_latest_snapshot("SPY", "1D")

    assert snapshot.source == "schwab"
    assert snapshot.close == 501.25
    assert snapshot.open == 499.0
    assert snapshot.volume == 1234567
    assert snapshot.as_of == datetime(2026, 1, 2, 20, 30, tzinfo=UTC)


def test_index_symbol_mapping_returns_schwab_snapshot(monkeypatch) -> None:
    cfg = _cfg()
    repo = _repo()
    _seed_token(repo, cfg)
    seen_urls: list[str] = []
    quote_time = int(datetime(2026, 1, 2, 20, 30, tzinfo=UTC).timestamp() * 1000)

    def fake_urlopen(request, timeout):  # noqa: ANN001
        seen_urls.append(request.full_url)
        return FakeResponse(
            {
                "$SPX": {
                    "quote": {
                        "lastPrice": 5000.0,
                        "closePrice": 4975.0,
                        "netChange": 25.0,
                        "netPercentChange": 0.5025,
                        "quoteTime": quote_time,
                    }
                }
            }
        )

    monkeypatch.setattr("macmarket_trader.data.providers.schwab.urlopen", fake_urlopen)

    provider = SchwabMarketDataProvider(repo=repo, cfg=cfg)
    snapshot = provider.fetch_index_snapshot("SPX")

    assert "symbols=%24SPX" in seen_urls[0]
    assert snapshot.provider == "schwab"
    assert snapshot.symbol == "SPX"
    assert snapshot.latest_value == 5000.0
    assert snapshot.previous_close == 4975.0
    assert snapshot.day_change_pct == 0.5025
    assert snapshot.missing_data == []


def test_handles_empty_candles_without_fabricating_bars(monkeypatch) -> None:
    cfg = _cfg()
    repo = _repo()
    _seed_token(repo, cfg)
    monkeypatch.setattr(
        "macmarket_trader.data.providers.schwab.urlopen",
        lambda request, timeout: FakeResponse({"candles": []}),
    )

    provider = SchwabMarketDataProvider(repo=repo, cfg=cfg)
    bars, metadata = provider.fetch_raw_historical_bars("SPY", "1D", 10)

    assert bars == []
    assert metadata["candles_returned"] == 0


def test_handles_empty_symbol_response(monkeypatch) -> None:
    cfg = _cfg()
    repo = _repo()
    _seed_token(repo, cfg)
    monkeypatch.setattr(
        "macmarket_trader.data.providers.schwab.urlopen",
        lambda request, timeout: FakeResponse({"empty": True, "candles": []}),
    )

    provider = SchwabMarketDataProvider(repo=repo, cfg=cfg)
    with pytest.raises(SymbolNotFoundError):
        provider.fetch_raw_historical_bars("SPY", "1D", 10)


def test_intraday_normalization_shifts_schwab_bar_end_labels_before_rth_aggregation() -> None:
    cfg = _cfg()
    repo = _repo()
    provider = SchwabMarketDataProvider(repo=repo, cfg=cfg)
    raw = [
        provider._normalize_candle(
            {
                "datetime": int(datetime(2026, 1, 2, 15, 0, tzinfo=UTC).timestamp() * 1000),
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.5,
                "volume": 1000,
            },
            provider="schwab",
            source_timeframe="30M",
        ),
        provider._normalize_candle(
            {
                "datetime": int(datetime(2026, 1, 2, 15, 30, tzinfo=UTC).timestamp() * 1000),
                "open": 101,
                "high": 102,
                "low": 100,
                "close": 101.5,
                "volume": 1100,
            },
            provider="schwab",
            source_timeframe="30M",
        ),
    ]

    bars, metadata = provider.normalize_bars(raw, timeframe="1H", limit=5)

    assert len(bars) == 1
    assert bars[0].timestamp == datetime(2026, 1, 2, 14, 30, tzinfo=UTC)
    assert bars[0].open == 100
    assert bars[0].close == 101.5
    assert bars[0].volume == 2100
    assert metadata["source_timestamp_convention"] == "bar_end"
    assert metadata["timestamp_convention"] == "bar_start"
    assert metadata["timestamp_convention_adjustment"] == "schwab_intraday_bar_end_shifted_to_interval_start_for_rth_aggregation"


def test_handles_entitlement_errors_without_leaking_authorization(monkeypatch) -> None:
    cfg = _cfg()
    repo = _repo()
    _seed_token(repo, cfg)

    def forbidden(request, timeout):
        raise HTTPError(request.full_url, 403, "forbidden", None, None)

    monkeypatch.setattr("macmarket_trader.data.providers.schwab.urlopen", forbidden)

    provider = SchwabMarketDataProvider(repo=repo, cfg=cfg)
    with pytest.raises(DataNotEntitledError):
        provider.fetch_raw_historical_bars("SPY", "1D", 10)

    redacted = redact_schwab_text("Authorization: Bearer unit-test-access-token-placeholder", cfg)
    assert "unit-test-access-token-placeholder" not in redacted
    assert "Authorization header" in redacted


def test_schwab_option_chain_snapshot_and_resolution(monkeypatch) -> None:
    cfg = _cfg()
    repo = _repo()
    _seed_token(repo, cfg)
    quote_time = int(datetime.now(tz=UTC).timestamp() * 1000)

    def fake_urlopen(request, timeout):  # noqa: ANN001
        if "/chains" in request.full_url:
            return FakeResponse(
                {
                    "callExpDateMap": {
                        "2026-05-15:30": {
                            "500.0": [
                                {
                                    "symbol": "SPY  260515C00500000",
                                    "putCall": "CALL",
                                    "strikePrice": 500.0,
                                    "expirationDate": "2026-05-15",
                                    "openInterest": 100,
                                }
                            ]
                        }
                    },
                    "putExpDateMap": {
                        "2026-05-15:30": {
                            "495.0": [
                                {
                                    "symbol": "SPY  260515P00495000",
                                    "putCall": "PUT",
                                    "strikePrice": 495.0,
                                    "expirationDate": "2026-05-15",
                                    "openInterest": 90,
                                }
                            ]
                        }
                    },
                }
            )
        return FakeResponse(
            {
                "SPY  260515C00500000": {
                    "quote": {
                        "bidPrice": 10.0,
                        "askPrice": 11.0,
                        "lastPrice": 10.4,
                        "openInterest": 100,
                        "volatility": 0.2,
                        "delta": 0.5,
                        "quoteTime": quote_time,
                    }
                }
            }
        )

    monkeypatch.setattr("macmarket_trader.data.providers.schwab.urlopen", fake_urlopen)

    provider = SchwabMarketDataProvider(repo=repo, cfg=cfg)
    contracts = provider.fetch_option_contracts(
        underlying_symbol="SPY",
        expiration=date(2026, 5, 15),
        option_type="call",
    )
    preview = provider.fetch_options_chain_preview("SPY")
    resolution = provider.resolve_option_contract(
        underlying_symbol="SPY",
        expiration=date(2026, 5, 15),
        option_type="call",
        target_strike=501.0,
    )
    snapshot = provider.fetch_option_contract_snapshot("SPY", "SPY  260515C00500000")

    assert contracts[0]["ticker"] == "SPY  260515C00500000"
    assert preview["source"] == "schwab_options_chain"
    assert preview["calls"][0]["ticker"] == "SPY  260515C00500000"
    assert resolution.resolved is True
    assert resolution.provider == "schwab"
    assert resolution.option_symbol == "SPY  260515C00500000"
    assert snapshot.mark_price == 10.5
    assert snapshot.mark_method == "quote_mid"
    assert snapshot.open_interest == 100


def test_schwab_market_data_status_marks_reconnect_when_live_probe_401(monkeypatch) -> None:
    cfg = _cfg()
    cfg.market_data_enabled = True
    cfg.market_data_provider = "schwab"
    repo = _repo()
    _seed_token(repo, cfg)

    def unauthorized(request, timeout):  # noqa: ANN001
        raise HTTPError(request.full_url, 401, "unauthorized", None, None)

    monkeypatch.setattr("macmarket_trader.data.providers.schwab.urlopen", unauthorized)

    status = schwab_market_data_status(repo=repo, cfg=cfg, include_probe=True, sample_symbol="SPY")

    assert status["mode"] == "primary_market_data"
    assert status["active_production_provider"] is True
    assert status["live_probe_status"] == "degraded"
    assert status["token_status"] == "reconnect_required"
    assert status["requires_reconnect"] is True
    assert status["action"] == "reconnect_schwab"
    assert "reconnect_required" in str(status["details"])


def test_refreshes_access_token_near_expiry(monkeypatch) -> None:
    cfg = _cfg()
    repo = _repo()
    _seed_token(repo, cfg, expires_at=datetime.now(tz=UTC) + timedelta(seconds=10))
    calls: list[str] = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if request.full_url == cfg.schwab_token_url:
            return FakeResponse(
                {
                    "access_token": "unit-test-fresh-access-token-placeholder",
                    "token_type": "Bearer",
                    "scope": "read",
                    "expires_in": 1800,
                }
            )
        return FakeResponse({"candles": _candles()})

    monkeypatch.setattr("macmarket_trader.data.providers.schwab.urlopen", fake_urlopen)

    provider = SchwabMarketDataProvider(repo=repo, cfg=cfg)
    provider.fetch_raw_historical_bars("SPY", "1D", 2)

    assert cfg.schwab_token_url in calls
    with SessionLocal() as session:
        token = session.execute(select(ProviderOAuthTokenModel).where(ProviderOAuthTokenModel.provider == "schwab")).scalar_one()
        assert token.last_refresh_at is not None
        assert token.encrypted_access_token != "unit-test-fresh-access-token-placeholder"
        assert parse_schwab_token_payload({"access_token": "x", "expires_in": 1}).access_token == "x"
