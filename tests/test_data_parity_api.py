from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.domain.models import AppUserModel
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


def test_data_parity_run_is_admin_only() -> None:
    unauthenticated = client.post("/admin/data-parity/run", json={})
    assert unauthenticated.status_code == 401

    client.get("/user/me", headers={"Authorization": "Bearer user-token"})
    pending = client.post("/admin/data-parity/run", headers={"Authorization": "Bearer user-token"}, json={})
    assert pending.status_code == 403


def test_data_parity_run_caps_symbols_and_lookback() -> None:
    _approve_admin()
    too_many_symbols = client.post(
        "/admin/data-parity/run",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "symbols": [f"SYM{i}" for i in range(11)],
            "timeframes": ["1D"],
            "lookbackBars": 250,
        },
    )
    assert too_many_symbols.status_code == 400
    assert "at most 10" in too_many_symbols.json()["detail"]

    too_many_bars = client.post(
        "/admin/data-parity/run",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "symbols": ["SPY"],
            "timeframes": ["1D"],
            "lookbackBars": 501,
        },
    )
    assert too_many_bars.status_code == 400
    assert "between 5 and 500" in too_many_bars.json()["detail"]


def test_data_parity_run_returns_expected_response_shape(monkeypatch) -> None:
    admin_id = _approve_admin()
    captured: dict[str, object] = {}

    class FakeProviderParityService:
        def __init__(self, **kwargs) -> None:
            captured["kwargs"] = kwargs

        def run(self, request: dict[str, object], *, app_user_id: int) -> dict[str, object]:
            captured["request"] = request
            captured["app_user_id"] = app_user_id
            return {
                "runId": "dpar_test",
                "asOf": "2026-05-29T12:00:00+00:00",
                "providers": {
                    "current": {"provider": "polygon", "productionProviderUnchanged": True},
                    "candidate": {"provider": "schwab_market_data", "token_status": "connected"},
                },
                "summary": {"total": 1, "match": 1},
                "results": [
                    {
                        "symbol": "SPY",
                        "timeframe": "1D",
                        "rawBars": {"verdict": "match"},
                        "canonicalBars": {"verdict": "match"},
                        "indicators": {"verdict": "match", "current": {}, "candidate": {}, "mismatches": []},
                        "tosReference": {"provided": False, "verdict": "not_provided", "mismatches": []},
                        "rootCause": "match",
                        "warnings": [],
                        "errors": [],
                    }
                ],
                "warnings": [],
                "errors": [],
                "readOnly": True,
                "brokerRoutingEnabled": False,
                "productionProviderUnchanged": True,
            }

    monkeypatch.setattr("macmarket_trader.api.routes.data_parity.ProviderParityService", FakeProviderParityService)

    response = client.post(
        "/admin/data-parity/run",
        headers={"Authorization": "Bearer admin-token"},
        json={
            "symbols": ["spy", "SPY", "qqq"],
            "timeframes": ["1D", "30M"],
            "lookbackBars": 250,
            "saveSnapshot": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["runId"] == "dpar_test"
    assert payload["readOnly"] is True
    assert payload["brokerRoutingEnabled"] is False
    assert payload["productionProviderUnchanged"] is True
    assert payload["providers"]["candidate"]["provider"] == "schwab_market_data"
    assert captured["app_user_id"] == admin_id
    assert captured["request"]["symbols"] == ["SPY", "QQQ"]
    assert captured["request"]["timeframes"] == ["1D", "30M"]
