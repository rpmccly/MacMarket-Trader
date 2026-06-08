"use client";

import React, { useEffect, useMemo, useState } from "react";

import { Card, EmptyState, ErrorState, PageHeader, ResponsiveTable, StatusBadge } from "@/components/operator-ui";
import { fetchAtrHeatmap, downloadAtrHeatmapCsv, type AtrHeatmapResponse, type AtrHeatmapRow } from "@/lib/atr-heatmap-api";
import { fetchWatchlists, type Watchlist } from "@/lib/watchlists-api";

const TIMEFRAMES = ["1W", "1D", "4H", "1H", "30M"] as const;

function parseSymbols(input: string): string[] {
  const seen: string[] = [];
  for (const raw of input.split(/[\s,]+/)) {
    const sym = raw.trim().toUpperCase();
    if (sym && !seen.includes(sym)) seen.push(sym);
  }
  return seen;
}

function alignmentTone(label: string): "good" | "warn" | "bad" | "neutral" {
  if (label === "LONG") return "good";
  if (label === "SHORT") return "bad";
  if (label === "MIXED") return "warn";
  return "neutral";
}

function stateTone(state: string | null | undefined): "good" | "warn" | "bad" | "neutral" {
  if (state === "long") return "good";
  if (state === "short") return "bad";
  return "neutral";
}

function cellLabel(row: AtrHeatmapRow, tf: string): { label: string; tone: "good" | "warn" | "bad" | "neutral" } {
  const cell = row.states?.[tf];
  if (!cell || cell.status !== "ok" || !cell.state) return { label: "—", tone: "neutral" };
  return { label: cell.state.toUpperCase(), tone: stateTone(cell.state) };
}

function fmtNum(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : value.toFixed(2);
}

function fmtPct(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : `${value.toFixed(2)}%`;
}

function fmtTime(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length > 19 ? value.slice(0, 19).replace("T", " ") : value.replace("T", " ");
}

