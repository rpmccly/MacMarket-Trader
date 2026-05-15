// Phase C — True Momentum research closeout status helper.
//
// Pure, side-effect-free helpers that summarize the current Phase C
// posture (research-only) and the blocking items that remain before
// any future active Phase C is even considered. The module:
//
// - never generates queue candidates,
// - never approves / rejects / sizes / routes trades,
// - never calls a backend, provider, or LLM,
// - never returns a live-execution status,
// - never auto-resolves blockers.
//
// Consumed by ``components/recommendations/true-momentum-phase-c-closeout-card.tsx``
// and by the Phase C closeout integration guard tests.

import type { MomentumRankingStatus } from "@/lib/momentum-ranking-status";
import {
  findSelectedSymbolParitySummary,
  type SelectedSymbolParitySummary,
} from "@/lib/true-momentum-strategy-context";
import type { TrueMomentumCohortReadinessStatus } from "@/lib/true-momentum-cohort-review";

export const TRUE_MOMENTUM_PHASE_C_CLOSEOUT_DETERMINISTIC_NOTE =
  "Phase C research closeout is operator readiness context only. It does not generate queue candidates, and does not approve, reject, size, or route trades. It also does not activate Phase C strategy families.";

export type TrueMomentumPhaseCBlockerId =
  | "parity_mixed"
  | "xlp_composite_mismatch"
  | "insufficient_b8_evidence"
  | "insufficient_c3_cohort"
  | "operator_authorization_required"
  | "active_generation_not_implemented";

export type TrueMomentumPhaseCBlocker = {
  id: TrueMomentumPhaseCBlockerId;
  label: string;
  detail: string;
  /**
   * Per-symbol detail when the blocker is symbol-scoped (e.g. XLP
   * composite mismatch). Empty array when the blocker is global.
   */
  symbols: string[];
};

export type TrueMomentumPhaseCShippedPhaseId =
  | "C0"
  | "C1"
  | "C2"
  | "C2.1"
  | "C2.2"
  | "C3"
  | "C4"
  | "C4.1"
  | "C4.2";

export const TRUE_MOMENTUM_PHASE_C_SHIPPED_PHASES: ReadonlyArray<TrueMomentumPhaseCShippedPhaseId> = [
  "C0",
  "C1",
  "C2",
  "C2.1",
  "C2.2",
  "C3",
  "C4",
  "C4.1",
  "C4.2",
];

export type TrueMomentumPhaseCParitySummary = {
  visual_attestation_passed_symbols: string[];
  visual_attestation_failed_symbols: string[];
  visual_attestation_partial_symbols: string[];
  oscillator_aligned_symbols: string[];
  composite_mismatch_symbols: string[];
};

export type TrueMomentumPhaseCCloseoutStatus = {
  research_implementation_status: "complete" | "incomplete";
  active_generation_status: "reserved" | "disabled" | "not_implemented";
  can_generate_queue_candidates: false;
  can_approve_trades: false;
  can_route_orders: false;
  can_size_trades: false;
  can_create_paper_orders: false;
  can_change_paper_order_behavior: false;
  blockers: TrueMomentumPhaseCBlocker[];
  shipped_phases: ReadonlyArray<TrueMomentumPhaseCShippedPhaseId>;
  current_parity_summary: TrueMomentumPhaseCParitySummary;
  next_allowed_phase: {
    id: string;
    label: string;
    description: string;
  };
  recommended_action: string;
  deterministic_note: string;
};

export type TrueMomentumPhaseCCompletionSummary = {
  shipped: ReadonlyArray<TrueMomentumPhaseCShippedPhaseId>;
  blockers_open: number;
  composite_mismatch_symbols: string[];
};

const NEXT_ALLOWED_PHASE = {
  id: "C5",
  label: "C5 research candidate proposal",
  description:
    "C5 may propose research candidates only — still non-active, still non-ordering, and still gated behind operator authorization, an accumulated B8 outcome evidence corpus, and a representative C3 cohort review.",
} as const;

const RECOMMENDED_ACTION =
  "Continue research evidence collection. Resolve / document the XLP composite mismatch, accumulate the B8 outcome evidence corpus, and broaden the C3 cohort review across sectors and regimes before any operator authorization decision.";

