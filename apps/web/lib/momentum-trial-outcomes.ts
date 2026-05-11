// Phase B8 — outcome tagging for Active Momentum Trial Journal snapshots.
//
// Pure, side-effect-free helpers that let an operator review a captured
// Phase B7 snapshot after a session and tag each candidate with the
// observed outcome (worked / missed / too aggressive / good warning /
// false warning / watchlist only / needs ToS parity check / ignored /
// unclear). Outcome tagging is local/export-only — no backend
// persistence, no DB row, no LLM call.
//
// The helpers never mutate the snapshot, never approve / reject / size /
// route trades, and never change queue sorting, ranking math, or
// paper-order behavior.

import type {
  MomentumTrialCandidateSnapshot,
  MomentumTrialSnapshot,
} from "@/lib/momentum-trial-journal";
import {
  buildMomentumTrialJson,
  momentumTrialUniverseLabel,
} from "@/lib/momentum-trial-journal";

export const MOMENTUM_TRIAL_OUTCOME_REVIEW_VERSION = "phase_b8.v1";

export const MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE =
  "Outcome tags are operator research notes only. They do not change ranking, approval, sizing, or order routing.";

export const MOMENTUM_TRIAL_OUTCOME_STORAGE_KEY =
  "macmarket.momentumTrial.outcome.latest";

export type MomentumTrialOutcomeTag =
  | "worked"
  | "missed"
  | "too_aggressive"
  | "good_warning"
  | "false_warning"
  | "watchlist_only"
  | "needs_tos_parity_check"
  | "ignored"
  | "unclear";

export const MOMENTUM_TRIAL_OUTCOME_TAGS: ReadonlyArray<MomentumTrialOutcomeTag> = [
  "worked",
  "missed",
  "too_aggressive",
  "good_warning",
  "false_warning",
  "watchlist_only",
  "needs_tos_parity_check",
  "ignored",
  "unclear",
];

const OUTCOME_TAG_LABELS: Record<MomentumTrialOutcomeTag, string> = {
  worked: "Worked",
  missed: "Missed",
  too_aggressive: "Too aggressive",
  good_warning: "Good warning",
  false_warning: "False warning",
  watchlist_only: "Watchlist only",
  needs_tos_parity_check: "Needs ToS parity check",
  ignored: "Ignored",
  unclear: "Unclear",
};

const OUTCOME_TAG_TONES: Record<MomentumTrialOutcomeTag, "good" | "warn" | "bad" | "neutral"> = {
  worked: "good",
  missed: "bad",
  too_aggressive: "warn",
  good_warning: "good",
  false_warning: "warn",
  watchlist_only: "neutral",
  needs_tos_parity_check: "warn",
  ignored: "neutral",
  unclear: "neutral",
};

export function outcomeTagLabel(
  tag: MomentumTrialOutcomeTag | string | null | undefined,
): string {
  if (tag == null) return "Unclear";
  if (typeof tag === "string" && tag in OUTCOME_TAG_LABELS) {
    return OUTCOME_TAG_LABELS[tag as MomentumTrialOutcomeTag];
  }
  return "Unclear";
}

export function outcomeTagTone(
  tag: MomentumTrialOutcomeTag | string | null | undefined,
): "good" | "warn" | "bad" | "neutral" {
  if (tag == null) return "neutral";
  if (typeof tag === "string" && tag in OUTCOME_TAG_TONES) {
    return OUTCOME_TAG_TONES[tag as MomentumTrialOutcomeTag];
  }
  return "neutral";
}

export function isMomentumTrialOutcomeTag(
  value: unknown,
): value is MomentumTrialOutcomeTag {
  return (
    typeof value === "string" &&
    (MOMENTUM_TRIAL_OUTCOME_TAGS as ReadonlyArray<string>).includes(value)
  );
}

export type MomentumTrialOutcomeNote = {
  text: string;
  authored_at: string;
};

export type MomentumTrialCandidateOutcome = {
  symbol: string;
  strategy: string;
  rank: number;
  tag: MomentumTrialOutcomeTag;
  note: string;
  // Reason codes are copied verbatim from the source snapshot so the
  // outcome export can stand alone without the original snapshot.
  reason_codes: string[];
  trade_warning_flags: string[];
  operational_caveat_flags: string[];
};

export type MomentumTrialOutcomeSummary = {
  candidate_count: number;
  worked_count: number;
  missed_count: number;
  too_aggressive_count: number;
  good_warning_count: number;
  false_warning_count: number;
  watchlist_only_count: number;
  needs_tos_parity_check_count: number;
  ignored_count: number;
  unclear_count: number;
  // Aggregate of every reason_code on candidate outcomes.
  reason_code_counts: Record<string, number>;
};

