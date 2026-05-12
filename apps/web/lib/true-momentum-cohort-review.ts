// Phase C3 — True Momentum research cohort review.
//
// Pure helpers that archive Phase C2 preview evidence bundles, summarize
// outcomes across sessions / families, and emit a research-only
// activation-readiness report. Local/export-only — no backend write,
// no DB row, no LLM call, no queue candidates, no approval / promote /
// route / size / order behavior change.

import type {
  TrueMomentumPreviewEvidenceBundle,
  TrueMomentumPreviewEvidenceCandidate,
  TrueMomentumPreviewEvidenceOutcomeSummary,
  TrueMomentumPreviewEvidenceReviewTag,
  TrueMomentumPreviewEvidenceSnapshotLinkStatus,
  TrueMomentumPreviewEvidenceOutcomeLinkStatus,
} from "@/lib/true-momentum-preview-evidence";
import type { TrueMomentumStrategyPreviewFamilyId } from "@/lib/true-momentum-strategy-preview";
import { familyPreviewLabel } from "@/lib/true-momentum-strategy-preview";

export const TRUE_MOMENTUM_COHORT_ARCHIVE_SCHEMA_VERSION = "phase_c3.v1";
export const TRUE_MOMENTUM_COHORT_REPORT_SCHEMA_VERSION = "phase_c3.v1";
export const TRUE_MOMENTUM_COHORT_STORAGE_KEY =
  "macmarket.trueMomentumCohortReview.archive";

export const TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE =
  "True Momentum cohort review is research-only. It does not generate queue candidates, approve, reject, size, or route trades.";

export type TrueMomentumCohortReadinessStatus =
  | "insufficient_evidence"
  | "parity_blocked"
  | "promising_research"
  | "mixed_research"
  | "needs_operator_review"
  | "not_recommended_for_activation";

const READINESS_LABELS: Record<TrueMomentumCohortReadinessStatus, string> = {
  insufficient_evidence: "Insufficient evidence",
  parity_blocked: "Parity blocked",
  promising_research: "Promising research",
  mixed_research: "Mixed research",
  needs_operator_review: "Needs operator review",
  not_recommended_for_activation: "Not recommended for activation",
};

const READINESS_TONES: Record<
  TrueMomentumCohortReadinessStatus,
  "good" | "warn" | "bad" | "neutral"
> = {
  insufficient_evidence: "neutral",
  parity_blocked: "warn",
  promising_research: "good",
  mixed_research: "warn",
  needs_operator_review: "warn",
  not_recommended_for_activation: "bad",
};

export function trueMomentumCohortReadinessLabel(
  status: TrueMomentumCohortReadinessStatus | string | null | undefined,
): string {
  if (status == null) return READINESS_LABELS.insufficient_evidence;
  if (typeof status === "string" && status in READINESS_LABELS) {
    return READINESS_LABELS[status as TrueMomentumCohortReadinessStatus];
  }
  return READINESS_LABELS.insufficient_evidence;
}

export function trueMomentumCohortReadinessTone(
  status: TrueMomentumCohortReadinessStatus | string | null | undefined,
): "good" | "warn" | "bad" | "neutral" {
  if (status == null) return "neutral";
  if (typeof status === "string" && status in READINESS_TONES) {
    return READINESS_TONES[status as TrueMomentumCohortReadinessStatus];
  }
  return "neutral";
}

// ── Note sanitization ────────────────────────────────────────────────

const MAX_NOTE_LENGTH = 1200;
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

