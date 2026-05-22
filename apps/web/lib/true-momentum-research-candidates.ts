// Phase C5 — True Momentum research candidate proposal helpers.
//
// Pure, side-effect-free helpers that derive research-only proposals
// from the already-loaded Recommendations queue + Phase C1 family
// preview classifier + Phase C4 selected-candidate context + parity
// status. C5 proposals:
//
// - never enter the live ranked queue,
// - never approve, reject, size, route, open, close, or settle trades,
// - never create paper orders,
// - never change ranking math, queue sorting, recommendation approval,
//   promote / make-active / save flows, replay, or options behavior,
// - never call providers, the database, or an LLM.
//
// The Phase C5 boundary is enforced through two always-blocking
// decision gates (``operator_authorization`` and
// ``active_generation_reserved``) that fire on every proposal.

import type { MomentumRankingStatus } from "@/lib/momentum-ranking-status";
import type { QueueCandidate } from "@/lib/recommendations";
import {
  buildTrueMomentumStrategyContext,
  type TrueMomentumStrategyContext,
} from "@/lib/true-momentum-strategy-context";
import type {
  TrueMomentumStrategyPreviewFamilyId,
  TrueMomentumStrategyPreviewMatchStrength,
} from "@/lib/true-momentum-strategy-preview";
import type { TrueMomentumStrategyFamilyStatus } from "@/lib/true-momentum-strategy-families";
import type { TrueMomentumCohortReadinessStatus } from "@/lib/true-momentum-cohort-review";

export const TRUE_MOMENTUM_RESEARCH_CANDIDATES_SCHEMA_VERSION = "phase_c5.v1";
export const TRUE_MOMENTUM_RESEARCH_CANDIDATES_PHASE = "C5";

export const TRUE_MOMENTUM_RESEARCH_CANDIDATES_DETERMINISTIC_NOTE =
  "C5 research candidate proposals are non-active and non-ordering. They do not enter the ranked queue, and do not approve, reject, size, or route trades. They never create paper orders.";

export type TrueMomentumResearchCandidateProposalType =
  | "continuation_research"
  | "pullback_research"
  | "watch_only_research";

export type TrueMomentumResearchCandidateProposalStatus =
  | "proposed_for_research"
  | "watch_only"
  | "blocked_by_warning"
  | "blocked_by_parity"
  | "blocked_by_composite_mismatch"
  | "insufficient_evidence";

export type TrueMomentumResearchCandidateConfidenceTier =
  | "high"
  | "medium"
  | "watch"
  | "blocked";

export type TrueMomentumResearchCandidateDecisionGateStatus =
  | "pass"
  | "warning"
  | "fail"
  | "unavailable";

export type TrueMomentumResearchCandidateDecisionGate = {
  id: string;
  label: string;
  status: TrueMomentumResearchCandidateDecisionGateStatus;
  reason: string;
  blocks_activation: boolean;
};

export type TrueMomentumResearchCandidateProposal = {
  proposal_id: string;
  generated_at: string;
  source_queue_signature: string;
  rank: number;
  symbol: string;
  source_strategy: string;
  proposed_family_id: TrueMomentumStrategyPreviewFamilyId;
  proposed_family_label: string;
  proposal_type: TrueMomentumResearchCandidateProposalType;
  proposal_status: TrueMomentumResearchCandidateProposalStatus;
  confidence_tier: TrueMomentumResearchCandidateConfidenceTier;
  source_candidate_score: number | null;
  baseline_score: number | null;
  active_score: number | null;
  raw_contribution: number | null;
  applied_delta: number | null;
  total_score: number | null;
  total_label: string | null;
  trend_score: number | null;
  momo_score: number | null;
  true_momentum: number | null;
  true_momentum_ema: number | null;
  hilo_score: number | null;
  hilo_thrust_state: string | null;
  match_strength: TrueMomentumStrategyPreviewMatchStrength | null;
  parity_status: string;
  b8_outcome_status: string;
  c3_readiness_status: string;
  checklist_pass_count: number;
  checklist_total_count: number;
  decision_gates: TrueMomentumResearchCandidateDecisionGate[];
  caveats: string[];
  research_notes: string[];
  non_actionable: true;
};

