"use client";

import React from "react";

import { StatusBadge } from "@/components/operator-ui";
import {
  buildCandleStatusBadges,
  buildHiloPanelBadges,
  buildTrueMomentumPanelBadges,
  type VisualParityBadge,
} from "@/lib/momentum-chart";
import type {
  MomentumVisualParityPoint,
  MomentumVisualParitySnapshot,
} from "@/lib/momentum-api";

const ROW_STYLE: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 6,
  alignItems: "center",
  margin: 0,
};

const CHIP_STYLE: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  fontSize: "0.74rem",
};

const LABEL_STYLE: React.CSSProperties = {
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.7rem",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

type ChartStatusBadgesProps = {
  badges: VisualParityBadge[];
  testId?: string;
  ariaLabel?: string;
};

export function ChartStatusBadges({
  badges,
  testId = "chart-status-badges",
  ariaLabel = "Chart status badges",
}: ChartStatusBadgesProps) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      data-testid={testId}
      style={ROW_STYLE}
    >
      {badges.map((badge) => (
        <span
          key={badge.id}
          style={CHIP_STYLE}
          data-testid={`${testId}-${badge.id}`}
          data-unavailable={badge.unavailable ? "true" : "false"}
        >
          <span style={LABEL_STYLE}>{badge.label}</span>
          <StatusBadge tone={badge.tone} aria-label={`${badge.label} ${badge.value}`}>
            {badge.value}
          </StatusBadge>
        </span>
      ))}
    </div>
  );
}

/**
 * Convenience wrapper that renders the candle-panel top-left badges
 * (IV%, Total label, Trend, Momo) from a visual parity snapshot or
 * a per-bar parity point (hover-aware).
 */
export function CandleStatusBadges({
  snapshot,
  testId = "candle-status-badges",
}: {
  snapshot: MomentumVisualParitySnapshot | MomentumVisualParityPoint | null | undefined;
  testId?: string;
}) {
  const badges = buildCandleStatusBadges(snapshot);
  return (
    <ChartStatusBadges
      badges={badges}
      testId={testId}
      ariaLabel="Candle chart status badges"
    />
  );
}

/** Convenience wrapper for the True Momentum panel top-left badges. */
export function TrueMomentumPanelStatusBadges({
  snapshot,
  testId = "true-momentum-panel-status-badges",
}: {
  snapshot: MomentumVisualParitySnapshot | MomentumVisualParityPoint | null | undefined;
  testId?: string;
}) {
  const badges = buildTrueMomentumPanelBadges(snapshot);
  return (
    <ChartStatusBadges
      badges={badges}
      testId={testId}
      ariaLabel="True Momentum panel status badges"
    />
  );
}

/** Convenience wrapper for the HiLo panel top-left badges. */
export function HiloPanelStatusBadges({
  snapshot,
  testId = "hilo-panel-status-badges",
}: {
  snapshot: MomentumVisualParitySnapshot | MomentumVisualParityPoint | null | undefined;
  testId?: string;
}) {
  const badges = buildHiloPanelBadges(snapshot);
  return (
    <ChartStatusBadges
      badges={badges}
      testId={testId}
      ariaLabel="HiLo panel status badges"
    />
  );
}
