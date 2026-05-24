import { SUPPORTED_TIMEFRAME_VALUES, type SupportedTimeframe } from "@/lib/timeframes";

export const HACO_HEATMAP_REFRESH_ROW_CHUNK_SIZE = 8;

export type HacoHeatmapCellStatus = "ok" | "unavailable" | "unsupported" | "error";

export type HacoHeatmapDirectionCell = {
  value: "long" | "short" | null;
  label: "LONG" | "SHORT" | "—" | string;
  status: HacoHeatmapCellStatus;
  reason?: string | null;
  as_of?: string | null;
  data_source?: string | null;
  fallback_mode?: boolean | null;
  stale?: boolean | null;
};

export type HacoHeatmapRequestRow = {
  id: string;
  symbol: string;
  displayName?: string;
  providerSymbol?: string;
  originalSymbol?: string;
  workbookOrder?: number;
  enabled?: boolean;
  userAdded?: boolean;
  unsupported?: boolean;
  unsupportedReason?: string | null;
  notes?: string | null;
};

export type HacoHeatmapRequestCategory = {
  categoryId: string;
  categoryLabel: string;
  rows: HacoHeatmapRequestRow[];
  included?: boolean;
  collapsed?: boolean;
};

export type HacoHeatmapRequest = {
  profileId?: string;
  categories: HacoHeatmapRequestCategory[];
  timeframes: SupportedTimeframe[];
};

export type HacoHeatmapRefreshRow = Pick<HacoHeatmapRequestRow, "id" | "symbol" | "displayName" | "providerSymbol">;

export type HacoHeatmapRefreshCategory = {
  categoryId: string;
  categoryLabel: string;
  rows: HacoHeatmapRefreshRow[];
};

export type HacoHeatmapRefreshRequest = {
  profileId?: string;
  categories: HacoHeatmapRefreshCategory[];
  timeframes: SupportedTimeframe[];
};

export type HacoHeatmapResponseRow = {
  id: string;
  symbol: string;
  displayName: string;
  providerSymbol: string;
  states: Record<SupportedTimeframe, HacoHeatmapDirectionCell>;
  overall_bias: "LONG" | "SHORT" | "MIXED" | null;
  overall_alignment_percent: number | null;
  daily_context: "LONG" | "SHORT" | null;
  macro_context?: "LONG" | "SHORT" | null;
  short_term_bias: "LONG" | "SHORT" | "MIXED" | null;
  short_term_alignment_percent: number | null;
  tags: string[];
  changed_since_last?: boolean;
  prior_overall_bias?: "LONG" | "SHORT" | "MIXED" | null;
  alignment_delta?: number | null;
};

export type HacoHeatmapResponseCategory = {
  categoryId: string;
  categoryLabel: string;
  rows: HacoHeatmapResponseRow[];
};

export type HacoHeatmapResponse = {
  generated_at: string;
  timeframes: SupportedTimeframe[];
  categories: HacoHeatmapResponseCategory[];
};

export type HacoHeatmapViewSettings = {
  sort?: string;
  filters?: Record<string, unknown>;
  showChanges?: boolean;
  slug?: string;
  viewType?: string;
  description?: string;
  purpose?: string;
  isSystemSeeded?: boolean;
};

export type HacoHeatmapReportPreferences = {
  includeFullTable?: boolean;
  reportMode?: string;
};

export type HacoHeatmapServerProfile = {
  id: string;
  profileId: string;
  databaseId?: number;
  name: string;
  description?: string | null;
  slug?: string | null;
  viewType?: string | null;
  categories: HacoHeatmapRequestCategory[];
  viewSettings: HacoHeatmapViewSettings;
  reportPreferences: HacoHeatmapReportPreferences;
  isDefault?: boolean;
  isSystemSeeded?: boolean;
  createdAt?: string | null;
  updatedAt?: string | null;
};

