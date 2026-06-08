from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.agent_mode.service import AgentModeService
from macmarket_trader.api.main import app
from macmarket_trader.api.routes import agent_mode as agent_mode_routes
from macmarket_trader.api.routes import admin as admin_routes
from macmarket_trader.config import settings
from macmarket_trader.data.providers.market_data import DeterministicFallbackMarketDataProvider, MarketSnapshot
from macmarket_trader.domain.models import AppUserModel, NotificationAttemptModel, OrderModel, PaperPositionModel, PaperTradeModel, WatchlistModel
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import AgentModeRepository, AgentProfileRepository, PaperPortfolioRepository


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


def _get_user(*, external_auth_user_id: str = "clerk_user") -> AppUserModel:
    with SessionLocal() as session:
        return session.execute(
            select(AppUserModel).where(AppUserModel.external_auth_user_id == external_auth_user_id)
        ).scalar_one()


def _order_count() -> int:
    with SessionLocal() as session:
        return len(list(session.execute(select(OrderModel)).scalars()))


def _position_count(*, status: str = "open") -> int:
    with SessionLocal() as session:
        return len(list(session.execute(select(PaperPositionModel).where(PaperPositionModel.status == status)).scalars()))


def test_agent_mode_requires_authentication_and_approval() -> None:
    no_auth = client.get("/user/agent-mode/settings")
    assert no_auth.status_code == 401
    assert client.get("/user/agent-mode/runs").status_code == 401
    assert client.get("/user/agent-mode/trades").status_code == 401
    assert client.get("/user/agent-mode/performance").status_code == 401

    pending = client.get("/user/agent-mode/settings", headers=USER_AUTH)
    assert pending.status_code == 403
    assert client.get("/user/agent-mode/runs", headers=USER_AUTH).status_code == 403


def test_agent_mode_service_rejects_unapproved_user_direct_call(monkeypatch) -> None:
    response = client.get("/user/me", headers=USER_AUTH)
    assert response.status_code == 200, response.text
    user = _get_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())

    with pytest.raises(HTTPException) as exc_info:
        AgentModeService().run(user=user, request={"dry_run": False, "symbols": ["SPY"]})

    assert exc_info.value.status_code == 403
    assert _order_count() == 0
    assert _position_count() == 0


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


def test_agent_mode_schedule_status_disabled_never_run() -> None:
    _approve_user()

    response = client.get("/user/agent-mode/status", headers=USER_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["agent_enabled"] is False
    assert payload["last_run_status"] == "disabled"
    assert payload["last_skip_reason"] == "agent_disabled"
    assert payload["next_scheduled_run_at"] is None
    assert payload["scheduler_source"] == "external-cli-loop"
    assert payload["scheduler_health"] == "unknown"
    assert payload["scheduler_due_now"] is False
    assert payload["paperOnly"] is True


def test_agent_mode_schedule_status_enabled_has_next_run_and_last_success(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "daily_run_time": "15:45", "timezone": "America/New_York"},
    )

    run_response = client.post(
        "/user/agent-mode/run",
        headers=USER_AUTH,
        json={"dry_run": True, "symbols": ["SPY"], "scan_depth": 1},
    )
    assert run_response.status_code == 200, run_response.text
    response = client.get("/user/agent-mode/status", headers=USER_AUTH)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["agent_enabled"] is True
    assert payload["configured_timezone"] == "America/New_York"
    assert payload["configured_daily_run_time"] == "15:45"
    assert payload["next_scheduled_run_at"] is not None
    assert payload["seconds_until_next_run"] is not None
    assert payload["last_run_status"] == "success"
    assert payload["last_run_id"] == run_response.json()["runId"]
    assert payload["last_run_position_review_count"] >= 0
    assert payload["scheduler_source"] == "external-cli-loop"
    assert "selected_watchlist_name" in payload


