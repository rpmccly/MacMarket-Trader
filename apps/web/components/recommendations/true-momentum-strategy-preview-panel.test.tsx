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

import {
  TrueMomentumStrategyPreviewPanel,
  TrueMomentumStrategyPreviewPanelView,
} from "@/components/recommendations/true-momentum-strategy-preview-panel";
import {
  buildTrueMomentumStrategyPreview,
  TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE,
} from "@/lib/true-momentum-strategy-preview";
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
    momo_score: 73,
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

const DISABLED_STATUS = status({
  effective_mode: "disabled",
  requested_mode: "disabled",
  enabled: false,
  guard_enabled: false,
});

const ACTIVE_RESERVED_STATUS = status({
  effective_mode: "disabled",
  requested_mode: "active",
  enabled: false,
  guard_enabled: false,
});

describe("TrueMomentumStrategyPreviewPanelView — disabled state", () => {
  it("renders the disabled empty state with env instructions", () => {
    const result = buildTrueMomentumStrategyPreview([candidate()], DISABLED_STATUS);
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanelView result={result} status={DISABLED_STATUS} />,
    );
    expect(html).toContain("true-momentum-strategy-preview-disabled");
    expect(html).toContain("Phase C1 research preview is disabled.");
    expect(html).toContain("MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=research_preview");
    expect(html).toContain("MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES=true");
    expect(html).toContain("does not generate queue candidates");
    expect(html).toContain(TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE);
  });

  it("shows active-reserved copy when active was requested but blocked", () => {
    const result = buildTrueMomentumStrategyPreview([candidate()], ACTIVE_RESERVED_STATUS);
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanelView
        result={result}
        status={ACTIVE_RESERVED_STATUS}
      />,
    );
    expect(html).toContain("true-momentum-strategy-preview-active-reserved");
    expect(html).toContain("Active Phase C is reserved and not implemented");
  });
});

describe("TrueMomentumStrategyPreviewPanelView — research-preview state", () => {
  it("renders continuation rows with the right family label + match strength", () => {
    const result = buildTrueMomentumStrategyPreview([candidate({ symbol: "XLK" })], status());
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanelView result={result} status={status()} />,
    );
    expect(html).toContain("true-momentum-strategy-preview");
    expect(html).toContain("true-momentum-strategy-preview-table");
    expect(html).toContain("True Momentum Continuation");
    expect(html).toContain('data-family-id="true_momentum_continuation"');
    expect(html).toContain('data-match-strength="strong"');
  });

  it("renders pullback rows when the source carries the pullback signal", () => {
    const queue = [
      candidate({
        symbol: "IWM",
        strategy: "Pullback / Trend Continuation",
        momentum_contribution: contribution({ pullback_signal: true }),
      }),
    ];
    const result = buildTrueMomentumStrategyPreview(queue, status());
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanelView result={result} status={status()} />,
    );
    expect(html).toContain('data-family-id="true_momentum_pullback"');
    expect(html).toContain("True Momentum Pullback");
  });

  it("renders reversal/watch rows on no-trade warning", () => {
    const queue = [
      candidate({
        symbol: "BAD",
        momentum_contribution: contribution({
          no_trade_warning: true,
          reason_codes: ["momentum_no_trade_warning"],
        }),
      }),
    ];
    const result = buildTrueMomentumStrategyPreview(queue, status());
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanelView result={result} status={status()} />,
    );
    expect(html).toContain('data-family-id="true_momentum_reversal_watch"');
    expect(html).toContain("True Momentum Reversal / Weakening Watch");
    expect(html).toContain("No-trade warning");
  });

  it("renders the per-family + caveat summary counts", () => {
    const queue = [
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
          reason_codes: ["momentum_no_trade_warning", "thinkorswim_parity_pending"],
        }),
      }),
    ];
    const result = buildTrueMomentumStrategyPreview(queue, status());
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanelView result={result} status={status()} />,
    );
    expect(html).toContain("true-momentum-strategy-preview-summary");
    expect(html).toContain("true-momentum-strategy-preview-summary-continuation");
    expect(html).toContain("true-momentum-strategy-preview-summary-pullback");
    expect(html).toContain("true-momentum-strategy-preview-summary-reversal");
    expect(html).toContain("Parity pending");
    expect(html).toContain("Operational caveats");
  });

  it("Phase C2.1 — suppresses the C1 deterministic note when the evidence panel is mounted (previews exist)", () => {
    const result = buildTrueMomentumStrategyPreview([candidate()], status());
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanelView result={result} status={status()} />,
    );
    // The evidence panel is the canonical owner of the deterministic
    // research-only note + still-pending caveat copy whenever it is
    // mounted, so the C1 panel must not duplicate them.
    expect(html).not.toContain(TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE);
    // The evidence panel still renders its own (different) deterministic
    // note + the shared still-pending caveat line.
    expect(html).toContain(
      "True Momentum preview evidence is research-only.",
    );
    expect(html).toContain("Still pending: accumulated B8 outcome evidence");
  });

  it("Phase C2.1 — keeps the C1 deterministic note when no previews matched", () => {
    const result = buildTrueMomentumStrategyPreview([], status());
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanelView result={result} status={status()} />,
    );
    expect(html).toContain(TRUE_MOMENTUM_STRATEGY_PREVIEW_DETERMINISTIC_NOTE);
    expect(html).toContain("Still pending: accumulated B8 outcome evidence");
  });

  it("never renders forbidden trade-action language", () => {
    const queue = [
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
    ];
    const result = buildTrueMomentumStrategyPreview(queue, status());
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanelView result={result} status={status()} />,
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
    // The deterministic note legitimately uses the negation ("do not
    // generate queue candidates"); we only forbid the affirmative form
    // that would imply Phase C1 emits new queue rows.
    const result = buildTrueMomentumStrategyPreview([candidate()], status());
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanelView result={result} status={status()} />,
    ).toLowerCase();
    expect(html).not.toContain("generates queue candidates");
    expect(html).not.toContain("emits queue candidate");
    expect(html).not.toContain("creates queue candidate");
  });

  it("renders empty state when no rows match a planned family", () => {
    const offCandidate = candidate({
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
    });
    const result = buildTrueMomentumStrategyPreview([offCandidate], status());
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanelView result={result} status={status()} />,
    );
    expect(html).toContain("true-momentum-strategy-preview-empty");
    expect(html).toContain("No candidates matched a planned True Momentum family");
  });
});

describe("TrueMomentumStrategyPreviewPanel (container)", () => {
  it("renders without triggering a fetch when an initial status is provided", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanel
        candidates={[candidate()]}
        initialStatus={status()}
      />,
    );
    expect(html).toContain("true-momentum-strategy-preview");
    expect(html).toContain("True Momentum Continuation");
  });

  it("renders the disabled empty state when initialStatus is disabled", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyPreviewPanel
        candidates={[candidate()]}
        initialStatus={DISABLED_STATUS}
      />,
    );
    expect(html).toContain("true-momentum-strategy-preview-disabled");
    expect(html).toContain("MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=research_preview");
  });
});
