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
  fetchAgentModeStatus: vi.fn(async () => ({ ok: true, data: null })),
  fetchAgentModeTrades: vi.fn(async () => ({ ok: true, data: { items: [] } })),
  fetchAgentProfiles: vi.fn(async () => ({ ok: true, data: { profiles: [] } })),
  fetchLatestAgentModeRun: vi.fn(async () => ({ ok: true, data: null })),
  runAgentMode: vi.fn(async () => ({ ok: true, data: null })),
  saveAgentModeSettings: vi.fn(async () => ({ ok: true, data: null })),
  createAgentProfile: vi.fn(async () => ({ ok: true, data: null })),
  updateAgentProfile: vi.fn(async () => ({ ok: true, data: null })),
  deleteAgentProfile: vi.fn(async () => ({ ok: true, data: { status: "deleted" } })),
  setDefaultAgentProfile: vi.fn(async () => ({ ok: true, data: null })),
  testAgentModeNotification: vi.fn(async () => ({ ok: true, data: { attempts: [] } })),
}));

vi.mock("@/lib/watchlists-api", () => ({
  fetchWatchlists: vi.fn(async () => ({ ok: true, data: [] })),
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

    expect(html).toContain("Agent Profiles");
    expect(html).toContain("Paper-only cockpit for your Standard, HACO Direction, True Momentum, and Hybrid agents.");
    expect(html).toContain("Paper only. No live routing. Disable anytime.");
    expect(html).toContain("Your agents");
    expect(html).toContain("All agents");
    expect(html).toContain("New agent");
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
    expect(source).toContain("fetchAgentModeStatus");
    expect(source).toContain("fetchAgentModeRuns");
    expect(source).toContain("fetchAgentModeTrades");
    expect(source).toContain("fetchAgentModePerformance");
    expect(source).toContain("fetchWatchlists");
    expect(source).toContain("testAgentModeNotification");
    expect(source).toContain("Agent Mode unavailable");
    expect(source).toContain("window.confirm");
    expect(source).toContain("Enabled paper run completed through Agent Mode paper lifecycle only.");
    expect(source).toContain("Dry-run completed. No paper orders were created.");
    expect(source).toContain("Enabled paper mode can create paper orders or close paper positions through the Agent Mode paper lifecycle.");
    expect(source).toContain("Executed");
  });

  it("contains performance cockpit tables and count consistency fields", () => {
    expect(source).toContain("Schedule status");
    expect(source).toContain("Scheduler health");
    expect(source).toContain("Last scheduler check");
    expect(source).toContain("Due now");
    expect(source).toContain("Last scheduled result");
    expect(source).toContain("Resolved symbols");
    expect(source).toContain("scheduler_due_now");
    expect(source).toContain("scheduler_last_check_result");
    expect(source).toContain("Time until next run");
    expect(source).toContain("Your browser timezone differs from the Agent Mode timezone");
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

  it("contains operational-control settings and notification fields", () => {
    expect(source).toContain("Selected watchlist");
    expect(source).toContain("Manual override symbols");
    expect(source).toContain("Resolved run universe");
    expect(source).toContain("This run will analyze:");
    expect(source).toContain("Max dollars/trade");
    expect(source).toContain("Max new trades/run");
    expect(source).toContain("Sizing preview");
    expect(source).toContain("Notification preferences");
    expect(source).toContain("single Agent Mode run digest");
    expect(source).toContain("Allows Agent Mode to review existing open positions");
    expect(source).toContain("Allows more than one open Agent position");
    expect(source).toContain("Test SMS");
    expect(source).toContain("Twilio secrets stay server-only");
    expect(source).toContain("last_30_days");
  });

  it("contains performance and positions polish fields", () => {
    expect(source).toContain("Cost basis");
    expect(source).toContain("Market value");
    expect(source).toContain("agent-performance-hero");
    expect(source).toContain("Percent return");
    expect(source).toContain("No Agent Mode performance yet");
  });

  it("contains the agent-profiles cockpit and agent-type controls", () => {
    // Profile CRUD + scoping wiring.
    expect(source).toContain("fetchAgentProfiles");
    expect(source).toContain("createAgentProfile");
    expect(source).toContain("updateAgentProfile");
    expect(source).toContain("deleteAgentProfile");
    expect(source).toContain("setDefaultAgentProfile");
    expect(source).toContain("scopeAll");
    expect(source).toContain("selectedProfileId");
    // Per-profile controls and the four templates.
    expect(source).toContain("New agent");
    expect(source).toContain("Make default");
    expect(source).toContain("Kill switch");
    expect(source).toContain("Standard Strategy");
    expect(source).toContain("HACO Direction");
    expect(source).toContain("True Momentum");
    expect(source).toContain("Hybrid");
    // Agent-type configuration.
    expect(source).toContain("HACO direction mode");
    expect(source).toContain("True Momentum trigger mode");
    expect(source).toContain("Require HACO long filter");
    expect(source).toContain("Require True Momentum confirmation");
    expect(source).toContain("Strategy families this agent may trade");
    // Paper-only guardrails on the new surfaces.
    expect(source).toContain("Agent Mode never creates paper shorts");
    expect(source).toContain("Review-only never opens paper trades");
    // Paper-open capability + missing-watchlist indicators.
    expect(source).toContain("paperOpenCapability");
    expect(source).toContain("Opens paper longs");
    expect(source).toContain("Review only (no paper opens)");
    expect(source).toContain("No watchlist selected");
    expect(source).toContain("Resolved symbols:");
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

  it("surfaces the position-ownership boundary in the run preview", () => {
    // Ownership labels + the explicit "will not close what it does not own" copy.
    expect(source).toContain("ownership-boundary-note");
    expect(source).toContain("It will not close positions it does not own");
    expect(source).toContain("formatOwnerLabel");
    expect(source).toContain("position_owner");
    expect(source).toContain("This agent");
    expect(source).toContain("Another agent");
    expect(source).toContain("Manual trade");
    // Owner column header in the paper-actions table.
    expect(source).toContain("<th>Owner</th>");
  });

  it("surfaces the market-closed (weekend/holiday) label in the run preview", () => {
    expect(source).toContain("market-closed-note");
    expect(source).toContain("Market closed");
    expect(source).toContain("skipped on weekends and US market holidays");
    expect(source).toContain("marketClosed");
    expect(source).toContain("next_trading_day");
  });
});
