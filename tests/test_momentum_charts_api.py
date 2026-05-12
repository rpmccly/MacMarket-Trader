from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.charts.momentum_service import MomentumChartService
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.domain.schemas import Bar
from macmarket_trader.storage.db import SessionLocal, init_db


def _daily_bars(n: int = 60) -> list[dict[str, object]]:
    base = date(2026, 1, 1)
    return [
        {
            "date": (base + timedelta(days=i)).isoformat(),
            "open": 100 + i * 0.5,
            "high": 101 + i * 0.5,
            "low": 99 + i * 0.5,
            "close": 100.5 + i * 0.5,
            "volume": 1_000_000 + i * 10_000,
        }
        for i in range(n)
    ]


def setup_module() -> None:
    init_db()


def _approve_default_user(client: TestClient) -> None:
    client.get("/user/me", headers={"Authorization": "Bearer user-token"})
    with SessionLocal() as session:
        user = session.execute(select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_user")).scalar_one()
        user.approval_status = "approved"
        session.commit()


def test_momentum_chart_payload_shape_and_layer_alignment() -> None:
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={"symbol": "AAPL", "timeframe": "1D", "bars": _daily_bars(80)},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["candles"]
    candle_times = [c["time"] for c in payload["candles"]]
    for layer_name in (
        "true_momentum_line",
        "true_momentum_ema_line",
        "hilo_slowd_line",
        "hilo_slowd_x_line",
        "hilo_thrust_strip",
        "score_strip",
    ):
        layer = payload[layer_name]
        assert len(layer) == len(candle_times)
        assert [point["time"] for point in layer] == candle_times

    assert payload["latest_snapshot"] is not None
    assert "component_breakdown" in payload["latest_snapshot"]
    assert payload["data_source"]
    assert "fallback_mode" in payload
    assert payload["higher_timeframe_source"] in {
        "provided_higher_timeframe_bars",
        "derived_from_chart_bars",
        "insufficient_data",
    }
    assert payload["parity_status"] == "pending_thinkorswim_fixture_validation"


def test_momentum_chart_requires_auth() -> None:
    client = TestClient(app)
    response = client.post("/charts/momentum", json={"symbol": "AAPL", "bars": _daily_bars(40)})
    assert response.status_code == 401


def test_momentum_intraday_1h_uses_unique_unix_second_times() -> None:
    service = MomentumChartService()
    bars = [
        Bar(
            date=date(2026, 4, 1),
            timestamp=datetime(2026, 4, 1, 14, 30, tzinfo=UTC) + timedelta(hours=i),
            open=100 + i * 0.1,
            high=101 + i * 0.1,
            low=99 + i * 0.1,
            close=100.5 + i * 0.1,
            volume=1000,
        )
        for i in range(60)
    ]
    payload = service.build_payload("AAPL", "1H", bars)
    times = [c.time for c in payload.candles]
    assert len(times) == len(set(times))
    assert all(isinstance(t, int) for t in times)
    assert [p.time for p in payload.true_momentum_line] == times


def test_momentum_daily_payload_keeps_date_time_values() -> None:
    service = MomentumChartService()
    bars = [
        Bar(
            date=date(2026, 4, 1) + timedelta(days=i),
            open=100 + i,
            high=101 + i,
            low=99 + i,
            close=100.5 + i,
            volume=1000,
        )
        for i in range(40)
    ]
    payload = service.build_payload("GOOG", "1D", bars)
    times = [c.time for c in payload.candles]
    assert all(isinstance(t, str) for t in times)
    assert times == sorted(times)


def test_momentum_empty_bars_yield_neutral_payload() -> None:
    service = MomentumChartService()
    payload = service.build_payload("AAPL", "1D", [])
    assert payload.candles == []
    assert payload.latest_snapshot is None
    assert payload.higher_timeframe_source == "insufficient_data"


def test_momentum_chart_marker_indices_align_to_candles_and_use_context_only_text() -> None:
    service = MomentumChartService()
    closes = [100.0 + i * 0.6 for i in range(120)] + [100.0 + 120 * 0.6 - i * 0.8 for i in range(60)]
    bars = [
        Bar(
            date=date(2025, 1, 1) + timedelta(days=i),
            open=c,
            high=c + 1.0,
            low=c - 1.0,
            close=c,
            volume=1000,
        )
        for i, c in enumerate(closes)
    ]
    payload = service.build_payload("AAPL", "1D", bars)
    candle_indices = {c.index for c in payload.candles}
    forbidden_substrings = ("buy", "sell", "short", "enter")
    for marker in payload.markers:
        assert marker.index in candle_indices
        # Phase A3 copy hardening: marker text is context-only (no action verbs).
        lowered = marker.text.lower()
        for bad in forbidden_substrings:
            assert bad not in lowered, f"marker text {marker.text!r} contains action verb {bad!r}"
        assert marker.direction in {"bullish", "bearish", "warning"}


def test_momentum_chart_defaults_history_range_to_1Y() -> None:
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={"symbol": "AAPL", "timeframe": "1D", "bars": _daily_bars()},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["history_range"] == "1Y"
    assert payload["lookback_days"] == 366
    assert payload["bars_returned"] == len(_daily_bars())


def test_momentum_chart_accepts_supported_history_ranges() -> None:
    client = TestClient(app)
    _approve_default_user(client)
    expected = {"1M": 31, "3M": 93, "6M": 186, "1Y": 366, "2Y": 732, "5Y": 1830}
    for range_id, lookback_days in expected.items():
        response = client.post(
            "/charts/momentum",
            headers={"Authorization": "Bearer user-token"},
            json={
                "symbol": "AAPL",
                "timeframe": "1D",
                "bars": _daily_bars(),
                "history_range": range_id,
            },
        )
        assert response.status_code == 200, range_id
        payload = response.json()
        assert payload["history_range"] == range_id
        assert payload["lookback_days"] == lookback_days


def test_momentum_chart_falls_back_to_1Y_on_invalid_history_range() -> None:
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbol": "AAPL",
            "timeframe": "1D",
            "bars": _daily_bars(),
            "history_range": "garbage",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["history_range"] == "1Y"
    assert payload["lookback_days"] == 366


def test_momentum_chart_metadata_includes_bars_returned_and_lookback_days() -> None:
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbol": "AAPL",
            "timeframe": "1D",
            "bars": _daily_bars(),
            "history_range": "5Y",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["history_range"] == "5Y"
    assert payload["lookback_days"] == 1830
    assert payload["bars_returned"] >= len(payload["candles"])
    assert isinstance(payload["bars_returned"], int)


def test_chart_history_range_helpers_pure_module() -> None:
    """Pure helper tests that mirror the frontend lib + protect the
    backend allowlist from drift."""
    from macmarket_trader.domain.schemas import (
        CHART_HISTORY_RANGE_LOOKBACK_DAYS,
        DEFAULT_CHART_HISTORY_RANGE,
        chart_history_range_bar_limit,
        chart_history_range_to_lookback_days,
    )

    assert DEFAULT_CHART_HISTORY_RANGE == "1Y"
    assert CHART_HISTORY_RANGE_LOOKBACK_DAYS["1M"] == 31
    assert CHART_HISTORY_RANGE_LOOKBACK_DAYS["1Y"] == 366
    assert CHART_HISTORY_RANGE_LOOKBACK_DAYS["5Y"] == 1830
    # Unknown values fall back to 1Y.
    assert chart_history_range_to_lookback_days("garbage") == 366
    assert chart_history_range_to_lookback_days(None) == 366
    # Bar-limit scales with the range for daily bars.
    assert chart_history_range_bar_limit("1D", "1M") == max(31, 60)
    assert chart_history_range_bar_limit("1D", "5Y") == 1830
    assert chart_history_range_bar_limit("1D", "5Y") > chart_history_range_bar_limit(
        "1D", "1Y"
    )
    # Intraday limits are bounded.
    assert chart_history_range_bar_limit("1H", "5Y") <= 4000
    assert chart_history_range_bar_limit("4H", "5Y") <= 2000
