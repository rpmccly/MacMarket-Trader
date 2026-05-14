import { describe, expect, it } from "vitest";

import type { MomentumRankingStatus } from "@/lib/momentum-ranking-status";
import type { QueueCandidate } from "@/lib/recommendations";
import {
  buildTrueMomentumStrategyContext,
  buildTrueMomentumTriggerChecklist,
  classifyTrueMomentumStrategyActivationReadiness,
  collectTrueMomentumStrategyContextSurfaces,
  findSelectedSymbolParitySummary,
  summarizeTrueMomentumStrategyContext,
  trueMomentumStrategyActivationReadinessLabel,
  trueMomentumStrategyActivationReadinessTone,
  TRUE_MOMENTUM_STRATEGY_CONTEXT_DETERMINISTIC_NOTE,
} from "@/lib/true-momentum-strategy-context";

const FORBIDDEN_NOTE_FRAGMENTS = [
  ["app", "rove ", "tra", "de"].join(""),
  ["au", "to a", "ppr", "ove"].join(""),
  ["rou", "te o", "rd", "er"].join(""),
  ["pla", "ce o", "rd", "er"].join(""),
  ["b", "uy n", "o", "w"].join(""),
  ["s", "ell n", "o", "w"].join(""),
  ["e", "nter n", "o", "w"].join(""),
  ["s", "hort n", "o", "w"].join(""),
];
import type { TrueMomentumStrategyFamilyStatus } from "@/lib/true-momentum-strategy-families";

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
        timeframe: "1D",
        fixture_name: "SPY_1D_visual_attestation_2026_05_13",
        parity_mode: "visual_attestation",
        status: "visual_attested",
        diagnostic_classification: ["oscillator_aligned"],
        diagnostic_flags: {
          oscillator_aligned: true,
          composite_score_failed: false,
        },
        reason_codes: ["thinkorswim_visual_attested"],
        observed_bar_date: "2026-05-13",
      },
      {
        symbol: "XLP",
        timeframe: "1D",
        fixture_name: "XLP_1D_visual_attestation_2026_05_13",
        parity_mode: "visual_attestation",
        status: "visual_failed",
        diagnostic_classification: ["oscillator_aligned", "composite_mismatch"],
        diagnostic_flags: {
          oscillator_aligned: true,
          composite_score_failed: true,
        },
        reason_codes: ["thinkorswim_visual_attestation_failed"],
        observed_bar_date: "2026-05-13",
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

describe("findSelectedSymbolParitySummary", () => {
  it("returns the matching summary entry by symbol", () => {
    const summary = findSelectedSymbolParitySummary(rankingStatus(), "xlp");
    expect(summary?.symbol).toBe("XLP");
    expect(summary?.status).toBe("visual_failed");
    expect(summary?.diagnostic_classification).toContain("composite_mismatch");
  });

  it("returns null when no summary matches", () => {
    expect(findSelectedSymbolParitySummary(rankingStatus(), "AAPL")).toBeNull();
  });

  it("returns null when ranking status is unset", () => {
    expect(findSelectedSymbolParitySummary(null, "SPY")).toBeNull();
  });
});

describe("buildTrueMomentumStrategyContext", () => {
  it("returns null when no candidate is selected", () => {
    expect(
      buildTrueMomentumStrategyContext({
        candidate: null,
        strategyFamilyStatus: familyStatus(),
        rankingStatus: rankingStatus(),
      }),
    ).toBeNull();
  });

  it("classifies a strong continuation candidate as research_ready when parity passes for the symbol", () => {
    const ctx = buildTrueMomentumStrategyContext({
      candidate: candidate({ symbol: "SPY" }),
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    expect(ctx).not.toBeNull();
    expect(ctx?.family_id).toBe("true_momentum_continuation");
    expect(ctx?.match_strength).toBe("strong");
    expect(ctx?.parity_status).toBe("passed");
    expect(ctx?.readiness).toBe("research_ready");
  });

  it("classifies the XLP-style failing symbol as composite_mismatch_review", () => {
    const ctx = buildTrueMomentumStrategyContext({
      candidate: candidate({
        symbol: "XLP",
        strategy: "Event Continuation",
      }),
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    expect(ctx).not.toBeNull();
    expect(ctx?.parity_diagnostics.classification).toContain("composite_mismatch");
    expect(ctx?.readiness).toBe("composite_mismatch_review");
  });

  it("does not block an unrelated symbol when only XLP composite-mismatch fires globally", () => {
    const status = rankingStatus({
      thinkorswim_parity_visual_attestation_status: "visual_failed",
      thinkorswim_parity_workflow_status: "failed",
      thinkorswim_parity_symbol_summaries: [
        {
          symbol: "XLP",
          status: "visual_failed",
          diagnostic_classification: ["oscillator_aligned", "composite_mismatch"],
        },
      ],
    });
    const ctx = buildTrueMomentumStrategyContext({
      candidate: candidate({ symbol: "AAPL" }),
      strategyFamilyStatus: familyStatus(),
      rankingStatus: status,
    });
    expect(ctx?.parity_status).toBe("global_mixed");
    // AAPL is not the failing symbol — must NOT be classified as
    // parity_blocked solely because of XLP.
    expect(ctx?.readiness).not.toBe("parity_blocked");
    expect(ctx?.readiness).not.toBe("composite_mismatch_review");
  });

  it("classifies no_trade_warning candidates that land in reversal_watch family as watch_only", () => {
    // The C1 preview classifier routes no_trade_warning candidates into
    // reversal_watch. Per the Phase C4 rule "warning_blocked unless
    // family is reversal_watch", the readiness must end up watch_only.
    const c = candidate();
    c.momentum_contribution = {
      ...(c.momentum_contribution ?? {}),
      no_trade_warning: true,
    };
    const ctx = buildTrueMomentumStrategyContext({
      candidate: c,
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    expect(ctx?.no_trade_warning).toBe(true);
    expect(ctx?.family_id).toBe("true_momentum_reversal_watch");
    expect(ctx?.readiness).toBe("watch_only");
  });

  it("classifies reversal_warning candidates that land in reversal_watch family as watch_only", () => {
    const c = candidate();
    c.momentum_contribution = {
      ...(c.momentum_contribution ?? {}),
      reversal_warning: true,
    };
    const ctx = buildTrueMomentumStrategyContext({
      candidate: c,
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    expect(ctx?.reversal_warning).toBe(true);
    expect(ctx?.family_id).toBe("true_momentum_reversal_watch");
    expect(ctx?.readiness).toBe("watch_only");
  });

  it("classifies bearish-contradiction long-strategy candidates as watch_only", () => {
    const c = candidate({ symbol: "XLE" });
    c.momentum_contribution = {
      ...(c.momentum_contribution ?? {}),
      total_label: "Bear",
      total_score: -100,
      trend_score: -100,
      momo_score: -80,
    };
    const ctx = buildTrueMomentumStrategyContext({
      candidate: c,
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    expect(ctx?.family_id).toBe("true_momentum_reversal_watch");
    expect(ctx?.readiness).toBe("watch_only");
  });

  it("returns no family match when no preview classification fires", () => {
    const c = candidate({
      strategy: "Some neutral strategy",
      momentum_contribution: {
        mode: "active",
        enabled: true,
        applied: true,
        total_contribution: 0,
        no_trade_warning: false,
        pullback_signal: false,
        reversal_warning: false,
        total_score: 0,
        total_label: "Neutral",
        trend_score: 0,
        momo_score: 0,
        inferred_direction: "unknown",
        raw_total_contribution: 0,
        applied_score_delta: 0,
      },
    });
    const ctx = buildTrueMomentumStrategyContext({
      candidate: c,
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    expect(ctx?.family_id).toBeNull();
    expect(ctx?.readiness).toBe("not_applicable");
  });
});

describe("buildTrueMomentumTriggerChecklist", () => {
  it("builds the continuation checklist with status flags", () => {
    const ctx = buildTrueMomentumStrategyContext({
      candidate: candidate(),
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const checklist = ctx?.trigger_checklist;
    expect(checklist).not.toBeNull();
    expect(checklist?.family_id).toBe("true_momentum_continuation");
    const ids = checklist?.items.map((i) => i.id) ?? [];
    expect(ids).toContain("continuation_total_score");
    expect(ids).toContain("continuation_true_momentum_above_ema");
    expect(ids).toContain("continuation_trend_score");
    expect(ids).toContain("continuation_momo_score");
    expect(ids).toContain("continuation_hilo");
    expect(ids).toContain("continuation_no_trade");
    expect(ids).toContain("continuation_no_reversal");
    expect(ids).toContain("continuation_setup_exists");
    expect(ids).toContain("continuation_parity_review");
    expect(checklist?.summary.total).toBe(checklist?.items.length);
  });

  it("builds the pullback checklist when the source strategy is Pullback", () => {
    const ctx = buildTrueMomentumStrategyContext({
      candidate: candidate({
        symbol: "SPY",
        strategy: "Pullback",
      }),
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const checklist = ctx?.trigger_checklist;
    expect(checklist?.family_id).toBe("true_momentum_pullback");
    const ids = checklist?.items.map((i) => i.id) ?? [];
    expect(ids).toContain("pullback_signal_or_strategy");
    expect(ids).toContain("pullback_no_reversal");
    expect(ids).toContain("pullback_risk_invalidation");
  });

  it("builds the reversal-watch checklist for bear/long-strategy contradictions", () => {
    const c = candidate();
    c.momentum_contribution = {
      ...(c.momentum_contribution ?? {}),
      total_label: "Bear",
      total_score: -100,
    };
    const ctx = buildTrueMomentumStrategyContext({
      candidate: c,
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const checklist = ctx?.trigger_checklist;
    expect(checklist?.family_id).toBe("true_momentum_reversal_watch");
    const ids = checklist?.items.map((i) => i.id) ?? [];
    expect(ids).toContain("reversal_watch_trigger");
    expect(ids).toContain("reversal_watch_watch_only");
    expect(ids).toContain("reversal_watch_no_entry_proposed");
  });

  it("flags missing momentum fields as unavailable", () => {
    const c = candidate();
    c.momentum_contribution = {
      ...(c.momentum_contribution ?? {}),
      trend_score: null,
      momo_score: null,
    };
    const ctx = buildTrueMomentumStrategyContext({
      candidate: c,
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const checklist = ctx?.trigger_checklist;
    const trend = checklist?.items.find((i) => i.id === "continuation_trend_score");
    const momo = checklist?.items.find((i) => i.id === "continuation_momo_score");
    expect(trend?.status).toBe("unavailable");
    expect(momo?.status).toBe("unavailable");
  });

  it("returns null when no preview classification matches", () => {
    const c = candidate({
      strategy: "Some neutral strategy",
      momentum_contribution: {
        ...(candidate().momentum_contribution ?? {}),
        total_label: "Neutral",
        total_score: 0,
        raw_total_contribution: 0,
        applied_score_delta: 0,
      },
    });
    expect(
      buildTrueMomentumTriggerChecklist(
        c,
        null,
      ),
    ).toBeNull();
  });
});

describe("classifyTrueMomentumStrategyActivationReadiness", () => {
  it("returns research_ready when the checklist research-ready and parity passes", () => {
    const ctx = buildTrueMomentumStrategyContext({
      candidate: candidate({ symbol: "SPY" }),
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    expect(ctx?.readiness).toBe("research_ready");
  });

  it("reversal_watch family stays watch_only even when XLP composite-mismatch parity fires", () => {
    // The Phase C4 rule "If family is reversal_watch -> watch_only"
    // beats the composite_mismatch_review fallback. The composite
    // mismatch still surfaces in evidence_caveats / classification.
    const c = candidate({ symbol: "XLP" });
    c.momentum_contribution = {
      ...(c.momentum_contribution ?? {}),
      reversal_warning: true,
    };
    const ctx = buildTrueMomentumStrategyContext({
      candidate: c,
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    expect(ctx?.family_id).toBe("true_momentum_reversal_watch");
    expect(ctx?.readiness).toBe("watch_only");
    // Composite_mismatch parity diagnostic is still surfaced for the
    // audit trail, just not used as the readiness classification.
    expect(ctx?.parity_diagnostics.classification).toContain("composite_mismatch");
  });

  it("returns needs_more_evidence when cohort readiness is insufficient_evidence", () => {
    const ctx = buildTrueMomentumStrategyContext({
      candidate: candidate({ symbol: "SPY" }),
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
      cohortReadinessStatus: "insufficient_evidence",
    });
    expect(ctx?.readiness).toBe("needs_more_evidence");
  });
});

describe("labels / tones / forbidden language", () => {
  it("renders readiness labels and tones", () => {
    expect(trueMomentumStrategyActivationReadinessLabel("research_ready")).toBe(
      "Research-ready",
    );
    expect(trueMomentumStrategyActivationReadinessTone("research_ready")).toBe("good");
    expect(trueMomentumStrategyActivationReadinessTone("watch_only")).toBe("warn");
    expect(trueMomentumStrategyActivationReadinessTone("not_applicable")).toBe(
      "neutral",
    );
  });

  it("the deterministic note never includes action language", () => {
    const lowered = TRUE_MOMENTUM_STRATEGY_CONTEXT_DETERMINISTIC_NOTE.toLowerCase();
    for (const forbidden of [
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "place order",
      "route order",
    ]) {
      expect(lowered.includes(forbidden)).toBe(false);
    }
  });

  it("buildTrueMomentumStrategyContext output contains no forbidden action language", () => {
    const ctx = buildTrueMomentumStrategyContext({
      candidate: candidate(),
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const lower = collectTrueMomentumStrategyContextSurfaces(ctx)
      .join("\n")
      .toLowerCase();
    for (const fragment of FORBIDDEN_NOTE_FRAGMENTS) {
      expect(lower.includes(fragment)).toBe(false);
    }
  });

  it("summary helper returns family / readiness summary", () => {
    const ctx = buildTrueMomentumStrategyContext({
      candidate: candidate(),
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const summary = summarizeTrueMomentumStrategyContext(ctx);
    expect(summary?.family_id).toBe("true_momentum_continuation");
    expect(summary?.readiness).toBe("research_ready");
    expect(summary?.symbol).toBe("XLK");
  });
});

describe("NaN/Inf safety", () => {
  it("does not emit NaN or Infinity in numeric context fields when inputs are invalid", () => {
    const c = candidate();
    c.score = Number.NaN;
    c.score_before_momentum = Number.POSITIVE_INFINITY;
    c.momentum_score_delta = Number.NEGATIVE_INFINITY;
    const ctx = buildTrueMomentumStrategyContext({
      candidate: c,
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const fields = [
      ctx?.active_score,
      ctx?.baseline_score,
      ctx?.raw_contribution,
      ctx?.applied_delta,
      ctx?.total_score,
      ctx?.trend_score,
      ctx?.momo_score,
    ];
    for (const v of fields) {
      if (v != null) {
        expect(Number.isFinite(v)).toBe(true);
      }
    }
  });
});
