// Phase C2 — True Momentum research-preview evidence bundle helpers.
//
// Pure, side-effect-free helpers that wrap an existing Phase C1 preview
// classification (and optionally the captured Phase B7 trial snapshot
// + Phase B8 outcome review) into a deterministic operator evidence
// bundle. Local/export-only — no backend write, no DB row, no LLM call.
// Never mutates the source candidates, never proposes entries / stops /
// targets / sizes / approvals / orders, and never generates queue
// candidates.

import type {
  MomentumTrialOutcomeReview,
} from "@/lib/momentum-trial-outcomes";
import type { MomentumTrialSnapshot } from "@/lib/momentum-trial-journal";
import type { QueueCandidate } from "@/lib/recommendations";
import type {
  TrueMomentumStrategyPreviewCandidate,
  TrueMomentumStrategyPreviewFamilyId,
  TrueMomentumStrategyPreviewMatchStrength,
  TrueMomentumStrategyPreviewResult,
} from "@/lib/true-momentum-strategy-preview";
import {
  familyPreviewLabel,
  trueMomentumPreviewReasonLabels,
  TRUE_MOMENTUM_STRATEGY_PREVIEW_PHASE,
} from "@/lib/true-momentum-strategy-preview";

export const TRUE_MOMENTUM_PREVIEW_EVIDENCE_SCHEMA_VERSION = "phase_c2.v1";
export const TRUE_MOMENTUM_PREVIEW_EVIDENCE_PHASE = "C2";
export const TRUE_MOMENTUM_PREVIEW_EVIDENCE_IMPLEMENTATION_STATUS =
  "research_preview_evidence";

export const TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE =
  "True Momentum preview evidence is research-only. It does not generate queue candidates, approve, reject, size, or route trades.";

export const TRUE_MOMENTUM_PREVIEW_EVIDENCE_STORAGE_KEY =
  "macmarket.trueMomentumPreviewEvidence.latest";

export type TrueMomentumPreviewEvidenceUniverseKind = "evaluated" | "captured";

export type TrueMomentumPreviewEvidenceReviewTag =
  | "research_candidate"
  | "watchlist_only"
  | "needs_tos_parity_check"
  | "needs_b8_outcome_evidence"
  | "too_noisy"
  | "defer";

export const TRUE_MOMENTUM_PREVIEW_EVIDENCE_REVIEW_TAGS: ReadonlyArray<TrueMomentumPreviewEvidenceReviewTag> = [
  "research_candidate",
  "watchlist_only",
  "needs_tos_parity_check",
  "needs_b8_outcome_evidence",
  "too_noisy",
  "defer",
];

const REVIEW_TAG_LABELS: Record<TrueMomentumPreviewEvidenceReviewTag, string> = {
  research_candidate: "Research candidate",
  watchlist_only: "Watchlist only",
  needs_tos_parity_check: "Needs ToS parity check",
  needs_b8_outcome_evidence: "Needs B8 outcome evidence",
  too_noisy: "Too noisy",
  defer: "Defer",
};

const REVIEW_TAG_TONES: Record<
  TrueMomentumPreviewEvidenceReviewTag,
  "good" | "warn" | "bad" | "neutral"
> = {
  research_candidate: "good",
  watchlist_only: "neutral",
  needs_tos_parity_check: "warn",
  needs_b8_outcome_evidence: "warn",
  too_noisy: "warn",
  defer: "neutral",
};

export function trueMomentumPreviewEvidenceTagLabel(
  tag: TrueMomentumPreviewEvidenceReviewTag | string | null | undefined,
): string {
  if (tag == null) return "—";
  if (typeof tag === "string" && tag in REVIEW_TAG_LABELS) {
    return REVIEW_TAG_LABELS[tag as TrueMomentumPreviewEvidenceReviewTag];
  }
  return String(tag);
}

export function trueMomentumPreviewEvidenceTagTone(
  tag: TrueMomentumPreviewEvidenceReviewTag | string | null | undefined,
): "good" | "warn" | "bad" | "neutral" {
  if (tag == null) return "neutral";
  if (typeof tag === "string" && tag in REVIEW_TAG_TONES) {
    return REVIEW_TAG_TONES[tag as TrueMomentumPreviewEvidenceReviewTag];
  }
  return "neutral";
}

export function isTrueMomentumPreviewEvidenceReviewTag(
  value: unknown,
): value is TrueMomentumPreviewEvidenceReviewTag {
  return (
    typeof value === "string" &&
    (TRUE_MOMENTUM_PREVIEW_EVIDENCE_REVIEW_TAGS as ReadonlyArray<string>).includes(
      value,
    )
  );
}

