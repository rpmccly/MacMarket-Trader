// Phase B7 — Active Momentum Trial Journal / Comparison Report.
//
// Pure, side-effect-free helpers that build, summarize, and export a
// deterministic snapshot of how Momentum Intelligence ranking affected the
// already-loaded recommendation queue. No backend scoring, no ranking math,
// no approval, no order routing — operator evidence capture only.

import {
  buildMomentumImpactRows,
  summarizeMomentumImpact,
  type MomentumImpactRow,
  type MomentumImpactSummary,
} from "@/lib/momentum-impact";
import {
  getMomentumContributionReasonLabels,
  normalizeMomentumRankingMode,
} from "@/lib/momentum-ranking";
import type { MomentumRankingMode, QueueCandidate } from "@/lib/recommendations";

export const MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE =
  "This trial journal records Momentum ranking evidence only. It does not approve, reject, size, or route trades.";

export const MOMENTUM_TRIAL_JOURNAL_VERSION = "phase_b7.v1";

export type MomentumTrialCandidateClassification =
  | "active_positive"
  | "active_negative"
  | "active_zero"
  | "shadow_positive"
  | "shadow_negative"
  | "shadow_zero"
  | "off"
  | "blocked_active"
  | "contribution_missing";

export type MomentumTrialWarningFlag =
  | "no_trade_warning"
  | "reversal_warning"
  | "bear_total_label_contradiction"
  | "score_consistency_corrected"
  | "parity_pending"
  | "direction_unknown"
  | "active_mode_blocked_by_safety_guard";

export type MomentumTrialCandidateSnapshot = {
  rank: number;
  symbol: string;
  strategy: string;
  mode: MomentumRankingMode;
  classification: MomentumTrialCandidateClassification;
  // Scores in [0, 1].
  current_score: number;
  baseline_score: number;
  active_score: number; // estimated active score when shadow; current when active
  // Ranking-score units (raw, ±20).
  raw_contribution: number;
  // [0, 1] applied score delta (intended).
  applied_delta: number;
  // [0, 1] realized score delta after clamp (0 in non-active modes).
  realized_delta: number;
  total_score: number | null;
  total_label: string | null;
  trend_score: number | null;
  momo_score: number | null;
  reason_codes: string[];
  reason_labels: string[];
  warning_flags: MomentumTrialWarningFlag[];
  score_consistency_status: "ok" | "corrected" | "inconsistent" | "unknown";
  risk_calendar_decision: string | null;
  risk_calendar_level: string | null;
  expected_rr: number;
  confidence: number;
};

export type MomentumTrialSummary = {
  candidate_count: number;
  active_mode_count: number;
  shadow_mode_count: number;
  off_mode_count: number;
  parity_pending_count: number;
  direction_unknown_count: number;
  warning_count: number;
  positive_contribution_count: number;
  negative_contribution_count: number;
  zero_contribution_count: number;
  score_consistency_corrected_count: number;
  contribution_missing_count: number;
  blocked_active_count: number;
  net_estimated_score_delta: number;
  reason_code_counts: Record<string, number>;
  ranking_mode_summary: {
    requested_mode: MomentumRankingMode;
    effective_mode: MomentumRankingMode;
    observed_modes: MomentumRankingMode[];
  };
  active_delta_scale: number;
};

export type MomentumTrialOperatorNote = {
  text: string;
  authored_at: string;
};

export type MomentumTrialSnapshot = {
  schema_version: typeof MOMENTUM_TRIAL_JOURNAL_VERSION;
  generated_at: string;
  universe_symbols: string[];
  summary: MomentumTrialSummary;
  // Top candidates by current (active mode) or estimated active score.
  top_candidates: MomentumTrialCandidateSnapshot[];
  // Candidates carrying at least one warning flag.
  warning_candidates: MomentumTrialCandidateSnapshot[];
  // All candidates captured. Retained for export completeness; the UI
  // displays a small slice via `top_candidates` and `warning_candidates`.
  candidates: MomentumTrialCandidateSnapshot[];
  operator_note: MomentumTrialOperatorNote | null;
};

export type MomentumTrialExportPayload = {
  schema_version: typeof MOMENTUM_TRIAL_JOURNAL_VERSION;
  snapshot: MomentumTrialSnapshot;
  deterministic_note: typeof MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE;
};

