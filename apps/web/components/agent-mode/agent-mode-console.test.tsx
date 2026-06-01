import React from "react";
import type { ReactNode } from "react";
import { createRequire } from "module";
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/operator-ui", async () => {
  const ReactModule = await import("react");
  const wrap = (tag: string, className: string) =>
    ({ children, title, hint }: { children?: ReactNode; title?: string; hint?: string }) =>
      ReactModule.createElement(
        tag,
        { className },
        title ? ReactModule.createElement("strong", null, title) : null,
        hint ? ReactModule.createElement("p", null, hint) : null,
        children,
      );
  return {
    Card: wrap("section", "op-card"),
    EmptyState: wrap("div", "op-empty"),
    ErrorState: wrap("div", "op-error"),
    InlineFeedback: ({ message }: { message?: string }) => ReactModule.createElement("div", null, message),
    PageHeader: ({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) =>
      ReactModule.createElement("header", null, ReactModule.createElement("h1", null, title), subtitle ? ReactModule.createElement("p", null, subtitle) : null, actions),
    ResponsiveTable: ({ children }: { children: ReactNode }) => ReactModule.createElement("div", null, children),
    StatusBadge: ({ children }: { children: ReactNode }) => ReactModule.createElement("span", null, children),
  };
});

vi.mock("@/lib/agent-mode-api", () => ({
  fetchAgentModePerformance: vi.fn(async () => ({ ok: true, data: null })),
  fetchAgentModeRuns: vi.fn(async () => ({ ok: true, data: { items: [] } })),
  fetchAgentModeSettings: vi.fn(async () => ({ ok: true, data: null })),
  fetchAgentModeTrades: vi.fn(async () => ({ ok: true, data: { items: [] } })),
  fetchLatestAgentModeRun: vi.fn(async () => ({ ok: true, data: null })),
  runAgentMode: vi.fn(async () => ({ ok: true, data: null })),
  saveAgentModeSettings: vi.fn(async () => ({ ok: true, data: null })),
}));

import { AgentModeConsole } from "@/components/agent-mode/agent-mode-console";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

const source = readFileSync(new URL("./agent-mode-console.tsx", import.meta.url), "utf8");

describe("AgentModeConsole", () => {
  it("renders the protected paper-only console sections", () => {
    const html = renderToStaticMarkup(<AgentModeConsole />);

    expect(html).toContain("Agent Mode");
    expect(html).toContain("Paper-only performance cockpit");
    expect(html).toContain("Paper only. No live routing. Disable anytime.");
    expect(html).toContain("Overview");
    expect(html).toContain("Runs");
    expect(html).toContain("Trades");
    expect(html).toContain("Positions");
    expect(html).toContain("Performance");
    expect(html).toContain("Settings");
    expect(html).toContain("Latest run counts");
    expect(html).toContain("Grouped candidate queue");
    expect(html).toContain("Paper actions");
    expect(html).toContain("Data quality / warnings");
  });

  it("contains dry-run, enabled-run, settings, and error paths", () => {
    expect(source).toContain("Run dry-run");
    expect(source).toContain("Run enabled paper mode");
    expect(source).toContain("saveAgentModeSettings");
    expect(source).toContain("runAgentMode");
    expect(source).toContain("fetchLatestAgentModeRun");
    expect(source).toContain("fetchAgentModeRuns");
    expect(source).toContain("fetchAgentModeTrades");
    expect(source).toContain("fetchAgentModePerformance");
    expect(source).toContain("Agent Mode unavailable");
    expect(source).toContain("window.confirm");
    expect(source).toContain("Enabled paper run completed through Agent Mode paper lifecycle only.");
    expect(source).toContain("Dry-run completed. No paper orders were created.");
    expect(source).toContain("Enabled paper mode can create paper orders or close paper positions through the Agent Mode paper lifecycle.");
    expect(source).toContain("Executed");
  });

  it("contains performance cockpit tables and count consistency fields", () => {
    expect(source).toContain("paper opens");
    expect(source).toContain("paper closes");
    expect(source).toContain("cash/no trade");
    expect(source).toContain("executed actions");
    expect(source).toContain("Cumulative realized P&L");
    expect(source).toContain("Profit factor");
    expect(source).toContain("Run history");
    expect(source).toContain("Trade ledger");
    expect(source).toContain("Current open paper positions");
    expect(source).toContain("paperOpensExecuted");
    expect(source).toContain("paperClosesExecuted");
    expect(source).toContain("totalExecutedActions");
  });

  it("uses paper-safe language only", () => {
    expect(source).toContain("paper open");
    expect(source).toContain("paper close");
    expect(source).toContain("hold");
    expect(source).toContain("replace paper position");
    expect(source).toContain("cash/no trade");
    expect(source).not.toMatch(/buy now/i);
    expect(source).not.toMatch(/sell now/i);
    expect(source).not.toMatch(/financial advice/i);
  });
});
