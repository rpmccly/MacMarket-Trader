import { describe, expect, it } from "vitest";

import {
  buildMomentumImpactRows,
  estimateActiveRankDelta,
  estimateActiveScore,
  formatRankDelta,
  formatScoreUnit,
  formatUnitScore,
  MOMENTUM_IMPACT_DETERMINISTIC_NOTE,
  momentumImpactTone,
  sortMomentumImpactRows,
  summarizeMomentumImpact,
} from "@/lib/momentum-impact";
import type {
  MomentumRankingContribution,
  MomentumRankingMode,
  QueueCandidate,
} from "@/lib/recommendations";

function contribution(
  overrides: Partial<MomentumRankingContribution> = {},
): MomentumRankingContribution {
  return {
    mode: "shadow",
    enabled: true,
    applied: false,
    total_contribution: 0,
    shadow_contribution: 18,
    momentum_alignment_score: 10,
    trend_alignment_score: 8,
    hilo_confirmation_bonus: 5,
    reversal_warning_penalty: 0,
    no_trade_warning: false,
    pullback_signal: false,
    reversal_warning: false,
    parity_status: "pending_thinkorswim_fixture_validation",
    higher_timeframe_source: "derived_from_chart_bars",
    total_score: 100,
    total_label: "Max Bull",
    trend_score: 100,
    momo_score: 90,
    inferred_direction: "long",
    calculation_notes: [],
    reason_codes: ["thinkorswim_parity_pending", "derived_higher_timeframe"],
    ...overrides,
  };
}

function candidate(overrides: Partial<QueueCandidate> = {}): QueueCandidate {
  return {
    rank: 1,
    symbol: "AAPL",
    strategy: "Event Continuation",
    workflow_source: "test_provider",
    timeframe: "1D",
    status: "top_candidate",
    score: 0.7,
    expected_rr: 2.0,
    confidence: 0.7,
    reason_text: "",
    thesis: "",
    momentum_contribution: contribution(),
    ...overrides,
  };
}

describe("estimateActiveScore", () => {
  it("shadow mode adds shadow_contribution / 100 * scale then clamps to [0,1]", () => {
    // Phase B6.1 — default scale 0.35 dampens active estimates: 18/100*0.35 = 0.063.
    expect(estimateActiveScore(candidate({ score: 0.7 }))).toBeCloseTo(0.763, 5);
    expect(
      estimateActiveScore(
        candidate({
          score: 0.95,
          momentum_contribution: contribution({ shadow_contribution: 18, active_delta_scale: 1.0 }),
        }),
      ),
    ).toBe(1);
    expect(
      estimateActiveScore(
        candidate({
          score: 0.05,
          momentum_contribution: contribution({ shadow_contribution: -12, active_delta_scale: 1.0 }),
        }),
      ),
    ).toBe(0);
  });

  it("uses the candidate-level active_delta_scale when provided", () => {
    expect(
      estimateActiveScore(
        candidate({
          score: 0.5,
          momentum_contribution: contribution({ shadow_contribution: 20, active_delta_scale: 0.5 }),
        }),
      ),
    ).toBeCloseTo(0.6, 5); // 0.5 + 20/100 * 0.5
  });

  it("defaults to 0.35 when active_delta_scale is missing on the contribution", () => {
    const c = contribution({ shadow_contribution: 20 });
    delete (c as Partial<typeof c>).active_delta_scale;
    expect(estimateActiveScore(candidate({ score: 0.5, momentum_contribution: c }))).toBeCloseTo(0.57, 5);
  });

  it("active mode returns the candidate score unchanged (no double count)", () => {
    const activeContribution = contribution({
      mode: "active",
      applied: true,
      total_contribution: 9,
      shadow_contribution: 9,
    });
    expect(estimateActiveScore(candidate({ score: 0.8, momentum_contribution: activeContribution }))).toBeCloseTo(0.8, 5);
  });

  it("off / missing / direction-unknown shows no movement", () => {
    expect(estimateActiveScore(candidate({ momentum_contribution: contribution({ mode: "off", enabled: false }) })))
      .toBeCloseTo(0.7, 5);
    expect(estimateActiveScore(candidate({ momentum_contribution: null }))).toBeCloseTo(0.7, 5);
    const dirUnknown = contribution({ reason_codes: ["direction_unknown"] });
    expect(estimateActiveScore(candidate({ momentum_contribution: dirUnknown }))).toBeCloseTo(0.7, 5);
  });

  it("returns 0 for null candidate and never NaN", () => {
    expect(estimateActiveScore(null)).toBe(0);
    expect(estimateActiveScore(undefined)).toBe(0);
    // NaN score + missing contribution → clamped to 0, no movement.
    expect(estimateActiveScore(candidate({ score: Number.NaN, momentum_contribution: null }))).toBe(0);
    // NaN score is sanitized to 0; shadow contribution still applies → finite.
    const result = estimateActiveScore(candidate({ score: Number.NaN }));
    expect(Number.isFinite(result)).toBe(true);
    expect(Number.isNaN(result)).toBe(false);
  });
});

