import { describe, expect, it } from "vitest";

import {
  buildMomentumTrialJson,
  buildMomentumTrialMarkdown,
  buildMomentumTrialSnapshot,
  classifyMomentumTrialCandidate,
  formatMomentumTrialTimestamp,
  MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE,
  MOMENTUM_TRIAL_JOURNAL_VERSION,
  momentumTrialWarnings,
  rankMovementBuckets,
  sanitizeMomentumTrialNote,
  summarizeMomentumTrialSnapshot,
  topMomentumTrialMovers,
  topMomentumTrialWarnings,
  validateMomentumTrialSnapshot,
} from "@/lib/momentum-trial-journal";
import type {
  MomentumRankingContribution,
  QueueCandidate,
} from "@/lib/recommendations";

function contribution(overrides: Partial<MomentumRankingContribution> = {}): MomentumRankingContribution {
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
    total_score: 80,
    total_label: "Bull",
    trend_score: 75,
    momo_score: 65,
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
  // Mirror the Phase B6.3 invariant that `score_after_momentum` matches
  // the live `score` field — otherwise tests that override only `score`
  // would leave the impact row reading the factory default and break
  // the baseline/current/applied-delta invariant.
  const score = overrides.score ?? 0.877;
  const scoreBefore = overrides.score_before_momentum ?? 0.807;
  return {
    rank: 1,
    symbol: "SPY",
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
    momentum_score_delta: 0.07,
    momentum_realized_score_delta: 0.07,
    score_consistency_status: "ok",
    ...overrides,
  };
}

const ACTIVE_DEPLOYED_QUEUE: QueueCandidate[] = [
  candidate({
    rank: 1,
    symbol: "XLK",
    strategy: "Event Continuation",
    score: 0.967,
    score_before_momentum: 0.897,
  }),
  candidate({
    rank: 2,
    symbol: "IWM",
    strategy: "Event Continuation",
    score: 0.948,
    score_before_momentum: 0.878,
  }),
  candidate({
    rank: 3,
    symbol: "QQQ",
    strategy: "Event Continuation",
    score: 0.917,
    score_before_momentum: 0.847,
  }),
  candidate({
    rank: 4,
    symbol: "SPY",
    strategy: "Event Continuation",
    score: 0.877,
    score_before_momentum: 0.807,
  }),
];

