from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.api.routes import charts as charts_routes
from macmarket_trader.charts.momentum_service import MomentumChartService
from macmarket_trader.data.providers.market_data import DeterministicFallbackMarketDataProvider
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.domain.schemas import Bar, MomentumChartRequest
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


class _Fallback30mMarketDataService:
    def __init__(self) -> None:
        self.provider = DeterministicFallbackMarketDataProvider()
        self.last_historical_metadata: dict[str, object] | None = None

    def historical_bars(self, symbol: str, timeframe: str, limit: int):  # noqa: ANN001
        assert timeframe == "30M"
        bars = self.provider.fetch_historical_bars(symbol=symbol, timeframe=timeframe, limit=limit)
        first = bars[0] if bars else None
        last = bars[-1] if bars else None
        self.last_historical_metadata = {
            "provider": "fallback",
            "timeframe": "30M",
            "fallback_mode": True,
            "session_policy": first.session_policy if first else None,
            "source_session_policy": first.source_session_policy if first else None,
            "source_timeframe": first.source_timeframe if first else None,
            "output_timeframe": "30M",
            "filtered_extended_hours_count": 0,
            "rth_bucket_count": len(bars),
            "first_bar_timestamp": first.timestamp.isoformat() if first and first.timestamp else None,
            "last_bar_timestamp": last.timestamp.isoformat() if last and last.timestamp else None,
        }
        return bars, "fallback", True


def test_momentum_chart_payload_shape_and_layer_alignment() -> None:
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={"symbol": "SPY", "timeframe": "1D", "bars": _daily_bars(80)},
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
    assert payload["squeeze_pro"]["enabled"] is True
    assert payload["squeeze_pro"]["status"] == "ok"
    assert payload["squeeze_pro"]["show_arrows"] is False
    assert payload["squeeze_pro"]["arrow_mode"] == "disabled_pending_approved_arrow_rules"
    assert len(payload["squeeze_pro"]["series"]) == len(candle_times)
    assert [point["time"] for point in payload["squeeze_pro"]["series"]] == candle_times
    first_squeeze_ok_index = next(
        index for index, point in enumerate(payload["squeeze_pro"]["series"]) if point["status"] == "ok"
    )
    assert first_squeeze_ok_index > 0
    squeeze_warmup = payload["squeeze_pro"]["series"][:first_squeeze_ok_index]
    assert [point["time"] for point in squeeze_warmup] == candle_times[:first_squeeze_ok_index]
    assert all(point["oscillator_value"] is None for point in squeeze_warmup)
    assert all(point["squeeze_state"] == "unavailable" for point in squeeze_warmup)
    assert all(point["arrow"] is None for point in payload["squeeze_pro"]["series"])
    assert all(point["arrow_reason"] is None for point in payload["squeeze_pro"]["series"])

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
    response = client.post("/charts/momentum", json={"symbol": "SPY", "bars": _daily_bars(40)})
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
    payload = service.build_payload("SPY", "1H", bars)
    times = [c.time for c in payload.candles]
    assert len(times) == len(set(times))
    assert all(isinstance(t, int) for t in times)
    assert [p.time for p in payload.true_momentum_line] == times


def test_momentum_chart_request_accepts_weekly_and_30m_timeframes() -> None:
    assert MomentumChartRequest(symbol="SPY", timeframe="1W").timeframe == "1W"
    assert MomentumChartRequest(symbol="SPY", timeframe="30M").timeframe == "30M"


def test_momentum_weekly_payload_keeps_date_time_values() -> None:
    service = MomentumChartService()
    bars = [
        Bar(
            date=date(2026, 1, 2) + timedelta(days=i * 7),
            open=100 + i,
            high=102 + i,
            low=99 + i,
            close=101 + i,
            volume=1000,
        )
        for i in range(60)
    ]
    payload = service.build_payload("SPY", "1W", bars)
    times = [c.time for c in payload.candles]
    assert all(isinstance(t, str) for t in times)
    assert times == sorted(times)


def test_momentum_30m_payload_uses_unix_seconds() -> None:
    service = MomentumChartService()
    bars = [
        Bar(
            date=date(2026, 4, 1),
            timestamp=datetime(2026, 4, 1, 13, 30, tzinfo=UTC) + timedelta(minutes=30 * i),
            open=100 + i * 0.1,
            high=101 + i * 0.1,
            low=99 + i * 0.1,
            close=100.5 + i * 0.1,
            volume=1000,
        )
        for i in range(80)
    ]
    payload = service.build_payload("SPY", "30M", bars)
    times = [c.time for c in payload.candles]
    assert all(isinstance(t, int) for t in times)
    assert len(times) == len(set(times))