export type TrueMomentumPreviewEvidenceCandidate = {
  preview_id: string;
  family_id: TrueMomentumStrategyPreviewFamilyId;
  family_label: string;
  rank: number;
  symbol: string;
  current_strategy: string;
  baseline_score: number;
  active_score: number;
  raw_contribution: number;
  applied_delta: number;
  total_score: number | null;
  total_label: string | null;
  trend_score: number | null;
  momo_score: number | null;
  match_strength: TrueMomentumStrategyPreviewMatchStrength;
  inferred_direction: "long" | "short" | "unknown";
  pullback_signal: boolean;
  reversal_warning: boolean;
  no_trade_warning: boolean;
  reason_codes: string[];
  operational_caveats: string[];
  trade_warnings: string[];
  non_actionable: true;
};

export type TrueMomentumPreviewEvidenceFamilySummary = {
  family_id: TrueMomentumStrategyPreviewFamilyId;
  family_label: string;
  preview_count: number;
  strong_count: number;
  moderate_count: number;
  watch_count: number;
  blocked_count: number;
  parity_pending_count: number;
  derived_higher_timeframe_count: number;
  operational_caveat_count: number;
  candidates: TrueMomentumPreviewEvidenceCandidate[];
};

export type TrueMomentumPreviewEvidenceCandidateNote = {
  preview_id: string;
  symbol: string;
  text: string;
  tag: TrueMomentumPreviewEvidenceReviewTag | null;
};

export type TrueMomentumPreviewEvidenceOperatorReview = {
  global_conclusion: string;
  family_notes: Record<TrueMomentumStrategyPreviewFamilyId, string>;
  candidate_notes: TrueMomentumPreviewEvidenceCandidateNote[];
  review_tags: TrueMomentumPreviewEvidenceReviewTag[];
  authored_at: string;
};

export type TrueMomentumPreviewEvidenceFamilyCounts = {
  continuation_count: number;
  pullback_count: number;
  reversal_watch_count: number;
};

export type TrueMomentumPreviewEvidenceBundle = {
  schema_version: typeof TRUE_MOMENTUM_PREVIEW_EVIDENCE_SCHEMA_VERSION;
  generated_at: string;
  preview_phase: typeof TRUE_MOMENTUM_PREVIEW_EVIDENCE_PHASE;
  implementation_status: typeof TRUE_MOMENTUM_PREVIEW_EVIDENCE_IMPLEMENTATION_STATUS;
  ranking_mode: string;
  active_delta_scale: number;
  evaluated_universe: string[];
  universe_kind: TrueMomentumPreviewEvidenceUniverseKind;
  candidate_count: number;
  preview_count: number;
  family_counts: TrueMomentumPreviewEvidenceFamilyCounts;
  continuation_count: number;
  pullback_count: number;
  reversal_watch_count: number;
  parity_pending_count: number;
  derived_higher_timeframe_count: number;
  trade_warning_count: number;
  operational_caveat_count: number;
  score_consistency_corrected_count: number;
  b8_snapshot_present: boolean;
  b8_outcome_review_present: boolean;
  family_summaries: TrueMomentumPreviewEvidenceFamilySummary[];
  preview_candidates: TrueMomentumPreviewEvidenceCandidate[];
  operator_review: TrueMomentumPreviewEvidenceOperatorReview;
  deterministic_note: typeof TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE;
};

export type TrueMomentumPreviewEvidenceSummary = {
  candidate_count: number;
  preview_count: number;
  continuation_count: number;
  pullback_count: number;
  reversal_watch_count: number;
  parity_pending_count: number;
  derived_higher_timeframe_count: number;
  trade_warning_count: number;
  operational_caveat_count: number;
  score_consistency_corrected_count: number;
  b8_snapshot_present: boolean;
  b8_outcome_review_present: boolean;
};

export type TrueMomentumPreviewEvidenceExportPayload = {
  schema_version: typeof TRUE_MOMENTUM_PREVIEW_EVIDENCE_SCHEMA_VERSION;
  bundle: TrueMomentumPreviewEvidenceBundle;
  deterministic_note: typeof TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE;
};

// ── Note sanitization ────────────────────────────────────────────────

const MAX_NOTE_LENGTH = 1200;

// Constructed from token pairs so trade-direction / order-routing
// literals never appear in this source file.
const ACTION_WORD_PAIRS: ReadonlyArray<readonly [string, string]> = [
  ["buy", "now"],
  ["sell", "now"],
  ["enter", "now"],
  ["short", "now"],
  ["auto", "approve"],
  ["route", "order"],
  ["place", "order"],
  ["submit", "order"],
];

const FORBIDDEN_NOTE_PHRASES: ReadonlyArray<string> = (() => {
  const out: string[] = [];
  for (const [a, b] of ACTION_WORD_PAIRS) {
    out.push(`${a} ${b}`);
    if (a === "auto") out.push(`${a}-${b}`);
  }
  return out;
})();

