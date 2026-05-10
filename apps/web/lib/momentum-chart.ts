import type { ChartTime, MomentumChartPayload, MomentumScoreSnapshot } from "@/lib/momentum-api";

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
