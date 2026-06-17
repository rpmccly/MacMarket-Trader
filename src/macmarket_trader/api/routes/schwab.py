"""Schwab OAuth and diagnostic status routes."""

from __future__ import annotations

from datetime import timedelta
from secrets import token_urlsafe
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse

from macmarket_trader.api.deps.auth import require_admin
from macmarket_trader.config import settings
from macmarket_trader.data.providers.schwab import (
    SCHWAB_PROVIDER,
    SchwabAuthRequiredError,
    SchwabConfigurationError,
    exchange_code_for_tokens,
    parse_schwab_token_payload,
    redact_schwab_text,
    save_schwab_token_bundle,
    schwab_market_data_status,
    schwab_oauth_configured,
)
from macmarket_trader.domain.time import utc_now
from macmarket_trader.storage.db import SessionLocal
from macmarket_trader.storage.repositories import ProviderOAuthRepository


router = APIRouter(tags=["schwab"])
oauth_repo = ProviderOAuthRepository(SessionLocal)


def _safe_return_path(value: str | None) -> str:
    candidate = str(value or "/admin/data-parity").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/admin/data-parity"
    return candidate[:255]


def _safe_error_code(value: object) -> str:
    text = redact_schwab_text(value).strip().lower().replace(" ", "_")
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch in {"_", "-"})
    return (cleaned or "schwab_error")[:80]


def _app_redirect(return_path: str, **params: str) -> RedirectResponse:
    sep = "&" if "?" in return_path else "?"
    query = urlencode(params)
    return RedirectResponse(f"{settings.app_base_url.rstrip('/')}{return_path}{sep}{query}", status_code=302)


@router.get("/auth/schwab/start")
def start_schwab_oauth(
    admin=Depends(require_admin),
    return_path: str = Query(default="/admin/data-parity"),
) -> RedirectResponse:
    safe_path = _safe_return_path(return_path)
    if not schwab_oauth_configured(settings) or not settings.schwab_token_encryption_key.strip():
        return _app_redirect(safe_path, schwab="error", code="schwab_not_configured")

    state = token_urlsafe(48)
    oauth_repo.create_state(
        provider=SCHWAB_PROVIDER,
        app_user_id=admin.id,
        state=state,
        return_path=safe_path,
        expires_at=utc_now() + timedelta(minutes=10),
    )
    target = f"{settings.schwab_auth_url}?{urlencode({
        'response_type': 'code',
        'client_id': settings.schwab_client_id.strip(),
        'redirect_uri': settings.schwab_redirect_uri.strip(),
        'state': state,
    })}"
    return RedirectResponse(target, status_code=302)


@router.get("/auth/schwab/callback")
def schwab_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        return _app_redirect("/admin/data-parity", schwab="error", code=_safe_error_code(error))
    if not state:
        return _app_redirect("/admin/data-parity", schwab="error", code="missing_state")

    state_status, state_row = oauth_repo.consume_state(provider=SCHWAB_PROVIDER, state=state)
    if state_status != "ok" or state_row is None:
        return _app_redirect("/admin/data-parity", schwab="error", code=f"state_{state_status}")
    return_path = _safe_return_path(state_row.return_path)

    if not code:
        return _app_redirect(return_path, schwab="error", code="missing_code")
    try:
        payload = exchange_code_for_tokens(code, cfg=settings)
        bundle = parse_schwab_token_payload(payload)
        save_schwab_token_bundle(
            repo=oauth_repo,
            bundle=bundle,
            app_user_id=state_row.app_user_id,
            cfg=settings,
        )
    except (SchwabAuthRequiredError, SchwabConfigurationError, ValueError) as exc:
        return _app_redirect(return_path, schwab="error", code=_safe_error_code(exc))
    except Exception as exc:  # noqa: BLE001 - callback must redirect with a safe error code
        return _app_redirect(return_path, schwab="error", code=_safe_error_code(exc))

    return _app_redirect(return_path, schwab="connected")


@router.get("/admin/schwab/status")
def admin_schwab_status(_admin=Depends(require_admin)):
    return schwab_market_data_status(repo=oauth_repo, cfg=settings, include_probe=True, sample_symbol="SPY")
