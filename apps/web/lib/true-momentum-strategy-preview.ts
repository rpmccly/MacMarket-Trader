// Phase C1 — True Momentum strategy-family research-preview classifier
// (frontend mirror).
//
// Pure, side-effect-free helpers that classify the already-loaded
// recommendation queue into the three planned True Momentum families
// (continuation / pullback / reversal-watch). This module never mutates
// the source candidates, never fetches market data, never approves /
// rejects / sizes / routes trades, and never generates new queue
// candidates. The backend evaluator at
// ``src/macmarket_trader/recommendation/true_momentum_strategy_families.py``
// applies the same rules — this helper exists so the Recommendations
// page can render the preview locally without an HTTP round-trip.

import type { QueueCandidate } from "@/lib/recommendations";
import type { TrueMomentumStrategyFamilyStatus } from "@/lib/true-momentum-strategy-families";

export type TrueMomentumStrategyPreviewFamilyId =
  | "true_momentum_continuation"
  | "true_momentum_pullback"
  | "true_momentum_reversal_watch";

export type TrueMomentumStrategyPreviewMatchStrength =
  | "strong"
  | "moderate"
  | "watch"
  | "blocked";

export const TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE =
  "True Momentum strategy previews are research-only. They do not generate queue candidates, approve, reject, size, or route trades.";

export const TRUE_MOMENTUM_STRATEGY_PREVIEW_PHASE = "C1";
export const TRUE_MOMENTUM_STRATEGY_PREVIEW_IMPLEMENTATION_STATUS = "research_preview";

const FAMILY_LABELS: Record<TrueMomentumStrategyPreviewFamilyId, string> = {
  true_momentum_continuation: "True Momentum Continuation",
  true_momentum_pullback: "True Momentum Pullback",
  true_momentum_reversal_watch: "True Momentum Reversal / Weakening Watch",
};

export function familyPreviewLabel(
  id: TrueMomentumStrategyPreviewFamilyId | string | null | undefined,
): string {
  if (id == null) return "Unknown";
  if (typeof id === "string" && id in FAMILY_LABELS) {
    return FAMILY_LABELS[id as TrueMomentumStrategyPreviewFamilyId];
  }
  return String(id);
}

const MATCH_STRENGTH_TONES: Record<
  TrueMomentumStrategyPreviewMatchStrength,
  "good" | "warn" | "bad" | "neutral"
> = {
  strong: "good",
  moderate: "neutral",
  watch: "warn",
  blocked: "neutral",
};

export function trueMomentumPreviewTone(
  strength: TrueMomentumStrategyPreviewMatchStrength | string | null | undefined,
): "good" | "warn" | "bad" | "neutral" {
  if (strength == null) return "neutral";
  if (typeof strength === "string" && strength in MATCH_STRENGTH_TONES) {
    return MATCH_STRENGTH_TONES[strength as TrueMomentumStrategyPreviewMatchStrength];
  }
  return "neutral";
}

const REASON_LABELS: Record<string, string> = {
  true_momentum_continuation_match: "Continuation pattern match",
  true_momentum_pullback_match: "Pullback pattern match",
  true_momentum_reversal_watch_match: "Reversal / weakening watch",
  momentum_no_trade_warning: "No-trade warning",
  momentum_reversal_warning: "Reversal warning",
  momentum_pullback_signal_active: "Pullback signal active",
  momentum_total_label_bullish: "Total label bullish",
  momentum_total_score_strong: "Total score ≥ 80",
  trend_alignment_long_confirmed: "Trend alignment long",
  momo_score_long_confirmed: "Momo score ≥ 70",
  strategy_is_pullback_or_trend_continuation: "Source strategy is pullback / trend continuation",
  bear_total_label_long_strategy_contradiction:
    "Bear total label on long-biased strategy",
  bear_total_score_long_strategy_contradiction:
    "Deeply bearish total score on long-biased strategy",
  thinkorswim_parity_pending: "Thinkorswim parity pending",
  derived_higher_timeframe: "Derived higher timeframe",
  direction_unknown: "Direction unknown",
  active_mode_blocked_by_safety_guard:
    "Active mode blocked by safety guard",
  score_consistency_corrected: "Score consistency corrected",
  true_momentum_strategy_mode_disabled:
    "Phase C1 research preview disabled — set MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=research_preview and the guard env",
  true_momentum_strategy_active_mode_not_implemented:
    "Active Phase C is not implemented — degraded to research preview",
  true_momentum_preview_no_candidates: "No preview rows for the supplied candidates",
};