describe("buildMomentumImpactRows", () => {
  it("returns one row per candidate with carried reason codes", () => {
    const rows = buildMomentumImpactRows([candidate(), candidate({ symbol: "MSFT", rank: 2 })]);
    expect(rows).toHaveLength(2);
    expect(rows[0].symbol).toBe("AAPL");
    expect(rows[0].reasonCodes).toContain("thinkorswim_parity_pending");
    expect(rows[0].reasonCodes).toContain("derived_higher_timeframe");
    expect(rows[0].parityPending).toBe(true);
    expect(rows[0].derivedHigherTimeframe).toBe(true);
  });

  it("adds momentum_contribution_missing when contribution is null/disabled", () => {
    const rows = buildMomentumImpactRows([
      candidate({ momentum_contribution: null }),
      candidate({ momentum_contribution: contribution({ mode: "off", enabled: false }), symbol: "MSFT", rank: 2 }),
    ]);
    expect(rows[0].contributionMissing).toBe(true);
    expect(rows[0].reasonCodes).toContain("momentum_contribution_missing");
    expect(rows[1].contributionMissing).toBe(true);
    expect(rows[1].reasonCodes).toContain("momentum_contribution_missing");
  });

  it("never mutates input candidates", () => {
    const input = candidate();
    const beforeJson = JSON.stringify(input);
    buildMomentumImpactRows([input]);
    expect(JSON.stringify(input)).toBe(beforeJson);
  });

  it("clamps estimated active score to [0,1]", () => {
    const rows = buildMomentumImpactRows([
      candidate({ score: 0.95, momentum_contribution: contribution({ shadow_contribution: 50 }) }),
      candidate({ score: 0.05, momentum_contribution: contribution({ shadow_contribution: -50 }), symbol: "MSFT", rank: 2 }),
    ]);
    expect(rows[0].estimatedActiveScore).toBe(1);
    expect(rows[1].estimatedActiveScore).toBe(0);
  });

  it("computes estimated rank-after based on estimated active scores", () => {
    const rows = buildMomentumImpactRows([
      candidate({ score: 0.5, rank: 1, momentum_contribution: contribution({ shadow_contribution: -10 }) }),
      candidate({ score: 0.4, rank: 2, momentum_contribution: contribution({ shadow_contribution: 20 }), symbol: "MSFT" }),
    ]);
    // After: MSFT (0.6) > AAPL (0.4). AAPL drops from rank 1 → 2, MSFT moves 2 → 1.
    const aapl = rows[0];
    const msft = rows[1];
    expect(aapl.estimatedRankAfter).toBe(2);
    expect(aapl.estimatedRankDelta).toBe(-1);
    expect(msft.estimatedRankAfter).toBe(1);
    expect(msft.estimatedRankDelta).toBe(1);
  });

  it("returns empty array for null/empty inputs", () => {
    expect(buildMomentumImpactRows(null)).toEqual([]);
    expect(buildMomentumImpactRows(undefined)).toEqual([]);
    expect(buildMomentumImpactRows([])).toEqual([]);
  });
});

