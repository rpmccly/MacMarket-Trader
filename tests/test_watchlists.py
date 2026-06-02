from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.domain.models import AppUserModel, WatchlistModel
from macmarket_trader.symbols.starter_watchlists import (
    STARTER_MARKET_WATCHLIST_NAME,
    starter_market_watchlist_symbols,
)
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import WatchlistRepository

client = TestClient(app)


def _seed_and_approve_user() -> int:
    client.get("/user/me", headers={"Authorization": "Bearer user-token"})
    with SessionLocal() as session:
        user = session.execute(
            select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_user")
        ).scalar_one()
        user.approval_status = "approved"
        session.commit()
        return user.id


def _approve_user(*, token: str, external_auth_user_id: str) -> int:
    client.get("/user/me", headers={"Authorization": f"Bearer {token}"})
    with SessionLocal() as session:
        user = session.execute(
            select(AppUserModel).where(AppUserModel.external_auth_user_id == external_auth_user_id)
        ).scalar_one()
        user.approval_status = "approved"
        session.commit()
        return user.id


def _watchlists_for_user(app_user_id: int) -> list[WatchlistModel]:
    with SessionLocal() as session:
        return list(
            session.execute(
                select(WatchlistModel)
                .where(WatchlistModel.app_user_id == app_user_id)
                .order_by(WatchlistModel.id.asc())
            ).scalars()
        )


def test_new_auth_user_creation_seeds_starter_watchlist_once() -> None:
    client.get("/user/me", headers={"Authorization": "Bearer user-token"})

    with SessionLocal() as session:
        user = session.execute(
            select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_user")
        ).scalar_one()
        rows = list(
            session.execute(
                select(WatchlistModel).where(WatchlistModel.app_user_id == user.id)
            ).scalars()
        )

    assert len(rows) == 1
    assert rows[0].name == STARTER_MARKET_WATCHLIST_NAME
    assert rows[0].symbols == starter_market_watchlist_symbols()
    assert len(rows[0].symbols) == 25


def test_get_watchlists_returns_seeded_list_for_newly_approved_user() -> None:
    _seed_and_approve_user()

    resp = client.get("/user/watchlists", headers={"Authorization": "Bearer user-token"})
    assert resp.status_code == 200
    payload = resp.json()

    assert len(payload) == 1
    assert payload[0]["name"] == STARTER_MARKET_WATCHLIST_NAME
    assert payload[0]["symbols"] == starter_market_watchlist_symbols()
    assert payload[0]["is_starter"] is True
    assert payload[0]["is_default"] is True
    assert "Agent Mode" in payload[0]["usage_hints"]


def test_get_watchlists_does_not_reseed_after_user_deletes_all_watchlists() -> None:
    _seed_and_approve_user()
    initial = client.get("/user/watchlists", headers={"Authorization": "Bearer user-token"})
    assert initial.status_code == 200
    starter_id = initial.json()[0]["id"]

    deleted = client.delete(
        f"/user/watchlists/{starter_id}",
        headers={"Authorization": "Bearer user-token"},
    )
    assert deleted.status_code == 200

    after_delete = client.get("/user/watchlists", headers={"Authorization": "Bearer user-token"})
    assert after_delete.status_code == 200
    assert after_delete.json() == []


def test_starter_watchlist_repository_helper_is_idempotent() -> None:
    with SessionLocal() as session:
        user = AppUserModel(
            external_auth_user_id="manual_backfill_user",
            email="manual.backfill@example.com",
            display_name="Manual Backfill",
            approval_status="approved",
            app_role="user",
            mfa_enabled=False,
        )
        session.add(user)
        session.commit()
        user_id = user.id

    repo = WatchlistRepository(SessionLocal)

    first = repo.ensure_starter_watchlist_for_user(user_id)
    second = repo.ensure_starter_watchlist_for_user(user_id)

    rows = _watchlists_for_user(user_id)
    assert first is not None
    assert second is None
    assert len(rows) == 1
    assert rows[0].name == STARTER_MARKET_WATCHLIST_NAME


def test_starter_watchlist_is_user_scoped() -> None:
    user_a_id = _approve_user(token="user-token", external_auth_user_id="clerk_user")
    user_b_id = _approve_user(token="admin-token", external_auth_user_id="clerk_admin")

    user_a_rows = _watchlists_for_user(user_a_id)
    user_b_rows = _watchlists_for_user(user_b_id)

    assert len(user_a_rows) == 1
    assert len(user_b_rows) == 1
    assert user_a_rows[0].app_user_id == user_a_id
    assert user_b_rows[0].app_user_id == user_b_id
    assert user_a_rows[0].id != user_b_rows[0].id