export default function Page() {
  const [symbolInput, setSymbolInput] = useState("SPY, QQQ, MTUM");
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [trailType, setTrailType] = useState("modified");
  const [atrPeriod, setAtrPeriod] = useState(9);
  const [atrFactor, setAtrFactor] = useState(2.9);
  const [firstTrade, setFirstTrade] = useState("long");
  const [averageType, setAverageType] = useState("wilders");
  const [response, setResponse] = useState<AtrHeatmapResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const result = await fetchWatchlists();
      if (result.ok && Array.isArray(result.data)) setWatchlists(result.data);
    })();
  }, []);

  const symbols = useMemo(() => parseSymbols(symbolInput), [symbolInput]);

  function requestBody() {
    return {
      symbols,
      timeframes: [...TIMEFRAMES],
      decision_timeframe: "1D",
      trail_type: trailType,
      atr_period: atrPeriod,
      atr_factor: atrFactor,
      first_trade: firstTrade,
      average_type: averageType,
    };
  }

  async function refresh() {
    if (!symbols.length) {
      setError("Enter at least one symbol (or pick a watchlist).");
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      setResponse(await fetchAtrHeatmap(requestBody()));
    } catch (err) {
      setError(err instanceof Error && err.message === "AUTH_NOT_READY" ? "Authenticating… try again in a moment." : "Failed to load ATR Direction Heatmap.");
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }

  async function exportCsv() {
    if (!symbols.length) return;
    try {
      const { csv, filename } = await downloadAtrHeatmapCsv(requestBody());
      const blob = new Blob([csv], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename || "atr-direction-heatmap-report.csv";
      link.click();
      URL.revokeObjectURL(url);
      setNotice("CSV exported.");
    } catch {
      setError("Failed to export CSV.");
    }
  }

  const summary = response?.summary;

  return (
    <div className="op-stack">
      <PageHeader
        title="ATR Direction Heatmap"
        subtitle="Research-only multi-timeframe ATR Trailing Stop direction + alignment. Not trade approval, sizing, or routing."
        actions={<StatusBadge tone="neutral">Research only</StatusBadge>}
      />

      <Card title="Symbols">
        <div className="op-row" style={{ alignItems: "flex-end", flexWrap: "wrap" }}>
          <label style={{ flex: "1 1 320px" }}>
            <span className="agent-setting-help">Symbols (comma or space separated)</span>
            <input aria-label="Symbols" data-testid="atr-heatmap-symbols" value={symbolInput} onChange={(event) => setSymbolInput(event.target.value)} placeholder="SPY, QQQ, MTUM" />
          </label>
          <label>
            <span className="agent-setting-help">Load watchlist</span>
            <select
              aria-label="Watchlist"
              data-testid="atr-heatmap-watchlist"
              value=""
              onChange={(event) => {
                const wl = watchlists.find((item) => String(item.id) === event.target.value);
                if (wl) setSymbolInput(wl.symbols.join(", "));
              }}
            >
              <option value="">— pick a watchlist —</option>
              {watchlists.map((wl) => <option key={wl.id} value={String(wl.id)}>{wl.name} ({wl.symbols.length})</option>)}
            </select>
          </label>
          <button className="op-btn op-btn-primary" type="button" onClick={() => void refresh()} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>
          <button className="op-btn op-btn-ghost" type="button" onClick={() => void exportCsv()} disabled={loading || !response}>Export CSV</button>
        </div>
        <p className="agent-setting-help">{symbols.length} symbol(s). The ATR trailing stop is both the direction signal and the protective stop / risk reference.</p>
        <details data-testid="atr-heatmap-advanced">
          <summary style={{ cursor: "pointer", fontWeight: 600 }}>Advanced ATR settings</summary>
          <div className="op-grid op-grid-3" style={{ marginTop: 8 }}>
            <label><span className="agent-setting-help">Trail type</span>
              <select aria-label="Trail type" value={trailType} onChange={(event) => setTrailType(event.target.value)}><option value="modified">Modified</option><option value="unmodified">Unmodified</option></select>
            </label>
            <label><span className="agent-setting-help">ATR period</span><input aria-label="ATR period" type="number" min={1} value={atrPeriod} onChange={(event) => setAtrPeriod(Number(event.target.value))} /></label>
            <label><span className="agent-setting-help">ATR factor</span><input aria-label="ATR factor" type="number" step="0.1" min={0} value={atrFactor} onChange={(event) => setAtrFactor(Number(event.target.value))} /></label>
            <label><span className="agent-setting-help">First trade</span>
              <select aria-label="First trade" value={firstTrade} onChange={(event) => setFirstTrade(event.target.value)}><option value="long">Long</option><option value="short">Short</option></select>
            </label>
            <label><span className="agent-setting-help">Average type</span>
              <select aria-label="Average type" value={averageType} onChange={(event) => setAverageType(event.target.value)}><option value="wilders">Wilders</option><option value="simple">Simple</option></select>
            </label>
          </div>
        </details>
      </Card>

      {error ? <ErrorState title="ATR Direction Heatmap unavailable" hint={error} /> : null}
      {notice ? <p className="agent-setting-help" data-testid="atr-heatmap-notice">{notice}</p> : null}

      {response ? (
        <Card title="Direction heatmap">
          <div className="op-row" style={{ gap: 8, marginBottom: 8 }}>
            <StatusBadge tone="good">LONG {summary?.long_count ?? 0}</StatusBadge>
            <StatusBadge tone="bad">SHORT {summary?.short_count ?? 0}</StatusBadge>
            <StatusBadge tone="warn">MIXED {summary?.mixed_count ?? 0}</StatusBadge>
            <StatusBadge tone="neutral">Unavailable {summary?.unavailable_count ?? 0}</StatusBadge>
          </div>
          {response.rows.length ? (
            <ResponsiveTable label="ATR Direction Heatmap">
              <table className="op-table">
                <thead><tr>
                  <th>Symbol</th><th>1W</th><th>1D</th><th>4H</th><th>1H</th><th>30M</th>
                  <th>Alignment</th><th>Trailing stop</th><th>Distance %</th><th>Bars since flip</th><th>Last flip</th>
                </tr></thead>
                <tbody>{response.rows.map((row) => (
                  <tr key={row.symbol}>
                    <td>{row.symbol}</td>
                    {TIMEFRAMES.map((tf) => {
                      const cell = cellLabel(row, tf);
                      return <td key={tf}><StatusBadge tone={cell.tone}>{cell.label}</StatusBadge></td>;
                    })}
                    <td><StatusBadge tone={alignmentTone(row.alignment_label)}>{row.alignment_label} ({row.alignment_score >= 0 ? "+" : ""}{row.alignment_score})</StatusBadge></td>
                    <td>{fmtNum(row.latest_trailing_stop)}</td>
                    <td>{fmtPct(row.distance_to_stop_pct)}</td>
                    <td>{row.bars_since_flip ?? "—"}</td>
                    <td>{(row.last_flip_direction ? row.last_flip_direction.toUpperCase() : "—")} @ {fmtTime(row.last_flip_time)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </ResponsiveTable>
          ) : <EmptyState title="No symbols" hint="Enter symbols or pick a watchlist, then refresh." />}
        </Card>
      ) : !error ? (
        <Card title="ATR Direction Heatmap"><EmptyState title="Refresh to load" hint="Enter symbols (or pick a watchlist) and click Refresh to compute the multi-timeframe ATR direction heatmap." /></Card>
      ) : null}
    </div>
  );
}
