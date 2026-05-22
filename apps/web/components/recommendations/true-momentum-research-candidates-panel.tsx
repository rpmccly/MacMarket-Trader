"use client";

// Phase C5 — True Momentum research candidate proposal panel.
//
// Research-only UI surface. Reads the already-loaded Recommendations
// queue, Phase C1 classifier, and parity status, and emits proposal
// rows + decision gates + Markdown / JSON exports. Generates only
// when the operator clicks Generate. Optional localStorage persistence
// is research-only. The panel:
//
// - never submits to the ranked queue,
// - never approves / rejects / sizes / routes trades,
// - never creates paper orders,
// - never changes recommendation behavior or any backend state.

import React, { useEffect, useMemo, useState } from "react";

import { Card, EmptyState, StatusBadge } from "@/components/operator-ui";
import {
  fetchMomentumRankingStatus,
  type MomentumRankingStatus,
} from "@/lib/momentum-ranking-status";
import type { QueueCandidate } from "@/lib/recommendations";
import type { TrueMomentumCohortReadinessStatus } from "@/lib/true-momentum-cohort-review";
import {
  fetchTrueMomentumStrategyFamilyStatus,
  type TrueMomentumStrategyFamilyStatus,
} from "@/lib/true-momentum-strategy-families";
import {
  buildTrueMomentumResearchCandidateJson,
  buildTrueMomentumResearchCandidateMarkdown,
  buildTrueMomentumResearchCandidateProposalSet,
  partitionTrueMomentumResearchCandidatesByFamily,
  rankTrueMomentumResearchCandidates,
  TRUE_MOMENTUM_RESEARCH_CANDIDATES_DETERMINISTIC_NOTE,
  trueMomentumResearchCandidateStatusLabel,
  trueMomentumResearchCandidateTone,
  type TrueMomentumResearchCandidateProposal,
  type TrueMomentumResearchCandidateProposalSet,
} from "@/lib/true-momentum-research-candidates";

const NOTE_STYLE: React.CSSProperties = {
  margin: 0,
  color: "var(--op-muted, #7a8999)",
  fontSize: "0.78rem",
  lineHeight: 1.5,
};

const SECTION_HEADER_STYLE: React.CSSProperties = {
  margin: "0 0 4px 0",
  fontSize: "0.86rem",
  fontWeight: 600,
};

const TABLE_STYLE: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "0.82rem",
};

const TH_STYLE: React.CSSProperties = {
  textAlign: "left",
  padding: "4px 6px",
  borderBottom: "1px solid rgba(115, 138, 163, 0.22)",
  fontWeight: 600,
};

const TD_STYLE: React.CSSProperties = {
  padding: "4px 6px",
  borderBottom: "1px solid rgba(115, 138, 163, 0.10)",
  verticalAlign: "top",
};

export const TRUE_MOMENTUM_RESEARCH_CANDIDATES_STORAGE_KEY =
  "macmarket.trueMomentumResearchCandidates.latest";

export type TrueMomentumResearchCandidatesPanelProps = {
  title?: string;
  queueCandidates: ReadonlyArray<QueueCandidate>;
  cohortReadinessStatus?:
    | TrueMomentumCohortReadinessStatus
    | "not_evaluated"
    | null;
  b8OutcomeStatus?:
    | "available"
    | "captured_without_outcomes"
    | "not_captured"
    | "unavailable";
  enableLocalPersistence?: boolean;
  initialProposalSet?: TrueMomentumResearchCandidateProposalSet | null;
  /** Test-only injection points. */
  initialStrategyFamilyStatus?: TrueMomentumStrategyFamilyStatus | null;
  initialRankingStatus?: MomentumRankingStatus | null;
};

function copyToClipboard(text: string) {
  if (typeof navigator === "undefined" || !navigator.clipboard) return;
  void navigator.clipboard.writeText(text).catch(() => {});
}

