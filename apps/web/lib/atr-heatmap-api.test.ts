import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchAtrHeatmap, downloadAtrHeatmapCsv } from "@/lib/atr-heatmap-api";

const HEATMAP = {
  rows: [],
  summary: { total: 0, long_count: 0, short_count: 0, mixed_count: 0, unavailable_count: 0 },
  timeframes: ["1W", "1D", "4H", "1H", "30M"],
  config: { trail_type: "modified", atr_period: 9, atr_factor: 2.9, first_trade: "long", average_type: "wilders" },
  generated_at: "2026-06-08T00:00:00+00:00",
  notes: [],
};

describe("atr-heatmap-api", () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch");
  beforeEach(() => fetchSpy.mockReset());
  afterEach(() => fetchSpy.mockReset());

  it("fetchAtrHeatmap posts symbols to /api/charts/atr-heatmap", async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify(HEATMAP), { status: 200, headers: { "content-type": "application/json" } }));
    await fetchAtrHeatmap({ symbols: ["SPY", "QQQ"], timeframes: ["1W", "1D", "4H", "1H", "30M"], atr_period: 9 });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe("/api/charts/atr-heatmap");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("include");
    const body = JSON.parse(String(init?.body));
    expect(body.symbols).toEqual(["SPY", "QQQ"]);
    expect(body.timeframes).toEqual(["1W", "1D", "4H", "1H", "30M"]);
  });

  it("downloadAtrHeatmapCsv posts to the CSV endpoint", async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify({ csv: "symbol,1w\n", filename: "atr-direction-heatmap-report.csv" }), { status: 200, headers: { "content-type": "application/json" } }));
    const result = await downloadAtrHeatmapCsv({ symbols: ["SPY"] });
    expect(fetchSpy.mock.calls[0][0]).toBe("/api/charts/atr-heatmap/report/csv");
    expect(result.filename).toBe("atr-direction-heatmap-report.csv");
  });

  it("throws AUTH_NOT_READY on 425", async () => {
    fetchSpy.mockResolvedValue(new Response("", { status: 425 }));
    await expect(fetchAtrHeatmap({ symbols: ["SPY"] })).rejects.toThrow("AUTH_NOT_READY");
  });
});
