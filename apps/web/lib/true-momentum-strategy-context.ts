// Phase C4 — True Momentum strategy-family research context.
//
// Pure, side-effect-free helpers that compose the existing Phase C1
// research-preview classification, Phase C3 cohort readiness, and the
// Thinkorswim visual-attestation parity status into a single
// operator-readable context bundle for a selected Recommendations
// queue candidate.
//
// This module:
//
// - never generates queue candidates,
// - never mutates the source candidates,
// - never approves / rejects / sizes / routes trades,
// - never calls a backend, provider, or LLM,
// - never reads localStorage or other persistence,
// - and never returns "approved" or "ready for live" status.
//
// All status outputs are research readiness signals only.
//
// Used by ``components/recommendations/true-momentum-strategy-context-card.tsx``
// and the Phase C4 integration guard tests.

import type { MomentumRankingStatus } from "@/lib/momentum-ranking-status";
import type { QueueCandidate } from "@/lib/recommendations";
import type { TrueMomentumCohortReadinessStatus } from "@/lib/true-momentum-cohort-review";
import {
  buildTrueMomentumStrategyPreview,
  type TrueMomentumStrategyPreviewCandidate,
  type TrueMomentumStrategyPreviewFamilyId,
  type TrueMomentumStrategyPreviewMatchStrength,
} from "@/lib/true-momentum-strategy-preview";
import type { TrueMomentumStrategyFamilyStatus } from "@/lib/true-momentum-strategy-families";

export const TRUE_MOMENTUM_STRATEGY_CONTEXT_PHASE = "C4";
export const TRUE_MOMENTUM_STRATEGY_CONTEXT_IMPLEMENTATION_STATUS =
  "research_context_integration";

export const TRUE_MOMENTUM_STRATEGY_CONTEXT_DETERMINISTIC_NOTE =
  "True Momentum strategy context is research-only. It does not generate queue candidates, approve, reject, size, or route trades, and does not activate Phase C strategy families.";

// Activation readiness — research readiness only. Never approval.
export type TrueMomentumStrategyActivationReadiness =
  | "research_ready"
  | "needs_more_evidence"
  | "parity_blocked"
  | "composite_mismatch_review"
  | "warning_blocked"
  | "not_applicable"
  | "watch_only";

const READINESS_LABELS: Record<TrueMomentumStrategyActivationReadiness, string> = {
  research_ready: "Research-ready",
  needs_more_evidence: "Needs more evidence",
  parity_blocked: "Parity blocked",
  composite_mismatch_review: "Composite mismatch under review",
  warning_blocked: "Blocked by warning",
  not_applicable: "Not applicable",
  watch_only: "Watch-only",
};

const READINESS_TONES: Record<
  TrueMomentumStrategyActivationReadiness,
  "good" | "warn" | "bad" | "neutral"
> = {
  research_ready: "good",
  needs_more_evidence: "neutral",
  parity_blocked: "warn",
  composite_mismatch_review: "warn",
  warning_blocked: "warn",
  not_applicable: "neutral",
  watch_only: "warn",
};

export function trueMomentumStrategyActivationReadinessLabel(
  status: TrueMomentumStrategyActivationReadiness | string | null | undefined,
): string {
  if (status == null) return READINESS_LABELS.not_applicable;
  if (typeof status === "string" && status in READINESS_LABELS) {
    return READINESS_LABELS[status as TrueMomentumStrategyActivationReadiness];
  }
  return READINESS_LABELS.not_applicable;
}

export function trueMomentumStrategyActivationReadinessTone(
  status: TrueMomentumStrategyActivationReadiness | string | null | undefined,
): "good" | "warn" | "bad" | "neutral" {
  if (status == null) return "neutral";
  if (typeof status === "string" && status in READINESS_TONES) {
    return READINESS_TONES[status as TrueMomentumStrategyActivationReadiness];
  }
  return "neutral";
}

export type TrueMomentumStrategyTriggerChecklistItemStatus =
  | "pass"
  | "fail"
  | "warning"
  | "unavailable";

export type TrueMomentumStrategyTriggerChecklistItem = {
  id: string;
  label: string;
  status: TrueMomentumStrategyTriggerChecklistItemStatus;
  reason: string;
  source_field?: string;
};

export type TrueMomentumStrategyTriggerChecklist = {
  family_id: TrueMomentumStrategyPreviewFamilyId;
  items: TrueMomentumStrategyTriggerChecklistItem[];
  summary: {
    total: number;
    pass: number;
    warning: number;
    fail: number;
    unavailable: number;
  };
  research_ready_for_family: boolean;
};

