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

import {
  DataParityLab,
  cleanDataParityErrorMessage,
  formatDataParityValue,
  isSchwabConnected,
  shouldShowSchwabReconnect,
} from "@/components/admin/data-parity-lab";

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
    expect(html).toContain("Freshness / Delay");
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
    expect(source).toContain("Schwab is already primary");
    expect(source).toContain("Legacy Polygon/Massive");
    expect(source).toContain("no useful legacy-vs-Schwab comparison target");
    expect(source).not.toContain("SCHWAB_CLIENT_SECRET");
    expect(source).not.toContain("access_token");
    expect(source).not.toContain("refresh_token");
    expect(source).not.toContain("Authorization");
  });

  it("keeps the matrix focused on side-by-side raw, canonical, indicator, and TOS verdicts", () => {
    for (const label of [
      "Raw A close",
      "Raw B close",
      "Raw delta / tolerance",
      "Canonical A close",
      "Canonical B close",
      "Canonical delta / tolerance",
      "Indicators",
      "TOS Reference",
      "Root Cause",
      "Schwab asOf",
      "Timestamp delta",
      "Aligned latest",
      "alignment mode",
      "latest alignment label",
      "Current timestamp",
      "Schwab timestamp",
      "Interval start",
      "Interval end",
      "Timestamp convention",
      "Completed bars only",
      "diagnostic notes",
      "Verdict reason",
      "lag vs server",
      "lag vs expected",
    ]) {
      expect(source).toContain(label);
    }
    expect(source).toContain("Indicator side-by-side");
    expect(source).toContain("Provider freshness and delay by comparison row");
    expect(source).toContain("delayed_15_min_like");
    expect(source).toContain("market_session_state");
    expect(source).toContain("SideBySideBarsTable");
    expect(source).toContain("Raw provider bars");
    expect(source).toContain("Canonical MacMarket bars");
    expect(source).toContain("indicator_input_alignment");
  });

  it("does not push reconnect as the primary action while Schwab is connected", () => {
    const connected = {
      provider: "schwab_market_data",
      mode: "diagnostic",
      status: "ok",
      configured: true,
      credentials_present: true,
      oauth_connected: true,
      token_status: "connected",
      details: "connected",
    };

    expect(isSchwabConnected(connected)).toBe(true);
    expect(shouldShowSchwabReconnect(connected)).toBe(false);
    expect(source).toContain("Refresh Schwab status");
  });

  it("cleans raw HTML API errors before rendering feedback", () => {
    expect(
      cleanDataParityErrorMessage(
        "<!doctype html><html><body>404 - This page could not be found.</body></html>",
        "Data parity run failed.",
      ),
    ).toBe("Data parity run failed.");
    expect(cleanDataParityErrorMessage("Backend unavailable", "Data parity run failed.")).toBe("Backend unavailable");
  });

  it("renders diagnostic objects as readable text instead of object strings", () => {
    expect(formatDataParityValue({ error: "Schwab provider unavailable", code: "provider_unavailable" })).toBe(
      "Schwab provider unavailable",
    );
    const fallback = formatDataParityValue({ code: "provider_unavailable", details: ["missing quote"] });
    expect(fallback).toContain("provider_unavailable");
    expect(fallback).not.toContain("[object Object]");
  });
});