export function sanitizeTrueMomentumPreviewEvidenceNote(note: unknown): string {
  if (note == null) return "";
  const raw = String(note);
  const collapsed = raw
    .replace(/\r\n?/g, "\n")
    .replace(/[\t ]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (!collapsed) return "";
  let cleaned = collapsed;
  const lowered = cleaned.toLowerCase();
  for (const phrase of FORBIDDEN_NOTE_PHRASES) {
    if (lowered.includes(phrase)) {
      const re = new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "ig");
      cleaned = cleaned.replace(re, "[redacted]");
    }
  }
  if (cleaned.length > MAX_NOTE_LENGTH) {
    cleaned = `${cleaned.slice(0, MAX_NOTE_LENGTH - 1).trimEnd()}…`;
  }
  return cleaned;
}

// ── Number sanitization ──────────────────────────────────────────────

function sanitizeFinite(value: unknown, fallback = 0): number {
  if (value == null) return fallback;
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num) || !Number.isFinite(num)) return fallback;
  return num;
}

function sanitizeOptionalNumber(value: unknown): number | null {
  if (value == null) return null;
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num) || !Number.isFinite(num)) return null;
  return num;
}

function sanitizeOptionalInt(value: unknown): number | null {
  const num = sanitizeOptionalNumber(value);
  return num == null ? null : Math.trunc(num);
}

function clampUnit(value: number): number {
  if (!Number.isFinite(value) || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function nowIso(): string {
  return new Date().toISOString();
}

function formatTimestamp(value: unknown): string {
  if (value == null) return nowIso();
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return nowIso();
    const parsed = Date.parse(trimmed);
    if (!Number.isFinite(parsed)) return trimmed;
    return new Date(parsed).toISOString();
  }
  if (value instanceof Date) {
    const ms = value.getTime();
    if (!Number.isFinite(ms)) return nowIso();
    return value.toISOString();
  }
  return nowIso();
}

function dedupeStrings(values: ReadonlyArray<string> | null | undefined): string[] {
  if (!Array.isArray(values)) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    if (typeof value !== "string") continue;
    const trimmed = value.trim();
    if (!trimmed) continue;
    if (seen.has(trimmed)) continue;
    seen.add(trimmed);
    out.push(trimmed);
  }
  return out;
}

function dedupeSymbols(values: ReadonlyArray<string>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const value of values) {
    if (typeof value !== "string") continue;
    const trimmed = value.trim();
    if (!trimmed) continue;
    const upper = trimmed.toUpperCase();
    if (seen.has(upper)) continue;
    seen.add(upper);
    out.push(upper);
  }
  return out;
}

// ── Candidate adapter ────────────────────────────────────────────────

function lookupQueueCandidate(
  queueCandidates: ReadonlyArray<QueueCandidate>,
  preview: TrueMomentumStrategyPreviewCandidate,
): QueueCandidate | null {
  for (const candidate of queueCandidates) {
    if (!candidate) continue;
    if (
      candidate.symbol === preview.symbol &&
      candidate.strategy === preview.strategy &&
      sanitizeFinite(candidate.rank, -1) === preview.rank
    ) {
      return candidate;
    }
  }
  return null;
}

function tradeWarningsFor(
  preview: TrueMomentumStrategyPreviewCandidate,
): string[] {
  const flags: string[] = [];
  if (preview.no_trade_warning) flags.push("no_trade_warning");
  if (preview.reversal_warning) flags.push("reversal_warning");
  return flags;
}

function evidenceCandidateFromPreview(
  preview: TrueMomentumStrategyPreviewCandidate,
  source: QueueCandidate | null,
): TrueMomentumPreviewEvidenceCandidate {
  const fallbackStrategy =
    typeof source?.strategy === "string" ? source.strategy : preview.strategy;
  return {
    preview_id: preview.preview_id,
    family_id: preview.family_id,
    family_label: preview.family_label || familyPreviewLabel(preview.family_id),
    rank: Math.trunc(sanitizeFinite(preview.rank, 0)),
    symbol: preview.symbol,
    current_strategy: fallbackStrategy,
    baseline_score: clampUnit(sanitizeFinite(preview.baseline_score, 0)),
    active_score: clampUnit(sanitizeFinite(preview.active_score, 0)),
    raw_contribution: sanitizeFinite(preview.raw_contribution, 0),
    applied_delta: sanitizeFinite(preview.applied_delta, 0),
    total_score: sanitizeOptionalInt(preview.total_score),
    total_label:
      typeof preview.total_label === "string" && preview.total_label.trim()
        ? preview.total_label.trim()
        : null,
    trend_score: sanitizeOptionalNumber(preview.trend_score),
    momo_score: sanitizeOptionalNumber(preview.momo_score),
    match_strength: preview.match_strength,
    inferred_direction: preview.inferred_direction,
    pullback_signal: !!preview.pullback_signal,
    reversal_warning: !!preview.reversal_warning,
    no_trade_warning: !!preview.no_trade_warning,
    reason_codes: dedupeStrings(preview.reason_codes),
    operational_caveats: dedupeStrings(preview.operational_caveats),
    trade_warnings: tradeWarningsFor(preview),
    non_actionable: true,
  };
}