export function sanitizeTrueMomentumCohortNote(note: unknown): string {
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

// ── Types ────────────────────────────────────────────────────────────

export type TrueMomentumCohortRecord = {
  record_id: string;
  captured_at: string;
  source_bundle_generated_at: string;
  queue_signature: string;
  evaluated_universe: string[];
  ranking_mode: string;
  active_delta_scale: number;
  preview_count: number;
  family_counts: {
    continuation_count: number;
    pullback_count: number;
    reversal_watch_count: number;
  };
  b8_snapshot_link_status: TrueMomentumPreviewEvidenceSnapshotLinkStatus;
  b8_outcome_review_link_status: TrueMomentumPreviewEvidenceOutcomeLinkStatus;
  b8_outcome_summary: TrueMomentumPreviewEvidenceOutcomeSummary | null;
  parity_pending_count: number;
  derived_higher_timeframe_count: number;
  score_consistency_corrected_count: number;
  continuation_candidates: TrueMomentumPreviewEvidenceCandidate[];
  pullback_candidates: TrueMomentumPreviewEvidenceCandidate[];
  reversal_watch_candidates: TrueMomentumPreviewEvidenceCandidate[];
  operator_review: {
    global_conclusion: string;
    review_tags: TrueMomentumPreviewEvidenceReviewTag[];
  };
  deterministic_note: typeof TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE;
};

export type TrueMomentumCohortArchive = {
  schema_version: typeof TRUE_MOMENTUM_COHORT_ARCHIVE_SCHEMA_VERSION;
  created_at: string;
  updated_at: string;
  records: TrueMomentumCohortRecord[];
};

export type TrueMomentumCohortOutcomeSummary = {
  worked_count: number;
  missed_count: number;
  too_aggressive_count: number;
  good_warning_count: number;
  false_warning_count: number;
  watchlist_only_count: number;
  needs_tos_parity_check_count: number;
  ignored_count: number;
  unclear_count: number;
  total_outcome_candidate_count: number;
};

export type TrueMomentumFamilyCohortSummary = {
  family_id: TrueMomentumStrategyPreviewFamilyId;
  family_label: string;
  record_count: number;
  preview_count: number;
  strong_count: number;
  moderate_count: number;
  watch_count: number;
  blocked_count: number;
  parity_pending_count: number;
};

export type TrueMomentumCohortArchiveSummary = {
  record_count: number;
  total_preview_count: number;
  continuation_count: number;
  pullback_count: number;
  reversal_watch_count: number;
  parity_pending_records: number;
  records_with_outcome_review: number;
  outcome_counts: TrueMomentumCohortOutcomeSummary;
  family_summaries: TrueMomentumFamilyCohortSummary[];
};

export type TrueMomentumCohortReviewReport = {
  schema_version: typeof TRUE_MOMENTUM_COHORT_REPORT_SCHEMA_VERSION;
  generated_at: string;
  archive: TrueMomentumCohortArchive;
  summary: TrueMomentumCohortArchiveSummary;
  readiness: TrueMomentumCohortReadinessStatus;
  readiness_caveats: string[];
  deterministic_note: typeof TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE;
};

export type TrueMomentumCohortExportPayload = {
  schema_version: typeof TRUE_MOMENTUM_COHORT_REPORT_SCHEMA_VERSION;
  report: TrueMomentumCohortReviewReport;
  archive: TrueMomentumCohortArchive;
  deterministic_note: typeof TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE;
};

// ── Helpers ──────────────────────────────────────────────────────────

function nowIso(): string {
  return new Date().toISOString();
}

function sanitizeFinite(value: unknown, fallback = 0): number {
  if (value == null) return fallback;
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num) || !Number.isFinite(num)) return fallback;
  return num;
}

function safeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === "string");
}

function safeFamilyId(
  value: unknown,
): TrueMomentumStrategyPreviewFamilyId | null {
  if (
    value === "true_momentum_continuation" ||
    value === "true_momentum_pullback" ||
    value === "true_momentum_reversal_watch"
  ) {
    return value;
  }
  return null;
}

function safeCandidate(value: unknown): TrueMomentumPreviewEvidenceCandidate | null {
  if (!value || typeof value !== "object") return null;
  const obj = value as Record<string, unknown>;
  const familyId = safeFamilyId(obj.family_id);
  if (!familyId) return null;
  return value as TrueMomentumPreviewEvidenceCandidate;
}

export function emptyCohortArchive(): TrueMomentumCohortArchive {
  const now = nowIso();
  return {
    schema_version: TRUE_MOMENTUM_COHORT_ARCHIVE_SCHEMA_VERSION,
    created_at: now,
    updated_at: now,
    records: [],
  };
}