export type TrueMomentumStrategyParityCaveatStatus =
  | "passed"
  | "failed"
  | "partial"
  | "not_covered"
  | "global_mixed"
  | "pending";

export type TrueMomentumStrategyEvidenceCaveats = {
  parity_status: TrueMomentumStrategyParityCaveatStatus;
  parity_messages: string[];
  parity_classification: string[];
  b8_outcome_status:
    | "available"
    | "captured_without_outcomes"
    | "not_captured"
    | "unavailable";
  c3_readiness_status: TrueMomentumCohortReadinessStatus | "not_evaluated";
};

export type TrueMomentumStrategyContextSummary = {
  family_id: TrueMomentumStrategyPreviewFamilyId | null;
  family_label: string | null;
  match_strength: TrueMomentumStrategyPreviewMatchStrength | null;
  readiness: TrueMomentumStrategyActivationReadiness;
  readiness_label: string;
  readiness_tone: "good" | "warn" | "bad" | "neutral";
  symbol: string;
  strategy: string;
  rank: number | null;
};

export type TrueMomentumStrategyContext = {
  symbol: string;
  strategy: string;
  rank: number | null;
  family_id: TrueMomentumStrategyPreviewFamilyId | null;
  family_label: string | null;
  match_strength: TrueMomentumStrategyPreviewMatchStrength | null;
  active_score: number | null;
  baseline_score: number | null;
  raw_contribution: number | null;
  applied_delta: number | null;
  total_score: number | null;
  total_label: string | null;
  trend_score: number | null;
  momo_score: number | null;
  true_momentum: number | null;
  true_momentum_ema: number | null;
  momentum_state: string | null;
  hilo_thrust_state: string | null;
  hilo_score: number | null;
  no_trade_warning: boolean;
  reversal_warning: boolean;
  pullback_signal: boolean;
  parity_status: TrueMomentumStrategyParityCaveatStatus;
  parity_diagnostics: {
    selected_symbol_summary: SelectedSymbolParitySummary | null;
    classification: string[];
    flags: Record<string, boolean>;
    reason_codes: string[];
    observed_bar_date: string | null;
    fixture_name: string | null;
  };
  b8_outcome_status:
    | "available"
    | "captured_without_outcomes"
    | "not_captured"
    | "unavailable";
  c3_readiness_status: TrueMomentumCohortReadinessStatus | "not_evaluated";
  trigger_checklist: TrueMomentumStrategyTriggerChecklist | null;
  evidence_caveats: TrueMomentumStrategyEvidenceCaveats;
  readiness: TrueMomentumStrategyActivationReadiness;
  research_notes: string[];
  guardrails: string[];
  non_actionable: true;
  preview: TrueMomentumStrategyPreviewCandidate | null;
};

export type SelectedSymbolParitySummary = {
  symbol: string;
  status: string;
  diagnostic_classification: string[];
  diagnostic_flags: Record<string, boolean>;
  reason_codes: string[];
  observed_bar_date: string | null;
  fixture_name: string | null;
  parity_mode: string | null;
  // C4.2 composite-mismatch drilldown values surfaced from the
  // parity-report.json per-fixture result.
  tos_total_score: number | null;
  mm_total_score: number | null;
  mm_component_sum: number | null;
  composite_score_attribution: Record<string, unknown>;
};

function safeNumber(value: unknown): number | null {
  if (value == null) return null;
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num) || !Number.isFinite(num)) return null;
  return num;
}

function pluckPreviewForCandidate(
  candidate: QueueCandidate,
  status: TrueMomentumStrategyFamilyStatus | null | undefined,
): TrueMomentumStrategyPreviewCandidate | null {
  const preview = buildTrueMomentumStrategyPreview([candidate], status ?? null);
  return preview.previews[0] ?? null;
}

function symbolUpper(value: string | null | undefined): string {
  return typeof value === "string" ? value.trim().toUpperCase() : "";
}