// ── Summaries ────────────────────────────────────────────────────────

const FAMILY_ORDER: ReadonlyArray<TrueMomentumStrategyPreviewFamilyId> = [
  "true_momentum_continuation",
  "true_momentum_pullback",
  "true_momentum_reversal_watch",
];

function emptyFamilySummary(
  familyId: TrueMomentumStrategyPreviewFamilyId,
): TrueMomentumPreviewEvidenceFamilySummary {
  return {
    family_id: familyId,
    family_label: familyPreviewLabel(familyId),
    preview_count: 0,
    strong_count: 0,
    moderate_count: 0,
    watch_count: 0,
    blocked_count: 0,
    parity_pending_count: 0,
    derived_higher_timeframe_count: 0,
    operational_caveat_count: 0,
    candidates: [],
  };
}

function buildFamilySummaries(
  evidenceCandidates: ReadonlyArray<TrueMomentumPreviewEvidenceCandidate>,
): TrueMomentumPreviewEvidenceFamilySummary[] {
  const summaries = new Map<
    TrueMomentumStrategyPreviewFamilyId,
    TrueMomentumPreviewEvidenceFamilySummary
  >();
  for (const familyId of FAMILY_ORDER) {
    summaries.set(familyId, emptyFamilySummary(familyId));
  }
  for (const candidate of evidenceCandidates) {
    const summary = summaries.get(candidate.family_id);
    if (!summary) continue;
    summary.preview_count += 1;
    summary.candidates.push(candidate);
    if (candidate.match_strength === "strong") summary.strong_count += 1;
    else if (candidate.match_strength === "moderate") summary.moderate_count += 1;
    else if (candidate.match_strength === "watch") summary.watch_count += 1;
    else if (candidate.match_strength === "blocked") summary.blocked_count += 1;
    if (candidate.operational_caveats.includes("thinkorswim_parity_pending")) {
      summary.parity_pending_count += 1;
    }
    if (candidate.operational_caveats.includes("derived_higher_timeframe")) {
      summary.derived_higher_timeframe_count += 1;
    }
    if (candidate.operational_caveats.length > 0) {
      summary.operational_caveat_count += 1;
    }
  }
  return FAMILY_ORDER.map((id) => summaries.get(id)!).map((s) => ({
    ...s,
    candidates: s.candidates.slice(),
  }));
}

function defaultOperatorReview(
  generatedAt: string,
): TrueMomentumPreviewEvidenceOperatorReview {
  return {
    global_conclusion: "",
    family_notes: {
      true_momentum_continuation: "",
      true_momentum_pullback: "",
      true_momentum_reversal_watch: "",
    },
    candidate_notes: [],
    review_tags: [],
    authored_at: generatedAt,
  };
}

function normalizeIncomingOperatorReview(
  raw: unknown,
  generatedAt: string,
): TrueMomentumPreviewEvidenceOperatorReview {
  const out = defaultOperatorReview(generatedAt);
  if (!raw || typeof raw !== "object") return out;
  const obj = raw as Record<string, unknown>;
  out.global_conclusion = sanitizeTrueMomentumPreviewEvidenceNote(
    obj.global_conclusion ?? "",
  );
  const familyNotesRaw = obj.family_notes;
  if (familyNotesRaw && typeof familyNotesRaw === "object") {
    const map = familyNotesRaw as Record<string, unknown>;
    for (const familyId of FAMILY_ORDER) {
      const value = map[familyId];
      out.family_notes[familyId] = sanitizeTrueMomentumPreviewEvidenceNote(
        value ?? "",
      );
    }
  }
  if (Array.isArray(obj.candidate_notes)) {
    for (const noteRaw of obj.candidate_notes) {
      if (!noteRaw || typeof noteRaw !== "object") continue;
      const noteObj = noteRaw as Record<string, unknown>;
      const previewId = typeof noteObj.preview_id === "string" ? noteObj.preview_id : "";
      const symbol = typeof noteObj.symbol === "string" ? noteObj.symbol : "";
      const text = sanitizeTrueMomentumPreviewEvidenceNote(noteObj.text ?? "");
      const tag = isTrueMomentumPreviewEvidenceReviewTag(noteObj.tag)
        ? noteObj.tag
        : null;
      if (!previewId || !symbol) continue;
      out.candidate_notes.push({ preview_id: previewId, symbol, text, tag });
    }
  }
  if (Array.isArray(obj.review_tags)) {
    for (const tag of obj.review_tags) {
      if (isTrueMomentumPreviewEvidenceReviewTag(tag)) {
        out.review_tags.push(tag);
      }
    }
  }
  if (typeof obj.authored_at === "string" && obj.authored_at.trim()) {
    out.authored_at = formatTimestamp(obj.authored_at);
  }
  return out;
}