def test_agent_mode_advanced_settings_update_and_user_scope() -> None:
    user_id = _approve_user()
    other_user_id = _approve_user(headers=ADMIN_AUTH, external_auth_user_id="clerk_admin")
    with SessionLocal() as session:
        watchlist = WatchlistModel(app_user_id=user_id, name="Agent picks", symbols=["SPY", "QQQ"])
        other_watchlist = WatchlistModel(app_user_id=other_user_id, name="Other picks", symbols=["NVDA"])
        session.add_all([watchlist, other_watchlist])
        session.commit()
        watchlist_id = watchlist.id
        other_watchlist_id = other_watchlist.id

    response = client.post(
        "/user/agent-mode/settings",
        headers=USER_AUTH,
        json={
            "mode": "paper",
            "enabled": True,
            "default_watchlist_id": watchlist_id,
            "universe_source": "watchlist",
            "max_dollars_per_trade": 750,
            "max_percent_of_paper_account_per_trade": 5,
            "max_new_trades_per_run": 2,
            "max_new_trades_per_day": 3,
            "max_open_agent_positions": 4,
            "max_exposure_per_symbol": 1000,
            "min_cash_reserve": 250,
            "allow_scale_ins": True,
            "allow_new_trade_when_symbol_already_open": True,
            "notification_preference": "sms",
            "notification_phone_number": "+15551234567",
            "sms_consent_confirmed": True,
        },
    )
    forbidden = client.post(
        "/user/agent-mode/settings",
        headers=USER_AUTH,
        json={"mode": "paper", "default_watchlist_id": other_watchlist_id},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["default_watchlist_id"] == watchlist_id
    assert payload["max_dollars_per_trade"] == 750
    assert payload["max_percent_of_paper_account_per_trade"] == 5
    assert payload["max_new_trades_per_run"] == 2
    assert payload["max_new_trades_per_day"] == 3
    assert payload["max_open_agent_positions"] == 4
    assert payload["max_exposure_per_symbol"] == 1000
    assert payload["min_cash_reserve"] == 250
    assert payload["allow_scale_ins"] is True
    assert payload["allow_new_trade_when_symbol_already_open"] is True
    assert payload["notification_preference"] == "sms"
    assert payload["sms_notifications_enabled"] is True
    assert payload["email_notifications_enabled"] is False
    assert forbidden.status_code == 404


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
    assert payload["summary"]["paperOpensExecuted"] == 0
    assert payload["summary"]["paperClosesExecuted"] == 0
    assert payload["summary"]["totalExecutedActions"] == 0
    assert _order_count() == 0
    assert _position_count() == 0


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
    assert _position_count() == 0


@pytest.mark.parametrize(
    "updates",
    [
        {"enabled": True, "paused": True},
        {"enabled": True, "kill_switch_enabled": True},
    ],
)
def test_agent_mode_paused_or_kill_switch_forces_dry_run_no_orders(monkeypatch, updates) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(app_user_id=user_id, updates=updates)

    response = client.post(
        "/user/agent-mode/run",
        headers=USER_AUTH,
        json={"dry_run": False, "symbols": ["SPY"], "scan_depth": 1},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["dryRun"] is True
    assert payload["summary"]["executedOrderCount"] == 0
    assert all(intent["status"] in {"dry_run", "blocked"} for intent in payload["intents"])
    assert _order_count() == 0
    assert _position_count() == 0


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
    assert payload["summary"]["paperOpensExecuted"] == 1
    assert payload["summary"]["paperClosesExecuted"] == 0
    assert payload["summary"]["totalExecutedActions"] == 1
    assert payload["summary"]["positionsBeforeCount"] == 0
    assert payload["summary"]["positionsAfterCount"] == 1
    assert _order_count() == payload["summary"]["executedOrderCount"]
    assert all(intent["paper_only"] is True for intent in payload["intents"])
    assert all(intent["no_live_routing"] is True for intent in payload["intents"])
    executed_open = [intent for intent in payload["intents"] if intent["intent"] == "OPEN_PAPER" and intent["status"] == "executed"]
    assert executed_open and executed_open[0]["position_id"]


def test_agent_mode_per_run_trade_cap_blocks_new_opens(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "max_new_trades_per_run": 0},
    )

    response = client.post(
        "/user/agent-mode/run",
        headers=USER_AUTH,
        json={"dry_run": False, "symbols": ["SPY"], "scan_depth": 1},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["dryRun"] is False
    assert payload["summary"]["paperOpensExecuted"] == 0
    assert payload["summary"]["maxNewTradesPerRun"] == 0
    assert any(intent["reason"] == "max_new_trades_per_run_reached" for intent in payload["intents"])
    assert _order_count() == 0
    assert _position_count() == 0


def test_agent_mode_agent_sizing_cap_blocks_when_too_small(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=105.0))
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "max_dollars_per_trade": 25.0},
    )

    response = client.post(
        "/user/agent-mode/run",
        headers=USER_AUTH,
        json={"dry_run": False, "symbols": ["SPY"], "scan_depth": 1},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    opens = [intent for intent in payload["intents"] if intent["intent"] == "OPEN_PAPER"]
    assert opens and opens[0]["status"] == "blocked"
    assert opens[0]["agent_sizing_status"] == "blocked"
    assert opens[0]["execution_error"] == "max_dollars_per_trade"
    assert payload["summary"]["paperOpensExecuted"] == 0
    assert _order_count() == 0


def test_agent_mode_watchlist_mode_missing_watchlist_skips_run(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    with SessionLocal() as session:
        session.query(WatchlistModel).filter(WatchlistModel.app_user_id == user_id).delete()
        session.commit()
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "universe_source": "watchlist", "watchlist_ids": [], "default_watchlist_id": None},
    )

    response = client.post(
        "/user/agent-mode/run",
        headers=USER_AUTH,
        json={"dry_run": False, "scan_depth": 1},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["paperOpensExecuted"] == 0
    assert payload["universe"]["symbols"] == []
    assert any(item.get("reason") == "watchlist_missing_or_empty" for item in payload["dataQuality"])
    assert any(intent["reason"] == "watchlist_missing_or_empty" for intent in payload["intents"])


def test_agent_mode_run_uses_selected_watchlist_and_records_snapshot(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    with SessionLocal() as session:
        watchlist = WatchlistModel(app_user_id=user_id, name="Selected Agent List", symbols=["QQQ", "XLK"])
        session.add(watchlist)
        session.commit()
        watchlist_id = watchlist.id
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={
            "enabled": True,
            "universe_source": "watchlist",
            "default_watchlist_id": watchlist_id,
            "watchlist_ids": [watchlist_id],
        },
    )

    payload = AgentModeService().run(
        user=_get_user(),
        request={"dry_run": True, "symbols": ["SPY"], "scan_depth": 2},
    )

    universe = payload["universe"]
    assert universe["source"] == "watchlist"
    assert universe["watchlist_id"] == watchlist_id
    assert universe["watchlist_name"] == "Selected Agent List"
    assert universe["symbols"] == ["QQQ", "XLK"]
    assert universe["resolved_symbols_snapshot"] == ["QQQ", "XLK"]
    assert universe["manual_override"] is False


def test_agent_mode_manual_override_records_manual_source(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    with SessionLocal() as session:
        watchlist = WatchlistModel(app_user_id=user_id, name="Selected Agent List", symbols=["QQQ"])
        session.add(watchlist)
        session.commit()
        watchlist_id = watchlist.id
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "universe_source": "watchlist", "default_watchlist_id": watchlist_id},
    )

    payload = AgentModeService().run(
        user=_get_user(),
        request={"dry_run": True, "universe_source": "manual", "manual_symbols": ["SPY"], "scan_depth": 1},
    )

    universe = payload["universe"]
    assert universe["source"] == "manual"
    assert universe["symbols"] == ["SPY"]
    assert universe["manual_override"] is True
    assert universe["watchlist_id"] is None