// ── Build cohort record from a C2 bundle ─────────────────────────────

export type BuildTrueMomentumCohortRecordOptions = {
  capturedAt?: string | Date | null;
  /** Override the deterministic record id. Default:
   *  ``${queue_signature}::${source_bundle_generated_at}``. */
  recordId?: string | null;
  queueSignature?: string | null;
};

function deriveQueueSignatureFromBundle(
  bundle: TrueMomentumPreviewEvidenceBundle,
): string {
  // The C2 bundle carries the evaluated universe symbols + universe
  // kind + the preview-candidate rows (rank/symbol/strategy). Build a
  // signature that matches the shape used by
  // ``computeMomentumQueueSignature`` in C2.1.
  const rows = bundle.preview_candidates.map((c) => ({
    rank: c.rank,
    symbol: c.symbol,
    strategy: c.current_strategy,
  }));
  if (rows.length === 0) return "empty";
  const parts: string[] = [];
  for (const row of rows) {
    parts.push(`${row.rank}::${row.symbol}::${row.strategy}`);
  }
  return parts.sort().join("|");
}

export function buildTrueMomentumCohortRecord(
  bundle: TrueMomentumPreviewEvidenceBundle | null | undefined,
  options: BuildTrueMomentumCohortRecordOptions = {},
): TrueMomentumCohortRecord | null {
  if (!bundle || typeof bundle !== "object") return null;
  const capturedAt =
    typeof options.capturedAt === "string"
      ? options.capturedAt
      : options.capturedAt instanceof Date
        ? options.capturedAt.toISOString()
        : nowIso();
  const queueSignature =
    typeof options.queueSignature === "string" && options.queueSignature.trim()
      ? options.queueSignature
      : deriveQueueSignatureFromBundle(bundle);
  const recordId =
    typeof options.recordId === "string" && options.recordId.trim()
      ? options.recordId
      : `${queueSignature}::${bundle.generated_at}`;
  return {
    record_id: recordId,
    captured_at: capturedAt,
    source_bundle_generated_at: bundle.generated_at,
    queue_signature: queueSignature,
    evaluated_universe: safeStringList(bundle.evaluated_universe).slice(),
    ranking_mode: typeof bundle.ranking_mode === "string" ? bundle.ranking_mode : "unknown",
    active_delta_scale: sanitizeFinite(bundle.active_delta_scale, 0),
    preview_count: sanitizeFinite(bundle.preview_count, 0),
    family_counts: {
      continuation_count: sanitizeFinite(bundle.continuation_count, 0),
      pullback_count: sanitizeFinite(bundle.pullback_count, 0),
      reversal_watch_count: sanitizeFinite(bundle.reversal_watch_count, 0),
    },
    b8_snapshot_link_status: bundle.b8_snapshot_link_status,
    b8_outcome_review_link_status: bundle.b8_outcome_review_link_status,
    b8_outcome_summary: bundle.b8_outcome_summary
      ? { ...bundle.b8_outcome_summary }
      : null,
    parity_pending_count: sanitizeFinite(bundle.parity_pending_count, 0),
    derived_higher_timeframe_count: sanitizeFinite(
      bundle.derived_higher_timeframe_count,
      0,
    ),
    score_consistency_corrected_count: sanitizeFinite(
      bundle.score_consistency_corrected_count,
      0,
    ),
    continuation_candidates: bundle.preview_candidates
      .filter((c) => c.family_id === "true_momentum_continuation")
      .map((c) => ({ ...c })),
    pullback_candidates: bundle.preview_candidates
      .filter((c) => c.family_id === "true_momentum_pullback")
      .map((c) => ({ ...c })),
    reversal_watch_candidates: bundle.preview_candidates
      .filter((c) => c.family_id === "true_momentum_reversal_watch")
      .map((c) => ({ ...c })),
    operator_review: {
      global_conclusion: sanitizeTrueMomentumCohortNote(
        bundle.operator_review?.global_conclusion ?? "",
      ),
      review_tags: Array.isArray(bundle.operator_review?.review_tags)
        ? bundle.operator_review.review_tags.slice()
        : [],
    },
    deterministic_note: TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE,
  };
}

