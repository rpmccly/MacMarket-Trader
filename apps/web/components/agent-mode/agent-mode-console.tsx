"use client";

import React from "react";
import { useEffect, useMemo, useState } from "react";

import { Card, EmptyState, ErrorState, InlineFeedback, PageHeader, ResponsiveTable, StatusBadge } from "@/components/operator-ui";
import {
  fetchAgentModeSettings,
  fetchLatestAgentModeRun,
  runAgentMode,
  saveAgentModeSettings,
  type AgentModeRunResult,
  type AgentModeSettings,
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

export function AgentModeConsole() {
  const [settings, setSettings] = useState<AgentModeSettings>(defaultSettings);
  const [latest, setLatest] = useState<AgentModeRunResult | null>(null);
  const [symbolsText, setSymbolsText] = useState(defaultSettings.manual_symbols.join(", "));
  const [loadState, setLoadState] = useState<"loading" | "error" | "ready">("loading");
  const [feedback, setFeedback] = useState<{ state: "idle" | "loading" | "success" | "error"; message?: string }>({ state: "idle" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoadState("loading");
      const [settingsResponse, latestResponse] = await Promise.all([
        fetchAgentModeSettings(),
        fetchLatestAgentModeRun(),
      ]);
      if (cancelled) return;
      if (!settingsResponse.ok || !settingsResponse.data) {
        setLoadState("error");
        setFeedback({ state: "error", message: settingsResponse.error ?? "Agent Mode settings unavailable." });
        return;
      }
      setSettings(settingsResponse.data);
      setSymbolsText((settingsResponse.data.manual_symbols ?? []).join(", "));
      const latestRun = latestResponse.data?.latestRun?.result ?? null;
      setLatest(latestRun);
      setLoadState("ready");
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const run = latest;
  const summary = run?.summary;
  const intentCounts = summary?.intentCounts ?? {};
  const dryRun = summary?.dryRun ?? !settings.enabled;
  const scheduledLabel = settings.enabled && !settings.paused && !settings.kill_switch_enabled
    ? `Scheduled daily at ${settings.daily_run_time} ${settings.timezone}`
    : "Scheduled run disabled";

  const parsedSymbols = useMemo(
    () => symbolsText.split(/[,\s]+/).map((item) => item.trim().toUpperCase()).filter(Boolean),
    [symbolsText],
  );

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
    setFeedback({ state: "loading", message: dry_run ? "Running dry-run Agent Mode." : "Running enabled paper Agent Mode." });
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
      message: response.data.summary.dryRun ? "Dry-run completed. No paper orders were created." : "Completed through paper lifecycle only.",
    });
  }

  if (loadState === "error") {
    return (
      <div className="op-stack">
        <PageHeader
          title="Agent Mode"
          subtitle="Autonomous paper-trading operator"
        />
        <ErrorState title="Agent Mode unavailable" hint={feedback.message ?? "Refresh after backend health recovers."} />
      </div>
    );
  }

  return (
    <div className="op-stack">
      <PageHeader
        title="Agent Mode"
        subtitle="Autonomous paper-trading operator"
        actions={<StatusBadge tone="warn">Paper only. No live routing. Disable anytime.</StatusBadge>}
      />

      <InlineFeedback state={feedback.state} message={feedback.message} />

      <Card title="Agent status/settings">
        {loadState === "loading" ? (
          <EmptyState title="Loading Agent Mode" hint="Fetching paper-only settings and the latest run." />
        ) : (
          <div className="op-stack">
            <div className="op-row" style={{ flexWrap: "wrap" }}>
              <StatusBadge tone={settings.enabled ? "good" : "neutral"}>{settings.enabled ? "enabled" : "disabled"}</StatusBadge>
              <StatusBadge tone={settings.paused || settings.kill_switch_enabled ? "bad" : "good"}>
                {settings.paused || settings.kill_switch_enabled ? "paused / kill switch" : "paper guard active"}
              </StatusBadge>
              <StatusBadge tone="neutral">{scheduledLabel}</StatusBadge>
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
            <div className="op-row" style={{ flexWrap: "wrap" }}>
              <label><input type="checkbox" checked={settings.allow_opens} onChange={(event) => setSettings({ ...settings, allow_opens: event.target.checked })} /> Allow paper opens</label>
              <label><input type="checkbox" checked={settings.allow_closes} onChange={(event) => setSettings({ ...settings, allow_closes: event.target.checked })} /> Allow paper closes</label>
              <label><input type="checkbox" checked={settings.allow_scale_resize} onChange={(event) => setSettings({ ...settings, allow_scale_resize: event.target.checked })} /> Allow scale/resize review</label>
            </div>
            <div className="op-row">
              <button onClick={saveSettings}>Save settings</button>
              <button onClick={() => runNow(true)}>Run dry-run</button>
              <button onClick={() => runNow(false)} disabled={!settings.enabled || settings.paused || settings.kill_switch_enabled}>
                Run enabled paper mode
              </button>
            </div>
          </div>
        )}
      </Card>

      <Card title="Latest run summary">
        {!run ? (
          <EmptyState title="No Agent Mode run yet" hint="Run dry-run first to inspect paper intents before enabling execution." />
        ) : (
          <div className="op-grid op-grid-4">
            <div><strong>{summary?.dryRun ? "Dry-run" : "Completed"}</strong><span>State</span></div>
            <div><strong>{summary?.openPositionsBefore ?? 0}</strong><span>Paper book before</span></div>
            <div><strong>{summary?.targetPositionsMax ?? 5}</strong><span>Target cap</span></div>
            <div><strong>{summary?.executedOrderCount ?? 0}</strong><span>Executed paper orders</span></div>
          </div>
        )}
      </Card>

      <Card title="Current paper book">
        {run?.currentPaperBook?.length ? (
          <ResponsiveTable label="Current paper book">
            <table>
              <thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Avg entry</th><th>Status</th></tr></thead>
              <tbody>{run.currentPaperBook.map((row, index) => (
                <tr key={`${row.symbol}-${index}`}>
                  <td>{asText(row.symbol)}</td><td>{asText(row.side)}</td><td>{asText(row.remaining_qty)}</td><td>{asText(row.avg_entry_price)}</td><td>{asText(row.status)}</td>
                </tr>
              ))}</tbody>
            </table>
          </ResponsiveTable>
        ) : <EmptyState title="No open paper positions" hint="Agent Mode will not force trades just to fill five slots." />}
      </Card>

      <Card title="Proposed/executed paper actions">
        {run?.intents?.length ? (
          <ResponsiveTable label="Agent Mode intents">
            <table>
              <thead><tr><th>Action</th><th>Symbol</th><th>Status</th><th>Reason</th><th>Summary</th></tr></thead>
              <tbody>{run.intents.map((intent, index) => (
                <tr key={`${intent.intent}-${intent.symbol ?? index}-${index}`}>
                  <td><StatusBadge tone={toneForIntent(intent.intent)}>{formatIntentLabel(intent.intent)}</StatusBadge></td>
                  <td>{intent.symbol ?? "-"}</td>
                  <td>{intent.status}</td>
                  <td>{intent.reason ?? "-"}</td>
                  <td>{intent.summary ?? "-"}</td>
                </tr>
              ))}</tbody>
            </table>
          </ResponsiveTable>
        ) : <EmptyState title="No paper actions" hint="Run Agent Mode to generate hold, paper open, paper close, or cash/no trade intents." />}
      </Card>

      <Card title="Candidate queue">
        {run?.candidateQueue?.length ? (
          <ResponsiveTable label="Candidate queue">
            <table>
              <thead><tr><th>Rank</th><th>Symbol</th><th>Strategy</th><th>Status</th><th>Score</th><th>Source</th></tr></thead>
              <tbody>{run.candidateQueue.slice(0, 12).map((row, index) => (
                <tr key={`${row.symbol}-${row.strategy}-${index}`}>
                  <td>{asText(row.rank)}</td><td>{asText(row.symbol)}</td><td>{asText(row.strategy)}</td><td>{asText(row.status)}</td><td>{asText(row.score)}</td><td>{asText(row.workflow_source ?? row.source)}</td>
                </tr>
              ))}</tbody>
            </table>
          </ResponsiveTable>
        ) : <EmptyState title="Candidate queue empty" hint="Cash/no trade remains valid when deterministic gates do not produce candidates." />}
      </Card>

      <Card title="Decision memo">
        <div className="op-stack">
          {(run?.decisionMemo ?? [
            "Paper only. No live routing. Disable anytime.",
            "Dry-run mode records intents without creating paper orders.",
          ]).map((line) => <p key={line}>{line}</p>)}
          <div className="op-row" style={{ flexWrap: "wrap" }}>
            {Object.entries(intentCounts).map(([key, value]) => <StatusBadge key={key} tone="neutral">{formatIntentLabel(key)}: {value}</StatusBadge>)}
          </div>
        </div>
      </Card>

      <Card title="Data quality / warnings">
        {run?.dataQuality?.length ? (
          <ResponsiveTable label="Data quality">
            <table>
              <thead><tr><th>Symbol</th><th>Status</th><th>Source</th><th>Fallback</th><th>Reason</th></tr></thead>
              <tbody>{run.dataQuality.map((row, index) => (
                <tr key={`${row.symbol}-${index}`}>
                  <td>{asText(row.symbol)}</td><td>{asText(row.status)}</td><td>{asText(row.source)}</td><td>{asText(row.fallback_mode)}</td><td>{asText(row.reason)}</td>
                </tr>
              ))}</tbody>
            </table>
          </ResponsiveTable>
        ) : <EmptyState title="No data quality report yet" hint="The next run will label provider, fallback, and missing data for each symbol." />}
        {dryRun ? <p style={{ color: "var(--op-muted, #7a8999)" }}>Dry-run state: no paper orders are created.</p> : null}
      </Card>
    </div>
  );
}