def test_agent_mode_run_history_exposes_count_consistency(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(app_user_id=user_id, updates={"enabled": True})

    run_response = client.post(
        "/user/agent-mode/run",
        headers=USER_AUTH,
        json={"dry_run": False, "symbols": ["SPY"], "scan_depth": 1},
    )
    assert run_response.status_code == 200, run_response.text

    history_response = client.get("/user/agent-mode/runs?limit=10", headers=USER_AUTH)

    assert history_response.status_code == 200, history_response.text
    rows = history_response.json()["items"]
    assert len(rows) == 1
    row = rows[0]
    assert row["paperOpensExecuted"] == 1
    assert row["paperClosesExecuted"] == 0
    assert row["totalExecutedActions"] == 1
    assert row["positionsBeforeCount"] == 0
    assert row["positionsAfterCount"] == 1


def test_agent_mode_settings_and_latest_run_are_user_scoped(monkeypatch) -> None:
    user_id = _approve_user()
    other_user_id = _approve_user(headers=ADMIN_AUTH, external_auth_user_id="clerk_admin")
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    repo = AgentModeRepository(SessionLocal)
    repo.update_settings(app_user_id=user_id, updates={"enabled": True, "manual_symbols": ["SPY"]})
    repo.update_settings(app_user_id=other_user_id, updates={"enabled": False, "manual_symbols": ["QQQ"]})

    run_response = client.post(
        "/user/agent-mode/run",
        headers=USER_AUTH,
        json={"dry_run": True, "symbols": ["SPY"], "scan_depth": 1},
    )
    assert run_response.status_code == 200, run_response.text

    user_latest = client.get("/user/agent-mode/latest", headers=USER_AUTH)
    other_latest = client.get("/user/agent-mode/latest", headers=ADMIN_AUTH)
    user_runs = client.get("/user/agent-mode/runs", headers=USER_AUTH)
    other_runs = client.get("/user/agent-mode/runs", headers=ADMIN_AUTH)

    assert user_latest.status_code == 200, user_latest.text
    assert other_latest.status_code == 200, other_latest.text
    assert user_latest.json()["latestRun"] is not None
    assert user_latest.json()["settings"]["manual_symbols"] == ["SPY"]
    assert other_latest.json()["latestRun"] is None
    assert other_latest.json()["settings"]["manual_symbols"] == ["QQQ"]
    assert len(user_runs.json()["items"]) == 1
    assert other_runs.json()["items"] == []


def test_agent_mode_preserves_valid_holds(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=105.0))
    own_profile_id = AgentProfileRepository(SessionLocal).get_default_profile(app_user_id=user_id).id
    PaperPortfolioRepository(SessionLocal).create_position(
        app_user_id=user_id,
        symbol="SPY",
        side="long",
        quantity=5,
        average_price=100.0,
        order_id="paper-hold-spy",
        agent_profile_id=own_profile_id,
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
    own_profile_id = AgentProfileRepository(SessionLocal).get_default_profile(app_user_id=user_id).id
    for symbol in ["AAA", "BBB", "CCC", "DDD"]:
        repo.create_position(app_user_id=user_id, symbol=symbol, side="long", quantity=1, average_price=100.0, agent_profile_id=own_profile_id)

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


def test_agent_mode_test_sms_disabled_records_safe_attempt(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(settings, "sms_notifications_enabled", False)
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={
            "notification_preference": "sms",
            "sms_notifications_enabled": True,
            "notification_phone_number": "+15551234567",
            "sms_consent_confirmed": True,
        },
    )

    response = client.post("/user/agent-mode/notifications/test", headers=USER_AUTH, json={"channel": "sms"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["attempts"][0]["status"] == "disabled"
    assert payload["attempts"][0]["failureReason"] == "sms_disabled"
    assert payload["attempts"][0]["recipientRedacted"].endswith("4567")
    with SessionLocal() as session:
        attempts = list(session.execute(select(NotificationAttemptModel).where(NotificationAttemptModel.app_user_id == user_id)).scalars())
    assert len(attempts) == 1
    assert attempts[0].status == "disabled"
    assert attempts[0].recipient_redacted != "+15551234567"


def test_agent_mode_notification_none_sends_nothing() -> None:
    user_id = _approve_user()
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"notification_preference": "none"},
    )

    response = client.post("/user/agent-mode/notifications/test", headers=USER_AUTH, json={"channel": "none"})

    assert response.status_code == 200, response.text
    assert response.json()["attempts"] == []
    with SessionLocal() as session:
        attempts = list(session.execute(select(NotificationAttemptModel).where(NotificationAttemptModel.app_user_id == user_id)).scalars())
    assert attempts == []


def test_agent_mode_run_notification_none_sends_no_digest(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "notification_preference": "none"},
    )

    response = AgentModeService().run(
        user=_get_user(),
        request={"dry_run": False, "symbols": ["SPY", "QQQ"], "scan_depth": 2},
    )

    assert response["notificationAttempts"] == []
    with SessionLocal() as session:
        attempts = list(session.execute(select(NotificationAttemptModel).where(NotificationAttemptModel.app_user_id == user_id)).scalars())
    assert attempts == []


