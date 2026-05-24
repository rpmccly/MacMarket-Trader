import { SUPPORTED_TIMEFRAME_VALUES, type SupportedTimeframe } from "@/lib/timeframes";

export const HEATMAP_REFRESH_ROW_CHUNK_SIZE = 8;

export type MomentumHeatmapScoreStatus = "ok" | "unavailable" | "unsupported" | "error";

export type MomentumHeatmapScoreCell = {
  value: number | null;
  status: MomentumHeatmapScoreStatus;
  reason?: string | null;
  data_source?: string | null;
  fallback_mode?: boolean | null;
  as_of?: string | null;
  stale?: boolean | null;
};

export type MomentumHeatmapSqueezeCell = {
  value: string | null;
  status: "deferred" | "ok" | "unavailable";
  reason?: string | null;
  state?: "high" | "mid" | "low" | "none" | null;
  as_of?: string | null;
  timeframes?: Record<string, {
    status?: string | null;
    state?: string | null;
    value?: string | null;
    reason?: string | null;
    oscillator_value?: number | null;
    oscillator_state?: string | null;
    as_of?: string | null;
    data_source?: string | null;
    fallback_mode?: boolean | null;
  }>;
};

export type MomentumHeatmapRequestRow = {
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

export type MomentumHeatmapRequestCategory = {
  categoryId: string;
  categoryLabel: string;
  rows: MomentumHeatmapRequestRow[];
};

export type MomentumHeatmapRequest = {
  profileId?: string;
  categories: MomentumHeatmapRequestCategory[];
  timeframes: SupportedTimeframe[];
};

export type MomentumHeatmapResponseRow = {
  id: string;
  symbol: string;
  displayName: string;
  providerSymbol: string;
  scores: Record<SupportedTimeframe, MomentumHeatmapScoreCell>;
  long_term_score: number | null;
  short_term_score: number | null;
  strength_percent: number | null;
  squeeze: MomentumHeatmapSqueezeCell;
  row_tags?: string[];
  availability_status?: string;
  stale?: boolean;
};

export type MomentumHeatmapResponseCategory = {
  categoryId: string;
  categoryLabel: string;
  rows: MomentumHeatmapResponseRow[];
};

export type MomentumHeatmapResponse = {
  generated_at: string;
  timeframes: SupportedTimeframe[];
  categories: MomentumHeatmapResponseCategory[];
};

export type MomentumHeatmapProfileCategory = MomentumHeatmapRequestCategory & {
  included?: boolean;
  collapsed?: boolean;
};

export type MomentumHeatmapViewSettings = {
  sort?: string;
  filters?: Record<string, unknown>;
  showDeltas?: boolean;
  staleThresholdHours?: number;
  slug?: string;
  viewType?: string;
  description?: string;
  purpose?: string;
  isSystemSeeded?: boolean;
};

export type MomentumHeatmapReportPreferences = {
  includeFullTable?: boolean;
  includeCsvAttachment?: boolean;
  reportMode?: string;
};

export type MomentumHeatmapServerProfile = {
  id: string;
  profileId: string;
  databaseId?: number;
  name: string;
  description?: string | null;
  slug?: string | null;
  viewType?: string | null;
  categories: MomentumHeatmapProfileCategory[];
  colorRanges: unknown[];
  viewSettings: MomentumHeatmapViewSettings;
  reportPreferences: MomentumHeatmapReportPreferences;
  isDefault?: boolean;
  isSystemSeeded?: boolean;
  isDefaultSeed?: boolean;
  createdAt?: string | null;
  updatedAt?: string | null;
};

export type MomentumHeatmapSchedulePreferences = {
  id?: string;
  profileId?: string;
  enabled: boolean;
  timezone: string;
  runTime: string;
  daysOfWeek: string[];
  reportMode: "latest_snapshot" | "refresh_then_report" | string;
  recipients: string[];
  includeCsvAttachment: boolean;
  includeFullTable: boolean;
  latestStatus?: string;
  nextRunAt?: string | null;
  schedulerActive?: boolean;
  runnerHook?: string;
};

export type MomentumHeatmapSnapshot = {
  id: string;
  databaseId?: number;
  profileId?: number | string;
  status: "fresh" | "partial" | "stale" | "not_refreshed" | "failed" | string;
  generated_at?: string | null;
  generatedAt?: string | null;
  payload: MomentumHeatmapResponse;
  categorySummaries?: MomentumHeatmapCategorySummary[];
  unsupportedSummary?: Record<string, unknown>;
};

export type MomentumHeatmapCategorySummary = {
  categoryId: string;
  categoryLabel: string;
  average_strength_percent: number | null;
  average_long_term_score: number | null;
  average_short_term_score: number | null;
  count_ok: number;
  count_unsupported: number;
  count_unavailable_error: number;
  count_bullish_aligned: number;
  count_bearish_aligned: number;
  count_improving: number;
  count_weakening: number;
  status: "fresh" | "partial" | "stale" | "not_refreshed" | "failed" | string;
};

export type MomentumHeatmapDelta = {
  strength_percent?: number | null;
  long_term_score?: number | null;
  short_term_score?: number | null;
  timeframes?: Partial<Record<SupportedTimeframe, number | null>>;
  became_available?: boolean;
  became_unavailable?: boolean;
};

export type MomentumHeatmapProfilePayload = {
  profile: MomentumHeatmapServerProfile;
  profiles?: MomentumHeatmapServerProfile[];
  schedulePreferences?: MomentumHeatmapSchedulePreferences;
  source: "server" | string;
};

export type MomentumHeatmapRefreshResponse = {
  heatmap: MomentumHeatmapResponse;
  snapshot?: MomentumHeatmapSnapshot | null;
  previousSnapshot?: MomentumHeatmapSnapshot | null;
  deltas?: Record<string, MomentumHeatmapDelta>;
  categorySummaries?: MomentumHeatmapCategorySummary[];
  unsupportedSummary?: Record<string, unknown>;
  categoryStatus?: Record<string, string>;
};

export type MomentumHeatmapLatestSnapshotResponse = {
  profile: MomentumHeatmapServerProfile;
  snapshot: MomentumHeatmapSnapshot | null;
  previousSnapshot?: MomentumHeatmapSnapshot | null;
  deltas?: Record<string, MomentumHeatmapDelta>;
  message: string;
};

export type MomentumHeatmapReportPreviewResponse = {
  report: Record<string, unknown>;
  html: string;
  emailStatus?: string;
};

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload?.detail === "string"
      ? payload.detail
      : typeof payload?.detail?.message === "string"
        ? payload.detail.message
        : `Request failed: ${response.status}`;
    const error = new Error(detail);
    (error as Error & { payload?: unknown; status?: number }).payload = payload;
    (error as Error & { payload?: unknown; status?: number }).status = response.status;
    throw error;
  }
  return payload as T;
}

