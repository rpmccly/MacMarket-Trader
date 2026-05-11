"use client";

import React, { useEffect, useState } from "react";

import { Card, EmptyState, ErrorState, StatusBadge } from "@/components/operator-ui";
import {
  fetchTrueMomentumStrategyFamilyStatus,
  trueMomentumStrategyDirectionLabel,
  trueMomentumStrategyModeLabel,
  trueMomentumStrategyReasonLabel,
  TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE,
  type TrueMomentumStrategyFamilySpec,
  type TrueMomentumStrategyFamilyStatus,
} from "@/lib/true-momentum-strategy-families";

const NOTE_STYLE: React.CSSProperties = {
  margin: 0,
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.78rem",
  lineHeight: 1.5,
};

const SUMMARY_CARD_STYLE: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 2,
  padding: "6px 10px",
  borderRadius: 6,
  background: "rgba(15, 24, 34, 0.45)",
  border: "1px solid rgba(115, 138, 163, 0.18)",
  minWidth: 120,
};

const SUMMARY_LABEL_STYLE: React.CSSProperties = {
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.72rem",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const SUMMARY_VALUE_STYLE: React.CSSProperties = {
  fontVariantNumeric: "tabular-nums",
  fontSize: "1.05rem",
  fontWeight: 600,
};

function modeTone(status: TrueMomentumStrategyFamilyStatus | null | undefined): "good" | "warn" | "neutral" {
  if (!status) return "neutral";
  if (status.effective_mode === "disabled") return "neutral";
  if (status.effective_mode === "research_preview") return "warn";
  return "neutral";
}

function FamilySpecRow({ spec }: { spec: TrueMomentumStrategyFamilySpec }) {
  return (
    <tr
      data-testid="true-momentum-family-row"
      data-family-id={spec.id}
    >
      <td style={{ fontWeight: 600 }}>{spec.label}</td>
      <td>
        <StatusBadge tone="neutral">{spec.status}</StatusBadge>
      </td>
      <td>{trueMomentumStrategyDirectionLabel(spec.intended_direction)}</td>
      <td style={{ color: "var(--op-muted, #7a8999)" }}>{spec.description}</td>
    </tr>
  );
}

