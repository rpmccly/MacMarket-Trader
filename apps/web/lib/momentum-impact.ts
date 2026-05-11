import {
  formatMomentumContribution,
  isMomentumContributionApplied,
  normalizeMomentumRankingMode,
} from "@/lib/momentum-ranking";
import type {
  MomentumRankingContribution,
  MomentumRankingMode,
  QueueCandidate,
} from "@/lib/recommendations";

export type MomentumImpactTone = "good" | "warn" | "bad" | "neutral";

export type MomentumImpactRow = {
  symbol: string;
  strategy: string;
  rank: number;
  mode: MomentumRankingMode;
  enabled: boolean;
  currentScore: number;
  contributionScoreUnits: number;
  shadowContributionScoreUnits: number;
  scoreDelta: number;
  estimatedActiveScore: number;
  totalScore: number | null;
  totalLabel: string | null;
  reasonCodes: string[];
  noTradeWarning: boolean;
  reversalWarning: boolean;
  pullbackSignal: boolean;
  parityPending: boolean;
  directionUnknown: boolean;
  derivedHigherTimeframe: boolean;
  contributionMissing: boolean;
  estimatedRankBefore: number;
  estimatedRankAfter: number;
  estimatedRankDelta: number;
  // Phase B6.1 — operator-tunable scale + applied ranking-score delta.
  activeDeltaScale: number;
  rawTotalContribution: number;
  appliedScoreDelta: number;
  // Phase B6.2 — baseline score before the Momentum delta was applied.
  // Sourced from ``candidate.score_before_momentum`` when present; falls
  // back to ``candidate.score - appliedScoreDelta`` in active mode so
  // older payloads still surface a reasonable baseline.
  baselineScore: number;
};

export type MomentumImpactSummary = {
  candidates_reviewed: number;
  positive_contribution_count: number;
  negative_contribution_count: number;
  zero_contribution_count: number;
  warnings_count: number;
  parity_pending_count: number;
  direction_unknown_count: number;
  contribution_missing_count: number;
  net_estimated_score_delta: number;
  observed_modes: MomentumRankingMode[];
};

const RANKING_SCORE_SCALE = 100; // mirrors MomentumRankingConfig.ranking_score_scale

// Phase B6.1 — fallback when the contribution payload does not carry the
// operator scale (older backend, or off-mode contributions). Mirrors
// ``DEFAULT_ACTIVE_DELTA_SCALE`` in
// ``src/macmarket_trader/recommendation/momentum_ranking.py``.
const DEFAULT_ACTIVE_DELTA_SCALE = 0.35;

function resolveActiveDeltaScale(value: number | null | undefined): number {
  if (value == null || Number.isNaN(value) || !Number.isFinite(value)) {
    return DEFAULT_ACTIVE_DELTA_SCALE;
  }
  if (value < 0 || value > 1) return DEFAULT_ACTIVE_DELTA_SCALE;
  return value;
}

function sanitizeNumber(value: unknown, fallback = 0): number {
  if (value == null) return fallback;
  if (typeof value === "number") {
    if (Number.isNaN(value) || !Number.isFinite(value)) return fallback;
    return value;
  }
  const num = Number(value);
  if (Number.isNaN(num) || !Number.isFinite(num)) return fallback;
  return num;
}

