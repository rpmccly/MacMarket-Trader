from fastapi.testclient import TestClient
from sqlalchemy import select

from macmarket_trader.api.main import app
from macmarket_trader.charts.haco_heatmap_service import HacoHeatmapService
from macmarket_trader.data.providers.market_data import DeterministicFallbackMarketDataProvider
from macmarket_trader.domain.models import AppUserModel, HacoHeatmapProfileModel, HacoHeatmapSnapshotModel
from macmarket_trader.domain.schemas import HacoHeatmapDirectionCell, HacoHeatmapRowRequest
from macmarket_trader.storage.db import SessionLocal


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


def _approve_default_user(client: TestClient) -> int:
    return _approve_user(client, token="user-token", external_auth_user_id="clerk_user")


def _direction_cell(value: str) -> HacoHeatmapDirectionCell:
    return HacoHeatmapDirectionCell(value=value, label="LONG" if value == "long" else "SHORT", status="ok", data_source="test", fallback_mode=False)


def _unsupported_cell(reason: str = "unsupported_symbol_format") -> HacoHeatmapDirectionCell:
    return HacoHeatmapDirectionCell(value=None, label="—", status="unsupported", reason=reason)


def _profile_by_name(payload: dict, name: str) -> dict:
    return next(profile for profile in payload["profiles"] if profile["name"] == name)


def _category(profile: dict, category_id: str) -> dict:
    return next(category for category in profile["categories"] if category["categoryId"] == category_id)


def _row_ids(profile: dict) -> set[str]:
    return {row["id"] for category in profile["categories"] for row in category["rows"]}


class DeterministicHistoricalBarService:
    def __init__(self) -> None:
        self.provider = DeterministicFallbackMarketDataProvider()

    def historical_bars(self, symbol: str, timeframe: str, limit: int):  # noqa: ANN001
        bars = self.provider.fetch_historical_bars(symbol=symbol, timeframe=timeframe, limit=limit)
        return bars, "fallback", True


class NoProviderCallsExpected:
    def historical_bars(self, symbol: str, timeframe: str, limit: int):  # noqa: ANN001
        raise AssertionError(f"provider call should have failed fast for {symbol} {timeframe} {limit}")


def test_haco_heatmap_uses_existing_haco_chart_path_for_valid_symbol() -> None:
    service = HacoHeatmapService(DeterministicHistoricalBarService())
    request = HacoHeatmapRowRequest(id="indexes:SPY", symbol="SPY", displayName="SPY", providerSymbol="SPY")

    row = service._build_row(request, ["1W", "1D", "4H", "1H", "30M"])

    assert row.provider_symbol == "SPY"
    assert set(row.states) == {"1W", "1D", "4H", "1H", "30M"}
    assert all(cell.status == "ok" for cell in row.states.values())
    assert all(cell.label in {"LONG", "SHORT"} for cell in row.states.values())
    assert row.overall_bias in {"LONG", "SHORT", "MIXED"}
    assert row.short_term_bias in {"LONG", "SHORT", "MIXED"}


