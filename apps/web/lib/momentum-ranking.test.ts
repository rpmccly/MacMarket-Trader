import { describe, expect, it } from "vitest";

import {
  buildMomentumRankingBreakdown,
  formatMomentumContribution,
  getMomentumContributionReasonLabels,
  hasMomentumRankingWarnings,
  isMomentumContributionApplied,
  isMomentumContributionShadow,
  MOMENTUM_RANKING_DETERMINISTIC_NOTE,
  momentumContributionTone,
  momentumRankingAppliedLabel,
  momentumRankingModeLabel,
  momentumScoreContextRow,
  normalizeMomentumRankingMode,
  summarizeMomentumContribution,
} from "@/lib/momentum-ranking";
import type { MomentumRankingContribution } from "@/lib/recommendations";

function shadowContribution(overrides: Partial<MomentumRankingContribution> = {}): MomentumRankingContribution {
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

describe("normalizeMomentumRankingMode", () => {
  it("returns canonical strings for known modes", () => {
    expect(normalizeMomentumRankingMode("off")).toBe("off");
    expect(normalizeMomentumRankingMode("shadow")).toBe("shadow");
    expect(normalizeMomentumRankingMode("active")).toBe("active");
    expect(normalizeMomentumRankingMode("SHADOW")).toBe("shadow");
  });

  it("falls back to 'off' on unknown values", () => {
    expect(normalizeMomentumRankingMode(undefined)).toBe("off");
    expect(normalizeMomentumRankingMode(null)).toBe("off");
    expect(normalizeMomentumRankingMode("garbage")).toBe("off");
  });
});

describe("momentumRankingModeLabel", () => {
  it("uses operator-friendly framing without action verbs", () => {
    expect(momentumRankingModeLabel("off")).toBe("Off — not computed");
    expect(momentumRankingModeLabel("shadow")).toBe("Shadow — computed, not applied");
    expect(momentumRankingModeLabel("active")).toBe("Active — applied to ranking");

    for (const mode of ["off", "shadow", "active"] as const) {
      const label = momentumRankingModeLabel(mode).toLowerCase();
      for (const verb of ["buy now", "sell now", "enter now", "short now", "approve", "reject"]) {
        expect(label.includes(verb)).toBe(false);
      }
    }
  });
});

describe("isMomentumContributionApplied / isMomentumContributionShadow", () => {
  it("reports shadow correctly", () => {
    expect(isMomentumContributionShadow(shadowContribution())).toBe(true);
    expect(isMomentumContributionApplied(shadowContribution())).toBe(false);
  });

  it("reports active+applied correctly", () => {
    const active = shadowContribution({ mode: "active", applied: true, total_contribution: 12 });
    expect(isMomentumContributionShadow(active)).toBe(false);
    expect(isMomentumContributionApplied(active)).toBe(true);
  });

  it("handles missing or off contributions", () => {
    expect(isMomentumContributionApplied(null)).toBe(false);
    expect(isMomentumContributionShadow(undefined)).toBe(false);
    expect(isMomentumContributionShadow({ mode: "off", enabled: false })).toBe(false);
  });
});

describe("momentumRankingAppliedLabel", () => {
  it("distinguishes off, shadow, active behavior", () => {
    expect(momentumRankingAppliedLabel(null)).toBe("Not available");
    expect(momentumRankingAppliedLabel({ mode: "off", enabled: false })).toBe("Not computed");
    expect(momentumRankingAppliedLabel(shadowContribution())).toBe("Computed — final score unchanged");
    expect(
      momentumRankingAppliedLabel(shadowContribution({ mode: "active", applied: true, total_contribution: 5 })),
    ).toBe("Bounded contribution applied to ranking");
    expect(
      momentumRankingAppliedLabel(shadowContribution({ mode: "active", applied: false, total_contribution: 0 })),
    ).toBe("Computed — bounded contribution not applied");
  });
});

describe("formatMomentumContribution", () => {
  it("formats positive/negative/zero/missing values", () => {
    expect(formatMomentumContribution(0)).toBe("0.00");
    expect(formatMomentumContribution(5)).toBe("+5.00");
    expect(formatMomentumContribution(-12)).toBe("-12.00");
    expect(formatMomentumContribution(null)).toBe("—");
    expect(formatMomentumContribution(undefined)).toBe("—");
    expect(formatMomentumContribution(Number.NaN)).toBe("—");
  });
});

describe("momentumContributionTone", () => {
  it("warns on reversal/no-trade and tones by effective value otherwise", () => {
    expect(momentumContributionTone(null)).toBe("neutral");
    expect(momentumContributionTone({ mode: "off", enabled: false })).toBe("neutral");
    expect(momentumContributionTone(shadowContribution({ shadow_contribution: 18 }))).toBe("good");
    expect(momentumContributionTone(shadowContribution({ shadow_contribution: -10 }))).toBe("bad");
    expect(momentumContributionTone(shadowContribution({ shadow_contribution: 2 }))).toBe("warn");
    expect(momentumContributionTone(shadowContribution({ reversal_warning: true }))).toBe("warn");
  });
});

describe("summarizeMomentumContribution", () => {
  it("describes shadow contributions with mode framing", () => {
    expect(summarizeMomentumContribution(shadowContribution())).toContain("Shadow");
    expect(summarizeMomentumContribution(shadowContribution())).toContain("shadow");
    expect(summarizeMomentumContribution(shadowContribution())).toContain("+18");
  });

  it("describes active contributions as applied", () => {
    const summary = summarizeMomentumContribution(
      shadowContribution({ mode: "active", applied: true, total_contribution: 9, shadow_contribution: 9 }),
    );
    expect(summary).toContain("Active");
    expect(summary).toContain("applied");
  });

  it("falls back to unavailable message for missing/off contributions", () => {
    expect(summarizeMomentumContribution(null)).toBe("Momentum ranking context unavailable.");
    expect(summarizeMomentumContribution({ mode: "off", enabled: false })).toBe("Momentum ranking context unavailable.");
  });
});

describe("getMomentumContributionReasonLabels", () => {
  it("translates known reason codes and dedupes", () => {
    const labels = getMomentumContributionReasonLabels([
      "thinkorswim_parity_pending",
      "derived_higher_timeframe",
      "direction_unknown",
      "thinkorswim_parity_pending",
      "momentum_no_trade_warning",
      "momentum_reversal_warning",
      "momentum_pullback_signal",
    ]);
    expect(labels).toEqual([
      "Thinkorswim parity pending",
      "Derived higher timeframe",
      "Direction unknown",
      "No-trade warning",
      "Reversal warning",
      "Pullback signal",
    ]);
  });

  it("handles missing/empty arrays", () => {
    expect(getMomentumContributionReasonLabels(null)).toEqual([]);
    expect(getMomentumContributionReasonLabels(undefined)).toEqual([]);
    expect(getMomentumContributionReasonLabels([])).toEqual([]);
  });

  it("falls back to humanized labels for unknown reason codes", () => {
    expect(getMomentumContributionReasonLabels(["some_new_reason"])).toEqual(["some new reason"]);
  });

  it("translates Phase B4.2 direction-inference reason codes", () => {
    expect(
      getMomentumContributionReasonLabels([
        "direction_from_candidate_metadata",
        "direction_from_strategy_metadata",
        "bullish_strategy_direction_inferred",
        "direction_inferred_from_strategy",
      ]),
    ).toEqual([
      "Direction from candidate metadata",
      "Direction from strategy metadata",
      "Bullish strategy direction inferred",
      "Direction inferred from strategy",
    ]);
  });
});

describe("hasMomentumRankingWarnings", () => {
  it("returns true on reversal or no-trade flags only", () => {
    expect(hasMomentumRankingWarnings(null)).toBe(false);
    expect(hasMomentumRankingWarnings(shadowContribution())).toBe(false);
    expect(hasMomentumRankingWarnings(shadowContribution({ reversal_warning: true }))).toBe(true);
    expect(hasMomentumRankingWarnings(shadowContribution({ no_trade_warning: true }))).toBe(true);
  });
});

describe("buildMomentumRankingBreakdown", () => {
  it("returns four labelled component rows with tones", () => {
    const rows = buildMomentumRankingBreakdown(shadowContribution());
    expect(rows.map((r) => r.label)).toEqual([
      "Momentum alignment",
      "Trend alignment",
      "HiLo confirmation",
      "Reversal warning penalty",
    ]);
    expect(rows[0].tone).toBe("good");
    expect(rows[3].tone).toBe("neutral"); // no reversal in baseline
  });

  it("returns empty when contribution is missing/off", () => {
    expect(buildMomentumRankingBreakdown(null)).toEqual([]);
    expect(buildMomentumRankingBreakdown({ mode: "off", enabled: false })).toEqual([]);
  });

  it("colors the reversal-penalty row bad when negative", () => {
    const rows = buildMomentumRankingBreakdown(
      shadowContribution({ reversal_warning_penalty: -12, reversal_warning: true }),
    );
    expect(rows[3].tone).toBe("bad");
  });
});

describe("momentumScoreContextRow", () => {
  it("formats total / label / trend / momo", () => {
    expect(momentumScoreContextRow(shadowContribution())).toEqual({
      totalScore: "+100.00",
      totalLabel: "Max Bull",
      trend: "+100.00",
      momo: "+90.00",
    });
  });

  it("returns dashes for missing contribution", () => {
    expect(momentumScoreContextRow(null)).toEqual({ totalScore: "—", totalLabel: "—", trend: "—", momo: "—" });
  });
});

describe("MOMENTUM_RANKING_DETERMINISTIC_NOTE", () => {
  it("frames context only and never uses action language", () => {
    expect(MOMENTUM_RANKING_DETERMINISTIC_NOTE).toContain("deterministic context");
    expect(MOMENTUM_RANKING_DETERMINISTIC_NOTE).toContain("does not approve, reject, size, or route");
    for (const verb of ["buy now", "sell now", "enter now", "short now", "approve trade", "auto approve", "route order"]) {
      expect(MOMENTUM_RANKING_DETERMINISTIC_NOTE.toLowerCase().includes(verb)).toBe(false);
    }
  });
});
