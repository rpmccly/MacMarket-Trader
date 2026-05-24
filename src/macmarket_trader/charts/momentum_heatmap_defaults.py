"""Server-side defaults for the Momentum Heatmap workbook view.

These defaults mirror the workbook-derived frontend seed. They are used only
to create user-scoped heatmap profiles and report preferences; they do not
change Momentum Intelligence scoring, recommendation approval, or paper-order
behavior.
"""

from __future__ import annotations

from typing import Any

from macmarket_trader.charts.momentum_heatmap_service import MomentumHeatmapService

DEFAULT_MOMENTUM_HEATMAP_PROFILE_NAME = "Default Momentum Heatmap"
DEFAULT_MOMENTUM_HEATMAP_STALE_THRESHOLD_HOURS = 24

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


def default_momentum_heatmap_view_settings() -> dict[str, object]:
    return {
        "sort": "workbook",
        "filters": {
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
    }


def default_momentum_heatmap_report_preferences() -> dict[str, object]:
    return {
        "includedProfileMode": "current_profile",
        "includeFullTable": True,
        "includeCsvAttachment": True,
        "reportMode": "latest_snapshot",
        "notes": [
            "Intraday timeframe scores use latest completed regular-hours bars.",
            "Squeeze remains deferred until an approved squeeze algorithm/version is added.",
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