def test_haco_heatmap_alignment_formulas_bias_thresholds_and_tags(monkeypatch) -> None:
    states = {
        "SPY": {"1W": "long", "1D": "long", "4H": "long", "1H": "long", "30M": "long"},
        "QQQ": {"1W": "short", "1D": "short", "4H": "short", "1H": "short", "30M": "short"},
        "NVDA": {"1W": "long", "1D": "long", "4H": "short", "1H": "short", "30M": "short"},
        "MSFT": {"1W": "short", "1D": "short", "4H": "long", "1H": "long", "30M": "long"},
        "IBM": {"1W": "long", "1D": "short", "4H": "long", "1H": "short", "30M": "long"},
    }

    def fake_state_cell(self, *, provider_symbol: str, timeframe: str):  # noqa: ANN001
        del self
        return _direction_cell(states[provider_symbol][timeframe])

    monkeypatch.setattr(HacoHeatmapService, "_state_cell", fake_state_cell)
    client = TestClient(app)
    _approve_default_user(client)
    response = client.post(
        "/user/haco-heatmap/refresh",
        headers=_auth("user-token"),
        json={
            "categories": [
                {
                    "categoryId": "indexes",
                    "categoryLabel": "INDEXES",
                    "rows": [
                        {"id": "indexes:SPY", "symbol": "SPY", "displayName": "SPY", "providerSymbol": "SPY"},
                        {"id": "indexes:QQQ", "symbol": "QQQ", "displayName": "QQQ", "providerSymbol": "QQQ"},
                        {"id": "indexes:NVDA", "symbol": "NVDA", "displayName": "NVDA", "providerSymbol": "NVDA"},
                        {"id": "indexes:MSFT", "symbol": "MSFT", "displayName": "MSFT", "providerSymbol": "MSFT"},
                        {"id": "indexes:IBM", "symbol": "IBM", "displayName": "IBM", "providerSymbol": "IBM"},
                    ],
                }
            ],
            "timeframes": ["1W", "1D", "4H", "1H", "30M"],
        },
    )

    assert response.status_code == 200
    rows = {row["providerSymbol"]: row for row in response.json()["heatmap"]["categories"][0]["rows"]}
    assert rows["SPY"]["overall_alignment_percent"] == 100
    assert rows["SPY"]["short_term_alignment_percent"] == 100
    assert rows["SPY"]["overall_bias"] == "LONG"
    assert rows["SPY"]["tags"] == ["All LONG"]

    assert rows["QQQ"]["overall_alignment_percent"] == -100
    assert rows["QQQ"]["short_term_alignment_percent"] == -100
    assert rows["QQQ"]["overall_bias"] == "SHORT"
    assert rows["QQQ"]["tags"] == ["All SHORT"]

    assert rows["NVDA"]["overall_alignment_percent"] == 20
    assert rows["NVDA"]["short_term_alignment_percent"] == -100
    assert rows["NVDA"]["overall_bias"] == "MIXED"
    assert "Daily LONG / Short-Term Pullback" in rows["NVDA"]["tags"]

    assert rows["MSFT"]["overall_alignment_percent"] == -20
    assert rows["MSFT"]["short_term_alignment_percent"] == 100
    assert rows["MSFT"]["overall_bias"] == "MIXED"
    assert "Daily SHORT / Short-Term Bounce" in rows["MSFT"]["tags"]

    assert rows["IBM"]["overall_alignment_percent"] == 20
    assert rows["IBM"]["overall_bias"] == "MIXED"
    assert "Mixed / Chop" in rows["IBM"]["tags"]


def test_haco_heatmap_unsupported_symbols_fail_fast_before_provider_calls() -> None:
    service = HacoHeatmapService(NoProviderCallsExpected())
    for symbol, expected_reason in (("/CL", "unsupported_symbol_format"), ("MAG7", "composite_symbol_deferred")):
        row = service._build_row(
            HacoHeatmapRowRequest(
                id=f"indexes:{symbol}",
                symbol=symbol,
                displayName=symbol,
                providerSymbol=symbol,
            ),
            ["1W", "1D", "4H", "1H", "30M"],
        )
        assert all(cell.status == "unsupported" for cell in row.states.values())
        assert all(cell.reason == expected_reason for cell in row.states.values())
        assert row.overall_bias is None
        assert row.tags == ["Unsupported"]


def test_haco_heatmap_refresh_accepts_frontend_saved_view_payload_and_row_level_unsupported(monkeypatch) -> None:
    client = TestClient(app)
    _approve_default_user(client)
    profile = client.get("/user/haco-heatmap/profile", headers=_auth("user-token")).json()["profile"]
    provider_calls: list[str] = []

    def fake_state_cell(self, *, provider_symbol: str, timeframe: str):  # noqa: ANN001
        del self, timeframe
        provider_calls.append(provider_symbol)
        return _direction_cell("long")

    monkeypatch.setattr(HacoHeatmapService, "_state_cell", fake_state_cell)
    response = client.post(
        "/user/haco-heatmap/refresh",
        headers=_auth("user-token"),
        json={
            "profileId": profile["id"],
            "categories": [
                {
                    "categoryId": "indexes",
                    "categoryLabel": "INDEXES",
                    "included": True,
                    "collapsed": False,
                    "rows": [
                        {
                            "id": "indexes:SPY",
                            "categoryId": "indexes",
                            "categoryLabel": "INDEXES",
                            "symbol": "SPY",
                            "displayName": "SPY",
                            "providerSymbol": "SPY",
                            "originalSymbol": "SPY",
                            "workbookOrder": 0,
                            "enabled": True,
                            "userAdded": False,
                            "unsupported": False,
                            "unsupportedReason": None,
                        },
                        {
                            "id": "indexes:QQQ",
                            "categoryId": "indexes",
                            "categoryLabel": "INDEXES",
                            "symbol": "QQQ",
                            "displayName": "QQQ",
                            "providerSymbol": "QQQ",
                            "workbookOrder": 1,
                            "enabled": True,
                        },
                        {
                            "id": "indexes:/NKD",
                            "categoryId": "indexes",
                            "categoryLabel": "INDEXES",
                            "symbol": "/NKD",
                            "displayName": "Japan - /NKD",
                            "providerSymbol": "/NKD",
                            "workbookOrder": 2,
                            "enabled": True,
                            "unsupported": True,
                            "unsupportedReason": "unsupported_symbol_format",
                            "notes": "Workbook label retained for operator context.",
                        },
                    ],
                }
            ],
            "timeframes": ["1W", "1D", "4H", "1H", "30M"],
        },
    )

    assert response.status_code == 200
    rows = {row["id"]: row for row in response.json()["heatmap"]["categories"][0]["rows"]}
    assert rows["indexes:SPY"]["providerSymbol"] == "SPY"
    assert all(cell["status"] == "ok" for cell in rows["indexes:SPY"]["states"].values())
    assert rows["indexes:QQQ"]["overall_bias"] == "LONG"
    assert all(cell["status"] == "unsupported" for cell in rows["indexes:/NKD"]["states"].values())
    assert all(cell["reason"] == "unsupported_symbol_format" for cell in rows["indexes:/NKD"]["states"].values())
    assert "/NKD" not in provider_calls


