import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  addTrueMomentumCohortRecord,
  buildTrueMomentumCohortJson,
  buildTrueMomentumCohortMarkdown,
  buildTrueMomentumCohortRecord,
  buildTrueMomentumCohortReviewReport,
  classifyTrueMomentumCohortReadiness,
  cohortArchiveContainsRecordId,
  emptyCohortArchive,
  readTrueMomentumCohortArchiveFromStorage,
  removeTrueMomentumCohortRecord,
  replaceTrueMomentumCohortRecord,
  sanitizeTrueMomentumCohortNote,
  summarizeTrueMomentumCohortArchive,
  summarizeTrueMomentumFamilyCohort,
  TRUE_MOMENTUM_COHORT_ARCHIVE_SCHEMA_VERSION,
  TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE,
  TRUE_MOMENTUM_COHORT_STORAGE_KEY,
  trueMomentumCohortReadinessLabel,
  trueMomentumCohortReadinessTone,
  validateTrueMomentumCohortArchive,
  writeTrueMomentumCohortArchiveToStorage,
  type TrueMomentumCohortArchive,
  type TrueMomentumCohortRecord,
} from "@/lib/true-momentum-cohort-review";
import type { TrueMomentumPreviewEvidenceBundle } from "@/lib/true-momentum-preview-evidence";

function bundle(
  overrides: Partial<TrueMomentumPreviewEvidenceBundle> = {},
): TrueMomentumPreviewEvidenceBundle {
  const generated = overrides.generated_at ?? "2026-05-12T12:00:00Z";
  return {
    schema_version: "phase_c2.v1",
    generated_at: generated,
    preview_phase: "C2",
    implementation_status: "research_preview_evidence",
    ranking_mode: "research_preview",
    active_delta_scale: 0.35,
    evaluated_universe: ["XLK", "IWM", "QQQ"],
    universe_kind: "evaluated",
    candidate_count: 3,
    preview_count: 3,
    family_counts: {
      continuation_count: 1,
      pullback_count: 1,
      reversal_watch_count: 1,
    },
    continuation_count: 1,
    pullback_count: 1,
    reversal_watch_count: 1,
    parity_pending_count: 0,
    derived_higher_timeframe_count: 0,
    trade_warning_count: 0,
    operational_caveat_count: 0,
    score_consistency_corrected_count: 0,
    b8_snapshot_present: true,
    b8_outcome_review_present: true,
    b8_snapshot_linked: true,
    b8_outcome_review_linked: true,
    b8_snapshot_link_status: "linked",
    b8_outcome_review_link_status: "linked",
    b8_snapshot_generated_at: "2026-05-12T11:59:00Z",
    b8_outcome_generated_at: "2026-05-12T11:59:30Z",
    b8_snapshot_candidate_count: 3,
    b8_outcome_reviewed_count: 3,
    b8_outcome_summary: {
      candidate_count: 3,
      worked_count: 1,
      missed_count: 0,
      too_aggressive_count: 0,
      good_warning_count: 0,
      false_warning_count: 0,
      watchlist_only_count: 0,
      needs_tos_parity_check_count: 0,
      ignored_count: 0,
      unclear_count: 2,
    },
    linked_b8_snapshot_schema_version: "phase_b7_1.v1",
    linked_b8_outcome_schema_version: "phase_b8.v1",
    b8_link_warning: null,
    family_summaries: [],
    preview_candidates: [
      {
        preview_id: "preview::true_momentum_continuation::XLK::Event Continuation::1",
        family_id: "true_momentum_continuation",
        family_label: "True Momentum Continuation",
        rank: 1,
        symbol: "XLK",
        current_strategy: "Event Continuation",
        baseline_score: 0.88,
        active_score: 0.95,
        raw_contribution: 20,
        applied_delta: 0.07,
        total_score: 85,
        total_label: "Bull",
        trend_score: 78,
        momo_score: 72,
        match_strength: "strong",
        inferred_direction: "long",
        pullback_signal: false,
        reversal_warning: false,
        no_trade_warning: false,
        reason_codes: ["true_momentum_continuation_match"],
        operational_caveats: [],
        trade_warnings: [],
        non_actionable: true,
      },
      {
        preview_id: "preview::true_momentum_pullback::IWM::Pullback / Trend Continuation::2",
        family_id: "true_momentum_pullback",
        family_label: "True Momentum Pullback",
        rank: 2,
        symbol: "IWM",
        current_strategy: "Pullback / Trend Continuation",
        baseline_score: 0.88,
        active_score: 0.95,
        raw_contribution: 20,
        applied_delta: 0.07,
        total_score: 82,
        total_label: "Bull",
        trend_score: 72,
        momo_score: 72,
        match_strength: "strong",
        inferred_direction: "long",
        pullback_signal: true,
        reversal_warning: false,
        no_trade_warning: false,
        reason_codes: ["true_momentum_pullback_match"],
        operational_caveats: [],
        trade_warnings: [],
        non_actionable: true,
      },
      {
        preview_id: "preview::true_momentum_reversal_watch::BAD::Event Continuation::3",
        family_id: "true_momentum_reversal_watch",
        family_label: "True Momentum Reversal / Weakening Watch",
        rank: 3,
        symbol: "BAD",
        current_strategy: "Event Continuation",
        baseline_score: 0.88,
        active_score: 0.95,
        raw_contribution: 20,
        applied_delta: 0.07,
        total_score: 85,
        total_label: "Bull",
        trend_score: 78,
        momo_score: 72,
        match_strength: "watch",
        inferred_direction: "long",
        pullback_signal: false,
        reversal_warning: false,
        no_trade_warning: true,
        reason_codes: ["true_momentum_reversal_watch_match"],
        operational_caveats: [],
        trade_warnings: ["no_trade_warning"],
        non_actionable: true,
      },
    ],
    operator_review: {
      global_conclusion: "",
      family_notes: {
        true_momentum_continuation: "",
        true_momentum_pullback: "",
        true_momentum_reversal_watch: "",
      },
      candidate_notes: [],
      review_tags: ["research_candidate"],
      authored_at: generated,
    },
    deterministic_note:
      "True Momentum preview evidence is research-only. It does not generate queue candidates, approve, reject, size, or route trades.",
    ...overrides,
  };
}

