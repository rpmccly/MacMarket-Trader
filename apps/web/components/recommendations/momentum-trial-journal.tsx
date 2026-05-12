"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import { Card, EmptyState, StatusBadge } from "@/components/operator-ui";
import {
  buildMomentumTrialJson,
  buildMomentumTrialMarkdown,
  buildMomentumTrialSnapshot,
  MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE,
  MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY as MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY_LIB,
  momentumTrialUniverseLabel,
  sanitizeMomentumTrialNote,
  validateMomentumTrialSnapshot,
  type MomentumTrialCandidateSnapshot,
  type MomentumTrialSnapshot,
} from "@/lib/momentum-trial-journal";
import { MomentumTrialOutcomeReviewPanel } from "@/components/recommendations/momentum-trial-outcome-review";
import type { MomentumTrialOutcomeReview } from "@/lib/momentum-trial-outcomes";
import { momentumRankingModeLabel } from "@/lib/momentum-ranking";
import type { QueueCandidate } from "@/lib/recommendations";

// Re-exported from the lib so existing component-level imports keep working.
// The single source of truth lives in ``@/lib/momentum-trial-journal``.
export const MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY =
  MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY_LIB;

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

const NOTE_INPUT_STYLE: React.CSSProperties = {
  width: "100%",
  minHeight: 56,
  resize: "vertical",
  fontFamily: "inherit",
  fontSize: "0.85rem",
  padding: 8,
  borderRadius: 6,
  background: "rgba(15, 24, 34, 0.55)",
  border: "1px solid rgba(115, 138, 163, 0.28)",
  color: "var(--op-text, #d9e2ef)",
};

function fmtUnitScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value) || !Number.isFinite(value)) return "—";
  const rounded = Math.round(value * 10000) / 10000;
  return rounded.toFixed(3);
}

function fmtSignedScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value) || !Number.isFinite(value)) return "—";
  if (value === 0) return value.toFixed(3);
  return value > 0 ? `+${value.toFixed(3)}` : value.toFixed(3);
}

function fmtRawScoreUnits(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value) || !Number.isFinite(value)) return "—";
  const rounded = Math.round(value * 100) / 100;
  if (rounded === 0) return "0.00";
  return rounded > 0 ? `+${rounded.toFixed(2)}` : rounded.toFixed(2);
}

function classificationTone(
  classification: MomentumTrialCandidateSnapshot["classification"],
): "good" | "warn" | "bad" | "neutral" {
  switch (classification) {
    case "active_positive":
    case "shadow_positive":
      return "good";
    case "active_negative":
    case "shadow_negative":
      return "bad";
    case "blocked_active":
    case "contribution_missing":
      return "warn";
    default:
      return "neutral";
  }
}

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
    // Best-effort; never throws to caller. Operator can still copy markdown.
  }
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (
      typeof navigator !== "undefined" &&
      navigator.clipboard &&
      typeof navigator.clipboard.writeText === "function"
    ) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to legacy path
  }
  return false;
}

function readLatestSnapshotFromStorage(): MomentumTrialSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const result = validateMomentumTrialSnapshot(parsed);
    if (!result.ok) return null;
    return result.snapshot;
  } catch {
    return null;
  }
}

