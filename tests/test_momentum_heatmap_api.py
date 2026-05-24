from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.charts.momentum_heatmap_service import MomentumHeatmapService
from macmarket_trader.charts.momentum_service import MomentumChartService
from macmarket_trader.data.providers.market_data import DeterministicFallbackMarketDataProvider
from macmarket_trader.domain.models import AppUserModel
from macmarket_trader.domain.schemas import MomentumHeatmapRowRequest, MomentumHeatmapScoreCell
from macmarket_trader.domain.timeframes import CHART_BAR_LIMIT_BY_TIMEFRAME, ChartTimeframe
from macmarket_trader.indicators.hilo_elite import compute_hilo_elite
from macmarket_trader.indicators.true_momentum import compute_true_momentum
from macmarket_trader.indicators.true_momentum_score import compute_true_momentum_score
from macmarket_trader.storage.db import SessionLocal, init_db

PARITY_SYMBOLS = ("SPY", "QQQ", "NVDA")
PARITY_TIMEFRAMES: tuple[ChartTimeframe, ...] = ("1W", "1D", "4H", "1H", "30M")


def setup_module() -> None:
    init_db()


def _approve_default_user(client: TestClient) -> None:
    client.get("/user/me", headers={"Authorization": "Bearer user-token"})
    with SessionLocal() as session:
        user = session.execute(select(AppUserModel).where(AppUserModel.external_auth_user_id == "clerk_user")).scalar_one()
        user.approval_status = "approved"
        session.commit()


class DeterministicHistoricalBarService:
    def __init__(self) -> None:
        self.provider = DeterministicFallbackMarketDataProvider()
        self.bars_by_request: dict[tuple[str, str, int], list] = {}

    def historical_bars(self, symbol: str, timeframe: str, limit: int):  # noqa: ANN001
        bars = self.provider.fetch_historical_bars(symbol=symbol, timeframe=timeframe, limit=limit)
        self.bars_by_request[(symbol, timeframe, limit)] = bars
        return bars, "fallback", True


class NoProviderCallsExpected:
    def historical_bars(self, symbol: str, timeframe: str, limit: int):  # noqa: ANN001
        raise AssertionError(f"provider call should have failed fast for {symbol} {timeframe} {limit}")


def test_momentum_heatmap_scores_match_momentum_intelligence_path_for_all_timeframes() -> None:
    market_data = DeterministicHistoricalBarService()
    heatmap_service = MomentumHeatmapService(market_data)
    momentum_service = MomentumChartService()

    for symbol in PARITY_SYMBOLS:
        for timeframe in PARITY_TIMEFRAMES:
            cell = heatmap_service._score_cell(provider_symbol=symbol, timeframe=timeframe)
            assert cell.status == "ok", (symbol, timeframe, cell.reason)

            limit = CHART_BAR_LIMIT_BY_TIMEFRAME[timeframe]
            bars = market_data.bars_by_request[(symbol, timeframe, limit)]
            payload = momentum_service.build_payload(
                symbol=symbol,
                timeframe=timeframe,
                bars=bars,
                include_markers=False,
                data_source="fallback",
                fallback_mode=True,
            )

            assert payload.latest_snapshot is not None
            assert cell.value == payload.latest_snapshot.total_score


def test_true_momentum_score_internal_preprocessing_matches_momentum_service_precomputed_path() -> None:
    provider = DeterministicFallbackMarketDataProvider()
    momentum_service = MomentumChartService()

    for symbol in PARITY_SYMBOLS:
        for timeframe in PARITY_TIMEFRAMES:
            bars = provider.fetch_historical_bars(
                symbol=symbol,
                timeframe=timeframe,
                limit=CHART_BAR_LIMIT_BY_TIMEFRAME[timeframe],
            )
            canonical_bars = momentum_service._dedupe_canonical_bars(
                momentum_service._canonical_bars(bars),
                timeframe,
            )
            true_momentum = compute_true_momentum(canonical_bars, timeframe=timeframe)
            hilo = compute_hilo_elite(canonical_bars, timeframe=timeframe)

            precomputed = compute_true_momentum_score(
                canonical_bars,
                timeframe=timeframe,
                true_momentum_series=true_momentum,
                hilo_series=hilo,
            )
            internal = compute_true_momentum_score(canonical_bars, timeframe=timeframe)

            assert precomputed.points
            assert internal.points
            assert internal.points[-1].total_score == precomputed.points[-1].total_score
            assert internal.points[-1].component_breakdown == precomputed.points[-1].component_breakdown


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
    assert all(cell["reason"] == "unsupported_symbol_format" for cell in row["scores"].values())


