"""Server-side defaults for the Momentum Heatmap workbook view.

These defaults mirror the workbook-derived frontend seed. They are used only
to create user-scoped heatmap profiles and report preferences; they do not
change Momentum Intelligence scoring, recommendation approval, or paper-order
behavior.
"""

from __future__ import annotations

from typing import Any

from macmarket_trader.charts.momentum_heatmap_service import MomentumHeatmapService

DEFAULT_MOMENTUM_HEATMAP_PROFILE_NAME = "Morning Macro"
DEFAULT_MOMENTUM_HEATMAP_STALE_THRESHOLD_HOURS = 24
MOMENTUM_HEATMAP_SEEDED_VIEW_SLUGS = (
    "morning-macro",
    "growth-leaders",
    "commodities",
    "pullback-watch",
    "custom-watchlist",
)

DEFAULT_MOMENTUM_HEATMAP_COLOR_RANGES: list[dict[str, object]] = [
    {"id": "bright-green", "min": 75, "max": 100, "label": "Bright green", "color": "#56f08a", "className": "hm-score-bright-green"},
    {"id": "green", "min": 25, "max": 74.999, "label": "Green", "color": "#1f9f62", "className": "hm-score-green"},
    {"id": "purple", "min": -24.999, "max": 24.999, "label": "Purple", "color": "#7d5cff", "className": "hm-score-purple"},
    {"id": "red", "min": -74.999, "max": -25, "label": "Red", "color": "#bd3d4b", "className": "hm-score-red"},
    {"id": "bright-red", "min": -100, "max": -75, "label": "Bright red", "color": "#ff4b4b", "className": "hm-score-bright-red"},
]


SymbolEntry = str | dict[str, str]


def _row_id(category_id: str, display_name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in display_name.upper()).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return f"{category_id}:{cleaned or 'ROW'}"


def _row(category_id: str, category_label: str, entry: SymbolEntry, order: int) -> dict[str, Any]:
    if isinstance(entry, str):
        symbol = entry
        display_name = entry
        provider_symbol = entry
    else:
        symbol = entry["symbol"]
        display_name = entry.get("displayName", symbol)
        provider_symbol = entry.get("providerSymbol", symbol)
    normalized_provider_symbol = str(provider_symbol or symbol).strip().upper()
    unsupported_reason = MomentumHeatmapService._unsupported_provider_symbol_reason(normalized_provider_symbol)
    return {
        "id": _row_id(category_id, display_name),
        "categoryId": category_id,
        "categoryLabel": category_label,
        "symbol": str(symbol).strip(),
        "displayName": str(display_name).strip(),
        "providerSymbol": normalized_provider_symbol,
        "originalSymbol": str(symbol).strip(),
        "workbookOrder": order,
        "enabled": True,
        "userAdded": False,
        "unsupported": unsupported_reason is not None,
        "unsupportedReason": unsupported_reason,
        "notes": unsupported_reason,
    }


def _category(category_id: str, category_label: str, entries: list[SymbolEntry]) -> dict[str, Any]:
    return {
        "categoryId": category_id,
        "categoryLabel": category_label,
        "included": True,
        "collapsed": False,
        "rows": [_row(category_id, category_label, entry, idx) for idx, entry in enumerate(entries)],
    }


