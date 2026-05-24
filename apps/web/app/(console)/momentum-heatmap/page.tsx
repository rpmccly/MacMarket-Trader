"use client";

import { type CSSProperties, useEffect, useMemo, useState } from "react";

import { Card, EmptyState, ErrorState, InlineFeedback, PageHeader, StatusBadge } from "@/components/operator-ui";
import {
  cloneDefaultMomentumHeatmapScoreRanges,
  MOMENTUM_HEATMAP_COLOR_STORAGE_KEY,
  momentumHeatmapScoreRange,
  normalizeMomentumHeatmapScoreRanges,
  readableTextColor,
  type MomentumHeatmapScoreRange,
} from "@/lib/momentum-heatmap-colors";
import {
  DEFAULT_MOMENTUM_HEATMAP_CATEGORIES,
  MOMENTUM_HEATMAP_STORAGE_KEY,
  type MomentumHeatmapCategoryConfig,
  type MomentumHeatmapRowConfig,
} from "@/lib/momentum-heatmap-defaults";
import {
  addMomentumHeatmapRow,
  chunkMomentumHeatmapCategory,
  createMomentumHeatmapProfile,
  deleteMomentumHeatmapProfile,
  downloadMomentumHeatmapCsv,
  duplicateMomentumHeatmapProfile,
  emailMomentumHeatmapReport,
  fetchLatestMomentumHeatmapSnapshot,
  fetchMomentumHeatmapProfile,
  fetchMomentumHeatmapSchedule,
  generateMomentumHeatmapReportPreview,
  mergeMomentumHeatmapResponse,
  refreshMomentumHeatmapSnapshot,
  removeMomentumHeatmapRow,
  resetMomentumHeatmapProfile,
  saveMomentumHeatmapProfile,
  saveMomentumHeatmapSchedule,
  type MomentumHeatmapCategorySummary,
  type MomentumHeatmapDelta,
  type MomentumHeatmapRequestCategory,
  type MomentumHeatmapResponse,
  type MomentumHeatmapResponseCategory,
  type MomentumHeatmapResponseRow,
  type MomentumHeatmapSchedulePreferences,
  type MomentumHeatmapScoreCell,
  type MomentumHeatmapServerProfile,
  type MomentumHeatmapSqueezeCell,
} from "@/lib/momentum-heatmap-api";
import { squeezeProStateLabel } from "@/lib/squeeze-pro";
import type { SupportedTimeframe } from "@/lib/timeframes";

const WORKBOOK_TIMEFRAME_LABELS: Array<{ key: SupportedTimeframe; label: string }> = [
  { key: "1W", label: "Weekly" },
  { key: "1D", label: "Daily" },
  { key: "4H", label: "4HR" },
  { key: "1H", label: "1HR" },
  { key: "30M", label: "30M" },
];

const SORT_OPTIONS = [
  ["workbook", "Workbook/default order"],
  ["symbol-az", "Symbol A-Z"],
  ["strength-desc", "Strength % high to low"],
  ["strength-asc", "Strength % low to high"],
  ["long-desc", "Long-Term Score high to low"],
  ["long-asc", "Long-Term Score low to high"],
  ["short-desc", "Short-Term Score high to low"],
  ["short-asc", "Short-Term Score low to high"],
  ["short-minus-long-desc", "Short-Term minus Long-Term high to low"],
  ["unsupported-last", "Unsupported/unavailable last"],
] as const;

type FeedbackState = { state: "idle" | "loading" | "success" | "error"; message?: string };
type FilterMode = "all" | "bullish" | "bearish" | "pullback" | "reversal";
type SecondaryPanel = "symbols" | "colors" | "report" | "schedule" | null;
type RefreshProgress = {
  currentCategoryLabel: string | null;
  completedCategories: number;
  totalCategories: number;
  completedRows: number;
  totalRows: number;
  failedCategories: number;
};

function cloneDefaultCategories(): MomentumHeatmapCategoryConfig[] {
  return DEFAULT_MOMENTUM_HEATMAP_CATEGORIES.map((category) => ({
    ...category,
    included: true,
    collapsed: false,
    rows: category.rows.map((row) => ({ ...row, enabled: row.enabled ?? true })),
  }));
}

function toCategoryConfig(category: MomentumHeatmapCategoryConfig): MomentumHeatmapCategoryConfig {
  return {
    categoryId: category.categoryId,
    categoryLabel: category.categoryLabel,
    included: category.included !== false,
    collapsed: category.collapsed === true,
    rows: (category.rows ?? []).map((row, index) => ({
      id: row.id,
      categoryId: row.categoryId ?? category.categoryId,
      categoryLabel: row.categoryLabel ?? category.categoryLabel,
      symbol: row.symbol,
      displayName: row.displayName || row.providerSymbol || row.symbol,
      providerSymbol: (row.providerSymbol || row.symbol).trim().toUpperCase(),
      originalSymbol: row.originalSymbol ?? row.symbol,
      workbookOrder: typeof row.workbookOrder === "number" ? row.workbookOrder : index,
      enabled: row.enabled !== false,
      userAdded: row.userAdded === true,
      unsupported: row.unsupported === true,
      unsupportedReason: row.unsupportedReason ?? null,
      notes: row.notes ?? null,
    })),
  };
}

function profileCategories(profile: MomentumHeatmapServerProfile): MomentumHeatmapCategoryConfig[] {
  return (profile.categories ?? []).map((category) => toCategoryConfig(category as MomentumHeatmapCategoryConfig));
}

function formatScore(value: number | null | undefined, suffix = ""): string {
  if (value == null || Number.isNaN(value)) return "--";
  return `${Math.round(value)}${suffix}`;
}

function hasNumericDelta(delta: MomentumHeatmapDelta | undefined): boolean {
  return (
    typeof delta?.strength_percent === "number" ||
    typeof delta?.long_term_score === "number" ||
    typeof delta?.short_term_score === "number"
  );
}

function hasAnyNumericDelta(deltas: Record<string, MomentumHeatmapDelta>): boolean {
  return Object.values(deltas).some((delta) => hasNumericDelta(delta));
}

function scoreTitle(cell: MomentumHeatmapScoreCell | null | undefined): string | undefined {
  if (!cell) return undefined;
  const parts = [
    cell.stale ? "stale previous value" : cell.status,
    cell.reason,
    cell.data_source ? `source: ${cell.data_source}` : null,
    cell.fallback_mode ? "fallback mode" : null,
    cell.as_of ? `as of ${cell.as_of}` : null,
  ].filter(Boolean);
  return parts.join(" | ");
}

function squeezeTitle(cell: MomentumHeatmapSqueezeCell | null | undefined): string | undefined {
  if (!cell) return undefined;
  const timeframeDetails = Object.entries(cell.timeframes ?? {})
    .map(([timeframe, detail]) => {
      const bits = [
        timeframe,
        detail.value ?? detail.state ?? detail.status,
        detail.reason,
        detail.oscillator_value != null ? `osc ${Number(detail.oscillator_value).toFixed(2)}` : null,
        detail.as_of ? `as of ${detail.as_of}` : null,
      ].filter(Boolean);
      return bits.join(": ");
    })
    .filter(Boolean);
  return [cell.value ?? cell.status, cell.reason, cell.as_of ? `as of ${cell.as_of}` : null, ...timeframeDetails]
    .filter(Boolean)
    .join(" | ");
}

function SqueezeCell({ cell }: { cell: MomentumHeatmapSqueezeCell | null | undefined }) {
  const state = cell?.status === "ok" ? cell.state ?? "none" : null;
  const label = cell?.status === "ok" ? cell.value ?? squeezeProStateLabel(state) : "Unavailable";
  return (
    <td className="hm-squeeze-cell" title={squeezeTitle(cell) ?? "Squeeze Pro unavailable"}>
      <span className={`hm-squeeze-badge hm-squeeze-${state ?? "unavailable"}`}>
        {label}
      </span>
    </td>
  );
}

