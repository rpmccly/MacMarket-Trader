"""HACO Direction Heatmap summaries, changes, and report rendering."""

from __future__ import annotations

import csv
from io import StringIO
from statistics import mean
from typing import Any

TIMEFRAME_KEYS = ("1W", "1D", "4H", "1H", "30M")


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _row_availability(row: dict[str, Any]) -> str:
    states = row.get("states")
    if not isinstance(states, dict) or not states:
        return "not_refreshed"
    cells = [cell for cell in states.values() if isinstance(cell, dict)]
    if cells and all(cell.get("status") == "ok" for cell in cells):
        return "fresh"
    if any(cell.get("status") == "ok" for cell in cells):
        return "partial"
    if cells and all(cell.get("status") == "unsupported" for cell in cells):
        return "unsupported"
    if any(cell.get("status") == "error" for cell in cells):
        return "failed"
    return "unavailable"


def _state_label(row: dict[str, Any], timeframe: str) -> str | None:
    states = row.get("states")
    if not isinstance(states, dict):
        return None
    cell = states.get(timeframe)
    if not isinstance(cell, dict) or cell.get("status") != "ok":
        return None
    label = str(cell.get("label") or "").strip().upper()
    return label if label in {"LONG", "SHORT"} else None


def _row_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for category in payload.get("categories") or []:
        if not isinstance(category, dict):
            continue
        for row in category.get("rows") or []:
            if isinstance(row, dict):
                indexed = dict(row)
                indexed.setdefault("categoryId", category.get("categoryId"))
                indexed.setdefault("categoryLabel", category.get("categoryLabel"))
                output[str(indexed.get("id"))] = indexed
    return output


