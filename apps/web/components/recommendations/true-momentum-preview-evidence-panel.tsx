"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";

import { Card, EmptyState, StatusBadge } from "@/components/operator-ui";
import {
  buildTrueMomentumPreviewEvidenceBundle,
  buildTrueMomentumPreviewEvidenceJson,
  buildTrueMomentumPreviewEvidenceMarkdown,
  isTrueMomentumPreviewEvidenceReviewTag,
  TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE,
  TRUE_MOMENTUM_PREVIEW_EVIDENCE_REVIEW_TAGS,
  TRUE_MOMENTUM_PREVIEW_EVIDENCE_STORAGE_KEY,
  sanitizeTrueMomentumPreviewEvidenceNote,
  trueMomentumPreviewEvidenceTagLabel,
  trueMomentumPreviewEvidenceTagTone,
  validateTrueMomentumPreviewEvidenceBundle,
  type TrueMomentumPreviewEvidenceBundle,
  type TrueMomentumPreviewEvidenceCandidate,
  type TrueMomentumPreviewEvidenceOperatorReview,
  type TrueMomentumPreviewEvidenceReviewTag,
} from "@/lib/true-momentum-preview-evidence";
import { trueMomentumPreviewReasonLabels } from "@/lib/true-momentum-strategy-preview";
import type { TrueMomentumStrategyPreviewResult } from "@/lib/true-momentum-strategy-preview";
import type { MomentumTrialSnapshot } from "@/lib/momentum-trial-journal";
import type { MomentumTrialOutcomeReview } from "@/lib/momentum-trial-outcomes";
import type { QueueCandidate } from "@/lib/recommendations";
import type { TrueMomentumStrategyPreviewFamilyId } from "@/lib/true-momentum-strategy-preview";

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

const SHORT_NOTE_INPUT_STYLE: React.CSSProperties = {
  width: "100%",
  minHeight: 32,
  resize: "vertical",
  fontFamily: "inherit",
  fontSize: "0.82rem",
  padding: 6,
  borderRadius: 6,
  background: "rgba(15, 24, 34, 0.55)",
  border: "1px solid rgba(115, 138, 163, 0.28)",
  color: "var(--op-text, #d9e2ef)",
};

function fmtScore(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function fmtRaw(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const rounded = Math.round(value * 100) / 100;
  if (rounded === 0) return "0.00";
  return rounded > 0 ? `+${rounded.toFixed(2)}` : rounded.toFixed(2);
}

function fmtSigned(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value === 0) return value.toFixed(digits);
  return value > 0 ? `+${value.toFixed(digits)}` : value.toFixed(digits);
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
    // best-effort
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
    // fall through
  }
  return false;
}

type PersistedPayload = {
  signature: string;
  generated_at: string;
  bundle: TrueMomentumPreviewEvidenceBundle;
};

function queueSignature(
  candidates: ReadonlyArray<QueueCandidate> | null | undefined,
): string {
  if (!Array.isArray(candidates) || candidates.length === 0) return "empty";
  const parts: string[] = [];
  for (const candidate of candidates) {
    parts.push(
      `${candidate?.symbol ?? ""}::${candidate?.strategy ?? ""}::${candidate?.rank ?? 0}`,
    );
  }
  return parts.join("|");
}

function readPersistedBundle(
  signature: string,
): TrueMomentumPreviewEvidenceBundle | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(
      TRUE_MOMENTUM_PREVIEW_EVIDENCE_STORAGE_KEY,
    );
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedPayload | null;
    if (!parsed || typeof parsed !== "object") return null;
    if (parsed.signature !== signature) return null;
    const validation = validateTrueMomentumPreviewEvidenceBundle(parsed.bundle);
    return validation.ok ? validation.bundle : null;
  } catch {
    return null;
  }
}

function persistBundle(
  signature: string,
  bundle: TrueMomentumPreviewEvidenceBundle,
): void {
  if (typeof window === "undefined") return;
  try {
    const payload: PersistedPayload = {
      signature,
      generated_at: bundle.generated_at,
      bundle,
    };
    window.localStorage.setItem(
      TRUE_MOMENTUM_PREVIEW_EVIDENCE_STORAGE_KEY,
      JSON.stringify(payload),
    );
  } catch {
    // best-effort
  }
}

function clearPersistedBundle(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(TRUE_MOMENTUM_PREVIEW_EVIDENCE_STORAGE_KEY);
  } catch {
    // best-effort
  }
}