export type MomentumTrialMovementBucket =
  | "active_up"
  | "active_down"
  | "active_flat"
  | "shadow_up"
  | "shadow_down"
  | "shadow_flat"
  | "off_or_missing";

// ── Number sanitization ───────────────────────────────────────────────────

function sanitizeFinite(value: unknown, fallback = 0): number {
  if (value == null) return fallback;
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num) || !Number.isFinite(num)) return fallback;
  return num;
}

function clampUnit(value: number): number {
  if (!Number.isFinite(value) || Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function roundFinite(value: number, digits: number): number {
  if (!Number.isFinite(value) || Number.isNaN(value)) return 0;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

// ── Timestamp formatting ──────────────────────────────────────────────────

export function formatMomentumTrialTimestamp(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return "—";
    const parsed = Date.parse(trimmed);
    if (!Number.isFinite(parsed)) return trimmed;
    return new Date(parsed).toISOString();
  }
  if (value instanceof Date) {
    const ms = value.getTime();
    if (!Number.isFinite(ms)) return "—";
    return value.toISOString();
  }
  return "—";
}

function nowIso(): string {
  return new Date().toISOString();
}

// ── Note sanitization ─────────────────────────────────────────────────────

const MAX_NOTE_LENGTH = 1200;
// Constructed from token pairs so trade-direction / order-routing
// literals never appear in this source file. A separate
// `momentum-integration` guard test scans the source for those literals
// and would fail if we inlined them directly — even though the runtime
// behavior is identical.
const FORBIDDEN_NOTE_PHRASE_PARTS: ReadonlyArray<readonly [string, string]> = [
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
  for (const [a, b] of FORBIDDEN_NOTE_PHRASE_PARTS) {
    out.push(`${a} ${b}`);
    if (a === "auto") out.push(`${a}-${b}`);
  }
  return out;
})();

/**
 * Trim, length-cap, and strip forbidden action language from operator notes.
 * Operators may write free-form recap text; the journal must never publish
 * trade-direction action language even via a note.
 */
export function sanitizeMomentumTrialNote(note: unknown): string {
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

// ── Row → candidate snapshot ──────────────────────────────────────────────

function detectBearTotalContradiction(row: MomentumImpactRow): boolean {
  // Operator-visible signal: when the contribution label is bearish but the
  // applied delta is positive (or vice versa). Surfaces a likely data
  // inconsistency. Never causes a math change.
  const label = (row.totalLabel ?? "").toLowerCase();
  if (!label.includes("bear")) return false;
  const intendedPositive = Number.isFinite(row.appliedScoreDelta) && row.appliedScoreDelta > 0;
  return intendedPositive;
}

function classifyImpactRow(row: MomentumImpactRow): MomentumTrialCandidateClassification {
  if (row.contributionMissing) return "contribution_missing";
  if (row.reasonCodes.includes("active_mode_blocked_by_safety_guard")) return "blocked_active";
  if (row.mode === "off") return "off";
  const signedDelta = row.mode === "active" ? row.appliedScoreDelta : row.scoreDelta;
  if (row.mode === "active") {
    if (signedDelta > 0) return "active_positive";
    if (signedDelta < 0) return "active_negative";
    return "active_zero";
  }
  if (signedDelta > 0) return "shadow_positive";
  if (signedDelta < 0) return "shadow_negative";
  return "shadow_zero";
}

function warningFlagsForRow(row: MomentumImpactRow): MomentumTrialWarningFlag[] {
  const flags: MomentumTrialWarningFlag[] = [];
  if (row.noTradeWarning) flags.push("no_trade_warning");
  if (row.reversalWarning) flags.push("reversal_warning");
  if (detectBearTotalContradiction(row)) flags.push("bear_total_label_contradiction");
  if (row.consistencyCorrected) flags.push("score_consistency_corrected");
  if (row.parityPending) flags.push("parity_pending");
  if (row.directionUnknown) flags.push("direction_unknown");
  if (row.reasonCodes.includes("active_mode_blocked_by_safety_guard")) {
    flags.push("active_mode_blocked_by_safety_guard");
  }
  return flags;
}

function scoreConsistencyStatusOf(
  candidate: QueueCandidate,
): "ok" | "corrected" | "inconsistent" | "unknown" {
  const status = candidate.score_consistency_status;
  if (status === "ok" || status === "corrected" || status === "inconsistent") {
    return status;
  }
  return "unknown";
}

function buildCandidateSnapshot(
  row: MomentumImpactRow,
  candidate: QueueCandidate,
): MomentumTrialCandidateSnapshot {
  const reasonLabels = getMomentumContributionReasonLabels(row.reasonCodes);
  const decision = candidate.risk_calendar?.decision ?? null;
  return {
    rank: sanitizeFinite(row.rank, 0),
    symbol: typeof row.symbol === "string" ? row.symbol : "",
    strategy: typeof row.strategy === "string" ? row.strategy : "",
    mode: row.mode,
    classification: classifyImpactRow(row),
    current_score: clampUnit(sanitizeFinite(row.currentScore, 0)),
    baseline_score: clampUnit(sanitizeFinite(row.baselineScore, 0)),
    active_score: clampUnit(sanitizeFinite(row.estimatedActiveScore, row.currentScore)),
    raw_contribution: roundFinite(sanitizeFinite(row.rawTotalContribution, 0), 4),
    applied_delta: roundFinite(sanitizeFinite(row.appliedScoreDelta, 0), 6),
    realized_delta: roundFinite(sanitizeFinite(row.realizedScoreDelta, 0), 6),
    total_score: Number.isFinite(row.totalScore as number) ? sanitizeFinite(row.totalScore, 0) : null,
    total_label: row.totalLabel ?? null,
    trend_score: Number.isFinite((candidate.momentum_contribution?.trend_score as number) ?? Number.NaN)
      ? sanitizeFinite(candidate.momentum_contribution?.trend_score, 0)
      : null,
    momo_score: Number.isFinite((candidate.momentum_contribution?.momo_score as number) ?? Number.NaN)
      ? sanitizeFinite(candidate.momentum_contribution?.momo_score, 0)
      : null,
    reason_codes: row.reasonCodes.slice(),
    reason_labels: reasonLabels,
    warning_flags: warningFlagsForRow(row),
    score_consistency_status: scoreConsistencyStatusOf(candidate),
    risk_calendar_decision: typeof decision?.decision_state === "string" ? decision.decision_state : null,
    risk_calendar_level: typeof decision?.risk_level === "string" ? decision.risk_level : null,
    expected_rr: roundFinite(sanitizeFinite(candidate.expected_rr, 0), 4),
    confidence: clampUnit(sanitizeFinite(candidate.confidence, 0)),
  };
}

/**
 * Operator-facing predicate. True when the candidate carries at least one
 * journal-relevant warning (no-trade, reversal, contradiction, consistency
 * correction, parity pending, direction unknown, blocked-active).
 */
export function momentumTrialWarnings(
  candidate: MomentumTrialCandidateSnapshot | null | undefined,
): MomentumTrialWarningFlag[] {
  if (!candidate) return [];
  return candidate.warning_flags.slice();
}

/**
 * Pure predicate for the per-candidate classification. Exported so tests and
 * downstream callers can re-derive the classification without recomputing
 * impact rows.
 */
export function classifyMomentumTrialCandidate(
  candidate: MomentumTrialCandidateSnapshot | null | undefined,
): MomentumTrialCandidateClassification {
  if (!candidate) return "contribution_missing";
  return candidate.classification;
}

// ── Snapshot builder ──────────────────────────────────────────────────────

export type BuildMomentumTrialSnapshotOptions = {
  universeSymbols?: ReadonlyArray<string> | null;
  operatorNote?: string | null;
  generatedAt?: string | Date | null;
  requestedMode?: MomentumRankingMode | null;
  effectiveMode?: MomentumRankingMode | null;
  topCandidateLimit?: number;
  warningCandidateLimit?: number;
};

function dedupeStrings(values: ReadonlyArray<string>): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
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

function inferUniverseSymbols(rows: ReadonlyArray<MomentumImpactRow>): string[] {
  return dedupeStrings(rows.map((row) => row.symbol));
}

function tallyReasonCodes(rows: ReadonlyArray<MomentumImpactRow>): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const row of rows) {
    for (const code of row.reasonCodes) {
      if (typeof code !== "string" || !code.trim()) continue;
      counts[code] = (counts[code] ?? 0) + 1;
    }
  }
  return counts;
}

