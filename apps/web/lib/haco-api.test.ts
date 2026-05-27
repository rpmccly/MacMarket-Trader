import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchHacoChart } from "@/lib/haco-api";

describe("fetchHacoChart", () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch");

  beforeEach(() => {
    fetchSpy.mockReset();
  });

  afterEach(() => {
    fetchSpy.mockReset();
  });

  it("forwards the operator-selected 30M timeframe without coercion", async () => {
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({
          symbol: "SPY",
          timeframe: "30M",
          candles: [],
          heikin_ashi_candles: [],
          markers: [],
          haco_strip: [],
          hacolt_strip: [],
          explanation: {
            current_haco_state: "neutral",
            latest_flip: "none",
            latest_flip_bars_ago: null,
            current_hacolt_direction: "flat",
          },
          data_source: "polygon",
          fallback_mode: false,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    await fetchHacoChart({
      symbol: "SPY",
      timeframe: "30M",
      include_heikin_ashi: true,
      history_range: "1M",
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe("/api/charts/haco");
    expect(init?.method).toBe("POST");
    expect(init?.cache).toBe("no-store");
    expect(init?.credentials).toBe("include");
    expect(JSON.parse(String(init?.body))).toEqual({
      symbol: "SPY",
      timeframe: "30M",
      include_heikin_ashi: true,
      history_range: "1M",
    });
  });
});
