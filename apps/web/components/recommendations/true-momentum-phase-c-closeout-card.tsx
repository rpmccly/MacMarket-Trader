"use client";

// Phase C — True Momentum research closeout card.
//
// Renders the operator-readable Phase C closeout posture: what
// shipped (C0/C1/C2/C2.1/C2.2/C3/C4/C4.1), what is explicitly NOT
// shipped (active generation, queue candidate generation, auto
// approval, auto sizing, order routing), the remaining blockers
// before any future active Phase C decision, and the next allowed
// research phase (C5 candidate proposal, still non-active /
// non-ordering).
//
// This card never approves / rejects / sizes / routes trades, never
// generates queue candidates, never mutates the queue, and never
// returns "ready for live" or "approved" framing.

import React, { useEffect, useMemo, useState } from "react";

import { Card, StatusBadge } from "@/components/operator-ui";
import {
  fetchMomentumRankingStatus,
  type MomentumRankingStatus,
} from "@/lib/momentum-ranking-status";
import {
  buildTrueMomentumPhaseCCloseoutStatus,
  TRUE_MOMENTUM_PHASE_C_CLOSEOUT_DETERMINISTIC_NOTE,
  TRUE_MOMENTUM_PHASE_C_SHIPPED_PHASES,
  type TrueMomentumPhaseCCloseoutStatus,
} from "@/lib/true-momentum-phase-c-closeout";
import type { TrueMomentumCohortReadinessStatus } from "@/lib/true-momentum-cohort-review";

const NOTE_STYLE: React.CSSProperties = {
  margin: 0,
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.78rem",
  lineHeight: 1.5,
};

const NOT_SHIPPED_ITEMS: ReadonlyArray<string> = [
  "Active True Momentum strategy generation",
  "True Momentum queue candidate generation",
  "Auto approval",
  "Auto sizing",
  "Order routing",
];

export type TrueMomentumPhaseCCloseoutCardProps = {
  title?: string;
  cohortReadinessStatus?:
    | TrueMomentumCohortReadinessStatus
    | "not_evaluated"
    | null;
  b8OutcomeStatus?:
    | "available"
    | "captured_without_outcomes"
    | "not_captured"
    | "unavailable";
  /** Test-only injection point. */
  initialRankingStatus?: MomentumRankingStatus | null;
};

