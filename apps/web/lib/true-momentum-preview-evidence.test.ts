import { describe, expect, it } from "vitest";

import {
  buildTrueMomentumPreviewEvidenceBundle,
  buildTrueMomentumPreviewEvidenceJson,
  buildTrueMomentumPreviewEvidenceMarkdown,
  computeMomentumQueueSignature,
  partitionTrueMomentumPreviewEvidenceByFamily,
  sanitizeTrueMomentumPreviewEvidenceNote,
  summarizeTrueMomentumPreviewEvidence,
  topTrueMomentumPreviewEvidence,
  TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE,
  TRUE_MOMENTUM_PREVIEW_EVIDENCE_PHASE,
  TRUE_MOMENTUM_PREVIEW_EVIDENCE_SCHEMA_VERSION,
  trueMomentumPreviewEvidenceTagLabel,
  trueMomentumPreviewEvidenceTagTone,
  trueMomentumPreviewEvidenceWarnings,
  validateTrueMomentumPreviewEvidenceBundle,
} from "@/lib/true-momentum-preview-evidence";
import { buildTrueMomentumStrategyPreview } from "@/lib/true-momentum-strategy-preview";
import { buildMomentumTrialSnapshot } from "@/lib/momentum-trial-journal";
import { buildMomentumTrialOutcomeReview } from "@/lib/momentum-trial-outcomes";
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

const MIXED_QUEUE: QueueCandidate[] = [
  candidate({ rank: 1, symbol: "XLK" }),
  candidate({
    rank: 2,
    symbol: "IWM",
    strategy: "Pullback / Trend Continuation",
    momentum_contribution: contribution({
      pullback_signal: true,
      reason_codes: ["thinkorswim_parity_pending"],
    }),
  }),
  candidate({
    rank: 3,
    symbol: "BAD",
    momentum_contribution: contribution({
      no_trade_warning: true,
      reason_codes: ["momentum_no_trade_warning", "derived_higher_timeframe"],
    }),
  }),
];

const PREVIEW_RESULT = buildTrueMomentumStrategyPreview(MIXED_QUEUE, status());

describe("trueMomentumPreviewEvidenceTagLabel + tone", () => {
  it("labels each review tag", () => {
    expect(trueMomentumPreviewEvidenceTagLabel("research_candidate")).toBe(
      "Research candidate",
    );
    expect(trueMomentumPreviewEvidenceTagLabel("watchlist_only")).toBe("Watchlist only");
    expect(trueMomentumPreviewEvidenceTagLabel("needs_tos_parity_check")).toBe(
      "Needs ToS parity check",
    );
    expect(trueMomentumPreviewEvidenceTagLabel("needs_b8_outcome_evidence")).toBe(
      "Needs B8 outcome evidence",
    );
    expect(trueMomentumPreviewEvidenceTagLabel("too_noisy")).toBe("Too noisy");
    expect(trueMomentumPreviewEvidenceTagLabel("defer")).toBe("Defer");
    expect(trueMomentumPreviewEvidenceTagLabel(null)).toBe("—");
  });

  it("returns expected tones", () => {
    expect(trueMomentumPreviewEvidenceTagTone("research_candidate")).toBe("good");
    expect(trueMomentumPreviewEvidenceTagTone("watchlist_only")).toBe("neutral");
    expect(trueMomentumPreviewEvidenceTagTone("needs_tos_parity_check")).toBe("warn");
    expect(trueMomentumPreviewEvidenceTagTone("too_noisy")).toBe("warn");
    expect(trueMomentumPreviewEvidenceTagTone(null)).toBe("neutral");
  });
});

describe("sanitizeTrueMomentumPreviewEvidenceNote", () => {
  it("trims + collapses whitespace and length-caps", () => {
    expect(sanitizeTrueMomentumPreviewEvidenceNote("  a    b  ")).toBe("a b");
    expect(sanitizeTrueMomentumPreviewEvidenceNote(null)).toBe("");
    expect(
      sanitizeTrueMomentumPreviewEvidenceNote("x".repeat(2000)).length,
    ).toBeLessThanOrEqual(1200);
  });

  it("redacts forbidden trade-action language", () => {
    const cleaned = sanitizeTrueMomentumPreviewEvidenceNote(
      "buy now XLK because Momentum is strong",
    );
    expect(cleaned.toLowerCase()).not.toContain("buy now");
    expect(cleaned).toContain("[redacted]");
  });
});