describe("summarizeMomentumImpact", () => {
  it("counts positive, negative, zero, warning, parity, direction-unknown, and missing", () => {
    const rows = buildMomentumImpactRows([
      candidate({ symbol: "AAPL", momentum_contribution: contribution({ shadow_contribution: 10 }) }),
      candidate({ symbol: "MSFT", rank: 2, momentum_contribution: contribution({ shadow_contribution: -5 }) }),
      candidate({ symbol: "NVDA", rank: 3, momentum_contribution: contribution({ shadow_contribution: 0 }) }),
      candidate({
        symbol: "TSLA",
        rank: 4,
        momentum_contribution: contribution({
          shadow_contribution: 4,
          reversal_warning: true,
          reason_codes: ["momentum_reversal_warning"],
        }),
      }),
      candidate({
        symbol: "META",
        rank: 5,
        momentum_contribution: contribution({
          shadow_contribution: 0,
          reason_codes: ["direction_unknown"],
        }),
      }),
      candidate({ symbol: "AMZN", rank: 6, momentum_contribution: null }),
    ]);
    const summary = summarizeMomentumImpact(rows);
    expect(summary.candidates_reviewed).toBe(6);
    // Positive: AAPL (10), TSLA (4). Negative: MSFT (-5). Zero: NVDA, META, AMZN.
    expect(summary.positive_contribution_count).toBe(2);
    expect(summary.negative_contribution_count).toBe(1);
    expect(summary.zero_contribution_count).toBe(3);
    expect(summary.warnings_count).toBe(1);
    expect(summary.direction_unknown_count).toBe(1);
    expect(summary.contribution_missing_count).toBe(1);
    // AAPL/MSFT/NVDA carry the default parity_pending reason; TSLA/META
    // overrode reason_codes; AMZN has no contribution.
    expect(summary.parity_pending_count).toBe(3);
  });

  it("observed_modes reflects per-candidate modes", () => {
    const rows = buildMomentumImpactRows([
      candidate({ symbol: "AAPL", momentum_contribution: contribution({ mode: "shadow" }) }),
      candidate({ symbol: "MSFT", rank: 2, momentum_contribution: contribution({ mode: "active", applied: true, total_contribution: 5 }) }),
      candidate({ symbol: "NVDA", rank: 3, momentum_contribution: contribution({ mode: "off", enabled: false }) }),
    ]);
    const summary = summarizeMomentumImpact(rows);
    const observed = new Set<MomentumRankingMode>(summary.observed_modes);
    expect(observed.has("shadow")).toBe(true);
    expect(observed.has("active")).toBe(true);
    expect(observed.has("off")).toBe(true);
  });

  it("net delta is finite (never NaN/inf)", () => {
    const rows = buildMomentumImpactRows([candidate()]);
    const summary = summarizeMomentumImpact(rows);
    expect(Number.isFinite(summary.net_estimated_score_delta)).toBe(true);
    expect(Number.isNaN(summary.net_estimated_score_delta)).toBe(false);
  });
});

describe("Phase B4.2 direction-inference impact on summaries", () => {
  it("bullish-strategy-inferred candidates do not count toward direction_unknown", () => {
    const rows = buildMomentumImpactRows([
      candidate({
        symbol: "AAPL",
        momentum_contribution: contribution({
          shadow_contribution: 15,
          inferred_direction: "long",
          reason_codes: ["thinkorswim_parity_pending", "bullish_strategy_direction_inferred"],
        }),
      }),
      candidate({
        symbol: "MSFT",
        rank: 2,
        momentum_contribution: contribution({
          shadow_contribution: 12,
          inferred_direction: "long",
          reason_codes: ["direction_from_strategy_metadata"],
        }),
      }),
    ]);
    const summary = summarizeMomentumImpact(rows);
    expect(summary.direction_unknown_count).toBe(0);
  });

  it("direction_unknown_count still counts rows that explicitly carry the code", () => {
    const rows = buildMomentumImpactRows([
      candidate({
        momentum_contribution: contribution({
          reason_codes: ["direction_unknown"],
        }),
      }),
    ]);
    const summary = summarizeMomentumImpact(rows);
    expect(summary.direction_unknown_count).toBe(1);
  });
});

describe("estimateActiveRankDelta", () => {
  it("counts upgraded/downgraded/unchanged rows", () => {
    const rows = buildMomentumImpactRows([
      candidate({ score: 0.5, rank: 1, momentum_contribution: contribution({ shadow_contribution: -10 }) }),
      candidate({ score: 0.4, rank: 2, momentum_contribution: contribution({ shadow_contribution: 20 }), symbol: "MSFT" }),
    ]);
    const delta = estimateActiveRankDelta(rows);
    expect(delta.upgraded).toBe(1);
    expect(delta.downgraded).toBe(1);
    expect(delta.unchanged).toBe(0);
  });
});