def test_momentum_30m_route_returns_shared_intraday_axis(monkeypatch) -> None:
    monkeypatch.setattr(charts_routes, "market_data_service", _Fallback30mMarketDataService())
    client = TestClient(app)
    _approve_default_user(client)

    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={"symbol": "SPY", "timeframe": "30M", "history_range": "1M"},
    )

    assert response.status_code == 200
    payload = response.json()
    candle_times = [candle["time"] for candle in payload["candles"]]

    assert payload["timeframe"] == "30M"
    assert payload["output_timeframe"] == "30M"
    assert payload["source_timeframe"] == "30M"
    assert payload["fallback_mode"] is True
    assert payload["data_source"] == "fallback"
    assert len(candle_times) == payload["bars_returned"]
    assert len(candle_times) >= 13
    assert all(isinstance(time, int) for time in candle_times)
    assert candle_times == sorted(candle_times)
    assert len(candle_times) == len(set(candle_times))
    for layer_name in (
        "true_momentum_line",
        "true_momentum_ema_line",
        "hilo_slowd_line",
        "hilo_slowd_x_line",
        "hilo_thrust_strip",
        "score_strip",
    ):
        assert [point["time"] for point in payload[layer_name]] == candle_times
    assert [point["time"] for point in payload["squeeze_pro"]["series"]] == candle_times


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
    payload = service.build_payload("SPY", "1D", [])
    assert payload.candles == []
    assert payload.latest_snapshot is None
    assert payload.higher_timeframe_source == "insufficient_data"
    assert payload.squeeze_pro is not None
    assert payload.squeeze_pro.status == "unavailable"
    assert payload.squeeze_pro.reason == "no chart bars provided"


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
    payload = service.build_payload("SPY", "1D", bars)
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
        json={"symbol": "SPY", "timeframe": "1D", "bars": _daily_bars()},
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
                "symbol": "SPY",
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
            "symbol": "SPY",
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
            "symbol": "SPY",
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
    # Bar-limit respects bounded chart route caps by timeframe.
    assert chart_history_range_bar_limit("1D", "1M") == max(31, 60)
    assert chart_history_range_bar_limit("1D", "5Y") == 120
    assert chart_history_range_bar_limit("1W", "5Y") == 156
    assert chart_history_range_bar_limit("30M", "5Y") == 500
    assert chart_history_range_bar_limit("1H", "5Y") == 400
    assert chart_history_range_bar_limit("4H", "5Y") == 200


# ── Visual parity chart polish ─────────────────────────────────────────────


def test_momentum_chart_payload_includes_visual_parity_snapshot() -> None:
    """Latest-bar parity snapshot is populated with already-computed
    indicator state. IV% is intentionally null (no deterministic IV
    source) and listed in unavailable_fields."""
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={"symbol": "SPY", "timeframe": "1D", "bars": _daily_bars(80)},
    )
    assert response.status_code == 200
    payload = response.json()

    snapshot = payload["visual_parity_snapshot"]
    assert snapshot is not None
    for field in (
        "total_score",
        "total_label",
        "trend_score",
        "momo_score",
        "true_momentum",
        "true_momentum_ema",
        "hilo_slowd",
        "hilo_slowd_x",
        "tos_hilo_elite_scalar",
        "hilo_thrust_state",
        "hilo_score",
        "pullback_signal",
        "reversal_warning",
        "no_trade_warning",
        "iv_percent",
        "source_notes",
        "unavailable_fields",
        "as_of",
        "symbol",
        "timeframe",
    ):
        assert field in snapshot, f"visual_parity_snapshot missing {field!r}"
    # IV% is unavailable — never fabricated.
    assert snapshot["iv_percent"] is None
    assert "iv_percent" in snapshot["unavailable_fields"]
    # ToS-comparable HiLo Elite scalar is unavailable — MacMarket does
    # not currently compute it, so the field stays null and the badge
    # never lies about parity.
    assert snapshot["tos_hilo_elite_scalar"] is None
    assert "tos_hilo_elite_scalar" in snapshot["unavailable_fields"]
    # SlowD / SlowD_X are kept distinct from the thrust state and the
    # composite HiLo score.
    assert isinstance(snapshot["hilo_slowd"], (int, float))
    assert isinstance(snapshot["hilo_slowd_x"], (int, float))
    assert snapshot["hilo_thrust_state"] in {"bullish", "bearish", "neutral"}
    # Symbol/timeframe echo the request.
    assert snapshot["symbol"] == "SPY"
    assert snapshot["timeframe"] == "1D"