describe("buildTrueMomentumPreviewEvidenceBundle", () => {
  it("builds a bundle from the C1 preview result + queue candidates", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      evaluatedUniverse: ["XLK", "IWM", "BAD", "DIA"],
      rankingMode: "research_preview",
      activeDeltaScale: 0.35,
    });
    expect(bundle.schema_version).toBe(TRUE_MOMENTUM_PREVIEW_EVIDENCE_SCHEMA_VERSION);
    expect(bundle.preview_phase).toBe(TRUE_MOMENTUM_PREVIEW_EVIDENCE_PHASE);
    expect(bundle.deterministic_note).toBe(
      TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE,
    );
    expect(bundle.candidate_count).toBe(3);
    expect(bundle.preview_count).toBeGreaterThan(0);
    expect(bundle.continuation_count).toBe(1); // XLK
    expect(bundle.pullback_count).toBe(1); // IWM
    expect(bundle.reversal_watch_count).toBe(1); // BAD
    expect(bundle.universe_kind).toBe("evaluated");
    expect(bundle.evaluated_universe).toContain("DIA");
    expect(bundle.active_delta_scale).toBe(0.35);
    expect(bundle.ranking_mode).toBe("research_preview");
  });

  it("counts parity-pending and derived-HTF caveats per row + per summary", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    expect(bundle.parity_pending_count).toBe(1);
    expect(bundle.derived_higher_timeframe_count).toBe(1);
  });

  it("falls back to captured-symbols universe when none is provided", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    expect(bundle.universe_kind).toBe("captured");
    expect(bundle.evaluated_universe).toEqual(["XLK", "IWM", "BAD"]);
  });

  it("preview candidates carry baseline / active / raw / applied score fields", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    const xlk = bundle.preview_candidates.find((c) => c.symbol === "XLK")!;
    expect(xlk.baseline_score).toBeGreaterThan(0);
    expect(xlk.active_score).toBeGreaterThan(0);
    expect(xlk.raw_contribution).toBeGreaterThan(0);
    expect(xlk.applied_delta).toBeGreaterThan(0);
    expect(xlk.non_actionable).toBe(true);
    expect(xlk.family_id).toBe("true_momentum_continuation");
  });

  it("never emits NaN/Infinity in JSON serialization", () => {
    const broken = candidate({
      symbol: "BRK",
      score: Number.NaN,
      score_before_momentum: Number.NaN,
      momentum_contribution: contribution({
        applied_score_delta: Number.NaN,
        raw_total_contribution: Number.NaN,
        total_score: Number.NaN,
        trend_score: Number.NaN,
        momo_score: Number.NaN,
      }),
    } as Partial<QueueCandidate>);
    const previewResult = buildTrueMomentumStrategyPreview([broken], status());
    const bundle = buildTrueMomentumPreviewEvidenceBundle(previewResult, {
      queueCandidates: [broken],
    });
    const json = buildTrueMomentumPreviewEvidenceJson(bundle);
    expect(json).not.toMatch(/\bNaN\b/);
    expect(json).not.toMatch(/\bInfinity\b/);
  });

  it("missing previewResult degrades gracefully", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(null, {
      queueCandidates: MIXED_QUEUE,
    });
    expect(bundle.preview_count).toBe(0);
    expect(bundle.preview_candidates).toEqual([]);
    expect(bundle.candidate_count).toBe(3);
  });

  it("threads through B8 snapshot/outcome presence flags", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      b8Snapshot: { schema_version: "phase_b7_1.v1" } as never,
      b8OutcomeReview: { schema_version: "phase_b8.v1" } as never,
    });
    expect(bundle.b8_snapshot_present).toBe(true);
    expect(bundle.b8_outcome_review_present).toBe(true);
  });

  it("sanitizes operator-supplied global conclusion + family notes", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      operatorReview: {
        global_conclusion: "buy now XLK because Momentum is strong",
        family_notes: {
          true_momentum_continuation: "clean continuation",
          true_momentum_pullback: "watch for sell now",
          true_momentum_reversal_watch: "noisy",
        },
        candidate_notes: [
          {
            preview_id: "preview::true_momentum_continuation::XLK::Event Continuation::1",
            symbol: "XLK",
            text: "route order for follow-through",
            tag: "research_candidate",
          },
        ],
        review_tags: ["research_candidate", "needs_tos_parity_check"],
      },
    });
    expect(bundle.operator_review.global_conclusion.toLowerCase()).not.toContain("buy now");
    expect(bundle.operator_review.family_notes.true_momentum_pullback.toLowerCase()).not.toContain("sell now");
    expect(bundle.operator_review.candidate_notes[0].text.toLowerCase()).not.toContain("route order");
    expect(bundle.operator_review.review_tags).toEqual([
      "research_candidate",
      "needs_tos_parity_check",
    ]);
  });
});