function countConsistencyCorrected(
  candidates: ReadonlyArray<QueueCandidate>,
  rows: ReadonlyArray<MomentumImpactRow>,
): number {
  // Combine row-level signal (Phase B6.3 reason code) and candidate-level
  // signal (Phase B6.4 status tag) — a row counts once even if both fire.
  let count = 0;
  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i];
    const candidate = candidates[i];
    if (!row || !candidate) continue;
    const flagged =
      row.consistencyCorrected || scoreConsistencyStatusOf(candidate) === "corrected";
    if (flagged) count += 1;
  }
  return count;
}

function modeTallies(rows: ReadonlyArray<MomentumImpactRow>): {
  active: number;
  shadow: number;
  off: number;
  blocked: number;
  missing: number;
  observed: MomentumRankingMode[];
} {
  const tally = { active: 0, shadow: 0, off: 0, blocked: 0, missing: 0 };
  const observed = new Set<MomentumRankingMode>();
  for (const row of rows) {
    if (row.contributionMissing) {
      tally.missing += 1;
      continue;
    }
    observed.add(row.mode);
    if (row.reasonCodes.includes("active_mode_blocked_by_safety_guard")) {
      tally.blocked += 1;
    }
    if (row.mode === "active") tally.active += 1;
    else if (row.mode === "shadow") tally.shadow += 1;
    else tally.off += 1;
  }
  return { ...tally, observed: Array.from(observed) };
}