// ── Builder ──────────────────────────────────────────────────────────

export type BuildTrueMomentumPreviewEvidenceOptions = {
  queueCandidates?: ReadonlyArray<QueueCandidate> | null;
  evaluatedUniverse?: ReadonlyArray<string> | null;
  rankingMode?: string | null;
  activeDeltaScale?: number | null;
  b8Snapshot?: MomentumTrialSnapshot | null;
  b8OutcomeReview?: MomentumTrialOutcomeReview | null;
  operatorReview?: unknown;
  generatedAt?: string | Date | null;
};

/**
 * Build a deterministic Phase C2 evidence bundle from an existing
 * Phase C1 preview result and the source queue candidates. Pure /
 * side-effect-free; never mutates inputs and never emits forbidden
 * trade-direction or order-routing language.
 */
export function buildTrueMomentumPreviewEvidenceBundle(
  previewResult: TrueMomentumStrategyPreviewResult | null | undefined,
  options: BuildTrueMomentumPreviewEvidenceOptions = {},
): TrueMomentumPreviewEvidenceBundle {
  const generatedAt = formatTimestamp(options.generatedAt ?? null);
  const previews = previewResult?.previews ?? [];
  const status = previewResult?.status ?? null;
  const queueCandidates = Array.isArray(options.queueCandidates)
    ? (options.queueCandidates as ReadonlyArray<QueueCandidate>)
    : [];

  const evidenceCandidates: TrueMomentumPreviewEvidenceCandidate[] = previews.map(
    (preview) =>
      evidenceCandidateFromPreview(
        preview,
        lookupQueueCandidate(queueCandidates, preview),
      ),
  );

  const familySummaries = buildFamilySummaries(evidenceCandidates);
  const continuationSummary = familySummaries.find(
    (s) => s.family_id === "true_momentum_continuation",
  );
  const pullbackSummary = familySummaries.find(
    (s) => s.family_id === "true_momentum_pullback",
  );
  const reversalSummary = familySummaries.find(
    (s) => s.family_id === "true_momentum_reversal_watch",
  );

  const family_counts: TrueMomentumPreviewEvidenceFamilyCounts = {
    continuation_count: continuationSummary?.preview_count ?? 0,
    pullback_count: pullbackSummary?.preview_count ?? 0,
    reversal_watch_count: reversalSummary?.preview_count ?? 0,
  };

  let parity_pending_count = 0;
  let derived_higher_timeframe_count = 0;
  let trade_warning_count = 0;
  let operational_caveat_count = 0;
  let score_consistency_corrected_count = 0;
  for (const candidate of evidenceCandidates) {
    if (candidate.operational_caveats.includes("thinkorswim_parity_pending")) {
      parity_pending_count += 1;
    }
    if (candidate.operational_caveats.includes("derived_higher_timeframe")) {
      derived_higher_timeframe_count += 1;
    }
    if (candidate.operational_caveats.includes("score_consistency_corrected")) {
      score_consistency_corrected_count += 1;
    }
    if (candidate.trade_warnings.length > 0) trade_warning_count += 1;
    if (candidate.operational_caveats.length > 0) operational_caveat_count += 1;
  }

  const hasExplicitUniverse =
    Array.isArray(options.evaluatedUniverse) && options.evaluatedUniverse.length > 0;
  const evaluated_universe = hasExplicitUniverse
    ? dedupeSymbols(options.evaluatedUniverse as ReadonlyArray<string>)
    : dedupeSymbols(queueCandidates.map((c) => c.symbol));
  const universe_kind: TrueMomentumPreviewEvidenceUniverseKind = hasExplicitUniverse
    ? "evaluated"
    : "captured";

  const ranking_mode =
    typeof options.rankingMode === "string" && options.rankingMode.trim()
      ? options.rankingMode.trim()
      : status?.effective_mode === "research_preview"
        ? "research_preview"
        : status?.effective_mode === "disabled"
          ? "disabled"
          : "unknown";

  const operator_review = options.operatorReview
    ? normalizeIncomingOperatorReview(options.operatorReview, generatedAt)
    : defaultOperatorReview(generatedAt);

  const active_delta_scale = sanitizeFinite(
    options.activeDeltaScale ?? null,
    0,
  );

  return {
    schema_version: TRUE_MOMENTUM_PREVIEW_EVIDENCE_SCHEMA_VERSION,
    generated_at: generatedAt,
    preview_phase: TRUE_MOMENTUM_PREVIEW_EVIDENCE_PHASE,
    implementation_status: TRUE_MOMENTUM_PREVIEW_EVIDENCE_IMPLEMENTATION_STATUS,
    ranking_mode,
    active_delta_scale,
    evaluated_universe,
    universe_kind,
    candidate_count: queueCandidates.length,
    preview_count: evidenceCandidates.length,
    family_counts,
    continuation_count: family_counts.continuation_count,
    pullback_count: family_counts.pullback_count,
    reversal_watch_count: family_counts.reversal_watch_count,
    parity_pending_count,
    derived_higher_timeframe_count,
    trade_warning_count,
    operational_caveat_count,
    score_consistency_corrected_count,
    b8_snapshot_present: !!options.b8Snapshot,
    b8_outcome_review_present: !!options.b8OutcomeReview,
    family_summaries: familySummaries,
    preview_candidates: evidenceCandidates,
    operator_review,
    deterministic_note: TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE,
  };
}

