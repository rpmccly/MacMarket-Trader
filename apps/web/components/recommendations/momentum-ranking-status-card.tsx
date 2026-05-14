"use client";

import React, { useEffect, useState } from "react";

import { Card, EmptyState, ErrorState, StatusBadge } from "@/components/operator-ui";
import {
  fetchMomentumRankingStatus,
  type MomentumRankingStatus,
} from "@/lib/momentum-ranking-status";
import {
  momentumRankingModeLabel,
  normalizeMomentumRankingMode,
} from "@/lib/momentum-ranking";

const DETERMINISTIC_NOTE =
  "Momentum ranking status is operator readiness context only. It does not approve, reject, size, or route trades.";

const NOTE_STYLE: React.CSSProperties = {
  margin: 0,
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.78rem",
  lineHeight: 1.5,
};

function describeAppliedByDefault(status: MomentumRankingStatus): string {
  if (!status.enabled) return "Contribution not computed";
  if (status.applied_by_default) return "Bounded contribution applied to ranking";
  return "Computed — final score unchanged";
}

function describeParity(status: MomentumRankingStatus): { label: string; tone: "good" | "warn" | "bad" | "neutral" } {
  const workflow = status.thinkorswim_parity_workflow_status;
  if (workflow === "passed") {
    return { label: "Thinkorswim parity passed", tone: "good" };
  }
  if (workflow === "failed") {
    return { label: "Thinkorswim parity failed", tone: "warn" };
  }
  if (workflow === "partial") {
    return { label: "Thinkorswim parity partial — fixture files missing", tone: "warn" };
  }
  if (workflow === "ready") {
    return { label: "Thinkorswim parity ready — run validator", tone: "neutral" };
  }
  if (status.parity_fixture_manifest_present) {
    return { label: "Thinkorswim parity manifest present", tone: "neutral" };
  }
  return { label: "Thinkorswim parity pending", tone: "neutral" };
}

const PARITY_WORKFLOW_LABEL: Record<string, string> = {
  missing: "Missing",
  partial: "Partial",
  ready: "Report available — pending",
  passed: "Passed",
  failed: "Failed",
  pending: "Pending",
};

function parityWorkflowTone(
  workflow: MomentumRankingStatus["thinkorswim_parity_workflow_status"],
): "good" | "warn" | "bad" | "neutral" {
  if (workflow === "passed") return "good";
  if (workflow === "failed") return "warn";
  if (workflow === "partial") return "warn";
  return "neutral";
}

function modeTone(status: MomentumRankingStatus): "good" | "warn" | "bad" | "neutral" {
  const mode = normalizeMomentumRankingMode(status.mode);
  if (mode === "off") return "neutral";
  if (mode === "shadow") return "neutral";
  // active
  return status.real_thinkorswim_parity_pending ? "warn" : "good";
}

const REASON_LABELS: Record<string, string> = {
  invalid_env_value_resolved_to_shadow: "Invalid env value — resolved to shadow",
  thinkorswim_parity_pending: "Thinkorswim parity pending",
  active_mode_with_parity_pending: "Active mode while parity pending",
  active_blocked_parity_required: "Active blocked — parity required",
  // Phase B6 — safety-guard reason codes.
  active_mode_blocked_by_safety_guard: "Active blocked — safety guard not enabled",
  // Thinkorswim parity workflow reason codes.
  thinkorswim_manifest_missing: "Thinkorswim manifest missing",
  thinkorswim_fixture_files_missing: "Thinkorswim fixture files missing",
  thinkorswim_fixture_validation_failed: "Thinkorswim fixture validation failed",
  thinkorswim_parity_passed: "Thinkorswim parity passed",
  thinkorswim_parity_failed: "Thinkorswim parity failed",
  thinkorswim_parity_partial: "Thinkorswim parity partial",
  // Visual / manual observation parity reason codes.
  thinkorswim_visual_parity_passed: "Visual parity passed",
  thinkorswim_visual_parity_failed: "Visual parity failed",
  thinkorswim_visual_parity_observations_available: "Visual parity observations available",
  thinkorswim_visual_observation_missing: "Visual observation not yet recorded",
  thinkorswim_exported_study_csv_unavailable:
    "Exported study CSV parity unavailable / not provided",
  // Visual attestation (no-bars ToS-vs-MM) reason codes.
  thinkorswim_visual_attested: "Visual attestation passed",
  thinkorswim_visual_attestation_failed: "Visual attestation failed",
  thinkorswim_visual_attestation_partial: "Visual attestation partial",
  thinkorswim_visual_attestation_observations_available:
    "Visual attestation observations available",
};

