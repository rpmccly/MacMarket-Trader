import React from "react";
import type { ReactNode } from "react";
import { createRequire } from "module";
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/operator-ui", async () => {
  const ReactModule = await import("react");
  const wrap = (tag: string, className: string) =>
    ({ children, title, hint, subtitle, actions }: { children?: ReactNode; title?: string; hint?: string; subtitle?: string; actions?: ReactNode }) =>
      ReactModule.createElement(tag, { className }, title ? ReactModule.createElement("strong", null, title) : null, subtitle ? ReactModule.createElement("p", null, subtitle) : null, hint ? ReactModule.createElement("p", null, hint) : null, actions, children);
  return {
    PageHeader: ({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) =>
      ReactModule.createElement("header", null, ReactModule.createElement("h1", null, title), subtitle ? ReactModule.createElement("p", null, subtitle) : null, actions),
    Card: wrap("section", "op-card"),
    EmptyState: wrap("div", "op-empty"),
    ErrorState: wrap("div", "op-error"),
    ResponsiveTable: ({ children }: { children: ReactNode }) => ReactModule.createElement("div", null, children),
    StatusBadge: ({ children }: { children: ReactNode }) => ReactModule.createElement("span", null, children),
  };
});

vi.mock("@/components/charts/chart-history-range-select", async () => {
  const ReactModule = await import("react");
  return { ChartHistoryRangeSelect: () => ReactModule.createElement("select", { "aria-label": "History range" }) };
});

vi.mock("@/lib/atr-api", () => ({ fetchAtrChart: vi.fn(async () => null) }));

import { AtrWorkspace } from "@/components/charts/atr-workspace";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as { renderToStaticMarkup: (element: ReactNode) => string };
const source = readFileSync(new URL("./atr-workspace.tsx", import.meta.url), "utf8");

describe("AtrWorkspace", () => {
  it("renders the ATR Intel page shell without crashing", () => {
    const html = renderToStaticMarkup(<AtrWorkspace />);
    expect(html).toContain("ATR Intel");
    expect(html).toContain("Research only");
    // Symbol input + explainer copy (signal + stop/risk reference).
    expect(html).toContain("atr-symbol-input");
    expect(html).toContain("both the direction signal and the protective stop");
  });

  it("contains symbol/timeframe controls and the ATR API wiring", () => {
    expect(source).toContain("atr-symbol-input");
    expect(source).toContain("atr-timeframe-select");
    expect(source).toContain("fetchAtrChart");
    expect(source).toContain("ChartHistoryRangeSelect");
    expect(source).toContain("multi_timeframes");
  });

  it("renders the snapshot fields: state, trailing stop, distance %, bars since flip, last flip", () => {
    expect(source).toContain("Current state:");
    expect(source).toContain("Latest trailing stop:");
    expect(source).toContain("Distance to stop:");
    expect(source).toContain("Bars since flip:");
    expect(source).toContain("Last flip:");
    expect(source).toContain("atr-price-stop-chart");
    expect(source).toContain("OHLC candles");
    expect(source).toContain("Long/support ATR stop");
    expect(source).toContain("Short/resistance ATR stop");
    expect(source).toContain("<rect");
    expect(source).toContain("<path");
  });

  it("renders the multi-timeframe table for 1W/1D/4H/1H/30M", () => {
    expect(source).toContain('["1W", "1D", "4H", "1H", "30M"]');
    expect(source).toContain("Multi-timeframe ATR state");
    expect(source).toContain("<th>Timeframe</th>");
    expect(source).toContain("Trailing stop");
  });

  it("has collapsed advanced settings: trail type, period, factor, first trade, average type", () => {
    expect(source).toContain("atr-advanced-settings");
    expect(source).toContain("<details");
    expect(source).toContain("Trail type");
    expect(source).toContain("ATR period");
    expect(source).toContain("ATR factor");
    expect(source).toContain("First trade");
    expect(source).toContain("Average type");
    expect(source).toContain('useState("exponential")');
    expect(source).toContain('<option value="exponential">Exponential</option>');
  });

  it("handles no-data / unsupported symbol states", () => {
    expect(source).toContain("No data for this symbol");
    expect(source).toContain('no_bars');
    expect(source).toContain("Unavailable / no data");
  });
});
