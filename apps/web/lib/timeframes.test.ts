import { describe, expect, it } from "vitest";

import { normalizeTimeframe, SUPPORTED_TIMEFRAME_OPTIONS, SUPPORTED_TIMEFRAME_VALUES } from "@/lib/timeframes";

describe("shared timeframe options", () => {
  it("includes weekly and 30-minute chart timeframes", () => {
    expect(SUPPORTED_TIMEFRAME_VALUES).toEqual(["1W", "1D", "4H", "1H", "30M"]);
    expect(SUPPORTED_TIMEFRAME_OPTIONS).toContainEqual({ value: "1W", label: "1W" });
    expect(SUPPORTED_TIMEFRAME_OPTIONS).toContainEqual({ value: "30M", label: "30M" });
  });

  it("normalizes unsupported values to daily", () => {
    expect(normalizeTimeframe("30m")).toBe("30M");
    expect(normalizeTimeframe("garbage")).toBe("1D");
  });
});