export type HacoHeatmapCategorySummary = {
  categoryId: string;
  categoryLabel: string;
  average_alignment_percent: number | null;
  count_long: number;
  count_short: number;
  count_mixed: number;
  count_unsupported: number;
  count_unavailable_error: number;
  status: "fresh" | "partial" | "stale" | "not_refreshed" | "failed" | string;
};

export type HacoHeatmapChange = {
  changed_since_last?: boolean;
  prior_overall_bias?: "LONG" | "SHORT" | "MIXED" | null;
  current_overall_bias?: "LONG" | "SHORT" | "MIXED" | null;
  alignment_delta?: number | null;
  timeframe_flips?: Partial<Record<SupportedTimeframe, { prior: string | null; current: string | null }>>;
  reason?: string | null;
};

export type HacoHeatmapSnapshot = {
  id: string;
  databaseId?: number;
  profileId?: number | string;
  status: "fresh" | "partial" | "stale" | "not_refreshed" | "failed" | string;
  generated_at?: string | null;
  generatedAt?: string | null;
  payload: HacoHeatmapResponse;
  categorySummaries?: HacoHeatmapCategorySummary[];
  unsupportedSummary?: Record<string, unknown>;
};

export type HacoHeatmapProfilePayload = {
  profile: HacoHeatmapServerProfile;
  profiles?: HacoHeatmapServerProfile[];
  source: "server" | string;
};

export type HacoHeatmapRefreshResponse = {
  heatmap: HacoHeatmapResponse;
  snapshot?: HacoHeatmapSnapshot | null;
  previousSnapshot?: HacoHeatmapSnapshot | null;
  changes?: Record<string, HacoHeatmapChange>;
  categorySummaries?: HacoHeatmapCategorySummary[];
  unsupportedSummary?: Record<string, unknown>;
  categoryStatus?: Record<string, string>;
};

export type HacoHeatmapLatestSnapshotResponse = {
  profile: HacoHeatmapServerProfile;
  snapshot: HacoHeatmapSnapshot | null;
  previousSnapshot?: HacoHeatmapSnapshot | null;
  changes?: Record<string, HacoHeatmapChange>;
  message: string;
};

export type HacoHeatmapReportPreviewResponse = {
  report: Record<string, unknown>;
  html: string;
  emailStatus?: string;
};

function readText(source: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (trimmed) return trimmed;
    }
  }
  return "";
}

function formatApiDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const rendered = detail.slice(0, 5).map((item) => {
      if (!item || typeof item !== "object") return String(item);
      const record = item as Record<string, unknown>;
      const loc = Array.isArray(record.loc) ? record.loc.map(String).join(".") : "";
      const msg = typeof record.msg === "string" ? record.msg : typeof record.message === "string" ? record.message : "";
      return [loc, msg].filter(Boolean).join(": ");
    }).filter(Boolean);
    if (!rendered.length) return null;
    const remaining = detail.length > rendered.length ? `; ${detail.length - rendered.length} more validation error(s)` : "";
    return `${rendered.join("; ")}${remaining}`;
  }
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    if (typeof record.message === "string") return record.message;
    if (record.detail) return formatApiDetail(record.detail);
  }
  return null;
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = formatApiDetail((payload as { detail?: unknown })?.detail ?? payload);
    const error = new Error(detail ? `Request failed: ${response.status} - ${detail}` : `Request failed: ${response.status}`);
    (error as Error & { payload?: unknown; status?: number }).payload = payload;
    (error as Error & { payload?: unknown; status?: number }).status = response.status;
    throw error;
  }
  return payload as T;
}

function profileQuery(profileId?: string): string {
  return profileId ? `?profileId=${encodeURIComponent(profileId)}` : "";
}

