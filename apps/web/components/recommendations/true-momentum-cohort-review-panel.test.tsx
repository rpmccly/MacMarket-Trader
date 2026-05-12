import React from "react";
import type { ReactNode } from "react";
import { createRequire } from "module";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/operator-ui", async () => {
  const ReactModule = await import("react");
  return {
    Card: ({ title, children }: { title?: string; children: ReactNode }) =>
      ReactModule.createElement(
        "section",
        {},
        title ? ReactModule.createElement("h3", {}, title) : null,
        children,
      ),
    EmptyState: ({ title, hint }: { title: string; hint: string }) =>
      ReactModule.createElement("div", { "data-testid": "empty" }, `${title} ${hint}`),
    ErrorState: ({ title, hint }: { title: string; hint: string }) =>
      ReactModule.createElement("div", { "data-testid": "error" }, `${title} ${hint}`),
    StatusBadge: ({
      tone,
      children,
      ...rest
    }: {
      tone?: string;
      children: ReactNode;
      [key: string]: unknown;
    }) =>
      ReactModule.createElement(
        "span",
        { className: `op-badge op-badge-${tone ?? "neutral"}`, ...rest },
        children,
      ),
  };
});

import { TrueMomentumCohortReviewPanel } from "@/components/recommendations/true-momentum-cohort-review-panel";
import {
  addTrueMomentumCohortRecord,
  buildTrueMomentumCohortRecord,
  emptyCohortArchive,
  TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE,
  type TrueMomentumCohortArchive,
} from "@/lib/true-momentum-cohort-review";
import type { TrueMomentumPreviewEvidenceBundle } from "@/lib/true-momentum-preview-evidence";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

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
    evaluated_universe: ["XLK"],
    universe_kind: "evaluated",
    candidate_count: 1,
    preview_count: 1,
    family_counts: { continuation_count: 1, pullback_count: 0, reversal_watch_count: 0 },
    continuation_count: 1,
    pullback_count: 0,
    reversal_watch_count: 0,
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
    b8_snapshot_candidate_count: 1,
    b8_outcome_reviewed_count: 1,
    b8_outcome_summary: {
      candidate_count: 1,
      worked_count: 1,
      missed_count: 0,
      too_aggressive_count: 0,
      good_warning_count: 0,
      false_warning_count: 0,
      watchlist_only_count: 0,
      needs_tos_parity_check_count: 0,
      ignored_count: 0,
      unclear_count: 0,
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

describe("TrueMomentumCohortReviewPanel — empty + populated render", () => {
  it("renders the empty-archive state when no records exist", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumCohortReviewPanel
        currentBundle={null}
        persistLatest={false}
      />,
    );
    expect(html).toContain("true-momentum-cohort-review");
    expect(html).toContain("0 archived sessions");
    expect(html).toContain("No archived sessions yet");
    expect(html).toContain(TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE);
  });

  it("renders the populated archive with summary cards, family lines, and a record table", () => {
    const record = buildTrueMomentumCohortRecord(bundle())!;
    const archive: TrueMomentumCohortArchive = addTrueMomentumCohortRecord(
      emptyCohortArchive(),
      record,
    );
    const html = renderToStaticMarkup(
      <TrueMomentumCohortReviewPanel
        currentBundle={bundle()}
        persistLatest={false}
        initialArchive={archive}
      />,
    );
    expect(html).toContain("1 archived session");
    expect(html).toContain("true-momentum-cohort-summary");
    expect(html).toContain("true-momentum-cohort-family-summaries");
    expect(html).toContain("true-momentum-cohort-table");
    expect(html).toContain("true-momentum-cohort-record-row");
    // Already-archived badge appears because currentBundle matches the
    // archived record.
    expect(html).toContain("true-momentum-cohort-already-archived");
    // Outcome counts include the worked tag.
    expect(html).toContain("Worked: 1");
  });

  it("renders the readiness badge with one of the documented statuses", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumCohortReviewPanel persistLatest={false} />,
    );
    expect(html).toContain("true-momentum-cohort-readiness-badge");
    expect(html).toContain("Readiness:");
  });

  it("Add / Clear / Export buttons render with the expected testids", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumCohortReviewPanel
        currentBundle={bundle()}
        persistLatest={false}
      />,
    );
    expect(html).toContain("true-momentum-cohort-add-current");
    expect(html).toContain("true-momentum-cohort-download-markdown");
    expect(html).toContain("true-momentum-cohort-download-json");
    expect(html).toContain("true-momentum-cohort-clear-archive");
  });

  it("disables the Add button when currentBundle is null", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumCohortReviewPanel currentBundle={null} persistLatest={false} />,
    );
    expect(html).toMatch(
      /<button[^>]*data-testid="true-momentum-cohort-add-current"[^>]*disabled/,
    );
  });

  it("never renders forbidden trade-action / approval / order-routing language", () => {
    const record = buildTrueMomentumCohortRecord(bundle())!;
    const archive = addTrueMomentumCohortRecord(emptyCohortArchive(), record);
    const html = renderToStaticMarkup(
      <TrueMomentumCohortReviewPanel
        currentBundle={bundle()}
        persistLatest={false}
        initialArchive={archive}
      />,
    ).toLowerCase();
    for (const phrase of [
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "auto approve",
      "route order",
      "approve trade",
      "promote to recommendation",
      "place order",
    ]) {
      expect(html).not.toContain(phrase);
    }
    // No affirmative queue-generation copy either.
    expect(html).not.toContain("generates queue candidates");
  });
});