export function trueMomentumPreviewReasonLabels(codes: ReadonlyArray<string>): string[] {
  return codes.map((code) => REASON_LABELS[code] ?? code.replaceAll("_", " "));
}

export type TrueMomentumStrategyPreviewCandidate = {
  preview_id: string;
  family_id: TrueMomentumStrategyPreviewFamilyId;
  family_label: string;
  symbol: string;
  strategy: string;
  rank: number;
  baseline_score: number;
  active_score: number;
  raw_contribution: number;
  applied_delta: number;
  total_score: number | null;
  total_label: string | null;
  trend_score: number | null;
  momo_score: number | null;
  inferred_direction: "long" | "short" | "unknown";
  pullback_signal: boolean;
  reversal_warning: boolean;
  no_trade_warning: boolean;
  reason_codes: string[];
  operational_caveats: string[];
  match_strength: TrueMomentumStrategyPreviewMatchStrength;
  research_notes: string[];
  non_actionable: true;
};

export type TrueMomentumStrategyPreviewSummary = {
  candidate_count: number;
  preview_count: number;
  continuation_count: number;
  pullback_count: number;
  reversal_watch_count: number;
  strong_count: number;
  moderate_count: number;
  watch_count: number;
  blocked_count: number;
  parity_pending_count: number;
  derived_higher_timeframe_count: number;
  operational_caveat_count: number;
};

export type TrueMomentumStrategyPreviewResult = {
  status: TrueMomentumStrategyFamilyStatus | null;
  previews: TrueMomentumStrategyPreviewCandidate[];
  previews_generated: boolean;
  summary: TrueMomentumStrategyPreviewSummary;
  preview_phase: string;
  preview_implementation_status: string;
  deterministic_note: string;
  extra_reason_codes: string[];
};

// ── Number sanitization ──────────────────────────────────────────────

function sanitizeFinite(value: unknown, fallback = 0): number {
  if (value == null) return fallback;
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num) || !Number.isFinite(num)) return fallback;
  return num;
}

function sanitizeOptionalNumber(value: unknown): number | null {
  if (value == null) return null;
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num) || !Number.isFinite(num)) return null;
  return num;
}

function sanitizeOptionalInt(value: unknown): number | null {
  const num = sanitizeOptionalNumber(value);
  return num == null ? null : Math.trunc(num);
}

function clampUnit(value: number): number {
  if (!Number.isFinite(value) || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function safeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === "string");
}

// ── Candidate normalization ──────────────────────────────────────────

type NormalizedCandidate = {
  symbol: string;
  strategy: string;
  strategyLower: string;
  rank: number;
  baselineScore: number;
  activeScore: number;
  rawContribution: number;
  appliedDelta: number;
  totalScore: number | null;
  totalLabel: string | null;
  trendScore: number | null;
  momoScore: number | null;
  inferredDirection: "long" | "short" | "unknown";
  pullbackSignal: boolean;
  reversalWarning: boolean;
  noTradeWarning: boolean;
  reasonCodes: string[];
  operationalCaveats: string[];
};

const STRATEGY_LONG_HINTS = [
  "event continuation",
  "event_continuation",
  "breakout",
  "pullback",
  "trend",
  "haco",
  "continuation",
];

