"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";

import { Card, EmptyState, ErrorState, PageHeader, ResponsiveTable, StatusBadge } from "@/components/operator-ui";
import { ChartHistoryRangeSelect } from "@/components/charts/chart-history-range-select";
import {
  defaultChartHistoryRange,
  type ChartHistoryRangeId,
} from "@/lib/chart-history-range";
import { SUPPORTED_TIMEFRAME_OPTIONS, type SupportedTimeframe } from "@/lib/timeframes";
import { fetchAtrChart, type AtrChartPayload } from "@/lib/atr-api";

const TABLE_TIMEFRAMES = ["1W", "1D", "4H", "1H", "30M"] as const;

function stateTone(state: string | null | undefined): "good" | "warn" | "bad" | "neutral" {
  if (state === "long") return "good";
  if (state === "short") return "bad";
  return "neutral";
}

function stateLabel(state: string | null | undefined): string {
  if (state === "long") return "LONG";
  if (state === "short") return "SHORT";
  return "—";
}

function fmtNum(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : value.toFixed(digits);
}

function fmtPct(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value) ? "—" : `${value.toFixed(2)}%`;
}

function fmtTime(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length > 19 ? value.slice(0, 19).replace("T", " ") : value.replace("T", " ");
}

// Dependency-free, responsive price + trailing-stop line chart (SVG). No canvas,
// so it renders + tests in jsdom and scales with its container via viewBox.
function AtrPriceStopChart({ payload }: { payload: AtrChartPayload }) {
  const points = payload.trailing_stop;
  if (points.length < 2) return null;
  const width = 720;
  const height = 260;
  const pad = 8;
  const closes = points.map((p) => p.close);
  const stops = points.map((p) => p.trailing_stop);
  const lo = Math.min(...closes, ...stops);
  const hi = Math.max(...closes, ...stops);
  const range = hi - lo || 1;
  const x = (i: number) => pad + (i / (points.length - 1)) * (width - 2 * pad);
  const y = (v: number) => pad + (1 - (v - lo) / range) * (height - 2 * pad);
  const priceLine = points.map((p, i) => `${x(i).toFixed(2)},${y(p.close).toFixed(2)}`).join(" ");
  const stopLine = points.map((p, i) => `${x(i).toFixed(2)},${y(p.trailing_stop).toFixed(2)}`).join(" ");
  return (
    <div className="op-chart-frame" data-testid="atr-price-stop-chart">
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="ATR price and trailing stop" preserveAspectRatio="none" style={{ maxHeight: 280 }}>
        <polyline fill="none" stroke="#9fb0c3" strokeWidth={1.5} points={priceLine} />
        <polyline fill="none" stroke="#f2a03f" strokeWidth={1.5} strokeDasharray="4 3" points={stopLine} />
      </svg>
      <div className="op-row" style={{ gap: 14, marginTop: 4, fontSize: 12, color: "var(--muted)" }}>
        <span><span style={{ color: "#9fb0c3" }}>──</span> Close price</span>
        <span><span style={{ color: "#f2a03f" }}>┄┄</span> ATR trailing stop</span>
      </div>
    </div>
  );
}

