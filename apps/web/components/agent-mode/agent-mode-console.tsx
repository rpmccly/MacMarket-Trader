"use client";

import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Card, EmptyState, ErrorState, InlineFeedback, PageHeader, ResponsiveTable, StatusBadge } from "@/components/operator-ui";
import {
  fetchAgentModeStatus,
  fetchAgentModePerformance,
  fetchAgentModeRuns,
  fetchAgentModeSettings,
  fetchAgentModeTrades,
  fetchLatestAgentModeRun,
  runAgentMode,
  saveAgentModeSettings,
  testAgentModeNotification,
  type AgentModePerformance,
  type AgentModeRunHistoryItem,
  type AgentModeRunResult,
  type AgentModeSettings,
  type AgentModeStatus,
  type AgentModeTrade,
} from "@/lib/agent-mode-api";
import { fetchWatchlists, type Watchlist } from "@/lib/watchlists-api";

const defaultSettings: AgentModeSettings = {
  enabled: false,
  paused: false,
  kill_switch_enabled: false,
  daily_run_time: "15:45",
  timezone: "America/New_York",
  universe_source: "manual",
  manual_symbols: ["SPY", "QQQ", "MTUM"],
  watchlist_ids: [],
  default_watchlist_id: null,
  max_positions: 5,
  scan_depth: 12,
  max_dollars_per_trade: null,
  max_percent_of_paper_account_per_trade: 10,
  max_new_trades_per_run: 5,
  max_new_trades_per_day: 5,
  max_open_agent_positions: 5,
  max_exposure_per_symbol: null,
  min_cash_reserve: 0,
  allow_opens: true,
  allow_closes: true,
  allow_scale_resize: false,
  allow_scale_ins: false,
  allow_new_trade_when_symbol_already_open: false,
  require_confirmation_for_restricted: true,
  notification_preference: "none",
  notification_phone_number: "",
  sms_consent_confirmed: false,
  email_notifications_enabled: false,
  sms_notifications_enabled: false,
  paper_only: true,
  execution_mode: "paper",
};

const tabs = ["Overview", "Runs", "Trades", "Positions", "Performance", "Settings"] as const;
type AgentModeTab = typeof tabs[number];

const timeframeOptions = [
  ["today", "Today"],
  ["yesterday", "Yesterday"],
  ["last_7_days", "Last 7 days"],
  ["last_30_days", "Last 30 days"],
  ["month_to_date", "Month to date"],
  ["previous_month", "Previous month"],
  ["all_time", "All time"],
] as const;

function toneForIntent(intent: string): "good" | "warn" | "bad" | "neutral" {
  if (intent === "OPEN_PAPER") return "good";
  if (intent === "CLOSE_PAPER" || intent === "REPLACE_PAPER") return "warn";
  if (intent === "CASH_NO_TRADE") return "neutral";
  return "neutral";
}

function asText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function asNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatIntentLabel(intent: string): string {
  return intent
    .replace("OPEN_PAPER", "paper open")
    .replace("CLOSE_PAPER", "paper close")
    .replace("REPLACE_PAPER", "replace paper position")
    .replace("SCALE_IN_PAPER", "scale-in paper review")
    .replace("REDUCE_PAPER", "reduce paper review")
    .replace("CASH_NO_TRADE", "cash/no trade")
    .replace("HOLD", "hold");
}

const currencyFormatter = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

function formatMoney(value: unknown): string {
  const parsed = asNumber(value);
  return parsed === null ? "-" : currencyFormatter.format(parsed);
}

function formatPrice(value: unknown): string {
  const parsed = asNumber(value);
  return parsed === null ? "-" : parsed.toFixed(2);
}

function formatQty(value: unknown): string {
  const parsed = asNumber(value);
  return parsed === null ? "-" : numberFormatter.format(parsed);
}

function formatPercent(value: unknown): string {
  const parsed = asNumber(value);
  return parsed === null ? "-" : `${parsed.toFixed(2)}%`;
}

function formatWinRate(value: unknown): string {
  const parsed = asNumber(value);
  if (parsed === null) return "-";
  return `${(parsed * 100).toFixed(1)}%`;
}

function formatDateTime(value: unknown): string {
  if (!value) return "-";
  const parsed = new Date(String(value));
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}

function toneForSigned(value: unknown): "good" | "bad" | "neutral" {
  const parsed = asNumber(value);
  if (parsed === null || parsed === 0) return "neutral";
  return parsed > 0 ? "good" : "bad";
}