def default_momentum_heatmap_categories() -> list[dict[str, Any]]:
    return [
        _category(
            "indexes",
            "INDEXES",
            [
                "SPY",
                "QQQ",
                "DIA",
                "IWM",
                "RSP",
                "QQQE",
                "MAG7",
                "MTUM",
                {"symbol": "VTI", "displayName": "ALL U.S. - VTI", "providerSymbol": "VTI"},
                {"symbol": "VT", "displayName": "ALL WORLD - VT", "providerSymbol": "VT"},
                {"symbol": "/NKD", "displayName": "Japan - /NKD", "providerSymbol": "/NKD"},
                {"symbol": "DAX:DBI", "displayName": "Eur - DAX:DBI", "providerSymbol": "DAX:DBI"},
                {"symbol": "FXI", "displayName": "China - FXI", "providerSymbol": "FXI"},
                "EEM",
            ],
        ),
        _category(
            "sectors",
            "SECTORS",
            [
                "XLB",
                "XLC",
                "XLE",
                "OIH",
                "XLF",
                "KRE",
                "XLI",
                "XLK",
                "XLP",
                "XLU",
                "XLV",
                "XLY",
                "XLRE",
                "XBI",
                "XME",
                "XRT",
                "GDX",
                "SMH",
                "IGV",
                "$DJT",
                "ITB",
                "ARKK",
                "ITA",
                "JETS",
                "UFO",
                "BOTZ",
                "URA",
                "ICLN",
                "TAN",
                "KWEB",
            ],
        ),
        _category(
            "major-stocks",
            "MAJOR STOCKS",
            [
                "AAPL",
                "ALAB",
                "AMAT",
                "AMZN",
                "AMD",
                "APP",
                "AVGO",
                "BABA",
                "BRK/B",
                "CAT",
                "CEG",
                "COIN",
                "CRDO",
                "CRWD",
                "CVNA",
                "GE",
                "GEV",
                "GOOGL",
                "GS",
                "IONQ",
                "IREN",
                "HD",
                "HOOD",
                "INTC",
                "JPM",
                "LITE",
                "LLY",
                "META",
                "MSFT",
                "MSTR",
                "MU",
                "NBIS",
                "NFLX",
                "NVDA",
                "OKLO",
                "ORCL",
                "PLTR",
                "RKLB",
                "SLB",
                "TSLA",
                "TSM",
                "UNH",
                "V",
                "VRT",
                "WMT",
                "XOM",
            ],
        ),
        _category(
            "bonds-misc",
            "BONDS + MISC",
            ["/ZT", "/ZN", "/ZB", "TLT", "LQD", "HYG", "$DXY", "AUD/JPY", "/VX", "VIX", "VXX", "VVIX", "$SPXA50R", "$PCALL", "SKEW", "T10Y2Y:FRED"],
        ),
        _category("commodities", "COMMODITIES", ["$DJCI", "/CL", "USO", "/RB", "/NG", "/HG", "/GC", "GLD", "/SI", "SLV", "/BTC", "/ETH", "/ZC", "/ZS", "/ZW"]),
    ]


def default_momentum_heatmap_view_settings(
    *,
    slug: str = "morning-macro",
    description: str = "Broad morning market regime read.",
    purpose: str = "Broad morning market regime read.",
    view_type: str = "system_seeded",
    filters: dict[str, object] | None = None,
    is_system_seeded: bool = True,
) -> dict[str, object]:
    return {
        "sort": "workbook",
        "filters": filters or {
            "search": "",
            "supportedOnly": False,
            "hideUnavailable": False,
            "alignment": "all",
            "strengthMin": None,
            "strengthMax": None,
            "changedOnly": False,
            "positiveDeltaOnly": False,
            "negativeDeltaOnly": False,
        },
        "showDeltas": True,
        "staleThresholdHours": DEFAULT_MOMENTUM_HEATMAP_STALE_THRESHOLD_HOURS,
        "slug": slug,
        "viewType": view_type,
        "description": description,
        "purpose": purpose,
        "isSystemSeeded": is_system_seeded,
    }


def default_momentum_heatmap_report_preferences() -> dict[str, object]:
    return {
        "includedProfileMode": "current_profile",
        "includeFullTable": True,
        "includeCsvAttachment": True,
        "reportMode": "latest_snapshot",
        "notes": [
            "Intraday timeframe scores use latest completed regular-hours bars.",
            "Squeeze Pro is displayed as research context and is not part of True Momentum scoring.",
        ],
    }


def default_momentum_heatmap_schedule_preferences(user_email: str | None = None) -> dict[str, object]:
    return {
        "enabled": False,
        "timezone": "America/Indiana/Indianapolis",
        "runTime": "07:00",
        "daysOfWeek": ["mon", "tue", "wed", "thu", "fri"],
        "reportMode": "latest_snapshot",
        "recipients": [user_email] if user_email else [],
        "includeCsvAttachment": True,
        "includeFullTable": True,
        "schedulerActive": False,
        "runnerHook": "python -m macmarket_trader.cli run-due-momentum-heatmap-reports",
    }


def _base_category_map() -> dict[str, dict[str, Any]]:
    return {str(category["categoryId"]): category for category in default_momentum_heatmap_categories()}


def _copy_whole_category(category_id: str) -> dict[str, Any]:
    return _base_category_map()[category_id]


