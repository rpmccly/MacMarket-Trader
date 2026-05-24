from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.charts.momentum_heatmap_service import MomentumHeatmapService
from macmarket_trader.charts.momentum_service import MomentumChartService
from macmarket_trader.data.providers.market_data import DeterministicFallbackMarketDataProvider
from macmarket_trader.domain.models import (
    AppUserModel,
    MomentumHeatmapProfileModel,
    MomentumHeatmapSchedulePreferenceModel,
    MomentumHeatmapSnapshotModel,
)
from macmarket_trader.domain.schemas import MomentumHeatmapRowRequest, MomentumHeatmapScoreCell, MomentumHeatmapSqueezeCell
from macmarket_trader.domain.timeframes import CHART_BAR_LIMIT_BY_TIMEFRAME, ChartTimeframe
from macmarket_trader.indicators.hilo_elite import compute_hilo_elite
from macmarket_trader.indicators.true_momentum import compute_true_momentum
from macmarket_trader.indicators.true_momentum_score import compute_true_momentum_score
from macmarket_trader.storage.db import SessionLocal, init_db

PARITY_SYMBOLS = ("SPY", "QQQ", "NVDA")
PARITY_TIMEFRAMES: tuple[ChartTimeframe, ...] = ("1W", "1D", "4H", "1H", "30M")


def setup_module() -> None:
    init_db()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _approve_user(client: TestClient, *, token: str, external_auth_user_id: str) -> int:
    client.get("/user/me", headers=_auth(token))
    with SessionLocal() as session:
        user = session.execute(select(AppUserModel).where(AppUserModel.external_auth_user_id == external_auth_user_id)).scalar_one()
        user.approval_status = "approved"
        if external_auth_user_id == "clerk_admin":
            user.app_role = "admin"
            user.mfa_enabled = True
        session.commit()
        return int(user.id)


def _approve_default_user(client: TestClient) -> None:
    _approve_user(client, token="user-token", external_auth_user_id="clerk_user")


def _reset_momentum_heatmap_profile(client: TestClient, token: str) -> dict:
    profile_response = client.get("/user/momentum-heatmap/profile", headers=_auth(token))
    assert profile_response.status_code == 200
    profile_id = profile_response.json()["profile"]["id"]
    reset_response = client.post(
        "/user/momentum-heatmap/profile/reset",
        headers=_auth(token),
        json={"profileId": profile_id},
    )
    assert reset_response.status_code == 200
    return reset_response.json()["profile"]


def _category(profile: dict, category_id: str) -> dict:
    return next(category for category in profile["categories"] if category["categoryId"] == category_id)


def _row_ids(profile: dict) -> set[str]:
    return {
        row["id"]
        for category in profile["categories"]
        for row in category["rows"]
    }


def _profile_by_name(payload: dict, name: str) -> dict:
    return next(profile for profile in payload["profiles"] if profile["name"] == name)


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


def _ok_squeeze_cell(self, *, provider_symbol: str, timeframes: list[str], deadline=None, forced_reason=None):  # noqa: ANN001
    del self, provider_symbol, timeframes, deadline
    if forced_reason is not None:
        return MomentumHeatmapSqueezeCell(value=None, status="unavailable", reason=forced_reason)
    return MomentumHeatmapSqueezeCell(
        value="No squeeze",
        status="ok",
        state="none",
        reason="test_squeeze_state",
        timeframes={"1D": {"status": "ok", "state": "none", "value": "No squeeze"}},
    )


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
    monkeypatch.setattr(MomentumHeatmapService, "_squeeze_cell", _ok_squeeze_cell)
    monkeypatch.setattr(MomentumHeatmapService, "_squeeze_cell", _ok_squeeze_cell)

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
        assert row.squeeze.status == "unavailable"
        assert row.squeeze.reason == expected_reason


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


