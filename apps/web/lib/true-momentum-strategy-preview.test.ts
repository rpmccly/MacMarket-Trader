import { describe, expect, it } from "vitest";

import {
  buildTrueMomentumStrategyPreview,
  familyPreviewLabel,
  summarizeTrueMomentumStrategyPreview,
  TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE,
  TRUE_MOMENTUM_STRATEGY_PREVIEW_IMPLEMENTATION_STATUS,
  TRUE_MOMENTUM_STRATEGY_PREVIEW_PHASE,
  trueMomentumPreviewReasonLabels,
  trueMomentumPreviewTone,
} from "@/lib/true-momentum-strategy-preview";
import type { TrueMomentumStrategyFamilyStatus } from "@/lib/true-momentum-strategy-families";
import type {
  MomentumRankingContribution,
  QueueCandidate,
} from "@/lib/recommendations";

function contribution(
  overrides: Partial<MomentumRankingContribution> = {},
): MomentumRankingContribution {
  return {
    mode: "active",
    enabled: true,
    applied: true,
    total_contribution: 20,
    shadow_contribution: 20,
    momentum_alignment_score: 10,
    trend_alignment_score: 6,
    hilo_confirmation_bonus: 4,
    reversal_warning_penalty: 0,
    no_trade_warning: false,
    pullback_signal: false,
    reversal_warning: false,
    parity_status: "pending_thinkorswim_fixture_validation",
    higher_timeframe_source: "derived_from_chart_bars",
    total_score: 85,
    total_label: "Bull",
    trend_score: 78,
    momo_score: 72,
    inferred_direction: "long",
    calculation_notes: [],
    reason_codes: [],
    active_delta_scale: 0.35,
    raw_total_contribution: 20,
    applied_score_delta: 0.07,
    ...overrides,
  };
}

function candidate(overrides: Partial<QueueCandidate> = {}): QueueCandidate {
  const score = overrides.score ?? 0.95;
  const scoreBefore = overrides.score_before_momentum ?? 0.88;
  return {
    rank: 1,
    symbol: "XLK",
    strategy: "Event Continuation",
    workflow_source: "test_provider",
    timeframe: "1D",
    status: "top_candidate",
    score,
    expected_rr: 2.0,
    confidence: 0.7,
    reason_text: "",
    thesis: "",
    momentum_contribution: contribution(),
    score_before_momentum: scoreBefore,
    score_after_momentum: score,
    momentum_score_delta: score - scoreBefore,
    momentum_realized_score_delta: score - scoreBefore,
    score_consistency_status: "ok",
    ...overrides,
  };
}

function status(
  overrides: Partial<TrueMomentumStrategyFamilyStatus> = {},
): TrueMomentumStrategyFamilyStatus {
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
    implementation_status: "scaffold_only",
    parity_status: "pending_thinkorswim_fixture_validation",
    parity_required_for_active: true,
    ...overrides,
  };
}

describe("familyPreviewLabel + trueMomentumPreviewTone + reason labels", () => {
  it("labels the three planned families", () => {
    expect(familyPreviewLabel("true_momentum_continuation")).toBe(
      "True Momentum Continuation",
    );
    expect(familyPreviewLabel("true_momentum_pullback")).toBe(
      "True Momentum Pullback",
    );
    expect(familyPreviewLabel("true_momentum_reversal_watch")).toBe(
      "True Momentum Reversal / Weakening Watch",
    );
    expect(familyPreviewLabel(null)).toBe("Unknown");
  });

  it("returns expected tones per match strength", () => {
    expect(trueMomentumPreviewTone("strong")).toBe("good");
    expect(trueMomentumPreviewTone("moderate")).toBe("neutral");
    expect(trueMomentumPreviewTone("watch")).toBe("warn");
    expect(trueMomentumPreviewTone("blocked")).toBe("neutral");
    expect(trueMomentumPreviewTone(null)).toBe("neutral");
  });

  it("translates known reason codes to operator copy", () => {
    const labels = trueMomentumPreviewReasonLabels([
      "true_momentum_continuation_match",
      "momentum_pullback_signal_active",
      "thinkorswim_parity_pending",
      "totally_unknown_code",
    ]);
    expect(labels[0]).toBe("Continuation pattern match");
    expect(labels[1]).toBe("Pullback signal active");
    expect(labels[2]).toBe("Thinkorswim parity pending");
    expect(labels[3]).toBe("totally unknown code");
  });
});