// ── Archive mutators (immutable) ─────────────────────────────────────

function bumpArchiveTimestamp(
  archive: TrueMomentumCohortArchive,
  records: TrueMomentumCohortRecord[],
): TrueMomentumCohortArchive {
  return {
    schema_version: TRUE_MOMENTUM_COHORT_ARCHIVE_SCHEMA_VERSION,
    created_at: archive.created_at,
    updated_at: nowIso(),
    records,
  };
}

export function addTrueMomentumCohortRecord(
  archive: TrueMomentumCohortArchive | null | undefined,
  record: TrueMomentumCohortRecord,
): TrueMomentumCohortArchive {
  const base = archive ?? emptyCohortArchive();
  if (base.records.some((r) => r.record_id === record.record_id)) return base;
  return bumpArchiveTimestamp(base, [...base.records, { ...record }]);
}

export function replaceTrueMomentumCohortRecord(
  archive: TrueMomentumCohortArchive | null | undefined,
  record: TrueMomentumCohortRecord,
): TrueMomentumCohortArchive {
  const base = archive ?? emptyCohortArchive();
  const records = base.records.map((r) =>
    r.record_id === record.record_id ? { ...record } : r,
  );
  if (!records.some((r) => r.record_id === record.record_id)) {
    records.push({ ...record });
  }
  return bumpArchiveTimestamp(base, records);
}

export function removeTrueMomentumCohortRecord(
  archive: TrueMomentumCohortArchive | null | undefined,
  recordId: string,
): TrueMomentumCohortArchive {
  const base = archive ?? emptyCohortArchive();
  const records = base.records.filter((r) => r.record_id !== recordId);
  return bumpArchiveTimestamp(base, records);
}

export function cohortArchiveContainsRecordId(
  archive: TrueMomentumCohortArchive | null | undefined,
  recordId: string,
): boolean {
  if (!archive) return false;
  return archive.records.some((r) => r.record_id === recordId);
}

// ── Summaries ─────────────────────────────────────────────────────────

const FAMILY_ORDER: ReadonlyArray<TrueMomentumStrategyPreviewFamilyId> = [
  "true_momentum_continuation",
  "true_momentum_pullback",
  "true_momentum_reversal_watch",
];

function emptyOutcomeSummary(): TrueMomentumCohortOutcomeSummary {
  return {
    worked_count: 0,
    missed_count: 0,
    too_aggressive_count: 0,
    good_warning_count: 0,
    false_warning_count: 0,
    watchlist_only_count: 0,
    needs_tos_parity_check_count: 0,
    ignored_count: 0,
    unclear_count: 0,
    total_outcome_candidate_count: 0,
  };
}

export function summarizeTrueMomentumFamilyCohort(
  archive: TrueMomentumCohortArchive | null | undefined,
  familyId: TrueMomentumStrategyPreviewFamilyId,
): TrueMomentumFamilyCohortSummary {
  const summary: TrueMomentumFamilyCohortSummary = {
    family_id: familyId,
    family_label: familyPreviewLabel(familyId),
    record_count: 0,
    preview_count: 0,
    strong_count: 0,
    moderate_count: 0,
    watch_count: 0,
    blocked_count: 0,
    parity_pending_count: 0,
  };
  if (!archive) return summary;
  for (const record of archive.records) {
    const bucket =
      familyId === "true_momentum_continuation"
        ? record.continuation_candidates
        : familyId === "true_momentum_pullback"
          ? record.pullback_candidates
          : record.reversal_watch_candidates;
    if (!Array.isArray(bucket)) continue;
    if (bucket.length > 0) summary.record_count += 1;
    for (const candidate of bucket) {
      summary.preview_count += 1;
      if (candidate.match_strength === "strong") summary.strong_count += 1;
      else if (candidate.match_strength === "moderate") summary.moderate_count += 1;
      else if (candidate.match_strength === "watch") summary.watch_count += 1;
      else if (candidate.match_strength === "blocked") summary.blocked_count += 1;
      if (
        Array.isArray(candidate.operational_caveats) &&
        candidate.operational_caveats.includes("thinkorswim_parity_pending")
      ) {
        summary.parity_pending_count += 1;
      }
    }
  }
  return summary;
}