def test_momentum_heatmap_squeeze_uses_squeeze_pro_for_valid_symbols() -> None:
    service = MomentumHeatmapService(DeterministicHistoricalBarService())
    row = service._build_row(
        MomentumHeatmapRowRequest(
            id="indexes:SPY",
            symbol="SPY",
            displayName="SPY",
            providerSymbol="SPY",
        ),
        ["1W", "1D", "4H", "1H", "30M"],
    )

    assert row.squeeze.status == "ok"
    assert row.squeeze.value in {"High squeeze", "Mid squeeze", "Low squeeze", "No squeeze"}
    assert row.squeeze.state in {"high", "mid", "low", "none"}
    assert set(row.squeeze.timeframes) == {"1W", "1D", "4H", "1H", "30M"}
    assert row.squeeze.timeframes["1D"]["status"] == "ok"
    assert "arrow" not in row.squeeze.timeframes["1D"]
    assert "arrow_reason" not in row.squeeze.timeframes["1D"]


def test_momentum_heatmap_profile_default_seed_and_color_update() -> None:
    client = TestClient(app)
    _approve_default_user(client)

    profile_response = client.get("/user/momentum-heatmap/profile", headers={"Authorization": "Bearer user-token"})
    assert profile_response.status_code == 200
    payload = profile_response.json()
    profile = payload["profile"]
    names = {item["name"] for item in payload["profiles"]}
    assert {"Morning Macro", "Growth Leaders", "Commodities", "Pullback Watch", "Custom Watchlist"}.issubset(names)
    assert profile["name"] in names
    assert _profile_by_name(payload, "Morning Macro")["isSystemSeeded"] is True
    assert _profile_by_name(payload, "Custom Watchlist")["viewSettings"]["slug"] == "custom-watchlist"
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


def test_momentum_heatmap_seeded_views_are_user_scoped_and_switchable() -> None:
    client = TestClient(app)
    _approve_user(client, token="user-token", external_auth_user_id="clerk_user")
    _approve_user(client, token="admin-token", external_auth_user_id="clerk_admin")

    user_a_payload = client.get("/user/momentum-heatmap/profile", headers=_auth("user-token")).json()
    user_b_payload = client.get("/user/momentum-heatmap/profile", headers=_auth("admin-token")).json()
    required = {"Morning Macro", "Growth Leaders", "Commodities", "Pullback Watch", "Custom Watchlist"}
    assert required.issubset({profile["name"] for profile in user_a_payload["profiles"]})
    assert required.issubset({profile["name"] for profile in user_b_payload["profiles"]})

    growth_a = _profile_by_name(user_a_payload, "Growth Leaders")
    commodities_a = _profile_by_name(user_a_payload, "Commodities")
    custom_a = _profile_by_name(user_a_payload, "Custom Watchlist")
    custom_b = _profile_by_name(user_b_payload, "Custom Watchlist")

    growth = client.get(
        "/user/momentum-heatmap/profile",
        headers=_auth("user-token"),
        params={"profileId": growth_a["id"]},
    )
    assert growth.status_code == 200
    assert growth.json()["profile"]["name"] == "Growth Leaders"
    assert "NVDA" in str(growth.json()["profile"]["categories"])

    commodities = client.get(
        "/user/momentum-heatmap/profile",
        headers=_auth("user-token"),
        params={"profileId": commodities_a["id"]},
    )
    assert commodities.status_code == 200
    assert "GLD" in str(commodities.json()["profile"]["categories"])
    assert "/CL" in str(commodities.json()["profile"]["categories"])

    add = client.post(
        "/user/momentum-heatmap/rows",
        headers=_auth("user-token"),
        json={
            "profileId": custom_a["id"],
            "categoryId": "custom-watchlist",
            "symbol": "IBM",
            "displayName": "IBM Custom",
            "providerSymbol": " ibm ",
        },
    )
    assert add.status_code == 200
    added_row_id = add.json()["row"]["id"]
    assert add.json()["row"]["providerSymbol"] == "IBM"

    user_b_custom = client.get(
        "/user/momentum-heatmap/profile",
        headers=_auth("admin-token"),
        params={"profileId": custom_b["id"]},
    )
    assert user_b_custom.status_code == 200
    assert "IBM Custom" not in str(user_b_custom.json()["profile"]["categories"])

    blocked_cross_user = client.get(
        "/user/momentum-heatmap/profile",
        headers=_auth("user-token"),
        params={"profileId": custom_b["id"]},
    )
    assert blocked_cross_user.status_code == 404

    remove = client.delete(
        f"/user/momentum-heatmap/rows/{added_row_id}?profileId={custom_a['id']}",
        headers=_auth("user-token"),
    )
    assert remove.status_code == 200
    assert "IBM Custom" not in str(remove.json()["profile"]["categories"])


