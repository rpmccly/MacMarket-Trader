import React from "react";
import type { ReactNode } from "react";
import { createRequire } from "module";
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) =>
    React.createElement("a", { href }, children),
}));

vi.mock("@/lib/api-client", () => ({
  fetchWorkflowApi: vi.fn(async () => ({ ok: true, data: null, items: [] })),
}));

vi.mock("@/components/symbol-entry-preview", () => ({
  SymbolEntryPreview: () => React.createElement("div", null, "symbol preview"),
}));

vi.mock("@/components/operator-ui", async () => {
  const ReactModule = await import("react");
  const wrap = (tag: string) =>
    ({ children, title, hint }: { children?: ReactNode; title?: string; hint?: string }) =>
      ReactModule.createElement(
        tag,
        null,
        title ? ReactModule.createElement("strong", null, title) : null,
        hint ? ReactModule.createElement("p", null, hint) : null,
        children,
      );
  return {
    Card: wrap("section"),
    EmptyState: wrap("div"),
    ErrorState: wrap("div"),
    InlineFeedback: ({ message }: { message?: string }) => ReactModule.createElement("div", null, message),
    PageHeader: ({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) =>
      ReactModule.createElement("header", null, ReactModule.createElement("h1", null, title), subtitle ? ReactModule.createElement("p", null, subtitle) : null, actions),
    ResponsiveTable: ({ children }: { children: ReactNode }) => ReactModule.createElement("div", null, children),
    StatusBadge: ({ children }: { children: ReactNode }) => ReactModule.createElement("span", null, children),
  };
});

import SchedulesPage from "./page";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

const source = readFileSync(new URL("./page.tsx", import.meta.url), "utf8");

describe("SchedulesPage report types", () => {
  it("renders the scheduled reports header and report type selector", () => {
    const html = renderToStaticMarkup(<SchedulesPage />);

    expect(html).toContain("Scheduled Reports");
    expect(html).toContain("Report type");
    expect(html).toContain("Strategy Candidate Scan");
    expect(html).toContain("Momentum Heatmap");
    expect(html).toContain("HACO Heatmap");
  });

  it("wires report_type payloads and keeps heatmap fields research-only", () => {
    expect(source).toContain('report_type: reportType');
    expect(source).toContain('timeframes: ["1W", "1D", "4H", "1H", "30M"]');
    expect(source).toContain('if (!selectedReportIsHeatmap)');
    expect(source).toContain("Custom recipients, market mode, and Top N are disabled for heatmap reports.");
    expect(source).toContain("Recipient: your signed-in account email");
    expect(source).toContain("research-only email");
  });

  it("displays type-aware active schedules, history summaries, and heatmap detail rows", () => {
    expect(source).toContain("report_type_label");
    expect(source).toContain("formatRunSummary");
    expect(source).toContain("Scheduled heatmap run rows");
    expect(source).toContain("heatmapCellValue");
    expect(source).toContain("Click to view run detail");
  });
});