function clampUnit(value: number): number {
  if (Number.isNaN(value) || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function reasonHasDirectionUnknown(codes: string[] | undefined): boolean {
  if (!codes) return false;
  return codes.includes("direction_unknown");
}

function effectiveContributionScoreUnits(
  contribution: MomentumRankingContribution | null | undefined,
  mode: MomentumRankingMode,
): { contribution: number; shadow: number } {
  if (!contribution) return { contribution: 0, shadow: 0 };
  const applied = sanitizeNumber(contribution.total_contribution, 0);
  const shadow = sanitizeNumber(contribution.shadow_contribution, 0);
  if (mode === "active") {
    // In active mode the contribution is already in candidate.score; the
    // "shadow" still reports the bounded score-units value for display so
    // operators can see what was applied.
    const appliedValue = isMomentumContributionApplied(contribution) ? applied : 0;
    return { contribution: appliedValue, shadow: appliedValue };
  }
  if (mode === "shadow") {
    return { contribution: 0, shadow };
  }
  return { contribution: 0, shadow: 0 };
}

/**
 * Estimate the score a candidate would receive in active mode.
 *
 * Rules from Phase B4 prompt:
 * - shadow mode: candidate.score + shadow_contribution / 100, clamped to [0, 1].
 * - active mode: contribution already applied — return candidate.score unchanged.
 * - off / missing / direction-unknown: no movement.
 * - Never returns NaN/inf; never mutates inputs.
 */
export function estimateActiveScore(candidate: QueueCandidate | null | undefined): number {
  if (!candidate) return 0;
  const score = clampUnit(sanitizeNumber(candidate.score, 0));
  const contribution = candidate.momentum_contribution ?? null;
  if (!contribution || contribution.enabled === false) return score;
  const mode = normalizeMomentumRankingMode(contribution.mode);
  if (mode === "off") return score;
  if (reasonHasDirectionUnknown(contribution.reason_codes)) return score;
  // Phase B6.1 — active scores are already published with the scaled
  // delta applied. Don't double-count.
  if (mode === "active") return score;
  if (mode === "shadow") {
    const shadow = sanitizeNumber(contribution.shadow_contribution, 0);
    const scale = resolveActiveDeltaScale(contribution.active_delta_scale);
    return clampUnit(score + (shadow / RANKING_SCORE_SCALE) * scale);
  }
  return score;
}

/**
 * Build review rows from in-memory candidates. Never refetches data, never
 * mutates inputs. Estimated-rank-after is computed by sorting a snapshot of
 * the estimated active scores, so operators can see how ranks would shift
 * if active mode were enabled — without actually changing the queue.
 */
export function buildMomentumImpactRows(
  candidates: ReadonlyArray<QueueCandidate> | null | undefined,
): MomentumImpactRow[] {
  if (!candidates || candidates.length === 0) return [];

  // Snapshot estimated scores so rank-after can be derived without mutating
  // anything. The "before" rank uses the candidate's published rank to keep
  // parity with the live queue display; "after" derives from estimated
  // active scores.
  const estimatedScores: Array<{ symbol: string; strategy: string; rank: number; estimated: number }> = [];
  for (const candidate of candidates) {
    if (!candidate || typeof candidate !== "object") continue;
    estimatedScores.push({
      symbol: candidate.symbol,
      strategy: candidate.strategy,
      rank: sanitizeNumber(candidate.rank, 0),
      estimated: estimateActiveScore(candidate),
    });
  }
  // Stable sort: by estimated DESC, breaking ties by original rank ASC.
  const sortedForRank = estimatedScores
    .map((row, idx) => ({ ...row, originalIndex: idx }))
    .sort((a, b) => {
      if (b.estimated !== a.estimated) return b.estimated - a.estimated;
      if (a.rank !== b.rank) return a.rank - b.rank;
      return a.originalIndex - b.originalIndex;
    });
  const rankAfterByKey = new Map<string, number>();
  sortedForRank.forEach((entry, idx) => {
    rankAfterByKey.set(`${entry.symbol}::${entry.strategy}::${entry.originalIndex}`, idx + 1);
  });

  const out: MomentumImpactRow[] = [];
  candidates.forEach((candidate, idx) => {
    if (!candidate || typeof candidate !== "object") return;
    const contribution = candidate.momentum_contribution ?? null;
    const mode = contribution
      ? normalizeMomentumRankingMode(contribution.mode)
      : "off";
    const enabled = !!contribution && contribution.enabled !== false;
    const { contribution: contributionScoreUnits, shadow: shadowContributionScoreUnits } =
      effectiveContributionScoreUnits(contribution, mode);
    const currentScore = clampUnit(sanitizeNumber(candidate.score, 0));
    const estimatedActiveScore = estimateActiveScore(candidate);
    const scoreDelta = estimatedActiveScore - currentScore;
    const reasonCodes = (contribution?.reason_codes ?? []).slice();
    const contributionMissing = !contribution || contribution.enabled === false;
    if (contributionMissing && !reasonCodes.includes("momentum_contribution_missing")) {
      reasonCodes.push("momentum_contribution_missing");
    }
    const rankBefore = sanitizeNumber(candidate.rank, idx + 1);
    const rankAfter =
      rankAfterByKey.get(`${candidate.symbol}::${candidate.strategy}::${idx}`) ?? rankBefore;
    const estimatedRankDelta = rankAfter === 0 ? 0 : rankBefore - rankAfter; // positive = moved up

    // Phase B6.2 — single fallback chain for the applied score delta.
    // Active rows must surface the actual scaled delta even when one of
    // the payload fields is missing on the wire.
    const scaleForRow = resolveActiveDeltaScale(contribution?.active_delta_scale);
    const rawForRow = sanitizeNumber(
      contribution?.raw_total_contribution ?? contribution?.shadow_contribution,
      0,
    );
    let appliedScoreDelta: number;
    if (mode === "active") {
      const candidateDelta = candidate.momentum_score_delta;
      const contributionDelta = contribution?.applied_score_delta;
      if (candidateDelta != null && Number.isFinite(candidateDelta) && candidateDelta !== 0) {
        appliedScoreDelta = sanitizeNumber(candidateDelta, 0);
      } else if (
        contributionDelta != null &&
        Number.isFinite(contributionDelta) &&
        contributionDelta !== 0
      ) {
        appliedScoreDelta = sanitizeNumber(contributionDelta, 0);
      } else {
        appliedScoreDelta = (rawForRow / RANKING_SCORE_SCALE) * scaleForRow;
      }
    } else {
      appliedScoreDelta = sanitizeNumber(contribution?.applied_score_delta, 0);
    }
    // Phase B6.2 — baseline score before Momentum was applied. Prefer the
    // candidate-level field that Phase B6 added on the backend; fall
    // back to ``current_score - appliedScoreDelta`` for older payloads
    // so the impact review can still show a sensible baseline column.
    const baselineFromCandidate = sanitizeNumber(candidate.score_before_momentum, Number.NaN);
    const baselineScore =
      mode === "active"
        ? Number.isFinite(baselineFromCandidate)
          ? clampUnit(baselineFromCandidate)
          : clampUnit(currentScore - appliedScoreDelta)
        : currentScore;

    out.push({
      symbol: candidate.symbol,
      strategy: candidate.strategy,
      rank: rankBefore,
      mode,
      enabled,
      currentScore,
      contributionScoreUnits,
      shadowContributionScoreUnits,
      scoreDelta,
      estimatedActiveScore,
      totalScore: contribution?.total_score ?? null,
      totalLabel: contribution?.total_label ?? null,
      reasonCodes,
      noTradeWarning: !!contribution?.no_trade_warning,
      reversalWarning: !!contribution?.reversal_warning,
      pullbackSignal: !!contribution?.pullback_signal,
      parityPending: reasonCodes.includes("thinkorswim_parity_pending"),
      directionUnknown: reasonHasDirectionUnknown(reasonCodes),
      derivedHigherTimeframe: reasonCodes.includes("derived_higher_timeframe"),
      contributionMissing,
      estimatedRankBefore: rankBefore,
      estimatedRankAfter: rankAfter,
      estimatedRankDelta,
      activeDeltaScale: scaleForRow,
      rawTotalContribution: rawForRow,
      appliedScoreDelta,
      baselineScore,
    });
  });
  return out;
}

export function summarizeMomentumImpact(rows: ReadonlyArray<MomentumImpactRow>): MomentumImpactSummary {
  const modes = new Set<MomentumRankingMode>();
  let positive = 0;
  let negative = 0;
  let zero = 0;
  let warnings = 0;
  let parityPending = 0;
  let directionUnknown = 0;
  let contributionMissing = 0;
  let netDelta = 0;
  for (const row of rows) {
    modes.add(row.mode);
    const shadow = row.shadowContributionScoreUnits;
    if (shadow > 0) positive += 1;
    else if (shadow < 0) negative += 1;
    else zero += 1;
    if (row.noTradeWarning || row.reversalWarning) warnings += 1;
    if (row.parityPending) parityPending += 1;
    if (row.directionUnknown) directionUnknown += 1;
    if (row.contributionMissing) contributionMissing += 1;
    netDelta += row.scoreDelta;
  }
  return {
    candidates_reviewed: rows.length,
    positive_contribution_count: positive,
    negative_contribution_count: negative,
    zero_contribution_count: zero,
    warnings_count: warnings,
    parity_pending_count: parityPending,
    direction_unknown_count: directionUnknown,
    contribution_missing_count: contributionMissing,
    net_estimated_score_delta: roundFinite(netDelta, 6),
    observed_modes: Array.from(modes),
  };
}

function roundFinite(value: number, digits: number): number {
  if (!Number.isFinite(value) || Number.isNaN(value)) return 0;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

export function estimateActiveRankDelta(rows: ReadonlyArray<MomentumImpactRow>): {
  upgraded: number;
  downgraded: number;
  unchanged: number;
} {
  let upgraded = 0;
  let downgraded = 0;
  let unchanged = 0;
  for (const row of rows) {
    if (row.estimatedRankDelta > 0) upgraded += 1;
    else if (row.estimatedRankDelta < 0) downgraded += 1;
    else unchanged += 1;
  }
  return { upgraded, downgraded, unchanged };
}

export function momentumImpactTone(row: MomentumImpactRow): MomentumImpactTone {
  if (row.reversalWarning || row.noTradeWarning) return "warn";
  if (!row.enabled || row.mode === "off") return "neutral";
  if (row.shadowContributionScoreUnits >= 5) return "good";
  if (row.shadowContributionScoreUnits <= -5) return "bad";
  if (row.shadowContributionScoreUnits !== 0) return "warn";
  return "neutral";
}

export type MomentumImpactSortMode =
  | "rank_asc"
  | "estimated_score_desc"
  | "score_delta_desc"
  | "warning_first";

export function sortMomentumImpactRows(
  rows: ReadonlyArray<MomentumImpactRow>,
  mode: MomentumImpactSortMode,
): MomentumImpactRow[] {
  // Always returns a fresh array; never mutates `rows`.
  const copy = [...rows];
  switch (mode) {
    case "estimated_score_desc":
      return copy.sort((a, b) => b.estimatedActiveScore - a.estimatedActiveScore);
    case "score_delta_desc":
      return copy.sort((a, b) => b.scoreDelta - a.scoreDelta);
    case "warning_first":
      return copy.sort((a, b) => {
        const aWarn = a.reversalWarning || a.noTradeWarning ? 1 : 0;
        const bWarn = b.reversalWarning || b.noTradeWarning ? 1 : 0;
        if (aWarn !== bWarn) return bWarn - aWarn;
        return a.rank - b.rank;
      });
    case "rank_asc":
    default:
      return copy.sort((a, b) => a.rank - b.rank);
  }
}

export const MOMENTUM_IMPACT_DETERMINISTIC_NOTE =
  "This review estimates impact only. It does not change queue sorting, approval, sizing, or order routing.";

export function formatScoreUnit(value: number | null | undefined): string {
  return formatMomentumContribution(value);
}

export function formatUnitScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const rounded = Math.round(Number(value) * 10000) / 10000;
  return rounded.toFixed(3);
}

export function formatRankDelta(delta: number): string {
  if (delta === 0 || Number.isNaN(delta)) return "0";
  return delta > 0 ? `▲ ${Math.abs(delta)}` : `▼ ${Math.abs(delta)}`;
}