export function summarizeTrueMomentumCohortArchive(
  archive: TrueMomentumCohortArchive | null | undefined,
): TrueMomentumCohortArchiveSummary {
  const summary: TrueMomentumCohortArchiveSummary = {
    record_count: 0,
    total_preview_count: 0,
    continuation_count: 0,
    pullback_count: 0,
    reversal_watch_count: 0,
    parity_pending_records: 0,
    records_with_outcome_review: 0,
    outcome_counts: emptyOutcomeSummary(),
    family_summaries: FAMILY_ORDER.map((id) =>
      summarizeTrueMomentumFamilyCohort(archive, id),
    ),
  };
  if (!archive) return summary;
  summary.record_count = archive.records.length;
  for (const record of archive.records) {
    summary.total_preview_count += sanitizeFinite(record.preview_count, 0);
    summary.continuation_count += sanitizeFinite(
      record.family_counts?.continuation_count,
      0,
    );
    summary.pullback_count += sanitizeFinite(
      record.family_counts?.pullback_count,
      0,
    );
    summary.reversal_watch_count += sanitizeFinite(
      record.family_counts?.reversal_watch_count,
      0,
    );
    if (sanitizeFinite(record.parity_pending_count, 0) > 0) {
      summary.parity_pending_records += 1;
    }
    if (
      record.b8_outcome_review_link_status === "linked" ||
      record.b8_outcome_review_link_status === "partial"
    ) {
      summary.records_with_outcome_review += 1;
    }
    const o = record.b8_outcome_summary;
    if (o) {
      summary.outcome_counts.worked_count += sanitizeFinite(o.worked_count, 0);
      summary.outcome_counts.missed_count += sanitizeFinite(o.missed_count, 0);
      summary.outcome_counts.too_aggressive_count += sanitizeFinite(
        o.too_aggressive_count,
        0,
      );
      summary.outcome_counts.good_warning_count += sanitizeFinite(
        o.good_warning_count,
        0,
      );
      summary.outcome_counts.false_warning_count += sanitizeFinite(
        o.false_warning_count,
        0,
      );
      summary.outcome_counts.watchlist_only_count += sanitizeFinite(
        o.watchlist_only_count,
        0,
      );
      summary.outcome_counts.needs_tos_parity_check_count += sanitizeFinite(
        o.needs_tos_parity_check_count,
        0,
      );
      summary.outcome_counts.ignored_count += sanitizeFinite(o.ignored_count, 0);
      summary.outcome_counts.unclear_count += sanitizeFinite(o.unclear_count, 0);
      summary.outcome_counts.total_outcome_candidate_count += sanitizeFinite(
        o.candidate_count,
        0,
      );
    }
  }
  return summary;
}

// ── Readiness classifier ─────────────────────────────────────────────

export function classifyTrueMomentumCohortReadiness(
  summary: TrueMomentumCohortArchiveSummary | null | undefined,
): { status: TrueMomentumCohortReadinessStatus; caveats: string[] } {
  const caveats: string[] = [];
  if (!summary || summary.record_count === 0) {
    return { status: "insufficient_evidence", caveats };
  }
  // Parity pending across most/all records → parity_blocked.
  if (
    summary.parity_pending_records > 0 &&
    summary.parity_pending_records >= Math.ceil(summary.record_count * 0.5)
  ) {
    caveats.push(
      "Thinkorswim parity is pending across at least half of the archived records.",
    );
    return { status: "parity_blocked", caveats };
  }
  if (summary.record_count < 3) {
    caveats.push("Fewer than 3 archived sessions — keep collecting evidence.");
    return { status: "insufficient_evidence", caveats };
  }
  const outcomes = summary.outcome_counts;
  const tagged =
    outcomes.total_outcome_candidate_count - outcomes.unclear_count;
  if (outcomes.total_outcome_candidate_count === 0 || tagged === 0) {
    caveats.push(
      "No tagged B8 outcomes yet — every archived candidate is still unclear.",
    );
    return { status: "insufficient_evidence", caveats };
  }
  const positive =
    outcomes.worked_count + outcomes.good_warning_count;
  const negative =
    outcomes.missed_count +
    outcomes.too_aggressive_count +
    outcomes.false_warning_count;
  if (negative > positive && negative >= positive * 2) {
    caveats.push(
      "Negative outcomes outnumber positive outcomes ≥ 2× across archived records.",
    );
    return { status: "not_recommended_for_activation", caveats };
  }
  if (outcomes.needs_tos_parity_check_count > 0) {
    caveats.push(
      "At least one archived record flagged needs_tos_parity_check.",
    );
  }
  if (negative >= positive) {
    return { status: "needs_operator_review", caveats };
  }
  if (positive >= negative + 2 && tagged >= 5) {
    return { status: "promising_research", caveats };
  }
  return { status: "mixed_research", caveats };
}

