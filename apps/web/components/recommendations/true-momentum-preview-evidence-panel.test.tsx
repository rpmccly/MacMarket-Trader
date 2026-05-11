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
    StatusBadge: ({ tone, children }: { tone?: string; children: ReactNode }) =>
      ReactModule.createElement(
        "span",
        { className: `op-badge op-badge-${tone ?? "neutral"}` },
        children,
      ),
  };
});

import { TrueMomentumPreviewEvidencePanel } from "@/components/recommendations/true-momentum-preview-evidence-panel";
import {
  buildTrueMomentumPreviewEvidenceBundle,
  TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE,
  type TrueMomentumPreviewEvidenceBundle,
} from "@/lib/true-momentum-preview-evidence";
import { buildTrueMomentumStrategyPreview } from "@/lib/true-momentum-strategy-preview";
import type { TrueMomentumStrategyFamilyStatus } from "@/lib/true-momentum-strategy-families";
import type {
  MomentumRankingContribution,
  QueueCandidate,
} from "@/lib/recommendations";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

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
    momentum_contribution: contribution({ pullback_signal: true }),
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

const PREVIEW_RESULT = buildTrueMomentumStrategyPreview(MIXED_QUEUE, status());

const EMPTY_PREVIEW = buildTrueMomentumStrategyPreview([], status());

describe("TrueMomentumPreviewEvidencePanel — empty/disabled state", () => {
  it("renders the empty hint when no preview rows exist", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={[]}
        previewResult={EMPTY_PREVIEW}
        persistLatest={false}
      />,
    );
    expect(html).toContain("true-momentum-preview-evidence-empty");
    expect(html).toContain("No preview rows to capture.");
    expect(html).toContain(TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE);
  });

  it("renders the empty hint when previewResult is null", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={null}
        persistLatest={false}
      />,
    );
    expect(html).toContain("true-momentum-preview-evidence-empty");
  });
});

describe("TrueMomentumPreviewEvidencePanel — populated state", () => {
  it("renders summary cards and family sections", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={PREVIEW_RESULT}
        universeSymbols={["XLK", "IWM", "BAD", "QQQ"]}
        persistLatest={false}
      />,
    );
    expect(html).toContain("true-momentum-preview-evidence");
    expect(html).toContain("true-momentum-preview-evidence-summary");
    expect(html).toContain("true-momentum-preview-evidence-family-sections");
    expect(html).toContain("True Momentum Continuation (1)");
    expect(html).toContain("True Momentum Pullback (1)");
    expect(html).toContain("True Momentum Reversal / Weakening Watch (1)");
  });

  it("renders summary cards for B8 snapshot and outcome review links", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={PREVIEW_RESULT}
        persistLatest={false}
      />,
    );
    expect(html).toContain("B8 snapshot");
    expect(html).toContain("B8 outcome review");
  });

  it("renders the per-family operator note inputs", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={PREVIEW_RESULT}
        persistLatest={false}
      />,
    );
    expect(html).toContain('data-family-id="true_momentum_continuation"');
    expect(html).toContain('data-family-id="true_momentum_pullback"');
    expect(html).toContain('data-family-id="true_momentum_reversal_watch"');
    expect(html).toContain("true-momentum-preview-evidence-family-note");
  });

  it("renders preview rows in their family table with the correct data attributes", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={PREVIEW_RESULT}
        persistLatest={false}
      />,
    );
    expect(html).toContain('data-symbol="XLK"');
    expect(html).toContain('data-symbol="IWM"');
    expect(html).toContain('data-symbol="BAD"');
    expect(html).toContain('data-family-id="true_momentum_continuation"');
    expect(html).toContain('data-family-id="true_momentum_pullback"');
    expect(html).toContain('data-family-id="true_momentum_reversal_watch"');
  });

  it("renders capture / export / clear buttons", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={PREVIEW_RESULT}
        persistLatest={false}
      />,
    );
    expect(html).toContain("true-momentum-preview-evidence-capture");
    expect(html).toContain("true-momentum-preview-evidence-copy-markdown");
    expect(html).toContain("true-momentum-preview-evidence-download-markdown");
    expect(html).toContain("true-momentum-preview-evidence-download-json");
    expect(html).toContain("true-momentum-preview-evidence-clear");
  });

  it("renders the global conclusion textarea and review-tag buttons", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={PREVIEW_RESULT}
        persistLatest={false}
      />,
    );
    expect(html).toContain("true-momentum-preview-evidence-global-conclusion");
    expect(html).toContain("true-momentum-preview-evidence-review-tags");
    expect(html).toContain('data-tag="research_candidate"');
    expect(html).toContain('data-tag="watchlist_only"');
    expect(html).toContain('data-tag="needs_tos_parity_check"');
    expect(html).toContain('data-tag="needs_b8_outcome_evidence"');
    expect(html).toContain('data-tag="too_noisy"');
    expect(html).toContain('data-tag="defer"');
  });

  it("renders deterministic note and still-pending caveat copy", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={PREVIEW_RESULT}
        persistLatest={false}
      />,
    );
    expect(html).toContain(TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE);
    expect(html).toContain("Still pending: accumulated B8 outcome evidence");
    expect(html).toContain("Thinkorswim fixture parity");
    expect(html).toContain("operator authorization before any active Phase C");
  });

  it("respects initialBundle by surfacing the captured-state badge", () => {
    const initialBundle: TrueMomentumPreviewEvidenceBundle =
      buildTrueMomentumPreviewEvidenceBundle(PREVIEW_RESULT, {
        queueCandidates: MIXED_QUEUE,
        operatorReview: {
          global_conclusion: "XLK clean.",
          family_notes: {
            true_momentum_continuation: "",
            true_momentum_pullback: "",
            true_momentum_reversal_watch: "",
          },
        },
      });
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={PREVIEW_RESULT}
        persistLatest={false}
        initialBundle={initialBundle}
      />,
    );
    expect(html).toContain("Bundle captured");
    expect(html).toContain("XLK clean.");
  });

  it("never renders forbidden trade-action language", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={PREVIEW_RESULT}
        persistLatest={false}
      />,
    ).toLowerCase();
    for (const phrase of [
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "auto approve",
      "route order",
    ]) {
      expect(html).not.toContain(phrase);
    }
  });

  it("never renders affirmative queue-candidate-generation copy", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={PREVIEW_RESULT}
        persistLatest={false}
      />,
    ).toLowerCase();
    expect(html).not.toContain("generates queue candidates");
    expect(html).not.toContain("emits queue candidate");
    expect(html).not.toContain("creates queue candidate");
  });

  it("never renders approval / promote / order-routing copy", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPreviewEvidencePanel
        candidates={MIXED_QUEUE}
        previewResult={PREVIEW_RESULT}
        persistLatest={false}
      />,
    ).toLowerCase();
    expect(html).not.toContain("promote to recommendation");
    expect(html).not.toContain("approve trade");
    expect(html).not.toContain("place order");
  });
});