function scoreStyle(value: number | null | undefined, ranges: MomentumHeatmapScoreRange[]): CSSProperties | undefined {
  const range = momentumHeatmapScoreRange(value, ranges);
  if (!range) return undefined;
  return {
    "--hm-score-bg": range.color,
    "--hm-score-fg": readableTextColor(range.color),
  } as CSSProperties;
}

function HeatmapScoreCell({
  cell,
  colorRanges,
  showStale,
}: {
  cell: MomentumHeatmapScoreCell | null | undefined;
  colorRanges: MomentumHeatmapScoreRange[];
  showStale: boolean;
}) {
  const value = cell?.status === "ok" ? cell.value : null;
  const className = value == null ? "hm-score-unavailable" : "hm-score-custom";
  return (
    <td className={`hm-cell hm-score-cell ${className} ${cell?.stale ? "is-stale" : ""}`} title={scoreTitle(cell)} style={scoreStyle(value, colorRanges)}>
      {value == null ? "--" : formatScore(value)}
      {showStale && cell?.stale ? <span className="hm-delta"> stale</span> : null}
    </td>
  );
}

function DerivedScoreCell({
  value,
  title,
  colorRanges,
  suffix = "",
}: {
  value: number | null | undefined;
  title: string;
  colorRanges: MomentumHeatmapScoreRange[];
  suffix?: string;
}) {
  const className = value == null ? "hm-score-unavailable" : "hm-score-custom";
  return (
    <td className={`hm-cell hm-score-cell ${className}`} title={title} style={scoreStyle(value, colorRanges)}>
      {formatScore(value, suffix)}
    </td>
  );
}

function DeltaCell({
  value,
  delta,
  hasPreviousSnapshot,
}: {
  value: number | null | undefined;
  delta: MomentumHeatmapDelta | undefined;
  hasPreviousSnapshot: boolean;
}) {
  const deltaMeta = delta as (MomentumHeatmapDelta & { new?: boolean; reason?: string }) | undefined;
  if (!hasPreviousSnapshot) {
    return <td className="hm-cell hm-score-unavailable" title="Deltas need two successful snapshots.">n/a</td>;
  }
  if (delta?.became_available || deltaMeta?.new) {
    return <td className="hm-cell hm-delta-new" title={deltaMeta?.reason ?? "New row has no prior snapshot value."}>new</td>;
  }
  if (delta?.became_unavailable) {
    return <td className="hm-cell hm-score-unavailable" title="Current row became unavailable; delta is not calculated.">n/a</td>;
  }
  if (value == null || Number.isNaN(value)) {
    return <td className="hm-cell hm-score-unavailable" title={deltaMeta?.reason ?? "Prior or current value is unavailable."}>--</td>;
  }
  const className = value > 0 ? "hm-delta-positive" : value < 0 ? "hm-delta-negative" : "hm-muted";
  return <td className={`hm-cell ${className}`}>{value > 0 ? "+" : ""}{value.toFixed(1)}</td>;
}

function resultRowById(category: MomentumHeatmapResponseCategory | undefined): Map<string, MomentumHeatmapResponseRow> {
  return new Map((category?.rows ?? []).map((row) => [row.id, row]));
}

function rowReason(row: MomentumHeatmapResponseRow | undefined): string | null {
  const cells = Object.values(row?.scores ?? {});
  if (cells.length === 0) return null;
  const problem = cells.find((cell) => cell.status !== "ok" && cell.reason);
  if (!problem?.reason) return null;
  const prefix = cells.every((cell) => cell.status === "unsupported") ? "Unsupported" : "Unavailable";
  return `${prefix}: ${problem.reason}`;
}

function toRequestCategory(category: MomentumHeatmapCategoryConfig): MomentumHeatmapRequestCategory {
  return {
    categoryId: category.categoryId,
    categoryLabel: category.categoryLabel,
    rows: category.rows
      .filter((row) => row.enabled !== false)
      .map((row) => ({
        id: row.id,
        symbol: row.symbol,
        displayName: row.displayName,
        providerSymbol: row.providerSymbol,
      })),
  };
}

function cellValues(row: MomentumHeatmapResponseRow | undefined): number[] {
  if (!row) return [];
  return WORKBOOK_TIMEFRAME_LABELS.flatMap(({ key }) => {
    const cell = row.scores?.[key];
    return cell?.status === "ok" && typeof cell.value === "number" ? [cell.value] : [];
  });
}

function isUnavailable(row: MomentumHeatmapResponseRow | undefined): boolean {
  if (!row) return true;
  const cells = Object.values(row.scores ?? {});
  return cells.length === 0 || cells.every((cell) => cell.status !== "ok");
}

function rowMatchesFilter(row: MomentumHeatmapRowConfig, result: MomentumHeatmapResponseRow | undefined, filters: {
  search: string;
  filterMode: FilterMode;
  supportedOnly: boolean;
  hideUnavailable: boolean;
  strengthMin: string;
  strengthMax: string;
  changedOnly: boolean;
  deltaDirection: "all" | "positive" | "negative";
}, delta: MomentumHeatmapDelta | undefined): boolean {
  const search = filters.search.trim().toUpperCase();
  if (search && !`${row.displayName} ${row.providerSymbol} ${row.symbol}`.toUpperCase().includes(search)) return false;
  if (filters.supportedOnly && row.unsupported) return false;
  if (filters.hideUnavailable && isUnavailable(result)) return false;
  const strength = result?.strength_percent;
  if (filters.strengthMin.trim() && strength != null && strength < Number(filters.strengthMin)) return false;
  if (filters.strengthMax.trim() && strength != null && strength > Number(filters.strengthMax)) return false;
  if (filters.changedOnly && delta?.strength_percent == null) return false;
  if (filters.deltaDirection === "positive" && !((delta?.strength_percent ?? 0) > 0)) return false;
  if (filters.deltaDirection === "negative" && !((delta?.strength_percent ?? 0) < 0)) return false;
  const values = cellValues(result);
  const positiveCount = values.filter((value) => value > 0).length;
  const negativeCount = values.filter((value) => value < 0).length;
  if (filters.filterMode === "bullish") return values.length > 0 && positiveCount >= Math.max(1, values.length - 1) && (strength ?? 0) > 25;
  if (filters.filterMode === "bearish") return values.length > 0 && negativeCount >= Math.max(1, values.length - 1) && (strength ?? 0) < -25;
  if (filters.filterMode === "pullback") return (result?.long_term_score ?? -999) > 25 && (result?.short_term_score ?? 999) < (result?.long_term_score ?? 0);
  if (filters.filterMode === "reversal") return (result?.long_term_score ?? 999) < 0 && ((delta?.strength_percent ?? 0) > 0 || (result?.short_term_score ?? -999) > (result?.long_term_score ?? 0));
  return true;
}

function sortRows(
  rows: MomentumHeatmapRowConfig[],
  rowResults: Map<string, MomentumHeatmapResponseRow>,
  sortMode: string,
): MomentumHeatmapRowConfig[] {
  const sortable = [...rows];
  const value = (row: MomentumHeatmapRowConfig, key: "strength_percent" | "long_term_score" | "short_term_score") => rowResults.get(row.id)?.[key] ?? null;
  const score = (row: MomentumHeatmapRowConfig, key: "strength_percent" | "long_term_score" | "short_term_score") => value(row, key) ?? -99999;
  if (sortMode === "symbol-az") return sortable.sort((a, b) => a.displayName.localeCompare(b.displayName));
  if (sortMode === "strength-desc") return sortable.sort((a, b) => score(b, "strength_percent") - score(a, "strength_percent"));
  if (sortMode === "strength-asc") return sortable.sort((a, b) => score(a, "strength_percent") - score(b, "strength_percent"));
  if (sortMode === "long-desc") return sortable.sort((a, b) => score(b, "long_term_score") - score(a, "long_term_score"));
  if (sortMode === "long-asc") return sortable.sort((a, b) => score(a, "long_term_score") - score(b, "long_term_score"));
  if (sortMode === "short-desc") return sortable.sort((a, b) => score(b, "short_term_score") - score(a, "short_term_score"));
  if (sortMode === "short-asc") return sortable.sort((a, b) => score(a, "short_term_score") - score(b, "short_term_score"));
  if (sortMode === "short-minus-long-desc") {
    return sortable.sort((a, b) => ((value(b, "short_term_score") ?? 0) - (value(b, "long_term_score") ?? 0)) - ((value(a, "short_term_score") ?? 0) - (value(a, "long_term_score") ?? 0)));
  }
  if (sortMode === "unsupported-last") return sortable.sort((a, b) => Number(isUnavailable(rowResults.get(a.id))) - Number(isUnavailable(rowResults.get(b.id))));
  return sortable.sort((a, b) => (a.workbookOrder ?? 0) - (b.workbookOrder ?? 0));
}

