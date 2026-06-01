"use client";

import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Card, EmptyState, ErrorState, InlineFeedback, PageHeader, ResponsiveTable, StatusBadge } from "@/components/operator-ui";
import {
  fetchAgentModePerformance,
  fetchAgentModeRuns,
  fetchAgentModeSettings,
  fetchAgentModeTrades,
  fetchLatestAgentModeRun,
  runAgentMode,
  saveAgentModeSettings,
  type AgentModePerformance,
  type AgentModeRunHistoryItem,
  type AgentModeRunResult,
  type AgentModeSettings,
  type AgentModeTrade,
} from "@/lib/agent-mode-api";

const defaultSettings: AgentModeSettings = {
  enabled: false,
  paused: false,
  kill_switch_enabled: false,
  daily_run_time: "15:45",
  timezone: "America/New_York",
  universe_source: "manual",
  manual_symbols: ["SPY", "QQQ", "MTUM"],
  watchlist_ids: [],
  max_positions: 5,
  scan_depth: 12,
  allow_opens: true,
  allow_closes: true,
  allow_scale_resize: false,
  paper_only: true,
  execution_mode: "paper",
};

const tabs = ["Overview", "Runs", "Trades", "Positions", "Performance", "Settings"] as const;
type AgentModeTab = typeof tabs[number];

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

