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
    PageHeader: ({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) =>
      ReactModule.createElement(
        "header",
        null,
        ReactModule.createElement("h1", null, title),
        subtitle ? ReactModule.createElement("p", null, subtitle) : null,
        actions,
      ),
    ResponsiveTable: ({ children }: { children: ReactNode }) => ReactModule.createElement("div", null, children),
    StatusBadge: ({ children }: { children: ReactNode }) => ReactModule.createElement("span", null, children),
  };
});

import { DataParityLab } from "@/components/admin/data-parity-lab";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

const source = readFileSync(new URL("./data-parity-lab.tsx", import.meta.url), "utf8");

describe("DataParityLab", () => {
  it("renders the admin diagnostic shell with loading and empty states", () => {
    const html = renderToStaticMarkup(<DataParityLab />);

    expect(html).toContain("Market Data Parity Lab");
    expect(html).toContain("Schwab connection");
    expect(html).toContain("Run controls");
    expect(html).toContain("TOS manual reference");
    expect(html).toContain("No comparison run yet");
    expect(html).toContain("Snapshot history");
    expect(html).toContain("Read-only");
  });

  it("contains success, error, TOS row, and export paths without browser-visible secrets", () => {
    expect(source).toContain("setResult(response)");
    expect(source).toContain("setRunError");
    expect(source).toContain("Add TOS row");
    expect(source).toContain("createBlankTosReference()");
    expect(source).toContain("runDataParity");
    expect(source).toContain("buildDataParityCsv");
    expect(source).toContain("fetchDataParitySnapshot");
    expect(source).toContain("/api/admin/schwab/start");
    expect(source).not.toContain("SCHWAB_CLIENT_SECRET");
    expect(source).not.toContain("access_token");
    expect(source).not.toContain("refresh_token");
    expect(source).not.toContain("Authorization");
  });

  it("keeps the matrix focused on raw, canonical, indicator, and TOS verdicts", () => {
    for (const label of [
      "Raw bars verdict",
      "Canonical bars verdict",
      "True Momentum",
      "HACO",
      "HACOLT",
      "Hi/Lo",
      "Squeeze",
      "TOS Reference",
      "Root Cause",
    ]) {
      expect(source).toContain(label);
    }
    expect(source).toContain("Indicator payload comparison");
    expect(source).toContain("Raw provider bars");
    expect(source).toContain("Canonical MacMarket bars");
  });
});