export type TrueMomentumResearchCandidateFamilyBucket = {
  family_id: TrueMomentumStrategyPreviewFamilyId;
  family_label: string;
  proposals: TrueMomentumResearchCandidateProposal[];
};

export type TrueMomentumResearchCandidateProposalSummary = {
  generated_at: string;
  candidate_count: number;
  proposed_for_research_count: number;
  continuation_count: number;
  pullback_count: number;
  watch_only_count: number;
  blocked_count: number;
  blocked_by_parity_count: number;
  blocked_by_composite_mismatch_count: number;
  insufficient_evidence_count: number;
  symbols_covered: string[];
  parity_mixed: boolean;
  xlp_composite_mismatch_present: boolean;
  active_generation_reserved: true;
};

export type TrueMomentumResearchCandidateProposalSet = {
  schema_version: string;
  phase: string;
  generated_at: string;
  source_queue_signature: string;
  proposals: TrueMomentumResearchCandidateProposal[];
  summary: TrueMomentumResearchCandidateProposalSummary;
  deterministic_note: string;
};

export type TrueMomentumResearchCandidateExportPayload = {
  schema_version: string;
  proposal_set: TrueMomentumResearchCandidateProposalSet;
  deterministic_note: string;
};

export type BuildTrueMomentumResearchCandidateArgs = {
  queueCandidates: ReadonlyArray<QueueCandidate>;
  strategyFamilyStatus: TrueMomentumStrategyFamilyStatus | null;
  rankingStatus: MomentumRankingStatus | null;
  cohortReadinessStatus?:
    | TrueMomentumCohortReadinessStatus
    | "not_evaluated"
    | null;
  b8OutcomeStatus?:
    | "available"
    | "captured_without_outcomes"
    | "not_captured"
    | "unavailable";
  generatedAt?: string;
};

function safeFinite(value: unknown): number | null {
  if (value == null) return null;
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num) || !Number.isFinite(num)) return null;
  return num;
}

function deriveQueueSignature(queueCandidates: ReadonlyArray<QueueCandidate>): string {
  const parts = queueCandidates
    .map((c) => `${c.symbol}-${c.strategy}-${c.rank}`)
    .slice(0, 50);
  return parts.join("|");
}

function classifyConfidenceTier(
  match: TrueMomentumStrategyPreviewMatchStrength | null,
  status: TrueMomentumResearchCandidateProposalStatus,
): TrueMomentumResearchCandidateConfidenceTier {
  if (
    status === "blocked_by_warning" ||
    status === "blocked_by_parity" ||
    status === "blocked_by_composite_mismatch"
  ) {
    return "blocked";
  }
  if (status === "watch_only") return "watch";
  if (match === "strong") return "high";
  if (match === "moderate") return "medium";
  if (match === "watch") return "watch";
  return "medium";
}

