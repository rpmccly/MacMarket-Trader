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
  if (status.parity_fixture_manifest_present) {
    return { label: "Thinkorswim parity manifest present", tone: "good" };
  }
  return { label: "Thinkorswim parity pending", tone: "neutral" };
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