function Metric({ label, value, tone = "neutral" }: { label: string; value: string | number; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return (
    <div className={`agent-metric agent-metric-${tone}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
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
  const [latest, setLatest] = useState<AgentModeRunResult | null>(null);
  const [runs, setRuns] = useState<AgentModeRunHistoryItem[]>([]);
  const [trades, setTrades] = useState<AgentModeTrade[]>([]);
  const [performance, setPerformance] = useState<AgentModePerformance | null>(null);
  const [symbolsText, setSymbolsText] = useState(defaultSettings.manual_symbols.join(", "));
  const [loadState, setLoadState] = useState<"loading" | "error" | "ready">("loading");
  const [feedback, setFeedback] = useState<{ state: "idle" | "loading" | "success" | "error"; message?: string }>({ state: "idle" });
  const [activeTab, setActiveTab] = useState<AgentModeTab>("Overview");
  const [runFilter, setRunFilter] = useState<"all" | "dry-run" | "enabled" | "errors">("all");
  const [expandedSymbols, setExpandedSymbols] = useState<Record<string, boolean>>({});

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoadState("loading");
    const [settingsResponse, latestResponse, runsResponse, tradesResponse, performanceResponse] = await Promise.all([
      fetchAgentModeSettings(),
      fetchLatestAgentModeRun(),
      fetchAgentModeRuns({ limit: 50 }),
      fetchAgentModeTrades(100),
      fetchAgentModePerformance(),
    ]);
    if (!settingsResponse.ok || !settingsResponse.data) {
      setLoadState("error");
      setFeedback({ state: "error", message: settingsResponse.error ?? "Agent Mode settings unavailable." });
      return;
    }
    setSettings(settingsResponse.data);
    setSymbolsText((settingsResponse.data.manual_symbols ?? []).join(", "));
    setLatest(latestResponse.data?.latestRun?.result ?? null);
    setRuns(runsResponse.data?.items ?? []);
    setTrades(tradesResponse.data?.items ?? []);
    setPerformance(performanceResponse.data ?? null);
    setLoadState("ready");
    if (!latestResponse.ok || !runsResponse.ok || !tradesResponse.ok || !performanceResponse.ok) {
      setFeedback({ state: "error", message: "Some Agent Mode performance panels could not refresh. Core settings are still available." });
    }
  }, []);

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

  const parsedSymbols = useMemo(
    () => symbolsText.split(/[,\s]+/).map((item) => item.trim().toUpperCase()).filter(Boolean),
    [symbolsText],
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
    setFeedback({ state: "loading", message: "Saving Agent Mode settings." });
    const response = await saveAgentModeSettings({
      ...settings,
      manual_symbols: parsedSymbols,
      max_positions: 5,
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
    if (!dry_run) {
      const confirmed = window.confirm("Run enabled Agent Mode paper lifecycle now? This may create paper orders or close paper positions. No live broker routing is enabled.");
      if (!confirmed) return;
    }
    setFeedback({ state: "loading", message: dry_run ? "Running dry-run Agent Mode." : "Running enabled paper lifecycle." });
    const response = await runAgentMode({
      dry_run,
      symbols: parsedSymbols,
      scan_depth: settings.scan_depth,
      mode: "paper",
    });
    if (!response.ok || !response.data) {
      setFeedback({ state: "error", message: response.error ?? "Agent Mode run failed." });
      return;
    }
    setLatest(response.data);
    setFeedback({
      state: "success",
      message: response.data.summary.dryRun ? "Dry-run completed. No paper orders were created." : "Enabled paper run completed through Agent Mode paper lifecycle only.",
    });
    await load(true);
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
            {(["all", "dry-run", "enabled", "errors"] as const).map((filter) => (
              <button key={filter} className={`op-btn ${runFilter === filter ? "op-btn-secondary is-active" : "op-btn-ghost"}`} type="button" onClick={() => setRunFilter(filter)}>
                {filter}
              </button>
            ))}
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
          {trades.length ? (
            <ResponsiveTable label="Agent Mode trade ledger">
              <table className="op-table">
                <thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>Exit</th><th>Realized P&L</th><th>Return</th><th>Holding days</th><th>Entry reason</th><th>Exit reason</th><th>Run ID</th></tr></thead>
                <tbody>{trades.map((trade) => (
                  <tr key={trade.id}>
                    <td><strong>{trade.symbol}</strong></td>
                    <td>{trade.side}</td>
                    <td>{formatQty(trade.qty)}</td>
                    <td>{formatPrice(trade.entry_price)}</td>
                    <td>{formatPrice(trade.exit_price)}</td>
                    <td>{formatMoney(trade.realized_pnl)}</td>
                    <td>{formatPercent(trade.return_pct)}</td>
                    <td>{formatQty(trade.holding_days)}</td>
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
                <thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Avg entry</th><th>Mark</th><th>Unrealized P&L</th><th>Return</th><th>Days held</th><th>Current agent action</th><th>Status</th></tr></thead>
                <tbody>{currentPositions.map((row, index) => (
                  <tr key={`${asText(row.id)}-${index}`}>
                    <td><strong>{asText(row.symbol)}</strong></td>
                    <td>{asText(row.side)}</td>
                    <td>{formatQty(row.remaining_qty ?? row.qty)}</td>
                    <td>{formatPrice(row.avg_entry_price)}</td>
                    <td>{formatPrice(row.current_mark_price ?? row.mark)}</td>
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
          {performance ? (
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
                  <tr><th>Profit factor</th><td>{performance.profitFactor ?? "-"}</td></tr>
                  <tr><th>Max drawdown</th><td>{formatMoney(performance.maxDrawdown)}</td></tr>
                  <tr><th>Runs tracked</th><td>{performance.runsTracked}</td></tr>
                </tbody>
              </table>
            </ResponsiveTable>
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
                <StatusBadge tone="neutral">max 5 paper positions</StatusBadge>
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
                  <span>Scan depth</span>
                  <input type="number" min={1} max={25} value={settings.scan_depth} onChange={(event) => setSettings({ ...settings, scan_depth: Number(event.target.value) })} />
                </label>
                <label>
                  <span>Universe source</span>
                  <select value={settings.universe_source} onChange={(event) => setSettings({ ...settings, universe_source: event.target.value })}>
                    <option value="manual">Manual symbols</option>
                    <option value="watchlist">Watchlist</option>
                    <option value="watchlist_plus_manual">Watchlist plus manual</option>
                    <option value="all_active">All active user symbols</option>
                  </select>
                </label>
              </div>
              <label>
                <span>Symbols</span>
                <textarea value={symbolsText} onChange={(event) => setSymbolsText(event.target.value)} rows={3} />
              </label>
              <div className="op-row">
                <label><input type="checkbox" checked={settings.allow_opens} onChange={(event) => setSettings({ ...settings, allow_opens: event.target.checked })} /> Allow paper opens</label>
                <label><input type="checkbox" checked={settings.allow_closes} onChange={(event) => setSettings({ ...settings, allow_closes: event.target.checked })} /> Allow Agent Mode paper closes</label>
                <label><input type="checkbox" checked={settings.allow_scale_resize} onChange={(event) => setSettings({ ...settings, allow_scale_resize: event.target.checked })} /> Allow scale/resize review</label>
              </div>
              <div className="agent-paper-warning">
                Enabled paper mode can create paper orders or close paper positions through the Agent Mode paper lifecycle. It never enables live broker routing.
              </div>
              <div className="op-row">
                <button className="op-btn op-btn-secondary" type="button" onClick={saveSettings}>Save settings</button>
                <button className="op-btn op-btn-primary" type="button" onClick={() => runNow(true)}>Run dry-run</button>
                <button className="op-btn op-btn-destructive" type="button" onClick={() => runNow(false)} disabled={!settings.enabled || settings.paused || settings.kill_switch_enabled}>
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
