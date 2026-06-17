import { LineStyle, LineType, type CandlestickData, type HistogramData, type IChartApi, type Time } from "lightweight-charts";

import type { IndicatorId } from "@/lib/indicator-framework";

type NumericPoint = { time: Time; value: number; color?: string };
type AtrTrailingStopState = "long" | "short";

export type IndicatorPane = "price" | "volume" | "momentum";

export type IndicatorLegendEntry = {
  id: IndicatorId;
  label: string;
  color: string;
  pane: IndicatorPane;
  latestValue: number | null;
  valuesByTime: Map<string, number>;
};

export type IndicatorLineDescriptor = {
  id: IndicatorId;
  label: string;
  color: string;
  pane: IndicatorPane;
  points: NumericPoint[];
  lineWidth?: number;
  lineStyle?: LineStyle;
  lineType?: LineType;
  priceScaleId?: string;
  lastValueVisible?: boolean;
  priceLineVisible?: boolean;
  fixedRange?: { minValue: number; maxValue: number };
};

export type IndicatorGuideDescriptor = {
  label: string;
  color: string;
  value: number;
  lineStyle?: LineStyle;
};

export type IndicatorHistogramDescriptor = {
  id: IndicatorId;
  label: string;
  pane: IndicatorPane;
  color: string;
  data: HistogramData<Time>[];
};

export type IndicatorPanelDescriptor = {
  id: IndicatorId;
  label: string;
  pane: Exclude<IndicatorPane, "price">;
  scaleId: string;
  lines: IndicatorLineDescriptor[];
  guides?: IndicatorGuideDescriptor[];
};

export type IndicatorRenderResult = {
  legendEntries: IndicatorLegendEntry[];
  priceOverlays: IndicatorLineDescriptor[];
  volumePanel: IndicatorHistogramDescriptor | null;
  momentumPanels: IndicatorPanelDescriptor[];
};

export const ATR_TRAILING_STOP_DISPLAY_DEFAULTS = {
  trailType: "modified",
  atrPeriod: 9,
  atrFactor: 2.9,
  firstTrade: "long",
  averageType: "exponential",
} as const;

export const ATR_TRAILING_STOP_COLORS: Record<AtrTrailingStopState, string> = {
  long: "#35d07f",
  short: "#ff6f91",
};

export type AtrTrailingStopDisplayPoint = NumericPoint & {
  close: number;
  state: AtrTrailingStopState;
};

export type AtrTrailingStopDisplaySegment = {
  state: AtrTrailingStopState;
  points: NumericPoint[];
};

export type AtrTrailingStopDisplayModel = {
  points: AtrTrailingStopDisplayPoint[];
  segments: AtrTrailingStopDisplaySegment[];
};

export const FIRST_CLASS_WORKFLOW_INDICATORS: IndicatorId[] = [
  "volume",
  "sma20",
  "sma50",
  "ema20",
  "ema50",
  "ema200",
  "vwap",
  "atr",
  "bollinger",
  "prior_day_levels",
  "rsi",
];

export const HACO_CONTEXT_SUPPORTED_INDICATORS: IndicatorId[] = ["haco", "hacolt"];

function timeKey(time: Time): string {
  if (typeof time === "number" || typeof time === "string") return String(time);
  return `${time.year}-${String(time.month).padStart(2, "0")}-${String(time.day).padStart(2, "0")}`;
}

function sma(values: number[], period: number): Array<number | null> {
  return values.map((_, idx) => {
    if (idx < period - 1) return null;
    const slice = values.slice(idx - period + 1, idx + 1);
    return slice.reduce((acc, item) => acc + item, 0) / period;
  });
}

function ema(values: number[], period: number): Array<number | null> {
  const multiplier = 2 / (period + 1);
  const output: Array<number | null> = [];
  let prev: number | null = null;
  values.forEach((value, idx) => {
    if (idx < period - 1) {
      output.push(null);
      return;
    }
    if (prev === null) {
      const seed = values.slice(idx - period + 1, idx + 1).reduce((acc, item) => acc + item, 0) / period;
      prev = seed;
      output.push(seed);
      return;
    }
    const next = (value - prev) * multiplier + prev;
    prev = next;
    output.push(next);
  });
  return output;
}

function buildSeries(times: Time[], values: Array<number | null>): NumericPoint[] {
  return values
    .map((value, idx) => (value == null ? null : ({ time: times[idx], value })))
    .filter((item): item is NumericPoint => item !== null);
}

