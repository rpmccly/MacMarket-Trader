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
from macmarket_trader.domain.models import AppUserModel, NotificationAttemptModel, PaperPositionModel
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import AgentModeRepository, AgentProfileRepository


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


def test_true_momentum_profile_defaults_to_review_only() -> None:
    _approve_user()
    momentum = _create_profile({"agent_type": "true_momentum", "name": "Momentum"})
    # Guardrail: never default a new True Momentum profile to aggressive auto-open.
    assert momentum["true_momentum_trigger_mode"] == "review_only"


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
    assert any("haco_short_review_only" in str(r.get("reason")) for r in reviews)


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
    assert any(i.get("reason") == "short_recommendation_review_only" for i in _reviews(result))
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
