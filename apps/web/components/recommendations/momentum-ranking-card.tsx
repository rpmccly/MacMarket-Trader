import React from "react";

import { Card, EmptyState, StatusBadge } from "@/components/operator-ui";
import {
  buildMomentumRankingBreakdown,
  formatMomentumContribution,
  getMomentumContributionReasonLabels,
  hasMomentumRankingWarnings,
  isMomentumContributionApplied,
  isMomentumContributionShadow,
  MOMENTUM_RANKING_DETERMINISTIC_NOTE,
  momentumContributionTone,
  momentumRankingAppliedLabel,
  momentumRankingModeLabel,
  momentumScoreContextRow,
  normalizeMomentumRankingMode,
  type MomentumRankingTone,
} from "@/lib/momentum-ranking";
import type { MomentumRankingContribution } from "@/lib/recommendations";

const NOTE_STYLE: React.CSSProperties = {
  margin: 0,
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.78rem",
  lineHeight: 1.5,
};

function rowStyle(compact: boolean): React.CSSProperties {
  return {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: compact ? "3px 6px" : "4px 8px",
    borderRadius: 6,
    background: "rgba(15, 24, 34, 0.45)",
    border: "1px solid rgba(115, 138, 163, 0.18)",
    gap: 8,
    minWidth: 0,
  };
}

function ToneBadge({ tone, ariaLabel, children }: { tone: MomentumRankingTone; ariaLabel?: string; children: React.ReactNode }) {
  return (
    <span aria-label={ariaLabel}>
      <StatusBadge tone={tone}>{children}</StatusBadge>
    </span>
  );
}

