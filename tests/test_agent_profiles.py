"""Phase 11 — Agent Profiles (multi-agent) tests.

Covers migration, multi-profile CRUD, the four agent types' trigger eligibility,
profile-scoped runs/trades/performance, one-digest-per-profile notifications, user
isolation, no-paper-shorts, and scheduler diagnostics across profiles.

Indicator outputs are monkeypatched at the trigger module boundary so the real
dispatch/run-loop integration is exercised without depending on indicator math.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.agent_mode.service import AgentModeService
from macmarket_trader.api.main import app
from macmarket_trader.api.routes import admin as admin_routes
from macmarket_trader.api.routes import agent_mode as agent_mode_routes
from macmarket_trader.data.providers.market_data import DeterministicFallbackMarketDataProvider, MarketSnapshot
from macmarket_trader.domain.models import AppUserModel, NotificationAttemptModel, PaperPositionModel, PaperTradeModel
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import AgentModeRepository, AgentProfileRepository, PaperPortfolioRepository


client = TestClient(app)
USER_AUTH = {"Authorization": "Bearer user-token"}
ADMIN_AUTH = {"Authorization": "Bearer admin-token"}


class StubMarketData:
    def __init__(self, *, mark: float = 105.0) -> None:
        self.provider = DeterministicFallbackMarketDataProvider()
        self.mark = mark
        self.last_historical_metadata = {"session_policy": "regular_hours", "source_timeframe": "1D"}

    def historical_bars(self, symbol: str, timeframe: str, limit: int):
        return self.provider.fetch_historical_bars(symbol, timeframe, limit), "polygon", False

    def latest_snapshot(self, symbol: str, timeframe: str = "1D") -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol, timeframe=timeframe, as_of=datetime(2026, 5, 31, 15, 55, tzinfo=timezone.utc),
            open=self.mark, high=self.mark, low=self.mark, close=self.mark, volume=1_000_000,
            source="polygon", fallback_mode=False,
        )


def _approve_user(*, external_auth_user_id: str = "clerk_user", headers=None) -> int:
    response = client.get("/user/me", headers=headers or USER_AUTH)
    assert response.status_code == 200, response.text
    with SessionLocal() as session:
        user = session.execute(
            select(AppUserModel).where(AppUserModel.external_auth_user_id == external_auth_user_id)
        ).scalar_one()
        user.approval_status = "approved"
        session.commit()
        return user.id


def _user(user_id: int) -> AppUserModel:
    with SessionLocal() as session:
        return session.get(AppUserModel, user_id)


# ── Indicator fakes (state-controlled) ───────────────────────────────────────
class _HacoPoint:
    def __init__(self, state: str, flip=None) -> None:
        self.state = state
        self.flip = flip


class _ScorePoint:
    def __init__(self, total_state: str, trend_score: float = 0.0) -> None:
        self.total_state = total_state
        self.total_label = total_state
        self.trend_score = trend_score


class _TmPoint:
    def __init__(self, *, cross_up=False, cross_down=False, new_bull_signal=False, new_bear_signal=False, trend_direction=0) -> None:
        self.cross_up = cross_up
        self.cross_down = cross_down
        self.new_bull_signal = new_bull_signal
        self.new_bear_signal = new_bear_signal
        self.trend_direction = trend_direction


class _Series:
    def __init__(self, points) -> None:
        self.points = points


def _patch_haco(monkeypatch, state: str) -> None:
    monkeypatch.setattr("macmarket_trader.agent_mode.triggers.compute_haco_states", lambda *a, **k: [_HacoPoint(state)])


def _patch_momentum(monkeypatch, *, total_state: str, trend_score: float = 0.0, **tm) -> None:
    monkeypatch.setattr(
        "macmarket_trader.agent_mode.triggers.compute_true_momentum_score",
        lambda *a, **k: _Series([_ScorePoint(total_state, trend_score)]),
    )
    monkeypatch.setattr(
        "macmarket_trader.agent_mode.triggers.compute_true_momentum",
        lambda *a, **k: _Series([_TmPoint(**tm)]),
    )


def _create_profile(payload: dict) -> dict:
    response = client.post("/user/agent-mode/profiles", json=payload, headers=USER_AUTH)
    assert response.status_code == 200, response.text
    return response.json()


def _run(profile_id: int, *, dry_run: bool = True, no_notifications: bool = True) -> dict:
    return agent_mode_routes.agent_service.run(
        user=_user(_approve_user.__wrapped__ if False else profile_id and _CURRENT_USER[0]),
        request={"mode": "paper", "dry_run": dry_run, "profile_id": profile_id, "no_notifications": no_notifications},
    )


_CURRENT_USER = [0]


def _service_run(user_id: int, profile_id: int, *, dry_run: bool = True) -> dict:
    return agent_mode_routes.agent_service.run(
        user=_user(user_id),
        request={"mode": "paper", "dry_run": dry_run, "profile_id": profile_id, "no_notifications": True},
    )


def _intents(result: dict) -> list[dict]:
    return list(result.get("intents") or [])


def _opens(result: dict) -> list[dict]:
    return [i for i in _intents(result) if i.get("intent") == "OPEN_PAPER"]


def _reviews(result: dict) -> list[dict]:
    return [i for i in _intents(result) if i.get("status") == "review_only"]


# ── Migration + serialization ────────────────────────────────────────────────
def test_migration_creates_default_standard_profile_and_is_idempotent() -> None:
    user_id = _approve_user()
    AgentModeRepository(SessionLocal).update_settings(
        app_user_id=user_id, updates={"enabled": True, "daily_run_time": "12:00", "timezone": "UTC"}
    )
    repo = AgentProfileRepository(SessionLocal)
    first = repo.migrate_legacy_settings_to_profiles()
    assert first["profiles_created"] == 1
    profiles = repo.list_profiles(app_user_id=user_id)
    assert len(profiles) == 1
    assert profiles[0].name == "Standard Strategy Agent"
    assert profiles[0].agent_type == "standard"
    assert bool(profiles[0].is_default) is True
    assert bool(profiles[0].enabled) is True
    assert profiles[0].daily_run_time == "12:00"
    # Default Standard strategies preserve the legacy first-three behavior.
    assert profiles[0].strategy_families == [
        "event_continuation", "breakout_prior_day_high", "pullback_trend_continuation"
    ]
    again = repo.migrate_legacy_settings_to_profiles()
    assert again["profiles_created"] == 0
    assert len(repo.list_profiles(app_user_id=user_id)) == 1


def test_serialize_profile_is_superset_of_settings() -> None:
    user_id = _approve_user()
    settings_row = AgentModeRepository(SessionLocal).get_or_create_settings(app_user_id=user_id)
    profile = AgentProfileRepository(SessionLocal).get_default_profile(app_user_id=user_id)
    settings_keys = set(AgentModeService.serialize_settings(settings_row).keys())
    profile_keys = set(AgentModeService.serialize_profile(profile).keys())
    assert settings_keys.issubset(profile_keys)
    assert {"agent_type", "strategy_families", "haco_direction_mode", "true_momentum_trigger_mode"}.issubset(profile_keys)


# ── Multiple profiles + CRUD ─────────────────────────────────────────────────
def test_user_can_create_multiple_profiles() -> None:
    _approve_user()
    standard = client.get("/user/agent-mode/settings", headers=USER_AUTH).json()  # triggers default creation
    assert standard["agent_type"] == "standard"
    haco = _create_profile({"agent_type": "haco_direction", "name": "HACO"})
    momentum = _create_profile({"agent_type": "true_momentum", "name": "Momentum"})
    hybrid = _create_profile({"agent_type": "hybrid", "name": "Hybrid"})
    listing = client.get("/user/agent-mode/profiles", headers=USER_AUTH).json()
    types = {p["agent_type"] for p in listing["profiles"]}
    assert types == {"standard", "haco_direction", "true_momentum", "hybrid"}
    assert len(listing["profiles"]) == 4
    assert haco["agent_type"] == "haco_direction"
    assert momentum["agent_type"] == "true_momentum"
    assert hybrid["agent_type"] == "hybrid"


def test_true_momentum_profile_defaults_to_conservative() -> None:
    _approve_user()
    momentum = _create_profile({"agent_type": "true_momentum", "name": "Momentum"})
    # New True Momentum profiles are intended to trade: default to conservative
    # (long-term + short-term aligned), never aggressive.
    assert momentum["true_momentum_trigger_mode"] == "conservative"
    # review_only remains explicitly selectable as a safe, no-open mode.
    updated = client.put(
        f"/user/agent-mode/profiles/{momentum['profile_uid']}",
        json={"true_momentum_trigger_mode": "review_only"},
        headers=USER_AUTH,
    ).json()
    assert updated["true_momentum_trigger_mode"] == "review_only"


def test_delete_default_and_last_profile_blocked() -> None:
    _approve_user()
    default = client.get("/user/agent-mode/settings", headers=USER_AUTH).json()
    # Cannot delete the default profile.
    blocked = client.delete(f"/user/agent-mode/profiles/{default['profile_uid']}", headers=USER_AUTH)
    assert blocked.status_code == 409
    # Create a second, make it default, then the original can be deleted but never the last.
    extra = _create_profile({"agent_type": "haco_direction", "name": "HACO"})
    client.post(f"/user/agent-mode/profiles/{extra['profile_uid']}/default", headers=USER_AUTH)
    deleted = client.delete(f"/user/agent-mode/profiles/{default['profile_uid']}", headers=USER_AUTH)
    assert deleted.status_code == 200
    last = client.delete(f"/user/agent-mode/profiles/{extra['profile_uid']}", headers=USER_AUTH)
    assert last.status_code == 409


# ── Agent-type trigger eligibility ───────────────────────────────────────────
def test_haco_profile_only_uses_haco_triggers(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    haco = _create_profile({"agent_type": "haco_direction", "name": "HACO", "haco_direction_mode": "long_and_short"})

    _patch_haco(monkeypatch, "green")
    green = _service_run(user_id, haco["agent_profile_id"], dry_run=True)
    opens = _opens(green)
    assert opens, "HACO green should produce eligible long candidates"
    assert all(i.get("primary_trigger") == "HACO Direction" for i in opens)

    _patch_haco(monkeypatch, "red")
    red = _service_run(user_id, haco["agent_profile_id"], dry_run=True)
    assert not _opens(red), "HACO red must not open a paper long"
    reviews = _reviews(red)
    assert reviews and all(r.get("primary_trigger") == "HACO Direction" for r in reviews)
    assert any(r.get("reason") == "paper_short_not_supported" for r in reviews)


def test_haco_short_is_review_only_and_never_a_paper_short(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    haco = _create_profile({
        "agent_type": "haco_direction", "name": "HACO", "haco_direction_mode": "short_only", "enabled": True,
    })
    _patch_haco(monkeypatch, "red")
    # Enabled, non-dry run: a short signal must never create a paper order/position.
    result = _service_run(user_id, haco["agent_profile_id"], dry_run=False)
    assert not _opens(result)
    assert all(i.get("side", "long") == "long" for i in _intents(result))
    assert _reviews(result)
    with SessionLocal() as session:
        positions = list(session.execute(select(PaperPositionModel).where(PaperPositionModel.app_user_id == user_id)).scalars())
    assert positions == []


class _FakeShortSide:
    value = "short"


class _FakeShortRec:
    approved = True
    rejection_reason = None
    recommendation_id = "rec_fake_short"
    side = _FakeShortSide()


def test_enabled_run_never_routes_a_paper_short_even_if_recommendation_is_short(monkeypatch) -> None:
    # Even when the deterministic engine resolves a short and the user-approval
    # override approves it, Agent Mode must never create a paper short.
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    monkeypatch.setattr(admin_routes.recommendation_service, "generate", lambda *a, **k: _FakeShortRec())
    haco = _create_profile({
        "agent_type": "haco_direction", "name": "HACO", "haco_direction_mode": "long_and_short", "enabled": True,
    })
    _patch_haco(monkeypatch, "green")  # long-eligible candidates reach _execute_open

    result = _service_run(user_id, haco["agent_profile_id"], dry_run=False)

    # No paper short order/position is created; the short rec becomes review-only.
    assert not [i for i in _intents(result) if i.get("intent") == "OPEN_PAPER" and i.get("status") == "executed"]
    assert any(i.get("reason") == "paper_short_not_supported" for i in _reviews(result))
    assert int(result["summary"].get("executedOrderCount", 0)) == 0
    with SessionLocal() as session:
        positions = list(session.execute(select(PaperPositionModel).where(PaperPositionModel.app_user_id == user_id)).scalars())
    assert positions == []


def test_true_momentum_trigger_modes_gate_candidates(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())

    review_only = _create_profile({"agent_type": "true_momentum", "name": "Review", "true_momentum_trigger_mode": "review_only"})
    conservative = _create_profile({"agent_type": "true_momentum", "name": "Cons", "true_momentum_trigger_mode": "conservative"})
    aggressive = _create_profile({"agent_type": "true_momentum", "name": "Aggr", "true_momentum_trigger_mode": "aggressive"})

    # review_only never opens, even with a strong bullish read.
    _patch_momentum(monkeypatch, total_state="max_bull", trend_score=80.0, cross_up=True, trend_direction=1)
    assert not _opens(_service_run(user_id, review_only["agent_profile_id"]))

    # conservative requires long-term bullish AND short-term rising → opens.
    assert _opens(_service_run(user_id, conservative["agent_profile_id"]))

    # conservative does NOT open when long-term is only neutral/improving.
    _patch_momentum(monkeypatch, total_state="neutral_up", trend_score=5.0, cross_up=True, new_bull_signal=True)
    assert not _opens(_service_run(user_id, conservative["agent_profile_id"]))

    # aggressive opens on a short-term trigger when long-term is neutral/improving.
    assert _opens(_service_run(user_id, aggressive["agent_profile_id"]))


def test_hybrid_combines_standard_and_filters(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    hybrid = _create_profile({
        "agent_type": "hybrid", "name": "Hybrid", "use_haco_filter": True, "use_true_momentum_confirmation": True,
        "true_momentum_trigger_mode": "balanced",
    })
    # Top-ranked Standard candidate + HACO long + momentum confirmed → eligible.
    _patch_haco(monkeypatch, "green")
    _patch_momentum(monkeypatch, total_state="bull", trend_score=60.0, cross_up=True)
    confirmed = _service_run(user_id, hybrid["agent_profile_id"])
    if _opens(confirmed):
        assert all(i.get("primary_trigger") == "Hybrid" for i in _opens(confirmed))

    # HACO filter red blocks the hybrid open even when ranking is favorable.
    _patch_haco(monkeypatch, "red")
    blocked = _service_run(user_id, hybrid["agent_profile_id"])
    assert not _opens(blocked)


def test_standard_profile_uses_selected_strategies(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    captured: dict[str, object] = {}

    def _spy(**kwargs):
        captured["strategies"] = list(kwargs.get("strategies") or [])
        return {"queue": []}

    monkeypatch.setattr(admin_routes.ranking_engine, "rank_candidates", _spy)
    standard = _create_profile({
        "agent_type": "standard", "name": "Picked",
        "strategy_families": ["breakout_prior_day_high", "mean_reversion"],
    })
    _service_run(user_id, standard["agent_profile_id"])
    assert captured["strategies"] == ["Breakout / Prior-Day High", "Mean Reversion"]


# ── Enabled runs actually open paper longs on valid long triggers ────────────
def test_haco_green_enabled_creates_one_paper_long(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    _patch_haco(monkeypatch, "green")
    haco = _create_profile({
        "agent_type": "haco_direction", "name": "HACO Long", "haco_direction_mode": "long_only",
        "enabled": True, "universe_source": "manual", "manual_symbols": ["SPY"], "scan_depth": 1,
    })
    result = _service_run(user_id, haco["agent_profile_id"], dry_run=False)
    opens = [i for i in _intents(result) if i.get("intent") == "OPEN_PAPER" and i.get("status") == "executed"]
    assert len(opens) == 1
    assert opens[0]["side"] == "long"
    assert opens[0].get("outcome") == "opened_paper_long"
    assert opens[0].get("primary_trigger") == "HACO Direction"
    assert result["summary"]["paperOpensExecuted"] == 1
    with SessionLocal() as session:
        positions = list(session.execute(select(PaperPositionModel).where(PaperPositionModel.app_user_id == user_id)).scalars())
    assert len(positions) == 1
    assert positions[0].side == "long"


def test_true_momentum_conservative_enabled_creates_one_paper_long(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    _patch_momentum(monkeypatch, total_state="max_bull", trend_score=90.0, cross_up=True, trend_direction=1)
    tm = _create_profile({
        "agent_type": "true_momentum", "name": "TM Cons", "true_momentum_trigger_mode": "conservative",
        "enabled": True, "universe_source": "manual", "manual_symbols": ["SPY"], "scan_depth": 1,
    })
    result = _service_run(user_id, tm["agent_profile_id"], dry_run=False)
    opens = [i for i in _intents(result) if i.get("intent") == "OPEN_PAPER" and i.get("status") == "executed"]
    assert len(opens) == 1
    assert opens[0]["side"] == "long"
    assert opens[0].get("outcome") == "opened_paper_long"
    assert opens[0].get("primary_trigger") == "True Momentum"
    assert result["summary"]["paperOpensExecuted"] == 1


def test_watchlist_profile_without_watchlist_is_no_universe(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    prof = _create_profile({"agent_type": "standard", "name": "WL", "universe_source": "watchlist", "enabled": True})
    result = _service_run(user_id, prof["agent_profile_id"], dry_run=True)
    assert result["summary"]["noUniverse"] is True
    assert "watchlist" in str(result["summary"]["universeSkipReason"])
    assert result["summary"]["skipReason"] == result["summary"]["universeSkipReason"]
    assert not [i for i in _intents(result) if i.get("intent") == "OPEN_PAPER"]


def test_manual_universe_resolves_per_profile(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    a = _create_profile({"agent_type": "standard", "name": "A", "universe_source": "manual", "manual_symbols": ["SPY"]})
    b = _create_profile({"agent_type": "standard", "name": "B", "universe_source": "manual", "manual_symbols": ["QQQ", "MTUM"]})
    ra = _service_run(user_id, a["agent_profile_id"], dry_run=True)
    rb = _service_run(user_id, b["agent_profile_id"], dry_run=True)
    assert ra["universe"]["symbols"] == ["SPY"]
    assert rb["universe"]["symbols"] == ["QQQ", "MTUM"]


# ── Profile-scoped runs/trades/performance ───────────────────────────────────
def test_runs_filter_by_profile(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    a = _create_profile({"agent_type": "standard", "name": "A"})
    b = _create_profile({"agent_type": "haco_direction", "name": "B"})
    _patch_haco(monkeypatch, "green")
    _service_run(user_id, a["agent_profile_id"])
    _service_run(user_id, b["agent_profile_id"])
    _service_run(user_id, b["agent_profile_id"])

    runs_a = client.get(f"/user/agent-mode/runs?profile_id={a['agent_profile_id']}", headers=USER_AUTH).json()
    runs_b = client.get(f"/user/agent-mode/runs?profile_id={b['agent_profile_id']}", headers=USER_AUTH).json()
    all_runs = client.get("/user/agent-mode/runs", headers=USER_AUTH).json()
    assert len(runs_a["items"]) == 1
    assert len(runs_b["items"]) == 2
    assert len(all_runs["items"]) == 3
    assert all(item["agentProfileId"] == a["agent_profile_id"] for item in runs_a["items"])


# ── Notifications: one digest per profile run per channel ────────────────────
def test_one_digest_per_profile_run_per_channel(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    for name in ("Alpha", "Bravo"):
        _create_profile({
            "agent_type": "standard", "name": name, "enabled": True, "daily_run_time": "09:30", "timezone": "UTC",
            "notification_preference": "email",
        })
    runs = AgentModeService().run_due(now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc))
    completed = [r for r in runs if r.get("status") == "completed"]
    assert len(completed) == 2
    with SessionLocal() as session:
        attempts = list(session.execute(select(NotificationAttemptModel)).scalars())
    email_attempts = [a for a in attempts if a.channel == "email"]
    # Exactly one email digest per profile run, distinct run ids.
    assert len(email_attempts) == 2
    assert len({a.run_id for a in email_attempts}) == 2


# ── User isolation ───────────────────────────────────────────────────────────
def test_profiles_are_user_scoped(monkeypatch) -> None:
    owner_id = _approve_user(external_auth_user_id="clerk_user", headers=USER_AUTH)
    owner_profile = _create_profile({"agent_type": "haco_direction", "name": "Owner HACO"})
    # A different approved user must not see or run the owner's profile.
    other_headers = {"Authorization": "Bearer admin-token"}
    _approve_user(external_auth_user_id="clerk_admin", headers=other_headers)
    blocked = client.get(f"/user/agent-mode/profiles/{owner_profile['profile_uid']}", headers=other_headers)
    assert blocked.status_code == 404
    other_list = client.get("/user/agent-mode/profiles", headers=other_headers).json()
    assert owner_profile["profile_uid"] not in {p["profile_uid"] for p in other_list["profiles"]}
    del owner_id


# ── Scheduler diagnostics across profiles (post-deploy smoke) ────────────────
def test_scheduler_diagnostics_lists_multiple_profiles(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    client.get("/user/agent-mode/settings", headers=USER_AUTH)  # creates the default Standard profile
    _create_profile({"agent_type": "standard", "name": "S", "enabled": True, "daily_run_time": "09:30", "timezone": "UTC"})
    _create_profile({"agent_type": "true_momentum", "name": "M", "enabled": True, "daily_run_time": "09:30", "timezone": "UTC"})
    diagnostics = AgentModeService().scheduler_diagnostics(now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc))
    user_profiles = [row for row in diagnostics["profiles"] if row["app_user_id"] == user_id]
    assert len(user_profiles) >= 3  # default Standard + the two created
    assert diagnostics["counts"]["profiles"] >= 3
    assert {row["agent_type"] for row in user_profiles} >= {"standard", "true_momentum"}
    del user_id


# ── Ownership boundary: an agent manages (closes/flips) ONLY its own positions ─
def _seed_position(user_id, *, symbol="SPY", side="long", qty=2.0, price=100.0, agent_profile_id=None):
    return PaperPortfolioRepository(SessionLocal).create_position(
        app_user_id=user_id, symbol=symbol, side=side, quantity=qty,
        average_price=price, agent_profile_id=agent_profile_id,
    )


def _force_stop_review(monkeypatch, *, mark=94.0):
    """Force every open position to look stop-triggered (close-worthy)."""
    def _review(position, **_kwargs):
        return {
            "position_id": position.id,
            "symbol": position.symbol,
            "side": position.side,
            "current_mark_price": mark,
            "action_classification": "stop_triggered",
            "action_summary": f"{position.symbol} protective stop triggered",
            "warnings": [],
            "missing_data": [],
        }
    monkeypatch.setattr(admin_routes, "_build_position_review", _review)


def _force_hold_review(monkeypatch):
    """Force every open position to look like a benign hold (no close-worthy action)."""
    def _review(position, **_kwargs):
        return {
            "position_id": position.id,
            "symbol": position.symbol,
            "side": position.side,
            "current_mark_price": 100.0,
            "action_classification": "hold",
            "action_summary": f"{position.symbol} hold",
            "warnings": [],
            "missing_data": [],
        }
    monkeypatch.setattr(admin_routes, "_build_position_review", _review)


def _own_profile(agent_type, name, **extra):
    payload = {
        "agent_type": agent_type, "name": name, "enabled": True,
        "allow_opens": False, "universe_source": "manual", "manual_symbols": ["SPY"],
    }
    payload.update(extra)
    return _create_profile(payload)


def _position_status(position_id):
    with SessionLocal() as session:
        row = session.get(PaperPositionModel, position_id)
        return row.status if row else None


def test_ownership_haco_cannot_close_true_momentum_position(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=94.0))
    haco = _own_profile("haco_direction", "HACO")
    tm = _own_profile("true_momentum", "TM")
    tm_pos = _seed_position(user_id, agent_profile_id=tm["agent_profile_id"])
    _force_stop_review(monkeypatch)
    result = _service_run(user_id, haco["agent_profile_id"], dry_run=False)
    blocks = [i for i in _intents(result) if i.get("reason") == "blocked_foreign_agent_position"]
    assert blocks and blocks[0]["position_id"] == tm_pos.id
    assert blocks[0]["position_owner"] == "foreign_agent"
    assert not [i for i in _intents(result) if i.get("intent") == "CLOSE_PAPER"]
    assert _position_status(tm_pos.id) == "open"  # never closed by a foreign agent


def test_ownership_true_momentum_cannot_close_haco_position(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=94.0))
    haco = _own_profile("haco_direction", "HACO")
    tm = _own_profile("true_momentum", "TM")
    haco_pos = _seed_position(user_id, agent_profile_id=haco["agent_profile_id"])
    _force_stop_review(monkeypatch)
    result = _service_run(user_id, tm["agent_profile_id"], dry_run=False)
    blocks = [i for i in _intents(result) if i.get("reason") == "blocked_foreign_agent_position"]
    assert blocks and blocks[0]["position_id"] == haco_pos.id
    assert not [i for i in _intents(result) if i.get("intent") == "CLOSE_PAPER"]
    assert _position_status(haco_pos.id) == "open"


def test_ownership_atr_cannot_close_manual_position(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=94.0))
    atr = _own_profile("atr_trailing_stop", "ATR")
    manual_pos = _seed_position(user_id, agent_profile_id=None)  # manual paper trade (NULL owner)
    _force_stop_review(monkeypatch)
    result = _service_run(user_id, atr["agent_profile_id"], dry_run=False)
    blocks = [i for i in _intents(result) if i.get("reason") == "blocked_manual_position"]
    assert blocks and blocks[0]["position_id"] == manual_pos.id
    assert blocks[0]["position_owner"] == "manual"
    assert not [i for i in _intents(result) if i.get("intent") == "CLOSE_PAPER"]
    assert _position_status(manual_pos.id) == "open"  # manual trades are never agent-closed


def test_ownership_agent_closes_only_its_own_position(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=94.0))
    haco = _own_profile("haco_direction", "HACO")
    own_pos = _seed_position(user_id, agent_profile_id=haco["agent_profile_id"])
    _force_stop_review(monkeypatch)
    result = _service_run(user_id, haco["agent_profile_id"], dry_run=False)
    closes = [i for i in _intents(result) if i.get("intent") == "CLOSE_PAPER"]
    assert len(closes) == 1
    assert closes[0]["position_id"] == own_pos.id
    assert closes[0]["position_owner"] == "own"
    assert closes[0].get("action_reason") == "managed_own_position"
    assert closes[0]["status"] == "executed"
    assert _position_status(own_pos.id) == "closed"
    # The realized trade is tagged to the owning profile.
    with SessionLocal() as session:
        trade = session.execute(
            select(PaperTradeModel).where(PaperTradeModel.position_id == own_pos.id)
        ).scalar_one()
    assert trade.agent_profile_id == haco["agent_profile_id"]


def test_all_agents_view_aggregates_but_execution_is_profile_owned(monkeypatch) -> None:
    # The user can SEE positions across all profiles, but a single run only acts
    # on the running profile's own positions (others become block reviews).
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=94.0))
    haco = _own_profile("haco_direction", "HACO")
    tm = _own_profile("true_momentum", "TM")
    haco_pos = _seed_position(user_id, symbol="SPY", agent_profile_id=haco["agent_profile_id"])
    tm_pos = _seed_position(user_id, symbol="QQQ", agent_profile_id=tm["agent_profile_id"])
    _force_stop_review(monkeypatch)
    result = _service_run(user_id, haco["agent_profile_id"], dry_run=False)
    closes = [i for i in _intents(result) if i.get("intent") == "CLOSE_PAPER"]
    assert {i["position_id"] for i in closes} == {haco_pos.id}
    assert any(
        i.get("reason") == "blocked_foreign_agent_position" and i["position_id"] == tm_pos.id
        for i in _intents(result)
    )
    assert _position_status(haco_pos.id) == "closed"
    assert _position_status(tm_pos.id) == "open"


def test_digest_distinguishes_owned_actions_from_reviewed_external(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData(mark=94.0))
    haco = _own_profile("haco_direction", "HACO")
    tm = _own_profile("true_momentum", "TM")
    _seed_position(user_id, symbol="SPY", agent_profile_id=haco["agent_profile_id"])
    _seed_position(user_id, symbol="QQQ", agent_profile_id=tm["agent_profile_id"])
    _force_stop_review(monkeypatch)
    summary = _service_run(user_id, haco["agent_profile_id"], dry_run=False)["summary"]
    assert summary["paperClosesExecuted"] == 1            # owned position acted on
    assert summary["reviewedExternalPositions"] == 1      # foreign reviewed, never closed
    assert summary["reviewedExternalPositions"] <= summary["triggerReviewOnly"]


# ── Optional cross-profile opposing-exposure guard (default OFF) ──────────────
def test_cross_profile_opposing_open_allowed_by_default(monkeypatch) -> None:
    # Default: a long open is NOT blocked just because another profile holds an
    # opposing short in the same symbol.
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    _patch_haco(monkeypatch, "green")
    _force_hold_review(monkeypatch)
    other = _own_profile("true_momentum", "TM")
    _seed_position(user_id, symbol="SPY", side="short", agent_profile_id=other["agent_profile_id"])
    haco = _create_profile({
        "agent_type": "haco_direction", "name": "HACO", "haco_direction_mode": "long_only",
        "enabled": True, "universe_source": "manual", "manual_symbols": ["SPY"], "scan_depth": 1,
    })
    result = _service_run(user_id, haco["agent_profile_id"], dry_run=False)
    assert not [i for i in _intents(result) if i.get("reason") == "blocked_opposing_cross_profile"]
    opens = [i for i in _intents(result) if i.get("intent") == "OPEN_PAPER" and i.get("status") == "executed"]
    assert len(opens) == 1  # the long open proceeds despite the cross-profile short


def test_cross_profile_opposing_open_blocked_when_enabled(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    _patch_haco(monkeypatch, "green")
    _force_hold_review(monkeypatch)
    other = _own_profile("true_momentum", "TM")
    short_pos = _seed_position(user_id, symbol="SPY", side="short", agent_profile_id=other["agent_profile_id"])
    haco = _create_profile({
        "agent_type": "haco_direction", "name": "HACO", "haco_direction_mode": "long_only",
        "enabled": True, "universe_source": "manual", "manual_symbols": ["SPY"], "scan_depth": 1,
        "prevent_opposing_agent_positions_across_profiles": True,
    })
    result = _service_run(user_id, haco["agent_profile_id"], dry_run=False)
    blocked = [i for i in _intents(result) if i.get("reason") == "blocked_opposing_cross_profile"]
    assert blocked and blocked[0]["symbol"] == "SPY"
    assert not [i for i in _intents(result) if i.get("intent") == "OPEN_PAPER" and i.get("status") == "executed"]
    assert _position_status(short_pos.id) == "open"  # the other profile's short is NOT closed


# ── Market-session scheduler guard: no scheduled trading on closed days ───────
SATURDAY = datetime(2026, 6, 6, 15, 0, tzinfo=timezone.utc)
SUNDAY = datetime(2026, 6, 7, 15, 0, tzinfo=timezone.utc)
MONDAY = datetime(2026, 6, 8, 15, 0, tzinfo=timezone.utc)
HOLIDAY = datetime(2026, 7, 3, 15, 0, tzinfo=timezone.utc)  # Independence Day (observed)


def _enabled_scheduled_profile(name="Sched"):
    return _create_profile({
        "agent_type": "standard", "name": name, "enabled": True,
        "daily_run_time": "09:30", "timezone": "UTC",
        "universe_source": "manual", "manual_symbols": ["SPY"],
    })


def test_scheduler_skips_saturday_and_sunday(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    prof = _enabled_scheduled_profile()
    for now in (SATURDAY, SUNDAY):
        rows = AgentModeService().run_due(now=now)
        mine = [r for r in rows if r.get("agent_profile_id") == prof["agent_profile_id"]]
        assert mine and all(r["status"] == "skipped" for r in mine)
        assert all(r["reason"] == "market_closed_weekend" for r in mine)
        assert all(r.get("market_closed") is True for r in mine)
        # A weekend tick never produces a completed (trading) run.
        assert not [r for r in rows if r.get("status") == "completed"]


def test_scheduler_skips_known_market_holiday(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    prof = _enabled_scheduled_profile()
    rows = AgentModeService().run_due(now=HOLIDAY)
    mine = [r for r in rows if r.get("agent_profile_id") == prof["agent_profile_id"]]
    assert mine and all(r["reason"] == "market_closed_holiday" for r in mine)
    assert not [r for r in rows if r.get("status") == "completed"]


def test_scheduler_runs_on_monday_after_weekend(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    prof = _enabled_scheduled_profile()
    # Weekend ticks skip WITHOUT claiming the window...
    AgentModeService().run_due(now=SATURDAY)
    AgentModeService().run_due(now=SUNDAY)
    # ...so Monday still runs (the weekend never claimed or dup-blocked it).
    rows = AgentModeService().run_due(now=MONDAY)
    mine = [r for r in rows if r.get("agent_profile_id") == prof["agent_profile_id"]]
    assert mine and mine[0]["status"] == "completed"
    # Exactly one scheduled run row exists for the Monday window (no duplicate).
    runs = client.get(f"/user/agent-mode/runs?profile_id={prof['agent_profile_id']}", headers=USER_AUTH).json()
    assert len(runs["items"]) == 1


def test_scheduler_weekend_creates_no_runs_or_orders(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    prof = _enabled_scheduled_profile()
    AgentModeService().run_due(now=SATURDAY)
    # No run rows, no positions, no notification attempts created on a weekend.
    runs = client.get(f"/user/agent-mode/runs?profile_id={prof['agent_profile_id']}", headers=USER_AUTH).json()
    assert runs["items"] == []
    with SessionLocal() as session:
        positions = list(session.execute(select(PaperPositionModel).where(PaperPositionModel.app_user_id == user_id)).scalars())
        attempts = list(session.execute(select(NotificationAttemptModel)).scalars())
    assert positions == []
    assert attempts == []


def test_manual_dry_run_labeled_market_closed_on_weekend(monkeypatch) -> None:
    user_id = _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    prof = _enabled_scheduled_profile()
    # A manual dry-run may still run, but must be labeled market_closed.
    import macmarket_trader.agent_mode.service as svc
    monkeypatch.setattr(svc, "utc_now", lambda: SATURDAY)
    result = _service_run(user_id, prof["agent_profile_id"], dry_run=True)
    assert result["summary"]["marketClosed"] is True
    assert result["summary"]["marketSession"]["closed_reason"] == "market_closed_weekend"


def test_scheduler_diagnostics_report_market_session(monkeypatch) -> None:
    _approve_user()
    monkeypatch.setattr(admin_routes, "market_data_service", StubMarketData())
    _enabled_scheduled_profile()
    diag = AgentModeService().scheduler_diagnostics(now=SATURDAY)
    assert diag["market_session"]["closed_reason"] == "market_closed_weekend"
    assert diag["scheduler"]["market_open_today"] is False
    assert diag["scheduler"]["skips_weekends_and_holidays"] is True
    row = next(r for r in diag["profiles"])
    assert row["market_open_today"] is False
    assert row["would_run_now"] is False  # never "would run" on a closed day
    assert str(row["next_eligible_trading_run"]).startswith("2026-06-08")  # next Monday
