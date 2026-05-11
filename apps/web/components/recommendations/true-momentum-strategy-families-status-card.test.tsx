import React from "react";
import type { ReactNode } from "react";
import { createRequire } from "module";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/operator-ui", async () => {
  const ReactModule = await import("react");
  return {
    Card: ({ title, children }: { title?: string; children: ReactNode }) =>
      ReactModule.createElement(
        "section",
        {},
        title ? ReactModule.createElement("h3", {}, title) : null,
        children,
      ),
    EmptyState: ({ title, hint }: { title: string; hint: string }) =>
      ReactModule.createElement("div", { "data-testid": "empty" }, `${title} ${hint}`),
    ErrorState: ({ title, hint }: { title: string; hint: string }) =>
      ReactModule.createElement("div", { "data-testid": "error" }, `${title} ${hint}`),
    StatusBadge: ({ tone, children }: { tone?: string; children: ReactNode }) =>
      ReactModule.createElement(
        "span",
        { className: `op-badge op-badge-${tone ?? "neutral"}` },
        children,
      ),
  };
});

import {
  TrueMomentumStrategyFamiliesStatusCardView,
  TrueMomentumStrategyFamiliesStatusCard,
} from "@/components/recommendations/true-momentum-strategy-families-status-card";
import {
  TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE,
  type TrueMomentumStrategyFamilyStatus,
} from "@/lib/true-momentum-strategy-families";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

function familySpec(id: string, label: string, direction: "long" | "watch" = "long") {
  return {
    id,
    label,
    description: `${label} description.`,
    status: "planned" as const,
    intended_direction: direction,
    required_inputs: ["momentum_score_snapshot"],
    deterministic_signals: ["deterministic_signal_placeholder"],
    guardrails: ["Phase C0 is scaffold-only."],
    not_allowed_actions: ["approve_trade", "route_order"],
    phase: "C0",
    implementation_status: "scaffold_only",
  };
}

const DISABLED_STATUS: TrueMomentumStrategyFamilyStatus = {
  requested_mode: "disabled",
  effective_mode: "disabled",
  enabled: false,
  guard_enabled: false,
  invalid_env_value: false,
  mode_env_var: "MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE",
  guard_env_var: "MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES",
  reason_codes: ["thinkorswim_parity_pending"],
  guardrails: [
    "Phase C0 is scaffold-only — no queue candidates are generated.",
    "True Momentum strategy families do not approve, reject, size, or route trades.",
  ],
  family_specs: [
    familySpec("true_momentum_continuation", "True Momentum Continuation"),
    familySpec("true_momentum_pullback", "True Momentum Pullback"),
    familySpec("true_momentum_reversal_watch", "True Momentum Reversal / Weakening Watch", "watch"),
  ],
  phase: "C0",
  implementation_status: "scaffold_only",
  parity_status: "pending_thinkorswim_fixture_validation",
  parity_required_for_active: true,
};

const BLOCKED_STATUS: TrueMomentumStrategyFamilyStatus = {
  ...DISABLED_STATUS,
  requested_mode: "research_preview",
  effective_mode: "disabled",
  enabled: false,
  guard_enabled: false,
  reason_codes: [
    "true_momentum_strategy_mode_blocked_by_guard",
    "thinkorswim_parity_pending",
  ],
};

const RESEARCH_PREVIEW_STATUS: TrueMomentumStrategyFamilyStatus = {
  ...DISABLED_STATUS,
  requested_mode: "research_preview",
  effective_mode: "research_preview",
  enabled: true,
  guard_enabled: true,
  reason_codes: ["thinkorswim_parity_pending"],
};

describe("TrueMomentumStrategyFamiliesStatusCardView", () => {
  it("renders disabled-by-default copy with effective mode and family specs", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyFamiliesStatusCardView status={DISABLED_STATUS} />,
    );
    expect(html).toContain("Phase C0");
    expect(html).toContain("scaffold_only");
    expect(html).toContain("Effective: Disabled");
    expect(html).toContain("Requested: Disabled");
    expect(html).toContain("Guard: disabled");
    expect(html).toContain("True Momentum Continuation");
    expect(html).toContain("True Momentum Pullback");
    expect(html).toContain("True Momentum Reversal / Weakening Watch");
    expect(html).toContain(TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE);
    expect(html).toContain("Still pending");
  });

  it("renders guard-blocked reason copy when research_preview was requested without the guard", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyFamiliesStatusCardView status={BLOCKED_STATUS} />,
    );
    expect(html).toContain("Effective: Disabled");
    expect(html).toContain("Requested: Research preview");
    expect(html).toContain("Mode blocked");
  });

  it("renders research-preview when guard is enabled", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyFamiliesStatusCardView status={RESEARCH_PREVIEW_STATUS} />,
    );
    expect(html).toContain("Effective: Research preview");
    expect(html).toContain("Guard: enabled");
  });

  it("renders error state when error is provided", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyFamiliesStatusCardView status={null} error="Backend offline" />,
    );
    expect(html).toContain("true-momentum-strategy-families-status-error");
    expect(html).toContain("Backend offline");
    expect(html).toContain(TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE);
  });

  it("renders loading state while no status is available", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyFamiliesStatusCardView status={null} loading />,
    );
    expect(html).toContain("Loading True Momentum strategy family status");
  });

  it("never renders forbidden trade-action language", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyFamiliesStatusCardView status={DISABLED_STATUS} />,
    ).toLowerCase();
    for (const phrase of ["buy now", "sell now", "enter now", "short now", "auto approve", "route order"]) {
      expect(html).not.toContain(phrase);
    }
  });

  it("never renders order/approval/sizing copy", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyFamiliesStatusCardView status={DISABLED_STATUS} />,
    ).toLowerCase();
    for (const phrase of [
      "approve trade",
      "place order",
      "submit order",
      "open position",
      "close position",
      "settle position",
    ]) {
      expect(html).not.toContain(phrase);
    }
  });
});

describe("TrueMomentumStrategyFamiliesStatusCard (container)", () => {
  it("renders without triggering a fetch when an initial status is provided", () => {
    const html = renderToStaticMarkup(
      <TrueMomentumStrategyFamiliesStatusCard initialStatus={DISABLED_STATUS} />,
    );
    expect(html).toContain("Phase C0");
    expect(html).toContain("True Momentum Continuation");
    expect(html).toContain(TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE);
  });
});
