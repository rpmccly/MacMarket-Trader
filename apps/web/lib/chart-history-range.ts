// Shared chart history-range model. Used by every chart surface in
// the app so the operator can ask the backend for a wider window of
// historical bars (1M / 3M / 6M / 1Y / 2Y / 5Y) and pan farther back
// into the loaded history. The model is pure — no fetch, no
// localStorage I/O. The component that owns range state handles
// persistence via ``macmarket.chart.historyRange``.

export type ChartHistoryRangeId =
  | "1M"
  | "3M"
  | "6M"
  | "1Y"
  | "2Y"
  | "5Y";

export type ChartHistoryRangeOption = {
  id: ChartHistoryRangeId;
  label: string;
  lookbackDays: number;
  description: string;
};

export const CHART_HISTORY_RANGES: ReadonlyArray<ChartHistoryRangeOption> = [
  { id: "1M", label: "1M", lookbackDays: 31, description: "~1 month of bars" },
  { id: "3M", label: "3M", lookbackDays: 93, description: "~3 months of bars" },
  { id: "6M", label: "6M", lookbackDays: 186, description: "~6 months of bars" },
  { id: "1Y", label: "1Y", lookbackDays: 366, description: "~1 year of bars (default)" },
  { id: "2Y", label: "2Y", lookbackDays: 732, description: "~2 years of bars" },
  { id: "5Y", label: "5Y", lookbackDays: 1830, description: "~5 years of bars" },
];

export const CHART_HISTORY_RANGE_IDS: ReadonlyArray<ChartHistoryRangeId> =
  CHART_HISTORY_RANGES.map((option) => option.id);

const RANGE_BY_ID = new Map<ChartHistoryRangeId, ChartHistoryRangeOption>(
  CHART_HISTORY_RANGES.map((option) => [option.id, option]),
);

export const CHART_HISTORY_RANGE_STORAGE_KEY = "macmarket.chart.historyRange";

export function defaultChartHistoryRange(): ChartHistoryRangeId {
  return "1Y";
}

export function isChartHistoryRangeId(value: unknown): value is ChartHistoryRangeId {
  return (
    typeof value === "string" &&
    (CHART_HISTORY_RANGE_IDS as ReadonlyArray<string>).includes(value)
  );
}

export function validateChartHistoryRange(value: unknown): ChartHistoryRangeId {
  if (isChartHistoryRangeId(value)) return value;
  return defaultChartHistoryRange();
}

export function chartHistoryRangeToLookbackDays(
  value: unknown,
): number {
  const id = validateChartHistoryRange(value);
  const option = RANGE_BY_ID.get(id);
  if (!option) return RANGE_BY_ID.get(defaultChartHistoryRange())!.lookbackDays;
  return option.lookbackDays;
}

export function chartHistoryRangeOption(
  value: unknown,
): ChartHistoryRangeOption {
  const id = validateChartHistoryRange(value);
  return RANGE_BY_ID.get(id) ?? RANGE_BY_ID.get(defaultChartHistoryRange())!;
}

/**
 * Read the persisted chart history-range id from localStorage.
 * Falls back to {@link defaultChartHistoryRange} on any parse failure
 * or missing entry. Safe to call from SSR (returns the default).
 */
export function readChartHistoryRangeFromStorage(): ChartHistoryRangeId {
  if (typeof window === "undefined") return defaultChartHistoryRange();
  try {
    const raw = window.localStorage.getItem(CHART_HISTORY_RANGE_STORAGE_KEY);
    if (!raw) return defaultChartHistoryRange();
    return validateChartHistoryRange(raw);
  } catch {
    return defaultChartHistoryRange();
  }
}

export function writeChartHistoryRangeToStorage(value: ChartHistoryRangeId | string): void {
  if (typeof window === "undefined") return;
  try {
    const id = validateChartHistoryRange(value);
    window.localStorage.setItem(CHART_HISTORY_RANGE_STORAGE_KEY, id);
  } catch {
    // best-effort
  }
}