export function findSelectedSymbolParitySummary(
  rankingStatus: MomentumRankingStatus | null | undefined,
  symbol: string | null | undefined,
): SelectedSymbolParitySummary | null {
  const target = symbolUpper(symbol);
  if (!target) return null;
  const summaries = rankingStatus?.thinkorswim_parity_symbol_summaries;
  if (!Array.isArray(summaries) || summaries.length === 0) return null;
  for (const entry of summaries) {
    if (!entry || typeof entry !== "object") continue;
    if (symbolUpper(entry.symbol) !== target) continue;
    return {
      symbol: target,
      status: typeof entry.status === "string" ? entry.status : "",
      diagnostic_classification: Array.isArray(entry.diagnostic_classification)
        ? entry.diagnostic_classification.filter((v): v is string => typeof v === "string")
        : [],
      diagnostic_flags:
        entry.diagnostic_flags && typeof entry.diagnostic_flags === "object"
          ? Object.fromEntries(
              Object.entries(entry.diagnostic_flags).map(([k, v]) => [k, Boolean(v)]),
            )
          : {},
      reason_codes: Array.isArray(entry.reason_codes)
        ? entry.reason_codes.filter((v): v is string => typeof v === "string")
        : [],
      observed_bar_date:
        typeof entry.observed_bar_date === "string" ? entry.observed_bar_date : null,
      fixture_name: typeof entry.fixture_name === "string" ? entry.fixture_name : null,
      parity_mode: typeof entry.parity_mode === "string" ? entry.parity_mode : null,
      tos_total_score: safeNumber(
        (entry as { tos_total_score?: unknown }).tos_total_score,
      ),
      mm_total_score: safeNumber(
        (entry as { mm_total_score?: unknown }).mm_total_score,
      ),
      mm_component_sum: safeNumber(
        (entry as { mm_component_sum?: unknown }).mm_component_sum,
      ),
      composite_score_attribution:
        typeof (entry as { composite_score_attribution?: unknown })
          .composite_score_attribution === "object" &&
        (entry as { composite_score_attribution?: unknown })
          .composite_score_attribution !== null
          ? ((entry as { composite_score_attribution?: Record<string, unknown> })
              .composite_score_attribution as Record<string, unknown>)
          : {},
    };
  }
  return null;
}

function classifyParityCaveatStatus(
  rankingStatus: MomentumRankingStatus | null | undefined,
  symbolSummary: SelectedSymbolParitySummary | null,
): { status: TrueMomentumStrategyParityCaveatStatus; messages: string[] } {
  const messages: string[] = [];
  if (!rankingStatus) {
    return { status: "pending", messages };
  }
  if (symbolSummary) {
    const status = symbolSummary.status;
    if (status === "visual_attested" || status === "passed") {
      messages.push(
        `${symbolSummary.symbol} visual attestation passed (parity research evidence).`,
      );
      return { status: "passed", messages };
    }
    if (status === "visual_failed" || status === "failed") {
      if (symbolSummary.diagnostic_classification.includes("composite_mismatch")) {
        messages.push(
          `${symbolSummary.symbol} parity: oscillator fields aligned but composite total score differs. Composite mismatch under review.`,
        );
      } else {
        messages.push(
          `${symbolSummary.symbol} visual attestation failed — review parity-report.md before treating as research-ready.`,
        );
      }
      return { status: "failed", messages };
    }
    if (status === "visual_partial" || status === "partial") {
      messages.push(
        `${symbolSummary.symbol} visual attestation partial — recapture missing fields before treating as research-ready.`,
      );
      return { status: "partial", messages };
    }
  }
  const workflow = rankingStatus.thinkorswim_parity_workflow_status;
  const attestationStatus = rankingStatus.thinkorswim_parity_visual_attestation_status;
  const attestationFailed =
    (rankingStatus.thinkorswim_parity_visual_attestation_failed_count ?? 0) > 0;
  if (workflow === "failed" || attestationStatus === "visual_failed" || attestationFailed) {
    messages.push(
      "Visual parity mixed: oscillator fields aligned for failing fixture; composite score mismatch remains under review.",
    );
    return { status: "global_mixed", messages };
  }
  if (workflow === "partial" || attestationStatus === "visual_partial") {
    messages.push(
      "Visual parity partial — fixtures present but not all attestations complete.",
    );
    return { status: "partial", messages };
  }
  if (workflow === "passed" || attestationStatus === "visual_attested") {
    messages.push(
      "Visual parity passed globally, but the selected symbol is not covered by visual attestation evidence.",
    );
    return { status: "not_covered", messages };
  }
  messages.push("Visual attestation pending — no parity evidence covers this symbol yet.");
  return { status: "pending", messages };
}