function formatDuration(seconds: unknown): string {
  const parsed = asNumber(seconds);
  if (parsed === null) return "-";
  const clamped = Math.max(0, Math.floor(parsed));
  const hours = Math.floor(clamped / 3600);
  const minutes = Math.floor((clamped % 3600) / 60);
  const secs = clamped % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

function formatFieldLabel(value: unknown): string {
  return asText(value).replace(/_/g, " ");
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: string | number; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return (
    <div className={`agent-metric agent-metric-${tone}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function SettingHelp({ children }: { children: React.ReactNode }) {
  return <span className="agent-setting-help">{children}</span>;
}

type CandidateGroup = {
  symbol: string;
  best: Record<string, unknown>;
  supporting: Array<Record<string, unknown>>;
};

function candidateSortValue(row: Record<string, unknown>): number {
  const rank = asNumber(row.rank);
  if (rank !== null) return rank;
  const score = asNumber(row.score);
  return score === null ? 9999 : 9999 - score;
}

export function AgentModeConsole() {
  const [settings, setSettings] = useState<AgentModeSettings>(defaultSettings);
  const [status, setStatus] = useState<AgentModeStatus | null>(null);
  const [latest, setLatest] = useState<AgentModeRunResult | null>(null);
  const [runs, setRuns] = useState<AgentModeRunHistoryItem[]>([]);
  const [trades, setTrades] = useState<AgentModeTrade[]>([]);
  const [performance, setPerformance] = useState<AgentModePerformance | null>(null);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [symbolsText, setSymbolsText] = useState(defaultSettings.manual_symbols.join(", "));
  const [loadState, setLoadState] = useState<"loading" | "error" | "ready">("loading");
  const [feedback, setFeedback] = useState<{ state: "idle" | "loading" | "success" | "error"; message?: string }>({ state: "idle" });
  const [activeTab, setActiveTab] = useState<AgentModeTab>("Overview");
  const [runFilter, setRunFilter] = useState<"all" | "dry-run" | "enabled" | "errors">("all");
  const [performanceTimeframe, setPerformanceTimeframe] = useState("last_30_days");
  const [tradeTimeframe, setTradeTimeframe] = useState("all_time");
  const [tradeSymbol, setTradeSymbol] = useState("");
  const [tradeStatus, setTradeStatus] = useState("");
  const [runStartedAt, setRunStartedAt] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [expandedSymbols, setExpandedSymbols] = useState<Record<string, boolean>>({});

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoadState("loading");
    const [settingsResponse, statusResponse, latestResponse, runsResponse, tradesResponse, performanceResponse, watchlistsResponse] = await Promise.all([
      fetchAgentModeSettings(),
      fetchAgentModeStatus(),
      fetchLatestAgentModeRun(),
      fetchAgentModeRuns({ limit: 50, timeframe: performanceTimeframe }),
      fetchAgentModeTrades({ limit: 100, timeframe: tradeTimeframe, symbol: tradeSymbol.trim() || undefined, status: tradeStatus || undefined }),
      fetchAgentModePerformance({ timeframe: performanceTimeframe, source: "agent_mode" }),
      fetchWatchlists(),
    ]);
    if (!settingsResponse.ok || !settingsResponse.data) {
      setLoadState("error");
      setFeedback({ state: "error", message: settingsResponse.error ?? "Agent Mode settings unavailable." });
      return;
    }
    setSettings(settingsResponse.data);
    setSymbolsText((settingsResponse.data.manual_symbols ?? []).join(", "));
    setStatus(statusResponse.data ?? null);
    setLatest(latestResponse.data?.latestRun?.result ?? null);
    setRuns(runsResponse.data?.items ?? []);
    setTrades(tradesResponse.data?.items ?? []);
    setPerformance(performanceResponse.data ?? null);
    setWatchlists(watchlistsResponse.items);
    setCountdown(statusResponse.data?.seconds_until_next_run ?? null);
    setLoadState("ready");
    if (!statusResponse.ok || !latestResponse.ok || !runsResponse.ok || !tradesResponse.ok || !performanceResponse.ok || !watchlistsResponse.ok) {
      setFeedback({ state: "error", message: "Some Agent Mode performance panels could not refresh. Core settings are still available." });
    }
  }, [performanceTimeframe, tradeStatus, tradeSymbol, tradeTimeframe]);

  useEffect(() => {
    let cancelled = false;
    async function loadInitial() {
      await load();
      if (cancelled) return;
    }
    void loadInitial();
    return () => {
      cancelled = true;
    };
  }, [load]);

  useEffect(() => {
    if (countdown === null) return;
    const timer = window.setInterval(() => {
      setCountdown((current) => current === null ? null : Math.max(0, current - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [countdown === null]);

  const run = latest;
  const summary = run?.summary;
  const latestHistory = performance?.latestRun ?? runs[0] ?? null;
  const latestCounts = {
    paperOpens: summary?.paperOpensExecuted ?? latestHistory?.paperOpensExecuted ?? summary?.executedOrderCount ?? 0,
    paperCloses: summary?.paperClosesExecuted ?? latestHistory?.paperClosesExecuted ?? 0,
    holds: summary?.holds ?? latestHistory?.holds ?? summary?.intentCounts?.HOLD ?? 0,
    blocked: summary?.blockedActions ?? latestHistory?.blockedActions ?? 0,
    cashNoTrade: summary?.cashNoTrade ?? latestHistory?.cashNoTrade ?? summary?.intentCounts?.CASH_NO_TRADE ?? 0,
    totalExecuted: summary?.totalExecutedActions ?? latestHistory?.totalExecutedActions ?? summary?.executedOrderCount ?? 0,
  };
  const scheduledLabel = settings.enabled && !settings.paused && !settings.kill_switch_enabled
    ? `Daily at ${settings.daily_run_time} ${settings.timezone}`
    : "Disabled";
  const agentStatus = settings.kill_switch_enabled ? "kill switch" : settings.paused ? "paused" : settings.enabled ? "enabled" : "disabled";
  const currentPositions = performance?.openPositions ?? run?.currentPaperBook ?? [];
  const browserTimezone = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "unknown", []);
  const agentTimezone = status?.configured_timezone ?? settings.timezone;
  const timezoneMismatch = Boolean(agentTimezone && browserTimezone !== "unknown" && browserTimezone !== agentTimezone);
  const isRunning = feedback.state === "loading" || Boolean(status?.in_progress);
  const isSaving = feedback.state === "loading";
  const paperAccountBasis = (() => {
    const percent = asNumber(settings.max_percent_of_paper_account_per_trade);
    const dollars = asNumber(settings.max_dollars_per_trade);
    if (percent !== null && percent > 0 && dollars !== null && dollars > 0) {
      const normalized = percent > 1 ? percent / 100 : percent;
      return normalized > 0 ? dollars / normalized : null;
    }
    return null;
  })();
  const percentCap = (() => {
    const percent = asNumber(settings.max_percent_of_paper_account_per_trade);
    if (percent === null || percent <= 0 || paperAccountBasis === null) return null;
    const normalized = percent > 1 ? percent / 100 : percent;
    return paperAccountBasis * normalized;
  })();
  const capValues = [settings.max_dollars_per_trade, percentCap, settings.max_exposure_per_symbol]
    .map(asNumber)
    .filter((value): value is number => value !== null && value > 0);
  const effectiveCap = capValues.length ? Math.min(...capValues) : settings.max_dollars_per_trade;

  const parsedSymbols = useMemo(
    () => symbolsText.split(/[,\s]+/).map((item) => item.trim().toUpperCase()).filter(Boolean),
    [symbolsText],
  );
  const selectedWatchlist = useMemo(
    () => watchlists.find((row) => row.id === settings.default_watchlist_id) ?? null,
    [settings.default_watchlist_id, watchlists],
  );
  const universeSource = settings.universe_source || "manual";
  const watchlistMode = universeSource === "watchlist" || universeSource === "watchlist_plus_manual";
  const watchlistSymbols = selectedWatchlist?.symbols ?? [];
  const resolvedRunSymbols = useMemo(() => {
    const merged = new Set<string>();
    if (universeSource === "watchlist" || universeSource === "watchlist_plus_manual") {
      for (const symbol of watchlistSymbols) merged.add(symbol);
    }
    if (universeSource === "manual" || universeSource === "watchlist_plus_manual" || universeSource === "all_active") {
      for (const symbol of parsedSymbols) merged.add(symbol);
    }
    return Array.from(merged).slice(0, settings.scan_depth || 25);
  }, [parsedSymbols, settings.scan_depth, universeSource, watchlistSymbols]);
  const watchlistUnavailable = watchlistMode && (!settings.default_watchlist_id || !selectedWatchlist || watchlistSymbols.length === 0);
  const hasPerformanceHistory = Boolean(
    performance && (
      (performance.runsTracked ?? 0) > 0
      || (performance.tradeCount ?? 0) > 0
      || (performance.openPositionCount ?? 0) > 0
    ),
  );

  const candidateGroups = useMemo<CandidateGroup[]>(() => {
    const groups = new Map<string, Array<Record<string, unknown>>>();
    for (const candidate of run?.candidateQueue ?? []) {
      const symbol = String(candidate.symbol ?? "").toUpperCase() || "UNKNOWN";
      groups.set(symbol, [...(groups.get(symbol) ?? []), candidate]);
    }
    return Array.from(groups.entries())
      .map(([symbol, rows]) => {
        const sorted = [...rows].sort((a, b) => candidateSortValue(a) - candidateSortValue(b));
        return { symbol, best: sorted[0], supporting: sorted.slice(1) };
      })
      .sort((a, b) => candidateSortValue(a.best) - candidateSortValue(b.best));
  }, [run?.candidateQueue]);

  const filteredRuns = useMemo(() => runs.filter((item) => {
    if (runFilter === "dry-run") return item.dryRun;
    if (runFilter === "enabled") return !item.dryRun;
    if (runFilter === "errors") return item.status !== "completed" || (item.warnings?.length ?? 0) > 0 || (item.missingData?.length ?? 0) > 0;
    return true;
  }), [runFilter, runs]);

  async function saveSettings() {
    const watchlistIds = settings.default_watchlist_id ? [settings.default_watchlist_id] : [];
    setFeedback({ state: "loading", message: "Saving Agent Mode settings." });
    const response = await saveAgentModeSettings({
      ...settings,
      manual_symbols: parsedSymbols,
      watchlist_ids: watchlistIds,
      max_positions: settings.max_positions,
      mode: "paper",
    } as Partial<AgentModeSettings> & { mode: "paper" });
    if (!response.ok || !response.data) {
      setFeedback({ state: "error", message: response.error ?? "Settings save failed." });
      return;
    }
    setSettings(response.data);
    setFeedback({ state: "success", message: "Settings saved. Paper-only guard remains active." });
  }

  async function runNow(dry_run: boolean) {
    if (watchlistUnavailable) {
      setFeedback({
        state: "error",
        message: settings.default_watchlist_id
          ? "Selected watchlist is missing or empty. Choose a valid watchlist or switch to manual override."
          : "Choose a watchlist or switch Universe source to manual override before running.",
      });
      return;
    }
    if (!dry_run) {
      const confirmed = window.confirm("Run enabled Agent Mode paper lifecycle now? This may create paper orders or close paper positions. No live broker routing is enabled.");
      if (!confirmed) return;
    }
    const watchlistIds = settings.default_watchlist_id ? [settings.default_watchlist_id] : [];
    const payload: Record<string, unknown> = {
      dry_run,
      universe_source: universeSource,
      default_watchlist_id: settings.default_watchlist_id ?? null,
      watchlist_ids: watchlistIds,
      scan_depth: settings.scan_depth,
      mode: "paper",
    };
    if (universeSource === "manual" || universeSource === "watchlist_plus_manual" || universeSource === "all_active") {
      payload.manual_symbols = parsedSymbols;
      payload.manual_override = universeSource === "manual";
    }
    const started = new Date().toISOString();
    setRunStartedAt(started);
    setFeedback({ state: "loading", message: dry_run ? "Running dry-run Agent Mode." : "Running enabled paper lifecycle." });
    const response = await runAgentMode(payload);
    if (!response.ok || !response.data) {
      setFeedback({ state: "error", message: response.error ?? "Agent Mode run failed." });
      setRunStartedAt(null);
      return;
    }
    setLatest(response.data);
    setFeedback({
      state: "success",
      message: response.data.summary.dryRun ? "Dry-run completed. No paper orders were created." : "Enabled paper run completed through Agent Mode paper lifecycle only.",
    });
    await load(true);
    setRunStartedAt(null);
  }

  async function sendTestNotification(channel: "email" | "sms" | "both" | "none") {
    setFeedback({ state: "loading", message: `Sending ${channel} test notification.` });
    const response = await testAgentModeNotification(channel);
    if (!response.ok || !response.data) {
      setFeedback({ state: "error", message: response.error ?? "Test notification failed." });
      return;
    }
    const statuses = response.data.attempts.map((attempt) => `${asText(attempt.channel)} ${asText(attempt.status)}`).join(", ");
    setFeedback({ state: "success", message: statuses || "Notification preference is none; no message was sent." });
  }

  function toggleSymbol(symbol: string) {
    setExpandedSymbols((current) => ({ ...current, [symbol]: !current[symbol] }));
  }

  if (loadState === "error") {
    return (
      <div className="op-stack">
        <PageHeader
          title="Agent Mode"
          subtitle="Paper-only performance cockpit"
        />
        <ErrorState title="Agent Mode unavailable" hint={feedback.message ?? "Refresh after backend health recovers."} />
      </div>
    );
  }

  return (
    <div className="op-stack">
      <PageHeader
        title="Agent Mode"
        subtitle="Paper-only performance cockpit for deterministic Agent Mode runs."
        actions={<StatusBadge tone="warn">Paper only. No live routing. Disable anytime.</StatusBadge>}
      />

      <InlineFeedback state={feedback.state} message={feedback.message} />

      {isRunning ? (
        <Card title={status?.in_progress ? "Agent Mode run in progress" : "Agent Mode operation running"}>
          <div className="agent-running-banner">
            <strong>{feedback.message ?? "Agent Mode is working."}</strong>
            <span>Started at {formatDateTime(runStartedAt ?? status?.last_run_started_at)}. Previous successful results remain visible while this refresh runs.</span>
            <span>Stage: analyzing watchlist, recommendations, positions, sizing caps, and paper-only risk gates.</span>
          </div>
        </Card>
      ) : null}

      <div className="op-tabs" role="tablist" aria-label="Agent Mode sections">
        {tabs.map((tab) => (
          <button
            key={tab}
            className={`op-tab ${activeTab === tab ? "is-active" : ""}`}
            type="button"
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "Overview" ? (
        <div className="op-stack">
          <Card title="Schedule status">
            {status ? (
              <div className="op-stack">
                <div className="op-grid op-grid-4">
                  <Metric label="Enabled" value={status.agent_enabled ? "enabled" : "disabled"} tone={status.agent_enabled ? "good" : "neutral"} />
                  <Metric label="Server time" value={formatDateTime(status.current_server_time)} />
                  <Metric label="Agent timezone" value={asText(status.configured_timezone)} />
                  <Metric label="Daily run time" value={asText(status.configured_daily_run_time)} />
                  <Metric label="Next scheduled run" value={formatDateTime(status.next_scheduled_run_at)} tone={status.next_scheduled_run_at ? "good" : "neutral"} />
                  <Metric label="Time until next run" value={formatDuration(countdown ?? status.seconds_until_next_run)} />
                  <Metric label="Last result" value={formatFieldLabel(status.last_run_status)} tone={status.last_run_status === "success" ? "good" : status.last_run_status === "failed" ? "bad" : "neutral"} />
                  <Metric label="Last run trades" value={status.last_run_trade_count ?? 0} />
                  <Metric label="Position reviews" value={status.last_run_position_review_count ?? 0} />
                  <Metric label="Blocked actions" value={status.last_run_blocked_count ?? 0} tone={(status.last_run_blocked_count ?? 0) ? "warn" : "neutral"} />
                  <Metric label="Last started" value={formatDateTime(status.last_run_started_at)} />
                  <Metric label="Last completed" value={formatDateTime(status.last_run_completed_at)} />
                </div>
                <div className="op-row">
                  <StatusBadge tone="neutral">scheduler source: {asText(status.scheduler_source)}</StatusBadge>
                  <StatusBadge tone={status.in_progress ? "warn" : "neutral"}>{status.in_progress ? "running" : "not running"}</StatusBadge>
                  {status.last_run_id ? <StatusBadge tone="neutral">run {status.last_run_id}</StatusBadge> : null}
                </div>
                {status.last_skip_reason ? <div className="agent-paper-warning">Last skip/block reason: {formatFieldLabel(status.last_skip_reason)}</div> : null}
                {status.last_error_summary ? <div className="agent-paper-warning">Last error summary: {status.last_error_summary}</div> : null}
                {timezoneMismatch ? (
                  <div className="agent-paper-warning">
                    Your browser timezone differs from the Agent Mode timezone. Agent runs use {agentTimezone}.
                  </div>
                ) : null}
              </div>
            ) : (
              <EmptyState title="Schedule status unavailable" hint="Refresh after backend health recovers. Agent Mode schedule truth is backend-owned." />
            )}
          </Card>

          <Card title="Overview">
            {loadState === "loading" ? (
              <EmptyState title="Loading Agent Mode" hint="Fetching settings, run history, paper trades, and performance." />
            ) : (
              <div className="op-grid op-grid-4">
                <Metric label="Agent status" value={agentStatus} tone={settings.enabled && !settings.paused && !settings.kill_switch_enabled ? "good" : "neutral"} />
                <Metric label="Next scheduled run" value={scheduledLabel} />
                <Metric label="Last run state" value={latestHistory ? (latestHistory.dryRun ? "dry-run" : "enabled paper") : "none"} />
                <Metric label="Paper book count / max" value={`${performance?.openPositionCount ?? currentPositions.length}/${settings.max_positions}`} />
                <Metric label="Realized P&L" value={formatMoney(performance?.realizedPnl)} tone={(performance?.realizedPnl ?? 0) >= 0 ? "good" : "bad"} />
                <Metric label="Unrealized P&L" value={formatMoney(performance?.unrealizedPnl)} tone={(performance?.unrealizedPnl ?? 0) >= 0 ? "good" : "bad"} />
                <Metric label="Total paper P&L" value={formatMoney(performance?.totalPaperPnl)} tone={(performance?.totalPaperPnl ?? 0) >= 0 ? "good" : "bad"} />
                <Metric label="Win rate" value={formatWinRate(performance?.winRate)} />
                <Metric label="Max drawdown" value={formatMoney(performance?.maxDrawdown)} tone="warn" />
                <Metric label="Paper opens latest" value={latestCounts.paperOpens} tone="good" />
                <Metric label="Paper closes latest" value={latestCounts.paperCloses} tone="warn" />
                <Metric label="Blocked latest" value={latestCounts.blocked} tone={latestCounts.blocked ? "warn" : "neutral"} />
              </div>
            )}
          </Card>

          <Card title="Latest run counts">
            {!run && !latestHistory ? (
              <EmptyState title="No Agent Mode run yet" hint="Run dry-run first to inspect paper intents before enabling the paper lifecycle." />
            ) : (
              <div className="op-row">
                <StatusBadge tone="good">paper opens: {latestCounts.paperOpens}</StatusBadge>
                <StatusBadge tone="warn">paper closes: {latestCounts.paperCloses}</StatusBadge>
                <StatusBadge tone="neutral">holds: {latestCounts.holds}</StatusBadge>
                <StatusBadge tone="warn">blocked: {latestCounts.blocked}</StatusBadge>
                <StatusBadge tone="neutral">cash/no trade: {latestCounts.cashNoTrade}</StatusBadge>
                <StatusBadge tone={latestCounts.totalExecuted ? "good" : "neutral"}>executed actions: {latestCounts.totalExecuted}</StatusBadge>
              </div>
            )}
          </Card>

          <Card title="Grouped candidate queue">
            {candidateGroups.length ? (
              <ResponsiveTable label="Grouped candidate queue">
                <table className="op-table">
                  <thead><tr><th>Symbol</th><th>Best strategy</th><th>Rank</th><th>Score</th><th>Status</th><th>Supporting strategies</th></tr></thead>
                  <tbody>{candidateGroups.slice(0, 12).map((group) => (
                    <React.Fragment key={group.symbol}>
                      <tr>
                        <td><strong>{group.symbol}</strong></td>
                        <td>{asText(group.best.strategy)}</td>
                        <td>{asText(group.best.rank)}</td>
                        <td>{asText(group.best.score)}</td>
                        <td>{asText(group.best.status)}</td>
                        <td>
                          {group.supporting.length ? (
                            <button className="op-btn op-btn-ghost" type="button" onClick={() => toggleSymbol(group.symbol)}>
                              {expandedSymbols[group.symbol] ? "Hide" : "Show"} {group.supporting.length}
                            </button>
                          ) : "None"}
                        </td>
                      </tr>
                      {expandedSymbols[group.symbol] ? group.supporting.map((row, index) => (
                        <tr key={`${group.symbol}-${String(row.strategy)}-${index}`} className="agent-support-row">
                          <td>{group.symbol}</td>
                          <td>{asText(row.strategy)}</td>
                          <td>{asText(row.rank)}</td>
                          <td>{asText(row.score)}</td>
                          <td>{asText(row.status)}</td>
                          <td>{asText(row.workflow_source ?? row.source)}</td>
                        </tr>
                      )) : null}
                    </React.Fragment>
                  ))}</tbody>
                </table>
              </ResponsiveTable>
            ) : <EmptyState title="Candidate queue empty" hint="Cash/no trade remains valid when deterministic gates do not produce candidates." />}
          </Card>

          <Card title="Paper actions">
            {run?.intents?.length ? (
              <ResponsiveTable label="Agent Mode paper actions">
                <table className="op-table">
                  <thead><tr><th>Action</th><th>Symbol</th><th>Status</th><th>Reason</th><th>Linked paper IDs</th><th>Summary</th></tr></thead>
                  <tbody>{run.intents.map((intent, index) => (
                    <tr key={`${intent.intent}-${intent.symbol ?? index}-${index}`}>
                      <td><StatusBadge tone={toneForIntent(intent.intent)}>{formatIntentLabel(intent.intent)}</StatusBadge></td>
                      <td>{intent.symbol ?? "-"}</td>
                      <td>{intent.status}</td>
                      <td>{intent.reason ?? "-"}</td>
                      <td>{[intent.order_id ? `order ${intent.order_id}` : null, intent.position_id ? `position ${intent.position_id}` : null, intent.trade_id ? `trade ${intent.trade_id}` : null].filter(Boolean).join(", ") || "-"}</td>
                      <td>{intent.summary ?? "-"}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </ResponsiveTable>
            ) : <EmptyState title="No paper actions" hint="Run Agent Mode to generate holds, paper opens, paper closes, or cash/no trade decisions." />}
          </Card>
        </div>
      ) : null}

      {activeTab === "Runs" ? (
        <Card title="Run history">
          <div className="op-row agent-filter-row">
            <label>
              <span>Timeframe</span>
              <select value={performanceTimeframe} onChange={(event) => setPerformanceTimeframe(event.target.value)}>
                {timeframeOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            {(["all", "dry-run", "enabled", "errors"] as const).map((filter) => (
              <button key={filter} className={`op-btn ${runFilter === filter ? "op-btn-secondary is-active" : "op-btn-ghost"}`} type="button" onClick={() => setRunFilter(filter)}>
                {filter}
              </button>
            ))}
            <button className="op-btn op-btn-ghost" type="button" onClick={() => load(true)}>Refresh</button>
          </div>
          {filteredRuns.length ? (
            <ResponsiveTable label="Agent Mode run history">
              <table className="op-table">
                <thead><tr><th>Generated</th><th>Mode</th><th>Symbols</th><th>Before</th><th>After</th><th>Opens</th><th>Closes</th><th>Holds</th><th>Blocked</th><th>Cash/no trade</th><th>Executed</th><th>Run ID</th></tr></thead>
                <tbody>{filteredRuns.map((row) => (
                  <tr key={row.runId}>
                    <td>{asText(row.generatedAt)}</td>
                    <td>{row.dryRun ? "dry-run" : "enabled paper"}</td>
                    <td>{row.symbols?.join(", ") || "-"}</td>
                    <td>{row.positionsBeforeCount ?? 0}</td>
                    <td>{row.positionsAfterCount ?? 0}</td>
                    <td>{row.paperOpensExecuted ?? 0}</td>
                    <td>{row.paperClosesExecuted ?? 0}</td>
                    <td>{row.holds ?? 0}</td>
                    <td>{row.blockedActions ?? 0}</td>
                    <td>{row.cashNoTrade ?? 0}</td>
                    <td>{row.totalExecutedActions ?? 0}</td>
                    <td>{row.runId}</td>
                  </tr>
                ))}</tbody>
              </table>
            </ResponsiveTable>
          ) : <EmptyState title="No runs match this filter" hint="Agent Mode run audits appear here after dry-run or enabled paper runs." />}
        </Card>
      ) : null}

      {activeTab === "Trades" ? (
        <Card title="Trade ledger">
          <div className="op-row agent-filter-row">
            <label>
              <span>Timeframe</span>
              <select value={tradeTimeframe} onChange={(event) => setTradeTimeframe(event.target.value)}>
                {timeframeOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>
              <span>Symbol</span>
              <input value={tradeSymbol} onChange={(event) => setTradeSymbol(event.target.value.toUpperCase())} placeholder="Optional" />
            </label>
            <label>
              <span>Status</span>
              <select value={tradeStatus} onChange={(event) => setTradeStatus(event.target.value)}>
                <option value="">All</option>
                <option value="open">Open</option>
                <option value="closed">Closed</option>
                <option value="filled">Filled</option>
              </select>
            </label>
            <button className="op-btn op-btn-ghost" type="button" onClick={() => load(true)}>Refresh</button>
          </div>
          {trades.length ? (
            <ResponsiveTable label="Agent Mode trade ledger">
              <table className="op-table">
                <thead><tr><th>Created</th><th>Submitted</th><th>Filled/executed</th><th>Closed</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>Exit</th><th>Realized P&L</th><th>Return</th><th>Holding days</th><th>Status</th><th>Entry reason</th><th>Exit reason</th><th>Run ID</th></tr></thead>
                <tbody>{trades.map((trade) => (
                  <tr key={trade.id}>
                    <td>{formatDateTime(trade.created_at ?? trade.opened_at)}</td>
                    <td>{formatDateTime(trade.submitted_at)}</td>
                    <td>{formatDateTime(trade.filled_at ?? trade.executed_at)}</td>
                    <td>{formatDateTime(trade.closed_at)}</td>
                    <td><strong>{trade.symbol}</strong></td>
                    <td>{trade.side}</td>
                    <td>{formatQty(trade.qty)}</td>
                    <td>{formatPrice(trade.entry_price)}</td>
                    <td>{formatPrice(trade.exit_price)}</td>
                    <td>{formatMoney(trade.realized_pnl)}</td>
                    <td>{formatPercent(trade.return_pct)}</td>
                    <td>{formatQty(trade.holding_days)}</td>
                    <td>{asText(trade.status)}</td>
                    <td>{asText(trade.entry_reason)}</td>
                    <td>{asText(trade.exit_reason)}</td>
                    <td>{asText(trade.linked_run_id)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </ResponsiveTable>
          ) : <EmptyState title="No Agent Mode closed trades yet" hint="Executed paper closes will appear here with linked run IDs and realized P&L." />}
        </Card>
      ) : null}

      {activeTab === "Positions" ? (
        <Card title="Current open paper positions">
          {currentPositions.length ? (
            <ResponsiveTable label="Current open paper positions">
              <table className="op-table">
                <thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Avg entry</th><th>Cost basis</th><th>Mark</th><th>Market value</th><th>Unrealized P&L</th><th>Return</th><th>Days held</th><th>Current agent action</th><th>Status</th></tr></thead>
                <tbody>{currentPositions.map((row, index) => (
                  <tr key={`${asText(row.id)}-${index}`}>
                    <td><strong>{asText(row.symbol)}</strong></td>
                    <td>{asText(row.side)}</td>
                    <td>{formatQty(row.remaining_qty ?? row.qty)}</td>
                    <td>{formatPrice(row.avg_entry_price)}</td>
                    <td>{formatMoney(row.cost_basis ?? row.invested_amount ?? row.open_notional)}</td>
                    <td>{formatPrice(row.current_mark_price ?? row.mark)}</td>
                    <td>{formatMoney(row.current_market_value)}</td>
                    <td>{formatMoney(row.unrealized_pnl)}</td>
                    <td>{formatPercent(row.unrealized_return_pct)}</td>
                    <td>{asText(row.days_held)}</td>
                    <td>{asText(row.current_agent_action)}</td>
                    <td>{asText(row.current_agent_status ?? row.status)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </ResponsiveTable>
          ) : <EmptyState title="No open paper positions" hint="Agent Mode will not force trades just to fill five slots." />}
        </Card>
      ) : null}

      {activeTab === "Performance" ? (
        <Card title="Performance">
          <div className="op-row agent-filter-row">
            <label>
              <span>Timeframe</span>
              <select value={performanceTimeframe} onChange={(event) => setPerformanceTimeframe(event.target.value)}>
                {timeframeOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <StatusBadge tone="neutral">source: {performance?.source ?? "agent_mode"}</StatusBadge>
            <button className="op-btn op-btn-ghost" type="button" onClick={() => load(true)}>Refresh</button>
          </div>
          {performance ? (
            <div className="op-stack">
              {!hasPerformanceHistory ? (
                <EmptyState title="No Agent Mode performance yet" hint="Performance tiles populate after Agent Mode dry-runs, paper opens, paper closes, and position reviews are recorded." />
              ) : null}
              <div className="agent-performance-hero">
                <Metric label="Realized P&L" value={formatMoney(performance.realizedPnl)} tone={toneForSigned(performance.realizedPnl)} />
                <Metric label="Unrealized P&L" value={formatMoney(performance.unrealizedPnl)} tone={toneForSigned(performance.unrealizedPnl)} />
                <Metric label="Total P&L" value={formatMoney(performance.totalPaperPnl)} tone={toneForSigned(performance.totalPaperPnl)} />
                <Metric label="Percent return" value={formatPercent(performance.tradeMetrics?.averageReturn)} tone={toneForSigned(performance.tradeMetrics?.averageReturn)} />
                <Metric label="Open exposure" value={formatMoney(performance.positionMetrics?.openExposure)} />
                <Metric label="Trades opened" value={performance.tradeMetrics?.tradesCreated ?? performance.tradeCount} tone="good" />
                <Metric label="Trades closed" value={performance.tradeMetrics?.closedTrades ?? 0} />
                <Metric label="Win / loss" value={`${performance.winCount} / ${performance.lossCount}`} />
                <Metric label="Runs completed" value={performance.runMetrics?.runsCompleted ?? 0} tone="good" />
                <Metric label="Runs skipped" value={performance.runMetrics?.runsSkipped ?? 0} tone={(performance.runMetrics?.runsSkipped ?? 0) ? "warn" : "neutral"} />
                <Metric label="Runs failed" value={performance.runMetrics?.runsFailed ?? 0} tone={(performance.runMetrics?.runsFailed ?? 0) ? "bad" : "neutral"} />
                <Metric label="Risk blocks" value={performance.runMetrics?.tradesBlocked ?? 0} tone={(performance.runMetrics?.tradesBlocked ?? 0) ? "warn" : "neutral"} />
              </div>
              <div className="op-grid op-grid-4">
                <Metric label="Runs completed" value={performance.runMetrics?.runsCompleted ?? 0} tone="good" />
                <Metric label="Runs failed" value={performance.runMetrics?.runsFailed ?? 0} tone={(performance.runMetrics?.runsFailed ?? 0) ? "bad" : "neutral"} />
                <Metric label="Runs skipped" value={performance.runMetrics?.runsSkipped ?? 0} tone={(performance.runMetrics?.runsSkipped ?? 0) ? "warn" : "neutral"} />
                <Metric label="Avg candidates" value={performance.runMetrics?.averageCandidatesReviewed ?? 0} />
                <Metric label="Trades created" value={performance.tradeMetrics?.tradesCreated ?? performance.tradeCount} tone="good" />
                <Metric label="Trades blocked" value={performance.runMetrics?.tradesBlocked ?? 0} tone={(performance.runMetrics?.tradesBlocked ?? 0) ? "warn" : "neutral"} />
                <Metric label="Open positions" value={performance.positionMetrics?.openPositions ?? performance.openPositionCount} />
                <Metric label="Open exposure" value={formatMoney(performance.positionMetrics?.openExposure)} />
                <Metric label="Sizing blocks" value={performance.riskBlockMetrics?.sizingBlocks ?? 0} tone={(performance.riskBlockMetrics?.sizingBlocks ?? 0) ? "warn" : "neutral"} />
                <Metric label="Stale data blocks" value={performance.riskBlockMetrics?.staleDataBlocks ?? 0} tone={(performance.riskBlockMetrics?.staleDataBlocks ?? 0) ? "warn" : "neutral"} />
                <Metric label="No-watchlist skips" value={performance.riskBlockMetrics?.noWatchlistSkips ?? 0} tone={(performance.riskBlockMetrics?.noWatchlistSkips ?? 0) ? "warn" : "neutral"} />
                <Metric label="Disabled-agent skips" value={performance.riskBlockMetrics?.disabledAgentSkips ?? 0} tone={(performance.riskBlockMetrics?.disabledAgentSkips ?? 0) ? "warn" : "neutral"} />
              </div>
              <ResponsiveTable label="Agent Mode performance">
                <table className="op-table agent-performance-table">
                  <tbody>
                    <tr><th>Cumulative realized P&L</th><td>{formatMoney(performance.cumulativeRealizedPnl)}</td></tr>
                    <tr><th>Unrealized P&L</th><td>{formatMoney(performance.unrealizedPnl)}</td></tr>
                    <tr><th>Total paper P&L</th><td>{formatMoney(performance.totalPaperPnl)}</td></tr>
                    <tr><th>Win / loss count</th><td>{performance.winCount} / {performance.lossCount}</td></tr>
                    <tr><th>Win rate</th><td>{formatWinRate(performance.winRate)}</td></tr>
                    <tr><th>Average win</th><td>{formatMoney(performance.avgWin)}</td></tr>
                    <tr><th>Average loss</th><td>{formatMoney(performance.avgLoss)}</td></tr>
                    <tr><th>Average return</th><td>{formatPercent(performance.tradeMetrics?.averageReturn)}</td></tr>
                    <tr><th>Average hold time</th><td>{formatQty(performance.tradeMetrics?.averageHoldDays)} days</td></tr>
                    <tr><th>Profit factor</th><td>{performance.profitFactor ?? "-"}</td></tr>
                    <tr><th>Max drawdown</th><td>{formatMoney(performance.maxDrawdown)}</td></tr>
                    <tr><th>Runs tracked</th><td>{performance.runsTracked}</td></tr>
                  </tbody>
                </table>
              </ResponsiveTable>
            </div>
          ) : <EmptyState title="Performance unavailable" hint="Run Agent Mode once to start building paper performance history." />}
        </Card>
      ) : null}

      {activeTab === "Settings" ? (
        <Card title="Settings and run controls">
          {loadState === "loading" ? (
            <EmptyState title="Loading Agent Mode" hint="Fetching paper-only settings and run controls." />
          ) : (
            <div className="op-stack">
              <div className="op-row">
                <StatusBadge tone={settings.enabled ? "good" : "neutral"}>{settings.enabled ? "enabled" : "disabled"}</StatusBadge>
                <StatusBadge tone={settings.paused || settings.kill_switch_enabled ? "bad" : "good"}>
                  {settings.paused || settings.kill_switch_enabled ? "paused / kill switch" : "paper guard active"}
                </StatusBadge>
                <StatusBadge tone="neutral">max {settings.max_open_agent_positions ?? settings.max_positions} Agent paper positions</StatusBadge>
                <StatusBadge tone="neutral">SMS provider: {settings.sms_provider_status?.status ?? "unknown"}</StatusBadge>
              </div>
              <div className="op-grid op-grid-3">
                <label>
                  <span>Enabled</span>
                  <input type="checkbox" checked={settings.enabled} onChange={(event) => setSettings({ ...settings, enabled: event.target.checked })} />
                </label>
                <label>
                  <span>Pause agent</span>
                  <input type="checkbox" checked={settings.paused} onChange={(event) => setSettings({ ...settings, paused: event.target.checked })} />
                </label>
                <label>
                  <span>Kill switch</span>
                  <input type="checkbox" checked={settings.kill_switch_enabled} onChange={(event) => setSettings({ ...settings, kill_switch_enabled: event.target.checked })} />
                </label>
                <label>
                  <span>Daily run time</span>
                  <input value={settings.daily_run_time} onChange={(event) => setSettings({ ...settings, daily_run_time: event.target.value })} />
                </label>
                <label>
                  <span>Agent timezone</span>
                  <input value={settings.timezone} onChange={(event) => setSettings({ ...settings, timezone: event.target.value })} />
                </label>
                <label>
                  <span>Scan depth</span>
                  <input type="number" min={1} max={25} value={settings.scan_depth} onChange={(event) => setSettings({ ...settings, scan_depth: Number(event.target.value) })} />
                </label>
                <label>
                  <span>Universe source</span>
                  <select value={settings.universe_source} onChange={(event) => setSettings({ ...settings, universe_source: event.target.value })}>
                    <option value="watchlist">Use selected watchlist</option>
                    <option value="manual">Manual override symbols</option>
                    <option value="watchlist_plus_manual">Selected watchlist plus temporary symbols</option>
                    <option value="all_active">All active user symbols</option>
                  </select>
                  <SettingHelp>Selected watchlist is the default Agent universe. Manual symbols are an explicit temporary override.</SettingHelp>
                </label>
                <label>
                  <span>Selected watchlist</span>
                  <select
                    value={settings.default_watchlist_id ?? ""}
                    onChange={(event) => setSettings({
                      ...settings,
                      default_watchlist_id: event.target.value ? Number(event.target.value) : null,
                      universe_source: event.target.value ? "watchlist" : settings.universe_source,
                    })}
                  >
                    <option value="">No selected watchlist</option>
                    {watchlists.map((row) => (
                      <option key={row.id} value={row.id}>{row.name}{row.is_starter || row.starter ? " (starter)" : ""}</option>
                    ))}
                  </select>
                  <SettingHelp>Scheduled and manual Agent Mode runs use this watchlist unless manual override is selected.</SettingHelp>
                </label>
                <label>
                  <span>Max open Agent positions</span>
                  <input type="number" min={1} max={5} value={settings.max_open_agent_positions ?? 5} onChange={(event) => setSettings({ ...settings, max_open_agent_positions: Number(event.target.value), max_positions: Number(event.target.value) })} />
                  <SettingHelp>Caps the number of open positions Agent Mode may manage in the paper book.</SettingHelp>
                </label>
                <label>
                  <span>Max new trades/run</span>
                  <input type="number" min={0} max={5} value={settings.max_new_trades_per_run ?? 5} onChange={(event) => setSettings({ ...settings, max_new_trades_per_run: Number(event.target.value) })} />
                  <SettingHelp>Limits new Agent-created paper opens in a single run.</SettingHelp>
                </label>
                <label>
                  <span>Max new trades/day</span>
                  <input type="number" min={0} max={5} value={settings.max_new_trades_per_day ?? 5} onChange={(event) => setSettings({ ...settings, max_new_trades_per_day: Number(event.target.value) })} />
                  <SettingHelp>Limits new Agent-created paper opens across the Agent day.</SettingHelp>
                </label>
                <label>
                  <span>Max dollars/trade</span>
                  <input type="number" min={0} step={100} value={settings.max_dollars_per_trade ?? ""} onChange={(event) => setSettings({ ...settings, max_dollars_per_trade: event.target.value ? Number(event.target.value) : null })} />
                </label>
                <label>
                  <span>Max percent/trade</span>
                  <input type="number" min={0} max={100} step={0.5} value={settings.max_percent_of_paper_account_per_trade ?? ""} onChange={(event) => setSettings({ ...settings, max_percent_of_paper_account_per_trade: event.target.value ? Number(event.target.value) : null })} />
                </label>
                <label>
                  <span>Max exposure/symbol</span>
                  <input type="number" min={0} step={100} value={settings.max_exposure_per_symbol ?? ""} onChange={(event) => setSettings({ ...settings, max_exposure_per_symbol: event.target.value ? Number(event.target.value) : null })} />
                </label>
                <label>
                  <span>Min cash reserve</span>
                  <input type="number" min={0} step={100} value={settings.min_cash_reserve ?? 0} onChange={(event) => setSettings({ ...settings, min_cash_reserve: Number(event.target.value) })} />
                  <SettingHelp>Leaves this much simulated paper cash unused when sizing new Agent paper trades.</SettingHelp>
                </label>
              </div>
              <label>
                <span>Manual override symbols</span>
                <textarea value={symbolsText} onChange={(event) => setSymbolsText(event.target.value)} rows={3} />
                <SettingHelp>Used only when Universe source is Manual override, or added to the selected watchlist in plus-manual mode.</SettingHelp>
              </label>
              <section className="agent-settings-section" aria-label="Resolved run universe">
                <h3>Resolved run universe</h3>
                <div className="op-row">
                  <StatusBadge tone={watchlistUnavailable ? "bad" : "neutral"}>
                    source: {universeSource.replace(/_/g, " ")}
                  </StatusBadge>
                  {selectedWatchlist ? <StatusBadge tone="neutral">watchlist: {selectedWatchlist.name}</StatusBadge> : null}
                  <StatusBadge tone={resolvedRunSymbols.length ? "good" : "warn"}>{resolvedRunSymbols.length} symbols</StatusBadge>
                </div>
                {watchlistUnavailable ? (
                  <div className="agent-paper-warning">Selected watchlist is missing or empty. Choose a valid watchlist or switch to manual override before running.</div>
                ) : (
                  <p className="agent-resolved-symbols">This run will analyze: {resolvedRunSymbols.join(", ") || "no symbols resolved"}</p>
                )}
              </section>
              <div className="op-row">
                <label><input type="checkbox" checked={settings.allow_opens} onChange={(event) => setSettings({ ...settings, allow_opens: event.target.checked })} /> Allow paper opens</label>
                <label><input type="checkbox" checked={settings.allow_closes} onChange={(event) => setSettings({ ...settings, allow_closes: event.target.checked })} /> Allow Agent Mode paper closes</label>
                <label><input type="checkbox" checked={settings.allow_scale_resize} onChange={(event) => setSettings({ ...settings, allow_scale_resize: event.target.checked })} /> Allow scale-in review <SettingHelp>Allows Agent Mode to review existing open positions for possible add-on opportunities. This does not bypass risk gates.</SettingHelp></label>
                <label><input type="checkbox" checked={Boolean(settings.allow_scale_ins)} onChange={(event) => setSettings({ ...settings, allow_scale_ins: event.target.checked })} /> Allow scale in <SettingHelp>Allows Agent Mode to create an additional paper trade in a symbol that already has an open Agent position, subject to sizing and risk limits.</SettingHelp></label>
                <label><input type="checkbox" checked={Boolean(settings.allow_new_trade_when_symbol_already_open)} onChange={(event) => setSettings({ ...settings, allow_new_trade_when_symbol_already_open: event.target.checked })} /> Allow duplicate open symbol <SettingHelp>Allows more than one open Agent position for the same symbol. Leave off for cleaner position management.</SettingHelp></label>
                <label><input type="checkbox" checked={Boolean(settings.require_confirmation_for_restricted)} onChange={(event) => setSettings({ ...settings, require_confirmation_for_restricted: event.target.checked })} /> Require restricted confirmation <SettingHelp>Restricted candidates are not automatically acted on unless this setting permits a confirmation workflow. Paper-only guardrails still apply.</SettingHelp></label>
              </div>
              <section className="agent-settings-section" aria-label="Sizing preview">
                <h3>Sizing preview</h3>
                <div className="op-grid op-grid-4">
                  <Metric label="Paper account basis" value={formatMoney(paperAccountBasis)} />
                  <Metric label="Max dollars/trade" value={formatMoney(settings.max_dollars_per_trade)} />
                  <Metric label="Percent cap" value={formatMoney(percentCap)} />
                  <Metric label="Effective cap" value={formatMoney(effectiveCap)} tone="warn" />
                  <Metric label="Max trades/run" value={settings.max_new_trades_per_run ?? 5} />
                  <Metric label="Max trades/day" value={settings.max_new_trades_per_day ?? 5} />
                  <Metric label="Max open positions" value={settings.max_open_agent_positions ?? settings.max_positions} />
                  <Metric label="Min cash reserve" value={formatMoney(settings.min_cash_reserve)} />
                </div>
              </section>
              <section className="agent-settings-section" aria-label="Notification preferences">
                <h3>Notification preferences</h3>
                <div className="op-stack">
                  <div className="op-grid op-grid-3">
                    <label>
                      <span>Preference</span>
                      <select
                        value={settings.notification_preference ?? "none"}
                        onChange={(event) => {
                          const preference = event.target.value as "none" | "email" | "sms" | "both";
                          setSettings({
                            ...settings,
                            notification_preference: preference,
                            email_notifications_enabled: preference === "email" || preference === "both",
                            sms_notifications_enabled: preference === "sms" || preference === "both",
                          });
                        }}
                      >
                        <option value="none">None</option>
                        <option value="email">Email</option>
                        <option value="sms">SMS</option>
                        <option value="both">Both</option>
                      </select>
                      <SettingHelp>Controls the single Agent Mode run digest. It does not send one message per symbol.</SettingHelp>
                    </label>
                    <label>
                      <span>Phone number</span>
                      <input value={settings.notification_phone_number ?? ""} onChange={(event) => setSettings({ ...settings, notification_phone_number: event.target.value })} placeholder="+1..." />
                    </label>
                    <label className="dtb-checkbox">
                      <input type="checkbox" checked={Boolean(settings.sms_consent_confirmed)} onChange={(event) => setSettings({ ...settings, sms_consent_confirmed: event.target.checked })} />
                      <span>SMS consent confirmed</span>
                      <SettingHelp>Required before MacMarket sends Agent Mode SMS digests to this phone number.</SettingHelp>
                    </label>
                  </div>
                  <div className="op-row">
                    <StatusBadge tone={settings.sms_provider_status?.status === "ready" ? "good" : "warn"}>
                      SMS {settings.sms_provider_status?.status ?? "unknown"}
                    </StatusBadge>
                    <StatusBadge tone="neutral">Twilio secrets stay server-only</StatusBadge>
                    <button className="op-btn op-btn-ghost" type="button" onClick={() => sendTestNotification("email")} disabled={isSaving}>Test email</button>
                    <button className="op-btn op-btn-ghost" type="button" onClick={() => sendTestNotification("sms")} disabled={isSaving}>Test SMS</button>
                  </div>
                </div>
              </section>
              <div className="agent-paper-warning">
                Enabled paper mode can create paper orders or close paper positions through the Agent Mode paper lifecycle. It never enables live broker routing.
              </div>
              <div className="op-row">
                <button className="op-btn op-btn-secondary" type="button" onClick={saveSettings} disabled={isRunning}>Save settings</button>
                <button className="op-btn op-btn-primary" type="button" onClick={() => runNow(true)} disabled={isRunning || watchlistUnavailable}>Run dry-run</button>
                <button className="op-btn op-btn-destructive" type="button" onClick={() => runNow(false)} disabled={isRunning || watchlistUnavailable || !settings.enabled || settings.paused || settings.kill_switch_enabled}>
                  Run enabled paper mode
                </button>
              </div>
            </div>
          )}
        </Card>
      ) : null}

      <Card title="Data quality / warnings">
        {run?.dataQuality?.length ? (
          <ResponsiveTable label="Data quality">
            <table className="op-table">
              <thead><tr><th>Symbol</th><th>Status</th><th>Source</th><th>Fallback</th><th>Reason</th></tr></thead>
              <tbody>{run.dataQuality.map((row, index) => (
                <tr key={`${asText(row.symbol)}-${index}`}>
                  <td>{asText(row.symbol)}</td><td>{asText(row.status)}</td><td>{asText(row.source)}</td><td>{asText(row.fallback_mode)}</td><td>{asText(row.reason)}</td>
                </tr>
              ))}</tbody>
            </table>
          </ResponsiveTable>
        ) : <EmptyState title="No data quality report yet" hint="The next run will label provider, fallback, and missing data for each symbol." />}
      </Card>
    </div>
  );
}