function downloadFile(filename: string, content: string, mime: string) {
  if (typeof window === "undefined") return;
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function safeFilenameTimestamp(value: string | null | undefined): string {
  if (!value) return "latest";
  return value.replace(/[:.]/g, "-");
}

function ProposalRow({
  proposal,
}: {
  proposal: TrueMomentumResearchCandidateProposal;
}) {
  const tone = trueMomentumResearchCandidateTone(proposal.proposal_status);
  return (
    <tr
      data-testid="true-momentum-research-candidate-row"
      data-proposal-status={proposal.proposal_status}
    >
      <td style={TD_STYLE}>#{proposal.rank}</td>
      <td style={TD_STYLE}>
        <strong>{proposal.symbol}</strong>
        <div style={{ ...NOTE_STYLE, fontSize: "0.72rem" }}>
          {proposal.source_strategy}
        </div>
      </td>
      <td style={TD_STYLE}>
        <StatusBadge tone={tone}>
          {trueMomentumResearchCandidateStatusLabel(proposal.proposal_status)}
        </StatusBadge>
      </td>
      <td style={TD_STYLE}>{proposal.confidence_tier}</td>
      <td style={{ ...TD_STYLE, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
        {proposal.active_score != null ? proposal.active_score.toFixed(3) : "—"}
      </td>
      <td style={TD_STYLE}>
        {proposal.checklist_pass_count}/{proposal.checklist_total_count}
      </td>
      <td style={TD_STYLE}>
        {proposal.caveats.length === 0 ? (
          <span style={NOTE_STYLE}>—</span>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {proposal.caveats.map((c) => (
              <li key={c} style={{ fontSize: "0.78rem" }}>
                {c}
              </li>
            ))}
          </ul>
        )}
      </td>
    </tr>
  );
}

function DecisionGatesList({
  proposal,
}: {
  proposal: TrueMomentumResearchCandidateProposal;
}) {
  return (
    <ul
      data-testid="true-momentum-research-candidate-decision-gates"
      style={{ margin: 0, paddingLeft: 16 }}
    >
      {proposal.decision_gates.map((gate) => (
        <li
          key={gate.id}
          style={{ fontSize: "0.78rem", marginTop: 2 }}
          data-testid={`true-momentum-research-candidate-gate-${gate.id}`}
          data-blocks-activation={gate.blocks_activation ? "true" : "false"}
        >
          <strong>{gate.label}:</strong>{" "}
          <em style={{ fontStyle: "normal" }}>{gate.status}</em>
          {" — "}
          {gate.reason}
        </li>
      ))}
    </ul>
  );
}

export function TrueMomentumResearchCandidatesPanelView({
  proposalSet,
  onClear,
  onCopyMarkdown,
  onCopyJson,
  onDownloadMarkdown,
  onDownloadJson,
  hasGenerated,
}: {
  proposalSet: TrueMomentumResearchCandidateProposalSet | null;
  onClear: () => void;
  onCopyMarkdown: () => void;
  onCopyJson: () => void;
  onDownloadMarkdown: () => void;
  onDownloadJson: () => void;
  hasGenerated: boolean;
}) {
  if (!hasGenerated || !proposalSet) {
    return (
      <EmptyState
        title="No research candidate proposals yet"
        hint="Click Generate to derive research-only proposals from the current queue, parity status, and Phase C context."
      />
    );
  }
  const buckets = partitionTrueMomentumResearchCandidatesByFamily(proposalSet);
  const ranked = rankTrueMomentumResearchCandidates(proposalSet);
  return (
    <div
      role="region"
      aria-label="True Momentum Phase C5 research candidate proposals"
      data-testid="true-momentum-research-candidates-panel-body"
      className="op-stack"
      style={{ gap: 10 }}
    >
      <section
        data-testid="true-momentum-research-candidates-panel-summary"
        aria-label="C5 proposal summary"
      >
        <h4 style={SECTION_HEADER_STYLE}>Summary</h4>
        <div className="op-row" style={{ flexWrap: "wrap", gap: 6 }}>
          <StatusBadge tone="neutral">
            Candidates: {proposalSet.summary.candidate_count}
          </StatusBadge>
          <StatusBadge tone="good">
            Proposed for research: {proposalSet.summary.proposed_for_research_count}
          </StatusBadge>
          <StatusBadge tone="neutral">
            Continuation: {proposalSet.summary.continuation_count}
          </StatusBadge>
          <StatusBadge tone="neutral">
            Pullback: {proposalSet.summary.pullback_count}
          </StatusBadge>
          <StatusBadge tone="warn">
            Watch-only: {proposalSet.summary.watch_only_count}
          </StatusBadge>
          <StatusBadge tone="warn">
            Blocked: {proposalSet.summary.blocked_count}
          </StatusBadge>
          <StatusBadge tone="neutral">
            Insufficient evidence: {proposalSet.summary.insufficient_evidence_count}
          </StatusBadge>
          {proposalSet.summary.xlp_composite_mismatch_present ? (
            <StatusBadge tone="warn">
              XLP composite mismatch present
            </StatusBadge>
          ) : null}
        </div>
        <p
          style={NOTE_STYLE}
          data-testid="true-momentum-research-candidates-panel-summary-note"
        >
          Symbols covered: {proposalSet.summary.symbols_covered.join(", ") || "—"}.
          Generated at {proposalSet.generated_at}. Schema:{" "}
          <code>{proposalSet.schema_version}</code>.
        </p>
      </section>

      <section data-testid="true-momentum-research-candidates-panel-ranked-table">
        <h4 style={SECTION_HEADER_STYLE}>Ranked proposals</h4>
        <div style={{ overflowX: "auto" }}>
          <table style={TABLE_STYLE}>
            <thead>
              <tr>
                <th style={TH_STYLE}>Rank</th>
                <th style={TH_STYLE}>Symbol / source</th>
                <th style={TH_STYLE}>Status</th>
                <th style={TH_STYLE}>Confidence</th>
                <th style={{ ...TH_STYLE, textAlign: "right" }}>Active score</th>
                <th style={TH_STYLE}>Checklist</th>
                <th style={TH_STYLE}>Caveats</th>
              </tr>
            </thead>
            <tbody>
              {ranked.map((p) => (
                <ProposalRow key={p.proposal_id} proposal={p} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section
        data-testid="true-momentum-research-candidates-panel-family-groups"
        aria-label="C5 proposals grouped by family"
      >
        <h4 style={SECTION_HEADER_STYLE}>By family</h4>
        {buckets.map((bucket) => (
          <details
            key={bucket.family_id}
            data-testid={`true-momentum-research-candidates-panel-family-${bucket.family_id}`}
            style={{ marginTop: 6 }}
          >
            <summary style={{ cursor: "pointer", fontSize: "0.84rem", fontWeight: 600 }}>
              {bucket.family_label} ({bucket.proposals.length})
            </summary>
            <ul style={{ margin: "6px 0 0 0", paddingLeft: 18 }}>
              {bucket.proposals.map((p) => (
                <li
                  key={p.proposal_id}
                  style={{ marginTop: 6, fontSize: "0.82rem" }}
                  data-testid="true-momentum-research-candidate-family-entry"
                >
                  <div>
                    <strong>{p.symbol}</strong>{" — "}
                    {trueMomentumResearchCandidateStatusLabel(p.proposal_status)} (
                    {p.confidence_tier})
                  </div>
                  <DecisionGatesList proposal={p} />
                </li>
              ))}
            </ul>
          </details>
        ))}
      </section>

      <section
        data-testid="true-momentum-research-candidates-panel-exports"
        aria-label="C5 export controls"
      >
        <h4 style={SECTION_HEADER_STYLE}>Export</h4>
        <div className="op-row" style={{ flexWrap: "wrap", gap: 6 }}>
          <button
            type="button"
            className="op-button"
            data-testid="true-momentum-research-candidates-panel-copy-markdown"
            onClick={onCopyMarkdown}
          >
            Copy Markdown
          </button>
          <button
            type="button"
            className="op-button"
            data-testid="true-momentum-research-candidates-panel-copy-json"
            onClick={onCopyJson}
          >
            Copy JSON
          </button>
          <button
            type="button"
            className="op-button"
            data-testid="true-momentum-research-candidates-panel-download-markdown"
            onClick={onDownloadMarkdown}
          >
            Download Markdown
          </button>
          <button
            type="button"
            className="op-button"
            data-testid="true-momentum-research-candidates-panel-download-json"
            onClick={onDownloadJson}
          >
            Download JSON
          </button>
          <button
            type="button"
            className="op-button"
            data-testid="true-momentum-research-candidates-panel-clear"
            onClick={onClear}
          >
            Clear proposals
          </button>
        </div>
      </section>

      <p
        style={NOTE_STYLE}
        data-testid="true-momentum-research-candidates-panel-deterministic-note"
      >
        {TRUE_MOMENTUM_RESEARCH_CANDIDATES_DETERMINISTIC_NOTE}
      </p>
    </div>
  );
}

export function TrueMomentumResearchCandidatesPanel({
  title = "Phase C5 — True Momentum research candidate proposals (research-only)",
  queueCandidates,
  cohortReadinessStatus = null,
  b8OutcomeStatus = "unavailable",
  enableLocalPersistence = true,
  initialProposalSet = null,
  initialStrategyFamilyStatus = null,
  initialRankingStatus = null,
}: TrueMomentumResearchCandidatesPanelProps) {
  const [proposalSet, setProposalSet] =
    useState<TrueMomentumResearchCandidateProposalSet | null>(initialProposalSet);
  const [hasGenerated, setHasGenerated] = useState<boolean>(initialProposalSet != null);
  const [strategyFamilyStatus, setStrategyFamilyStatus] =
    useState<TrueMomentumStrategyFamilyStatus | null>(initialStrategyFamilyStatus);
  const [rankingStatus, setRankingStatus] = useState<MomentumRankingStatus | null>(
    initialRankingStatus,
  );

  useEffect(() => {
    if (initialStrategyFamilyStatus !== null) return;
    let cancelled = false;
    async function load() {
      const result = await fetchTrueMomentumStrategyFamilyStatus();
      if (cancelled) return;
      if (result.ok && result.data) setStrategyFamilyStatus(result.data);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [initialStrategyFamilyStatus]);

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

  useEffect(() => {
    if (!enableLocalPersistence) return;
    if (initialProposalSet) return;
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(
        TRUE_MOMENTUM_RESEARCH_CANDIDATES_STORAGE_KEY,
      );
      if (!raw) return;
      const parsed = JSON.parse(raw) as TrueMomentumResearchCandidateProposalSet;
      if (parsed && Array.isArray(parsed.proposals)) {
        setProposalSet(parsed);
        setHasGenerated(true);
      }
    } catch {
      // ignore
    }
  }, [enableLocalPersistence, initialProposalSet]);

  const canGenerate = queueCandidates.length > 0;

  function handleGenerate() {
    const next = buildTrueMomentumResearchCandidateProposalSet({
      queueCandidates,
      strategyFamilyStatus,
      rankingStatus,
      cohortReadinessStatus,
      b8OutcomeStatus,
    });
    setProposalSet(next);
    setHasGenerated(true);
    if (enableLocalPersistence && typeof window !== "undefined") {
      try {
        window.localStorage.setItem(
          TRUE_MOMENTUM_RESEARCH_CANDIDATES_STORAGE_KEY,
          JSON.stringify(next),
        );
      } catch {
        // ignore
      }
    }
  }

  function handleClear() {
    setProposalSet(null);
    setHasGenerated(false);
    if (enableLocalPersistence && typeof window !== "undefined") {
      try {
        window.localStorage.removeItem(
          TRUE_MOMENTUM_RESEARCH_CANDIDATES_STORAGE_KEY,
        );
      } catch {
        // ignore
      }
    }
  }

  const markdown = useMemo(
    () => (proposalSet ? buildTrueMomentumResearchCandidateMarkdown(proposalSet) : ""),
    [proposalSet],
  );
  const jsonPayload = useMemo(
    () => (proposalSet ? buildTrueMomentumResearchCandidateJson(proposalSet) : null),
    [proposalSet],
  );
  const jsonText = useMemo(
    () => (jsonPayload ? JSON.stringify(jsonPayload, null, 2) : ""),
    [jsonPayload],
  );

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label="True Momentum Phase C5 research candidate proposals"
        data-testid="true-momentum-research-candidates-panel"
        className="op-stack"
        style={{ gap: 10 }}
      >
        <div className="op-row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <button
            type="button"
            className="op-button op-button-primary"
            data-testid="true-momentum-research-candidates-panel-generate"
            onClick={handleGenerate}
            disabled={!canGenerate}
          >
            Generate research proposals
          </button>
          <span style={NOTE_STYLE}>
            {canGenerate
              ? `${queueCandidates.length} queue candidate(s) available for analysis.`
              : "No queue candidates available to analyze."}
          </span>
        </div>

        <p style={NOTE_STYLE} data-testid="true-momentum-research-candidates-panel-disclaimer">
          Research-only. C5 proposals do not enter the ranked queue, and do not
          approve, reject, size, or route trades. They never create paper
          orders.
        </p>

        <TrueMomentumResearchCandidatesPanelView
          proposalSet={proposalSet}
          hasGenerated={hasGenerated}
          onClear={handleClear}
          onCopyMarkdown={() => copyToClipboard(markdown)}
          onCopyJson={() => copyToClipboard(jsonText)}
          onDownloadMarkdown={() =>
            downloadFile(
              `true-momentum-research-candidates-${safeFilenameTimestamp(proposalSet?.generated_at)}.md`,
              markdown,
              "text/markdown;charset=utf-8",
            )
          }
          onDownloadJson={() =>
            downloadFile(
              `true-momentum-research-candidates-${safeFilenameTimestamp(proposalSet?.generated_at)}.json`,
              jsonText,
              "application/json;charset=utf-8",
            )
          }
        />
      </div>
    </Card>
  );
}