describe("readiness labels + tones", () => {
  it("labels every readiness status", () => {
    expect(trueMomentumCohortReadinessLabel("insufficient_evidence")).toBe(
      "Insufficient evidence",
    );
    expect(trueMomentumCohortReadinessLabel("parity_blocked")).toBe("Parity blocked");
    expect(trueMomentumCohortReadinessLabel("promising_research")).toBe(
      "Promising research",
    );
    expect(trueMomentumCohortReadinessLabel("mixed_research")).toBe("Mixed research");
    expect(trueMomentumCohortReadinessLabel("needs_operator_review")).toBe(
      "Needs operator review",
    );
    expect(trueMomentumCohortReadinessLabel("not_recommended_for_activation")).toBe(
      "Not recommended for activation",
    );
    expect(trueMomentumCohortReadinessLabel(null)).toBe("Insufficient evidence");
  });

  it("returns expected tones", () => {
    expect(trueMomentumCohortReadinessTone("promising_research")).toBe("good");
    expect(trueMomentumCohortReadinessTone("parity_blocked")).toBe("warn");
    expect(trueMomentumCohortReadinessTone("not_recommended_for_activation")).toBe(
      "bad",
    );
    expect(trueMomentumCohortReadinessTone("insufficient_evidence")).toBe("neutral");
  });
});

describe("sanitizeTrueMomentumCohortNote", () => {
  it("redacts forbidden action language", () => {
    const cleaned = sanitizeTrueMomentumCohortNote("operator says buy now XLK");
    expect(cleaned.toLowerCase()).not.toContain("buy now");
    expect(cleaned).toContain("[redacted]");
  });

  it("returns empty string for null/undefined", () => {
    expect(sanitizeTrueMomentumCohortNote(null)).toBe("");
    expect(sanitizeTrueMomentumCohortNote(undefined)).toBe("");
  });
});

