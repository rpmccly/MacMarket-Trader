"""ATR Intel chart route tests (research-only; reads the frozen ATR engine)."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.api.routes import charts as charts_routes
from macmarket_trader.domain.models import AppUserModel
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


def _rising_bars(n: int = 60) -> list[dict[str, object]]:
    base = date(2026, 1, 1)
    return [
        {"date": (base + timedelta(days=i)).isoformat(), "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100.5 + i, "volume": 1_000_000}
        for i in range(n)
    ]


def _rise_then_fall_bars() -> list[dict[str, object]]:
    base = date(2026, 1, 1)
    closes = [100 + i for i in range(30)] + [129 - 3 * i for i in range(16)]  # sharp drop forces a short flip
    bars = []
    prev = closes[0]
    for i, close in enumerate(closes):
        bars.append({
            "date": (base + timedelta(days=i)).isoformat(),
            "open": float(prev), "high": float(max(prev, close) + 1), "low": float(min(prev, close) - 1),
            "close": float(close), "volume": 1_000_000,
        })
        prev = close
    return bars


class _EmptyMarketData:
    last_historical_metadata = None

    def historical_bars(self, symbol: str, timeframe: str, limit: int):  # noqa: ANN001
        return [], "unavailable", False


def test_atr_chart_payload_shape() -> None:
    client = TestClient(app)
    _approve(client)
    response = client.post(
        "/charts/atr",
        headers=AUTH,
        json={"symbol": "AAPL", "timeframe": "1D", "bars": _rising_bars(), "multi_timeframes": ["1W", "1D", "4H", "1H", "30M"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["candles"] and len(payload["candles"]) == len(payload["trailing_stop"])
    assert payload["explanation"]["current_state"] in {"long", "short", "neutral"}
    assert payload["explanation"]["latest_trailing_stop"] is not None
    assert "distance_to_stop_pct" in payload["explanation"]
    assert "bars_since_flip" in payload["explanation"]
    # Config echo of the advanced settings (defaults here).
    assert payload["config"]["atr_period"] == 9 and payload["config"]["trail_type"] == "modified"
    # Multi-timeframe table covers all requested timeframes.
    timeframes = {row["timeframe"] for row in payload["timeframe_states"]}
    assert {"1W", "1D", "4H", "1H", "30M"}.issubset(timeframes)


def test_atr_chart_echoes_advanced_settings() -> None:
    client = TestClient(app)
    _approve(client)
    response = client.post(
        "/charts/atr",
        headers=AUTH,
        json={
            "symbol": "AAPL", "timeframe": "1D", "bars": _rising_bars(),
            "trail_type": "unmodified", "atr_period": 5, "atr_factor": 1.5, "first_trade": "short", "average_type": "simple",
        },
    )
    assert response.status_code == 200, response.text
    config = response.json()["config"]
    assert config == {"trail_type": "unmodified", "atr_period": 5, "atr_factor": 1.5, "first_trade": "short", "average_type": "simple"}


def test_atr_chart_emits_flip_marker_on_reversal() -> None:
    client = TestClient(app)
    _approve(client)
    response = client.post(
        "/charts/atr",
        headers=AUTH,
        json={"symbol": "AAPL", "timeframe": "1D", "bars": _rise_then_fall_bars(), "atr_factor": 1.0, "multi_timeframes": ["1D"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    # A rise-then-sharp-fall series flips long→short, producing a sell marker and a SHORT current state.
    assert any(m["direction"] == "sell" for m in payload["markers"])
    assert payload["explanation"]["current_state"] == "short"


def test_atr_chart_no_data_symbol(monkeypatch) -> None:
    monkeypatch.setattr(charts_routes, "market_data_service", _EmptyMarketData())
    client = TestClient(app)
    _approve(client)
    response = client.post(
        "/charts/atr",
        headers=AUTH,
        json={"symbol": "ZZZZNODATA", "timeframe": "1D", "multi_timeframes": ["1W", "1D", "4H"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["candles"] == []
    assert payload["trailing_stop"] == []
    assert "no_bars" in payload["notes"]
    assert payload["explanation"]["current_state"] == "neutral"
    assert payload["timeframe_states"] and all(row["status"] == "unavailable" for row in payload["timeframe_states"])
    assert all(row["reason"] == "no_bars" for row in payload["timeframe_states"])
