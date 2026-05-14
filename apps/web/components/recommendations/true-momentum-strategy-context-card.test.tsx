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

import { TrueMomentumStrategyContextCardView } from "@/components/recommendations/true-momentum-strategy-context-card";
import {
  buildTrueMomentumStrategyContext,
  type TrueMomentumStrategyContext,
} from "@/lib/true-momentum-strategy-context";
import type { MomentumRankingStatus } from "@/lib/momentum-ranking-status";
import type { QueueCandidate } from "@/lib/recommendations";
import type { TrueMomentumStrategyFamilyStatus } from "@/lib/true-momentum-strategy-families";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

function familyStatus(): TrueMomentumStrategyFamilyStatus {
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
    implementation_status: "research_preview",
    parity_status: "validated_against_thinkorswim_fixture",
    parity_required_for_active: true,
  };
}

function rankingStatus(overrides: Partial<MomentumRankingStatus> = {}): MomentumRankingStatus {
  return {
    mode: "active",
    default_mode: "shadow",
    env_var: "MACMARKET_MOMENTUM_RANKING_MODE",
    enabled: true,
    applied_by_default: true,
    parity_status: "validated_against_thinkorswim_fixture",
    parity_fixture_manifest_present: true,
    parity_required_for_active: true,
    real_thinkorswim_parity_pending: false,
    reason_codes: [],
    guardrails: [],
    thinkorswim_parity_workflow_status: "passed",
    thinkorswim_parity_visual_attestation_status: "visual_attested",
    thinkorswim_parity_visual_attestation_count: 4,
    thinkorswim_parity_visual_attestation_passed_count: 3,
    thinkorswim_parity_visual_attestation_failed_count: 1,
    thinkorswim_parity_visual_attestation_partial_count: 0,
    thinkorswim_parity_symbol_summaries: [
      {
        symbol: "XLK",
        status: "visual_attested",
        diagnostic_classification: ["oscillator_aligned"],
        diagnostic_flags: { oscillator_aligned: true },
        reason_codes: ["thinkorswim_visual_attested"],
      },
      {
        symbol: "XLP",
        status: "visual_failed",
        diagnostic_classification: ["oscillator_aligned", "composite_mismatch"],
        diagnostic_flags: {
          oscillator_aligned: true,
          composite_score_failed: true,
        },
        reason_codes: ["thinkorswim_visual_attestation_failed"],
      },
    ],
    ...overrides,
  };
}

function candidate(overrides: Partial<QueueCandidate> = {}): QueueCandidate {
  return {
    rank: 1,
    symbol: "XLK",
    side: "long",
    strategy: "Event Continuation",
    workflow_source: "test",
    timeframe: "1D",
    status: "pending",
    score: 0.62,
    score_before_momentum: 0.55,
    score_after_momentum: 0.62,
    momentum_score_delta: 0.07,
    expected_rr: 1.8,
    confidence: 0.7,
    reason_text: "Event continuation candidate",
    thesis: "Operator captured this.",
    trigger: "Hold above prior day high",
    entry_zone: { low: 100, high: 101 },
    invalidation: { price: 99 },
    momentum_contribution: {
      mode: "active",
      enabled: true,
      applied: true,
      total_contribution: 20,
      momentum_alignment_score: 5,
      hilo_confirmation_bonus: 15,
      total_score: 100,
      total_label: "Max Bull",
      trend_score: 100,
      momo_score: 100,
      inferred_direction: "long",
      raw_total_contribution: 20,
      applied_score_delta: 0.07,
      active_delta_scale: 0.35,
    },
    ...overrides,
  };
}

function contextFor(c: QueueCandidate, statusOverrides: Partial<MomentumRankingStatus> = {}) {
  return buildTrueMomentumStrategyContext({
    candidate: c,
    strategyFamilyStatus: familyStatus(),
    rankingStatus: rankingStatus(statusOverrides),
  });
}

