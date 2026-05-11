import { describe, expect, it } from "vitest";

import {
  buildMomentumTrialSnapshot,
  type MomentumTrialSnapshot,
} from "@/lib/momentum-trial-journal";
import {
  buildMomentumOutcomeJson,
  buildMomentumOutcomeMarkdown,
  buildMomentumTrialOutcomeReview,
  candidateOutcomeDefaults,
  isMomentumTrialOutcomeTag,
  momentumCandidateOutcomeKey,
  MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE,
  MOMENTUM_TRIAL_OUTCOME_REVIEW_VERSION,
  MOMENTUM_TRIAL_OUTCOME_TAGS,
  outcomeReasonCounts,
  outcomeTagLabel,
  outcomeTagTone,
  sanitizeMomentumOutcomeNote,
  summarizeMomentumTrialOutcomes,
  validateMomentumTrialOutcomeReview,
} from "@/lib/momentum-trial-outcomes";
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

const ACTIVE_QUEUE: QueueCandidate[] = [
  candidate({ rank: 1, symbol: "XLK", score: 0.967, score_before_momentum: 0.897 }),
  candidate({ rank: 2, symbol: "IWM", score: 0.948, score_before_momentum: 0.878 }),
  candidate({ rank: 3, symbol: "QQQ", score: 0.917, score_before_momentum: 0.847 }),
];

const MIXED_QUEUE: QueueCandidate[] = [
  candidate({ rank: 1, symbol: "XLK" }),
  candidate({
    rank: 2,
    symbol: "PARITY",
    momentum_contribution: contribution({
      reason_codes: ["thinkorswim_parity_pending"],
    }),
  }),
  candidate({
    rank: 3,
    symbol: "BAD",
    momentum_contribution: contribution({
      no_trade_warning: true,
      reason_codes: ["momentum_no_trade_warning"],
    }),
  }),
];

function snapshotFor(rows: QueueCandidate[]): MomentumTrialSnapshot {
  return buildMomentumTrialSnapshot(rows, {
    universeSymbols: rows.map((r) => r.symbol),
  });
}

describe("outcomeTagLabel + outcomeTagTone", () => {
  it("labels every supported tag", () => {
    expect(outcomeTagLabel("worked")).toBe("Worked");
    expect(outcomeTagLabel("missed")).toBe("Missed");
    expect(outcomeTagLabel("too_aggressive")).toBe("Too aggressive");
    expect(outcomeTagLabel("good_warning")).toBe("Good warning");
    expect(outcomeTagLabel("false_warning")).toBe("False warning");
    expect(outcomeTagLabel("watchlist_only")).toBe("Watchlist only");
    expect(outcomeTagLabel("needs_tos_parity_check")).toBe("Needs ToS parity check");
    expect(outcomeTagLabel("ignored")).toBe("Ignored");
    expect(outcomeTagLabel("unclear")).toBe("Unclear");
  });

  it("falls back to 'Unclear' for unknown / null tags", () => {
    expect(outcomeTagLabel(null)).toBe("Unclear");
    expect(outcomeTagLabel(undefined)).toBe("Unclear");
    expect(outcomeTagLabel("garbage")).toBe("Unclear");
  });

  it("returns expected tones", () => {
    expect(outcomeTagTone("worked")).toBe("good");
    expect(outcomeTagTone("missed")).toBe("bad");
    expect(outcomeTagTone("too_aggressive")).toBe("warn");
    expect(outcomeTagTone("good_warning")).toBe("good");
    expect(outcomeTagTone("false_warning")).toBe("warn");
    expect(outcomeTagTone("needs_tos_parity_check")).toBe("warn");
    expect(outcomeTagTone("watchlist_only")).toBe("neutral");
    expect(outcomeTagTone("ignored")).toBe("neutral");
    expect(outcomeTagTone("unclear")).toBe("neutral");
    expect(outcomeTagTone(null)).toBe("neutral");
  });

  it("isMomentumTrialOutcomeTag accepts every supported tag", () => {
    for (const tag of MOMENTUM_TRIAL_OUTCOME_TAGS) {
      expect(isMomentumTrialOutcomeTag(tag)).toBe(true);
    }
    expect(isMomentumTrialOutcomeTag("garbage")).toBe(false);
    expect(isMomentumTrialOutcomeTag(null)).toBe(false);
  });
});

describe("sanitizeMomentumOutcomeNote", () => {
  it("trims and collapses whitespace", () => {
    expect(sanitizeMomentumOutcomeNote("  hello    world  ")).toBe("hello world");
  });

  it("redacts forbidden trade-action language", () => {
    const cleaned = sanitizeMomentumOutcomeNote(
      "operator says buy now SPY because Momentum is strong",
    );
    expect(cleaned.toLowerCase()).not.toContain("buy now");
    expect(cleaned).toContain("[redacted]");
  });

  it("length-caps overlong notes", () => {
    const big = "x".repeat(2000);
    const cleaned = sanitizeMomentumOutcomeNote(big);
    expect(cleaned.length).toBeLessThanOrEqual(1200);
  });

  it("returns empty string for null/undefined", () => {
    expect(sanitizeMomentumOutcomeNote(null)).toBe("");
    expect(sanitizeMomentumOutcomeNote(undefined)).toBe("");
  });
});