function buildLegendEntry(
  id: IndicatorId,
  label: string,
  color: string,
  pane: IndicatorLegendEntry["pane"],
  points: NumericPoint[],
): IndicatorLegendEntry {
  return {
    id,
    label,
    color,
    pane,
    latestValue: points.at(-1)?.value ?? null,
    valuesByTime: new Map(points.map((point) => [timeKey(point.time), point.value])),
  };
}

function calculateVwap(closes: number[], highs: number[], lows: number[], volumes: number[]): Array<number | null> {
  let cumulativeTpv = 0;
  let cumulativeVolume = 0;
  return closes.map((close, idx) => {
    const volume = volumes[idx] ?? 0;
    const typicalPrice = ((highs[idx] ?? close) + (lows[idx] ?? close) + close) / 3;
    cumulativeTpv += typicalPrice * volume;
    cumulativeVolume += volume;
    if (cumulativeVolume <= 0) return null;
    return cumulativeTpv / cumulativeVolume;
  });
}

function calculateBollinger(closes: number[], period = 20) {
  const mid: Array<number | null> = [];
  const upper: Array<number | null> = [];
  const lower: Array<number | null> = [];
  closes.forEach((_, idx) => {
    if (idx < period - 1) {
      mid.push(null);
      upper.push(null);
      lower.push(null);
      return;
    }
    const slice = closes.slice(idx - period + 1, idx + 1);
    const mean = slice.reduce((acc, item) => acc + item, 0) / period;
    const variance = slice.reduce((acc, item) => acc + (item - mean) ** 2, 0) / period;
    const sigma = Math.sqrt(variance);
    mid.push(mean);
    upper.push(mean + 2 * sigma);
    lower.push(mean - 2 * sigma);
  });
  return { mid, upper, lower };
}

function seededEma(values: number[], period: number): number[] {
  if (values.length === 0) return [];
  const multiplier = 2 / (period + 1);
  const output = [values[0]];
  for (let idx = 1; idx < values.length; idx += 1) {
    output.push(values[idx] * multiplier + output[idx - 1] * (1 - multiplier));
  }
  return output;
}

function rollingSimple(values: number[], period: number): number[] {
  const output: number[] = [];
  let running = 0;
  for (let idx = 0; idx < values.length; idx += 1) {
    running += values[idx];
    if (idx >= period) running -= values[idx - period];
    output.push(running / Math.min(idx + 1, period));
  }
  return output;
}

function calculateModifiedTrueRange(highs: number[], lows: number[], closes: number[], period: number): number[] {
  const highLow = highs.map((high, idx) => high - lows[idx]);
  const highLowAverage = rollingSimple(highLow, period);
  return highs.map((high, idx) => {
    const low = lows[idx];
    if (idx === 0) return Math.max(0, high - low);
    const prevClose = closes[idx - 1];
    const prevHigh = highs[idx - 1];
    const prevLow = lows[idx - 1];
    const hiLo = Math.min(high - low, 1.5 * highLowAverage[idx]);
    const hRef = low <= prevHigh ? high - prevClose : high - prevClose - 0.5 * (low - prevHigh);
    const lRef = high >= prevLow ? prevClose - low : prevClose - low - 0.5 * (prevLow - high);
    return Math.max(hiLo, hRef, lRef);
  });
}

function isFiniteNumber(value: number): boolean {
  return Number.isFinite(value) && !Number.isNaN(value);
}

function segmentAtrTrailingStop(points: AtrTrailingStopDisplayPoint[]): AtrTrailingStopDisplaySegment[] {
  const segments: AtrTrailingStopDisplaySegment[] = [];
  let activeState: AtrTrailingStopState | null = null;
  let activePoints: NumericPoint[] = [];

  for (const point of points) {
    if (activeState !== point.state) {
      if (activeState && activePoints.length > 0) {
        segments.push({ state: activeState, points: activePoints });
      }
      activeState = point.state;
      activePoints = [];
    }
    activePoints.push({ time: point.time, value: point.value });
  }

  if (activeState && activePoints.length > 0) {
    segments.push({ state: activeState, points: activePoints });
  }

  return segments;
}

