import { describe, expect, it } from "vitest";

import {
  buildMomentumTrialJson,
  buildMomentumTrialMarkdown,
  buildMomentumTrialSnapshot,
  classifyMomentumTrialCandidate,
  formatMomentumTrialTimestamp,
  isOperationalCaveatFlag,
  isTradeWarningFlag,
  MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE,
  MOMENTUM_TRIAL_JOURNAL_VERSION,
  momentumTrialOperationalCaveats,
  momentumTrialTradeWarnings,
  momentumTrialUniverseLabel,
  momentumTrialWarnings,
  partitionWarningFlags,
  rankMovementBuckets,
  sanitizeMomentumTrialNote,
  summarizeMomentumTrialSnapshot,
  topMomentumTrialMovers,
  topMomentumTrialOperationalCaveats,
  topMomentumTrialTradeWarnings,
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

  it("always emits Trade warnings + Operational caveats sections", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE);
    const md = buildMomentumTrialMarkdown(snapshot);
    // Phase B7.1: the single ambiguous "## Warnings" header is gone.
    // The two replacement sections are always emitted so operators can
    // see the snapshot explicitly answered each question.
    expect(md).not.toMatch(/^## Warnings$/m);
    expect(md).toContain("## Trade warnings");
    expect(md).toContain("## Operational caveats");
    expect(md).toContain("No trade warnings captured.");
    expect(md).toContain("No operational caveats captured.");
  });

  it("routes reversal warnings to the Trade warnings section", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        momentum_contribution: contribution({
          reversal_warning: true,
          reason_codes: ["momentum_reversal_warning"],
        }),
      }),
    ]);
    const md = buildMomentumTrialMarkdown(snapshot);
    expect(md).toContain("## Trade warnings");
    expect(md).toContain("reversal_warning");
    expect(md).toContain("## Operational caveats");
    expect(md).toContain("No operational caveats captured.");
  });

  it("routes parity-pending-only rows to Operational caveats, not Trade warnings", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        momentum_contribution: contribution({
          reason_codes: ["thinkorswim_parity_pending"],
        }),
      }),
    ]);
    const md = buildMomentumTrialMarkdown(snapshot);
    expect(md).toContain("## Trade warnings");
    expect(md).toContain("No trade warnings captured.");
    expect(md).toContain("## Operational caveats");
    expect(md).toContain("parity_pending");
  });

  it("emits the new universe-kind label", () => {
    const evaluated = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE, {
      universeSymbols: ["XLK", "IWM", "QQQ", "SPY", "DIA"],
    });
    const captured = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE);
    expect(buildMomentumTrialMarkdown(evaluated)).toContain("- Evaluated universe:");
    expect(buildMomentumTrialMarkdown(captured)).toContain("- Captured symbols:");
  });

  it("emits the new summary counts", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE);
    const md = buildMomentumTrialMarkdown(snapshot);
    expect(md).toContain("- Trade warnings: ");
    expect(md).toContain("- Operational caveats: ");
    expect(md).toContain("- Derived higher timeframe: ");
  });

  it("renders the deterministic guardrail copy exactly once", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE);
    const md = buildMomentumTrialMarkdown(snapshot);
    const occurrences = md.split(MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE).length - 1;
    expect(occurrences).toBe(1);
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