describe("buildTrueMomentumStrategyPreview — disabled state", () => {
  it("returns no previews and the disabled reason when effective mode is disabled", () => {
    const result = buildTrueMomentumStrategyPreview(
      [candidate({ symbol: "XLK" })],
      status({ effective_mode: "disabled", requested_mode: "disabled" }),
    );
    expect(result.previews).toEqual([]);
    expect(result.previews_generated).toBe(false);
    expect(result.extra_reason_codes).toContain("true_momentum_strategy_mode_disabled");
  });

  it("returns no previews + active-not-implemented reason when active requested but blocked", () => {
    const result = buildTrueMomentumStrategyPreview(
      [candidate({ symbol: "XLK" })],
      status({ effective_mode: "disabled", requested_mode: "active" }),
    );
    expect(result.previews).toEqual([]);
    expect(result.previews_generated).toBe(false);
    expect(result.extra_reason_codes).toContain(
      "true_momentum_strategy_active_mode_not_implemented",
    );
  });

  it("returns no previews when status is null (treated as disabled)", () => {
    const result = buildTrueMomentumStrategyPreview([candidate()], null);
    expect(result.previews).toEqual([]);
    expect(result.previews_generated).toBe(false);
  });

  it("carries the preview phase / implementation tags + deterministic note", () => {
    const result = buildTrueMomentumStrategyPreview([], status());
    expect(result.preview_phase).toBe(TRUE_MOMENTUM_STRATEGY_PREVIEW_PHASE);
    expect(result.preview_implementation_status).toBe(
      TRUE_MOMENTUM_STRATEGY_PREVIEW_IMPLEMENTATION_STATUS,
    );
    expect(result.deterministic_note).toBe(TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE);
  });
});