// Frontend-only display model for workflow charts. ATR Intel and Agent Mode
// continue to use the frozen backend ATR engine and persisted backend defaults.
export function buildAtrTrailingStopDisplayModel(candles: CandlestickData<Time>[]): AtrTrailingStopDisplayModel {
  const highs = candles.map((item) => Number(item.high));
  const lows = candles.map((item) => Number(item.low));
  const closes = candles.map((item) => Number(item.close));
  if (
    candles.length === 0 ||
    !highs.every(isFiniteNumber) ||
    !lows.every(isFiniteNumber) ||
    !closes.every(isFiniteNumber)
  ) {
    return { points: [], segments: [] };
  }

  const { atrPeriod, atrFactor, firstTrade } = ATR_TRAILING_STOP_DISPLAY_DEFAULTS;
  const trueRanges = calculateModifiedTrueRange(highs, lows, closes, atrPeriod);
  const losses = seededEma(trueRanges, atrPeriod).map((value) => value * atrFactor);
  const points: AtrTrailingStopDisplayPoint[] = [];

  let previousState: AtrTrailingStopState | null = null;
  let previousTrail: number | null = null;

  for (let idx = 0; idx < candles.length; idx += 1) {
    const close = closes[idx];
    const loss = losses[idx];
    let state: AtrTrailingStopState;
    let trail: number;

    if (!previousState || previousTrail == null) {
      state = firstTrade;
      trail = state === "long" ? close - loss : close + loss;
    } else if (previousState === "long") {
      if (close > previousTrail) {
        state = "long";
        trail = Math.max(previousTrail, close - loss);
      } else {
        state = "short";
        trail = close + loss;
      }
    } else if (close < previousTrail) {
      state = "short";
      trail = Math.min(previousTrail, close + loss);
    } else {
      state = "long";
      trail = close - loss;
    }

    points.push({
      time: candles[idx].time,
      value: Number(trail.toFixed(6)),
      close,
      state,
    });
    previousState = state;
    previousTrail = trail;
  }

  return { points, segments: segmentAtrTrailingStop(points) };
}

function calculateRsi(closes: number[], period = 14): Array<number | null> {
  if (closes.length === 0) return [];
  const gains: number[] = [0];
  const losses: number[] = [0];
  for (let idx = 1; idx < closes.length; idx += 1) {
    const delta = closes[idx] - closes[idx - 1];
    gains.push(Math.max(delta, 0));
    losses.push(Math.max(-delta, 0));
  }
  let avgGain = 0;
  let avgLoss = 0;
  const out: Array<number | null> = closes.map(() => null);
  for (let idx = 1; idx < closes.length; idx += 1) {
    if (idx <= period) {
      avgGain += gains[idx];
      avgLoss += losses[idx];
      if (idx === period) {
        avgGain /= period;
        avgLoss /= period;
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        out[idx] = 100 - 100 / (1 + rs);
      }
      continue;
    }
    avgGain = (avgGain * (period - 1) + gains[idx]) / period;
    avgLoss = (avgLoss * (period - 1) + losses[idx]) / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    out[idx] = 100 - 100 / (1 + rs);
  }
  return out;
}

