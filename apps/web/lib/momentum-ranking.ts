import type {
  MomentumRankingContribution,
  MomentumRankingMode,
} from "@/lib/recommendations";

export type MomentumRankingTone = "good" | "warn" | "bad" | "neutral";

export const MOMENTUM_RANKING_DETERMINISTIC_NOTE =
  "Momentum ranking contribution is bounded deterministic context. It does not approve, reject, size, or route trades.";

export function normalizeMomentumRankingMode(value: unknown): MomentumRankingMode {
  if (value === "off" || value === "shadow" || value === "active") return value;
  if (typeof value === "string") {
    const lower = value.trim().toLowerCase();
    if (lower === "off" || lower === "shadow" || lower === "active") return lower;
  }
  // Permissive: anything we don't recognize is treated as the safest mode.
  return "off";
}

export function momentumRankingModeLabel(mode: unknown): string {
  switch (normalizeMomentumRankingMode(mode)) {
    case "off":
      return "Off — not computed";
    case "shadow":
      return "Shadow — computed, not applied";
    case "active":
      return "Active — applied to ranking";
  }
}

export function isMomentumContributionApplied(
  contribution: MomentumRankingContribution | null | undefined,
): boolean {
  if (!contribution) return false;
  if (contribution.applied === true) return true;
  if (normalizeMomentumRankingMode(contribution.mode) === "active") {
    // Defensive: some serializers may omit `applied` even in active mode.
    return Number(contribution.total_contribution ?? 0) !== 0;
  }
  return false;
}

export function isMomentumContributionShadow(
  contribution: MomentumRankingContribution | null | undefined,
): boolean {
  if (!contribution) return false;
  return normalizeMomentumRankingMode(contribution.mode) === "shadow" && contribution.enabled !== false;
}

export function momentumRankingAppliedLabel(
  contribution: MomentumRankingContribution | null | undefined,
): string {
  if (!contribution) return "Not available";
  const mode = normalizeMomentumRankingMode(contribution.mode);
  if (mode === "off" || contribution.enabled === false) return "Not computed";
  if (mode === "shadow") return "Computed — final score unchanged";
  if (mode === "active") {
    return isMomentumContributionApplied(contribution)
      ? "Bounded contribution applied to ranking"
      : "Computed — bounded contribution not applied";
  }
  return "Not available";
}

export function formatMomentumContribution(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const rounded = Math.round(value * 100) / 100;
  if (rounded === 0) return "0.00";
  return rounded > 0 ? `+${rounded.toFixed(2)}` : rounded.toFixed(2);
}

export function momentumContributionTone(
  contribution: MomentumRankingContribution | null | undefined,
): MomentumRankingTone {
  if (!contribution) return "neutral";
  if (contribution.reversal_warning || contribution.no_trade_warning) return "warn";
  if (normalizeMomentumRankingMode(contribution.mode) === "off") return "neutral";
  const effective = isMomentumContributionApplied(contribution)
    ? contribution.total_contribution
    : contribution.shadow_contribution;
  if (effective == null || Number.isNaN(effective)) return "neutral";
  if (effective >= 5) return "good";
  if (effective <= -5) return "bad";
  if (effective > 0 || effective < 0) return "warn";
  return "neutral";
}

export function summarizeMomentumContribution(
  contribution: MomentumRankingContribution | null | undefined,
): string {
  if (!contribution || contribution.enabled === false) {
    return "Momentum ranking context unavailable.";
  }
  const mode = normalizeMomentumRankingMode(contribution.mode);
  const value = isMomentumContributionApplied(contribution)
    ? contribution.total_contribution
    : contribution.shadow_contribution;
  const label = mode === "active" ? "applied" : "shadow";
  return `${momentumRankingModeLabel(mode)} · ${label} ${formatMomentumContribution(value)}`;
}