describe("buildTrueMomentumCohortRecord", () => {
  it("returns null for null/undefined bundle", () => {
    expect(buildTrueMomentumCohortRecord(null)).toBeNull();
    expect(buildTrueMomentumCohortRecord(undefined)).toBeNull();
  });

  it("derives a stable record_id from queue signature + generated_at", () => {
    const a = buildTrueMomentumCohortRecord(bundle())!;
    const b = buildTrueMomentumCohortRecord(bundle())!;
    expect(a.record_id).toBe(b.record_id);
    expect(a.record_id).toContain("2026-05-12T12:00:00Z");
  });

  it("partitions preview candidates into family-specific arrays", () => {
    const record = buildTrueMomentumCohortRecord(bundle())!;
    expect(record.continuation_candidates.length).toBe(1);
    expect(record.pullback_candidates.length).toBe(1);
    expect(record.reversal_watch_candidates.length).toBe(1);
    expect(record.continuation_candidates[0].symbol).toBe("XLK");
  });

  it("copies the B8 outcome summary verbatim", () => {
    const record = buildTrueMomentumCohortRecord(bundle())!;
    expect(record.b8_outcome_summary?.worked_count).toBe(1);
    expect(record.b8_outcome_summary?.unclear_count).toBe(2);
  });
});

describe("archive mutators", () => {
  it("addTrueMomentumCohortRecord dedupes by record_id and never mutates the input", () => {
    const archive = emptyCohortArchive();
    const record = buildTrueMomentumCohortRecord(bundle())!;
    const first = addTrueMomentumCohortRecord(archive, record);
    const second = addTrueMomentumCohortRecord(first, record);
    expect(first.records.length).toBe(1);
    expect(second.records.length).toBe(1);
    // The original input archive is untouched.
    expect(archive.records.length).toBe(0);
  });

  it("removeTrueMomentumCohortRecord removes by record_id only", () => {
    const archive = emptyCohortArchive();
    const r1 = buildTrueMomentumCohortRecord(bundle({ generated_at: "2026-05-12T12:00:00Z" }))!;
    const r2 = buildTrueMomentumCohortRecord(bundle({ generated_at: "2026-05-12T13:00:00Z" }))!;
    const populated = addTrueMomentumCohortRecord(
      addTrueMomentumCohortRecord(archive, r1),
      r2,
    );
    const removed = removeTrueMomentumCohortRecord(populated, r1.record_id);
    expect(removed.records.length).toBe(1);
    expect(removed.records[0].record_id).toBe(r2.record_id);
    // The populated archive is unchanged.
    expect(populated.records.length).toBe(2);
  });

  it("replaceTrueMomentumCohortRecord updates by record_id or appends", () => {
    const archive = emptyCohortArchive();
    const r1 = buildTrueMomentumCohortRecord(bundle())!;
    const populated = addTrueMomentumCohortRecord(archive, r1);
    const r1Updated = { ...r1, preview_count: 99 };
    const replaced = replaceTrueMomentumCohortRecord(populated, r1Updated);
    expect(replaced.records.length).toBe(1);
    expect(replaced.records[0].preview_count).toBe(99);
  });

  it("cohortArchiveContainsRecordId is true for an archived record_id", () => {
    const record = buildTrueMomentumCohortRecord(bundle())!;
    const archive = addTrueMomentumCohortRecord(emptyCohortArchive(), record);
    expect(cohortArchiveContainsRecordId(archive, record.record_id)).toBe(true);
    expect(cohortArchiveContainsRecordId(archive, "garbage")).toBe(false);
    expect(cohortArchiveContainsRecordId(null, record.record_id)).toBe(false);
  });
});