export function buildWorkflowIndicatorModel(
  candles: CandlestickData<Time>[],
  selectedIndicators: IndicatorId[],
): IndicatorRenderResult {
  const legendEntries: IndicatorLegendEntry[] = [];
  const priceOverlays: IndicatorLineDescriptor[] = [];
  const momentumPanels: IndicatorPanelDescriptor[] = [];
  const times = candles.map((item) => item.time);
  const opens = candles.map((item) => Number(item.open));
  const highs = candles.map((item) => Number(item.high));
  const lows = candles.map((item) => Number(item.low));
  const closes = candles.map((item) => Number(item.close));

  let volumePanel: IndicatorHistogramDescriptor | null = null;

  if (selectedIndicators.includes("volume")) {
    const data: HistogramData<Time>[] = candles.map((item, idx) => ({
      time: item.time,
      value: Number((item as { volume?: number }).volume ?? 0),
      color: closes[idx] >= opens[idx] ? "#2c9f5d" : "#b24f4f",
    }));
    volumePanel = {
      id: "volume",
      label: "Volume",
      pane: "volume",
      color: "#54708b",
      data,
    };
    legendEntries.push(buildLegendEntry("volume", "Volume", "#54708b", "volume", data.map((item) => ({ time: item.time, value: Number(item.value) }))));
  }

  if (selectedIndicators.includes("sma20")) {
    const points = buildSeries(times, sma(closes, 20));
    priceOverlays.push({ id: "sma20", label: "SMA 20", color: "#ffd166", pane: "price", points, lineWidth: 2 });
    legendEntries.push(buildLegendEntry("sma20", "SMA 20", "#ffd166", "price", points));
  }
  if (selectedIndicators.includes("sma50")) {
    const points = buildSeries(times, sma(closes, 50));
    priceOverlays.push({ id: "sma50", label: "SMA 50", color: "#ff9f6e", pane: "price", points, lineWidth: 2 });
    legendEntries.push(buildLegendEntry("sma50", "SMA 50", "#ff9f6e", "price", points));
  }
  if (selectedIndicators.includes("ema20")) {
    const points = buildSeries(times, ema(closes, 20));
    priceOverlays.push({ id: "ema20", label: "EMA 20", color: "#5ab0ff", pane: "price", points, lineWidth: 2 });
    legendEntries.push(buildLegendEntry("ema20", "EMA 20", "#5ab0ff", "price", points));
  }
  if (selectedIndicators.includes("ema50")) {
    const points = buildSeries(times, ema(closes, 50));
    priceOverlays.push({ id: "ema50", label: "EMA 50", color: "#9d7dff", pane: "price", points, lineWidth: 2 });
    legendEntries.push(buildLegendEntry("ema50", "EMA 50", "#9d7dff", "price", points));
  }
  if (selectedIndicators.includes("ema200")) {
    const points = buildSeries(times, ema(closes, 200));
    priceOverlays.push({ id: "ema200", label: "EMA 200", color: "#f2c96d", pane: "price", points, lineWidth: 2 });
    legendEntries.push(buildLegendEntry("ema200", "EMA 200", "#f2c96d", "price", points));
  }

  if (selectedIndicators.includes("vwap")) {
    const volumes = candles.map((item) => Number((item as { volume?: number }).volume ?? 0));
    const points = buildSeries(times, calculateVwap(closes, highs, lows, volumes));
    priceOverlays.push({ id: "vwap", label: "VWAP", color: "#4dd0c6", pane: "price", points, lineWidth: 2 });
    legendEntries.push(buildLegendEntry("vwap", "VWAP", "#4dd0c6", "price", points));
  }

  if (selectedIndicators.includes("atr")) {
    const atrModel = buildAtrTrailingStopDisplayModel(candles);
    const coloredPoints: NumericPoint[] = atrModel.points.map((point) => ({
      time: point.time,
      value: point.value,
      color: ATR_TRAILING_STOP_COLORS[point.state],
    }));
    if (coloredPoints.length > 0) {
      priceOverlays.push({
        id: "atr",
        label: "ATR Trailing Stop",
        color: coloredPoints.at(-1)?.color ?? ATR_TRAILING_STOP_COLORS.long,
        pane: "price",
        points: coloredPoints,
        lineWidth: 2,
        lineType: LineType.WithSteps,
        priceLineVisible: false,
      });
    }
    const longPoints = atrModel.points.filter((point) => point.state === "long");
    const shortPoints = atrModel.points.filter((point) => point.state === "short");
    if (longPoints.length > 0) {
      legendEntries.push(buildLegendEntry("atr", "ATR Long Stop", ATR_TRAILING_STOP_COLORS.long, "price", longPoints));
    }
    if (shortPoints.length > 0) {
      legendEntries.push(buildLegendEntry("atr", "ATR Short Stop", ATR_TRAILING_STOP_COLORS.short, "price", shortPoints));
    }
  }

  if (selectedIndicators.includes("bollinger")) {
    const bands = calculateBollinger(closes, 20);
    const upperPoints = buildSeries(times, bands.upper);
    const midPoints = buildSeries(times, bands.mid);
    const lowerPoints = buildSeries(times, bands.lower);
    priceOverlays.push({ id: "bollinger", label: "BB Upper", color: "#7eb6ff", pane: "price", points: upperPoints, lineWidth: 1, lineStyle: LineStyle.Dashed });
    priceOverlays.push({ id: "bollinger", label: "BB Mid", color: "#6f7786", pane: "price", points: midPoints, lineWidth: 1, lineStyle: LineStyle.Dashed });
    priceOverlays.push({ id: "bollinger", label: "BB Lower", color: "#7eb6ff", pane: "price", points: lowerPoints, lineWidth: 1, lineStyle: LineStyle.Dashed });
    legendEntries.push(buildLegendEntry("bollinger", "BB Upper", "#7eb6ff", "price", upperPoints));
    legendEntries.push(buildLegendEntry("bollinger", "BB Mid", "#6f7786", "price", midPoints));
    legendEntries.push(buildLegendEntry("bollinger", "BB Lower", "#7eb6ff", "price", lowerPoints));
  }

  if (selectedIndicators.includes("prior_day_levels") && candles.length > 1) {
    const prevHigh: Array<number | null> = [null];
    const prevLow: Array<number | null> = [null];
    for (let idx = 1; idx < candles.length; idx += 1) {
      prevHigh.push(highs[idx - 1]);
      prevLow.push(lows[idx - 1]);
    }
    const prevHighPoints = buildSeries(times, prevHigh);
    const prevLowPoints = buildSeries(times, prevLow);
    priceOverlays.push({ id: "prior_day_levels", label: "Prev High", color: "#f29f67", pane: "price", points: prevHighPoints, lineWidth: 1, lineStyle: LineStyle.Dotted });
    priceOverlays.push({ id: "prior_day_levels", label: "Prev Low", color: "#f29f67", pane: "price", points: prevLowPoints, lineWidth: 1, lineStyle: LineStyle.Dotted });
    legendEntries.push(buildLegendEntry("prior_day_levels", "Prev High", "#f29f67", "price", prevHighPoints));
    legendEntries.push(buildLegendEntry("prior_day_levels", "Prev Low", "#f29f67", "price", prevLowPoints));
  }

  if (selectedIndicators.includes("rsi")) {
    const rsiPoints = buildSeries(times, calculateRsi(closes));
    momentumPanels.push({
      id: "rsi",
      label: "RSI 14",
      pane: "momentum",
      scaleId: "rsi",
      lines: [
        {
          id: "rsi",
          label: "RSI 14",
          color: "#b9a0ff",
          pane: "momentum",
          points: rsiPoints,
          lineWidth: 2,
          priceScaleId: "rsi",
          lastValueVisible: false,
          priceLineVisible: false,
          fixedRange: { minValue: 0, maxValue: 100 },
        },
      ],
      guides: [
        { label: "RSI 70", value: 70, color: "#6b7080", lineStyle: LineStyle.Dotted },
        { label: "RSI 50", value: 50, color: "#5d6574", lineStyle: LineStyle.Dashed },
        { label: "RSI 30", value: 30, color: "#6b7080", lineStyle: LineStyle.Dotted },
      ],
    });
    legendEntries.push(buildLegendEntry("rsi", "RSI 14", "#b9a0ff", "momentum", rsiPoints));
  }

  return { legendEntries, priceOverlays, volumePanel, momentumPanels };
}