export function TrueMomentumStrategyFamiliesStatusCardView({
  status,
  loading = false,
  error = null,
  title = "True Momentum strategy families (Phase C0 scaffolding)",
}: {
  status: TrueMomentumStrategyFamilyStatus | null;
  loading?: boolean;
  error?: string | null;
  title?: string;
}) {
  if (error) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="True Momentum strategy family status error"
          data-testid="true-momentum-strategy-families-status-error"
        >
          <ErrorState
            title="True Momentum strategy family status unavailable"
            hint={error}
          />
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>
            {TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }

  if (loading && !status) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="True Momentum strategy family status loading"
          data-testid="true-momentum-strategy-families-status-loading"
        >
          <div
            role="status"
            aria-live="polite"
            style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.85rem" }}
          >
            Loading True Momentum strategy family status…
          </div>
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>
            {TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }

  if (!status) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="True Momentum strategy family status empty"
          data-testid="true-momentum-strategy-families-status-empty"
        >
          <EmptyState
            title="True Momentum strategy family status unavailable"
            hint="Status will appear once the backend endpoint responds."
          />
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>
            {TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label="True Momentum strategy family status"
        data-testid="true-momentum-strategy-families-status"
        className="op-stack"
        style={{ gap: 10 }}
      >
        <div className="op-row" style={{ flexWrap: "wrap", gap: 6, alignItems: "center" }}>
          <StatusBadge tone="neutral">
            Phase {status.phase} · {status.implementation_status}
          </StatusBadge>
          <StatusBadge tone={modeTone(status)} data-testid="true-momentum-effective-mode-badge">
            Effective: {trueMomentumStrategyModeLabel(status.effective_mode)}
          </StatusBadge>
          <StatusBadge tone="neutral" data-testid="true-momentum-requested-mode-badge">
            Requested: {trueMomentumStrategyModeLabel(status.requested_mode)}
          </StatusBadge>
          <StatusBadge tone={status.guard_enabled ? "good" : "neutral"}>
            Guard: {status.guard_enabled ? "enabled" : "disabled"}
          </StatusBadge>
        </div>

        <div className="op-row" style={{ flexWrap: "wrap", gap: 8 }}>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Mode env var</span>
            <span style={{ ...SUMMARY_VALUE_STYLE, fontSize: "0.85rem" }}>
              {status.mode_env_var}
            </span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Guard env var</span>
            <span style={{ ...SUMMARY_VALUE_STYLE, fontSize: "0.85rem" }}>
              {status.guard_env_var}
            </span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Parity status</span>
            <span style={{ ...SUMMARY_VALUE_STYLE, fontSize: "0.85rem" }}>
              {status.parity_status}
            </span>
          </div>
        </div>

        {status.reason_codes.length > 0 ? (
          <div
            className="op-row"
            style={{ flexWrap: "wrap", gap: 4 }}
            data-testid="true-momentum-reason-codes"
          >
            {status.reason_codes.map((code) => (
              <StatusBadge key={code} tone="warn">
                {trueMomentumStrategyReasonLabel(code)}
              </StatusBadge>
            ))}
          </div>
        ) : null}

        <div data-testid="true-momentum-family-specs" style={{ overflowX: "auto", minWidth: 0 }}>
          <h4 style={{ margin: "4px 0 6px 0", fontSize: "0.92rem" }}>Planned families</h4>
          <table className="op-table" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>Family</th>
                <th style={{ textAlign: "left" }}>Status</th>
                <th style={{ textAlign: "left" }}>Intended direction</th>
                <th style={{ textAlign: "left" }}>Description</th>
              </tr>
            </thead>
            <tbody>
              {status.family_specs.map((spec) => (
                <FamilySpecRow key={spec.id} spec={spec} />
              ))}
            </tbody>
          </table>
        </div>

        <ul
          data-testid="true-momentum-guardrails"
          style={{
            margin: 0,
            paddingLeft: 18,
            color: "var(--op-muted, #7a8999)",
            fontSize: "0.82rem",
            lineHeight: 1.55,
          }}
        >
          {status.guardrails.map((line, idx) => (
            <li key={`guardrail-${idx}`}>{line}</li>
          ))}
        </ul>

        <p
          style={NOTE_STYLE}
          data-testid="true-momentum-strategy-families-deterministic-note"
        >
          {TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE}
        </p>

        <p style={NOTE_STYLE} data-testid="true-momentum-still-pending">
          Still pending: Thinkorswim fixture parity · active trial outcome review.
        </p>
      </div>
    </Card>
  );
}

export function TrueMomentumStrategyFamiliesStatusCard({
  title,
  initialStatus = null,
}: {
  title?: string;
  /**
   * Test-only: render with a pre-fetched status instead of triggering
   * the backend fetch. Production callers should leave this undefined.
   */
  initialStatus?: TrueMomentumStrategyFamilyStatus | null;
}) {
  const [status, setStatus] = useState<TrueMomentumStrategyFamilyStatus | null>(initialStatus);
  const [loading, setLoading] = useState<boolean>(!initialStatus);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialStatus) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      const result = await fetchTrueMomentumStrategyFamilyStatus();
      if (cancelled) return;
      setLoading(false);
      if (result.authPending) {
        setError(null);
        setStatus(null);
        return;
      }
      if (!result.ok) {
        setError(result.error ?? "Unable to load True Momentum strategy family status.");
        return;
      }
      setStatus(result.data);
      setError(null);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [initialStatus]);

  return (
    <TrueMomentumStrategyFamiliesStatusCardView
      status={status}
      loading={loading}
      error={error}
      title={title}
    />
  );
}