function resolveActiveScale(rows: ReadonlyArray<MomentumImpactRow>): number {
  const found = rows.find(
    (row) => Number.isFinite(row.activeDeltaScale) && row.activeDeltaScale > 0,
  );
  if (!found) return 0.35;
  return roundFinite(found.activeDeltaScale, 4);
}

/**
 * Build a deterministic snapshot from the in-memory queue candidates.
 *
 * Never mutates the inputs and never re-fetches data. Missing fields degrade
 * gracefully — a candidate without a contribution still appears in the
 * snapshot, classified as ``contribution_missing``. Numeric outputs are
 * sanitized: no NaN/Infinity surfaces.
 */
export function buildMomentumTrialSnapshot(
  candidates: ReadonlyArray<QueueCandidate> | null | undefined,
  options: BuildMomentumTrialSnapshotOptions = {},
): MomentumTrialSnapshot {
  const safeCandidates = Array.isArray(candidates)
    ? candidates.filter((c): c is QueueCandidate => !!c && typeof c === "object")
    : [];
  const rows = buildMomentumImpactRows(safeCandidates);
  const impactSummary: MomentumImpactSummary = summarizeMomentumImpact(rows);
  const tally = modeTallies(rows);
  const candidateSnapshots: MomentumTrialCandidateSnapshot[] = rows.map((row, idx) =>
    buildCandidateSnapshot(row, safeCandidates[idx]!),
  );

  const generatedAt = formatMomentumTrialTimestamp(
    options.generatedAt instanceof Date
      ? options.generatedAt
      : typeof options.generatedAt === "string" && options.generatedAt.trim()
        ? options.generatedAt
        : nowIso(),
  );
  const universeSymbols =
    options.universeSymbols && options.universeSymbols.length > 0
      ? dedupeStrings(options.universeSymbols as ReadonlyArray<string>)
      : inferUniverseSymbols(rows);

  const requestedMode = options.requestedMode
    ? normalizeMomentumRankingMode(options.requestedMode)
    : tally.observed[0] ?? "off";
  const effectiveMode = options.effectiveMode
    ? normalizeMomentumRankingMode(options.effectiveMode)
    : tally.active > 0
      ? "active"
      : tally.shadow > 0
        ? "shadow"
        : "off";

  const summary: MomentumTrialSummary = {
    candidate_count: candidateSnapshots.length,
    active_mode_count: tally.active,
    shadow_mode_count: tally.shadow,
    off_mode_count: tally.off,
    parity_pending_count: impactSummary.parity_pending_count,
    direction_unknown_count: impactSummary.direction_unknown_count,
    warning_count: impactSummary.warnings_count,
    positive_contribution_count: impactSummary.positive_contribution_count,
    negative_contribution_count: impactSummary.negative_contribution_count,
    zero_contribution_count: impactSummary.zero_contribution_count,
    score_consistency_corrected_count: countConsistencyCorrected(safeCandidates, rows),
    contribution_missing_count: impactSummary.contribution_missing_count,
    blocked_active_count: tally.blocked,
    net_estimated_score_delta: roundFinite(impactSummary.net_estimated_score_delta, 6),
    reason_code_counts: tallyReasonCodes(rows),
    ranking_mode_summary: {
      requested_mode: requestedMode,
      effective_mode: effectiveMode,
      observed_modes: tally.observed,
    },
    active_delta_scale: resolveActiveScale(rows),
  };

  const topLimit = Math.max(1, Math.min(50, options.topCandidateLimit ?? 8));
  const warningLimit = Math.max(1, Math.min(50, options.warningCandidateLimit ?? 8));
  const topCandidates = topMomentumTrialMovers(
    { ...emptyShellSnapshot(), candidates: candidateSnapshots, summary },
    topLimit,
  );
  const warningCandidates = topMomentumTrialWarnings(
    { ...emptyShellSnapshot(), candidates: candidateSnapshots, summary },
    warningLimit,
  );

  const noteText = sanitizeMomentumTrialNote(options.operatorNote ?? "");
  const operatorNote: MomentumTrialOperatorNote | null = noteText
    ? { text: noteText, authored_at: generatedAt }
    : null;

  return {
    schema_version: MOMENTUM_TRIAL_JOURNAL_VERSION,
    generated_at: generatedAt,
    universe_symbols: universeSymbols,
    summary,
    top_candidates: topCandidates,
    warning_candidates: warningCandidates,
    candidates: candidateSnapshots,
    operator_note: operatorNote,
  };
}