def test_agent_mode_run_sends_one_digest_per_channel(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    monkeypatch.setattr(settings, "sms_notifications_enabled", True)
    monkeypatch.setattr(settings, "twilio_account_sid", "test-account-sid")
    monkeypatch.setattr(settings, "twilio_auth_token", "test-auth-token")
    monkeypatch.setattr(settings, "twilio_from_number", "+15550001111")
    sent_sms: list[dict[str, object]] = []

    def fake_sms_send(*, to_number: str, body: str) -> str:
        sent_sms.append({"to": to_number, "body": body})
        return "SM-test"

    monkeypatch.setattr(agent_mode_routes.agent_service.notification_service.sms_client, "send", fake_sms_send)
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={
            "enabled": True,
            "notification_preference": "both",
            "email_notifications_enabled": True,
            "sms_notifications_enabled": True,
            "notification_phone_number": "+15551234567",
            "sms_consent_confirmed": True,
        },
    )

    response = agent_mode_routes.agent_service.run(
        user=_get_user(),
        request={"dry_run": False, "symbols": ["SPY", "QQQ", "MTUM"], "scan_depth": 3},
    )

    attempts = response["notificationAttempts"]
    assert len(attempts) == 2
    assert {attempt["channel"] for attempt in attempts} == {"email", "sms"}
    assert {attempt["eventType"] for attempt in attempts} == {"agent_run_completed"}
    assert len(sent_sms) == 1
    assert "MacMarket Agent" in str(sent_sms[0]["body"])
    with SessionLocal() as session:
        rows = list(session.execute(select(NotificationAttemptModel).where(NotificationAttemptModel.app_user_id == user_id)).scalars())
    assert len(rows) == 2
    assert {row.channel for row in rows} == {"email", "sms"}
    assert {row.event_type for row in rows} == {"agent_run_completed"}
    assert all((row.payload_json or {}).get("digest") is True for row in rows)


