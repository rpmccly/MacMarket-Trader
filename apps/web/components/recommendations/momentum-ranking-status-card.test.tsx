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
    StatusBadge: ({
      tone,
      children,
      ...rest
    }: {
      tone?: string;
      children: ReactNode;
      [key: string]: unknown;
    }) =>
      ReactModule.createElement(
        "span",
        { className: `op-badge op-badge-${tone ?? "neutral"}`, ...rest },
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
    active_delta_scale: 0.35,
    active_delta_scale_env_var: "MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE",
    active_delta_scale_invalid: false,
    active_delta_scale_warning: null,
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
      "Approval, sizing, and paper-order creation remain manual.",
      "Active mode changes ranking order only; it does not approve, reject, size, or route trades.",
      "Active Momentum ranking requires MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true.",
      "Thinkorswim parity fixtures are still pending.",
    ],
    requested_mode: "shadow",
    effective_mode: "shadow",
    active_allowed: false,
    active_guard_env_var: "MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING",
    active_mode_blocked: false,
    active_mode_block_reason: null,
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
    expect(html).toContain("Thinkorswim parity fixtures are still pending.");
    expect(html).toContain(DETERMINISTIC_NOTE);
  });

  it("renders off status with disabled framing and no breakdown", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          mode: "off",
          requested_mode: "off",
          effective_mode: "off",
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
          requested_mode: "active",
          effective_mode: "active",
          active_allowed: true,
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

  // ── Phase B6 — safety-guard rendering ───────────────────────────────

  it("renders blocked-active warning when active was requested without the safety guard", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          mode: "shadow",
          requested_mode: "active",
          effective_mode: "shadow",
          active_allowed: false,
          active_mode_blocked: true,
          active_mode_block_reason:
            "Active Momentum ranking was requested but blocked because MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING is not enabled.",
          reason_codes: ["thinkorswim_parity_pending", "active_mode_blocked_by_safety_guard"],
          active_mode_warning:
            "Active Momentum ranking was requested but blocked because MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING is not enabled.",
        })}
      />,
    );
    expect(html).toContain("Effective: Shadow — computed, not applied");
    expect(html).toContain("Requested: Active — applied to ranking");
    expect(html).toContain("Active blocked — safety guard not enabled");
    expect(html).toContain("Active allowed: No");
    expect(html).toContain("MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING");
    expect(html).toContain('data-testid="momentum-ranking-status-safety-guard-block"');
    expect(html).toContain('role="alert"');
  });

  it("renders allowed-active state with active allowed badge in good tone", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          mode: "active",
          requested_mode: "active",
          effective_mode: "active",
          active_allowed: true,
          active_mode_blocked: false,
          applied_by_default: true,
          reason_codes: ["thinkorswim_parity_pending", "active_mode_with_parity_pending"],
        })}
      />,
    );
    expect(html).toContain("Effective: Active — applied to ranking");
    expect(html).toContain("Active allowed: Yes");
    expect(html).not.toContain("Active blocked — safety guard not enabled");
  });

  it("renders Phase B6 guardrail copy when supplied", () => {
    const html = renderToStaticMarkup(<MomentumRankingStatusCard status={shadowStatus()} />);
    expect(html).toContain("Approval, sizing, and paper-order creation remain manual.");
    expect(html).toContain(
      "Active mode changes ranking order only; it does not approve, reject, size, or route trades.",
    );
    expect(html).toContain(
      "Active Momentum ranking requires MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true.",
    );
    expect(html).toContain("Thinkorswim parity fixtures are still pending.");
  });

  it("renders the active guard env var label", () => {
    const html = renderToStaticMarkup(<MomentumRankingStatusCard status={shadowStatus()} />);
    expect(html).toContain("Active guard env var");
    expect(html).toContain('data-testid="momentum-ranking-status-active-guard-env-var"');
    expect(html).toContain("MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING");
  });

  // ── Phase B6.1 — active delta scale rendering ────────────────────────

  it("renders the Phase B6.1 active delta scale + env var", () => {
    const html = renderToStaticMarkup(<MomentumRankingStatusCard status={shadowStatus()} />);
    expect(html).toContain("Active delta scale");
    expect(html).toContain("0.35");
    expect(html).toContain('data-testid="momentum-ranking-status-active-delta-scale-env-var"');
    expect(html).toContain("MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE");
    expect(html).toContain("Active score delta = raw contribution ÷ 100 × active delta scale.");
  });

  it("renders the invalid-scale alert when active_delta_scale_invalid is true", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          active_delta_scale: 0.35,
          active_delta_scale_invalid: true,
          active_delta_scale_warning:
            "Configured MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE was unparseable or out of range [0.0, 1.0]; falling back to the deterministic default 0.35.",
          reason_codes: ["thinkorswim_parity_pending", "momentum_active_delta_scale_invalid"],
        })}
      />,
    );
    expect(html).toContain("data-testid=\"momentum-ranking-status-active-delta-scale-invalid\"");
    expect(html).toContain("MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE");
    expect(html).toContain("falling back to the deterministic default 0.35");
  });

  // ── Thinkorswim parity workflow ─────────────────────────────────────

  it("renders the Thinkorswim parity workflow section (missing) by default", () => {
    const html = renderToStaticMarkup(<MomentumRankingStatusCard status={shadowStatus()} />);
    expect(html).toContain('data-testid="thinkorswim-parity-workflow-section"');
    expect(html).toContain('data-testid="thinkorswim-parity-workflow-badge"');
    expect(html).toContain('data-testid="thinkorswim-parity-fixture-count-badge"');
    expect(html).toContain('data-testid="thinkorswim-parity-operator-hint"');
    expect(html).toContain("Thinkorswim parity workflow");
    expect(html).toContain("python scripts/validate_thinkorswim_momentum_parity.py");
  });

  it("renders 'Passed' status when the parity workflow reports passed", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          thinkorswim_parity_workflow_status: "passed",
          thinkorswim_parity_fixture_count: 5,
          thinkorswim_parity_fixtures_ready: 5,
          thinkorswim_parity_fixtures_passed: 5,
          thinkorswim_parity_fixtures_failed: 0,
          thinkorswim_parity_report_available: true,
          thinkorswim_parity_last_report_generated_at: "2026-05-12T01:00:00+00:00",
          thinkorswim_parity_reason_codes: ["thinkorswim_parity_passed"],
          thinkorswim_parity_summary: "Parity passed for 5/5 fixtures.",
          parity_fixture_manifest_present: true,
        })}
      />,
    );
    expect(html).toContain("Passed");
    expect(html).toContain("Fixtures: 5/5");
    expect(html).toContain("Passed: 5");
    expect(html).toContain('data-testid="thinkorswim-parity-report-available-badge"');
    expect(html).toContain("Parity passed for 5/5 fixtures");
    expect(html).toContain("Thinkorswim parity passed");
    expect(html).toContain('data-testid="thinkorswim-parity-last-report"');
  });

  it("renders 'Failed' status when the parity workflow reports failed", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          thinkorswim_parity_workflow_status: "failed",
          thinkorswim_parity_fixture_count: 5,
          thinkorswim_parity_fixtures_ready: 5,
          thinkorswim_parity_fixtures_passed: 3,
          thinkorswim_parity_fixtures_failed: 2,
          thinkorswim_parity_report_available: true,
          thinkorswim_parity_reason_codes: ["thinkorswim_parity_failed"],
          thinkorswim_parity_summary: "Parity failed for 2 fixture(s). Review parity-report.md.",
          parity_fixture_manifest_present: true,
        })}
      />,
    );
    expect(html).toContain("Failed");
    expect(html).toContain("Failed: 2");
    expect(html).toContain("Thinkorswim parity failed");
    expect(html).toContain("Parity failed for 2 fixture(s)");
  });

  it("renders 'Partial' status when fixture files are missing", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          thinkorswim_parity_workflow_status: "partial",
          thinkorswim_parity_fixture_count: 5,
          thinkorswim_parity_fixtures_ready: 2,
          thinkorswim_parity_reason_codes: ["thinkorswim_fixture_files_missing"],
          thinkorswim_parity_summary:
            "2/5 fixtures have all required CSV files. Add the missing files and rerun the validator.",
          parity_fixture_manifest_present: true,
        })}
      />,
    );
    expect(html).toContain("Partial");
    expect(html).toContain("Fixtures: 2/5");
    expect(html).toContain("Thinkorswim fixture files missing");
  });

  it("parity workflow section never includes approval/order/route language", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          thinkorswim_parity_workflow_status: "passed",
          thinkorswim_parity_fixtures_passed: 5,
          thinkorswim_parity_fixture_count: 5,
          thinkorswim_parity_report_available: true,
        })}
      />,
    ).toLowerCase();
    // Affirmative trade-action / approval / routing language must never
    // appear here. The hint copy contains the negation "does not
    // auto-activate Phase C" so we deliberately don't list
    // "activate phase c" as a forbidden substring (it matches the
    // negation by substring).
    for (const forbidden of [
      "approve trade",
      "auto approve",
      "route order",
      "place order",
      "promote to recommendation",
      "buy now",
      "sell now",
    ]) {
      expect(html.includes(forbidden)).toBe(false);
    }
    // A parity pass surfaces explicit non-activation copy.
    expect(html).toContain("does not auto-activate phase c");
  });

  // ── Visual / manual observation parity mode rendering ─────────────

  it("renders visual_observation mode counts when present", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          thinkorswim_parity_workflow_status: "ready",
          thinkorswim_parity_fixture_count: 2,
          thinkorswim_parity_fixtures_ready: 2,
          thinkorswim_parity_visual_observation_count: 2,
          thinkorswim_parity_exported_study_csv_count: 0,
          thinkorswim_parity_visual_reviewed: true,
          thinkorswim_parity_exported_study_csv_available: false,
          thinkorswim_parity_reason_codes: [
            "thinkorswim_parity_pending",
            "thinkorswim_visual_parity_observations_available",
            "thinkorswim_exported_study_csv_unavailable",
          ],
        })}
      />,
    );
    expect(html).toContain('data-testid="thinkorswim-parity-visual-observation-badge"');
    expect(html).toContain("Visual observations: 2");
    expect(html).toContain('data-testid="thinkorswim-parity-exported-study-csv-badge"');
    expect(html).toContain("Exported study CSVs: 0");
    expect(html).toContain('data-testid="thinkorswim-parity-visual-reviewed-badge"');
    expect(html).toContain("Visual/manual ToS observations are accepted");
    expect(html).toContain("Exported study CSV parity unavailable");
    expect(html).toContain("Visual parity observations available");
    expect(html).toContain("Exported study CSV parity unavailable / not provided");
  });

  it("renders visual_passed badge when the visual parity report passes", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          thinkorswim_parity_workflow_status: "passed",
          thinkorswim_parity_fixture_count: 3,
          thinkorswim_parity_fixtures_ready: 3,
          thinkorswim_parity_fixtures_passed: 3,
          thinkorswim_parity_fixtures_failed: 0,
          thinkorswim_parity_visual_observation_count: 3,
          thinkorswim_parity_visual_observation_passed_count: 3,
          thinkorswim_parity_visual_observation_failed_count: 0,
          thinkorswim_parity_visual_reviewed: true,
          thinkorswim_parity_exported_study_csv_count: 0,
          thinkorswim_parity_report_available: true,
          thinkorswim_parity_reason_codes: [
            "thinkorswim_parity_passed",
            "thinkorswim_visual_parity_passed",
            "thinkorswim_exported_study_csv_unavailable",
          ],
        })}
      />,
    );
    expect(html).toContain('data-testid="thinkorswim-parity-visual-passed-badge"');
    expect(html).toContain("Visual parity passed");
  });

  it("renders visual_failed badge when the visual parity report fails", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          thinkorswim_parity_workflow_status: "failed",
          thinkorswim_parity_fixture_count: 3,
          thinkorswim_parity_fixtures_ready: 3,
          thinkorswim_parity_fixtures_passed: 2,
          thinkorswim_parity_fixtures_failed: 1,
          thinkorswim_parity_visual_observation_count: 3,
          thinkorswim_parity_visual_observation_passed_count: 2,
          thinkorswim_parity_visual_observation_failed_count: 1,
          thinkorswim_parity_visual_reviewed: true,
          thinkorswim_parity_exported_study_csv_count: 0,
          thinkorswim_parity_report_available: true,
          thinkorswim_parity_reason_codes: [
            "thinkorswim_parity_failed",
            "thinkorswim_visual_parity_failed",
          ],
        })}
      />,
    );
    expect(html).toContain('data-testid="thinkorswim-parity-visual-failed-badge"');
    expect(html).toContain("Visual parity failed");
  });

  it("renders exported_study_csv mode counts when only exported CSV fixtures are present", () => {
    const html = renderToStaticMarkup(
      <MomentumRankingStatusCard
        status={shadowStatus({
          thinkorswim_parity_workflow_status: "passed",
          thinkorswim_parity_fixture_count: 2,
          thinkorswim_parity_fixtures_ready: 2,
          thinkorswim_parity_fixtures_passed: 2,
          thinkorswim_parity_visual_observation_count: 0,
          thinkorswim_parity_exported_study_csv_count: 2,
          thinkorswim_parity_visual_reviewed: false,
          thinkorswim_parity_exported_study_csv_available: true,
          thinkorswim_parity_report_available: true,
        })}
      />,
    );
    expect(html).toContain("Visual observations: 0");
    expect(html).toContain("Exported study CSVs: 2");
    // Visual reviewed badge should NOT render when no visual observations exist.
    expect(html).not.toContain('data-testid="thinkorswim-parity-visual-reviewed-badge"');
    // Visual-only banner copy should NOT render.
    expect(html).not.toContain('data-testid="thinkorswim-parity-exported-csv-unavailable-note"');
  });

  it("renders the parity workflow as missing when no fixtures exist", () => {
    const html = renderToStaticMarkup(<MomentumRankingStatusCard status={shadowStatus()} />);
    expect(html).toContain('data-testid="thinkorswim-parity-visual-observation-badge"');
    expect(html).toContain("Visual observations: 0");
    expect(html).toContain("Exported study CSVs: 0");
    // No approval/order language in any branch.
    const lower = html.toLowerCase();
    for (const forbidden of ["approve trade", "route order", "place order"]) {
      expect(lower.includes(forbidden)).toBe(false);
    }
  });
});
