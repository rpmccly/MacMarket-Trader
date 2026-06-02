import { fetchWorkflowApi } from "@/lib/api-client";

export type AgentModeSettings = {
  enabled: boolean;
  paused: boolean;
  kill_switch_enabled: boolean;
  daily_run_time: string;
  timezone: string;
  universe_source: string;
  manual_symbols: string[];
  watchlist_ids: number[];
  default_watchlist_id?: number | null;
  max_positions: number;
  scan_depth: number;
  max_dollars_per_trade?: number | null;
  max_percent_of_paper_account_per_trade?: number | null;
  max_new_trades_per_run?: number;
  max_new_trades_per_day?: number;
  max_open_agent_positions?: number;
  max_exposure_per_symbol?: number | null;
  min_cash_reserve?: number | null;
  allow_opens: boolean;
  allow_closes: boolean;
  allow_scale_resize: boolean;
  allow_scale_ins?: boolean;
  allow_new_trade_when_symbol_already_open?: boolean;
  require_confirmation_for_restricted?: boolean;
  notification_preference?: "none" | "email" | "sms" | "both" | string;
  notification_phone_number?: string | null;
  sms_consent_confirmed?: boolean;
  email_notifications_enabled?: boolean;
  sms_notifications_enabled?: boolean;
  sms_provider_status?: {
    provider?: string;
    enabled?: boolean;
    configured?: boolean;
    account_sid_present?: boolean;
    auth_token_present?: boolean;
    messaging_service_sid_present?: boolean;
    from_number_present?: boolean;
    status?: string;
  };
  paper_only?: boolean;
  execution_mode?: string;
};

export type AgentModeStatus = {
  agent_enabled: boolean;
  configured_timezone?: string | null;
  configured_daily_run_time?: string | null;
  current_server_time?: string | null;
  current_server_timezone?: string | null;
  next_scheduled_run_at?: string | null;
  seconds_until_next_run?: number | null;
  last_run_started_at?: string | null;
  last_run_completed_at?: string | null;
  last_run_status: "success" | "failed" | "skipped" | "running" | "never_run" | "disabled" | string;
  last_skip_reason?: string | null;
  last_error_summary?: string | null;
  last_run_id?: string | null;
  last_run_trade_count?: number;
  last_run_position_review_count?: number;
  last_run_blocked_count?: number;
  in_progress?: boolean;
  lock_diagnostics?: Record<string, unknown>;
  scheduler_source?: string;
  paperOnly?: boolean;
  executionMode?: string;
};

export type AgentModeIntent = {
  intent: string;
  symbol?: string | null;
  side?: string | null;
  status: string;
  reason?: string | null;
  summary?: string | null;
  order_id?: string | null;
  trade_id?: number | null;
  position_id?: number | null;
  recommendation_id?: string | null;
  paper_only?: boolean;
  no_live_routing?: boolean;
  warnings?: string[];
  missing_data?: string[];
  candidate?: Record<string, unknown> | null;
  review?: Record<string, unknown> | null;
};

export type AgentModeRunResult = {
  runId: string;
  asOf: string;
  status: string;
  settings: AgentModeSettings;
  universe: {
    symbols: string[];
    source: string;
    source_label?: string;
    scan_depth: number;
    watchlist_id?: number | null;
    watchlist_name?: string | null;
    watchlist_ids?: number[];
    watchlist_names?: string[];
    resolved_symbols_snapshot?: string[];
    manual_override?: boolean;
    source_status?: string;
    reason?: string | null;
  };
  summary: {
    paperOnly: boolean;
    executionMode: string;
    dryRun: boolean;
    enabled: boolean;
    paused: boolean;
    killSwitchEnabled: boolean;
    maxPositions: number;
    openPositionsBefore: number;
    openPositionsAfter?: number;
    positionsBeforeCount?: number;
    positionsAfterCount?: number;
    targetPositionsMax: number;
    intentCounts: Record<string, number>;
    executedOrderCount: number;
    paperOpensExecuted?: number;
    paperClosesExecuted?: number;
    holds?: number;
    blockedActions?: number;
    cashNoTrade?: number;
    totalExecutedActions?: number;
    skipReason?: string | null;
    maxOpenAgentPositions?: number;
    maxNewTradesPerRun?: number;
    maxNewTradesPerDay?: number;
    paperOpensTodayBeforeRun?: number;
    realizedPnlFromClosedPositions?: number | null;
    unrealizedPnlAfter?: number | null;
    totalAgentPaperPnl?: number | null;
    linkedPaperOrderIds?: string[];
    linkedPositionIds?: number[];
    linkedTradeIds?: number[];
  };
  paperBookBefore?: Array<Record<string, unknown>>;
  currentPaperBook: Array<Record<string, unknown>>;
  positionReviews: Array<Record<string, unknown>>;
  intents: AgentModeIntent[];
  candidateQueue: Array<Record<string, unknown>>;
  decisionMemo: string[];
  dataQuality: Array<Record<string, unknown>>;
  warnings: string[];
  notificationAttempts?: Array<Record<string, unknown>>;
};

export type AgentModeLatestResponse = {
  settings: AgentModeSettings;
  latestRun: {
    runId: string;
    status: string;
    executionMode: string;
    dryRun: boolean;
    result: AgentModeRunResult;
    createdAt?: string | null;
    completedAt?: string | null;
  } | null;
  empty: boolean;
  paperOnly: boolean;
  executionMode: string;
};