def _copy_filtered_category(category_id: str, symbols: list[str]) -> dict[str, Any]:
    base = _base_category_map()[category_id]
    wanted = [symbol.strip().upper() for symbol in symbols]
    by_symbol = {
        str(row.get("providerSymbol") or row.get("symbol") or "").strip().upper(): row
        for row in base.get("rows", [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for order, symbol in enumerate(wanted):
        source = by_symbol.get(symbol)
        if source is None:
            source = _row(str(base["categoryId"]), str(base["categoryLabel"]), symbol, order)
        row = dict(source)
        row["workbookOrder"] = order
        rows.append(row)
    return {
        "categoryId": base["categoryId"],
        "categoryLabel": base["categoryLabel"],
        "included": True,
        "collapsed": False,
        "rows": rows,
    }


def _custom_watchlist_category() -> dict[str, Any]:
    return _category("custom-watchlist", "CUSTOM WATCHLIST", ["SPY", "QQQ", "IWM", "NVDA", "TSLA"])


def _seed_view_payload(
    *,
    name: str,
    slug: str,
    description: str,
    purpose: str,
    categories: list[dict[str, Any]],
    is_default: bool = False,
    filters: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "slug": slug,
        "description": description,
        "purpose": purpose,
        "categories": categories,
        "color_ranges": [dict(item) for item in DEFAULT_MOMENTUM_HEATMAP_COLOR_RANGES],
        "view_settings": default_momentum_heatmap_view_settings(
            slug=slug,
            description=description,
            purpose=purpose,
            filters=filters,
            is_system_seeded=True,
        ),
        "report_preferences": default_momentum_heatmap_report_preferences(),
        "is_default": is_default,
        "is_system_seeded": True,
    }


def seeded_momentum_heatmap_profile_payloads() -> list[dict[str, object]]:
    pullback_filters: dict[str, object] = {
        "search": "",
        "supportedOnly": False,
        "hideUnavailable": True,
        "alignment": "pullback",
        "strengthMin": 25,
        "strengthMax": None,
        "changedOnly": False,
        "positiveDeltaOnly": False,
        "negativeDeltaOnly": False,
    }
    return [
        _seed_view_payload(
            name="Morning Macro",
            slug="morning-macro",
            description="Broad morning market regime read.",
            purpose="Broad morning market regime read.",
            categories=[
                _copy_whole_category("indexes"),
                _copy_whole_category("sectors"),
                _copy_whole_category("bonds-misc"),
                _copy_whole_category("commodities"),
            ],
            is_default=True,
        ),
        _seed_view_payload(
            name="Growth Leaders",
            slug="growth-leaders",
            description="Growth, high-beta, and leadership scan.",
            purpose="Growth / high-beta / leadership scan.",
            categories=[
                _copy_filtered_category("indexes", ["QQQ", "QQQE", "MTUM"]),
                _copy_filtered_category("sectors", ["SMH", "IGV", "XLK", "XLC", "ARKK"]),
                _copy_filtered_category(
                    "major-stocks",
                    [
                        "AAPL",
                        "AMZN",
                        "AMD",
                        "APP",
                        "AVGO",
                        "CRWD",
                        "GOOGL",
                        "IONQ",
                        "META",
                        "MSFT",
                        "MSTR",
                        "MU",
                        "NFLX",
                        "NVDA",
                        "PLTR",
                        "TSLA",
                        "TSM",
                        "VRT",
                    ],
                ),
            ],
        ),
        _seed_view_payload(
            name="Commodities",
            slug="commodities",
            description="Commodity, rates, dollar, and inflation-sensitive scan.",
            purpose="Commodity/rates/inflation-sensitive scan.",
            categories=[
                _copy_whole_category("commodities"),
                _copy_filtered_category("bonds-misc", ["$DXY", "TLT", "T10Y2Y:FRED"]),
                _copy_filtered_category("sectors", ["XLE", "OIH", "GDX"]),
            ],
        ),
        _seed_view_payload(
            name="Pullback Watch",
            slug="pullback-watch",
            description="Long-term bullish names where shorter-term momentum is weaker or cooling.",
            purpose="Research candidates with stronger long-term momentum and weaker short-term momentum.",
            categories=[
                _copy_filtered_category("indexes", ["SPY", "QQQ", "IWM", "RSP"]),
                _copy_filtered_category("sectors", ["XLK", "XLC", "XLE", "XLF", "XLV", "SMH", "IGV"]),
                _copy_filtered_category(
                    "major-stocks",
                    ["AAPL", "AMZN", "AMD", "AVGO", "GOOGL", "META", "MSFT", "NVDA", "PLTR", "TSLA", "V", "WMT"],
                ),
            ],
            filters=pullback_filters,
        ),
        _seed_view_payload(
            name="Custom Watchlist",
            slug="custom-watchlist",
            description="Blank/lightly seeded user-editable watchlist.",
            purpose="Easiest place to add and remove symbols.",
            categories=[_custom_watchlist_category()],
        ),
    ]


def seeded_momentum_heatmap_profile_payload(slug: str) -> dict[str, object] | None:
    normalized = slug.strip().lower()
    for payload in seeded_momentum_heatmap_profile_payloads():
        if payload.get("slug") == normalized:
            return payload
    return None