function buildContinuationChecklist(
  preview: TrueMomentumStrategyPreviewCandidate | null,
  candidate: QueueCandidate,
): TrueMomentumStrategyTriggerChecklistItem[] {
  const total = preview?.total_score ?? null;
  const label = preview?.total_label ?? null;
  const trend = preview?.trend_score ?? null;
  const momo = preview?.momo_score ?? null;
  const trueMomentum = safeNumber(
    preview?.applied_delta != null ? undefined : preview?.applied_delta,
  );
  // The preview doesn't carry true_momentum vs ema directly — fall back
  // to candidate.momentum_contribution for richer checks.
  const tm = safeNumber(candidate.momentum_contribution?.momentum_alignment_score);
  const ema = null;
  const noTrade = !!preview?.no_trade_warning;
  const reversal = !!preview?.reversal_warning;
  const hiloScore = candidate.momentum_contribution?.hilo_confirmation_bonus ?? null;
  const items: TrueMomentumStrategyTriggerChecklistItem[] = [];

  items.push(buildScoreItem("continuation_total_score", "Total score Bull / Max Bull or ≥ 80", total, label));
  items.push(
    buildOscillatorItem("continuation_true_momentum_above_ema", "True Momentum above EMA", tm, ema, preview),
  );
  items.push(buildThresholdItem("continuation_trend_score", "Trend score ≥ 70", trend, 70));
  items.push(buildThresholdItem("continuation_momo_score", "Momo score ≥ 70", momo, 70));
  items.push(buildHiloItem("continuation_hilo", "HiLo score > 0 or thrust confirmed", hiloScore, preview));
  items.push(buildWarningItem("continuation_no_trade", "No no-trade warning", "no_trade_warning", noTrade));
  items.push(buildWarningItem("continuation_no_reversal", "No reversal warning", "reversal_warning", reversal));
  items.push(buildSetupItem("continuation_setup_exists", "Existing deterministic price setup exists", candidate));
  items.push({
    id: "continuation_parity_review",
    label: "Parity / evidence does not block research review",
    status: "warning",
    reason: "Parity / evidence caveats reviewed separately in the Evidence section.",
    source_field: "parity_status",
  });
  return items;
}

function buildPullbackChecklist(
  preview: TrueMomentumStrategyPreviewCandidate | null,
  candidate: QueueCandidate,
): TrueMomentumStrategyTriggerChecklistItem[] {
  const total = preview?.total_score ?? null;
  const label = preview?.total_label ?? null;
  const reversal = !!preview?.reversal_warning;
  const pullbackActive = !!preview?.pullback_signal;
  const strategyLower = (candidate.strategy ?? "").toLowerCase();
  const isPullbackStrategy =
    strategyLower.includes("pullback") || strategyLower.includes("trend continuation");
  const invalidation =
    typeof candidate.invalidation === "object" && candidate.invalidation
      ? Object.keys(candidate.invalidation).length > 0
      : typeof candidate.invalidation === "string" && candidate.invalidation.trim().length > 0;
  const tm = safeNumber(candidate.momentum_contribution?.momentum_alignment_score);
  const hiloScore = candidate.momentum_contribution?.hilo_confirmation_bonus ?? null;

  const items: TrueMomentumStrategyTriggerChecklistItem[] = [];
  items.push(buildScoreItem("pullback_total_score", "Total score Bull / Max Bull or ≥ 80", total, label));
  items.push({
    id: "pullback_signal_or_strategy",
    label: "Pullback signal active OR strategy is Pullback / Trend Continuation",
    status: pullbackActive || isPullbackStrategy ? "pass" : "warning",
    reason: pullbackActive
      ? "Deterministic pullback signal is active."
      : isPullbackStrategy
        ? "Source strategy is Pullback / Trend Continuation aligned."
        : "Neither pullback signal nor pullback-aligned strategy detected.",
    source_field: pullbackActive ? "pullback_signal" : "strategy",
  });
  items.push(
    buildOscillatorItem(
      "pullback_true_momentum_above_ema",
      "True Momentum above EMA or recently crossed",
      tm,
      null,
      preview,
    ),
  );
  items.push({
    id: "pullback_hilo_not_strongly_negative",
    label: "HiLo score not strongly negative",
    status: hiloScore == null ? "unavailable" : hiloScore > -10 ? "pass" : "warning",
    reason:
      hiloScore == null
        ? "HiLo score not surfaced on the candidate."
        : `HiLo score is ${hiloScore}.`,
    source_field: "hilo_score",
  });
  items.push(buildWarningItem("pullback_no_reversal", "No reversal warning", "reversal_warning", reversal));
  items.push(buildSetupItem("pullback_setup_exists", "Existing deterministic pullback setup exists", candidate));
  items.push({
    id: "pullback_risk_invalidation",
    label: "Risk / invalidation captured on the queue candidate",
    status: invalidation ? "pass" : "warning",
    reason: invalidation
      ? "Candidate carries an invalidation block."
      : "Candidate is missing an invalidation block — research review only.",
    source_field: "invalidation",
  });
  return items;
}