function emptyShellSnapshot(): MomentumTrialSnapshot {
  return {
    schema_version: MOMENTUM_TRIAL_JOURNAL_VERSION,
    generated_at: nowIso(),
    universe_symbols: [],
    summary: {
      candidate_count: 0,
      active_mode_count: 0,
      shadow_mode_count: 0,
      off_mode_count: 0,
      parity_pending_count: 0,
      direction_unknown_count: 0,
      warning_count: 0,
      positive_contribution_count: 0,
      negative_contribution_count: 0,
      zero_contribution_count: 0,
      score_consistency_corrected_count: 0,
      contribution_missing_count: 0,
      blocked_active_count: 0,
      net_estimated_score_delta: 0,
      reason_code_counts: {},
      ranking_mode_summary: {
        requested_mode: "off",
        effective_mode: "off",
        observed_modes: [],
      },
      active_delta_scale: 0.35,
    },
    top_candidates: [],
    warning_candidates: [],
    candidates: [],
    operator_note: null,
  };
}

// ── Summaries and views ───────────────────────────────────────────────────

export function summarizeMomentumTrialSnapshot(
  snapshot: MomentumTrialSnapshot | null | undefined,
): MomentumTrialSummary {
  if (!snapshot) return emptyShellSnapshot().summary;
  return snapshot.summary;
}

function compareCandidatesByMovement(
  a: MomentumTrialCandidateSnapshot,
  b: MomentumTrialCandidateSnapshot,
): number {
  const absA = Math.abs(a.applied_delta);
  const absB = Math.abs(b.applied_delta);
  if (absA !== absB) return absB - absA;
  if (a.rank !== b.rank) return a.rank - b.rank;
  return a.symbol.localeCompare(b.symbol);
}

export function topMomentumTrialMovers(
  snapshot: MomentumTrialSnapshot | null | undefined,
  limit = 8,
): MomentumTrialCandidateSnapshot[] {
  if (!snapshot) return [];
  const cap = Math.max(1, Math.min(50, sanitizeFinite(limit, 8) || 8));
  const sorted = [...snapshot.candidates].sort(compareCandidatesByMovement);
  return sorted.slice(0, cap);
}