describe("buildMomentumTrialSnapshot", () => {
  it("builds a snapshot from active-mode candidates with baseline/current/active fields", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE, {
      universeSymbols: ["XLK", "IWM", "QQQ", "SPY"],
    });
    expect(snapshot.schema_version).toBe(MOMENTUM_TRIAL_JOURNAL_VERSION);
    expect(snapshot.summary.candidate_count).toBe(4);
    expect(snapshot.summary.active_mode_count).toBe(4);
    expect(snapshot.summary.shadow_mode_count).toBe(0);
    expect(snapshot.summary.off_mode_count).toBe(0);
    expect(snapshot.universe_symbols).toEqual(["XLK", "IWM", "QQQ", "SPY"]);
    expect(snapshot.candidates.length).toBe(4);
    for (const c of snapshot.candidates) {
      expect(c.current_score).toBeGreaterThan(0);
      expect(c.baseline_score).toBeGreaterThan(0);
      expect(c.active_score).toBeGreaterThan(0);
      expect(Math.abs(c.current_score - c.baseline_score - c.applied_delta)).toBeLessThan(1e-3);
    }
  });

  it("counts positive/negative/zero contributions", () => {
    const candidates: QueueCandidate[] = [
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({ shadow_contribution: 12, mode: "shadow", applied: false, total_contribution: 0 }),
        momentum_score_delta: 0,
      }),
      candidate({
        symbol: "BBB",
        momentum_contribution: contribution({ shadow_contribution: -8, mode: "shadow", applied: false, total_contribution: 0 }),
        momentum_score_delta: 0,
      }),
      candidate({
        symbol: "CCC",
        momentum_contribution: contribution({ shadow_contribution: 0, mode: "shadow", applied: false, total_contribution: 0 }),
        momentum_score_delta: 0,
      }),
    ];
    const snapshot = buildMomentumTrialSnapshot(candidates);
    expect(snapshot.summary.positive_contribution_count).toBe(1);
    expect(snapshot.summary.negative_contribution_count).toBe(1);
    expect(snapshot.summary.zero_contribution_count).toBe(1);
    expect(snapshot.summary.shadow_mode_count).toBe(3);
  });

  it("counts parity pending candidates", () => {
    const candidates: QueueCandidate[] = [
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({
          reason_codes: ["thinkorswim_parity_pending"],
        }),
      }),
      candidate({
        symbol: "BBB",
        momentum_contribution: contribution({
          reason_codes: ["thinkorswim_parity_pending", "direction_unknown"],
        }),
      }),
      candidate({ symbol: "CCC", momentum_contribution: contribution() }),
    ];
    const snapshot = buildMomentumTrialSnapshot(candidates);
    expect(snapshot.summary.parity_pending_count).toBe(2);
  });

  it("counts direction-unknown candidates", () => {
    const candidates: QueueCandidate[] = [
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({ reason_codes: ["direction_unknown"] }),
      }),
      candidate({ symbol: "BBB", momentum_contribution: contribution() }),
    ];
    const snapshot = buildMomentumTrialSnapshot(candidates);
    expect(snapshot.summary.direction_unknown_count).toBe(1);
  });

  it("counts score consistency corrected candidates from either signal", () => {
    const candidates: QueueCandidate[] = [
      candidate({
        symbol: "AAA",
        // Phase B6.4 status tag alone is enough.
        score_consistency_status: "corrected",
      }),
      candidate({
        symbol: "BBB",
        // Phase B6.3 reason code alone is enough.
        momentum_contribution: contribution({
          reason_codes: ["momentum_score_consistency_corrected"],
        }),
      }),
      candidate({ symbol: "CCC" }),
    ];
    const snapshot = buildMomentumTrialSnapshot(candidates);
    expect(snapshot.summary.score_consistency_corrected_count).toBe(2);
  });

  it("handles missing fields safely without NaN/Infinity", () => {
    const malformed: QueueCandidate = {
      rank: NaN as unknown as number,
      symbol: "BAD",
      strategy: "Broken",
      workflow_source: "x",
      timeframe: "1D",
      status: "top_candidate",
      score: NaN as unknown as number,
      expected_rr: NaN as unknown as number,
      confidence: NaN as unknown as number,
      reason_text: "",
      thesis: "",
      momentum_contribution: undefined,
    };
    const snapshot = buildMomentumTrialSnapshot([
      malformed,
      candidate({ symbol: "OK" }),
    ]);
    expect(snapshot.summary.candidate_count).toBe(2);
    for (const c of snapshot.candidates) {
      expect(Number.isFinite(c.current_score)).toBe(true);
      expect(Number.isFinite(c.baseline_score)).toBe(true);
      expect(Number.isFinite(c.active_score)).toBe(true);
      expect(Number.isFinite(c.applied_delta)).toBe(true);
      expect(Number.isFinite(c.realized_delta)).toBe(true);
      expect(Number.isFinite(c.expected_rr)).toBe(true);
      expect(Number.isFinite(c.confidence)).toBe(true);
    }
    const json = buildMomentumTrialJson(snapshot);
    expect(json).not.toMatch(/NaN/i);
    expect(json).not.toMatch(/Infinity/i);
  });

  it("attaches a sanitized operator note when provided", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE, {
      operatorNote: "   XLK leading; SPY trailing.   ",
    });
    expect(snapshot.operator_note).not.toBeNull();
    expect(snapshot.operator_note?.text).toBe("XLK leading; SPY trailing.");
  });

  it("flags blocked-active candidates separately from active/shadow tallies", () => {
    const blocked = candidate({
      symbol: "XLE",
      momentum_contribution: contribution({
        mode: "shadow",
        applied: false,
        reason_codes: ["active_mode_blocked_by_safety_guard"],
      }),
    });
    const snapshot = buildMomentumTrialSnapshot([blocked]);
    expect(snapshot.summary.blocked_active_count).toBe(1);
    expect(snapshot.candidates[0].classification).toBe("blocked_active");
    expect(momentumTrialWarnings(snapshot.candidates[0])).toContain(
      "active_mode_blocked_by_safety_guard",
    );
  });

  it("infers universe_symbols from candidate symbols when not provided", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE);
    expect(snapshot.universe_symbols).toEqual(["XLK", "IWM", "QQQ", "SPY"]);
  });

  it("emits empty snapshot when given no candidates", () => {
    const snapshot = buildMomentumTrialSnapshot([]);
    expect(snapshot.summary.candidate_count).toBe(0);
    expect(snapshot.candidates.length).toBe(0);
    expect(snapshot.top_candidates.length).toBe(0);
    expect(snapshot.warning_candidates.length).toBe(0);
  });
});