def test_momentum_heatmap_custom_view_lifecycle_and_seeded_delete_protection() -> None:
    client = TestClient(app)
    _approve_default_user(client)

    seed_payload = client.get("/user/momentum-heatmap/profile", headers=_auth("user-token")).json()
    morning_macro = _profile_by_name(seed_payload, "Morning Macro")

    protected_delete = client.delete(
        f"/user/momentum-heatmap/profile/{morning_macro['id']}",
        headers=_auth("user-token"),
    )
    assert protected_delete.status_code == 409
    assert protected_delete.json()["detail"] == "momentum_heatmap_seeded_or_default_profile_protected"

    create = client.post(
        "/user/momentum-heatmap/profile",
        headers=_auth("user-token"),
        json={"name": "Lifecycle Test View", "description": "Temporary custom lifecycle view."},
    )
    assert create.status_code == 200
    custom = create.json()["profile"]
    assert custom["name"] == "Lifecycle Test View"
    assert custom["isSystemSeeded"] is False

    rename = client.put(
        "/user/momentum-heatmap/profile",
        headers=_auth("user-token"),
        json={"profileId": custom["id"], "name": "Lifecycle Test View Renamed", "description": "Renamed temporary view."},
    )
    assert rename.status_code == 200
    assert rename.json()["profile"]["name"] == "Lifecycle Test View Renamed"
    assert rename.json()["profile"]["description"] == "Renamed temporary view."

    duplicate = client.post(
        "/user/momentum-heatmap/profile/duplicate",
        headers=_auth("user-token"),
        json={"profileId": custom["id"], "name": "Lifecycle Test View Copy"},
    )
    assert duplicate.status_code == 200
    copied = duplicate.json()["profile"]
    assert copied["name"] == "Lifecycle Test View Copy"
    assert copied["id"] != custom["id"]
    assert copied["isSystemSeeded"] is False

    delete_copy = client.delete(
        f"/user/momentum-heatmap/profile/{copied['id']}",
        headers=_auth("user-token"),
    )
    assert delete_copy.status_code == 200
    assert delete_copy.json()["deleted"] is True
    assert copied["id"] not in {profile["id"] for profile in delete_copy.json()["profiles"]}

    delete_custom = client.delete(
        f"/user/momentum-heatmap/profile/{custom['id']}",
        headers=_auth("user-token"),
    )
    assert delete_custom.status_code == 200
    assert custom["id"] not in {profile["id"] for profile in delete_custom.json()["profiles"]}