describe("summarize + partition + top helpers", () => {
  it("summarizes per-family + per-caveat counts", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    const summary = summarizeTrueMomentumPreviewEvidence(bundle);
    expect(summary.preview_count).toBe(bundle.preview_count);
    expect(summary.continuation_count).toBe(1);
    expect(summary.pullback_count).toBe(1);
    expect(summary.reversal_watch_count).toBe(1);
    expect(summary.parity_pending_count).toBe(1);
  });

  it("partitions preview candidates by family id", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    const partition = partitionTrueMomentumPreviewEvidenceByFamily(bundle);
    expect(partition.true_momentum_continuation.map((c) => c.symbol)).toEqual(["XLK"]);
    expect(partition.true_momentum_pullback.map((c) => c.symbol)).toEqual(["IWM"]);
    expect(partition.true_momentum_reversal_watch.map((c) => c.symbol)).toEqual(["BAD"]);
  });

  it("topTrueMomentumPreviewEvidence orders strong before moderate/watch", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    const top = topTrueMomentumPreviewEvidence(bundle);
    expect(top[0].match_strength).toBe("strong");
  });

  it("trueMomentumPreviewEvidenceWarnings returns trade warnings only", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    const bad = bundle.preview_candidates.find((c) => c.symbol === "BAD")!;
    const warnings = trueMomentumPreviewEvidenceWarnings(bad);
    expect(warnings).toContain("no_trade_warning");
  });
});

describe("Markdown + JSON exports", () => {
  it("Markdown includes family sections, summary, remaining caveats, and deterministic note", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      evaluatedUniverse: ["XLK", "IWM", "BAD"],
      operatorReview: {
        global_conclusion: "XLK clean continuation, IWM still watchlist only.",
        family_notes: {
          true_momentum_continuation: "Continuation row tracked well",
          true_momentum_pullback: "",
          true_momentum_reversal_watch: "",
        },
      },
    });
    const md = buildTrueMomentumPreviewEvidenceMarkdown(bundle);
    expect(md).toContain("# True Momentum Preview Evidence Bundle");
    expect(md).toContain("## Summary");
    expect(md).toContain("- Continuation: 1");
    expect(md).toContain("## Preview families");
    expect(md).toContain("### True Momentum Continuation");
    expect(md).toContain("### True Momentum Pullback");
    expect(md).toContain("### True Momentum Reversal / Weakening Watch");
    expect(md).toContain("## Operator review");
    expect(md).toContain("XLK clean continuation, IWM still watchlist only.");
    expect(md).toContain("## Remaining caveats");
    expect(md).toContain("Active Phase C True Momentum strategy families are not implemented");
    expect(md).toContain(TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE);
  });

  it("Markdown labels Evaluated universe / Captured symbols correctly", () => {
    const captured = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    const evaluated = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      evaluatedUniverse: ["XLK", "IWM", "BAD", "QQQ"],
    });
    expect(buildTrueMomentumPreviewEvidenceMarkdown(captured)).toContain("- Captured symbols:");
    expect(buildTrueMomentumPreviewEvidenceMarkdown(evaluated)).toContain("- Evaluated universe:");
  });

  it("JSON export is parseable with schema_version + deterministic_note", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    const json = buildTrueMomentumPreviewEvidenceJson(bundle);
    const parsed = JSON.parse(json);
    expect(parsed.schema_version).toBe(TRUE_MOMENTUM_PREVIEW_EVIDENCE_SCHEMA_VERSION);
    expect(parsed.deterministic_note).toBe(
      TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE,
    );
    expect(parsed.bundle.preview_candidates.length).toBe(bundle.preview_count);
  });

  it("Markdown and JSON never include forbidden trade-action language", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      operatorReview: {
        global_conclusion: "regular review notes",
        family_notes: {
          true_momentum_continuation: "tracked well",
          true_momentum_pullback: "watchlist only",
          true_momentum_reversal_watch: "noisy",
        },
      },
    });
    const md = buildTrueMomentumPreviewEvidenceMarkdown(bundle).toLowerCase();
    const json = buildTrueMomentumPreviewEvidenceJson(bundle).toLowerCase();
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

