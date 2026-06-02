import { fetchWorkflowApi } from "@/lib/api-client";

export const DATA_PARITY_TIMEFRAMES = ["1W", "1D", "4H", "1H", "30M"] as const;
export type DataParityTimeframe = (typeof DATA_PARITY_TIMEFRAMES)[number];

export type TosReferenceInput = {
  symbol: string;
  timeframe: string;
  trueMomentumScore?: number | null;
  hacoDirection?: string | null;
  hacoLatestFlip?: string | null;
  hacoltDirection?: string | null;
  hiLoState?: string | null;
  hiLoValue?: number | null;
  squeezeState?: string | null;
  squeezeHistogram?: number | null;
  notes?: string;
};

export type DataParityRunRequest = {
  symbols: string[];
  timeframes: string[];
  lookbackBars: number;
  sessionPolicy: "regular_hours" | string;
  includeExtendedHours: boolean;
  completedBarsOnly?: boolean;
  saveSnapshot: boolean;
  tosReferences: TosReferenceInput[];
};

export type SchwabStatus = {
  provider: string;
  mode: string;
  status: string;
  configured: boolean;
  enabled?: boolean;
  credentials_present: boolean;
  encryption_key_present?: boolean;
  oauth_connected: boolean;
  token_status: string;
  access_state?: string;
  refresh_state?: string;
  requires_reconnect?: boolean;
  last_refresh_at?: string | null;
  access_token_expires_at?: string | null;
  refresh_token_expires_at?: string | null;
  last_error?: string | null;
  details: string;
  operational_impact?: string;
};

export type DataParitySummary = Record<string, number>;

export type DataParityResult = {
  symbol: string;
  timeframe: string;
  rawBars?: Record<string, unknown> | null;
  canonicalBars?: Record<string, unknown> | null;
  indicators?: {
    verdict?: string;
    mismatches?: Array<Record<string, unknown>>;
    current?: Record<string, unknown>;
    candidate?: Record<string, unknown>;
  } | null;
  tosReference?: {
    provided?: boolean;
    verdict?: string;
    mismatches?: Array<Record<string, unknown>>;
    notes?: string;
  };
  rootCause: string;
  freshness?: Record<string, unknown> | null;
  warnings: string[];
  errors: string[];
};

export type DataParityRunResponse = {
  runId: string;
  asOf: string;
  providers: {
    current: Record<string, unknown>;
    candidate: SchwabStatus;
  };
  request: Record<string, unknown>;
  summary: DataParitySummary;
  results: DataParityResult[];
  warnings: string[];
  errors: Array<Record<string, unknown>>;
  readOnly: boolean;
  brokerRoutingEnabled: boolean;
  productionProviderUnchanged: boolean;
};

export type DataParitySnapshotSummary = {
  runId: string;
  createdAt: string | null;
  providerCurrent: string;
  providerCandidate: string;
  symbols: string[];
  timeframes: string[];
  summary: DataParitySummary;
};

export const DATA_PARITY_DEFAULT_SYMBOLS = "SPY, QQQ, MTUM";
export const DATA_PARITY_DEFAULT_LOOKBACK_BARS = 250;

export function createBlankTosReference(): TosReferenceInput {
  return {
    symbol: "",
    timeframe: "1D",
    trueMomentumScore: null,
    hacoDirection: "",
    hacoLatestFlip: "",
    hacoltDirection: "",
    hiLoState: "",
    hiLoValue: null,
    squeezeState: "",
    squeezeHistogram: null,
    notes: "",
  };
}

export function parseParitySymbols(input: string): string[] {
  const seen = new Set<string>();
  return input
    .split(/[\s,]+/)
    .map((part) => part.trim().toUpperCase())
    .filter(Boolean)
    .filter((symbol) => {
      if (seen.has(symbol)) return false;
      seen.add(symbol);
      return true;
    });
}

