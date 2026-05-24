import React from "react";
import type { ReactNode } from "react";
import { createRequire } from "module";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { WelcomeClient } from "@/components/welcome-client";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

describe("WelcomeClient", () => {
  it("renders the quick-start cheat sheet and current safety boundaries", () => {
    const markdown = readFileSync(resolve(process.cwd(), "..", "..", "docs", "alpha-user-welcome.md"), "utf8");
    const html = renderToStaticMarkup(<WelcomeClient markdown={markdown} />);

    expect(html).toContain("MacMarket Quick Start");
    expect(html).toContain("research and paper-trading console");
    expect(html).toContain("No live trading");
    expect(html).toContain("No broker routing");
    expect(html).toContain("Provider Health");
    expect(html).toContain("Market Risk Today");
    expect(html).toContain("Refresh the");
    expect(html).toContain("Recommendations");
    expect(html).toContain("Opportunity Intelligence");
    expect(html).toContain("risk-at-stop");
    expect(html).toContain("Active Position Review");
    expect(html).toContain("Option marks");
    expect(html).toContain("provider entitlement");
    expect(html).toContain("mark_unavailable");
    expect(html).toContain("Deterministic engines own approval");
    expect(html).toContain("paper order creation");
    expect(html).not.toContain("live broker routing");
    expect(html).not.toContain("automatic live execution");
  });

  it("documents Momentum Heatmap, Squeeze Pro, reporting, and expanded chart timeframes", () => {
    const markdown = readFileSync(resolve(process.cwd(), "..", "..", "docs", "alpha-user-welcome.md"), "utf8");
    const html = renderToStaticMarkup(<WelcomeClient markdown={markdown} />);

    expect(html).toContain("Momentum Intelligence");
    expect(html).toContain("/charts/momentum");
    expect(html).toContain("1W");
    expect(html).toContain("30M");
    expect(html).toContain("Squeeze Pro");
    expect(html).toContain("compression dots are implemented");
    expect(html).toContain("linear-regression momentum approximation");
    expect(html).toContain("Arrow logic is deferred");
    expect(html).toContain("Momentum Heatmap");
    expect(html).toContain("/momentum-heatmap");
    expect(html).toContain("workbook-style");
    expect(html).toContain("Long-Term Score");
    expect(html).toContain("Short-Term Score");
    expect(html).toContain("Strength %");
    expect(html).toContain("Deltas where available");
    expect(html).toContain("server-backed and account-scoped");
    expect(html).toContain("does not auto-refresh on load");
    expect(html).toContain("report preview");
    expect(html).toContain("CSV export");
    expect(html).toContain("Email report delivery is available only when");
    expect(html).toContain("Automatic scheduled delivery is not active unless");
    expect(html).toContain("Premarket reports mostly reflect the prior completed session");
    expect(html).toContain("Saved heatmap views");
    expect(html).toContain("Research dashboard only");
    expect(html).toContain("Not trade execution");
    expect(html).toContain("Not investment advice");
    expect(html).toContain("Intraday scores depend on latest available completed bars");
    expect(html).toContain("/recommendations");
    expect(html).toContain("/orders");
    expect(html).not.toContain("live broker routing");
    expect(html).not.toContain("automatic live execution");
    expect(html).not.toContain("automated execution support");
  });
});