def test_agent_mode_close_uses_paper_lifecycle(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=94.0))
    AgentModeRepository(SessionLocal).update_settings(app_user_id=user_id, updates={"enabled": True, "allow_opens": False})
    own_profile_id = AgentProfileRepository(SessionLocal).get_default_profile(app_user_id=user_id).id
    position = PaperPortfolioRepository(SessionLocal).create_position(
        app_user_id=user_id,
        symbol="SPY",
        side="long",
        quantity=2,
        average_price=100.0,
        order_id="paper-close-spy",
        agent_profile_id=own_profile_id,
    )

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
    assert close_intents[0]["summary"] == "paper close executed by Agent Mode paper lifecycle."
    summary = response.json()["summary"]
    assert summary["paperOpensExecuted"] == 0
    assert summary["paperClosesExecuted"] == 1
    assert summary["totalExecutedActions"] == 1
    assert summary["realizedPnlFromClosedPositions"] < 0
    with SessionLocal() as session:
        row = session.get(PaperPositionModel, position.id)
        assert row is not None
        assert row.status == "closed"
        trades = list(session.execute(select(PaperTradeModel)).scalars())
        assert len(trades) == 1
        assert trades[0].close_reason == "agent_mode:stop_triggered"

    trades_response = client.get("/user/agent-mode/trades", headers=USER_AUTH)
    performance_response = client.get("/user/agent-mode/performance", headers=USER_AUTH)

    assert trades_response.status_code == 200, trades_response.text
    trade_items = trades_response.json()["items"]
    assert len(trade_items) == 1
    assert trade_items[0]["symbol"] == "SPY"
    assert trade_items[0]["exit_reason"] == "stop_triggered"
    assert trade_items[0]["linked_run_id"] == response.json()["runId"]
    assert performance_response.status_code == 200, performance_response.text
    performance = performance_response.json()
    assert performance["tradeCount"] == 1
    assert performance["lossCount"] == 1
    assert performance["realizedPnl"] < 0


def test_agent_mode_endpoint_caps_are_enforced() -> None:
    _approve_user()

    too_many_runs = client.get("/user/agent-mode/runs?limit=101", headers=USER_AUTH)
    too_many_trades = client.get("/user/agent-mode/trades?limit=251", headers=USER_AUTH)

    assert too_many_runs.status_code == 422
    assert too_many_trades.status_code == 422


