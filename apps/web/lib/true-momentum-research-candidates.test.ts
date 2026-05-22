import { describe, expect, it } from "vitest";

import type { MomentumRankingStatus } from "@/lib/momentum-ranking-status";
import type { QueueCandidate } from "@/lib/recommendations";
import type { TrueMomentumStrategyFamilyStatus } from "@/lib/true-momentum-strategy-families";
import {
  buildTrueMomentumResearchCandidateJson,
  buildTrueMomentumResearchCandidateMarkdown,
  buildTrueMomentumResearchCandidateProposalSet,
  partitionTrueMomentumResearchCandidatesByFamily,
  rankTrueMomentumResearchCandidates,
  summarizeTrueMomentumResearchCandidates,
  TRUE_MOMENTUM_RESEARCH_CANDIDATES_DETERMINISTIC_NOTE,
  TRUE_MOMENTUM_RESEARCH_CANDIDATES_PHASE,
  TRUE_MOMENTUM_RESEARCH_CANDIDATES_SCHEMA_VERSION,
  trueMomentumResearchCandidateStatusLabel,
  trueMomentumResearchCandidateTone,
  validateTrueMomentumResearchCandidateProposalSet,
} from "@/lib/true-momentum-research-candidates";

function familyStatus(): TrueMomentumStrategyFamilyStatus {
  return {
    requested_mode: "research_preview",
    effective_mode: "research_preview",
    enabled: true,
    guard_enabled: true,
    invalid_env_value: false,
    mode_env_var: "MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE",
    guard_env_var: "MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES",
    reason_codes: [],
    guardrails: [],
    family_specs: [],
    phase: "C0",
    implementation_status: "research_preview",
    parity_status: "validated_against_thinkorswim_fixture",
    parity_required_for_active: true,
  };
}

function rankingStatus(
  overrides: Partial<MomentumRankingStatus> = {},
): MomentumRankingStatus {
  return {
    mode: "active",
    default_mode: "shadow",
    env_var: "MACMARKET_MOMENTUM_RANKING_MODE",
    enabled: true,
    applied_by_default: true,
    parity_status: "validated_against_thinkorswim_fixture",
    parity_fixture_manifest_present: true,
    parity_required_for_active: true,
    real_thinkorswim_parity_pending: false,
    reason_codes: [],
    guardrails: [],
    thinkorswim_parity_workflow_status: "passed",
    thinkorswim_parity_visual_attestation_status: "visual_attested",
    thinkorswim_parity_visual_attestation_count: 4,
    thinkorswim_parity_visual_attestation_passed_count: 3,
    thinkorswim_parity_visual_attestation_failed_count: 1,
    thinkorswim_parity_visual_attestation_partial_count: 0,
    thinkorswim_parity_symbol_summaries: [
      {
        symbol: "SPY",
        status: "visual_attested",
        diagnostic_classification: ["oscillator_aligned"],
        diagnostic_flags: { oscillator_aligned: true },
        reason_codes: [],
      },
      {
        symbol: "XLP",
        status: "visual_failed",
        diagnostic_classification: ["oscillator_aligned", "composite_mismatch"],
        diagnostic_flags: {
          oscillator_aligned: true,
          composite_score_failed: true,
        },
        reason_codes: ["thinkorswim_visual_attestation_failed"],
      },
    ],
    ...overrides,
  };
}

function candidate(overrides: Partial<QueueCandidate> = {}): QueueCandidate {
  return {
    rank: 1,
    symbol: "XLK",
    side: "long",
    strategy: "Event Continuation",
    workflow_source: "test",
    timeframe: "1D",
    status: "pending",
    score: 0.62,
    score_before_momentum: 0.55,
    score_after_momentum: 0.62,
    momentum_score_delta: 0.07,
    expected_rr: 1.8,
    confidence: 0.7,
    reason_text: "Event continuation candidate",
    thesis: "Operator captured this.",
    trigger: "Hold above prior day high",
    entry_zone: { low: 100, high: 101 },
    invalidation: { price: 99 },
    momentum_contribution: {
      mode: "active",
      enabled: true,
      applied: true,
      total_contribution: 20,
      shadow_contribution: 20,
      momentum_alignment_score: 5,
      trend_alignment_score: 100,
      hilo_confirmation_bonus: 15,
      reversal_warning_penalty: 0,
      no_trade_warning: false,
      pullback_signal: false,
      reversal_warning: false,
      total_score: 100,
      total_label: "Max Bull",
      trend_score: 100,
      momo_score: 100,
      inferred_direction: "long",
      reason_codes: [],
      raw_total_contribution: 20,
      applied_score_delta: 0.07,
      active_delta_scale: 0.35,
    },
    ...overrides,
  };
}