def test_momentum_heatmap_snapshot_report_csv_and_schedule_are_view_scoped(monkeypatch) -> None:
    client = TestClient(app)
    _approve_user(client, token="user-token", external_auth_user_id="clerk_user")
    profile_payload = client.get("/user/momentum-heatmap/profile", headers=_auth("user-token")).json()
    custom = _profile_by_name(profile_payload, "Custom Watchlist")
    growth = _profile_by_name(profile_payload, "Growth Leaders")
    custom_row = custom["categories"][0]["rows"][0]
    custom_request_row = {
        "id": custom_row["id"],
        "symbol": custom_row["symbol"],
        "displayName": custom_row["displayName"],
        "providerSymbol": custom_row["providerSymbol"],
    }
    values = {"value": 12}

    def fake_score_cell(self, *, provider_symbol: str, timeframe: str):  # noqa: ANN001
        del self, provider_symbol, timeframe
        return MomentumHeatmapScoreCell(value=values["value"], status="ok", data_source="test", fallback_mode=False)

    monkeypatch.setattr(MomentumHeatmapService, "_score_cell", fake_score_cell)
    monkeypatch.setattr(MomentumHeatmapService, "_squeeze_cell", _ok_squeeze_cell)

    request_payload = {
        "profileId": custom["id"],
        "categories": [
                {
                    "categoryId": "custom-watchlist",
                    "categoryLabel": "CUSTOM WATCHLIST",
                    "rows": [custom_request_row],
                }
        ],
        "timeframes": ["1W", "1D", "4H", "1H", "30M"],
    }
    first = client.post("/user/momentum-heatmap/refresh", headers=_auth("user-token"), json=request_payload)
    assert first.status_code == 200
    assert first.json()["snapshot"]["profileId"] == custom["databaseId"]

    values["value"] = 30
    second = client.post("/user/momentum-heatmap/refresh", headers=_auth("user-token"), json=request_payload)
    assert second.status_code == 200
    assert second.json()["deltas"][custom_row["id"]]["strength_percent"] == 18

    latest = client.get(
        "/user/momentum-heatmap/snapshots/latest",
        headers=_auth("user-token"),
        params={"profileId": custom["id"]},
    )
    assert latest.status_code == 200
    assert latest.json()["profile"]["name"] == "Custom Watchlist"
    assert latest.json()["snapshot"]["profileId"] == custom["databaseId"]
    assert latest.json()["previousSnapshot"] is not None
    assert latest.json()["deltas"][custom_row["id"]]["strength_percent"] == 18

    wrong_profile_report = client.post(
        "/user/momentum-heatmap/report/preview",
        headers=_auth("user-token"),
        json={"profileId": growth["id"], "snapshotId": second.json()["snapshot"]["id"]},
    )
    assert wrong_profile_report.status_code == 404

    preview = client.post(
        "/user/momentum-heatmap/report/preview",
        headers=_auth("user-token"),
        json={"profileId": custom["id"]},
    )
    assert preview.status_code == 200
    assert preview.json()["report"]["profile_name"] == "Custom Watchlist"
    assert "Custom Watchlist" in preview.json()["html"]

    csv_response = client.post(
        "/user/momentum-heatmap/report/csv",
        headers=_auth("user-token"),
        json={"profileId": custom["id"]},
    )
    assert csv_response.status_code == 200
    assert custom_row["displayName"] in csv_response.json()["csv"]

    schedule = client.put(
        "/user/momentum-heatmap/schedule",
        headers=_auth("user-token"),
        json={"profileId": custom["id"], "runTime": "10:15", "enabled": True, "recipients": ["user@example.com"]},
    )
    assert schedule.status_code == 200
    assert schedule.json()["schedulePreferences"]["runTime"] == "10:15"

    custom_schedule = client.get(
        "/user/momentum-heatmap/schedule",
        headers=_auth("user-token"),
        params={"profileId": custom["id"]},
    )
    growth_schedule = client.get(
        "/user/momentum-heatmap/schedule",
        headers=_auth("user-token"),
        params={"profileId": growth["id"]},
    )
    assert custom_schedule.json()["schedulePreferences"]["runTime"] == "10:15"
    assert growth_schedule.json()["schedulePreferences"]["runTime"] != "10:15"


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
    monkeypatch.setattr(MomentumHeatmapService, "_squeeze_cell", _ok_squeeze_cell)
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
    assert "Squeeze Pro is research context only" in preview.json()["html"]
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
    assert "squeeze_value" in csv_response.json()["csv"]


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


def test_momentum_heatmap_default_profiles_rows_and_removals_are_account_isolated() -> None:
    client = TestClient(app)
    user_a_id = _approve_user(client, token="user-token", external_auth_user_id="clerk_user")
    user_b_id = _approve_user(client, token="admin-token", external_auth_user_id="clerk_admin")
    profile_a = _reset_momentum_heatmap_profile(client, "user-token")
    profile_b = _reset_momentum_heatmap_profile(client, "admin-token")

    assert profile_a["id"] != profile_b["id"]
    assert profile_a["databaseId"] != profile_b["databaseId"]

    add = client.post(
        "/user/momentum-heatmap/rows",
        headers=_auth("user-token"),
        json={
            "profileId": profile_a["id"],
            "categoryId": "indexes",
            "symbol": "TSLA",
            "displayName": "TSLA Custom Isolation",
            "providerSymbol": "TSLA",
        },
    )
    assert add.status_code == 200
    added_row_id = add.json()["row"]["id"]

    user_b_after_add = client.get("/user/momentum-heatmap/profile", headers=_auth("admin-token"))
    assert user_b_after_add.status_code == 200
    assert added_row_id not in _row_ids(user_b_after_add.json()["profile"])
    assert "TSLA Custom Isolation" not in str(user_b_after_add.json()["profile"]["categories"])

    cross_user_remove = client.delete(
        f"/user/momentum-heatmap/rows/{added_row_id}?profileId={profile_b['id']}",
        headers=_auth("admin-token"),
    )
    assert cross_user_remove.status_code == 404

    user_a_latest = client.get("/user/momentum-heatmap/profile", headers=_auth("user-token")).json()["profile"]
    spy_row_id = next(row["id"] for row in _category(user_a_latest, "indexes")["rows"] if row["providerSymbol"] == "SPY")
    remove = client.delete(
        f"/user/momentum-heatmap/rows/{spy_row_id}?profileId={profile_a['id']}",
        headers=_auth("user-token"),
    )
    assert remove.status_code == 200
    assert all(row["providerSymbol"] != "SPY" for row in _category(remove.json()["profile"], "indexes")["rows"])

    user_b_after_remove = client.get("/user/momentum-heatmap/profile", headers=_auth("admin-token"))
    assert user_b_after_remove.status_code == 200
    assert any(row["providerSymbol"] == "SPY" for row in _category(user_b_after_remove.json()["profile"], "indexes")["rows"])

    with SessionLocal() as session:
        db_profile_a = session.get(MomentumHeatmapProfileModel, profile_a["databaseId"])
        db_profile_b = session.get(MomentumHeatmapProfileModel, profile_b["databaseId"])
        assert db_profile_a is not None
        assert db_profile_b is not None
        assert db_profile_a.app_user_id == user_a_id
        assert db_profile_b.app_user_id == user_b_id


