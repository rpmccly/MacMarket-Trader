"use client";

import React, { useMemo, useState } from "react";

import { Card, EmptyState, StatusBadge } from "@/components/operator-ui";
import {
  buildMomentumImpactRows,
  estimateActiveRankDelta,
  formatRankDelta,
  formatScoreUnit,
  formatUnitScore,
  MOMENTUM_IMPACT_DETERMINISTIC_NOTE,
  momentumImpactTone,
  sortMomentumImpactRows,
  summarizeMomentumImpact,
  type MomentumImpactRow,
  type MomentumImpactSortMode,
} from "@/lib/momentum-impact";
import {
  getMomentumContributionReasonLabels,
  momentumRankingModeLabel,
  normalizeMomentumRankingMode,
} from "@/lib/momentum-ranking";
import type { MomentumRankingMode, QueueCandidate } from "@/lib/recommendations";

const NOTE_STYLE: React.CSSProperties = {
  margin: 0,
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.78rem",
  lineHeight: 1.5,
};

function effectiveMode(rows: MomentumImpactRow[]): MomentumRankingMode {
  // The review is mode-aware: pick the most common non-off mode if any
  // candidates carry a contribution, otherwise "off". Operators who run
  // in mixed modes (unusual) still see the dominant framing plus
  // per-row mode badges.
  if (rows.length === 0) return "off";
  const tally = new Map<MomentumRankingMode, number>();
  for (const row of rows) {
    tally.set(row.mode, (tally.get(row.mode) ?? 0) + 1);
  }
  // Prefer active > shadow > off when tied.
  const order: MomentumRankingMode[] = ["active", "shadow", "off"];
  let best: MomentumRankingMode = "off";
  let bestCount = -1;
  for (const mode of order) {
    const count = tally.get(mode) ?? 0;
    if (count > bestCount) {
      best = mode;
      bestCount = count;
    }
  }
  return best;
}

function modeFraming(mode: MomentumRankingMode, blockedActive: boolean): string {
  if (blockedActive) {
    return "Active was requested but the safety guard blocked application; review is running as shadow. Final scores are unchanged. Active Momentum ranking requires MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true.";
  }
  switch (mode) {
    case "active":
      return "Momentum contribution is currently applied to ranking. Approval and paper orders remain manual. Active mode changes ranking order only; it does not approve, reject, size, or route trades.";
    case "shadow":
      return "Shadow mode is enabled. Final scores are unchanged. The estimated active score shows what would happen if active mode were enabled.";
    case "off":
      return "Momentum contribution is disabled (off) or not computed. No estimated movement is shown.";
  }
}

function modeBadgeTone(mode: MomentumRankingMode): "good" | "warn" | "bad" | "neutral" {
  if (mode === "active") return "warn";
  if (mode === "shadow") return "neutral";
  return "neutral";
}

const SORT_OPTIONS: Array<{ id: MomentumImpactSortMode; label: string }> = [
  { id: "rank_asc", label: "Current rank" },
  { id: "estimated_score_desc", label: "Estimated active score" },
  { id: "score_delta_desc", label: "Score delta" },
  { id: "warning_first", label: "Warnings first" },
];

