"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import { Card, EmptyState, StatusBadge } from "@/components/operator-ui";
import {
  addTrueMomentumCohortRecord,
  buildTrueMomentumCohortJson,
  buildTrueMomentumCohortMarkdown,
  buildTrueMomentumCohortRecord,
  buildTrueMomentumCohortReviewReport,
  cohortArchiveContainsRecordId,
  emptyCohortArchive,
  readTrueMomentumCohortArchiveFromStorage,
  removeTrueMomentumCohortRecord,
  TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE,
  trueMomentumCohortReadinessLabel,
  trueMomentumCohortReadinessTone,
  writeTrueMomentumCohortArchiveToStorage,
  type TrueMomentumCohortArchive,
  type TrueMomentumCohortRecord,
} from "@/lib/true-momentum-cohort-review";
import type { TrueMomentumPreviewEvidenceBundle } from "@/lib/true-momentum-preview-evidence";

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
  minWidth: 110,
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

function downloadTextFile(filename: string, mime: string, content: string): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  try {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch {
    // best-effort
  }
}

export type TrueMomentumCohortReviewPanelProps = {
  currentBundle?: TrueMomentumPreviewEvidenceBundle | null;
  compact?: boolean;
  persistLatest?: boolean;
  /** Test-only — render with a pre-loaded archive instead of hitting
   *  localStorage. Production callers leave this null. */
  initialArchive?: TrueMomentumCohortArchive | null;
  title?: string;
};