export function chunkHacoHeatmapCategory(
  category: HacoHeatmapRequestCategory,
  chunkSize = HACO_HEATMAP_REFRESH_ROW_CHUNK_SIZE,
): HacoHeatmapRefreshCategory[] {
  const size = Math.max(1, Math.floor(chunkSize));
  const rows = (category.rows ?? []).map(normalizeHacoHeatmapRefreshRow);
  const chunks: HacoHeatmapRefreshCategory[] = [];
  for (let index = 0; index < rows.length; index += size) {
    chunks.push({
      categoryId: category.categoryId,
      categoryLabel: category.categoryLabel,
      rows: rows.slice(index, index + size),
    });
  }
  return chunks.length > 0 ? chunks : [{ categoryId: category.categoryId, categoryLabel: category.categoryLabel, rows: [] }];
}

export function normalizeHacoHeatmapRefreshRow(row: HacoHeatmapRequestRow): HacoHeatmapRefreshRow {
  const source = row as unknown as Record<string, unknown>;
  const id = readText(source, "id") || readText(source, "providerSymbol", "provider_symbol", "symbol") || "unknown";
  const providerSymbol = readText(source, "providerSymbol", "provider_symbol", "symbol") || id;
  const symbol = readText(source, "symbol", "providerSymbol", "provider_symbol") || providerSymbol;
  const displayName = readText(source, "displayName", "display_name") || symbol || providerSymbol;
  return { id, symbol, displayName, providerSymbol };
}

export function normalizeHacoHeatmapRefreshCategory(category: HacoHeatmapRequestCategory): HacoHeatmapRefreshCategory {
  return {
    categoryId: category.categoryId,
    categoryLabel: category.categoryLabel,
    rows: (category.rows ?? []).map(normalizeHacoHeatmapRefreshRow),
  };
}

export function buildHacoHeatmapRefreshPayload(
  categories: HacoHeatmapRequestCategory[],
  profileId?: string,
): HacoHeatmapRefreshRequest {
  return {
    profileId,
    categories: categories.map(normalizeHacoHeatmapRefreshCategory),
    timeframes: [...SUPPORTED_TIMEFRAME_VALUES],
  };
}

export function hacoHeatmapSymbolDisplayParts(input: {
  displayName?: string | null;
  providerSymbol?: string | null;
  symbol?: string | null;
}): { label: string; providerLabel: string | null } {
  const providerSymbol = (input.providerSymbol || input.symbol || "").trim();
  const label = (input.displayName || input.symbol || providerSymbol || "Unknown").trim();
  const providerLabel = providerSymbol && providerSymbol.toUpperCase() !== label.toUpperCase() ? providerSymbol : null;
  return { label, providerLabel };
}

export function mergeHacoHeatmapResponse(
  previous: HacoHeatmapResponse | null,
  next: HacoHeatmapResponse,
): HacoHeatmapResponse {
  if (!previous) return next;
  const categories = new Map(previous.categories.map((category) => [category.categoryId, category]));
  for (const nextCategory of next.categories) {
    const existing = categories.get(nextCategory.categoryId);
    if (!existing) {
      categories.set(nextCategory.categoryId, nextCategory);
      continue;
    }
    const rows = new Map(existing.rows.map((row) => [row.id, row]));
    for (const nextRow of nextCategory.rows) {
      const previousRow = rows.get(nextRow.id);
      if (!previousRow) {
        rows.set(nextRow.id, nextRow);
        continue;
      }
      const states = { ...nextRow.states };
      for (const timeframe of SUPPORTED_TIMEFRAME_VALUES) {
        const nextCell = nextRow.states?.[timeframe];
        const previousCell = previousRow.states?.[timeframe];
        if (nextCell?.status !== "ok" && previousCell?.status === "ok") {
          states[timeframe] = {
            ...previousCell,
            stale: true,
            reason: `stale_previous_haco_value_after_refresh_failed:${nextCell?.reason ?? nextCell?.status ?? "unknown"}`,
          };
        }
      }
      rows.set(nextRow.id, {
        ...nextRow,
        states,
        overall_bias: nextRow.overall_bias ?? previousRow.overall_bias,
        overall_alignment_percent: nextRow.overall_alignment_percent ?? previousRow.overall_alignment_percent,
        short_term_bias: nextRow.short_term_bias ?? previousRow.short_term_bias,
        short_term_alignment_percent: nextRow.short_term_alignment_percent ?? previousRow.short_term_alignment_percent,
      });
    }
    categories.set(nextCategory.categoryId, {
      ...existing,
      categoryLabel: nextCategory.categoryLabel,
      rows: Array.from(rows.values()),
    });
  }
  return {
    generated_at: next.generated_at,
    timeframes: next.timeframes,
    categories: Array.from(categories.values()),
  };
}

