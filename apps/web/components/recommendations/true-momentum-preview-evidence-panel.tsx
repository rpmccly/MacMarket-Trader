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
import {
  MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY,
  validateMomentumTrialSnapshot,
  type MomentumTrialSnapshot,
} from "@/lib/momentum-trial-journal";
import {
  MOMENTUM_TRIAL_OUTCOME_STORAGE_KEY,
  validateMomentumTrialOutcomeReview,
  type MomentumTrialOutcomeReview,
} from "@/lib/momentum-trial-outcomes";
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

// Phase C2.1 — read-only rehydration of the Phase B7 trial snapshot
// and Phase B8 outcome review from localStorage. Lets the evidence
// panel surface "linked / missing / mismatch" status without lifting
// state into the Recommendations page.
function readPersistedB8Snapshot(): MomentumTrialSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(MOMENTUM_TRIAL_JOURNAL_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const result = validateMomentumTrialSnapshot(parsed);
    return result.ok ? result.snapshot : null;
  } catch {
    return null;
  }
}

function readPersistedB8OutcomeReview(
  snapshot: MomentumTrialSnapshot | null,
): MomentumTrialOutcomeReview | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(MOMENTUM_TRIAL_OUTCOME_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    // The outcome review is persisted as a flat
    // ``{ snapshot_generated_at, outcomes, global_conclusion }`` envelope
    // (see ``momentum-trial-outcome-review.tsx``). Rebuild the full
    // ``MomentumTrialOutcomeReview`` shape against the live snapshot
    // so the C2 resolver can compare snapshot signatures.
    if (
      parsed &&
      typeof parsed === "object" &&
      typeof parsed.snapshot_generated_at === "string" &&
      Array.isArray(parsed.outcomes) &&
      snapshot &&
      snapshot.generated_at === parsed.snapshot_generated_at
    ) {
      const candidateOutcomes: MomentumTrialOutcomeReview["candidate_outcomes"] = [];
      for (const raw of parsed.outcomes) {
        if (!raw || typeof raw !== "object") continue;
        candidateOutcomes.push({
          symbol: typeof raw.symbol === "string" ? raw.symbol : "",
          strategy: typeof raw.strategy === "string" ? raw.strategy : "",
          rank: typeof raw.rank === "number" ? raw.rank : 0,
          tag: raw.tag ?? "unclear",
          note: typeof raw.note === "string" ? raw.note : "",
          reason_codes: Array.isArray(raw.reason_codes) ? raw.reason_codes : [],
          trade_warning_flags: Array.isArray(raw.trade_warning_flags)
            ? raw.trade_warning_flags
            : [],
          operational_caveat_flags: Array.isArray(raw.operational_caveat_flags)
            ? raw.operational_caveat_flags
            : [],
        });
      }
      const conclusionText =
        typeof parsed.global_conclusion === "string"
          ? parsed.global_conclusion
          : "";
      const stub: MomentumTrialOutcomeReview = {
        schema_version: "phase_b8.v1",
        generated_at: parsed.snapshot_generated_at,
        snapshot,
        global_conclusion: conclusionText
          ? { text: conclusionText, authored_at: parsed.snapshot_generated_at }
          : null,
        candidate_outcomes: candidateOutcomes,
        summary: {
          candidate_count: candidateOutcomes.length,
          worked_count: 0,
          missed_count: 0,
          too_aggressive_count: 0,
          good_warning_count: 0,
          false_warning_count: 0,
          watchlist_only_count: 0,
          needs_tos_parity_check_count: 0,
          ignored_count: 0,
          unclear_count: 0,
          reason_code_counts: {},
        },
      };
      return stub;
    }
    // Some callers persist a full envelope already (e.g. tests). Run
    // it through the schema validator; if it parses, return as-is.
    const validation = validateMomentumTrialOutcomeReview(parsed);
    if (validation.ok) return validation.review;
    return null;
  } catch {
    return null;
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

  // Phase C2.1 — rehydrate B7 snapshot + B8 outcome review from
  // localStorage when the caller did not pass them in explicitly.
  // Read-only and runs once per signature; never writes back.
  const [hydratedB8Snapshot, setHydratedB8Snapshot] =
    useState<MomentumTrialSnapshot | null>(b8Snapshot);
  const [hydratedB8OutcomeReview, setHydratedB8OutcomeReview] =
    useState<MomentumTrialOutcomeReview | null>(b8OutcomeReview);

  useEffect(() => {
    if (b8Snapshot !== null) {
      setHydratedB8Snapshot(b8Snapshot);
    } else if (persistLatest) {
      setHydratedB8Snapshot(readPersistedB8Snapshot());
    } else {
      setHydratedB8Snapshot(null);
    }
  }, [b8Snapshot, persistLatest, signature]);

  useEffect(() => {
    if (b8OutcomeReview !== null) {
      setHydratedB8OutcomeReview(b8OutcomeReview);
    } else if (persistLatest) {
      setHydratedB8OutcomeReview(readPersistedB8OutcomeReview(hydratedB8Snapshot));
    } else {
      setHydratedB8OutcomeReview(null);
    }
  }, [b8OutcomeReview, persistLatest, hydratedB8Snapshot]);

  const effectiveB8Snapshot = hydratedB8Snapshot;
  const effectiveB8OutcomeReview = hydratedB8OutcomeReview;

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
      b8Snapshot: effectiveB8Snapshot,
      b8OutcomeReview: effectiveB8OutcomeReview,
      operatorReview: buildOperatorReview(),
    });
  }, [
    previewResult,
    previewCount,
    candidates,
    universeSymbols,
    effectiveB8Snapshot,
    effectiveB8OutcomeReview,
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
      b8Snapshot: effectiveB8Snapshot,
      b8OutcomeReview: effectiveB8OutcomeReview,
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
            <StatusBadge
              tone={
                livePreview.b8_snapshot_link_status === "linked"
                  ? "good"
                  : livePreview.b8_snapshot_link_status === "mismatch"
                    ? "warn"
                    : "neutral"
              }
              data-testid="true-momentum-preview-evidence-snapshot-status-badge"
            >
              B8 snapshot: {livePreview.b8_snapshot_link_status}
            </StatusBadge>
            <StatusBadge
              tone={
                livePreview.b8_outcome_review_link_status === "linked"
                  ? "good"
                  : livePreview.b8_outcome_review_link_status === "mismatch"
                    ? "warn"
                    : livePreview.b8_outcome_review_link_status === "partial"
                      ? "warn"
                      : "neutral"
              }
              data-testid="true-momentum-preview-evidence-outcome-status-badge"
            >
              B8 outcome review: {livePreview.b8_outcome_review_link_status}
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
            <span
              style={SUMMARY_VALUE_STYLE}
              data-testid="true-momentum-preview-evidence-summary-snapshot"
            >
              {summary.b8_snapshot_link_status}
            </span>
          </div>
          <div style={SUMMARY_CARD_STYLE}>
            <span style={SUMMARY_LABEL_STYLE}>B8 outcome review</span>
            <span
              style={SUMMARY_VALUE_STYLE}
              data-testid="true-momentum-preview-evidence-summary-outcome"
            >
              {summary.b8_outcome_review_link_status}
            </span>
          </div>
          {livePreview.b8_outcome_reviewed_count != null ? (
            <div style={SUMMARY_CARD_STYLE}>
              <span style={SUMMARY_LABEL_STYLE}>Reviewed candidates</span>
              <span
                style={SUMMARY_VALUE_STYLE}
                data-testid="true-momentum-preview-evidence-summary-reviewed"
              >
                {livePreview.b8_outcome_reviewed_count}
              </span>
            </div>
          ) : null}
          {livePreview.b8_outcome_summary ? (
            <div style={SUMMARY_CARD_STYLE}>
              <span style={SUMMARY_LABEL_STYLE}>Unclear outcomes</span>
              <span
                style={SUMMARY_VALUE_STYLE}
                data-testid="true-momentum-preview-evidence-summary-unclear"
              >
                {livePreview.b8_outcome_summary.unclear_count}
              </span>
            </div>
          ) : null}
        </div>

        <div
          data-testid="true-momentum-preview-evidence-b8-link"
          className="op-stack"
          style={{ gap: 4 }}
        >
          <p
            style={NOTE_STYLE}
            data-testid="true-momentum-preview-evidence-b8-link-snapshot"
          >
            {livePreview.b8_snapshot_link_status === "linked"
              ? `Linked to current Momentum Trial Journal snapshot${
                  livePreview.b8_snapshot_generated_at
                    ? ` (captured ${livePreview.b8_snapshot_generated_at})`
                    : ""
                }.`
              : livePreview.b8_snapshot_link_status === "mismatch"
                ? "A B8 snapshot exists, but it belongs to a different queue."
                : "No B8 snapshot linked. Capture a Momentum Trial Journal snapshot for this queue."}
          </p>
          <p
            style={NOTE_STYLE}
            data-testid="true-momentum-preview-evidence-b8-link-outcome"
          >
            {livePreview.b8_outcome_review_link_status === "linked"
              ? `B8 outcome review linked${
                  livePreview.b8_outcome_generated_at
                    ? ` (authored ${livePreview.b8_outcome_generated_at})`
                    : ""
                }.`
              : livePreview.b8_outcome_review_link_status === "partial"
                ? "Outcome review linked, but most outcomes are still unclear."
                : livePreview.b8_outcome_review_link_status === "mismatch"
                  ? "A B8 outcome review exists, but it belongs to a different queue."
                  : "No B8 outcome review captured yet for this queue."}
          </p>
          {livePreview.b8_outcome_summary &&
          livePreview.b8_outcome_review_link_status !== "missing" ? (
            <p
              style={NOTE_STYLE}
              data-testid="true-momentum-preview-evidence-b8-link-outcome-counts"
            >
              Outcome counts — worked: {livePreview.b8_outcome_summary.worked_count} ·
              missed: {livePreview.b8_outcome_summary.missed_count} · too aggressive:{" "}
              {livePreview.b8_outcome_summary.too_aggressive_count} · good warnings:{" "}
              {livePreview.b8_outcome_summary.good_warning_count} · false warnings:{" "}
              {livePreview.b8_outcome_summary.false_warning_count} · needs ToS parity:{" "}
              {livePreview.b8_outcome_summary.needs_tos_parity_check_count} · unclear:{" "}
              {livePreview.b8_outcome_summary.unclear_count}
            </p>
          ) : null}
          {livePreview.b8_link_warning ? (
            <p
              style={{ ...NOTE_STYLE, color: "var(--op-warn-text, #d6a25b)" }}
              data-testid="true-momentum-preview-evidence-b8-link-warning"
            >
              {livePreview.b8_link_warning}
            </p>
          ) : null}
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
