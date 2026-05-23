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
    expect(source).toContain("Long-Term Score = (Weekly + Daily) / 2");
    expect(source).toContain("Short-Term Score = (4HR + 1HR + 30M) / 3");
    expect(source).toContain("Strength % = (Weekly*3 + Daily*3 + 4HR + 1HR + 30M) / 9");
    expect(source).toContain("Squeeze column deferred until approved squeeze algorithm is added.");
  });
});