export function chunkMomentumHeatmapCategory(
  category: MomentumHeatmapRequestCategory,
  chunkSize = HEATMAP_REFRESH_ROW_CHUNK_SIZE,
): MomentumHeatmapRequestCategory[] {
  const size = Math.max(1, Math.floor(chunkSize));
  const chunks: MomentumHeatmapRequestCategory[] = [];
  for (let index = 0; index < category.rows.length; index += size) {
    chunks.push({
      categoryId: category.categoryId,
      categoryLabel: category.categoryLabel,
      rows: category.rows.slice(index, index + size),
    });
  }
  return chunks.length > 0 ? chunks : [{ ...category, rows: [] }];
}

export function mergeMomentumHeatmapResponse(
  previous: MomentumHeatmapResponse | null,
  next: MomentumHeatmapResponse,
): MomentumHeatmapResponse {
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
      const scores = { ...nextRow.scores };
      for (const timeframe of SUPPORTED_TIMEFRAME_VALUES) {
        const nextCell = nextRow.scores?.[timeframe];
        const previousCell = previousRow.scores?.[timeframe];
        if (nextCell?.status !== "ok" && previousCell?.status === "ok") {
          scores[timeframe] = {
            ...previousCell,
            stale: true,
            reason: `stale_previous_value_after_refresh_failed:${nextCell?.reason ?? nextCell?.status ?? "unknown"}`,
          };
        }
      }
      rows.set(nextRow.id, {
        ...nextRow,
        scores,
        long_term_score: nextRow.long_term_score ?? previousRow.long_term_score,
        short_term_score: nextRow.short_term_score ?? previousRow.short_term_score,
        strength_percent: nextRow.strength_percent ?? previousRow.strength_percent,
        squeeze: nextRow.squeeze?.status === "ok" ? nextRow.squeeze : previousRow.squeeze,
        stale: Object.values(scores).some((cell) => cell?.stale),
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

export async function fetchMomentumHeatmap(categories: MomentumHeatmapRequestCategory[]): Promise<MomentumHeatmapResponse> {
  const response = await fetch("/api/charts/momentum-heatmap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      categories,
      timeframes: [...SUPPORTED_TIMEFRAME_VALUES],
    } satisfies MomentumHeatmapRequest),
  });
  if (!response.ok) {
    throw new Error(`Failed to load Momentum Heatmap: ${response.status}`);
  }
  return response.json() as Promise<MomentumHeatmapResponse>;
}