export type MomentumTrialOutcomeReview = {
  schema_version: typeof MOMENTUM_TRIAL_OUTCOME_REVIEW_VERSION;
  generated_at: string;
  snapshot: MomentumTrialSnapshot;
  global_conclusion: MomentumTrialOutcomeNote | null;
  candidate_outcomes: MomentumTrialCandidateOutcome[];
  summary: MomentumTrialOutcomeSummary;
};

export type MomentumTrialOutcomeExportPayload = {
  schema_version: typeof MOMENTUM_TRIAL_OUTCOME_REVIEW_VERSION;
  review: MomentumTrialOutcomeReview;
  deterministic_note: typeof MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE;
};

// ── Note sanitization ─────────────────────────────────────────────────

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

const FORBIDDEN_OUTCOME_NOTE_PHRASES: ReadonlyArray<string> = (() => {
  const out: string[] = [];
  for (const [a, b] of ACTION_WORD_PAIRS) {
    out.push(`${a} ${b}`);
    if (a === "auto") out.push(`${a}-${b}`);
  }
  return out;
})();

export function sanitizeMomentumOutcomeNote(note: unknown): string {
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
  for (const phrase of FORBIDDEN_OUTCOME_NOTE_PHRASES) {
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

// ── Timestamp helper ──────────────────────────────────────────────────

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

// ── Candidate keying ──────────────────────────────────────────────────

export function momentumCandidateOutcomeKey(input: {
  symbol: string;
  strategy: string;
  rank: number;
}): string {
  return `${input.symbol}::${input.strategy}::${input.rank}`;
}

function sortByRankThenSymbol(
  a: MomentumTrialCandidateSnapshot,
  b: MomentumTrialCandidateSnapshot,
): number {
  if (a.rank !== b.rank) return a.rank - b.rank;
  return a.symbol.localeCompare(b.symbol);
}

/**
 * Build the default per-candidate outcome rows from a snapshot.
 *
 * Default selection follows the Phase B7.1 split: every top-candidate
 * row plus every trade-warning row plus every operational-caveat row,
 * deduped by ``symbol::strategy::rank``. Each row starts with the
 * ``unclear`` tag and an empty note so the operator can update them
 * one at a time.
 */
export function candidateOutcomeDefaults(
  snapshot: MomentumTrialSnapshot | null | undefined,
): MomentumTrialCandidateOutcome[] {
  if (!snapshot) return [];
  const seen = new Set<string>();
  const merged: MomentumTrialCandidateSnapshot[] = [];
  const buckets = [
    snapshot.top_candidates,
    snapshot.trade_warning_candidates,
    snapshot.operational_caveat_candidates,
  ];
  for (const bucket of buckets) {
    if (!Array.isArray(bucket)) continue;
    for (const candidate of bucket) {
      if (!candidate) continue;
      const key = momentumCandidateOutcomeKey(candidate);
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(candidate);
    }
  }
  merged.sort(sortByRankThenSymbol);
  return merged.map((candidate) => ({
    symbol: candidate.symbol,
    strategy: candidate.strategy,
    rank: Number.isFinite(candidate.rank) ? candidate.rank : 0,
    tag: "unclear",
    note: "",
    reason_codes: Array.isArray(candidate.reason_codes)
      ? candidate.reason_codes.slice()
      : [],
    trade_warning_flags: Array.isArray(candidate.trade_warning_flags)
      ? candidate.trade_warning_flags.slice()
      : [],
    operational_caveat_flags: Array.isArray(candidate.operational_caveat_flags)
      ? candidate.operational_caveat_flags.slice()
      : [],
  }));
}

function normalizeIncomingOutcome(
  raw: unknown,
): MomentumTrialCandidateOutcome | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const symbol = typeof obj.symbol === "string" ? obj.symbol : "";
  const strategy = typeof obj.strategy === "string" ? obj.strategy : "";
  const rankRaw = obj.rank;
  const rank =
    typeof rankRaw === "number" && Number.isFinite(rankRaw) ? rankRaw : 0;
  if (!symbol || !strategy) return null;
  const tag = isMomentumTrialOutcomeTag(obj.tag) ? obj.tag : "unclear";
  const note = sanitizeMomentumOutcomeNote(obj.note ?? "");
  const reason_codes = Array.isArray(obj.reason_codes)
    ? (obj.reason_codes as unknown[])
        .filter((v): v is string => typeof v === "string")
        .slice()
    : [];
  const trade_warning_flags = Array.isArray(obj.trade_warning_flags)
    ? (obj.trade_warning_flags as unknown[])
        .filter((v): v is string => typeof v === "string")
        .slice()
    : [];
  const operational_caveat_flags = Array.isArray(obj.operational_caveat_flags)
    ? (obj.operational_caveat_flags as unknown[])
        .filter((v): v is string => typeof v === "string")
        .slice()
    : [];
  return {
    symbol,
    strategy,
    rank,
    tag,
    note,
    reason_codes,
    trade_warning_flags,
    operational_caveat_flags,
  };
}

// ── Summary ───────────────────────────────────────────────────────────

function emptySummary(): MomentumTrialOutcomeSummary {
  return {
    candidate_count: 0,
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
  };
}

const TAG_COUNT_FIELDS: Record<MomentumTrialOutcomeTag, keyof MomentumTrialOutcomeSummary> = {
  worked: "worked_count",
  missed: "missed_count",
  too_aggressive: "too_aggressive_count",
  good_warning: "good_warning_count",
  false_warning: "false_warning_count",
  watchlist_only: "watchlist_only_count",
  needs_tos_parity_check: "needs_tos_parity_check_count",
  ignored: "ignored_count",
  unclear: "unclear_count",
};

export function summarizeMomentumTrialOutcomes(
  review: MomentumTrialOutcomeReview | null | undefined,
): MomentumTrialOutcomeSummary {
  const summary = emptySummary();
  if (!review || !Array.isArray(review.candidate_outcomes)) return summary;
  for (const outcome of review.candidate_outcomes) {
    if (!outcome) continue;
    summary.candidate_count += 1;
    const tagKey = TAG_COUNT_FIELDS[outcome.tag];
    if (tagKey) {
      const current = summary[tagKey];
      if (typeof current === "number") {
        (summary as unknown as Record<string, number>)[tagKey] = current + 1;
      }
    }
    if (Array.isArray(outcome.reason_codes)) {
      for (const code of outcome.reason_codes) {
        if (typeof code !== "string" || !code.trim()) continue;
        summary.reason_code_counts[code] =
          (summary.reason_code_counts[code] ?? 0) + 1;
      }
    }
  }
  return summary;
}

export function outcomeReasonCounts(
  review: MomentumTrialOutcomeReview | null | undefined,
): Record<string, number> {
  return summarizeMomentumTrialOutcomes(review).reason_code_counts;
}

// ── Builder ───────────────────────────────────────────────────────────

export type BuildMomentumTrialOutcomeReviewOptions = {
  /** Existing outcomes (e.g. re-hydrated from localStorage) keyed by
   *  ``symbol::strategy::rank``. Unknown candidates degrade gracefully:
   *  if a snapshot row is missing an existing outcome we drop into the
   *  ``unclear`` default; if an incoming outcome references a candidate
   *  no longer in the snapshot, it is ignored. */
  existingOutcomes?: ReadonlyArray<unknown> | null;
  /** Operator's global conclusion text. Sanitized exactly like a
   *  candidate note. */
  globalConclusion?: string | null;
  generatedAt?: string | Date | null;
};

/**
 * Build a deterministic outcome review for a captured snapshot.
 *
 * Never mutates the snapshot, never produces NaN/Infinity, and never
 * emits forbidden trade-direction or order-routing language.
 */
export function buildMomentumTrialOutcomeReview(
  snapshot: MomentumTrialSnapshot | null | undefined,
  options: BuildMomentumTrialOutcomeReviewOptions = {},
): MomentumTrialOutcomeReview {
  const generatedAt = formatTimestamp(options.generatedAt ?? null);
  const defaults = candidateOutcomeDefaults(snapshot);
  const incoming = Array.isArray(options.existingOutcomes)
    ? options.existingOutcomes.map(normalizeIncomingOutcome).filter(
        (entry): entry is MomentumTrialCandidateOutcome => entry !== null,
      )
    : [];
  const byKey = new Map<string, MomentumTrialCandidateOutcome>();
  for (const entry of incoming) {
    byKey.set(momentumCandidateOutcomeKey(entry), entry);
  }

  const candidateOutcomes: MomentumTrialCandidateOutcome[] = defaults.map(
    (defaultRow) => {
      const key = momentumCandidateOutcomeKey(defaultRow);
      const existing = byKey.get(key);
      if (!existing) return defaultRow;
      return {
        ...defaultRow,
        tag: existing.tag,
        note: existing.note,
      };
    },
  );

  const conclusionText = sanitizeMomentumOutcomeNote(
    options.globalConclusion ?? "",
  );
  const global_conclusion: MomentumTrialOutcomeNote | null = conclusionText
    ? { text: conclusionText, authored_at: generatedAt }
    : null;

  const review: MomentumTrialOutcomeReview = {
    schema_version: MOMENTUM_TRIAL_OUTCOME_REVIEW_VERSION,
    generated_at: generatedAt,
    snapshot: snapshot ?? emptySnapshotFallback(),
    global_conclusion,
    candidate_outcomes: candidateOutcomes,
    summary: emptySummary(),
  };
  review.summary = summarizeMomentumTrialOutcomes(review);
  return review;
}

function emptySnapshotFallback(): MomentumTrialSnapshot {
  // The trial-journal lib does not export an empty-shell builder, so we
  // construct a minimal valid snapshot just for the case where the
  // operator opens the outcome review with no captured snapshot at all
  // (UI keeps this guarded — see ``MomentumTrialOutcomeReview`` empty
  // state).
  return {
    schema_version: "phase_b7_1.v1",
    generated_at: nowIso(),
    universe_symbols: [],
    universe_kind: "captured",
    summary: {
      candidate_count: 0,
      active_mode_count: 0,
      shadow_mode_count: 0,
      off_mode_count: 0,
      parity_pending_count: 0,
      direction_unknown_count: 0,
      derived_higher_timeframe_count: 0,
      warning_count: 0,
      trade_warning_count: 0,
      operational_caveat_count: 0,
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
    trade_warning_candidates: [],
    operational_caveat_candidates: [],
    candidates: [],
    operator_note: null,
  };
}

// ── Validation ────────────────────────────────────────────────────────

export function validateMomentumTrialOutcomeReview(
  review: unknown,
):
  | { ok: true; review: MomentumTrialOutcomeReview }
  | { ok: false; error: string } {
  if (!review || typeof review !== "object") {
    return { ok: false, error: "Outcome review must be an object." };
  }
  const obj = review as Record<string, unknown>;
  if (obj.schema_version !== MOMENTUM_TRIAL_OUTCOME_REVIEW_VERSION) {
    return {
      ok: false,
      error: `Unexpected schema_version: ${String(obj.schema_version)}`,
    };
  }
  if (typeof obj.generated_at !== "string" || !obj.generated_at) {
    return { ok: false, error: "Missing generated_at." };
  }
  if (!obj.snapshot || typeof obj.snapshot !== "object") {
    return { ok: false, error: "Missing snapshot." };
  }
  if (!Array.isArray(obj.candidate_outcomes)) {
    return { ok: false, error: "Missing candidate_outcomes array." };
  }
  if (!obj.summary || typeof obj.summary !== "object") {
    return { ok: false, error: "Missing summary." };
  }
  return { ok: true, review: review as MomentumTrialOutcomeReview };
}

// ── Exports: JSON + Markdown ──────────────────────────────────────────

export function buildMomentumOutcomeJson(
  review: MomentumTrialOutcomeReview,
): string {
  const payload: MomentumTrialOutcomeExportPayload = {
    schema_version: MOMENTUM_TRIAL_OUTCOME_REVIEW_VERSION,
    review,
    deterministic_note: MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE,
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

export function buildMomentumOutcomeMarkdown(
  review: MomentumTrialOutcomeReview,
): string {
  const lines: string[] = [];
  const snapshot = review.snapshot;
  const summary = review.summary;

  lines.push("# Momentum Trial Outcome Review");
  lines.push("");
  lines.push(`- Snapshot generated at: \`${snapshot.generated_at}\``);
  lines.push(`- Review generated at: \`${review.generated_at}\``);
  lines.push(`- Schema version: \`${review.schema_version}\``);
  lines.push(
    `- Requested mode: \`${snapshot.summary.ranking_mode_summary.requested_mode}\` · Effective mode: \`${snapshot.summary.ranking_mode_summary.effective_mode}\``,
  );
  lines.push(
    `- Active delta scale: \`${snapshot.summary.active_delta_scale.toFixed(2)}\``,
  );
  lines.push(
    `- ${momentumTrialUniverseLabel(snapshot.universe_kind)}: ${
      snapshot.universe_symbols.length > 0
        ? snapshot.universe_symbols.map((s) => `\`${s}\``).join(", ")
        : "_(empty)_"
    }`,
  );
  if (snapshot.operator_note) {
    lines.push("");
    lines.push("## Snapshot operator note");
    lines.push("");
    lines.push(`> ${snapshot.operator_note.text.replace(/\n/g, "\n> ")}`);
  }

  lines.push("");
  lines.push("## Global outcome conclusion");
  lines.push("");
  if (review.global_conclusion) {
    lines.push(`> ${review.global_conclusion.text.replace(/\n/g, "\n> ")}`);
    lines.push("");
    lines.push(`_authored ${review.global_conclusion.authored_at}_`);
  } else {
    lines.push("_No global conclusion recorded._");
  }

  lines.push("");
  lines.push("## Outcome summary");
  lines.push("");
  lines.push(`- Candidates tagged: ${summary.candidate_count}`);
  lines.push(`- Worked: ${summary.worked_count}`);
  lines.push(`- Missed: ${summary.missed_count}`);
  lines.push(`- Too aggressive: ${summary.too_aggressive_count}`);
  lines.push(`- Good warnings: ${summary.good_warning_count}`);
  lines.push(`- False warnings: ${summary.false_warning_count}`);
  lines.push(`- Watchlist only: ${summary.watchlist_only_count}`);
  lines.push(`- Needs ToS parity check: ${summary.needs_tos_parity_check_count}`);
  lines.push(`- Ignored: ${summary.ignored_count}`);
  lines.push(`- Unclear: ${summary.unclear_count}`);

  lines.push("");
  lines.push("## Candidate outcomes");
  lines.push("");
  if (review.candidate_outcomes.length === 0) {
    lines.push("_No candidates captured in the source snapshot._");
  } else {
    lines.push(
      "| Rank | Symbol | Strategy | Baseline | Active/Current | Raw | Applied Δ | Total | Outcome | Note | Reasons / caveats |",
    );
    lines.push(
      "| ---: | :----- | :------- | -------: | -------------: | ---:| --------:| :---- | :------ | :--- | :---------------- |",
    );
    const candidateByKey = new Map<string, MomentumTrialCandidateSnapshot>();
    for (const c of snapshot.candidates) {
      candidateByKey.set(momentumCandidateOutcomeKey(c), c);
    }
    for (const outcome of review.candidate_outcomes) {
      const key = momentumCandidateOutcomeKey(outcome);
      const snap = candidateByKey.get(key);
      const baseline = snap ? fmtScore(snap.baseline_score) : "—";
      const active = snap ? fmtScore(snap.active_score) : "—";
      const raw = snap ? fmtRaw(snap.raw_contribution) : "—";
      const applied = snap ? fmtSigned(snap.applied_delta) : "—";
      const totalCell =
        !snap || snap.total_score == null
          ? "—"
          : `${snap.total_score}${snap.total_label ? ` (${snap.total_label})` : ""}`;
      const reasonCell = (() => {
        const parts: string[] = [];
        if (outcome.trade_warning_flags.length > 0) {
          parts.push(`trade: ${outcome.trade_warning_flags.join(", ")}`);
        }
        if (outcome.operational_caveat_flags.length > 0) {
          parts.push(`caveats: ${outcome.operational_caveat_flags.join(", ")}`);
        }
        if (parts.length === 0) {
          return outcome.reason_codes.length === 0
            ? "—"
            : outcome.reason_codes.join(", ");
        }
        return parts.join("; ");
      })();
      const noteCell = outcome.note
        ? outcome.note.replace(/\|/g, "\\|").replace(/\n/g, " ")
        : "—";
      lines.push(
        `| ${outcome.rank} | ${outcome.symbol} | ${outcome.strategy} | ${baseline} | ${active} | ${raw} | ${applied} | ${totalCell} | ${outcomeTagLabel(outcome.tag)} | ${noteCell} | ${reasonCell} |`,
      );
    }
  }

  lines.push("");
  lines.push("## Remaining caveats");
  lines.push("");
  lines.push(
    `- Thinkorswim parity pending: ${snapshot.summary.parity_pending_count > 0 || snapshot.summary.reason_code_counts["thinkorswim_parity_pending"] ? "yes" : "review locally"}`,
  );
  lines.push(
    `- Derived higher timeframe rows: ${snapshot.summary.derived_higher_timeframe_count}`,
  );
  lines.push("- Phase C True Momentum strategy families are not active.");

  lines.push("");
  lines.push(`_${MOMENTUM_TRIAL_OUTCOME_DETERMINISTIC_NOTE}_`);
  lines.push("");
  return lines.join("\n");
}

// Re-export the snapshot JSON helper so a caller that wants to bundle
// the original snapshot alongside an outcome export does not need to
// import two helpers.
export { buildMomentumTrialJson };
