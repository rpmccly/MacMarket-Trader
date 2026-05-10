import React from "react";
import type { ReactNode } from "react";

import { Card, EmptyState, ErrorState, StatusBadge } from "@/components/operator-ui";
import {
  buildMomentumLegendValues,
  formatMomentumScore,
  getLatestMomentumSnapshot,
  hasMomentumWarning,
  type MomentumLegendValue,
  type MomentumTone,
} from "@/lib/momentum-chart";
import type { MomentumChartPayload } from "@/lib/momentum-api";

const DETERMINISTIC_NOTE =
  "Momentum Intelligence is deterministic context only in Phase A. It does not approve, reject, size, or rank trades.";

function toneBadge(tone: MomentumTone, label: ReactNode) {
  return <StatusBadge tone={tone}>{label}</StatusBadge>;
}

function formatHigherTimeframeSource(value: string | null | undefined): { label: string; tone: MomentumTone } {
  if (value === "provided_higher_timeframe_bars") return { label: "Provided HTF bars", tone: "good" };
  if (value === "derived_from_chart_bars") return { label: "HTF derived from chart bars", tone: "warn" };
  if (value === "insufficient_data") return { label: "HTF insufficient data", tone: "warn" };
  return { label: value ? value.replaceAll("_", " ") : "HTF source unavailable", tone: "neutral" };
}

function formatParityStatus(value: string | null | undefined): { label: string; tone: MomentumTone } {
  if (value === "validated_against_thinkorswim_fixture") return { label: "Parity validated", tone: "good" };
  if (value === "pending_thinkorswim_fixture_validation") return { label: "Parity pending Thinkorswim fixtures", tone: "warn" };
  return { label: value ?? "Parity unknown", tone: "neutral" };
}

function formatStateLabel(state: string | null | undefined): string {
  if (!state) return "—";
  return state.replaceAll("_", " ");
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
        <ErrorState title="Momentum context unavailable" hint={error} />
        <p style={{ marginTop: 8, color: "var(--op-muted, #7a8999)", fontSize: "0.78rem", lineHeight: 1.5 }}>
          {DETERMINISTIC_NOTE}
        </p>
      </Card>
    );
  }

  if (loading && !payload) {
    return (
      <Card title={title}>
        <div style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.85rem" }}>Loading momentum context…</div>
        <p style={{ marginTop: 8, color: "var(--op-muted, #7a8999)", fontSize: "0.78rem", lineHeight: 1.5 }}>
          {DETERMINISTIC_NOTE}
        </p>
      </Card>
    );
  }

  if (!payload) {
    return (
      <Card title={title}>
        <EmptyState title="No momentum context loaded" hint="Run analysis to render the deterministic momentum snapshot." />
        <p style={{ marginTop: 8, color: "var(--op-muted, #7a8999)", fontSize: "0.78rem", lineHeight: 1.5 }}>
          {DETERMINISTIC_NOTE}
        </p>
      </Card>
    );
  }

  const snapshot = getLatestMomentumSnapshot(payload);
  const legend: MomentumLegendValue[] = buildMomentumLegendValues(payload);
  const reversalWarning = Boolean(payload.explanation?.reversal_warning);
  const pullbackSignal = Boolean(payload.explanation?.pullback_signal);
  const noTradeWarning = Boolean(payload.explanation?.no_trade_warning);
  const overallWarning = hasMomentumWarning(payload);
  const htf = formatHigherTimeframeSource(payload.higher_timeframe_source);
  const parity = formatParityStatus(payload.parity_status);

  const headerScoreTone: MomentumTone = snapshot ? legend[0].tone : "neutral";
  const totalLabel = snapshot?.total_label ?? "—";
  const totalState = formatStateLabel(snapshot?.total_state);

  return (
    <Card title={title}>
      <div className="op-stack" style={{ gap: 8 }}>
        <div className="op-row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          {toneBadge(headerScoreTone, `${totalLabel} ${formatMomentumScore(snapshot?.total_score ?? null)}`)}
          <StatusBadge tone="neutral">State: {totalState}</StatusBadge>
          {pullbackSignal ? <StatusBadge tone="warn">Pullback signal</StatusBadge> : null}
          {reversalWarning ? <StatusBadge tone="warn">Reversal warning</StatusBadge> : null}
          {noTradeWarning && !reversalWarning ? <StatusBadge tone="warn">No-trade warning</StatusBadge> : null}
          {overallWarning ? null : !pullbackSignal ? <StatusBadge tone="neutral">Stable</StatusBadge> : null}
        </div>

        <div
          className={compact ? "op-grid-2" : "op-grid-3"}
          style={{ gap: compact ? 6 : 8, fontSize: compact ? "0.82rem" : "0.86rem" }}
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
              }}
            >
              <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>{row.label}</span>
              <StatusBadge tone={row.tone}>{row.value}</StatusBadge>
            </div>
          ))}
        </div>

        <div className="op-row" style={{ flexWrap: "wrap", gap: 6 }}>
          <StatusBadge tone={payload.fallback_mode ? "warn" : "good"}>
            {payload.fallback_mode ? "Fallback bars" : "Provider-backed bars"}
          </StatusBadge>
          <StatusBadge tone="neutral">Source: {payload.data_source ?? "unavailable"}</StatusBadge>
          <StatusBadge tone={htf.tone}>{htf.label}</StatusBadge>
          {payload.higher_timeframe ? (
            <StatusBadge tone="neutral">HTF: {payload.higher_timeframe}</StatusBadge>
          ) : null}
          <StatusBadge tone={parity.tone}>{parity.label}</StatusBadge>
        </div>

        <p
          style={{
            margin: 0,
            color: "var(--op-muted, #7a8999)",
            fontSize: "0.78rem",
            lineHeight: 1.5,
          }}
        >
          {DETERMINISTIC_NOTE}
        </p>
      </div>
    </Card>
  );
}

export const MOMENTUM_DETERMINISTIC_NOTE = DETERMINISTIC_NOTE;