// ── Report ────────────────────────────────────────────────────────────

export function buildTrueMomentumCohortReviewReport(
  archive: TrueMomentumCohortArchive | null | undefined,
): TrueMomentumCohortReviewReport {
  const safeArchive: TrueMomentumCohortArchive = archive ?? emptyCohortArchive();
  const summary = summarizeTrueMomentumCohortArchive(safeArchive);
  const { status, caveats } = classifyTrueMomentumCohortReadiness(summary);
  return {
    schema_version: TRUE_MOMENTUM_COHORT_REPORT_SCHEMA_VERSION,
    generated_at: nowIso(),
    archive: safeArchive,
    summary,
    readiness: status,
    readiness_caveats: caveats,
    deterministic_note: TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE,
  };
}

// ── Validation ────────────────────────────────────────────────────────

export function validateTrueMomentumCohortArchive(
  archive: unknown,
):
  | { ok: true; archive: TrueMomentumCohortArchive }
  | { ok: false; error: string } {
  if (!archive || typeof archive !== "object") {
    return { ok: false, error: "Archive must be an object." };
  }
  const obj = archive as Record<string, unknown>;
  if (obj.schema_version !== TRUE_MOMENTUM_COHORT_ARCHIVE_SCHEMA_VERSION) {
    return {
      ok: false,
      error: `Unexpected schema_version: ${String(obj.schema_version)}`,
    };
  }
  if (!Array.isArray(obj.records)) {
    return { ok: false, error: "Missing records array." };
  }
  if (typeof obj.created_at !== "string" || !obj.created_at) {
    return { ok: false, error: "Missing created_at." };
  }
  return { ok: true, archive: archive as TrueMomentumCohortArchive };
}

// ── Exports ────────────────────────────────────────────────────────────

export function buildTrueMomentumCohortJson(
  report: TrueMomentumCohortReviewReport,
): string {
  const payload: TrueMomentumCohortExportPayload = {
    schema_version: TRUE_MOMENTUM_COHORT_REPORT_SCHEMA_VERSION,
    report,
    archive: report.archive,
    deterministic_note: TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE,
  };
  return JSON.stringify(payload, null, 2);
}

