import { fetchWorkflowApi } from "@/lib/api-client";

export type AgentType = "standard" | "haco_direction" | "true_momentum" | "hybrid" | "atr_trailing_stop";
export type HacoDirectionMode = "long_only" | "short_only" | "long_and_short";
export type TrueMomentumTriggerMode = "conservative" | "balanced" | "aggressive" | "review_only";
export type AtrTrailType = "modified" | "unmodified";
export type AtrAverageType = "wilders" | "simple";

export type AgentModeSettings = {
  // Phase 11 — Agent Profile identity + agent-type configuration.
  profile_uid?: string | null;
  agent_profile_id?: number | null;
  name?: string | null;
  agent_type?: AgentType | string;
  is_default?: boolean;
  strategy_families?: string[];
  haco_direction_mode?: HacoDirectionMode | string;
  true_momentum_trigger_mode?: TrueMomentumTriggerMode | string;
  use_haco_filter?: boolean;
  use_true_momentum_confirmation?: boolean;
  // Phase 12 — ATR config + bidirectional (directional) execution controls.
  // Exposed here so the execution settings round-trip and are testable; the
  // cockpit controls for these land with the directional/ATR UI increment.
  atr_trail_type?: AtrTrailType | string;
  atr_period?: number;
  atr_factor?: number;
  atr_first_trade?: string;
  atr_average_type?: AtrAverageType | string;
  atr_decision_timeframe?: string;
  atr_alignment_mode?: string;
  allow_shorts?: boolean;
  allow_direction_flip?: boolean;
  close_opposite_before_open?: boolean;
  close_on_opposite_signal?: boolean;
  hedge_allowed?: boolean;
  use_atr_filter?: boolean;
  prevent_opposing_agent_positions_across_profiles?: boolean;
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
  scheduler_health?: "ok" | "stale" | "degraded" | "unknown" | string;
  scheduler_last_checked_at?: string | null;
  scheduler_last_check_result?: string | null;
  scheduler_last_check_reason?: string | null;
  scheduler_last_due_at?: string | null;
  scheduler_last_run_id?: string | null;
  scheduler_last_window_key?: string | null;
  scheduler_check_age_seconds?: number | null;
  scheduler_expected_interval_seconds?: number | null;
  scheduler_stale_after_seconds?: number | null;
  scheduler_due_now?: boolean;
  scheduler_current_window_key?: string | null;
  scheduler_current_due_at?: string | null;
  scheduler_current_due_at_local?: string | null;
  scheduler_already_ran_current_window?: boolean;
  selected_watchlist_id?: number | null;
  selected_watchlist_name?: string | null;
  resolved_symbol_count?: number;
  resolved_symbols_preview?: string[];
  universe_source?: string | null;
  universe_source_status?: string | null;
  universe_skip_reason?: string | null;
  last_scheduled_run_id?: string | null;
  last_scheduled_run_started_at?: string | null;
  last_scheduled_run_completed_at?: string | null;
  last_scheduled_run_status?: string | null;
  last_scheduled_skip_reason?: string | null;
  last_scheduled_trade_count?: number;
  in_progress?: boolean;
  lock_diagnostics?: Record<string, unknown>;
  scheduler_source?: string;
  paperOnly?: boolean;
  executionMode?: string;
};

export type PositionOwnerKind = "own" | "foreign_agent" | "manual";

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
  // Ownership boundary: who owns the position this intent refers to.
  position_owner?: PositionOwnerKind | null;
  action_reason?: string | null;
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
    triggerReviewOnly?: number;
    reviewedExternalPositions?: number;
    marketClosed?: boolean;
    marketSession?: {
      market_timezone?: string;
      session_date?: string;
      is_open_trading_day?: boolean;
      closed_reason?: string | null;
      next_trading_day?: string;
    } | null;
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

export type AgentProfileOverview = {
  profile_uid: string;
  agent_profile_id: number;
  name: string;
  agent_type: AgentType | string;
  is_default: boolean;
  enabled: boolean;
  enabled_setting?: boolean;
  paused?: boolean;
  kill_switch_enabled?: boolean;
  daily_run_time?: string | null;
  timezone?: string | null;
  next_scheduled_run_at?: string | null;
  last_run_status?: string | null;
  last_run_at?: string | null;
  universe_source?: string | null;
  watchlist_name?: string | null;
  resolved_symbol_count?: number;
  strategy_count?: number | null;
  haco_direction_mode?: string | null;
  true_momentum_trigger_mode?: string | null;
  open_position_count?: number;
  realized_pnl?: number | null;
  trade_count?: number;
  // Phase 12 — directional capability + current state for the cockpit card.
  directional?: boolean;
  allow_shorts?: boolean;
  allow_direction_flip?: boolean;
  current_position_side?: string | null;
  last_action?: string | null;
};

