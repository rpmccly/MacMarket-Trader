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

vi.mock("@/lib/atr-heatmap-api", () => ({
  fetchAtrHeatmap: vi.fn(async () => null),
  downloadAtrHeatmapCsv: vi.fn(async () => ({ csv: "", filename: "atr-direction-heatmap-report.csv" })),
}));

vi.mock("@/lib/watchlists-api", () => ({
  fetchWatchlists: vi.fn(async () => ({ ok: true, data: [] })),
}));

import Page from "@/app/(console)/atr-heatmap/page";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as { renderToStaticMarkup: (element: ReactNode) => string };
const source = readFileSync(new URL("./page.tsx", import.meta.url), "utf8");

describe("ATR Direction Heatmap page", () => {
  it("renders the heatmap page shell without crashing", () => {
    const html = renderToStaticMarkup(<Page />);
    expect(html).toContain("ATR Direction Heatmap");
    expect(html).toContain("Research only");
    expect(html).toContain("atr-heatmap-symbols");
  });

  it("wires symbol/watchlist input, refresh, and CSV export to the ATR heatmap API", () => {
    expect(source).toContain("fetchAtrHeatmap");
    expect(source).toContain("downloadAtrHeatmapCsv");
    expect(source).toContain("fetchWatchlists");
    expect(source).toContain("atr-heatmap-symbols");
    expect(source).toContain("atr-heatmap-watchlist");
    expect(source).toContain("Refresh");
    expect(source).toContain("Export CSV");
  });

  it("renders all heatmap columns", () => {
    expect(source).toContain("<th>Symbol</th>");
    expect(source).toContain("<th>1W</th>");
    expect(source).toContain("<th>1D</th>");
    expect(source).toContain("<th>4H</th>");
    expect(source).toContain("<th>1H</th>");
    expect(source).toContain("<th>30M</th>");
    expect(source).toContain("<th>Alignment</th>");
    expect(source).toContain("<th>Trailing stop</th>");
    expect(source).toContain("<th>Distance %</th>");
    expect(source).toContain("<th>Bars since flip</th>");
    expect(source).toContain("<th>Last flip</th>");
  });

  it("has collapsed advanced ATR settings and a responsive table wrapper", () => {
    expect(source).toContain("atr-heatmap-advanced");
    expect(source).toContain("<details");
    expect(source).toContain("ResponsiveTable");
    expect(source).toContain("op-table");
  });

  it("shows summary counts and the stop/risk explainer", () => {
    expect(source).toContain("LONG {summary?.long_count");
    expect(source).toContain("SHORT {summary?.short_count");
    expect(source).toContain("MIXED {summary?.mixed_count");
    expect(source).toContain("both the direction signal and the protective stop");
  });
});