function buildDecisionGates(
  context: TrueMomentumStrategyContext,
  args: BuildTrueMomentumResearchCandidateArgs,
): TrueMomentumResearchCandidateDecisionGate[] {
  const checklist = context.trigger_checklist;
  const trendStrong =
    context.trend_score != null && context.trend_score >= 70;
  const momoStrong = context.momo_score != null && context.momo_score >= 70;
  const oscillatorAligned =
    context.parity_diagnostics.classification.includes("oscillator_aligned");
  const hiloPositive = (context.hilo_score ?? 0) > 0;
  const parityFlags =
    context.parity_diagnostics.selected_symbol_summary?.diagnostic_flags ?? {};
  const compositeMismatch =
    context.parity_diagnostics.classification.includes("composite_mismatch");
  const familyMatch = context.match_strength != null && context.match_strength !== "blocked";
  const b8Available = args.b8OutcomeStatus === "available";
  const cohort = args.cohortReadinessStatus ?? "not_evaluated";
  const cohortGood = cohort === "promising_research" || cohort === "mixed_research";

  return [
    {
      id: "family_fit",
      label: "Family fit",
      status: familyMatch ? "pass" : "warning",
      reason: familyMatch
        ? `Family ${context.family_label ?? context.family_id ?? "unknown"} matched at ${context.match_strength ?? "unknown"} strength.`
        : "No True Momentum family match for this candidate.",
      blocks_activation: false,
    },
    {
      id: "momentum_alignment",
      label: "Momentum alignment",
      status: oscillatorAligned
        ? "pass"
        : (context.raw_contribution ?? 0) > 0
          ? "pass"
          : "warning",
      reason: oscillatorAligned
        ? "Oscillator (True Momentum / EMA) aligned per parity diagnostics."
        : (context.raw_contribution ?? 0) > 0
          ? `Raw Momentum contribution is +${(context.raw_contribution ?? 0).toFixed(2)}.`
          : "Momentum alignment not confirmed.",
      blocks_activation: false,
    },
    {
      id: "trend_alignment",
      label: "Trend alignment",
      status: trendStrong ? "pass" : context.trend_score == null ? "unavailable" : "warning",
      reason:
        context.trend_score == null
          ? "Trend score not surfaced on the candidate."
          : `Trend score ${context.trend_score.toFixed(0)} vs threshold 70.`,
      blocks_activation: false,
    },
    {
      id: "momo_alignment",
      label: "Momo alignment",
      status: momoStrong ? "pass" : context.momo_score == null ? "unavailable" : "warning",
      reason:
        context.momo_score == null
          ? "Momo score not surfaced on the candidate."
          : `Momo score ${context.momo_score.toFixed(0)} vs threshold 70.`,
      blocks_activation: false,
    },
    {
      id: "hilo_confirmation",
      label: "HiLo confirmation",
      status: hiloPositive ? "pass" : context.hilo_score == null ? "unavailable" : "warning",
      reason: hiloPositive
        ? `HiLo score ${context.hilo_score}.`
        : "HiLo score is zero / negative / not surfaced.",
      blocks_activation: false,
    },
    {
      id: "warning_state",
      label: "Warning state",
      status:
        context.no_trade_warning || context.reversal_warning ? "fail" : "pass",
      reason:
        context.no_trade_warning
          ? "no_trade_warning active — blocked by warning."
          : context.reversal_warning
            ? "reversal_warning active — blocked by warning."
            : "No no-trade / reversal warnings active.",
      blocks_activation: context.no_trade_warning || context.reversal_warning,
    },
    {
      id: "parity_status",
      label: "Parity status",
      status: compositeMismatch
        ? "fail"
        : context.parity_status === "failed"
          ? "fail"
          : context.parity_status === "passed"
            ? "pass"
            : "warning",
      reason: compositeMismatch
        ? `Symbol-specific composite mismatch under review (${context.symbol}).`
        : context.parity_status === "passed"
          ? `${context.symbol} visual attestation passed.`
          : context.parity_status === "failed"
            ? `${context.symbol} visual attestation failed — review parity report.`
            : `Parity status: ${context.parity_status}.`,
      blocks_activation: compositeMismatch || context.parity_status === "failed",
    },
    {
      id: "b8_evidence",
      label: "B8 outcome evidence",
      status: b8Available ? "pass" : "warning",
      reason: b8Available
        ? "B8 outcome evidence available for this session."
        : `B8 outcome status: ${args.b8OutcomeStatus ?? "unavailable"}. Accumulated B8 corpus is still required before activation.`,
      blocks_activation: !b8Available,
    },
    {
      id: "c3_cohort_evidence",
      label: "C3 cohort evidence",
      status: cohortGood ? "pass" : "warning",
      reason: cohortGood
        ? `Cohort readiness: ${cohort}.`
        : `Cohort readiness: ${cohort}. Representative cross-sector / cross-regime corpus required.`,
      blocks_activation: !cohortGood,
    },
    {
      id: "operator_authorization",
      label: "Operator authorization",
      status: "warning",
      reason:
        "Explicit per-family operator authorization is required for any future active Phase C decision. Activation is never automatic.",
      blocks_activation: true,
    },
    {
      id: "active_generation_reserved",
      label: "Active generation reserved",
      status: "fail",
      reason:
        "Active Phase C strategy generation remains reserved / not implemented. C5 proposals are research-only and never enter the ranked queue.",
      blocks_activation: true,
    },
  ];
}

