import { describe, expect, it } from "vitest";

import { DEFAULT_MOMENTUM_HEATMAP_CATEGORIES, MOMENTUM_HEATMAP_STORAGE_KEY } from "@/lib/momentum-heatmap-defaults";

describe("momentum heatmap defaults", () => {
  it("keeps the configured localStorage key and workbook categories", () => {
    expect(MOMENTUM_HEATMAP_STORAGE_KEY).toBe("macmarket-momentum-heatmap-symbols-v1");
    expect(DEFAULT_MOMENTUM_HEATMAP_CATEGORIES.map((category) => category.categoryLabel)).toEqual([
      "INDEXES",
      "SECTORS",
      "MAJOR STOCKS",
      "BONDS + MISC",
      "COMMODITIES",
    ]);
  });

  it("preserves display labels while using mapped provider symbols", () => {
    const indexes = DEFAULT_MOMENTUM_HEATMAP_CATEGORIES.find((category) => category.categoryId === "indexes");
    expect(indexes?.rows).toContainEqual(expect.objectContaining({
      symbol: "VTI",
      displayName: "ALL U.S. - VTI",
      providerSymbol: "VTI",
    }));
    expect(indexes?.rows).toContainEqual(expect.objectContaining({
      symbol: "FXI",
      displayName: "China - FXI",
      providerSymbol: "FXI",
    }));
  });
});