function normalizeCandidate(candidate: QueueCandidate | null | undefined): NormalizedCandidate | null {
  if (!candidate) return null;
  const symbol = typeof candidate.symbol === "string" ? candidate.symbol.trim() : "";
  const strategy = typeof candidate.strategy === "string" ? candidate.strategy.trim() : "";
  if (!symbol || !strategy) return null;
  const contribution = candidate.momentum_contribution ?? null;
  const rawCurrent = sanitizeFinite(
    candidate.score_after_momentum ?? candidate.score,
    sanitizeFinite(candidate.score, 0),
  );
  const activeScore = clampUnit(rawCurrent);
  const baselineFromCandidate = candidate.score_before_momentum;
  const baselineScore = clampUnit(
    sanitizeFinite(baselineFromCandidate, activeScore),
  );
  let appliedDelta = sanitizeFinite(candidate.momentum_score_delta, 0);
  let rawContribution = 0;
  let totalScore: number | null = null;
  let totalLabel: string | null = null;
  let trendScore: number | null = null;
  let momoScore: number | null = null;
  let inferredDirection: "long" | "short" | "unknown" = "unknown";
  let pullbackSignal = false;
  let reversalWarning = false;
  let noTradeWarning = false;
  let reasonCodes: string[] = [];
  const operationalCaveats: string[] = [];

  if (contribution) {
    rawContribution = sanitizeFinite(
      contribution.raw_total_contribution ?? contribution.shadow_contribution,
      0,
    );
    const contributionDelta = sanitizeOptionalNumber(contribution.applied_score_delta);
    if (contributionDelta != null) appliedDelta = contributionDelta;
    totalScore = sanitizeOptionalInt(contribution.total_score);
    if (typeof contribution.total_label === "string") {
      totalLabel = contribution.total_label.trim();
    }
    trendScore = sanitizeOptionalNumber(contribution.trend_score);
    momoScore = sanitizeOptionalNumber(contribution.momo_score);
    if (
      contribution.inferred_direction === "long" ||
      contribution.inferred_direction === "short" ||
      contribution.inferred_direction === "unknown"
    ) {
      inferredDirection = contribution.inferred_direction;
    }
    pullbackSignal = !!contribution.pullback_signal;
    reversalWarning = !!contribution.reversal_warning;
    noTradeWarning = !!contribution.no_trade_warning;
    reasonCodes = safeStringList(contribution.reason_codes);
    if (reasonCodes.includes("thinkorswim_parity_pending")) {
      operationalCaveats.push("thinkorswim_parity_pending");
    }
    if (reasonCodes.includes("derived_higher_timeframe")) {
      operationalCaveats.push("derived_higher_timeframe");
    }
    if (reasonCodes.includes("direction_unknown")) {
      operationalCaveats.push("direction_unknown");
    }
    if (reasonCodes.includes("active_mode_blocked_by_safety_guard")) {
      operationalCaveats.push("active_mode_blocked_by_safety_guard");
    }
    if (candidate.score_consistency_status === "corrected") {
      operationalCaveats.push("score_consistency_corrected");
    }
  }

  return {
    symbol,
    strategy,
    strategyLower: strategy.toLowerCase(),
    rank: Math.trunc(sanitizeFinite(candidate.rank, 0)),
    baselineScore,
    activeScore,
    rawContribution,
    appliedDelta,
    totalScore,
    totalLabel,
    trendScore,
    momoScore,
    inferredDirection,
    pullbackSignal,
    reversalWarning,
    noTradeWarning,
    reasonCodes,
    operationalCaveats,
  };
}

// ── Classification helpers ───────────────────────────────────────────

function labelIsBullish(label: string | null): boolean {
  if (!label) return false;
  const lower = label.trim().toLowerCase();
  return lower === "bull" || lower === "max bull";
}

function labelIsBearish(label: string | null): boolean {
  if (!label) return false;
  const lower = label.trim().toLowerCase();
  return lower === "bear" || lower === "max bear";
}

