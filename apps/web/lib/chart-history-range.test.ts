import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  CHART_HISTORY_RANGES,
  CHART_HISTORY_RANGE_IDS,
  CHART_HISTORY_RANGE_STORAGE_KEY,
  chartHistoryRangeOption,
  chartHistoryRangeToLookbackDays,
  defaultChartHistoryRange,
  isChartHistoryRangeId,
  readChartHistoryRangeFromStorage,
  validateChartHistoryRange,
  writeChartHistoryRangeToStorage,
} from "@/lib/chart-history-range";

describe("defaultChartHistoryRange", () => {
  it("is 1Y", () => {
    expect(defaultChartHistoryRange()).toBe("1Y");
  });
});

describe("CHART_HISTORY_RANGES table", () => {
  it("includes exactly 1M / 3M / 6M / 1Y / 2Y / 5Y in order", () => {
    expect(CHART_HISTORY_RANGE_IDS).toEqual(["1M", "3M", "6M", "1Y", "2Y", "5Y"]);
  });

  it("maps ids to the documented lookback days", () => {
    const byId = new Map(CHART_HISTORY_RANGES.map((o) => [o.id, o.lookbackDays]));
    expect(byId.get("1M")).toBe(31);
    expect(byId.get("3M")).toBe(93);
    expect(byId.get("6M")).toBe(186);
    expect(byId.get("1Y")).toBe(366);
    expect(byId.get("2Y")).toBe(732);
    expect(byId.get("5Y")).toBe(1830);
  });

  it("every option has a finite positive lookbackDays", () => {
    for (const option of CHART_HISTORY_RANGES) {
      expect(Number.isFinite(option.lookbackDays)).toBe(true);
      expect(option.lookbackDays).toBeGreaterThan(0);
    }
  });
});

describe("isChartHistoryRangeId / validateChartHistoryRange", () => {
  it("accepts every supported id", () => {
    for (const id of CHART_HISTORY_RANGE_IDS) {
      expect(isChartHistoryRangeId(id)).toBe(true);
      expect(validateChartHistoryRange(id)).toBe(id);
    }
  });

  it("rejects unknown / nullish / non-string values and falls back to the default", () => {
    expect(isChartHistoryRangeId("garbage")).toBe(false);
    expect(isChartHistoryRangeId(null)).toBe(false);
    expect(isChartHistoryRangeId(undefined)).toBe(false);
    expect(isChartHistoryRangeId(42)).toBe(false);
    expect(validateChartHistoryRange("garbage")).toBe("1Y");
    expect(validateChartHistoryRange(null)).toBe("1Y");
    expect(validateChartHistoryRange(undefined)).toBe("1Y");
    expect(validateChartHistoryRange(42)).toBe("1Y");
  });
});

describe("chartHistoryRangeToLookbackDays", () => {
  it("returns the documented day counts for known ids", () => {
    expect(chartHistoryRangeToLookbackDays("1M")).toBe(31);
    expect(chartHistoryRangeToLookbackDays("3M")).toBe(93);
    expect(chartHistoryRangeToLookbackDays("6M")).toBe(186);
    expect(chartHistoryRangeToLookbackDays("1Y")).toBe(366);
    expect(chartHistoryRangeToLookbackDays("2Y")).toBe(732);
    expect(chartHistoryRangeToLookbackDays("5Y")).toBe(1830);
  });

  it("falls back to 1Y's lookback for unknown ids", () => {
    expect(chartHistoryRangeToLookbackDays("garbage")).toBe(366);
    expect(chartHistoryRangeToLookbackDays(null)).toBe(366);
    expect(chartHistoryRangeToLookbackDays(undefined)).toBe(366);
  });

  it("never returns NaN/Infinity", () => {
    for (const value of ["garbage", null, undefined, 42, "1Y", "5Y"]) {
      const days = chartHistoryRangeToLookbackDays(value);
      expect(Number.isFinite(days)).toBe(true);
      expect(Number.isNaN(days)).toBe(false);
    }
  });
});

describe("chartHistoryRangeOption", () => {
  it("resolves to the matching option for known ids", () => {
    const option = chartHistoryRangeOption("3M");
    expect(option.id).toBe("3M");
    expect(option.label).toBe("3M");
    expect(option.lookbackDays).toBe(93);
  });

  it("falls back to the default option for unknown ids", () => {
    expect(chartHistoryRangeOption("garbage").id).toBe("1Y");
  });
});

describe("localStorage round-trip", () => {
  // The test runner is node-mode by default, so install a minimal
  // localStorage shim on ``globalThis`` for these assertions. Tests
  // that don't touch storage are unaffected.
  let originalWindow: unknown;
  beforeEach(() => {
    originalWindow = (globalThis as { window?: unknown }).window;
    const store = new Map<string, string>();
    (globalThis as { window?: unknown }).window = {
      localStorage: {
        getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
        setItem: (key: string, value: string) => {
          store.set(key, value);
        },
        removeItem: (key: string) => {
          store.delete(key);
        },
        clear: () => store.clear(),
      },
    };
  });

  afterEach(() => {
    (globalThis as { window?: unknown }).window = originalWindow;
  });

  it("returns the default when nothing is persisted", () => {
    expect(readChartHistoryRangeFromStorage()).toBe("1Y");
  });

  it("persists and reads back a valid id", () => {
    writeChartHistoryRangeToStorage("5Y");
    expect(readChartHistoryRangeFromStorage()).toBe("5Y");
  });

  it("ignores corrupt values and falls back to the default", () => {
    (globalThis as { window?: { localStorage: Storage } }).window!.localStorage.setItem(
      CHART_HISTORY_RANGE_STORAGE_KEY,
      "garbage",
    );
    expect(readChartHistoryRangeFromStorage()).toBe("1Y");
  });

  it("normalizes invalid input on write", () => {
    writeChartHistoryRangeToStorage("garbage");
    expect(readChartHistoryRangeFromStorage()).toBe("1Y");
  });
});
