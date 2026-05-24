import { describe, expect, it } from "vitest";

import {
  chunkMomentumHeatmapCategory,
  HEATMAP_REFRESH_ROW_CHUNK_SIZE,
  mergeMomentumHeatmapResponse,
  type MomentumHeatmapRequestCategory,
  type MomentumHeatmapResponse,
} from "@/lib/momentum-heatmap-api";

function row(id: string) {
  return { id, symbol: id, displayName: id, providerSymbol: id };
}

function response(categoryId: string, rowIds: string[]): MomentumHeatmapResponse {
  return {
    generated_at: `2026-05-23T12:00:0${rowIds.length}Z`,
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
          scores: {
            "1W": { value: 1, status: "ok" },
            "1D": { value: 1, status: "ok" },
            "4H": { value: 1, status: "ok" },
            "1H": { value: 1, status: "ok" },
            "30M": { value: 1, status: "ok" },
          },
          long_term_score: 1,
          short_term_score: 1,
          strength_percent: 1,
          squeeze: { value: null, status: "deferred" },
        })),
      },
    ],
  };
}

describe("Momentum Heatmap chunked refresh helpers", () => {
  it("chunks category row refreshes below the backend request row cap", () => {
    const category: MomentumHeatmapRequestCategory = {
      categoryId: "major-stocks",
      categoryLabel: "MAJOR STOCKS",
      rows: Array.from({ length: HEATMAP_REFRESH_ROW_CHUNK_SIZE + 3 }, (_, index) => row(`ROW${index}`)),
    };

    const chunks = chunkMomentumHeatmapCategory(category);

    expect(chunks).toHaveLength(2);
    expect(chunks[0].rows).toHaveLength(HEATMAP_REFRESH_ROW_CHUNK_SIZE);
    expect(chunks[1].rows).toHaveLength(3);
  });

  it("merges partial category results without wiping successful prior categories", () => {
    const previous = response("indexes", ["SPY"]);
    const merged = mergeMomentumHeatmapResponse(previous, response("sectors", ["XLK"]));

    expect(merged.categories.map((category) => category.categoryId)).toEqual(["indexes", "sectors"]);
    expect(merged.categories.find((category) => category.categoryId === "indexes")?.rows[0].id).toBe("SPY");
  });

  it("merges later chunks into the same category without losing prior chunk rows", () => {
    const previous = response("major-stocks", ["AAPL"]);
    const merged = mergeMomentumHeatmapResponse(previous, response("major-stocks", ["NVDA"]));

    expect(merged.categories[0].rows.map((mergedRow) => mergedRow.id)).toEqual(["AAPL", "NVDA"]);
  });

  it("preserves prior ok cells as stale when a later refresh fails that row", () => {
    const previous = response("indexes", ["SPY"]);
    const failed = response("indexes", ["SPY"]);
    failed.categories[0].rows[0].scores["1D"] = { value: null, status: "unsupported", reason: "unsupported_symbol_format" };
    failed.categories[0].rows[0].long_term_score = null;

    const merged = mergeMomentumHeatmapResponse(previous, failed);

    expect(merged.categories[0].rows[0].scores["1D"]).toMatchObject({
      value: 1,
      status: "ok",
      stale: true,
    });
    expect(merged.categories[0].rows[0].long_term_score).toBe(1);
  });
});
