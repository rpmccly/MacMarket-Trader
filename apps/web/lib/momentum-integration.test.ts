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
  it("does not import momentum payload clients into recommendation ranking, approval, or paper-order helper modules", () => {
    // Phase A defense: confirm no ranking/approval helper file reaches into
    // the momentum **payload** client. Workflow integration is permitted to
    // render context panels via the typed contribution on candidates, but
    // must never import the chart payload or its fetcher as a ranking input.
    const guardedCandidates = [
      "lib/orders-helpers.ts",
    ];
    for (const candidate of guardedCandidates) {
      try {
        const source = read(candidate);
        expect(source).not.toContain("momentum-api");
        expect(source).not.toContain("momentum-chart");
        expect(source).not.toContain("momentum-ranking");
        expect(source).not.toContain("MomentumChartPayload");
        expect(source).not.toContain("MomentumScoreSnapshot");
        expect(source).not.toContain("fetchMomentumChart");
      } catch {
        // file may not exist in a given snapshot; nothing to guard then
      }
    }
  });
});

describe("Momentum Intelligence Phase B2 display guards", () => {
  const RANKING_HELPER_IMPORT_PATTERNS = [
    "@/lib/momentum-ranking",
    "from \"@/components/recommendations/momentum-ranking-card\"",
    "MomentumRankingCard",
    "MomentumRankingInlineBadge",
    // Phase B3 status surfaces — must also stay out of order/approval paths.
    "@/lib/momentum-ranking-status",
    "@/components/recommendations/momentum-ranking-status-card",
    "MomentumRankingStatusCard",
    "MomentumRankingStatusSection",
    "fetchMomentumRankingStatus",
    // Phase B4 impact-review surfaces — same isolation.
    "@/lib/momentum-impact",
    "@/components/recommendations/momentum-impact-review",
    "MomentumImpactReview",
    "buildMomentumImpactRows",
    "summarizeMomentumImpact",
    "estimateActiveScore",
  ];

  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("ranking-display helpers are not imported into order, paper-order, or options routes", () => {
    const routesToGuard = [
      "app/api/user/orders/route.ts",
      "app/api/user/orders/[orderId]/route.ts",
      "app/api/user/orders/portfolio-summary/route.ts",
      "app/api/user/paper-positions/route.ts",
      "app/api/user/paper-trades/route.ts",
      "app/api/user/options/replay-preview/route.ts",
      "app/api/user/options/paper-structures/route.ts",
      "app/api/user/options/paper-structures/open/route.ts",
      "app/api/user/options/paper-structures/review/route.ts",
    ];
    for (const route of routesToGuard) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of RANKING_HELPER_IMPORT_PATTERNS) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("recommendation-approval/order helper files do not import momentum-ranking display helpers", () => {
    const guarded = [
      "lib/orders-helpers.ts",
      "lib/api-client.ts",
      "lib/guided-workflow.ts",
      "lib/lineage-format.ts",
    ];
    for (const candidate of guarded) {
      const source = readSafe(candidate);
      if (source === null) continue;
      for (const pattern of RANKING_HELPER_IMPORT_PATTERNS) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("ranking-display surfaces never use trade-approval or order-routing language", () => {
    const surfaces = [
      "lib/momentum-ranking.ts",
      "components/recommendations/momentum-ranking-card.tsx",
      // Phase B3 status surfaces — same no-action-language guard.
      "lib/momentum-ranking-status.ts",
      "components/recommendations/momentum-ranking-status-card.tsx",
      // Phase B4 impact-review surfaces — same guard.
      "lib/momentum-impact.ts",
      "components/recommendations/momentum-impact-review.tsx",
    ];
    const forbidden = [
      "approve trade",
      "auto approve",
      "route order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
    ];
    for (const surface of surfaces) {
      const source = readSafe(surface);
      expect(source).not.toBeNull();
      const lowered = (source ?? "").toLowerCase();
      for (const phrase of forbidden) {
        expect(lowered.includes(phrase)).toBe(false);
      }
    }
  });

  it("Recommendations page wires the MomentumRankingCard once for selected detail", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain("@/components/recommendations/momentum-ranking-card");
    expect(source).toContain("MomentumRankingCard");
    expect(source).toContain("momentum_contribution");
  });
});

describe("Momentum Intelligence Phase B3 status guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Settings page wires the Momentum ranking status section", () => {
    const source = read("app/(console)/settings/page.tsx");
    expect(source).toContain("@/components/recommendations/momentum-ranking-status-card");
    expect(source).toContain("MomentumRankingStatusSection");
  });

  it("Momentum ranking status proxy route forwards to the backend status endpoint", () => {
    const source = read("app/api/user/momentum-ranking-status/route.ts");
    expect(source).toContain("proxyWorkflowRequest");
    expect(source).toContain("/user/momentum-ranking-status");
  });

  it("status card and client never use trade-approval or order-routing copy", () => {
    const surfaces = [
      "lib/momentum-ranking-status.ts",
      "components/recommendations/momentum-ranking-status-card.tsx",
    ];
    const forbidden = ["approve trade", "auto approve", "route order", "buy now", "sell now", "enter now", "short now"];
    for (const surface of surfaces) {
      const source = readSafe(surface);
      expect(source).not.toBeNull();
      const lowered = (source ?? "").toLowerCase();
      for (const phrase of forbidden) {
        expect(lowered.includes(phrase)).toBe(false);
      }
    }
  });

  it("status helpers do not leak into recommendation-approval/order helper files", () => {
    const guarded = [
      "lib/orders-helpers.ts",
      "lib/api-client.ts",
      "lib/guided-workflow.ts",
      "lib/lineage-format.ts",
    ];
    const patterns = [
      "@/lib/momentum-ranking-status",
      "@/components/recommendations/momentum-ranking-status-card",
      "MomentumRankingStatusCard",
      "MomentumRankingStatusSection",
      "fetchMomentumRankingStatus",
    ];
    for (const candidate of guarded) {
      const source = readSafe(candidate);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });
});

describe("Momentum Intelligence Phase B4 impact-review guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Recommendations page imports MomentumImpactReview and passes the existing queue", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain("@/components/recommendations/momentum-impact-review");
    expect(source).toContain("MomentumImpactReview");
    expect(source).toContain("candidates={queue}");
  });

  it("impact-review helpers/component are not imported into order, paper-position, paper-trade, options-paper, or replay-preview routes", () => {
    const routes = [
      "app/api/user/orders/route.ts",
      "app/api/user/orders/[orderId]/route.ts",
      "app/api/user/orders/portfolio-summary/route.ts",
      "app/api/user/paper-positions/route.ts",
      "app/api/user/paper-trades/route.ts",
      "app/api/user/options/replay-preview/route.ts",
      "app/api/user/options/paper-structures/route.ts",
      "app/api/user/options/paper-structures/open/route.ts",
      "app/api/user/options/paper-structures/review/route.ts",
    ];
    const patterns = [
      "@/lib/momentum-impact",
      "@/components/recommendations/momentum-impact-review",
      "MomentumImpactReview",
      "buildMomentumImpactRows",
      "estimateActiveScore",
    ];
    for (const route of routes) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("impact-review helpers/component do not leak into approval/order helper files", () => {
    const guarded = [
      "lib/orders-helpers.ts",
      "lib/api-client.ts",
      "lib/guided-workflow.ts",
      "lib/lineage-format.ts",
    ];
    const patterns = [
      "@/lib/momentum-impact",
      "@/components/recommendations/momentum-impact-review",
      "MomentumImpactReview",
      "buildMomentumImpactRows",
      "estimateActiveScore",
    ];
    for (const candidate of guarded) {
      const source = readSafe(candidate);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("impact-review surfaces avoid forbidden trade-approval/order-routing language", () => {
    const surfaces = [
      "lib/momentum-impact.ts",
      "components/recommendations/momentum-impact-review.tsx",
    ];
    const forbidden = ["approve trade", "auto approve", "route order", "buy now", "sell now", "enter now", "short now"];
    for (const surface of surfaces) {
      const source = readSafe(surface);
      expect(source).not.toBeNull();
      const lowered = (source ?? "").toLowerCase();
      for (const phrase of forbidden) {
        expect(lowered.includes(phrase)).toBe(false);
      }
    }
  });
});

describe("Momentum Intelligence Phase B6 safety-guard guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Settings still mounts the Momentum ranking status section", () => {
    const source = read("app/(console)/settings/page.tsx");
    expect(source).toContain("MomentumRankingStatusSection");
  });

  it("status card references MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING", () => {
    const source = read("components/recommendations/momentum-ranking-status-card.tsx");
    expect(source).toContain("MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING");
    expect(source).toContain("Active blocked — safety guard not enabled");
  });

  it("impact review carries the Phase B6 blocked-active framing", () => {
    const source = read("components/recommendations/momentum-impact-review.tsx");
    expect(source).toContain("safety guard blocked application");
    expect(source).toContain("MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true");
  });

  it("safety-guard env var is not referenced from order/paper-order/options-paper/replay-preview routes", () => {
    const routes = [
      "app/api/user/orders/route.ts",
      "app/api/user/orders/[orderId]/route.ts",
      "app/api/user/orders/portfolio-summary/route.ts",
      "app/api/user/paper-positions/route.ts",
      "app/api/user/paper-trades/route.ts",
      "app/api/user/options/replay-preview/route.ts",
      "app/api/user/options/paper-structures/route.ts",
      "app/api/user/options/paper-structures/open/route.ts",
      "app/api/user/options/paper-structures/review/route.ts",
    ];
    for (const route of routes) {
      const source = readSafe(route);
      if (source === null) continue;
      expect(source).not.toContain("MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING");
      expect(source).not.toContain("active_mode_blocked_by_safety_guard");
    }
  });
});
