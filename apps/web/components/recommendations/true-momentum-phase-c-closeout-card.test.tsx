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
  };
});

import { TrueMomentumPhaseCCloseoutCardView } from "@/components/recommendations/true-momentum-phase-c-closeout-card";
import {
  buildTrueMomentumPhaseCCloseoutStatus,
  TRUE_MOMENTUM_PHASE_C_SHIPPED_PHASES,
} from "@/lib/true-momentum-phase-c-closeout";
import type { MomentumRankingStatus } from "@/lib/momentum-ranking-status";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

function rankingStatus(
  overrides: Partial<MomentumRankingStatus> = {},
): MomentumRankingStatus {
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
    thinkorswim_parity_workflow_status: "failed",
    thinkorswim_parity_visual_attestation_status: "visual_failed",
    thinkorswim_parity_visual_attestation_count: 4,
    thinkorswim_parity_visual_attestation_passed_count: 3,
    thinkorswim_parity_visual_attestation_failed_count: 1,
    thinkorswim_parity_visual_attestation_partial_count: 0,
    thinkorswim_parity_symbol_summaries: [
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

describe("TrueMomentumPhaseCCloseoutCardView", () => {
  it("renders shipped phases C0–C4.1", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumPhaseCCloseoutCardView status={status} />,
    );
    expect(html).toContain('data-testid="true-momentum-phase-c-closeout-card"');
    expect(html).toContain('data-testid="true-momentum-phase-c-closeout-card-shipped-phases"');
    for (const phase of TRUE_MOMENTUM_PHASE_C_SHIPPED_PHASES) {
      expect(html).toContain(phase);
    }
  });

  it("renders the explicit not-shipped list (active generation, queue, approval, sizing, routing)", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumPhaseCCloseoutCardView status={status} />,
    );
    expect(html).toContain('data-testid="true-momentum-phase-c-closeout-card-not-shipped"');
    expect(html).toContain("Active True Momentum strategy generation");
    expect(html).toContain("True Momentum queue candidate generation");
    expect(html).toContain("Auto approval");
    expect(html).toContain("Auto sizing");
    expect(html).toContain("Order routing");
  });

  it("renders Research implementation: complete and Active generation: reserved badges", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumPhaseCCloseoutCardView status={status} />,
    );
    expect(html).toContain("Research implementation: complete");
    expect(html).toContain("Active generation: reserved");
    expect(html).toContain("Queue candidates generated: No");
    expect(html).toContain("Approval / order behavior: unchanged / manual");
  });

  it("renders the XLP composite mismatch blocker with the affected symbol attached", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumPhaseCCloseoutCardView status={status} />,
    );
    expect(html).toContain('data-testid="true-momentum-phase-c-closeout-card-blocker-parity_mixed"');
    expect(html).toContain("Visual parity mixed");
    expect(html).toContain("Affected symbols: XLP");
  });

  it("renders operator_authorization_required and active_generation_not_implemented as blockers", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumPhaseCCloseoutCardView status={status} />,
    );
    expect(html).toContain(
      'data-testid="true-momentum-phase-c-closeout-card-blocker-operator_authorization_required"',
    );
    expect(html).toContain(
      'data-testid="true-momentum-phase-c-closeout-card-blocker-active_generation_not_implemented"',
    );
  });

  it("renders the C5 research-candidate-proposal next-allowed-phase line", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumPhaseCCloseoutCardView status={status} />,
    );
    expect(html).toContain('data-testid="true-momentum-phase-c-closeout-card-next-phase"');
    expect(html).toContain("C5 research candidate proposal");
    expect(html).toContain("non-active");
    expect(html).toContain("non-ordering");
  });

  it("never carries forbidden trade-action language", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumPhaseCCloseoutCardView status={status} />,
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

  it("always renders the deterministic note", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumPhaseCCloseoutCardView status={status} />,
    );
    expect(html).toContain('data-testid="true-momentum-phase-c-closeout-card-deterministic-note"');
    expect(html).toContain('data-testid="true-momentum-phase-c-closeout-card-recommended-action"');
  });

  it("renders the paper-order-creation badge as manual / unaffected", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumPhaseCCloseoutCardView status={status} />,
    );
    expect(html).toContain('data-testid="true-momentum-phase-c-closeout-card-paper-order"');
    expect(html).toContain("Paper-order creation: manual / unaffected");
  });

  it("renders the current parity summary block with SPY / XLK / XLE passing and XLP composite-mismatch", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus({
        thinkorswim_parity_symbol_summaries: [
          {
            symbol: "SPY",
            status: "visual_attested",
            diagnostic_classification: ["oscillator_aligned"],
            diagnostic_flags: { oscillator_aligned: true },
            reason_codes: [],
          },
          {
            symbol: "XLK",
            status: "visual_attested",
            diagnostic_classification: ["oscillator_aligned"],
            diagnostic_flags: { oscillator_aligned: true },
            reason_codes: [],
          },
          {
            symbol: "XLE",
            status: "visual_attested",
            diagnostic_classification: ["oscillator_aligned"],
            diagnostic_flags: { oscillator_aligned: true },
            reason_codes: [],
          },
          {
            symbol: "XLP",
            status: "visual_failed",
            diagnostic_classification: [
              "oscillator_aligned",
              "composite_mismatch",
            ],
            diagnostic_flags: {
              oscillator_aligned: true,
              composite_score_failed: true,
            },
            reason_codes: [],
          },
        ],
      }),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumPhaseCCloseoutCardView status={status} />,
    );
    expect(html).toContain('data-testid="true-momentum-phase-c-closeout-card-parity-summary"');
    expect(html).toContain("Visual attestation passed");
    expect(html).toContain("SPY");
    expect(html).toContain("XLK");
    expect(html).toContain("XLE");
    expect(html).toContain("Visual attestation failed");
    expect(html).toContain("Composite mismatch under review");
    expect(html).toContain("XLP");
  });

  it("renders the dedicated xlp_composite_mismatch blocker line", () => {
    const status = buildTrueMomentumPhaseCCloseoutStatus({
      rankingStatus: rankingStatus(),
    });
    const html = renderToStaticMarkup(
      <TrueMomentumPhaseCCloseoutCardView status={status} />,
    );
    expect(html).toContain(
      'data-testid="true-momentum-phase-c-closeout-card-blocker-xlp_composite_mismatch"',
    );
    expect(html).toContain("XLP composite mismatch under review");
  });
});