function writeLatestSnapshotToStorage(snapshot: MomentumTrialSnapshot | null): void {
  if (typeof window === "undefined") return;
  try {
    if (snapshot == null) {
      window.localStorage.removeItem(MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(
      MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY,
      JSON.stringify(snapshot),
    );
  } catch {
    // localStorage may be unavailable (private mode, quota). Best-effort.
  }
}

export type MomentumTrialJournalProps = {
  candidates: ReadonlyArray<QueueCandidate> | null | undefined;
  universeSymbols?: ReadonlyArray<string> | null;
  title?: string;
  compact?: boolean;
  /**
   * Test-only: render the view with a pre-built snapshot instead of waiting
   * for the operator to capture. Production callers should leave this
   * undefined — capture is always operator-initiated in the live UI.
   */
  initialSnapshot?: MomentumTrialSnapshot | null;
  /**
   * Disable localStorage round-trip. Defaults to enabled. Tests pass
   * `persistLatest={false}` so they do not depend on a browser environment.
   */
  persistLatest?: boolean;
  /**
   * Phase C2.2 — notify the parent whenever the captured B7 trial
   * snapshot changes (capture / clear / hydration). Lets the
   * Recommendations page lift snapshot state and pass it directly to
   * the Phase C2 evidence panel so it always sees the live snapshot.
   */
  onSnapshotChange?: (snapshot: MomentumTrialSnapshot | null) => void;
  /**
   * Phase C2.2 — notify the parent whenever the Phase B8 outcome review
   * inside this trial journal changes (tag toggle, note edit,
   * conclusion edit, clear, hydration).
   */
  onOutcomeReviewChange?: (review: MomentumTrialOutcomeReview | null) => void;
};

export function MomentumTrialJournalView({
  snapshot,
  onCopyMarkdown,
  onDownloadMarkdown,
  onDownloadJson,
  onClear,
  compact = false,
}: {
  snapshot: MomentumTrialSnapshot;
  onCopyMarkdown?: () => void;
  onDownloadMarkdown?: () => void;
  onDownloadJson?: () => void;
  onClear?: () => void;
  compact?: boolean;
}) {
  const summary = snapshot.summary;
  return (
    <div
      role="region"
      aria-label="Momentum trial journal snapshot"
      data-testid="momentum-trial-journal-snapshot"
      className="op-stack"
      style={{ gap: 10 }}
    >
      <div
        className="op-row"
        style={{ flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}
      >
        <div className="op-row" style={{ flexWrap: "wrap", gap: 6, alignItems: "center" }}>
          <StatusBadge tone="neutral" data-testid="momentum-trial-journal-mode-badge">
            Effective: {momentumRankingModeLabel(summary.ranking_mode_summary.effective_mode)}
          </StatusBadge>
          <StatusBadge tone="neutral">
            Requested: {momentumRankingModeLabel(summary.ranking_mode_summary.requested_mode)}
          </StatusBadge>
          <StatusBadge tone="neutral">
            Scale {summary.active_delta_scale.toFixed(2)}
          </StatusBadge>
          <StatusBadge tone="neutral" data-testid="momentum-trial-journal-generated-at">
            {snapshot.generated_at}
          </StatusBadge>
        </div>
        <div className="op-row" style={{ flexWrap: "wrap", gap: 6 }}>
          <button
            type="button"
            data-testid="momentum-trial-journal-copy-markdown"
            onClick={onCopyMarkdown}
            disabled={!onCopyMarkdown}
          >
            Copy Markdown
          </button>
          <button
            type="button"
            data-testid="momentum-trial-journal-download-markdown"
            onClick={onDownloadMarkdown}
            disabled={!onDownloadMarkdown}
          >
            Download Markdown
          </button>
          <button
            type="button"
            data-testid="momentum-trial-journal-download-json"
            onClick={onDownloadJson}
            disabled={!onDownloadJson}
          >
            Download JSON
          </button>
          <button
            type="button"
            data-testid="momentum-trial-journal-clear"
            onClick={onClear}
            disabled={!onClear}
          >
            Clear snapshot
          </button>
        </div>
      </div>

      <div
        data-testid="momentum-trial-journal-summary"
        className="op-row"
        style={{ flexWrap: "wrap", gap: 8 }}
        aria-label="Trial snapshot summary"
      >
        <div style={SUMMARY_CARD_STYLE}>
          <span style={SUMMARY_LABEL_STYLE}>Candidates captured</span>
          <span style={SUMMARY_VALUE_STYLE} data-testid="momentum-trial-journal-summary-count">
            {summary.candidate_count}
          </span>
        </div>
        <div style={SUMMARY_CARD_STYLE}>
          <span style={SUMMARY_LABEL_STYLE}>Active / shadow / off</span>
          <span style={SUMMARY_VALUE_STYLE}>
            {summary.active_mode_count} / {summary.shadow_mode_count} / {summary.off_mode_count}
          </span>
        </div>
        <div style={SUMMARY_CARD_STYLE}>
          <span style={SUMMARY_LABEL_STYLE}>Positive / negative / zero contribution</span>
          <span style={SUMMARY_VALUE_STYLE}>
            {summary.positive_contribution_count} / {summary.negative_contribution_count} / {summary.zero_contribution_count}
          </span>
        </div>
        <div style={SUMMARY_CARD_STYLE}>
          <span style={SUMMARY_LABEL_STYLE}>Trade warnings</span>
          <span
            style={SUMMARY_VALUE_STYLE}
            data-testid="momentum-trial-journal-summary-trade-warnings"
          >
            {summary.trade_warning_count}
          </span>
        </div>
        <div style={SUMMARY_CARD_STYLE}>
          <span style={SUMMARY_LABEL_STYLE}>Operational caveats</span>
          <span
            style={SUMMARY_VALUE_STYLE}
            data-testid="momentum-trial-journal-summary-operational-caveats"
          >
            {summary.operational_caveat_count}
          </span>
        </div>
        <div style={SUMMARY_CARD_STYLE}>
          <span style={SUMMARY_LABEL_STYLE}>Parity pending</span>
          <span style={SUMMARY_VALUE_STYLE}>{summary.parity_pending_count}</span>
        </div>
        <div style={SUMMARY_CARD_STYLE}>
          <span style={SUMMARY_LABEL_STYLE}>Direction unknown</span>
          <span style={SUMMARY_VALUE_STYLE}>{summary.direction_unknown_count}</span>
        </div>
        <div style={SUMMARY_CARD_STYLE}>
          <span style={SUMMARY_LABEL_STYLE}>Score consistency corrected</span>
          <span style={SUMMARY_VALUE_STYLE} data-testid="momentum-trial-journal-summary-corrected">
            {summary.score_consistency_corrected_count}
          </span>
        </div>
        <div style={SUMMARY_CARD_STYLE}>
          <span style={SUMMARY_LABEL_STYLE}>Blocked active</span>
          <span style={SUMMARY_VALUE_STYLE}>{summary.blocked_active_count}</span>
        </div>
      </div>

      {snapshot.universe_symbols.length > 0 ? (
        <div
          data-testid="momentum-trial-journal-universe"
          data-universe-kind={snapshot.universe_kind}
          style={{ fontSize: "0.78rem", color: "var(--op-muted, #7a8999)" }}
        >
          {momentumTrialUniverseLabel(snapshot.universe_kind)}: {snapshot.universe_symbols.join(", ")}
        </div>
      ) : null}

      <div data-testid="momentum-trial-journal-top-candidates" style={{ overflowX: "auto", minWidth: 0 }}>
        <h4 style={{ margin: "4px 0 6px 0", fontSize: "0.92rem" }}>Top candidates</h4>
        {snapshot.top_candidates.length === 0 ? (
          <p style={NOTE_STYLE}>No captured candidates yet.</p>
        ) : (
          <table className="op-table" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>Rank</th>
                <th style={{ textAlign: "left" }}>Symbol</th>
                <th style={{ textAlign: "left" }}>Strategy</th>
                <th style={{ textAlign: "left" }}>Mode</th>
                <th style={{ textAlign: "right" }}>Baseline</th>
                <th style={{ textAlign: "right" }}>Active / current</th>
                <th style={{ textAlign: "right" }}>Raw</th>
                <th style={{ textAlign: "right" }}>Applied Δ</th>
                <th style={{ textAlign: "left" }}>Total</th>
                <th style={{ textAlign: "left" }}>Trade warnings</th>
                <th style={{ textAlign: "left" }}>Operational caveats / reasons</th>
              </tr>
            </thead>
            <tbody>
              {snapshot.top_candidates.map((c) => (
                <tr
                  key={`${c.symbol}-${c.strategy}-${c.rank}`}
                  data-testid="momentum-trial-journal-top-row"
                  data-symbol={c.symbol}
                  data-classification={c.classification}
                >
                  <td>{c.rank}</td>
                  <td style={{ fontWeight: 600 }}>{c.symbol}</td>
                  <td>{c.strategy}</td>
                  <td>
                    <StatusBadge tone={classificationTone(c.classification)}>
                      {momentumRankingModeLabel(c.mode)}
                    </StatusBadge>
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {fmtUnitScore(c.baseline_score)}
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {fmtUnitScore(c.active_score)}
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {fmtRawScoreUnits(c.raw_contribution)}
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {fmtSignedScore(c.applied_delta)}
                  </td>
                  <td>
                    {c.total_score == null ? "—" : c.total_score}
                    {c.total_label ? (
                      <span style={{ color: "var(--op-muted, #7a8999)", marginLeft: 4 }}>
                        ({c.total_label})
                      </span>
                    ) : null}
                  </td>
                  <td>
                    <div className="op-row" style={{ flexWrap: "wrap", gap: 4 }}>
                      {c.trade_warning_flags.length === 0 ? (
                        <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>—</span>
                      ) : (
                        c.trade_warning_flags.map((flag) => (
                          <StatusBadge key={flag} tone="bad">
                            {flag.replaceAll("_", " ")}
                          </StatusBadge>
                        ))
                      )}
                    </div>
                  </td>
                  <td>
                    <div className="op-row" style={{ flexWrap: "wrap", gap: 4 }}>
                      {c.operational_caveat_flags.length === 0 && c.reason_labels.length === 0 ? (
                        <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>—</span>
                      ) : (
                        <>
                          {c.operational_caveat_flags.map((flag) => (
                            <StatusBadge key={flag} tone="warn">
                              {flag.replaceAll("_", " ")}
                            </StatusBadge>
                          ))}
                          {c.reason_labels.map((label) => (
                            <StatusBadge key={`reason-${label}`} tone="neutral">
                              {label}
                            </StatusBadge>
                          ))}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {!compact ? (
        <>
          <div data-testid="momentum-trial-journal-trade-warnings-table" style={{ overflowX: "auto", minWidth: 0 }}>
            <h4 style={{ margin: "4px 0 6px 0", fontSize: "0.92rem" }}>Trade warnings</h4>
            {snapshot.trade_warning_candidates.length === 0 ? (
              <p style={NOTE_STYLE} data-testid="momentum-trial-journal-trade-warnings-empty">
                No trade warnings captured.
              </p>
            ) : (
              <table className="op-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Rank</th>
                    <th style={{ textAlign: "left" }}>Symbol</th>
                    <th style={{ textAlign: "left" }}>Strategy</th>
                    <th style={{ textAlign: "left" }}>Mode</th>
                    <th style={{ textAlign: "left" }}>Flags</th>
                    <th style={{ textAlign: "left" }}>Reasons</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshot.trade_warning_candidates.map((c) => (
                    <tr
                      key={`trade-${c.symbol}-${c.strategy}-${c.rank}`}
                      data-testid="momentum-trial-journal-trade-warning-row"
                      data-symbol={c.symbol}
                    >
                      <td>{c.rank}</td>
                      <td style={{ fontWeight: 600 }}>{c.symbol}</td>
                      <td>{c.strategy}</td>
                      <td>{momentumRankingModeLabel(c.mode)}</td>
                      <td>
                        <div className="op-row" style={{ flexWrap: "wrap", gap: 4 }}>
                          {c.trade_warning_flags.map((flag) => (
                            <StatusBadge key={flag} tone="bad">
                              {flag.replaceAll("_", " ")}
                            </StatusBadge>
                          ))}
                        </div>
                      </td>
                      <td>
                        <div className="op-row" style={{ flexWrap: "wrap", gap: 4 }}>
                          {c.reason_labels.length === 0 ? (
                            <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>—</span>
                          ) : (
                            c.reason_labels.map((label) => (
                              <StatusBadge key={label} tone="neutral">
                                {label}
                              </StatusBadge>
                            ))
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div data-testid="momentum-trial-journal-operational-caveats-table" style={{ overflowX: "auto", minWidth: 0 }}>
            <h4 style={{ margin: "4px 0 6px 0", fontSize: "0.92rem" }}>Operational caveats</h4>
            {snapshot.operational_caveat_candidates.length === 0 ? (
              <p style={NOTE_STYLE} data-testid="momentum-trial-journal-operational-caveats-empty">
                No operational caveats captured.
              </p>
            ) : (
              <>
                <p
                  style={{ ...NOTE_STYLE, marginTop: 0 }}
                  data-testid="momentum-trial-journal-operational-caveats-explainer"
                >
                  Operational caveats describe data-quality, parity, and guardrail context.
                  They are not trade-direction warnings.
                </p>
                <table className="op-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left" }}>Rank</th>
                      <th style={{ textAlign: "left" }}>Symbol</th>
                      <th style={{ textAlign: "left" }}>Strategy</th>
                      <th style={{ textAlign: "left" }}>Mode</th>
                      <th style={{ textAlign: "left" }}>Flags</th>
                      <th style={{ textAlign: "left" }}>Reasons</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.operational_caveat_candidates.map((c) => (
                      <tr
                        key={`caveat-${c.symbol}-${c.strategy}-${c.rank}`}
                        data-testid="momentum-trial-journal-operational-caveat-row"
                        data-symbol={c.symbol}
                      >
                        <td>{c.rank}</td>
                        <td style={{ fontWeight: 600 }}>{c.symbol}</td>
                        <td>{c.strategy}</td>
                        <td>{momentumRankingModeLabel(c.mode)}</td>
                        <td>
                          <div className="op-row" style={{ flexWrap: "wrap", gap: 4 }}>
                            {c.operational_caveat_flags.map((flag) => (
                              <StatusBadge key={flag} tone="warn">
                                {flag.replaceAll("_", " ")}
                              </StatusBadge>
                            ))}
                          </div>
                        </td>
                        <td>
                          <div className="op-row" style={{ flexWrap: "wrap", gap: 4 }}>
                            {c.reason_labels.length === 0 ? (
                              <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>—</span>
                            ) : (
                              c.reason_labels.map((label) => (
                                <StatusBadge key={label} tone="neutral">
                                  {label}
                                </StatusBadge>
                              ))
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </>
      ) : null}

      {snapshot.operator_note ? (
        <div
          data-testid="momentum-trial-journal-operator-note-display"
          style={{
            padding: "8px 10px",
            borderRadius: 8,
            background: "rgba(15, 35, 55, 0.5)",
            border: "1px solid rgba(115, 138, 163, 0.24)",
            color: "var(--op-text, #d9e2ef)",
            fontSize: "0.85rem",
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
          }}
        >
          <strong style={{ display: "block", marginBottom: 2 }}>Operator note</strong>
          {snapshot.operator_note.text}
        </div>
      ) : null}
    </div>
  );
}

export function MomentumTrialJournal({
  candidates,
  universeSymbols,
  title = "Active Momentum Trial Journal",
  compact = false,
  initialSnapshot = null,
  persistLatest = true,
  onSnapshotChange,
  onOutcomeReviewChange,
}: MomentumTrialJournalProps) {
  const [noteDraft, setNoteDraft] = useState<string>("");
  const [snapshot, setSnapshot] = useState<MomentumTrialSnapshot | null>(initialSnapshot ?? null);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");

  // Phase C2.2 — notify the parent whenever the captured snapshot
  // changes. The parent lifts this state so the Phase C2 evidence
  // panel always sees the live snapshot.
  useEffect(() => {
    onSnapshotChange?.(snapshot);
  }, [snapshot, onSnapshotChange]);

  // Lazy load latest snapshot from localStorage on mount.
  useEffect(() => {
    if (!persistLatest) return;
    if (initialSnapshot) return;
    const cached = readLatestSnapshotFromStorage();
    if (cached) {
      setSnapshot(cached);
      if (cached.operator_note?.text) {
        setNoteDraft(cached.operator_note.text);
      }
    }
  }, [persistLatest, initialSnapshot]);

  const safeCandidates = useMemo(() => candidates ?? [], [candidates]);

  const captureSnapshot = useCallback(() => {
    const built = buildMomentumTrialSnapshot(safeCandidates, {
      universeSymbols: universeSymbols ?? undefined,
      operatorNote: noteDraft,
    });
    setSnapshot(built);
    if (persistLatest) writeLatestSnapshotToStorage(built);
    setCopyStatus("idle");
  }, [safeCandidates, universeSymbols, noteDraft, persistLatest]);

  const clearSnapshot = useCallback(() => {
    setSnapshot(null);
    if (persistLatest) writeLatestSnapshotToStorage(null);
    setCopyStatus("idle");
    // Clearing the snapshot also clears any associated outcome review.
    onOutcomeReviewChange?.(null);
  }, [persistLatest, onOutcomeReviewChange]);

  const downloadJsonHandler = useCallback(() => {
    if (!snapshot) return;
    const stamp = snapshot.generated_at.replace(/[^0-9A-Za-z]+/g, "-");
    downloadTextFile(
      `momentum-trial-${stamp}.json`,
      "application/json;charset=utf-8",
      buildMomentumTrialJson(snapshot),
    );
  }, [snapshot]);

  const downloadMarkdownHandler = useCallback(() => {
    if (!snapshot) return;
    const stamp = snapshot.generated_at.replace(/[^0-9A-Za-z]+/g, "-");
    downloadTextFile(
      `momentum-trial-${stamp}.md`,
      "text/markdown;charset=utf-8",
      buildMomentumTrialMarkdown(snapshot),
    );
  }, [snapshot]);

  const copyMarkdownHandler = useCallback(async () => {
    if (!snapshot) return;
    const ok = await copyToClipboard(buildMomentumTrialMarkdown(snapshot));
    setCopyStatus(ok ? "copied" : "failed");
  }, [snapshot]);

  const candidateCount = safeCandidates.length;
  const sanitizedNotePreview = useMemo(
    () => sanitizeMomentumTrialNote(noteDraft),
    [noteDraft],
  );

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label="Momentum trial journal"
        data-testid="momentum-trial-journal"
        className="op-stack"
        style={{ gap: 10 }}
      >
        <div
          className="op-row"
          style={{ flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}
        >
          <div className="op-row" style={{ flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            <StatusBadge tone="neutral">{candidateCount} candidate(s) in current queue</StatusBadge>
            <StatusBadge tone={snapshot ? "good" : "neutral"}>
              {snapshot ? "Snapshot captured" : "No snapshot captured yet"}
            </StatusBadge>
          </div>
          <div className="op-row" style={{ flexWrap: "wrap", gap: 6 }}>
            <button
              type="button"
              data-testid="momentum-trial-journal-capture"
              onClick={captureSnapshot}
              disabled={candidateCount === 0}
              aria-disabled={candidateCount === 0}
            >
              Capture Momentum Trial Snapshot
            </button>
          </div>
        </div>

        <label
          style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.82rem" }}
          aria-label="Operator note"
        >
          <span style={SUMMARY_LABEL_STYLE}>Operator note (optional)</span>
          <textarea
            data-testid="momentum-trial-journal-note-input"
            value={noteDraft}
            onChange={(event) => setNoteDraft(event.target.value)}
            placeholder='e.g. "XLK/IWM/QQQ leading; XLE/XLV weak; compare next session."'
            style={NOTE_INPUT_STYLE}
            maxLength={1500}
          />
          {sanitizedNotePreview && sanitizedNotePreview !== noteDraft.trim() ? (
            <span
              data-testid="momentum-trial-journal-note-sanitized"
              style={{ color: "var(--op-warn-text, #d6a25b)", fontSize: "0.72rem" }}
            >
              Note will be saved with action language redacted.
            </span>
          ) : null}
        </label>

        {snapshot ? (
          <>
            <MomentumTrialJournalView
              snapshot={snapshot}
              onCopyMarkdown={copyMarkdownHandler}
              onDownloadMarkdown={downloadMarkdownHandler}
              onDownloadJson={downloadJsonHandler}
              onClear={clearSnapshot}
              compact={compact}
            />
            {/*
              Phase B8 — Active Momentum Trial Outcome Review.
              Operator research notes only. Local/export-only — no
              backend persistence, no DB migration, no ranking, queue,
              approval, paper-order, or strategy-family behavior change.
            */}
            <MomentumTrialOutcomeReviewPanel
              snapshot={snapshot}
              persistLatest={persistLatest}
              onReviewChange={onOutcomeReviewChange}
            />
          </>
        ) : (
          <div role="region" aria-label="Momentum trial journal empty" data-testid="momentum-trial-journal-empty">
            <EmptyState
              title="No trial snapshot captured yet"
              hint={
                candidateCount === 0
                  ? "Generate a recommendation queue first, then capture a snapshot here."
                  : "Press “Capture Momentum Trial Snapshot” to record current queue evidence."
              }
            />
          </div>
        )}

        {copyStatus !== "idle" ? (
          <div
            data-testid="momentum-trial-journal-copy-status"
            style={{
              fontSize: "0.78rem",
              color:
                copyStatus === "copied"
                  ? "var(--op-good-text, #6ec07c)"
                  : "var(--op-warn-text, #d6a25b)",
            }}
            role="status"
            aria-live="polite"
          >
            {copyStatus === "copied"
              ? "Markdown copied to clipboard."
              : "Clipboard unavailable — use Download Markdown instead."}
          </div>
        ) : null}

        <p style={NOTE_STYLE} data-testid="momentum-trial-journal-deterministic-note-container">
          {MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE}
        </p>
      </div>
    </Card>
  );
}