export type BuildTrueMomentumPhaseCCloseoutArgs = {
  rankingStatus: MomentumRankingStatus | null | undefined;
  /**
   * Accumulated B8 outcome status surfaced from the operator's
   * Recommendations page (passes through the same value the C4 card
   * already consumes).
   */
  b8OutcomeStatus?:
    | "available"
    | "captured_without_outcomes"
    | "not_captured"
    | "unavailable";
  /**
   * C3 cohort readiness status. Defaults to "not_evaluated".
   */
  cohortReadinessStatus?:
    | TrueMomentumCohortReadinessStatus
    | "not_evaluated"
    | null;
};

export function buildTrueMomentumPhaseCCloseoutStatus(
  args: BuildTrueMomentumPhaseCCloseoutArgs,
): TrueMomentumPhaseCCloseoutStatus {
  const blockers: TrueMomentumPhaseCBlocker[] = [];
  const parity_summary = buildTrueMomentumPhaseCParitySummary(args.rankingStatus);

  // Parity blocker — surface every symbol carrying composite_mismatch.
  const compositeMismatchSymbols = parity_summary.composite_mismatch_symbols;
  if (compositeMismatchSymbols.length > 0) {
    blockers.push({
      id: "parity_mixed",
      label: "Visual parity mixed",
      detail:
        "At least one visual_attestation fixture is oscillator_aligned + composite_mismatch. Resolve or document the composite-score divergence before treating parity as fully attested.",
      symbols: compositeMismatchSymbols,
    });
    // XLP-specific blocker — surface separately so the closeout card
    // and the docs contract test can pin the current research item by
    // name. Fires whenever the parity summary carries XLP as a
    // composite_mismatch symbol; never blocks unrelated symbols.
    if (
      compositeMismatchSymbols
        .map((s) => s.toUpperCase())
        .includes("XLP")
    ) {
      blockers.push({
        id: "xlp_composite_mismatch",
        label: "XLP composite mismatch under review",
        detail:
          "XLP visual_attestation: True Momentum / EMA oscillator fields aligned, but composite total score / label differ (ToS 35 Neutral vs MM 65 Neutral Up). Resolve or document the divergence (capture MM composite breakdown + close-price context) before any future active Phase C decision.",
        symbols: ["XLP"],
      });
    }
  }

  // B8 outcome evidence corpus.
  const b8 = args.b8OutcomeStatus ?? "unavailable";
  if (b8 !== "available") {
    blockers.push({
      id: "insufficient_b8_evidence",
      label: "Need accumulated B8 outcome evidence",
      detail:
        "An accumulated Phase B8 outcome evidence corpus across sectors and regimes is still required before any future active Phase C decision.",
      symbols: [],
    });
  }

  // C3 cohort review.
  const cohort = args.cohortReadinessStatus ?? "not_evaluated";
  if (
    cohort === "not_evaluated" ||
    cohort === "insufficient_evidence" ||
    cohort === "parity_blocked" ||
    cohort === "needs_operator_review" ||
    cohort === "not_recommended_for_activation"
  ) {
    blockers.push({
      id: "insufficient_c3_cohort",
      label: "Need C3 cohort evidence across sectors / regimes",
      detail:
        "Phase C3 cohort review must reach a representative sector / regime mix before activation is considered.",
      symbols: [],
    });
  }

  // Operator authorization remains a hard prerequisite.
  blockers.push({
    id: "operator_authorization_required",
    label: "Operator authorization required",
    detail:
      "Explicit operator authorization is required for any future move toward active Phase C strategy generation. Activation is never automatic.",
    symbols: [],
  });

  // Active generation is structurally not implemented.
  blockers.push({
    id: "active_generation_not_implemented",
    label: "Active Phase C generation is not implemented",
    detail:
      "The True Momentum strategy families remain disabled by default. No active generator function exists; the C0 mode + safety guard env vars must be flipped explicitly and only after the other blockers clear.",
    symbols: [],
  });

  return {
    research_implementation_status: "complete",
    active_generation_status: "reserved",
    can_generate_queue_candidates: false,
    can_approve_trades: false,
    can_route_orders: false,
    can_size_trades: false,
    can_create_paper_orders: false,
    can_change_paper_order_behavior: false,
    blockers,
    shipped_phases: TRUE_MOMENTUM_PHASE_C_SHIPPED_PHASES,
    current_parity_summary: parity_summary,
    next_allowed_phase: NEXT_ALLOWED_PHASE,
    recommended_action: RECOMMENDED_ACTION,
    deterministic_note: TRUE_MOMENTUM_PHASE_C_CLOSEOUT_DETERMINISTIC_NOTE,
  };
}