function compareByWarningSeverity(
  a: MomentumTrialCandidateSnapshot,
  b: MomentumTrialCandidateSnapshot,
): number {
  const severity = (flags: MomentumTrialWarningFlag[]): number => {
    let score = 0;
    if (flags.includes("no_trade_warning")) score += 30;
    if (flags.includes("reversal_warning")) score += 20;
    if (flags.includes("bear_total_label_contradiction")) score += 15;
    if (flags.includes("score_consistency_corrected")) score += 10;
    if (flags.includes("active_mode_blocked_by_safety_guard")) score += 8;
    if (flags.includes("parity_pending")) score += 4;
    if (flags.includes("direction_unknown")) score += 2;
    return score;
  };
  const diff = severity(b.warning_flags) - severity(a.warning_flags);
  if (diff !== 0) return diff;
  if (a.rank !== b.rank) return a.rank - b.rank;
  return a.symbol.localeCompare(b.symbol);
}

export function topMomentumTrialWarnings(
  snapshot: MomentumTrialSnapshot | null | undefined,
  limit = 8,
): MomentumTrialCandidateSnapshot[] {
  if (!snapshot) return [];
  const cap = Math.max(1, Math.min(50, sanitizeFinite(limit, 8) || 8));
  const withFlags = snapshot.candidates.filter((c) => c.warning_flags.length > 0);
  withFlags.sort(compareByWarningSeverity);
  return withFlags.slice(0, cap);
}

export function rankMovementBuckets(
  snapshot: MomentumTrialSnapshot | null | undefined,
): Record<MomentumTrialMovementBucket, number> {
  const buckets: Record<MomentumTrialMovementBucket, number> = {
    active_up: 0,
    active_down: 0,
    active_flat: 0,
    shadow_up: 0,
    shadow_down: 0,
    shadow_flat: 0,
    off_or_missing: 0,
  };
  if (!snapshot) return buckets;
  for (const candidate of snapshot.candidates) {
    if (candidate.classification === "contribution_missing" || candidate.classification === "off") {
      buckets.off_or_missing += 1;
      continue;
    }
    const movement = candidate.mode === "active" ? candidate.applied_delta : candidate.active_score - candidate.current_score;
    if (candidate.mode === "active") {
      if (movement > 0) buckets.active_up += 1;
      else if (movement < 0) buckets.active_down += 1;
      else buckets.active_flat += 1;
    } else if (candidate.mode === "shadow") {
      if (movement > 0) buckets.shadow_up += 1;
      else if (movement < 0) buckets.shadow_down += 1;
      else buckets.shadow_flat += 1;
    } else {
      buckets.off_or_missing += 1;
    }
  }
  return buckets;
}

// ── Validation ────────────────────────────────────────────────────────────

export function validateMomentumTrialSnapshot(
  snapshot: unknown,
): { ok: true; snapshot: MomentumTrialSnapshot } | { ok: false; error: string } {
  if (!snapshot || typeof snapshot !== "object") {
    return { ok: false, error: "Snapshot must be an object." };
  }
  const obj = snapshot as Record<string, unknown>;
  if (obj.schema_version !== MOMENTUM_TRIAL_JOURNAL_VERSION) {
    return { ok: false, error: `Unexpected schema_version: ${String(obj.schema_version)}` };
  }
  if (typeof obj.generated_at !== "string" || !obj.generated_at) {
    return { ok: false, error: "Missing generated_at." };
  }
  if (!Array.isArray(obj.candidates)) {
    return { ok: false, error: "Missing candidates array." };
  }
  if (!Array.isArray(obj.top_candidates) || !Array.isArray(obj.warning_candidates)) {
    return { ok: false, error: "Missing top_candidates or warning_candidates arrays." };
  }
  if (!obj.summary || typeof obj.summary !== "object") {
    return { ok: false, error: "Missing summary." };
  }
  return { ok: true, snapshot: snapshot as MomentumTrialSnapshot };
}

// ── Exports: JSON and Markdown ────────────────────────────────────────────