function classifyProposalStatus(
  context: TrueMomentumStrategyContext,
  args: BuildTrueMomentumResearchCandidateArgs,
): {
  type: TrueMomentumResearchCandidateProposalType;
  status: TrueMomentumResearchCandidateProposalStatus;
} {
  const family = context.family_id;
  // Reversal/watch family → always watch_only_research.
  if (family === "true_momentum_reversal_watch") {
    if (
      context.parity_diagnostics.classification.includes("composite_mismatch")
    ) {
      return { type: "watch_only_research", status: "blocked_by_composite_mismatch" };
    }
    return { type: "watch_only_research", status: "watch_only" };
  }
  // Warning blocked.
  if (context.no_trade_warning || context.reversal_warning) {
    return {
      type: family === "true_momentum_pullback" ? "pullback_research" : "continuation_research",
      status: "blocked_by_warning",
    };
  }
  // Selected-symbol composite mismatch (e.g. XLP).
  if (context.parity_diagnostics.classification.includes("composite_mismatch")) {
    return {
      type: "watch_only_research",
      status: "blocked_by_composite_mismatch",
    };
  }
  // Symbol-specific parity failure (without composite mismatch).
  if (context.parity_status === "failed") {
    return {
      type: family === "true_momentum_pullback" ? "pullback_research" : "continuation_research",
      status: "blocked_by_parity",
    };
  }
  // Family-typed proposals.
  if (family === "true_momentum_pullback") {
    const ready =
      context.readiness === "research_ready" ||
      (context.readiness === "needs_more_evidence" &&
        (context.trigger_checklist?.summary.pass ?? 0) >=
          Math.ceil((context.trigger_checklist?.summary.total ?? 1) / 2));
    if (ready) return { type: "pullback_research", status: "proposed_for_research" };
    return { type: "pullback_research", status: "insufficient_evidence" };
  }
  if (family === "true_momentum_continuation") {
    const ready =
      context.readiness === "research_ready" ||
      (context.readiness === "needs_more_evidence" &&
        (context.trigger_checklist?.summary.pass ?? 0) >=
          Math.ceil((context.trigger_checklist?.summary.total ?? 1) / 2));
    if (ready) return { type: "continuation_research", status: "proposed_for_research" };
    return { type: "continuation_research", status: "insufficient_evidence" };
  }
  return { type: "watch_only_research", status: "insufficient_evidence" };
}

function buildProposalForCandidate(
  candidate: QueueCandidate,
  args: BuildTrueMomentumResearchCandidateArgs,
  generatedAt: string,
  signature: string,
): TrueMomentumResearchCandidateProposal | null {
  const context = buildTrueMomentumStrategyContext({
    candidate,
    strategyFamilyStatus: args.strategyFamilyStatus,
    rankingStatus: args.rankingStatus,
    cohortReadinessStatus:
      args.cohortReadinessStatus === "not_evaluated" ? null : args.cohortReadinessStatus,
    b8OutcomeStatus: args.b8OutcomeStatus,
  });
  if (!context || !context.family_id || !context.family_label) return null;
  const { type, status } = classifyProposalStatus(context, args);
  const decision_gates = buildDecisionGates(context, args);
  const caveats: string[] = [];
  if (context.parity_diagnostics.classification.includes("composite_mismatch")) {
    caveats.push(
      "Oscillator aligned; composite total score mismatch under review.",
    );
  }
  for (const message of context.evidence_caveats.parity_messages) {
    if (!caveats.includes(message)) caveats.push(message);
  }
  if (context.no_trade_warning) caveats.push("no_trade_warning active.");
  if (context.reversal_warning) caveats.push("reversal_warning active.");

  return {
    proposal_id: `c5::${context.family_id}::${candidate.symbol}::${candidate.strategy}::${candidate.rank}`,
    generated_at: generatedAt,
    source_queue_signature: signature,
    rank: candidate.rank,
    symbol: candidate.symbol,
    source_strategy: candidate.strategy,
    proposed_family_id: context.family_id,
    proposed_family_label: context.family_label,
    proposal_type: type,
    proposal_status: status,
    confidence_tier: classifyConfidenceTier(context.match_strength, status),
    source_candidate_score: safeFinite(candidate.score),
    baseline_score: context.baseline_score,
    active_score: context.active_score,
    raw_contribution: context.raw_contribution,
    applied_delta: context.applied_delta,
    total_score: context.total_score,
    total_label: context.total_label,
    trend_score: context.trend_score,
    momo_score: context.momo_score,
    true_momentum: context.true_momentum,
    true_momentum_ema: context.true_momentum_ema,
    hilo_score: context.hilo_score,
    hilo_thrust_state: context.hilo_thrust_state,
    match_strength: context.match_strength,
    parity_status: context.parity_status,
    b8_outcome_status: context.b8_outcome_status,
    c3_readiness_status: context.c3_readiness_status,
    checklist_pass_count: context.trigger_checklist?.summary.pass ?? 0,
    checklist_total_count: context.trigger_checklist?.summary.total ?? 0,
    decision_gates,
    caveats,
    research_notes: context.research_notes.slice(),
    non_actionable: true,
  };
}

