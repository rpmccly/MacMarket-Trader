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
    StatusBadge: ({ tone, children, ...rest }: { tone?: string; children: ReactNode }) =>
      ReactModule.createElement(
        "span",
        { className: `op-badge op-badge-${tone ?? "neutral"}`, ...rest },
        children,
      ),
  };
});

import {
  MomentumRankingCard,
  MomentumRankingInlineBadge,
} from "@/components/recommendations/momentum-ranking-card";
import type { MomentumRankingContribution } from "@/lib/recommendations";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

const DETERMINISTIC_NOTE =
  "Momentum ranking contribution is bounded deterministic context. It does not approve, reject, size, or route trades.";

function shadow(overrides: Partial<MomentumRankingContribution> = {}): MomentumRankingContribution {
  return {
    mode: "shadow",
    enabled: true,
    applied: false,
    total_contribution: 0,
    shadow_contribution: 18,
    momentum_alignment_score: 10,
    trend_alignment_score: 8,
    hilo_confirmation_bonus: 5,
    reversal_warning_penalty: 0,
    no_trade_warning: false,
    pullback_signal: false,
    reversal_warning: false,
    parity_status: "pending_thinkorswim_fixture_validation",
    higher_timeframe_source: "derived_from_chart_bars",
    total_score: 100,
    total_label: "Max Bull",
    trend_score: 100,
    momo_score: 90,
    inferred_direction: "long",
    calculation_notes: [],
    reason_codes: ["thinkorswim_parity_pending", "derived_higher_timeframe"],
    active_delta_scale: 0.35,
    raw_total_contribution: 18,
    applied_score_delta: 0,
    ...overrides,
  };
}

describe("MomentumRankingCard", () => {
  it("renders missing state when contribution is null", () => {
    const html = renderToStaticMarkup(<MomentumRankingCard contribution={null} />);
    expect(html).toContain("Momentum ranking contribution not available");
    expect(html).toContain(DETERMINISTIC_NOTE);
    expect(html).toContain("data-testid=\"momentum-ranking-card-missing\"");
  });

  it("renders off state with off framing and no breakdown", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingCard contribution={{ mode: "off", enabled: false }} />,
    );
    expect(html).toContain("Off — not computed");
    expect(html).toContain("Not computed");
    expect(html).toContain(DETERMINISTIC_NOTE);
    expect(html).toContain("data-testid=\"momentum-ranking-card-off\"");
    expect(html).not.toContain("Momentum alignment");
  });

  it("renders shadow contribution as computed-but-not-applied with final-score-unchanged badge", () => {
    const html = renderToStaticMarkup(<MomentumRankingCard contribution={shadow()} />);
    expect(html).toContain("Shadow — computed, not applied");
    expect(html).toContain("Computed — final score unchanged");
    expect(html).toContain("Final score unchanged");
    expect(html).toContain("Shadow +18");
    expect(html).toContain("Momentum alignment");
    expect(html).toContain("Trend alignment");
    expect(html).toContain("HiLo confirmation");
    expect(html).toContain("Reversal warning penalty");
    expect(html).toContain("Total score");
    expect(html).toContain("Max Bull");
    expect(html).toContain("Thinkorswim parity pending");
    expect(html).toContain("Derived higher timeframe");
    expect(html).toContain("Inferred direction: long");
    expect(html).toContain(DETERMINISTIC_NOTE);
  });

  it("renders active contribution as bounded contribution applied", () => {
    const active = shadow({ mode: "active", applied: true, total_contribution: 9, shadow_contribution: 9 });
    const html = renderToStaticMarkup(<MomentumRankingCard contribution={active} />);
    expect(html).toContain("Active — applied to ranking");
    expect(html).toContain("Bounded contribution applied to ranking");
    expect(html).toContain("Applied +9");
    expect(html).not.toContain("Final score unchanged");
  });

  it("renders no-trade and reversal warning chips when flags are set", () => {
    const data = shadow({
      reversal_warning: true,
      no_trade_warning: true,
      reversal_warning_penalty: -12,
      reason_codes: ["momentum_reversal_warning", "momentum_no_trade_warning"],
    });
    const html = renderToStaticMarkup(<MomentumRankingCard contribution={data} />);
    expect(html).toContain("Reversal warning");
    expect(html).toContain("No-trade warning");
    expect(html).toMatch(/<strong[^>]*data-testid="momentum-ranking-warning"/);
  });

  it("renders direction_unknown reason code as a chip", () => {
    const data = shadow({ reason_codes: ["direction_unknown"], inferred_direction: "unknown" });
    const html = renderToStaticMarkup(<MomentumRankingCard contribution={data} />);
    expect(html).toContain("Direction unknown");
    expect(html).toContain("Inferred direction: unknown");
  });

  it("never includes trade-approval or order-routing copy", () => {
    const data = shadow();
    const html = renderToStaticMarkup(<MomentumRankingCard contribution={data} />).toLowerCase();
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

  it("compact mode collapses the breakdown to two-column grid", () => {
    const html = renderToStaticMarkup(<MomentumRankingCard contribution={shadow()} compact />);
    expect(html).toContain("op-grid-2");
  });

  // ── Phase B6.1 raw-vs-applied surfacing ──────────────────────────────

  it("shows raw contribution and estimated active delta at scale in shadow mode", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingCard
        contribution={shadow({ shadow_contribution: 20, raw_total_contribution: 20, active_delta_scale: 0.35 })}
      />,
    );
    expect(html).toContain("Shadow +20.00 raw");
    expect(html).toContain("Est. delta @ scale +0.07");
    expect(html).toContain("Active delta scale: 0.35");
  });

  it("shows applied score delta in active mode without double counting", () => {
    const active = shadow({
      mode: "active",
      applied: true,
      total_contribution: 20,
      shadow_contribution: 20,
      raw_total_contribution: 20,
      applied_score_delta: 0.07,
      active_delta_scale: 0.35,
    });
    const html = renderToStaticMarkup(<MomentumRankingCard contribution={active} />);
    expect(html).toContain("Applied +20.00 raw");
    expect(html).toContain("Score delta +0.07");
    expect(html).toContain("Active delta scale: 0.35");
  });

  it("defaults to 0.35 scale when active_delta_scale is missing", () => {
    const missingScale = shadow({ shadow_contribution: 20, raw_total_contribution: 20 });
    delete (missingScale as Partial<typeof missingScale>).active_delta_scale;
    const html = renderToStaticMarkup(<MomentumRankingCard contribution={missingScale} />);
    expect(html).toContain("Active delta scale: 0.35");
    expect(html).toContain("Est. delta @ scale +0.07");
  });
});

describe("MomentumRankingInlineBadge", () => {
  it("renders shadow inline badge", () => {
    const html = renderToStaticMarkup(<MomentumRankingInlineBadge contribution={shadow()} />);
    expect(html).toContain("Momentum shadow");
    expect(html).toContain("+18");
  });

  it("renders active inline badge", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingInlineBadge
        contribution={shadow({ mode: "active", applied: true, total_contribution: 7 })}
      />,
    );
    expect(html).toContain("Momentum active");
    expect(html).toContain("+7");
  });

  it("renders nothing for missing or off contribution", () => {
    expect(renderToStaticMarkup(<MomentumRankingInlineBadge contribution={null} />)).toBe("");
    expect(
      renderToStaticMarkup(<MomentumRankingInlineBadge contribution={{ mode: "off", enabled: false }} />),
    ).toBe("");
  });
});