describe("summarizeTrueMomentumCohortArchive", () => {
  it("returns zeros for an empty archive", () => {
    const summary = summarizeTrueMomentumCohortArchive(emptyCohortArchive());
    expect(summary.record_count).toBe(0);
    expect(summary.total_preview_count).toBe(0);
    expect(summary.outcome_counts.worked_count).toBe(0);
    expect(summary.family_summaries.length).toBe(3);
  });

  it("aggregates family + outcome counts across records", () => {
    let archive = emptyCohortArchive();
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(bundle({ generated_at: "t1" }))!,
    );
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(bundle({ generated_at: "t2" }))!,
    );
    const summary = summarizeTrueMomentumCohortArchive(archive);
    expect(summary.record_count).toBe(2);
    expect(summary.continuation_count).toBe(2);
    expect(summary.pullback_count).toBe(2);
    expect(summary.reversal_watch_count).toBe(2);
    expect(summary.outcome_counts.worked_count).toBe(2);
    expect(summary.outcome_counts.unclear_count).toBe(4);
    expect(summary.records_with_outcome_review).toBe(2);
  });

  it("flags parity_pending_records for records with parity-pending counts", () => {
    let archive = emptyCohortArchive();
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(
        bundle({ generated_at: "t1", parity_pending_count: 2 }),
      )!,
    );
    const summary = summarizeTrueMomentumCohortArchive(archive);
    expect(summary.parity_pending_records).toBe(1);
  });

  it("summarizeTrueMomentumFamilyCohort returns per-family rollups", () => {
    let archive = emptyCohortArchive();
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(bundle())!,
    );
    const family = summarizeTrueMomentumFamilyCohort(archive, "true_momentum_continuation");
    expect(family.preview_count).toBe(1);
    expect(family.strong_count).toBe(1);
  });
});

