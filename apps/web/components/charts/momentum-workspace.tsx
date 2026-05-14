"use client";

import React from "react";
import {
  ColorType,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { Card, ErrorState, StatusBadge } from "@/components/operator-ui";
import { MomentumSummaryPanel } from "@/components/charts/momentum-summary-panel";
import {
  CandleStatusBadges,
  HiloPanelStatusBadges,
  TrueMomentumPanelStatusBadges,
} from "@/components/charts/chart-status-badges";
import { MomentumContextLegend } from "@/components/charts/momentum-context-legend";
import { ChartHistoryRangeSelect } from "@/components/charts/chart-history-range-select";
import {
  defaultChartHistoryRange,
  readChartHistoryRangeFromStorage,
  writeChartHistoryRangeToStorage,
  type ChartHistoryRangeId,
} from "@/lib/chart-history-range";
import {
  describeHigherTimeframeSource,
  describeParityStatus,
  MOMENTUM_DETERMINISTIC_NOTE,
  splitMomentumLineByDirection,
} from "@/lib/momentum-chart";
import {
  fetchMomentumChart,
  type MomentumChartPayload,
  type MomentumPanelMarker,
  type MomentumSignalMarker,
} from "@/lib/momentum-api";

const TIMEFRAMES = ["1D", "4H", "1H"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

const COLORS = {
  bull: "#21c06e",
  bear: "#c64242",
  warn: "#f2a03f",
  neutral: "#5a6b7c",
  trueMomentum: "#21c06e",
  trueMomentumEma: "#d14b4b",
  slowD: "#5ab0ff",
  slowDX: "#9d7dff",
  scoreBull: "#21c06e",
  scoreBear: "#c64242",
  scoreNeutral: "#54708b",
};

function markerProps(marker: MomentumSignalMarker): {
  position: "belowBar" | "aboveBar";
  color: string;
  shape: "arrowUp" | "arrowDown" | "circle";
} {
  if (marker.direction === "bullish") return { position: "belowBar", color: COLORS.bull, shape: "arrowUp" };
  if (marker.direction === "bearish") return { position: "aboveBar", color: COLORS.bear, shape: "arrowDown" };
  return { position: "aboveBar", color: COLORS.warn, shape: "circle" };
}

function panelMarkerProps(marker: MomentumPanelMarker): {
  position: "belowBar" | "aboveBar";
  color: string;
  shape: "arrowUp" | "arrowDown" | "circle";
} {
  if (marker.direction === "up") return { position: "belowBar", color: COLORS.bull, shape: "arrowUp" };
  if (marker.direction === "down") return { position: "aboveBar", color: COLORS.bear, shape: "arrowDown" };
  return { position: "aboveBar", color: COLORS.warn, shape: "circle" };
}

function scoreColor(state: string): string {
  if (state === "max_bull" || state === "bull") return COLORS.scoreBull;
  if (state === "max_bear" || state === "bear") return COLORS.scoreBear;
  return COLORS.scoreNeutral;
}

function thrustColor(state: string): string {
  if (state === "bullish") return COLORS.bull;
  if (state === "bearish") return COLORS.bear;
  return COLORS.neutral;
}

function PanelHeading({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="op-row" style={{ justifyContent: "space-between", alignItems: "baseline", marginTop: 6 }}>
      <h4 style={{ margin: 0, fontSize: "0.86rem", fontWeight: 600 }}>{title}</h4>
      <span style={{ fontSize: "0.76rem", color: "var(--op-muted, #7a8999)" }}>{hint}</span>
    </div>
  );
}

export function MomentumWorkspace() {
  const [symbol, setSymbol] = useState("AAPL");
  const [timeframe, setTimeframe] = useState<Timeframe>("1D");
  const [historyRange, setHistoryRange] = useState<ChartHistoryRangeId>(
    defaultChartHistoryRange(),
  );
  const [data, setData] = useState<MomentumChartPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const priceRef = useRef<HTMLDivElement | null>(null);
  const trueMomentumRef = useRef<HTMLDivElement | null>(null);
  const hiloRef = useRef<HTMLDivElement | null>(null);
  const scoreRef = useRef<HTMLDivElement | null>(null);
  const thrustRef = useRef<HTMLDivElement | null>(null);

  // Lazy-hydrate the persisted history range on mount so all chart
  // surfaces share the same operator preference via
  // ``macmarket.chart.historyRange``.
  useEffect(() => {
    setHistoryRange(readChartHistoryRangeFromStorage());
  }, []);

  async function load(overrideHistoryRange?: ChartHistoryRangeId) {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchMomentumChart({
        symbol,
        timeframe,
        history_range: overrideHistoryRange ?? historyRange,
      });
      setData(payload);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load Momentum chart.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  function handleHistoryRangeChange(next: ChartHistoryRangeId) {
    setHistoryRange(next);
    writeChartHistoryRangeToStorage(next);
    void load(next);
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!data) return;
    const priceContainer = priceRef.current;
    const trueContainer = trueMomentumRef.current;
    const hiloContainer = hiloRef.current;
    const scoreContainer = scoreRef.current;
    const thrustContainer = thrustRef.current;
    if (!priceContainer || !trueContainer || !hiloContainer || !scoreContainer || !thrustContainer) return;

    const baseOptions = {
      layout: { background: { type: ColorType.Solid, color: "#0b1219" }, textColor: "#d9e2ef" },
      grid: { vertLines: { color: "#1f2a36" }, horzLines: { color: "#1f2a36" } },
      rightPriceScale: { borderColor: "#26303a" },
      timeScale: { borderColor: "#26303a" },
      autoSize: true,
    };

    const priceChart = createChart(priceContainer, { ...baseOptions, height: 320 });
    const trueChart = createChart(trueContainer, { ...baseOptions, height: 130 });
    const hiloChart = createChart(hiloContainer, { ...baseOptions, height: 130 });
    const scoreChart = createChart(scoreContainer, { ...baseOptions, height: 110 });
    const thrustChart = createChart(thrustContainer, { ...baseOptions, height: 90 });

    const candles: CandlestickData<Time>[] = data.candles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    const priceSeries: ISeriesApi<"Candlestick"> = priceChart.addCandlestickSeries();
    if (candles.length > 0) priceSeries.setData(candles);

    if (data.markers.length > 0 && candles.length > 0) {
      priceSeries.setMarkers(
        data.markers.map((m) => {
          const props = markerProps(m);
          return {
            time: m.time as Time,
            position: props.position,
            color: props.color,
            shape: props.shape,
            text: m.text,
          };
        }),
      );
    }

    // Directional True Momentum / EMA series — bullish (above EMA)
    // renders green, bearish (below EMA) renders red so direction is
    // visually obvious in the same way as the Thinkorswim chart. The
    // raw numeric values are preserved; only the visual segmentation
    // is recomputed for split-series overlay rendering.
    const { bullSeries: tmBull, bearSeries: tmBear } = splitMomentumLineByDirection(
      data.true_momentum_line,
      data.true_momentum_ema_line,
    );
    const { bullSeries: emaBull, bearSeries: emaBear } = splitMomentumLineByDirection(
      data.true_momentum_ema_line,
      data.true_momentum_line,
    );
    if (tmBull.length > 0) {
      const series = trueChart.addLineSeries({ color: COLORS.bull, lineWidth: 2 });
      series.setData(tmBull.map((p) => ({ time: p.time as Time, value: p.value })));
    }
    if (tmBear.length > 0) {
      const series = trueChart.addLineSeries({ color: COLORS.bear, lineWidth: 2 });
      series.setData(tmBear.map((p) => ({ time: p.time as Time, value: p.value })));
    }
    if (emaBull.length > 0) {
      const series = trueChart.addLineSeries({ color: COLORS.bull, lineWidth: 1, lineStyle: 2 });
      series.setData(emaBull.map((p) => ({ time: p.time as Time, value: p.value })));
    }
    if (emaBear.length > 0) {
      const series = trueChart.addLineSeries({ color: COLORS.bear, lineWidth: 1, lineStyle: 2 });
      series.setData(emaBear.map((p) => ({ time: p.time as Time, value: p.value })));
    }

    // Render True Momentum panel markers (cross-up / cross-down) on
    // the True Momentum series. Markers describe deterministic context
    // only — they are never buy/sell signals.
    const tmMarkers = data.true_momentum_panel_markers ?? [];
    if (tmMarkers.length > 0 && (tmBull.length > 0 || tmBear.length > 0)) {
      // Attach to whichever series has the most data — markers display
      // independent of the underlying series direction.
      const carrier = trueChart.addLineSeries({
        color: "rgba(0,0,0,0)",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const carrierData: LineData<Time>[] = data.true_momentum_line.map((p) => ({
        time: p.time as Time,
        value: p.value,
      }));
      carrier.setData(carrierData);
      carrier.setMarkers(
        tmMarkers.map((m) => {
          const props = panelMarkerProps(m);
          return {
            time: m.time as Time,
            position: props.position,
            color: props.color,
            shape: props.shape,
            text: m.label,
          };
        }),
      );
    }

    const slowDLine: LineData<Time>[] = data.hilo_slowd_line.map((p) => ({ time: p.time as Time, value: p.value }));
    const slowDXLine: LineData<Time>[] = data.hilo_slowd_x_line.map((p) => ({ time: p.time as Time, value: p.value }));
    let hiloMarkerSeries: ISeriesApi<"Line"> | null = null;
    if (slowDLine.length > 0) {
      const sd = hiloChart.addLineSeries({ color: COLORS.slowD, lineWidth: 2 });
      sd.setData(slowDLine);
      hiloMarkerSeries = sd;
    }
    if (slowDXLine.length > 0) {
      const sdx = hiloChart.addLineSeries({ color: COLORS.slowDX, lineWidth: 2 });
      sdx.setData(slowDXLine);
    }

    const hiloMarkers = data.hilo_panel_markers ?? [];
    if (hiloMarkerSeries && hiloMarkers.length > 0) {
      hiloMarkerSeries.setMarkers(
        hiloMarkers.map((m) => {
          const props = panelMarkerProps(m);
          return {
            time: m.time as Time,
            position: props.position,
            color: props.color,
            shape: props.shape,
            text: m.label,
          };
        }),
      );
    }

    if (data.score_strip.length > 0) {
      const scoreData: HistogramData<Time>[] = data.score_strip.map((p) => ({
        time: p.time as Time,
        value: p.total_score,
        color: scoreColor(p.state),
      }));
      const scoreSeries = scoreChart.addHistogramSeries({ base: 0, color: COLORS.scoreNeutral });
      scoreSeries.setData(scoreData);
    }

    if (data.hilo_thrust_strip.length > 0) {
      const thrustData: HistogramData<Time>[] = data.hilo_thrust_strip.map((p) => ({
        time: p.time as Time,
        value: p.value,
        color: thrustColor(p.state),
      }));
      const thrustSeries = thrustChart.addHistogramSeries({ base: 50, color: COLORS.neutral });
      thrustSeries.setData(thrustData);
    }

    let syncing = false;
    const charts: IChartApi[] = [priceChart, trueChart, hiloChart, scoreChart, thrustChart];
    const syncFrom = (source: IChartApi) => {
      source.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        // Phase A3 hardening: sparse/empty payloads must not crash the
        // synchronization handler. Bail out cleanly on null ranges or while
        // another sync pass is already in flight.
        if (!range || syncing) return;
        syncing = true;
        try {
          for (const chart of charts) {
            if (chart === source) continue;
            try {
              chart.timeScale().setVisibleLogicalRange(range);
            } catch {
              // ignore — peer chart may have been disposed or empty
            }
          }
        } finally {
          syncing = false;
        }
      });
    };
    for (const chart of charts) syncFrom(chart);
    if (candles.length > 0) priceChart.timeScale().fitContent();

    return () => {
      for (const chart of charts) chart.remove();
    };
  }, [data]);

  const sessionLabel = data?.session_policy ? data.session_policy.replaceAll("_", " ") : null;
  const htfLabel = describeHigherTimeframeSource(data?.higher_timeframe_source);
  const parityLabel = describeParityStatus(data?.parity_status);

  return (
    <main
      role="main"
      aria-label="Momentum Intelligence workspace"
      data-testid="momentum-workspace"
      style={{ display: "grid", gap: 12 }}
    >
      <Card>
        <h2 style={{ margin: 0 }}>Momentum Intelligence workspace</h2>
        <p style={{ marginBottom: 0, color: "#9fb0c3" }} data-testid="momentum-workspace-deterministic-note">
          {MOMENTUM_DETERMINISTIC_NOTE}
        </p>
      </Card>

      <Card>
        <div className="op-row" role="group" aria-label="Momentum query controls" style={{ flexWrap: "wrap", gap: 12 }}>
          <label>
            <span style={{ marginRight: 8 }}>Symbol</span>
            <input
              aria-label="Symbol"
              data-testid="momentum-symbol-input"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              onBlur={(e) => setSymbol(e.target.value.toUpperCase())}
            />
          </label>
          <label>
            <span style={{ marginRight: 8 }}>Timeframe</span>
            <select
              aria-label="Timeframe"
              data-testid="momentum-timeframe-select"
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value as Timeframe)}
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </select>
          </label>
          <ChartHistoryRangeSelect
            value={historyRange}
            onChange={handleHistoryRangeChange}
            disabled={loading}
            testId="momentum-history-range-select"
          />
          <button
            type="button"
            aria-label="Run Momentum analysis"
            data-testid="momentum-load-button"
            onClick={() => void load()}
            disabled={loading}
          >
            {loading ? "Loading..." : "Run Momentum analysis"}
          </button>
        </div>

        <div className="op-row" style={{ flexWrap: "wrap", gap: 6, marginTop: 10 }} aria-label="Momentum metadata">
          <StatusBadge tone={data?.fallback_mode ? "warn" : "good"}>
            {data ? (data.fallback_mode ? "Fallback bars" : "Provider-backed bars") : "Awaiting load"}
          </StatusBadge>
          <StatusBadge tone="neutral">Source: {data?.data_source ?? "not loaded"}</StatusBadge>
          {sessionLabel ? <StatusBadge tone="neutral">Session: {sessionLabel}</StatusBadge> : null}
          <StatusBadge tone={htfLabel.tone}>{htfLabel.label}</StatusBadge>
          {data?.higher_timeframe ? <StatusBadge tone="neutral">HTF: {data.higher_timeframe}</StatusBadge> : null}
          <StatusBadge tone={parityLabel.tone}>{parityLabel.label}</StatusBadge>
        </div>
      </Card>

      {error ? (
        <div data-testid="momentum-workspace-error">
          <ErrorState title="Momentum workspace unavailable" hint={error} />
        </div>
      ) : null}

      <Card title="Price + Momentum Intelligence layers">
        <p style={{ margin: "6px 0", color: "#9fb0c3", fontSize: "0.85rem" }}>
          One canonical time axis spans all five panels. Markers describe deterministic context only — they are not buy or sell instructions.
        </p>
        <PanelHeading title="Price" hint="Primary candles" />
        <div style={{ marginBottom: 4 }}>
          <CandleStatusBadges
            snapshot={data?.visual_parity_snapshot ?? null}
            testId="workspace-candle-status-badges"
          />
        </div>
        <div ref={priceRef} role="img" aria-label="Price candles" style={{ minHeight: 200 }} />
        <PanelHeading title="True Momentum vs EMA" hint="Lower-pane lines (green=above EMA, red=below)" />
        <div style={{ marginBottom: 4 }}>
          <TrueMomentumPanelStatusBadges
            snapshot={data?.visual_parity_snapshot ?? null}
            testId="workspace-true-momentum-status-badges"
          />
        </div>
        <div ref={trueMomentumRef} role="img" aria-label="True Momentum and EMA panel" style={{ minHeight: 90 }} />
        <PanelHeading title="HiLo SlowD vs SlowD_X" hint="Stochastic cycle context" />
        <div style={{ marginBottom: 4 }}>
          <HiloPanelStatusBadges
            snapshot={data?.visual_parity_snapshot ?? null}
            testId="workspace-hilo-status-badges"
          />
        </div>
        <div ref={hiloRef} role="img" aria-label="HiLo SlowD and SlowD X panel" style={{ minHeight: 90 }} />
        <PanelHeading title="Composite total score" hint="Histogram (-130…+130)" />
        <div ref={scoreRef} role="img" aria-label="Composite score histogram" style={{ minHeight: 80 }} />
        <PanelHeading title="HiLo thrust strip" hint="Bullish / bearish / neutral" />
        <div ref={thrustRef} role="img" aria-label="HiLo thrust strip" style={{ minHeight: 60 }} />
        <div style={{ marginTop: 8 }}>
          <MomentumContextLegend testId="workspace-context-legend" />
        </div>
      </Card>

      <MomentumSummaryPanel payload={data} loading={loading} error={error} title="Momentum Intelligence snapshot" />
    </main>
  );
}
