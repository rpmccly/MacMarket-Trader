import { describe, expect, it } from "vitest";

import { momentumHeatmapScoreClass, MOMENTUM_HEATMAP_SCORE_RANGES } from "@/lib/momentum-heatmap-colors";

describe("momentum heatmap color rules", () => {
  it("covers the five configured score ranges", () => {
    expect(MOMENTUM_HEATMAP_SCORE_RANGES.map((range) => range.label)).toEqual([
      "80 to 100",
      "60 to <80",
      "40 to <60",
      "20 to <40",
      "0 to <20",
    ]);
  });

  it("maps representative scores to heatmap classes", () => {
    expect(momentumHeatmapScoreClass(90)).toBe("hm-score-bright-green");
    expect(momentumHeatmapScoreClass(70)).toBe("hm-score-green");
    expect(momentumHeatmapScoreClass(50)).toBe("hm-score-purple");
    expect(momentumHeatmapScoreClass(30)).toBe("hm-score-red");
    expect(momentumHeatmapScoreClass(10)).toBe("hm-score-bright-red");
    expect(momentumHeatmapScoreClass(null)).toBe("hm-score-unavailable");
  });
});