function buildReversalWatchChecklist(
  preview: TrueMomentumStrategyPreviewCandidate | null,
  candidate: QueueCandidate,
): TrueMomentumStrategyTriggerChecklistItem[] {
  const total = preview?.total_score ?? null;
  const label = preview?.total_label ?? null;
  const reversal = !!preview?.reversal_warning;
  const noTrade = !!preview?.no_trade_warning;
  const labelLower = label ? label.trim().toLowerCase() : "";
  const bearishLabel = labelLower === "bear" || labelLower === "max bear";
  const deeplyBearish = total != null && total <= -50;
  const watchTriggered = reversal || noTrade || bearishLabel || deeplyBearish;
  const strategyLower = (candidate.strategy ?? "").toLowerCase();
  const longBiased =
    strategyLower.includes("event continuation") ||
    strategyLower.includes("breakout") ||
    strategyLower.includes("pullback") ||
    strategyLower.includes("trend");
  const items: TrueMomentumStrategyTriggerChecklistItem[] = [];

  items.push({
    id: "reversal_watch_trigger",
    label:
      "Reversal warning OR no-trade warning OR Bear / Max Bear contradiction OR total_score ≤ -50",
    status: watchTriggered ? "pass" : "warning",
    reason: watchTriggered
      ? [
          reversal ? "reversal_warning active" : null,
          noTrade ? "no_trade_warning active" : null,
          bearishLabel ? `total_label is ${label}` : null,
          deeplyBearish ? `total_score is ${total}` : null,
        ]
          .filter(Boolean)
          .join("; ")
      : "No reversal / no-trade trigger detected on this candidate.",
    source_field: "reversal_warning",
  });
  items.push({
    id: "reversal_watch_watch_only",
    label: "Watch-only — never proposes entry",
    status: "pass",
    reason: "Reversal / weakening watch is research context only.",
    source_field: "family",
  });
  items.push({
    id: "reversal_watch_no_entry_proposed",
    label: "No entry / stop / target is proposed",
    status: "pass",
    reason: "The watch family deliberately stops at flagged context — no order plan is produced.",
    source_field: "family",
  });
  items.push({
    id: "reversal_watch_existing_candidate_downgrade",
    label: "Existing candidate downgraded to warning / research context",
    status: longBiased && watchTriggered ? "warning" : "pass",
    reason:
      longBiased && watchTriggered
        ? `Long-biased strategy (${candidate.strategy}) carries a watch trigger — treat as research context, not entry.`
        : "Source strategy already aligns with research context.",
    source_field: "strategy",
  });
  return items;
}

function buildScoreItem(
  id: string,
  label: string,
  total: number | null,
  totalLabel: string | null,
): TrueMomentumStrategyTriggerChecklistItem {
  if (total == null && totalLabel == null) {
    return {
      id,
      label,
      status: "unavailable",
      reason: "Total score / label not surfaced on the candidate.",
      source_field: "total_score",
    };
  }
  const labelLower = totalLabel ? totalLabel.trim().toLowerCase() : "";
  const labelBullish = labelLower === "bull" || labelLower === "max bull";
  const strong = total != null && total >= 80;
  const status: TrueMomentumStrategyTriggerChecklistItemStatus = labelBullish || strong ? "pass" : "warning";
  return {
    id,
    label,
    status,
    reason:
      labelBullish || strong
        ? `Total label ${totalLabel ?? "unknown"} / score ${total ?? "unknown"}.`
        : `Total label ${totalLabel ?? "unknown"} / score ${total ?? "unknown"} below 80.`,
    source_field: "total_score",
  };
}

function buildOscillatorItem(
  id: string,
  label: string,
  tm: number | null,
  ema: number | null,
  preview: TrueMomentumStrategyPreviewCandidate | null,
): TrueMomentumStrategyTriggerChecklistItem {
  if (preview == null) {
    return {
      id,
      label,
      status: "unavailable",
      reason: "Preview classification not available for this candidate.",
      source_field: "true_momentum",
    };
  }
  // We don't always have true_momentum / ema raw values here. Use
  // raw_contribution > 0 as a proxy for "oscillator broadly aligned".
  const rawAlignment = preview.raw_contribution ?? 0;
  if (rawAlignment <= 0) {
    return {
      id,
      label,
      status: "warning",
      reason: "Momentum raw contribution is not positive — oscillator alignment not confirmed.",
      source_field: "raw_contribution",
    };
  }
  return {
    id,
    label,
    status: "pass",
    reason: `Raw Momentum contribution is +${rawAlignment.toFixed(2)} (oscillator alignment confirmed at preview level).`,
    source_field: "raw_contribution",
  };
}

