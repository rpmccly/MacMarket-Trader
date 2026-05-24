"""Momentum Heatmap summaries, deltas, and report rendering.

This module is deliberately report/read-model oriented. It consumes heatmap
payloads produced by ``MomentumHeatmapService`` and never recomputes True
Momentum scores or changes recommendation / paper-order behavior.
"""

from __future__ import annotations

import csv
from io import StringIO
from statistics import mean
from typing import Any

SCORE_KEYS = ("long_term_score", "short_term_score", "strength_percent")
TIMEFRAME_KEYS = ("1W", "1D", "4H", "1H", "30M")
DEFAULT_SCORE_RANGES = (
    {"min": 75, "max": 100, "color": "#56f08a"},
    {"min": 25, "max": 74.999, "color": "#1f9f62"},
    {"min": -24.999, "max": 24.999, "color": "#7d5cff"},
    {"min": -74.999, "max": -25, "color": "#bd3d4b"},
    {"min": -100, "max": -75, "color": "#ff4b4b"},
)


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _score_cell_value(row: dict[str, Any], timeframe: str) -> float | None:
    scores = row.get("scores")
    if not isinstance(scores, dict):
        return None
    cell = scores.get(timeframe)
    if not isinstance(cell, dict) or cell.get("status") != "ok":
        return None
    return _num(cell.get("value"))


def _row_values(row: dict[str, Any]) -> list[float]:
    return [value for tf in TIMEFRAME_KEYS if (value := _score_cell_value(row, tf)) is not None]


def _all_cells(row: dict[str, Any]) -> list[dict[str, Any]]:
    scores = row.get("scores")
    if not isinstance(scores, dict):
        return []
    return [cell for cell in scores.values() if isinstance(cell, dict)]


def _row_availability(row: dict[str, Any]) -> str:
    cells = _all_cells(row)
    if not cells:
        return "not_refreshed"
    if all(cell.get("status") == "ok" for cell in cells):
        return "fresh"
    if any(cell.get("status") == "ok" for cell in cells):
        return "partial"
    if all(cell.get("status") == "unsupported" for cell in cells):
        return "unsupported"
    if any(cell.get("status") == "error" for cell in cells):
        return "failed"
    return "unavailable"


def _mostly_positive(values: list[float]) -> bool:
    return bool(values) and sum(1 for value in values if value > 0) >= max(1, len(values) - 1)


def _mostly_negative(values: list[float]) -> bool:
    return bool(values) and sum(1 for value in values if value < 0) >= max(1, len(values) - 1)


def row_tags(row: dict[str, Any], delta: dict[str, Any] | None = None) -> list[str]:
    availability = _row_availability(row)
    if availability == "unsupported":
        return ["Unsupported"]
    if availability in {"unavailable", "failed", "not_refreshed"}:
        return ["Stale" if row.get("stale") else "Mixed/chop"]
    if row.get("stale"):
        return ["Stale"]

    values = _row_values(row)
    strength = _num(row.get("strength_percent"))
    long_score = _num(row.get("long_term_score"))
    short_score = _num(row.get("short_term_score"))
    strength_delta = _num((delta or {}).get("strength_percent"))

    tags: list[str] = []
    if strength is not None and strength >= 75 and (long_score or 0) >= 25 and (short_score or 0) >= 25:
        tags.append("Trend leader")
    if long_score is not None and short_score is not None and long_score >= 25 and short_score < long_score - 15:
        tags.append("Pullback in uptrend")
    if short_score is not None and long_score is not None and short_score >= long_score + 20:
        tags.append("Short-term acceleration")
    if long_score is not None and short_score is not None and long_score < 0 and short_score >= long_score + 20:
        tags.append("Possible reversal")
    if _mostly_negative(values) and strength is not None and strength <= -25:
        tags.append("Bearish alignment")
    if not tags and _mostly_positive(values) and strength is not None and strength >= 25:
        tags.append("Trend leader")
    if strength_delta is not None and strength_delta >= 10 and "Short-term acceleration" not in tags:
        tags.append("Short-term acceleration")
    return tags or ["Mixed/chop"]