function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code.replaceAll("_", " ");
}

export function MomentumRankingStatusCard({
  status,
  loading = false,
  error = null,
  title = "Momentum ranking status",
}: {
  status: MomentumRankingStatus | null;
  loading?: boolean;
  error?: string | null;
  title?: string;
}) {
  if (error) {
    return (
      <Card title={title}>
        <div role="region" aria-label="Momentum ranking status error" data-testid="momentum-ranking-status-error">
          <ErrorState title="Momentum ranking status unavailable" hint={error} />
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>{DETERMINISTIC_NOTE}</p>
        </div>
      </Card>
    );
  }

  if (loading && !status) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="Momentum ranking status loading"
          data-testid="momentum-ranking-status-loading"
        >
          <div role="status" aria-live="polite" style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.85rem" }}>
            Loading momentum ranking status…
          </div>
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>{DETERMINISTIC_NOTE}</p>
        </div>
      </Card>
    );
  }

  if (!status) {
    return (
      <Card title={title}>
        <div role="region" aria-label="Momentum ranking status unavailable" data-testid="momentum-ranking-status-empty">
          <EmptyState title="Momentum ranking status not loaded" hint="Reload the page to fetch the current Momentum Intelligence ranking mode and parity state." />
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>{DETERMINISTIC_NOTE}</p>
        </div>
      </Card>
    );
  }

  const mode = normalizeMomentumRankingMode(status.mode);
  const requestedMode = normalizeMomentumRankingMode(status.requested_mode ?? mode);
  const effectiveMode = normalizeMomentumRankingMode(status.effective_mode ?? mode);
  const activeAllowed = status.active_allowed === true;
  const activeBlocked = status.active_mode_blocked === true;
  const activeGuardEnvVar = status.active_guard_env_var ?? "MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING";
  const requestedDiffersFromEffective = requestedMode !== effectiveMode;
  const parity = describeParity(status);
  const tone = modeTone(status);
  const activeWithParityPending = mode === "active" && status.real_thinkorswim_parity_pending;

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label={`Momentum ranking status (${mode})`}
        data-testid="momentum-ranking-status-card"
        className="op-stack"
        style={{ gap: 8 }}
      >
        <div className="op-row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <StatusBadge tone={tone} aria-label="Effective Momentum ranking mode">
            Effective: {momentumRankingModeLabel(effectiveMode)}
          </StatusBadge>
          {requestedDiffersFromEffective ? (
            <StatusBadge tone="warn" aria-label="Requested Momentum ranking mode">
              Requested: {momentumRankingModeLabel(requestedMode)}
            </StatusBadge>
          ) : null}
          <StatusBadge tone="neutral">Default mode: {momentumRankingModeLabel(status.default_mode)}</StatusBadge>
          <StatusBadge tone={status.applied_by_default ? "warn" : "neutral"}>
            {describeAppliedByDefault(status)}
          </StatusBadge>
          <StatusBadge tone={parity.tone}>{parity.label}</StatusBadge>
          <StatusBadge
            tone={activeAllowed ? "good" : "neutral"}
            data-testid="momentum-ranking-status-allowed-badge"
          >
            Active allowed: {activeAllowed ? "Yes" : "No"}
          </StatusBadge>
          {status.invalid_env_value ? (
            <strong data-testid="momentum-ranking-status-invalid-env">
              <StatusBadge tone="warn">Invalid env value — resolved to shadow</StatusBadge>
            </strong>
          ) : null}
          {activeBlocked ? (
            <strong data-testid="momentum-ranking-status-safety-guard-block">
              <StatusBadge tone="warn">Active blocked — safety guard not enabled</StatusBadge>
            </strong>
          ) : null}
          {activeWithParityPending ? (
            <strong data-testid="momentum-ranking-status-active-warning">
              <StatusBadge tone="warn">Active mode while parity pending</StatusBadge>
            </strong>
          ) : null}
        </div>

        <div
          className="op-grid-2"
          aria-label="Momentum ranking environment context"
          style={{ gap: 8, fontSize: "0.82rem", margin: 0 }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "4px 8px",
              borderRadius: 6,
              background: "rgba(15, 24, 34, 0.45)",
              border: "1px solid rgba(115, 138, 163, 0.18)",
              gap: 8,
            }}
          >
            <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>Env var</span>
            <code style={{ fontVariantNumeric: "tabular-nums" }}>{status.env_var}</code>
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "4px 8px",
              borderRadius: 6,
              background: "rgba(15, 24, 34, 0.45)",
              border: "1px solid rgba(115, 138, 163, 0.18)",
              gap: 8,
            }}
          >
            <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>Parity required for active</span>
            <StatusBadge tone={status.parity_required_for_active ? "warn" : "neutral"}>
              {status.parity_required_for_active ? "Yes" : "No"}
            </StatusBadge>
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "4px 8px",
              borderRadius: 6,
              background: "rgba(15, 24, 34, 0.45)",
              border: "1px solid rgba(115, 138, 163, 0.18)",
              gap: 8,
            }}
          >
            <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>Active guard env var</span>
            <code style={{ fontVariantNumeric: "tabular-nums" }} data-testid="momentum-ranking-status-active-guard-env-var">
              {activeGuardEnvVar}
            </code>
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "4px 8px",
              borderRadius: 6,
              background: "rgba(15, 24, 34, 0.45)",
              border: "1px solid rgba(115, 138, 163, 0.18)",
              gap: 8,
            }}
          >
            <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>Active delta scale</span>
            <StatusBadge tone={status.active_delta_scale_invalid ? "warn" : "neutral"}>
              {typeof status.active_delta_scale === "number" ? status.active_delta_scale.toFixed(2) : "0.35"}
            </StatusBadge>
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "4px 8px",
              borderRadius: 6,
              background: "rgba(15, 24, 34, 0.45)",
              border: "1px solid rgba(115, 138, 163, 0.18)",
              gap: 8,
            }}
          >
            <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>Active delta scale env var</span>
            <code
              style={{ fontVariantNumeric: "tabular-nums" }}
              data-testid="momentum-ranking-status-active-delta-scale-env-var"
            >
              {status.active_delta_scale_env_var ?? "MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE"}
            </code>
          </div>
        </div>
        <p
          style={{ ...NOTE_STYLE, marginTop: 0 }}
          data-testid="momentum-ranking-status-active-delta-scale-helper"
        >
          Active score delta = raw contribution ÷ 100 × active delta scale.
        </p>
        {status.active_delta_scale_invalid ? (
          <div
            data-testid="momentum-ranking-status-active-delta-scale-invalid"
            role="alert"
            style={{
              padding: "8px 10px",
              borderRadius: 8,
              background: "rgba(76, 56, 24, 0.5)",
              border: "1px solid rgba(242, 160, 63, 0.4)",
              color: "#f2c89a",
              fontSize: "0.85rem",
              lineHeight: 1.5,
            }}
          >
            {status.active_delta_scale_warning ??
              "Configured MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE was unparseable or out of range; falling back to 0.35."}
          </div>
        ) : null}

        {status.active_mode_warning ? (
          <div
            data-testid="momentum-ranking-status-active-warning-text"
            style={{
              padding: "8px 10px",
              borderRadius: 8,
              background: "rgba(76, 56, 24, 0.5)",
              border: "1px solid rgba(242, 160, 63, 0.4)",
              color: "#f2c89a",
              fontSize: "0.85rem",
              lineHeight: 1.5,
            }}
            role="alert"
            aria-label="Active mode warning"
          >
            {status.active_mode_warning}
          </div>
        ) : null}

        {status.reason_codes.length > 0 ? (
          <div className="op-row" style={{ flexWrap: "wrap", gap: 6 }} aria-label="Status reason codes">
            {status.reason_codes.map((code) => (
              <StatusBadge key={code} tone="neutral">
                {reasonLabel(code)}
              </StatusBadge>
            ))}
          </div>
        ) : null}

        {status.guardrails.length > 0 ? (
          <ul
            aria-label="Operator guardrails"
            style={{ margin: 0, paddingLeft: 20, color: "var(--op-muted, #7a8999)", fontSize: "0.82rem", lineHeight: 1.5 }}
          >
            {status.guardrails.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}

        <ThinkorswimParityWorkflowSection status={status} />

        <p style={NOTE_STYLE} data-testid="momentum-ranking-status-deterministic-note">
          {DETERMINISTIC_NOTE}
        </p>
        <p
          style={{ ...NOTE_STYLE, marginTop: 0 }}
          data-testid="momentum-ranking-status-impact-review-pointer"
        >
          Review shadow impact in <a href="/recommendations">Recommendations</a>.
        </p>
        <p
          style={{ ...NOTE_STYLE, marginTop: 0 }}
          data-testid="momentum-ranking-status-trial-journal-pointer"
        >
          Capture trial evidence in <a href="/recommendations">Recommendations</a>.
        </p>
      </div>
    </Card>
  );
}