describe("candidateOutcomeDefaults", () => {
  it("returns one outcome row per top/warning/caveat candidate, deduped", () => {
    const snapshot = snapshotFor(MIXED_QUEUE);
    const defaults = candidateOutcomeDefaults(snapshot);
    const keys = defaults.map((row) => momentumCandidateOutcomeKey(row));
    const uniqueKeys = new Set(keys);
    expect(keys.length).toBe(uniqueKeys.size);
    const symbols = defaults.map((row) => row.symbol);
    // The mixed queue rows all surface in either top, trade-warning,
    // or operational-caveat buckets.
    for (const sym of ["XLK", "PARITY", "BAD"]) {
      expect(symbols).toContain(sym);
    }
  });

  it("defaults every outcome tag to 'unclear' and copies reason flags", () => {
    const snapshot = snapshotFor(MIXED_QUEUE);
    const defaults = candidateOutcomeDefaults(snapshot);
    for (const row of defaults) {
      expect(row.tag).toBe("unclear");
      expect(row.note).toBe("");
      expect(Array.isArray(row.reason_codes)).toBe(true);
      expect(Array.isArray(row.trade_warning_flags)).toBe(true);
      expect(Array.isArray(row.operational_caveat_flags)).toBe(true);
    }
  });

  it("returns an empty list for null/undefined snapshots", () => {
    expect(candidateOutcomeDefaults(null)).toEqual([]);
    expect(candidateOutcomeDefaults(undefined)).toEqual([]);
  });
});

describe("buildMomentumTrialOutcomeReview", () => {
  it("builds defaults when no existing outcomes are provided", () => {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot);
    expect(review.schema_version).toBe(MOMENTUM_TRIAL_OUTCOME_REVIEW_VERSION);
    expect(review.snapshot).toBe(snapshot);
    expect(review.candidate_outcomes.length).toBeGreaterThan(0);
    for (const row of review.candidate_outcomes) {
      expect(row.tag).toBe("unclear");
    }
  });

  it("re-applies tags/notes from existing outcomes keyed by symbol+strategy+rank", () => {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot, {
      existingOutcomes: [
        {
          symbol: "XLK",
          strategy: "Event Continuation",
          rank: 1,
          tag: "worked",
          note: "Clean continuation",
        },
        {
          symbol: "IWM",
          strategy: "Event Continuation",
          rank: 2,
          tag: "too_aggressive",
          note: "Saturated too quickly",
        },
      ],
    });
    const xlk = review.candidate_outcomes.find((r) => r.symbol === "XLK");
    const iwm = review.candidate_outcomes.find((r) => r.symbol === "IWM");
    expect(xlk?.tag).toBe("worked");
    expect(xlk?.note).toBe("Clean continuation");
    expect(iwm?.tag).toBe("too_aggressive");
    expect(iwm?.note).toBe("Saturated too quickly");
  });

  it("ignores existing outcomes that no longer match a snapshot row", () => {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot, {
      existingOutcomes: [
        {
          symbol: "ZZZZ",
          strategy: "Event Continuation",
          rank: 9,
          tag: "missed",
          note: "Stale row",
        },
      ],
    });
    const symbols = review.candidate_outcomes.map((r) => r.symbol);
    expect(symbols).not.toContain("ZZZZ");
  });

  it("sanitizes the global conclusion", () => {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot, {
      globalConclusion: "buy now XLK — Momentum lifted everything",
    });
    expect(review.global_conclusion).not.toBeNull();
    expect(review.global_conclusion?.text.toLowerCase()).not.toContain("buy now");
    expect(review.global_conclusion?.text).toContain("[redacted]");
  });

  it("degrades gracefully for a null snapshot", () => {
    const review = buildMomentumTrialOutcomeReview(null);
    expect(review.candidate_outcomes).toEqual([]);
    expect(review.summary.candidate_count).toBe(0);
  });

  it("output never includes NaN or Infinity", () => {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot);
    const json = buildMomentumOutcomeJson(review);
    expect(json).not.toMatch(/NaN/i);
    expect(json).not.toMatch(/Infinity/i);
  });
});

