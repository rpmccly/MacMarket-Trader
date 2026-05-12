import {
  validateChartHistoryRange,
  type ChartHistoryRangeId,
} from "@/lib/chart-history-range";

export type ChartTime = string | number;

export type HacoChartRequest = {
  symbol: string;
  timeframe: string;
  include_heikin_ashi: boolean;
  bars?: Array<{
    date: string;
    timestamp?: string | null;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    rel_volume?: number;
    session_policy?: string | null;
    source_session_policy?: string | null;
    source_timeframe?: string | null;
    provider?: string | null;
  }>;
  /** Operator-selected chart history range (1M / 3M / 6M / 1Y / 2Y / 5Y).
   *  Defaults to 1Y on the backend when omitted. */
  history_range?: ChartHistoryRangeId | string | null;
};

export type HacoChartPayload = {
  symbol: string;
  timeframe: string;
  candles: Array<{ index: number; time: ChartTime; open: number; high: number; low: number; close: number; volume: number }>;
  heikin_ashi_candles: Array<{ index: number; time: ChartTime; open: number; high: number; low: number; close: number; volume: number }>;
  markers: Array<{ index: number; time: ChartTime; marker_type: string; direction: string; price: number; text: string }>;
  haco_strip: Array<{ index: number; time: ChartTime; value: number; state: string }>;
  hacolt_strip: Array<{ index: number; time: ChartTime; value: number; direction: string }>;
  explanation: {
    current_haco_state: string;
    latest_flip: string;
    latest_flip_bars_ago: number | null;
    current_hacolt_direction: string;
  };
  data_source: string;
  fallback_mode: boolean;
  session_policy?: string | null;
  source_session_policy?: string | null;
  source_timeframe?: string | null;
  output_timeframe?: string | null;
  filtered_extended_hours_count?: number | null;
  rth_bucket_count?: number | null;
  first_bar_timestamp?: string | null;
  last_bar_timestamp?: string | null;
  /** Echoed by the chart route — the resolved history range and the
   *  trailing bar count the operator can now pan into. */
  history_range?: string | null;
  lookback_days?: number | null;
  bars_returned?: number | null;
};

export async function fetchHacoChart(request: HacoChartRequest): Promise<HacoChartPayload> {
  const { history_range, ...rest } = request;
  const body = {
    ...rest,
    history_range: validateChartHistoryRange(history_range ?? undefined),
  };
  const response = await fetch("/api/charts/haco", {
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
    throw new Error(`Failed to load HACO chart: ${response.status}`);
  }
  return (await response.json()) as HacoChartPayload;
}
