import { describe, expect, it } from "vitest";

import type { MomentumRankingStatus } from "@/lib/momentum-ranking-status";
import {
  buildTrueMomentumPhaseCCloseoutStatus,
  collectCompositeMismatchSymbols,
  summarizeTrueMomentumPhaseCCloseout,
  trueMomentumPhaseCCloseoutBlockerLabels,
  TRUE_MOMENTUM_PHASE_C_CLOSEOUT_DETERMINISTIC_NOTE,
  TRUE_MOMENTUM_PHASE_C_SHIPPED_PHASES,
} from "@/lib/true-momentum-phase-c-closeout";

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

describe("collectCompositeMismatchSymbols", () => {
  it("returns symbols whose classification carries composite_mismatch", () => {
    expect(collectCompositeMismatchSymbols(rankingStatus())).toEqual(["XLP"]);
  });

  it("returns an empty array when no summaries present", () => {
    expect(collectCompositeMismatchSymbols(null)).toEqual([]);
    expect(
      collectCompositeMismatchSymbols(
        rankingStatus({ thinkorswim_parity_symbol_summaries: [] }),
      ),
    ).toEqual([]);
  });
});

describe("buildTrueMomentumPhaseCCloseoutStatus", () => {
  it("reports research_implementation_status complete and active_generation_status reserved", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    expect(status.research_implementation_status).toBe("complete");
    expect(status.active_generation_status).toBe("reserved");
  });

  it("forbids queue / approval / order capabilities", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    expect(status.can_generate_queue_candidates).toBe(false);
    expect(status.can_approve_trades).toBe(false);
    expect(status.can_route_orders).toBe(false);
    expect(status.can_change_paper_order_behavior).toBe(false);
  });

  it("ships C0–C4.1 in the canonical order", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    expect(status.shipped_phases).toEqual(TRUE_MOMENTUM_PHASE_C_SHIPPED_PHASES);
    expect(status.shipped_phases).toEqual([
      "C0",
      "C1",
      "C2",
      "C2.1",
      "C2.2",
      "C3",
      "C4",
      "C4.1",
      "C4.2",
    ]);
  });

  it("surfaces XLP composite mismatch as a parity_mixed blocker with the symbol attached", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const parity = status.blockers.find((b) => b.id === "parity_mixed");
    expect(parity).toBeDefined();
    expect(parity?.symbols).toContain("XLP");
  });

  it("emits insufficient_b8_evidence when B8 outcome status is anything other than 'available'", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
      b8OutcomeStatus: "captured_without_outcomes",
    });
    expect(status.blockers.find((b) => b.id === "insufficient_b8_evidence")).toBeDefined();
  });

  it("does not emit insufficient_b8_evidence when B8 outcomes are available", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
      b8OutcomeStatus: "available",
    });
    expect(
      status.blockers.find((b) => b.id === "insufficient_b8_evidence"),
    ).toBeUndefined();
  });

  it("emits insufficient_c3_cohort when cohort readiness is not promising", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
      cohortReadinessStatus: "insufficient_evidence",
    });
    expect(status.blockers.find((b) => b.id === "insufficient_c3_cohort")).toBeDefined();
  });

  it("does not emit insufficient_c3_cohort when cohort readiness is promising_research", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
      cohortReadinessStatus: "promising_research",
    });
    expect(
      status.blockers.find((b) => b.id === "insufficient_c3_cohort"),
    ).toBeUndefined();
  });

  it("always emits operator_authorization_required and active_generation_not_implemented blockers", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus({ thinkorswim_parity_symbol_summaries: [] }),
      b8OutcomeStatus: "available",
      cohortReadinessStatus: "promising_research",
    });
    expect(
      status.blockers.find((b) => b.id === "operator_authorization_required"),
    ).toBeDefined();
    expect(
      status.blockers.find((b) => b.id === "active_generation_not_implemented"),
    ).toBeDefined();
  });

  it("recommends continuing research evidence collection", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    expect(status.recommended_action.toLowerCase()).toContain(
      "continue research evidence collection",
    );
  });

  it("names C5 research candidate proposal as the next allowed phase", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    expect(status.next_allowed_phase.id).toBe("C5");
    expect(status.next_allowed_phase.label).toContain("C5 research candidate proposal");
    expect(status.next_allowed_phase.description.toLowerCase()).toContain(
      "non-active",
    );
    expect(status.next_allowed_phase.description.toLowerCase()).toContain(
      "non-ordering",
    );
  });

  it("never returns 'ready for live' / 'approved' / 'activate' wording on the status object", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const json = JSON.stringify(status).toLowerCase();
    expect(json.includes("ready for live")).toBe(false);
    expect(json.includes("activate now")).toBe(false);
    // The blocker label "operator authorization required" is allowed
    // — the forbidden patterns are affirmative live/active wording.
    for (const phrase of [
      "approve trade",
      "auto approve",
      "route order",
      "place order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
    ]) {
      expect(json.includes(phrase)).toBe(false);
    }
  });

  it("the deterministic note never includes trade-action language", () => {
    const lower = TRUE_MOMENTUM_PHASE_C_CLOSEOUT_DETERMINISTIC_NOTE.toLowerCase();
    for (const phrase of [
      "approve trade",
      "auto approve",
      "route order",
      "place order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
    ]) {
      expect(lower.includes(phrase)).toBe(false);
    }
  });
});