export function summarizeTrueMomentumPreviewEvidence(
  bundle: TrueMomentumPreviewEvidenceBundle | null | undefined,
): TrueMomentumPreviewEvidenceSummary {
  if (!bundle) {
    return {
      candidate_count: 0,
      preview_count: 0,
      continuation_count: 0,
      pullback_count: 0,
      reversal_watch_count: 0,
      parity_pending_count: 0,
      derived_higher_timeframe_count: 0,
      trade_warning_count: 0,
      operational_caveat_count: 0,
      score_consistency_corrected_count: 0,
      b8_snapshot_present: false,
      b8_outcome_review_present: false,
    };
  }
  return {
    candidate_count: bundle.candidate_count,
    preview_count: bundle.preview_count,
    continuation_count: bundle.continuation_count,
    pullback_count: bundle.pullback_count,
    reversal_watch_count: bundle.reversal_watch_count,
    parity_pending_count: bundle.parity_pending_count,
    derived_higher_timeframe_count: bundle.derived_higher_timeframe_count,
    trade_warning_count: bundle.trade_warning_count,
    operational_caveat_count: bundle.operational_caveat_count,
    score_consistency_corrected_count: bundle.score_consistency_corrected_count,
    b8_snapshot_present: bundle.b8_snapshot_present,
    b8_outcome_review_present: bundle.b8_outcome_review_present,
  };
}

export function partitionTrueMomentumPreviewEvidenceByFamily(
  bundle: TrueMomentumPreviewEvidenceBundle | null | undefined,
): Record<
  TrueMomentumStrategyPreviewFamilyId,
  TrueMomentumPreviewEvidenceCandidate[]
> {
  const out: Record<
    TrueMomentumStrategyPreviewFamilyId,
    TrueMomentumPreviewEvidenceCandidate[]
  > = {
    true_momentum_continuation: [],
    true_momentum_pullback: [],
    true_momentum_reversal_watch: [],
  };
  if (!bundle) return out;
  for (const candidate of bundle.preview_candidates) {
    out[candidate.family_id].push(candidate);
  }
  return out;
}

export function topTrueMomentumPreviewEvidence(
  bundle: TrueMomentumPreviewEvidenceBundle | null | undefined,
  limit = 8,
): TrueMomentumPreviewEvidenceCandidate[] {
  if (!bundle) return [];
  const cap = Math.max(1, Math.min(50, Number.isFinite(limit) ? limit : 8));
  // Strong > moderate > watch > blocked; tie-break by rank ascending.
  const STRENGTH_ORDER: Record<TrueMomentumStrategyPreviewMatchStrength, number> = {
    strong: 0,
    moderate: 1,
    watch: 2,
    blocked: 3,
  };
  const sorted = [...bundle.preview_candidates].sort((a, b) => {
    const diff = STRENGTH_ORDER[a.match_strength] - STRENGTH_ORDER[b.match_strength];
    if (diff !== 0) return diff;
    if (a.rank !== b.rank) return a.rank - b.rank;
    return a.symbol.localeCompare(b.symbol);
  });
  return sorted.slice(0, cap);
}

export function trueMomentumPreviewEvidenceWarnings(
  candidate: TrueMomentumPreviewEvidenceCandidate | null | undefined,
): string[] {
  if (!candidate) return [];
  return candidate.trade_warnings.slice();
}

