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
  max_positions: number;
  scan_depth: number;
  allow_opens: boolean;
  allow_closes: boolean;
  allow_scale_resize: boolean;
  paper_only?: boolean;
  execution_mode?: string;
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
};

export type AgentModeTradesResponse = {
  items: AgentModeTrade[];
  limit: number;
  paperOnly: boolean;
  executionMode: string;
};

export type AgentModePerformance = {
  paperOnly: boolean;
  executionMode: string;
  asOf: string;
  settings: AgentModeSettings;
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
};

export async function fetchAgentModeSettings() {
  return fetchWorkflowApi<AgentModeSettings>("/api/user/agent-mode/settings");
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

export async function fetchAgentModeRuns(params?: { limit?: number; status?: string; dryRun?: boolean }) {
  const search = new URLSearchParams();
  if (params?.limit) search.set("limit", String(params.limit));
  if (params?.status) search.set("status", params.status);
  if (params?.dryRun !== undefined) search.set("dry_run", String(params.dryRun));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchWorkflowApi<AgentModeRunsResponse>(`/api/user/agent-mode/runs${suffix}`);
}

export async function fetchAgentModeTrades(limit = 100) {
  return fetchWorkflowApi<AgentModeTradesResponse>(`/api/user/agent-mode/trades?limit=${encodeURIComponent(String(limit))}`);
}

export async function fetchAgentModePerformance() {
  return fetchWorkflowApi<AgentModePerformance>("/api/user/agent-mode/performance");
}
