from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.config import settings
from macmarket_trader.domain.models import AppUserModel, ProviderOAuthStateModel, ProviderOAuthTokenModel
from macmarket_trader.domain.time import utc_now
from macmarket_trader.storage.db import SessionLocal


client = TestClient(app)


def _approve_admin() -> int:
    resp = client.get("/user/me", headers={"Authorization": "Bearer admin-token"})
    assert resp.status_code == 200
    with SessionLocal() as session:
        admin = session.execute(select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_admin")).scalar_one()
        admin.app_role = "admin"
        admin.approval_status = "approved"
        admin.mfa_enabled = True
        session.commit()
        return admin.id


def _configure_schwab(monkeypatch) -> str:
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setattr(settings, "schwab_enabled", True)
    monkeypatch.setattr(settings, "schwab_client_id", "test-client-id")
    monkeypatch.setattr(settings, "schwab_client_secret", "unit-test-client-secret-placeholder")
    monkeypatch.setattr(settings, "schwab_redirect_uri", "https://api.macmarket.io/auth/schwab/callback")
    monkeypatch.setattr(settings, "schwab_auth_url", "https://api.schwabapi.com/v1/oauth/authorize")
    monkeypatch.setattr(settings, "schwab_token_url", "https://api.schwabapi.com/v1/oauth/token")
    monkeypatch.setattr(settings, "schwab_market_data_base_url", "https://api.schwabapi.com/marketdata/v1")
    monkeypatch.setattr(settings, "schwab_token_encryption_key", key)
    monkeypatch.setattr(settings, "app_base_url", "http://localhost:9500")
    return key


def test_start_route_requires_admin(monkeypatch) -> None:
    _configure_schwab(monkeypatch)

    unauthenticated = client.get("/auth/schwab/start", follow_redirects=False)
    assert unauthenticated.status_code == 401

    client.get("/user/me", headers={"Authorization": "Bearer user-token"})
    pending = client.get("/auth/schwab/start", headers={"Authorization": "Bearer user-token"}, follow_redirects=False)
    assert pending.status_code == 403


def test_start_generates_and_persists_state(monkeypatch) -> None:
    _configure_schwab(monkeypatch)
    admin_id = _approve_admin()

    response = client.get(
        "/auth/schwab/start?return_path=/admin/data-parity",
        headers={"Authorization": "Bearer admin-token"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "api.schwabapi.com"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["test-client-id"]
    assert query["redirect_uri"] == ["https://api.macmarket.io/auth/schwab/callback"]
    state = query["state"][0]
    assert len(state) > 40

    with SessionLocal() as session:
        row = session.execute(select(ProviderOAuthStateModel).where(ProviderOAuthStateModel.state == state)).scalar_one()
        assert row.provider == "schwab"
        assert row.app_user_id == admin_id
        assert row.return_path == "/admin/data-parity"
        assert row.used_at is None
        assert row.expires_at is not None


def test_callback_rejects_missing_expired_and_used_state(monkeypatch) -> None:
    _configure_schwab(monkeypatch)
    admin_id = _approve_admin()

    missing = client.get("/auth/schwab/callback?code=abc&state=missing", follow_redirects=False)
    assert missing.status_code == 302
    assert "schwab=error" in missing.headers["location"]
    assert "state_missing" in missing.headers["location"]

    with SessionLocal() as session:
        expired = ProviderOAuthStateModel(
            provider="schwab",
            app_user_id=admin_id,
            state="expired-state",
            return_path="/admin/data-parity",
            expires_at=utc_now() - timedelta(minutes=1),
        )
        used = ProviderOAuthStateModel(
            provider="schwab",
            app_user_id=admin_id,
            state="used-state",
            return_path="/admin/data-parity",
            expires_at=utc_now() + timedelta(minutes=1),
            used_at=utc_now(),
        )
        session.add_all([expired, used])
        session.commit()

    expired_resp = client.get("/auth/schwab/callback?code=abc&state=expired-state", follow_redirects=False)
    used_resp = client.get("/auth/schwab/callback?code=abc&state=used-state", follow_redirects=False)

    assert "state_expired" in expired_resp.headers["location"]
    assert "state_used" in used_resp.headers["location"]


def test_callback_stores_token_bundle_encrypted_and_never_returns_tokens(monkeypatch) -> None:
    key = _configure_schwab(monkeypatch)
    admin_id = _approve_admin()

    with SessionLocal() as session:
        session.add(
            ProviderOAuthStateModel(
                provider="schwab",
                app_user_id=admin_id,
                state="fresh-state",
                return_path="/admin/data-parity",
                expires_at=utc_now() + timedelta(minutes=5),
            )
        )
        session.commit()

    def fake_exchange(code: str, *, cfg=settings):
        assert code == "auth-code"
        assert cfg.schwab_client_secret == "unit-test-client-secret-placeholder"
        return {
            "access_token": "unit-test-access-token-placeholder",
            "refresh_token": "unit-test-refresh-token-placeholder",
            "token_type": "Bearer",
            "scope": "read",
            "expires_in": 1800,
            "refresh_token_expires_in": 86400,
        }

    monkeypatch.setattr("macmarket_trader.api.routes.schwab.exchange_code_for_tokens", fake_exchange)

    response = client.get("/auth/schwab/callback?code=auth-code&state=fresh-state", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:9500/admin/data-parity?schwab=connected"
    assert "unit-test-access-token-placeholder" not in response.headers["location"]
    assert "unit-test-refresh-token-placeholder" not in response.headers["location"]

    with SessionLocal() as session:
        token = session.execute(select(ProviderOAuthTokenModel).where(ProviderOAuthTokenModel.provider == "schwab")).scalar_one()
        state = session.execute(select(ProviderOAuthStateModel).where(ProviderOAuthStateModel.state == "fresh-state")).scalar_one()
        assert state.used_at is not None
        assert token.status == "connected"
        assert token.encrypted_access_token != "unit-test-access-token-placeholder"
        assert token.encrypted_refresh_token != "unit-test-refresh-token-placeholder"
        cipher = Fernet(key.encode("utf-8"))
        assert cipher.decrypt(token.encrypted_access_token.encode("utf-8")).decode("utf-8") == "unit-test-access-token-placeholder"
        assert cipher.decrypt(token.encrypted_refresh_token.encode("utf-8")).decode("utf-8") == "unit-test-refresh-token-placeholder"


def test_callback_error_redirect_uses_safe_error_code(monkeypatch) -> None:
    _configure_schwab(monkeypatch)
    admin_id = _approve_admin()

    with SessionLocal() as session:
        session.add(
            ProviderOAuthStateModel(
                provider="schwab",
                app_user_id=admin_id,
                state="error-state",
                return_path="/admin/data-parity",
                expires_at=utc_now() + timedelta(minutes=5),
            )
        )
        session.commit()

    def fake_exchange(code: str, *, cfg=settings):
        del code
        raise RuntimeError(f"Authorization: Bearer unit-test-raw-access-token-placeholder {cfg.schwab_client_secret}")

    monkeypatch.setattr("macmarket_trader.api.routes.schwab.exchange_code_for_tokens", fake_exchange)

    response = client.get("/auth/schwab/callback?code=auth-code&state=error-state", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert query["schwab"] == ["error"]
    assert query["code"] == ["schwab_provider_error_included_an_authorization_header_value_redacted"]
    assert "unit-test-raw-access-token-placeholder" not in location
    assert "unit-test-client-secret-placeholder" not in location
    assert "Authorization" not in location