export function MomentumImpactReview({
  candidates,
  compact = false,
  title = "Momentum Shadow Impact Review",
}: {
  candidates: ReadonlyArray<QueueCandidate> | null | undefined;
  compact?: boolean;
  title?: string;
}) {
  const [sortMode, setSortMode] = useState<MomentumImpactSortMode>("rank_asc");
  const [collapsed, setCollapsed] = useState<boolean>(false);

  const rows = useMemo(() => buildMomentumImpactRows(candidates ?? []), [candidates]);
  const sortedRows = useMemo(() => sortMomentumImpactRows(rows, sortMode), [rows, sortMode]);
  const summary = useMemo(() => summarizeMomentumImpact(rows), [rows]);
  const rankDelta = useMemo(() => estimateActiveRankDelta(rows), [rows]);
  // Phase B6 — detect blocked-active state from per-row reason codes so the
  // review can swap framing copy without needing the status endpoint.
  const blockedActive = useMemo(
    () => rows.some((row) => row.reasonCodes.includes("active_mode_blocked_by_safety_guard")),
    [rows],
  );
  const mode = useMemo(() => effectiveMode(rows), [rows]);

  if (rows.length === 0) {
    return (
      <Card title={title}>
        <div role="region" aria-label="Momentum impact review empty" data-testid="momentum-impact-empty">
          <EmptyState
            title="No candidates to review"
            hint="Generate a recommendation queue to see how Momentum Intelligence would affect ranking."
          />
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>{MOMENTUM_IMPACT_DETERMINISTIC_NOTE}</p>
        </div>
      </Card>
    );
  }

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label={`Momentum impact review (${mode})`}
        data-testid="momentum-impact-review"
        className="op-stack"
        style={{ gap: 10 }}
      >
        <div
          className="op-row"
          style={{ flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}
        >
          <div className="op-row" style={{ flexWrap: "wrap", gap: 8 }}>
            <StatusBadge tone={modeBadgeTone(mode)}>{momentumRankingModeLabel(mode)}</StatusBadge>
            <StatusBadge tone="neutral">{summary.candidates_reviewed} candidate(s)</StatusBadge>
            <StatusBadge tone="good">{summary.positive_contribution_count} positive</StatusBadge>
            <StatusBadge tone={summary.negative_contribution_count > 0 ? "bad" : "neutral"}>
              {summary.negative_contribution_count} negative
            </StatusBadge>
            <StatusBadge tone={summary.warnings_count > 0 ? "warn" : "neutral"}>
              {summary.warnings_count} warning(s)
            </StatusBadge>
            <StatusBadge tone="neutral">{summary.parity_pending_count} parity pending</StatusBadge>
            <StatusBadge tone="neutral">{summary.direction_unknown_count} direction unknown</StatusBadge>
            <StatusBadge tone="neutral">{summary.contribution_missing_count} missing</StatusBadge>
          </div>
          <div className="op-row" style={{ flexWrap: "wrap", gap: 8 }}>
            <label style={{ fontSize: "0.82rem", color: "var(--op-muted, #7a8999)" }}>
              <span style={{ marginRight: 6 }}>Sort</span>
              <select
                aria-label="Momentum impact sort"
                data-testid="momentum-impact-sort"
                value={sortMode}
                onChange={(e) => setSortMode(e.target.value as MomentumImpactSortMode)}
              >
                {SORT_OPTIONS.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              aria-expanded={!collapsed}
              data-testid="momentum-impact-collapse"
              onClick={() => setCollapsed((prev) => !prev)}
            >
              {collapsed ? "Show details" : "Hide details"}
            </button>
          </div>
        </div>

        <div
          data-testid="momentum-impact-mode-framing"
          style={{
            padding: "8px 10px",
            borderRadius: 8,
            background:
              mode === "active"
                ? "rgba(76, 56, 24, 0.45)"
                : mode === "shadow"
                  ? "rgba(15, 35, 55, 0.5)"
                  : "rgba(20, 26, 33, 0.4)",
            border: "1px solid rgba(115, 138, 163, 0.24)",
            color: "var(--op-text, #d9e2ef)",
            fontSize: "0.85rem",
            lineHeight: 1.5,
          }}
          role="note"
        >
          {modeFraming(mode, blockedActive)}
        </div>

        <div className="op-row" style={{ flexWrap: "wrap", gap: 8 }} aria-label="Estimated rank movement summary">
          <StatusBadge tone={rankDelta.upgraded > 0 ? "good" : "neutral"}>
            ▲ {rankDelta.upgraded} would move up
          </StatusBadge>
          <StatusBadge tone={rankDelta.downgraded > 0 ? "warn" : "neutral"}>
            ▼ {rankDelta.downgraded} would move down
          </StatusBadge>
          <StatusBadge tone="neutral">{rankDelta.unchanged} unchanged</StatusBadge>
          <StatusBadge tone="neutral">
            Net Δ score {formatScoreUnit(summary.net_estimated_score_delta)}
          </StatusBadge>
        </div>

        {!collapsed ? (
          <div
            data-testid="momentum-impact-table"
            style={{ overflowX: "auto", minWidth: 0 }}
            aria-label="Momentum impact rows"
          >
            <table className="op-table" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Rank</th>
                  <th style={{ textAlign: "left" }}>Symbol / strategy</th>
                  <th style={{ textAlign: "left" }}>Mode</th>
                  <th style={{ textAlign: "right" }}>Current score</th>
                  <th style={{ textAlign: "right" }}>Shadow / applied (score units)</th>
                  <th style={{ textAlign: "right" }}>Estimated active</th>
                  <th style={{ textAlign: "right" }}>Rank Δ</th>
                  <th style={{ textAlign: "left" }}>Score</th>
                  <th style={{ textAlign: "left" }}>Reasons</th>
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((row) => {
                  const tone = momentumImpactTone(row);
                  const reasonLabels = getMomentumContributionReasonLabels(row.reasonCodes);
                  const deltaLabel = formatRankDelta(row.estimatedRankDelta);
                  const deltaTone =
                    row.estimatedRankDelta > 0
                      ? "good"
                      : row.estimatedRankDelta < 0
                        ? "warn"
                        : "neutral";
                  return (
                    <tr
                      key={`${row.symbol}-${row.strategy}-${row.rank}`}
                      data-testid="momentum-impact-row"
                      data-symbol={row.symbol}
                      data-mode={row.mode}
                    >
                      <td>{row.rank}</td>
                      <td>
                        <div style={{ fontWeight: 600 }}>{row.symbol}</div>
                        <div style={{ fontSize: "0.78rem", color: "var(--op-muted, #7a8999)" }}>
                          {row.strategy}
                        </div>
                      </td>
                      <td>
                        <StatusBadge tone={modeBadgeTone(row.mode)}>
                          {momentumRankingModeLabel(row.mode)}
                        </StatusBadge>
                      </td>
                      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {formatUnitScore(row.currentScore)}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <StatusBadge tone={tone}>
                          {formatScoreUnit(row.shadowContributionScoreUnits)}
                        </StatusBadge>
                      </td>
                      <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {formatUnitScore(row.estimatedActiveScore)}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <StatusBadge tone={deltaTone}>{deltaLabel}</StatusBadge>
                      </td>
                      <td>
                        {row.totalScore == null ? (
                          "—"
                        ) : (
                          <>
                            {row.totalScore}
                            {row.totalLabel ? (
                              <span style={{ color: "var(--op-muted, #7a8999)", marginLeft: 4 }}>
                                ({row.totalLabel})
                              </span>
                            ) : null}
                          </>
                        )}
                      </td>
                      <td>
                        <div className="op-row" style={{ flexWrap: "wrap", gap: 4 }}>
                          {reasonLabels.length === 0 ? (
                            <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>—</span>
                          ) : (
                            reasonLabels.map((label) => (
                              <StatusBadge
                                key={label}
                                tone={
                                  label.toLowerCase().includes("warning")
                                    ? "warn"
                                    : "neutral"
                                }
                              >
                                {label}
                              </StatusBadge>
                            ))
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}

        <p style={NOTE_STYLE} data-testid="momentum-impact-deterministic-note">
          {MOMENTUM_IMPACT_DETERMINISTIC_NOTE}
        </p>
      </div>
    </Card>
  );
}
