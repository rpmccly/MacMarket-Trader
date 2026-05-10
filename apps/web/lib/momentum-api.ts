import type { ChartTime } from "@/lib/haco-api";

export type { ChartTime } from "@/lib/haco-api";

export type MomentumBarInput = {
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
};

export type MomentumChartRequest = {
  symbol: string;
  timeframe: string;
  bars?: MomentumBarInput[];
  higher_timeframe_bars?: MomentumBarInput[];
  include_markers?: boolean;
};

export type MomentumLinePoint = {
  index: number;
  time: ChartTime;
  value: number;
};

export type MomentumStripPoint = {
  index: number;
  time: ChartTime;
  value: number;
  state: string;
};

export type MomentumScoreStripPoint = {
  index: number;
  time: ChartTime;
  total_score: number;
  state: string;
};

export type MomentumSignalMarkerType =
  | "bullish_pullback_buy"
  | "bearish_rally_sell"
  | "reversal_warning"
  | "neutral_to_bull"
  | "neutral_to_bear";

export type MomentumSignalMarker = {
  index: number;
  time: ChartTime;
  marker_type: MomentumSignalMarkerType;
  direction: "buy" | "sell" | "warning";
  price: number;
  text: string;
};

export type MomentumComponentBreakdownPayload = {
  true_momentum_score: number;
  hilo_thrust: number;
  bull_ma: number;
  bear_ma: number;
  atr_value: number;
  macd_bias: number;
  intraday_penalty: number;
  base_score: number;
};

export type MomentumScoreSnapshot = {
  total_score: number;
  total_label: string;
  total_state: string;
  trend_score: number;
  momo_score: number;
  true_momentum: number;
  true_momentum_ema: number;
  true_momentum_score: number;
  hilo_thrust: number;
  hilo_score: number;
  atr_bias: number;
  macd_bias: number;
  ma_bias: number;
  component_breakdown: MomentumComponentBreakdownPayload;
};

export type MomentumChartExplanation = {
  snapshot: MomentumScoreSnapshot;
  reversal_warning: boolean;
  pullback_signal: boolean;
  no_trade_warning: boolean;
  notes: string[];
};

export type MomentumChartCandle = {
  index: number;
  time: ChartTime;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type MomentumChartPayload = {
  symbol: string;
  timeframe: string;
  candles: MomentumChartCandle[];
  true_momentum_line: MomentumLinePoint[];
  true_momentum_ema_line: MomentumLinePoint[];
  hilo_slowd_line: MomentumLinePoint[];
  hilo_slowd_x_line: MomentumLinePoint[];
  hilo_thrust_strip: MomentumStripPoint[];
  score_strip: MomentumScoreStripPoint[];
  markers: MomentumSignalMarker[];
  latest_snapshot: MomentumScoreSnapshot | null;
  explanation: MomentumChartExplanation | null;
  data_source: string;
  fallback_mode: boolean;
  session_policy?: string | null;
  source_session_policy?: string | null;
  source_timeframe?: string | null;
  output_timeframe?: string | null;
  first_bar_timestamp?: string | null;
  last_bar_timestamp?: string | null;
  higher_timeframe_source: string;
  higher_timeframe?: string | null;
  parity_status: string;
  calculation_notes: string[];
};

export async function fetchMomentumChart(request: MomentumChartRequest): Promise<MomentumChartPayload> {
  const response = await fetch("/api/charts/momentum", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
    credentials: "include",
  });
  if (!response.ok) {
    if (response.status === 425) {
      throw new Error("AUTH_NOT_READY");
    }
    throw new Error(`Failed to load Momentum chart: ${response.status}`);
  }
  return (await response.json()) as MomentumChartPayload;
}
