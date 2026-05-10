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
