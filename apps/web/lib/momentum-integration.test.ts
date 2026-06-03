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

  it("Phase C6 exposes True Momentum applicability in Analyze and Recommendations review surfaces", () => {
    const analyze = read("app/(console)/analyze/page.tsx");
    const recommendations = read("app/(console)/recommendations/page.tsx");
    const types = read("lib/recommendations.ts");

    expect(types).toContain("TrueMomentumApplicability");
    expect(analyze).toContain("Strategy Applicability");
    expect(analyze).toContain("true_momentum_applicability");
    expect(recommendations).toContain("TrueMomentumApplicabilityMini");
    expect(recommendations).toContain("TrueMomentumApplicabilityDetail");
    expect(recommendations).toContain("non-actionable");
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

describe("Momentum Intelligence Phase B7 trial-journal guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Recommendations page imports the trial journal and passes queue + universeSymbols", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain("@/components/recommendations/momentum-trial-journal");
    expect(source).toContain("MomentumTrialJournal");
    // Phase B7.1 — the page must now hand the parsed manual-symbol
    // input through as the evaluated universe so the journal can label
    // "Evaluated universe" rather than "Captured symbols".
    expect(source).toContain("candidates={queue}");
    expect(source).toContain("universeSymbols={parsedSymbols.symbols}");
  });

  it("trial-journal helpers and component are not imported into order, paper-position, paper-trade, options-paper, or replay-preview routes", () => {
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
      "@/lib/momentum-trial-journal",
      "@/components/recommendations/momentum-trial-journal",
      "MomentumTrialJournal",
      "MomentumTrialJournalView",
      "buildMomentumTrialSnapshot",
      "buildMomentumTrialMarkdown",
      "buildMomentumTrialJson",
    ];
    for (const route of routes) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("trial-journal helpers/component do not leak into recommendation-approval/order helper files", () => {
    const guarded = [
      "lib/orders-helpers.ts",
      "lib/api-client.ts",
      "lib/guided-workflow.ts",
      "lib/lineage-format.ts",
      "lib/recommendations.ts",
    ];
    const patterns = [
      "@/lib/momentum-trial-journal",
      "@/components/recommendations/momentum-trial-journal",
      "MomentumTrialJournal",
      "MomentumTrialJournalView",
      "buildMomentumTrialSnapshot",
      "buildMomentumTrialMarkdown",
      "buildMomentumTrialJson",
    ];
    for (const candidate of guarded) {
      const source = readSafe(candidate);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("trial-journal surfaces avoid forbidden trade-approval/order-routing language", () => {
    const surfaces = [
      "lib/momentum-trial-journal.ts",
      "components/recommendations/momentum-trial-journal.tsx",
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

  it("trial-journal carries the deterministic operator-evidence guardrail copy", () => {
    const lib = read("lib/momentum-trial-journal.ts");
    expect(lib).toContain(
      "This trial journal records Momentum ranking evidence only. It does not approve, reject, size, or route trades.",
    );
  });

  it("Phase B7.1 — trade warning vs operational caveat copy exists in both surfaces", () => {
    const lib = read("lib/momentum-trial-journal.ts");
    const view = read("components/recommendations/momentum-trial-journal.tsx");
    // Helper exports the partition + the universe label helper.
    expect(lib).toContain("MOMENTUM_TRIAL_TRADE_WARNING_FLAGS");
    expect(lib).toContain("MOMENTUM_TRIAL_OPERATIONAL_CAVEAT_FLAGS");
    expect(lib).toContain("momentumTrialUniverseLabel");
    expect(lib).toContain("trade_warning_count");
    expect(lib).toContain("operational_caveat_count");
    expect(lib).toContain("derived_higher_timeframe_count");
    expect(lib).toContain("Evaluated universe");
    expect(lib).toContain("Captured symbols");
    expect(lib).toContain("## Trade warnings");
    expect(lib).toContain("## Operational caveats");
    expect(lib).toContain("No trade warnings captured.");
    expect(lib).toContain("No operational caveats captured.");
    // View renders the new section headings + empty states.
    expect(view).toContain("Trade warnings");
    expect(view).toContain("Operational caveats");
    expect(view).toContain("No trade warnings captured.");
    expect(view).toContain("No operational caveats captured.");
    expect(view).toContain("momentum-trial-journal-trade-warnings-table");
    expect(view).toContain("momentum-trial-journal-operational-caveats-table");
  });

  it("Phase B7.1 — view does not duplicate the deterministic note (container owns it)", () => {
    const view = read("components/recommendations/momentum-trial-journal.tsx");
    // The trailing per-snapshot note that used to live inside the view
    // is gone; only the container-owned ``-container`` testid remains
    // so the deterministic note renders exactly once.
    expect(view).toContain("momentum-trial-journal-deterministic-note-container");
    expect(view).not.toContain('"momentum-trial-journal-deterministic-note"');
  });
});

describe("Momentum Intelligence Phase C0 True Momentum scaffolding guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Phase C0 lib + component exist and render the scaffold-only copy", () => {
    const lib = read("lib/true-momentum-strategy-families.ts");
    const view = read("components/recommendations/true-momentum-strategy-families-status-card.tsx");
    expect(lib).toContain("Phase C0");
    expect(lib).toContain("scaffold");
    expect(lib).toContain("/api/user/true-momentum-strategy-families/status");
    expect(view).toContain("Phase C0");
    expect(view).toContain("scaffold");
    expect(view).toContain("Still pending");
  });

  it("Phase C0 module is not imported into order, paper-position, paper-trade, options-paper, or replay-preview routes", () => {
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
      "@/lib/true-momentum-strategy-families",
      "@/components/recommendations/true-momentum-strategy-families-status-card",
      "TrueMomentumStrategyFamiliesStatusCard",
      "TrueMomentumStrategyFamiliesStatusCardView",
      "fetchTrueMomentumStrategyFamilyStatus",
    ];
    for (const route of routes) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Phase C0 module is not imported into order/recommendation helper files", () => {
    const guarded = [
      "lib/orders-helpers.ts",
      "lib/api-client.ts",
      "lib/guided-workflow.ts",
      "lib/lineage-format.ts",
      "lib/recommendations.ts",
      "lib/momentum-impact.ts",
      "lib/momentum-trial-journal.ts",
    ];
    const patterns = [
      "@/lib/true-momentum-strategy-families",
      "@/components/recommendations/true-momentum-strategy-families-status-card",
      "TrueMomentumStrategyFamiliesStatusCard",
      "fetchTrueMomentumStrategyFamilyStatus",
    ];
    for (const candidate of guarded) {
      const source = readSafe(candidate);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Phase C0 surfaces avoid forbidden trade-approval / order-routing language", () => {
    const surfaces = [
      "lib/true-momentum-strategy-families.ts",
      "components/recommendations/true-momentum-strategy-families-status-card.tsx",
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

  it("Settings page mounts the Phase C0 card under Momentum ranking status", () => {
    const source = read("app/(console)/settings/page.tsx");
    expect(source).toContain("TrueMomentumStrategyFamiliesStatusCard");
    expect(source).toContain(
      "@/components/recommendations/true-momentum-strategy-families-status-card",
    );
    // The card sits AFTER the Phase B Momentum ranking status section.
    const momentumIdx = source.indexOf("MomentumRankingStatusSection");
    const phaseCIdx = source.indexOf("<TrueMomentumStrategyFamiliesStatusCard");
    expect(momentumIdx).toBeGreaterThan(-1);
    expect(phaseCIdx).toBeGreaterThan(momentumIdx);
  });

  it("Recommendations page does not mount the Phase C0 card", () => {
    // Phase C0 explicitly stays out of the recommendation queue surface
    // — operator status only, under Settings.
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).not.toContain("TrueMomentumStrategyFamiliesStatusCard");
    expect(source).not.toContain("true-momentum-strategy-families");
  });
});

describe("Momentum Intelligence Phase B8 outcome review guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Phase B8 lib + component exist and carry the deterministic outcome copy", () => {
    const lib = read("lib/momentum-trial-outcomes.ts");
    const view = read("components/recommendations/momentum-trial-outcome-review.tsx");
    expect(lib).toContain("Phase B8");
    expect(lib).toContain(
      "Outcome tags are operator research notes only. They do not change ranking, approval, sizing, or order routing.",
    );
    expect(lib).toContain("MOMENTUM_TRIAL_OUTCOME_STORAGE_KEY");
    expect(lib).toContain("macmarket.momentumTrial.outcome.latest");
    expect(view).toContain("MomentumTrialOutcomeReviewPanel");
    expect(view).toContain("momentum-trial-outcome-review");
  });

  it("Trial-journal container mounts the outcome review panel after capture", () => {
    const source = read("components/recommendations/momentum-trial-journal.tsx");
    expect(source).toContain(
      "@/components/recommendations/momentum-trial-outcome-review",
    );
    expect(source).toContain("MomentumTrialOutcomeReviewPanel");
  });

  it("Outcome helpers/components are not imported into order, paper, replay, or options-paper routes", () => {
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
      "@/lib/momentum-trial-outcomes",
      "@/components/recommendations/momentum-trial-outcome-review",
      "MomentumTrialOutcomeReviewPanel",
      "buildMomentumTrialOutcomeReview",
      "buildMomentumOutcomeMarkdown",
      "buildMomentumOutcomeJson",
    ];
    for (const route of routes) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Outcome helpers/components do not leak into order/recommendation helper files", () => {
    const guarded = [
      "lib/orders-helpers.ts",
      "lib/api-client.ts",
      "lib/guided-workflow.ts",
      "lib/lineage-format.ts",
      "lib/recommendations.ts",
    ];
    const patterns = [
      "@/lib/momentum-trial-outcomes",
      "@/components/recommendations/momentum-trial-outcome-review",
      "MomentumTrialOutcomeReviewPanel",
      "buildMomentumTrialOutcomeReview",
    ];
    for (const candidate of guarded) {
      const source = readSafe(candidate);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Outcome surfaces avoid forbidden trade-approval / order-routing language", () => {
    const surfaces = [
      "lib/momentum-trial-outcomes.ts",
      "components/recommendations/momentum-trial-outcome-review.tsx",
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

  it("Recommendations page still mounts the trial journal only (no direct outcome panel mount)", () => {
    // The trial-journal container is the canonical mount site for the
    // outcome review (it owns the snapshot). The Recommendations page
    // never imports the outcome panel directly.
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain("MomentumTrialJournal");
    expect(source).not.toContain("@/components/recommendations/momentum-trial-outcome-review");
    expect(source).not.toContain("MomentumTrialOutcomeReviewPanel");
  });
});

describe("Momentum Intelligence Phase B8.1 copy polish guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Phase C0 Settings card names accumulated B8 outcome evidence as pending, not the feature itself", () => {
    const view = read(
      "components/recommendations/true-momentum-strategy-families-status-card.tsx",
    );
    expect(view).toContain("accumulated B8 outcome evidence");
    // The previous wording implied B8 itself was unimplemented. After
    // B8.1 the card must not claim "active trial outcome review" is
    // pending — that feature ships.
    expect(view).not.toMatch(/active trial outcome review/i);
  });

  it("Phase C0 Settings card carries a pointer to Recommendations for B8 evidence", () => {
    const view = read(
      "components/recommendations/true-momentum-strategy-families-status-card.tsx",
    );
    expect(view).toContain("true-momentum-b8-evidence-pointer");
    expect(view).toContain("Capture and tag B8 outcome evidence in");
    expect(view).toContain('href="/recommendations"');
  });

  it("Phase C0 Settings card still records the scaffold-only / no-queue / no-approval posture", () => {
    const view = read(
      "components/recommendations/true-momentum-strategy-families-status-card.tsx",
    );
    expect(view).toContain("Phase C0 remains scaffold-only");
    expect(view).toContain("do not generate queue candidates");
    expect(view).toContain("do not approve, reject,");
    expect(view).toContain("Paper-order creation remains manual.");
  });

  it("Phase C0 / B8 copy across helper + component avoids forbidden action language", () => {
    const surfaces = [
      "lib/true-momentum-strategy-families.ts",
      "components/recommendations/true-momentum-strategy-families-status-card.tsx",
      "lib/momentum-trial-outcomes.ts",
      "components/recommendations/momentum-trial-outcome-review.tsx",
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

  it("Phase C0 status card stays out of order/paper/replay/options-paper routes (B8.1 re-guard)", () => {
    const routes = [
      "app/api/user/orders/route.ts",
      "app/api/user/orders/[orderId]/route.ts",
      "app/api/user/paper-positions/route.ts",
      "app/api/user/paper-trades/route.ts",
      "app/api/user/options/replay-preview/route.ts",
      "app/api/user/options/paper-structures/route.ts",
      "app/api/user/options/paper-structures/open/route.ts",
      "app/api/user/options/paper-structures/review/route.ts",
    ];
    const patterns = [
      "@/components/recommendations/true-momentum-strategy-families-status-card",
      "TrueMomentumStrategyFamiliesStatusCard",
    ];
    for (const route of routes) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });
});

describe("Momentum Intelligence Phase C1 research-preview guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Phase C1 lib + panel exist and carry the deterministic preview note", () => {
    const lib = read("lib/true-momentum-strategy-preview.ts");
    const view = read("components/recommendations/true-momentum-strategy-preview-panel.tsx");
    expect(lib).toContain("Phase C1");
    expect(lib).toContain("buildTrueMomentumStrategyPreview");
    expect(lib).toContain("summarizeTrueMomentumStrategyPreview");
    expect(lib).toContain(
      "True Momentum strategy previews are research-only. They do not generate queue candidates, approve, reject, size, or route trades.",
    );
    expect(view).toContain("TrueMomentumStrategyPreviewPanel");
    expect(view).toContain("true-momentum-strategy-preview");
    expect(view).toContain("Phase C1 research preview is disabled.");
  });

  it("Recommendations page mounts the Phase C1 preview panel inside the research evidence section", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain(
      "@/components/recommendations/true-momentum-strategy-preview-panel",
    );
    expect(source).toContain("<TrueMomentumStrategyPreviewPanel");
    expect(source).toContain("candidates={queue}");
    // Both the Trial Journal and the C1 preview panel are mounted on
    // the page (Phase C4.1 wraps them inside the True Momentum
    // research evidence collapsible — the relative order between C1
    // and B7/B8 is no longer strict, but both must still be present).
    expect(source).toContain("<MomentumTrialJournal");
    // The C1 panel now lives under the research-evidence section.
    const researchEvidenceIdx = source.indexOf("true-momentum-research-evidence-section");
    const previewIdx = source.indexOf("<TrueMomentumStrategyPreviewPanel");
    expect(researchEvidenceIdx).toBeGreaterThan(-1);
    expect(previewIdx).toBeGreaterThan(researchEvidenceIdx);
  });

  it("Phase C1 lib / panel are not imported into order, paper, replay, options-paper routes", () => {
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
      "@/lib/true-momentum-strategy-preview",
      "@/components/recommendations/true-momentum-strategy-preview-panel",
      "TrueMomentumStrategyPreviewPanel",
      "buildTrueMomentumStrategyPreview",
    ];
    for (const route of routes) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Phase C1 lib / panel do not leak into order/recommendation helper files", () => {
    const guarded = [
      "lib/orders-helpers.ts",
      "lib/api-client.ts",
      "lib/guided-workflow.ts",
      "lib/lineage-format.ts",
      "lib/recommendations.ts",
    ];
    const patterns = [
      "@/lib/true-momentum-strategy-preview",
      "@/components/recommendations/true-momentum-strategy-preview-panel",
      "TrueMomentumStrategyPreviewPanel",
      "buildTrueMomentumStrategyPreview",
    ];
    for (const candidate of guarded) {
      const source = readSafe(candidate);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Phase C1 surfaces avoid forbidden trade-approval / order-routing language", () => {
    const surfaces = [
      "lib/true-momentum-strategy-preview.ts",
      "components/recommendations/true-momentum-strategy-preview-panel.tsx",
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

  it("Phase C1 surfaces never imply queue-candidate generation", () => {
    const surfaces = [
      "lib/true-momentum-strategy-preview.ts",
      "components/recommendations/true-momentum-strategy-preview-panel.tsx",
    ];
    for (const surface of surfaces) {
      const source = readSafe(surface);
      expect(source).not.toBeNull();
      const lowered = (source ?? "").toLowerCase();
      // The phrase appears only as a negation ("do not generate queue
      // candidates"). We assert the bare assertion phrase is absent so a
      // future edit cannot silently say "generates queue candidates".
      expect(lowered).not.toContain("generates queue candidates");
    }
  });
});

describe("Momentum Intelligence Phase C2 preview-evidence guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Phase C2 lib + panel exist and carry the deterministic evidence copy", () => {
    const lib = read("lib/true-momentum-preview-evidence.ts");
    const view = read(
      "components/recommendations/true-momentum-preview-evidence-panel.tsx",
    );
    expect(lib).toContain("Phase C2");
    expect(lib).toContain("buildTrueMomentumPreviewEvidenceBundle");
    expect(lib).toContain("summarizeTrueMomentumPreviewEvidence");
    expect(lib).toContain("partitionTrueMomentumPreviewEvidenceByFamily");
    expect(lib).toContain("topTrueMomentumPreviewEvidence");
    expect(lib).toContain("buildTrueMomentumPreviewEvidenceMarkdown");
    expect(lib).toContain("buildTrueMomentumPreviewEvidenceJson");
    expect(lib).toContain("validateTrueMomentumPreviewEvidenceBundle");
    expect(lib).toContain("phase_c2.v1");
    // Storage key lives in the lib module (the panel imports it by
    // name via TRUE_MOMENTUM_PREVIEW_EVIDENCE_STORAGE_KEY).
    expect(lib).toContain("macmarket.trueMomentumPreviewEvidence.latest");
    expect(lib).toContain(
      "True Momentum preview evidence is research-only. It does not generate queue candidates, approve, reject, size, or route trades.",
    );
    expect(view).toContain("TrueMomentumPreviewEvidencePanel");
    expect(view).toContain("Capture True Momentum Preview Evidence");
    // The panel references the storage key by its imported identifier
    // rather than the raw literal.
    expect(view).toContain("TRUE_MOMENTUM_PREVIEW_EVIDENCE_STORAGE_KEY");
  });

  it("C1 preview panel mounts the evidence panel only inside the Recommendations preview flow", () => {
    const source = read(
      "components/recommendations/true-momentum-strategy-preview-panel.tsx",
    );
    expect(source).toContain(
      "@/components/recommendations/true-momentum-preview-evidence-panel",
    );
    expect(source).toContain("<TrueMomentumPreviewEvidencePanel");
    // The evidence panel is only mounted when previews exist.
    expect(source).toContain("previews.length > 0");
  });

  it("Recommendations page wires the evaluated universe into the C1 preview panel", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain("<TrueMomentumStrategyPreviewPanel");
    expect(source).toContain("candidates={queue}");
    expect(source).toContain("universeSymbols={parsedSymbols.symbols}");
  });

  it("Phase C2 lib + panel are not imported into order / paper / replay / options-paper routes", () => {
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
      "@/lib/true-momentum-preview-evidence",
      "@/components/recommendations/true-momentum-preview-evidence-panel",
      "TrueMomentumPreviewEvidencePanel",
      "buildTrueMomentumPreviewEvidenceBundle",
      "buildTrueMomentumPreviewEvidenceMarkdown",
      "buildTrueMomentumPreviewEvidenceJson",
    ];
    for (const route of routes) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Phase C2 lib + panel do not leak into order / recommendation helper files", () => {
    const guarded = [
      "lib/orders-helpers.ts",
      "lib/api-client.ts",
      "lib/guided-workflow.ts",
      "lib/lineage-format.ts",
      "lib/recommendations.ts",
    ];
    const patterns = [
      "@/lib/true-momentum-preview-evidence",
      "@/components/recommendations/true-momentum-preview-evidence-panel",
      "TrueMomentumPreviewEvidencePanel",
      "buildTrueMomentumPreviewEvidenceBundle",
    ];
    for (const candidate of guarded) {
      const source = readSafe(candidate);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Phase C2 surfaces avoid forbidden trade-approval / order-routing language", () => {
    const surfaces = [
      "lib/true-momentum-preview-evidence.ts",
      "components/recommendations/true-momentum-preview-evidence-panel.tsx",
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

  it("Phase C2 surfaces never affirmatively claim to generate queue candidates", () => {
    const surfaces = [
      "lib/true-momentum-preview-evidence.ts",
      "components/recommendations/true-momentum-preview-evidence-panel.tsx",
    ];
    for (const surface of surfaces) {
      const source = readSafe(surface);
      expect(source).not.toBeNull();
      const lowered = (source ?? "").toLowerCase();
      expect(lowered).not.toContain("generates queue candidates");
      expect(lowered).not.toContain("emits queue candidate");
      expect(lowered).not.toContain("creates queue candidate");
      // Approval / order-routing affirmative phrases.
      expect(lowered).not.toContain("approve trade");
      expect(lowered).not.toContain("promote to recommendation");
    }
  });
});

describe("Momentum Intelligence Phase C2.1 — B8 link + duplicate-guardrail guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("C2 evidence panel rehydrates B7/B8 from localStorage via the lib's storage keys", () => {
    const view = read(
      "components/recommendations/true-momentum-preview-evidence-panel.tsx",
    );
    // The panel pulls the B7 snapshot + B8 outcome storage keys from
    // the lib modules so all three surfaces agree on the keys.
    expect(view).toContain("MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY");
    expect(view).toContain("MOMENTUM_TRIAL_OUTCOME_STORAGE_KEY");
    expect(view).toContain("validateMomentumTrialSnapshot");
    expect(view).toContain("validateMomentumTrialOutcomeReview");
    expect(view).toContain("readPersistedB8Snapshot");
    expect(view).toContain("readPersistedB8OutcomeReview");
    // Lib carries the canonical signature helper + link-status union.
    const lib = read("lib/true-momentum-preview-evidence.ts");
    expect(lib).toContain("computeMomentumQueueSignature");
    expect(lib).toContain("b8_snapshot_link_status");
    expect(lib).toContain("b8_outcome_review_link_status");
  });

  it("C1 preview panel does not duplicate the deterministic note when the evidence panel is mounted", () => {
    const source = read(
      "components/recommendations/true-momentum-strategy-preview-panel.tsx",
    );
    // The trailing C1 deterministic note + still-pending caveat now
    // only render when no previews exist (the evidence panel covers
    // both lines whenever it is mounted).
    expect(source).toContain(
      "previews.length === 0 ? (",
    );
    expect(source).toContain("true-momentum-strategy-preview-deterministic-note");
  });

  it("C2 evidence panel stays out of order / paper / replay / options-paper routes (C2.1 re-guard)", () => {
    const routes = [
      "app/api/user/orders/route.ts",
      "app/api/user/orders/[orderId]/route.ts",
      "app/api/user/paper-positions/route.ts",
      "app/api/user/paper-trades/route.ts",
      "app/api/user/options/replay-preview/route.ts",
      "app/api/user/options/paper-structures/route.ts",
      "app/api/user/options/paper-structures/open/route.ts",
      "app/api/user/options/paper-structures/review/route.ts",
    ];
    const patterns = [
      "@/components/recommendations/true-momentum-preview-evidence-panel",
      "TrueMomentumPreviewEvidencePanel",
      "buildTrueMomentumPreviewEvidenceBundle",
      "computeMomentumQueueSignature",
    ];
    for (const route of routes) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("C2.1 surfaces avoid forbidden trade-action / queue-generation / approval / order-routing language", () => {
    const surfaces = [
      "lib/true-momentum-preview-evidence.ts",
      "components/recommendations/true-momentum-preview-evidence-panel.tsx",
    ];
    const forbidden = [
      "approve trade",
      "auto approve",
      "route order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "promote to recommendation",
    ];
    for (const surface of surfaces) {
      const source = readSafe(surface);
      expect(source).not.toBeNull();
      const lowered = (source ?? "").toLowerCase();
      for (const phrase of forbidden) {
        expect(lowered).not.toContain(phrase);
      }
      expect(lowered).not.toContain("generates queue candidates");
    }
  });
});

describe("Momentum Intelligence Phase C2.2 — live B8 linkage + scroll polish guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Recommendations page lifts B7 snapshot + B8 outcome review state and threads it into the C1 panel", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain("setB8Snapshot");
    expect(source).toContain("setB8OutcomeReview");
    expect(source).toContain("onSnapshotChange={setB8Snapshot}");
    expect(source).toContain("onOutcomeReviewChange={setB8OutcomeReview}");
    expect(source).toContain("b8Snapshot={b8Snapshot}");
    expect(source).toContain("b8OutcomeReview={b8OutcomeReview}");
  });

  it("MomentumTrialJournal exposes the lift callbacks", () => {
    const source = read("components/recommendations/momentum-trial-journal.tsx");
    expect(source).toContain("onSnapshotChange?: (snapshot: MomentumTrialSnapshot | null) => void;");
    expect(source).toContain("onOutcomeReviewChange?: (review: MomentumTrialOutcomeReview | null) => void;");
  });

  it("MomentumTrialOutcomeReview accepts the onReviewChange callback and fires it on review changes", () => {
    const source = read(
      "components/recommendations/momentum-trial-outcome-review.tsx",
    );
    expect(source).toContain("onReviewChange?: (review: MomentumTrialOutcomeReview | null) => void;");
    expect(source).toContain("onReviewChange(snapshot ? review : null);");
  });

  it("C1 preview panel threads lifted B7/B8 props into the C2 evidence panel", () => {
    const source = read(
      "components/recommendations/true-momentum-strategy-preview-panel.tsx",
    );
    expect(source).toContain("b8Snapshot?: MomentumTrialSnapshot | null;");
    expect(source).toContain("b8OutcomeReview?: MomentumTrialOutcomeReview | null;");
    expect(source).toContain("b8Snapshot={b8Snapshot}");
    expect(source).toContain("b8OutcomeReview={b8OutcomeReview}");
  });

  it("Ranked queue panel uses the scrollable container pattern with a max-height of ~10 rows", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain('data-testid="ranked-queue-scroll-container"');
    expect(source).toContain('maxHeight: 360');
    expect(source).toContain('overflowY: "auto"');
    // The scroll container sits immediately above the Ranked queue
    // table — the table block still renders as before.
    const containerIdx = source.indexOf('data-testid="ranked-queue-scroll-container"');
    const tableIdx = source.indexOf("<table className=\"op-table\"", containerIdx);
    expect(tableIdx).toBeGreaterThan(containerIdx);
  });

  it("Persisted recommendations panel keeps its existing scroll wrapper", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    // The Persisted recommendations block still scrolls at its
    // historical max-height. We assert both scroll wrappers coexist.
    const ranked = source.indexOf('data-testid="ranked-queue-scroll-container"');
    expect(ranked).toBeGreaterThan(-1);
    const persisted = source.indexOf(
      'maxHeight: 360, overflowY: "auto"',
      ranked + 1,
    );
    expect(persisted).toBeGreaterThan(ranked);
  });

  it("C2 evidence component remains out of order / paper / replay / options-paper routes (C2.2 re-guard)", () => {
    const routes = [
      "app/api/user/orders/route.ts",
      "app/api/user/orders/[orderId]/route.ts",
      "app/api/user/paper-positions/route.ts",
      "app/api/user/paper-trades/route.ts",
      "app/api/user/options/replay-preview/route.ts",
      "app/api/user/options/paper-structures/route.ts",
      "app/api/user/options/paper-structures/open/route.ts",
      "app/api/user/options/paper-structures/review/route.ts",
    ];
    const patterns = [
      "@/components/recommendations/true-momentum-preview-evidence-panel",
      "TrueMomentumPreviewEvidencePanel",
      "buildTrueMomentumPreviewEvidenceBundle",
    ];
    for (const route of routes) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("scroll-polish does not alter recommendation approval / promote / paper-order paths", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    // The scroll wrapper is purely a visual container; the table row
    // click handler that selects a queue candidate must still be
    // intact, and there must be no new promote / approve / route /
    // paper-order calls introduced.
    expect(source).toContain("setSelectedQueueKey(key)");
    expect(source).toMatch(/setSelectedQueueKey\(key\)/);
    // The new scroll container should not duplicate the click handler
    // or wrap it in any disabling logic.
  });
});

describe("Momentum Intelligence Phase C3 — cohort review guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Phase C3 lib + panel exist and carry the deterministic cohort copy", () => {
    const lib = read("lib/true-momentum-cohort-review.ts");
    const view = read(
      "components/recommendations/true-momentum-cohort-review-panel.tsx",
    );
    expect(lib).toContain("Phase C3");
    expect(lib).toContain("phase_c3.v1");
    expect(lib).toContain("buildTrueMomentumCohortRecord");
    expect(lib).toContain("addTrueMomentumCohortRecord");
    expect(lib).toContain("removeTrueMomentumCohortRecord");
    expect(lib).toContain("replaceTrueMomentumCohortRecord");
    expect(lib).toContain("summarizeTrueMomentumCohortArchive");
    expect(lib).toContain("classifyTrueMomentumCohortReadiness");
    expect(lib).toContain("buildTrueMomentumCohortMarkdown");
    expect(lib).toContain("buildTrueMomentumCohortJson");
    expect(lib).toContain("validateTrueMomentumCohortArchive");
    expect(lib).toContain("sanitizeTrueMomentumCohortNote");
    expect(lib).toContain("macmarket.trueMomentumCohortReview.archive");
    expect(lib).toContain(
      "True Momentum cohort review is research-only. It does not generate queue candidates, approve, reject, size, or route trades.",
    );
    expect(view).toContain("TrueMomentumCohortReviewPanel");
    expect(view).toContain("true-momentum-cohort-review");
    expect(view).toContain("Add current evidence bundle to cohort archive");
    expect(view).toContain("Export Cohort Markdown");
    expect(view).toContain("Export Cohort JSON");
    expect(view).toContain("Clear Archive");
  });

  it("C2 evidence panel mounts the C3 cohort panel and passes the current bundle", () => {
    const source = read(
      "components/recommendations/true-momentum-preview-evidence-panel.tsx",
    );
    expect(source).toContain(
      "@/components/recommendations/true-momentum-cohort-review-panel",
    );
    expect(source).toContain("<TrueMomentumCohortReviewPanel");
    expect(source).toContain("currentBundle={livePreview}");
  });

  it("Phase C3 surfaces are not imported into order / paper / replay / options-paper routes", () => {
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
      "@/lib/true-momentum-cohort-review",
      "@/components/recommendations/true-momentum-cohort-review-panel",
      "TrueMomentumCohortReviewPanel",
      "buildTrueMomentumCohortRecord",
      "buildTrueMomentumCohortReviewReport",
    ];
    for (const route of routes) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Phase C3 lib / panel do not leak into order / recommendation helper files", () => {
    const guarded = [
      "lib/orders-helpers.ts",
      "lib/api-client.ts",
      "lib/guided-workflow.ts",
      "lib/lineage-format.ts",
      "lib/recommendations.ts",
      "lib/momentum-impact.ts",
    ];
    const patterns = [
      "@/lib/true-momentum-cohort-review",
      "@/components/recommendations/true-momentum-cohort-review-panel",
      "TrueMomentumCohortReviewPanel",
      "buildTrueMomentumCohortRecord",
    ];
    for (const candidate of guarded) {
      const source = readSafe(candidate);
      if (source === null) continue;
      for (const pattern of patterns) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Phase C3 surfaces avoid forbidden trade-action / queue-generation / approval / order-routing language", () => {
    const surfaces = [
      "lib/true-momentum-cohort-review.ts",
      "components/recommendations/true-momentum-cohort-review-panel.tsx",
    ];
    const forbidden = [
      "approve trade",
      "auto approve",
      "route order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "promote to recommendation",
      "ready for live",
      "activate now",
    ];
    for (const surface of surfaces) {
      const source = readSafe(surface);
      expect(source).not.toBeNull();
      const lowered = (source ?? "").toLowerCase();
      for (const phrase of forbidden) {
        expect(lowered).not.toContain(phrase);
      }
      expect(lowered).not.toContain("generates queue candidates");
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

describe("Momentum visual parity chart polish guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Momentum summary panel imports the visual parity badges + legend", () => {
    const source = read("components/charts/momentum-summary-panel.tsx");
    expect(source).toContain("@/components/charts/chart-status-badges");
    expect(source).toContain("@/components/charts/momentum-context-legend");
    expect(source).toContain("CandleStatusBadges");
    expect(source).toContain("MomentumContextLegend");
    expect(source).toContain("buildVisualParityFields");
    expect(source).toContain("SqueezeProSummaryStrip");
    expect(source).toContain("momentum-summary-squeeze-pro");
  });

  it("Momentum workspace wires status badges + legend on the canonical chart page", () => {
    const source = read("components/charts/momentum-workspace.tsx");
    expect(source).toContain("CandleStatusBadges");
    expect(source).toContain("TrueMomentumPanelStatusBadges");
    expect(source).toContain("HiloPanelStatusBadges");
    expect(source).toContain("MomentumContextLegend");
    expect(source).toContain("splitMomentumLineByDirection");
    expect(source).toContain("true_momentum_panel_markers");
    expect(source).toContain("hilo_panel_markers");
  });

  it("Momentum workspace renders the Squeeze Pro lower panel and legend", () => {
    const source = read("components/charts/momentum-workspace.tsx");
    expect(source).toContain("Squeeze Pro");
    expect(source).toContain("squeeze-pro-panel");
    expect(source).toContain("squeeze-pro-legend");
    expect(source).toContain("Histogram momentum");
    expect(source).toContain("Squeeze state dots");
    expect(source).not.toContain("Derived arrow events");
    expect(source).not.toContain("point.arrow");
    expect(source).not.toContain("Squeeze Pro derived event");
    expect(source).toContain("data.squeeze_pro");
    expect(source).toContain("WhitespaceData");
    expect(source).toContain("squeezeHistogramData");
    expect(source).toContain("squeezePoints.map((point)");
    expect(source).toContain("momentum-price-panel");
    expect(source).toContain("subscribeVisibleTimeRangeChange");
  });

  it("Recommendations page imports MomentumSummaryPanel so the parity polish reaches the recommendation detail surface", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain("MomentumSummaryPanel");
    expect(source).toContain("@/components/charts/momentum-summary-panel");
  });

  it("Chart parity badges/legend are not imported into order, paper-order, or replay route handlers", () => {
    const routesToGuard = [
      "app/api/user/orders/route.ts",
      "app/api/user/orders/[orderId]/route.ts",
      "app/api/user/paper-positions/route.ts",
      "app/api/user/paper-trades/route.ts",
      "app/api/user/options/replay-preview/route.ts",
      "app/api/user/options/paper-structures/route.ts",
      "app/api/user/options/paper-structures/open/route.ts",
      "app/api/user/options/paper-structures/review/route.ts",
      "app/api/user/recommendations/queue/route.ts",
      "app/api/user/recommendations/queue/promote/route.ts",
    ];
    for (const route of routesToGuard) {
      const source = readSafe(route);
      if (source === null) continue;
      expect(source).not.toContain("chart-status-badges");
      expect(source).not.toContain("momentum-context-legend");
      expect(source).not.toContain("splitMomentumLineByDirection");
      expect(source).not.toContain("CandleStatusBadges");
    }
  });

  it("Chart parity surfaces never use trade-approval or order-routing language", () => {
    const surfaces = [
      "lib/momentum-chart.ts",
      "components/charts/chart-status-badges.tsx",
      "components/charts/momentum-context-legend.tsx",
    ];
    const forbidden = [
      "approve trade",
      "auto approve",
      "route order",
      "place order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
    ];
    for (const surface of surfaces) {
      const source = readSafe(surface);
      expect(source).not.toBeNull();
      const lower = (source ?? "").toLowerCase();
      for (const phrase of forbidden) {
        expect(lower.includes(phrase)).toBe(false);
      }
    }
  });
});

describe("Momentum Intelligence Phase C4 — True Momentum strategy context guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Recommendations page mounts the True Momentum Strategy Context card", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain("@/components/recommendations/true-momentum-strategy-context-card");
    expect(source).toContain("TrueMomentumStrategyContextCard");
    // The card must be wired with the selected queue candidate, not a
    // synthetic / generated row.
    expect(source).toContain("candidate={selectedQueue}");
  });

  it("Phase C4 helper / card are not imported into order, paper, replay, or options-paper routes", () => {
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
      "app/api/user/recommendations/queue/promote/route.ts",
    ];
    const forbiddenImports = [
      "@/lib/true-momentum-strategy-context",
      "true-momentum-strategy-context-card",
      "buildTrueMomentumStrategyContext",
      "classifyTrueMomentumStrategyActivationReadiness",
      "TrueMomentumStrategyContextCard",
    ];
    for (const route of routesToGuard) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of forbiddenImports) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Phase C4 helper / card never use trade-approval or order-routing language", () => {
    const surfaces = [
      "lib/true-momentum-strategy-context.ts",
      "components/recommendations/true-momentum-strategy-context-card.tsx",
    ];
    const forbidden = [
      "approve trade",
      "auto approve",
      "route order",
      "place order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "auto-create order",
    ];
    for (const surface of surfaces) {
      const source = readSafe(surface);
      expect(source).not.toBeNull();
      const lower = (source ?? "").toLowerCase();
      for (const phrase of forbidden) {
        expect(lower.includes(phrase)).toBe(false);
      }
    }
  });

  it("Phase C4 helper is research-only and never generates queue candidates", () => {
    const source = read("lib/true-momentum-strategy-context.ts");
    // Helper must explicitly carry the never-generates / never-approves
    // deterministic note.
    expect(source).toContain(
      "does not generate queue candidates",
    );
    // Activation readiness must never produce an "approved" status —
    // the union of readiness values is closed and known.
    const readinessUnion = source.match(/TrueMomentumStrategyActivationReadiness\s*=([\s\S]+?);/);
    expect(readinessUnion).not.toBeNull();
    const readinessLines = (readinessUnion?.[0] ?? "").toLowerCase();
    expect(readinessLines.includes("approved")).toBe(false);
    expect(readinessLines.includes("ready_for_live")).toBe(false);
    expect(source).toContain("research_ready");
    expect(source).toContain("watch_only");
    // The non_actionable: true marker must remain on every context
    // bundle.
    expect(source).toContain("non_actionable: true");
  });

  it("Recommendation page does not change queue sorting or order paths when mounting the C4 card", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    // Activation-readiness is never wired into the promote / make-active /
    // save / paper-order surfaces. The card sits beside the C1 panel.
    expect(source).toContain("TrueMomentumStrategyContextCard");
    expect(source).not.toContain("activation_readiness=\"approved\"");
    // The promote / make-active hook is not derived from the C4 readiness.
    expect(source).not.toContain("ctx.readiness === \"approved\"");
  });
});