const REASON_CODE_LABELS: Record<string, string> = {
  thinkorswim_parity_pending: "Thinkorswim parity pending",
  derived_higher_timeframe: "Derived higher timeframe",
  direction_unknown: "Direction unknown",
  momentum_payload_unavailable: "Momentum payload unavailable",
  momentum_no_trade_warning: "No-trade warning",
  momentum_reversal_warning: "Reversal warning",
  momentum_pullback_signal: "Pullback signal",
  active_blocked_parity_required: "Active blocked — parity required",
  // Phase B4.2 — direction inference reason codes.
  direction_from_candidate_metadata: "Direction from candidate metadata",
  direction_from_strategy_metadata: "Direction from strategy metadata",
  bullish_strategy_direction_inferred: "Bullish strategy direction inferred",
  direction_inferred_from_strategy: "Direction inferred from strategy",
};

export function getMomentumContributionReasonLabels(
  reasonCodes: ReadonlyArray<string> | null | undefined,
): string[] {
  if (!reasonCodes || reasonCodes.length === 0) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const code of reasonCodes) {
    if (typeof code !== "string" || !code.trim()) continue;
    const labelled = REASON_CODE_LABELS[code] ?? code.replaceAll("_", " ");
    if (seen.has(labelled)) continue;
    seen.add(labelled);
    out.push(labelled);
  }
  return out;
}

export function hasMomentumRankingWarnings(
  contribution: MomentumRankingContribution | null | undefined,
): boolean {
  if (!contribution) return false;
  if (contribution.reversal_warning === true) return true;
  if (contribution.no_trade_warning === true) return true;
  return false;
}

export type MomentumRankingComponentRow = {
  label: string;
  value: string;
  tone: MomentumRankingTone;
  hint: string;
};

export function buildMomentumRankingBreakdown(
  contribution: MomentumRankingContribution | null | undefined,
): MomentumRankingComponentRow[] {
  if (!contribution || contribution.enabled === false) return [];
  const components: Array<{ label: string; value: number | null | undefined; hint: string; positiveOnly?: boolean }> = [
    {
      label: "Momentum alignment",
      value: contribution.momentum_alignment_score,
      hint: "Bull/bear state agreement with the inferred direction (cap +10).",
      positiveOnly: true,
    },
    {
      label: "Trend alignment",
      value: contribution.trend_alignment_score,
      hint: "Trend-score magnitude when its sign agrees with direction (cap +8).",
      positiveOnly: true,
    },
    {
      label: "HiLo confirmation",
      value: contribution.hilo_confirmation_bonus,
      hint: "HiLo composite agreement with direction (cap +5).",
      positiveOnly: true,
    },
    {
      label: "Reversal warning penalty",
      value: contribution.reversal_warning_penalty,
      hint: "Capped negative penalty when a reversal warning is active (floor -12).",
    },
  ];
  return components.map((row) => ({
    label: row.label,
    value: formatMomentumContribution(row.value ?? 0),
    tone: signedTone(row.value, row.positiveOnly),
    hint: row.hint,
  }));
}

function signedTone(value: number | null | undefined, positiveOnly = false): MomentumRankingTone {
  if (value == null || Number.isNaN(value)) return "neutral";
  if (value > 0) return "good";
  if (value < 0) return positiveOnly ? "neutral" : "bad";
  return "neutral";
}

export function momentumScoreContextRow(
  contribution: MomentumRankingContribution | null | undefined,
): { totalScore: string; totalLabel: string; trend: string; momo: string } {
  if (!contribution) return { totalScore: "—", totalLabel: "—", trend: "—", momo: "—" };
  return {
    totalScore: contribution.total_score == null ? "—" : formatMomentumContribution(contribution.total_score),
    totalLabel: contribution.total_label ?? "—",
    trend: contribution.trend_score == null ? "—" : formatMomentumContribution(contribution.trend_score),
    momo: contribution.momo_score == null ? "—" : formatMomentumContribution(contribution.momo_score),
  };
}