export function TrueMomentumCohortReviewPanel({
  currentBundle = null,
  compact = false,
  persistLatest = true,
  initialArchive = null,
  title = "True Momentum cohort review (Phase C3 research-only)",
}: TrueMomentumCohortReviewPanelProps) {
  const [archive, setArchive] = useState<TrueMomentumCohortArchive | null>(
    initialArchive,
  );

  useEffect(() => {
    if (initialArchive) return;
    if (!persistLatest) return;
    const cached = readTrueMomentumCohortArchiveFromStorage();
    if (cached) setArchive(cached);
  }, [initialArchive, persistLatest]);

  const candidateRecord = useMemo(
    () =>
      currentBundle
        ? buildTrueMomentumCohortRecord(currentBundle, {
            capturedAt: new Date().toISOString(),
          })
        : null,
    [currentBundle],
  );

  const alreadyArchived =
    candidateRecord != null &&
    cohortArchiveContainsRecordId(archive, candidateRecord.record_id);

  const report = useMemo(
    () => buildTrueMomentumCohortReviewReport(archive),
    [archive],
  );
  const summary = report.summary;

  const persistArchive = useCallback(
    (next: TrueMomentumCohortArchive) => {
      setArchive(next);
      if (persistLatest) writeTrueMomentumCohortArchiveToStorage(next);
    },
    [persistLatest],
  );

  const handleAddCurrent = useCallback(() => {
    if (!candidateRecord) return;
    const next = addTrueMomentumCohortRecord(
      archive ?? emptyCohortArchive(),
      candidateRecord,
    );
    persistArchive(next);
  }, [archive, candidateRecord, persistArchive]);

  const handleRemoveRecord = useCallback(
    (recordId: string) => {
      const next = removeTrueMomentumCohortRecord(archive, recordId);
      persistArchive(next);
    },
    [archive, persistArchive],
  );

  const handleClearArchive = useCallback(() => {
    const fresh = emptyCohortArchive();
    persistArchive(fresh);
  }, [persistArchive]);

  const handleDownloadMarkdown = useCallback(() => {
    const stamp = report.generated_at.replace(/[^0-9A-Za-z]+/g, "-");
    downloadTextFile(
      `true-momentum-cohort-${stamp}.md`,
      "text/markdown;charset=utf-8",
      buildTrueMomentumCohortMarkdown(report),
    );
  }, [report]);

  const handleDownloadJson = useCallback(() => {
    const stamp = report.generated_at.replace(/[^0-9A-Za-z]+/g, "-");
    downloadTextFile(
      `true-momentum-cohort-${stamp}.json`,
      "application/json;charset=utf-8",
      buildTrueMomentumCohortJson(report),
    );
  }, [report]);

  const safeArchive = archive ?? emptyCohortArchive();
  const recordCount = safeArchive.records.length;

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label="True Momentum cohort review"
        data-testid="true-momentum-cohort-review"
        className="op-stack"
        style={{ gap: 10 }}
      >
        <div
          className="op-row"
          style={{ flexWrap: "wrap", gap: 6, alignItems: "center", justifyContent: "space-between" }}
        >
          <div className="op-row" style={{ flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            <StatusBadge tone="neutral">
              {recordCount} archived session{recordCount === 1 ? "" : "s"}
            </StatusBadge>
            <StatusBadge tone={trueMomentumCohortReadinessTone(report.readiness)} data-testid="true-momentum-cohort-readiness-badge">
              Readiness: {trueMomentumCohortReadinessLabel(report.readiness)}
            </StatusBadge>
            {alreadyArchived ? (
              <StatusBadge tone="good" data-testid="true-momentum-cohort-already-archived">
                Current bundle already archived
              </StatusBadge>
            ) : null}
          </div>
          <div className="op-row" style={{ flexWrap: "wrap", gap: 6 }}>
            <button
              type="button"
              data-testid="true-momentum-cohort-add-current"
              onClick={handleAddCurrent}
              disabled={!candidateRecord || alreadyArchived}
              aria-disabled={!candidateRecord || alreadyArchived}
            >
              Add current evidence bundle to cohort archive
            </button>
          </div>
        </div>

        {recordCount === 0 ? (
          <EmptyState
            title="No archived sessions yet"
            hint={
              candidateRecord
                ? "Press “Add current evidence bundle to cohort archive” to start the research corpus."
                : "Capture a Phase C2 evidence bundle to enable archive entries."
            }
          />
        ) : null}

        <div
          data-testid="true-momentum-cohort-summary"
          className="op-row"
          style={{ flexWrap: "wrap", gap: 8 }}
          aria-label="Cohort summary"
        >
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Archived sessions</span>
            <span style={SUMMARY_VALUE_STYLE} data-testid="true-momentum-cohort-summary-record-count">
              {summary.record_count}
            </span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Total preview rows</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.total_preview_count}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Continuation</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.continuation_count}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Pullback</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.pullback_count}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Reversal / watch</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.reversal_watch_count}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Linked B8 reviews</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.records_with_outcome_review}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Parity-pending records</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.parity_pending_records}</span>
          </div>
        </div>

        <div
          data-testid="true-momentum-cohort-outcome-summary"
          className="op-row"
          style={{ flexWrap: "wrap", gap: 6, fontSize: "0.82rem" }}
          aria-label="Cohort outcome counts"
        >
          <StatusBadge tone="good">Worked: {summary.outcome_counts.worked_count}</StatusBadge>
          <StatusBadge tone="bad">Missed: {summary.outcome_counts.missed_count}</StatusBadge>
          <StatusBadge tone="warn">Too aggressive: {summary.outcome_counts.too_aggressive_count}</StatusBadge>
          <StatusBadge tone="good">Good warnings: {summary.outcome_counts.good_warning_count}</StatusBadge>
          <StatusBadge tone="warn">False warnings: {summary.outcome_counts.false_warning_count}</StatusBadge>
          <StatusBadge tone="warn">Needs ToS parity: {summary.outcome_counts.needs_tos_parity_check_count}</StatusBadge>
          <StatusBadge tone="neutral">Unclear: {summary.outcome_counts.unclear_count}</StatusBadge>
        </div>

        {report.readiness_caveats.length > 0 ? (
          <ul
            data-testid="true-momentum-cohort-readiness-caveats"
            style={{
              margin: 0,
              paddingLeft: 18,
              color: "var(--op-warn-text, #d6a25b)",
              fontSize: "0.82rem",
              lineHeight: 1.5,
            }}
          >
            {report.readiness_caveats.map((caveat, idx) => (
              <li key={`caveat-${idx}`}>{caveat}</li>
            ))}
          </ul>
        ) : null}

        <div data-testid="true-momentum-cohort-family-summaries" className="op-stack" style={{ gap: 4 }}>
          <h4 style={{ margin: "4px 0 6px 0", fontSize: "0.92rem" }}>Family summaries</h4>
          {summary.family_summaries.map((family) => (
            <div
              key={family.family_id}
              data-testid="true-momentum-cohort-family-summary"
              data-family-id={family.family_id}
              style={{ fontSize: "0.82rem" }}
            >
              <strong>{family.family_label}:</strong> {family.preview_count} previews across {family.record_count} record(s) ·{" "}
              strong {family.strong_count} / moderate {family.moderate_count} / watch {family.watch_count} / blocked {family.blocked_count} ·{" "}
              parity pending {family.parity_pending_count}
            </div>
          ))}
        </div>

        {recordCount > 0 ? (
          <div data-testid="true-momentum-cohort-table" style={{ overflowX: "auto", minWidth: 0 }}>
            <table className="op-table" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left" }}>Captured at</th>
                  <th style={{ textAlign: "left" }}>Universe</th>
                  <th style={{ textAlign: "right" }}>Preview rows</th>
                  <th style={{ textAlign: "left" }}>B8 snapshot</th>
                  <th style={{ textAlign: "left" }}>B8 outcome review</th>
                  <th style={{ textAlign: "right" }}>Parity pending</th>
                  <th style={{ textAlign: "left" }}>Tags</th>
                  <th style={{ textAlign: "left" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {safeArchive.records.map((record: TrueMomentumCohortRecord) => (
                  <tr
                    key={record.record_id}
                    data-testid="true-momentum-cohort-record-row"
                    data-record-id={record.record_id}
                  >
                    <td>{record.captured_at}</td>
                    <td>{record.evaluated_universe.length} symbol(s)</td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {record.preview_count}
                    </td>
                    <td>{record.b8_snapshot_link_status}</td>
                    <td>
                      {record.b8_outcome_review_link_status}
                      {record.b8_outcome_summary
                        ? ` (worked ${record.b8_outcome_summary.worked_count} / unclear ${record.b8_outcome_summary.unclear_count})`
                        : ""}
                    </td>
                    <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {record.parity_pending_count}
                    </td>
                    <td>{record.operator_review.review_tags.join(", ") || "—"}</td>
                    <td>
                      <button
                        type="button"
                        data-testid="true-momentum-cohort-remove-record"
                        onClick={() => handleRemoveRecord(record.record_id)}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        <div className="op-row" style={{ flexWrap: "wrap", gap: 6, justifyContent: "flex-end" }}>
          <button
            type="button"
            data-testid="true-momentum-cohort-download-markdown"
            onClick={handleDownloadMarkdown}
            disabled={recordCount === 0}
            aria-disabled={recordCount === 0}
          >
            Export Cohort Markdown
          </button>
          <button
            type="button"
            data-testid="true-momentum-cohort-download-json"
            onClick={handleDownloadJson}
            disabled={recordCount === 0}
            aria-disabled={recordCount === 0}
          >
            Export Cohort JSON
          </button>
          <button
            type="button"
            data-testid="true-momentum-cohort-clear-archive"
            onClick={handleClearArchive}
            disabled={recordCount === 0}
            aria-disabled={recordCount === 0}
          >
            Clear Archive
          </button>
        </div>

        <p
          style={NOTE_STYLE}
          data-testid="true-momentum-cohort-deterministic-note"
        >
          {TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE}
        </p>
        <p style={NOTE_STYLE} data-testid="true-momentum-cohort-still-pending">
          Still pending: larger B8 outcome evidence corpus · Thinkorswim fixture parity ·
          operator authorization before any active Phase C.
        </p>
      </div>
    </Card>
  );
}