describe("buildTrueMomentumResearchCandidateProposalSet", () => {
  it("returns a versioned, deterministic-note-bearing proposal set", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [candidate({ symbol: "SPY" })],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
      generatedAt: "2026-05-15T00:00:00.000Z",
    });
    expect(set.schema_version).toBe(TRUE_MOMENTUM_RESEARCH_CANDIDATES_SCHEMA_VERSION);
    expect(set.phase).toBe(TRUE_MOMENTUM_RESEARCH_CANDIDATES_PHASE);
    expect(set.deterministic_note).toBe(
      TRUE_MOMENTUM_RESEARCH_CANDIDATES_DETERMINISTIC_NOTE,
    );
    expect(set.proposals.length).toBe(1);
    expect(set.proposals[0]?.non_actionable).toBe(true);
  });

  it("classifies a passing SPY continuation candidate as proposed_for_research with continuation type", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [candidate({ symbol: "SPY" })],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
      b8OutcomeStatus: "available",
      cohortReadinessStatus: "promising_research",
    });
    const proposal = set.proposals[0];
    expect(proposal?.proposal_type).toBe("continuation_research");
    expect(proposal?.proposal_status).toBe("proposed_for_research");
  });

  it("classifies an XLP candidate as blocked_by_composite_mismatch and watch_only_research", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [candidate({ symbol: "XLP" })],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const proposal = set.proposals[0];
    expect(proposal?.proposal_type).toBe("watch_only_research");
    expect(proposal?.proposal_status).toBe("blocked_by_composite_mismatch");
    expect(set.summary.xlp_composite_mismatch_present).toBe(true);
  });

  it("does not block an unrelated symbol just because XLP composite mismatch is present", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [
        candidate({ symbol: "SPY", rank: 1 }),
        candidate({ symbol: "XLP", rank: 2 }),
      ],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
      b8OutcomeStatus: "available",
      cohortReadinessStatus: "promising_research",
    });
    const spy = set.proposals.find((p) => p.symbol === "SPY");
    const xlp = set.proposals.find((p) => p.symbol === "XLP");
    expect(spy?.proposal_status).toBe("proposed_for_research");
    expect(xlp?.proposal_status).toBe("blocked_by_composite_mismatch");
  });

  it("emits a watch_only_research proposal for a reversal-warning candidate", () => {
    const reversalCandidate = candidate({
      symbol: "AAPL",
      strategy: "Event Continuation",
      momentum_contribution: {
        mode: "active",
        enabled: true,
        applied: true,
        total_contribution: -30,
        shadow_contribution: -30,
        momentum_alignment_score: -10,
        trend_alignment_score: -50,
        hilo_confirmation_bonus: -20,
        reversal_warning_penalty: 20,
        no_trade_warning: false,
        pullback_signal: false,
        reversal_warning: true,
        total_score: -60,
        total_label: "Max Bear",
        trend_score: -50,
        momo_score: -60,
        inferred_direction: "long",
        reason_codes: ["reversal_warning"],
        raw_total_contribution: -30,
        applied_score_delta: -0.07,
        active_delta_scale: 0.35,
      },
    });
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [reversalCandidate],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const proposal = set.proposals[0];
    expect(proposal?.proposal_type).toBe("watch_only_research");
  });

  it("always attaches the two activation-blocking decision gates", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [candidate({ symbol: "SPY" })],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const proposal = set.proposals[0];
    const opAuth = proposal?.decision_gates.find(
      (g) => g.id === "operator_authorization",
    );
    const activeGen = proposal?.decision_gates.find(
      (g) => g.id === "active_generation_reserved",
    );
    expect(opAuth?.blocks_activation).toBe(true);
    expect(activeGen?.blocks_activation).toBe(true);
  });
});

describe("summarizeTrueMomentumResearchCandidates", () => {
  it("counts continuation / pullback / watch / blocked / insufficient buckets", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [
        candidate({ symbol: "SPY", rank: 1 }),
        candidate({ symbol: "XLP", rank: 2 }),
      ],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
      b8OutcomeStatus: "available",
      cohortReadinessStatus: "promising_research",
    });
    const summary = summarizeTrueMomentumResearchCandidates(set);
    expect(summary.candidate_count).toBe(2);
    expect(summary.symbols_covered).toEqual(["SPY", "XLP"]);
    expect(summary.parity_mixed).toBe(true);
    expect(summary.xlp_composite_mismatch_present).toBe(true);
    expect(summary.active_generation_reserved).toBe(true);
  });
});