describe("sanitizeMomentumTrialNote", () => {
  it("trims whitespace and collapses internal whitespace", () => {
    expect(sanitizeMomentumTrialNote("  hello    world  ")).toBe("hello world");
  });

  it("redacts forbidden action language", () => {
    const cleaned = sanitizeMomentumTrialNote("buy now SPY because momentum is strong");
    expect(cleaned.toLowerCase()).not.toContain("buy now");
    expect(cleaned).toContain("[redacted]");
  });

  it("returns empty string for null/undefined", () => {
    expect(sanitizeMomentumTrialNote(null)).toBe("");
    expect(sanitizeMomentumTrialNote(undefined)).toBe("");
  });
});

describe("buildMomentumTrialMarkdown", () => {
  it("includes summary and top candidates", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE, {
      operatorNote: "XLK and IWM leading.",
    });
    const md = buildMomentumTrialMarkdown(snapshot);
    expect(md).toContain("# Momentum Trial Journal Snapshot");
    expect(md).toContain("## Summary");
    expect(md).toContain("- Candidates captured: 4");
    expect(md).toContain("## Top candidates");
    expect(md).toContain("| XLK |");
    expect(md).toContain("| SPY |");
    expect(md).toContain("Operator note");
    expect(md).toContain("XLK and IWM leading.");
    expect(md).toContain(MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE);
  });

  it("omits warning table when no candidates carry flags", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE);
    const md = buildMomentumTrialMarkdown(snapshot);
    expect(md).not.toContain("## Warnings");
  });

  it("includes warning rows when present", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        momentum_contribution: contribution({
          reversal_warning: true,
          reason_codes: ["momentum_reversal_warning", "thinkorswim_parity_pending"],
        }),
      }),
    ]);
    const md = buildMomentumTrialMarkdown(snapshot);
    expect(md).toContain("## Warnings");
    expect(md).toContain("reversal_warning");
  });
});

describe("buildMomentumTrialJson", () => {
  it("is parseable JSON with snapshot + deterministic_note", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE);
    const json = buildMomentumTrialJson(snapshot);
    const parsed = JSON.parse(json);
    expect(parsed.schema_version).toBe(MOMENTUM_TRIAL_JOURNAL_VERSION);
    expect(parsed.deterministic_note).toBe(MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE);
    expect(parsed.snapshot.candidates.length).toBe(4);
    expect(json).not.toMatch(/NaN/i);
    expect(json).not.toMatch(/Infinity/i);
  });
});

describe("validateMomentumTrialSnapshot", () => {
  it("accepts a freshly built snapshot", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE);
    const result = validateMomentumTrialSnapshot(snapshot);
    expect(result.ok).toBe(true);
  });

  it("rejects malformed snapshots", () => {
    expect(validateMomentumTrialSnapshot(null).ok).toBe(false);
    expect(validateMomentumTrialSnapshot("not-an-object").ok).toBe(false);
    expect(
      validateMomentumTrialSnapshot({ schema_version: "wrong" }).ok,
    ).toBe(false);
  });
});