export function TrueMomentumPhaseCCloseoutCardView({
  status,
  title = "Phase C research closeout (research-only)",
}: {
  status: TrueMomentumPhaseCCloseoutStatus;
  title?: string;
}) {
  return (
    <Card title={title}>
      <div
        role="region"
        aria-label="True Momentum Phase C research closeout"
        data-testid="true-momentum-phase-c-closeout-card"
        className="op-stack"
        style={{ gap: 10 }}
      >
        <div className="op-row" style={{ flexWrap: "wrap", gap: 8 }}>
          <StatusBadge tone="good" data-testid="true-momentum-phase-c-closeout-card-research-status">
            Research implementation: {status.research_implementation_status}
          </StatusBadge>
          <StatusBadge tone="warn" data-testid="true-momentum-phase-c-closeout-card-active-status">
            Active generation: {status.active_generation_status} / not implemented
          </StatusBadge>
          <StatusBadge tone="neutral">
            Queue candidates generated: No
          </StatusBadge>
          <StatusBadge tone="neutral">
            Approval / order behavior: unchanged / manual
          </StatusBadge>
          <StatusBadge tone="neutral" data-testid="true-momentum-phase-c-closeout-card-paper-order">
            Paper-order creation: manual / unaffected
          </StatusBadge>
        </div>

        <section
          aria-label="Current parity summary"
          data-testid="true-momentum-phase-c-closeout-card-parity-summary"
        >
          <h4 style={{ margin: "0 0 4px 0", fontSize: "0.86rem", fontWeight: 600 }}>
            Current parity summary
          </h4>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: "0.82rem" }}>
            {status.current_parity_summary.visual_attestation_passed_symbols.length > 0 ? (
              <li
                data-testid="true-momentum-phase-c-closeout-card-parity-passed"
              >
                <strong>Visual attestation passed:</strong>{" "}
                {status.current_parity_summary.visual_attestation_passed_symbols.join(", ")}.
              </li>
            ) : null}
            {status.current_parity_summary.visual_attestation_failed_symbols.length > 0 ? (
              <li
                data-testid="true-momentum-phase-c-closeout-card-parity-failed"
              >
                <strong>Visual attestation failed:</strong>{" "}
                {status.current_parity_summary.visual_attestation_failed_symbols.join(", ")}.
              </li>
            ) : null}
            {status.current_parity_summary.composite_mismatch_symbols.length > 0 ? (
              <li
                data-testid="true-momentum-phase-c-closeout-card-parity-composite-mismatch"
              >
                <strong>Composite mismatch under review:</strong>{" "}
                {status.current_parity_summary.composite_mismatch_symbols.join(", ")}.
                {" "}
                Oscillator (True Momentum / EMA) aligned; composite total score differs.
              </li>
            ) : null}
            {status.current_parity_summary.oscillator_aligned_symbols.length > 0 ? (
              <li
                data-testid="true-momentum-phase-c-closeout-card-parity-oscillator-aligned"
              >
                <strong>Oscillator aligned:</strong>{" "}
                {status.current_parity_summary.oscillator_aligned_symbols.join(", ")}.
              </li>
            ) : null}
            {status.current_parity_summary.visual_attestation_passed_symbols.length === 0 &&
            status.current_parity_summary.visual_attestation_failed_symbols.length === 0 &&
            status.current_parity_summary.visual_attestation_partial_symbols.length === 0 ? (
              <li>No parity-report fixtures available yet.</li>
            ) : null}
          </ul>
        </section>

        <section
          aria-label="Phase C shipped phases"
          data-testid="true-momentum-phase-c-closeout-card-shipped-phases"
        >
          <h4 style={{ margin: "0 0 4px 0", fontSize: "0.86rem", fontWeight: 600 }}>
            Shipped (research-only)
          </h4>
          <div className="op-row" style={{ flexWrap: "wrap", gap: 6 }}>
            {TRUE_MOMENTUM_PHASE_C_SHIPPED_PHASES.map((phase) => (
              <StatusBadge key={phase} tone="good">
                {phase}
              </StatusBadge>
            ))}
          </div>
        </section>

        <section
          aria-label="Phase C explicitly not shipped"
          data-testid="true-momentum-phase-c-closeout-card-not-shipped"
        >
          <h4 style={{ margin: "0 0 4px 0", fontSize: "0.86rem", fontWeight: 600 }}>
            Explicitly not shipped
          </h4>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {NOT_SHIPPED_ITEMS.map((item) => (
              <li key={item} style={{ fontSize: "0.82rem" }}>
                {item}
              </li>
            ))}
          </ul>
        </section>

        <section
          aria-label="Phase C closeout blockers"
          data-testid="true-momentum-phase-c-closeout-card-blockers"
        >
          <h4 style={{ margin: "0 0 4px 0", fontSize: "0.86rem", fontWeight: 600 }}>
            Blockers before active Phase C
          </h4>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {status.blockers.map((blocker) => (
              <li
                key={blocker.id}
                style={{ fontSize: "0.82rem", marginTop: 4 }}
                data-testid={`true-momentum-phase-c-closeout-card-blocker-${blocker.id}`}
              >
                <strong>{blocker.label}.</strong>{" "}
                <span>{blocker.detail}</span>
                {blocker.symbols.length > 0 ? (
                  <span style={{ ...NOTE_STYLE, display: "block", marginTop: 2 }}>
                    Affected symbols: {blocker.symbols.join(", ")}.
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </section>

        <section
          aria-label="Next allowed Phase C research phase"
          data-testid="true-momentum-phase-c-closeout-card-next-phase"
        >
          <h4 style={{ margin: "0 0 4px 0", fontSize: "0.86rem", fontWeight: 600 }}>
            Next allowed work
          </h4>
          <p style={{ margin: 0, fontSize: "0.82rem" }}>
            <strong>{status.next_allowed_phase.label}:</strong>{" "}
            {status.next_allowed_phase.description}
          </p>
        </section>

        <p
          style={NOTE_STYLE}
          data-testid="true-momentum-phase-c-closeout-card-recommended-action"
        >
          {status.recommended_action}
        </p>
        <p
          style={NOTE_STYLE}
          data-testid="true-momentum-phase-c-closeout-card-deterministic-note"
        >
          {TRUE_MOMENTUM_PHASE_C_CLOSEOUT_DETERMINISTIC_NOTE}
        </p>
      </div>
    </Card>
  );
}

export function TrueMomentumPhaseCCloseoutCard({
  title,
  cohortReadinessStatus = null,
  b8OutcomeStatus = "unavailable",
  initialRankingStatus = null,
}: TrueMomentumPhaseCCloseoutCardProps) {
  const [rankingStatus, setRankingStatus] = useState<MomentumRankingStatus | null>(
    initialRankingStatus ?? null,
  );

  useEffect(() => {
    if (initialRankingStatus !== null) return;
    let cancelled = false;
    async function load() {
      const result = await fetchMomentumRankingStatus();
      if (cancelled) return;
      if (result.ok && result.data) setRankingStatus(result.data);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [initialRankingStatus]);

  const status = useMemo(
    () =>
      buildTrueMomentumPhaseCCloseoutStatus({
        rankingStatus,
        b8OutcomeStatus,
        cohortReadinessStatus:
          cohortReadinessStatus === "not_evaluated" ? null : cohortReadinessStatus,
      }),
    [rankingStatus, b8OutcomeStatus, cohortReadinessStatus],
  );

  return <TrueMomentumPhaseCCloseoutCardView status={status} title={title} />;
}
