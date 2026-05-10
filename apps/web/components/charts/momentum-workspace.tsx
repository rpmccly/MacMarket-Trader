"use client";

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
  fetchMomentumChart,
  type MomentumChartPayload,
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
  if (marker.direction === "buy") return { position: "belowBar", color: COLORS.bull, shape: "arrowUp" };
  if (marker.direction === "sell") return { position: "aboveBar", color: COLORS.bear, shape: "arrowDown" };
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

export function MomentumWorkspace() {
  const [symbol, setSymbol] = useState("AAPL");
  const [timeframe, setTimeframe] = useState<Timeframe>("1D");
  const [data, setData] = useState<MomentumChartPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const priceRef = useRef<HTMLDivElement | null>(null);
  const trueMomentumRef = useRef<HTMLDivElement | null>(null);
  const hiloRef = useRef<HTMLDivElement | null>(null);
  const scoreRef = useRef<HTMLDivElement | null>(null);
  const thrustRef = useRef<HTMLDivElement | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchMomentumChart({ symbol, timeframe });
      setData(payload);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load Momentum chart.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
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
    priceSeries.setData(candles);

    if (data.markers.length > 0) {
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

    const trueMomentumLine: LineData<Time>[] = data.true_momentum_line.map((p) => ({ time: p.time as Time, value: p.value }));
    const trueMomentumEmaLine: LineData<Time>[] = data.true_momentum_ema_line.map((p) => ({ time: p.time as Time, value: p.value }));
    if (trueMomentumLine.length > 0) {
      const tm = trueChart.addLineSeries({ color: COLORS.trueMomentum, lineWidth: 2 });
      tm.setData(trueMomentumLine);
    }
    if (trueMomentumEmaLine.length > 0) {
      const tmEma = trueChart.addLineSeries({ color: COLORS.trueMomentumEma, lineWidth: 2 });
      tmEma.setData(trueMomentumEmaLine);
    }

    const slowDLine: LineData<Time>[] = data.hilo_slowd_line.map((p) => ({ time: p.time as Time, value: p.value }));
    const slowDXLine: LineData<Time>[] = data.hilo_slowd_x_line.map((p) => ({ time: p.time as Time, value: p.value }));
    if (slowDLine.length > 0) {
      const sd = hiloChart.addLineSeries({ color: COLORS.slowD, lineWidth: 2 });
      sd.setData(slowDLine);
    }
    if (slowDXLine.length > 0) {
      const sdx = hiloChart.addLineSeries({ color: COLORS.slowDX, lineWidth: 2 });
      sdx.setData(slowDXLine);
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
        if (!range || syncing) return;
        syncing = true;
        for (const chart of charts) {
          if (chart === source) continue;
          chart.timeScale().setVisibleLogicalRange(range);
        }
        syncing = false;
      });
    };
    for (const chart of charts) syncFrom(chart);
    priceChart.timeScale().fitContent();

    return () => {
      for (const chart of charts) chart.remove();
    };
  }, [data]);

  const sessionLabel = data?.session_policy ? data.session_policy.replaceAll("_", " ") : null;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <Card>
        <h2 style={{ margin: 0 }}>Momentum Intelligence workspace</h2>
        <p style={{ marginBottom: 0, color: "#9fb0c3" }}>
          Source: <StatusBadge tone={data?.fallback_mode ? "warn" : "good"}>{data?.data_source ?? "not loaded"}</StatusBadge>
          {sessionLabel ? <> · <StatusBadge tone="neutral">Session: {sessionLabel}</StatusBadge></> : null}
          {data?.higher_timeframe ? <> · <StatusBadge tone="neutral">HTF: {data.higher_timeframe}</StatusBadge></> : null}
          {" "}· deterministic context only — no trade approval, ranking, or sizing influence.
        </p>
      </Card>

      <div className="op-row">
        <label>
          Symbol{" "}
          <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} style={{ marginLeft: 8 }} />
        </label>
        <label>
          Timeframe{" "}
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value as Timeframe)}
            style={{ marginLeft: 8 }}
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>
        <button onClick={() => void load()} disabled={loading}>
          {loading ? "Loading..." : "Run Momentum analysis"}
        </button>
      </div>

      {error ? <ErrorState title="Momentum workspace unavailable" hint={error} /> : null}

      <Card title="Price + Momentum Intelligence layers">
        <p style={{ margin: "6px 0", color: "#9fb0c3", fontSize: "0.85rem" }}>
          Price candles, True Momentum (green) vs EMA (red), HiLo SlowD (blue) vs SlowD_X (purple), composite score histogram, and thrust strip share one canonical time axis.
        </p>
        <div ref={priceRef} />
        <div style={{ marginTop: 6, fontSize: "0.78rem", color: "var(--op-muted, #7a8999)" }}>True Momentum / EMA</div>
        <div ref={trueMomentumRef} />
        <div style={{ marginTop: 6, fontSize: "0.78rem", color: "var(--op-muted, #7a8999)" }}>HiLo SlowD / SlowD_X</div>
        <div ref={hiloRef} />
        <div style={{ marginTop: 6, fontSize: "0.78rem", color: "var(--op-muted, #7a8999)" }}>Composite Total Score</div>
        <div ref={scoreRef} />
        <div style={{ marginTop: 6, fontSize: "0.78rem", color: "var(--op-muted, #7a8999)" }}>HiLo Thrust strip</div>
        <div ref={thrustRef} />
      </Card>

      <MomentumSummaryPanel payload={data} loading={loading} error={error} />
    </div>
  );
}
