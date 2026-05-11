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
    StatusBadge: ({ tone, children }: { tone?: string; children: ReactNode }) =>
      ReactModule.createElement(
        "span",
        { className: `op-badge op-badge-${tone ?? "neutral"}` },
        children,
      ),
  };
});

import { MomentumImpactReview } from "@/components/recommendations/momentum-impact-review";
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
    mode: "shadow",
    enabled: true,
    applied: false,
    total_contribution: 0,
    shadow_contribution: 12,
    momentum_alignment_score: 8,
    trend_alignment_score: 4,
    hilo_confirmation_bonus: 0,
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
    reason_codes: ["thinkorswim_parity_pending", "derived_higher_timeframe"],
    active_delta_scale: 0.35,
    raw_total_contribution: 12,
    applied_score_delta: 0,
    ...overrides,
  };
}

function candidate(overrides: Partial<QueueCandidate> = {}): QueueCandidate {
  return {
    rank: 1,
    symbol: "AAPL",
    strategy: "Event Continuation",
    workflow_source: "test_provider",
    timeframe: "1D",
    status: "top_candidate",
    score: 0.6,
    expected_rr: 2.0,
    confidence: 0.7,
    reason_text: "",
    thesis: "",
    momentum_contribution: contribution(),
    ...overrides,
  };
}

const DETERMINISTIC_NOTE =
  "This review estimates impact only. It does not change queue sorting, approval, sizing, or order routing.";