export function buildTrueMomentumResearchCandidateProposalSet(
  args: BuildTrueMomentumResearchCandidateArgs,
): TrueMomentumResearchCandidateProposalSet {
  const generatedAt = args.generatedAt ?? new Date().toISOString();
  const signature = deriveQueueSignature(args.queueCandidates);
  const proposals: TrueMomentumResearchCandidateProposal[] = [];
  for (const candidate of args.queueCandidates) {
    const proposal = buildProposalForCandidate(candidate, args, generatedAt, signature);
    if (proposal) proposals.push(proposal);
  }
  const summary = summarizeTrueMomentumResearchCandidates(
    { proposals, generated_at: generatedAt } as TrueMomentumResearchCandidateProposalSet,
  );
  return {
    schema_version: TRUE_MOMENTUM_RESEARCH_CANDIDATES_SCHEMA_VERSION,
    phase: TRUE_MOMENTUM_RESEARCH_CANDIDATES_PHASE,
    generated_at: generatedAt,
    source_queue_signature: signature,
    proposals,
    summary,
    deterministic_note: TRUE_MOMENTUM_RESEARCH_CANDIDATES_DETERMINISTIC_NOTE,
  };
}

export function summarizeTrueMomentumResearchCandidates(
  proposalSet: Pick<
    TrueMomentumResearchCandidateProposalSet,
    "proposals" | "generated_at"
  >,
): TrueMomentumResearchCandidateProposalSummary {
  const proposals = proposalSet.proposals;
  const symbolsCovered = Array.from(new Set(proposals.map((p) => p.symbol))).sort();
  let continuation = 0;
  let pullback = 0;
  let watch = 0;
  let proposed = 0;
  let blocked = 0;
  let blockedByParity = 0;
  let blockedByCompositeMismatch = 0;
  let insufficient = 0;
  let xlpComposite = false;
  for (const p of proposals) {
    if (p.proposal_type === "continuation_research") continuation += 1;
    else if (p.proposal_type === "pullback_research") pullback += 1;
    else watch += 1;
    if (p.proposal_status === "proposed_for_research") proposed += 1;
    if (
      p.proposal_status === "blocked_by_warning" ||
      p.proposal_status === "blocked_by_parity" ||
      p.proposal_status === "blocked_by_composite_mismatch"
    ) {
      blocked += 1;
    }
    if (p.proposal_status === "blocked_by_parity") blockedByParity += 1;
    if (p.proposal_status === "blocked_by_composite_mismatch") {
      blockedByCompositeMismatch += 1;
      if (p.symbol.toUpperCase() === "XLP") xlpComposite = true;
    }
    if (p.proposal_status === "insufficient_evidence") insufficient += 1;
  }
  return {
    generated_at: proposalSet.generated_at,
    candidate_count: proposals.length,
    proposed_for_research_count: proposed,
    continuation_count: continuation,
    pullback_count: pullback,
    watch_only_count: watch,
    blocked_count: blocked,
    blocked_by_parity_count: blockedByParity,
    blocked_by_composite_mismatch_count: blockedByCompositeMismatch,
    insufficient_evidence_count: insufficient,
    symbols_covered: symbolsCovered,
    parity_mixed: blockedByParity > 0 || blockedByCompositeMismatch > 0,
    xlp_composite_mismatch_present: xlpComposite,
    active_generation_reserved: true,
  };
}