describe("summarizeMomentumTrialOutcomes + outcomeReasonCounts", () => {
  function snapshotWithTagged(tags: Record<string, string>) {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const outcomes = candidateOutcomeDefaults(snapshot).map((row) => ({
      ...row,
      tag: (tags[row.symbol] ?? row.tag) as ReturnType<typeof outcomeTagLabel> extends string
        ? typeof row.tag
        : never,
    }));
    return buildMomentumTrialOutcomeReview(snapshot, {
      existingOutcomes: outcomes,
    });
  }

  it("counts every tag bucket", () => {
    const review = snapshotWithTagged({
      XLK: "worked",
      IWM: "missed",
      QQQ: "needs_tos_parity_check",
    });
    expect(review.summary.candidate_count).toBe(3);
    expect(review.summary.worked_count).toBe(1);
    expect(review.summary.missed_count).toBe(1);
    expect(review.summary.needs_tos_parity_check_count).toBe(1);
    expect(review.summary.unclear_count).toBe(0);
  });

  it("returns reason_code_counts via outcomeReasonCounts", () => {
    const snapshot = snapshotFor(MIXED_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot);
    const reasonCounts = outcomeReasonCounts(review);
    // PARITY row should surface the thinkorswim_parity_pending reason code.
    expect(reasonCounts["thinkorswim_parity_pending"]).toBeGreaterThan(0);
  });

  it("summarize returns shell summary for null", () => {
    const summary = summarizeMomentumTrialOutcomes(null);
    expect(summary.candidate_count).toBe(0);
    expect(summary.worked_count).toBe(0);
    expect(summary.reason_code_counts).toEqual({});
  });
});

describe("validateMomentumTrialOutcomeReview", () => {
  it("accepts a freshly built review", () => {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot);
    const result = validateMomentumTrialOutcomeReview(review);
    expect(result.ok).toBe(true);
  });

  it("rejects malformed payloads", () => {
    expect(validateMomentumTrialOutcomeReview(null).ok).toBe(false);
    expect(validateMomentumTrialOutcomeReview("not-an-object").ok).toBe(false);
    expect(
      validateMomentumTrialOutcomeReview({ schema_version: "wrong" }).ok,
    ).toBe(false);
  });
});

describe("buildMomentumOutcomeMarkdown", () => {
  it("includes snapshot + review headers, global conclusion, summary, and table", () => {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot, {
      existingOutcomes: [
        {
          symbol: "XLK",
          strategy: "Event Continuation",
          rank: 1,
          tag: "worked",
          note: "Continuation through 3:30 close",
        },
      ],
      globalConclusion: "Momentum correctly elevated XLK; review IWM next session.",
    });
    const md = buildMomentumOutcomeMarkdown(review);
    expect(md).toContain("# Momentum Trial Outcome Review");
    expect(md).toContain("- Snapshot generated at:");
    expect(md).toContain("- Review generated at:");
    expect(md).toContain("## Global outcome conclusion");
    expect(md).toContain("Momentum correctly elevated XLK");
    expect(md).toContain("## Outcome summary");
    expect(md).toContain("- Worked: 1");
    expect(md).toContain("## Candidate outcomes");
    expect(md).toContain("| XLK |");
    expect(md).toContain("Worked");
    expect(md).toContain("Continuation through 3:30 close");
    expect(md).toContain("## Remaining caveats");
    expect(md).toContain("Phase C True Momentum strategy families are not active.");
    expect(md).toContain(MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE);
  });

  it("renders the 'no global conclusion' empty state", () => {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot);
    const md = buildMomentumOutcomeMarkdown(review);
    expect(md).toContain("_No global conclusion recorded._");
  });

  it("renders the universe heading using the snapshot's universe_kind", () => {
    const evaluated = buildMomentumTrialOutcomeReview(
      buildMomentumTrialSnapshot(ACTIVE_QUEUE, {
        universeSymbols: ["XLK", "IWM", "QQQ", "DIA"],
      }),
    );
    const captured = buildMomentumTrialOutcomeReview(snapshotFor([]));
    expect(buildMomentumOutcomeMarkdown(evaluated)).toContain("- Evaluated universe:");
    expect(buildMomentumOutcomeMarkdown(captured)).toContain("- Captured symbols:");
  });

  it("never contains forbidden trade-action language", () => {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot, {
      globalConclusion: "regular review notes only",
    });
    const md = buildMomentumOutcomeMarkdown(review).toLowerCase();
    for (const phrase of [
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "auto approve",
      "route order",
    ]) {
      expect(md).not.toContain(phrase);
    }
  });
});

describe("buildMomentumOutcomeJson", () => {
  it("is parseable JSON with review + deterministic_note", () => {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot, {
      existingOutcomes: [
        {
          symbol: "XLK",
          strategy: "Event Continuation",
          rank: 1,
          tag: "worked",
          note: "Notes",
        },
      ],
      globalConclusion: "Looked good overall.",
    });
    const json = buildMomentumOutcomeJson(review);
    const parsed = JSON.parse(json);
    expect(parsed.schema_version).toBe(MOMENTUM_TRIAL_OUTCOME_REVIEW_VERSION);
    expect(parsed.deterministic_note).toBe(MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE);
    expect(parsed.review.candidate_outcomes.length).toBeGreaterThan(0);
    expect(parsed.review.snapshot).toBeDefined();
    expect(parsed.review.summary).toBeDefined();
  });

  it("never contains forbidden trade-action language", () => {
    const snapshot = snapshotFor(ACTIVE_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot, {
      globalConclusion: "regular review notes only",
    });
    const json = buildMomentumOutcomeJson(review).toLowerCase();
    for (const phrase of [
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "auto approve",
      "route order",
    ]) {
      expect(json).not.toContain(phrase);
    }
  });
});