describe("summarizeTrueMomentumPhaseCCloseout", () => {
  it("collects open blocker count + composite mismatch symbol list", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const summary = summarizeTrueMomentumPhaseCCloseout(status);
    expect(summary.shipped).toEqual(TRUE_MOMENTUM_PHASE_C_SHIPPED_PHASES);
    expect(summary.blockers_open).toBeGreaterThan(0);
    expect(summary.composite_mismatch_symbols).toContain("XLP");
  });
});

describe("trueMomentumPhaseCCloseoutBlockerLabels", () => {
  it("returns the operator-facing labels for each blocker", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const labels = trueMomentumPhaseCCloseoutBlockerLabels(status);
    expect(labels).toContain("Visual parity mixed");
    expect(labels).toContain("Operator authorization required");
    expect(labels).toContain("Active Phase C generation is not implemented");
  });
});

describe("Phase C closeout extended capability flags", () => {
  it("can_size_trades and can_create_paper_orders are always false", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    expect(status.can_size_trades).toBe(false);
    expect(status.can_create_paper_orders).toBe(false);
  });
});

describe("xlp_composite_mismatch blocker", () => {
  it("surfaces xlp_composite_mismatch as a separate blocker when XLP is in composite mismatch", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const xlpBlocker = status.blockers.find((b) => b.id === "xlp_composite_mismatch");
    expect(xlpBlocker).toBeDefined();
    expect(xlpBlocker?.symbols).toEqual(["XLP"]);
    expect(xlpBlocker?.label.toLowerCase()).toContain("xlp");
  });

  it("does not emit xlp_composite_mismatch when XLP is not present", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus({
        thinkorswim_parity_symbol_summaries: [
          {
            symbol: "SPY",
            status: "visual_attested",
            diagnostic_classification: ["oscillator_aligned"],
            diagnostic_flags: { oscillator_aligned: true },
            reason_codes: [],
          },
        ],
      }),
    });
    expect(
      status.blockers.find((b) => b.id === "xlp_composite_mismatch"),
    ).toBeUndefined();
  });
});

describe("current_parity_summary", () => {
  it("buckets symbols by status and classification", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus({
        thinkorswim_parity_symbol_summaries: [
          {
            symbol: "SPY",
            status: "visual_attested",
            diagnostic_classification: ["oscillator_aligned"],
            diagnostic_flags: { oscillator_aligned: true },
            reason_codes: [],
          },
          {
            symbol: "XLK",
            status: "visual_attested",
            diagnostic_classification: ["oscillator_aligned"],
            diagnostic_flags: { oscillator_aligned: true },
            reason_codes: [],
          },
          {
            symbol: "XLE",
            status: "visual_attested",
            diagnostic_classification: ["oscillator_aligned"],
            diagnostic_flags: { oscillator_aligned: true },
            reason_codes: [],
          },
          {
            symbol: "XLP",
            status: "visual_failed",
            diagnostic_classification: [
              "oscillator_aligned",
              "composite_mismatch",
            ],
            diagnostic_flags: {
              oscillator_aligned: true,
              composite_score_failed: true,
            },
            reason_codes: [],
          },
        ],
      }),
    });
    const summary = status.current_parity_summary;
    expect(summary.visual_attestation_passed_symbols).toEqual(
      expect.arrayContaining(["SPY", "XLK", "XLE"]),
    );
    expect(summary.visual_attestation_failed_symbols).toEqual(["XLP"]);
    expect(summary.composite_mismatch_symbols).toEqual(["XLP"]);
    expect(summary.oscillator_aligned_symbols).toEqual(
      expect.arrayContaining(["SPY", "XLK", "XLE", "XLP"]),
    );
  });

  it("is empty when no parity report has landed", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus({ thinkorswim_parity_symbol_summaries: [] }),
    });
    expect(status.current_parity_summary.visual_attestation_passed_symbols).toEqual([]);
    expect(status.current_parity_summary.visual_attestation_failed_symbols).toEqual([]);
    expect(status.current_parity_summary.composite_mismatch_symbols).toEqual([]);
  });
});
