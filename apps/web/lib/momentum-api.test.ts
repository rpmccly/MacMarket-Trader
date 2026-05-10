import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMomentumChart } from "@/lib/momentum-api";

describe("fetchMomentumChart", () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch");

  beforeEach(() => {
    fetchSpy.mockReset();
  });
  afterEach(() => {
    fetchSpy.mockReset();
  });

  it("posts JSON to /api/charts/momentum with credentials and no-store cache", async () => {
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({
          symbol: "AAPL",
          timeframe: "1D",
          candles: [],
          true_momentum_line: [],
          true_momentum_ema_line: [],
          hilo_slowd_line: [],
          hilo_slowd_x_line: [],
          hilo_thrust_strip: [],
          score_strip: [],
          markers: [],
          latest_snapshot: null,
          explanation: null,
          data_source: "polygon",
          fallback_mode: false,
          higher_timeframe_source: "derived_from_chart_bars",
          parity_status: "pending_thinkorswim_fixture_validation",
          calculation_notes: [],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    await fetchMomentumChart({ symbol: "AAPL", timeframe: "1D" });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe("/api/charts/momentum");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string> | undefined)?.["Content-Type"]).toBe("application/json");
    expect(init?.cache).toBe("no-store");
    expect(init?.credentials).toBe("include");
    expect(typeof init?.body).toBe("string");
    expect(JSON.parse(String(init?.body))).toEqual({ symbol: "AAPL", timeframe: "1D" });
  });

  it("maps HTTP 425 to AUTH_NOT_READY", async () => {
    fetchSpy.mockResolvedValue(new Response(JSON.stringify({ detail: "auth init" }), { status: 425 }));
    await expect(fetchMomentumChart({ symbol: "AAPL", timeframe: "1D" })).rejects.toThrow("AUTH_NOT_READY");
  });

  it("throws a clear error for non-OK responses", async () => {
    fetchSpy.mockResolvedValue(new Response("nope", { status: 503 }));
    await expect(fetchMomentumChart({ symbol: "AAPL", timeframe: "1D" })).rejects.toThrow("Failed to load Momentum chart: 503");
  });
});