describe("classifyTrueMomentumCohortReadiness", () => {
  it("returns insufficient_evidence for empty / null summaries", () => {
    expect(classifyTrueMomentumCohortReadiness(null).status).toBe(
      "insufficient_evidence",
    );
    expect(
      classifyTrueMomentumCohortReadiness(
        summarizeTrueMomentumCohortArchive(emptyCohortArchive()),
      ).status,
    ).toBe("insufficient_evidence");
  });

  it("returns parity_blocked when parity is pending across most records", () => {
    let archive = emptyCohortArchive();
    for (let i = 0; i < 4; i += 1) {
      archive = addTrueMomentumCohortRecord(
        archive,
        buildTrueMomentumCohortRecord(
          bundle({ generated_at: `t${i}`, parity_pending_count: 3 }),
        )!,
      );
    }
    const summary = summarizeTrueMomentumCohortArchive(archive);
    const { status, caveats } = classifyTrueMomentumCohortReadiness(summary);
    expect(status).toBe("parity_blocked");
    expect(caveats.join(" ").toLowerCase()).toContain("parity");
  });

  it("returns insufficient_evidence when all outcomes are still unclear", () => {
    let archive = emptyCohortArchive();
    for (let i = 0; i < 4; i += 1) {
      archive = addTrueMomentumCohortRecord(
        archive,
        buildTrueMomentumCohortRecord(
          bundle({
            generated_at: `t${i}`,
            b8_outcome_summary: {
              candidate_count: 3,
              worked_count: 0,
              missed_count: 0,
              too_aggressive_count: 0,
              good_warning_count: 0,
              false_warning_count: 0,
              watchlist_only_count: 0,
              needs_tos_parity_check_count: 0,
              ignored_count: 0,
              unclear_count: 3,
            },
          }),
        )!,
      );
    }
    const summary = summarizeTrueMomentumCohortArchive(archive);
    expect(classifyTrueMomentumCohortReadiness(summary).status).toBe(
      "insufficient_evidence",
    );
  });

  it("returns not_recommended_for_activation when negatives ≥ 2× positives", () => {
    let archive = emptyCohortArchive();
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(
        bundle({
          generated_at: "neg",
          b8_outcome_summary: {
            candidate_count: 10,
            worked_count: 1,
            missed_count: 5,
            too_aggressive_count: 0,
            good_warning_count: 0,
            false_warning_count: 0,
            watchlist_only_count: 0,
            needs_tos_parity_check_count: 0,
            ignored_count: 0,
            unclear_count: 4,
          },
        }),
      )!,
    );
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(
        bundle({
          generated_at: "neg2",
          b8_outcome_summary: {
            candidate_count: 10,
            worked_count: 0,
            missed_count: 0,
            too_aggressive_count: 3,
            good_warning_count: 0,
            false_warning_count: 0,
            watchlist_only_count: 0,
            needs_tos_parity_check_count: 0,
            ignored_count: 0,
            unclear_count: 7,
          },
        }),
      )!,
    );
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(
        bundle({
          generated_at: "neg3",
          b8_outcome_summary: {
            candidate_count: 10,
            worked_count: 0,
            missed_count: 2,
            too_aggressive_count: 0,
            good_warning_count: 0,
            false_warning_count: 0,
            watchlist_only_count: 0,
            needs_tos_parity_check_count: 0,
            ignored_count: 0,
            unclear_count: 8,
          },
        }),
      )!,
    );
    const summary = summarizeTrueMomentumCohortArchive(archive);
    expect(classifyTrueMomentumCohortReadiness(summary).status).toBe(
      "not_recommended_for_activation",
    );
  });

  it("returns mixed_research / needs_operator_review based on outcome balance", () => {
    let archive = emptyCohortArchive();
    for (let i = 0; i < 3; i += 1) {
      archive = addTrueMomentumCohortRecord(
        archive,
        buildTrueMomentumCohortRecord(
          bundle({
            generated_at: `mixed-${i}`,
            b8_outcome_summary: {
              candidate_count: 6,
              worked_count: 2,
              missed_count: 2,
              too_aggressive_count: 0,
              good_warning_count: 0,
              false_warning_count: 0,
              watchlist_only_count: 0,
              needs_tos_parity_check_count: 0,
              ignored_count: 0,
              unclear_count: 2,
            },
          }),
        )!,
      );
    }
    const summary = summarizeTrueMomentumCohortArchive(archive);
    const result = classifyTrueMomentumCohortReadiness(summary);
    expect(result.status === "mixed_research" || result.status === "needs_operator_review").toBe(true);
  });

  it("never returns 'ready for live' / 'activate now' wording", () => {
    const allStatuses = [
      "insufficient_evidence",
      "parity_blocked",
      "promising_research",
      "mixed_research",
      "needs_operator_review",
      "not_recommended_for_activation",
    ];
    for (const status of allStatuses) {
      const label = trueMomentumCohortReadinessLabel(status).toLowerCase();
      expect(label).not.toContain("ready for live");
      expect(label).not.toContain("activate now");
    }
  });
});

describe("buildTrueMomentumCohortReviewReport + markdown / json exports", () => {
  it("exports a Markdown report with readiness + family + outcome sections", () => {
    let archive = emptyCohortArchive();
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(bundle())!,
    );
    const report = buildTrueMomentumCohortReviewReport(archive);
    const md = buildTrueMomentumCohortMarkdown(report);
    expect(md).toContain("# True Momentum Cohort Review (Phase C3)");
    expect(md).toContain("## Archive summary");
    expect(md).toContain("## Outcome counts");
    expect(md).toContain("## Family summaries");
    expect(md).toContain("## Archived records");
    expect(md).toContain("Pending prerequisites for any active Phase C");
    expect(md).toContain(TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE);
  });

  it("JSON export is parseable with schema_version + deterministic_note", () => {
    let archive = emptyCohortArchive();
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(bundle())!,
    );
    const report = buildTrueMomentumCohortReviewReport(archive);
    const json = buildTrueMomentumCohortJson(report);
    const parsed = JSON.parse(json);
    expect(parsed.schema_version).toBe("phase_c3.v1");
    expect(parsed.deterministic_note).toBe(TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE);
    expect(parsed.archive.records.length).toBe(1);
    expect(parsed.report.readiness).toBeDefined();
  });

  it("Markdown / JSON never contain forbidden action language", () => {
    let archive = emptyCohortArchive();
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(bundle())!,
    );
    const report = buildTrueMomentumCohortReviewReport(archive);
    const md = buildTrueMomentumCohortMarkdown(report).toLowerCase();
    const json = buildTrueMomentumCohortJson(report).toLowerCase();
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

  it("JSON export never contains NaN/Infinity", () => {
    let archive = emptyCohortArchive();
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(
        bundle({
          // Inject NaN/Inf into a couple of numeric fields to confirm
          // the cohort builder sanitizes them.
          active_delta_scale: Number.NaN,
          preview_count: Number.POSITIVE_INFINITY,
        }) as never,
      )!,
    );
    const report = buildTrueMomentumCohortReviewReport(archive);
    const json = buildTrueMomentumCohortJson(report);
    expect(json).not.toMatch(/\bNaN\b/);
    expect(json).not.toMatch(/\bInfinity\b/);
  });
});

