import { describe, expect, it } from "vitest";

import {
  MOMENTUM_HEATMAP_COLOR_STORAGE_KEY,
  MOMENTUM_HEATMAP_SCORE_RANGES,
  momentumHeatmapScoreClass,
  momentumHeatmapScoreRange,
  normalizeMomentumHeatmapScoreRanges,
} from "@/lib/momentum-heatmap-colors";

describe("momentum heatmap color rules", () => {
  it("keeps the configured localStorage key", () => {
    expect(MOMENTUM_HEATMAP_COLOR_STORAGE_KEY).toBe("macmarket-momentum-heatmap-colors-v1");
  });

  it("covers the five configured negative-to-positive score ranges", () => {
    expect(MOMENTUM_HEATMAP_SCORE_RANGES.map((range) => [range.label, range.min, range.max])).toEqual([
      ["Bright green", 75, 100],
      ["Green", 25, 74.999],
      ["Purple", -24.999, 24.999],
      ["Red", -74.999, -25],
      ["Bright red", -100, -75],
    ]);
  });

  it("maps representative scores to heatmap classes", () => {
    expect(momentumHeatmapScoreClass(90)).toBe("hm-score-bright-green");
    expect(momentumHeatmapScoreClass(40)).toBe("hm-score-green");
    expect(momentumHeatmapScoreClass(0)).toBe("hm-score-purple");
    expect(momentumHeatmapScoreClass(-40)).toBe("hm-score-red");
    expect(momentumHeatmapScoreClass(-90)).toBe("hm-score-bright-red");
    expect(momentumHeatmapScoreClass(null)).toBe("hm-score-unavailable");
  });

  it("normalizes saved custom ranges without dropping default range identities", () => {
    const normalized = normalizeMomentumHeatmapScoreRanges([
      { id: "green", min: 20, max: 70, label: "Custom green", color: "#123456" },
    ]);
    expect(normalized).toHaveLength(5);
    expect(normalized.find((range) => range.id === "green")).toMatchObject({
      min: 20,
      max: 70,
      label: "Custom green",
      color: "#123456",
    });
    expect(momentumHeatmapScoreRange(-100, normalized)?.id).toBe("bright-red");
  });
});