function buildThresholdItem(
  id: string,
  label: string,
  value: number | null,
  threshold: number,
): TrueMomentumStrategyTriggerChecklistItem {
  if (value == null) {
    return {
      id,
      label,
      status: "unavailable",
      reason: `Field for "${label}" not surfaced on the candidate.`,
    };
  }
  const status: TrueMomentumStrategyTriggerChecklistItemStatus = value >= threshold ? "pass" : "warning";
  return {
    id,
    label,
    status,
    reason: `Value ${value.toFixed(0)} vs threshold ${threshold}.`,
  };
}

function buildHiloItem(
  id: string,
  label: string,
  hiloScore: number | null,
  preview: TrueMomentumStrategyPreviewCandidate | null,
): TrueMomentumStrategyTriggerChecklistItem {
  if (hiloScore == null && preview == null) {
    return {
      id,
      label,
      status: "unavailable",
      reason: "HiLo score / thrust not surfaced on the candidate.",
      source_field: "hilo_score",
    };
  }
  if (hiloScore != null && hiloScore > 0) {
    return {
      id,
      label,
      status: "pass",
      reason: `HiLo score is +${hiloScore}.`,
      source_field: "hilo_score",
    };
  }
  return {
    id,
    label,
    status: hiloScore != null && hiloScore < 0 ? "warning" : "warning",
    reason:
      hiloScore != null
        ? `HiLo score is ${hiloScore} — confirmation not strong.`
        : "HiLo score not surfaced.",
    source_field: "hilo_score",
  };
}

function buildWarningItem(
  id: string,
  label: string,
  flag: "no_trade_warning" | "reversal_warning",
  triggered: boolean,
): TrueMomentumStrategyTriggerChecklistItem {
  return {
    id,
    label,
    status: triggered ? "fail" : "pass",
    reason: triggered
      ? `${flag} is active — blocked by warning.`
      : `${flag} is not active.`,
    source_field: flag,
  };
}

function buildSetupItem(
  id: string,
  label: string,
  candidate: QueueCandidate,
): TrueMomentumStrategyTriggerChecklistItem {
  const trigger = (candidate.trigger ?? "").toString().trim();
  const entryZone =
    typeof candidate.entry_zone === "object" && candidate.entry_zone
      ? Object.keys(candidate.entry_zone).length > 0
      : typeof candidate.entry_zone === "string" && candidate.entry_zone.trim().length > 0;
  const hasSetup = !!candidate.strategy && (entryZone || trigger.length > 0);
  return {
    id,
    label,
    status: hasSetup ? "pass" : "warning",
    reason: hasSetup
      ? `Candidate carries a deterministic ${candidate.strategy} setup.`
      : "Candidate is missing a deterministic price setup (entry zone / trigger).",
    source_field: "strategy",
  };
}

function summarizeChecklist(items: TrueMomentumStrategyTriggerChecklistItem[]): TrueMomentumStrategyTriggerChecklist["summary"] {
  const summary = { total: items.length, pass: 0, warning: 0, fail: 0, unavailable: 0 };
  for (const item of items) {
    if (item.status === "pass") summary.pass += 1;
    else if (item.status === "warning") summary.warning += 1;
    else if (item.status === "fail") summary.fail += 1;
    else summary.unavailable += 1;
  }
  return summary;
}

/**
 * Build the family-specific trigger-readiness checklist for the
 * selected candidate. Returns ``null`` when the candidate has no
 * preview classification (no family match).
 */
