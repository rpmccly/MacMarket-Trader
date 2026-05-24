import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildHacoHeatmapRefreshPayload,
  chunkHacoHeatmapCategory,
  HACO_HEATMAP_REFRESH_ROW_CHUNK_SIZE,
  hacoHeatmapSymbolDisplayParts,
  mergeHacoHeatmapResponse,
  refreshHacoHeatmapSnapshot,
  type HacoHeatmapRequestCategory,
  type HacoHeatmapResponse,
} from "@/lib/haco-heatmap-api";

function row(id: string) {
  return { id, symbol: id, displayName: id, providerSymbol: id };
}

function response(categoryId: string, rowIds: string[], status: "ok" | "unsupported" = "ok"): HacoHeatmapResponse {
  return {
    generated_at: `2026-05-24T12:00:0${rowIds.length}Z`,
    timeframes: ["1W", "1D", "4H", "1H", "30M"],
    categories: [
      {
        categoryId,
        categoryLabel: categoryId.toUpperCase(),
        rows: rowIds.map((id) => ({
          id,
          symbol: id,
          displayName: id,
          providerSymbol: id,
          states: {
            "1W": status === "ok" ? { value: "long", label: "LONG", status: "ok" } : { value: null, label: "—", status: "unsupported", reason: "unsupported_symbol_format" },
            "1D": status === "ok" ? { value: "long", label: "LONG", status: "ok" } : { value: null, label: "—", status: "unsupported", reason: "unsupported_symbol_format" },
            "4H": status === "ok" ? { value: "long", label: "LONG", status: "ok" } : { value: null, label: "—", status: "unsupported", reason: "unsupported_symbol_format" },
            "1H": status === "ok" ? { value: "long", label: "LONG", status: "ok" } : { value: null, label: "—", status: "unsupported", reason: "unsupported_symbol_format" },
            "30M": status === "ok" ? { value: "long", label: "LONG", status: "ok" } : { value: null, label: "—", status: "unsupported", reason: "unsupported_symbol_format" },
          },
          overall_bias: status === "ok" ? "LONG" : null,
          overall_alignment_percent: status === "ok" ? 100 : null,
          daily_context: status === "ok" ? "LONG" : null,
          short_term_bias: status === "ok" ? "LONG" : null,
          short_term_alignment_percent: status === "ok" ? 100 : null,
          tags: status === "ok" ? ["All LONG"] : ["Unsupported"],
        })),
      },
    ],
  };
}

describe("HACO Direction Heatmap chunked refresh helpers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("chunks category row refreshes below the backend request row cap", () => {
    const category: HacoHeatmapRequestCategory = {
      categoryId: "major-stocks",
      categoryLabel: "MAJOR STOCKS",
      rows: Array.from({ length: HACO_HEATMAP_REFRESH_ROW_CHUNK_SIZE + 3 }, (_, index) => row(`ROW${index}`)),
    };

    const chunks = chunkHacoHeatmapCategory(category);

    expect(chunks).toHaveLength(2);
    expect(chunks[0].rows).toHaveLength(HACO_HEATMAP_REFRESH_ROW_CHUNK_SIZE);
    expect(chunks[1].rows).toHaveLength(3);
  });

  it("strips saved-view metadata from refresh chunks before hitting the backend contract", () => {
    const category = {
      categoryId: "indexes",
      categoryLabel: "INDEXES",
      included: true,
      collapsed: false,
      rows: [
        {
          id: "indexes:SPY",
          categoryId: "indexes",
          categoryLabel: "INDEXES",
          symbol: "SPY",
          displayName: "SPY",
          providerSymbol: "SPY",
          originalSymbol: "SPY",
          workbookOrder: 0,
          enabled: true,
          unsupported: false,
          unsupportedReason: null,
        },
      ],
    } as unknown as HacoHeatmapRequestCategory;

    const payload = buildHacoHeatmapRefreshPayload(chunkHacoHeatmapCategory(category), "haco-profile-morning");

    expect(payload).toEqual({
      profileId: "haco-profile-morning",
      categories: [
        {
          categoryId: "indexes",
          categoryLabel: "INDEXES",
          rows: [{ id: "indexes:SPY", symbol: "SPY", displayName: "SPY", providerSymbol: "SPY" }],
        },
      ],
      timeframes: ["1W", "1D", "4H", "1H", "30M"],
    });
    expect(payload.categories[0]).not.toHaveProperty("included");
    expect(payload.categories[0].rows[0]).not.toHaveProperty("workbookOrder");
    expect(payload.categories[0].rows[0]).not.toHaveProperty("enabled");
  });

  it("merges partial category results without wiping prior categories", () => {
    const previous = response("indexes", ["SPY"]);
    const merged = mergeHacoHeatmapResponse(previous, response("sectors", ["XLK"]));

    expect(merged.categories.map((category) => category.categoryId)).toEqual(["indexes", "sectors"]);
    expect(merged.categories.find((category) => category.categoryId === "indexes")?.rows[0].id).toBe("SPY");
  });

  it("preserves prior ok HACO cells as stale when a later refresh fails that row", () => {
    const previous = response("indexes", ["SPY"]);
    const failed = response("indexes", ["SPY"], "unsupported");

    const merged = mergeHacoHeatmapResponse(previous, failed);

    expect(merged.categories[0].rows[0].states["1D"]).toMatchObject({
      value: "long",
      label: "LONG",
      status: "ok",
      stale: true,
    });
    expect(merged.categories[0].rows[0].overall_bias).toBe("LONG");
  });

  it("surfaces FastAPI 422 validation details as readable operator feedback", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      detail: [
        {
          loc: ["body", "categories", 0, "rows", 0, "workbookOrder"],
          msg: "Extra inputs are not permitted",
        },
      ],
    }), { status: 422, headers: { "Content-Type": "application/json" } })));

    await expect(refreshHacoHeatmapSnapshot([], "haco-profile-morning")).rejects.toThrow(
      "Request failed: 422 - body.categories.0.rows.0.workbookOrder: Extra inputs are not permitted",
    );
  });

  it("renders clean symbol labels without duplicating provider symbols", () => {
    expect(hacoHeatmapSymbolDisplayParts({ displayName: "SPY", providerSymbol: "SPY", symbol: "SPY" })).toEqual({
      label: "SPY",
      providerLabel: null,
    });
    expect(hacoHeatmapSymbolDisplayParts({ displayName: "ALL U.S. - VTI", providerSymbol: "VTI", symbol: "VTI" })).toEqual({
      label: "ALL U.S. - VTI",
      providerLabel: "VTI",
    });
    expect(hacoHeatmapSymbolDisplayParts({ displayName: "Japan - /NKD", providerSymbol: "/NKD", symbol: "/NKD" })).toEqual({
      label: "Japan - /NKD",
      providerLabel: "/NKD",
    });
  });
});
