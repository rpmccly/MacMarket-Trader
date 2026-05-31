"use client";

import React, { Fragment, useEffect, useMemo, useState } from "react";

import { Card, EmptyState, ErrorState, PageHeader, ResponsiveTable, StatusBadge } from "@/components/operator-ui";
import {
  buildDataParityCsv,
  createBlankTosReference,
  DATA_PARITY_DEFAULT_LOOKBACK_BARS,
  DATA_PARITY_DEFAULT_SYMBOLS,
  DATA_PARITY_TIMEFRAMES,
  fetchDataParitySnapshot,
  fetchDataParitySnapshots,
  fetchSchwabStatus,
  normalizeTosReferenceRows,
  parseParitySymbols,
  runDataParity,
  type DataParityResult,
  type DataParityRunResponse,
  type DataParitySnapshotSummary,
  type DataParityTimeframe,
  type SchwabStatus,
  type TosReferenceInput,
} from "@/lib/data-parity-api";

type BadgeTone = "good" | "warn" | "bad" | "neutral";

const COMPONENT_FIELDS: Record<string, string[]> = {
  trueMomentum: ["trueMomentumScore", "trueMomentum", "trueMomentumEma"],
  haco: ["hacoDirection", "hacoLatestFlip"],
  hacolt: ["hacoltDirection"],
  hiLo: ["hiLoState", "hiLoValue", "hiLoScore"],
  squeeze: ["squeezeState", "squeezeHistogram"],
};

function verdictTone(value: string | undefined | null): BadgeTone {
  switch (String(value ?? "").toLowerCase()) {
    case "match":
    case "ok":
    case "connected":
      return "good";
    case "not_provided":
    case "unavailable":
    case "configured":
      return "neutral";
    case "mismatch":
    case "insufficient_data":
    case "expired":
    case "reconnect_required":
    case "schwab_not_connected":
      return "warn";
    case "error":
    case "degraded":
      return "bad";
    default:
      return "neutral";
  }
}

