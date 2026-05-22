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
    EmptyState: ({ title, hint }: { title: string; hint: string }) =>
      ReactModule.createElement(
        "div",
        { className: "op-empty" },
        ReactModule.createElement("strong", {}, title),
        ReactModule.createElement("p", {}, hint),
      ),
  };
});

import { TrueMomentumResearchCandidatesPanelView } from "@/components/recommendations/true-momentum-research-candidates-panel";
import { buildTrueMomentumResearchCandidateProposalSet } from "@/lib/true-momentum-research-candidates";
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

function rankingStatus(): MomentumRankingStatus {
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
        symbol: "SPY",
        status: "visual_attested",
        diagnostic_classification: ["oscillator_aligned"],
        diagnostic_flags: { oscillator_aligned: true },
        reason_codes: [],
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
  };
}

function candidate(overrides: Partial<QueueCandidate> = {}): QueueCandidate {
  return {
    rank: 1,
    symbol: "SPY",
    side: "long",
    strategy: "Event Continuation",
    workflow_source: "test",
    timeframe: "1D",
    status: "pending",
    score: 0.62,
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
      shadow_contribution: 20,
      momentum_alignment_score: 5,
      trend_alignment_score: 100,
      hilo_confirmation_bonus: 15,
      reversal_warning_penalty: 0,
      no_trade_warning: false,
      pullback_signal: false,
      reversal_warning: false,
      total_score: 100,
      total_label: "Max Bull",
      trend_score: 100,
      momo_score: 100,
      inferred_direction: "long",
      reason_codes: [],
      raw_total_contribution: 20,
      applied_score_delta: 0.07,
      active_delta_scale: 0.35,
    },
    ...overrides,
  };
}

describe("TrueMomentumResearchCandidatesPanelView", () => {
  it("renders the empty state until proposals are generated", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumResearchCandidatesPanelView
        proposalSet={null}
        hasGenerated={false}
        onClear={() => {}}
        onCopyMarkdown={() => {}}
        onCopyJson={() => {}}
        onDownloadMarkdown={() => {}}
        onDownloadJson={() => {}}
      />,
    );
    expect(html).toContain("No research candidate proposals yet");
  });

  it("renders summary chips and the ranked proposals table when generated", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [
        candidate({ symbol: "SPY", rank: 1 }),
        candidate({ symbol: "XLP", rank: 2 }),
      ],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumResearchCandidatesPanelView
        proposalSet={set}
        hasGenerated={true}
        onClear={() => {}}
        onCopyMarkdown={() => {}}
        onCopyJson={() => {}}
        onDownloadMarkdown={() => {}}
        onDownloadJson={() => {}}
      />,
    );
    expect(html).toContain('data-testid="true-momentum-research-candidates-panel-body"');
    expect(html).toContain('data-testid="true-momentum-research-candidates-panel-summary"');
    expect(html).toContain('data-testid="true-momentum-research-candidates-panel-ranked-table"');
    expect(html).toContain("SPY");
    expect(html).toContain("XLP");
    expect(html).toContain("XLP composite mismatch present");
  });

  it("renders the decision-gate list including the two always-blocking gates", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [candidate({ symbol: "SPY" })],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumResearchCandidatesPanelView
        proposalSet={set}
        hasGenerated={true}
        onClear={() => {}}
        onCopyMarkdown={() => {}}
        onCopyJson={() => {}}
        onDownloadMarkdown={() => {}}
        onDownloadJson={() => {}}
      />,
    );
    expect(html).toContain(
      'data-testid="true-momentum-research-candidate-gate-operator_authorization"',
    );
    expect(html).toContain(
      'data-testid="true-momentum-research-candidate-gate-active_generation_reserved"',
    );
  });

  it("renders the export controls and deterministic note", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [candidate({ symbol: "SPY" })],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumResearchCandidatesPanelView
        proposalSet={set}
        hasGenerated={true}
        onClear={() => {}}
        onCopyMarkdown={() => {}}
        onCopyJson={() => {}}
        onDownloadMarkdown={() => {}}
        onDownloadJson={() => {}}
      />,
    );
    expect(html).toContain(
      'data-testid="true-momentum-research-candidates-panel-copy-markdown"',
    );
    expect(html).toContain(
      'data-testid="true-momentum-research-candidates-panel-copy-json"',
    );
    expect(html).toContain(
      'data-testid="true-momentum-research-candidates-panel-download-markdown"',
    );
    expect(html).toContain(
      'data-testid="true-momentum-research-candidates-panel-download-json"',
    );
    expect(html).toContain(
      'data-testid="true-momentum-research-candidates-panel-clear"',
    );
    expect(html).toContain(
      'data-testid="true-momentum-research-candidates-panel-deterministic-note"',
    );
  });

  it("never carries forbidden trade-action language", () => {
    const set = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates: [
        candidate({ symbol: "SPY", rank: 1 }),
        candidate({ symbol: "XLP", rank: 2 }),
      ],
      strategyFamilyStatus: familyStatus(),
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumResearchCandidatesPanelView
        proposalSet={set}
        hasGenerated={true}
        onClear={() => {}}
        onCopyMarkdown={() => {}}
        onCopyJson={() => {}}
        onDownloadMarkdown={() => {}}
        onDownloadJson={() => {}}
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
      "ready for live",
      "activate now",
    ]) {
      expect(html.includes(forbidden)).toBe(false);
    }
  });
});