def test_momentum_heatmap_profile_colors_reports_and_schedule_are_account_isolated() -> None:
    client = TestClient(app)
    user_a_id = _approve_user(client, token="user-token", external_auth_user_id="clerk_user")
    user_b_id = _approve_user(client, token="admin-token", external_auth_user_id="clerk_admin")
    profile_a = _reset_momentum_heatmap_profile(client, "user-token")
    profile_b = _reset_momentum_heatmap_profile(client, "admin-token")
    user_b_profile_before = client.get("/user/momentum-heatmap/profile", headers=_auth("admin-token")).json()["profile"]
    user_b_schedule_before = client.get("/user/momentum-heatmap/schedule", headers=_auth("admin-token")).json()["schedulePreferences"]

    updated_ranges = [dict(item) for item in profile_a["colorRanges"]]
    updated_ranges[0] = {**updated_ranges[0], "min": 64, "label": "User A bright green"}
    update_profile = client.put(
        "/user/momentum-heatmap/profile",
        headers=_auth("user-token"),
        json={
            "profileId": profile_a["id"],
            "colorRanges": updated_ranges,
            "reportPreferences": {"isolationMarker": "user-a-report-settings"},
        },
    )
    assert update_profile.status_code == 200
    assert update_profile.json()["profile"]["colorRanges"][0]["min"] == 64
    assert update_profile.json()["profile"]["reportPreferences"]["isolationMarker"] == "user-a-report-settings"

    update_schedule = client.put(
        "/user/momentum-heatmap/schedule",
        headers=_auth("user-token"),
        json={
            "profileId": profile_a["id"],
            "enabled": True,
            "runTime": "10:15",
            "recipients": ["user@example.com"],
            "includeCsvAttachment": False,
        },
    )
    assert update_schedule.status_code == 200

    user_b_profile_after = client.get("/user/momentum-heatmap/profile", headers=_auth("admin-token")).json()["profile"]
    user_b_schedule_after = client.get("/user/momentum-heatmap/schedule", headers=_auth("admin-token")).json()["schedulePreferences"]

    assert user_b_profile_after["id"] == profile_b["id"]
    assert user_b_profile_after["colorRanges"] == user_b_profile_before["colorRanges"]
    assert user_b_profile_after["reportPreferences"] == user_b_profile_before["reportPreferences"]
    assert user_b_schedule_after["runTime"] == user_b_schedule_before["runTime"]
    assert user_b_schedule_after["recipients"] == user_b_schedule_before["recipients"]

    with SessionLocal() as session:
        schedule_a = session.execute(
            select(MomentumHeatmapSchedulePreferenceModel).where(
                MomentumHeatmapSchedulePreferenceModel.app_user_id == user_a_id,
                MomentumHeatmapSchedulePreferenceModel.profile_id == profile_a["databaseId"],
            )
        ).scalar_one()
        schedule_b = session.execute(
            select(MomentumHeatmapSchedulePreferenceModel).where(
                MomentumHeatmapSchedulePreferenceModel.app_user_id == user_b_id,
                MomentumHeatmapSchedulePreferenceModel.profile_id == profile_b["databaseId"],
            )
        ).scalar_one()
        assert schedule_a.run_time == "10:15"
        assert schedule_a.recipients == ["user@example.com"]
        assert schedule_b.run_time == user_b_schedule_before["runTime"]
        assert schedule_b.recipients == user_b_schedule_before["recipients"]


