"""ATR Direction Heatmap reporting: CSV + branded HTML + report payload.

Consumes the :class:`AtrHeatmapResponse` (json) shape. Used by the interactive
CSV/preview endpoints and the scheduled ATR report (email-only). Research-only.
"""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

TIMEFRAME_KEYS = ["1W", "1D", "4H", "1H", "30M"]


def _cell_label(row: dict[str, Any], timeframe: str) -> str:
    states = row.get("states") if isinstance(row.get("states"), dict) else {}
    cell = states.get(timeframe) if isinstance(states, dict) else None
    if not isinstance(cell, dict) or cell.get("status") != "ok":
        return "—"
    state = str(cell.get("state") or "")
    return state.upper() if state in {"long", "short"} else "—"


def build_atr_report_payload(*, response: dict[str, Any], profile_name: str, generated_at: str | None = None) -> dict[str, Any]:
    rows = [row for row in response.get("rows") or [] if isinstance(row, dict)]
    summary = response.get("summary") if isinstance(response.get("summary"), dict) else {}
    available = [r for r in rows if r.get("status") == "ok"]
    longs = sorted([r for r in available if r.get("alignment_label") == "LONG"], key=lambda r: r.get("alignment_score") or 0, reverse=True)
    shorts = sorted([r for r in available if r.get("alignment_label") == "SHORT"], key=lambda r: r.get("alignment_score") or 0)
    recently_flipped = sorted(
        [r for r in available if isinstance(r.get("bars_since_flip"), int)],
        key=lambda r: r.get("bars_since_flip"),
    )
    return {
        "profile_name": profile_name or "ATR Direction Heatmap",
        "generated_at": generated_at or response.get("generated_at"),
        "timeframes": response.get("timeframes") or TIMEFRAME_KEYS,
        "summary": {
            "total": summary.get("total", len(rows)),
            "long_count": summary.get("long_count", len(longs)),
            "short_count": summary.get("short_count", len(shorts)),
            "mixed_count": summary.get("mixed_count", 0),
            "unavailable_count": summary.get("unavailable_count", 0),
        },
        "top_long": longs[:10],
        "top_short": shorts[:10],
        "recently_flipped": recently_flipped[:10],
        "rows": rows,
        "config": response.get("config") or {},
        "notes": [
            "Research dashboard only. Not trade execution or investment advice.",
            "ATR LONG/SHORT states + trailing stop are directional research/risk context.",
            "No live trading, broker routing, recommendations, paper orders, or automatic execution are created by this report.",
        ],
    }


def atr_heatmap_csv(report_payload: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "symbol", "1w", "1d", "4h", "1h", "30m",
            "alignment_score", "alignment_label",
            "latest_trailing_stop", "distance_to_stop_pct", "bars_since_flip",
            "last_flip_direction", "last_flip_time", "status",
        ],
    )
    writer.writeheader()
    for row in report_payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        writer.writerow(
            {
                "symbol": row.get("symbol"),
                "1w": _cell_label(row, "1W"),
                "1d": _cell_label(row, "1D"),
                "4h": _cell_label(row, "4H"),
                "1h": _cell_label(row, "1H"),
                "30m": _cell_label(row, "30M"),
                "alignment_score": row.get("alignment_score"),
                "alignment_label": row.get("alignment_label"),
                "latest_trailing_stop": row.get("latest_trailing_stop"),
                "distance_to_stop_pct": row.get("distance_to_stop_pct"),
                "bars_since_flip": row.get("bars_since_flip"),
                "last_flip_direction": row.get("last_flip_direction"),
                "last_flip_time": row.get("last_flip_time"),
                "status": row.get("status"),
            }
        )
    return output.getvalue()