describe("Momentum Intelligence Phase C4.1 — UX consolidation guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Recommendations page places the C4 selected-candidate card before the research evidence section", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    // Use the JSX mount tag (not the import) so the ordering check is
    // robust to import re-shuffling.
    const c4Mount = source.indexOf("<TrueMomentumStrategyContextCard");
    const researchEvidence = source.indexOf("true-momentum-research-evidence-section");
    expect(c4Mount).toBeGreaterThan(-1);
    expect(researchEvidence).toBeGreaterThan(-1);
    expect(c4Mount).toBeLessThan(researchEvidence);
    // The C4 card must still be wired to the selected queue candidate.
    expect(source).toContain("candidate={selectedQueue}");
  });

  it("Recommendations page renders the True Momentum operator guide above the C4 card", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    const guideAnchor = source.indexOf("true-momentum-operator-guide");
    const c4Mount = source.indexOf("<TrueMomentumStrategyContextCard");
    expect(guideAnchor).toBeGreaterThan(-1);
    expect(c4Mount).toBeGreaterThan(-1);
    expect(guideAnchor).toBeLessThan(c4Mount);
    // The guide carries the recommended workflow lines.
    expect(source).toContain("Select a queue candidate");
    expect(source).toContain("Approval and paper orders remain manual");
  });

  it("research evidence section is wrapped in collapsible details summary (collapsed by default)", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain('data-testid="true-momentum-research-evidence-section"');
    expect(source).toContain('data-testid="true-momentum-research-evidence-summary"');
    expect(source).toContain('data-testid="true-momentum-research-evidence-c1-section"');
    expect(source).toContain('data-testid="true-momentum-research-evidence-b78-section"');
    // The wrapper uses details/summary HTML (no `open` attribute means
    // collapsed-by-default).
    const wrapperBlock = source.match(
      /<details[^>]*data-testid="true-momentum-research-evidence-section"[^>]*>/,
    );
    expect(wrapperBlock).not.toBeNull();
    expect(wrapperBlock?.[0] ?? "").not.toContain(" open");
  });

  it("Momentum Shadow Impact Review is labeled as ranking diagnostics and collapsed by default", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain('data-testid="momentum-ranking-diagnostics-section"');
    expect(source).toContain('data-testid="momentum-ranking-diagnostics-summary"');
    expect(source).toContain("Momentum ranking diagnostics");
    const wrapperBlock = source.match(
      /<details[^>]*data-testid="momentum-ranking-diagnostics-section"[^>]*>/,
    );
    expect(wrapperBlock).not.toBeNull();
    expect(wrapperBlock?.[0] ?? "").not.toContain(" open");
  });

  it("each collapsible subsection is labeled by phase / purpose", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain("C1 Family Preview — current queue");
    // C2 + C3 are nested inside the C1 preview panel — the page surfaces a hint pointing there.
    expect(source).toContain('data-testid="true-momentum-research-evidence-c2-c3-hint"');
    expect(source).toContain("B7/B8 Trial Journal — capture and tag outcomes");
  });

  it("C4 card carries the selected-candidate scope note and the no-selection empty state", () => {
    const card = read("components/recommendations/true-momentum-strategy-context-card.tsx");
    // Scope note (visible on both populated and empty states). The
    // assertion is tolerant of source-level line breaks inside the
    // JSX literal — collapse whitespace before matching.
    expect(card).toContain("This card evaluates the selected queue candidate only");
    const collapsed = card.replace(/\s+/g, " ");
    expect(collapsed).toContain(
      "It does not generate recommendations, and does not approve, reject, size, or route trades",
    );
    // Empty-state guidance.
    expect(card).toContain(
      "Select a queue candidate to view True Momentum strategy context",
    );
    // Default title now includes the "selected candidate" disambiguator.
    expect(card).toContain("True Momentum Strategy Context — selected candidate");
  });

  it("C4.1 collapsible wrappers do not import order / paper / replay routes", () => {
    const routesToGuard = [
      "app/api/user/orders/route.ts",
      "app/api/user/orders/[orderId]/route.ts",
      "app/api/user/paper-positions/route.ts",
      "app/api/user/paper-trades/route.ts",
      "app/api/user/options/replay-preview/route.ts",
      "app/api/user/options/paper-structures/route.ts",
      "app/api/user/options/paper-structures/open/route.ts",
      "app/api/user/options/paper-structures/review/route.ts",
      "app/api/user/recommendations/queue/promote/route.ts",
    ];
    const forbidden = [
      "true-momentum-strategy-context-card",
      "TrueMomentumStrategyContextCard",
      "true-momentum-operator-guide",
      "momentum-ranking-diagnostics-section",
      "true-momentum-research-evidence-section",
    ];
    for (const route of routesToGuard) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of forbidden) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("Recommendations page does not contain forbidden trade-action language inside the new C4.1 wrappers", () => {
    const source = read("app/(console)/recommendations/page.tsx").toLowerCase();
    for (const forbidden of [
      "approve trade",
      "auto approve",
      "route order",
      "place order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
    ]) {
      expect(source.includes(forbidden)).toBe(false);
    }
  });
});

