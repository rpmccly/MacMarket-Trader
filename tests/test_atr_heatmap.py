"""ATR Direction Heatmap route + service tests (research-only)."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.api.routes import charts as charts_routes
from macmarket_trader.charts.atr_heatmap_service import AtrHeatmapService
from macmarket_trader.data.providers.market_data import DeterministicFallbackMarketDataProvider
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.domain.schemas import AtrHeatmapRequest
from macmarket_trader.storage.db import SessionLocal, init_db

AUTH = {"Authorization": "Bearer user-token"}


def setup_module() -> None:
    init_db()


def _approve(client: TestClient) -> None:
    client.get("/user/me", headers=AUTH)
    with SessionLocal() as session:
        user = session.execute(select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_user")).scalar_one()
        user.approval_status = "approved"
        session.commit()


class _PartialMarketData:
    """Returns bars for known symbols, nothing for ZZZZNODATA (unsupported)."""

    last_historical_metadata = None

    def __init__(self) -> None:
        self.provider = DeterministicFallbackMarketDataProvider()

    def historical_bars(self, symbol: str, timeframe: str, limit: int):  # noqa: ANN001
        if symbol == "ZZZZNODATA":
            return [], "unavailable", False
        return self.provider.fetch_historical_bars(symbol=symbol, timeframe=timeframe, limit=limit), "polygon", False


def test_atr_heatmap_service_alignment_is_deterministic() -> None:
    service = AtrHeatmapService(_PartialMarketData())
    response = service.build_heatmap(AtrHeatmapRequest(symbols=["SPY", "ZZZZNODATA"], timeframes=["1W", "1D", "4H", "1H", "30M"]))
    by_symbol = {row.symbol: row for row in response.rows}
    spy = by_symbol["SPY"]
    # +1 per LONG timeframe, -1 per SHORT; score == long_count - short_count.
    assert spy.alignment_score == spy.long_count - spy.short_count
    assert spy.alignment_label in {"LONG", "SHORT", "MIXED"}
    assert spy.status == "ok"
    # Unsupported symbol degrades to unavailable, not an error.
    missing = by_symbol["ZZZZNODATA"]
    assert missing.status == "unavailable"
    assert missing.alignment_label == "—"
    assert all(cell.status == "unavailable" for cell in missing.states.values())


def test_atr_heatmap_route_refresh_shape() -> None:
    client = TestClient(app)
    _approve(client)
    response = client.post("/charts/atr-heatmap", headers=AUTH, json={"symbols": ["SPY", "QQQ"], "timeframes": ["1W", "1D", "4H", "1H", "30M"]})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert {row["symbol"] for row in payload["rows"]} == {"SPY", "QQQ"}
    for row in payload["rows"]:
        assert set(row["states"].keys()) == {"1W", "1D", "4H", "1H", "30M"}
        assert "alignment_score" in row and "alignment_label" in row
        assert "latest_trailing_stop" in row and "distance_to_stop_pct" in row
        assert "bars_since_flip" in row and "last_flip_direction" in row and "last_flip_time" in row
    assert payload["summary"]["total"] == 2
    # Config echo uses ATR defaults when not overridden.
    assert payload["config"] == {"trail_type": "modified", "atr_period": 9, "atr_factor": 2.9, "first_trade": "long", "average_type": "wilders"}


def test_atr_heatmap_route_uses_default_config_and_overrides() -> None:
    client = TestClient(app)
    _approve(client)
    response = client.post(
        "/charts/atr-heatmap",
        headers=AUTH,
        json={"symbols": ["SPY"], "trail_type": "unmodified", "atr_period": 5, "atr_factor": 1.5, "first_trade": "short", "average_type": "simple"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["config"] == {"trail_type": "unmodified", "atr_period": 5, "atr_factor": 1.5, "first_trade": "short", "average_type": "simple"}


def test_atr_heatmap_unsupported_symbol(monkeypatch) -> None:
    monkeypatch.setattr(charts_routes, "market_data_service", _PartialMarketData())
    client = TestClient(app)
    _approve(client)
    response = client.post("/charts/atr-heatmap", headers=AUTH, json={"symbols": ["SPY", "ZZZZNODATA"]})
    assert response.status_code == 200, response.text
    payload = response.json()
    missing = next(row for row in payload["rows"] if row["symbol"] == "ZZZZNODATA")
    assert missing["status"] == "unavailable"
    assert payload["summary"]["unavailable_count"] >= 1


def test_atr_heatmap_csv_export() -> None:
    client = TestClient(app)
    _approve(client)
    response = client.post("/charts/atr-heatmap/report/csv", headers=AUTH, json={"symbols": ["SPY", "QQQ"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["filename"] == "atr-direction-heatmap-report.csv"
    lines = body["csv"].splitlines()
    assert lines[0].startswith("symbol,1w,1d,4h,1h,30m,alignment_score,alignment_label")
    assert len(lines) == 3  # header + 2 symbols


def test_atr_heatmap_report_preview_html() -> None:
    client = TestClient(app)
    _approve(client)
    response = client.post("/charts/atr-heatmap/report/preview", headers=AUTH, json={"symbols": ["SPY"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "ATR Direction Heatmap" in body["html"]
    assert body["emailStatus"] == "preview_only_no_email_sent"
    assert "summary" in body["report"] and "rows" in body["report"]