export function buildTrueMomentumTriggerChecklist(
  candidate: QueueCandidate,
  preview: TrueMomentumStrategyPreviewCandidate | null,
): TrueMomentumStrategyTriggerChecklist | null {
  if (!preview) return null;
  let items: TrueMomentumStrategyTriggerChecklistItem[];
  if (preview.family_id === "true_momentum_continuation") {
    items = buildContinuationChecklist(preview, candidate);
  } else if (preview.family_id === "true_momentum_pullback") {
    items = buildPullbackChecklist(preview, candidate);
  } else if (preview.family_id === "true_momentum_reversal_watch") {
    items = buildReversalWatchChecklist(preview, candidate);
  } else {
    return null;
  }
  const summary = summarizeChecklist(items);
  const research_ready_for_family =
    preview.family_id === "true_momentum_reversal_watch"
      ? summary.fail === 0 && summary.warning <= summary.total // watch is always research-ready-as-watch
      : summary.fail === 0 && summary.pass >= Math.ceil(summary.total / 2);
  return { family_id: preview.family_id, items, summary, research_ready_for_family };
}

function deriveMomentumState(preview: TrueMomentumStrategyPreviewCandidate | null): string | null {
  if (!preview) return null;
  if (preview.no_trade_warning) return "no_trade_warning";
  if (preview.reversal_warning) return "reversal_warning";
  if (preview.pullback_signal) return "pullback";
  if (preview.total_label) return preview.total_label.toLowerCase().replace(/\s+/g, "_");
  return null;
}

function deriveGuardrails(): string[] {
  return [
    "Research-only — does not generate queue candidates, and does not approve, reject, size, or route trades.",
    "Phase C strategy families are reserved and disabled by default.",
    "Activation readiness is research context, not trade approval.",
    "Visual attestation parity is operator-reviewed manual evidence; passing parity does not auto-activate Phase C.",
  ];
}

export type BuildTrueMomentumStrategyContextArgs = {
  candidate: QueueCandidate | null | undefined;
  strategyFamilyStatus: TrueMomentumStrategyFamilyStatus | null | undefined;
  rankingStatus: MomentumRankingStatus | null | undefined;
  cohortReadinessStatus?: TrueMomentumCohortReadinessStatus | null | undefined;
  b8OutcomeStatus?:
    | "available"
    | "captured_without_outcomes"
    | "not_captured"
    | "unavailable";
};

/**
 * Compose the Phase C4 strategy context bundle for the selected
 * Recommendations queue candidate. Returns ``null`` when the candidate
 * is missing.
 */
export function buildTrueMomentumStrategyContext(
  args: BuildTrueMomentumStrategyContextArgs,
): TrueMomentumStrategyContext | null {
  const { candidate, strategyFamilyStatus, rankingStatus } = args;
  if (!candidate) return null;
  const preview = pluckPreviewForCandidate(candidate, strategyFamilyStatus ?? null);
  const symbolSummary = findSelectedSymbolParitySummary(rankingStatus, candidate.symbol);
  const parity = classifyParityCaveatStatus(rankingStatus, symbolSummary);
  const checklist = buildTrueMomentumTriggerChecklist(candidate, preview);
  const noTrade = !!preview?.no_trade_warning;
  const reversal = !!preview?.reversal_warning;
  const cohortReadiness = args.cohortReadinessStatus ?? "not_evaluated";
  const b8Status = args.b8OutcomeStatus ?? "unavailable";

  const baseContext: TrueMomentumStrategyContext = {
    symbol: candidate.symbol ?? "",
    strategy: candidate.strategy ?? "",
    rank: candidate.rank ?? null,
    family_id: preview?.family_id ?? null,
    family_label: preview?.family_label ?? null,
    match_strength: preview?.match_strength ?? null,
    active_score: preview?.active_score ?? null,
    baseline_score: preview?.baseline_score ?? null,
    raw_contribution: preview?.raw_contribution ?? null,
    applied_delta: preview?.applied_delta ?? null,
    total_score: preview?.total_score ?? null,
    total_label: preview?.total_label ?? null,
    trend_score: preview?.trend_score ?? null,
    momo_score: preview?.momo_score ?? null,
    true_momentum: safeNumber(candidate.momentum_contribution?.momentum_alignment_score),
    true_momentum_ema: null,
    momentum_state: deriveMomentumState(preview),
    hilo_thrust_state:
      typeof candidate.momentum_contribution?.parity_status === "string"
        ? candidate.momentum_contribution?.parity_status
        : null,
    hilo_score: safeNumber(candidate.momentum_contribution?.hilo_confirmation_bonus),
    no_trade_warning: noTrade,
    reversal_warning: reversal,
    pullback_signal: !!preview?.pullback_signal,
    parity_status: parity.status,
    parity_diagnostics: {
      selected_symbol_summary: symbolSummary,
      classification: symbolSummary?.diagnostic_classification ?? [],
      flags: symbolSummary?.diagnostic_flags ?? {},
      reason_codes: symbolSummary?.reason_codes ?? [],
      observed_bar_date: symbolSummary?.observed_bar_date ?? null,
      fixture_name: symbolSummary?.fixture_name ?? null,
    },
    b8_outcome_status: b8Status,
    c3_readiness_status: cohortReadiness,
    trigger_checklist: checklist,
    evidence_caveats: {
      parity_status: parity.status,
      parity_messages: parity.messages,
      parity_classification: symbolSummary?.diagnostic_classification ?? [],
      b8_outcome_status: b8Status,
      c3_readiness_status: cohortReadiness,
    },
    readiness: "not_applicable",
    research_notes: preview?.research_notes ?? [],
    guardrails: deriveGuardrails(),
    non_actionable: true,
    preview,
  };

  baseContext.readiness = classifyTrueMomentumStrategyActivationReadiness(baseContext);

  return baseContext;
}