def test_momentum_heatmap_unsupported_symbols_fail_fast_before_provider_calls() -> None:
    service = MomentumHeatmapService(NoProviderCallsExpected())
    for symbol, expected_reason in (("/CL", "unsupported_symbol_format"), ("MAG7", "composite_symbol_deferred")):
        row = service._build_row(
            MomentumHeatmapRowRequest(
                id=f"indexes:{symbol}",
                symbol=symbol,
                displayName=symbol,
                providerSymbol=symbol,
            ),
            ["1W", "1D", "4H", "1H", "30M"],
        )
        assert all(cell.status == "unsupported" for cell in row.scores.values())
        assert all(cell.reason == expected_reason for cell in row.scores.values())


def test_momentum_heatmap_request_row_limit_returns_partial_results(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_score_cell(self, *, provider_symbol: str, timeframe: str):  # noqa: ANN001
        del self
        calls.append((provider_symbol, timeframe))
        return MomentumHeatmapScoreCell(value=50, status="ok", data_source="test", fallback_mode=False)

    monkeypatch.setattr(MomentumHeatmapService, "_score_cell", fake_score_cell)

    rows = [
        {
            "id": f"major-stocks:TEST{i}",
            "symbol": f"TEST{i}",
            "displayName": f"TEST{i}",
            "providerSymbol": f"TEST{i}",
        }
        for i in range(13)
    ]
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/charts/momentum-heatmap",
        headers={"Authorization": "Bearer user-token"},
        json={
            "categories": [{"categoryId": "major-stocks", "categoryLabel": "MAJOR STOCKS", "rows": rows}],
            "timeframes": ["1D"],
        },
    )

    assert response.status_code == 200
    response_rows = response.json()["categories"][0]["rows"]
    assert response_rows[0]["scores"]["1D"]["status"] == "ok"
    assert response_rows[-1]["scores"]["1D"]["status"] == "unavailable"
    assert response_rows[-1]["scores"]["1D"]["reason"] == "heatmap_request_row_limit_exceeded"
    assert len(calls) == 12


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


def test_momentum_heatmap_profile_default_seed_and_color_update() -> None:
    client = TestClient(app)
    _approve_default_user(client)

    profile_response = client.get("/user/momentum-heatmap/profile", headers={"Authorization": "Bearer user-token"})
    assert profile_response.status_code == 200
    profile = profile_response.json()["profile"]
    assert profile["name"] == "Default Momentum Heatmap"
    assert profile["categories"][0]["categoryLabel"] == "INDEXES"
    assert profile["colorRanges"][0]["min"] == 75

    updated_ranges = profile["colorRanges"]
    updated_ranges[0] = {**updated_ranges[0], "min": 70}
    update_response = client.put(
        "/user/momentum-heatmap/profile",
        headers={"Authorization": "Bearer user-token"},
        json={"profileId": profile["id"], "colorRanges": updated_ranges},
    )

    assert update_response.status_code == 200
    assert update_response.json()["profile"]["colorRanges"][0]["min"] == 70


def test_momentum_heatmap_server_duplicate_prevention_and_remove() -> None:
    client = TestClient(app)
    _approve_default_user(client)

    same_category = client.post(
        "/user/momentum-heatmap/rows",
        headers={"Authorization": "Bearer user-token"},
        json={"categoryId": "indexes", "symbol": " spy ", "displayName": "SPY duplicate", "providerSymbol": " spy "},
    )
    assert same_category.status_code == 409
    assert "SPY is already in INDEXES" in same_category.json()["detail"]["message"]

    cross_category = client.post(
        "/user/momentum-heatmap/rows",
        headers={"Authorization": "Bearer user-token"},
        json={"categoryId": "sectors", "symbol": " spy ", "displayName": "SPY sector copy", "providerSymbol": " spy "},
    )
    assert cross_category.status_code == 200
    assert "already exists in INDEXES" in cross_category.json()["warning"]
    added_row_id = cross_category.json()["row"]["id"]

    remove = client.delete(
        f"/user/momentum-heatmap/rows/{added_row_id}",
        headers={"Authorization": "Bearer user-token"},
    )
    assert remove.status_code == 200
    sectors = next(category for category in remove.json()["profile"]["categories"] if category["categoryId"] == "sectors")
    assert all(row["id"] != added_row_id for row in sectors["rows"])


