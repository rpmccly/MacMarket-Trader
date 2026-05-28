"use client";

import { type ChangeEvent, useEffect, useMemo, useState } from "react";

import { Card, EmptyState, ErrorState, InlineFeedback, PageHeader, StatusBadge } from "@/components/operator-ui";
import {
  addHacoHeatmapRow,
  chunkHacoHeatmapCategory,
  downloadHacoHeatmapCsv,
  fetchHacoHeatmapProfile,
  fetchLatestHacoHeatmapSnapshot,
  generateHacoHeatmapReportPreview,
  hacoHeatmapSymbolDisplayParts,
  mergeHacoHeatmapResponse,
  refreshHacoHeatmapSnapshot,
  removeHacoHeatmapRow,
  resetHacoHeatmapProfile,
  saveHacoHeatmapProfile,
  type HacoHeatmapCategorySummary,
  type HacoHeatmapChange,
  type HacoHeatmapDirectionCell,
  type HacoHeatmapRequestCategory,
  type HacoHeatmapRequestRow,
  type HacoHeatmapResponse,
  type HacoHeatmapResponseCategory,
  type HacoHeatmapResponseRow,
  type HacoHeatmapServerProfile,
} from "@/lib/haco-heatmap-api";
import { SUPPORTED_TIMEFRAME_VALUES, type SupportedTimeframe } from "@/lib/timeframes";

const TIMEFRAME_LABELS: Array<{ key: SupportedTimeframe; label: string }> = [
  { key: "1W", label: "1W" },
  { key: "1D", label: "1D" },
  { key: "4H", label: "4H" },
  { key: "1H", label: "1H" },
  { key: "30M", label: "30M" },
];

const SORT_OPTIONS = [
  ["workbook", "Workbook/default order"],
  ["symbol-az", "Symbol A-Z"],
  ["alignment-desc", "Overall alignment high to low"],
  ["alignment-asc", "Overall alignment low to high"],
  ["short-desc", "Short-term alignment high to low"],
  ["short-asc", "Short-term alignment low to high"],
  ["changed-first", "Changed since last first"],
  ["unsupported-last", "Unsupported/unavailable last"],
] as const;

type FeedbackState = { state: "idle" | "loading" | "success" | "error"; message?: string };
type DirectionFilter = "all" | "long" | "short" | "mixed";
type SecondaryPanel = "symbols" | "settings" | "report" | null;
type RefreshProgress = {
  currentCategoryLabel: string | null;
  completedCategories: number;
  totalCategories: number;
  completedRows: number;
  totalRows: number;
  failedCategories: number;
};

const EMPTY_PROGRESS: RefreshProgress = {
  currentCategoryLabel: null,
  completedCategories: 0,
  totalCategories: 0,
  completedRows: 0,
  totalRows: 0,
  failedCategories: 0,
};

