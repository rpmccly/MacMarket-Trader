"use client";

// Phase C4 — True Momentum Strategy Context card.
//
// Renders the research-only Phase C4 context bundle for the currently
// selected Recommendations queue candidate: family badge + match
// strength, trigger-readiness checklist, parity/evidence caveats, and
// the activation-readiness status string. The card never approves /
// rejects / sizes / routes trades, never mutates the queue, never
// changes promote / save / paper-order flows, and never returns
// "approved" status.

import React, { useEffect, useMemo, useState } from "react";

import { Card, EmptyState, StatusBadge } from "@/components/operator-ui";
import {
  fetchMomentumRankingStatus,
  type MomentumRankingStatus,
} from "@/lib/momentum-ranking-status";
import type { QueueCandidate } from "@/lib/recommendations";
import {
  buildTrueMomentumStrategyContext,
  trueMomentumStrategyActivationReadinessLabel,
  trueMomentumStrategyActivationReadinessTone,
  TRUE_MOMENTUM_STRATEGY_CONTEXT_DETERMINISTIC_NOTE,
  type TrueMomentumStrategyContext,
  type TrueMomentumStrategyTriggerChecklistItem,
} from "@/lib/true-momentum-strategy-context";
import {
  fetchTrueMomentumStrategyFamilyStatus,
  type TrueMomentumStrategyFamilyStatus,
} from "@/lib/true-momentum-strategy-families";
import {
  familyPreviewLabel,
  trueMomentumPreviewTone,
} from "@/lib/true-momentum-strategy-preview";
import type { TrueMomentumCohortReadinessStatus } from "@/lib/true-momentum-cohort-review";

const NOTE_STYLE: React.CSSProperties = {
  margin: 0,
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.78rem",
  lineHeight: 1.5,
};

function checklistTone(
  status: TrueMomentumStrategyTriggerChecklistItem["status"],
): "good" | "warn" | "bad" | "neutral" {
  if (status === "pass") return "good";
  if (status === "fail") return "bad";
  if (status === "warning") return "warn";
  return "neutral";
}

const PARITY_STATUS_LABEL: Record<
  TrueMomentumStrategyContext["parity_status"],
  string
> = {
  passed: "Visual attestation passed",
  failed: "Visual attestation failed",
  partial: "Visual attestation partial",
  not_covered: "Not covered by visual attestation",
  global_mixed: "Visual parity mixed",
  pending: "Visual attestation pending",
};

const PARITY_STATUS_TONE: Record<
  TrueMomentumStrategyContext["parity_status"],
  "good" | "warn" | "bad" | "neutral"
> = {
  passed: "good",
  failed: "warn",
  partial: "warn",
  not_covered: "neutral",
  global_mixed: "warn",
  pending: "neutral",
};

export type TrueMomentumStrategyContextCardProps = {
  /** Selected queue candidate. Pass ``null`` when nothing selected. */
  candidate: QueueCandidate | null | undefined;
  /** Optional title override. */
  title?: string;
  /**
   * Cohort readiness — pass through from the existing Phase C3 cohort
   * review surface when available. Defaults to ``not_evaluated``.
   */
  cohortReadinessStatus?: TrueMomentumCohortReadinessStatus | "not_evaluated" | null;
  /**
   * Phase B7/B8 outcome status — accepted from the page so the card
   * doesn't re-fetch. Defaults to ``unavailable``.
   */
  b8OutcomeStatus?:
    | "available"
    | "captured_without_outcomes"
    | "not_captured"
    | "unavailable";
  /**
   * Test-only injection point. When provided, skip the family-status
   * fetch and render directly with these values.
   */
  initialStrategyFamilyStatus?: TrueMomentumStrategyFamilyStatus | null;
  initialRankingStatus?: MomentumRankingStatus | null;
};