def compute_changes(current_payload: dict[str, Any], previous_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not previous_payload:
        return {}
    previous_rows = _row_index(previous_payload)
    previous_by_provider = {
        (
            str(row.get("providerSymbol") or row.get("symbol") or "").strip().upper(),
            str(row.get("categoryId") or row.get("categoryLabel") or "").strip().upper(),
        ): row
        for row in previous_rows.values()
    }
    changes: dict[str, dict[str, Any]] = {}
    for row_id, row in _row_index(current_payload).items():
        previous = previous_rows.get(row_id) or previous_by_provider.get(
            (
                str(row.get("providerSymbol") or row.get("symbol") or "").strip().upper(),
                str(row.get("categoryId") or row.get("categoryLabel") or "").strip().upper(),
            )
        )
        if previous is None:
            changes[row_id] = {"changed_since_last": True, "new": True, "reason": "new_symbol_no_previous_snapshot_value"}
            continue
        current_bias = row.get("overall_bias")
        previous_bias = previous.get("overall_bias")
        current_alignment = _num(row.get("overall_alignment_percent"))
        previous_alignment = _num(previous.get("overall_alignment_percent"))
        timeframe_flips: dict[str, dict[str, str]] = {}
        for timeframe in TIMEFRAME_KEYS:
            current_state = _state_label(row, timeframe)
            previous_state = _state_label(previous, timeframe)
            if current_state and previous_state and current_state != previous_state:
                timeframe_flips[timeframe] = {"from": previous_state, "to": current_state}
        alignment_delta = (
            round(current_alignment - previous_alignment, 2)
            if current_alignment is not None and previous_alignment is not None
            else None
        )
        changed = bool(current_bias != previous_bias or timeframe_flips or (alignment_delta is not None and alignment_delta != 0))
        changes[row_id] = {
            "changed_since_last": changed,
            "prior_overall_bias": previous_bias,
            "current_overall_bias": current_bias,
            "alignment_delta": alignment_delta,
            "timeframe_flips": timeframe_flips,
        }
    return changes


def row_tags(row: dict[str, Any], change: dict[str, Any] | None = None) -> list[str]:
    tags = list(row.get("tags") or [])
    if _row_availability(row) == "unsupported" and "Unsupported" not in tags:
        tags.append("Unsupported")
    if change and change.get("prior_overall_bias") in {"SHORT", "MIXED", None} and row.get("overall_bias") == "LONG":
        tags.append("Fresh LONG Flip")
    if change and change.get("prior_overall_bias") in {"LONG", "MIXED", None} and row.get("overall_bias") == "SHORT":
        tags.append("Fresh SHORT Flip")
    return tags or ["Mixed / Chop"]


def annotate_rows(payload: dict[str, Any], changes: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
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
            change = (changes or {}).get(row_id, {})
            next_row["tags"] = row_tags(next_row, change)
            next_row["availability_status"] = _row_availability(next_row)
            next_row["changed_since_last"] = bool(change.get("changed_since_last")) if changes else None
            next_row["prior_overall_bias"] = change.get("prior_overall_bias") if isinstance(change, dict) else None
            next_row["alignment_delta"] = change.get("alignment_delta") if isinstance(change, dict) else None
            next_rows.append(next_row)
        next_category["rows"] = next_rows
        categories.append(next_category)
    annotated["categories"] = categories
    return annotated


def category_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for category in payload.get("categories") or []:
        if not isinstance(category, dict):
            continue
        rows = [row for row in category.get("rows") or [] if isinstance(row, dict)]
        alignments = [value for row in rows if (value := _num(row.get("overall_alignment_percent"))) is not None]
        long_count = sum(1 for row in rows if row.get("overall_bias") == "LONG")
        short_count = sum(1 for row in rows if row.get("overall_bias") == "SHORT")
        mixed_count = sum(1 for row in rows if row.get("overall_bias") == "MIXED")
        unsupported_count = sum(1 for row in rows if _row_availability(row) == "unsupported")
        unavailable_count = sum(1 for row in rows if _row_availability(row) in {"unavailable", "failed", "not_refreshed"})
        changed_count = sum(1 for row in rows if row.get("changed_since_last") is True)
        ok_count = sum(1 for row in rows if _row_availability(row) == "fresh")
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
                "average_alignment_percent": round(mean(alignments), 2) if alignments else None,
                "count_long": long_count,
                "count_short": short_count,
                "count_mixed": mixed_count,
                "count_unsupported": unsupported_count,
                "count_unavailable_error": unavailable_count,
                "long_count": long_count,
                "short_count": short_count,
                "mixed_count": mixed_count,
                "unsupported_count": unsupported_count,
                "unavailable_count": unavailable_count,
                "changed_count": changed_count,
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
            states = row.get("states") if isinstance(row.get("states"), dict) else {}
            reason = next((str(cell.get("reason")) for cell in states.values() if isinstance(cell, dict) and cell.get("reason")), None)
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
            label = str(row.get("displayName") or row.get("symbol") or row.get("providerSymbol") or "")
            availability = _row_availability(row)
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


def build_report_payload(
    *,
    profile: dict[str, Any],
    snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else snapshot
    previous_payload = previous_snapshot.get("payload") if previous_snapshot and isinstance(previous_snapshot.get("payload"), dict) else None
    changes = compute_changes(payload, previous_payload)
    annotated = annotate_rows(payload, changes)
    summaries = category_summaries(annotated)
    unsupported = unsupported_summary(annotated)
    rows = [row for category in annotated.get("categories") or [] for row in (category.get("rows") or []) if isinstance(row, dict)]

    all_long = [row for row in rows if "All LONG" in row.get("tags", [])]
    all_short = [row for row in rows if "All SHORT" in row.get("tags", [])]
    fresh_long = [row for row in rows if "Fresh LONG Flip" in row.get("tags", [])]
    fresh_short = [row for row in rows if "Fresh SHORT Flip" in row.get("tags", [])]
    pullbacks = [row for row in rows if "Daily LONG / Short-Term Pullback" in row.get("tags", [])]
    bounces = [row for row in rows if "Daily SHORT / Short-Term Bounce" in row.get("tags", [])]
    mixed = [row for row in rows if "Mixed / Chop" in row.get("tags", [])]

    return {
        "generated_at": snapshot.get("generated_at") or payload.get("generated_at"),
        "profile_id": profile.get("profile_uid") or profile.get("id"),
        "profile_name": profile.get("name") or "HACO Direction Heatmap",
        "data_as_of_note": "Uses the selected HACO heatmap snapshot; refresh to update current states.",
        "category_summaries": summaries,
        "all_long": all_long,
        "all_short": all_short,
        "fresh_long_flips": fresh_long,
        "fresh_short_flips": fresh_short,
        "daily_long_pullbacks": pullbacks,
        "daily_short_bounces": bounces,
        "mixed_chop": mixed,
        "unsupported_summary": unsupported,
        "full_heatmap": annotated,
        "changes": changes,
        "notes": [
            "Research dashboard only. Not trade execution or investment advice.",
            "HACO states use LONG/SHORT labels as directional research context.",
            "Intraday timeframe states use latest available completed regular-hours bars when provider metadata supports it.",
        ],
        "email_status": "email_not_configured_for_haco_heatmap_reports",
    }


def haco_heatmap_csv(report_payload: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "category",
            "display_label",
            "provider_symbol",
            "overall_bias",
            "overall_alignment_percent",
            "daily_context",
            "short_term_bias",
            "short_term_alignment_percent",
            "1w",
            "1d",
            "4h",
            "1h",
            "30m",
            "tags",
            "changed_since_last",
            "prior_bias",
            "status_reasons",
            "as_of_timestamps",
        ],
    )
    writer.writeheader()
    for category in (report_payload.get("full_heatmap") or {}).get("categories") or []:
        if not isinstance(category, dict):
            continue
        for row in category.get("rows") or []:
            if not isinstance(row, dict):
                continue
            states = row.get("states") if isinstance(row.get("states"), dict) else {}
            reasons = []
            as_of = []
            for timeframe in TIMEFRAME_KEYS:
                cell = states.get(timeframe) if isinstance(states, dict) else None
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
                    "overall_bias": row.get("overall_bias"),
                    "overall_alignment_percent": row.get("overall_alignment_percent"),
                    "daily_context": row.get("daily_context"),
                    "short_term_bias": row.get("short_term_bias"),
                    "short_term_alignment_percent": row.get("short_term_alignment_percent"),
                    "1w": _state_label(row, "1W"),
                    "1d": _state_label(row, "1D"),
                    "4h": _state_label(row, "4H"),
                    "1h": _state_label(row, "1H"),
                    "30m": _state_label(row, "30M"),
                    "tags": "; ".join(str(tag) for tag in row.get("tags") or []),
                    "changed_since_last": row.get("changed_since_last"),
                    "prior_bias": row.get("prior_overall_bias"),
                    "status_reasons": "; ".join(reasons),
                    "as_of_timestamps": "; ".join(as_of),
                }
            )
    return output.getvalue()


