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

vi.mock("@/lib/daily-target-book-api", () => ({
  buildDailyTargetBook: vi.fn(async () => ({ ok: true, data: null })),
  fetchDailyTargetBookLatest: vi.fn(async () => ({ ok: true, data: null })),
}));

import { DailyTargetBookConsole, dailyTargetBookErrorMessage } from "@/components/daily-target-book/daily-target-book-console";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

const source = readFileSync(new URL("./daily-target-book-console.tsx", import.meta.url), "utf8");

describe("DailyTargetBookConsole", () => {
  it("renders the read-only target book cockpit sections", () => {
    const html = renderToStaticMarkup(<DailyTargetBookConsole />);

    expect(html).toContain("Daily Target Book");
    expect(html).toContain("Manual-review 5-position target book");
    expect(html).toContain("Read-only. No orders are created. Operator review required.");
    expect(html).toContain("Build controls");
    expect(html).toContain("Overview");
    expect(html).toContain("Target Book");
    expect(html).toContain("Current Paper Book");
    expect(html).toContain("Candidate Queue");
    expect(html).toContain("Differences / Required Review");
    expect(html).toContain("Decision Memo");
    expect(html).toContain("Data Quality");
  });

  it("contains build flow, grouped candidates, and current-vs-target review copy", () => {
    expect(source).toContain("buildDailyTargetBook");
    expect(source).toContain("fetchDailyTargetBookLatest");
    expect(source).toContain("Build target book");
    expect(source).toContain("Current Book vs Target Book");
    expect(source).toContain("candidateGroups");
    expect(source).toContain("supportingStrategies");
    expect(source).toContain("Target Book only");
    expect(source).toContain("Current Book only");
    expect(source).toContain("No target book yet");
    expect(source).toContain("Daily Target Book unavailable");
    expect(source).toContain("Daily Target Book build running");
    expect(source).toContain("Building Daily Target Book");
    expect(source).toContain("The previous read-only target book remains visible while this runs.");
  });

  it("uses read-only action wording and no execution controls", () => {
    expect(source).toContain("KEEP_REVIEW");
    expect(source).toContain("EXIT_REVIEW");
    expect(source).toContain("OPEN_REVIEW");
    expect(source).toContain("REPLACE_REVIEW");
    expect(source).toContain("SCALE_REVIEW");
    expect(source).toContain("CASH_NO_TRADE");
    expect(source).toContain("No paper orders were created and no positions were changed.");
    expect(source).not.toContain("Run enabled paper mode");
    expect(source).not.toContain("window.confirm");
    expect(source).not.toMatch(/buy now/i);
    expect(source).not.toMatch(/sell now/i);
  });

  it("sanitizes raw HTML route errors before showing operator feedback", () => {
    expect(
      dailyTargetBookErrorMessage(
        "<!doctype html><html><body>404 - This page could not be found.</body></html>",
        "Target book build failed.",
      ),
    ).toBe("Target book build failed.");
    expect(dailyTargetBookErrorMessage("Backend unavailable", "Target book build failed.")).toBe("Backend unavailable");
  });

  it("wires successful build responses into the rendered target book state", () => {
    expect(source).toContain("setResult(response.data)");
    expect(source).toContain("Target book built. No paper orders were created and no positions were changed.");
    expect(source).toContain("result.targetBook.map");
  });
});