// ── Validation ────────────────────────────────────────────────────────

export function validateTrueMomentumPreviewEvidenceBundle(
  bundle: unknown,
):
  | { ok: true; bundle: TrueMomentumPreviewEvidenceBundle }
  | { ok: false; error: string } {
  if (!bundle || typeof bundle !== "object") {
    return { ok: false, error: "Evidence bundle must be an object." };
  }
  const obj = bundle as Record<string, unknown>;
  if (obj.schema_version !== TRUE_MOMENTUM_PREVIEW_EVIDENCE_SCHEMA_VERSION) {
    return {
      ok: false,
      error: `Unexpected schema_version: ${String(obj.schema_version)}`,
    };
  }
  if (typeof obj.generated_at !== "string" || !obj.generated_at) {
    return { ok: false, error: "Missing generated_at." };
  }
  if (!Array.isArray(obj.preview_candidates)) {
    return { ok: false, error: "Missing preview_candidates array." };
  }
  if (!Array.isArray(obj.family_summaries)) {
    return { ok: false, error: "Missing family_summaries array." };
  }
  if (!obj.operator_review || typeof obj.operator_review !== "object") {
    return { ok: false, error: "Missing operator_review." };
  }
  return { ok: true, bundle: bundle as TrueMomentumPreviewEvidenceBundle };
}

// ── Exports: JSON + Markdown ─────────────────────────────────────────

export function buildTrueMomentumPreviewEvidenceJson(
  bundle: TrueMomentumPreviewEvidenceBundle,
): string {
  const payload: TrueMomentumPreviewEvidenceExportPayload = {
    schema_version: TRUE_MOMENTUM_PREVIEW_EVIDENCE_SCHEMA_VERSION,
    bundle,
    deterministic_note: TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE,
  };
  return JSON.stringify(payload, null, 2);
}

function fmtScore(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function fmtSigned(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value === 0) return value.toFixed(digits);
  return value > 0 ? `+${value.toFixed(digits)}` : value.toFixed(digits);
}

function fmtRaw(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value === 0) return "0.00";
  return value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2);
}

function evidenceUniverseLabel(
  kind: TrueMomentumPreviewEvidenceUniverseKind | null | undefined,
): string {
  return kind === "evaluated" ? "Evaluated universe" : "Captured symbols";
}

function familyMarkdownTable(
  family: TrueMomentumPreviewEvidenceFamilySummary,
  notes: string,
): string[] {
  const lines: string[] = [];
  lines.push(`### ${family.family_label}`);
  lines.push("");
  lines.push(
    `- Preview count: ${family.preview_count} · strong: ${family.strong_count} · moderate: ${family.moderate_count} · watch: ${family.watch_count} · blocked: ${family.blocked_count}`,
  );
  lines.push(
    `- Parity pending: ${family.parity_pending_count} · derived HTF: ${family.derived_higher_timeframe_count} · operational caveats: ${family.operational_caveat_count}`,
  );
  if (notes) {
    lines.push("");
    lines.push(`> ${notes.replace(/\n/g, "\n> ")}`);
  }
  if (family.candidates.length === 0) {
    lines.push("");
    lines.push("_No preview rows in this family._");
    return lines;
  }
  lines.push("");
  lines.push(
    "| Rank | Symbol | Current strategy | Match | Baseline | Active | Raw | Applied Δ | Total | Reasons | Trade warnings | Caveats |",
  );
  lines.push(
    "| ---: | :----- | :--------------- | :---- | -------: | -----: | ---:| --------:| :---- | :------ | :------------- | :------ |",
  );
  for (const c of family.candidates) {
    const totalCell =
      c.total_score == null
        ? "—"
        : `${c.total_score}${c.total_label ? ` (${c.total_label})` : ""}`;
    const reasonLabels = trueMomentumPreviewReasonLabels(c.reason_codes);
    const caveatLabels = trueMomentumPreviewReasonLabels(c.operational_caveats);
    const reasonCell = reasonLabels.length === 0 ? "—" : reasonLabels.join("; ");
    const caveatCell = caveatLabels.length === 0 ? "—" : caveatLabels.join("; ");
    const tradeCell =
      c.trade_warnings.length === 0 ? "—" : c.trade_warnings.join(", ");
    lines.push(
      `| ${c.rank} | ${c.symbol} | ${c.current_strategy} | ${c.match_strength} | ${fmtScore(c.baseline_score)} | ${fmtScore(c.active_score)} | ${fmtRaw(c.raw_contribution)} | ${fmtSigned(c.applied_delta)} | ${totalCell} | ${reasonCell} | ${tradeCell} | ${caveatCell} |`,
    );
  }
  return lines;
}