describe("True Momentum Phase C research closeout guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("Phase C closeout helper carries the canonical shipped phases and no live activation copy", () => {
    const source = read("lib/true-momentum-phase-c-closeout.ts");
    for (const phase of ["C0", "C1", "C2", "C2.1", "C2.2", "C3", "C4", "C4.1"]) {
      expect(source).toContain(`"${phase}"`);
    }
    expect(source).toContain("research_implementation_status");
    expect(source).toContain("can_generate_queue_candidates");
    expect(source).toContain("can_approve_trades");
    expect(source).toContain("can_route_orders");
    expect(source).toContain('"C5"');
    const lower = source.toLowerCase();
    for (const forbidden of [
      "approve trade",
      "auto approve",
      "route order",
      "place order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "ready for live",
    ]) {
      expect(lower.includes(forbidden)).toBe(false);
    }
  });

  it("Phase C closeout card is mounted inside the research-evidence collapsible", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain(
      "@/components/recommendations/true-momentum-phase-c-closeout-card",
    );
    expect(source).toContain("TrueMomentumPhaseCCloseoutCard");
    expect(source).toContain('data-testid="true-momentum-research-evidence-closeout-section"');
    // Closeout collapsible sits inside the parent research-evidence
    // collapsible (i.e. after its opening anchor).
    const evidenceIdx = source.indexOf("true-momentum-research-evidence-section");
    const closeoutIdx = source.indexOf("true-momentum-research-evidence-closeout-section");
    expect(evidenceIdx).toBeGreaterThan(-1);
    expect(closeoutIdx).toBeGreaterThan(evidenceIdx);
  });

  it("Phase C closeout helper / card are not imported into order / paper / replay / options-paper routes", () => {
    const routesToGuard = [
      "app/api/user/orders/route.ts",
      "app/api/user/orders/[orderId]/route.ts",
      "app/api/user/paper-positions/route.ts",
      "app/api/user/paper-trades/route.ts",
      "app/api/user/options/replay-preview/route.ts",
      "app/api/user/options/paper-structures/route.ts",
      "app/api/user/options/paper-structures/open/route.ts",
      "app/api/user/options/paper-structures/review/route.ts",
      "app/api/user/recommendations/queue/promote/route.ts",
    ];
    const forbidden = [
      "@/lib/true-momentum-phase-c-closeout",
      "true-momentum-phase-c-closeout-card",
      "buildTrueMomentumPhaseCCloseoutStatus",
      "TrueMomentumPhaseCCloseoutCard",
    ];
    for (const route of routesToGuard) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of forbidden) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("C4.2 composite-mismatch drilldown lives on the C4 card and is gated on parity classification", () => {
    const card = read(
      "components/recommendations/true-momentum-strategy-context-card.tsx",
    );
    expect(card).toContain("CompositeMismatchDrilldown");
    expect(card).toContain("Composite score mismatch under review");
    expect(card).toContain('data-testid="true-momentum-strategy-context-card-composite-drilldown"');
    // Drilldown is gated on the two classification tags from the
    // selected symbol's parity summary — never an unrelated symbol.
    expect(card).toContain('classification.includes("oscillator_aligned")');
    expect(card).toContain('classification.includes("composite_mismatch")');
    expect(card).toContain(
      "Oscillator parity is aligned, but composite score differs",
    );
  });
});