export function partitionTrueMomentumResearchCandidatesByFamily(
  proposalSet: TrueMomentumResearchCandidateProposalSet,
): TrueMomentumResearchCandidateFamilyBucket[] {
  const buckets = new Map<
    TrueMomentumStrategyPreviewFamilyId,
    TrueMomentumResearchCandidateFamilyBucket
  >();
  for (const p of proposalSet.proposals) {
    const bucket = buckets.get(p.proposed_family_id) ?? {
      family_id: p.proposed_family_id,
      family_label: p.proposed_family_label,
      proposals: [],
    };
    bucket.proposals.push(p);
    buckets.set(p.proposed_family_id, bucket);
  }
  return Array.from(buckets.values());
}

const STATUS_RANK: Record<TrueMomentumResearchCandidateProposalStatus, number> = {
  proposed_for_research: 0,
  insufficient_evidence: 1,
  watch_only: 2,
  blocked_by_warning: 3,
  blocked_by_parity: 4,
  blocked_by_composite_mismatch: 5,
};

export function rankTrueMomentumResearchCandidates(
  proposalSet: TrueMomentumResearchCandidateProposalSet,
): TrueMomentumResearchCandidateProposal[] {
  return proposalSet.proposals.slice().sort((a, b) => {
    const sa = STATUS_RANK[a.proposal_status] ?? 99;
    const sb = STATUS_RANK[b.proposal_status] ?? 99;
    if (sa !== sb) return sa - sb;
    return a.rank - b.rank;
  });
}

const STATUS_LABELS: Record<TrueMomentumResearchCandidateProposalStatus, string> = {
  proposed_for_research: "Proposed for research",
  watch_only: "Watch only",
  blocked_by_warning: "Blocked by warning",
  blocked_by_parity: "Blocked by parity",
  blocked_by_composite_mismatch: "Blocked by composite mismatch",
  insufficient_evidence: "Insufficient evidence",
};

const STATUS_TONES: Record<
  TrueMomentumResearchCandidateProposalStatus,
  "good" | "warn" | "bad" | "neutral"
> = {
  proposed_for_research: "good",
  watch_only: "warn",
  blocked_by_warning: "warn",
  blocked_by_parity: "warn",
  blocked_by_composite_mismatch: "warn",
  insufficient_evidence: "neutral",
};

export function trueMomentumResearchCandidateStatusLabel(
  status: TrueMomentumResearchCandidateProposalStatus | string,
): string {
  return STATUS_LABELS[status as TrueMomentumResearchCandidateProposalStatus] ?? status;
}

export function trueMomentumResearchCandidateTone(
  status: TrueMomentumResearchCandidateProposalStatus | string,
): "good" | "warn" | "bad" | "neutral" {
  return STATUS_TONES[status as TrueMomentumResearchCandidateProposalStatus] ?? "neutral";
}

export function validateTrueMomentumResearchCandidateProposalSet(
  proposalSet: TrueMomentumResearchCandidateProposalSet,
): string[] {
  const errors: string[] = [];
  if (proposalSet.schema_version !== TRUE_MOMENTUM_RESEARCH_CANDIDATES_SCHEMA_VERSION) {
    errors.push(`schema_version must be ${TRUE_MOMENTUM_RESEARCH_CANDIDATES_SCHEMA_VERSION}`);
  }
  if (proposalSet.phase !== TRUE_MOMENTUM_RESEARCH_CANDIDATES_PHASE) {
    errors.push("phase must be C5");
  }
  for (const p of proposalSet.proposals) {
    if (p.non_actionable !== true) {
      errors.push(`proposal ${p.proposal_id} must carry non_actionable: true`);
    }
    const required = ["operator_authorization", "active_generation_reserved"];
    for (const gateId of required) {
      const gate = p.decision_gates.find((g) => g.id === gateId);
      if (!gate || !gate.blocks_activation) {
        errors.push(
          `proposal ${p.proposal_id} must include a blocking ${gateId} gate`,
        );
      }
    }
  }
  return errors;
}

