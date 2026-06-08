"""Phase 12 — bidirectional (directional) paper lifecycle integration tests.

Proves the run-loop wiring of the decision engine + paper short/flip execution:
opens long/short, blocks shorts when disabled, flips own positions, applies the
same lifecycle to HACO/True Momentum when allow_shorts is on, enforces the
ownership boundary on the directional path, forbids simultaneous long+short for
the same symbol/profile, and computes side-aware short P&L. Paper-only.

The directional indicator read is patched at the trigger-module boundary
(``directional_signal``) so the lifecycle is exercised deterministically without
depending on ATR/HACO/Momentum math.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.agent_mode.service import AgentModeService
from macmarket_trader.agent_mode.triggers import DirectionalSignal
from macmarket_trader.api.main import app
from macmarket_trader.api.routes import admin as admin_routes
from macmarket_trader.data.providers.market_data import DeterministicFallbackMarketDataProvider, MarketSnapshot
from macmarket_trader.domain.models import AppUserModel, PaperPositionModel, PaperTradeModel
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import AgentProfileRepository, PaperPortfolioRepository


client = TestClient(app)
USER_AUTH = {"Authorization": "Bearer user-token"}


class StubMarketData:
    def __init__(self, *, mark: float = 100.0) -> None:
        self.provider = DeterministicFallbackMarketDataProvider()
        self.mark = mark
        self.last_historical_metadata = {"session_policy": "regular_hours", "source_timeframe": "1D"}

    def historical_bars(self, symbol: str, timeframe: str, limit: int):
        return self.provider.fetch_historical_bars(symbol, timeframe, limit), "polygon", False

    def latest_snapshot(self, symbol: str, timeframe: str = "1D") -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol, timeframe=timeframe, as_of=datetime(2026, 6, 3, 15, 55, tzinfo=timezone.utc),
            open=self.mark, high=self.mark, low=self.mark, close=self.mark, volume=1_000_000,
            source="polygon", fallback_mode=False,
        )


def _approve() -> int:
    response = client.get("/user/me", headers=USER_AUTH)
    assert response.status_code == 200, response.text
    with SessionLocal() as session:
        user = session.execute(select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_user")).scalar_one()
        user.approval_status = "approved"
        session.commit()
        return user.id


def _user(user_id: int) -> AppUserModel:
    with SessionLocal() as session:
        return session.get(AppUserModel, user_id)


def _create_profile(payload: dict) -> dict:
    response = client.post("/user/agent-mode/profiles", json=payload, headers=USER_AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def _run(user_id: int, profile_id: int, *, dry_run: bool = False) -> dict:
    from macmarket_trader.api.routes import agent_mode as agent_mode_routes
    return agent_mode_routes.agent_service.run(
        user=_user(user_id),
        request={"mode": "paper", "dry_run": dry_run, "profile_id": profile_id, "no_notifications": True},
    )


def _intents(result: dict) -> list[dict]:
    return list(result.get("intents") or [])


def _executed_opens(result: dict, side: str | None = None) -> list[dict]:
    out = [i for i in _intents(result) if i.get("intent") == "OPEN_PAPER" and i.get("status") == "executed"]
    return [i for i in out if side is None or str(i.get("side")) == side]


def _closes(result: dict) -> list[dict]:
    return [i for i in _intents(result) if i.get("intent") == "CLOSE_PAPER"]


def _seed_position(user_id, *, symbol="SPY", side="long", qty=2.0, price=100.0, agent_profile_id=None):
    return PaperPortfolioRepository(SessionLocal).create_position(
        app_user_id=user_id, symbol=symbol, side=side, quantity=qty,
        average_price=price, agent_profile_id=agent_profile_id,
    )


def _position_status(position_id):
    with SessionLocal() as session:
        row = session.get(PaperPositionModel, position_id)
        return row.status if row else None


def _open_positions(user_id, symbol):
    with SessionLocal() as session:
        return list(session.execute(
            select(PaperPositionModel).where(
                PaperPositionModel.app_user_id == user_id,
                PaperPositionModel.symbol == symbol,
                PaperPositionModel.status == "open",
            )
        ).scalars())


def _patch_directional(monkeypatch, *, direction, fresh_flip=False, protective_stop=None, primary="ATR Trailing Stop"):
    sig = DirectionalSignal(direction, fresh_flip, primary, f"atr_{direction}", f"ATR {direction}", protective_stop=protective_stop, detail={})
    monkeypatch.setattr("macmarket_trader.agent_mode.triggers.directional_signal", lambda **_k: sig)


def _patch_hold_review(monkeypatch):
    def _review(position, **_kwargs):
        return {"position_id": position.id, "symbol": position.symbol, "side": position.side,
                "current_mark_price": 100.0, "action_classification": "hold",
                "action_summary": f"{position.symbol} hold", "warnings": [], "missing_data": []}
    monkeypatch.setattr(admin_routes, "_build_position_review", _review)


def _force_stop_review(monkeypatch, *, mark=95.0):
    def _review(position, **_kwargs):
        return {"position_id": position.id, "symbol": position.symbol, "side": position.side,
                "current_mark_price": mark, "action_classification": "stop_triggered",
                "action_summary": f"{position.symbol} stop", "warnings": [], "missing_data": []}
    monkeypatch.setattr(admin_routes, "_build_position_review", _review)


def _atr(allow_shorts=True, **extra):
    payload = {
        "agent_type": "atr_trailing_stop", "name": "ATR", "enabled": True,
        "allow_shorts": allow_shorts, "universe_source": "manual", "manual_symbols": ["SPY"], "scan_depth": 1,
    }
    payload.update(extra)
    return _create_profile(payload)


# ── opens ─────────────────────────────────────────────────────────────────────
def test_atr_opens_long_on_long_signal(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=100.0))
    _patch_directional(monkeypatch, direction="long")
    atr = _atr(allow_shorts=True)
    result = _run(user_id, atr["agent_profile_id"], dry_run=False)
    opens = _executed_opens(result, side="long")
    assert len(opens) == 1
    assert opens[0].get("outcome") == "opened_paper_long"
    positions = _open_positions(user_id, "SPY")
    assert len(positions) == 1 and positions[0].side == "long"


def test_atr_opens_short_on_short_signal_when_allowed(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=100.0))
    _patch_directional(monkeypatch, direction="short", protective_stop=105.0)
    atr = _atr(allow_shorts=True)
    result = _run(user_id, atr["agent_profile_id"], dry_run=False)
    opens = _executed_opens(result, side="short")
    assert len(opens) == 1
    assert opens[0].get("outcome") == "opened_paper_short"
    positions = _open_positions(user_id, "SPY")
    assert len(positions) == 1 and positions[0].side == "short"
    assert positions[0].agent_profile_id == atr["agent_profile_id"]


def test_atr_does_not_open_short_when_disallowed(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=100.0))
    _patch_directional(monkeypatch, direction="short", protective_stop=105.0)
    atr = _atr(allow_shorts=False)
    result = _run(user_id, atr["agent_profile_id"], dry_run=False)
    assert not _executed_opens(result)
    assert any(i.get("reason") == "paper_short_not_allowed" for i in _intents(result))
    assert _open_positions(user_id, "SPY") == []


# ── flips ──────────────────────────────────────────────────────────────────────
def test_atr_flips_own_long_to_short(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=100.0))
    _patch_hold_review(monkeypatch)
    _patch_directional(monkeypatch, direction="short", fresh_flip=True, protective_stop=105.0)
    atr = _atr(allow_shorts=True)
    own_long = _seed_position(user_id, side="long", agent_profile_id=atr["agent_profile_id"])
    result = _run(user_id, atr["agent_profile_id"], dry_run=False)
    # The own long is closed (flip close-leg) and a short is opened.
    closes = [i for i in _closes(result) if i.get("position_id") == own_long.id]
    assert closes and closes[0]["reason"] == "flipped_long_to_short"
    assert _executed_opens(result, side="short")
    assert _position_status(own_long.id) == "closed"
    positions = _open_positions(user_id, "SPY")
    assert len(positions) == 1 and positions[0].side == "short"


def test_atr_flips_own_short_to_long(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=100.0))
    _patch_hold_review(monkeypatch)
    _patch_directional(monkeypatch, direction="long", fresh_flip=True)
    atr = _atr(allow_shorts=True)
    own_short = _seed_position(user_id, side="short", agent_profile_id=atr["agent_profile_id"])
    result = _run(user_id, atr["agent_profile_id"], dry_run=False)
    closes = [i for i in _closes(result) if i.get("position_id") == own_short.id]
    assert closes and closes[0]["reason"] == "flipped_short_to_long"
    assert _executed_opens(result, side="long")
    assert _position_status(own_short.id) == "closed"
    positions = _open_positions(user_id, "SPY")
    assert len(positions) == 1 and positions[0].side == "long"


def test_no_simultaneous_long_and_short_for_same_symbol_profile(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=100.0))
    _patch_hold_review(monkeypatch)
    _patch_directional(monkeypatch, direction="short", fresh_flip=True, protective_stop=105.0)
    atr = _atr(allow_shorts=True)
    _seed_position(user_id, side="long", agent_profile_id=atr["agent_profile_id"])
    _run(user_id, atr["agent_profile_id"], dry_run=False)
    positions = _open_positions(user_id, "SPY")
    # Exactly one open position remains (the flipped short) — never long+short at once.
    assert len(positions) == 1 and positions[0].side == "short"


# ── HACO / True Momentum share the directional lifecycle when allow_shorts=true ─
def test_haco_with_allow_shorts_opens_short(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=100.0))
    _patch_directional(monkeypatch, direction="short", protective_stop=105.0, primary="HACO Direction")
    haco = _create_profile({
        "agent_type": "haco_direction", "name": "HACO", "enabled": True, "allow_shorts": True,
        "universe_source": "manual", "manual_symbols": ["SPY"], "scan_depth": 1,
    })
    result = _run(user_id, haco["agent_profile_id"], dry_run=False)
    assert _executed_opens(result, side="short")
    positions = _open_positions(user_id, "SPY")
    assert len(positions) == 1 and positions[0].side == "short"


def test_true_momentum_with_allow_shorts_opens_short(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=100.0))
    _patch_directional(monkeypatch, direction="short", protective_stop=105.0, primary="True Momentum")
    tm = _create_profile({
        "agent_type": "true_momentum", "name": "TM", "enabled": True, "allow_shorts": True,
        "universe_source": "manual", "manual_symbols": ["SPY"], "scan_depth": 1,
    })
    result = _run(user_id, tm["agent_profile_id"], dry_run=False)
    assert _executed_opens(result, side="short")
    positions = _open_positions(user_id, "SPY")
    assert len(positions) == 1 and positions[0].side == "short"


def test_standard_agent_stays_long_only_and_ignores_allow_shorts_directional(monkeypatch) -> None:
    # Standard is never directional; an injected short signal is irrelevant (it
    # uses the long-only ranking eligibility path). No short is ever opened.
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=100.0))
    _patch_directional(monkeypatch, direction="short", protective_stop=105.0)
    standard = _create_profile({
        "agent_type": "standard", "name": "Std", "enabled": True,
        "universe_source": "manual", "manual_symbols": ["SPY"], "scan_depth": 1,
    })
    result = _run(user_id, standard["agent_profile_id"], dry_run=False)
    assert not _executed_opens(result, side="short")
    assert all(str(p.side) == "long" for p in _open_positions(user_id, "SPY"))


# ── ownership boundary holds on the directional path ────────────────────────────
def test_directional_agent_cannot_close_foreign_position(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=95.0))
    other = _create_profile({"agent_type": "true_momentum", "name": "Other", "enabled": True})
    foreign = _seed_position(user_id, side="long", agent_profile_id=other["agent_profile_id"])
    # Even with a close-worthy stop review AND an opposing directional signal, the
    # ATR agent must not close another profile's position.
    _force_stop_review(monkeypatch, mark=95.0)
    _patch_directional(monkeypatch, direction="short", protective_stop=105.0)
    atr = _atr(allow_shorts=True, allow_opens=False)
    result = _run(user_id, atr["agent_profile_id"], dry_run=False)
    assert any(i.get("reason") == "blocked_foreign_agent_position" for i in _intents(result))
    assert not [i for i in _closes(result) if i.get("position_id") == foreign.id]
    assert _position_status(foreign.id) == "open"


def test_directional_agent_cannot_close_manual_position(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=95.0))
    manual = _seed_position(user_id, side="long", agent_profile_id=None)
    _force_stop_review(monkeypatch, mark=95.0)
    _patch_directional(monkeypatch, direction="short", protective_stop=105.0)
    atr = _atr(allow_shorts=True, allow_opens=False)
    result = _run(user_id, atr["agent_profile_id"], dry_run=False)
    assert any(i.get("reason") == "blocked_manual_position" for i in _intents(result))
    assert not [i for i in _closes(result) if i.get("position_id") == manual.id]
    assert _position_status(manual.id) == "open"


# ── side-aware P&L for shorts ───────────────────────────────────────────────────
def test_short_realized_pnl_is_side_aware(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=95.0))
    atr = _atr(allow_shorts=True, allow_opens=False)
    short_pos = _seed_position(user_id, side="short", qty=2.0, price=100.0, agent_profile_id=atr["agent_profile_id"])
    # Protective-stop close at 95 on a short opened at 100 → profit (+5/share).
    _force_stop_review(monkeypatch, mark=95.0)
    result = _run(user_id, atr["agent_profile_id"], dry_run=False)
    closes = [i for i in _closes(result) if i.get("position_id") == short_pos.id and i.get("status") == "executed"]
    assert closes, "the agent should close its own short on a protective stop"
    assert _position_status(short_pos.id) == "closed"
    with SessionLocal() as session:
        trade = session.execute(select(PaperTradeModel).where(PaperTradeModel.position_id == short_pos.id)).scalar_one()
    # (entry - exit) * qty for a short = (100 - 95) * 2 = +10 (commission = 0 by default).
    assert round(trade.realized_pnl, 2) == 10.0
    assert trade.side == "short"
    assert trade.agent_profile_id == atr["agent_profile_id"]


def test_digest_directional_action_buckets_opened_short(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=100.0))
    _patch_directional(monkeypatch, direction="short", protective_stop=105.0)
    atr = _atr(allow_shorts=True)
    summary = _run(user_id, atr["agent_profile_id"], dry_run=False)["summary"]
    assert summary["openedShort"] == 1
    assert summary["openedLong"] == 0
    assert summary["paperOpensExecuted"] == 1


def test_digest_directional_action_buckets_flip(monkeypatch) -> None:
    user_id = _approve()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=100.0))
    _patch_hold_review(monkeypatch)
    _patch_directional(monkeypatch, direction="short", fresh_flip=True, protective_stop=105.0)
    atr = _atr(allow_shorts=True)
    _seed_position(user_id, side="long", agent_profile_id=atr["agent_profile_id"])
    summary = _run(user_id, atr["agent_profile_id"], dry_run=False)["summary"]
    # The flip close-leg is bucketed as a flip (not a plain close); the open-leg is a short.
    assert summary["flippedLongToShort"] == 1
    assert summary["openedShort"] == 1
    assert summary["closedLong"] == 0


def test_short_unrealized_pnl_is_side_aware() -> None:
    user_id = _approve()
    service = AgentModeService()
    short_pos = _seed_position(user_id, side="short", qty=2.0, price=100.0)
    snapshot = service._serialize_position_snapshot(
        short_pos,
        user=_user(user_id),
        review_by_position_id={int(short_pos.id): {"position_id": short_pos.id, "current_mark_price": 95.0}},
    )
    # Short unrealized = (entry - mark) * qty = (100 - 95) * 2 = +10.
    assert snapshot["unrealized_pnl"] == 10.0
    assert snapshot["side"] == "short"
