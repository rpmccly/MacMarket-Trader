import json
from datetime import UTC, datetime, timedelta
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
