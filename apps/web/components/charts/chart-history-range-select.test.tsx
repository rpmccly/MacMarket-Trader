import React from "react";
import type { ReactElement, ReactNode } from "react";
import { createRequire } from "module";
import { describe, expect, it, vi } from "vitest";

import {
  CHART_HISTORY_RANGE_SELECT_TEST_ID,
  ChartHistoryRangeSelect,
} from "@/components/charts/chart-history-range-select";
import { validateChartHistoryRange } from "@/lib/chart-history-range";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

/** Invoke the component as a plain function to extract the rendered
 *  <select>'s onChange handler. Simpler than mounting a DOM. */
function extractSelectOnChange(
  componentProps: Parameters<typeof ChartHistoryRangeSelect>[0],
): ((event: { target: { value: string } }) => void) | null {
  const rendered = ChartHistoryRangeSelect(componentProps);
  if (!React.isValidElement(rendered)) return null;
  const labelProps = rendered.props as { children?: ReactNode };
  const children = React.Children.toArray(labelProps.children);
  for (const child of children) {
    if (
      React.isValidElement(child) &&
      child.type === "select" &&
      typeof (child.props as { onChange?: unknown }).onChange === "function"
    ) {
      return (child.props as { onChange: (event: { target: { value: string } }) => void })
        .onChange;
    }
  }
  return null;
}

describe("ChartHistoryRangeSelect", () => {
  it("renders all six options labelled with their range ids", () => {
    const html = renderToStaticMarkup(
      <ChartHistoryRangeSelect value="1Y" onChange={() => undefined} />,
    );
    expect(html).toContain(`data-testid="${CHART_HISTORY_RANGE_SELECT_TEST_ID}"`);
    for (const range of ["1M", "3M", "6M", "1Y", "2Y", "5Y"]) {
      expect(html).toContain(`value="${range}"`);
    }
  });

  it("preselects the supplied value", () => {
    const html = renderToStaticMarkup(
      <ChartHistoryRangeSelect value="2Y" onChange={() => undefined} />,
    );
    expect(html).toMatch(/value="2Y"[^>]*selected/);
    expect(html).not.toMatch(/value="1Y"[^>]*selected/);
  });

  it("falls back to 1Y when given an invalid value", () => {
    const html = renderToStaticMarkup(
      <ChartHistoryRangeSelect value={"garbage" as never} onChange={() => undefined} />,
    );
    expect(html).toMatch(/value="1Y"[^>]*selected/);
  });

  it("renders an accessible label", () => {
    const html = renderToStaticMarkup(
      <ChartHistoryRangeSelect value="1Y" onChange={() => undefined} />,
    );
    expect(html.toLowerCase()).toContain("history range");
    expect(html).toContain('aria-label="History range"');
  });

  it("forwards an explicit testId override", () => {
    const html = renderToStaticMarkup(
      <ChartHistoryRangeSelect
        value="1Y"
        onChange={() => undefined}
        testId="custom-history-range"
      />,
    );
    expect(html).toContain('data-testid="custom-history-range"');
  });

  it("disables the select when disabled is true", () => {
    const html = renderToStaticMarkup(
      <ChartHistoryRangeSelect value="1Y" onChange={() => undefined} disabled />,
    );
    expect(html).toContain("disabled");
  });

  it("emits the selected range via onChange", () => {
    const onChange = vi.fn();
    const handler = extractSelectOnChange({ value: "1Y", onChange });
    expect(handler).not.toBeNull();
    handler!({ target: { value: "3M" } });
    expect(onChange).toHaveBeenCalledWith("3M");
  });

  it("normalizes an invalid selection back to the default on emission", () => {
    const onChange = vi.fn();
    const handler = extractSelectOnChange({ value: "1Y", onChange });
    handler!({ target: { value: "garbage" } });
    expect(onChange).toHaveBeenCalledWith(validateChartHistoryRange("garbage"));
  });
});