export function buildTrueMomentumCohortMarkdown(
  report: TrueMomentumCohortReviewReport,
): string {
  const lines: string[] = [];
  const summary = report.summary;
  lines.push("# True Momentum Cohort Review (Phase C3)");
  lines.push("");
  lines.push(`- Generated at: \`${report.generated_at}\``);
  lines.push(`- Schema version: \`${report.schema_version}\``);
  lines.push(`- Archived sessions: ${summary.record_count}`);
  lines.push(`- Readiness: \`${report.readiness}\` — ${trueMomentumCohortReadinessLabel(report.readiness)}`);
  if (report.readiness_caveats.length > 0) {
    for (const caveat of report.readiness_caveats) {
      lines.push(`  - ${caveat}`);
    }
  }
  lines.push("");
  lines.push("## Archive summary");
  lines.push("");
  lines.push(`- Total preview rows: ${summary.total_preview_count}`);
  lines.push(`- Continuation rows: ${summary.continuation_count}`);
  lines.push(`- Pullback rows: ${summary.pullback_count}`);
  lines.push(`- Reversal / watch rows: ${summary.reversal_watch_count}`);
  lines.push(`- Parity-pending records: ${summary.parity_pending_records}`);
  lines.push(`- Records with linked B8 outcome review: ${summary.records_with_outcome_review}`);

  const o = summary.outcome_counts;
  lines.push("");
  lines.push("## Outcome counts (across archived B8 reviews)");
  lines.push("");
  lines.push(`- Tagged candidates: ${o.total_outcome_candidate_count - o.unclear_count} / ${o.total_outcome_candidate_count}`);
  lines.push(`- Worked: ${o.worked_count}`);
  lines.push(`- Missed: ${o.missed_count}`);
  lines.push(`- Too aggressive: ${o.too_aggressive_count}`);
  lines.push(`- Good warnings: ${o.good_warning_count}`);
  lines.push(`- False warnings: ${o.false_warning_count}`);
  lines.push(`- Watchlist only: ${o.watchlist_only_count}`);
  lines.push(`- Needs ToS parity: ${o.needs_tos_parity_check_count}`);
  lines.push(`- Ignored: ${o.ignored_count}`);
  lines.push(`- Unclear: ${o.unclear_count}`);

  lines.push("");
  lines.push("## Family summaries");
  lines.push("");
  for (const family of summary.family_summaries) {
    lines.push(
      `- ${family.family_label}: ${family.preview_count} previews across ${family.record_count} records (strong ${family.strong_count} / moderate ${family.moderate_count} / watch ${family.watch_count} / blocked ${family.blocked_count}, parity pending ${family.parity_pending_count})`,
    );
  }

  lines.push("");
  lines.push("## Archived records");
  lines.push("");
  if (report.archive.records.length === 0) {
    lines.push("_No archived sessions yet._");
  } else {
    lines.push(
      "| Captured at | Universe (count) | Preview rows | B8 snapshot | B8 outcome review | Parity pending | Readiness caveats |",
    );
    lines.push(
      "| :---------- | :--------------- | -----------: | :---------- | :---------------- | -------------: | :---------------- |",
    );
    for (const record of report.archive.records) {
      const universeCell = `${record.evaluated_universe.length}`;
      const outcomeLabel = record.b8_outcome_summary
        ? `${record.b8_outcome_review_link_status} (worked ${record.b8_outcome_summary.worked_count} / unclear ${record.b8_outcome_summary.unclear_count})`
        : record.b8_outcome_review_link_status;
      lines.push(
        `| ${record.captured_at} | ${universeCell} | ${record.preview_count} | ${record.b8_snapshot_link_status} | ${outcomeLabel} | ${record.parity_pending_count} | ${record.operator_review.review_tags.join(", ") || "—"} |`,
      );
    }
  }

  lines.push("");
  lines.push("## Pending prerequisites for any active Phase C");
  lines.push("");
  lines.push("- Accumulated B8 outcome evidence corpus.");
  lines.push("- Real Thinkorswim fixture parity.");
  lines.push("- Operator authorization before any active Phase C.");

  lines.push("");
  lines.push(`_${TRUE_MOMENTUM_COHORT_DETERMINISTIC_NOTE}_`);
  lines.push("");
  return lines.join("\n");
}

// ── localStorage round-trip ──────────────────────────────────────────

export function readTrueMomentumCohortArchiveFromStorage():
  | TrueMomentumCohortArchive
  | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(TRUE_MOMENTUM_COHORT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    const result = validateTrueMomentumCohortArchive(parsed);
    if (!result.ok) return null;
    return result.archive;
  } catch {
    return null;
  }
}

export function writeTrueMomentumCohortArchiveToStorage(
  archive: TrueMomentumCohortArchive | null,
): void {
  if (typeof window === "undefined") return;
  try {
    if (archive == null) {
      window.localStorage.removeItem(TRUE_MOMENTUM_COHORT_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(
      TRUE_MOMENTUM_COHORT_STORAGE_KEY,
      JSON.stringify(archive),
    );
  } catch {
    // best-effort
  }
}
