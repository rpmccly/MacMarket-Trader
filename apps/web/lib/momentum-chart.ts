import type {
  ChartTime,
  MomentumChartPayload,
  MomentumHiloThrustState,
  MomentumLinePoint,
  MomentumPanelMarker,
  MomentumScoreSnapshot,
  MomentumVisualParityPoint,
  MomentumVisualParitySnapshot,
} from "@/lib/momentum-api";

export type MomentumTone = "good" | "warn" | "bad" | "neutral";

export type MomentumLegendValue = {
  label: string;
  value: string;
  tone: MomentumTone;
};

export function momentumScoreTone(totalScore: number | null | undefined): MomentumTone {
  if (totalScore == null || Number.isNaN(totalScore)) return "neutral";
  if (totalScore >= 75) return "good";
  if (totalScore <= -75) return "bad";
  if (totalScore >= 45 || totalScore <= -45) return "warn";
  return "neutral";
}

export function formatMomentumScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const rounded = Math.round(value);
  return rounded > 0 ? `+${rounded}` : `${rounded}`;
}

export function formatMomentumValue(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

export function summarizeMomentumSnapshot(snapshot: MomentumScoreSnapshot | null | undefined): string {
  if (!snapshot) return "Momentum context unavailable.";
  const score = formatMomentumScore(snapshot.total_score);
  const trend = formatMomentumScore(snapshot.trend_score);
  const momo = formatMomentumScore(snapshot.momo_score);
  return `${snapshot.total_label} ${score} · Trend ${trend} · Momo ${momo}`;
}

export function hasMomentumWarning(payload: MomentumChartPayload | null | undefined): boolean {
  if (!payload) return false;
  if (payload.explanation?.reversal_warning) return true;
  if (payload.explanation?.no_trade_warning) return true;
  return false;
}

export function getLatestMomentumSnapshot(payload: MomentumChartPayload | null | undefined): MomentumScoreSnapshot | null {
  if (!payload) return null;
  return payload.latest_snapshot ?? payload.explanation?.snapshot ?? null;
}

export function buildMomentumLegendValues(payload: MomentumChartPayload | null | undefined): MomentumLegendValue[] {
  const snapshot = getLatestMomentumSnapshot(payload);
  if (!snapshot) {
    return [
      { label: "Total Score", value: "—", tone: "neutral" },
      { label: "Trend Score", value: "—", tone: "neutral" },
      { label: "Momo Score", value: "—", tone: "neutral" },
    ];
  }
  const cb = snapshot.component_breakdown;
  return [
    { label: "Total Score", value: formatMomentumScore(snapshot.total_score), tone: momentumScoreTone(snapshot.total_score) },
    { label: "Trend Score", value: formatMomentumScore(snapshot.trend_score), tone: momentumScoreTone(snapshot.trend_score) },
    { label: "Momo Score", value: formatMomentumScore(snapshot.momo_score), tone: momentumScoreTone(snapshot.momo_score) },
    { label: "True Momentum", value: formatMomentumValue(snapshot.true_momentum), tone: "neutral" },
    { label: "True Momentum EMA", value: formatMomentumValue(snapshot.true_momentum_ema), tone: "neutral" },
    { label: "True Momentum Score", value: formatMomentumScore(snapshot.true_momentum_score), tone: signedTone(snapshot.true_momentum_score) },
    { label: "HiLo Thrust", value: formatMomentumScore(snapshot.hilo_thrust), tone: signedTone(snapshot.hilo_thrust) },
    { label: "HiLo Score", value: formatMomentumScore(snapshot.hilo_score), tone: signedTone(snapshot.hilo_score) },
    { label: "ATR Bias", value: formatMomentumScore(cb.atr_value), tone: signedTone(cb.atr_value) },
    { label: "MACD Bias", value: formatMomentumScore(cb.macd_bias), tone: signedTone(cb.macd_bias) },
    { label: "MA Bias", value: formatMomentumScore(snapshot.ma_bias), tone: signedTone(snapshot.ma_bias) },
  ];
}

function signedTone(value: number | null | undefined): MomentumTone {
  if (value == null || Number.isNaN(value)) return "neutral";
  if (value > 0) return "good";
  if (value < 0) return "bad";
  return "neutral";
}

export function normalizeMomentumTimeKey(time: ChartTime | null | undefined): string {
  if (time == null) return "";
  return String(time);
}

export type HigherTimeframeSourceLabel = {
  label: string;
  tone: MomentumTone;
};

export function describeHigherTimeframeSource(value: string | null | undefined): HigherTimeframeSourceLabel {
  if (value === "provided_higher_timeframe_bars") return { label: "Provided HTF bars", tone: "good" };
  if (value === "derived_from_chart_bars") return { label: "HTF derived from chart bars", tone: "neutral" };
  if (value === "insufficient_data") return { label: "HTF insufficient data", tone: "warn" };
  return { label: value ? value.replaceAll("_", " ") : "HTF source unavailable", tone: "neutral" };
}

export type ParityStatusLabel = {
  label: string;
  tone: MomentumTone;
};

export function describeParityStatus(value: string | null | undefined): ParityStatusLabel {
  if (value === "validated_against_thinkorswim_fixture") return { label: "Parity validated", tone: "good" };
  if (value === "pending_thinkorswim_fixture_validation") return { label: "Parity pending Thinkorswim fixtures", tone: "neutral" };
  return { label: value ?? "Parity unknown", tone: "neutral" };
}

export const MOMENTUM_DETERMINISTIC_NOTE =
  "Momentum Intelligence is deterministic context only in Phase A. It does not approve, reject, size, or rank trades.";

// ── Visual parity chart polish helpers ──────────────────────────────

export type VisualParityBadge = {
  /** Stable id for keying. */
  id: string;
  label: string;
  /** Display value already formatted for the badge ("—" when unavailable). */
  value: string;
  tone: MomentumTone;
  /** True when the underlying value was unavailable so the UI can mark it. */
  unavailable: boolean;
};

export function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)}%`;
}

function thrustStateLabel(state: MomentumHiloThrustState | null | undefined): string {
  if (state === "bullish") return "Confirmed";
  if (state === "bearish") return "Deconfirmed";
  if (state === "neutral") return "Neutral";
  return "—";
}

function thrustStateTone(state: MomentumHiloThrustState | null | undefined): MomentumTone {
  if (state === "bullish") return "good";
  if (state === "bearish") return "bad";
  return "neutral";
}

function totalLabelTone(label: string | null | undefined): MomentumTone {
  if (!label) return "neutral";
  const lower = label.toLowerCase();
  if (lower.includes("max bull") || lower === "bull") return "good";
  if (lower.includes("max bear") || lower === "bear") return "bad";
  if (lower.includes("neutral up") || lower.includes("neutral down")) return "warn";
  return "neutral";
}

/**
 * Build the compact top-left badge row for the candle panel from a
 * visual parity snapshot. Hover-aware callers should pass the result
 * of {@link findVisualParityForTime} (or fall back to the latest
 * snapshot) here.
 *
 * IV% is rendered as "IV% —" with `unavailable=true` when the
 * snapshot does not carry a deterministic IV source.
 */
export function buildCandleStatusBadges(
  snapshot: MomentumVisualParitySnapshot | MomentumVisualParityPoint | null | undefined,
): VisualParityBadge[] {
  if (!snapshot) {
    return [
      { id: "iv", label: "IV%", value: "—", tone: "neutral", unavailable: true },
      { id: "total_label", label: "Total", value: "—", tone: "neutral", unavailable: true },
      { id: "trend", label: "Trend", value: "—", tone: "neutral", unavailable: true },
      { id: "momo", label: "Momo", value: "—", tone: "neutral", unavailable: true },
    ];
  }
  const iv = "iv_percent" in snapshot ? snapshot.iv_percent : null;
  const unavailable = "unavailable_fields" in snapshot ? snapshot.unavailable_fields : [];
  const ivUnavailable =
    iv == null || (Array.isArray(unavailable) && unavailable.includes("iv_percent"));
  return [
    {
      id: "iv",
      label: "IV%",
      value: ivUnavailable ? "—" : formatPercent(iv),
      tone: "neutral",
      unavailable: ivUnavailable,
    },
    {
      id: "total_label",
      label: "Total",
      value: snapshot.total_label
        ? `${snapshot.total_label} ${formatMomentumScore(snapshot.total_score)}`
        : formatMomentumScore(snapshot.total_score),
      tone: totalLabelTone(snapshot.total_label),
      unavailable: snapshot.total_score == null,
    },
    {
      id: "trend",
      label: "Trend",
      value: formatMomentumScore(snapshot.trend_score),
      tone: momentumScoreTone(snapshot.trend_score),
      unavailable: snapshot.trend_score == null,
    },
    {
      id: "momo",
      label: "Momo",
      value: formatMomentumScore(snapshot.momo_score),
      tone: momentumScoreTone(snapshot.momo_score),
      unavailable: snapshot.momo_score == null,
    },
  ];
}

/**
 * Build the True Momentum panel badge row (numeric value + EMA + state
 * direction). The state tone reflects whether True Momentum is above
 * its EMA (constructive) or below (weakening).
 */
export function buildTrueMomentumPanelBadges(
  snapshot: MomentumVisualParitySnapshot | MomentumVisualParityPoint | null | undefined,
): VisualParityBadge[] {
  if (!snapshot) {
    return [
      { id: "tm_state", label: "Momentum state", value: "—", tone: "neutral", unavailable: true },
      { id: "tm_value", label: "True Momentum", value: "—", tone: "neutral", unavailable: true },
      { id: "tm_ema", label: "True Momentum EMA", value: "—", tone: "neutral", unavailable: true },
    ];
  }
  const tm = snapshot.true_momentum;
  const ema = snapshot.true_momentum_ema;
  let state: string;
  let tone: MomentumTone;
  if (tm == null || ema == null) {
    state = "—";
    tone = "neutral";
  } else if (tm > ema) {
    state = "Bullish";
    tone = "good";
  } else if (tm < ema) {
    state = "Bearish";
    tone = "bad";
  } else {
    state = "Neutral";
    tone = "neutral";
  }
  return [
    { id: "tm_state", label: "Momentum state", value: state, tone, unavailable: tm == null || ema == null },
    {
      id: "tm_value",
      label: "True Momentum",
      value: formatMomentumValue(tm),
      tone: "neutral",
      unavailable: tm == null,
    },
    {
      id: "tm_ema",
      label: "True Momentum EMA",
      value: formatMomentumValue(ema),
      tone: "neutral",
      unavailable: ema == null,
    },
  ];
}

/** Build the HiLo panel badge row from a parity snapshot. */
export function buildHiloPanelBadges(
  snapshot: MomentumVisualParitySnapshot | MomentumVisualParityPoint | null | undefined,
): VisualParityBadge[] {
  if (!snapshot) {
    return [
      { id: "hilo_state", label: "Thrust", value: "—", tone: "neutral", unavailable: true },
      { id: "hilo_value", label: "HiLo Elite", value: "—", tone: "neutral", unavailable: true },
      { id: "hilo_score", label: "HiLo score", value: "—", tone: "neutral", unavailable: true },
    ];
  }
  const state = snapshot.hilo_thrust_state ?? null;
  return [
    {
      id: "hilo_state",
      label: "Thrust",
      value: thrustStateLabel(state),
      tone: thrustStateTone(state),
      unavailable: state == null,
    },
    {
      id: "hilo_value",
      label: "HiLo Elite",
      value: formatMomentumValue(snapshot.hilo_elite_value),
      tone: "neutral",
      unavailable: snapshot.hilo_elite_value == null,
    },
    {
      id: "hilo_score",
      label: "HiLo score",
      value: formatMomentumScore(snapshot.hilo_score),
      tone: signedTone(snapshot.hilo_score),
      unavailable: snapshot.hilo_score == null,
    },
  ];
}

/** Build the parity-panel summary row used by the snapshot panel. */
export function buildVisualParityFields(
  snapshot: MomentumVisualParitySnapshot | null | undefined,
): VisualParityBadge[] {
  if (!snapshot) {
    return [];
  }
  const unavailable = snapshot.unavailable_fields;
  const ivUnavailable = snapshot.iv_percent == null || unavailable.includes("iv_percent");
  return [
    { id: "total_score", label: "Total Score", value: formatMomentumScore(snapshot.total_score), tone: momentumScoreTone(snapshot.total_score), unavailable: snapshot.total_score == null },
    { id: "total_label", label: "Total Label", value: snapshot.total_label ?? "—", tone: totalLabelTone(snapshot.total_label), unavailable: snapshot.total_label == null },
    { id: "true_momentum", label: "True Momentum", value: formatMomentumValue(snapshot.true_momentum), tone: "neutral", unavailable: snapshot.true_momentum == null },
    { id: "true_momentum_ema", label: "True Momentum EMA", value: formatMomentumValue(snapshot.true_momentum_ema), tone: "neutral", unavailable: snapshot.true_momentum_ema == null },
    { id: "hilo_elite_value", label: "HiLo Elite", value: formatMomentumValue(snapshot.hilo_elite_value), tone: "neutral", unavailable: snapshot.hilo_elite_value == null },
    { id: "hilo_thrust_state", label: "HiLo thrust", value: thrustStateLabel(snapshot.hilo_thrust_state), tone: thrustStateTone(snapshot.hilo_thrust_state), unavailable: snapshot.hilo_thrust_state == null },
    { id: "hilo_score", label: "HiLo score", value: formatMomentumScore(snapshot.hilo_score), tone: signedTone(snapshot.hilo_score), unavailable: snapshot.hilo_score == null },
    { id: "pullback_signal", label: "Pullback signal", value: snapshot.pullback_signal == null ? "—" : snapshot.pullback_signal ? "Active" : "No", tone: snapshot.pullback_signal ? "warn" : "neutral", unavailable: snapshot.pullback_signal == null },
    { id: "reversal_warning", label: "Reversal warning", value: snapshot.reversal_warning == null ? "—" : snapshot.reversal_warning ? "Active" : "No", tone: snapshot.reversal_warning ? "warn" : "neutral", unavailable: snapshot.reversal_warning == null },
    { id: "no_trade_warning", label: "No-trade warning", value: snapshot.no_trade_warning == null ? "—" : snapshot.no_trade_warning ? "Active" : "No", tone: snapshot.no_trade_warning ? "warn" : "neutral", unavailable: snapshot.no_trade_warning == null },
    { id: "iv_percent", label: "IV%", value: ivUnavailable ? "—" : formatPercent(snapshot.iv_percent), tone: "neutral", unavailable: ivUnavailable },
  ];
}

/**
 * Hover-aware lookup: return the per-bar parity point whose ``time``
 * matches the supplied key, falling back to the snapshot's
 * ``visual_parity_snapshot`` when there is no exact match.
 */
export function findVisualParityForTime(
  payload: MomentumChartPayload | null | undefined,
  time: ChartTime | null | undefined,
): MomentumVisualParityPoint | MomentumVisualParitySnapshot | null {
  if (!payload) return null;
  const series = payload.visual_parity_series ?? [];
  if (series.length === 0) {
    return payload.visual_parity_snapshot ?? null;
  }
  if (time != null) {
    const key = normalizeMomentumTimeKey(time);
    for (const point of series) {
      if (normalizeMomentumTimeKey(point.time) === key) {
        return point;
      }
    }
  }
  return payload.visual_parity_snapshot ?? series[series.length - 1] ?? null;
}

// ── True Momentum line direction splitting ──────────────────────────

export type DirectionalLineSeries = {
  bullSeries: MomentumLinePoint[];
  bearSeries: MomentumLinePoint[];
};

/**
 * Split the True Momentum and EMA series into bull / bear segments
 * for directional coloring. The reference series (default: EMA) is
 * compared against the primary series so that bullish points (primary
 * > reference) land in ``bullSeries`` and bearish points land in
 * ``bearSeries``. A null-gap is inserted into the opposite series at
 * each point so segment lines don't connect across crossover events.
 *
 * Inputs are never mutated. When the series have different lengths,
 * the shorter is honored and remaining points are placed in the bull
 * series with a null reference value.
 */
export function splitMomentumLineByDirection(
  primary: MomentumLinePoint[] | null | undefined,
  reference: MomentumLinePoint[] | null | undefined,
): DirectionalLineSeries {
  if (!primary || primary.length === 0) {
    return { bullSeries: [], bearSeries: [] };
  }
  const refByTime = new Map<string, number>();
  if (reference) {
    for (const point of reference) {
      refByTime.set(normalizeMomentumTimeKey(point.time), point.value);
    }
  }
  const bull: MomentumLinePoint[] = [];
  const bear: MomentumLinePoint[] = [];
  for (const point of primary) {
    const refValue = refByTime.get(normalizeMomentumTimeKey(point.time));
    if (refValue == null || Number.isNaN(point.value) || !Number.isFinite(point.value)) {
      bull.push({ ...point });
      continue;
    }
    if (point.value >= refValue) {
      bull.push({ ...point });
    } else {
      bear.push({ ...point });
    }
  }
  return { bullSeries: bull, bearSeries: bear };
}

// ── Panel marker label helpers ──────────────────────────────────────

const PANEL_MARKER_LABELS: Record<MomentumPanelMarker["marker_type"], string> = {
  bullish_cross: "Cross up",
  bearish_cross: "Cross down",
  hilo_confirmed: "HiLo confirmed",
  hilo_deconfirmed: "HiLo deconfirmed",
  state_transition: "State transition",
  hilo_state_transition: "HiLo transition",
};

export function formatPanelMarkerLabel(marker: MomentumPanelMarker): string {
  return PANEL_MARKER_LABELS[marker.marker_type] ?? marker.label;
}

export function panelMarkerTone(marker: MomentumPanelMarker): MomentumTone {
  if (marker.direction === "up") return "good";
  if (marker.direction === "down") return "bad";
  return "neutral";
}