describe("buildTrueMomentumStrategyPreview — classification", () => {
  it("classifies a clean bullish row as continuation strong", () => {
    const result = buildTrueMomentumStrategyPreview(
      [candidate({ symbol: "XLK" })],
      status(),
    );
    expect(result.previews_generated).toBe(true);
    expect(result.previews.length).toBe(1);
    expect(result.previews[0].family_id).toBe("true_momentum_continuation");
    expect(result.previews[0].match_strength).toBe("strong");
    expect(result.previews[0].non_actionable).toBe(true);
  });

  it("classifies continuation as moderate when trend or momo are weak", () => {
    const result = buildTrueMomentumStrategyPreview(
      [
        candidate({
          symbol: "QQQ",
          momentum_contribution: contribution({
            trend_score: 60,
            momo_score: 62,
          }),
        }),
      ],
      status(),
    );
    expect(result.previews[0].match_strength).toBe("moderate");
  });

  it("classifies pullback via the pullback signal flag", () => {
    const result = buildTrueMomentumStrategyPreview(
      [
        candidate({
          symbol: "IWM",
          strategy: "Event Continuation",
          momentum_contribution: contribution({ pullback_signal: true }),
        }),
      ],
      status(),
    );
    expect(result.previews[0].family_id).toBe("true_momentum_pullback");
    expect(result.previews[0].match_strength).toBe("strong");
  });

  it("classifies pullback by source strategy label when no pullback_signal flag", () => {
    const result = buildTrueMomentumStrategyPreview(
      [
        candidate({
          symbol: "DIA",
          strategy: "Pullback / Trend Continuation",
          momentum_contribution: contribution({ pullback_signal: false }),
        }),
      ],
      status(),
    );
    expect(result.previews[0].family_id).toBe("true_momentum_pullback");
    expect(result.previews[0].match_strength).toBe("moderate");
  });

  it("classifies reversal_watch on no-trade warning", () => {
    const result = buildTrueMomentumStrategyPreview(
      [
        candidate({
          symbol: "BAD",
          momentum_contribution: contribution({
            no_trade_warning: true,
            reason_codes: ["momentum_no_trade_warning"],
          }),
        }),
      ],
      status(),
    );
    expect(result.previews[0].family_id).toBe("true_momentum_reversal_watch");
    expect(result.previews[0].match_strength).toBe("watch");
  });

  it("classifies reversal_watch on bear total label for a long-biased strategy", () => {
    const result = buildTrueMomentumStrategyPreview(
      [
        candidate({
          symbol: "CONTRA",
          momentum_contribution: contribution({
            total_label: "Max Bear",
            total_score: -65,
            raw_total_contribution: -15,
          }),
        }),
      ],
      status(),
    );
    expect(result.previews[0].family_id).toBe("true_momentum_reversal_watch");
  });

  it("applies precedence: reversal_watch beats continuation when both could match", () => {
    const result = buildTrueMomentumStrategyPreview(
      [
        candidate({
          symbol: "MIXED",
          momentum_contribution: contribution({
            reversal_warning: true,
            reason_codes: ["momentum_reversal_warning"],
          }),
        }),
      ],
      status(),
    );
    expect(result.previews[0].family_id).toBe("true_momentum_reversal_watch");
  });

  it("skips off-mode / unmatched rows", () => {
    const result = buildTrueMomentumStrategyPreview(
      [
        candidate({
          symbol: "OFF",
          strategy: "Mean Reversion",
          momentum_contribution: contribution({
            mode: "off",
            applied: false,
            inferred_direction: "unknown",
            total_label: null,
            total_score: null,
            trend_score: null,
            momo_score: null,
            raw_total_contribution: 0,
            applied_score_delta: 0,
          }),
        }),
      ],
      status(),
    );
    expect(result.previews).toEqual([]);
    expect(result.summary.candidate_count).toBe(1);
    expect(result.summary.preview_count).toBe(0);
  });

  it("flags parity-pending operational caveats per row + in the summary", () => {
    const result = buildTrueMomentumStrategyPreview(
      [
        candidate({
          symbol: "PARITY",
          momentum_contribution: contribution({
            reason_codes: ["thinkorswim_parity_pending", "derived_higher_timeframe"],
          }),
        }),
      ],
      status(),
    );
    expect(result.previews[0].operational_caveats).toContain("thinkorswim_parity_pending");
    expect(result.previews[0].operational_caveats).toContain("derived_higher_timeframe");
    expect(result.summary.parity_pending_count).toBe(1);
    expect(result.summary.derived_higher_timeframe_count).toBe(1);
  });

  it("preview row has no order/approval/entry/stop/target fields", () => {
    const result = buildTrueMomentumStrategyPreview([candidate()], status());
    const preview = result.previews[0];
    const keys = Object.keys(preview);
    for (const forbidden of [
      "entry",
      "stop",
      "target",
      "size",
      "order_id",
      "approved",
      "route",
    ]) {
      expect(keys).not.toContain(forbidden);
    }
  });
});

describe("summarizeTrueMomentumStrategyPreview", () => {
  it("counts per-family and per-strength buckets", () => {
    const result = buildTrueMomentumStrategyPreview(
      [
        candidate({ symbol: "XLK" }),
        candidate({
          symbol: "IWM",
          rank: 2,
          strategy: "Pullback / Trend Continuation",
          momentum_contribution: contribution({ pullback_signal: true }),
        }),
        candidate({
          symbol: "BAD",
          rank: 3,
          momentum_contribution: contribution({
            no_trade_warning: true,
            reason_codes: ["momentum_no_trade_warning"],
          }),
        }),
      ],
      status(),
    );
    const summary = result.summary;
    expect(summary.preview_count).toBe(3);
    expect(summary.continuation_count).toBe(1);
    expect(summary.pullback_count).toBe(1);
    expect(summary.reversal_watch_count).toBe(1);
    expect(summary.strong_count).toBeGreaterThan(0);
    expect(summary.watch_count).toBe(1);

    // The standalone summarizer mirrors the in-place summary.
    const standalone = summarizeTrueMomentumStrategyPreview(result.previews, 3);
    expect(standalone).toEqual(summary);
  });
});

describe("deterministic-language guard", () => {
  it("never contains forbidden trade-action language", () => {
    const text = TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE.toLowerCase();
    for (const phrase of [
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "auto approve",
      "route order",
    ]) {
      expect(text).not.toContain(phrase);
    }
  });
});