def atr_heatmap_text(report_payload: dict[str, Any]) -> str:
    summary = report_payload.get("summary") if isinstance(report_payload.get("summary"), dict) else {}
    top_long = [r for r in report_payload.get("top_long") or [] if isinstance(r, dict)]
    top_short = [r for r in report_payload.get("top_short") or [] if isinstance(r, dict)]
    flipped = [r for r in report_payload.get("recently_flipped") or [] if isinstance(r, dict)]
    lines = [
        f"MacMarket ATR Direction Heatmap - {report_payload.get('profile_name') or 'Scheduled ATR Heatmap'}",
        f"Generated: {report_payload.get('generated_at')}",
        "Research dashboard only. Not trade execution or investment advice.",
        f"Summary: LONG {summary.get('long_count', 0)} / SHORT {summary.get('short_count', 0)} / MIXED {summary.get('mixed_count', 0)} / unavailable {summary.get('unavailable_count', 0)}",
        "",
        "Top aligned LONG:",
        *(f"- {r.get('symbol')}: score {r.get('alignment_score')} (stop {r.get('latest_trailing_stop')}, {r.get('distance_to_stop_pct')}%)" for r in top_long[:5]),
        "" if top_long else "- None.",
        "Top aligned SHORT:",
        *(f"- {r.get('symbol')}: score {r.get('alignment_score')} (stop {r.get('latest_trailing_stop')}, {r.get('distance_to_stop_pct')}%)" for r in top_short[:5]),
        "" if top_short else "- None.",
        "Recently flipped:",
        *(f"- {r.get('symbol')}: {str(r.get('last_flip_direction') or '').upper()} {r.get('bars_since_flip')} bars ago ({r.get('last_flip_time')})" for r in flipped[:5]),
        "" if flipped else "- None.",
        "",
        "No live trading, broker routing, recommendations, paper orders, or automatic execution are created by this report.",
    ]
    return "\n".join(lines)