def test_haco_heatmap_server_seeded_views_and_profile_rows_are_account_isolated() -> None:
    client = TestClient(app)
    user_a_id = _approve_user(client, token="user-token", external_auth_user_id="clerk_user")
    user_b_id = _approve_user(client, token="admin-token", external_auth_user_id="clerk_admin")

    profile_a_response = client.get("/user/haco-heatmap/profile", headers=_auth("user-token"))
    profile_b_response = client.get("/user/haco-heatmap/profile", headers=_auth("admin-token"))
    assert profile_a_response.status_code == 200
    assert profile_b_response.status_code == 200
    profile_a = profile_a_response.json()["profile"]
    profile_b = profile_b_response.json()["profile"]
    names_a = {profile["name"] for profile in profile_a_response.json()["profiles"]}
    names_b = {profile["name"] for profile in profile_b_response.json()["profiles"]}
    assert {"Morning Macro", "Growth Leaders", "Commodities", "Pullback Watch", "Custom Watchlist"}.issubset(names_a)
    assert names_a == names_b
    assert profile_a["id"] != profile_b["id"]
    assert profile_a["databaseId"] != profile_b["databaseId"]

    custom_a = _profile_by_name(profile_a_response.json(), "Custom Watchlist")
    add = client.post(
        "/user/haco-heatmap/rows",
        headers=_auth("user-token"),
        json={
            "profileId": custom_a["id"],
            "categoryId": "custom-watchlist",
            "symbol": "ibm",
            "displayName": "IBM User A HACO",
            "providerSymbol": " ibm ",
        },
    )
    assert add.status_code == 200
    added_row_id = add.json()["row"]["id"]
    assert add.json()["row"]["providerSymbol"] == "IBM"

    duplicate = client.post(
        "/user/haco-heatmap/rows",
        headers=_auth("user-token"),
        json={"profileId": custom_a["id"], "categoryId": "custom-watchlist", "symbol": " IBM ", "providerSymbol": "IBM"},
    )
    assert duplicate.status_code == 409
    assert "IBM is already in CUSTOM WATCHLIST" in duplicate.json()["detail"]["message"]

    user_b_after_add = client.get("/user/haco-heatmap/profile", headers=_auth("admin-token"), params={"profileId": _profile_by_name(profile_b_response.json(), "Custom Watchlist")["id"]})
    assert user_b_after_add.status_code == 200
    assert added_row_id not in _row_ids(user_b_after_add.json()["profile"])
    assert "IBM User A HACO" not in str(user_b_after_add.json()["profile"]["categories"])

    remove = client.delete(f"/user/haco-heatmap/rows/{added_row_id}", headers=_auth("user-token"), params={"profileId": custom_a["id"]})
    assert remove.status_code == 200
    assert all(row["id"] != added_row_id for row in _category(remove.json()["profile"], "custom-watchlist")["rows"])

    with SessionLocal() as session:
        db_profile_a = session.get(HacoHeatmapProfileModel, profile_a["databaseId"])
        db_profile_b = session.get(HacoHeatmapProfileModel, profile_b["databaseId"])
        assert db_profile_a is not None
        assert db_profile_b is not None
        assert db_profile_a.app_user_id == user_a_id
        assert db_profile_b.app_user_id == user_b_id


