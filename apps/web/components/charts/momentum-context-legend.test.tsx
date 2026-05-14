import React from "react";
import type { ReactNode } from "react";
import { createRequire } from "module";
import { describe, expect, it } from "vitest";

import {
  MomentumContextLegend,
  MOMENTUM_CONTEXT_LEGEND_ENTRIES,
} from "@/components/charts/momentum-context-legend";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

describe("MomentumContextLegend", () => {
  it("renders the chart-annotation glossary terms and definitions", () => {
    const html = renderToStaticMarkup(<MomentumContextLegend initiallyOpen />);
    expect(html).toContain("Chart annotation glossary");
    expect(html).toContain("Rally context");
    expect(html).toContain("Pullback context");
    expect(html).toContain("Reversal warning");
    expect(html).toContain("Neutral → Bull");
    expect(html).toContain("Neutral → Bear");
    expect(html).toContain("No-trade warning");
    expect(html).toContain("True Momentum cross up");
    expect(html).toContain("HiLo confirmed");
    expect(html).toContain("HiLo deconfirmed");
  });

  it("renders the deterministic note framing the annotations as context only", () => {
    const html = renderToStaticMarkup(<MomentumContextLegend initiallyOpen />);
    expect(html).toContain("deterministic Momentum context only");
    expect(html).toContain("never trade approval");
  });

  it("never contains forbidden trade-action language", () => {
    const html = renderToStaticMarkup(<MomentumContextLegend initiallyOpen />).toLowerCase();
    for (const forbidden of [
      "approve trade",
      "auto approve",
      "route order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
    ]) {
      expect(html.includes(forbidden)).toBe(false);
    }
  });

  it("definitions in the canonical entry list are deterministic and non-actionable", () => {
    for (const entry of MOMENTUM_CONTEXT_LEGEND_ENTRIES) {
      const text = entry.definition.toLowerCase();
      for (const forbidden of ["buy ", "sell ", "enter ", "short ", "approve", "route order"]) {
        expect(text.includes(forbidden)).toBe(false);
      }
    }
  });

  it("respects a custom entry override", () => {
    const html = renderToStaticMarkup(
      <MomentumContextLegend
        initiallyOpen
        entries={[
          { id: "custom", term: "Custom term", definition: "Custom definition." },
        ]}
      />,
    );
    expect(html).toContain("Custom term");
    expect(html).toContain("Custom definition.");
    expect(html).not.toContain("Rally context");
  });
});