function strategyIsLongBiased(strategyLower: string): boolean {
  if (!strategyLower) return false;
  return STRATEGY_LONG_HINTS.some((hint) => strategyLower.includes(hint));
}

function strategyIsPullback(strategyLower: string): boolean {
  return (
    strategyLower.includes("pullback") || strategyLower.includes("trend continuation")
  );
}

type ClassificationResult =
  | {
      familyId: TrueMomentumStrategyPreviewFamilyId;
      matchStrength: TrueMomentumStrategyPreviewMatchStrength;
      reasons: string[];
      notes: string[];
    }
  | null;

function classifyReversalWatch(norm: NormalizedCandidate): ClassificationResult {
  const reasons: string[] = [];
  const notes: string[] = [];
  const longBiased =
    norm.inferredDirection === "long" || strategyIsLongBiased(norm.strategyLower);
  let matched = false;
  if (norm.reversalWarning) {
    matched = true;
    reasons.push("momentum_reversal_warning");
    notes.push("Reversal warning is active on the source candidate.");
  }
  if (norm.noTradeWarning) {
    matched = true;
    reasons.push("momentum_no_trade_warning");
    notes.push("No-trade warning is active on the source candidate.");
  }
  if (longBiased && labelIsBearish(norm.totalLabel)) {
    matched = true;
    reasons.push("bear_total_label_long_strategy_contradiction");
    notes.push("Long-biased strategy carries a Bear / Max Bear Momentum total label.");
  }
  if (longBiased && norm.totalScore != null && norm.totalScore <= -50) {
    matched = true;
    reasons.push("bear_total_score_long_strategy_contradiction");
    notes.push(
      `Long-biased strategy carries a deeply bearish Momentum total score (${norm.totalScore}).`,
    );
  }
  if (!matched) return null;
  reasons.push("true_momentum_reversal_watch_match");
  notes.push("Watch-only — never proposes an entry, stop, or order.");
  return {
    familyId: "true_momentum_reversal_watch",
    matchStrength: "watch",
    reasons,
    notes,
  };
}

function classifyPullback(norm: NormalizedCandidate): ClassificationResult {
  if (norm.noTradeWarning || norm.reversalWarning) return null;
  if (norm.inferredDirection !== "long") return null;
  if (labelIsBearish(norm.totalLabel)) return null;
  const labelBullish = labelIsBullish(norm.totalLabel);
  const scoreStrong = norm.totalScore != null && norm.totalScore >= 80;
  if (!labelBullish && !scoreStrong) return null;
  if (norm.rawContribution <= 0) return null;
  const pullbackByStrategy = strategyIsPullback(norm.strategyLower);
  if (!norm.pullbackSignal && !pullbackByStrategy) return null;
  const reasons: string[] = ["true_momentum_pullback_match"];
  const notes: string[] = [];
  if (norm.pullbackSignal) {
    reasons.push("momentum_pullback_signal_active");
    notes.push("Deterministic pullback signal is active.");
  }
  if (pullbackByStrategy) {
    reasons.push("strategy_is_pullback_or_trend_continuation");
    notes.push("Source strategy is Pullback / Trend Continuation aligned.");
  }
  if (labelBullish) notes.push(`Momentum total label is ${norm.totalLabel}.`);
  if (scoreStrong) notes.push(`Momentum total score is ${norm.totalScore} (≥ 80).`);
  notes.push("Research preview only — no entry / stop / target is proposed.");
  const matchStrength: TrueMomentumStrategyPreviewMatchStrength =
    norm.pullbackSignal && labelBullish ? "strong" : "moderate";
  return {
    familyId: "true_momentum_pullback",
    matchStrength,
    reasons,
    notes,
  };
}

