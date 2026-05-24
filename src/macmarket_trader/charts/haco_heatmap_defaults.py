"""Server-side defaults for the HACO Direction Heatmap.

The HACO heatmap reuses the Momentum Heatmap workbook universes and saved-view
names, but stores profile and snapshot history separately. These defaults do
not change HACO/HACOLT algorithms, recommendation approval, or paper-order
behavior.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from macmarket_trader.charts.momentum_heatmap_defaults import seeded_momentum_heatmap_profile_payload, seeded_momentum_heatmap_profile_payloads

DEFAULT_HACO_HEATMAP_PROFILE_NAME = "Morning Macro"
HACO_HEATMAP_SEEDED_VIEW_NAMES = (
    "Morning Macro",
    "Growth Leaders",
    "Commodities",
    "Pullback Watch",
    "Custom Watchlist",
)
HACO_HEATMAP_SEEDED_VIEW_SLUGS = (
    "morning-macro",
    "growth-leaders",
    "commodities",
    "pullback-watch",
    "custom-watchlist",
)


def default_haco_heatmap_view_settings(
    *,
    slug: str = "morning-macro",
    description: str = "Broad morning HACO direction read.",
    purpose: str = "Broad morning market regime read.",
    filters: dict[str, object] | None = None,
    is_system_seeded: bool = True,
) -> dict[str, object]:
    return {
        "sort": "workbook",
        "filters": filters or {
            "search": "",
            "showLongOnly": False,
            "showShortOnly": False,
            "showMixed": True,
            "hideUnsupported": False,
            "alignmentMin": None,
            "alignmentMax": None,
            "changedOnly": False,
        },
        "showChanges": True,
        "staleThresholdHours": 24,
        "slug": slug,
        "viewType": "system_seeded" if is_system_seeded else "custom",
        "description": description,
        "purpose": purpose,
        "isSystemSeeded": is_system_seeded,
    }


def default_haco_heatmap_report_preferences() -> dict[str, object]:
    return {
        "includedProfileMode": "current_profile",
        "includeFullTable": True,
        "reportMode": "latest_snapshot",
        "notes": [
            "HACO Direction Heatmap labels are research direction context, not trade recommendations.",
            "Intraday timeframe states use latest completed regular-hours bars when provider metadata supports it.",
        ],
    }


def _adapt_payload(payload: dict[str, object]) -> dict[str, object]:
    adapted = deepcopy(payload)
    slug = str(adapted.get("slug") or "morning-macro")
    description = str(adapted.get("description") or DEFAULT_HACO_HEATMAP_PROFILE_NAME)
    purpose = str(adapted.get("purpose") or description)
    filters = None
    if slug == "pullback-watch":
        filters = {
            "search": "",
            "showLongOnly": False,
            "showShortOnly": False,
            "showMixed": True,
            "hideUnsupported": True,
            "alignmentMin": 25,
            "alignmentMax": None,
            "changedOnly": False,
        }
    adapted["view_settings"] = default_haco_heatmap_view_settings(
        slug=slug,
        description=description,
        purpose=purpose,
        filters=filters,
        is_system_seeded=True,
    )
    adapted["report_preferences"] = default_haco_heatmap_report_preferences()
    adapted.pop("color_ranges", None)
    return adapted


def seeded_haco_heatmap_profile_payloads() -> list[dict[str, object]]:
    return [_adapt_payload(payload) for payload in seeded_momentum_heatmap_profile_payloads()]


def seeded_haco_heatmap_profile_payload(slug: str) -> dict[str, object] | None:
    source = seeded_momentum_heatmap_profile_payload(slug)
    if source is None:
        return None
    return _adapt_payload(source)