/**
 * Classify activation readiness from an already-built context. Never
 * returns ``approved`` or ``ready for live``.
 */
export function classifyTrueMomentumStrategyActivationReadiness(
  context: TrueMomentumStrategyContext,
): TrueMomentumStrategyActivationReadiness {
  if (!context.family_id) return "not_applicable";
  if (context.family_id === "true_momentum_reversal_watch") return "watch_only";
  // Warning blocked must precede composite mismatch / parity blocked so
  // a single fixture's composite mismatch never overrides an active
  // warning on the selected candidate.
  if (context.no_trade_warning || context.reversal_warning) {
    return "warning_blocked";
  }
  if (context.parity_diagnostics.selected_symbol_summary) {
    const summary = context.parity_diagnostics.selected_symbol_summary;
    if (summary.diagnostic_classification.includes("composite_mismatch")) {
      return "composite_mismatch_review";
    }
    if (summary.status === "visual_failed" || summary.status === "failed") {
      return "parity_blocked";
    }
    if (summary.status === "visual_partial" || summary.status === "partial") {
      return "needs_more_evidence";
    }
  } else if (context.parity_status === "global_mixed") {
    // Don't block a candidate's readiness solely because an unrelated
    // symbol's composite mismatch is under review. We still surface
    // the global caveat in evidence_caveats.parity_messages.
  } else if (context.parity_status === "failed") {
    return "parity_blocked";
  } else if (context.parity_status === "partial") {
    return "needs_more_evidence";
  } else if (context.parity_status === "not_covered" || context.parity_status === "pending") {
    // Not blocking; downgrade to needs_more_evidence only when other
    // signals also point that way.
  }
  if (
    context.c3_readiness_status === "insufficient_evidence" ||
    context.c3_readiness_status === "parity_blocked"
  ) {
    return "needs_more_evidence";
  }
  if (context.match_strength === "blocked") {
    return "warning_blocked";
  }
  // Research-ready only when oscillator passes and no blocking caveats
  // remain.
  if (
    context.trigger_checklist &&
    context.trigger_checklist.research_ready_for_family &&
    context.match_strength !== "watch"
  ) {
    return "research_ready";
  }
  return "needs_more_evidence";
}

export function summarizeTrueMomentumStrategyContext(
  context: TrueMomentumStrategyContext | null,
): TrueMomentumStrategyContextSummary | null {
  if (!context) return null;
  return {
    family_id: context.family_id,
    family_label: context.family_label,
    match_strength: context.match_strength,
    readiness: context.readiness,
    readiness_label: trueMomentumStrategyActivationReadinessLabel(context.readiness),
    readiness_tone: trueMomentumStrategyActivationReadinessTone(context.readiness),
    symbol: context.symbol,
    strategy: context.strategy,
    rank: context.rank,
  };
}

/**
 * Flatten every operator-visible text surface on a context bundle so
 * callers (tests, audit hooks) can run their own non-actionable
 * language guard. The helper itself does not embed the list of
 * forbidden substrings — that is a test concern.
 */
export function collectTrueMomentumStrategyContextSurfaces(
  context: TrueMomentumStrategyContext | null,
): string[] {
  if (!context) return [];
  const surfaces: string[] = [];
  for (const note of context.research_notes) surfaces.push(note);
  for (const note of context.evidence_caveats.parity_messages) surfaces.push(note);
  if (context.trigger_checklist) {
    for (const item of context.trigger_checklist.items) {
      surfaces.push(item.label);
      surfaces.push(item.reason);
    }
  }
  for (const guardrail of context.guardrails) surfaces.push(guardrail);
  return surfaces;
}