def test_agent_mode_scale_resize_stays_review_only_for_mvp(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=105.0))
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "allow_scale_resize": True},
    )
    own_profile_id = AgentProfileRepository(SessionLocal).get_default_profile(app_user_id=user_id).id
    position = PaperPortfolioRepository(SessionLocal).create_position(
        app_user_id=user_id,
        symbol="SPY",
        side="long",
        quantity=2,
        average_price=100.0,
        order_id="paper-scale-spy",
        agent_profile_id=own_profile_id,
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


def test_agent_mode_run_due_skips_unapproved_users(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(app_user_id=user_id, updates={"enabled": True})
    with SessionLocal() as session:
        user = session.get(AppUserModel, user_id)
        assert user is not None
        user.approval_status = "pending"
        session.commit()

    # Use a weekday (Mon 2026-06-01) so the unapproved-user skip is exercised
    # rather than the weekend market-session guard, which short-circuits earlier.
    runs = AgentModeService().run_due(now=datetime(2026, 6, 1, 22, 0, tzinfo=timezone.utc))

    assert len(runs) == 1
    assert runs[0]["app_user_id"] == user_id
    assert runs[0]["status"] == "skipped"
    assert runs[0]["reason"] == "user_not_approved"
    assert runs[0]["window_key"].startswith("2026-06-01|15:45|America/New_York|agentprof_")
    assert _order_count() == 0
    assert _position_count() == 0


def test_agent_mode_scheduler_due_dry_run_records_diagnostic_without_orders_or_notifications(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "daily_run_time": "09:30", "timezone": "UTC"},
    )

    runs = AgentModeService().run_due(
        now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc),
        dry_run=True,
        no_notifications=True,
    )

    assert runs and runs[0]["status"] == "completed"
    assert runs[0]["source"] == "scheduler_diagnostic"
    assert _order_count() == 0
    assert _position_count() == 0
    with SessionLocal() as session:
        assert len(list(session.execute(select(NotificationAttemptModel)).scalars())) == 0
    latest = AgentModeRepository(SessionLocal).latest_run(app_user_id=user_id)
    assert latest is not None
    assert latest.request_json["source"] == "scheduler_diagnostic"
    assert latest.request_json["no_notifications"] is True
    assert latest.response_json["notificationDigestSuppressed"] is True


def test_agent_mode_scheduler_not_due_updates_status_without_run(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "daily_run_time": "15:45", "timezone": "UTC"},
    )

    checked_at = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    status_at = checked_at + timedelta(minutes=20)
    runs = AgentModeService().run_due(now=checked_at, dry_run=True)
    monkeypatch.setattr("macmarket_trader.agent_mode.service.utc_now", lambda: status_at)

    assert len(runs) == 1
    assert runs[0]["status"] == "skipped"
    assert runs[0]["reason"] == "not_due_yet"
    assert runs[0]["due_now"] is False
    assert runs[0]["window_key"].startswith("2026-06-03|15:45|UTC|agentprof_")
    assert AgentModeRepository(SessionLocal).latest_run(app_user_id=user_id) is None
    status = client.get("/user/agent-mode/status", headers=USER_AUTH).json()
    assert status["scheduler_health"] == "stale"
    assert status["scheduler_check_age_seconds"] == 20 * 60
    assert status["scheduler_last_check_result"] == "skipped"
    assert status["scheduler_last_check_reason"] == "not_due_yet"
    assert status["scheduler_due_now"] is False