describe("validateTrueMomentumCohortArchive", () => {
  it("accepts a freshly built archive", () => {
    const result = validateTrueMomentumCohortArchive(emptyCohortArchive());
    expect(result.ok).toBe(true);
  });

  it("rejects malformed inputs", () => {
    expect(validateTrueMomentumCohortArchive(null).ok).toBe(false);
    expect(validateTrueMomentumCohortArchive("nope").ok).toBe(false);
    expect(
      validateTrueMomentumCohortArchive({ schema_version: "wrong" }).ok,
    ).toBe(false);
    expect(
      validateTrueMomentumCohortArchive({
        schema_version: "phase_c3.v1",
        records: "not-an-array",
        created_at: "now",
      }).ok,
    ).toBe(false);
  });
});

describe("localStorage round-trip", () => {
  let originalWindow: unknown;
  beforeEach(() => {
    originalWindow = (globalThis as { window?: unknown }).window;
    const store = new Map<string, string>();
    (globalThis as { window?: unknown }).window = {
      localStorage: {
        getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
        setItem: (key: string, value: string) => {
          store.set(key, value);
        },
        removeItem: (key: string) => {
          store.delete(key);
        },
        clear: () => store.clear(),
      },
    };
  });

  afterEach(() => {
    (globalThis as { window?: unknown }).window = originalWindow;
  });

  it("returns null when nothing is persisted", () => {
    expect(readTrueMomentumCohortArchiveFromStorage()).toBeNull();
  });

  it("persists + reads back a valid archive", () => {
    let archive: TrueMomentumCohortArchive = emptyCohortArchive();
    archive = addTrueMomentumCohortRecord(
      archive,
      buildTrueMomentumCohortRecord(bundle())!,
    );
    writeTrueMomentumCohortArchiveToStorage(archive);
    const loaded = readTrueMomentumCohortArchiveFromStorage();
    expect(loaded).not.toBeNull();
    expect(loaded!.records.length).toBe(1);
    expect(loaded!.schema_version).toBe(TRUE_MOMENTUM_COHORT_ARCHIVE_SCHEMA_VERSION);
  });

  it("handles corrupt JSON safely", () => {
    (globalThis as { window?: { localStorage: Storage } }).window!.localStorage.setItem(
      TRUE_MOMENTUM_COHORT_STORAGE_KEY,
      "{not-json",
    );
    expect(readTrueMomentumCohortArchiveFromStorage()).toBeNull();
  });

  it("ignores archives with wrong schema_version", () => {
    (globalThis as { window?: { localStorage: Storage } }).window!.localStorage.setItem(
      TRUE_MOMENTUM_COHORT_STORAGE_KEY,
      JSON.stringify({ schema_version: "wrong", records: [] }),
    );
    expect(readTrueMomentumCohortArchiveFromStorage()).toBeNull();
  });
});