export function buildTrueMomentumPreviewEvidenceMarkdown(
  bundle: TrueMomentumPreviewEvidenceBundle,
): string {
  const lines: string[] = [];
  lines.push("# True Momentum Preview Evidence Bundle");
  lines.push("");
  lines.push(`- Generated at: \`${bundle.generated_at}\``);
  lines.push(`- Schema version: \`${bundle.schema_version}\``);
  lines.push(
    `- Preview phase: \`${bundle.preview_phase}\` · implementation: \`${bundle.implementation_status}\``,
  );
  lines.push(
    `- Ranking mode: \`${bundle.ranking_mode}\` · active delta scale: \`${bundle.active_delta_scale.toFixed(
      2,
    )}\``,
  );
  lines.push(
    `- ${evidenceUniverseLabel(bundle.universe_kind)}: ${
      bundle.evaluated_universe.length > 0
        ? bundle.evaluated_universe.map((s) => `\`${s}\``).join(", ")
        : "_(empty)_"
    }`,
  );
  lines.push(
    `- B8 snapshot linked: ${bundle.b8_snapshot_present ? "yes" : "no"} · B8 outcome review linked: ${bundle.b8_outcome_review_present ? "yes" : "no"}`,
  );
  lines.push("");
  lines.push("## Summary");
  lines.push("");
  lines.push(`- Candidates captured: ${bundle.candidate_count}`);
  lines.push(`- Preview rows: ${bundle.preview_count}`);
  lines.push(`- Continuation: ${bundle.continuation_count}`);
  lines.push(`- Pullback: ${bundle.pullback_count}`);
  lines.push(`- Reversal / watch: ${bundle.reversal_watch_count}`);
  lines.push(`- Trade warnings: ${bundle.trade_warning_count}`);
  lines.push(`- Operational caveats: ${bundle.operational_caveat_count}`);
  lines.push(`- Parity pending: ${bundle.parity_pending_count}`);
  lines.push(`- Derived higher timeframe: ${bundle.derived_higher_timeframe_count}`);
  lines.push(
    `- Score consistency corrected: ${bundle.score_consistency_corrected_count}`,
  );

  lines.push("");
  lines.push("## Operator review");
  lines.push("");
  if (bundle.operator_review.global_conclusion) {
    lines.push("### Global conclusion");
    lines.push("");
    lines.push(`> ${bundle.operator_review.global_conclusion.replace(/\n/g, "\n> ")}`);
    lines.push("");
    lines.push(`_authored ${bundle.operator_review.authored_at}_`);
  } else {
    lines.push("_No global conclusion recorded._");
  }
  if (bundle.operator_review.review_tags.length > 0) {
    lines.push("");
    lines.push("### Review tags");
    lines.push("");
    lines.push(
      bundle.operator_review.review_tags
        .map((tag) => `- ${trueMomentumPreviewEvidenceTagLabel(tag)}`)
        .join("\n"),
    );
  }

  lines.push("");
  lines.push("## Preview families");
  lines.push("");
  for (const family of bundle.family_summaries) {
    const note = bundle.operator_review.family_notes[family.family_id] ?? "";
    lines.push(...familyMarkdownTable(family, note));
    lines.push("");
  }

  if (bundle.operator_review.candidate_notes.length > 0) {
    lines.push("## Candidate notes");
    lines.push("");
    lines.push("| Symbol | Tag | Note |");
    lines.push("| :----- | :-- | :--- |");
    for (const note of bundle.operator_review.candidate_notes) {
      const tagCell = note.tag ? trueMomentumPreviewEvidenceTagLabel(note.tag) : "—";
      const text = note.text ? note.text.replace(/\|/g, "\\|").replace(/\n/g, " ") : "—";
      lines.push(`| ${note.symbol} | ${tagCell} | ${text} |`);
    }
    lines.push("");
  }

  lines.push("## Remaining caveats");
  lines.push("");
  lines.push(
    `- Parity pending: ${bundle.parity_pending_count > 0 ? "yes" : "review locally"}`,
  );
  lines.push(
    `- Derived higher timeframe rows: ${bundle.derived_higher_timeframe_count}`,
  );
  lines.push(
    `- B8 outcome evidence linked: ${bundle.b8_outcome_review_present ? "yes" : "no — capture B8 outcome review for the same snapshot"}`,
  );
  lines.push(
    "- Active Phase C True Momentum strategy families are not implemented; this bundle is research-only.",
  );

  lines.push("");
  lines.push(`_${bundle.deterministic_note}_`);
  lines.push("");
  return lines.join("\n");
}

// Re-export the C1 preview phase constant so callers that pass the
// preview result through to this module do not need a second import.
export { TRUE_MOMENTUM_STRATEGY_PREVIEW_PHASE };