def atr_heatmap_html(report_payload: dict[str, Any]) -> str:
    def esc(value: object) -> str:
        return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    def badge(label: object) -> str:
        text = str(label or "—")
        colors = {"LONG": ("#1f9f62", "#06150b"), "SHORT": ("#bd3d4b", "#ffffff"), "MIXED": ("#7d5cff", "#ffffff")}
        bg, fg = colors.get(text, ("#17202b", "#9fb0c3"))
        return f'<span style="display:inline-block;border-radius:999px;padding:3px 7px;background:{bg};color:{fg};font-weight:700;font-size:11px;">{esc(text)}</span>'

    def compact(name: str, title: str) -> str:
        rows = [r for r in report_payload.get(name) or [] if isinstance(r, dict)]
        body = "".join(
            "<tr>"
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{esc(r.get("symbol"))}</td>'
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{badge(r.get("alignment_label"))}</td>'
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;text-align:right;">{esc(r.get("alignment_score"))}</td>'
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;text-align:right;">{esc(r.get("latest_trailing_stop"))}</td>'
            f'<td style="padding:6px 8px;border-top:1px solid #25303b;text-align:right;">{esc(r.get("distance_to_stop_pct"))}%</td>'
            "</tr>"
            for r in rows[:10]
        ) or '<tr><td colspan="5" style="padding:8px;color:#9fb0c3;border-top:1px solid #25303b;">No matching rows.</td></tr>'
        return (
            f'<h3 style="margin:18px 0 8px;font-size:15px;color:#d7dee8;">{esc(title)}</h3>'
            '<table role="presentation" style="width:100%;border-collapse:collapse;font-size:12px;">'
            '<thead><tr><th align="left" style="color:#9fb0c3;padding:4px 8px;">Symbol</th>'
            '<th align="left" style="color:#9fb0c3;padding:4px 8px;">Alignment</th>'
            '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Score</th>'
            '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Trailing stop</th>'
            '<th align="right" style="color:#9fb0c3;padding:4px 8px;">Dist %</th></tr></thead>'
            f"<tbody>{body}</tbody></table>"
        )

    summary = report_payload.get("summary") if isinstance(report_payload.get("summary"), dict) else {}
    state_rows = "".join(
        "<tr>"
        f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{esc(r.get("symbol"))}</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{badge(_cell_label(r, "1W"))}</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{badge(_cell_label(r, "1D"))}</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{badge(_cell_label(r, "4H"))}</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{badge(_cell_label(r, "1H"))}</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{badge(_cell_label(r, "30M"))}</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #25303b;text-align:right;">{esc(r.get("alignment_score"))}</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #25303b;text-align:right;">{esc(r.get("latest_trailing_stop"))}</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #25303b;text-align:right;">{esc(r.get("distance_to_stop_pct"))}%</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #25303b;text-align:right;">{esc(r.get("bars_since_flip"))}</td>'
        f'<td style="padding:6px 8px;border-top:1px solid #25303b;">{esc(str(r.get("last_flip_direction") or "").upper())} {esc(r.get("last_flip_time"))}</td>'
        "</tr>"
        for r in (report_payload.get("rows") or [])
        if isinstance(r, dict)
    )
    return f"""
<div style="margin:0;background:#0b0f14;color:#d7dee8;font-family:Inter,Segoe UI,Arial,sans-serif;">
  <div style="padding:26px 30px;background:#111821;border-bottom:1px solid #25303b;">
    <div style="font-size:12px;color:#9fb0c3;letter-spacing:.08em;text-transform:uppercase;">MacMarket Research Dashboard</div>
    <h1 style="margin:8px 0 4px;font-size:28px;line-height:1.15;">ATR Direction Heatmap</h1>
    <div style="font-size:13px;color:#9fb0c3;">Profile: {esc(report_payload.get("profile_name"))} - Generated: {esc(report_payload.get("generated_at"))}</div>
  </div>
  <div style="padding:20px 30px;">
    <p style="margin:0 0 16px;color:#9fb0c3;">Research dashboard only. Not trade execution or investment advice. The ATR trailing stop is both a direction signal and a protective-stop / risk reference.</p>
    <p style="margin:0 0 12px;color:#d7dee8;">Summary: <strong style="color:#56f08a;">LONG {esc(summary.get("long_count", 0))}</strong> · <strong style="color:#ff8b8b;">SHORT {esc(summary.get("short_count", 0))}</strong> · MIXED {esc(summary.get("mixed_count", 0))} · unavailable {esc(summary.get("unavailable_count", 0))}</p>
    {compact("top_long", "Top aligned LONG")}
    {compact("top_short", "Top aligned SHORT")}
    {compact("recently_flipped", "Recently flipped")}
    <h3 style="margin:18px 0 8px;font-size:15px;color:#d7dee8;">State table</h3>
    <table role="presentation" style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead><tr>
        <th align="left" style="color:#9fb0c3;padding:4px 8px;">Symbol</th>
        <th align="left" style="color:#9fb0c3;padding:4px 8px;">1W</th>
        <th align="left" style="color:#9fb0c3;padding:4px 8px;">1D</th>
        <th align="left" style="color:#9fb0c3;padding:4px 8px;">4H</th>
        <th align="left" style="color:#9fb0c3;padding:4px 8px;">1H</th>
        <th align="left" style="color:#9fb0c3;padding:4px 8px;">30M</th>
        <th align="right" style="color:#9fb0c3;padding:4px 8px;">Score</th>
        <th align="right" style="color:#9fb0c3;padding:4px 8px;">Trailing stop</th>
        <th align="right" style="color:#9fb0c3;padding:4px 8px;">Dist %</th>
        <th align="right" style="color:#9fb0c3;padding:4px 8px;">Bars since flip</th>
        <th align="left" style="color:#9fb0c3;padding:4px 8px;">Last flip</th>
      </tr></thead>
      <tbody>{state_rows or '<tr><td colspan="11" style="padding:8px;color:#9fb0c3;border-top:1px solid #25303b;">No rows.</td></tr>'}</tbody>
    </table>
    <p style="margin:18px 0 0;color:#6b7a8d;font-size:11px;">No live trading, broker routing, recommendations, paper orders, or automatic execution are created by this report.</p>
  </div>
</div>
"""