function optionalNumber(value: unknown): number | null {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function optionalText(value: unknown): string | null {
  const text = String(value ?? "").trim();
  return text ? text : null;
}

export function normalizeTosReferenceRows(rows: TosReferenceInput[]): TosReferenceInput[] {
  return rows
    .map((row) => ({
      symbol: String(row.symbol ?? "").trim().toUpperCase(),
      timeframe: String(row.timeframe ?? "1D").trim().toUpperCase(),
      trueMomentumScore: optionalNumber(row.trueMomentumScore),
      hacoDirection: optionalText(row.hacoDirection),
      hacoLatestFlip: optionalText(row.hacoLatestFlip),
      hacoltDirection: optionalText(row.hacoltDirection),
      hiLoState: optionalText(row.hiLoState),
      hiLoValue: optionalNumber(row.hiLoValue),
      squeezeState: optionalText(row.squeezeState),
      squeezeHistogram: optionalNumber(row.squeezeHistogram),
      notes: String(row.notes ?? "").trim(),
    }))
    .filter((row) => row.symbol && row.timeframe);
}

function valueAt(path: string[], source: unknown): unknown {
  let cursor = source;
  for (const key of path) {
    if (!cursor || typeof cursor !== "object" || !(key in cursor)) return null;
    cursor = (cursor as Record<string, unknown>)[key];
  }
  return cursor;
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "object" ? JSON.stringify(value) : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

export function buildDataParityCsv(response: DataParityRunResponse): string {
  const rows = response.results.map((result) => [
    result.symbol,
    result.timeframe,
    valueAt(["verdict"], result.rawBars),
    valueAt(["verdict"], result.canonicalBars),
    valueAt(["verdict"], result.indicators),
    result.tosReference?.verdict ?? "",
    result.rootCause,
    valueAt(["alignment_mode"], result.canonicalBars),
    valueAt(["comparison_scope"], result.canonicalBars),
    valueAt(["latest_common_alignment_label"], result.canonicalBars),
    valueAt(["latest_current_alignment", "timestamp_convention"], result.canonicalBars),
    valueAt(["latest_candidate_alignment", "timestamp_convention"], result.canonicalBars),
    valueAt(["latest_current_alignment", "canonical_interval_start", "utc"], result.canonicalBars),
    valueAt(["latest_current_alignment", "canonical_interval_end", "utc"], result.canonicalBars),
    valueAt(["latest_common_current_raw_timestamp"], result.canonicalBars),
    valueAt(["latest_common_candidate_raw_timestamp"], result.canonicalBars),
    valueAt(["latest_input_current_raw_timestamp"], result.canonicalBars),
    valueAt(["latest_input_candidate_raw_timestamp"], result.canonicalBars),
    valueAt(["latest_alignment_key_match"], result.canonicalBars),
    valueAt(["freshness", "current", "latest_bar_timestamp", "utc"], result),
    valueAt(["freshness", "current", "latest_bar_timestamp", "new_york"], result),
    valueAt(["freshness", "current", "latest_bar_timestamp", "market_session_state"], result),
    valueAt(["freshness", "current", "provider_lag_minutes_vs_server_run_time"], result),
    valueAt(["freshness", "current", "provider_lag_minutes_vs_expected_latest_market_bar"], result),
    valueAt(["freshness", "current", "classification"], result),
    valueAt(["freshness", "candidate", "latest_bar_timestamp", "utc"], result),
    valueAt(["freshness", "candidate", "latest_bar_timestamp", "new_york"], result),
    valueAt(["freshness", "candidate", "latest_bar_timestamp", "market_session_state"], result),
    valueAt(["freshness", "candidate", "provider_lag_minutes_vs_server_run_time"], result),
    valueAt(["freshness", "candidate", "provider_lag_minutes_vs_expected_latest_market_bar"], result),
    valueAt(["freshness", "candidate", "classification"], result),
    valueAt(["freshness", "expected_latest_market_bar", "utc"], result),
    valueAt(["freshness", "expected_latest_market_bar", "new_york"], result),
    valueAt(["freshness", "market_session_state"], result),
    valueAt(["freshness", "timestamp_delta_minutes"], result),
    valueAt(["freshness", "latest_common_aligned_timestamp", "utc"], result),
    valueAt(["freshness", "latest_common_aligned_timestamp", "new_york"], result),
    valueAt(["freshness", "verdict_reason"], result),
    valueAt(["latest_current", "close"], result.rawBars),
    valueAt(["latest_candidate", "close"], result.rawBars),
    valueAt(["latest_current", "close"], result.canonicalBars),
    valueAt(["latest_candidate", "close"], result.canonicalBars),
    valueAt(["comparison_diagnostics", "notes"], result.canonicalBars),
    result.warnings.join("; "),
    result.errors.join("; "),
  ]);
  return [
    [
      "symbol",
      "timeframe",
      "raw_bars",
      "canonical_bars",
      "indicators",
      "tos_reference",
      "root_cause",
      "canonical_alignment_mode",
      "canonical_comparison_scope",
      "canonical_latest_alignment_label",
      "canonical_current_timestamp_convention",
      "canonical_schwab_timestamp_convention",
      "canonical_interval_start_utc",
      "canonical_interval_end_utc",
      "canonical_current_common_raw_timestamp",
      "canonical_schwab_common_raw_timestamp",
      "canonical_current_latest_returned_raw_timestamp",
      "canonical_schwab_latest_returned_raw_timestamp",
      "canonical_latest_alignment_key_match",
      "current_provider_as_of_utc",
      "current_provider_as_of_new_york",
      "current_provider_as_of_session",
      "current_provider_lag_minutes_vs_server_run_time",
      "current_provider_lag_minutes_vs_expected_market_bar",
      "current_provider_freshness_classification",
      "schwab_as_of_utc",
      "schwab_as_of_new_york",
      "schwab_as_of_session",
      "schwab_lag_minutes_vs_server_run_time",
      "schwab_lag_minutes_vs_expected_market_bar",
      "schwab_freshness_classification",
      "expected_latest_market_bar_utc",
      "expected_latest_market_bar_new_york",
      "market_session_state",
      "timestamp_delta_minutes",
      "latest_common_aligned_timestamp_utc",
      "latest_common_aligned_timestamp_new_york",
      "verdict_reason",
      "raw_current_close",
      "raw_schwab_close",
      "canonical_current_close",
      "canonical_schwab_close",
      "canonical_diagnostic_notes",
      "warnings",
      "errors",
    ].map(csvCell).join(","),
    ...rows.map((row) => row.map(csvCell).join(",")),
  ].join("\n");
}

export async function fetchSchwabStatus(): Promise<SchwabStatus> {
  const response = await fetchWorkflowApi<SchwabStatus>("/api/admin/schwab/status");
  if (!response.ok || !response.data) {
    throw new Error(response.error ?? "Unable to load Schwab status.");
  }
  return response.data;
}

export async function runDataParity(request: DataParityRunRequest): Promise<DataParityRunResponse> {
  const response = await fetchWorkflowApi<DataParityRunResponse>("/api/admin/data-parity/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok || !response.data) {
    throw new Error(response.error ?? "Unable to run data parity comparison.");
  }
  return response.data;
}

export async function fetchDataParitySnapshots(): Promise<DataParitySnapshotSummary[]> {
  const response = await fetchWorkflowApi<{ snapshots: DataParitySnapshotSummary[] }>("/api/admin/data-parity/snapshots");
  if (!response.ok || !response.data) {
    throw new Error(response.error ?? "Unable to load parity snapshots.");
  }
  return response.data.snapshots ?? [];
}

export async function fetchDataParitySnapshot(runId: string): Promise<DataParityRunResponse> {
  const response = await fetchWorkflowApi<{ response: DataParityRunResponse }>(
    `/api/admin/data-parity/snapshots/${encodeURIComponent(runId)}`,
  );
  if (!response.ok || !response.data?.response) {
    throw new Error(response.error ?? "Unable to load parity snapshot.");
  }
  return response.data.response;
}