export type AgentProfilesResponse = {
  profiles: AgentProfileOverview[];
  paperOnly: boolean;
  executionMode: string;
};

function withProfile(path: string, profileId?: number | null): string {
  if (profileId === undefined || profileId === null) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}profile_id=${encodeURIComponent(String(profileId))}`;
}

export async function fetchAgentProfiles() {
  return fetchWorkflowApi<AgentProfilesResponse>("/api/user/agent-mode/profiles");
}

export async function createAgentProfile(payload: Partial<AgentModeSettings> & { agent_type: AgentType }) {
  return fetchWorkflowApi<AgentModeSettings>("/api/user/agent-mode/profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, mode: "paper" }),
  });
}

export async function updateAgentProfile(profileUid: string, settings: Partial<AgentModeSettings>) {
  return fetchWorkflowApi<AgentModeSettings>(`/api/user/agent-mode/profiles/${encodeURIComponent(profileUid)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...settings, mode: "paper" }),
  });
}

export async function deleteAgentProfile(profileUid: string) {
  return fetchWorkflowApi<{ status: string }>(`/api/user/agent-mode/profiles/${encodeURIComponent(profileUid)}`, {
    method: "DELETE",
  });
}

export async function setDefaultAgentProfile(profileUid: string) {
  return fetchWorkflowApi<AgentModeSettings>(`/api/user/agent-mode/profiles/${encodeURIComponent(profileUid)}/default`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

export async function fetchAgentModeSettings(profileId?: number | null) {
  return fetchWorkflowApi<AgentModeSettings>(withProfile("/api/user/agent-mode/settings", profileId));
}

export async function fetchAgentModeStatus(profileId?: number | null) {
  return fetchWorkflowApi<AgentModeStatus>(withProfile("/api/user/agent-mode/status", profileId));
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

export async function fetchLatestAgentModeRun(profileId?: number | null) {
  return fetchWorkflowApi<AgentModeLatestResponse>(withProfile("/api/user/agent-mode/latest", profileId));
}

export async function fetchAgentModeRuns(params?: { limit?: number; status?: string; dryRun?: boolean; timeframe?: string; profileId?: number | null }) {
  const search = new URLSearchParams();
  if (params?.limit) search.set("limit", String(params.limit));
  if (params?.status) search.set("status", params.status);
  if (params?.dryRun !== undefined) search.set("dry_run", String(params.dryRun));
  if (params?.timeframe) search.set("timeframe", params.timeframe);
  if (params?.profileId != null) search.set("profile_id", String(params.profileId));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchWorkflowApi<AgentModeRunsResponse>(`/api/user/agent-mode/runs${suffix}`);
}

export async function fetchAgentModeTrades(params: { limit?: number; timeframe?: string; symbol?: string; status?: string; source?: string; runId?: string; profileId?: number | null } = {}) {
  const search = new URLSearchParams();
  search.set("limit", String(params.limit ?? 100));
  if (params.timeframe) search.set("timeframe", params.timeframe);
  if (params.symbol) search.set("symbol", params.symbol);
  if (params.status) search.set("status", params.status);
  if (params.source) search.set("source", params.source);
  if (params.runId) search.set("run_id", params.runId);
  if (params.profileId != null) search.set("profile_id", String(params.profileId));
  return fetchWorkflowApi<AgentModeTradesResponse>(`/api/user/agent-mode/trades?${search.toString()}`);
}

export async function fetchAgentModePerformance(params: { timeframe?: string; source?: string; profileId?: number | null } = {}) {
  const search = new URLSearchParams();
  if (params.timeframe) search.set("timeframe", params.timeframe);
  if (params.source) search.set("source", params.source);
  if (params.profileId != null) search.set("profile_id", String(params.profileId));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchWorkflowApi<AgentModePerformance>(`/api/user/agent-mode/performance${suffix}`);
}

export async function testAgentModeNotification(channel: "email" | "sms" | "both" | "none", profileId?: number | null) {
  return fetchWorkflowApi<AgentModeNotificationTestResponse>("/api/user/agent-mode/notifications/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel, ...(profileId != null ? { profile_id: profileId } : {}) }),
  });
}