def test_haco_heatmap_refresh_snapshots_deltas_report_and_csv_are_profile_scoped(monkeypatch) -> None:
    client = TestClient(app)
    _approve_default_user(client)
    mode = {"direction": "long"}

    def fake_state_cell(self, *, provider_symbol: str, timeframe: str):  # noqa: ANN001
        del self, provider_symbol, timeframe
        return _direction_cell(mode["direction"])

    monkeypatch.setattr(HacoHeatmapService, "_state_cell", fake_state_cell)
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

    first = client.post("/user/haco-heatmap/refresh", headers=_auth("user-token"), json=request_payload)
    assert first.status_code == 200
    assert first.json()["snapshot"]["status"] == "fresh"
    assert first.json()["previousSnapshot"] is None
    assert first.json()["heatmap"]["categories"][0]["rows"][0]["overall_bias"] == "LONG"

    mode["direction"] = "short"
    second = client.post("/user/haco-heatmap/refresh", headers=_auth("user-token"), json=request_payload)
    assert second.status_code == 200
    assert second.json()["previousSnapshot"] is not None
    assert second.json()["changes"]["indexes:SPY"]["prior_overall_bias"] == "LONG"
    assert second.json()["changes"]["indexes:SPY"]["current_overall_bias"] == "SHORT"
    assert second.json()["changes"]["indexes:SPY"]["alignment_delta"] == -200
    assert "Fresh SHORT Flip" in second.json()["heatmap"]["categories"][0]["rows"][0]["tags"]

    latest = client.get("/user/haco-heatmap/snapshots/latest", headers=_auth("user-token"))
    assert latest.status_code == 200
    assert "Loaded last HACO Direction snapshot" in latest.json()["message"]
    assert latest.json()["previousSnapshot"] is not None

    preview = client.post("/user/haco-heatmap/report/preview", headers=_auth("user-token"), json={})
    assert preview.status_code == 200
    assert "HACO Direction Heatmap" in preview.json()["html"]
    assert "Category Direction Summary" in preview.json()["html"]
    assert "Full HACO Direction Table" in preview.json()["html"]
    assert "Research dashboard only. Not trade execution or investment advice." in preview.json()["html"]
    assert preview.json()["emailStatus"] == "email_not_configured_for_haco_heatmap_reports"

    csv_response = client.post("/user/haco-heatmap/report/csv", headers=_auth("user-token"), json={})
    assert csv_response.status_code == 200
    assert "overall_bias" in csv_response.json()["csv"]
    assert "SPY" in csv_response.json()["csv"]


def test_haco_heatmap_snapshots_reports_and_profile_ids_are_account_isolated(monkeypatch) -> None:
    client = TestClient(app)
    user_a_id = _approve_user(client, token="user-token", external_auth_user_id="clerk_user")
    user_b_id = _approve_user(client, token="admin-token", external_auth_user_id="clerk_admin")
    profile_a = client.get("/user/haco-heatmap/profile", headers=_auth("user-token")).json()["profile"]
    profile_b = client.get("/user/haco-heatmap/profile", headers=_auth("admin-token")).json()["profile"]

    def fake_state_cell(self, *, provider_symbol: str, timeframe: str):  # noqa: ANN001
        del self, provider_symbol, timeframe
        return _direction_cell("long")

    monkeypatch.setattr(HacoHeatmapService, "_state_cell", fake_state_cell)
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
    user_a_refresh = client.post("/user/haco-heatmap/refresh", headers=_auth("user-token"), json=request_payload)
    user_b_refresh = client.post("/user/haco-heatmap/refresh", headers=_auth("admin-token"), json=request_payload)
    assert user_a_refresh.status_code == 200
    assert user_b_refresh.status_code == 200
    user_a_snapshot_id = user_a_refresh.json()["snapshot"]["id"]
    user_b_snapshot_id = user_b_refresh.json()["snapshot"]["id"]
    assert user_a_snapshot_id != user_b_snapshot_id

    assert client.get(f"/user/haco-heatmap/snapshots/{user_a_snapshot_id}", headers=_auth("admin-token")).status_code == 404
    assert client.get(f"/user/haco-heatmap/snapshots/{user_b_snapshot_id}", headers=_auth("user-token")).status_code == 404
    assert client.post("/user/haco-heatmap/report/preview", headers=_auth("admin-token"), json={"snapshotId": user_a_snapshot_id}).status_code == 404
    assert client.post("/user/haco-heatmap/report/csv", headers=_auth("admin-token"), json={"snapshotId": user_a_snapshot_id}).status_code == 404
    assert client.put(
        "/user/haco-heatmap/profile",
        headers=_auth("user-token"),
        json={"profileId": profile_b["id"], "name": "Cross-user overwrite attempt"},
    ).status_code == 404
    assert client.post(
        "/user/haco-heatmap/profile/reset",
        headers=_auth("admin-token"),
        json={"profileId": profile_a["id"]},
    ).status_code == 404

    with SessionLocal() as session:
        snapshot_a = session.execute(select(HacoHeatmapSnapshotModel).where(HacoHeatmapSnapshotModel.snapshot_uid == user_a_snapshot_id)).scalar_one()
        snapshot_b = session.execute(select(HacoHeatmapSnapshotModel).where(HacoHeatmapSnapshotModel.snapshot_uid == user_b_snapshot_id)).scalar_one()
        assert snapshot_a.app_user_id == user_a_id
        assert snapshot_a.profile_id == profile_a["databaseId"]
        assert snapshot_b.app_user_id == user_b_id
        assert snapshot_b.profile_id == profile_b["databaseId"]
