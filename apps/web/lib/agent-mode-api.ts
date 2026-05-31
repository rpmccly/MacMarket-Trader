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
    targetPositionsMax: number;
    intentCounts: Record<string, number>;
    executedOrderCount: number;
  };
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
