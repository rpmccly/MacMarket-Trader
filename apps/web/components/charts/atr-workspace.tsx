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
import { ATR_TRAILING_STOP_COLORS } from "@/lib/chart-indicators";

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

type AtrStopState = "long" | "short";

type SvgStopPoint = {
  x: number;
  y: number;
  state: AtrStopState;
};

function normalizeStopState(value: string | null | undefined): AtrStopState | null {
  if (value === "long" || value === "short") return value;
  return null;
}

function buildStopSegments(points: SvgStopPoint[]): Array<{ state: AtrStopState; points: SvgStopPoint[] }> {
  const segments: Array<{ state: AtrStopState; points: SvgStopPoint[] }> = [];
  let activeState: AtrStopState | null = null;
  let activePoints: SvgStopPoint[] = [];

  for (const point of points) {
    if (activeState !== point.state) {
      if (activeState && activePoints.length > 0) segments.push({ state: activeState, points: activePoints });
      activeState = point.state;
      activePoints = [];
    }
    activePoints.push(point);
  }

  if (activeState && activePoints.length > 0) segments.push({ state: activeState, points: activePoints });
  return segments;
}

function buildStepPath(points: SvgStopPoint[], halfWidth: number): string {
  if (points.length === 0) return "";
  if (points.length === 1) {
    const point = points[0];
    return `M ${Math.max(0, point.x - halfWidth).toFixed(2)} ${point.y.toFixed(2)} H ${(point.x + halfWidth).toFixed(2)}`;
  }
  return points
    .slice(1)
    .reduce(
      (path, point) => `${path} H ${point.x.toFixed(2)} V ${point.y.toFixed(2)}`,
      `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`,
    );
}

// Dependency-free, responsive OHLC candle + ATR trailing-stop chart (SVG). No canvas,
// so it renders + tests in jsdom and scales with its container via viewBox.
function AtrPriceStopChart({ payload }: { payload: AtrChartPayload }) {
  const candles = payload.candles.slice(-180);
  if (candles.length < 2) return null;
  const width = 720;
  const height = 260;
  const padX = 12;
  const padY = 10;
  const stopByTime = new Map(payload.trailing_stop.map((point) => [String(point.time), point]));
  const stopValues = candles
    .map((candle) => stopByTime.get(String(candle.time))?.trailing_stop)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const lo = Math.min(...candles.map((candle) => candle.low), ...stopValues);
  const hi = Math.max(...candles.map((candle) => candle.high), ...stopValues);
  const range = hi - lo || 1;
  const x = (idx: number) => padX + (idx / (candles.length - 1)) * (width - 2 * padX);
  const y = (value: number) => padY + (1 - (value - lo) / range) * (height - 2 * padY);
  const slotWidth = (width - 2 * padX) / Math.max(1, candles.length - 1);
  const bodyWidth = Math.max(3, Math.min(9, slotWidth * 0.52));
  const stopPoints = candles
    .map((candle, idx): SvgStopPoint | null => {
      const stop = stopByTime.get(String(candle.time));
      const state = normalizeStopState(stop?.state);
      if (!stop || !state || !Number.isFinite(stop.trailing_stop)) return null;
      return { x: x(idx), y: y(stop.trailing_stop), state };
    })
    .filter((point): point is SvgStopPoint => point !== null);
  const stopSegments = buildStopSegments(stopPoints);
  return (
    <div className="op-chart-frame" data-testid="atr-price-stop-chart">
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label="ATR price and trailing stop" preserveAspectRatio="none" style={{ maxHeight: 280 }}>
        {candles.map((candle, idx) => {
          const cx = x(idx);
          const openY = y(candle.open);
          const closeY = y(candle.close);
          const highY = y(candle.high);
          const lowY = y(candle.low);
          const up = candle.close >= candle.open;
          const color = up ? "#2c9f5d" : "#b24f4f";
          const top = Math.min(openY, closeY);
          const bodyHeight = Math.max(1, Math.abs(closeY - openY));
          return (
            <g key={`${candle.time}-${idx}`}>
              <line x1={cx} x2={cx} y1={highY} y2={lowY} stroke={color} strokeWidth={1.15} opacity={0.9} />
              <rect x={cx - bodyWidth / 2} y={top} width={bodyWidth} height={bodyHeight} fill={color} opacity={0.84} rx={0.8} />
            </g>
          );
        })}
        {stopSegments.map((segment, idx) => (
          <path
            key={`${segment.state}-${idx}`}
            d={buildStepPath(segment.points, bodyWidth / 2)}
            fill="none"
            stroke={ATR_TRAILING_STOP_COLORS[segment.state]}
            strokeWidth={2.2}
            strokeLinecap="square"
            strokeLinejoin="miter"
          />
        ))}
      </svg>
      <div className="op-row" style={{ gap: 14, marginTop: 4, fontSize: 12, color: "var(--muted)" }}>
        <span><span style={{ color: "#9fb0c3" }}>--</span> OHLC candles</span>
        <span><span style={{ color: ATR_TRAILING_STOP_COLORS.long }}>--</span> Long/support ATR stop</span>
        <span><span style={{ color: ATR_TRAILING_STOP_COLORS.short }}>--</span> Short/resistance ATR stop</span>
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
  const [averageType, setAverageType] = useState("exponential");

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
                    <option value="exponential">Exponential</option>
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