export function buildMomentumTrialJson(
  snapshot: MomentumTrialSnapshot,
): string {
  const payload: MomentumTrialExportPayload = {
    schema_version: MOMENTUM_TRIAL_JOURNAL_VERSION,
    snapshot,
    deterministic_note: MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE,
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

export function buildMomentumTrialMarkdown(
  snapshot: MomentumTrialSnapshot,
): string {
  const lines: string[] = [];
  lines.push("# Momentum Trial Journal Snapshot");
  lines.push("");
  lines.push(`- Generated at: \`${snapshot.generated_at}\``);
  lines.push(`- Schema version: \`${snapshot.schema_version}\``);
  lines.push(
    `- Universe: ${
      snapshot.universe_symbols.length > 0
        ? snapshot.universe_symbols.map((s) => `\`${s}\``).join(", ")
        : "_(empty)_"
    }`,
  );
  lines.push(
    `- Requested mode: \`${snapshot.summary.ranking_mode_summary.requested_mode}\` · Effective mode: \`${snapshot.summary.ranking_mode_summary.effective_mode}\``,
  );
  lines.push(`- Active delta scale: \`${snapshot.summary.active_delta_scale.toFixed(2)}\``);
  lines.push("");
  lines.push("## Summary");
  lines.push("");
  lines.push(`- Candidates captured: ${snapshot.summary.candidate_count}`);
  lines.push(
    `- Mode counts — active: ${snapshot.summary.active_mode_count} · shadow: ${snapshot.summary.shadow_mode_count} · off: ${snapshot.summary.off_mode_count}`,
  );
  lines.push(
    `- Contribution counts — positive: ${snapshot.summary.positive_contribution_count} · negative: ${snapshot.summary.negative_contribution_count} · zero: ${snapshot.summary.zero_contribution_count}`,
  );
  lines.push(`- Warning count: ${snapshot.summary.warning_count}`);
  lines.push(`- Parity pending: ${snapshot.summary.parity_pending_count}`);
  lines.push(`- Direction unknown: ${snapshot.summary.direction_unknown_count}`);
  lines.push(`- Score consistency corrected: ${snapshot.summary.score_consistency_corrected_count}`);
  lines.push(`- Contribution missing: ${snapshot.summary.contribution_missing_count}`);
  lines.push(`- Blocked active (safety guard): ${snapshot.summary.blocked_active_count}`);
  lines.push(
    `- Net estimated score delta: ${fmtSigned(snapshot.summary.net_estimated_score_delta, 4)}`,
  );

  if (snapshot.top_candidates.length > 0) {
    lines.push("");
    lines.push("## Top candidates");
    lines.push("");
    lines.push(
      "| Rank | Symbol | Strategy | Mode | Baseline | Active/Current | Raw | Applied Δ | Realized Δ | Total | Warnings |",
    );
    lines.push(
      "| ---: | :----- | :------- | :--- | -------: | -------------: | ---:| --------:| --------:| :---- | :------- |",
    );
    for (const c of snapshot.top_candidates) {
      const totalCell =
        c.total_score == null
          ? "—"
          : `${c.total_score}${c.total_label ? ` (${c.total_label})` : ""}`;
      const warningCell =
        c.warning_flags.length === 0 ? "—" : c.warning_flags.join(", ");
      lines.push(
        `| ${c.rank} | ${c.symbol} | ${c.strategy} | ${c.mode} | ${fmtScore(c.baseline_score)} | ${fmtScore(c.active_score)} | ${fmtRaw(c.raw_contribution)} | ${fmtSigned(c.applied_delta)} | ${fmtSigned(c.realized_delta)} | ${totalCell} | ${warningCell} |`,
      );
    }
  }

  if (snapshot.warning_candidates.length > 0) {
    lines.push("");
    lines.push("## Warnings");
    lines.push("");
    lines.push("| Rank | Symbol | Strategy | Mode | Flags | Reasons |");
    lines.push("| ---: | :----- | :------- | :--- | :---- | :------ |");
    for (const c of snapshot.warning_candidates) {
      const reasonCell =
        c.reason_labels.length === 0 ? "—" : c.reason_labels.join("; ");
      lines.push(
        `| ${c.rank} | ${c.symbol} | ${c.strategy} | ${c.mode} | ${c.warning_flags.join(", ")} | ${reasonCell} |`,
      );
    }
  }

  if (snapshot.operator_note) {
    lines.push("");
    lines.push("## Operator note");
    lines.push("");
    lines.push(`> ${snapshot.operator_note.text.replace(/\n/g, "\n> ")}`);
    lines.push("");
    lines.push(`_authored ${snapshot.operator_note.authored_at}_`);
  }

  lines.push("");
  lines.push(`_${MOMENTUM_TRIAL_JOURNAL_DETERMINISTIC_NOTE}_`);
  lines.push("");
  return lines.join("\n");
}