describe("Phase C2.1 — computeMomentumQueueSignature", () => {
  it("returns a stable sorted signature for the queue rows", () => {
    const a = computeMomentumQueueSignature(MIXED_QUEUE);
    const reordered = [...MIXED_QUEUE].reverse();
    const b = computeMomentumQueueSignature(reordered);
    expect(a).toBe(b);
    expect(a).toContain("XLK");
    expect(a).toContain("IWM");
  });

  it("returns 'empty' for null/empty inputs", () => {
    expect(computeMomentumQueueSignature(null)).toBe("empty");
    expect(computeMomentumQueueSignature([])).toBe("empty");
  });

  it("degrades safely when fields are missing", () => {
    const sig = computeMomentumQueueSignature([
      { symbol: "XLK" } as never,
      { strategy: "Event Continuation", rank: 2 } as never,
    ]);
    expect(sig.length).toBeGreaterThan(0);
  });
});

describe("Phase C2.1 — B8 snapshot link status", () => {
  it("status missing when no snapshot is provided", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    expect(bundle.b8_snapshot_link_status).toBe("missing");
    expect(bundle.b8_snapshot_linked).toBe(false);
    expect(bundle.b8_snapshot_generated_at).toBeNull();
    expect(bundle.b8_snapshot_candidate_count).toBeNull();
  });

  it("status linked when snapshot signature matches the live queue", () => {
    const snapshot = buildMomentumTrialSnapshot(MIXED_QUEUE);
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      b8Snapshot: snapshot,
    });
    expect(bundle.b8_snapshot_link_status).toBe("linked");
    expect(bundle.b8_snapshot_linked).toBe(true);
    expect(bundle.b8_snapshot_generated_at).toBe(snapshot.generated_at);
    expect(bundle.b8_snapshot_candidate_count).toBe(MIXED_QUEUE.length);
    expect(bundle.linked_b8_snapshot_schema_version).toBe("phase_b7_1.v1");
  });

  it("status mismatch when snapshot signature differs from the live queue", () => {
    const otherQueue: QueueCandidate[] = [
      candidate({ rank: 1, symbol: "XLE" }),
      candidate({ rank: 2, symbol: "XLF" }),
    ];
    const snapshot = buildMomentumTrialSnapshot(otherQueue);
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      b8Snapshot: snapshot,
    });
    expect(bundle.b8_snapshot_link_status).toBe("mismatch");
    expect(bundle.b8_snapshot_linked).toBe(false);
    expect(bundle.b8_link_warning).not.toBeNull();
    expect((bundle.b8_link_warning ?? "").toLowerCase()).toContain("different queue");
  });
});

describe("Phase C2.1 — B8 outcome review link status", () => {
  it("status partial when all outcomes remain unclear", () => {
    const snapshot = buildMomentumTrialSnapshot(MIXED_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot);
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      b8Snapshot: snapshot,
      b8OutcomeReview: review,
    });
    expect(bundle.b8_outcome_review_link_status).toBe("partial");
    expect(bundle.b8_outcome_review_linked).toBe(true);
    expect(bundle.b8_outcome_reviewed_count).toBeGreaterThan(0);
    expect(bundle.b8_link_warning?.toLowerCase()).toContain("most outcomes are still unclear");
  });

  it("status linked when at least one outcome is tagged beyond unclear", () => {
    const snapshot = buildMomentumTrialSnapshot(MIXED_QUEUE);
    const defaults = buildMomentumTrialOutcomeReview(snapshot).candidate_outcomes;
    const tagged = defaults.map((row, idx) =>
      idx === 0 ? { ...row, tag: "worked" as const } : row,
    );
    const review = buildMomentumTrialOutcomeReview(snapshot, {
      existingOutcomes: tagged,
    });
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      b8Snapshot: snapshot,
      b8OutcomeReview: review,
    });
    expect(bundle.b8_outcome_review_link_status).toBe("linked");
    expect(bundle.b8_outcome_summary?.worked_count).toBe(1);
    expect(bundle.b8_outcome_summary?.candidate_count).toBe(defaults.length);
  });

  it("status mismatch when outcome review's snapshot differs from current queue", () => {
    const otherQueue: QueueCandidate[] = [
      candidate({ rank: 1, symbol: "XLE" }),
      candidate({ rank: 2, symbol: "XLF" }),
    ];
    const otherSnapshot = buildMomentumTrialSnapshot(otherQueue);
    const review = buildMomentumTrialOutcomeReview(otherSnapshot);
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      b8OutcomeReview: review,
    });
    expect(bundle.b8_outcome_review_link_status).toBe("mismatch");
    expect(bundle.b8_outcome_review_linked).toBe(false);
    expect(bundle.b8_link_warning?.toLowerCase()).toContain("different queue");
  });

  it("snapshot linked but outcome missing emits a friendly warning", () => {
    const snapshot = buildMomentumTrialSnapshot(MIXED_QUEUE);
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      b8Snapshot: snapshot,
    });
    expect(bundle.b8_snapshot_link_status).toBe("linked");
    expect(bundle.b8_outcome_review_link_status).toBe("missing");
    expect(bundle.b8_link_warning?.toLowerCase()).toContain("no outcome review");
  });
});