export async function fetchHacoHeatmapProfile(profileId?: string): Promise<HacoHeatmapProfilePayload> {
  const response = await fetch(`/api/user/haco-heatmap/profile${profileQuery(profileId)}`, { cache: "no-store" });
  return parseJsonResponse<HacoHeatmapProfilePayload>(response);
}

export async function saveHacoHeatmapProfile(profile: Partial<HacoHeatmapServerProfile>): Promise<HacoHeatmapProfilePayload> {
  const response = await fetch("/api/user/haco-heatmap/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profileId: profile.profileId ?? profile.id,
      name: profile.name,
      categories: profile.categories,
      viewSettings: profile.viewSettings,
      reportPreferences: profile.reportPreferences,
    }),
  });
  return parseJsonResponse<HacoHeatmapProfilePayload>(response);
}

export async function resetHacoHeatmapProfile(profileId: string): Promise<HacoHeatmapProfilePayload> {
  const response = await fetch("/api/user/haco-heatmap/profile/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profileId }),
  });
  return parseJsonResponse<HacoHeatmapProfilePayload>(response);
}

export async function addHacoHeatmapRow(input: {
  profileId?: string;
  categoryId: string;
  symbol: string;
  displayName?: string;
  providerSymbol?: string;
}): Promise<HacoHeatmapProfilePayload & { warning?: string | null; row?: HacoHeatmapRequestRow }> {
  const response = await fetch("/api/user/haco-heatmap/rows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseJsonResponse<HacoHeatmapProfilePayload & { warning?: string | null; row?: HacoHeatmapRequestRow }>(response);
}

export async function removeHacoHeatmapRow(input: { profileId?: string; rowId: string }): Promise<HacoHeatmapProfilePayload> {
  const suffix = input.profileId ? `?profileId=${encodeURIComponent(input.profileId)}` : "";
  const response = await fetch(`/api/user/haco-heatmap/rows/${encodeURIComponent(input.rowId)}${suffix}`, {
    method: "DELETE",
  });
  return parseJsonResponse<HacoHeatmapProfilePayload>(response);
}

export async function refreshHacoHeatmapSnapshot(categories: HacoHeatmapRequestCategory[], profileId?: string): Promise<HacoHeatmapRefreshResponse> {
  const response = await fetch("/api/user/haco-heatmap/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildHacoHeatmapRefreshPayload(categories, profileId)),
  });
  return parseJsonResponse<HacoHeatmapRefreshResponse>(response);
}

export async function fetchLatestHacoHeatmapSnapshot(profileId?: string): Promise<HacoHeatmapLatestSnapshotResponse> {
  const response = await fetch(`/api/user/haco-heatmap/snapshots/latest${profileQuery(profileId)}`, { cache: "no-store" });
  return parseJsonResponse<HacoHeatmapLatestSnapshotResponse>(response);
}

export async function generateHacoHeatmapReportPreview(snapshotId?: string, profileId?: string): Promise<HacoHeatmapReportPreviewResponse> {
  const response = await fetch("/api/user/haco-heatmap/report/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ snapshotId, profileId }),
  });
  return parseJsonResponse<HacoHeatmapReportPreviewResponse>(response);
}

export async function downloadHacoHeatmapCsv(snapshotId?: string, profileId?: string): Promise<{ csv: string; filename: string }> {
  const response = await fetch("/api/user/haco-heatmap/report/csv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ snapshotId, profileId }),
  });
  return parseJsonResponse<{ csv: string; filename: string }>(response);
}