function profileQuery(profileId?: string): string {
  return profileId ? `?profileId=${encodeURIComponent(profileId)}` : "";
}

export async function fetchMomentumHeatmapProfile(profileId?: string): Promise<MomentumHeatmapProfilePayload> {
  const response = await fetch(`/api/user/momentum-heatmap/profile${profileQuery(profileId)}`, { cache: "no-store" });
  return parseJsonResponse<MomentumHeatmapProfilePayload>(response);
}

export async function createMomentumHeatmapProfile(input: {
  name: string;
  description?: string;
  categories?: MomentumHeatmapProfileCategory[];
  colorRanges?: unknown[];
  viewSettings?: MomentumHeatmapViewSettings;
  reportPreferences?: MomentumHeatmapReportPreferences;
}): Promise<MomentumHeatmapProfilePayload> {
  const response = await fetch("/api/user/momentum-heatmap/profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseJsonResponse<MomentumHeatmapProfilePayload>(response);
}

export async function saveMomentumHeatmapProfile(profile: Partial<MomentumHeatmapServerProfile>): Promise<MomentumHeatmapProfilePayload> {
  const response = await fetch("/api/user/momentum-heatmap/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profileId: profile.profileId ?? profile.id,
      name: profile.name,
      categories: profile.categories,
      colorRanges: profile.colorRanges,
      viewSettings: profile.viewSettings,
      reportPreferences: profile.reportPreferences,
    }),
  });
  return parseJsonResponse<MomentumHeatmapProfilePayload>(response);
}

export async function duplicateMomentumHeatmapProfile(input: { profileId: string; name?: string }): Promise<MomentumHeatmapProfilePayload> {
  const response = await fetch("/api/user/momentum-heatmap/profile/duplicate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseJsonResponse<MomentumHeatmapProfilePayload>(response);
}

export async function resetMomentumHeatmapProfile(profileId: string): Promise<MomentumHeatmapProfilePayload> {
  const response = await fetch("/api/user/momentum-heatmap/profile/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profileId }),
  });
  return parseJsonResponse<MomentumHeatmapProfilePayload>(response);
}