function normalizeCategory(category: HacoHeatmapRequestCategory): HacoHeatmapRequestCategory {
  return {
    categoryId: category.categoryId,
    categoryLabel: category.categoryLabel,
    included: category.included !== false,
    collapsed: category.collapsed === true,
    rows: (category.rows ?? []).map((row, index) => ({
      id: row.id,
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

function blankStates(reason: string): Record<SupportedTimeframe, HacoHeatmapDirectionCell> {
  return SUPPORTED_TIMEFRAME_VALUES.reduce((acc, timeframe) => {
    acc[timeframe] = { value: null, label: "—", status: "unavailable", reason };
    return acc;
  }, {} as Record<SupportedTimeframe, HacoHeatmapDirectionCell>);
}

function placeholderRow(row: HacoHeatmapRequestRow): HacoHeatmapResponseRow {
  const providerSymbol = (row.providerSymbol || row.symbol).trim().toUpperCase();
  return {
    id: row.id,
    symbol: row.symbol,
    displayName: row.displayName || providerSymbol,
    providerSymbol,
    states: blankStates("not_refreshed"),
    overall_bias: null,
    overall_alignment_percent: null,
    daily_context: null,
    macro_context: null,
    short_term_bias: null,
    short_term_alignment_percent: null,
    tags: row.unsupported ? ["Unsupported"] : ["Not refreshed"],
  };
}

function resultRowById(category: HacoHeatmapResponseCategory | undefined): Map<string, HacoHeatmapResponseRow> {
  return new Map((category?.rows ?? []).map((row) => [row.id, row]));
}

function fmt(value: number | null | undefined, suffix = "%"): string {
  if (value == null || Number.isNaN(value)) return "--";
  return `${value > 0 ? "+" : ""}${Math.round(value)}${suffix}`;
}

function stateTitle(cell: HacoHeatmapDirectionCell | undefined): string | undefined {
  if (!cell) return undefined;
  return [
    cell.stale ? "stale previous value" : cell.status,
    cell.reason,
    cell.data_source ? `source: ${cell.data_source}` : null,
    cell.fallback_mode ? "fallback mode" : null,
    cell.as_of ? `as of ${cell.as_of}` : null,
  ].filter(Boolean).join(" | ");
}

function rowAvailability(row: HacoHeatmapResponseRow): "ok" | "unsupported" | "unavailable" {
  const states = Object.values(row.states ?? {});
  if (!states.length) return "unavailable";
  if (states.some((cell) => cell.status === "ok")) return "ok";
  if (states.every((cell) => cell.status === "unsupported")) return "unsupported";
  return "unavailable";
}

function rowReason(row: HacoHeatmapResponseRow): string | null {
  const reasons = Object.values(row.states ?? {}).map((cell) => cell.reason).filter(Boolean);
  return reasons.length ? Array.from(new Set(reasons)).join(", ") : null;
}

function biasTone(bias: string | null | undefined): "good" | "bad" | "warn" | "neutral" {
  if (bias === "LONG") return "good";
  if (bias === "SHORT") return "bad";
  if (bias === "MIXED") return "warn";
  return "neutral";
}

function stateClass(cell: HacoHeatmapDirectionCell | undefined): string {
  if (cell?.status !== "ok") return "haco-state-unavailable";
  if (cell.value === "long") return "haco-state-long";
  if (cell.value === "short") return "haco-state-short";
  return "haco-state-unavailable";
}

function StateCell({ cell }: { cell: HacoHeatmapDirectionCell | undefined }) {
  const label = cell?.status === "ok" ? cell.label : "—";
  return (
    <td className={`hm-cell haco-state-cell ${stateClass(cell)} ${cell?.stale ? "is-stale" : ""}`} title={stateTitle(cell)}>
      {label}
    </td>
  );
}

function categorySummary(
  category: HacoHeatmapRequestCategory,
  result: HacoHeatmapResponseCategory | undefined,
  serverSummary?: HacoHeatmapCategorySummary,
): HacoHeatmapCategorySummary {
  if (serverSummary) return serverSummary;
  const rows = result?.rows ?? [];
  const alignments = rows.map((row) => row.overall_alignment_percent).filter((value): value is number => typeof value === "number");
  return {
    categoryId: category.categoryId,
    categoryLabel: category.categoryLabel,
    average_alignment_percent: alignments.length ? Math.round(alignments.reduce((sum, value) => sum + value, 0) / alignments.length) : null,
    count_long: rows.filter((row) => row.overall_bias === "LONG").length,
    count_short: rows.filter((row) => row.overall_bias === "SHORT").length,
    count_mixed: rows.filter((row) => row.overall_bias === "MIXED").length,
    count_unsupported: rows.filter((row) => rowAvailability(row) === "unsupported").length,
    count_unavailable_error: rows.filter((row) => rowAvailability(row) === "unavailable").length,
    status: rows.length ? "fresh" : "not_refreshed",
  };
}

export default function HacoHeatmapPage() {
  const [profiles, setProfiles] = useState<HacoHeatmapServerProfile[]>([]);
  const [activeProfile, setActiveProfile] = useState<HacoHeatmapServerProfile | null>(null);
  const [categories, setCategories] = useState<HacoHeatmapRequestCategory[]>([]);
  const [heatmap, setHeatmap] = useState<HacoHeatmapResponse | null>(null);
  const [snapshotId, setSnapshotId] = useState<string | undefined>(undefined);
  const [hasPreviousSnapshot, setHasPreviousSnapshot] = useState(false);
  const [snapshotMessage, setSnapshotMessage] = useState<string>("");
  const [categorySummaries, setCategorySummaries] = useState<HacoHeatmapCategorySummary[]>([]);
  const [changes, setChanges] = useState<Record<string, HacoHeatmapChange>>({});
  const [feedback, setFeedback] = useState<FeedbackState>({ state: "idle" });
  const [progress, setProgress] = useState<RefreshProgress>(EMPTY_PROGRESS);
  const [refreshingCategoryIds, setRefreshingCategoryIds] = useState<Set<string>>(new Set());
  const [categoryErrors, setCategoryErrors] = useState<Record<string, string>>({});
  const [secondaryPanel, setSecondaryPanel] = useState<SecondaryPanel>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<string>("workbook");
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>("all");
  const [hideUnsupported, setHideUnsupported] = useState(false);
  const [changedOnly, setChangedOnly] = useState(false);
  const [alignmentMin, setAlignmentMin] = useState("");
  const [alignmentMax, setAlignmentMax] = useState("");
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [addCategoryId, setAddCategoryId] = useState("");
  const [addSymbol, setAddSymbol] = useState("");
  const [addDisplayName, setAddDisplayName] = useState("");
  const [reportHtml, setReportHtml] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isReporting, setIsReporting] = useState(false);

  async function loadProfile(profileId?: string) {
    setFeedback({ state: "loading", message: "Loading HACO Direction Heatmap profile." });
    try {
      const payload = await fetchHacoHeatmapProfile(profileId);
      const loadedProfile = payload.profile;
      setProfiles(payload.profiles ?? [loadedProfile]);
      setActiveProfile(loadedProfile);
      const loadedCategories = (loadedProfile.categories ?? []).map((category) => normalizeCategory(category));
      setCategories(loadedCategories);
      setAddCategoryId(loadedCategories[0]?.categoryId ?? "");
      setFeedback({ state: "success", message: "Server-backed HACO profile loaded." });
      await loadLatestSnapshot(loadedProfile.profileId);
    } catch (error) {
      setFeedback({ state: "error", message: error instanceof Error ? error.message : "Unable to load HACO profile." });
    }
  }

  async function loadLatestSnapshot(profileId?: string) {
    try {
      const latest = await fetchLatestHacoHeatmapSnapshot(profileId);
      setHeatmap(latest.snapshot?.payload ?? null);
      setSnapshotId(latest.snapshot?.id);
      setHasPreviousSnapshot(Boolean(latest.previousSnapshot));
      setSnapshotMessage(latest.message);
      setCategorySummaries(latest.snapshot?.categorySummaries ?? []);
      setChanges(latest.changes ?? {});
    } catch (error) {
      setSnapshotMessage(error instanceof Error ? error.message : "No HACO Direction Heatmap snapshot loaded.");
    }
  }

  useEffect(() => {
    void loadProfile();
  }, []);

  const profileId = activeProfile?.profileId ?? activeProfile?.id;
  const heatmapByCategory = useMemo(
    () => new Map((heatmap?.categories ?? []).map((category) => [category.categoryId, category])),
    [heatmap],
  );
  const summariesByCategory = useMemo(
    () => new Map(categorySummaries.map((summary) => [summary.categoryId, summary])),
    [categorySummaries],
  );

  function rowsForCategory(category: HacoHeatmapRequestCategory): HacoHeatmapResponseRow[] {
    const resultRows = resultRowById(heatmapByCategory.get(category.categoryId));
    return category.rows.map((row) => resultRows.get(row.id) ?? placeholderRow(row));
  }

  function filteredRows(category: HacoHeatmapRequestCategory): HacoHeatmapResponseRow[] {
    const query = search.trim().toUpperCase();
    const min = alignmentMin.trim() ? Number(alignmentMin) : null;
    const max = alignmentMax.trim() ? Number(alignmentMax) : null;
    let rows = rowsForCategory(category).filter((row) => {
      const text = `${row.displayName} ${row.symbol} ${row.providerSymbol}`.toUpperCase();
      if (query && !text.includes(query)) return false;
      if (directionFilter === "long" && row.overall_bias !== "LONG") return false;
      if (directionFilter === "short" && row.overall_bias !== "SHORT") return false;
      if (directionFilter === "mixed" && row.overall_bias !== "MIXED") return false;
      if (hideUnsupported && rowAvailability(row) !== "ok") return false;
      if (changedOnly && !row.changed_since_last && !changes[row.id]?.changed_since_last) return false;
      if (min != null && !Number.isNaN(min) && (row.overall_alignment_percent ?? -Infinity) < min) return false;
      if (max != null && !Number.isNaN(max) && (row.overall_alignment_percent ?? Infinity) > max) return false;
      return true;
    });
    rows = [...rows].sort((a, b) => {
      if (sort === "symbol-az") return a.displayName.localeCompare(b.displayName);
      if (sort === "alignment-desc") return (b.overall_alignment_percent ?? -999) - (a.overall_alignment_percent ?? -999);
      if (sort === "alignment-asc") return (a.overall_alignment_percent ?? 999) - (b.overall_alignment_percent ?? 999);
      if (sort === "short-desc") return (b.short_term_alignment_percent ?? -999) - (a.short_term_alignment_percent ?? -999);
      if (sort === "short-asc") return (a.short_term_alignment_percent ?? 999) - (b.short_term_alignment_percent ?? 999);
      if (sort === "changed-first") return Number(Boolean(b.changed_since_last || changes[b.id]?.changed_since_last)) - Number(Boolean(a.changed_since_last || changes[a.id]?.changed_since_last));
      if (sort === "unsupported-last") return Number(rowAvailability(a) !== "ok") - Number(rowAvailability(b) !== "ok");
      const aConfig = category.rows.find((row) => row.id === a.id);
      const bConfig = category.rows.find((row) => row.id === b.id);
      return (aConfig?.workbookOrder ?? 0) - (bConfig?.workbookOrder ?? 0);
    });
    return rows;
  }

  async function persistCategories(nextCategories: HacoHeatmapRequestCategory[], message: string) {
    setCategories(nextCategories);
    if (!activeProfile) return;
    try {
      const payload = await saveHacoHeatmapProfile({
        ...activeProfile,
        categories: nextCategories,
      });
      setActiveProfile(payload.profile);
      setProfiles(payload.profiles ?? [payload.profile]);
      setFeedback({ state: "success", message });
    } catch (error) {
      setFeedback({ state: "error", message: error instanceof Error ? error.message : "Unable to save HACO profile." });
    }
  }

  async function switchProfile(event: ChangeEvent<HTMLSelectElement>) {
    const nextProfileId = event.target.value;
    setHeatmap(null);
    setSnapshotId(undefined);
    setHasPreviousSnapshot(false);
    setSnapshotMessage("");
    setCategorySummaries([]);
    setChanges({});
    await loadProfile(nextProfileId);
  }

  async function refreshCategories(targetCategories: HacoHeatmapRequestCategory[]) {
    if (!profileId || !targetCategories.length) {
      setFeedback({ state: "error", message: "Select at least one included category before refreshing." });
      return;
    }
    const enabledCategories = targetCategories
      .filter((category) => category.included !== false)
      .map((category) => ({
        ...category,
        rows: category.rows.filter((row) => row.enabled !== false),
      }))
      .filter((category) => category.rows.length > 0);
    if (!enabledCategories.length) {
      setFeedback({ state: "error", message: "No enabled rows are included in refresh." });
      return;
    }
    setIsRefreshing(true);
    setCategoryErrors({});
    setProgress({
      currentCategoryLabel: enabledCategories[0]?.categoryLabel ?? null,
      completedCategories: 0,
      totalCategories: enabledCategories.length,
      completedRows: 0,
      totalRows: enabledCategories.reduce((sum, category) => sum + category.rows.length, 0),
      failedCategories: 0,
    });
    setFeedback({ state: "loading", message: "Refreshing HACO Direction Heatmap by category." });

    let nextHeatmap = heatmap;
    const nextErrors: Record<string, string> = {};
    const categoryIds = new Set<string>();
    try {
      for (const category of enabledCategories) {
        categoryIds.add(category.categoryId);
        setRefreshingCategoryIds(new Set(categoryIds));
        const chunks = chunkHacoHeatmapCategory(category);
        let categoryFailed = false;
        for (const chunk of chunks) {
          try {
            const result = await refreshHacoHeatmapSnapshot([chunk], profileId);
            nextHeatmap = mergeHacoHeatmapResponse(nextHeatmap, result.heatmap);
            setHeatmap(nextHeatmap);
            setSnapshotId(result.snapshot?.id ?? snapshotId);
            setHasPreviousSnapshot(Boolean(result.previousSnapshot));
            setCategorySummaries((current) => {
              const merged = new Map(current.map((summary) => [summary.categoryId, summary]));
              for (const summary of result.categorySummaries ?? []) merged.set(summary.categoryId, summary);
              return Array.from(merged.values());
            });
            setChanges((current) => ({ ...current, ...(result.changes ?? {}) }));
            setProgress((current) => ({
              ...current,
              completedRows: current.completedRows + chunk.rows.length,
            }));
          } catch (error) {
            categoryFailed = true;
            nextErrors[category.categoryId] = error instanceof Error ? error.message : "Category refresh failed.";
          }
        }
        categoryIds.delete(category.categoryId);
        setRefreshingCategoryIds(new Set(categoryIds));
        setProgress((current) => ({
          ...current,
          currentCategoryLabel: enabledCategories[current.completedCategories + 1]?.categoryLabel ?? null,
          completedCategories: current.completedCategories + 1,
          failedCategories: current.failedCategories + (categoryFailed ? 1 : 0),
        }));
      }
      setCategoryErrors(nextErrors);
      setSnapshotMessage(`Last refreshed ${new Date().toLocaleString()}; load latest snapshot or refresh again to update.`);
      setFeedback({
        state: Object.keys(nextErrors).length ? "error" : "success",
        message: Object.keys(nextErrors).length
          ? "Refresh completed with category-level errors; prior values were preserved where available."
          : "HACO Direction Heatmap refresh complete.",
      });
    } finally {
      setIsRefreshing(false);
      setRefreshingCategoryIds(new Set());
    }
  }

  async function toggleCategory(categoryId: string, updates: Partial<HacoHeatmapRequestCategory>, message: string) {
    const nextCategories = categories.map((category) => (
      category.categoryId === categoryId ? { ...category, ...updates } : category
    ));
    await persistCategories(nextCategories, message);
  }

  async function handleAddRow() {
    if (!addCategoryId || !addSymbol.trim()) {
      setFeedback({ state: "error", message: "Choose a category and enter a symbol." });
      return;
    }
    try {
      const payload = await addHacoHeatmapRow({
        profileId,
        categoryId: addCategoryId,
        symbol: addSymbol,
        displayName: addDisplayName,
      });
      setActiveProfile(payload.profile);
      setProfiles(payload.profiles ?? [payload.profile]);
      setCategories(payload.profile.categories.map((category) => normalizeCategory(category)));
      setAddSymbol("");
      setAddDisplayName("");
      setFeedback({ state: "success", message: payload.warning || "Symbol added to HACO view." });
    } catch (error) {
      setFeedback({ state: "error", message: error instanceof Error ? error.message : "Unable to add HACO row." });
    }
  }

  async function handleRemoveRow(row: HacoHeatmapResponseRow) {
    try {
      const payload = await removeHacoHeatmapRow({ profileId, rowId: row.id });
      setActiveProfile(payload.profile);
      setProfiles(payload.profiles ?? [payload.profile]);
      setCategories(payload.profile.categories.map((category) => normalizeCategory(category)));
      setFeedback({ state: "success", message: `${row.displayName} removed from active HACO view.` });
    } catch (error) {
      setFeedback({ state: "error", message: error instanceof Error ? error.message : "Unable to remove HACO row." });
    }
  }

  async function handleResetProfile() {
    if (!profileId) return;
    try {
      const payload = await resetHacoHeatmapProfile(profileId);
      setActiveProfile(payload.profile);
      setProfiles(payload.profiles ?? [payload.profile]);
      setCategories(payload.profile.categories.map((category) => normalizeCategory(category)));
      setHeatmap(null);
      setSnapshotId(undefined);
      setHasPreviousSnapshot(false);
      setFeedback({ state: "success", message: "Seeded HACO view reset to defaults." });
    } catch (error) {
      setFeedback({ state: "error", message: error instanceof Error ? error.message : "Unable to reset HACO view." });
    }
  }

  async function handleReportPreview() {
    setIsReporting(true);
    setSecondaryPanel("report");
    setFeedback({ state: "loading", message: "Generating HACO Direction report preview." });
    try {
      const payload = await generateHacoHeatmapReportPreview(snapshotId, profileId);
      setReportHtml(payload.html);
      setFeedback({ state: "success", message: payload.emailStatus?.includes("not_configured") ? "Report preview generated; email is not configured." : "Report preview generated." });
    } catch (error) {
      setFeedback({ state: "error", message: error instanceof Error ? error.message : "Unable to generate HACO report." });
    } finally {
      setIsReporting(false);
    }
  }

  async function handleDownloadCsv() {
    setIsReporting(true);
    try {
      const payload = await downloadHacoHeatmapCsv(snapshotId, profileId);
      const blob = new Blob([payload.csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = payload.filename || "haco-direction-heatmap-report.csv";
      link.click();
      URL.revokeObjectURL(url);
      setFeedback({ state: "success", message: "HACO Direction Heatmap CSV exported." });
    } catch (error) {
      setFeedback({ state: "error", message: error instanceof Error ? error.message : "Unable to export HACO CSV." });
    } finally {
      setIsReporting(false);
    }
  }

  function resetFilters() {
    setSearch("");
    setSort("workbook");
    setDirectionFilter("all");
    setHideUnsupported(false);
    setChangedOnly(false);
    setAlignmentMin("");
    setAlignmentMax("");
  }

  if (feedback.state === "error" && !activeProfile) {
    return (
      <>
        <PageHeader title="HACO Direction Heatmap" subtitle="Workbook-style LONG / SHORT direction dashboard using the existing HACO chart path." />
        <ErrorState title="Unable to load HACO Heatmap" hint={feedback.message ?? "Check authentication and try again."} />
      </>
    );
  }

  return (
    <div className="hm-page haco-heatmap-page">
      <PageHeader
        title="HACO Direction Heatmap"
        subtitle="Research dashboard only. HACO direction is LONG / SHORT state context, not a trade recommendation."
      />

      <section className="hm-command-center" data-testid="haco-heatmap-command-center">
        <div className="hm-command-meta">
          <label>
            <span>Active view</span>
            <select aria-label="HACO heatmap active view" data-testid="haco-heatmap-view-selector" value={profileId ?? ""} onChange={switchProfile} disabled={isRefreshing}>
              {profiles.map((profile) => (
                <option key={profile.profileId} value={profile.profileId}>{profile.name}</option>
              ))}
            </select>
          </label>
          <StatusBadge tone="neutral">{activeProfile?.isSystemSeeded ? "seeded view" : "custom view"}</StatusBadge>
          <span className="hm-muted">{snapshotMessage || "No auto-refresh on load; refresh when ready."}</span>
        </div>
        <div className="hm-command-actions">
          <button onClick={() => refreshCategories(categories)} disabled={isRefreshing || isReporting}>Refresh included</button>
          <button onClick={handleReportPreview} disabled={isRefreshing || isReporting || !snapshotId}>Generate report preview</button>
          <button onClick={handleDownloadCsv} disabled={isRefreshing || isReporting || !snapshotId}>Download CSV</button>
          <button onClick={() => setSecondaryPanel(secondaryPanel === "symbols" ? null : "symbols")}>Manage symbols</button>
          <button onClick={() => setSecondaryPanel(secondaryPanel === "settings" ? null : "settings")}>Settings</button>
        </div>
      </section>

      <div className="hm-status-strip" data-testid="haco-heatmap-status-strip">
        <InlineFeedback state={feedback.state} message={feedback.message} />
        {isRefreshing ? (
          <div className="hm-progress" data-testid="haco-heatmap-refresh-progress">
            Refreshing {progress.currentCategoryLabel ?? "category"} · categories {progress.completedCategories}/{progress.totalCategories} · rows {progress.completedRows}/{progress.totalRows}
          </div>
        ) : null}
      </div>

      {secondaryPanel === "symbols" ? (
        <Card title="Manage HACO symbols">
          <div className="hm-panel-grid">
            <label>
              <span>Category</span>
              <select aria-label="Category" value={addCategoryId} onChange={(event) => setAddCategoryId(event.target.value)}>
                {categories.map((category) => <option key={category.categoryId} value={category.categoryId}>{category.categoryLabel}</option>)}
              </select>
            </label>
            <label>
              <span>Symbol</span>
              <input aria-label="Symbol" value={addSymbol} onChange={(event) => setAddSymbol(event.target.value)} placeholder="SPY" />
            </label>
            <label>
              <span>Display label</span>
              <input aria-label="Display label" value={addDisplayName} onChange={(event) => setAddDisplayName(event.target.value)} placeholder="Optional" />
            </label>
            <button onClick={handleAddRow} disabled={isRefreshing}>Add</button>
          </div>
          <p className="hm-muted">Rows are saved to the active server-backed HACO view. Unsupported symbols stay visible and fail fast per row.</p>
        </Card>
      ) : null}

      {secondaryPanel === "settings" ? (
        <Card title="HACO view settings">
          <div className="hm-panel-grid">
            <button onClick={handleResetProfile} disabled={isRefreshing}>Reset seeded view to defaults</button>
            <button onClick={() => void loadLatestSnapshot(profileId)} disabled={isRefreshing}>Load last snapshot</button>
          </div>
          <p className="hm-muted">Schedule/email automation is not active from this Phase 1 HACO page. Report preview and CSV export use the active view snapshot.</p>
        </Card>
      ) : null}

      {secondaryPanel === "report" ? (
        <Card title="HACO Direction report preview">
          {reportHtml ? <div className="hm-report-preview" dangerouslySetInnerHTML={{ __html: reportHtml }} /> : <EmptyState title="No report preview yet" hint="Generate a preview after a HACO snapshot exists." />}
        </Card>
      ) : null}

      <section className="hm-filter-bar hm-filter-bar-compact" data-testid="haco-heatmap-filter-bar">
        <div className="hm-filter-toolbar">
          <label className="hm-filter-search">
            <span>Search</span>
            <input aria-label="Search symbol/label" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Symbol or label" />
          </label>
          <label>
            <span>Sort</span>
            <select aria-label="Sort selector" value={sort} onChange={(event) => setSort(event.target.value)}>
              {SORT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label>
            <span>Direction</span>
            <select aria-label="Direction filter" value={directionFilter} onChange={(event) => setDirectionFilter(event.target.value as DirectionFilter)}>
              <option value="all">All directions</option>
              <option value="long">Show LONG only</option>
              <option value="short">Show SHORT only</option>
              <option value="mixed">Show Mixed/Chop</option>
            </select>
          </label>
          <label className="hm-inline-check hm-filter-check">
            <input type="checkbox" checked={hideUnsupported} onChange={(event) => setHideUnsupported(event.target.checked)} />
            Hide unsupported
          </label>
          <button
            type="button"
            className="hm-filter-toggle"
            aria-expanded={showAdvancedFilters}
            aria-controls="haco-advanced-filters"
            onClick={() => setShowAdvancedFilters((value) => !value)}
          >
            Advanced filters
          </button>
        </div>
        {showAdvancedFilters ? (
          <div className="hm-filter-advanced" id="haco-advanced-filters" data-testid="haco-advanced-filters">
            <label className="hm-inline-check">
              <input type="checkbox" checked={changedOnly} onChange={(event) => setChangedOnly(event.target.checked)} />
              Changed since last snapshot
            </label>
            <label>
              <span>Alignment min</span>
              <input aria-label="Alignment minimum" type="number" value={alignmentMin} onChange={(event) => setAlignmentMin(event.target.value)} placeholder="Min" />
            </label>
            <label>
              <span>Alignment max</span>
              <input aria-label="Alignment maximum" type="number" value={alignmentMax} onChange={(event) => setAlignmentMax(event.target.value)} placeholder="Max" />
            </label>
            <button type="button" className="hm-filter-reset" onClick={resetFilters}>Reset filters</button>
          </div>
        ) : null}
      </section>

      {!hasPreviousSnapshot ? (
        <div className="hm-delta-notice" data-testid="haco-heatmap-change-notice">Changes need two successful snapshots.</div>
      ) : null}

      <section className="hm-table-workflow">
        {categories.length === 0 ? (
          <EmptyState title="No HACO categories configured" hint="Load a server profile or add rows to a HACO heatmap view." />
        ) : null}
        {categories.map((category) => {
          const resultCategory = heatmapByCategory.get(category.categoryId);
          const rows = filteredRows(category);
          const summary = categorySummary(category, resultCategory, summariesByCategory.get(category.categoryId));
          const isLoadingCategory = refreshingCategoryIds.has(category.categoryId);
          return (
            <Card key={category.categoryId}>
              <section className="hm-category-card" data-testid={`haco-heatmap-category-${category.categoryId}`}>
                <div className="hm-category-header">
                  <div className="hm-category-title">
                    <h3>{category.categoryLabel}</h3>
                    <StatusBadge tone={summary.status === "fresh" ? "good" : summary.status === "failed" ? "bad" : "warn"}>{isLoadingCategory ? "refreshing..." : summary.status}</StatusBadge>
                    <span className="hm-category-strength">{summary.average_alignment_percent == null ? "avg --" : `avg ${fmt(summary.average_alignment_percent)}`}</span>
                    {categoryErrors[category.categoryId] ? <StatusBadge tone="bad">{categoryErrors[category.categoryId]}</StatusBadge> : null}
                  </div>
                  <div className="hm-category-actions op-row">
                    <label className="hm-inline-check">
                      <input
                        type="checkbox"
                        checked={category.included !== false}
                        onChange={(event) => void toggleCategory(category.categoryId, { included: event.target.checked }, "HACO category include state saved.")}
                      />
                      Include in refresh
                    </label>
                    <button onClick={() => refreshCategories([category])} disabled={isRefreshing || isReporting}>Refresh this category</button>
                    <button onClick={() => void toggleCategory(category.categoryId, { collapsed: !category.collapsed }, "HACO category collapsed state saved.")}>{category.collapsed ? "Expand" : "Collapse"}</button>
                  </div>
                </div>

                <div className="hm-summary-strip">
                  <div className="hm-summary-card"><strong>{summary.count_long}</strong><span>LONG</span></div>
                  <div className="hm-summary-card"><strong>{summary.count_short}</strong><span>SHORT</span></div>
                  <div className="hm-summary-card"><strong>{summary.count_mixed}</strong><span>Mixed</span></div>
                  <div className="hm-summary-card"><strong>{summary.count_unsupported}</strong><span>Unsupported</span></div>
                  <div className="hm-summary-card"><strong>{summary.count_unavailable_error}</strong><span>Unavailable</span></div>
                </div>

                {!category.collapsed ? (
                  <div className="hm-table-wrap hm-category-table">
                    <table className="hm-table haco-heatmap-table">
                      <thead>
                        <tr>
                          <th>Symbol / label</th>
                          <th>Overall Bias</th>
                          <th>Overall Alignment %</th>
                          <th>Daily Context</th>
                          <th>Short-Term Bias</th>
                          <th>Short-Term Alignment %</th>
                          {TIMEFRAME_LABELS.map((timeframe) => <th key={timeframe.key}>{timeframe.label}</th>)}
                          <th>Tags</th>
                          <th>Changed Since Last</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.length === 0 ? (
                          <tr><td colSpan={14}>No rows match current HACO filters.</td></tr>
                        ) : rows.map((row) => {
                          const availability = rowAvailability(row);
                          const change = changes[row.id];
                          const symbolDisplay = hacoHeatmapSymbolDisplayParts(row);
                          return (
                            <tr key={row.id} className={availability !== "ok" ? "is-unavailable" : ""} title={rowReason(row) ?? undefined}>
                              <td className="hm-symbol-cell">
                                <strong>{symbolDisplay.label}</strong>
                                {symbolDisplay.providerLabel ? <span className="hm-symbol-provider">Provider: {symbolDisplay.providerLabel}</span> : null}
                              </td>
                              <td><StatusBadge tone={biasTone(row.overall_bias)}>{row.overall_bias ?? "—"}</StatusBadge></td>
                              <td className="hm-cell">{fmt(row.overall_alignment_percent)}</td>
                              <td><StatusBadge tone={biasTone(row.daily_context)}>{row.daily_context ?? "—"}</StatusBadge></td>
                              <td><StatusBadge tone={biasTone(row.short_term_bias)}>{row.short_term_bias ?? "—"}</StatusBadge></td>
                              <td className="hm-cell">{fmt(row.short_term_alignment_percent)}</td>
                              {TIMEFRAME_LABELS.map((timeframe) => <StateCell key={timeframe.key} cell={row.states?.[timeframe.key]} />)}
                              <td className="haco-tag-cell" title={(row.tags ?? []).join(" | ")}>{(row.tags ?? []).join(", ") || "—"}</td>
                              <td className="hm-cell" title={change?.reason ?? undefined}>
                                {change?.changed_since_last || row.changed_since_last
                                  ? `${change?.prior_overall_bias ?? row.prior_overall_bias ?? "—"} → ${row.overall_bias ?? "—"} (${fmt(change?.alignment_delta ?? row.alignment_delta)})`
                                  : hasPreviousSnapshot ? "—" : "n/a"}
                              </td>
                              <td><button className="hm-row-action" title={`Remove ${row.displayName}`} onClick={() => void handleRemoveRow(row)}>Remove</button></td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </section>
            </Card>
          );
        })}
      </section>
    </div>
  );
}