describe("Phase C2.1 — exports include linked B8 metadata", () => {
  it("Markdown export emits a Linked B8 Trial Evidence section with timestamps and counts", () => {
    const snapshot = buildMomentumTrialSnapshot(MIXED_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot, {
      existingOutcomes: snapshot.candidates.slice(0, 1).map((c) => ({
        symbol: c.symbol,
        strategy: c.strategy,
        rank: c.rank,
        tag: "worked" as const,
        note: "",
      })),
    });
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      b8Snapshot: snapshot,
      b8OutcomeReview: review,
    });
    const md = buildTrueMomentumPreviewEvidenceMarkdown(bundle);
    expect(md).toContain("## Linked B8 Trial Evidence");
    expect(md).toContain("- B8 snapshot: linked");
    expect(md).toContain("- B8 outcome review: linked");
    expect(md).toContain(snapshot.generated_at);
    expect(md).toContain("Outcome counts");
  });

  it("Markdown export says 'missing' when no B8 snapshot/review is linked", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    const md = buildTrueMomentumPreviewEvidenceMarkdown(bundle);
    expect(md).toContain("## Linked B8 Trial Evidence");
    expect(md).toContain("- B8 snapshot: missing");
    expect(md).toContain("- B8 outcome review: missing");
  });

  it("JSON export carries the new B8 link fields", () => {
    const snapshot = buildMomentumTrialSnapshot(MIXED_QUEUE);
    const review = buildMomentumTrialOutcomeReview(snapshot);
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
      b8Snapshot: snapshot,
      b8OutcomeReview: review,
    });
    const json = buildTrueMomentumPreviewEvidenceJson(bundle);
    const parsed = JSON.parse(json);
    expect(parsed.bundle.b8_snapshot_link_status).toBe("linked");
    expect(parsed.bundle.b8_outcome_review_link_status).toBe("partial");
    expect(parsed.bundle.b8_snapshot_generated_at).toBe(snapshot.generated_at);
    expect(parsed.bundle.linked_b8_snapshot_schema_version).toBe(
      "phase_b7_1.v1",
    );
    expect(parsed.bundle.b8_outcome_summary).not.toBeNull();
    expect(parsed.bundle.b8_link_warning).not.toBeNull();
  });

  it("summarize exposes link status + warning", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    const summary = summarizeTrueMomentumPreviewEvidence(bundle);
    expect(summary.b8_snapshot_link_status).toBe("missing");
    expect(summary.b8_outcome_review_link_status).toBe("missing");
    expect(summary.b8_snapshot_linked).toBe(false);
    expect(summary.b8_outcome_review_linked).toBe(false);
  });
});

describe("validateTrueMomentumPreviewEvidenceBundle", () => {
  it("accepts a freshly built bundle", () => {
    const bundle = buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
      queueCandidates: MIXED_QUEUE,
    });
    const result = validateTrueMomentumPreviewEvidenceBundle(bundle);
    expect(result.ok).toBe(true);
  });

  it("rejects malformed bundles", () => {
    expect(validateTrueMomentumPreviewEvidenceBundle(null).ok).toBe(false);
    expect(validateTrueMomentumPreviewEvidenceBundle("nope").ok).toBe(false);
    expect(
      validateTrueMomentumPreviewEvidenceBundle({ schema_version: "wrong" }).ok,
    ).toBe(false);
  });
});