export function TrueMomentumStrategyContextCardView({
  candidate,
  context,
  loading,
  error,
  title = "True Momentum Strategy Context (Phase C4 research-only)",
}: {
  candidate: QueueCandidate | null | undefined;
  context: TrueMomentumStrategyContext | null;
  loading: boolean;
  error: string | null;
  title?: string;
}) {
  if (error) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="True Momentum strategy context error"
          data-testid="true-momentum-strategy-context-card-error"
          className="op-stack"
          style={{ gap: 8 }}
        >
          <p style={{ color: "var(--op-text, #d9e2ef)" }}>{error}</p>
          <p
            style={NOTE_STYLE}
            data-testid="true-momentum-strategy-context-card-deterministic-note"
          >
            {TRUE_MOMENTUM_STRATEGY_CONTEXT_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }
  if (!candidate) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="True Momentum strategy context empty"
          data-testid="true-momentum-strategy-context-card-empty"
          className="op-stack"
          style={{ gap: 8 }}
        >
          <EmptyState
            title="Select a candidate"
            hint="Choose a Recommendations queue row to see its True Momentum strategy context."
          />
          <p
            style={NOTE_STYLE}
            data-testid="true-momentum-strategy-context-card-deterministic-note"
          >
            {TRUE_MOMENTUM_STRATEGY_CONTEXT_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }
  if (loading && !context) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="True Momentum strategy context loading"
          data-testid="true-momentum-strategy-context-card-loading"
          className="op-stack"
          style={{ gap: 8 }}
        >
          <div role="status" aria-live="polite" style={{ color: "var(--op-muted, #7a8999)" }}>
            Loading True Momentum strategy context…
          </div>
          <p
            style={NOTE_STYLE}
            data-testid="true-momentum-strategy-context-card-deterministic-note"
          >
            {TRUE_MOMENTUM_STRATEGY_CONTEXT_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }
  if (!context || !context.family_id) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="True Momentum strategy context — no family match"
          data-testid="true-momentum-strategy-context-card-no-match"
          className="op-stack"
          style={{ gap: 8 }}
        >
          <p style={{ margin: 0 }}>
            No True Momentum family match for selected candidate ({candidate.symbol}{" "}
            {candidate.strategy}).
          </p>
          <p
            style={NOTE_STYLE}
            data-testid="true-momentum-strategy-context-card-deterministic-note"
          >
            {TRUE_MOMENTUM_STRATEGY_CONTEXT_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }

  const readinessLabel = trueMomentumStrategyActivationReadinessLabel(context.readiness);
  const readinessTone = trueMomentumStrategyActivationReadinessTone(context.readiness);
  const familyLabel = context.family_label ?? familyPreviewLabel(context.family_id);
  const matchTone = trueMomentumPreviewTone(context.match_strength);
  const matchLabel = context.match_strength ?? "unknown";

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label="True Momentum strategy context"
        data-testid="true-momentum-strategy-context-card"
        className="op-stack"
        style={{ gap: 10 }}
      >
        <div
          className="op-row"
          style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}
          data-testid="true-momentum-strategy-context-card-header"
        >
          <strong style={{ fontSize: "0.9rem" }}>
            {context.symbol} · {context.strategy}
          </strong>
          <StatusBadge tone={matchTone} data-testid="true-momentum-strategy-context-card-family-badge">
            {familyLabel}
          </StatusBadge>
          <StatusBadge tone={matchTone}>Match: {matchLabel}</StatusBadge>
          <StatusBadge
            tone={readinessTone}
            data-testid="true-momentum-strategy-context-card-readiness-badge"
          >
            Readiness: {readinessLabel}
          </StatusBadge>
        </div>

        {context.trigger_checklist ? (
          <section
            aria-label="Trigger-readiness checklist"
            data-testid="true-momentum-strategy-context-card-checklist"
          >
            <h4 style={{ margin: "0 0 4px 0", fontSize: "0.86rem", fontWeight: 600 }}>
              Trigger-readiness checklist ({familyLabel})
            </h4>
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
              {context.trigger_checklist.items.map((item) => (
                <li
                  key={item.id}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "auto 1fr",
                    gap: 8,
                    alignItems: "start",
                  }}
                >
                  <StatusBadge tone={checklistTone(item.status)}>{item.status}</StatusBadge>
                  <div>
                    <div style={{ fontSize: "0.86rem", color: "var(--op-text, #d9e2ef)" }}>
                      {item.label}
                    </div>
                    <div style={{ ...NOTE_STYLE, fontSize: "0.76rem" }}>{item.reason}</div>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <section
          aria-label="Parity / evidence caveats"
          data-testid="true-momentum-strategy-context-card-parity"
        >
          <h4 style={{ margin: "0 0 4px 0", fontSize: "0.86rem", fontWeight: 600 }}>
            Parity / evidence caveats
          </h4>
          <div className="op-row" style={{ flexWrap: "wrap", gap: 6 }}>
            <StatusBadge tone={PARITY_STATUS_TONE[context.parity_status]}>
              {PARITY_STATUS_LABEL[context.parity_status]}
            </StatusBadge>
            {context.parity_diagnostics.classification.map((tag) => (
              <StatusBadge
                key={tag}
                tone={
                  tag === "oscillator_aligned"
                    ? "good"
                    : tag.includes("mismatch") || tag.includes("blocked")
                      ? "warn"
                      : "neutral"
                }
              >
                {tag.replaceAll("_", " ")}
              </StatusBadge>
            ))}
          </div>
          {context.evidence_caveats.parity_messages.length > 0 ? (
            <ul style={{ margin: "6px 0 0 0", paddingLeft: 18 }}>
              {context.evidence_caveats.parity_messages.map((msg) => (
                <li key={msg} style={{ ...NOTE_STYLE, marginTop: 4 }}>
                  {msg}
                </li>
              ))}
            </ul>
          ) : null}
          <div
            className="op-row"
            style={{ flexWrap: "wrap", gap: 6, marginTop: 6 }}
            aria-label="Evidence summary"
          >
            <StatusBadge tone="neutral">B8 outcomes: {context.b8_outcome_status}</StatusBadge>
            <StatusBadge tone="neutral">C3 readiness: {context.c3_readiness_status}</StatusBadge>
          </div>
        </section>

        {context.research_notes.length > 0 ? (
          <section
            aria-label="Research notes"
            data-testid="true-momentum-strategy-context-card-research-notes"
          >
            <h4 style={{ margin: "0 0 4px 0", fontSize: "0.86rem", fontWeight: 600 }}>
              Research notes
            </h4>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {context.research_notes.map((note) => (
                <li key={note} style={NOTE_STYLE}>
                  {note}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <section
          aria-label="Operator guardrails"
          data-testid="true-momentum-strategy-context-card-guardrails"
        >
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {context.guardrails.map((line) => (
              <li key={line} style={NOTE_STYLE}>
                {line}
              </li>
            ))}
          </ul>
        </section>

        <p
          style={NOTE_STYLE}
          data-testid="true-momentum-strategy-context-card-deterministic-note"
        >
          {TRUE_MOMENTUM_STRATEGY_CONTEXT_DETERMINISTIC_NOTE}
        </p>
      </div>
    </Card>
  );
}

export function TrueMomentumStrategyContextCard({
  candidate,
  title,
  cohortReadinessStatus = null,
  b8OutcomeStatus = "unavailable",
  initialStrategyFamilyStatus = null,
  initialRankingStatus = null,
}: TrueMomentumStrategyContextCardProps) {
  const [strategyFamilyStatus, setStrategyFamilyStatus] =
    useState<TrueMomentumStrategyFamilyStatus | null>(initialStrategyFamilyStatus ?? null);
  const [rankingStatus, setRankingStatus] = useState<MomentumRankingStatus | null>(
    initialRankingStatus ?? null,
  );
  const [loading, setLoading] = useState(
    !initialStrategyFamilyStatus || !initialRankingStatus,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Test injection: skip remote fetches.
    if (initialStrategyFamilyStatus !== null || initialRankingStatus !== null) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [family, ranking] = await Promise.all([
          fetchTrueMomentumStrategyFamilyStatus(),
          fetchMomentumRankingStatus(),
        ]);
        if (cancelled) return;
        if (family.ok && family.data) setStrategyFamilyStatus(family.data);
        if (ranking.ok && ranking.data) setRankingStatus(ranking.data);
      } catch (err) {
        if (cancelled) return;
        setError(
          err instanceof Error
            ? err.message
            : "Unable to load True Momentum strategy context.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [initialStrategyFamilyStatus, initialRankingStatus]);

  const context = useMemo(
    () =>
      buildTrueMomentumStrategyContext({
        candidate,
        strategyFamilyStatus,
        rankingStatus,
        cohortReadinessStatus:
          cohortReadinessStatus === "not_evaluated" ? null : cohortReadinessStatus,
        b8OutcomeStatus,
      }),
    [candidate, strategyFamilyStatus, rankingStatus, cohortReadinessStatus, b8OutcomeStatus],
  );

  return (
    <TrueMomentumStrategyContextCardView
      candidate={candidate}
      context={context}
      loading={loading}
      error={error}
      title={title}
    />
  );
}
