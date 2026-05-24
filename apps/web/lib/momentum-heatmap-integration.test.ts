import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

function read(relative: string): string {
  return readFileSync(path.join(ROOT, relative), "utf8");
}

describe("timeframe dropdown integration", () => {
  it("Analysis and chart workspaces use the shared timeframe options", () => {
    expect(read("app/(console)/analysis/page.tsx")).toContain("SUPPORTED_TIMEFRAME_OPTIONS");
    expect(read("components/charts/haco-workspace.tsx")).toContain("SUPPORTED_TIMEFRAME_OPTIONS");
    expect(read("components/charts/momentum-workspace.tsx")).toContain("SUPPORTED_TIMEFRAME_OPTIONS");
  });
});

describe("Momentum Heatmap page integration", () => {
  it("exposes the Research nav link and proxy route", () => {
    expect(read("components/console-shell.tsx")).toContain("/momentum-heatmap");
    expect(read("components/console-shell.tsx")).toContain("Momentum Heatmap");
    expect(read("app/api/charts/momentum-heatmap/route.ts")).toContain("/charts/momentum-heatmap");
    expect(read("app/api/user/momentum-heatmap/profile/route.ts")).toContain("/user/momentum-heatmap/profile");
    expect(read("app/api/user/momentum-heatmap/profile/duplicate/route.ts")).toContain("/user/momentum-heatmap/profile/duplicate");
    expect(read("app/api/user/momentum-heatmap/refresh/route.ts")).toContain("/user/momentum-heatmap/refresh");
  });

  it("includes refresh, visibility, add/remove, formula, storage, and squeeze copy", () => {
    const source = read("app/(console)/momentum-heatmap/page.tsx");
    expect(source).toContain("Refresh visible heatmap");
    expect(source).toContain("Include in refresh");
    expect(source).toContain("Collapse");
    expect(source).toContain("Expand");
    expect(source).toContain("Display label");
    expect(source).toContain("Remove");
    expect(source).toContain("macmarket-momentum-heatmap-symbols-v1");
    expect(source).toContain("macmarket-momentum-heatmap-colors-v1");
    expect(source).toContain("Score color ranges");
    expect(source).toContain("Save/update ranges");
    expect(source).toContain("Reset color ranges to default");
    expect(source).toContain("chunkMomentumHeatmapCategory");
    expect(source).toContain("mergeMomentumHeatmapResponse");
    expect(source).toContain("fetchMomentumHeatmapProfile");
    expect(source).toContain("refreshMomentumHeatmapSnapshot");
    expect(source).toContain("Server profile");
    expect(source).toContain("Active view");
    expect(source).toContain("momentum-heatmap-view-selector");
    expect(source).toContain("Create new view");
    expect(source).toContain("Rename view");
    expect(source).toContain("Duplicate view");
    expect(source).toContain("Reset seeded view to defaults");
    expect(source).toContain("Delete custom view");
    expect(source).toContain("not automatically imported");
    expect(source).toContain("Long-Term Score = (Weekly + Daily) / 2");
    expect(source).toContain("Short-Term Score = (4HR + 1HR + 30M) / 3");
    expect(source).toContain("Strength % = (Weekly*3 + Daily*3 + 4HR + 1HR + 30M) / 9");
    expect(source).toContain("Squeeze column now summarizes MacMarket Squeeze Pro research states.");
    expect(source).toContain("SqueezeCell");
  });

  it("includes server-backed operator controls for sorting, filtering, deltas, reports, and scheduling", () => {
    const source = read("app/(console)/momentum-heatmap/page.tsx");
    expect(source).toContain("hm-command-center");
    expect(source).toContain("momentum-heatmap-command-center");
    expect(source).toContain("secondaryPanel");
    expect(source).toContain("Manage symbols");
    expect(source).toContain("Score color ranges");
    expect(source).toContain("Report settings");
    expect(source).toContain("Schedule settings");
    expect(source).toContain("Refresh this category");
    expect(source).toContain("momentum-heatmap-refresh-progress");
    expect(source).toContain("momentum-heatmap-status-strip");
    expect(source).toContain("Sort selector");
    expect(source).toContain("Strength % high to low");
    expect(source).toContain("Bullish alignment");
    expect(source).toContain("Bearish alignment");
    expect(source).toContain("Long-term bullish + short-term weak");
    expect(source).toContain("Long-term weak + short-term improving");
    expect(source).toContain("Show rows changed since last snapshot");
    expect(source).toContain("Show positive delta only");
    expect(source).toContain("Show negative delta only");
    expect(source).toContain("Toggle delta columns");
    expect(source).toContain("Deltas need two successful snapshots.");
    expect(source).toContain("momentum-heatmap-delta-notice");
    expect(source).toContain("Average Strength %");
    expect(source).toContain("Generate report preview");
    expect(source).toContain("Download CSV");
    expect(source).toContain("Email report now");
    expect(source).toContain("Email recipients");
    expect(source).toContain("Scheduled report settings");
    expect(source).toContain("Schedule preferences apply to active view");
    expect(source).toContain("7:00 AM ET");
    expect(source).toContain("10:15 AM ET");
    expect(source).toContain("3:30 PM ET");
    expect(source).toContain("4:30 PM ET");
  });

  it("keeps saved heatmap view names and profile-scoped API calls visible in the implementation", () => {
    const source = read("app/(console)/momentum-heatmap/page.tsx");
    const api = read("lib/momentum-heatmap-api.ts");
    expect(source).toContain("switchProfile");
    expect(source).toContain("loadSnapshotAndScheduleForProfile");
    expect(api).toContain("profileQuery");
    expect(api).toContain("createMomentumHeatmapProfile");
    expect(api).toContain("duplicateMomentumHeatmapProfile");
    expect(api).toContain("deleteMomentumHeatmapProfile");
    expect(api).toContain("resetMomentumHeatmapProfile");
    expect(api).toContain("refreshMomentumHeatmapSnapshot(categories: MomentumHeatmapRequestCategory[], profileId?: string)");
    expect(read("../../src/macmarket_trader/charts/momentum_heatmap_defaults.py")).toContain("Morning Macro");
    expect(read("../../src/macmarket_trader/charts/momentum_heatmap_defaults.py")).toContain("Growth Leaders");
    expect(read("../../src/macmarket_trader/charts/momentum_heatmap_defaults.py")).toContain("Commodities");
    expect(read("../../src/macmarket_trader/charts/momentum_heatmap_defaults.py")).toContain("Pullback Watch");
    expect(read("../../src/macmarket_trader/charts/momentum_heatmap_defaults.py")).toContain("Custom Watchlist");
  });
});
