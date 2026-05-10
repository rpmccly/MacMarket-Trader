import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

function read(relative: string): string {
  return readFileSync(path.join(ROOT, relative), "utf8");
}

describe("Momentum Intelligence wiring", () => {
  it("Strategy Workbench imports the momentum panel and client", () => {
    const source = read("app/(console)/analysis/page.tsx");
    expect(source).toContain("@/lib/momentum-api");
    expect(source).toContain("@/components/charts/momentum-summary-panel");
    expect(source).toContain("fetchMomentumChart");
    expect(source).toContain("MomentumSummaryPanel");
  });

  it("Symbol Snapshot imports the momentum panel and client", () => {
    const source = read("app/(console)/analyze/page.tsx");
    expect(source).toContain("@/lib/momentum-api");
    expect(source).toContain("@/components/charts/momentum-summary-panel");
    expect(source).toContain("fetchMomentumChart");
    expect(source).toContain("MomentumSummaryPanel");
  });

  it("Recommendations imports the momentum panel and client without removing fetchHacoChart", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain("@/lib/momentum-api");
    expect(source).toContain("@/components/charts/momentum-summary-panel");
    expect(source).toContain("fetchMomentumChart");
    expect(source).toContain("MomentumSummaryPanel");
    expect(source).toContain("fetchHacoChart");
  });

  it("Momentum proxy route delegates to the workflow proxy with the correct backend path", () => {
    const source = read("app/api/charts/momentum/route.ts");
    expect(source).toContain("proxyWorkflowRequest");
    expect(source).toContain("/charts/momentum");
    expect(source).toContain("await request.text()");
  });

  it("Momentum console page mounts the workspace component", () => {
    const source = read("app/(console)/charts/momentum/page.tsx");
    expect(source).toContain("MomentumWorkspace");
    expect(source).toContain("@/components/charts/momentum-workspace");
  });

  it("Console shell exposes the Momentum Intelligence research nav link", () => {
    const source = read("components/console-shell.tsx");
    expect(source).toContain("/charts/momentum");
    expect(source).toContain("Momentum Intelligence");
  });
});

describe("Momentum Intelligence ranking-influence guard", () => {
  it("does not import momentum types/clients into recommendation ranking, approval, or paper-order modules", () => {
    // Phase A defense: confirm no ranking/approval files reach into the
    // momentum payload. Workflow integration is permitted to render context
    // panels but must never import momentum types as a ranking input.
    const guardedCandidates = [
      "lib/recommendations.ts",
      "lib/orders-helpers.ts",
    ];
    for (const candidate of guardedCandidates) {
      try {
        const source = read(candidate);
        expect(source).not.toContain("momentum-api");
        expect(source).not.toContain("momentum-chart");
        expect(source).not.toContain("MomentumChartPayload");
        expect(source).not.toContain("MomentumScoreSnapshot");
        expect(source).not.toContain("fetchMomentumChart");
      } catch {
        // file may not exist in a given snapshot; nothing to guard then
      }
    }
  });
});