def test_agent_mode_scheduler_disabled_user_records_skip(monkeypatch) -> None:
    user_id = _approve_user()
    AgentModeRepository(SessionLocal).get_or_create_settings(app_user_id=user_id)

    checked_at = datetime(2026, 6, 3, 20, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("macmarket_trader.agent_mode.service.utc_now", lambda: checked_at + timedelta(minutes=20))
    runs = AgentModeService().run_due(now=checked_at)

    assert len(runs) == 1
    assert runs[0]["app_user_id"] == user_id
    assert runs[0]["status"] == "skipped"
    assert runs[0]["reason"] == "agent_disabled"
    assert runs[0]["due_now"] is False
    status = client.get("/user/agent-mode/status", headers=USER_AUTH).json()
    assert status["scheduler_last_check_reason"] == "agent_disabled"
    assert status["scheduler_health"] == "stale"


def test_agent_mode_scheduler_recent_check_reports_ok(monkeypatch) -> None:
    user_id = _approve_user()
    repo = AgentModeRepository(SessionLocal)
    repo.update_settings(app_user_id=user_id, updates={"enabled": True, "daily_run_time": "15:45", "timezone": "UTC"})
    checked_at = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    repo.update_scheduler_check(
        app_user_id=user_id,
        checked_at=checked_at,
        result="skipped",
        reason="not_due_yet",
        due_at=datetime(2026, 6, 3, 15, 45, tzinfo=timezone.utc),
        run_id=None,
        window_key="2026-06-03|15:45|UTC",
    )
    monkeypatch.setattr("macmarket_trader.agent_mode.service.utc_now", lambda: checked_at + timedelta(minutes=2))

    status = client.get("/user/agent-mode/status", headers=USER_AUTH).json()

    assert status["scheduler_health"] == "ok"
    assert status["scheduler_last_check_result"] == "skipped"
    assert status["scheduler_last_check_reason"] == "not_due_yet"
    assert status["last_run_status"] == "never_run"


def test_agent_mode_scheduler_manual_run_does_not_block_scheduled_window(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    repo = AgentModeRepository(SessionLocal)
    repo.update_settings(app_user_id=user_id, updates={"enabled": True, "daily_run_time": "09:30", "timezone": "UTC"})
    repo.create_run(
        app_user_id=user_id,
        run_id="agent_manual_today",
        status="completed",
        execution_mode="paper",
        dry_run=True,
        intent_count=0,
        executed_order_count=0,
        request_json={"source": "manual_agent"},
        response_json={"source": "manual_agent", "summary": {"source": "manual_agent"}},
        completed_at=datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc),
    )

    runs = AgentModeService().run_due(
        now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc),
        dry_run=True,
        no_notifications=True,
    )

    assert runs[0]["status"] == "completed"
    assert runs[0]["source"] == "scheduler_diagnostic"


def test_agent_mode_scheduler_duplicate_window_guard_skips_existing_scheduled_run(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id, updates={"enabled": True, "daily_run_time": "09:30", "timezone": "UTC"}
    )
    service = AgentModeService()

    # First scheduled run in the window records a scheduled_agent run for the profile.
    first = service.run_due(now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc), no_notifications=True)
    assert first[0]["status"] == "completed"

    # A second check in the same profile window is deduped by the profile-qualified key.
    second = service.run_due(now=datetime(2026, 6, 3, 15, 5, tzinfo=timezone.utc), dry_run=True, no_notifications=True)

    assert second[0]["status"] == "skipped"
    assert second[0]["reason"] == "already_ran_for_window"
    assert second[0]["runId"] == first[0]["runId"]
    assert second[0]["window_key"].startswith("2026-06-03|09:30|UTC|agentprof_")


def test_agent_mode_scheduler_window_claim_prevents_duplicate_check(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id, updates={"enabled": True, "daily_run_time": "09:30", "timezone": "UTC"}
    )
    profile_repo = AgentProfileRepository(SessionLocal)
    profile_repo.migrate_legacy_settings_to_profiles()
    profile = profile_repo.get_default_profile(app_user_id=user_id)
    window_key = f"2026-06-03|09:30|UTC|{profile.profile_uid}"
    assert profile_repo.claim_scheduler_window(
        profile_id=profile.id,
        checked_at=datetime(2026, 6, 3, 15, 4, tzinfo=timezone.utc),
        due_at=datetime(2026, 6, 3, 9, 30, tzinfo=timezone.utc),
        window_key=window_key,
        stale_after_seconds=900,
    )

    runs = AgentModeService().run_due(
        now=datetime(2026, 6, 3, 15, 5, tzinfo=timezone.utc),
        dry_run=True,
        no_notifications=True,
    )

    assert runs[0]["status"] == "skipped"
    assert runs[0]["reason"] == "scheduler_window_already_claimed"
    assert runs[0]["due_now"] is True
    assert runs[0]["window_key"] == window_key
    assert profile_repo.latest_run(app_user_id=user_id, agent_profile_id=profile.id) is None


