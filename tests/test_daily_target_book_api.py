from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.api.routes import admin as admin_routes
from macmarket_trader.data.providers.market_data import DeterministicFallbackMarketDataProvider, MarketSnapshot, SymbolNotFoundError
from macmarket_trader.domain.models import AppUserModel, OrderModel, PaperPositionModel, PaperTradeModel
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import PaperPortfolioRepository


client = TestClient(app)
USER_AUTH = {"Authorization": "Bearer user-token"}
ADMIN_AUTH = {"Authorization": "Bearer admin-token"}


class StubMarketData:
    def __init__(self, *, fallback: bool = False, mark: float = 105.0) -> None:
        self.fallback = fallback
        self.mark = mark
        self.provider = DeterministicFallbackMarketDataProvider()
        self.last_historical_metadata = {"session_policy": "regular_hours", "source_timeframe": "1D"}

    def historical_bars(self, symbol: str, timeframe: str, limit: int):
        bars = self.provider.fetch_historical_bars(symbol, timeframe, limit)
        return bars, "fallback" if self.fallback else "polygon", self.fallback

    def latest_snapshot(self, symbol: str, timeframe: str = "1D") -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            as_of=datetime(2026, 5, 31, 15, 55, tzinfo=timezone.utc),
            open=self.mark,
            high=self.mark,
            low=self.mark,
            close=self.mark,
            volume=1_000_000,
            source="polygon",
            fallback_mode=False,
        )


class ErrorMarketData:
    last_historical_metadata = {"session_policy": "regular_hours", "source_timeframe": "1D"}

    def historical_bars(self, symbol: str, timeframe: str, limit: int):  # noqa: ARG002
        raise SymbolNotFoundError(symbol)

    def latest_snapshot(self, symbol: str, timeframe: str = "1D"):  # noqa: ARG002
        raise SymbolNotFoundError(symbol)


def _approve_user(
    *,
    headers: dict[str, str] | None = None,
    external_auth_user_id: str = "clerk_user",
) -> int:
    response = client.get("/user/me", headers=headers or USER_AUTH)
    assert response.status_code == 200, response.text
    with SessionLocal() as session:
        user = session.execute(
            select(AppUserModel).where(AppUserModel.external_auth_user_id == external_auth_user_id)
        ).scalar_one()
        user.approval_status = "approved"
        session.commit()
        return user.id


def _order_count() -> int:
    with SessionLocal() as session:
        return len(list(session.execute(select(OrderModel)).scalars()))


def _trade_count() -> int:
    with SessionLocal() as session:
        return len(list(session.execute(select(PaperTradeModel)).scalars()))


def _position_count(*, app_user_id: int | None = None) -> int:
    with SessionLocal() as session:
        stmt = select(PaperPositionModel).where(PaperPositionModel.status == "open")
        if app_user_id is not None:
            stmt = stmt.where(PaperPositionModel.app_user_id == app_user_id)
        return len(list(session.execute(stmt).scalars()))


def test_daily_target_book_requires_authentication_and_approval() -> None:
    no_auth = client.get("/user/daily-target-book/latest")
    assert no_auth.status_code == 401
    assert client.post("/user/daily-target-book/build", json={}).status_code == 401

    pending = client.get("/user/daily-target-book/latest", headers=USER_AUTH)
    assert pending.status_code == 403
    assert client.post("/user/daily-target-book/build", headers=USER_AUTH, json={}).status_code == 403