describe("TrueMomentumStrategyContextCardView", () => {
  it("renders an empty state when no candidate is selected", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={null}
        context={null}
        loading={false}
        error={null}
      />,
    );
    expect(html).toContain('data-testid="true-momentum-strategy-context-card-empty"');
  });

  it("renders a loading state with role=status while fetching", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={candidate()}
        context={null}
        loading
        error={null}
      />,
    );
    expect(html).toContain('data-testid="true-momentum-strategy-context-card-loading"');
    expect(html).toContain('role="status"');
  });

  it("renders an error state when error string is provided", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={candidate()}
        context={null}
        loading={false}
        error="Backend unavailable"
      />,
    );
    expect(html).toContain('data-testid="true-momentum-strategy-context-card-error"');
    expect(html).toContain("Backend unavailable");
  });

  it("renders no-family-match state when context has no family", () => {
    const c = candidate({
      strategy: "Neutral strategy",
      momentum_contribution: {
        ...(candidate().momentum_contribution ?? {}),
        total_label: "Neutral",
        total_score: 0,
        raw_total_contribution: 0,
        applied_score_delta: 0,
      },
    });
    const context = contextFor(c);
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={c}
        context={context}
        loading={false}
        error={null}
      />,
    );
    expect(html).toContain('data-testid="true-momentum-strategy-context-card-no-match"');
    expect(html).toContain("No True Momentum family match");
  });

  it("renders a continuation match card with checklist + readiness", () => {
    const c = candidate();
    const context = contextFor(c);
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={c}
        context={context}
        loading={false}
        error={null}
      />,
    );
    expect(html).toContain('data-testid="true-momentum-strategy-context-card"');
    expect(html).toContain('data-testid="true-momentum-strategy-context-card-family-badge"');
    expect(html).toContain("True Momentum Continuation");
    expect(html).toContain('data-testid="true-momentum-strategy-context-card-readiness-badge"');
    expect(html).toContain("Research-ready");
    expect(html).toContain('data-testid="true-momentum-strategy-context-card-checklist"');
    expect(html).toContain("Trigger-readiness checklist");
    expect(html).toContain('data-testid="true-momentum-strategy-context-card-parity"');
    expect(html).toContain("Visual attestation passed");
  });

  it("renders a pullback match card when source strategy is Pullback", () => {
    const c = candidate({ strategy: "Pullback" });
    const context = contextFor(c);
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={c}
        context={context}
        loading={false}
        error={null}
      />,
    );
    expect(html).toContain("True Momentum Pullback");
    expect(html).toContain("Pullback signal active");
  });

  it("renders the reversal/watch card with watch_only readiness", () => {
    const c = candidate({ symbol: "XLE" });
    c.momentum_contribution = {
      ...(c.momentum_contribution ?? {}),
      total_label: "Bear",
      total_score: -100,
    };
    const context = contextFor(c);
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={c}
        context={context}
        loading={false}
        error={null}
      />,
    );
    expect(html).toContain("True Momentum Reversal");
    expect(html).toContain("Watch-only");
    expect(html).toContain("never proposes entry");
  });

  it("renders the XLP composite-mismatch caveat for the failing symbol", () => {
    const c = candidate({ symbol: "XLP" });
    const context = contextFor(c);
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={c}
        context={context}
        loading={false}
        error={null}
      />,
    );
    expect(html).toContain("Visual attestation failed");
    // The caveat sentence + the classification chip both mention
    // composite mismatch. Case-insensitive match keeps the assertion
    // friendly to either renderer style.
    expect(html.toLowerCase()).toContain("composite mismatch under review");
    expect(html.toLowerCase()).toContain("composite_mismatch".replaceAll("_", " "));
  });

  it("renders the global mixed caveat for unrelated symbols when XLP is the only failing fixture", () => {
    const c = candidate({ symbol: "AAPL" });
    // Force a status with workflow=failed but no AAPL row in summaries.
    const context = contextFor(c, {
      thinkorswim_parity_workflow_status: "failed",
      thinkorswim_parity_visual_attestation_status: "visual_failed",
    });
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={c}
        context={context}
        loading={false}
        error={null}
      />,
    );
    expect(html).toContain("Visual parity mixed");
  });

  it("never contains forbidden trade-action language", () => {
    const c = candidate();
    const context = contextFor(c);
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={c}
        context={context}
        loading={false}
        error={null}
      />,
    ).toLowerCase();
    for (const forbidden of [
      "approve trade",
      "auto approve",
      "route order",
      "place order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
    ]) {
      expect(html.includes(forbidden)).toBe(false);
    }
    expect(html).toContain("does not generate queue candidates");
  });

  it("always renders the deterministic note", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={null}
        context={null}
        loading={false}
        error={null}
      />,
    );
    expect(html).toContain('data-testid="true-momentum-strategy-context-card-deterministic-note"');
  });

  it("renders guardrails non-actionable copy", () => {
    const c = candidate();
    const context = contextFor(c);
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyContextCardView
        candidate={c}
        context={context}
        loading={false}
        error={null}
      />,
    );
    expect(html).toContain('data-testid="true-momentum-strategy-context-card-guardrails"');
    expect(html).toContain("Activation readiness is research context");
  });
});

// Sanity: ensure the helper's context object passes the same forbidden-
// language guard the integration tests will rely on.
describe("forbidden-language guard via helper", () => {
  it("buildTrueMomentumStrategyContext returns a context with no forbidden action words", () => {
    const c = candidate();
    const context = contextFor(c);
    const surfaces: string[] = [];
    if (context) {
      surfaces.push(...context.guardrails);
      surfaces.push(...context.research_notes);
      surfaces.push(...context.evidence_caveats.parity_messages);
      if (context.trigger_checklist) {
        for (const item of context.trigger_checklist.items) {
          surfaces.push(item.label);
          surfaces.push(item.reason);
        }
      }
    }
    const lower = surfaces.join("\n").toLowerCase();
    for (const forbidden of [
      "approve trade",
      "auto approve",
      "route order",
      "place order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
    ]) {
      expect(lower.includes(forbidden)).toBe(false);
    }
  });
});

// Ensure context summary helper round-trips without throwing.
describe("TrueMomentumStrategyContext shape sanity", () => {
  it("context object has the expected required keys", () => {
    const c = candidate();
    const context = contextFor(c) as TrueMomentumStrategyContext;
    expect(context).not.toBeNull();
    expect(context.non_actionable).toBe(true);
    expect(context.symbol).toBe("XLK");
    expect(context.strategy).toBe("Event Continuation");
    expect(Array.isArray(context.guardrails)).toBe(true);
    expect(Array.isArray(context.research_notes)).toBe(true);
    expect(typeof context.evidence_caveats.parity_status).toBe("string");
  });
});