def test_agent_mode_scheduler_uses_selected_watchlist(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    with SessionLocal() as session:
        watchlist = WatchlistModel(app_user_id=user_id, name="Scheduler List", symbols=["QQQ", "XLK"])
        session.add(watchlist)
        session.commit()
        watchlist_id = watchlist.id
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={
            "enabled": True,
            "daily_run_time": "09:30",
            "timezone": "UTC",
            "universe_source": "watchlist",
            "default_watchlist_id": watchlist_id,
            "watchlist_ids": [watchlist_id],
        },
    )

    runs = AgentModeService().run_due(
        now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc),
        dry_run=True,
        no_notifications=True,
    )

    assert runs[0]["resolved_symbol_count"] == 2
    latest = AgentModeRepository(SessionLocal).latest_run(app_user_id=user_id)
    assert latest is not None
    assert latest.response_json["universe"]["watchlist_id"] == watchlist_id
    assert latest.response_json["universe"]["watchlist_name"] == "Scheduler List"
    assert latest.response_json["universe"]["symbols"] == ["QQQ", "XLK"]


def test_agent_mode_scheduler_empty_watchlist_records_clear_skip(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "daily_run_time": "09:30", "timezone": "UTC", "universe_source": "watchlist"},
    )

    runs = AgentModeService().run_due(
        now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc),
        dry_run=True,
        no_notifications=True,
    )

    # A watchlist profile with no/empty watchlist is SKIPPED before claiming the
    # window — never a misleading "completed" run with zero symbols.
    assert runs[0]["status"] == "skipped"
    assert runs[0]["reason"] == "no_universe"
    assert "watchlist" in str(runs[0].get("universe_reason"))
    assert AgentModeRepository(SessionLocal).latest_run(app_user_id=user_id) is None
    assert _order_count() == 0
    assert _position_count() == 0


def test_agent_mode_scheduler_timezone_due_conversion(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "daily_run_time": "09:30", "timezone": "America/New_York"},
    )

    not_due = AgentModeService().run_due(now=datetime(2026, 6, 3, 13, 20, tzinfo=timezone.utc), dry_run=True)
    due = AgentModeService().run_due(now=datetime(2026, 6, 3, 13, 31, tzinfo=timezone.utc), dry_run=True, no_notifications=True)

    assert not_due[0]["reason"] == "not_due_yet"
    assert due[0]["status"] == "completed"
    assert due[0]["window_key"].startswith("2026-06-03|09:30|America/New_York|agentprof_")


def test_agent_mode_scheduler_failure_creates_safe_error_record(monkeypatch) -> None:
    user_id = _approve_user()
    service = AgentModeService()
    service.agent_repo.update_settings(app_user_id=user_id, updates={"enabled": True, "daily_run_time": "09:30", "timezone": "UTC"})

    def fail_run(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("Authorization: unit-test-sensitive-placeholder")

    monkeypatch.setattr(service, "run", fail_run)

    runs = service.run_due(now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc), dry_run=True, no_notifications=True)

    assert runs[0]["status"] == "error"
    assert runs[0]["reason"] == "redacted_sensitive_error"
    latest = service.agent_repo.latest_run(app_user_id=user_id)
    assert latest is not None
    assert latest.status == "error"
    assert latest.response_json["warnings"] == ["redacted_sensitive_error"]
    assert "unit-test-sensitive-placeholder" not in str(latest.response_json)


def test_agent_mode_scheduler_status_reflects_completed_check(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id,
        updates={"enabled": True, "daily_run_time": "09:30", "timezone": "UTC"},
    )
    checked_at = datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc)
    AgentModeService().run_due(
        now=checked_at,
        dry_run=True,
        no_notifications=True,
    )
    monkeypatch.setattr("macmarket_trader.agent_mode.service.utc_now", lambda: checked_at + timedelta(minutes=2))

    payload = client.get("/user/agent-mode/status", headers=USER_AUTH).json()

    assert payload["scheduler_health"] == "ok"
    assert payload["scheduler_last_check_result"] == "completed"
    assert payload["scheduler_last_run_id"]
    assert payload["last_run_status"] == "success"
    assert payload["selected_watchlist_name"] is None
    assert payload["resolved_symbol_count"] >= 1
    assert payload["last_scheduled_run_status"] == "never_run"