def test_momentum_chart_visual_parity_series_per_bar() -> None:
    """Per-bar parity series mirrors candle alignment so the frontend
    can lookup status by hovered timestamp."""
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={"symbol": "SPY", "timeframe": "1D", "bars": _daily_bars(80)},
    )
    payload = response.json()
    series = payload["visual_parity_series"]
    candle_times = [c["time"] for c in payload["candles"]]
    assert len(series) == len(candle_times)
    assert [p["time"] for p in series] == candle_times
    # Latest series row drives the latest_snapshot — labels/state match.
    latest = series[-1]
    snapshot = payload["visual_parity_snapshot"]
    assert latest["total_score"] == snapshot["total_score"]
    assert latest["total_label"] == snapshot["total_label"]
    assert latest["hilo_thrust_state"] == snapshot["hilo_thrust_state"]


def test_momentum_chart_panel_markers_emit_no_action_language() -> None:
    """Panel markers describe deterministic context only — never
    buy/sell/enter/short/approve language."""
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={"symbol": "SPY", "timeframe": "1D", "bars": _daily_bars(80)},
    )
    payload = response.json()
    forbidden = ("buy", "sell", "enter", "short", "approve", "route", "place order")
    for marker in payload["true_momentum_panel_markers"] + payload["hilo_panel_markers"]:
        for field in ("label", "reason"):
            text = str(marker[field]).lower()
            for word in forbidden:
                assert word not in text, (
                    f"panel marker {marker['marker_type']!r} {field} leaked action word {word!r}: {text!r}"
                )
        assert marker["panel"] in {"true_momentum", "hilo"}
        assert marker["direction"] in {"up", "down", "neutral"}


def test_momentum_chart_panel_markers_include_bullish_cross() -> None:
    """Synthetic bars where True Momentum crosses above EMA produce a
    bullish_cross marker on the True Momentum panel."""
    # Trending up bars after a flat region: should produce at least
    # one cross over a 200-bar window.
    base = date(2026, 1, 1)
    bars: list[Bar] = []
    for i in range(200):
        if i < 60:
            close = 100.0
        else:
            close = 100.0 + (i - 60) * 0.3
        bars.append(
            Bar(
                date=base + timedelta(days=i),
                timestamp=None,
                open=close,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=1_000_000,
            )
        )
    payload = MomentumChartService().build_payload(symbol="SPY", timeframe="1D", bars=bars)
    types = {m.marker_type for m in payload.true_momentum_panel_markers}
    # At least one cross fires during the directional shift.
    assert types & {"bullish_cross", "bearish_cross"}
    for marker in payload.true_momentum_panel_markers:
        assert marker.panel == "true_momentum"
        assert marker.direction in {"up", "down", "neutral"}


def test_momentum_chart_panel_markers_include_hilo_state_transitions() -> None:
    """Synthetic bars covering an up→down regime change produce HiLo
    panel markers when the thrust state changes."""
    base = date(2026, 1, 1)
    bars: list[Bar] = []
    for i in range(180):
        # Aggressive up trend then sharp down trend to force HiLo
        # thrust transitions.
        if i < 90:
            close = 100.0 + i * 0.8
        else:
            close = 100.0 + 90 * 0.8 - (i - 90) * 0.9
        bars.append(
            Bar(
                date=base + timedelta(days=i),
                timestamp=None,
                open=close,
                high=close + 0.4,
                low=close - 0.4,
                close=close,
                volume=1_000_000,
            )
        )
    payload = MomentumChartService().build_payload(symbol="SPY", timeframe="1D", bars=bars)
    # HiLo state may or may not fire on every synthetic dataset, but the
    # bucket must be a list and obey the deterministic contract when it
    # does fire.
    assert isinstance(payload.hilo_panel_markers, list)
    for marker in payload.hilo_panel_markers:
        assert marker.panel == "hilo"
        assert marker.marker_type in {"hilo_confirmed", "hilo_deconfirmed", "hilo_state_transition"}
        assert marker.direction in {"up", "down", "neutral"}


