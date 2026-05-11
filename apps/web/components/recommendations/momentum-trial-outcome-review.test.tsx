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

import { MomentumTrialOutcomeReviewPanel } from "@/components/recommendations/momentum-trial-outcome-review";
import {
  buildMomentumTrialSnapshot,
} from "@/lib/momentum-trial-journal";
import {
  MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE,
} from "@/lib/momentum-trial-outcomes";
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
];

describe("MomentumTrialOutcomeReviewPanel — empty state", () => {
  it("renders an empty hint when no snapshot is provided", () => {
    const html = renderToStaticMarkup(
      <MomentumTrialOutcomeReviewPanel snapshot={null} persistLatest={false} />,
    );
    expect(html).toContain("momentum-trial-outcome-review-empty");
    expect(html).toContain("No snapshot captured yet");
    expect(html).toContain(MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE);
  });
});

describe("MomentumTrialOutcomeReviewPanel — populated state", () => {
  it("renders a row per default outcome with the unclear tag selected", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(
      <MomentumTrialOutcomeReviewPanel snapshot={snapshot} persistLatest={false} />,
    );
    expect(html).toContain("momentum-trial-outcome-review");
    expect(html).toContain("momentum-trial-outcome-table-wrapper");
    expect(html).toContain('data-symbol="XLK"');
    expect(html).toContain('data-symbol="IWM"');
    expect(html).toContain('data-tag="unclear"');
    // tag select carries an option per supported tag.
    for (const tag of [
      "worked",
      "missed",
      "too_aggressive",
      "good_warning",
      "false_warning",
      "watchlist_only",
      "needs_tos_parity_check",
      "ignored",
      "unclear",
    ]) {
      expect(html).toContain(`value="${tag}"`);
    }
  });

  it("renders the summary cards", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(
      <MomentumTrialOutcomeReviewPanel snapshot={snapshot} persistLatest={false} />,
    );
    expect(html).toContain("momentum-trial-outcome-summary");
    expect(html).toContain("Worked");
    expect(html).toContain("Missed");
    expect(html).toContain("Too aggressive");
    expect(html).toContain("Good warnings");
    expect(html).toContain("False warnings");
    expect(html).toContain("Needs ToS parity");
    expect(html).toContain("Unclear");
    expect(html).toContain("momentum-trial-outcome-summary-worked");
    expect(html).toContain("momentum-trial-outcome-summary-missed");
  });

  it("renders export and clear buttons", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(
      <MomentumTrialOutcomeReviewPanel snapshot={snapshot} persistLatest={false} />,
    );
    expect(html).toContain("momentum-trial-outcome-download-markdown");
    expect(html).toContain("momentum-trial-outcome-download-json");
    expect(html).toContain("momentum-trial-outcome-clear");
    expect(html).toContain("Export Outcome Markdown");
    expect(html).toContain("Export Outcome JSON");
    expect(html).toContain("Clear outcome review");
  });

  it("renders the global outcome conclusion textarea", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(
      <MomentumTrialOutcomeReviewPanel snapshot={snapshot} persistLatest={false} />,
    );
    expect(html).toContain("momentum-trial-outcome-global-conclusion");
    expect(html).toContain("Global outcome conclusion");
  });

  it("respects initialOutcomes + initialGlobalConclusion props", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(
      <MomentumTrialOutcomeReviewPanel
        snapshot={snapshot}
        persistLatest={false}
        initialOutcomes={[
          {
            symbol: "XLK",
            strategy: "Event Continuation",
            rank: 1,
            tag: "worked",
            note: "Clean continuation",
            reason_codes: [],
            trade_warning_flags: [],
            operational_caveat_flags: [],
          },
        ]}
        initialGlobalConclusion="Momentum correctly elevated XLK."
      />,
    );
    expect(html).toContain('data-symbol="XLK"');
    expect(html).toContain('data-tag="worked"');
    expect(html).toContain("Clean continuation");
    expect(html).toContain("Momentum correctly elevated XLK.");
  });

  it("renders the deterministic outcome guardrail copy", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(
      <MomentumTrialOutcomeReviewPanel snapshot={snapshot} persistLatest={false} />,
    );
    expect(html).toContain(MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE);
  });

  it("never renders forbidden trade-action language", () => {
    const snapshot = buildMomentumTrialSnapshot(ACTIVE_QUEUE);
    const html = renderToStaticMarkup(
      <MomentumTrialOutcomeReviewPanel snapshot={snapshot} persistLatest={false} />,
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
});
