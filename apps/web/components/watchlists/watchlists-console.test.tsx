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

vi.mock("@/lib/watchlists-api", () => ({
  createWatchlist: vi.fn(async () => ({ ok: true, data: null })),
  deleteWatchlist: vi.fn(async () => ({ ok: true, data: null })),
  fetchWatchlists: vi.fn(async () => ({ ok: true, data: [] })),
  updateWatchlist: vi.fn(async () => ({ ok: true, data: null })),
}));

import { WatchlistsConsole } from "@/components/watchlists/watchlists-console";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

const source = readFileSync(new URL("./watchlists-console.tsx", import.meta.url), "utf8");
const consoleShellSource = readFileSync(new URL("../console-shell.tsx", import.meta.url), "utf8");

describe("WatchlistsConsole", () => {
  it("renders the dedicated watchlist page shell", () => {
    const html = renderToStaticMarkup(<WatchlistsConsole />);

    expect(html).toContain("Watchlists");
    expect(html).toContain("Manage editable user-scoped symbol universes");
    expect(html).toContain("New watchlist");
    expect(html).toContain("Your watchlists");
    expect(html).toContain("Create watchlist");
  });

  it("contains user-safe watchlist management behavior", () => {
    expect(source).toContain("parseSymbols");
    expect(source).toContain("duplicates ignored");
    expect(source).toContain("unsupported");
    expect(source).toContain("Default watchlist");
    expect(source).toContain("watchlist-layout");
    expect(source).toContain("watchlist-symbol-chip");
    expect(source).toContain("Set default");
    expect(source).toContain("Used by Agent Mode");
    expect(source).toContain("editable starter list");
    expect(source).toContain("Delete");
    expect(source).toContain("does not auto-reseed the starter watchlist");
    expect(source).toContain("does not create orders");
  });

  it("keeps Watchlists under Workflow and Research in the required order", () => {
    const workflowIndex = consoleShellSource.indexOf('title: "Workflow"');
    const researchIndex = consoleShellSource.indexOf('title: "Research"');
    expect(workflowIndex).toBeGreaterThan(-1);
    expect(researchIndex).toBeGreaterThan(workflowIndex);
    expect(consoleShellSource.indexOf('["/watchlists", "Watchlists"]')).toBeGreaterThan(workflowIndex);
    expect(consoleShellSource.indexOf('["/watchlists", "Watchlists"]')).toBeLessThan(researchIndex);

    const symbol = consoleShellSource.indexOf('["/analyze", "Symbol Snapshot"]');
    const hacoContext = consoleShellSource.indexOf('["/charts/haco", "HACO Context"]');
    const hacoHeatmap = consoleShellSource.indexOf('["/haco-heatmap", "HACO Direction Heatmap"]');
    const momentum = consoleShellSource.indexOf('["/charts/momentum", "Momentum Intelligence"]');
    const momentumHeatmap = consoleShellSource.indexOf('["/momentum-heatmap", "Momentum Heatmap"]');
    expect(symbol).toBeLessThan(hacoContext);
    expect(hacoContext).toBeLessThan(hacoHeatmap);
    expect(hacoHeatmap).toBeLessThan(momentum);
    expect(momentum).toBeLessThan(momentumHeatmap);
  });
});