def test_watchlist_create_and_list() -> None:
    _seed_and_approve_user()
    resp = client.post(
        "/user/watchlists",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "Tech picks", "symbols": ["AAPL", "MSFT", "NVDA"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Tech picks"
    assert body["symbols"] == ["AAPL", "MSFT", "NVDA"]
    wl_id = body["id"]

    list_resp = client.get("/user/watchlists", headers={"Authorization": "Bearer user-token"})
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(item["id"] == wl_id for item in items)


def test_watchlist_description_default_and_duplicate_normalization() -> None:
    _seed_and_approve_user()
    first = client.post(
        "/user/watchlists",
        headers={"Authorization": "Bearer user-token"},
        json={
            "name": "Focused tech",
            "description": "Agent Mode shortlist",
            "symbols": ["aapl", "MSFT", "AAPL", "NVDA"],
            "is_default": True,
        },
    )
    second = client.post(
        "/user/watchlists",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "Energy", "symbols": ["XLE", "CVX"], "is_default": True},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["symbols"] == ["AAPL", "MSFT", "NVDA"]
    assert first.json()["description"] == "Agent Mode shortlist"
    list_resp = client.get("/user/watchlists", headers={"Authorization": "Bearer user-token"})
    assert list_resp.status_code == 200
    defaults = [item for item in list_resp.json() if item["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["name"] == "Energy"


def test_watchlist_update() -> None:
    _seed_and_approve_user()
    create = client.post(
        "/user/watchlists",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "ETFs", "symbols": ["SPY", "QQQ"]},
    )
    assert create.status_code == 200
    wl_id = create.json()["id"]

    update = client.put(
        f"/user/watchlists/{wl_id}",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "Sector ETFs", "symbols": ["XLK", "XLF", "XLE"]},
    )
    assert update.status_code == 200
    body = update.json()
    assert body["name"] == "Sector ETFs"
    assert body["symbols"] == ["XLK", "XLF", "XLE"]


def test_watchlist_update_symbols_only() -> None:
    _seed_and_approve_user()
    create = client.post(
        "/user/watchlists",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "Biotech", "symbols": ["MRNA"]},
    )
    assert create.status_code == 200
    wl_id = create.json()["id"]

    update = client.put(
        f"/user/watchlists/{wl_id}",
        headers={"Authorization": "Bearer user-token"},
        json={"symbols": ["MRNA", "BNTX", "PFE"]},
    )
    assert update.status_code == 200
    body = update.json()
    assert body["name"] == "Biotech"
    assert body["symbols"] == ["MRNA", "BNTX", "PFE"]


def test_watchlist_delete() -> None:
    _seed_and_approve_user()
    create = client.post(
        "/user/watchlists",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "To delete", "symbols": ["TSLA"]},
    )
    assert create.status_code == 200
    wl_id = create.json()["id"]

    delete = client.delete(
        f"/user/watchlists/{wl_id}",
        headers={"Authorization": "Bearer user-token"},
    )
    assert delete.status_code == 200
    assert delete.json()["deleted"] is True

    list_resp = client.get("/user/watchlists", headers={"Authorization": "Bearer user-token"})
    ids = [item["id"] for item in list_resp.json()]
    assert wl_id not in ids


def test_watchlist_delete_not_found() -> None:
    _seed_and_approve_user()
    resp = client.delete(
        "/user/watchlists/999999",
        headers={"Authorization": "Bearer user-token"},
    )
    assert resp.status_code == 404


def test_watchlist_update_not_found() -> None:
    _seed_and_approve_user()
    resp = client.put(
        "/user/watchlists/999999",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "Ghost"},
    )
    assert resp.status_code == 404


def test_watchlist_create_empty_symbols_rejected() -> None:
    _seed_and_approve_user()
    resp = client.post(
        "/user/watchlists",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "Empty", "symbols": []},
    )
    assert resp.status_code == 400


def test_watchlist_multiple_named_lists_per_user() -> None:
    _seed_and_approve_user()
    client.post(
        "/user/watchlists",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "Morning scan", "symbols": ["AAPL", "GOOGL"]},
    )
    client.post(
        "/user/watchlists",
        headers={"Authorization": "Bearer user-token"},
        json={"name": "Swing setups", "symbols": ["NVDA", "AMD"]},
    )
    list_resp = client.get("/user/watchlists", headers={"Authorization": "Bearer user-token"})
    names = [item["name"] for item in list_resp.json()]
    assert "Morning scan" in names
    assert "Swing setups" in names