function classifyContinuation(norm: NormalizedCandidate): ClassificationResult {
  if (norm.noTradeWarning || norm.reversalWarning) return null;
  if (norm.inferredDirection === "short") return null;
  const longBiased =
    norm.inferredDirection === "long" || strategyIsLongBiased(norm.strategyLower);
  if (!longBiased) return null;
  if (labelIsBearish(norm.totalLabel)) return null;
  const labelBullish = labelIsBullish(norm.totalLabel);
  const scoreStrong = norm.totalScore != null && norm.totalScore >= 80;
  if (!labelBullish && !scoreStrong) return null;
  if (norm.rawContribution <= 0) return null;
  const reasons: string[] = ["true_momentum_continuation_match"];
  const notes: string[] = [];
  if (labelBullish) {
    reasons.push("momentum_total_label_bullish");
    notes.push(`Momentum total label is ${norm.totalLabel}.`);
  }
  if (scoreStrong) {
    reasons.push("momentum_total_score_strong");
    notes.push(`Momentum total score is ${norm.totalScore} (≥ 80).`);
  }
  const trendStrong = norm.trendScore != null && norm.trendScore >= 70;
  const momoStrong = norm.momoScore != null && norm.momoScore >= 70;
  if (trendStrong) {
    reasons.push("trend_alignment_long_confirmed");
    notes.push(`Trend score is ${norm.trendScore?.toFixed(0)} (≥ 70).`);
  }
  if (momoStrong) {
    reasons.push("momo_score_long_confirmed");
    notes.push(`Momo score is ${norm.momoScore?.toFixed(0)} (≥ 70).`);
  }
  notes.push("Research preview only — no entry / stop / target is proposed.");
  const matchStrength: TrueMomentumStrategyPreviewMatchStrength =
    trendStrong && momoStrong ? "strong" : "moderate";
  return {
    familyId: "true_momentum_continuation",
    matchStrength,
    reasons,
    notes,
  };
}

function dedupe(values: ReadonlyArray<string>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    if (seen.has(value)) continue;
    seen.add(value);
    out.push(value);
  }
  return out;
}

function buildPreviewRow(
  norm: NormalizedCandidate,
  classification: NonNullable<ClassificationResult>,
): TrueMomentumStrategyPreviewCandidate {
  return {
    preview_id: `preview::${classification.familyId}::${norm.symbol}::${norm.strategy}::${norm.rank}`,
    family_id: classification.familyId,
    family_label: familyPreviewLabel(classification.familyId),
    symbol: norm.symbol,
    strategy: norm.strategy,
    rank: norm.rank,
    baseline_score: norm.baselineScore,
    active_score: norm.activeScore,
    raw_contribution: norm.rawContribution,
    applied_delta: norm.appliedDelta,
    total_score: norm.totalScore,
    total_label: norm.totalLabel,
    trend_score: norm.trendScore,
    momo_score: norm.momoScore,
    inferred_direction: norm.inferredDirection,
    pullback_signal: norm.pullbackSignal,
    reversal_warning: norm.reversalWarning,
    no_trade_warning: norm.noTradeWarning,
    reason_codes: dedupe(classification.reasons),
    operational_caveats: norm.operationalCaveats.slice(),
    match_strength: classification.matchStrength,
    research_notes: classification.notes.slice(),
    non_actionable: true,
  };
}

function emptySummary(candidateCount = 0): TrueMomentumStrategyPreviewSummary {
  return {
    candidate_count: candidateCount,
    preview_count: 0,
    continuation_count: 0,
    pullback_count: 0,
    reversal_watch_count: 0,
    strong_count: 0,
    moderate_count: 0,
    watch_count: 0,
    blocked_count: 0,
    parity_pending_count: 0,
    derived_higher_timeframe_count: 0,
    operational_caveat_count: 0,
  };
}

/**
 * Build a Phase C1 research-preview result from the existing
 * Recommendations queue and the resolved Phase C0 status.
 *
 * Disabled effective mode → returns no previews. Research preview →
 * runs the classifier with precedence reversal_watch > pullback >
 * continuation, one preview row per candidate. Active mode is still
 * reserved; ``status.effective_mode`` will already be ``research_preview``
 * if the C0 helper degraded it.
 */