export function buildTrueMomentumResearchCandidateMarkdown(
  proposalSet: TrueMomentumResearchCandidateProposalSet,
): string {
  const lines: string[] = [];
  lines.push("# Phase C5 — True Momentum research candidate proposal");
  lines.push("");
  lines.push(`- Generated at: \`${proposalSet.generated_at}\``);
  lines.push(`- Schema: \`${proposalSet.schema_version}\``);
  lines.push("");
  lines.push("_C5 research candidate proposals are non-active and non-ordering._");
  lines.push("");
  lines.push("## Summary");
  lines.push("");
  const s = proposalSet.summary;
  lines.push(`- Candidates analyzed: ${s.candidate_count}`);
  lines.push(`- Proposed for research: ${s.proposed_for_research_count}`);
  lines.push(`- Continuation: ${s.continuation_count}`);
  lines.push(`- Pullback: ${s.pullback_count}`);
  lines.push(`- Watch-only: ${s.watch_only_count}`);
  lines.push(`- Blocked: ${s.blocked_count}`);
  lines.push(`- Insufficient evidence: ${s.insufficient_evidence_count}`);
  lines.push(`- Symbols covered: ${s.symbols_covered.join(", ") || "—"}`);
  lines.push(
    `- XLP composite mismatch present: ${s.xlp_composite_mismatch_present ? "yes" : "no"}`,
  );
  lines.push("");
  lines.push("## Family groups");
  lines.push("");
  for (const bucket of partitionTrueMomentumResearchCandidatesByFamily(proposalSet)) {
    lines.push(`### ${bucket.family_label}`);
    lines.push("");
    lines.push(
      "| Rank | Symbol | Source strategy | Status | Confidence | Active score | Checklist | Caveats |",
    );
    lines.push("|---:|---|---|---|---|---:|---|---|");
    for (const p of bucket.proposals) {
      lines.push(
        `| ${p.rank} | ${p.symbol} | ${p.source_strategy} | ${trueMomentumResearchCandidateStatusLabel(p.proposal_status)} | ${p.confidence_tier} | ${p.active_score?.toFixed(3) ?? "—"} | ${p.checklist_pass_count}/${p.checklist_total_count} | ${p.caveats.join("; ") || "—"} |`,
      );
    }
    lines.push("");
  }
  lines.push("## Blockers (research-only — do not interpret as approval gates)");
  lines.push("");
  lines.push("- Operator authorization required for any future active Phase C decision.");
  lines.push("- Active Phase C generation remains reserved / not implemented.");
  lines.push("- Accumulated B8 outcome evidence corpus required across sectors / regimes.");
  lines.push("- C3 cohort review required to reach a representative sector / regime mix.");
  if (s.xlp_composite_mismatch_present) {
    lines.push(
      "- XLP composite mismatch under review (oscillator aligned, composite total score differs).",
    );
  }
  lines.push("");
  lines.push("## Not a recommendation");
  lines.push("");
  lines.push(
    "These proposals are research-only. They do not enter the ranked queue, and do not approve, reject, size, or route trades. They never create paper orders.",
  );
  return lines.join("\n") + "\n";
}

export function buildTrueMomentumResearchCandidateJson(
  proposalSet: TrueMomentumResearchCandidateProposalSet,
): TrueMomentumResearchCandidateExportPayload {
  return {
    schema_version: TRUE_MOMENTUM_RESEARCH_CANDIDATES_SCHEMA_VERSION,
    proposal_set: proposalSet,
    deterministic_note: TRUE_MOMENTUM_RESEARCH_CANDIDATES_DETERMINISTIC_NOTE,
  };
}
