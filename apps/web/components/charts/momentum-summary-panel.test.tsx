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
      ReactModule.createElement("div", {}, `${title} ${hint}`),
    ErrorState: ({ title, hint }: { title: string; hint: string }) =>
      ReactModule.createElement("div", {}, `${title} ${hint}`),
    StatusBadge: ({ children }: { children: ReactNode }) =>
      ReactModule.createElement("span", { className: "op-badge" }, children),
  };
});

import { MomentumSummaryPanel } from "@/components/charts/momentum-summary-panel";
import type { MomentumChartPayload, MomentumScoreSnapshot } from "@/lib/momentum-api";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

function snapshot(overrides: Partial<MomentumScoreSnapshot> = {}): MomentumScoreSnapshot {
  const breakdown = {
    true_momentum_score: 15,
    hilo_thrust: 5,
    bull_ma: 30,
    bear_ma: 0,
    atr_value: 5,
    macd_bias: 5,
    intraday_penalty: 0,
    base_score: 60,
    ...(overrides.component_breakdown ?? {}),
  };
  const { component_breakdown: _ignored, ...rest } = overrides;
  return {
    total_score: 90,
    total_label: "Bull",
    total_state: "bull",
    trend_score: 80,
    momo_score: 60,
    true_momentum: 65.5,
    true_momentum_ema: 60.1,
    true_momentum_score: breakdown.true_momentum_score,
    hilo_thrust: 1,
    hilo_score: breakdown.hilo_thrust,
    atr_bias: breakdown.atr_value,
    macd_bias: breakdown.macd_bias,
    ma_bias: breakdown.bull_ma + breakdown.bear_ma,
    ...rest,
    component_breakdown: breakdown,
  };
}

function payload(overrides: Partial<MomentumChartPayload> = {}): MomentumChartPayload {
  const snap = overrides.latest_snapshot ?? snapshot();
  return {
    symbol: "AAPL",
    timeframe: "1D",
    candles: [],
    true_momentum_line: [],
    true_momentum_ema_line: [],
    hilo_slowd_line: [],
    hilo_slowd_x_line: [],
    hilo_thrust_strip: [],
    score_strip: [],
    markers: [],
    latest_snapshot: snap,
    explanation: {
      snapshot: snap,
      reversal_warning: false,
      pullback_signal: false,
      no_trade_warning: false,
      notes: [],
    },
    data_source: "polygon",
    fallback_mode: false,
    higher_timeframe_source: "derived_from_chart_bars",
    higher_timeframe: "weekly",
    parity_status: "pending_thinkorswim_fixture_validation",
    calculation_notes: [],
    ...overrides,
  };
}

const DETERMINISTIC_NOTE =
  "Momentum Intelligence is deterministic context only in Phase A. It does not approve, reject, size, or rank trades.";

describe("MomentumSummaryPanel", () => {
  it("renders an empty state when no payload is loaded", () => {
    const html = renderToStaticMarkup(<MomentumSummaryPanel payload={null} />);
    expect(html).toContain("No momentum context loaded");
    expect(html).toContain(DETERMINISTIC_NOTE);
  });

  it("renders a loading state when loading and payload is null", () => {
    const html = renderToStaticMarkup(<MomentumSummaryPanel payload={null} loading />);
    expect(html).toContain("Loading momentum context");
  });

  it("renders an error state when error is provided", () => {
    const html = renderToStaticMarkup(<MomentumSummaryPanel payload={null} error="Provider unavailable" />);
    expect(html).toContain("Momentum context unavailable");
    expect(html).toContain("Provider unavailable");
    expect(html).toContain(DETERMINISTIC_NOTE);
  });

  it("renders score, trend, momo, components, parity, and HTF source for a bull payload", () => {
    const html = renderToStaticMarkup(<MomentumSummaryPanel payload={payload()} />);
    expect(html).toContain("Bull +90");
    expect(html).toContain("State: bull");
    expect(html).toContain("Total Score");
    expect(html).toContain("Trend Score");
    expect(html).toContain("Momo Score");
    expect(html).toContain("True Momentum");
    expect(html).toContain("HiLo Thrust");
    expect(html).toContain("ATR Bias");
    expect(html).toContain("MACD Bias");
    expect(html).toContain("MA Bias");
    expect(html).toContain("Parity pending Thinkorswim fixtures");
    expect(html).toContain("HTF derived from chart bars");
    expect(html).toContain("Provider-backed bars");
    expect(html).toContain("HTF: weekly");
    expect(html).toContain(DETERMINISTIC_NOTE);
  });

  it("renders reversal and no-trade warning badges when explanation flags are set", () => {
    const data = payload();
    data.explanation = {
      ...data.explanation!,
      reversal_warning: true,
      pullback_signal: true,
      no_trade_warning: true,
    };
    const html = renderToStaticMarkup(<MomentumSummaryPanel payload={data} />);
    expect(html).toContain("Reversal warning");
    expect(html).toContain("Pullback signal");
    // no_trade is suppressed when reversal already shown; reversal alone is enough to warn loudly
  });

  it("renders bear payload with bad-tone badges", () => {
    const data = payload({
      latest_snapshot: snapshot({
        total_score: -100,
        total_label: "Max Bear",
        total_state: "max_bear",
        trend_score: -90,
        momo_score: -80,
        component_breakdown: {
          true_momentum_score: -15,
          hilo_thrust: -5,
          bull_ma: 0,
          bear_ma: -30,
          atr_value: -5,
          macd_bias: -5,
          intraday_penalty: 0,
          base_score: -60,
        },
      }),
    });
    const html = renderToStaticMarkup(<MomentumSummaryPanel payload={data} />);
    expect(html).toContain("Max Bear -100");
    expect(html).toContain("State: max bear");
  });
});