export type TrueMomentumPreviewEvidencePanelProps = {
  candidates: ReadonlyArray<QueueCandidate> | null | undefined;
  previewResult: TrueMomentumStrategyPreviewResult | null | undefined;
  universeSymbols?: ReadonlyArray<string> | null;
  b8Snapshot?: MomentumTrialSnapshot | null;
  b8OutcomeReview?: MomentumTrialOutcomeReview | null;
  title?: string;
  compact?: boolean;
  persistLatest?: boolean;
  /**
   * Test-only: render with a pre-built bundle instead of waiting for
   * an operator capture. Production callers should leave this null.
   */
  initialBundle?: TrueMomentumPreviewEvidenceBundle | null;
};

export function TrueMomentumPreviewEvidencePanel({
  candidates,
  previewResult,
  universeSymbols,
  b8Snapshot = null,
  b8OutcomeReview = null,
  title = "True Momentum preview evidence (Phase C2 research-only)",
  compact = false,
  persistLatest = true,
  initialBundle = null,
}: TrueMomentumPreviewEvidencePanelProps) {
  const previewCount = previewResult?.previews?.length ?? 0;
  const signature = useMemo(() => queueSignature(candidates), [candidates]);

  const [bundle, setBundle] = useState<TrueMomentumPreviewEvidenceBundle | null>(
    initialBundle,
  );
  const [globalConclusion, setGlobalConclusion] = useState<string>(
    initialBundle?.operator_review.global_conclusion ?? "",
  );
  const defaultFamilyNotes = useMemo(
    () => ({
      true_momentum_continuation:
        initialBundle?.operator_review.family_notes.true_momentum_continuation ?? "",
      true_momentum_pullback:
        initialBundle?.operator_review.family_notes.true_momentum_pullback ?? "",
      true_momentum_reversal_watch:
        initialBundle?.operator_review.family_notes.true_momentum_reversal_watch ?? "",
    }),
    [initialBundle],
  );
  const [familyNotes, setFamilyNotes] = useState<
    Record<TrueMomentumStrategyPreviewFamilyId, string>
  >(defaultFamilyNotes);
  const [candidateNotes, setCandidateNotes] = useState<
    Record<string, { text: string; tag: TrueMomentumPreviewEvidenceReviewTag | null }>
  >(() => {
    const seed: Record<
      string,
      { text: string; tag: TrueMomentumPreviewEvidenceReviewTag | null }
    > = {};
    if (initialBundle) {
      for (const note of initialBundle.operator_review.candidate_notes) {
        seed[note.preview_id] = { text: note.text, tag: note.tag };
      }
    }
    return seed;
  });
  const [reviewTags, setReviewTags] = useState<TrueMomentumPreviewEvidenceReviewTag[]>(
    initialBundle?.operator_review.review_tags ?? [],
  );
  const [exportStatus, setExportStatus] = useState<"idle" | "copied" | "failed">(
    "idle",
  );

  // Lazy hydrate from localStorage when the same queue signature is on
  // screen.
  useEffect(() => {
    if (!persistLatest || initialBundle) return;
    const cached = readPersistedBundle(signature);
    if (!cached) return;
    setBundle(cached);
    setGlobalConclusion(cached.operator_review.global_conclusion);
    setFamilyNotes({
      true_momentum_continuation:
        cached.operator_review.family_notes.true_momentum_continuation,
      true_momentum_pullback:
        cached.operator_review.family_notes.true_momentum_pullback,
      true_momentum_reversal_watch:
        cached.operator_review.family_notes.true_momentum_reversal_watch,
    });
    const noteMap: Record<
      string,
      { text: string; tag: TrueMomentumPreviewEvidenceReviewTag | null }
    > = {};
    for (const note of cached.operator_review.candidate_notes) {
      noteMap[note.preview_id] = { text: note.text, tag: note.tag };
    }
    setCandidateNotes(noteMap);
    setReviewTags(cached.operator_review.review_tags);
  }, [persistLatest, initialBundle, signature]);

  const buildOperatorReview = useCallback((): TrueMomentumPreviewEvidenceOperatorReview => {
    const notes = Object.entries(candidateNotes)
      .map(([previewId, value]) => {
        const sourcePreview = previewResult?.previews?.find(
          (p) => p.preview_id === previewId,
        );
        if (!sourcePreview) return null;
        const cleaned = sanitizeTrueMomentumPreviewEvidenceNote(value.text);
        if (!cleaned && !value.tag) return null;
        return {
          preview_id: previewId,
          symbol: sourcePreview.symbol,
          text: cleaned,
          tag: value.tag,
        };
      })
      .filter((n): n is NonNullable<typeof n> => n !== null);
    return {
      global_conclusion: sanitizeTrueMomentumPreviewEvidenceNote(globalConclusion),
      family_notes: {
        true_momentum_continuation: sanitizeTrueMomentumPreviewEvidenceNote(
          familyNotes.true_momentum_continuation,
        ),
        true_momentum_pullback: sanitizeTrueMomentumPreviewEvidenceNote(
          familyNotes.true_momentum_pullback,
        ),
        true_momentum_reversal_watch: sanitizeTrueMomentumPreviewEvidenceNote(
          familyNotes.true_momentum_reversal_watch,
        ),
      },
      candidate_notes: notes,
      review_tags: reviewTags.slice(),
      authored_at: new Date().toISOString(),
    };
  }, [candidateNotes, familyNotes, globalConclusion, previewResult, reviewTags]);

  const buildLatestBundle = useCallback((): TrueMomentumPreviewEvidenceBundle | null => {
    if (!previewResult || previewCount === 0) return null;
    return buildTrueMomentumPreviewEvidenceBundle(previewResult, {
      queueCandidates: candidates ?? null,
      evaluatedUniverse: universeSymbols ?? null,
      rankingMode: previewResult.status?.effective_mode ?? null,
      activeDeltaScale: 0.35,
      b8Snapshot: b8Snapshot ?? null,
      b8OutcomeReview: b8OutcomeReview ?? null,
      operatorReview: buildOperatorReview(),
    });
  }, [
    previewResult,
    previewCount,
    candidates,
    universeSymbols,
    b8Snapshot,
    b8OutcomeReview,
    buildOperatorReview,
  ]);

  const captureBundle = useCallback(() => {
    const built = buildLatestBundle();
    if (!built) return;
    setBundle(built);
    if (persistLatest) persistBundle(signature, built);
    setExportStatus("idle");
  }, [buildLatestBundle, persistLatest, signature]);

  const clearBundle = useCallback(() => {
    setBundle(null);
    setGlobalConclusion("");
    setFamilyNotes({
      true_momentum_continuation: "",
      true_momentum_pullback: "",
      true_momentum_reversal_watch: "",
    });
    setCandidateNotes({});
    setReviewTags([]);
    if (persistLatest) clearPersistedBundle();
    setExportStatus("idle");
  }, [persistLatest]);

  const downloadMarkdown = useCallback(() => {
    const target = bundle ?? buildLatestBundle();
    if (!target) return;
    const stamp = target.generated_at.replace(/[^0-9A-Za-z]+/g, "-");
    downloadTextFile(
      `true-momentum-preview-evidence-${stamp}.md`,
      "text/markdown;charset=utf-8",
      buildTrueMomentumPreviewEvidenceMarkdown(target),
    );
    setExportStatus("idle");
  }, [bundle, buildLatestBundle]);

  const downloadJson = useCallback(() => {
    const target = bundle ?? buildLatestBundle();
    if (!target) return;
    const stamp = target.generated_at.replace(/[^0-9A-Za-z]+/g, "-");
    downloadTextFile(
      `true-momentum-preview-evidence-${stamp}.json`,
      "application/json;charset=utf-8",
      buildTrueMomentumPreviewEvidenceJson(target),
    );
    setExportStatus("idle");
  }, [bundle, buildLatestBundle]);

  const copyMarkdown = useCallback(async () => {
    const target = bundle ?? buildLatestBundle();
    if (!target) return;
    const ok = await copyToClipboard(
      buildTrueMomentumPreviewEvidenceMarkdown(target),
    );
    setExportStatus(ok ? "copied" : "failed");
  }, [bundle, buildLatestBundle]);

  const toggleReviewTag = useCallback((tag: TrueMomentumPreviewEvidenceReviewTag) => {
    setReviewTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
  }, []);

  if (previewCount === 0) {
    return (
      <Card title={title}>
        <div
          role="region"
          aria-label="True Momentum preview evidence empty"
          data-testid="true-momentum-preview-evidence-empty"
        >
          <EmptyState
            title="No preview rows to capture."
            hint="Enable the Phase C1 research preview and load a queue. The evidence bundle workflow captures whatever rows the classifier matched."
          />
          <p style={{ ...NOTE_STYLE, marginTop: 8 }}>
            {TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE}
          </p>
        </div>
      </Card>
    );
  }

  const livePreview =
    bundle ??
    buildTrueMomentumPreviewEvidenceBundle(previewResult ?? null, {
      queueCandidates: candidates ?? null,
      evaluatedUniverse: universeSymbols ?? null,
      rankingMode: previewResult?.status?.effective_mode ?? null,
      activeDeltaScale: 0.35,
      b8Snapshot: b8Snapshot ?? null,
      b8OutcomeReview: b8OutcomeReview ?? null,
      operatorReview: buildOperatorReview(),
      generatedAt: null,
    });

  const summary = livePreview;

  const renderFamilyTable = (
    familyId: TrueMomentumStrategyPreviewFamilyId,
    candidates: ReadonlyArray<TrueMomentumPreviewEvidenceCandidate>,
  ) => {
    if (candidates.length === 0) {
      return (
        <p
          style={NOTE_STYLE}
          data-testid={`true-momentum-preview-evidence-family-empty-${familyId}`}
        >
          No preview rows in this family.
        </p>
      );
    }
    return (
      <div
        data-testid={`true-momentum-preview-evidence-family-table-${familyId}`}
        style={{ overflowX: "auto", minWidth: 0 }}
      >
        <table className="op-table" style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>Rank</th>
              <th style={{ textAlign: "left" }}>Symbol</th>
              <th style={{ textAlign: "left" }}>Current strategy</th>
              <th style={{ textAlign: "left" }}>Match</th>
              <th style={{ textAlign: "right" }}>Baseline</th>
              <th style={{ textAlign: "right" }}>Active</th>
              <th style={{ textAlign: "right" }}>Raw</th>
              <th style={{ textAlign: "right" }}>Applied Δ</th>
              <th style={{ textAlign: "left" }}>Total</th>
              <th style={{ textAlign: "left" }}>Tag</th>
              <th style={{ textAlign: "left" }}>Operator note</th>
              <th style={{ textAlign: "left" }}>Reasons / caveats</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((row) => {
              const note = candidateNotes[row.preview_id] ?? { text: "", tag: null };
              const totalCell =
                row.total_score == null
                  ? "—"
                  : `${row.total_score}${row.total_label ? ` (${row.total_label})` : ""}`;
              const reasonLabels = trueMomentumPreviewReasonLabels(row.reason_codes);
              const caveatLabels = trueMomentumPreviewReasonLabels(
                row.operational_caveats,
              );
              return (
                <tr
                  key={row.preview_id}
                  data-testid="true-momentum-preview-evidence-row"
                  data-preview-id={row.preview_id}
                  data-symbol={row.symbol}
                  data-family-id={row.family_id}
                  data-match-strength={row.match_strength}
                >
                  <td>{row.rank}</td>
                  <td style={{ fontWeight: 600 }}>{row.symbol}</td>
                  <td>{row.current_strategy}</td>
                  <td>
                    <StatusBadge tone={row.match_strength === "watch" ? "warn" : row.match_strength === "strong" ? "good" : "neutral"}>
                      {row.match_strength}
                    </StatusBadge>
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {fmtScore(row.baseline_score)}
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {fmtScore(row.active_score)}
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {fmtRaw(row.raw_contribution)}
                  </td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {fmtSigned(row.applied_delta)}
                  </td>
                  <td>{totalCell}</td>
                  <td>
                    <select
                      aria-label={`Review tag for ${row.symbol}`}
                      data-testid="true-momentum-preview-evidence-candidate-tag"
                      value={note.tag ?? ""}
                      onChange={(event) => {
                        const next = event.target.value;
                        setCandidateNotes((prev) => ({
                          ...prev,
                          [row.preview_id]: {
                            text: prev[row.preview_id]?.text ?? "",
                            tag: isTrueMomentumPreviewEvidenceReviewTag(next)
                              ? (next as TrueMomentumPreviewEvidenceReviewTag)
                              : null,
                          },
                        }));
                        setExportStatus("idle");
                      }}
                      style={{
                        fontSize: "0.78rem",
                        padding: "2px 4px",
                        borderRadius: 4,
                        background: "rgba(15, 24, 34, 0.55)",
                        color: "var(--op-text, #d9e2ef)",
                        border: "1px solid rgba(115, 138, 163, 0.28)",
                      }}
                    >
                      <option value="">—</option>
                      {TRUE_MOMENTUM_PREVIEW_EVIDENCE_REVIEW_TAGS.map((tag) => (
                        <option key={tag} value={tag}>
                          {trueMomentumPreviewEvidenceTagLabel(tag)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <textarea
                      data-testid="true-momentum-preview-evidence-candidate-note"
                      aria-label={`Operator note for ${row.symbol}`}
                      value={note.text}
                      onChange={(event) => {
                        const next = event.target.value;
                        setCandidateNotes((prev) => ({
                          ...prev,
                          [row.preview_id]: {
                            text: next,
                            tag: prev[row.preview_id]?.tag ?? null,
                          },
                        }));
                        setExportStatus("idle");
                      }}
                      placeholder="Short note (optional)"
                      style={SHORT_NOTE_INPUT_STYLE}
                      maxLength={400}
                    />
                  </td>
                  <td>
                    <div className="op-row" style={{ flexWrap: "wrap", gap: 4 }}>
                      {reasonLabels.length === 0 && caveatLabels.length === 0 ? (
                        <span style={{ color: "var(--op-muted, #7a8999)", fontSize: "0.78rem" }}>
                          —
                        </span>
                      ) : (
                        <>
                          {reasonLabels.map((label) => (
                            <StatusBadge key={`reason-${label}`} tone="neutral">
                              {label}
                            </StatusBadge>
                          ))}
                          {caveatLabels.map((label) => (
                            <StatusBadge key={`caveat-${label}`} tone="warn">
                              {label}
                            </StatusBadge>
                          ))}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <Card title={title}>
      <div
        role="region"
        aria-label="True Momentum preview evidence"
        data-testid="true-momentum-preview-evidence"
        className="op-stack"
        style={{ gap: 10 }}
      >
        <div
          className="op-row"
          style={{ flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}
        >
          <div className="op-row" style={{ flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            <StatusBadge tone="neutral">
              {previewCount} preview row(s) eligible
            </StatusBadge>
            <StatusBadge tone={bundle ? "good" : "neutral"}>
              {bundle ? "Bundle captured" : "No bundle captured yet"}
            </StatusBadge>
            <StatusBadge tone={livePreview.b8_snapshot_present ? "good" : "neutral"}>
              B8 snapshot: {livePreview.b8_snapshot_present ? "linked" : "not linked"}
            </StatusBadge>
            <StatusBadge tone={livePreview.b8_outcome_review_present ? "good" : "neutral"}>
              B8 outcome review: {livePreview.b8_outcome_review_present ? "linked" : "not linked"}
            </StatusBadge>
          </div>
          <div className="op-row" style={{ flexWrap: "wrap", gap: 6 }}>
            <button
              type="button"
              data-testid="true-momentum-preview-evidence-capture"
              onClick={captureBundle}
              disabled={previewCount === 0}
              aria-disabled={previewCount === 0}
            >
              Capture True Momentum Preview Evidence
            </button>
          </div>
        </div>

        <div
          data-testid="true-momentum-preview-evidence-summary"
          className="op-row"
          style={{ flexWrap: "wrap", gap: 8 }}
          aria-label="Evidence summary"
        >
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Preview candidates</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.preview_count}</span>
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
            <span style={SUMMARY_LABEL_STYLE}>Parity pending</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.parity_pending_count}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>Derived HTF</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.derived_higher_timeframe_count}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>B8 snapshot</span>
            <span style={SUMMARY_VALUE_STYLE}>{summary.b8_snapshot_present ? "yes" : "no"}</span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>B8 outcome review</span>
            <span style={SUMMARY_VALUE_STYLE}>
              {summary.b8_outcome_review_present ? "yes" : "no"}
            </span>
          </div>
        </div>

        <label
          style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.82rem" }}
          aria-label="Global outcome conclusion"
        >
          <span style={SUMMARY_LABEL_STYLE}>Global research conclusion (optional)</span>
          <textarea
            data-testid="true-momentum-preview-evidence-global-conclusion"
            value={globalConclusion}
            onChange={(event) => {
              setGlobalConclusion(event.target.value);
              setExportStatus("idle");
            }}
            placeholder='e.g. "Continuation rows tracked well; pullback rows still need ToS spot-check."'
            style={NOTE_INPUT_STYLE}
            maxLength={1500}
          />
        </label>

        <div
          className="op-row"
          style={{ flexWrap: "wrap", gap: 6 }}
          data-testid="true-momentum-preview-evidence-review-tags"
        >
          {TRUE_MOMENTUM_PREVIEW_EVIDENCE_REVIEW_TAGS.map((tag) => {
            const active = reviewTags.includes(tag);
            return (
              <button
                key={tag}
                type="button"
                data-testid="true-momentum-preview-evidence-review-tag"
                data-tag={tag}
                data-active={active ? "true" : "false"}
                onClick={() => {
                  toggleReviewTag(tag);
                  setExportStatus("idle");
                }}
                style={{
                  padding: "2px 8px",
                  fontSize: "0.78rem",
                  borderRadius: 4,
                  border: active
                    ? "1px solid rgba(115, 220, 163, 0.4)"
                    : "1px solid rgba(115, 138, 163, 0.28)",
                  background: active
                    ? "rgba(110, 192, 124, 0.18)"
                    : "rgba(15, 24, 34, 0.55)",
                  color: "var(--op-text, #d9e2ef)",
                }}
              >
                <StatusBadge tone={trueMomentumPreviewEvidenceTagTone(tag)}>
                  {trueMomentumPreviewEvidenceTagLabel(tag)}
                </StatusBadge>
              </button>
            );
          })}
        </div>

        {!compact ? (
          <div data-testid="true-momentum-preview-evidence-family-sections" className="op-stack" style={{ gap: 10 }}>
            {livePreview.family_summaries.map((family) => (
              <div key={family.family_id} data-testid="true-momentum-preview-evidence-family-section">
                <h4 style={{ margin: "4px 0 6px 0", fontSize: "0.92rem" }}>
                  {family.family_label} ({family.preview_count})
                </h4>
                <label
                  style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.82rem" }}
                  aria-label={`${family.family_label} note`}
                >
                  <span style={SUMMARY_LABEL_STYLE}>Family note (optional)</span>
                  <textarea
                    data-testid="true-momentum-preview-evidence-family-note"
                    data-family-id={family.family_id}
                    value={familyNotes[family.family_id]}
                    onChange={(event) => {
                      const next = event.target.value;
                      setFamilyNotes((prev) => ({
                        ...prev,
                        [family.family_id]: next,
                      }));
                      setExportStatus("idle");
                    }}
                    placeholder="Operator family-level note"
                    style={NOTE_INPUT_STYLE}
                    maxLength={1500}
                  />
                </label>
                {renderFamilyTable(family.family_id, family.candidates)}
              </div>
            ))}
          </div>
        ) : null}

        <div className="op-row" style={{ flexWrap: "wrap", gap: 6, justifyContent: "flex-end" }}>
          <button
            type="button"
            data-testid="true-momentum-preview-evidence-copy-markdown"
            onClick={copyMarkdown}
          >
            Copy Markdown
          </button>
          <button
            type="button"
            data-testid="true-momentum-preview-evidence-download-markdown"
            onClick={downloadMarkdown}
          >
            Download Markdown
          </button>
          <button
            type="button"
            data-testid="true-momentum-preview-evidence-download-json"
            onClick={downloadJson}
          >
            Download JSON
          </button>
          <button
            type="button"
            data-testid="true-momentum-preview-evidence-clear"
            onClick={clearBundle}
            disabled={!bundle}
            aria-disabled={!bundle}
          >
            Clear current bundle
          </button>
        </div>

        {exportStatus !== "idle" ? (
          <div
            data-testid="true-momentum-preview-evidence-copy-status"
            role="status"
            aria-live="polite"
            style={{
              fontSize: "0.78rem",
              color:
                exportStatus === "copied"
                  ? "var(--op-good-text, #6ec07c)"
                  : "var(--op-warn-text, #d6a25b)",
            }}
          >
            {exportStatus === "copied"
              ? "Markdown copied to clipboard."
              : "Clipboard unavailable — use Download Markdown instead."}
          </div>
        ) : null}

        <p
          style={NOTE_STYLE}
          data-testid="true-momentum-preview-evidence-deterministic-note"
        >
          {TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE}
        </p>
        <p
          style={NOTE_STYLE}
          data-testid="true-momentum-preview-evidence-still-pending"
        >
          Still pending: accumulated B8 outcome evidence · Thinkorswim fixture parity ·
          operator authorization before any active Phase C.
        </p>
      </div>
    </Card>
  );
}