export async function deleteMomentumHeatmapProfile(profileId: string): Promise<MomentumHeatmapProfilePayload & { deleted?: boolean }> {
  const response = await fetch(`/api/user/momentum-heatmap/profile/${encodeURIComponent(profileId)}`, {
    method: "DELETE",
  });
  return parseJsonResponse<MomentumHeatmapProfilePayload & { deleted?: boolean }>(response);
}

export async function addMomentumHeatmapRow(input: {
  profileId?: string;
  categoryId: string;
  symbol: string;
  displayName?: string;
  providerSymbol?: string;
}): Promise<MomentumHeatmapProfilePayload & { warning?: string | null; row?: MomentumHeatmapRequestRow }> {
  const response = await fetch("/api/user/momentum-heatmap/rows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseJsonResponse<MomentumHeatmapProfilePayload & { warning?: string | null; row?: MomentumHeatmapRequestRow }>(response);
}

export async function removeMomentumHeatmapRow(input: { profileId?: string; rowId: string }): Promise<MomentumHeatmapProfilePayload> {
  const suffix = input.profileId ? `?profileId=${encodeURIComponent(input.profileId)}` : "";
  const response = await fetch(`/api/user/momentum-heatmap/rows/${encodeURIComponent(input.rowId)}${suffix}`, {
    method: "DELETE",
  });
  return parseJsonResponse<MomentumHeatmapProfilePayload>(response);
}

export async function refreshMomentumHeatmapSnapshot(categories: MomentumHeatmapRequestCategory[], profileId?: string): Promise<MomentumHeatmapRefreshResponse> {
  const response = await fetch("/api/user/momentum-heatmap/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profileId,
      categories,
      timeframes: [...SUPPORTED_TIMEFRAME_VALUES],
    } satisfies MomentumHeatmapRequest),
  });
  return parseJsonResponse<MomentumHeatmapRefreshResponse>(response);
}

export async function fetchLatestMomentumHeatmapSnapshot(profileId?: string): Promise<MomentumHeatmapLatestSnapshotResponse> {
  const response = await fetch(`/api/user/momentum-heatmap/snapshots/latest${profileQuery(profileId)}`, { cache: "no-store" });
  return parseJsonResponse<MomentumHeatmapLatestSnapshotResponse>(response);
}

export async function generateMomentumHeatmapReportPreview(snapshotId?: string, profileId?: string): Promise<MomentumHeatmapReportPreviewResponse> {
  const response = await fetch("/api/user/momentum-heatmap/report/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ snapshotId, profileId }),
  });
  return parseJsonResponse<MomentumHeatmapReportPreviewResponse>(response);
}

export async function downloadMomentumHeatmapCsv(snapshotId?: string, profileId?: string): Promise<{ csv: string; filename: string }> {
  const response = await fetch("/api/user/momentum-heatmap/report/csv", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ snapshotId, profileId }),
  });
  return parseJsonResponse<{ csv: string; filename: string }>(response);
}

export async function emailMomentumHeatmapReport(input: { snapshotId?: string; profileId?: string; recipients: string[] }): Promise<{ emailStatus: string; sentTo?: string[] }> {
  const response = await fetch("/api/user/momentum-heatmap/report/email", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseJsonResponse<{ emailStatus: string; sentTo?: string[] }>(response);
}

export async function fetchMomentumHeatmapSchedule(profileId?: string): Promise<{ schedulePreferences: MomentumHeatmapSchedulePreferences; timingSuggestions: Array<{ time: string; label: string; note: string }>; schedulerActive: boolean; runnerHook: string }> {
  const response = await fetch(`/api/user/momentum-heatmap/schedule${profileQuery(profileId)}`, { cache: "no-store" });
  return parseJsonResponse(response);
}

export async function saveMomentumHeatmapSchedule(input: Partial<MomentumHeatmapSchedulePreferences>): Promise<{ schedulePreferences: MomentumHeatmapSchedulePreferences; message: string; schedulerActive: boolean }> {
  const response = await fetch("/api/user/momentum-heatmap/schedule", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return parseJsonResponse(response);
}