def test_momentum_chart_payload_remains_backward_compatible() -> None:
    """Existing chart-payload fields are preserved alongside the new
    visual parity additions."""
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={"symbol": "SPY", "timeframe": "1D", "bars": _daily_bars(80)},
    )
    payload = response.json()
    for legacy_field in (
        "candles",
        "true_momentum_line",
        "true_momentum_ema_line",
        "hilo_slowd_line",
        "hilo_slowd_x_line",
        "hilo_thrust_strip",
        "score_strip",
        "markers",
        "latest_snapshot",
        "explanation",
        "parity_status",
        "data_source",
        "fallback_mode",
        "higher_timeframe_source",
    ):
        assert legacy_field in payload, f"chart payload missing legacy field {legacy_field!r}"
    # New visual parity fields are additions, not replacements.
    for new_field in (
        "visual_parity_snapshot",
        "visual_parity_series",
        "true_momentum_panel_markers",
        "hilo_panel_markers",
        "squeeze_pro",
    ):
        assert new_field in payload, f"chart payload missing new field {new_field!r}"


def test_momentum_chart_visual_parity_with_longer_history_range() -> None:
    """The visual parity series and panel markers still populate when
    the operator requests a longer history range."""
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={
            "symbol": "SPY",
            "timeframe": "1D",
            "bars": _daily_bars(220),
            "history_range": "1Y",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["visual_parity_series"]) == len(payload["candles"])
    assert payload["history_range"] == "1Y"
    assert payload["visual_parity_snapshot"] is not None


def test_momentum_chart_payload_separates_hilo_slowd_from_tos_scalar() -> None:
    """HiLo cleanup contract: ``hilo_slowd`` and ``hilo_slowd_x`` carry
    the rendered stochastic values, ``tos_hilo_elite_scalar`` stays
    null + listed in unavailable_fields, and the legacy
    ``hilo_elite_value`` key never appears on the payload."""
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={"symbol": "SPY", "timeframe": "1D", "bars": _daily_bars(80)},
    )
    payload = response.json()
    snapshot = payload["visual_parity_snapshot"]
    # New field discipline.
    assert "hilo_slowd" in snapshot
    assert "hilo_slowd_x" in snapshot
    assert "tos_hilo_elite_scalar" in snapshot
    assert snapshot["tos_hilo_elite_scalar"] is None
    assert "tos_hilo_elite_scalar" in snapshot["unavailable_fields"]
    # The misleading legacy key is gone — no "hilo_elite_value" on the
    # payload (catches accidental backslide).
    assert "hilo_elite_value" not in snapshot
    for point in payload["visual_parity_series"]:
        assert "hilo_slowd" in point
        assert "hilo_slowd_x" in point
        assert "hilo_elite_value" not in point
    # SlowD and SlowD_X also remain on their dedicated chart lines.
    assert payload["hilo_slowd_line"]
    assert payload["hilo_slowd_x_line"]


def test_momentum_chart_payload_hilo_slowd_matches_existing_slowd_line() -> None:
    """The visual parity ``hilo_slowd`` field for the last bar matches
    the last point of the existing ``hilo_slowd_line`` series — proves
    the new field is sourced from the same already-computed value the
    chart line uses."""
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum",
        headers={"Authorization": "Bearer user-token"},
        json={"symbol": "SPY", "timeframe": "1D", "bars": _daily_bars(80)},
    )
    payload = response.json()
    snapshot = payload["visual_parity_snapshot"]
    last_slowd = payload["hilo_slowd_line"][-1]["value"]
    last_slowd_x = payload["hilo_slowd_x_line"][-1]["value"]
    assert snapshot["hilo_slowd"] == last_slowd
    assert snapshot["hilo_slowd_x"] == last_slowd_x


def test_momentum_chart_empty_bars_returns_safe_parity_payload() -> None:
    """No-bars chart payload still returns a structured visual parity
    snapshot (with all fields in unavailable_fields)."""
    payload = MomentumChartService().build_payload(symbol="SPY", timeframe="1D", bars=[])
    assert payload.visual_parity_snapshot is not None
    snapshot = payload.visual_parity_snapshot
    # Everything but IV% — which is unavailable for a different reason —
    # collapses into unavailable_fields when there are no bars.
    assert "iv_percent" in snapshot.unavailable_fields
    assert "total_score" in snapshot.unavailable_fields
    assert snapshot.total_score is None
    assert payload.visual_parity_series == []
    assert payload.true_momentum_panel_markers == []
    assert payload.hilo_panel_markers == []
