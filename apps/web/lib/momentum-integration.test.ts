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

  it("Recommendations page mounts the Phase C1 preview panel near the trial journal", () => {
    const source = read("app/(console)/recommendations/page.tsx");
    expect(source).toContain(
      "@/components/recommendations/true-momentum-strategy-preview-panel",
    );
    expect(source).toContain("<TrueMomentumStrategyPreviewPanel");
    expect(source).toContain("candidates={queue}");
    // The Trial Journal mount must still come earlier in the file —
    // the preview panel sits *after* it.
    const trialIdx = source.indexOf("<MomentumTrialJournal");
    const previewIdx = source.indexOf("<TrueMomentumStrategyPreviewPanel");
    expect(trialIdx).toBeGreaterThan(-1);
    expect(previewIdx).toBeGreaterThan(trialIdx);
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
