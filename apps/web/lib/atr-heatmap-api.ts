export type AtrHeatmapRequest = {
  symbols: string[];
  timeframes?: string[];
  decision_timeframe?: string;
  trail_type?: string;
  atr_period?: number;
  atr_factor?: number;
  first_trade?: string;
  average_type?: string;
};

export type AtrHeatmapCell = {
  timeframe: string;
  status: "ok" | "unavailable" | string;
  state?: string | null;
  trailing_stop?: number | null;
  stop_distance_pct?: number | null;
  bars_since_flip?: number | null;
  last_flip_direction?: string | null;
  last_flip_time?: string | null;
  reason?: string | null;
};

export type AtrHeatmapRow = {
  symbol: string;
  states: Record<string, AtrHeatmapCell>;
  alignment_score: number;
  alignment_label: string;
  long_count: number;
  short_count: number;
  available_count: number;
  decision_timeframe?: string | null;
  latest_trailing_stop?: number | null;
  distance_to_stop_pct?: number | null;
  bars_since_flip?: number | null;
  last_flip_direction?: string | null;
  last_flip_time?: string | null;
  status: string;
  reason?: string | null;
};

export type AtrHeatmapResponse = {
  rows: AtrHeatmapRow[];
  summary: { total: number; long_count: number; short_count: number; mixed_count: number; unavailable_count: number };
  timeframes: string[];
  config: { trail_type: string; atr_period: number; atr_factor: number; first_trade: string; average_type: string };
  generated_at: string;
  notes: string[];
};

async function postAtrHeatmap<T>(path: string, request: AtrHeatmapRequest): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    if (response.status === 425) throw new Error("AUTH_NOT_READY");
    throw new Error(`Failed to load ATR Direction Heatmap: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchAtrHeatmap(request: AtrHeatmapRequest): Promise<AtrHeatmapResponse> {
  return postAtrHeatmap<AtrHeatmapResponse>("/api/charts/atr-heatmap", request);
}

export async function downloadAtrHeatmapCsv(request: AtrHeatmapRequest): Promise<{ csv: string; filename: string }> {
  return postAtrHeatmap<{ csv: string; filename: string }>("/api/charts/atr-heatmap/report/csv", request);
}