describe("MomentumImpactReview", () => {
  it("renders empty state when there are no candidates", () => {
    const html = renderToStaticMarkup(<MomentumImpactReview candidates={[]} />);
    expect(html).toContain("No candidates to review");
    expect(html).toContain(DETERMINISTIC_NOTE);
  });

  it("renders summary counts and mode framing for shadow mode", () => {
    const html = renderToStaticMarkup(
      <MomentumImpactReview
        candidates={[
          candidate({ symbol: "AAPL", momentum_contribution: contribution({ shadow_contribution: 12 }) }),
          candidate({ symbol: "MSFT", rank: 2, momentum_contribution: contribution({ shadow_contribution: -8 }) }),
          candidate({ symbol: "NVDA", rank: 3, momentum_contribution: contribution({ shadow_contribution: 0 }) }),
        ]}
      />,
    );
    expect(html).toContain("Shadow — computed, not applied");
    expect(html).toContain("3 candidate(s)");
    expect(html).toContain("1 positive");
    expect(html).toContain("1 negative");
    expect(html).toContain("Final scores are unchanged");
    expect(html).toContain(DETERMINISTIC_NOTE);
  });

  it("renders active-mode framing with no double counting note", () => {
    const html = renderToStaticMarkup(
      <MomentumImpactReview
        candidates={[
          candidate({
            momentum_contribution: contribution({ mode: "active", applied: true, total_contribution: 7 }),
          }),
        ]}
      />,
    );
    expect(html).toContain("Active — applied to ranking");
    expect(html).toContain("Momentum contribution is currently applied to ranking");
    expect(html).toContain("Approval and paper orders remain manual");
    expect(html).toContain("Active mode changes ranking order only");
  });

  it("renders blocked-active framing when safety guard is engaged", () => {
    const contributionWithBlock: MomentumRankingContribution = {
      ...contribution({
        mode: "shadow",
        applied: false,
        shadow_contribution: 14,
        reason_codes: [
          "active_mode_blocked_by_safety_guard",
          "thinkorswim_parity_pending",
        ],
      }),
    };
    const html = renderToStaticMarkup(
      <MomentumImpactReview candidates={[candidate({ momentum_contribution: contributionWithBlock })]} />,
    );
    expect(html).toContain(
      "Active was requested but the safety guard blocked application; review is running as shadow.",
    );
    expect(html).toContain("MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true");
    expect(html).toContain("Active blocked — safety guard not enabled");
  });

  it("renders off-mode disabled framing", () => {
    const html = renderToStaticMarkup(
      <MomentumImpactReview
        candidates={[
          candidate({ momentum_contribution: contribution({ mode: "off", enabled: false }) }),
        ]}
      />,
    );
    expect(html).toContain("Off — not computed");
    expect(html).toContain("disabled (off) or not computed");
  });

  it("renders parity-pending, direction-unknown, and reversal warning chips", () => {
    const html = renderToStaticMarkup(
      <MomentumImpactReview
        candidates={[
          candidate({
            momentum_contribution: contribution({
              reversal_warning: true,
              reason_codes: ["thinkorswim_parity_pending", "direction_unknown", "momentum_reversal_warning"],
            }),
          }),
        ]}
      />,
    );
    expect(html).toContain("Thinkorswim parity pending");
    expect(html).toContain("Direction unknown");
    expect(html).toContain("Reversal warning");
    expect(html).toContain("1 warning(s)");
  });

  it("renders estimated rank-up and rank-down counts when ranks would shift", () => {
    const html = renderToStaticMarkup(
      <MomentumImpactReview
        candidates={[
          candidate({
            symbol: "AAPL",
            rank: 1,
            score: 0.5,
            momentum_contribution: contribution({ shadow_contribution: -20 }),
          }),
          candidate({
            symbol: "MSFT",
            rank: 2,
            score: 0.4,
            momentum_contribution: contribution({ shadow_contribution: 25 }),
          }),
        ]}
      />,
    );
    expect(html).toContain("would move up");
    expect(html).toContain("would move down");
  });

  it("never contains trade-approval or order-routing copy", () => {
    const html = renderToStaticMarkup(
      <MomentumImpactReview candidates={[candidate()]} />,
    ).toLowerCase();
    for (const forbidden of [
      "approve trade",
      "auto approve",
      "route order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
    ]) {
      expect(html.includes(forbidden)).toBe(false);
    }
  });

  it("renders the deterministic-context note in every state", () => {
    const off = renderToStaticMarkup(
      <MomentumImpactReview
        candidates={[
          candidate({ momentum_contribution: contribution({ mode: "off", enabled: false }) }),
        ]}
      />,
    );
    expect(off).toContain(DETERMINISTIC_NOTE);
    const active = renderToStaticMarkup(
      <MomentumImpactReview
        candidates={[
          candidate({
            momentum_contribution: contribution({ mode: "active", applied: true, total_contribution: 7 }),
          }),
        ]}
      />,
    );
    expect(active).toContain(DETERMINISTIC_NOTE);
  });

  // ── Phase B6.1 — active delta scale visibility ──────────────────────

  it("surfaces the active delta scale and the new table column header", () => {
    const html = renderToStaticMarkup(
      <MomentumImpactReview
        candidates={[
          candidate({
            momentum_contribution: contribution({
              shadow_contribution: 18,
              raw_total_contribution: 18,
              active_delta_scale: 0.35,
            }),
          }),
        ]}
      />,
    );
    expect(html).toContain('data-testid="momentum-impact-delta-scale"');
    expect(html).toContain("Active delta scale: 0.35");
    expect(html).toContain("applied score delta = raw contribution ÷ 100 × scale");
    expect(html).toContain("Raw contribution (score units)");
    expect(html).toContain("Applied delta @ scale");
  });

  it("active-mode review uses payload-supplied applied_score_delta instead of recomputing", () => {
    const html = renderToStaticMarkup(
      <MomentumImpactReview
        candidates={[
          candidate({
            momentum_contribution: contribution({
              mode: "active",
              applied: true,
              total_contribution: 20,
              shadow_contribution: 20,
              raw_total_contribution: 20,
              applied_score_delta: 0.07,
              active_delta_scale: 0.35,
            }),
          }),
        ]}
      />,
    );
    expect(html).toContain("Applied delta @ scale");
    expect(html).toContain("0.070");
  });
});