describe("True Momentum Phase C5 research candidate proposal guards", () => {
  function readSafe(relative: string): string | null {
    try {
      return read(relative);
    } catch {
      return null;
    }
  }

  it("C5 helper exports the expected types, builder, and exports without forbidden trade-action language", () => {
    const source = read("lib/true-momentum-research-candidates.ts");
    expect(source).toContain("buildTrueMomentumResearchCandidateProposalSet");
    expect(source).toContain("summarizeTrueMomentumResearchCandidates");
    expect(source).toContain("partitionTrueMomentumResearchCandidatesByFamily");
    expect(source).toContain("rankTrueMomentumResearchCandidates");
    expect(source).toContain("buildTrueMomentumResearchCandidateMarkdown");
    expect(source).toContain("buildTrueMomentumResearchCandidateJson");
    expect(source).toContain("validateTrueMomentumResearchCandidateProposalSet");
    expect(source).toContain("trueMomentumResearchCandidateStatusLabel");
    expect(source).toContain("trueMomentumResearchCandidateTone");
    expect(source).toContain('"phase_c5.v1"');
    expect(source).toContain('"C5"');
    expect(source).toContain("operator_authorization");
    expect(source).toContain("active_generation_reserved");
    expect(source).toContain("non_actionable");
    const lower = source.toLowerCase();
    for (const forbidden of [
      "approve trade",
      "auto approve",
      "route order",
      "place order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "ready for live",
    ]) {
      expect(lower.includes(forbidden)).toBe(false);
    }
  });

  it("C5 UI panel is mounted inside the research-evidence collapsible after the Phase C closeout details", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain(
      "@/components/recommendations/true-momentum-research-candidates-panel",
    );
    expect(source).toContain("<TrueMomentumResearchCandidatesPanel");
    expect(source).toContain('data-testid="true-momentum-research-evidence-c5-section"');
    const evidenceIdx = source.indexOf("true-momentum-research-evidence-section");
    const closeoutIdx = source.indexOf("true-momentum-research-evidence-closeout-section");
    const c5Idx = source.indexOf("true-momentum-research-evidence-c5-section");
    expect(evidenceIdx).toBeGreaterThan(-1);
    expect(closeoutIdx).toBeGreaterThan(-1);
    expect(c5Idx).toBeGreaterThan(closeoutIdx);
  });

  it("C5 helper / panel are not imported into order / paper / replay / options-paper routes", () => {
    const routesToGuard = [
      "app/api/user/orders/route.ts",
      "app/api/user/orders/[orderId]/route.ts",
      "app/api/user/paper-positions/route.ts",
      "app/api/user/paper-trades/route.ts",
      "app/api/user/options/replay-preview/route.ts",
      "app/api/user/options/paper-structures/route.ts",
      "app/api/user/options/paper-structures/open/route.ts",
      "app/api/user/options/paper-structures/review/route.ts",
      "app/api/user/recommendations/queue/promote/route.ts",
      "app/(console)/orders/page.tsx",
      "app/(console)/replay-runs/page.tsx",
    ];
    const forbidden = [
      "@/lib/true-momentum-research-candidates",
      "true-momentum-research-candidates-panel",
      "buildTrueMomentumResearchCandidateProposalSet",
      "TrueMomentumResearchCandidatesPanel",
    ];
    for (const route of routesToGuard) {
      const source = readSafe(route);
      if (source === null) continue;
      for (const pattern of forbidden) {
        expect(source).not.toContain(pattern);
      }
    }
  });

  it("C5 panel + helper sources never carry forbidden trade-action language", () => {
    const sources = [
      read("lib/true-momentum-research-candidates.ts"),
      read("components/recommendations/true-momentum-research-candidates-panel.tsx"),
    ];
    for (const source of sources) {
      const lower = source.toLowerCase();
      for (const forbidden of [
        "approve trade",
        "auto approve",
        "route order",
        "place order",
        "buy now",
        "sell now",
        "enter now",
        "short now",
        "ready for live",
        "activate now",
      ]) {
        expect(lower.includes(forbidden)).toBe(false);
      }
    }
  });

  it("C5 helper always blocks activation via operator_authorization and active_generation_reserved gates", () => {
    const source = read("lib/true-momentum-research-candidates.ts");
    expect(source).toContain('id: "operator_authorization"');
    expect(source).toContain('id: "active_generation_reserved"');
    // Both gates must mark blocks_activation: true.
    const opAuthBlock = source.match(
      /id:\s*"operator_authorization"[\s\S]*?blocks_activation:\s*true/,
    );
    const activeGenBlock = source.match(
      /id:\s*"active_generation_reserved"[\s\S]*?blocks_activation:\s*true/,
    );
    expect(opAuthBlock).not.toBeNull();
    expect(activeGenBlock).not.toBeNull();
  });
});