export type AgentModeRunHistoryItem = {
  runId: string;
  generatedAt: string;
  mode: "dry_run" | "enabled" | string;
  status: string;
  executionMode: string;
  dryRun: boolean;
  universe?: Record<string, unknown>;
  symbols?: string[];
  positionsBeforeCount?: number;
  positionsAfterCount?: number;
  paperOpensExecuted?: number;
  paperClosesExecuted?: number;
  holds?: number;
  blockedActions?: number;
  blocked?: number;
  cashNoTrade?: number;
  totalExecutedActions?: number;
  realizedPnlFromClosedPositions?: number | null;
  unrealizedPnlAfter?: number | null;
  totalAgentPaperPnl?: number | null;
  warnings?: string[];
  missingData?: unknown[];
  linkedPaperOrderIds?: string[];
  linkedPositionIds?: number[];
  linkedTradeIds?: number[];
};

export type AgentModeRunsResponse = {
  items: AgentModeRunHistoryItem[];
  limit: number;
  timeframe?: string;
  paperOnly: boolean;
  executionMode: string;
};

export type AgentModeTrade = {
  id: number;
  symbol: string;
  side: string;
  qty: number;
  entry_price: number;
  exit_price?: number | null;
  realized_pnl?: number | null;
  return_pct?: number | null;
  holding_days?: number | null;
  entry_reason?: string | null;
  exit_reason?: string | null;
  linked_run_id?: string | null;
  opened_at?: string | null;
  closed_at?: string | null;
  position_id?: number | null;
  order_id?: string | null;
  created_at?: string | null;
  submitted_at?: string | null;
  filled_at?: string | null;
  executed_at?: string | null;
  status?: string | null;
  source?: string | null;
};

export type AgentModeTradesResponse = {
  items: AgentModeTrade[];
  limit: number;
  timeframe?: string;
  source?: string;
  paperOnly: boolean;
  executionMode: string;
};

export type AgentModePerformance = {
  paperOnly: boolean;
  executionMode: string;
  asOf: string;
  settings: AgentModeSettings;
  timeframe?: string;
  source?: string;
  latestRun?: AgentModeRunHistoryItem | null;
  openPositions: Array<Record<string, unknown>>;
  tradeCount: number;
  openPositionCount: number;
  realizedPnl?: number | null;
  unrealizedPnl?: number | null;
  totalPaperPnl?: number | null;
  cumulativeRealizedPnl?: number | null;
  winCount: number;
  lossCount: number;
  winRate?: number | null;
  avgWin?: number | null;
  avgLoss?: number | null;
  profitFactor?: number | null;
  maxDrawdown?: number | null;
  runsTracked: number;
  runMetrics?: Record<string, number | null>;
  tradeMetrics?: Record<string, number | null>;
  positionMetrics?: Record<string, number | null>;
  riskBlockMetrics?: Record<string, number | null>;
};

export type AgentModeNotificationTestResponse = {
  paperOnly: boolean;
  executionMode: string;
  preference: string;
  smsProvider?: AgentModeSettings["sms_provider_status"];
  attempts: Array<Record<string, unknown>>;
};

export async function fetchAgentModeSettings() {
  return fetchWorkflowApi<AgentModeSettings>("/api/user/agent-mode/settings");
}

export async function fetchAgentModeStatus() {
  return fetchWorkflowApi<AgentModeStatus>("/api/user/agent-mode/status");
}

export async function saveAgentModeSettings(settings: Partial<AgentModeSettings>) {
  return fetchWorkflowApi<AgentModeSettings>("/api/user/agent-mode/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...settings, mode: "paper" }),
  });
}

export async function runAgentMode(payload: Record<string, unknown>) {
  return fetchWorkflowApi<AgentModeRunResult>("/api/user/agent-mode/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, mode: "paper" }),
  });
}

export async function fetchLatestAgentModeRun() {
  return fetchWorkflowApi<AgentModeLatestResponse>("/api/user/agent-mode/latest");
}

export async function fetchAgentModeRuns(params?: { limit?: number; status?: string; dryRun?: boolean; timeframe?: string }) {
  const search = new URLSearchParams();
  if (params?.limit) search.set("limit", String(params.limit));
  if (params?.status) search.set("status", params.status);
  if (params?.dryRun !== undefined) search.set("dry_run", String(params.dryRun));
  if (params?.timeframe) search.set("timeframe", params.timeframe);
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchWorkflowApi<AgentModeRunsResponse>(`/api/user/agent-mode/runs${suffix}`);
}

export async function fetchAgentModeTrades(params: { limit?: number; timeframe?: string; symbol?: string; status?: string; source?: string; runId?: string } = {}) {
  const search = new URLSearchParams();
  search.set("limit", String(params.limit ?? 100));
  if (params.timeframe) search.set("timeframe", params.timeframe);
  if (params.symbol) search.set("symbol", params.symbol);
  if (params.status) search.set("status", params.status);
  if (params.source) search.set("source", params.source);
  if (params.runId) search.set("run_id", params.runId);
  return fetchWorkflowApi<AgentModeTradesResponse>(`/api/user/agent-mode/trades?${search.toString()}`);
}

export async function fetchAgentModePerformance(params: { timeframe?: string; source?: string } = {}) {
  const search = new URLSearchParams();
  if (params.timeframe) search.set("timeframe", params.timeframe);
  if (params.source) search.set("source", params.source);
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchWorkflowApi<AgentModePerformance>(`/api/user/agent-mode/performance${suffix}`);
}

export async function testAgentModeNotification(channel: "email" | "sms" | "both" | "none") {
  return fetchWorkflowApi<AgentModeNotificationTestResponse>("/api/user/agent-mode/notifications/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel }),
  });
}