export default function MomentumHeatmapPage() {
  const [profile, setProfile] = useState<MomentumHeatmapServerProfile | null>(null);
  const [profiles, setProfiles] = useState<MomentumHeatmapServerProfile[]>([]);
  const [categories, setCategories] = useState<MomentumHeatmapCategoryConfig[]>(() => cloneDefaultCategories());
  const [selectedCategoryId, setSelectedCategoryId] = useState(DEFAULT_MOMENTUM_HEATMAP_CATEGORIES[0]?.categoryId ?? "");
  const [symbolInput, setSymbolInput] = useState("");
  const [labelInput, setLabelInput] = useState("");
  const [secondaryPanel, setSecondaryPanel] = useState<SecondaryPanel>(null);
  const [colorRanges, setColorRanges] = useState<MomentumHeatmapScoreRange[]>(() => cloneDefaultMomentumHeatmapScoreRanges());
  const [sortMode, setSortMode] = useState("workbook");
  const [search, setSearch] = useState("");
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [supportedOnly, setSupportedOnly] = useState(false);
  const [hideUnavailable, setHideUnavailable] = useState(false);
  const [strengthMin, setStrengthMin] = useState("");
  const [strengthMax, setStrengthMax] = useState("");
  const [changedOnly, setChangedOnly] = useState(false);
  const [deltaDirection, setDeltaDirection] = useState<"all" | "positive" | "negative">("all");
  const [showDeltas, setShowDeltas] = useState(true);
  const [schedule, setSchedule] = useState<MomentumHeatmapSchedulePreferences | null>(null);
  const [timingSuggestions, setTimingSuggestions] = useState<Array<{ time: string; label: string; note: string }>>([]);
  const [emailRecipients, setEmailRecipients] = useState("");
  const [hydrated, setHydrated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [refreshProgress, setRefreshProgress] = useState<RefreshProgress | null>(null);
  const [refreshingCategoryId, setRefreshingCategoryId] = useState<string | null>(null);
  const [categoryErrors, setCategoryErrors] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState<FeedbackState>({ state: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [migrationWarning, setMigrationWarning] = useState<string | null>(null);
  const [heatmap, setHeatmap] = useState<MomentumHeatmapResponse | null>(null);
  const [latestSnapshotId, setLatestSnapshotId] = useState<string | undefined>();
  const [lastSnapshotMessage, setLastSnapshotMessage] = useState<string | null>(null);
  const [deltas, setDeltas] = useState<Record<string, MomentumHeatmapDelta>>({});
  const [hasPreviousSnapshot, setHasPreviousSnapshot] = useState(false);
  const [deltaNotice, setDeltaNotice] = useState<string | null>(null);
  const [categorySummaries, setCategorySummaries] = useState<MomentumHeatmapCategorySummary[]>([]);
  const [reportPreviewHtml, setReportPreviewHtml] = useState<string | null>(null);

  function activeProfileId(nextProfile = profile): string | undefined {
    return nextProfile?.profileId ?? nextProfile?.id;
  }

  function applyProfile(nextProfile: MomentumHeatmapServerProfile, nextSchedule?: MomentumHeatmapSchedulePreferences | null) {
    const nextCategories = profileCategories(nextProfile);
    const filters = (nextProfile.viewSettings?.filters ?? {}) as Record<string, unknown>;
    setProfile(nextProfile);
    setCategories(nextCategories);
    setSelectedCategoryId(nextCategories[0]?.categoryId ?? selectedCategoryId);
    setColorRanges(normalizeMomentumHeatmapScoreRanges(nextProfile.colorRanges));
    setSortMode(nextProfile.viewSettings?.sort ?? "workbook");
    setShowDeltas(typeof nextProfile.viewSettings?.showDeltas === "boolean" ? nextProfile.viewSettings.showDeltas : true);
    setSearch(typeof filters.search === "string" ? filters.search : "");
    setSupportedOnly(filters.supportedOnly === true);
    setHideUnavailable(filters.hideUnavailable === true);
    setFilterMode(typeof filters.alignment === "string" ? filters.alignment as FilterMode : "all");
    setStrengthMin(filters.strengthMin == null ? "" : String(filters.strengthMin));
    setStrengthMax(filters.strengthMax == null ? "" : String(filters.strengthMax));
    setChangedOnly(filters.changedOnly === true);
    setDeltaDirection(filters.positiveDeltaOnly === true ? "positive" : filters.negativeDeltaOnly === true ? "negative" : "all");
    if (nextSchedule) setSchedule(nextSchedule);
  }

  async function loadSnapshotAndScheduleForProfile(profileId: string | undefined) {
    const latest = await fetchLatestMomentumHeatmapSnapshot(profileId).catch(() => null);
    if (latest?.snapshot?.payload) {
      setHeatmap(latest.snapshot.payload);
      setLatestSnapshotId(latest.snapshot.id);
      setCategorySummaries(latest.snapshot.categorySummaries ?? []);
      setLastSnapshotMessage(latest.message);
      setHasPreviousSnapshot(Boolean(latest.previousSnapshot));
      setDeltas(latest.deltas ?? {});
      setDeltaNotice(latest.previousSnapshot ? (hasAnyNumericDelta(latest.deltas ?? {}) ? null : "No comparable numeric deltas are available for this snapshot.") : "Deltas need two successful snapshots.");
    } else {
      setHeatmap(null);
      setLatestSnapshotId(undefined);
      setCategorySummaries([]);
      setLastSnapshotMessage(latest?.message ?? "No Momentum Heatmap snapshot stored yet.");
      setHasPreviousSnapshot(false);
      setDeltas({});
      setDeltaNotice("Deltas need two successful snapshots.");
    }
    const schedulePayload = await fetchMomentumHeatmapSchedule(profileId).catch(() => null);
    if (schedulePayload) {
      setSchedule(schedulePayload.schedulePreferences);
      setTimingSuggestions(schedulePayload.timingSuggestions ?? []);
    }
  }

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        // localStorage key: macmarket-momentum-heatmap-symbols-v1
        const localSymbolRaw = window.localStorage.getItem(MOMENTUM_HEATMAP_STORAGE_KEY);
        // localStorage key: macmarket-momentum-heatmap-colors-v1
        const localColorRaw = window.localStorage.getItem(MOMENTUM_HEATMAP_COLOR_STORAGE_KEY);
        const server = await fetchMomentumHeatmapProfile();
        if (!active) return;
        let nextProfile = server.profile;

        if (nextProfile.isDefaultSeed && (localSymbolRaw || localColorRaw)) {
          setMigrationWarning(
            "Browser-local Momentum Heatmap settings were found but not automatically imported, so another account cannot overwrite this server profile. Server profile remains the source of truth.",
          );
        }

        setProfiles(server.profiles ?? [nextProfile]);
        applyProfile(nextProfile, server.schedulePreferences ?? null);
        await loadSnapshotAndScheduleForProfile(activeProfileId(nextProfile));
        if (!active) return;
      } catch (err) {
        if (!active) return;
        setMigrationWarning("Server heatmap profile unavailable. Using browser-local/default settings as an emergency fallback.");
        try {
          const raw = window.localStorage.getItem(MOMENTUM_HEATMAP_STORAGE_KEY);
          const colorRaw = window.localStorage.getItem(MOMENTUM_HEATMAP_COLOR_STORAGE_KEY);
          if (raw) setCategories((JSON.parse(raw) as MomentumHeatmapCategoryConfig[]).map(toCategoryConfig));
          if (colorRaw) setColorRanges(normalizeMomentumHeatmapScoreRanges(JSON.parse(colorRaw)));
        } catch {
          setError("Saved heatmap settings were unreadable. Defaults are loaded for this browser.");
        }
        setFeedback({ state: "error", message: err instanceof Error ? err.message : "Server heatmap profile load failed." });
      } finally {
        if (active) setHydrated(true);
      }
    }
    void load();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resultCategories = useMemo(
    () => new Map((heatmap?.categories ?? []).map((category) => [category.categoryId, category])),
    [heatmap],
  );

  const includedCategories = useMemo(
    () => categories.filter((category) => category.included !== false),
    [categories],
  );

  const hasComparableDeltas = useMemo(() => hasAnyNumericDelta(deltas), [deltas]);
  const actionsDisabled = loading || reporting || !hydrated;

  function persistProfile(nextCategories = categories, nextRanges = colorRanges, nextViewPatch: Record<string, unknown> = {}) {
    if (!profile) {
      if (hydrated) {
        window.localStorage.setItem(MOMENTUM_HEATMAP_STORAGE_KEY, JSON.stringify(nextCategories));
        window.localStorage.setItem(MOMENTUM_HEATMAP_COLOR_STORAGE_KEY, JSON.stringify(nextRanges));
      }
      return;
    }
    const nextProfile = {
      ...profile,
      categories: nextCategories,
      colorRanges: nextRanges,
      viewSettings: {
        ...(profile.viewSettings ?? {}),
        sort: sortMode,
        showDeltas,
        ...nextViewPatch,
      },
    };
    setProfile(nextProfile);
    setProfiles((current) => current.map((item) => (activeProfileId(item) === activeProfileId(nextProfile) ? nextProfile : item)));
    void saveMomentumHeatmapProfile(nextProfile).then((saved) => {
      setProfiles(saved.profiles ?? [saved.profile]);
      setProfile(saved.profile);
    }).catch((err) => {
      setMigrationWarning("Server profile save failed. Latest changes are retained in this browser until the next successful save.");
      window.localStorage.setItem(MOMENTUM_HEATMAP_STORAGE_KEY, JSON.stringify(nextCategories));
      window.localStorage.setItem(MOMENTUM_HEATMAP_COLOR_STORAGE_KEY, JSON.stringify(nextRanges));
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Server profile save failed." });
    });
  }

  function updateCategory(categoryId: string, patch: Partial<MomentumHeatmapCategoryConfig>) {
    const next = categories.map((category) => category.categoryId === categoryId ? { ...category, ...patch } : category);
    setCategories(next);
    persistProfile(next);
  }

  function updateColorRange(id: string, patch: Partial<MomentumHeatmapScoreRange>) {
    setColorRanges((current) => current.map((range) => (range.id === id ? { ...range, ...patch } : range)));
  }

  function panelButton(panel: Exclude<SecondaryPanel, null>, label: string) {
    return (
      <button
        type="button"
        className={secondaryPanel === panel ? "op-btn op-btn-secondary" : "op-btn op-btn-ghost"}
        onClick={() => setSecondaryPanel((current) => (current === panel ? null : panel))}
        aria-expanded={secondaryPanel === panel}
      >
        {label}
      </button>
    );
  }

  async function switchProfile(profileId: string) {
    if (!profileId || profileId === activeProfileId()) return;
    setLoading(true);
    setReportPreviewHtml(null);
    setFeedback({ state: "loading", message: "Loading selected Momentum Heatmap view." });
    try {
      const payload = await fetchMomentumHeatmapProfile(profileId);
      setProfiles(payload.profiles ?? [payload.profile]);
      applyProfile(payload.profile, payload.schedulePreferences ?? null);
      await loadSnapshotAndScheduleForProfile(activeProfileId(payload.profile));
      setFeedback({ state: "success", message: `Loaded ${payload.profile.name}. Refresh to update when ready.` });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Could not load selected view." });
    } finally {
      setLoading(false);
    }
  }

  async function createView() {
    const name = window.prompt("Name the new Momentum Heatmap view", "Custom Research View")?.trim();
    if (!name) return;
    setFeedback({ state: "loading", message: "Creating Momentum Heatmap view." });
    try {
      const payload = await createMomentumHeatmapProfile({
        name,
        description: "User-created heatmap view.",
        categories,
        colorRanges,
        viewSettings: profile?.viewSettings,
        reportPreferences: profile?.reportPreferences,
      });
      setProfiles(payload.profiles ?? [payload.profile]);
      applyProfile(payload.profile, payload.schedulePreferences ?? null);
      await loadSnapshotAndScheduleForProfile(activeProfileId(payload.profile));
      setFeedback({ state: "success", message: `${payload.profile.name} created. It will not auto-refresh until you choose refresh.` });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Could not create view." });
    }
  }

  async function renameView() {
    if (!profile) return;
    const name = window.prompt("Rename this Momentum Heatmap view", profile.name)?.trim();
    if (!name || name === profile.name) return;
    const nextProfile = { ...profile, name };
    setProfile(nextProfile);
    setProfiles((current) => current.map((item) => (activeProfileId(item) === activeProfileId(profile) ? nextProfile : item)));
    try {
      const payload = await saveMomentumHeatmapProfile(nextProfile);
      setProfiles(payload.profiles ?? [payload.profile]);
      setProfile(payload.profile);
      setFeedback({ state: "success", message: "Momentum Heatmap view renamed." });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Could not rename view." });
    }
  }

  async function duplicateView() {
    const profileId = activeProfileId();
    if (!profileId || !profile) return;
    const name = window.prompt("Name the duplicated Momentum Heatmap view", `Copy of ${profile.name}`)?.trim();
    if (!name) return;
    setFeedback({ state: "loading", message: "Duplicating Momentum Heatmap view." });
    try {
      const payload = await duplicateMomentumHeatmapProfile({ profileId, name });
      setProfiles(payload.profiles ?? [payload.profile]);
      applyProfile(payload.profile, payload.schedulePreferences ?? null);
      await loadSnapshotAndScheduleForProfile(activeProfileId(payload.profile));
      setFeedback({ state: "success", message: `${payload.profile.name} duplicated. Refresh remains manual.` });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Could not duplicate view." });
    }
  }

  async function resetSeededView() {
    const profileId = activeProfileId();
    if (!profileId || !profile?.isSystemSeeded) return;
    if (!window.confirm(`Reset ${profile.name} to its seeded defaults?`)) return;
    setFeedback({ state: "loading", message: "Resetting seeded Momentum Heatmap view." });
    try {
      const payload = await resetMomentumHeatmapProfile(profileId);
      setProfiles(payload.profiles ?? [payload.profile]);
      applyProfile(payload.profile, payload.schedulePreferences ?? null);
      setHeatmap(null);
      setLatestSnapshotId(undefined);
      setDeltas({});
      setDeltaNotice("Deltas need two successful snapshots.");
      setFeedback({ state: "success", message: `${payload.profile.name} reset to seeded defaults.` });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Could not reset seeded view." });
    }
  }

  async function deleteCustomView() {
    const profileId = activeProfileId();
    if (!profileId || !profile || profile.isSystemSeeded || profile.isDefault) return;
    if (!window.confirm(`Delete ${profile.name}? This only removes this saved view for your account.`)) return;
    setFeedback({ state: "loading", message: "Deleting custom Momentum Heatmap view." });
    try {
      const payload = await deleteMomentumHeatmapProfile(profileId);
      setProfiles(payload.profiles ?? [payload.profile]);
      applyProfile(payload.profile, payload.schedulePreferences ?? null);
      await loadSnapshotAndScheduleForProfile(activeProfileId(payload.profile));
      setFeedback({ state: "success", message: "Custom Momentum Heatmap view deleted." });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Could not delete custom view." });
    }
  }

  function saveColorRanges() {
    const normalized = normalizeMomentumHeatmapScoreRanges(colorRanges);
    setColorRanges(normalized);
    window.localStorage.setItem(MOMENTUM_HEATMAP_COLOR_STORAGE_KEY, JSON.stringify(normalized));
    persistProfile(categories, normalized);
    setFeedback({ state: "success", message: "Score color ranges saved to the server profile." });
  }

  function resetColorRanges() {
    const defaults = cloneDefaultMomentumHeatmapScoreRanges();
    setColorRanges(defaults);
    window.localStorage.setItem(MOMENTUM_HEATMAP_COLOR_STORAGE_KEY, JSON.stringify(defaults));
    persistProfile(categories, defaults);
    setFeedback({ state: "success", message: "Score color ranges reset to defaults." });
  }

  async function refreshCategories(targetCategories: MomentumHeatmapCategoryConfig[], label: string) {
    if (targetCategories.length === 0) {
      setFeedback({ state: "error", message: "Select at least one category for refresh." });
      return;
    }
    const totalRows = targetCategories.reduce((sum, category) => sum + category.rows.filter((row) => row.enabled !== false).length, 0);
    setLoading(true);
    setError(null);
    setCategoryErrors({});
    setRefreshProgress({
      currentCategoryLabel: null,
      completedCategories: 0,
      totalCategories: targetCategories.length,
      completedRows: 0,
      totalRows,
      failedCategories: 0,
    });
    setFeedback({ state: "loading", message: `Refreshing ${label} in bounded chunks.` });

    let completed = 0;
    let failed = 0;
    let completedRows = 0;
    for (const category of targetCategories) {
      setRefreshingCategoryId(category.categoryId);
      setRefreshProgress((current) => current ? { ...current, currentCategoryLabel: category.categoryLabel, completedCategories: completed, failedCategories: failed } : current);
      setCategoryErrors((current) => {
        const next = { ...current };
        delete next[category.categoryId];
        return next;
      });

      let categoryFailed = false;
      for (const chunk of chunkMomentumHeatmapCategory(toRequestCategory(category))) {
        try {
          const payload = await refreshMomentumHeatmapSnapshot([chunk], activeProfileId());
          setHeatmap((current) => mergeMomentumHeatmapResponse(current, payload.heatmap));
          setLatestSnapshotId(payload.snapshot?.id ?? latestSnapshotId);
          setHasPreviousSnapshot(Boolean(payload.previousSnapshot));
          setDeltas((current) => ({ ...current, ...(payload.deltas ?? {}) }));
          setDeltaNotice(payload.previousSnapshot ? null : "Deltas need two successful snapshots.");
          setCategorySummaries((current) => {
            const byId = new Map(current.map((summary) => [summary.categoryId, summary]));
            for (const summary of payload.categorySummaries ?? []) byId.set(summary.categoryId, summary);
            return Array.from(byId.values());
          });
          completedRows += chunk.rows.length;
          setRefreshProgress((current) => current ? { ...current, completedRows, completedCategories: completed, failedCategories: failed } : current);
        } catch (err) {
          categoryFailed = true;
          failed += 1;
          const message = err instanceof Error ? err.message : "Momentum Heatmap category refresh failed.";
          setCategoryErrors((current) => ({ ...current, [category.categoryId]: message }));
          break;
        }
      }

      if (!categoryFailed) completed += 1;
      setRefreshProgress((current) => current ? { ...current, completedCategories: completed, failedCategories: failed } : current);
    }

    setRefreshingCategoryId(null);
    setLoading(false);
    setLastSnapshotMessage(null);
    setRefreshProgress((current) => current ? { ...current, currentCategoryLabel: null, completedCategories: completed, failedCategories: failed } : current);
    setFeedback({
      state: failed > 0 ? "error" : "success",
      message: failed > 0
        ? `Refreshed ${completed} categories; ${failed} category refresh failed and prior/partial results were kept.`
        : `Refreshed ${completed} included categories and stored snapshot data.`,
    });
  }

  async function refreshVisibleHeatmap() {
    await refreshCategories(includedCategories, "included categories");
  }

  async function refreshCategory(category: MomentumHeatmapCategoryConfig) {
    await refreshCategories([category], category.categoryLabel);
  }

  async function addSymbol() {
    const providerSymbol = symbolInput.trim().toUpperCase();
    if (!providerSymbol) {
      setFeedback({ state: "error", message: "Enter a symbol before adding a row." });
      return;
    }
    const category = categories.find((item) => item.categoryId === selectedCategoryId);
    const duplicate = category?.rows.find((row) => row.providerSymbol.trim().toUpperCase() === providerSymbol);
    if (duplicate && category) {
      setFeedback({ state: "error", message: `${providerSymbol} is already in ${category.categoryLabel}.` });
      return;
    }
    try {
      const saved = await addMomentumHeatmapRow({
        profileId: profile?.profileId ?? profile?.id,
        categoryId: selectedCategoryId,
        symbol: providerSymbol,
        displayName: labelInput.trim() || providerSymbol,
        providerSymbol,
      });
      const nextCategories = profileCategories(saved.profile);
      setProfile(saved.profile);
      setCategories(nextCategories);
      setSymbolInput("");
      setLabelInput("");
      setFeedback({ state: saved.warning ? "success" : "success", message: saved.warning || `${providerSymbol} added to the heatmap profile.` });
    } catch (err) {
      const payload = (err as Error & { payload?: { detail?: { message?: string } } }).payload;
      setFeedback({ state: "error", message: payload?.detail?.message || (err instanceof Error ? err.message : "Could not add symbol.") });
    }
  }

  async function removeRow(categoryId: string, rowId: string) {
    try {
      const saved = await removeMomentumHeatmapRow({ profileId: profile?.profileId ?? profile?.id, rowId });
      setProfile(saved.profile);
      setCategories(profileCategories(saved.profile));
      setFeedback({ state: "success", message: "Row removed from server profile." });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Could not remove row." });
      const next = categories.map((category) =>
        category.categoryId === categoryId ? { ...category, rows: category.rows.filter((row) => row.id !== rowId) } : category,
      );
      setCategories(next);
    }
  }

  async function previewReport() {
    setReporting(true);
    setFeedback({ state: "loading", message: "Generating Momentum Heatmap report preview." });
    try {
      const payload = await generateMomentumHeatmapReportPreview(latestSnapshotId, activeProfileId());
      setReportPreviewHtml(payload.html);
      setSecondaryPanel("report");
      setFeedback({ state: "success", message: "Report preview generated from the latest stored snapshot." });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Generate report preview failed." });
    } finally {
      setReporting(false);
    }
  }

  async function downloadCsv() {
    setReporting(true);
    setFeedback({ state: "loading", message: "Preparing Momentum Heatmap CSV export." });
    try {
      const payload = await downloadMomentumHeatmapCsv(latestSnapshotId, activeProfileId());
      const blob = new Blob([payload.csv], { type: "text/csv;charset=utf-8" });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = payload.filename || "momentum-heatmap-report.csv";
      link.click();
      window.URL.revokeObjectURL(url);
      setFeedback({ state: "success", message: "CSV export generated." });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "CSV export failed." });
    } finally {
      setReporting(false);
    }
  }

  async function emailReportNow() {
    const recipients = emailRecipients.split(/[,\s]+/).map((item) => item.trim()).filter(Boolean);
    if (recipients.length === 0) {
      setFeedback({ state: "error", message: "Add at least one report recipient before emailing." });
      return;
    }
    setReporting(true);
    setFeedback({ state: "loading", message: "Sending Momentum Heatmap report through the configured email provider." });
    try {
      const payload = await emailMomentumHeatmapReport({ snapshotId: latestSnapshotId, profileId: activeProfileId(), recipients });
      setFeedback({ state: "success", message: `Momentum Heatmap report emailed to ${(payload.sentTo ?? recipients).join(", ")}.` });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Email report failed." });
    } finally {
      setReporting(false);
    }
  }

  async function saveSchedule(patch: Partial<MomentumHeatmapSchedulePreferences>) {
    const next = { ...(schedule ?? {}), ...patch, profileId: activeProfileId() } as MomentumHeatmapSchedulePreferences;
    setSchedule(next);
    try {
      const saved = await saveMomentumHeatmapSchedule(next);
      setSchedule(saved.schedulePreferences);
      setFeedback({ state: "success", message: saved.message });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Schedule preference save failed." });
    }
  }

  function renderColorRangeControls() {
    return (
      <Card title="Score color ranges">
        <div className="op-row hm-panel-heading">
          <span className="hm-muted">Customize -100 to 100 heatmap score bands in the server profile.</span>
          <button type="button" onClick={() => setSecondaryPanel(null)}>Collapse</button>
        </div>
        <div className="hm-table-wrap hm-panel-table">
          <table className="op-table hm-color-table">
            <thead>
              <tr>
                <th>Label</th>
                <th>Min score</th>
                <th>Max score</th>
                <th>Color</th>
              </tr>
            </thead>
            <tbody>
              {colorRanges.map((range) => (
                <tr key={range.id}>
                  <td><input value={range.label} onChange={(event) => updateColorRange(range.id, { label: event.target.value })} /></td>
                  <td><input type="number" step="0.001" value={range.min} onChange={(event) => updateColorRange(range.id, { min: Number(event.target.value) })} /></td>
                  <td><input type="number" step="0.001" value={range.max} onChange={(event) => updateColorRange(range.id, { max: Number(event.target.value) })} /></td>
                  <td>
                    <div className="op-row">
                      <input type="color" value={range.color} onChange={(event) => updateColorRange(range.id, { color: event.target.value })} />
                      <input value={range.color} onChange={(event) => updateColorRange(range.id, { color: event.target.value })} />
                      <span className="hm-color-swatch" style={{ backgroundColor: range.color }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="op-row hm-panel-actions">
            <button type="button" onClick={saveColorRanges} disabled={loading || reporting}>Save/update ranges</button>
            <button type="button" onClick={resetColorRanges} disabled={loading || reporting}>Reset color ranges to default</button>
          </div>
        </div>
      </Card>
    );
  }

  function renderReportControls() {
    return (
      <Card title="Report settings panel">
        <div className="op-row hm-panel-heading">
          <span className="hm-muted">Preview/export uses stored snapshots for active view: {profile?.name ?? "not loaded"}. It does not create recommendations or execution actions.</span>
          <button type="button" onClick={() => setSecondaryPanel(null)}>Collapse</button>
        </div>
        <div className="op-row hm-panel-actions">
          <button type="button" onClick={() => void previewReport()} disabled={loading || reporting}>Generate report preview</button>
          <button type="button" onClick={() => void downloadCsv()} disabled={loading || reporting}>Download CSV</button>
          <button type="button" onClick={() => reportPreviewHtml && window.print()} disabled={!reportPreviewHtml}>Download/print HTML report</button>
          <label>Email recipients
            <input value={emailRecipients} onChange={(event) => setEmailRecipients(event.target.value)} placeholder="operator@example.com" />
          </label>
          <button type="button" onClick={() => void emailReportNow()} disabled={!emailRecipients.trim() || loading || reporting}>Email report now</button>
        </div>
        {reportPreviewHtml ? (
          <div className="hm-report-preview" dangerouslySetInnerHTML={{ __html: reportPreviewHtml }} />
        ) : null}
      </Card>
    );
  }

  function renderScheduleControls() {
    return (
      <Card title="Scheduled report settings">
        <div className="op-row hm-panel-heading">
          <span className="hm-muted">Schedule preferences apply to active view: {profile?.name ?? "not loaded"}. Intraday scores depend on latest available completed bars.</span>
          <button type="button" onClick={() => setSecondaryPanel(null)}>Collapse</button>
        </div>
        <div className="op-stack hm-panel-table">
          <div className="op-row">
            <label><input type="checkbox" checked={schedule?.enabled ?? false} onChange={(event) => void saveSchedule({ enabled: event.target.checked })} /> Enabled</label>
            <label>Timezone <input value={schedule?.timezone ?? "America/Indiana/Indianapolis"} onChange={(event) => setSchedule((current) => ({ ...(current ?? defaultSchedule()), timezone: event.target.value }))} onBlur={(event) => void saveSchedule({ timezone: event.target.value })} /></label>
            <label>Run time <input type="time" value={schedule?.runTime ?? "07:00"} onChange={(event) => setSchedule((current) => ({ ...(current ?? defaultSchedule()), runTime: event.target.value }))} onBlur={(event) => void saveSchedule({ runTime: event.target.value })} /></label>
            <label>Report mode
              <select value={schedule?.reportMode ?? "latest_snapshot"} onChange={(event) => void saveSchedule({ reportMode: event.target.value })}>
                <option value="latest_snapshot">latest snapshot</option>
                <option value="refresh_then_report">refresh then report</option>
              </select>
            </label>
            <label><input type="checkbox" checked={schedule?.includeCsvAttachment ?? true} onChange={(event) => void saveSchedule({ includeCsvAttachment: event.target.checked })} /> Include CSV attachment</label>
            <label><input type="checkbox" checked={schedule?.includeFullTable ?? true} onChange={(event) => void saveSchedule({ includeFullTable: event.target.checked })} /> Include full table</label>
          </div>
          <div className="op-grid-4">
            {(timingSuggestions.length ? timingSuggestions : [
              { label: "7:00 AM ET", note: "Premarket read using prior completed session/intraday bars.", time: "07:00" },
              { label: "10:15 AM ET", note: "After market has enough regular-session data for 30M/1H context.", time: "10:15" },
              { label: "3:30 PM ET", note: "Late-session review before close.", time: "15:30" },
              { label: "4:30 PM ET", note: "Post-close summary.", time: "16:30" },
            ]).map((item) => (
              <div key={item.time} className="hm-summary-card">
                <strong>{item.label}</strong>
                <div className="hm-muted">{item.note}</div>
              </div>
            ))}
          </div>
          <p className="hm-muted">Premarket reports are useful but mostly reflect the prior session. Scheduler status: {schedule?.schedulerActive ? "active" : "preferences saved; runner hook not automatically installed"}.</p>
        </div>
      </Card>
    );
  }

  function renderManageSymbolsPanel() {
    return (
      <Card title="Manage symbols">
        <div className="op-row hm-panel-heading">
          <span className="hm-muted">Add rows to the server profile while preserving workbook order and duplicate protection.</span>
          <button type="button" onClick={() => setSecondaryPanel(null)}>Collapse</button>
        </div>
        <div className="op-row hm-panel-actions">
          <label>Category
            <select value={selectedCategoryId} onChange={(event) => setSelectedCategoryId(event.target.value)}>
              {categories.map((category) => <option key={category.categoryId} value={category.categoryId}>{category.categoryLabel}</option>)}
            </select>
          </label>
          <label>Symbol <input value={symbolInput} onChange={(event) => setSymbolInput(event.target.value)} placeholder="TSLA" /></label>
          <label>Display label <input value={labelInput} onChange={(event) => setLabelInput(event.target.value)} placeholder="Optional" /></label>
          <button type="button" onClick={() => void addSymbol()} disabled={loading || reporting}>Add</button>
        </div>
        <p className="hm-muted">Squeeze column now summarizes MacMarket Squeeze Pro research states. It is not part of True Momentum scoring.</p>
      </Card>
    );
  }

  function renderSecondaryPanel() {
    if (secondaryPanel === "symbols") return renderManageSymbolsPanel();
    if (secondaryPanel === "colors") return renderColorRangeControls();
    if (secondaryPanel === "report") return renderReportControls();
    if (secondaryPanel === "schedule") return renderScheduleControls();
    return null;
  }

  function renderFilterControls() {
    return (
      <div className="hm-filter-bar" data-testid="momentum-heatmap-filter-bar">
        <div className="op-row hm-filter-controls">
          <label>Sort selector
            <select value={sortMode} onChange={(event) => { setSortMode(event.target.value); persistProfile(categories, colorRanges, { sort: event.target.value }); }}>
              {SORT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label>Search symbol/label <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="SPY or ALL U.S." /></label>
          <label>Alignment filter
            <select value={filterMode} onChange={(event) => setFilterMode(event.target.value as FilterMode)}>
              <option value="all">All rows</option>
              <option value="bullish">Bullish alignment</option>
              <option value="bearish">Bearish alignment</option>
              <option value="pullback">Long-term bullish + short-term weak</option>
              <option value="reversal">Long-term weak + short-term improving</option>
            </select>
          </label>
          <label>Strength % minimum threshold <input type="number" value={strengthMin} onChange={(event) => setStrengthMin(event.target.value)} /></label>
          <label>Strength % maximum threshold <input type="number" value={strengthMax} onChange={(event) => setStrengthMax(event.target.value)} /></label>
          <label><input type="checkbox" checked={supportedOnly} onChange={(event) => setSupportedOnly(event.target.checked)} /> Supported only</label>
          <label><input type="checkbox" checked={hideUnavailable} onChange={(event) => setHideUnavailable(event.target.checked)} /> Hide unsupported/unavailable</label>
          <label><input type="checkbox" checked={changedOnly} onChange={(event) => setChangedOnly(event.target.checked)} /> Show rows changed since last snapshot</label>
          <label>Delta direction
            <select value={deltaDirection} onChange={(event) => setDeltaDirection(event.target.value as "all" | "positive" | "negative")}>
              <option value="all">All deltas</option>
              <option value="positive">Show positive delta only</option>
              <option value="negative">Show negative delta only</option>
            </select>
          </label>
          <label><input type="checkbox" checked={showDeltas} onChange={(event) => { setShowDeltas(event.target.checked); persistProfile(categories, colorRanges, { showDeltas: event.target.checked }); }} /> Toggle delta columns</label>
        </div>
        {showDeltas && (deltaNotice || !hasComparableDeltas) ? (
          <div className="hm-delta-notice" data-testid="momentum-heatmap-delta-notice">
            {deltaNotice ?? "No comparable numeric deltas are available for this snapshot."}
          </div>
        ) : null}
      </div>
    );
  }

  function renderCategory(category: MomentumHeatmapCategoryConfig) {
    const resultCategory = resultCategories.get(category.categoryId);
    const rowResults = resultRowById(resultCategory);
    const isCollapsed = category.collapsed === true;
    const isIncluded = category.included !== false;
    const categoryError = categoryErrors[category.categoryId];
    const isRefreshing = refreshingCategoryId === category.categoryId;
    const summary = categorySummaries.find((item) => item.categoryId === category.categoryId);
    const filteredRows = sortRows(
      category.rows.filter((row) => rowMatchesFilter(row, rowResults.get(row.id), {
        search,
        filterMode,
        supportedOnly,
        hideUnavailable,
        strengthMin,
        strengthMax,
        changedOnly,
        deltaDirection,
      }, deltas[row.id])),
      rowResults,
      sortMode,
    );
    return (
      <section key={category.categoryId} className="op-card hm-category-card" data-testid={`momentum-heatmap-category-${category.categoryId}`}>
        <div className="hm-category-header">
          <div className="hm-category-title">
            <h3>{category.categoryLabel}</h3>
            <StatusBadge tone={isIncluded ? "good" : "neutral"}>{isIncluded ? "Included" : "Excluded"}</StatusBadge>
            <StatusBadge tone={summary?.status === "fresh" ? "good" : summary?.status === "partial" ? "warn" : categoryError ? "bad" : "neutral"}>{categoryError ? "failed" : summary?.status ?? "not refreshed"}</StatusBadge>
            {isRefreshing ? <StatusBadge tone="warn">Refreshing...</StatusBadge> : null}
            <span className="hm-muted">{filteredRows.length} of {category.rows.length} rows</span>
            {summary?.average_strength_percent != null ? (
              <span className="hm-category-strength" style={scoreStyle(summary.average_strength_percent, colorRanges)}>
                Avg Strength {formatScore(summary.average_strength_percent, "%")}
              </span>
            ) : null}
          </div>
          <div className="op-row hm-category-actions">
            <label><input type="checkbox" checked={isIncluded} onChange={(event) => updateCategory(category.categoryId, { included: event.target.checked })} /> Include in refresh</label>
            <button type="button" onClick={() => void refreshCategory(category)} disabled={actionsDisabled}>Refresh this category</button>
            <button type="button" onClick={() => updateCategory(category.categoryId, { collapsed: !isCollapsed })}>{isCollapsed ? "Expand" : "Collapse"}</button>
          </div>
        </div>

        {summary ? (
          <div className="hm-summary-strip">
            <div className="hm-summary-card"><span>Average Strength %</span><strong>{formatScore(summary.average_strength_percent, "%")}</strong></div>
            <div className="hm-summary-card"><span>Average Long-Term Score</span><strong>{formatScore(summary.average_long_term_score)}</strong></div>
            <div className="hm-summary-card"><span>Average Short-Term Score</span><strong>{formatScore(summary.average_short_term_score)}</strong></div>
            <div className="hm-summary-card"><span>Counts</span><strong>{summary.count_ok} ok / {summary.count_unsupported} unsupported / {summary.count_unavailable_error} unavailable</strong></div>
            <div className="hm-summary-card"><span>Bullish aligned</span><strong>{summary.count_bullish_aligned}</strong></div>
            <div className="hm-summary-card"><span>Bearish aligned</span><strong>{summary.count_bearish_aligned}</strong></div>
            <div className="hm-summary-card"><span>Improving</span><strong>{summary.count_improving}</strong></div>
            <div className="hm-summary-card"><span>Weakening</span><strong>{summary.count_weakening}</strong></div>
          </div>
        ) : null}

        {categoryError ? <ErrorState title={`${category.categoryLabel} refresh failed`} hint={categoryError} /> : null}

        {isCollapsed ? null : (
          <div className="hm-table-wrap hm-category-table">
            <table className="op-table hm-table">
              <thead>
                <tr>
                  <th>Symbol / label</th>
                  <th>Tags</th>
                  <th>Long-Term Score</th>
                  {showDeltas ? <th>Delta Long-Term Score</th> : null}
                  <th>Weekly</th>
                  <th>Daily</th>
                  <th>Short-Term Score</th>
                  {showDeltas ? <th>Delta Short-Term Score</th> : null}
                  <th>4HR</th>
                  <th>1HR</th>
                  <th>30M</th>
                  <th>Strength %</th>
                  {showDeltas ? <th>Delta Strength %</th> : null}
                  <th>Squeezes</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((row) => {
                  const result = rowResults.get(row.id);
                  const reason = rowReason(result);
                  const delta = deltas[row.id];
                  const rowIsUnavailable = row.unsupported || isUnavailable(result);
                  return (
                    <tr key={row.id} className={`${result?.stale ? "is-stale" : ""} ${rowIsUnavailable ? "is-unavailable" : ""}`}>
                      <td className="hm-symbol-cell" title={reason ?? row.unsupportedReason ?? undefined}>
                        {row.displayName}
                        {row.providerSymbol !== row.displayName ? <div className="hm-muted">Provider: {row.providerSymbol}</div> : null}
                        {reason ? <div className="hm-muted" title={reason}>{reason}</div> : null}
                        {result?.stale ? <div className="hm-muted">Stale previous value preserved after refresh failure.</div> : null}
                      </td>
                      <td>{(result?.row_tags ?? (row.unsupported ? ["Unsupported"] : [])).map((tag) => <span key={tag} className="hm-tag" title={`Research label: ${tag}`}>{tag}</span>)}</td>
                      <DerivedScoreCell value={result?.long_term_score} title="Long-Term Score = (Weekly + Daily) / 2" colorRanges={colorRanges} />
                      {showDeltas ? <DeltaCell value={delta?.long_term_score} delta={delta} hasPreviousSnapshot={hasPreviousSnapshot} /> : null}
                      {WORKBOOK_TIMEFRAME_LABELS.slice(0, 2).map(({ key }) => <HeatmapScoreCell key={key} cell={result?.scores?.[key]} colorRanges={colorRanges} showStale={showDeltas} />)}
                      <DerivedScoreCell value={result?.short_term_score} title="Short-Term Score = (4HR + 1HR + 30M) / 3" colorRanges={colorRanges} />
                      {showDeltas ? <DeltaCell value={delta?.short_term_score} delta={delta} hasPreviousSnapshot={hasPreviousSnapshot} /> : null}
                      {WORKBOOK_TIMEFRAME_LABELS.slice(2).map(({ key }) => <HeatmapScoreCell key={key} cell={result?.scores?.[key]} colorRanges={colorRanges} showStale={showDeltas} />)}
                      <DerivedScoreCell value={result?.strength_percent} title="Strength % = (Weekly*3 + Daily*3 + 4HR + 1HR + 30M) / 9" colorRanges={colorRanges} suffix="%" />
                      {showDeltas ? <DeltaCell value={delta?.strength_percent} delta={delta} hasPreviousSnapshot={hasPreviousSnapshot} /> : null}
                      <SqueezeCell cell={result?.squeeze} />
                      <td><button type="button" className="hm-row-action" title={`Remove ${row.displayName}`} onClick={() => void removeRow(category.categoryId, row.id)} disabled={actionsDisabled}>Remove</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    );
  }

  return (
    <>
      <PageHeader
        title="Momentum Heatmap"
        subtitle="Server-backed True Momentum research dashboard."
      />

      <section className="hm-command-center" data-testid="momentum-heatmap-command-center">
        <div className="hm-command-meta">
          <div>
            <span className="hm-kicker">Active view</span>
            <strong>{profile?.name ?? "Default Momentum Heatmap"}</strong>
            {profile?.description ? <span className="hm-muted">{profile.description}</span> : null}
          </div>
          <label className="hm-view-selector">Active view
            <select
              data-testid="momentum-heatmap-view-selector"
              value={activeProfileId() ?? ""}
              onChange={(event) => void switchProfile(event.target.value)}
              disabled={actionsDisabled}
            >
              {profiles.map((item) => {
                const itemId = item.profileId ?? item.id;
                return (
                  <option key={itemId} value={itemId}>
                    {item.name}
                  </option>
                );
              })}
            </select>
          </label>
          <StatusBadge tone={profile ? "good" : "warn"}>{profile ? "Server profile" : "Local fallback"}</StatusBadge>
          {profile?.isSystemSeeded ? <StatusBadge tone="neutral">Seeded view</StatusBadge> : <StatusBadge tone="warn">Custom view</StatusBadge>}
          {heatmap?.generated_at ? <span className="hm-muted">Last refreshed: {new Date(heatmap.generated_at).toLocaleString()}</span> : null}
          {lastSnapshotMessage ? <span className="hm-muted">{lastSnapshotMessage}</span> : null}
        </div>
        <div className="hm-command-actions">
          <button type="button" className="op-btn op-btn-primary" onClick={() => void refreshVisibleHeatmap()} disabled={actionsDisabled}>
            {loading ? "Refreshing..." : "Refresh visible heatmap"}
          </button>
          <button type="button" className="op-btn op-btn-secondary" onClick={() => void previewReport()} disabled={actionsDisabled}>Generate report preview</button>
          <button type="button" className="op-btn op-btn-secondary" onClick={() => void downloadCsv()} disabled={actionsDisabled}>Download CSV</button>
          <button type="button" className="op-btn op-btn-ghost" onClick={() => void createView()} disabled={actionsDisabled}>Create new view</button>
          <button type="button" className="op-btn op-btn-ghost" onClick={() => void renameView()} disabled={actionsDisabled || !profile}>Rename view</button>
          <button type="button" className="op-btn op-btn-ghost" onClick={() => void duplicateView()} disabled={actionsDisabled || !profile}>Duplicate view</button>
          <button type="button" className="op-btn op-btn-ghost" onClick={() => void resetSeededView()} disabled={actionsDisabled || !profile?.isSystemSeeded}>Reset seeded view to defaults</button>
          <button type="button" className="op-btn op-btn-ghost" onClick={() => void deleteCustomView()} disabled={actionsDisabled || !profile || profile.isSystemSeeded || profile.isDefault}>Delete custom view</button>
          {panelButton("symbols", "Manage symbols")}
          {panelButton("colors", "Score color ranges")}
          {panelButton("report", "Report settings")}
          {panelButton("schedule", "Schedule settings")}
        </div>
      </section>

      {refreshProgress && (loading || refreshProgress.completedCategories > 0 || refreshProgress.failedCategories > 0) ? (
        <section className="hm-progress" data-testid="momentum-heatmap-refresh-progress">
          <div className="op-row">
            <StatusBadge tone={loading ? "warn" : refreshProgress.failedCategories > 0 ? "bad" : "good"}>
              {loading ? "working..." : refreshProgress.failedCategories > 0 ? "partial" : "complete"}
            </StatusBadge>
            <strong>{loading ? `Refreshing ${refreshProgress.currentCategoryLabel ?? "heatmap"}` : "Refresh status"}</strong>
            <span className="hm-muted">
              Categories {refreshProgress.completedCategories}/{refreshProgress.totalCategories}
              {refreshProgress.totalRows ? ` | Rows ${refreshProgress.completedRows}/${refreshProgress.totalRows}` : ""}
              {refreshProgress.failedCategories ? ` | Failed ${refreshProgress.failedCategories}` : ""}
            </span>
          </div>
          <div className="hm-progress-track" aria-hidden="true">
            <span style={{ width: `${Math.min(100, Math.round(((refreshProgress.completedRows || refreshProgress.completedCategories) / Math.max(1, refreshProgress.totalRows || refreshProgress.totalCategories)) * 100))}%` }} />
          </div>
        </section>
      ) : null}

      <div className="hm-status-strip" data-testid="momentum-heatmap-status-strip">
        <InlineFeedback state={feedback.state} message={feedback.message} />
      </div>

      {renderSecondaryPanel()}

      {migrationWarning ? <ErrorState title="Heatmap profile notice" hint={migrationWarning} /> : null}
      {error ? <ErrorState title="Heatmap saved config warning" hint={error} /> : null}
      {!heatmap ? <EmptyState title="Momentum Heatmap not refreshed" hint="Load last snapshot appears here when available. Use Refresh visible heatmap to fetch only included categories." /> : null}

      <section className="hm-table-workflow">
        {renderFilterControls()}
      </section>

      <div className="op-stack">
        {categories.map((category) => renderCategory(category))}
      </div>
    </>
  );
}

function defaultSchedule(): MomentumHeatmapSchedulePreferences {
  return {
    enabled: false,
    timezone: "America/Indiana/Indianapolis",
    runTime: "07:00",
    daysOfWeek: ["mon", "tue", "wed", "thu", "fri"],
    reportMode: "latest_snapshot",
    recipients: [],
    includeCsvAttachment: true,
    includeFullTable: true,
    schedulerActive: false,
  };
}