export function MomentumRankingCard({
  contribution,
  compact = false,
  title = "Momentum ranking contribution",
}: {
  contribution: MomentumRankingContribution | null | undefined;
  compact?: boolean;
  title?: string;
}) {
  if (!contribution) {
    return (
      <Card title={title}>
        <div role="region" aria-label="Momentum ranking contribution missing" data-testid="momentum-ranking-card-missing">
          <EmptyState
            title="Momentum ranking contribution not available"
            hint="Selected recommendation does not carry a momentum ranking contribution."
          />
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>{MOMENTUM_RANKING_DETERMINISTIC_NOTE}</p>
        </div>
      </Card>
    );
  }

  const mode = normalizeMomentumRankingMode(contribution.mode);
  const enabled = contribution.enabled !== false && mode !== "off";

  if (!enabled) {
    return (
      <Card title={title}>
        <div role="region" aria-label="Momentum ranking contribution off" data-testid="momentum-ranking-card-off">
          <div className="op-row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <StatusBadge tone="neutral">{momentumRankingModeLabel(mode)}</StatusBadge>
            <StatusBadge tone="neutral">{momentumRankingAppliedLabel(contribution)}</StatusBadge>
          </div>
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>{MOMENTUM_RANKING_DETERMINISTIC_NOTE}</p>
        </div>
      </Card>
    );
  }

  const breakdown = buildMomentumRankingBreakdown(contribution);
  const scoreContext = momentumScoreContextRow(contribution);
  const appliedLabel = momentumRankingAppliedLabel(contribution);
  const tone = momentumContributionTone(contribution);
  const applied = isMomentumContributionApplied(contribution);
  const shadow = isMomentumContributionShadow(contribution);
  const warningActive = hasMomentumRankingWarnings(contribution);
  const reasonLabels = getMomentumContributionReasonLabels(contribution.reason_codes);

  const headerContrib = applied
    ? formatMomentumContribution(contribution.total_contribution ?? 0)
    : formatMomentumContribution(contribution.shadow_contribution ?? 0);

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label={`Momentum ranking contribution (${mode})`}
        data-testid="momentum-ranking-card"
        className="op-stack"
        style={{ gap: 8 }}
      >
        <div className="op-row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <ToneBadge tone="neutral" ariaLabel={`Mode: ${mode}`}>
            {momentumRankingModeLabel(mode)}
          </ToneBadge>
          <ToneBadge tone={shadow ? "neutral" : tone} ariaLabel={appliedLabel}>
            {appliedLabel}
          </ToneBadge>
          <ToneBadge
            tone={applied ? tone : shadow ? "neutral" : tone}
            ariaLabel={
              applied
                ? `Applied contribution ${headerContrib}`
                : `Shadow contribution ${headerContrib}`
            }
          >
            {applied ? "Applied" : "Shadow"} {headerContrib}
          </ToneBadge>
          {shadow ? (
            <StatusBadge tone="neutral" data-testid="momentum-ranking-final-score-unchanged">
              Final score unchanged
            </StatusBadge>
          ) : null}
          {warningActive ? (
            <strong data-testid="momentum-ranking-warning">
              <ToneBadge tone="warn" ariaLabel="Momentum ranking warning active">
                Warning
              </ToneBadge>
            </strong>
          ) : null}
        </div>

        <dl
          className={compact ? "op-grid-2" : "op-grid-3"}
          aria-label="Momentum ranking component breakdown"
          style={{ gap: compact ? 6 : 8, fontSize: compact ? "0.82rem" : "0.86rem", margin: 0 }}
        >
          {breakdown.map((row) => (
            <div key={row.label} style={rowStyle(compact)} title={row.hint}>
              <dt
                style={{
                  color: "var(--op-muted, #7a8999)",
                  fontSize: "0.78rem",
                  margin: 0,
                  flex: "1 1 auto",
                  minWidth: 0,
                  wordBreak: "break-word",
                }}
              >
                {row.label}
              </dt>
              <dd style={{ margin: 0, flex: "0 0 auto" }}>
                <ToneBadge tone={row.tone} ariaLabel={`${row.label} ${row.value}`}>
                  {row.value}
                </ToneBadge>
              </dd>
            </div>
          ))}
        </dl>

        <div
          className="op-grid-2"
          aria-label="Momentum score context"
          style={{ gap: 8, fontSize: "0.82rem", margin: 0 }}
        >
          <div style={rowStyle(false)}>
            <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>Total score</span>
            <span>
              {scoreContext.totalScore}{" "}
              <span style={{ color: "var(--op-muted, #7a8999)" }}>({scoreContext.totalLabel})</span>
            </span>
          </div>
          <div style={rowStyle(false)}>
            <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>Trend / Momo</span>
            <span>
              {scoreContext.trend} / {scoreContext.momo}
            </span>
          </div>
        </div>

        {reasonLabels.length > 0 ? (
          <div
            className="op-row"
            style={{ flexWrap: "wrap", gap: 6 }}
            aria-label="Momentum ranking reason codes"
            data-testid="momentum-ranking-reason-chips"
          >
            {reasonLabels.map((label) => (
              <StatusBadge key={label} tone="neutral">
                {label}
              </StatusBadge>
            ))}
          </div>
        ) : null}

        {contribution.inferred_direction ? (
          <div style={{ fontSize: "0.78rem", color: "var(--op-muted, #7a8999)" }} data-testid="momentum-ranking-direction">
            Inferred direction: {String(contribution.inferred_direction)}
          </div>
        ) : null}

        <p style={NOTE_STYLE} data-testid="momentum-ranking-deterministic-note">
          {MOMENTUM_RANKING_DETERMINISTIC_NOTE}
        </p>
      </div>
    </Card>
  );
}

export function MomentumRankingInlineBadge({
  contribution,
}: {
  contribution: MomentumRankingContribution | null | undefined;
}) {
  // Tiny indicator suitable for dense rows. Renders nothing when contribution
  // is absent or disabled so list rows stay compact.
  if (!contribution) return null;
  const mode = normalizeMomentumRankingMode(contribution.mode);
  if (mode === "off" || contribution.enabled === false) return null;
  const label =
    mode === "active"
      ? `Momentum active ${formatMomentumContribution(contribution.total_contribution ?? 0)}`
      : `Momentum shadow ${formatMomentumContribution(contribution.shadow_contribution ?? 0)}`;
  return (
    <span data-testid="momentum-ranking-inline-badge" aria-label={label}>
      <StatusBadge tone="neutral">{label}</StatusBadge>
    </span>
  );
}