def haco_heatmap_html(report_payload: dict[str, Any]) -> str:
    def esc(value: object) -> str:
        return (
            str(value or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def fmt(value: object, suffix: str = "") -> str:
        number = _num(value)
        if number is None:
            return "--"
        return f"{number:.1f}{suffix}" if number % 1 else f"{number:.0f}{suffix}"

    def badge(label: object) -> str:
        text = str(label or "—")
        colors = {
            "LONG": ("#1f9f62", "#06150b"),
            "SHORT": ("#bd3d4b", "#ffffff"),
            "MIXED": ("#7d5cff", "#ffffff"),
        }
        bg, fg = colors.get(text, ("#17202b", "#9fb0c3"))
        return f'<span style="display:inline-block;border-radius:999px;padding:3px 7px;background:{bg};color:{fg};font-weight:700;font-size:11px;">{esc(text)}</span>'

    def compact_rows(name: str, title: str) -> str:
        rows = [row for row in report_payload.get(name) or [] if isinstance(row, dict)]
        body = "".join(
            "<tr>"
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{esc(row.get("displayName"))}</td>'
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{badge(row.get("overall_bias"))}</td>'
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;text-align:right;">{esc(fmt(row.get("overall_alignment_percent"), "%"))}</td>'
            "</tr>"
            for row in rows[:10]
        )
        if not body:
            body = '<tr><td colspan="3" style="padding:8px;color:#9fb0c3;border-top:1px solid #25303b;">No matching rows in this snapshot.</td></tr>'
        return (
            f'<h3 style="margin:18px 0 8px;font-size:15px;color:#d7dee8;">{esc(title)}</h3>'
            '<table role="presentation" style="width:100%;border-collapse:collapse;font-size:12px;">'
            '<thead><tr><th align="left" style="color:#9fb0c3;padding:4px 8px;">Symbol</th>'
            '<th align="left" style="color:#9fb0c3;padding:4px 8px;">Bias</th>'
            '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Alignment</th></tr></thead>'
            f"<tbody>{body}</tbody></table>"
        )

    summary_rows = "".join(
        "<tr>"
        f'<td style="padding:7px 8px;border-top:1px solid #25303b;">{esc(item.get("categoryLabel"))}</td>'
        f'<td style="padding:7px 8px;border-top:1px solid #25303b;text-align:right;">{esc(fmt(item.get("average_alignment_percent"), "%"))}</td>'
        f'<td style="padding:7px 8px;border-top:1px solid #25303b;text-align:right;color:#56f08a;">{esc(item.get("count_long", item.get("long_count")))}</td>'
        f'<td style="padding:7px 8px;border-top:1px solid #25303b;text-align:right;color:#ff8b8b;">{esc(item.get("count_short", item.get("short_count")))}</td>'
        f'<td style="padding:7px 8px;border-top:1px solid #25303b;text-align:right;">{esc(item.get("count_mixed", item.get("mixed_count")))}</td>'
        "</tr>"
        for item in report_payload.get("category_summaries") or []
        if isinstance(item, dict)
    )
    full_rows = []
    for category in (report_payload.get("full_heatmap") or {}).get("categories") or []:
        if not isinstance(category, dict):
            continue
        for row in category.get("rows") or []:
            if not isinstance(row, dict):
                continue
            full_rows.append(
                "<tr>"
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;color:#9fb0c3;">{esc(category.get("categoryLabel"))}</td>'
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{esc(row.get("displayName"))}</td>'
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{badge(row.get("overall_bias"))}</td>'
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;text-align:right;">{esc(fmt(row.get("overall_alignment_percent"), "%"))}</td>'
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{badge(row.get("daily_context"))}</td>'
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{badge(row.get("short_term_bias"))}</td>'
                f'<td style="padding:6px 8px;border-top:1px solid #25303b;color:#9fb0c3;">{esc("; ".join(str(tag) for tag in row.get("tags") or []))}</td>'
                "</tr>"
            )

    return f"""
<div style="margin:0;background:#0b0f14;color:#d7dee8;font-family:Inter,Segoe UI,Arial,sans-serif;">
  <div style="padding:26px 30px;background:#111821;border-bottom:1px solid #25303b;">
    <div style="font-size:12px;color:#9fb0c3;letter-spacing:.08em;text-transform:uppercase;">MacMarket Research Dashboard</div>
    <h1 style="margin:8px 0 4px;font-size:28px;line-height:1.15;">HACO Direction Heatmap</h1>
    <div style="font-size:13px;color:#9fb0c3;">Profile: {esc(report_payload.get("profile_name"))} - Generated: {esc(report_payload.get("generated_at"))}</div>
  </div>
  <div style="padding:20px 30px;">
    <p style="margin:0 0 16px;color:#9fb0c3;">Research dashboard only. Not trade execution or investment advice. HACO LONG/SHORT states are directional research context.</p>
    <h2 style="font-size:18px;margin:0 0 10px;">Category Direction Summary</h2>
    <table role="presentation" style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:18px;">
      <thead><tr><th align="left" style="color:#9fb0c3;padding:4px 8px;">Category</th><th align="right" style="color:#9fb0c3;padding:4px 8px;">Avg Alignment</th><th align="right" style="color:#9fb0c3;padding:4px 8px;">LONG</th><th align="right" style="color:#9fb0c3;padding:4px 8px;">SHORT</th><th align="right" style="color:#9fb0c3;padding:4px 8px;">Mixed</th></tr></thead>
      <tbody>{summary_rows or '<tr><td colspan="5" style="padding:8px;color:#9fb0c3;">No category summaries available.</td></tr>'}</tbody>
    </table>
    {compact_rows("all_long", "All LONG Alignment Rows")}
    {compact_rows("all_short", "All SHORT Alignment Rows")}
    {compact_rows("fresh_long_flips", "Fresh LONG Flips")}
    {compact_rows("fresh_short_flips", "Fresh SHORT Flips")}
    {compact_rows("daily_long_pullbacks", "Daily LONG / Short-Term Pullback Rows")}
    {compact_rows("daily_short_bounces", "Daily SHORT / Short-Term Bounce Rows")}
    {compact_rows("mixed_chop", "Mixed / Chop Rows")}
    <h2 style="font-size:18px;margin:20px 0 10px;">Full HACO Direction Table</h2>
    <table role="presentation" style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead><tr><th align="left" style="color:#9fb0c3;padding:4px 8px;">Category</th><th align="left" style="color:#9fb0c3;padding:4px 8px;">Symbol</th><th align="left" style="color:#9fb0c3;padding:4px 8px;">Bias</th><th align="right" style="color:#9fb0c3;padding:4px 8px;">Alignment</th><th align="left" style="color:#9fb0c3;padding:4px 8px;">Daily</th><th align="left" style="color:#9fb0c3;padding:4px 8px;">Short-term</th><th align="left" style="color:#9fb0c3;padding:4px 8px;">Tags</th></tr></thead>
      <tbody>{''.join(full_rows) or '<tr><td colspan="7" style="padding:8px;color:#9fb0c3;">No rows available.</td></tr>'}</tbody>
    </table>
  </div>
</div>
""".strip()
