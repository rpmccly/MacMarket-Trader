from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.charts.momentum_heatmap_service import MomentumHeatmapService
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.domain.schemas import MomentumHeatmapScoreCell
from macmarket_trader.storage.db import SessionLocal, init_db


def setup_module() -> None:
    init_db()


def _approve_default_user(client: TestClient) -> None:
    client.get("/user/me", headers={"Authorization": "Bearer user-token"})
    with SessionLocal() as session:
        user = session.execute(select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_user")).scalar_one()
        user.approval_status = "approved"
        session.commit()


def test_momentum_heatmap_formulas_calculate_from_timeframe_scores(monkeypatch) -> None:
    values = {"1W": 80, "1D": 60, "4H": 30, "1H": 45, "30M": 75}

    def fake_score_cell(self, *, provider_symbol: str, timeframe: str):  # noqa: ANN001
        del self, provider_symbol
        return MomentumHeatmapScoreCell(value=values[timeframe], status="ok", data_source="test", fallback_mode=False)

    monkeypatch.setattr(MomentumHeatmapService, "_score_cell", fake_score_cell)

    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum-heatmap",
        headers={"Authorization": "Bearer user-token"},
        json={
            "categories": [
                {
                    "categoryId": "major-stocks",
                    "categoryLabel": "MAJOR STOCKS",
                    "rows": [{"id": "major-stocks:TSLA", "symbol": "TSLA", "displayName": "TSLA", "providerSymbol": "TSLA"}],
                }
            ],
            "timeframes": ["1W", "1D", "4H", "1H", "30M"],
        },
    )

    assert response.status_code == 200
    row = response.json()["categories"][0]["rows"][0]
    assert row["long_term_score"] == 70
    assert row["short_term_score"] == 50
    assert row["strength_percent"] == 63.33


def test_momentum_heatmap_unsupported_symbol_status_does_not_crash() -> None:
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum-heatmap",
        headers={"Authorization": "Bearer user-token"},
        json={
            "categories": [
                {
                    "categoryId": "commodities",
                    "categoryLabel": "COMMODITIES",
                    "rows": [{"id": "commodities:/CL", "symbol": "/CL", "displayName": "/CL", "providerSymbol": "/CL"}],
                }
            ],
            "timeframes": ["1W", "1D", "4H", "1H", "30M"],
        },
    )

    assert response.status_code == 200
    row = response.json()["categories"][0]["rows"][0]
    assert row["long_term_score"] is None
    assert row["short_term_score"] is None
    assert row["strength_percent"] is None
    assert all(cell["status"] == "unsupported" for cell in row["scores"].values())
    assert all(cell["reason"] == "provider_symbol_not_supported_by_heatmap_v1" for cell in row["scores"].values())


def test_momentum_heatmap_squeeze_is_deferred_without_approved_algorithm(monkeypatch) -> None:
    def fake_score_cell(self, *, provider_symbol: str, timeframe: str):  # noqa: ANN001
        del self, provider_symbol, timeframe
        return MomentumHeatmapScoreCell(value=50, status="ok", data_source="test", fallback_mode=False)

    monkeypatch.setattr(MomentumHeatmapService, "_score_cell", fake_score_cell)

    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum-heatmap",
        headers={"Authorization": "Bearer user-token"},
        json={
            "categories": [
                {
                    "categoryId": "indexes",
                    "categoryLabel": "INDEXES",
                    "rows": [{"id": "indexes:SPY", "symbol": "SPY", "displayName": "SPY", "providerSymbol": "SPY"}],
                }
            ],
            "timeframes": ["1W", "1D", "4H", "1H", "30M"],
        },
    )

    assert response.status_code == 200
    squeeze = response.json()["categories"][0]["rows"][0]["squeeze"]
    assert squeeze["value"] is None
    assert squeeze["status"] == "deferred"
    assert squeeze["reason"] == "squeeze_algorithm_not_implemented"
