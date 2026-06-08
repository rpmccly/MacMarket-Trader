import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchAtrChart } from "@/lib/atr-api";

const EMPTY_PAYLOAD = {
  symbol: "SPY",
  timeframe: "1D",
  candles: [],
  trailing_stop: [],
  markers: [],
  explanation: { current_state: "neutral" },
  timeframe_states: [],
  config: { trail_type: "modified", atr_period: 9, atr_factor: 2.9, first_trade: "long", average_type: "wilders" },
  data_source: "polygon",
  fallback_mode: false,
  notes: [],
};

describe("fetchAtrChart", () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch");

  beforeEach(() => fetchSpy.mockReset());
  afterEach(() => fetchSpy.mockReset());

  it("posts ATR settings + timeframes to /api/charts/atr", async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify(EMPTY_PAYLOAD), { status: 200, headers: { "content-type": "application/json" } }));

    await fetchAtrChart({
      symbol: "SPY",
      timeframe: "1D",
      history_range: "1Y",
      trail_type: "modified",
      atr_period: 9,
      atr_factor: 2.9,
      first_trade: "long",
      average_type: "wilders",
      multi_timeframes: ["1W", "1D", "4H", "1H", "30M"],
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe("/api/charts/atr");
    expect(init?.method).toBe("POST");
    expect(init?.cache).toBe("no-store");
    expect(init?.credentials).toBe("include");
    const body = JSON.parse(String(init?.body));
    expect(body.symbol).toBe("SPY");
    expect(body.timeframe).toBe("1D");
    expect(body.history_range).toBe("1Y");
    expect(body.trail_type).toBe("modified");
    expect(body.atr_period).toBe(9);
    expect(body.atr_factor).toBe(2.9);
    expect(body.multi_timeframes).toEqual(["1W", "1D", "4H", "1H", "30M"]);
  });

  it("throws AUTH_NOT_READY on 425", async () => {
    fetchSpy.mockResolvedValue(new Response("", { status: 425 }));
    await expect(fetchAtrChart({ symbol: "SPY", timeframe: "1D" })).rejects.toThrow("AUTH_NOT_READY");
  });
});