describe("topMomentumTrialMovers + topMomentumTrialWarnings", () => {
  it("orders top movers by absolute applied delta", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({ applied_score_delta: 0.07, raw_total_contribution: 20 }),
        momentum_score_delta: 0.07,
        score_before_momentum: 0.4,
        score_after_momentum: 0.47,
        score: 0.47,
      }),
      candidate({
        symbol: "BBB",
        momentum_contribution: contribution({ applied_score_delta: -0.05, raw_total_contribution: -14 }),
        momentum_score_delta: -0.05,
        score_before_momentum: 0.5,
        score_after_momentum: 0.45,
        score: 0.45,
      }),
      candidate({
        symbol: "CCC",
        momentum_contribution: contribution({ applied_score_delta: 0.01, raw_total_contribution: 3 }),
        momentum_score_delta: 0.01,
        score_before_momentum: 0.5,
        score_after_momentum: 0.51,
        score: 0.51,
      }),
    ]);
    const top = topMomentumTrialMovers(snapshot, 3);
    expect(top.map((c) => c.symbol)).toEqual(["AAA", "BBB", "CCC"]);
  });

  it("orders top warnings by severity", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({
          no_trade_warning: true,
          reason_codes: ["momentum_no_trade_warning"],
        }),
      }),
      candidate({
        symbol: "BBB",
        momentum_contribution: contribution({
          reason_codes: ["thinkorswim_parity_pending"],
        }),
      }),
      candidate({
        symbol: "CCC",
        momentum_contribution: contribution({
          reversal_warning: true,
          reason_codes: ["momentum_reversal_warning"],
        }),
      }),
    ]);
    const top = topMomentumTrialWarnings(snapshot, 3);
    // no_trade > reversal > parity_pending
    expect(top.map((c) => c.symbol)).toEqual(["AAA", "CCC", "BBB"]);
  });
});

describe("rankMovementBuckets", () => {
  it("classifies active/shadow/off movements", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({ symbol: "AAA" }),
      candidate({
        symbol: "BBB",
        momentum_contribution: contribution({
          mode: "shadow",
          applied: false,
          shadow_contribution: 10,
          total_contribution: 0,
        }),
        momentum_score_delta: 0,
      }),
      candidate({
        symbol: "CCC",
        momentum_contribution: contribution({ mode: "off", enabled: false }),
        momentum_score_delta: 0,
      }),
    ]);
    const buckets = rankMovementBuckets(snapshot);
    expect(buckets.active_up).toBeGreaterThan(0);
    expect(buckets.shadow_up + buckets.shadow_flat + buckets.shadow_down).toBeGreaterThan(0);
    expect(buckets.off_or_missing).toBeGreaterThan(0);
  });
});

describe("formatMomentumTrialTimestamp + classifyMomentumTrialCandidate", () => {
  it("formats string and Date inputs to ISO-8601", () => {
    const date = new Date("2026-05-11T13:30:00Z");
    expect(formatMomentumTrialTimestamp(date)).toContain("2026-05-11T13:30:00");
    expect(formatMomentumTrialTimestamp("2026-05-11T13:30:00Z")).toContain("2026-05-11T13:30:00");
    expect(formatMomentumTrialTimestamp(null)).toBe("—");
  });

  it("classifies undefined candidate as contribution_missing", () => {
    expect(classifyMomentumTrialCandidate(undefined)).toBe("contribution_missing");
  });
});

describe("summarizeMomentumTrialSnapshot", () => {
  it("returns shell summary for null input", () => {
    const summary = summarizeMomentumTrialSnapshot(null);
    expect(summary.candidate_count).toBe(0);
    expect(summary.active_delta_scale).toBe(0.35);
  });
});

describe("deterministic-language guard", () => {
  it("snapshot output never includes action language", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE, {
      operatorNote: "review notes only",
    });
    const md = buildMomentumTrialMarkdown(snapshot).toLowerCase();
    const json = buildMomentumTrialJson(snapshot).toLowerCase();
    for (const phrase of [
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "auto approve",
      "route order",
    ]) {
      expect(md).not.toContain(phrase);
      expect(json).not.toContain(phrase);
    }
  });
});