function rootCauseTone(value: string): BadgeTone {
  return value === "match" ? "good" : value === "error" ? "bad" : "warn";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function formatTimestamp(value: unknown): string {
  if (!value) return "-";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function summaryValue(response: DataParityRunResponse | null, key: string): number {
  return Number(response?.summary?.[key] ?? 0);
}

function comparisonVerdict(result: DataParityResult, key: "rawBars" | "canonicalBars"): string {
  return String(asRecord(result[key])["verdict"] ?? "-");
}

function componentVerdict(result: DataParityResult, component: keyof typeof COMPONENT_FIELDS): string {
  const indicators = asRecord(result.indicators);
  const current = asRecord(asRecord(indicators.current)[component]);
  const candidate = asRecord(asRecord(indicators.candidate)[component]);
  if (current.available === false || candidate.available === false) return "unavailable";
  const mismatches = Array.isArray(indicators.mismatches) ? indicators.mismatches : [];
  const fields = COMPONENT_FIELDS[component];
  if (mismatches.some((item) => fields.includes(String(asRecord(item).field ?? "")))) return "mismatch";
  return String(indicators.verdict ?? "-");
}

function latestClose(comparison: unknown, side: "latest_current" | "latest_candidate"): string {
  return formatValue(asRecord(asRecord(comparison)[side]).close);
}

function downloadText(filename: string, mimeType: string, content: string) {
  const blob = new Blob([content], { type: mimeType });
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(href);
}

function ComparisonDetail({ title, comparison }: { title: string; comparison: unknown }) {
  const record = asRecord(comparison);
  const currentMeta = asRecord(record.current_metadata);
  const candidateMeta = asRecord(record.candidate_metadata);
  return (
    <section className="dp-detail-section">
      <div className="dp-detail-title">
        <strong>{title}</strong>
        <StatusBadge tone={verdictTone(String(record.verdict ?? ""))}>{formatValue(record.verdict)}</StatusBadge>
      </div>
      <div className="dp-kv-grid">
        <span>current bars</span><strong>{formatValue(record.bars_current)}</strong>
        <span>Schwab bars</span><strong>{formatValue(record.bars_candidate)}</strong>
        <span>aligned</span><strong>{formatValue(record.aligned_timestamps)}</strong>
        <span>current latest close</span><strong>{latestClose(record, "latest_current")}</strong>
        <span>Schwab latest close</span><strong>{latestClose(record, "latest_candidate")}</strong>
        <span>max price delta</span><strong>{formatValue(record.max_price_delta)}</strong>
        <span>max volume delta</span><strong>{formatValue(record.max_volume_delta)}</strong>
        <span>latest timestamp match</span><strong>{formatValue(record.latest_timestamp_match)}</strong>
        <span>current first</span><strong>{formatTimestamp(record.first_timestamp_current)}</strong>
        <span>Schwab first</span><strong>{formatTimestamp(record.first_timestamp_candidate)}</strong>
        <span>current last</span><strong>{formatTimestamp(record.last_timestamp_current)}</strong>
        <span>Schwab last</span><strong>{formatTimestamp(record.last_timestamp_candidate)}</strong>
        <span>missing on current</span><strong>{formatValue(record.missing_timestamps_current_count)}</strong>
        <span>extra on current</span><strong>{formatValue(record.extra_timestamps_current_count)}</strong>
        <span>current source</span><strong>{formatValue(currentMeta.provider)}</strong>
        <span>Schwab source</span><strong>{formatValue(candidateMeta.provider)}</strong>
        <span>session policy</span><strong>{formatValue(candidateMeta.session_policy ?? currentMeta.session_policy)}</strong>
      </div>
    </section>
  );
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <section className="dp-detail-section">
      <strong>{label}</strong>
      <pre className="dp-json">{JSON.stringify(value ?? {}, null, 2)}</pre>
    </section>
  );
}

export function DataParityLab() {
  const [schwabStatus, setSchwabStatus] = useState<SchwabStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [symbolsText, setSymbolsText] = useState(DATA_PARITY_DEFAULT_SYMBOLS);
  const [selectedTimeframes, setSelectedTimeframes] = useState<Record<DataParityTimeframe, boolean>>({
    "1W": true,
    "1D": true,
    "4H": true,
    "1H": true,
    "30M": true,
  });
  const [lookbackBars, setLookbackBars] = useState(DATA_PARITY_DEFAULT_LOOKBACK_BARS);
  const [saveSnapshot, setSaveSnapshot] = useState(true);
  const [tosRows, setTosRows] = useState<TosReferenceInput[]>([]);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<DataParityRunResponse | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<DataParitySnapshotSummary[]>([]);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);

  const selectedTfList = useMemo(
    () => DATA_PARITY_TIMEFRAMES.filter((timeframe) => selectedTimeframes[timeframe]),
    [selectedTimeframes],
  );

  async function loadStatus() {
    setStatusLoading(true);
    setStatusError(null);
    try {
      setSchwabStatus(await fetchSchwabStatus());
    } catch (error) {
      setStatusError(error instanceof Error ? error.message : "Unable to load Schwab status.");
    } finally {
      setStatusLoading(false);
    }
  }

  async function loadSnapshots() {
    setSnapshotError(null);
    try {
      setSnapshots(await fetchDataParitySnapshots());
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : "Unable to load snapshots.");
    }
  }

  useEffect(() => {
    void loadStatus();
    void loadSnapshots();
  }, []);

  function updateTosRow(index: number, field: keyof TosReferenceInput, value: string | number | null) {
    setTosRows((rows) => rows.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)));
  }

  async function runComparison() {
    setRunError(null);
    const symbols = parseParitySymbols(symbolsText);
    if (!symbols.length) {
      setRunError("Enter at least one symbol.");
      return;
    }
    if (!selectedTfList.length) {
      setRunError("Select at least one timeframe.");
      return;
    }
    setRunning(true);
    try {
      const response = await runDataParity({
        symbols,
        timeframes: selectedTfList,
        lookbackBars,
        sessionPolicy: "regular_hours",
        includeExtendedHours: false,
        saveSnapshot,
        tosReferences: normalizeTosReferenceRows(tosRows),
      });
      setResult(response);
      setExpandedKey(null);
      await loadStatus();
      if (saveSnapshot) await loadSnapshots();
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Data parity run failed.");
    } finally {
      setRunning(false);
    }
  }

  async function openSnapshot(runId: string) {
    setSnapshotError(null);
    try {
      setResult(await fetchDataParitySnapshot(runId));
      setExpandedKey(null);
    } catch (error) {
      setSnapshotError(error instanceof Error ? error.message : "Unable to open snapshot.");
    }
  }

  const statusBadge = statusLoading ? "loading" : schwabStatus?.token_status ?? "unknown";
  const statusTone = statusLoading ? "neutral" : verdictTone(schwabStatus?.token_status ?? schwabStatus?.status);

  return (
    <section className="dp-stack">
      <PageHeader
        title="Market Data Parity Lab"
        subtitle="Compare current MacMarket provider vs Schwab market data and derived MacMarket analytics. Read-only diagnostics only."
        actions={
          <>
            <button type="button" onClick={() => void loadStatus()} disabled={statusLoading}>
              Refresh status
            </button>
            <button type="button" onClick={() => window.location.assign("/api/admin/schwab/start")}>
              {schwabStatus?.token_status === "connected" ? "Reconnect Schwab" : "Connect Schwab"}
            </button>
          </>
        }
      />

      {statusError ? <ErrorState title="Schwab status unavailable" hint={statusError} /> : null}

      <Card title="Schwab connection">
        <div className="dp-status-grid">
          <div><span>status</span><StatusBadge tone={statusTone}>{statusBadge}</StatusBadge></div>
          <div><span>configured</span><strong>{schwabStatus?.configured ? "yes" : "no"}</strong></div>
          <div><span>credentials</span><strong>{schwabStatus?.credentials_present ? "present" : "missing"}</strong></div>
          <div><span>OAuth</span><strong>{schwabStatus?.oauth_connected ? "connected" : "not connected"}</strong></div>
          <div><span>last refresh</span><strong>{formatTimestamp(schwabStatus?.last_refresh_at)}</strong></div>
          <div><span>mode</span><strong>{schwabStatus?.mode ?? "diagnostic"}</strong></div>
        </div>
        <p className="dp-muted">{schwabStatus?.details ?? "Schwab diagnostics have not been loaded yet."}</p>
        <p className="dp-muted">{schwabStatus?.operational_impact ?? "Diagnostic market-data comparison only."}</p>
      </Card>

      <Card title="Run controls">
        <div className="dp-control-grid">
          <label className="dp-field">
            <span>Symbols</span>
            <textarea
              rows={3}
              value={symbolsText}
              onChange={(event) => setSymbolsText(event.currentTarget.value)}
            />
          </label>
          <fieldset className="dp-field dp-timeframes">
            <legend>Timeframes</legend>
            <div className="dp-checkbox-grid">
              {DATA_PARITY_TIMEFRAMES.map((timeframe) => (
                <label key={timeframe} className="dp-inline-check">
                  <input
                    type="checkbox"
                    checked={selectedTimeframes[timeframe]}
                    onChange={(event) => setSelectedTimeframes((prev) => ({ ...prev, [timeframe]: event.currentTarget.checked }))}
                  />
                  <span>{timeframe}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <label className="dp-field">
            <span>Lookback bars</span>
            <input
              type="number"
              min={5}
              max={500}
              value={lookbackBars}
              onChange={(event) => setLookbackBars(Number(event.currentTarget.value || DATA_PARITY_DEFAULT_LOOKBACK_BARS))}
            />
          </label>
          <label className="dp-field">
            <span>Session policy</span>
            <input value="regular_hours" readOnly />
          </label>
          <label className="dp-inline-check dp-save-check">
            <input
              type="checkbox"
              checked={saveSnapshot}
              onChange={(event) => setSaveSnapshot(event.currentTarget.checked)}
            />
            <span>Save snapshot</span>
          </label>
        </div>
        <div className="op-row dp-actions">
          <button type="button" onClick={() => void runComparison()} disabled={running}>
            {running ? "Running comparison..." : "Run comparison"}
          </button>
          <button
            type="button"
            disabled={!result}
            onClick={() => result && downloadText(`${result.runId}.json`, "application/json", JSON.stringify(result, null, 2))}
          >
            Export JSON
          </button>
          <button
            type="button"
            disabled={!result}
            onClick={() => result && downloadText(`${result.runId}.csv`, "text/csv", buildDataParityCsv(result))}
          >
            Export CSV
          </button>
          {runError ? <span className="dp-error-text">{runError}</span> : null}
        </div>
      </Card>

      <Card title="TOS manual reference">
        {tosRows.length === 0 ? (
          <EmptyState title="No TOS references entered" hint="Run comparisons without manual references, or add rows for screenshot-derived study values." />
        ) : null}
        <div className="dp-tos-list">
          {tosRows.map((row, index) => (
            <div key={index} className="dp-reference-grid">
              <label className="dp-field">
                <span>Symbol</span>
                <input value={row.symbol} onChange={(event) => updateTosRow(index, "symbol", event.currentTarget.value)} />
              </label>
              <label className="dp-field">
                <span>TF</span>
                <select value={row.timeframe} onChange={(event) => updateTosRow(index, "timeframe", event.currentTarget.value)}>
                  {DATA_PARITY_TIMEFRAMES.map((timeframe) => <option key={timeframe}>{timeframe}</option>)}
                </select>
              </label>
              <label className="dp-field">
                <span>True Momentum score</span>
                <input type="number" value={row.trueMomentumScore ?? ""} onChange={(event) => updateTosRow(index, "trueMomentumScore", event.currentTarget.value === "" ? null : Number(event.currentTarget.value))} />
              </label>
              <label className="dp-field">
                <span>HACO direction</span>
                <input value={row.hacoDirection ?? ""} onChange={(event) => updateTosRow(index, "hacoDirection", event.currentTarget.value)} />
              </label>
              <label className="dp-field">
                <span>HACO latest flip</span>
                <input value={row.hacoLatestFlip ?? ""} onChange={(event) => updateTosRow(index, "hacoLatestFlip", event.currentTarget.value)} />
              </label>
              <label className="dp-field">
                <span>HACOLT direction</span>
                <input value={row.hacoltDirection ?? ""} onChange={(event) => updateTosRow(index, "hacoltDirection", event.currentTarget.value)} />
              </label>
              <label className="dp-field">
                <span>Hi/Lo state</span>
                <input value={row.hiLoState ?? ""} onChange={(event) => updateTosRow(index, "hiLoState", event.currentTarget.value)} />
              </label>
              <label className="dp-field">
                <span>Hi/Lo value</span>
                <input type="number" value={row.hiLoValue ?? ""} onChange={(event) => updateTosRow(index, "hiLoValue", event.currentTarget.value === "" ? null : Number(event.currentTarget.value))} />
              </label>
              <label className="dp-field">
                <span>Squeeze state</span>
                <input value={row.squeezeState ?? ""} onChange={(event) => updateTosRow(index, "squeezeState", event.currentTarget.value)} />
              </label>
              <label className="dp-field">
                <span>Squeeze histogram</span>
                <input type="number" value={row.squeezeHistogram ?? ""} onChange={(event) => updateTosRow(index, "squeezeHistogram", event.currentTarget.value === "" ? null : Number(event.currentTarget.value))} />
              </label>
              <label className="dp-field dp-notes-field">
                <span>Notes</span>
                <input value={row.notes ?? ""} onChange={(event) => updateTosRow(index, "notes", event.currentTarget.value)} />
              </label>
              <button type="button" onClick={() => setTosRows((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}>
                Remove
              </button>
            </div>
          ))}
        </div>
        <button type="button" onClick={() => setTosRows((rows) => [...rows, createBlankTosReference()])}>
          Add TOS row
        </button>
      </Card>

      <div className="dp-summary-strip">
        {[
          ["total comparisons", "total"],
          ["matches", "match"],
          ["raw provider mismatches", "raw_provider_mismatch"],
          ["normalization mismatches", "normalization_mismatch"],
          ["indicator mismatches", "indicator_mismatch"],
          ["TOS mismatches", "tos_reference_mismatch"],
          ["insufficient/errors", "insufficient_data"],
        ].map(([label, key]) => (
          <Card key={key}>
            <div className="dp-summary-card">
              <span>{label}</span>
              <strong>{key === "insufficient_data" ? summaryValue(result, "insufficient_data") + summaryValue(result, "error") : summaryValue(result, key)}</strong>
            </div>
          </Card>
        ))}
      </div>

      <Card title="Comparison matrix">
        {!result ? (
          <EmptyState title="No comparison run yet" hint="Run a read-only parity comparison to populate the matrix." />
        ) : (
          <>
            <div className="op-row dp-run-meta">
              <StatusBadge tone="neutral">run {result.runId}</StatusBadge>
              <span>as of {formatTimestamp(result.asOf)}</span>
              <span>current provider: {formatValue(asRecord(result.providers.current).provider)}</span>
              <span>candidate: schwab</span>
            </div>
            <ResponsiveTable label="Market data parity comparison matrix">
              <table className="op-table dp-matrix">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>TF</th>
                    <th>Raw bars verdict</th>
                    <th>Canonical bars verdict</th>
                    <th>True Momentum</th>
                    <th>HACO</th>
                    <th>HACOLT</th>
                    <th>Hi/Lo</th>
                    <th>Squeeze</th>
                    <th>TOS Reference</th>
                    <th>Root Cause</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {result.results.map((item) => {
                    const key = `${item.symbol}-${item.timeframe}`;
                    const expanded = expandedKey === key;
                    return (
                      <Fragment key={key}>
                        <tr>
                          <td>{item.symbol}</td>
                          <td>{item.timeframe}</td>
                          <td><StatusBadge tone={verdictTone(comparisonVerdict(item, "rawBars"))}>{comparisonVerdict(item, "rawBars")}</StatusBadge></td>
                          <td><StatusBadge tone={verdictTone(comparisonVerdict(item, "canonicalBars"))}>{comparisonVerdict(item, "canonicalBars")}</StatusBadge></td>
                          <td><StatusBadge tone={verdictTone(componentVerdict(item, "trueMomentum"))}>{componentVerdict(item, "trueMomentum")}</StatusBadge></td>
                          <td><StatusBadge tone={verdictTone(componentVerdict(item, "haco"))}>{componentVerdict(item, "haco")}</StatusBadge></td>
                          <td><StatusBadge tone={verdictTone(componentVerdict(item, "hacolt"))}>{componentVerdict(item, "hacolt")}</StatusBadge></td>
                          <td><StatusBadge tone={verdictTone(componentVerdict(item, "hiLo"))}>{componentVerdict(item, "hiLo")}</StatusBadge></td>
                          <td><StatusBadge tone={verdictTone(componentVerdict(item, "squeeze"))}>{componentVerdict(item, "squeeze")}</StatusBadge></td>
                          <td><StatusBadge tone={verdictTone(item.tosReference?.verdict)}>{item.tosReference?.verdict ?? "-"}</StatusBadge></td>
                          <td><StatusBadge tone={rootCauseTone(item.rootCause)}>{item.rootCause}</StatusBadge></td>
                          <td>
                            <button
                              type="button"
                              aria-expanded={expanded}
                              onClick={() => setExpandedKey(expanded ? null : key)}
                            >
                              {expanded ? "Hide" : "Show"}
                            </button>
                          </td>
                        </tr>
                        {expanded ? (
                          <tr className="dp-detail-row">
                            <td colSpan={12}>
                              <div className="dp-detail-grid">
                                <ComparisonDetail title="Raw provider bars" comparison={item.rawBars} />
                                <ComparisonDetail title="Canonical MacMarket bars" comparison={item.canonicalBars} />
                                <JsonBlock label="Indicator payload comparison" value={item.indicators} />
                                <JsonBlock label="TOS reference comparison" value={item.tosReference} />
                                <JsonBlock label="Warnings and errors" value={{ warnings: item.warnings, errors: item.errors }} />
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </ResponsiveTable>
          </>
        )}
      </Card>

      <Card title="Snapshot history">
        {snapshotError ? <ErrorState title="Snapshots unavailable" hint={snapshotError} /> : null}
        {snapshots.length === 0 ? (
          <EmptyState title="No saved snapshots" hint="Saved parity runs will appear here for read-only review." />
        ) : (
          <ResponsiveTable label="Saved data parity snapshots">
            <table className="op-table dp-snapshots">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Created</th>
                  <th>Providers</th>
                  <th>Symbols</th>
                  <th>Timeframes</th>
                  <th>Matches</th>
                  <th>Open</th>
                </tr>
              </thead>
              <tbody>
                {snapshots.map((snapshot) => (
                  <tr key={snapshot.runId}>
                    <td>{snapshot.runId}</td>
                    <td>{formatTimestamp(snapshot.createdAt)}</td>
                    <td>{snapshot.providerCurrent} vs {snapshot.providerCandidate}</td>
                    <td>{snapshot.symbols.join(", ")}</td>
                    <td>{snapshot.timeframes.join(", ")}</td>
                    <td>{snapshot.summary.match ?? 0}</td>
                    <td><button type="button" onClick={() => void openSnapshot(snapshot.runId)}>Open</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ResponsiveTable>
        )}
      </Card>
    </section>
  );
}
