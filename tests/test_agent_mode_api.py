from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.api.routes import admin as admin_routes
from macmarket_trader.config import settings
from macmarket_trader.data.providers.market_data import DeterministicFallbackMarketDataProvider, MarketSnapshot
from macmarket_trader.domain.models import AppUserModel, OrderModel, PaperPositionModel, PaperTradeModel
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import AgentModeRepository, PaperPortfolioRepository


client = TestClient(app)
USER_AUTH = {"Authorization": "Bearer user-token"}


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


def _approve_user() -> int:
    response = client.get("/user/me", headers=USER_AUTH)
    assert response.status_code == 200, response.text
    with SessionLocal() as session:
        user = session.execute(select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_user")).scalar_one()
        user.approval_status = "approved"
        session.commit()
        return user.id


def _order_count() -> int:
    with SessionLocal() as session:
        return len(list(session.execute(select(OrderModel)).scalars()))


def _position_count(*, status: str = "open") -> int:
    with SessionLocal() as session:
        return len(list(session.execute(select(PaperPositionModel).where(PaperPositionModel.status == status)).scalars()))


def test_agent_mode_rejects_non_paper_mode() -> None:
    _approve_user()

    response = client.post("/user/agent-mode/run", headers=USER_AUTH, json={"mode": "live"})

    assert response.status_code == 409
    assert "paper mode" in response.json()["detail"]


def test_agent_mode_settings_reject_non_paper_mode() -> None:
    _approve_user()

    response = client.post("/user/agent-mode/settings", headers=USER_AUTH, json={"mode": "live", "enabled": True})

    assert response.status_code == 409
    assert "paper mode" in response.json()["detail"]


def test_agent_mode_dry_run_creates_no_orders(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())

    response = client.post(
        "/user/agent-mode/run",
        headers=USER_AUTH,
        json={"dry_run": True, "symbols": ["SPY", "QQQ", "MTUM"], "scan_depth": 3},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["paperOnly"] is True
    assert payload["summary"]["dryRun"] is True
    assert _order_count() == 0


def test_agent_mode_disabled_forces_dry_run_even_when_requested_false(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())

    response = client.post(
        "/user/agent-mode/run",
        headers=USER_AUTH,
        json={"dry_run": False, "symbols": ["SPY"], "scan_depth": 1},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["dryRun"] is True
    assert all(intent["status"] in {"dry_run", "blocked"} for intent in payload["intents"])
    assert _order_count() == 0


def test_agent_mode_enabled_run_creates_only_paper_orders(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(app_user_id=user_id, updates={"enabled": True})

    response = client.post(
        "/user/agent-mode/run",
        headers=USER_AUTH,
        json={"dry_run": False, "symbols": ["SPY"], "scan_depth": 1},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["executionMode"] == "paper"
    assert payload["summary"]["dryRun"] is False
    assert payload["summary"]["executedOrderCount"] == 1
    assert _order_count() == payload["summary"]["executedOrderCount"]
    assert all(intent["paper_only"] is True for intent in payload["intents"])
    assert all(intent["no_live_routing"] is True for intent in payload["intents"])


def test_agent_mode_preserves_valid_holds(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=105.0))
    PaperPortfolioRepository(SessionLocal).create_position(
        app_user_id=user_id,
        symbol="SPY",
        side="long",
        quantity=5,
        average_price=100.0,
        order_id="paper-hold-spy",
    )

    response = client.post("/user/agent-mode/run", headers=USER_AUTH, json={"dry_run": True, "symbols": ["SPY"]})

    assert response.status_code == 200, response.text
    holds = [intent for intent in response.json()["intents"] if intent["intent"] == "HOLD"]
    assert holds
    assert _position_count(status="open") == 1


def test_agent_mode_caps_target_book_at_five(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    repo = PaperPortfolioRepository(SessionLocal)
    for symbol in ["AAA", "BBB", "CCC", "DDD"]:
        repo.create_position(app_user_id=user_id, symbol=symbol, side="long", quantity=1, average_price=100.0)

    response = client.post(
        "/user/agent-mode/run",
        headers=USER_AUTH,
        json={"dry_run": True, "symbols": ["SPY", "QQQ", "MTUM"], "scan_depth": 5},
    )

    assert response.status_code == 200, response.text
    opens = [intent for intent in response.json()["intents"] if intent["intent"] == "OPEN_PAPER"]
    assert len(opens) <= 1
    assert response.json()["summary"]["targetPositionsMax"] == 5


def test_agent_mode_no_forced_trades_when_opens_disabled(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(app_user_id=user_id, updates={"allow_opens": False})

    response = client.post("/user/agent-mode/run", headers=USER_AUTH, json={"dry_run": True, "symbols": ["SPY"]})

    assert response.status_code == 200, response.text
    intents = response.json()["intents"]
    assert not any(intent["intent"] == "OPEN_PAPER" for intent in intents)
    assert any(intent["intent"] == "CASH_NO_TRADE" for intent in intents)


def test_agent_mode_labels_fallback_data(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(fallback=True))
    monkeypatch.setattr(settings, "market_data_enabled", False)
    monkeypatch.setattr(settings, "polygon_enabled", False)

    response = client.post("/user/agent-mode/run", headers=USER_AUTH, json={"dry_run": True, "symbols": ["SPY"]})

    assert response.status_code == 200, response.text
    quality = response.json()["dataQuality"]
    assert quality[0]["fallback_mode"] is True
    assert quality[0]["source"] == "fallback"


def test_agent_mode_close_uses_paper_lifecycle(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=94.0))
    position = PaperPortfolioRepository(SessionLocal).create_position(
        app_user_id=user_id,
        symbol="SPY",
        side="long",
        quantity=2,
        average_price=100.0,
        order_id="paper-close-spy",
    )
    AgentModeRepository(SessionLocal).update_settings(app_user_id=user_id, updates={"enabled": True})

    def close_review(*args, **kwargs):
        del args, kwargs
        return {
            "position_id": position.id,
            "symbol": "SPY",
            "side": "long",
            "current_mark_price": 94.0,
            "action_classification": "stop_triggered",
            "action_summary": "SPY crossed recovered stop.",
            "warnings": [],
            "missing_data": [],
        }

    monkeypatch.setattr(admin_routes, "_build_position_review", close_review)

    response = client.post("/user/agent-mode/run", headers=USER_AUTH, json={"dry_run": False, "symbols": ["QQQ"]})

    assert response.status_code == 200, response.text
    close_intents = [intent for intent in response.json()["intents"] if intent["intent"] == "CLOSE_PAPER"]
    assert close_intents and close_intents[0]["status"] == "executed"
    with SessionLocal() as session:
        row = session.get(PaperPositionModel, position.id)
        assert row is not None
        assert row.status == "closed"
        trades = list(session.execute(select(PaperTradeModel)).scalars())
        assert len(trades) == 1
        assert trades[0].close_reason == "agent_mode:stop_triggered"


def test_agent_mode_scale_resize_stays_review_only_for_mvp(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=105.0))
    position = PaperPortfolioRepository(SessionLocal).create_position(
        app_user_id=user_id,
        symbol="SPY",
        side="long",
        quantity=2,
        average_price=100.0,
        order_id="paper-scale-spy",
    )
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "allow_scale_resize": True},
    )

    def scale_review(*args, **kwargs):
        del args, kwargs
        return {
            "position_id": position.id,
            "symbol": "SPY",
            "side": "long",
            "current_mark_price": 105.0,
            "action_classification": "scale_in_candidate",
            "action_summary": "SPY remains strong but scale execution is deferred in MVP.",
            "warnings": [],
            "missing_data": [],
        }

    monkeypatch.setattr(admin_routes, "_build_position_review", scale_review)

    response = client.post("/user/agent-mode/run", headers=USER_AUTH, json={"dry_run": False, "symbols": ["QQQ"]})

    assert response.status_code == 200, response.text
    scale_intents = [intent for intent in response.json()["intents"] if intent["intent"] == "SCALE_IN_PAPER"]
    assert scale_intents and scale_intents[0]["status"] == "review_only"
    assert scale_intents[0]["execution_error"] == "scale_resize_execution_deferred"
