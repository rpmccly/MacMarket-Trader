"use client";

import { useEffect, useMemo, useState } from "react";

import { Card, EmptyState, ErrorState, InlineFeedback, PageHeader, StatusBadge } from "@/components/operator-ui";
import { momentumHeatmapScoreClass } from "@/lib/momentum-heatmap-colors";
import {
  DEFAULT_MOMENTUM_HEATMAP_CATEGORIES,
  MOMENTUM_HEATMAP_STORAGE_KEY,
  type MomentumHeatmapCategoryConfig,
  type MomentumHeatmapRowConfig,
} from "@/lib/momentum-heatmap-defaults";
import {
  fetchMomentumHeatmap,
  type MomentumHeatmapResponse,
  type MomentumHeatmapResponseCategory,
  type MomentumHeatmapResponseRow,
  type MomentumHeatmapScoreCell,
} from "@/lib/momentum-heatmap-api";
import type { SupportedTimeframe } from "@/lib/timeframes";

const WORKBOOK_TIMEFRAME_LABELS: Array<{ key: SupportedTimeframe; label: string }> = [
  { key: "1W", label: "Weekly" },
  { key: "1D", label: "Daily" },
  { key: "4H", label: "4HR" },
  { key: "1H", label: "1HR" },
  { key: "30M", label: "30M" },
];

function cloneDefaultCategories(): MomentumHeatmapCategoryConfig[] {
  return DEFAULT_MOMENTUM_HEATMAP_CATEGORIES.map((category) => ({
    ...category,
    rows: category.rows.map((row) => ({ ...row })),
  }));
}

function defaultToggleState(value: boolean): Record<string, boolean> {
  return Object.fromEntries(DEFAULT_MOMENTUM_HEATMAP_CATEGORIES.map((category) => [category.categoryId, value]));
}

