import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildDataParityCsv,
  createBlankTosReference,
  fetchDataParitySnapshots,
  normalizeTosReferenceRows,
  parseParitySymbols,
  runDataParity,
  type DataParityRunResponse,
} from "@/lib/data-parity-api";

describe("data parity API helpers", () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch");

  beforeEach(() => {
    fetchSpy.mockReset();
  });

  afterEach(() => {
    fetchSpy.mockReset();
  });

  it("dedupes and uppercases pasted symbol lists", () => {
    expect(parseParitySymbols("spy, qqq\nSPY mtum")).toEqual(["SPY", "QQQ", "MTUM"]);
  });

  it("normalizes optional TOS reference rows", () => {
    const row = createBlankTosReference();
    row.symbol = " mtum ";
    row.timeframe = "1w";
    row.trueMomentumScore = "100" as unknown as number;
    row.hacoDirection = " LONG ";
    row.hiLoValue = "" as unknown as number;

    expect(normalizeTosReferenceRows([row])).toEqual([
      {
        symbol: "MTUM",
        timeframe: "1W",
        trueMomentumScore: 100,
        hacoDirection: "LONG",
        hacoLatestFlip: null,
        hacoltDirection: null,
        hiLoState: null,
        hiLoValue: null,
        squeezeState: null,
        squeezeHistogram: null,
        notes: "",
      },
    ]);
  });

  it("posts the run payload to the admin proxy route", async () => {
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({
          runId: "dpar_test",
          asOf: "2026-05-29T12:00:00Z",
          providers: { current: {}, candidate: { provider: "schwab_market_data", token_status: "connected" } },
          request: {},
          summary: { total: 1, match: 1 },
          results: [],
          warnings: [],
          errors: [],
          readOnly: true,
          brokerRoutingEnabled: false,
          productionProviderUnchanged: true,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    await runDataParity({
      symbols: ["SPY"],
      timeframes: ["1D"],
      lookbackBars: 250,
      sessionPolicy: "regular_hours",
      includeExtendedHours: false,
      saveSnapshot: true,
      tosReferences: [],
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe("/api/admin/data-parity/run");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      symbols: ["SPY"],
      timeframes: ["1D"],
      lookbackBars: 250,
      sessionPolicy: "regular_hours",
      includeExtendedHours: false,
      saveSnapshot: true,
      tosReferences: [],
    });
  });

  it("returns a clean message when the proxy returns an HTML 404 page", async () => {
    fetchSpy.mockResolvedValue(
      new Response("<!doctype html><html><body>404 - This page could not be found.</body></html>", {
        status: 404,
        headers: { "content-type": "text/html; charset=utf-8" },
      }),
    );

    await expect(
      runDataParity({
        symbols: ["SPY"],
        timeframes: ["1D"],
        lookbackBars: 250,
        sessionPolicy: "regular_hours",
        includeExtendedHours: false,
        saveSnapshot: false,
        tosReferences: [],
      }),
    ).rejects.toThrow("Route not found");
  });

  it("loads snapshot summaries through the proxy route", async () => {
    fetchSpy.mockResolvedValue(
      new Response(
        JSON.stringify({
          snapshots: [
            {
              runId: "dpar_one",
              createdAt: "2026-05-29T12:00:00Z",
              providerCurrent: "polygon",
              providerCandidate: "schwab",
              symbols: ["SPY"],
              timeframes: ["1D"],
              summary: { total: 1, match: 1 },
            },
          ],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const snapshots = await fetchDataParitySnapshots();

    expect(fetchSpy).toHaveBeenCalledWith("/api/admin/data-parity/snapshots", expect.any(Object));
    expect(snapshots[0].runId).toBe("dpar_one");
  });

  it("builds CSV exports without dropping verdicts", () => {
    const response: DataParityRunResponse = {
      runId: "dpar_csv",
      asOf: "2026-05-29T12:00:00Z",
      providers: { current: {}, candidate: { provider: "schwab_market_data", mode: "diagnostic", status: "ok", configured: true, credentials_present: true, oauth_connected: true, token_status: "connected", details: "connected" } },
      request: {},
      summary: { total: 1, match: 1 },
      results: [
        {
          symbol: "SPY",
          timeframe: "1D",
          rawBars: { verdict: "match", latest_current: { close: 100 }, latest_candidate: { close: 100 } },
          canonicalBars: {
            verdict: "match",
            alignment_mode: "normalized_session_date",
            latest_common_alignment_label: "2026-05-29",
            latest_common_current_raw_timestamp: "2026-05-29T04:00:00+00:00",
            latest_common_candidate_raw_timestamp: "2026-05-29T05:00:00+00:00",
            latest_alignment_key_match: true,
            latest_current: { close: 100 },
            latest_candidate: { close: 100 },
            comparison_diagnostics: { notes: ["extended_hours_not_an_obvious_cause"] },
          },
          indicators: { verdict: "match", current: {}, candidate: {}, mismatches: [] },
          tosReference: { provided: false, verdict: "not_provided", mismatches: [] },
          rootCause: "match",
          warnings: [],
          errors: [],
        },
      ],
      warnings: [],
      errors: [],
      readOnly: true,
      brokerRoutingEnabled: false,
      productionProviderUnchanged: true,
    };

    const csv = buildDataParityCsv(response);
    expect(csv).toContain('"symbol","timeframe","raw_bars"');
    expect(csv).toContain('"current_provider_lag_minutes_vs_server_run_time"');
    expect(csv).toContain('"schwab_lag_minutes_vs_expected_market_bar"');
    expect(csv).toContain('"latest_common_aligned_timestamp_new_york"');
    expect(csv).toContain('"canonical_alignment_mode"');
    expect(csv).toContain('"canonical_latest_alignment_label"');
    expect(csv).toContain('"normalized_session_date"');
    expect(csv).toContain('"2026-05-29"');
    expect(csv).toContain('"SPY","1D","match","match","match","not_provided","match"');
  });
});