export function AtrWorkspace() {
  const [symbolInput, setSymbolInput] = useState("SPY");
  const [symbol, setSymbol] = useState("SPY");
  const [timeframe, setTimeframe] = useState<SupportedTimeframe>("1D");
  const [historyRange, setHistoryRange] = useState<ChartHistoryRangeId>(defaultChartHistoryRange());
  // Advanced ATR settings (math frozen on the backend; these only pick inputs).
  const [trailType, setTrailType] = useState("modified");
  const [atrPeriod, setAtrPeriod] = useState(9);
  const [atrFactor, setAtrFactor] = useState(2.9);
  const [firstTrade, setFirstTrade] = useState("long");
  const [averageType, setAverageType] = useState("wilders");

  const [payload, setPayload] = useState<AtrChartPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  async function load(nextSymbol: string) {
    const sym = nextSymbol.trim().toUpperCase();
    if (!sym) return;
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    setSymbol(sym);
    try {
      const result = await fetchAtrChart({
        symbol: sym,
        timeframe,
        history_range: historyRange,
        trail_type: trailType,
        atr_period: atrPeriod,
        atr_factor: atrFactor,
        first_trade: firstTrade,
        average_type: averageType,
        multi_timeframes: [...TABLE_TIMEFRAMES],
      });
      if (id === requestId.current) setPayload(result);
    } catch (err) {
      if (id === requestId.current) {
        setError(err instanceof Error && err.message === "AUTH_NOT_READY" ? "Authenticating… try again in a moment." : "Failed to load ATR Intel.");
        setPayload(null);
      }
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }

  // Reload when timeframe / range / advanced settings change for the loaded symbol.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load(symbol); }, [timeframe, historyRange, trailType, atrPeriod, atrFactor, firstTrade, averageType]);

  const explanation = payload?.explanation;
  const noData = useMemo(
    () => Boolean(payload && (payload.notes?.includes("no_bars") || payload.candles.length === 0)),
    [payload],
  );
  const stateByTimeframe = useMemo(() => {
    const map: Record<string, AtrChartPayload["timeframe_states"][number]> = {};
    for (const row of payload?.timeframe_states ?? []) map[row.timeframe] = row;
    return map;
  }, [payload]);

  return (
    <div className="op-stack">
      <PageHeader
        title="ATR Intel"
        subtitle="Research-only ATR Trailing Stop direction + protective-stop context. Not trade approval, sizing, or routing."
        actions={<StatusBadge tone="neutral">Research only</StatusBadge>}
      />

      <Card title="Symbol">
        <form
          className="op-row"
          onSubmit={(event) => { event.preventDefault(); void load(symbolInput); }}
        >
          <label>
            <span className="agent-setting-help">Symbol</span>
            <input aria-label="Symbol" data-testid="atr-symbol-input" value={symbolInput} onChange={(event) => setSymbolInput(event.target.value)} placeholder="e.g. SPY" />
          </label>
          <label>
            <span className="agent-setting-help">Timeframe</span>
            <select aria-label="Timeframe" data-testid="atr-timeframe-select" value={timeframe} onChange={(event) => setTimeframe(event.target.value as SupportedTimeframe)}>
              {SUPPORTED_TIMEFRAME_OPTIONS.map((tf) => <option key={tf.value} value={tf.value}>{tf.label}</option>)}
            </select>
          </label>
          <ChartHistoryRangeSelect value={historyRange} onChange={setHistoryRange} />
          <button className="op-btn op-btn-primary" type="submit" disabled={loading}>{loading ? "Loading…" : "Load"}</button>
        </form>
        <p className="agent-setting-help" data-testid="atr-explainer">
          The ATR Trailing Stop is <strong>both the direction signal and the protective stop / risk reference</strong>:
          when price holds above the trailing stop the state is LONG; a break below flips it SHORT. The same level is
          the suggested protective stop, so distance-to-stop is the per-share risk reference.
        </p>
      </Card>

      {error ? <ErrorState title="ATR Intel unavailable" hint={error} /> : null}

      {payload && !error ? (
        <>
          <Card title={`${payload.symbol} · ${payload.timeframe} snapshot`}>
            {noData ? (
              <EmptyState title="No data for this symbol" hint="No bars were returned for this symbol/timeframe. Check the ticker or try another timeframe." />
            ) : (
              <>
                <div className="op-row" style={{ gap: 10, alignItems: "center" }}>
                  <StatusBadge tone={stateTone(explanation?.current_state)} >Current state: {stateLabel(explanation?.current_state)}</StatusBadge>
                  <StatusBadge tone="neutral">source: {payload.data_source}{payload.fallback_mode ? " (fallback)" : ""}</StatusBadge>
                </div>
                <div className="agent-profile-card-meta" data-testid="atr-snapshot">
                  <span>Latest trailing stop: {fmtNum(explanation?.latest_trailing_stop)}</span>
                  <span>Distance to stop: {fmtPct(explanation?.distance_to_stop_pct)}</span>
                  <span>Bars since flip: {explanation?.bars_since_flip ?? "—"}</span>
                  <span>Last flip: {stateLabel(explanation?.last_flip_direction)} @ {fmtTime(explanation?.last_flip_time)}</span>
                </div>
                <AtrPriceStopChart payload={payload} />
              </>
            )}
          </Card>

          <Card title="Multi-timeframe ATR state">
            <ResponsiveTable label="ATR multi-timeframe state">
              <table className="op-table">
                <thead><tr><th>Timeframe</th><th>State</th><th>Trailing stop</th><th>Distance %</th><th>Bars since flip</th><th>Last flip</th><th>Source</th></tr></thead>
                <tbody>{TABLE_TIMEFRAMES.map((tf) => {
                  const row = stateByTimeframe[tf];
                  if (!row || row.status !== "ok") {
                    return (
                      <tr key={tf}>
                        <td>{tf}</td>
                        <td colSpan={5}><span className="agent-setting-help">{row?.reason === "insufficient_bars" ? "Insufficient bars" : "Unavailable / no data"}</span></td>
                        <td>{row?.data_source ?? "—"}</td>
                      </tr>
                    );
                  }
                  return (
                    <tr key={tf}>
                      <td>{tf}</td>
                      <td><StatusBadge tone={stateTone(row.state)}>{stateLabel(row.state)}</StatusBadge></td>
                      <td>{fmtNum(row.trailing_stop)}</td>
                      <td>{fmtPct(row.stop_distance_pct)}</td>
                      <td>{row.bars_since_flip ?? "—"}</td>
                      <td>{stateLabel(row.last_flip_direction)} @ {fmtTime(row.last_flip_time)}</td>
                      <td>{row.data_source ?? "—"}{row.fallback_mode ? " (fallback)" : ""}</td>
                    </tr>
                  );
                })}</tbody>
              </table>
            </ResponsiveTable>
          </Card>

          <Card title="Advanced ATR settings">
            <details data-testid="atr-advanced-settings">
              <summary style={{ cursor: "pointer", fontWeight: 600 }}>ATR inputs (trail type, period, factor, first trade, average type)</summary>
              <div className="op-grid op-grid-3" style={{ marginTop: 8 }}>
                <label>
                  <span className="agent-setting-help">Trail type</span>
                  <select aria-label="Trail type" value={trailType} onChange={(event) => setTrailType(event.target.value)}>
                    <option value="modified">Modified</option>
                    <option value="unmodified">Unmodified</option>
                  </select>
                </label>
                <label>
                  <span className="agent-setting-help">ATR period</span>
                  <input aria-label="ATR period" type="number" min={1} value={atrPeriod} onChange={(event) => setAtrPeriod(Number(event.target.value))} />
                </label>
                <label>
                  <span className="agent-setting-help">ATR factor</span>
                  <input aria-label="ATR factor" type="number" step="0.1" min={0} value={atrFactor} onChange={(event) => setAtrFactor(Number(event.target.value))} />
                </label>
                <label>
                  <span className="agent-setting-help">First trade</span>
                  <select aria-label="First trade" value={firstTrade} onChange={(event) => setFirstTrade(event.target.value)}>
                    <option value="long">Long</option>
                    <option value="short">Short</option>
                  </select>
                </label>
                <label>
                  <span className="agent-setting-help">Average type</span>
                  <select aria-label="Average type" value={averageType} onChange={(event) => setAverageType(event.target.value)}>
                    <option value="wilders">Wilders</option>
                    <option value="simple">Simple</option>
                  </select>
                </label>
              </div>
              <p className="agent-setting-help">ATR math is frozen and shared with the ATR Trailing Stop agent; these inputs only change how the signal/stop is computed for this view.</p>
            </details>
          </Card>
        </>
      ) : !error ? (
        <Card title="ATR Intel"><EmptyState title="Loading ATR Intel" hint="Enter a symbol and load to see the ATR state, trailing stop, and multi-timeframe table." /></Card>
      ) : null}
    </div>
  );
}