/**
 * Project the per-symbol parity summary into the lists the closeout
 * card renders (pass, fail, partial, oscillator-aligned,
 * composite-mismatch). Pure helper — never mutates inputs.
 */
export function buildTrueMomentumPhaseCParitySummary(
  rankingStatus: MomentumRankingStatus | null | undefined,
): TrueMomentumPhaseCParitySummary {
  const summary: TrueMomentumPhaseCParitySummary = {
    visual_attestation_passed_symbols: [],
    visual_attestation_failed_symbols: [],
    visual_attestation_partial_symbols: [],
    oscillator_aligned_symbols: [],
    composite_mismatch_symbols: [],
  };
  const entries = rankingStatus?.thinkorswim_parity_symbol_summaries;
  if (!Array.isArray(entries)) return summary;
  for (const entry of entries) {
    if (!entry || typeof entry !== "object") continue;
    const symbol = typeof entry.symbol === "string" ? entry.symbol.toUpperCase() : "";
    if (!symbol) continue;
    const status = typeof entry.status === "string" ? entry.status : "";
    if (status === "visual_attested" || status === "passed") {
      summary.visual_attestation_passed_symbols.push(symbol);
    } else if (status === "visual_failed" || status === "failed") {
      summary.visual_attestation_failed_symbols.push(symbol);
    } else if (status === "visual_partial" || status === "partial") {
      summary.visual_attestation_partial_symbols.push(symbol);
    }
    const classification = entry.diagnostic_classification;
    if (Array.isArray(classification)) {
      if (classification.includes("oscillator_aligned")) {
        summary.oscillator_aligned_symbols.push(symbol);
      }
      if (classification.includes("composite_mismatch")) {
        summary.composite_mismatch_symbols.push(symbol);
      }
    }
  }
  return summary;
}

export function collectCompositeMismatchSymbols(
  rankingStatus: MomentumRankingStatus | null | undefined,
): string[] {
  const summaries = rankingStatus?.thinkorswim_parity_symbol_summaries;
  if (!Array.isArray(summaries)) return [];
  const out: string[] = [];
  for (const entry of summaries) {
    if (!entry || typeof entry !== "object") continue;
    const classification = entry.diagnostic_classification;
    if (!Array.isArray(classification)) continue;
    if (!classification.includes("composite_mismatch")) continue;
    const symbol = typeof entry.symbol === "string" ? entry.symbol.toUpperCase() : "";
    if (symbol) out.push(symbol);
  }
  return out;
}

export function summarizeTrueMomentumPhaseCCloseout(
  status: TrueMomentumPhaseCCloseoutStatus,
): TrueMomentumPhaseCCompletionSummary {
  return {
    shipped: status.shipped_phases,
    blockers_open: status.blockers.length,
    composite_mismatch_symbols:
      status.current_parity_summary.composite_mismatch_symbols.slice(),
  };
}

export function trueMomentumPhaseCCloseoutBlockerLabels(
  status: TrueMomentumPhaseCCloseoutStatus,
): string[] {
  return status.blockers.map((b) => b.label);
}

/**
 * Convenience: pull the selected-candidate parity summary for the
 * symbol the operator is viewing. Re-exported here so the closeout
 * card can show a focused per-symbol caveat without re-importing the
 * C4 helper module.
 */
export function findCloseoutSelectedSymbolSummary(
  rankingStatus: MomentumRankingStatus | null | undefined,
  symbol: string | null | undefined,
): SelectedSymbolParitySummary | null {
  return findSelectedSymbolParitySummary(rankingStatus, symbol);
}
