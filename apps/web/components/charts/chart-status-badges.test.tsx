import React from "react";
import type { ReactNode } from "react";
import { createRequire } from "module";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/operator-ui", async () => {
  const ReactModule = await import("react");
  return {
    StatusBadge: ({ tone, children, ...rest }: { tone?: string; children: ReactNode; [key: string]: unknown }) =>
      ReactModule.createElement(
        "span",
        { className: `op-badge op-badge-${tone ?? "neutral"}`, ...rest },
        children,
      ),
  };
});

import {
  CandleStatusBadges,
  HiloPanelStatusBadges,
  TrueMomentumPanelStatusBadges,
} from "@/components/charts/chart-status-badges";
import type {
  MomentumVisualParityPoint,
  MomentumVisualParitySnapshot,
} from "@/lib/momentum-api";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

function snapshot(overrides: Partial<MomentumVisualParitySnapshot> = {}): MomentumVisualParitySnapshot {
  return {
    as_of: "2026-05-10",
    symbol: "SPY",
    timeframe: "1D",
    history_range: "1Y",
    total_score: 80,
    total_label: "Bull",
    trend_score: 70,
    momo_score: 60,
    true_momentum: 67.25,
    true_momentum_ema: 61.4,
    hilo_elite_value: 55.5,
    hilo_thrust_state: "bullish",
    hilo_score: 10,
    pullback_signal: false,
    reversal_warning: false,
    no_trade_warning: false,
    iv_percent: null,
    source_notes: [],
    unavailable_fields: ["iv_percent"],
    ...overrides,
  };
}

function point(overrides: Partial<MomentumVisualParityPoint> = {}): MomentumVisualParityPoint {
  return {
    index: 0,
    time: "2026-05-10",
    total_score: 80,
    total_label: "Bull",
    total_state: "bull",
    trend_score: 70,
    momo_score: 60,
    true_momentum: 67.25,
    true_momentum_ema: 61.4,
    hilo_elite_value: 55.5,
    hilo_thrust_state: "bullish",
    hilo_score: 10,
    pullback_signal: false,
    reversal_warning: false,
    no_trade_warning: false,
    ...overrides,
  };
}

describe("CandleStatusBadges", () => {
  it("renders Total Score / Total Label / Trend / Momo from a parity snapshot", () => {
    const html = renderToStaticMarkup(<CandleStatusBadges snapshot={snapshot()} />);
    expect(html).toContain("IV%");
    expect(html).toContain("Total");
    expect(html).toContain("Trend");
    expect(html).toContain("Momo");
    expect(html).toContain("Bull");
    expect(html).toContain("+70");
    expect(html).toContain("+60");
  });

  it("renders IV% as em dash with unavailable marker when no deterministic source is wired", () => {
    const html = renderToStaticMarkup(<CandleStatusBadges snapshot={snapshot()} />);
    expect(html).toMatch(/data-testid="candle-status-badges-iv"[^>]*data-unavailable="true"/);
  });

  it("renders IV% value when a deterministic source is provided", () => {
    const html = renderToStaticMarkup(
      <CandleStatusBadges snapshot={snapshot({ iv_percent: 27.5, unavailable_fields: [] })} />,
    );
    expect(html).toContain("27.5%");
    expect(html).toMatch(/data-testid="candle-status-badges-iv"[^>]*data-unavailable="false"/);
  });

  it("renders fallback placeholders when snapshot is null", () => {
    const html = renderToStaticMarkup(<CandleStatusBadges snapshot={null} />);
    expect(html).toContain("IV%");
    expect(html).toContain("—");
  });

  it("works equally with a per-bar parity point (hover-aware)", () => {
    const html = renderToStaticMarkup(<CandleStatusBadges snapshot={point({ total_score: 50, total_label: "Neutral Up" })} />);
    expect(html).toContain("Neutral Up");
    expect(html).toContain("+50");
  });

  it("never includes trade-action language in any branch", () => {
    const html = renderToStaticMarkup(<CandleStatusBadges snapshot={snapshot()} />).toLowerCase();
    for (const forbidden of ["approve trade", "route order", "buy now", "sell now", "enter now", "short now"]) {
      expect(html.includes(forbidden)).toBe(false);
    }
  });
});

describe("TrueMomentumPanelStatusBadges", () => {
  it("renders True Momentum, EMA, and bullish state when above EMA", () => {
    const html = renderToStaticMarkup(<TrueMomentumPanelStatusBadges snapshot={snapshot()} />);
    expect(html).toContain("True Momentum");
    expect(html).toContain("True Momentum EMA");
    expect(html).toContain("Bullish");
    expect(html).toContain("67.25");
    expect(html).toContain("61.40");
  });

  it("renders Bearish state when below EMA", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumPanelStatusBadges snapshot={snapshot({ true_momentum: 40, true_momentum_ema: 55 })} />,
    );
    expect(html).toContain("Bearish");
  });

  it("renders em-dash placeholders when snapshot is null", () => {
    const html = renderToStaticMarkup(<TrueMomentumPanelStatusBadges snapshot={null} />);
    expect(html).toContain("True Momentum");
    expect(html).toContain("—");
  });
});

describe("HiloPanelStatusBadges", () => {
  it("renders Confirmed thrust + HiLo Elite scalar + HiLo score for bullish state", () => {
    const html = renderToStaticMarkup(<HiloPanelStatusBadges snapshot={snapshot()} />);
    expect(html).toContain("Thrust");
    expect(html).toContain("Confirmed");
    expect(html).toContain("HiLo Elite");
    expect(html).toContain("55.50");
    expect(html).toContain("HiLo score");
    expect(html).toContain("+10");
  });

  it("renders Deconfirmed for bearish thrust", () => {
    const html = renderToStaticMarkup(
      <HiloPanelStatusBadges snapshot={snapshot({ hilo_thrust_state: "bearish", hilo_score: -5 })} />,
    );
    expect(html).toContain("Deconfirmed");
    expect(html).toContain("-5");
  });

  it("renders Neutral for neutral thrust", () => {
    const html = renderToStaticMarkup(
      <HiloPanelStatusBadges snapshot={snapshot({ hilo_thrust_state: "neutral" })} />,
    );
    expect(html).toContain("Neutral");
  });

  it("keeps the HiLo Elite scalar visually separate from the HiLo score", () => {
    const html = renderToStaticMarkup(<HiloPanelStatusBadges snapshot={snapshot()} />);
    // The two ids are rendered as separate badge testids.
    expect(html).toContain('data-testid="hilo-panel-status-badges-hilo_value"');
    expect(html).toContain('data-testid="hilo-panel-status-badges-hilo_score"');
  });
});