describe("momentumImpactTone", () => {
  it("warns on reversal/no-trade flags", () => {
    const [row] = buildMomentumImpactRows([
      candidate({ momentum_contribution: contribution({ reversal_warning: true }) }),
    ]);
    expect(momentumImpactTone(row)).toBe("warn");
  });

  it("good when shadow >= 5", () => {
    const [row] = buildMomentumImpactRows([
      candidate({ momentum_contribution: contribution({ shadow_contribution: 10 }) }),
    ]);
    expect(momentumImpactTone(row)).toBe("good");
  });

  it("bad when shadow <= -5", () => {
    const [row] = buildMomentumImpactRows([
      candidate({ momentum_contribution: contribution({ shadow_contribution: -10 }) }),
    ]);
    expect(momentumImpactTone(row)).toBe("bad");
  });

  it("neutral when off / no contribution", () => {
    const [row] = buildMomentumImpactRows([
      candidate({ momentum_contribution: contribution({ mode: "off", enabled: false }) }),
    ]);
    expect(momentumImpactTone(row)).toBe("neutral");
  });
});

describe("sortMomentumImpactRows", () => {
  const rows = buildMomentumImpactRows([
    candidate({ symbol: "AAPL", rank: 3, score: 0.4, momentum_contribution: contribution({ shadow_contribution: 0 }) }),
    candidate({ symbol: "MSFT", rank: 1, score: 0.7, momentum_contribution: contribution({ shadow_contribution: 18, reversal_warning: false }) }),
    candidate({ symbol: "TSLA", rank: 2, score: 0.5, momentum_contribution: contribution({ shadow_contribution: 5, reversal_warning: true, reason_codes: ["momentum_reversal_warning"] }) }),
  ]);

  it("never mutates input array", () => {
    const before = rows.map((r) => r.symbol);
    sortMomentumImpactRows(rows, "estimated_score_desc");
    expect(rows.map((r) => r.symbol)).toEqual(before);
  });

  it("rank_asc sorts by current rank", () => {
    expect(sortMomentumImpactRows(rows, "rank_asc").map((r) => r.symbol)).toEqual(["MSFT", "TSLA", "AAPL"]);
  });

  it("estimated_score_desc sorts by estimated active score desc", () => {
    const sorted = sortMomentumImpactRows(rows, "estimated_score_desc");
    expect(sorted[0].symbol).toBe("MSFT");
  });

  it("warning_first places warning rows ahead", () => {
    const sorted = sortMomentumImpactRows(rows, "warning_first");
    expect(sorted[0].symbol).toBe("TSLA");
  });
});

describe("formatting helpers and deterministic note", () => {
  it("formatRankDelta renders directional arrows", () => {
    expect(formatRankDelta(0)).toBe("0");
    expect(formatRankDelta(2)).toContain("▲");
    expect(formatRankDelta(-3)).toContain("▼");
  });

  it("formatScoreUnit / formatUnitScore handle nulls cleanly", () => {
    expect(formatScoreUnit(null)).toBe("—");
    expect(formatUnitScore(null)).toBe("—");
    expect(formatScoreUnit(5)).toBe("+5.00");
    expect(formatUnitScore(0.5)).toBe("0.500");
  });

  it("deterministic note frames context only and uses no action language", () => {
    expect(MOMENTUM_IMPACT_DETERMINISTIC_NOTE).toContain("estimates impact only");
    for (const forbidden of ["buy now", "sell now", "enter now", "short now", "approve trade", "auto approve", "route order"]) {
      expect(MOMENTUM_IMPACT_DETERMINISTIC_NOTE.toLowerCase().includes(forbidden)).toBe(false);
    }
  });
});