def category_summaries(payload: dict[str, Any], deltas: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for category in payload.get("categories") or []:
        if not isinstance(category, dict):
            continue
        rows = [row for row in category.get("rows") or [] if isinstance(row, dict)]
        strengths = [value for row in rows if (value := _num(row.get("strength_percent"))) is not None]
        longs = [value for row in rows if (value := _num(row.get("long_term_score"))) is not None]
        shorts = [value for row in rows if (value := _num(row.get("short_term_score"))) is not None]
        ok_count = sum(1 for row in rows if _row_availability(row) == "fresh")
        unsupported_count = sum(1 for row in rows if _row_availability(row) == "unsupported")
        unavailable_count = sum(1 for row in rows if _row_availability(row) in {"unavailable", "failed", "not_refreshed"})
        bullish_count = 0
        bearish_count = 0
        improving_count = 0
        weakening_count = 0
        for row in rows:
            values = _row_values(row)
            strength = _num(row.get("strength_percent"))
            if _mostly_positive(values) and strength is not None and strength > 25:
                bullish_count += 1
            if _mostly_negative(values) and strength is not None and strength < -25:
                bearish_count += 1
            row_delta = (deltas or {}).get(str(row.get("id")), {})
            strength_delta = _num(row_delta.get("strength_percent"))
            if strength_delta is not None and strength_delta > 0:
                improving_count += 1
            if strength_delta is not None and strength_delta < 0:
                weakening_count += 1
        if ok_count == len(rows) and rows:
            status = "fresh"
        elif ok_count > 0:
            status = "partial"
        elif unavailable_count > 0:
            status = "failed"
        else:
            status = "not_refreshed"
        summaries.append(
            {
                "categoryId": category.get("categoryId"),
                "categoryLabel": category.get("categoryLabel"),
                "average_strength_percent": round(mean(strengths), 2) if strengths else None,
                "average_long_term_score": round(mean(longs), 2) if longs else None,
                "average_short_term_score": round(mean(shorts), 2) if shorts else None,
                "count_ok": ok_count,
                "count_unsupported": unsupported_count,
                "count_unavailable_error": unavailable_count,
                "count_bullish_aligned": bullish_count,
                "count_bearish_aligned": bearish_count,
                "count_improving": improving_count,
                "count_weakening": weakening_count,
                "status": status,
            }
        )
    return summaries


def unsupported_summary(payload: dict[str, Any]) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    unsupported_symbols: list[str] = []
    unavailable_symbols: list[str] = []
    for category in payload.get("categories") or []:
        if not isinstance(category, dict):
            continue
        for row in category.get("rows") or []:
            if not isinstance(row, dict):
                continue
            availability = _row_availability(row)
            cells = _all_cells(row)
            reason = next((str(cell.get("reason")) for cell in cells if cell.get("reason")), None)
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
            label = str(row.get("displayName") or row.get("symbol") or row.get("providerSymbol") or "")
            if availability == "unsupported":
                unsupported_symbols.append(label)
            elif availability in {"unavailable", "failed"}:
                unavailable_symbols.append(label)
    return {
        "unsupported_count": len(unsupported_symbols),
        "unavailable_count": len(unavailable_symbols),
        "unsupported_symbols": unsupported_symbols,
        "unavailable_symbols": unavailable_symbols,
        "reasons": reasons,
    }


def _row_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for category in payload.get("categories") or []:
        if not isinstance(category, dict):
            continue
        for row in category.get("rows") or []:
            if isinstance(row, dict):
                indexed_row = dict(row)
                indexed_row.setdefault("categoryId", category.get("categoryId"))
                indexed_row.setdefault("categoryLabel", category.get("categoryLabel"))
                output[str(indexed_row.get("id"))] = indexed_row
    return output


def compute_deltas(current_payload: dict[str, Any], previous_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not previous_payload:
        return {}
    previous_rows = _row_index(previous_payload)
    previous_by_provider = {
        (
            str(row.get("providerSymbol") or row.get("symbol") or "").strip().upper(),
            str(row.get("categoryId") or row.get("categoryLabel") or "").strip().upper(),
        ): row
        for row in previous_rows.values()
        if str(row.get("providerSymbol") or row.get("symbol") or "").strip()
    }
    deltas: dict[str, dict[str, Any]] = {}
    for row_id, row in _row_index(current_payload).items():
        previous = previous_rows.get(row_id)
        if previous is None:
            previous = previous_by_provider.get(
                (
                    str(row.get("providerSymbol") or row.get("symbol") or "").strip().upper(),
                    str(row.get("categoryId") or row.get("categoryLabel") or "").strip().upper(),
                )
            )
        if previous is None:
            deltas[row_id] = {
                "strength_percent": None,
                "long_term_score": None,
                "short_term_score": None,
                "timeframes": {timeframe: None for timeframe in TIMEFRAME_KEYS},
                "new": True,
                "reason": "new_symbol_no_previous_snapshot_value",
            }
            continue
        row_delta: dict[str, Any] = {}
        for key in SCORE_KEYS:
            current_value = _num(row.get(key))
            previous_value = _num(previous.get(key))
            row_delta[key] = round(current_value - previous_value, 2) if current_value is not None and previous_value is not None else None
        timeframe_delta: dict[str, float | None] = {}
        for timeframe in TIMEFRAME_KEYS:
            current_value = _score_cell_value(row, timeframe)
            previous_value = _score_cell_value(previous, timeframe)
            timeframe_delta[timeframe] = round(current_value - previous_value, 2) if current_value is not None and previous_value is not None else None
        row_delta["timeframes"] = timeframe_delta
        row_delta["became_available"] = _row_availability(previous) != "fresh" and _row_availability(row) == "fresh"
        row_delta["became_unavailable"] = _row_availability(previous) == "fresh" and _row_availability(row) != "fresh"
        if row.get("stale") or any(cell.get("stale") for cell in _all_cells(row)):
            for key in SCORE_KEYS:
                row_delta[key] = None
            row_delta["timeframes"] = {timeframe: None for timeframe in TIMEFRAME_KEYS}
            row_delta["reason"] = "current_value_is_stale"
        deltas[row_id] = row_delta
    return deltas


def annotate_rows(payload: dict[str, Any], deltas: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    annotated = dict(payload)
    categories = []
    for category in payload.get("categories") or []:
        if not isinstance(category, dict):
            continue
        next_category = dict(category)
        next_rows = []
        for row in category.get("rows") or []:
            if not isinstance(row, dict):
                continue
            next_row = dict(row)
            row_id = str(next_row.get("id"))
            next_row["row_tags"] = row_tags(next_row, (deltas or {}).get(row_id))
            next_row["availability_status"] = _row_availability(next_row)
            next_rows.append(next_row)
        next_category["rows"] = next_rows
        categories.append(next_category)
    annotated["categories"] = categories
    return annotated


def build_report_payload(
    *,
    profile: dict[str, Any],
    snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None = None,
    stale: bool = False,
) -> dict[str, Any]:
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else snapshot
    previous_payload = None
    if previous_snapshot and isinstance(previous_snapshot.get("payload"), dict):
        previous_payload = previous_snapshot["payload"]
    deltas = compute_deltas(payload, previous_payload)
    annotated = annotate_rows(payload, deltas)
    summaries = category_summaries(annotated, deltas)
    unsupported = unsupported_summary(annotated)
    rows = [row for category in annotated.get("categories") or [] for row in (category.get("rows") or []) if isinstance(row, dict)]

    strongest = sorted(rows, key=lambda row: _num(row.get("strength_percent")) if _num(row.get("strength_percent")) is not None else -9999, reverse=True)[:10]
    weakest = sorted(rows, key=lambda row: _num(row.get("strength_percent")) if _num(row.get("strength_percent")) is not None else 9999)[:10]
    positive_movers = sorted(
        rows,
        key=lambda row: _num(deltas.get(str(row.get("id")), {}).get("strength_percent")) or -9999,
        reverse=True,
    )[:10]
    negative_movers = sorted(rows, key=lambda row: _num(deltas.get(str(row.get("id")), {}).get("strength_percent")) or 9999)[:10]
    bullish = [row for row in rows if "Trend leader" in row.get("row_tags", []) or "Short-term acceleration" in row.get("row_tags", [])]
    bearish = [row for row in rows if "Bearish alignment" in row.get("row_tags", [])]
    pullbacks = [row for row in rows if "Pullback in uptrend" in row.get("row_tags", [])]
    reversals = [row for row in rows if "Possible reversal" in row.get("row_tags", [])]

    return {
        "generated_at": snapshot.get("generated_at") or payload.get("generated_at"),
        "profile_id": profile.get("profile_uid") or profile.get("id"),
        "profile_name": profile.get("name") or "Momentum Heatmap",
        "color_ranges": profile.get("colorRanges") or profile.get("color_ranges") or [],
        "data_as_of_note": "Uses the selected heatmap snapshot; refresh to update current scores.",
        "stale_data_disclaimer": "This report uses a stale/last snapshot." if stale else None,
        "category_summaries": summaries,
        "top_strongest": strongest,
        "bottom_weakest": weakest,
        "positive_movers": positive_movers,
        "negative_movers": negative_movers,
        "bullish_alignment": bullish,
        "bearish_alignment": bearish,
        "pullback_candidates": pullbacks,
        "possible_reversal_candidates": reversals,
        "became_available": [row for row in rows if deltas.get(str(row.get("id")), {}).get("became_available")],
        "became_unavailable": [row for row in rows if deltas.get(str(row.get("id")), {}).get("became_unavailable")],
        "unsupported_summary": unsupported,
        "full_heatmap": annotated,
        "deltas": deltas,
        "notes": [
            "Intraday timeframe scores use latest completed regular-hours bars.",
            "Squeeze remains deferred until an approved squeeze algorithm/version is added.",
            "Momentum Heatmap labels are research context, not trade recommendations.",
        ],
        "email_status": "email_not_configured_for_heatmap_reports",
    }


def heatmap_csv(report_payload: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "category",
            "display_label",
            "provider_symbol",
            "long_term_score",
            "weekly",
            "daily",
            "short_term_score",
            "4hr",
            "1hr",
            "30m",
            "strength_percent",
            "delta_strength_percent",
            "delta_long_term_score",
            "delta_short_term_score",
            "squeeze_status",
            "row_tags",
            "statuses_reasons",
            "as_of_timestamps",
        ],
    )
    writer.writeheader()
    deltas = report_payload.get("deltas") if isinstance(report_payload.get("deltas"), dict) else {}
    for category in (report_payload.get("full_heatmap") or {}).get("categories") or []:
        if not isinstance(category, dict):
            continue
        for row in category.get("rows") or []:
            if not isinstance(row, dict):
                continue
            scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
            row_delta = deltas.get(str(row.get("id")), {}) if isinstance(deltas, dict) else {}
            reasons = []
            as_of = []
            for timeframe in TIMEFRAME_KEYS:
                cell = scores.get(timeframe) if isinstance(scores, dict) else None
                if isinstance(cell, dict):
                    if cell.get("status") != "ok" or cell.get("reason"):
                        reasons.append(f"{timeframe}:{cell.get('status')}:{cell.get('reason') or ''}")
                    if cell.get("as_of"):
                        as_of.append(f"{timeframe}:{cell.get('as_of')}")
            writer.writerow(
                {
                    "category": category.get("categoryLabel"),
                    "display_label": row.get("displayName"),
                    "provider_symbol": row.get("providerSymbol"),
                    "long_term_score": row.get("long_term_score"),
                    "weekly": _score_cell_value(row, "1W"),
                    "daily": _score_cell_value(row, "1D"),
                    "short_term_score": row.get("short_term_score"),
                    "4hr": _score_cell_value(row, "4H"),
                    "1hr": _score_cell_value(row, "1H"),
                    "30m": _score_cell_value(row, "30M"),
                    "strength_percent": row.get("strength_percent"),
                    "delta_strength_percent": row_delta.get("strength_percent") if isinstance(row_delta, dict) else None,
                    "delta_long_term_score": row_delta.get("long_term_score") if isinstance(row_delta, dict) else None,
                    "delta_short_term_score": row_delta.get("short_term_score") if isinstance(row_delta, dict) else None,
                    "squeeze_status": (row.get("squeeze") or {}).get("status") if isinstance(row.get("squeeze"), dict) else None,
                    "row_tags": "; ".join(str(tag) for tag in row.get("row_tags") or []),
                    "statuses_reasons": "; ".join(reasons),
                    "as_of_timestamps": "; ".join(as_of),
                }
            )
    return output.getvalue()


def heatmap_html(report_payload: dict[str, Any]) -> str:
    def esc(value: object) -> str:
        return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def fmt(value: object, suffix: str = "") -> str:
        number = _num(value)
        if number is None:
            return "--"
        return f"{number:.1f}{suffix}" if number % 1 else f"{number:.0f}{suffix}"

    def score_color(value: object) -> tuple[str, str]:
        number = _num(value)
        if number is None:
            return "#10151d", "#9fb0c3"
        raw_ranges = report_payload.get("color_ranges")
        ranges = raw_ranges if isinstance(raw_ranges, list) and raw_ranges else DEFAULT_SCORE_RANGES
        for item in ranges:
            if not isinstance(item, dict):
                continue
            min_value = _num(item.get("min"))
            max_value = _num(item.get("max"))
            color = str(item.get("color") or "").strip()
            if min_value is not None and max_value is not None and color and min_value <= number <= max_value:
                return color, "#06150b" if color.lower() in {"#56f08a", "#1f9f62"} else "#ffffff"
        return "#10151d", "#d7dee8"

    def score_cell(value: object, suffix: str = "") -> str:
        bg, fg = score_color(value)
        return (
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;text-align:right;'
            f'font-weight:700;background:{bg};color:{fg};">{esc(fmt(value, suffix))}</td>'
        )

    def delta_badge(row: dict[str, Any], key: str) -> str:
        deltas = report_payload.get("deltas") if isinstance(report_payload.get("deltas"), dict) else {}
        delta = deltas.get(str(row.get("id")), {}) if isinstance(deltas, dict) else {}
        value = _num(delta.get(key)) if isinstance(delta, dict) else None
        if value is None:
            label = "new" if isinstance(delta, dict) and delta.get("new") else "--"
            return f'<span style="color:#9fb0c3;font-size:11px;">{esc(label)}</span>'
        color = "#56f08a" if value > 0 else "#ff8b8b" if value < 0 else "#9fb0c3"
        prefix = "+" if value > 0 else ""
        return f'<span style="color:{color};font-size:11px;font-weight:700;">{prefix}{value:.1f}</span>'

    def rows_for(name: str) -> list[dict[str, Any]]:
        rows = report_payload.get(name)
        return [row for row in rows or [] if isinstance(row, dict)]

    def compact_rows(name: str, title: str) -> str:
        rows = rows_for(name)
        body = "".join(
            "<tr>"
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{esc(row.get("displayName"))}</td>'
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;color:#9fb0c3;">{esc(row.get("providerSymbol"))}</td>'
            f'{score_cell(row.get("strength_percent"), "%")}'
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{delta_badge(row, "strength_percent")}</td>'
            "</tr>"
            for row in rows[:10]
        )
        if not body:
            body = '<tr><td colspan="4" style="padding:8px;color:#9fb0c3;border-top:1px solid #25303b;">No matching rows in this snapshot.</td></tr>'
        return (
            '<td style="vertical-align:top;padding:0 8px 12px 0;width:50%;">'
            f'<h3 style="margin:0 0 8px;font-size:15px;color:#d7dee8;">{esc(title)}</h3>'
            '<table role="presentation" style="width:100%;border-collapse:collapse;font-size:12px;">'
            '<thead><tr><th align="left" style="color:#9fb0c3;padding:4px 8px;">Symbol</th>'
            '<th align="left" style="color:#9fb0c3;padding:4px 8px;">Provider</th>'
            '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Strength</th>'
            '<th align="left" style="color:#9fb0c3;padding:4px 8px;">Delta</th></tr></thead>'
            f"<tbody>{body}</tbody></table></td>"
        )

    summary_rows = []
    for summary in report_payload.get("category_summaries") or []:
        if not isinstance(summary, dict):
            continue
        bg, fg = score_color(summary.get("average_strength_percent"))
        summary_rows.append(
            "<tr>"
            f'<td style="padding:7px 8px;border-top:1px solid #25303b;font-weight:700;">{esc(summary.get("categoryLabel"))}</td>'
            f'<td style="padding:7px 8px;border-top:1px solid #25303b;background:{bg};color:{fg};font-weight:700;text-align:right;">{esc(fmt(summary.get("average_strength_percent"), "%"))}</td>'
            f'<td style="padding:7px 8px;border-top:1px solid #25303b;text-align:right;">{esc(fmt(summary.get("average_long_term_score")))}</td>'
            f'<td style="padding:7px 8px;border-top:1px solid #25303b;text-align:right;">{esc(fmt(summary.get("average_short_term_score")))}</td>'
            f'<td style="padding:7px 8px;border-top:1px solid #25303b;text-align:right;">{esc(summary.get("count_ok"))}</td>'
            f'<td style="padding:7px 8px;border-top:1px solid #25303b;text-align:right;color:#9fb0c3;">{esc(summary.get("count_unsupported"))}</td>'
            "</tr>"
        )

    rows = []
    for category in (report_payload.get("full_heatmap") or {}).get("categories") or []:
        if not isinstance(category, dict):
            continue
        for row in category.get("rows") or []:
            if not isinstance(row, dict):
                continue
            availability = str(row.get("availability_status") or "")
            muted = availability in {"unsupported", "unavailable", "failed", "not_refreshed"}
            text_color = "#74859a" if muted else "#d7dee8"
            scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
            squeeze = row.get("squeeze") if isinstance(row.get("squeeze"), dict) else {}
            rows.append(
                f'<tr style="color:{text_color};">'
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{esc(category.get("categoryLabel"))}</td>'
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;font-weight:700;">{esc(row.get("displayName"))}'
                f'<div style="color:#9fb0c3;font-size:11px;">{esc(row.get("providerSymbol"))}</div></td>'
                f'{score_cell(row.get("long_term_score"))}'
                f'{score_cell((scores.get("1W") or {}).get("value") if isinstance(scores.get("1W"), dict) else None)}'
                f'{score_cell((scores.get("1D") or {}).get("value") if isinstance(scores.get("1D"), dict) else None)}'
                f'{score_cell(row.get("short_term_score"))}'
                f'{score_cell((scores.get("4H") or {}).get("value") if isinstance(scores.get("4H"), dict) else None)}'
                f'{score_cell((scores.get("1H") or {}).get("value") if isinstance(scores.get("1H"), dict) else None)}'
                f'{score_cell((scores.get("30M") or {}).get("value") if isinstance(scores.get("30M"), dict) else None)}'
                f'{score_cell(row.get("strength_percent"), "%")}'
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{delta_badge(row, "strength_percent")}</td>'
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{esc("; ".join(str(tag) for tag in row.get("row_tags") or []))}</td>'
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;color:#9fb0c3;">{esc(squeeze.get("status") or "deferred")}</td>'
                "</tr>"
            )
    unsupported = report_payload.get("unsupported_summary") if isinstance(report_payload.get("unsupported_summary"), dict) else {}
    full_body = "".join(rows) or '<tr><td colspan="14" style="padding:10px;color:#9fb0c3;">No heatmap rows in this snapshot.</td></tr>'
    return (
        '<!doctype html><html><head><meta charset="utf-8"><title>MacMarket Momentum Heatmap</title></head>'
        '<body style="margin:0;background:#10151d;color:#d7dee8;font-family:Arial,Helvetica,sans-serif;">'
        '<div class="mh-report" style="max-width:1180px;margin:0 auto;padding:24px;">'
        '<div style="border:1px solid #2a3440;background:#0f1722;padding:20px;border-radius:10px;">'
        '<div style="color:#56f08a;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;">MacMarket Research Dashboard</div>'
        f'<h1 style="margin:6px 0 4px;font-size:28px;color:#ffffff;">{esc(report_payload.get("profile_name"))}</h1>'
        f'<p style="margin:0;color:#9fb0c3;">Generated: {esc(report_payload.get("generated_at"))} | {esc(report_payload.get("data_as_of_note"))}</p>'
        f'{"<p style=\"margin:10px 0 0;color:#f7b267;font-weight:700;\">" + esc(report_payload.get("stale_data_disclaimer")) + "</p>" if report_payload.get("stale_data_disclaimer") else ""}'
        '</div>'
        '<div style="margin-top:16px;border:1px solid #2a3440;background:#0f1722;padding:14px;border-radius:10px;">'
        '<h2 style="margin:0 0 10px;font-size:18px;color:#ffffff;">Category Regime Summary</h2>'
        '<table role="presentation" style="width:100%;border-collapse:collapse;font-size:13px;">'
        '<thead><tr><th align="left" style="color:#9fb0c3;padding:4px 8px;">Category</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Avg Strength</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Avg Long</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Avg Short</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">OK</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Unsupported</th></tr></thead>'
        f'<tbody>{"".join(summary_rows)}</tbody></table></div>'
        '<table role="presentation" style="width:100%;border-collapse:collapse;margin-top:16px;"><tr>'
        f'{compact_rows("top_strongest", "Top 10 strongest rows")}'
        f'{compact_rows("bottom_weakest", "Bottom 10 weakest rows")}'
        '</tr><tr>'
        f'{compact_rows("positive_movers", "Biggest positive Strength % movers")}'
        f'{compact_rows("negative_movers", "Biggest negative Strength % movers")}'
        '</tr><tr>'
        f'{compact_rows("bullish_alignment", "Bullish alignment rows")}'
        f'{compact_rows("bearish_alignment", "Bearish alignment rows")}'
        '</tr><tr>'
        f'{compact_rows("pullback_candidates", "Long-term bullish plus short-term weak")}'
        f'{compact_rows("possible_reversal_candidates", "Long-term weak plus short-term improving")}'
        '</tr></table>'
        '<div style="margin-top:16px;border:1px solid #2a3440;background:#0f1722;padding:14px;border-radius:10px;">'
        '<h2 style="margin:0 0 8px;font-size:18px;color:#ffffff;">Unsupported / Unavailable Summary</h2>'
        f'<p style="margin:0;color:#9fb0c3;">Unsupported: {esc(unsupported.get("unsupported_count"))} | Unavailable: {esc(unsupported.get("unavailable_count"))}</p>'
        '</div>'
        '<div style="margin-top:16px;border:1px solid #2a3440;background:#0f1722;padding:14px;border-radius:10px;">'
        '<h2 style="margin:0 0 10px;font-size:18px;color:#ffffff;">Full Heatmap Table</h2>'
        '<table role="presentation" style="width:100%;border-collapse:collapse;font-size:12px;">'
        '<thead><tr><th align="left" style="color:#9fb0c3;padding:4px 8px;">Category</th>'
        '<th align="left" style="color:#9fb0c3;padding:4px 8px;">Symbol / label</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Long</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Weekly</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Daily</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Short</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">4HR</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">1HR</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">30M</th>'
        '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Strength</th>'
        '<th align="left" style="color:#9fb0c3;padding:4px 8px;">Delta</th>'
        '<th align="left" style="color:#9fb0c3;padding:4px 8px;">Tags</th>'
        '<th align="left" style="color:#9fb0c3;padding:4px 8px;">Squeeze</th></tr></thead>'
        f"<tbody>{full_body}</tbody></table></div>"
        '<div style="margin-top:16px;color:#9fb0c3;font-size:12px;line-height:1.5;">'
        '<p style="margin:0 0 4px;color:#d7dee8;font-weight:700;">Research dashboard only. Not trade execution or investment advice.</p>'
        '<p style="margin:0 0 4px;">Intraday scores use latest available completed bars.</p>'
        '<p style="margin:0;">Squeeze remains deferred until an approved squeeze algorithm/version is added.</p>'
        '</div></div></body></html>'
    )


def heatmap_text(report_payload: dict[str, Any]) -> str:
    generated = report_payload.get("generated_at")
    profile = report_payload.get("profile_name") or "Momentum Heatmap"
    rows = report_payload.get("top_strongest") or []
    strongest_lines = []
    for row in rows[:5]:
        if isinstance(row, dict):
            strongest_lines.append(f"- {row.get('displayName')}: {row.get('strength_percent')}")
    return "\n".join(
        [
            f"MacMarket Momentum Heatmap - {profile}",
            f"Generated: {generated}",
            "Research dashboard only. Not trade execution or investment advice.",
            "Intraday scores use latest available completed bars.",
            "",
            "Top strongest rows by Strength %:",
            *(strongest_lines or ["- No rows available."]),
            "",
            "Squeeze remains deferred until an approved squeeze algorithm/version is added.",
        ]
    )
