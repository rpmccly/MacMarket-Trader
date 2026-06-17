import { describe, expect, it } from "vitest";
import { LineType } from "lightweight-charts";

import {
  ATR_TRAILING_STOP_COLORS,
  applyIndicatorsToChart,
  buildAtrTrailingStopDisplayModel,
  buildWorkflowIndicatorModel,
  FIRST_CLASS_WORKFLOW_INDICATORS,
  HACO_CONTEXT_SUPPORTED_INDICATORS,
} from "@/lib/chart-indicators";
import type { IndicatorId } from "@/lib/indicator-framework";

type SeriesRecorder = { kind: string; options?: Record<string, unknown>; data: unknown[] };

function buildChartRecorder() {
  const series: SeriesRecorder[] = [];
  const scaleCalls: Array<{ id: string; options: Record<string, unknown> }> = [];
  const events: Array<{ type: "series" | "scale"; id?: string }> = [];
  return {
    series,
    scaleCalls,
    events,
    chart: {
      addLineSeries: (options?: Record<string, unknown>) => {
        const record: SeriesRecorder = { kind: "line", options, data: [] };
        series.push(record);
        events.push({ type: "series", id: String(options?.priceScaleId ?? "") });
        return { setData: (data: unknown[]) => { record.data = data; } };
      },
      addHistogramSeries: (options?: Record<string, unknown>) => {
        const record: SeriesRecorder = { kind: "histogram", options, data: [] };
        series.push(record);
        events.push({ type: "series", id: String(options?.priceScaleId ?? "") });
        return { setData: (data: unknown[]) => { record.data = data; } };
      },
      priceScale: (id: string) => ({
        applyOptions: (options: Record<string, unknown>) => {
          scaleCalls.push({ id, options });
          events.push({ type: "scale", id });
        },
      }),
    },
  };
}

const candles = Array.from({ length: 240 }).map((_, idx) => ({
  time: `2026-01-${String((idx % 28) + 1).padStart(2, "0")}` as unknown as number,
  open: 100 + idx * 0.25,
  high: 101 + idx * 0.25,
  low: 99 + idx * 0.25,
  close: 100 + idx * 0.3,
  volume: 1_000_000 + idx * 1_000,
}));

const flipCloses = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 118, 112, 104, 96, 92, 94, 98, 104, 110];
const flipCandles = flipCloses.map((close, idx) => {
  const open = idx === 0 ? close : flipCloses[idx - 1];
  return {
    time: idx + 1,
    open,
    high: Math.max(open, close) + 1,
    low: Math.min(open, close) - 1,
    close,
    volume: 1_000_000,
  };
});

describe("applyIndicatorsToChart", () => {
  it("keeps HACO context indicator contract restricted to rendered strips", () => {
    expect(HACO_CONTEXT_SUPPORTED_INDICATORS).toEqual(["haco", "hacolt"]);
    expect(HACO_CONTEXT_SUPPORTED_INDICATORS.every((item) => !FIRST_CLASS_WORKFLOW_INDICATORS.includes(item))).toBe(true);
    expect(FIRST_CLASS_WORKFLOW_INDICATORS).toContain("atr");
  });

  it("renders first-class workflow indicators with data-bearing series", () => {
    const { chart, series, scaleCalls, events } = buildChartRecorder();
    const selected: IndicatorId[] = ["volume", "sma20", "sma50", "ema20", "ema50", "ema200", "vwap", "atr", "bollinger", "prior_day_levels", "rsi"];
    const result = applyIndicatorsToChart(chart as never, candles as never, selected);

    expect(series.length).toBeGreaterThanOrEqual(13);
    expect(series.some((entry) => entry.kind === "histogram" && entry.data.length === candles.length)).toBe(true);
    expect(series.some((entry) => entry.options?.priceScaleId === "rsi" && entry.data.length > 0)).toBe(true);
    expect(series.some((entry) => entry.kind === "line" && entry.options?.lineType === LineType.WithSteps && entry.options?.priceScaleId === undefined)).toBe(true);
    expect(series.some((entry) => entry.kind === "line" && entry.data.some((point) => (point as { color?: string }).color === ATR_TRAILING_STOP_COLORS.long))).toBe(true);
    expect(scaleCalls.some((call) => call.id === "volume")).toBe(true);
    expect(scaleCalls.some((call) => call.id === "rsi")).toBe(true);
    expect(events.findIndex((event) => event.type === "series" && event.id === "rsi")).toBeLessThan(
      events.findIndex((event) => event.type === "scale" && event.id === "rsi"),
    );
    expect(result.legendEntries.some((entry) => entry.label === "SMA 20" && entry.latestValue != null)).toBe(true);
    expect(result.legendEntries.some((entry) => entry.label === "RSI 14" && entry.pane === "momentum")).toBe(true);
    expect(result.legendEntries.some((entry) => entry.label === "ATR Long Stop" && entry.pane === "price")).toBe(true);
  });

  it("builds separate panel descriptors for price, volume, and momentum studies", () => {
    const model = buildWorkflowIndicatorModel(candles as never, ["volume", "sma20", "atr", "bollinger", "rsi"]);
    expect(model.priceOverlays.some((entry) => entry.label === "SMA 20")).toBe(true);
    expect(model.priceOverlays.some((entry) => entry.id === "atr" && entry.lineType === LineType.WithSteps)).toBe(true);
    expect(model.volumePanel?.label).toBe("Volume");
    expect(model.momentumPanels[0]?.label).toBe("RSI 14");
    expect(model.momentumPanels[0]?.guides?.map((entry) => entry.value)).toEqual([70, 50, 30]);
  });

  it("renders ATR trailing stop as state-colored price-overlay segments only", () => {
    const model = buildWorkflowIndicatorModel(flipCandles as never, ["atr"]);
    const atrModel = buildAtrTrailingStopDisplayModel(flipCandles as never);
    const states = new Set(atrModel.points.map((point) => point.state));
    const atrOverlays = model.priceOverlays.filter((entry) => entry.id === "atr");
    const atrOverlay = atrOverlays[0];
    const overlayColors = new Set(atrOverlay?.points.map((point) => point.color));

    expect(states).toEqual(new Set(["long", "short"]));
    expect(atrModel.segments.some((entry) => entry.state === "long")).toBe(true);
    expect(atrModel.segments.some((entry) => entry.state === "short")).toBe(true);
    expect(atrOverlays).toHaveLength(1);
    expect(atrOverlay?.label).toBe("ATR Trailing Stop");
    expect(overlayColors).toContain(ATR_TRAILING_STOP_COLORS.long);
    expect(overlayColors).toContain(ATR_TRAILING_STOP_COLORS.short);
    expect(atrOverlays.every((entry) => entry.pane === "price" && entry.lineType === LineType.WithSteps)).toBe(true);
    expect(model.volumePanel).toBeNull();
    expect(model.momentumPanels).toEqual([]);
  });

  it("keeps ATR signal polarity independent of candle up/down color", () => {
    const atrModel = buildAtrTrailingStopDisplayModel(flipCandles as never);
    const longDownCandle = atrModel.points[11];
    const shortUpCandle = atrModel.points[16];

    expect(flipCandles[11].close).toBeLessThan(flipCandles[11].open);
    expect(longDownCandle.state).toBe("long");
    expect(longDownCandle.value).toBeLessThan(longDownCandle.close);
    expect(flipCandles[16].close).toBeGreaterThan(flipCandles[16].open);
    expect(shortUpCandle.state).toBe("short");
    expect(shortUpCandle.value).toBeGreaterThan(shortUpCandle.close);
  });
});
