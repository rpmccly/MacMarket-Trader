import type { ChartTime } from "@/lib/haco-api";
import {
  validateChartHistoryRange,
  type ChartHistoryRangeId,
} from "@/lib/chart-history-range";

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
  /** Operator-selected chart history range (1M / 3M / 6M / 1Y / 2Y / 5Y).
   *  Defaults to 1Y on the backend when omitted. */
  history_range?: ChartHistoryRangeId | string | null;
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
  | "bullish_pullback_context"
  | "bearish_rally_context"
  | "reversal_warning"
  | "neutral_to_bull"
  | "neutral_to_bear";

export type MomentumSignalMarker = {
  index: number;
  time: ChartTime;
  marker_type: MomentumSignalMarkerType;
  direction: "bullish" | "bearish" | "warning";
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

export type MomentumHiloThrustState = "bullish" | "bearish" | "neutral";

export type MomentumVisualParitySnapshot = {
  as_of: string | null;
  symbol: string | null;
  timeframe: string | null;
  history_range: string | null;
  total_score: number | null;
  total_label: string | null;
  trend_score: number | null;
  momo_score: number | null;
  true_momentum: number | null;
  true_momentum_ema: number | null;
  hilo_elite_value: number | null;
  hilo_thrust_state: MomentumHiloThrustState | null;
  hilo_score: number | null;
  pullback_signal: boolean | null;
  reversal_warning: boolean | null;
  no_trade_warning: boolean | null;
  iv_percent: number | null;
  source_notes: string[];
  unavailable_fields: string[];
};

export type MomentumVisualParityPoint = {
  index: number;
  time: ChartTime;
  total_score: number;
  total_label: string;
  total_state: string;
  trend_score: number;
  momo_score: number;
  true_momentum: number;
  true_momentum_ema: number;
  hilo_elite_value: number;
  hilo_thrust_state: MomentumHiloThrustState;
  hilo_score: number;
  pullback_signal: boolean;
  reversal_warning: boolean;
  no_trade_warning: boolean;
};

export type MomentumPanelMarkerType =
  | "bullish_cross"
  | "bearish_cross"
  | "hilo_confirmed"
  | "hilo_deconfirmed"
  | "state_transition"
  | "hilo_state_transition";

export type MomentumPanelMarker = {
  index: number;
  time: ChartTime;
  panel: "true_momentum" | "hilo";
  marker_type: MomentumPanelMarkerType;
  direction: "up" | "down" | "neutral";
  label: string;
  value: number;
  reason: string;
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
  /** Echoed by the chart route — the resolved history range and the
   *  trailing bar count the operator can now pan into. */
  history_range?: string | null;
  lookback_days?: number | null;
  bars_returned?: number | null;
  /** Visual parity chart polish — normalized parity snapshot, per-bar
   *  parity points for hover lookup, and panel-specific markers. */
  visual_parity_snapshot?: MomentumVisualParitySnapshot | null;
  visual_parity_series?: MomentumVisualParityPoint[];
  true_momentum_panel_markers?: MomentumPanelMarker[];
  hilo_panel_markers?: MomentumPanelMarker[];
};

export async function fetchMomentumChart(request: MomentumChartRequest): Promise<MomentumChartPayload> {
  const { history_range, ...rest } = request;
  const body = {
    ...rest,
    history_range: validateChartHistoryRange(history_range ?? undefined),
  };
  const response = await fetch("/api/charts/momentum", {
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
    throw new Error(`Failed to load Momentum chart: ${response.status}`);
  }
  return (await response.json()) as MomentumChartPayload;
}