export function buildTrueMomentumStrategyPreview(
  candidates: ReadonlyArray<QueueCandidate> | null | undefined,
  status: TrueMomentumStrategyFamilyStatus | null | undefined,
): TrueMomentumStrategyPreviewResult {
  const safeCandidates = Array.isArray(candidates)
    ? candidates.filter((c): c is QueueCandidate => !!c && typeof c === "object")
    : [];
  const extraReasonCodes: string[] = [];
  const previews: TrueMomentumStrategyPreviewCandidate[] = [];

  const effectiveMode = status?.effective_mode ?? "disabled";

  if (effectiveMode === "disabled") {
    extraReasonCodes.push("true_momentum_strategy_mode_disabled");
    if (status?.requested_mode === "active") {
      extraReasonCodes.push("true_momentum_strategy_active_mode_not_implemented");
    }
    return {
      status: status ?? null,
      previews: [],
      previews_generated: false,
      summary: emptySummary(safeCandidates.length),
      preview_phase: TRUE_MOMENTUM_STRATEGY_PREVIEW_PHASE,
      preview_implementation_status: TRUE_MOMENTUM_STRATEGY_PREVIEW_IMPLEMENTATION_STATUS,
      deterministic_note: TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE,
      extra_reason_codes: extraReasonCodes,
    };
  }

  for (const raw of safeCandidates) {
    const norm = normalizeCandidate(raw);
    if (!norm) continue;
    const rw = classifyReversalWatch(norm);
    if (rw) {
      previews.push(buildPreviewRow(norm, rw));
      continue;
    }
    const pb = classifyPullback(norm);
    if (pb) {
      previews.push(buildPreviewRow(norm, pb));
      continue;
    }
    const ct = classifyContinuation(norm);
    if (ct) {
      previews.push(buildPreviewRow(norm, ct));
      continue;
    }
  }

  const summary = summarizeTrueMomentumStrategyPreview(previews, safeCandidates.length);
  if (status?.requested_mode === "active") {
    extraReasonCodes.push("true_momentum_strategy_active_mode_not_implemented");
  }
  if (previews.length === 0) {
    extraReasonCodes.push("true_momentum_preview_no_candidates");
  }

  return {
    status: status ?? null,
    previews,
    previews_generated: true,
    summary,
    preview_phase: TRUE_MOMENTUM_STRATEGY_PREVIEW_PHASE,
    preview_implementation_status: TRUE_MOMENTUM_STRATEGY_PREVIEW_IMPLEMENTATION_STATUS,
    deterministic_note: TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE,
    extra_reason_codes: extraReasonCodes,
  };
}

export function summarizeTrueMomentumStrategyPreview(
  previews: ReadonlyArray<TrueMomentumStrategyPreviewCandidate>,
  candidateCount: number = previews.length,
): TrueMomentumStrategyPreviewSummary {
  const summary = emptySummary(candidateCount);
  summary.preview_count = previews.length;
  for (const p of previews) {
    if (p.family_id === "true_momentum_continuation") summary.continuation_count += 1;
    else if (p.family_id === "true_momentum_pullback") summary.pullback_count += 1;
    else if (p.family_id === "true_momentum_reversal_watch") summary.reversal_watch_count += 1;
    if (p.match_strength === "strong") summary.strong_count += 1;
    else if (p.match_strength === "moderate") summary.moderate_count += 1;
    else if (p.match_strength === "watch") summary.watch_count += 1;
    else if (p.match_strength === "blocked") summary.blocked_count += 1;
    if (p.operational_caveats.includes("thinkorswim_parity_pending")) {
      summary.parity_pending_count += 1;
    }
    if (p.operational_caveats.includes("derived_higher_timeframe")) {
      summary.derived_higher_timeframe_count += 1;
    }
    if (p.operational_caveats.length > 0) summary.operational_caveat_count += 1;
  }
  return summary;
}