describe("partitionTrueMomentumResearchCandidatesByFamily", () => {
  it("groups proposals by family_id", () => {
    const reversalCandidate = candidate({
      symbol: "AAPL",
      rank: 3,
      strategy: "Event Continuation",
      momentum_contribution: {
        mode: "active",
        enabled: true,
        applied: true,
        total_contribution: -30,
        shadow_contribution: -30,
        momentum_alignment_score: -10,
        trend_alignment_score: -50,
        hilo_confirmation_bonus: -20,
        reversal_warning_penalty: 20,
        no_trade_warning: false,
        pullback_signal: false,
        reversal_warning: true,
        total_score: -60,
        total_label: "Max Bear",
        trend_score: -50,
        momo_score: -60,
        inferred_direction: "long",
        reason_codes: ["reversal_warning"],
        raw_total_contribution: -30,
        applied_score_delta: -0.07,
        active_delta_scale: 0.35,
      },
    });
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [
        candidate({ symbol: "SPY", rank: 1 }),
        candidate({ symbol: "XLP", rank: 2 }),
        reversalCandidate,
      ],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const buckets = partitionTrueMomentumResearchCandidatesByFamily(set);
    const families = buckets.map((b) => b.family_id).sort();
    expect(families).toContain("true_momentum_continuation");
    expect(families).toContain("true_momentum_reversal_watch");
  });
});

describe("rankTrueMomentumResearchCandidates", () => {
  it("places proposed_for_research before blocked rows", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [
        candidate({ symbol: "XLP", rank: 1 }),
        candidate({ symbol: "SPY", rank: 2 }),
      ],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
      b8OutcomeStatus: "available",
      cohortReadinessStatus: "promising_research",
    });
    const ranked = rankTrueMomentumResearchCandidates(set);
    expect(ranked[0]?.symbol).toBe("SPY");
    expect(ranked[ranked.length - 1]?.symbol).toBe("XLP");
  });
});

describe("buildTrueMomentumResearchCandidateMarkdown", () => {
  it("renders a research-only header, summary, and the not-a-recommendation closer", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [
        candidate({ symbol: "SPY", rank: 1 }),
        candidate({ symbol: "XLP", rank: 2 }),
      ],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
      generatedAt: "2026-05-15T00:00:00.000Z",
    });
    const md = buildTrueMomentumResearchCandidateMarkdown(set);
    expect(md).toContain("Phase C5");
    expect(md).toContain("research candidate proposal");
    expect(md).toContain("Summary");
    expect(md).toContain("Not a recommendation");
    expect(md).toContain("research-only");
    expect(md).toContain("XLP composite mismatch under review");
  });

  it("never embeds forbidden trade-action language", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [candidate({ symbol: "SPY" })],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const md = buildTrueMomentumResearchCandidateMarkdown(set).toLowerCase();
    for (const forbidden of [
      "approve trade",
      "auto approve",
      "route order",
      "place order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "ready for live",
    ]) {
      expect(md.includes(forbidden)).toBe(false);
    }
  });
});

describe("buildTrueMomentumResearchCandidateJson", () => {
  it("emits the schema-versioned payload with the deterministic note", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [candidate({ symbol: "SPY" })],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const payload = buildTrueMomentumResearchCandidateJson(set);
    expect(payload.schema_version).toBe(
      TRUE_MOMENTUM_RESEARCH_CANDIDATES_SCHEMA_VERSION,
    );
    expect(payload.deterministic_note).toBe(
      TRUE_MOMENTUM_RESEARCH_CANDIDATES_DETERMINISTIC_NOTE,
    );
    expect(payload.proposal_set.proposals.length).toBeGreaterThan(0);
  });
});

describe("validateTrueMomentumResearchCandidateProposalSet", () => {
  it("returns no errors for a freshly-built proposal set", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [candidate({ symbol: "SPY" })],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    expect(validateTrueMomentumResearchCandidateProposalSet(set)).toEqual([]);
  });

  it("flags a proposal that drops the operator_authorization gate", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [candidate({ symbol: "SPY" })],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const tampered = {
      ...set,
      proposals: set.proposals.map((p) => ({
        ...p,
        decision_gates: p.decision_gates.filter(
          (g) => g.id !== "operator_authorization",
        ),
      })),
    };
    const errors = validateTrueMomentumResearchCandidateProposalSet(tampered);
    expect(errors.length).toBeGreaterThan(0);
  });
});

describe("trueMomentumResearchCandidateStatusLabel / Tone", () => {
  it("returns human labels for known statuses", () => {
    expect(trueMomentumResearchCandidateStatusLabel("proposed_for_research")).toBe(
      "Proposed for research",
    );
    expect(trueMomentumResearchCandidateStatusLabel("blocked_by_composite_mismatch")).toContain(
      "composite",
    );
  });

  it("returns tones aligned with status severity", () => {
    expect(trueMomentumResearchCandidateTone("proposed_for_research")).toBe("good");
    expect(trueMomentumResearchCandidateTone("watch_only")).toBe("warn");
    expect(trueMomentumResearchCandidateTone("blocked_by_composite_mismatch")).toBe("warn");
    expect(trueMomentumResearchCandidateTone("insufficient_evidence")).toBe("neutral");
  });
});
