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

import { MomentumRankingStatusCard } from "@/components/recommendations/momentum-ranking-status-card";
import type { MomentumRankingStatus } from "@/lib/momentum-ranking-status";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

const DETERMINISTIC_NOTE =
  "Momentum ranking status is operator readiness context only. It does not approve, reject, size, or route trades.";

function shadowStatus(overrides: Partial<MomentumRankingStatus> = {}): MomentumRankingStatus {
  return {
    mode: "shadow",
    default_mode: "shadow",
    env_var: "MACMARKET_MOMENTUM_RANKING_MODE",
    raw_env_value: "shadow",
    invalid_env_value: false,
    enabled: true,
    applied_by_default: false,
    parity_status: "pending_thinkorswim_fixture_validation",
    parity_fixture_manifest_present: false,
    parity_required_for_active: false,
    real_thinkorswim_parity_pending: true,
    active_mode_warning: null,
    reason_codes: ["thinkorswim_parity_pending"],
    guardrails: [
      "Shadow mode computes contribution but does not alter final ranking.",
      "Active mode applies a bounded contribution only.",
      "This does not approve, reject, size, or route trades.",
      "Real Thinkorswim parity fixtures are still pending.",
    ],
    ...overrides,
  };
}

describe("MomentumRankingStatusCard", () => {
  it("renders empty state when status is null and not loading", () => {
    const html = renderToStaticMarkup(<MomentumRankingStatusCard status={null} />);
    expect(html).toContain("Momentum ranking status not loaded");
    expect(html).toContain(DETERMINISTIC_NOTE);
  });

  it("renders loading state with role=status", () => {
    const html = renderToStaticMarkup(<MomentumRankingStatusCard status={null} loading />);
    expect(html).toContain("Loading momentum ranking status");
    expect(html).toContain('role="status"');
  });

  it("renders error state", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard status={null} error="Provider unavailable" />,
    );
    expect(html).toContain("Momentum ranking status unavailable");
    expect(html).toContain("Provider unavailable");
    expect(html).toContain(DETERMINISTIC_NOTE);
  });

  it("renders shadow status with env var, parity pending, and applied=false framing", () => {
    const html = renderToStaticMarkup(<MomentumRankingStatusCard status={shadowStatus()} />);
    expect(html).toContain("Shadow — computed, not applied");
    expect(html).toContain("Default mode:");
    expect(html).toContain("Computed — final score unchanged");
    expect(html).toContain("Thinkorswim parity pending");
    expect(html).toContain("MACMARKET_MOMENTUM_RANKING_MODE");
    expect(html).toContain("Parity required for active");
    expect(html).toContain("Shadow mode computes contribution but does not alter final ranking.");
    expect(html).toContain("Real Thinkorswim parity fixtures are still pending.");
    expect(html).toContain(DETERMINISTIC_NOTE);
  });

  it("renders off status with disabled framing and no breakdown", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          mode: "off",
          enabled: false,
          applied_by_default: false,
          reason_codes: [],
        })}
      />,
    );
    expect(html).toContain("Off — not computed");
    expect(html).toContain("Contribution not computed");
  });

  it("renders active status with the parity-pending warning prominently", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          mode: "active",
          applied_by_default: true,
          reason_codes: ["thinkorswim_parity_pending", "active_mode_with_parity_pending"],
          active_mode_warning: "Active mode is applying a bounded momentum contribution while Thinkorswim parity fixtures are still pending review.",
        })}
      />,
    );
    expect(html).toContain("Active — applied to ranking");
    expect(html).toContain("Bounded contribution applied to ranking");
    expect(html).toContain("Active mode while parity pending");
    expect(html).toContain('role="alert"');
    expect(html).toContain("data-testid=\"momentum-ranking-status-active-warning-text\"");
    expect(html).toContain("Thinkorswim parity fixtures are still pending review");
  });

  it("renders invalid-env warning when resolved to shadow", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          mode: "shadow",
          raw_env_value: "bogus-mode",
          invalid_env_value: true,
          reason_codes: ["invalid_env_value_resolved_to_shadow", "thinkorswim_parity_pending"],
        })}
      />,
    );
    expect(html).toContain("Invalid env value — resolved to shadow");
    expect(html).toContain("data-testid=\"momentum-ranking-status-invalid-env\"");
  });

  it("renders parity manifest present in 'good' tone", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          parity_fixture_manifest_present: true,
          real_thinkorswim_parity_pending: false,
          parity_status: "validated_against_thinkorswim_fixture",
          reason_codes: [],
        })}
      />,
    );
    expect(html).toContain("Thinkorswim parity manifest present");
  });

  it("never includes trade-approval or order-routing copy in any branch", () => {
    const html = renderToStaticMarkup(<MomentumRankingStatusCard status={shadowStatus()} />).toLowerCase();
    for (const forbidden of [
      "approve trade",
      "auto approve",
      "route order",
      "buy now",
      "sell now",
      "enter now",
      "short now",
    ]) {
      expect(html.includes(forbidden)).toBe(false);
    }
  });
});