describe("Phase B7.1 — trade warnings vs operational caveats", () => {
  it("parity_pending alone increments operational_caveat_count, not trade_warning_count", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({
          reason_codes: ["thinkorswim_parity_pending"],
        }),
      }),
    ]);
    expect(snapshot.summary.trade_warning_count).toBe(0);
    expect(snapshot.summary.warning_count).toBe(0);
    expect(snapshot.summary.operational_caveat_count).toBe(1);
    expect(snapshot.summary.parity_pending_count).toBe(1);
  });

  it("derived_higher_timeframe increments operational_caveat_count + its own count", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({
          reason_codes: ["derived_higher_timeframe"],
        }),
      }),
    ]);
    expect(snapshot.summary.trade_warning_count).toBe(0);
    expect(snapshot.summary.operational_caveat_count).toBe(1);
    expect(snapshot.summary.derived_higher_timeframe_count).toBe(1);
  });

  it("no_trade_warning increments trade_warning_count", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({
          no_trade_warning: true,
          reason_codes: ["momentum_no_trade_warning"],
        }),
      }),
    ]);
    expect(snapshot.summary.trade_warning_count).toBe(1);
    expect(snapshot.summary.warning_count).toBe(1);
    expect(snapshot.summary.operational_caveat_count).toBe(0);
  });

  it("reversal_warning increments trade_warning_count", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({
          reversal_warning: true,
          reason_codes: ["momentum_reversal_warning"],
        }),
      }),
    ]);
    expect(snapshot.summary.trade_warning_count).toBe(1);
    expect(snapshot.summary.operational_caveat_count).toBe(0);
  });

  it("bearish total-label contradiction increments trade_warning_count", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({
          total_contribution: 12,
          shadow_contribution: 12,
          applied_score_delta: 0.05,
          raw_total_contribution: 12,
          total_label: "Bear",
          inferred_direction: "long",
        }),
        momentum_score_delta: 0.05,
      }),
    ]);
    expect(snapshot.candidates[0].trade_warning_flags).toContain(
      "bear_total_label_contradiction",
    );
    expect(snapshot.summary.trade_warning_count).toBe(1);
  });

  it("score_consistency_corrected increments operational_caveat_count, not trade_warning_count", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "AAA",
        score_consistency_status: "corrected",
      }),
    ]);
    expect(snapshot.summary.trade_warning_count).toBe(0);
    expect(snapshot.summary.operational_caveat_count).toBe(1);
    expect(snapshot.summary.score_consistency_corrected_count).toBe(1);
  });

  it("active_mode_blocked_by_safety_guard is an operational caveat, not a trade warning", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "XLE",
        momentum_contribution: contribution({
          mode: "shadow",
          applied: false,
          reason_codes: ["active_mode_blocked_by_safety_guard"],
        }),
      }),
    ]);
    expect(snapshot.summary.trade_warning_count).toBe(0);
    expect(snapshot.summary.operational_caveat_count).toBe(1);
    expect(snapshot.summary.blocked_active_count).toBe(1);
  });

  it("universe_kind reads 'evaluated' when universeSymbols provided", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE, {
      universeSymbols: ["XLK", "IWM", "QQQ", "SPY", "DIA"],
    });
    expect(snapshot.universe_kind).toBe("evaluated");
    expect(snapshot.universe_symbols).toEqual(["XLK", "IWM", "QQQ", "SPY", "DIA"]);
    expect(momentumTrialUniverseLabel(snapshot.universe_kind)).toBe("Evaluated universe");
  });

  it("universe_kind reads 'captured' when no universeSymbols provided", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_DEPLOYED_QUEUE);
    expect(snapshot.universe_kind).toBe("captured");
    expect(momentumTrialUniverseLabel(snapshot.universe_kind)).toBe("Captured symbols");
  });

  it("partitions warning flags into trade warnings and operational caveats", () => {
    const partition = partitionWarningFlags([
      "no_trade_warning",
      "parity_pending",
      "reversal_warning",
      "derived_higher_timeframe",
      "bear_total_label_contradiction",
      "direction_unknown",
      "score_consistency_corrected",
      "active_mode_blocked_by_safety_guard",
    ]);
    expect(partition.tradeWarnings).toEqual([
      "no_trade_warning",
      "reversal_warning",
      "bear_total_label_contradiction",
    ]);
    expect(partition.operationalCaveats).toEqual([
      "parity_pending",
      "derived_higher_timeframe",
      "direction_unknown",
      "score_consistency_corrected",
      "active_mode_blocked_by_safety_guard",
    ]);
  });

  it("isTradeWarningFlag / isOperationalCaveatFlag classify every flag in the union", () => {
    expect(isTradeWarningFlag("no_trade_warning")).toBe(true);
    expect(isTradeWarningFlag("parity_pending")).toBe(false);
    expect(isOperationalCaveatFlag("parity_pending")).toBe(true);
    expect(isOperationalCaveatFlag("derived_higher_timeframe")).toBe(true);
    expect(isOperationalCaveatFlag("no_trade_warning")).toBe(false);
  });

  it("topMomentumTrialTradeWarnings excludes parity-only rows", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({
          reason_codes: ["thinkorswim_parity_pending"],
        }),
      }),
      candidate({
        symbol: "BBB",
        momentum_contribution: contribution({
          no_trade_warning: true,
          reason_codes: ["momentum_no_trade_warning"],
        }),
      }),
    ]);
    expect(topMomentumTrialTradeWarnings(snapshot).map((c) => c.symbol)).toEqual(["BBB"]);
    expect(snapshot.trade_warning_candidates.map((c) => c.symbol)).toEqual(["BBB"]);
  });

  it("topMomentumTrialOperationalCaveats returns parity-only rows", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        symbol: "AAA",
        momentum_contribution: contribution({
          reason_codes: ["thinkorswim_parity_pending"],
        }),
      }),
      candidate({
        symbol: "BBB",
        momentum_contribution: contribution({
          no_trade_warning: true,
          reason_codes: ["momentum_no_trade_warning"],
        }),
      }),
    ]);
    expect(topMomentumTrialOperationalCaveats(snapshot).map((c) => c.symbol)).toEqual(["AAA"]);
    expect(snapshot.operational_caveat_candidates.map((c) => c.symbol)).toEqual(["AAA"]);
  });

  it("momentumTrialTradeWarnings + momentumTrialOperationalCaveats accessors mirror partition", () => {
    const snapshot = buildMomentumTrialSnapshot([
      candidate({
        momentum_contribution: contribution({
          no_trade_warning: true,
          reason_codes: ["momentum_no_trade_warning", "thinkorswim_parity_pending"],
        }),
      }),
    ]);
    const c = snapshot.candidates[0];
    expect(momentumTrialTradeWarnings(c)).toEqual(["no_trade_warning"]);
    expect(momentumTrialOperationalCaveats(c)).toEqual(["parity_pending"]);
    // Back-compat union accessor still returns the full list.
    expect(momentumTrialWarnings(c).sort()).toEqual(
      ["no_trade_warning", "parity_pending"].sort(),
    );
  });

  it("JSON export carries the new counts and the universe_kind", () => {
    const snapshot = buildMomentumTrialSnapshot(
      [
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
            reason_codes: ["thinkorswim_parity_pending", "derived_higher_timeframe"],
          }),
        }),
      ],
      { universeSymbols: ["AAA", "BBB", "CCC"] },
    );
    const json = buildMomentumTrialJson(snapshot);
    const parsed = JSON.parse(json) as {
      snapshot: ReturnType<typeof buildMomentumTrialSnapshot>;
    };
    expect(parsed.snapshot.summary.trade_warning_count).toBe(1);
    expect(parsed.snapshot.summary.operational_caveat_count).toBe(1);
    expect(parsed.snapshot.summary.parity_pending_count).toBe(1);
    expect(parsed.snapshot.summary.derived_higher_timeframe_count).toBe(1);
    expect(parsed.snapshot.universe_kind).toBe("evaluated");
    expect(parsed.snapshot.trade_warning_candidates.length).toBe(1);
    expect(parsed.snapshot.operational_caveat_candidates.length).toBe(1);
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