function formatScore(value: number | null | undefined, suffix = ""): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value)}${suffix}`;
}

function scoreTitle(cell: MomentumHeatmapScoreCell | null | undefined): string | undefined {
  if (!cell) return undefined;
  const parts = [
    cell.status,
    cell.reason,
    cell.data_source ? `source: ${cell.data_source}` : null,
    cell.fallback_mode ? "fallback mode" : null,
    cell.as_of ? `as of ${cell.as_of}` : null,
  ].filter(Boolean);
  return parts.join(" | ");
}

function HeatmapScoreCell({ cell }: { cell: MomentumHeatmapScoreCell | null | undefined }) {
  const value = cell?.status === "ok" ? cell.value : null;
  const className = value == null ? "hm-score-unavailable" : momentumHeatmapScoreClass(value);
  return (
    <td className={`hm-cell hm-score-cell ${className}`} title={scoreTitle(cell)}>
      {value == null ? "—" : formatScore(value)}
    </td>
  );
}

function DerivedScoreCell({ value, title, suffix = "" }: { value: number | null | undefined; title: string; suffix?: string }) {
  const className = value == null ? "hm-score-unavailable" : momentumHeatmapScoreClass(value);
  return (
    <td className={`hm-cell hm-score-cell ${className}`} title={title}>
      {formatScore(value, suffix)}
    </td>
  );
}

function resultRowById(category: MomentumHeatmapResponseCategory | undefined): Map<string, MomentumHeatmapResponseRow> {
  return new Map((category?.rows ?? []).map((row) => [row.id, row]));
}

export default function MomentumHeatmapPage() {
  const [categories, setCategories] = useState<MomentumHeatmapCategoryConfig[]>(() => cloneDefaultCategories());
  const [includedByCategory, setIncludedByCategory] = useState<Record<string, boolean>>(() => defaultToggleState(true));
  const [collapsedByCategory, setCollapsedByCategory] = useState<Record<string, boolean>>(() => defaultToggleState(false));
  const [selectedCategoryId, setSelectedCategoryId] = useState(DEFAULT_MOMENTUM_HEATMAP_CATEGORIES[0]?.categoryId ?? "");
  const [symbolInput, setSymbolInput] = useState("");
  const [labelInput, setLabelInput] = useState("");
  const [hydrated, setHydrated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ state: "idle" | "loading" | "success" | "error"; message?: string }>({ state: "idle" });
  const [error, setError] = useState<string | null>(null);
  const [heatmap, setHeatmap] = useState<MomentumHeatmapResponse | null>(null);

  useEffect(() => {
    try {
      // localStorage key: macmarket-momentum-heatmap-symbols-v1
      const raw = window.localStorage.getItem(MOMENTUM_HEATMAP_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as MomentumHeatmapCategoryConfig[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setCategories(parsed);
          setSelectedCategoryId(parsed[0]?.categoryId ?? selectedCategoryId);
        }
      }
    } catch {
      setError("Saved heatmap symbols were unreadable. Defaults are loaded for this browser.");
    } finally {
      setHydrated(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    // TODO(momentum-heatmap): move symbol customizations to a per-user backend
    // preference once the product needs cross-browser persistence.
    window.localStorage.setItem(MOMENTUM_HEATMAP_STORAGE_KEY, JSON.stringify(categories));
  }, [categories, hydrated]);

  const resultCategories = useMemo(
    () => new Map((heatmap?.categories ?? []).map((category) => [category.categoryId, category])),
    [heatmap],
  );

  const includedCategories = useMemo(
    () => categories.filter((category) => includedByCategory[category.categoryId] !== false),
    [categories, includedByCategory],
  );

  async function refreshVisibleHeatmap() {
    if (includedCategories.length === 0) {
      setFeedback({ state: "error", message: "Select at least one category for refresh." });
      return;
    }
    setLoading(true);
    setError(null);
    setFeedback({ state: "loading", message: "Refreshing included categories." });
    try {
      const payload = await fetchMomentumHeatmap(
        includedCategories.map((category) => ({
          categoryId: category.categoryId,
          categoryLabel: category.categoryLabel,
          rows: category.rows.map((row) => ({
            id: row.id,
            symbol: row.symbol,
            displayName: row.displayName,
            providerSymbol: row.providerSymbol,
          })),
        })),
      );
      setHeatmap(payload);
      setFeedback({ state: "success", message: `Refreshed ${includedCategories.length} included categories.` });
    } catch (err) {
      setFeedback({ state: "error", message: err instanceof Error ? err.message : "Momentum Heatmap refresh failed." });
    } finally {
      setLoading(false);
    }
  }

  function addSymbol() {
    const symbol = symbolInput.trim().toUpperCase();
    if (!symbol) {
      setFeedback({ state: "error", message: "Enter a symbol before adding a row." });
      return;
    }
    setCategories((current) =>
      current.map((category) => {
        if (category.categoryId !== selectedCategoryId) return category;
        const displayName = labelInput.trim() || symbol;
        const row: MomentumHeatmapRowConfig = {
          id: `${category.categoryId}:${displayName.replace(/[^A-Za-z0-9]+/g, "-").toUpperCase()}:${Date.now()}`,
          categoryId: category.categoryId,
          categoryLabel: category.categoryLabel,
          symbol,
          displayName,
          providerSymbol: symbol,
        };
        return { ...category, rows: [...category.rows, row] };
      }),
    );
    setSymbolInput("");
    setLabelInput("");
    setFeedback({ state: "success", message: `${symbol} added to the heatmap config.` });
  }

  function removeRow(categoryId: string, rowId: string) {
    setCategories((current) =>
      current.map((category) =>
        category.categoryId === categoryId
          ? { ...category, rows: category.rows.filter((row) => row.id !== rowId) }
          : category,
      ),
    );
  }

  function renderCategory(category: MomentumHeatmapCategoryConfig) {
    const resultCategory = resultCategories.get(category.categoryId);
    const rowResults = resultRowById(resultCategory);
    const isCollapsed = collapsedByCategory[category.categoryId] === true;
    const isIncluded = includedByCategory[category.categoryId] !== false;
    return (
      <Card key={category.categoryId}>
        <div className="op-row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <div className="op-row">
            <h3 style={{ margin: 0 }}>{category.categoryLabel}</h3>
            <StatusBadge tone={isIncluded ? "good" : "neutral"}>{isIncluded ? "Included in refresh" : "Excluded"}</StatusBadge>
            <span className="hm-muted">{category.rows.length} rows</span>
          </div>
          <div className="op-row">
            <label>
              <input
                type="checkbox"
                checked={isIncluded}
                onChange={(event) =>
                  setIncludedByCategory((current) => ({ ...current, [category.categoryId]: event.target.checked }))
                }
              />{" "}
              Include in refresh
            </label>
            <button
              type="button"
              onClick={() => setCollapsedByCategory((current) => ({ ...current, [category.categoryId]: !isCollapsed }))}
            >
              {isCollapsed ? "Expand" : "Collapse"}
            </button>
          </div>
        </div>

        {isCollapsed ? null : (
          <div className="hm-table-wrap" style={{ marginTop: 10 }}>
            <table className="op-table hm-table">
              <thead>
                <tr>
                  <th>Symbol / label</th>
                  <th>Long-Term Score</th>
                  <th>Weekly</th>
                  <th>Daily</th>
                  <th>Short-Term Score</th>
                  <th>4HR</th>
                  <th>1HR</th>
                  <th>30M</th>
                  <th>Strength %</th>
                  <th>Squeezes</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {category.rows.map((row) => {
                  const result = rowResults.get(row.id);
                  return (
                    <tr key={row.id}>
                      <td className="hm-symbol-cell">
                        {row.displayName}
                        {row.providerSymbol !== row.displayName ? <div className="hm-muted">Provider: {row.providerSymbol}</div> : null}
                      </td>
                      <DerivedScoreCell value={result?.long_term_score} title="Long-Term Score = (Weekly + Daily) / 2" />
                      {WORKBOOK_TIMEFRAME_LABELS.slice(0, 2).map(({ key }) => (
                        <HeatmapScoreCell key={key} cell={result?.scores?.[key]} />
                      ))}
                      <DerivedScoreCell value={result?.short_term_score} title="Short-Term Score = (4HR + 1HR + 30M) / 3" />
                      {WORKBOOK_TIMEFRAME_LABELS.slice(2).map(({ key }) => (
                        <HeatmapScoreCell key={key} cell={result?.scores?.[key]} />
                      ))}
                      <DerivedScoreCell
                        value={result?.strength_percent}
                        title="Strength % = (Weekly*3 + Daily*3 + 4HR + 1HR + 30M) / 9"
                        suffix="%"
                      />
                      <td title={result?.squeeze.reason ?? "squeeze_algorithm_not_implemented"}>
                        {result?.squeeze.status === "ok" ? result.squeeze.value : "Deferred"}
                      </td>
                      <td>
                        <button type="button" onClick={() => removeRow(category.categoryId, row.id)}>
                          Remove
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    );
  }

  return (
    <>
      <PageHeader
        title="Momentum Heatmap"
        subtitle="Workbook-style True Momentum score review by category and timeframe."
        actions={
          <>
            {heatmap?.generated_at ? <span className="hm-muted">Last refreshed: {new Date(heatmap.generated_at).toLocaleString()}</span> : null}
            <button type="button" onClick={() => void refreshVisibleHeatmap()} disabled={loading}>
              {loading ? "Refreshing..." : "Refresh visible heatmap"}
            </button>
          </>
        }
      />

      <Card title="Heatmap controls">
        <div className="op-row" style={{ alignItems: "end" }}>
          <label>
            Category
            <select value={selectedCategoryId} onChange={(event) => setSelectedCategoryId(event.target.value)}>
              {categories.map((category) => (
                <option key={category.categoryId} value={category.categoryId}>
                  {category.categoryLabel}
                </option>
              ))}
            </select>
          </label>
          <label>
            Symbol
            <input value={symbolInput} onChange={(event) => setSymbolInput(event.target.value)} placeholder="TSLA" />
          </label>
          <label>
            Display label
            <input value={labelInput} onChange={(event) => setLabelInput(event.target.value)} placeholder="Optional" />
          </label>
          <button type="button" onClick={addSymbol}>Add</button>
        </div>
        <p className="hm-muted" style={{ marginBottom: 0 }}>
          Squeeze column deferred until approved squeeze algorithm is added.
        </p>
      </Card>

      <InlineFeedback state={feedback.state} message={feedback.message} />
      {error ? <ErrorState title="Heatmap saved config warning" hint={error} /> : null}
      {!heatmap ? <EmptyState title="Momentum Heatmap not refreshed" hint="Use Refresh visible heatmap to fetch only the included categories." /> : null}

      <div className="op-stack">
        {categories.map((category) => renderCategory(category))}
      </div>
    </>
  );
}