def test_momentum_heatmap_refresh_stores_snapshot_deltas_summaries_report_and_csv(monkeypatch) -> None:
    client = TestClient(app)
    _approve_default_user(client)
    values = {"value": 10}

    def fake_score_cell(self, *, provider_symbol: str, timeframe: str):  # noqa: ANN001
        del self, provider_symbol, timeframe
        return MomentumHeatmapScoreCell(value=values["value"], status="ok", data_source="test", fallback_mode=False)

    monkeypatch.setattr(MomentumHeatmapService, "_score_cell", fake_score_cell)
    request_payload = {
        "categories": [
            {
                "categoryId": "indexes",
                "categoryLabel": "INDEXES",
                "rows": [{"id": "indexes:SPY", "symbol": "SPY", "displayName": "SPY", "providerSymbol": "SPY"}],
            }
        ],
        "timeframes": ["1W", "1D", "4H", "1H", "30M"],
    }

    first = client.post("/user/momentum-heatmap/refresh", headers={"Authorization": "Bearer user-token"}, json=request_payload)
    assert first.status_code == 200
    assert first.json()["snapshot"]["status"] == "fresh"
    assert first.json()["categorySummaries"][0]["average_strength_percent"] == 10

    values["value"] = 25
    second = client.post("/user/momentum-heatmap/refresh", headers={"Authorization": "Bearer user-token"}, json=request_payload)
    assert second.status_code == 200
    assert second.json()["deltas"]["indexes:SPY"]["strength_percent"] == 15
    assert "Trend leader" in second.json()["heatmap"]["categories"][0]["rows"][0]["row_tags"] or "Mixed/chop" in second.json()["heatmap"]["categories"][0]["rows"][0]["row_tags"]

    latest = client.get("/user/momentum-heatmap/snapshots/latest", headers={"Authorization": "Bearer user-token"})
    assert latest.status_code == 200
    assert "Loaded last snapshot" in latest.json()["message"]
    assert latest.json()["previousSnapshot"] is not None
    assert latest.json()["deltas"]["indexes:SPY"]["strength_percent"] == 15

    preview = client.post("/user/momentum-heatmap/report/preview", headers={"Authorization": "Bearer user-token"}, json={})
    assert preview.status_code == 200
    assert "unsupported_summary" in preview.json()["report"]
    assert "Squeeze remains deferred" in preview.json()["html"]
    assert "MacMarket Research Dashboard" in preview.json()["html"]
    assert "Category Regime Summary" in preview.json()["html"]
    assert "Top 10 strongest rows" in preview.json()["html"]
    assert "Bottom 10 weakest rows" in preview.json()["html"]
    assert "Full Heatmap Table" in preview.json()["html"]
    assert "Research dashboard only. Not trade execution or investment advice." in preview.json()["html"]
    assert any(color in preview.json()["html"] for color in ("background:#56f08a", "background:#1f9f62", "background:#7d5cff"))

    csv_response = client.post("/user/momentum-heatmap/report/csv", headers={"Authorization": "Bearer user-token"}, json={})
    assert csv_response.status_code == 200
    assert "delta_strength_percent" in csv_response.json()["csv"]


def test_momentum_heatmap_schedule_preferences_persist_and_email_requires_recipient() -> None:
    client = TestClient(app)
    _approve_default_user(client)

    schedule = client.put(
        "/user/momentum-heatmap/schedule",
        headers={"Authorization": "Bearer user-token"},
        json={
            "enabled": True,
            "timezone": "America/Indiana/Indianapolis",
            "runTime": "10:15",
            "daysOfWeek": ["mon", "wed", "fri"],
            "reportMode": "latest_snapshot",
            "recipients": [" user@example.com "],
            "includeCsvAttachment": False,
            "includeFullTable": True,
        },
    )

    assert schedule.status_code == 200
    assert schedule.json()["schedulePreferences"]["runTime"] == "10:15"
    assert schedule.json()["schedulePreferences"]["recipients"] == ["user@example.com"]
    assert schedule.json()["schedulerActive"] is False
    assert "runner hook" in schedule.json()["message"]

    bad_schedule = client.put(
        "/user/momentum-heatmap/schedule",
        headers={"Authorization": "Bearer user-token"},
        json={"recipients": ["other@example.com"]},
    )
    assert bad_schedule.status_code == 403
    assert bad_schedule.json()["detail"] == "momentum_heatmap_recipient_not_authorized"

    email = client.post("/user/momentum-heatmap/report/email", headers={"Authorization": "Bearer user-token"}, json={})
    assert email.status_code == 400

    bad_email = client.post(
        "/user/momentum-heatmap/report/email",
        headers={"Authorization": "Bearer user-token"},
        json={"recipients": ["other@example.com"]},
    )
    assert bad_email.status_code == 403
    assert bad_email.json()["detail"] == "momentum_heatmap_recipient_not_authorized"