def test_momentum_heatmap_snapshots_reports_and_profile_ids_are_account_isolated(monkeypatch) -> None:
    client = TestClient(app)
    user_a_id = _approve_user(client, token="user-token", external_auth_user_id="clerk_user")
    user_b_id = _approve_user(client, token="admin-token", external_auth_user_id="clerk_admin")
    profile_a = _reset_momentum_heatmap_profile(client, "user-token")
    profile_b = _reset_momentum_heatmap_profile(client, "admin-token")

    def fake_score_cell(self, *, provider_symbol: str, timeframe: str):  # noqa: ANN001
        del self, provider_symbol, timeframe
        return MomentumHeatmapScoreCell(value=42, status="ok", data_source="test", fallback_mode=False)

    monkeypatch.setattr(MomentumHeatmapService, "_score_cell", fake_score_cell)
    monkeypatch.setattr(MomentumHeatmapService, "_squeeze_cell", _ok_squeeze_cell)

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
    user_a_refresh = client.post("/user/momentum-heatmap/refresh", headers=_auth("user-token"), json=request_payload)
    user_b_refresh = client.post("/user/momentum-heatmap/refresh", headers=_auth("admin-token"), json=request_payload)
    assert user_a_refresh.status_code == 200
    assert user_b_refresh.status_code == 200
    user_a_snapshot_id = user_a_refresh.json()["snapshot"]["id"]
    user_b_snapshot_id = user_b_refresh.json()["snapshot"]["id"]
    assert user_a_snapshot_id != user_b_snapshot_id

    assert client.get(f"/user/momentum-heatmap/snapshots/{user_a_snapshot_id}", headers=_auth("admin-token")).status_code == 404
    assert client.get(f"/user/momentum-heatmap/snapshots/{user_b_snapshot_id}", headers=_auth("user-token")).status_code == 404
    assert client.post(
        "/user/momentum-heatmap/report/preview",
        headers=_auth("admin-token"),
        json={"snapshotId": user_a_snapshot_id},
    ).status_code == 404
    assert client.post(
        "/user/momentum-heatmap/report/csv",
        headers=_auth("admin-token"),
        json={"snapshotId": user_a_snapshot_id},
    ).status_code == 404
    assert client.post(
        "/user/momentum-heatmap/report/email",
        headers=_auth("admin-token"),
        json={"snapshotId": user_a_snapshot_id, "recipients": ["admin@example.com"]},
    ).status_code == 404
    assert client.post(
        "/user/momentum-heatmap/report/preview",
        headers=_auth("user-token"),
        json={"snapshotId": user_b_snapshot_id},
    ).status_code == 404
    assert client.put(
        "/user/momentum-heatmap/profile",
        headers=_auth("user-token"),
        json={"profileId": profile_b["id"], "name": "Cross-user overwrite attempt"},
    ).status_code == 404
    assert client.post(
        "/user/momentum-heatmap/profile/reset",
        headers=_auth("admin-token"),
        json={"profileId": profile_a["id"]},
    ).status_code == 404

    with SessionLocal() as session:
        snapshot_a = session.execute(
            select(MomentumHeatmapSnapshotModel).where(MomentumHeatmapSnapshotModel.snapshot_uid == user_a_snapshot_id)
        ).scalar_one()
        snapshot_b = session.execute(
            select(MomentumHeatmapSnapshotModel).where(MomentumHeatmapSnapshotModel.snapshot_uid == user_b_snapshot_id)
        ).scalar_one()
        assert snapshot_a.app_user_id == user_a_id
        assert snapshot_a.profile_id == profile_a["databaseId"]
        assert snapshot_b.app_user_id == user_b_id
        assert snapshot_b.profile_id == profile_b["databaseId"]
