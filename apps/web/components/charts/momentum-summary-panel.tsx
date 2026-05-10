import React from "react";
import type { ReactNode } from "react";

import { Card, EmptyState, ErrorState, StatusBadge } from "@/components/operator-ui";
import {
  buildMomentumLegendValues,
  describeHigherTimeframeSource,
  describeParityStatus,
  formatMomentumScore,
  getLatestMomentumSnapshot,
  hasMomentumWarning,
  MOMENTUM_DETERMINISTIC_NOTE,
  type MomentumLegendValue,
  type MomentumTone,
} from "@/lib/momentum-chart";
import type { MomentumChartPayload } from "@/lib/momentum-api";

const NOTE_STYLE: React.CSSProperties = {
  margin: 0,
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.78rem",
  lineHeight: 1.5,
};

function formatStateLabel(state: string | null | undefined): string {
  if (!state) return "—";
  return state.replaceAll("_", " ");
}

function ToneBadge({ tone, children, ariaLabel }: { tone: MomentumTone; children: ReactNode; ariaLabel?: string }) {
  return (
    <span aria-label={ariaLabel}>
      <StatusBadge tone={tone}>{children}</StatusBadge>
    </span>
  );
}

export function MomentumSummaryPanel({
  payload,
  loading = false,
  error = null,
  compact = false,
  title = "Momentum Intelligence",
}: {
  payload: MomentumChartPayload | null;
  loading?: boolean;
  error?: string | null;
  compact?: boolean;
  title?: string;
}) {
  if (error) {
    return (
      <Card title={title}>
        <div role="region" aria-label="Momentum Intelligence error" data-testid="momentum-summary-error">
          <ErrorState title="Momentum context unavailable" hint={error} />
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>{MOMENTUM_DETERMINISTIC_NOTE}</p>
        </div>
      </Card>
    );
  }

  if (loading && !payload) {
    return (
      <Card title={title}>
        <div role="region" aria-label="Momentum Intelligence loading" data-testid="momentum-summary-loading">
          <div style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.85rem" }} role="status" aria-live="polite">
            Loading momentum context…
          </div>
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>{MOMENTUM_DETERMINISTIC_NOTE}</p>
        </div>
      </Card>
    );
  }

  if (!payload) {
    return (
      <Card title={title}>
        <div role="region" aria-label="Momentum Intelligence empty" data-testid="momentum-summary-empty">
          <EmptyState title="No momentum context loaded" hint="Run analysis to render the deterministic momentum snapshot." />
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>{MOMENTUM_DETERMINISTIC_NOTE}</p>
        </div>
      </Card>
    );
  }

  const snapshot = getLatestMomentumSnapshot(payload);
  const legend: MomentumLegendValue[] = buildMomentumLegendValues(payload);
  const reversalWarning = Boolean(payload.explanation?.reversal_warning);
  const pullbackSignal = Boolean(payload.explanation?.pullback_signal);
  const noTradeWarning = Boolean(payload.explanation?.no_trade_warning);
  const overallWarning = hasMomentumWarning(payload);
  const htf = describeHigherTimeframeSource(payload.higher_timeframe_source);
  const parity = describeParityStatus(payload.parity_status);

  const headerScoreTone: MomentumTone = snapshot ? legend[0].tone : "neutral";
  const totalLabel = snapshot?.total_label ?? "—";
  const totalState = formatStateLabel(snapshot?.total_state);
  // Phase A3: neutral state must never look bullish or bearish.
  const headerLabel = `${totalLabel} ${formatMomentumScore(snapshot?.total_score ?? null)}`;

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label={`Momentum Intelligence summary — ${headerLabel}`}
        data-testid="momentum-summary"
        className="op-stack"
        style={{ gap: 8 }}
      >
        <div className="op-row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <ToneBadge tone={headerScoreTone} ariaLabel={`Total score ${headerLabel}`}>
            {headerLabel}
          </ToneBadge>
          <ToneBadge tone="neutral">State: {totalState}</ToneBadge>
          {pullbackSignal ? (
            <strong data-testid="momentum-pullback-signal">
              <ToneBadge tone="warn" ariaLabel="Pullback signal active">Pullback signal</ToneBadge>
            </strong>
          ) : null}
          {reversalWarning ? (
            <strong data-testid="momentum-reversal-warning">
              <ToneBadge tone="warn" ariaLabel="Reversal warning active">Reversal warning</ToneBadge>
            </strong>
          ) : null}
          {noTradeWarning && !reversalWarning ? (
            <strong data-testid="momentum-no-trade-warning">
              <ToneBadge tone="warn" ariaLabel="No-trade warning active">No-trade warning</ToneBadge>
            </strong>
          ) : null}
          {overallWarning ? null : !pullbackSignal ? (
            <ToneBadge tone="neutral">Stable</ToneBadge>
          ) : null}
        </div>

        <dl
          className={compact ? "op-grid-2" : "op-grid-3"}
          style={{ gap: compact ? 6 : 8, fontSize: compact ? "0.82rem" : "0.86rem", margin: 0 }}
          aria-label="Momentum Intelligence component breakdown"
        >
          {legend.map((row) => (
            <div
              key={row.label}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "4px 8px",
                borderRadius: 6,
                background: "rgba(15, 24, 34, 0.45)",
                border: "1px solid rgba(115, 138, 163, 0.18)",
                gap: 8,
                minWidth: 0,
              }}
            >
              <dt
                style={{
                  color: "var(--op-muted, #7a8999)",
                  fontSize: "0.78rem",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "normal",
                  wordBreak: "break-word",
                  margin: 0,
                  flex: "1 1 auto",
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

        <div className="op-row" style={{ flexWrap: "wrap", gap: 6 }} aria-label="Momentum Intelligence provenance">
          <ToneBadge tone={payload.fallback_mode ? "warn" : "good"}>
            {payload.fallback_mode ? "Fallback bars" : "Provider-backed bars"}
          </ToneBadge>
          <ToneBadge tone="neutral">Source: {payload.data_source ?? "unavailable"}</ToneBadge>
          <ToneBadge tone={htf.tone} ariaLabel={`Higher timeframe source: ${htf.label}`}>
            {htf.label}
          </ToneBadge>
          {payload.higher_timeframe ? (
            <ToneBadge tone="neutral">HTF: {payload.higher_timeframe}</ToneBadge>
          ) : null}
          <ToneBadge tone={parity.tone} ariaLabel={`Parity status: ${parity.label}`}>
            {parity.label}
          </ToneBadge>
        </div>

        <p style={NOTE_STYLE} data-testid="momentum-deterministic-note">
          {MOMENTUM_DETERMINISTIC_NOTE}
        </p>
      </div>
    </Card>
  );
}