function ThinkorswimParityWorkflowSection({
  status,
}: {
  status: MomentumRankingStatus;
}) {
  const workflow = status.thinkorswim_parity_workflow_status ?? "missing";
  const workflowLabel = PARITY_WORKFLOW_LABEL[workflow] ?? "Pending";
  const tone = parityWorkflowTone(workflow);
  const fixtureCount = status.thinkorswim_parity_fixture_count ?? 0;
  const fixturesReady = status.thinkorswim_parity_fixtures_ready ?? 0;
  const fixturesPassed = status.thinkorswim_parity_fixtures_passed ?? null;
  const fixturesFailed = status.thinkorswim_parity_fixtures_failed ?? null;
  const reportAvailable = status.thinkorswim_parity_report_available === true;
  const lastReportAt = status.thinkorswim_parity_last_report_generated_at ?? null;
  const reasonCodes = status.thinkorswim_parity_reason_codes ?? [];
  const summary = status.thinkorswim_parity_summary ?? null;
  const reportPath = status.thinkorswim_parity_report_path ?? null;
  const visualCount = status.thinkorswim_parity_visual_observation_count ?? 0;
  const exportedCount = status.thinkorswim_parity_exported_study_csv_count ?? 0;
  const visualPassed = status.thinkorswim_parity_visual_observation_passed_count ?? 0;
  const visualFailed = status.thinkorswim_parity_visual_observation_failed_count ?? 0;
  const visualReviewed = status.thinkorswim_parity_visual_reviewed === true;
  const exportedAvailable = status.thinkorswim_parity_exported_study_csv_available === true;
  const attestationCount = status.thinkorswim_parity_visual_attestation_count ?? 0;
  const attestationPassed = status.thinkorswim_parity_visual_attestation_passed_count ?? 0;
  const attestationFailed = status.thinkorswim_parity_visual_attestation_failed_count ?? 0;
  const attestationPartial = status.thinkorswim_parity_visual_attestation_partial_count ?? 0;
  const attestationStatus = status.thinkorswim_parity_visual_attestation_status ?? null;
  const visualOnly = visualCount > 0 && exportedCount === 0;
  const attestationOnly =
    attestationCount > 0 && visualCount === 0 && exportedCount === 0;
  const attestationStatusLabel = (() => {
    if (attestationStatus === "visual_attested") return "Visual attested";
    if (attestationStatus === "visual_failed") return "Visual failed";
    if (attestationStatus === "visual_partial") return "Visual partial";
    return null;
  })();
  const attestationStatusTone: "good" | "warn" | "neutral" = (() => {
    if (attestationStatus === "visual_attested") return "good";
    if (attestationStatus === "visual_failed") return "warn";
    if (attestationStatus === "visual_partial") return "warn";
    return "neutral";
  })();

  return (
    <div
      role="region"
      aria-label="Thinkorswim parity workflow"
      data-testid="thinkorswim-parity-workflow-section"
      className="op-stack"
      style={{
        gap: 8,
        padding: "10px 12px",
        borderRadius: 8,
        background: "rgba(15, 24, 34, 0.55)",
        border: "1px solid rgba(115, 138, 163, 0.22)",
      }}
    >
      <div className="op-row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <strong style={{ fontSize: "0.85rem" }}>Thinkorswim parity workflow</strong>
        <StatusBadge
          tone={tone}
          data-testid="thinkorswim-parity-workflow-badge"
        >
          {workflowLabel}
        </StatusBadge>
        <StatusBadge tone="neutral" data-testid="thinkorswim-parity-fixture-count-badge">
          Fixtures: {fixturesReady}/{fixtureCount}
        </StatusBadge>
        {reportAvailable ? (
          <StatusBadge tone="neutral" data-testid="thinkorswim-parity-report-available-badge">
            Report available
          </StatusBadge>
        ) : null}
        {fixturesPassed !== null ? (
          <StatusBadge tone={tone}>Passed: {fixturesPassed}</StatusBadge>
        ) : null}
        {fixturesFailed !== null && fixturesFailed > 0 ? (
          <StatusBadge tone="warn">Failed: {fixturesFailed}</StatusBadge>
        ) : null}
      </div>

      <div
        className="op-row"
        style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}
        aria-label="Thinkorswim parity mode counts"
        data-testid="thinkorswim-parity-mode-counts"
      >
        <StatusBadge
          tone={attestationStatusTone}
          data-testid="thinkorswim-parity-visual-attestation-badge"
        >
          Visual attestation fixtures: {attestationCount}
          {attestationCount > 0 ? (
            <>
              {" "}
              ({attestationPassed} passed
              {attestationFailed > 0 ? ` / ${attestationFailed} failed` : ""}
              {attestationPartial > 0 ? ` / ${attestationPartial} partial` : ""})
            </>
          ) : null}
        </StatusBadge>
        {attestationStatusLabel ? (
          <StatusBadge
            tone={attestationStatusTone}
            data-testid="thinkorswim-parity-visual-attestation-status-badge"
          >
            Status: {attestationStatusLabel}
          </StatusBadge>
        ) : null}
        <StatusBadge
          tone={visualReviewed ? (visualFailed > 0 ? "warn" : "good") : "neutral"}
          data-testid="thinkorswim-parity-visual-observation-badge"
        >
          Visual observations: {visualCount}
          {visualReviewed ? (
            <> ({visualPassed} passed{visualFailed > 0 ? ` / ${visualFailed} failed` : ""})</>
          ) : null}
        </StatusBadge>
        <StatusBadge
          tone={exportedAvailable ? "neutral" : "neutral"}
          data-testid="thinkorswim-parity-exported-study-csv-badge"
        >
          Exported study CSVs: {exportedCount}
        </StatusBadge>
        {visualReviewed || attestationCount > 0 ? (
          <StatusBadge tone="neutral" data-testid="thinkorswim-parity-visual-reviewed-badge">
            Visual reviewed
          </StatusBadge>
        ) : null}
        {workflow === "passed" && visualReviewed ? (
          <StatusBadge tone="good" data-testid="thinkorswim-parity-visual-passed-badge">
            Visual parity passed
          </StatusBadge>
        ) : null}
        {workflow === "failed" && visualFailed > 0 ? (
          <StatusBadge tone="warn" data-testid="thinkorswim-parity-visual-failed-badge">
            Visual parity failed
          </StatusBadge>
        ) : null}
      </div>

      {attestationCount > 0 ? (
        <p
          style={{ ...NOTE_STYLE, margin: 0 }}
          data-testid="thinkorswim-parity-visual-attestation-note"
        >
          Visual attestation compares operator-entered ToS and MacMarket (MM) rendered chart values
          because Thinkorswim does not export Momentum study rows or usable bars for this workflow.
        </p>
      ) : null}

      {visualReviewed ? (
        <p
          style={{ ...NOTE_STYLE, margin: 0 }}
          data-testid="thinkorswim-parity-visual-mode-note"
        >
          Visual/manual ToS observations are accepted because Thinkorswim does not export the Momentum study rows.
          Observations are operator-entered from rendered Thinkorswim chart labels and are auditable but not row-level CSV exports.
        </p>
      ) : null}

      {visualOnly ? (
        <p
          style={{ ...NOTE_STYLE, margin: 0 }}
          data-testid="thinkorswim-parity-exported-csv-unavailable-note"
        >
          Exported study CSV parity unavailable / not provided. The visual/manual observation set is the parity basis for this run.
        </p>
      ) : null}

      {summary ? (
        <p
          style={{ ...NOTE_STYLE, margin: 0 }}
          data-testid="thinkorswim-parity-summary"
        >
          {summary}
        </p>
      ) : null}
      {lastReportAt ? (
        <p
          style={{ ...NOTE_STYLE, margin: 0 }}
          data-testid="thinkorswim-parity-last-report"
        >
          Last report generated at <code>{lastReportAt}</code>
          {reportPath ? (
            <>
              {" "}
              (<code>{reportPath}</code>)
            </>
          ) : null}
          .
        </p>
      ) : null}
      {reasonCodes.length > 0 ? (
        <div
          className="op-row"
          style={{ flexWrap: "wrap", gap: 6 }}
          aria-label="Thinkorswim parity reason codes"
          data-testid="thinkorswim-parity-reason-codes"
        >
          {reasonCodes.map((code) => (
            <StatusBadge key={code} tone="neutral">
              {reasonLabel(code)}
            </StatusBadge>
          ))}
        </div>
      ) : null}
      <p
        style={{ ...NOTE_STYLE, margin: 0 }}
        data-testid="thinkorswim-parity-operator-hint"
      >
        Record ToS chart label values (or drop a study CSV when available) and run{" "}
        <code>python scripts/validate_thinkorswim_momentum_parity.py --write-report</code>{" "}
        to update this status. A visual parity pass does not approve, reject, size, or route trades, and does not auto-activate Phase C.
      </p>
    </div>
  );
}

export function MomentumRankingStatusSection({ title }: { title?: string }) {
  const [status, setStatus] = useState<MomentumRankingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      const result = await fetchMomentumRankingStatus();
      if (cancelled) return;
      if (!result.ok || !result.data) {
        setStatus(null);
        setError(result.error ?? "Unable to load momentum ranking status.");
      } else {
        setStatus(result.data);
      }
      setLoading(false);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return <MomentumRankingStatusCard status={status} loading={loading} error={error} title={title} />;
}