export function applyIndicatorsToChart(
  chart: IChartApi,
  candles: CandlestickData<Time>[],
  selectedIndicators: IndicatorId[],
): IndicatorRenderResult {
  const model = buildWorkflowIndicatorModel(candles, selectedIndicators);

  if (model.volumePanel) {
    const volumeSeries = chart.addHistogramSeries({
      priceScaleId: "volume",
      priceFormat: { type: "volume" },
      color: model.volumePanel.color,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.72, bottom: 0 } });
    volumeSeries.setData(model.volumePanel.data);
  }

  for (const overlay of model.priceOverlays) {
    chart
      .addLineSeries({
        color: overlay.color,
        lineWidth: (overlay.lineWidth ?? 2) as 1 | 2 | 3 | 4,
        lineStyle: overlay.lineStyle,
        lineType: overlay.lineType,
        priceScaleId: overlay.priceScaleId,
        lastValueVisible: overlay.lastValueVisible,
        priceLineVisible: overlay.priceLineVisible,
      })
      .setData(overlay.points);
  }

  for (const panel of model.momentumPanels) {
    let panelScaleCreated = false;
    for (const line of panel.lines) {
      chart
        .addLineSeries({
          color: line.color,
          lineWidth: (line.lineWidth ?? 2) as 1 | 2 | 3 | 4,
          lineStyle: line.lineStyle,
          lineType: line.lineType,
          priceScaleId: line.priceScaleId,
          lastValueVisible: line.lastValueVisible,
          priceLineVisible: line.priceLineVisible,
        })
        .setData(line.points);
      panelScaleCreated = true;
    }
    for (const guide of panel.guides ?? []) {
      chart
        .addLineSeries({
          color: guide.color,
          lineWidth: 1,
          lineStyle: guide.lineStyle,
          priceScaleId: panel.scaleId,
          lastValueVisible: false,
          priceLineVisible: false,
        })
        .setData(candles.map((candle) => ({ time: candle.time, value: guide.value })));
      panelScaleCreated = true;
    }
    if (panelScaleCreated) {
      chart.priceScale(panel.scaleId).applyOptions({ scaleMargins: { top: 0.82, bottom: 0.05 }, autoScale: false });
    }
  }

  return model;
}
