import {
  validateChartHistoryRange,
  type ChartHistoryRangeId,
} from "@/lib/chart-history-range";

export type ChartTime = string | number;
export type AtrState = "long" | "short" | "neutral" | string;

export type AtrTrailType = "modified" | "unmodified";
export type AtrAverageType = "wilders" | "simple" | "exponential";

export type AtrChartRequest = {
  symbol: string;
  timeframe: string;
  include_markers?: boolean;
  history_range?: ChartHistoryRangeId | string | null;
  // Advanced ATR settings (math frozen; these only select inputs).
  trail_type?: AtrTrailType | string;
  atr_period?: number;
  atr_factor?: number;
  first_trade?: string;
  average_type?: AtrAverageType | string;
  multi_timeframes?: string[];
};

export type AtrTrailingStopChartPoint = {
  index: number;
  time: ChartTime;
  close: number;
  state: string;
  trailing_stop: number;
  stop_distance: number;
  stop_distance_pct?: number | null;
  buy_signal?: boolean;
  sell_signal?: boolean;
};

export type AtrTimeframeState = {
  timeframe: string;
  status: "ok" | "unavailable" | string;
  state?: string | null;
  trailing_stop?: number | null;
  stop_distance_pct?: number | null;
  bars_since_flip?: number | null;
  last_flip_direction?: string | null;
  last_flip_time?: string | null;
  data_source?: string | null;
  fallback_mode?: boolean | null;
  reason?: string | null;
};

export type AtrChartPayload = {
  symbol: string;
  timeframe: string;
  candles: Array<{ index: number; time: ChartTime; open: number; high: number; low: number; close: number; volume: number }>;
  trailing_stop: AtrTrailingStopChartPoint[];
  markers: Array<{ index: number; time: ChartTime; marker_type: string; direction: string; price: number; text: string }>;
  explanation: {
    current_state: AtrState;
    latest_trailing_stop?: number | null;
    distance_to_stop_pct?: number | null;
    bars_since_flip?: number | null;
    last_flip_direction?: string | null;
    last_flip_time?: string | null;
  };
  timeframe_states: AtrTimeframeState[];
  config: {
    trail_type: string;
    atr_period: number;
    atr_factor: number;
    first_trade: string;
    average_type: string;
  };
  data_source: string;
  fallback_mode: boolean;
  session_policy?: string | null;
  source_session_policy?: string | null;
  source_timeframe?: string | null;
  output_timeframe?: string | null;
  first_bar_timestamp?: string | null;
  last_bar_timestamp?: string | null;
  history_range?: string | null;
  lookback_days?: number | null;
  bars_returned?: number | null;
  notes: string[];
};

export async function fetchAtrChart(request: AtrChartRequest): Promise<AtrChartPayload> {
  const { history_range, ...rest } = request;
  const body = {
    ...rest,
    history_range: validateChartHistoryRange(history_range ?? undefined),
  };
  const response = await fetch("/api/charts/atr", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    if (response.status === 425) {
      throw new Error("AUTH_NOT_READY");
    }
    throw new Error(`Failed to load ATR Intel: ${response.status}`);
  }
  return (await response.json()) as AtrChartPayload;
}