describe("Phase B6.2 applied-delta fallback chain", () => {
  function activeContribution(
    overrides: Partial<MomentumRankingContribution> = {},
  ): MomentumRankingContribution {
    return contribution({
      mode: "active",
      applied: true,
      total_contribution: 20,
      shadow_contribution: 20,
      raw_total_contribution: 20,
      applied_score_delta: 0.07,
      active_delta_scale: 0.35,
      ...overrides,
    });
  }

  it("active row prefers candidate.momentum_score_delta over contribution fields", () => {
    const c = candidate({
      score: 0.882,
      momentum_score_delta: 0.065,
      score_before_momentum: 0.817,
      momentum_contribution: activeContribution({ applied_score_delta: 0.07 }),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(row.appliedScoreDelta).toBeCloseTo(0.065, 5);
    expect(row.baselineScore).toBeCloseTo(0.817, 5);
  });

  it("active row falls back to contribution.applied_score_delta when candidate delta is missing", () => {
    const c = candidate({
      score: 0.882,
      momentum_contribution: activeContribution({ applied_score_delta: 0.07 }),
    });
    delete (c as Partial<typeof c>).momentum_score_delta;
    const [row] = buildMomentumImpactRows([c]);
    expect(row.appliedScoreDelta).toBeCloseTo(0.07, 5);
  });

  it("active row falls back to raw/100*scale when both candidate and contribution deltas are absent", () => {
    const c = candidate({
      score: 0.882,
      momentum_contribution: activeContribution({
        applied_score_delta: undefined,
        raw_total_contribution: 20,
        active_delta_scale: 0.35,
      }),
    });
    delete (c as Partial<typeof c>).momentum_score_delta;
    const [row] = buildMomentumImpactRows([c]);
    expect(row.appliedScoreDelta).toBeCloseTo(0.07, 5);
    expect(row.appliedScoreDelta).not.toBe(0);
  });

  it("active row never shows 0 when contribution is applied (regression: deployed bug)", () => {
    const c = candidate({
      score: 0.882,
      momentum_contribution: activeContribution({
        applied_score_delta: undefined,
      }),
    });
    delete (c as Partial<typeof c>).momentum_score_delta;
    const [row] = buildMomentumImpactRows([c]);
    expect(row.appliedScoreDelta).not.toBe(0);
  });

  it("baselineScore prefers candidate.score_before_momentum when present", () => {
    const c = candidate({
      score: 0.882,
      score_before_momentum: 0.812,
      momentum_score_delta: 0.07,
      momentum_contribution: activeContribution(),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(row.baselineScore).toBeCloseTo(0.812, 5);
  });

  it("baselineScore falls back to current_score - appliedScoreDelta when candidate field is missing", () => {
    const c = candidate({
      score: 0.882,
      momentum_score_delta: 0.07,
      momentum_contribution: activeContribution(),
    });
    delete (c as Partial<typeof c>).score_before_momentum;
    const [row] = buildMomentumImpactRows([c]);
    expect(row.baselineScore).toBeCloseTo(0.812, 5);
  });

  it("baselineScore equals currentScore in shadow mode", () => {
    const c = candidate({
      score: 0.812,
      momentum_contribution: contribution({ mode: "shadow", shadow_contribution: 20 }),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(row.baselineScore).toBeCloseTo(row.currentScore, 5);
  });

  it("active row applied delta and baseline stay finite under malformed payload", () => {
    const c = candidate({
      score: 0.882,
      momentum_score_delta: Number.NaN,
      momentum_contribution: activeContribution({ applied_score_delta: Number.POSITIVE_INFINITY }),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(Number.isFinite(row.appliedScoreDelta)).toBe(true);
    expect(Number.isFinite(row.baselineScore)).toBe(true);
  });
});

describe("Phase B6.3 realized-delta + consistency-corrected wiring", () => {
  function activeContribution(
    overrides: Partial<MomentumRankingContribution> = {},
  ): MomentumRankingContribution {
    return contribution({
      mode: "active",
      applied: true,
      total_contribution: 20,
      shadow_contribution: 20,
      raw_total_contribution: 20,
      applied_score_delta: 0.07,
      active_delta_scale: 0.35,
      ...overrides,
    });
  }

  it("realizedScoreDelta prefers candidate.momentum_realized_score_delta when finite", () => {
    const c = candidate({
      score: 0.882,
      score_before_momentum: 0.812,
      score_after_momentum: 0.882,
      momentum_score_delta: 0.07,
      momentum_realized_score_delta: 0.07,
      momentum_contribution: activeContribution(),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(row.realizedScoreDelta).toBeCloseTo(0.07, 5);
    expect(row.appliedScoreDelta).toBeCloseTo(0.07, 5);
    expect(row.baselineScore).toBeCloseTo(0.812, 5);
    expect(row.currentScore).toBeCloseTo(0.882, 5);
  });

  it("realizedScoreDelta tracks the clamp-truncated value when intended > headroom", () => {
    // Baseline 0.97 + intended +0.07 → clamp to 1.000, realized +0.03.
    const c = candidate({
      score: 1.0,
      score_before_momentum: 0.97,
      score_after_momentum: 1.0,
      momentum_score_delta: 0.07,
      momentum_realized_score_delta: 0.03,
      momentum_contribution: activeContribution(),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(row.appliedScoreDelta).toBeCloseTo(0.07, 5); // intended
    expect(row.realizedScoreDelta).toBeCloseTo(0.03, 5); // realized after clamp
    expect(row.currentScore).toBeCloseTo(1.0, 5);
    expect(row.baselineScore).toBeCloseTo(0.97, 5);
  });

  it("realizedScoreDelta falls back to current - baseline when candidate field is absent", () => {
    const c = candidate({
      score: 0.882,
      score_before_momentum: 0.812,
      score_after_momentum: 0.882,
      momentum_contribution: activeContribution(),
    });
    delete (c as Partial<typeof c>).momentum_realized_score_delta;
    const [row] = buildMomentumImpactRows([c]);
    expect(row.realizedScoreDelta).toBeCloseTo(0.07, 5);
  });

  it("realizedScoreDelta is 0 in shadow mode regardless of score arithmetic", () => {
    const c = candidate({
      score: 0.7,
      momentum_contribution: contribution({ mode: "shadow", applied: false, shadow_contribution: 18 }),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(row.realizedScoreDelta).toBe(0);
  });

  it("consistencyCorrected reflects the momentum_score_consistency_corrected reason code", () => {
    const c = candidate({
      score: 1.0,
      score_before_momentum: 0.812,
      score_after_momentum: 1.0,
      momentum_score_delta: 0.07,
      momentum_realized_score_delta: 0.188,
      momentum_contribution: activeContribution({
        reason_codes: [
          "thinkorswim_parity_pending",
          "momentum_score_consistency_corrected",
        ],
      }),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(row.consistencyCorrected).toBe(true);
    // The applied (intended) delta should remain the scaled value, never
    // the legacy implied current-baseline diff (0.188).
    expect(row.appliedScoreDelta).toBeCloseTo(0.07, 5);
  });

  it("consistencyCorrected is false when the reason code is absent", () => {
    const c = candidate({
      score: 0.882,
      score_before_momentum: 0.812,
      momentum_contribution: activeContribution(),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(row.consistencyCorrected).toBe(false);
  });

  it("currentScore prefers score_after_momentum when present", () => {
    // Even if candidate.score drifted (stale wire payload), use the
    // explicit score_after_momentum so the row matches the backend
    // consistency guard's output.
    const c = candidate({
      score: 1.0, // legacy / stale
      score_before_momentum: 0.812,
      score_after_momentum: 0.882, // single source of truth
      momentum_score_delta: 0.07,
      momentum_realized_score_delta: 0.07,
      momentum_contribution: activeContribution(),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(row.currentScore).toBeCloseTo(0.882, 5);
  });

  it("legacy-bug shape — current=1.000 but applied_score_delta=0.07 — still renders intended 0.070", () => {
    // Pin the exact deployed-bug signature: even if a stale wire row
    // arrives with current=1.000 (the legacy unscaled delta), the
    // operator UI must render the intended scaled +0.07 because
    // contribution.applied_score_delta is the single source of truth.
    const c = candidate({
      symbol: "SPY",
      score: 1.0,
      score_before_momentum: 0.812,
      momentum_score_delta: 0.07,
      momentum_contribution: activeContribution({ applied_score_delta: 0.07 }),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(row.appliedScoreDelta).toBeCloseTo(0.07, 5);
  });

  it("never returns NaN/Infinity in realized or applied delta under bad payloads", () => {
    const c = candidate({
      score: Number.NaN,
      score_before_momentum: Number.NaN,
      score_after_momentum: Number.NaN,
      momentum_score_delta: Number.NaN,
      momentum_realized_score_delta: Number.POSITIVE_INFINITY,
      momentum_contribution: activeContribution({
        applied_score_delta: Number.NaN,
        raw_total_contribution: Number.NaN,
        active_delta_scale: Number.NaN,
      }),
    });
    const [row] = buildMomentumImpactRows([c]);
    expect(Number.isFinite(row.appliedScoreDelta)).toBe(true);
    expect(Number.isFinite(row.realizedScoreDelta)).toBe(true);
    expect(Number.isFinite(row.currentScore)).toBe(true);
    expect(Number.isFinite(row.baselineScore)).toBe(true);
  });
});