def test_daily_target_book_build_returns_five_read_only_slots_and_no_orders(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())

    response = client.post(
        "/user/daily-target-book/build",
        headers=USER_AUTH,
        json={"symbols": ["SPY", "QQQ", "MTUM"], "scanDepth": 12},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["readOnly"] is True
    assert payload["paperOnly"] is True
    assert payload["noOrdersCreated"] is True
    assert payload["noPositionsChanged"] is True
    assert len(payload["targetBook"]) == 5
    assert payload["summary"]["slotsReturned"] == 5
    assert _order_count() == 0
    assert _trade_count() == 0
    assert _position_count() == 0


def test_daily_target_book_preserves_existing_position_without_changing_lifecycle(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=111.0))
    PaperPortfolioRepository(SessionLocal).create_position(
        app_user_id=user_id,
        symbol="SPY",
        side="long",
        quantity=10,
        average_price=100,
    )
    before_positions = _position_count(app_user_id=user_id)

    response = client.post(
        "/user/daily-target-book/build",
        headers=USER_AUTH,
        json={"symbols": ["QQQ", "MTUM"], "includeExistingPositions": True},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    spy_slots = [slot for slot in payload["targetBook"] if slot["symbol"] == "SPY"]
    assert len(spy_slots) == 1
    assert spy_slots[0]["alreadyOpen"] is True
    assert spy_slots[0]["action"] in {"KEEP_REVIEW", "SCALE_REVIEW", "EXIT_REVIEW"}
    assert _position_count(app_user_id=user_id) == before_positions
    assert _order_count() == 0


def test_daily_target_book_failed_gates_become_cash_no_trade(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", ErrorMarketData())

    response = client.post(
        "/user/daily-target-book/build",
        headers=USER_AUTH,
        json={"symbols": ["SPY", "QQQ"], "scanDepth": 2},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["targetBook"]) == 5
    assert {slot["action"] for slot in payload["targetBook"]} == {"CASH_NO_TRADE"}
    assert all(row["status"] == "error" for row in payload["dataQuality"])
    assert _order_count() == 0
    assert _trade_count() == 0


def test_daily_target_book_deduplicates_symbols_in_target_book(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())

    response = client.post(
        "/user/daily-target-book/build",
        headers=USER_AUTH,
        json={"symbols": ["SPY", "SPY", "QQQ", "QQQ", "MTUM"], "scanDepth": 12},
    )

    assert response.status_code == 200, response.text
    symbols = [slot["symbol"] for slot in response.json()["targetBook"] if slot.get("symbol")]
    assert symbols == list(dict.fromkeys(symbols))


def test_daily_target_book_is_user_scoped(monkeypatch) -> None:
    user_id = _approve_user()
    other_user_id = _approve_user(headers=ADMIN_AUTH, external_auth_user_id="clerk_admin")
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    PaperPortfolioRepository(SessionLocal).create_position(
        app_user_id=other_user_id,
        symbol="QQQ",
        side="long",
        quantity=5,
        average_price=100,
    )

    response = client.post(
        "/user/daily-target-book/build",
        headers=USER_AUTH,
        json={"symbols": ["SPY"], "includeExistingPositions": True},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["currentPaperBookCount"] == 0
    assert all(row.get("symbol") != "QQQ" for row in payload["currentPaperBook"])
    assert _position_count(app_user_id=user_id) == 0
    assert _position_count(app_user_id=other_user_id) == 1


def test_daily_target_book_labels_fallback_market_data(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(fallback=True))

    response = client.post(
        "/user/daily-target-book/build",
        headers=USER_AUTH,
        json={"symbols": ["SPY"], "scanDepth": 1},
    )

    assert response.status_code == 200, response.text
    quality = response.json()["dataQuality"]
    assert quality
    assert quality[0]["fallbackMode"] is True
    assert "fallback_market_data" in quality[0]["warnings"]


def test_daily_target_book_never_calls_paper_broker(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())

    def fail_execute(_intent):
        raise AssertionError("Daily Target Book must not call paper broker execution")

    monkeypatch.setattr(admin_routes.paper_broker, "execute", fail_execute)
    response = client.post(
        "/user/daily-target-book/build",
        headers=USER_AUTH,
        json={"symbols": ["SPY"], "scanDepth": 1},
    )

    assert response.status_code == 200, response.text
    assert response.json()["executionMode"] == "review_only"
    assert _order_count() == 0
