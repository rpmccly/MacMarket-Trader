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

const TRUE_MISMATCH_VERDICTS = new Set([
  "comparable_raw_mismatch",
  "comparable_normalized_mismatch",
  "comparable_indicator_mismatch",
  "tos_reference_mismatch",
]);
const NOT_COMPARABLE_VERDICTS = new Set([
  "provider_unavailable",
  "auth_unavailable",
  "no_bars",
  "insufficient_data",
  "stale_source",
  "no_aligned_bars",
]);

function verdictTone(value: string | undefined | null): BadgeTone {
  switch (String(value ?? "").toLowerCase()) {
    case "match":
    case "ok":
    case "connected":
    case "real_time_like":
      return "good";
    case "not_compared":
    case "not_provided":
    case "unavailable":
    case "configured":
    case "no_bars":
    case "no_aligned_bars":
      return "neutral";
    case "insufficient_data":
    case "expired":
    case "reconnect_required":
    case "auth_unavailable":
    case "stale_source":
    case "provider_unavailable":
    case "delayed_15_min_like":
    case "stale":
      return "warn";
    case "comparable_raw_mismatch":
    case "comparable_normalized_mismatch":
    case "comparable_indicator_mismatch":
    case "error":
    case "degraded":
      return "bad";
    default:
      return "neutral";
  }
}

function rootCauseTone(value: string): BadgeTone {
  if (value === "match") return "good";
  if (TRUE_MISMATCH_VERDICTS.has(value)) return "bad";
  if (NOT_COMPARABLE_VERDICTS.has(value)) return "warn";
  return value === "error" ? "bad" : "neutral";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function formatDataParityValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "object") {
    const record = asRecord(value);
    for (const key of ["message", "error", "detail", "details", "reason", "status", "verdict"]) {
      const candidate = record[key];
      if (typeof candidate === "string" && candidate.trim()) return candidate;
    }
    try {
      const text = JSON.stringify(value);
      return text.length > 240 ? `${text.slice(0, 237)}...` : text;
    } catch {
      return "unavailable diagnostic object";
    }
  }
  return String(value);
}

function formatValue(value: unknown): string {
  return formatDataParityValue(value);
}

function formatTimestampInZone(value: unknown, timeZone: "UTC" | "America/New_York"): string {
  if (!value) return "-";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

function formatTimestamp(value: unknown): string {
  if (!value) return "-";
  const record = asRecord(value);
  if (Object.keys(record).length > 0 && !record.utc && !record.new_york) return "-";
  const utcValue = record.utc ?? value;
  const newYorkValue = record.new_york ?? utcValue;
  const session = record.market_session_state ? ` (${String(record.market_session_state)})` : "";
  return `${formatTimestampInZone(utcValue, "UTC")} / ${formatTimestampInZone(newYorkValue, "America/New_York")}${session}`;
}

function formatProviderLabel(value: unknown, fallback = "Polygon/Massive"): string {
  const text = String(value ?? "").trim();
  if (!text || text === "not run" || text === "unknown") return fallback;
  if (text === "polygon_legacy") return "Legacy Polygon/Massive";
  if (text === "schwab_primary") return "Schwab primary";
  if (text === "schwab") return "Schwab/Thinkorswim";
  return text;
}

function freshnessRecord(result: DataParityResult): Record<string, unknown> {
  return asRecord(result.freshness ?? asRecord(result.canonicalBars).freshness ?? asRecord(result.rawBars).freshness);
}

function providerFreshnessRecord(result: DataParityResult): Record<string, unknown> {
  return asRecord(asRecord(result.rawBars).freshness ?? freshnessRecord(result));
}

function canonicalFreshnessRecord(result: DataParityResult): Record<string, unknown> {
  return asRecord(asRecord(result.canonicalBars).freshness ?? freshnessRecord(result));
}

function providerFreshness(result: DataParityResult, side: "current" | "candidate"): Record<string, unknown> {
  return asRecord(providerFreshnessRecord(result)[side]);
}

function providerAsOf(result: DataParityResult, side: "current" | "candidate"): string {
  const rawFreshness = providerFreshnessRecord(result);
  const inputKey = side === "current" ? "latest_input_bar_timestamp_current" : "latest_input_bar_timestamp_candidate";
  const inputTimestamp = asRecord(rawFreshness[inputKey]);
  if (inputTimestamp.utc || inputTimestamp.new_york) return formatTimestamp(inputTimestamp);
  return formatTimestamp(asRecord(providerFreshness(result, side).latest_bar_timestamp));
}

function providerLagVsExpected(result: DataParityResult, side: "current" | "candidate"): string {
  return formatValue(providerFreshness(result, side).provider_lag_minutes_vs_expected_latest_market_bar);
}

function providerLagVsServer(result: DataParityResult, side: "current" | "candidate"): string {
  return formatValue(providerFreshness(result, side).provider_lag_minutes_vs_server_run_time);
}

function providerClassification(result: DataParityResult, side: "current" | "candidate"): string {
  return String(providerFreshness(result, side).classification ?? "-");
}

function timestampDeltaMinutes(result: DataParityResult): string {
  return formatValue(providerFreshnessRecord(result).timestamp_delta_minutes);
}

function alignedLatestTimestamp(result: DataParityResult): string {
  const canonical = asRecord(result.canonicalBars);
  const alignmentLabel = canonical.latest_common_alignment_label;
  const alignmentMode = canonical.alignment_mode;
  if (alignmentLabel && alignmentMode && alignmentMode !== "exact_timestamp") {
    return `${formatValue(alignmentLabel)} (${formatValue(alignmentMode)})`;
  }
  const payload = asRecord(canonicalFreshnessRecord(result).latest_common_aligned_timestamp);
  if (payload.utc || payload.new_york) return formatTimestamp(payload);
  return formatTimestamp(canonical.latest_common_timestamp);
}

function verdictReason(result: DataParityResult): string {
  return String(canonicalFreshnessRecord(result).verdict_reason ?? asRecord(result.canonicalBars).verdict_reason ?? asRecord(result.rawBars).verdict_reason ?? result.rootCause);
}

function countProviderClassifications(response: DataParityRunResponse | null, side: "current" | "candidate"): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of response?.results ?? []) {
    const classification = providerClassification(item, side);
    if (classification === "-") continue;
    counts[classification] = (counts[classification] ?? 0) + 1;
  }
  return counts;
}

function formatClassificationCounts(counts: Record<string, number>): string {
  const entries = Object.entries(counts);
  if (!entries.length) return "-";
  return entries.map(([label, count]) => `${label}: ${count}`).join(", ");
}

export function cleanDataParityErrorMessage(error: string | null | undefined, fallback: string): string {
  const message = String(error ?? "").trim();
  if (!message) return fallback;
  const lower = message.slice(0, 512).toLowerCase();
  if (
    lower.includes("<!doctype html") ||
    lower.includes("<html") ||
    lower.includes("<body") ||
    lower.includes("<head") ||
    lower.includes("<script")
  ) {
    return fallback;
  }
  return message;
}

export function isSchwabConnected(status: SchwabStatus | null): boolean {
  return Boolean(status?.configured && status.credentials_present && status.oauth_connected && status.token_status === "connected");
}

export function shouldShowSchwabReconnect(status: SchwabStatus | null): boolean {
  if (!status) return false;
  return Boolean(status.requires_reconnect || !isSchwabConnected(status));
}

function summaryValue(response: DataParityRunResponse | null, key: string): number {
  return Number(response?.summary?.[key] ?? 0);
}

function comparisonVerdict(result: DataParityResult, key: "rawBars" | "canonicalBars"): string {
  return String(asRecord(result[key])["verdict"] ?? "-");
}

function componentVerdict(result: DataParityResult, component: keyof typeof COMPONENT_FIELDS): string {
  const indicators = asRecord(result.indicators);
  if (indicators.verdict === "not_compared") return "not_compared";
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

function latestCommonClose(comparison: unknown, side: "latest_common_current" | "latest_common_candidate"): string {
  return formatValue(asRecord(asRecord(comparison)[side]).close);
}

function latestDelta(comparison: unknown, field: string): string {
  return formatValue(asRecord(asRecord(comparison).latest_delta)[field]);
}

function priceTolerance(comparison: unknown): string {
  const record = asRecord(comparison);
  return `${formatValue(record.price_absolute_tolerance)} abs / ${formatValue(record.price_relative_tolerance)} rel`;
}

function countResults(response: DataParityRunResponse | null, predicate: (item: DataParityResult) => boolean): number {
  return response?.results.filter(predicate).length ?? 0;
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
  const freshness = asRecord(record.freshness);
  const currentFreshness = asRecord(freshness.current);
  const candidateFreshness = asRecord(freshness.candidate);
  const diagnostics = asRecord(record.comparison_diagnostics);
  const diagnosticNotes = Array.isArray(diagnostics.notes) ? diagnostics.notes.map(formatValue).join(", ") : formatValue(diagnostics.notes);
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
        <span>latest common timestamp</span><strong>{formatTimestamp(record.latest_common_timestamp)}</strong>
        <span>alignment mode</span><strong>{formatValue(record.alignment_mode)}</strong>
        <span>comparison scope</span><strong>{formatValue(record.comparison_scope)}</strong>
        <span>latest alignment label</span><strong>{formatValue(record.latest_common_alignment_label)}</strong>
        <span>current common raw timestamp</span><strong>{formatTimestamp(record.latest_common_current_raw_timestamp)}</strong>
        <span>Schwab common raw timestamp</span><strong>{formatTimestamp(record.latest_common_candidate_raw_timestamp)}</strong>
        <span>current latest returned</span><strong>{formatTimestamp(record.latest_input_current_raw_timestamp)}</strong>
        <span>Schwab latest returned</span><strong>{formatTimestamp(record.latest_input_candidate_raw_timestamp)}</strong>
        <span>latest alignment match</span><strong>{formatValue(record.latest_alignment_key_match)}</strong>
        <span>alignment failure</span><strong>{formatValue(record.alignment_failure_reason)}</strong>
        <span>current in-progress filtered</span><strong>{formatValue(record.filtered_in_progress_current_count)}</strong>
        <span>Schwab in-progress filtered</span><strong>{formatValue(record.filtered_in_progress_candidate_count)}</strong>
        <span>current as-of</span><strong>{formatTimestamp(asRecord(currentFreshness.latest_bar_timestamp))}</strong>
        <span>Schwab as-of</span><strong>{formatTimestamp(asRecord(candidateFreshness.latest_bar_timestamp))}</strong>
        <span>market session</span><strong>{formatValue(freshness.market_session_state)}</strong>
        <span>expected latest bar</span><strong>{formatTimestamp(asRecord(freshness.expected_latest_market_bar))}</strong>
        <span>current lag vs server</span><strong>{formatValue(currentFreshness.provider_lag_minutes_vs_server_run_time)} min</strong>
        <span>Schwab lag vs server</span><strong>{formatValue(candidateFreshness.provider_lag_minutes_vs_server_run_time)} min</strong>
        <span>current lag vs expected</span><strong>{formatValue(currentFreshness.provider_lag_minutes_vs_expected_latest_market_bar)} min</strong>
        <span>Schwab lag vs expected</span><strong>{formatValue(candidateFreshness.provider_lag_minutes_vs_expected_latest_market_bar)} min</strong>
        <span>freshness classification</span><strong>{formatValue(freshness.classification)}</strong>
        <span>verdict reason</span><strong>{formatValue(record.verdict_reason ?? freshness.verdict_reason)}</strong>
        <span>latest common close delta</span><strong>{latestDelta(record, "close")}</strong>
        <span>price tolerance</span><strong>{priceTolerance(record)}</strong>
        <span>max price delta</span><strong>{formatValue(record.max_price_delta)}</strong>
        <span>max volume delta</span><strong>{formatValue(record.max_volume_delta)}</strong>
        <span>latest timestamp match</span><strong>{formatValue(record.latest_timestamp_match)}</strong>
        <span>as-of delta seconds</span><strong>{formatValue(record.latest_timestamp_delta_seconds)}</strong>
        <span>as-of tolerance seconds</span><strong>{formatValue(record.latest_timestamp_tolerance_seconds)}</strong>
        <span>current first</span><strong>{formatTimestamp(record.first_timestamp_current)}</strong>
        <span>Schwab first</span><strong>{formatTimestamp(record.first_timestamp_candidate)}</strong>
        <span>current last</span><strong>{formatTimestamp(record.last_timestamp_current)}</strong>
        <span>Schwab last</span><strong>{formatTimestamp(record.last_timestamp_candidate)}</strong>
        <span>missing on current</span><strong>{formatValue(record.missing_timestamps_current_count)}</strong>
        <span>extra on current</span><strong>{formatValue(record.extra_timestamps_current_count)}</strong>
        <span>current source</span><strong>{formatValue(currentMeta.provider)}</strong>
        <span>Schwab source</span><strong>{formatValue(candidateMeta.provider)}</strong>
        <span>session policy</span><strong>{formatValue(candidateMeta.session_policy ?? currentMeta.session_policy)}</strong>
        <span>current timestamp convention</span><strong>{formatValue(asRecord(record.latest_current_alignment).timestamp_convention)}</strong>
        <span>Schwab timestamp convention</span><strong>{formatValue(asRecord(record.latest_candidate_alignment).timestamp_convention)}</strong>
        <span>current interval start</span><strong>{formatTimestamp(asRecord(asRecord(record.latest_current_alignment).canonical_interval_start))}</strong>
        <span>current interval end</span><strong>{formatTimestamp(asRecord(asRecord(record.latest_current_alignment).canonical_interval_end))}</strong>
        <span>Schwab interval start</span><strong>{formatTimestamp(asRecord(asRecord(record.latest_candidate_alignment).canonical_interval_start))}</strong>
        <span>Schwab interval end</span><strong>{formatTimestamp(asRecord(asRecord(record.latest_candidate_alignment).canonical_interval_end))}</strong>
        <span>diagnostic notes</span><strong>{diagnosticNotes}</strong>
      </div>
    </section>
  );
}

function SideBySideBarsTable({ title, comparison }: { title: string; comparison: unknown }) {
  const comparisonRecord = asRecord(comparison);
  const rows = Array.isArray(comparisonRecord.aligned_rows) ? (comparisonRecord.aligned_rows as unknown[]) : [];
  if (!rows.length) {
    return (
      <section className="dp-detail-section">
        <strong>{title}</strong>
        <p className="dp-muted">No aligned bars are available for side-by-side display.</p>
      </section>
    );
  }
  return (
    <section className="dp-detail-section dp-wide-detail">
      <strong>{title}</strong>
      <ResponsiveTable label={title}>
        <table className="op-table dp-bars-table">
          <thead>
            <tr>
              <th>Alignment</th>
              <th>Interval start</th>
              <th>Interval end</th>
              <th>Current timestamp</th>
              <th>Schwab timestamp</th>
              <th>Timestamp convention</th>
              <th>Completed</th>
              <th>Current provider O/H/L/C/V</th>
              <th>Schwab O/H/L/C/V</th>
              <th>Close delta</th>
              <th>Volume delta</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const record = asRecord(row);
              const current = asRecord(record.current);
              const candidate = asRecord(record.candidate);
              const deltas = asRecord(record.deltas);
              return (
                <tr key={`${String(record.alignment_key ?? record.timestamp)}-${index}`}>
                  <td>{formatValue(record.alignment_label ?? record.alignment_key)}</td>
                  <td>{formatTimestamp(asRecord(record.canonical_interval_start))}</td>
                  <td>{formatTimestamp(asRecord(record.canonical_interval_end))}</td>
                  <td>{formatTimestamp(record.current_raw_provider_timestamp ?? record.timestamp)}</td>
                  <td>{formatTimestamp(record.candidate_raw_provider_timestamp)}</td>
                  <td>{formatValue(record.current_timestamp_convention)} / {formatValue(record.candidate_timestamp_convention)}</td>
                  <td>{formatValue(record.current_bar_completed)} / {formatValue(record.candidate_bar_completed)}</td>
                  <td>{[current.open, current.high, current.low, current.close, current.volume].map(formatValue).join(" / ")}</td>
                  <td>{[candidate.open, candidate.high, candidate.low, candidate.close, candidate.volume].map(formatValue).join(" / ")}</td>
                  <td>{formatValue(deltas.close)}</td>
                  <td>{formatValue(deltas.volume)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </ResponsiveTable>
    </section>
  );
}

function IndicatorSideBySideTable({ comparison }: { comparison: unknown }) {
  const record = asRecord(comparison);
  const rows = Array.isArray(record.rows) ? record.rows as unknown[] : [];
  const inputAlignment = asRecord(record.indicator_input_alignment);
  return (
    <section className="dp-detail-section dp-wide-detail">
      <div className="dp-detail-title">
        <strong>Indicator side-by-side</strong>
        <StatusBadge tone={verdictTone(String(record.verdict ?? ""))}>{formatValue(record.verdict)}</StatusBadge>
      </div>
      {Object.keys(inputAlignment).length ? (
        <p className="dp-muted">
          Indicator input alignment: {formatValue(inputAlignment.mode)}; normalized: {formatValue(inputAlignment.normalized)}; latest label: {formatValue(inputAlignment.latest_common_alignment_label)}.
        </p>
      ) : null}
      {!rows.length ? (
        <p className="dp-muted">Indicators were not compared: {formatValue(record.not_comparable_reason ?? "no comparable indicator rows")}.</p>
      ) : (
        <ResponsiveTable label="Indicator side-by-side comparison">
          <table className="op-table dp-indicator-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Current provider</th>
                <th>Schwab</th>
                <th>Delta</th>
                <th>Tolerance</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const item = asRecord(row);
                return (
                  <tr key={String(item.field)}>
                    <td>{formatValue(item.field)}</td>
                    <td>{formatValue(item.current)}</td>
                    <td>{formatValue(item.candidate)}</td>
                    <td>{formatValue(item.delta)}</td>
                    <td>{formatValue(item.tolerance)}</td>
                    <td><StatusBadge tone={verdictTone(String(item.verdict ?? ""))}>{formatValue(item.verdict)}</StatusBadge></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </ResponsiveTable>
      )}
    </section>
  );
}

function FreshnessDelaySection({ result }: { result: DataParityRunResponse | null }) {
  const currentCounts = countProviderClassifications(result, "current");
  const schwabCounts = countProviderClassifications(result, "candidate");
  const firstFreshness = result?.results[0] ? freshnessRecord(result.results[0]) : {};
  const currentProviderName = formatProviderLabel(asRecord(result?.providers.current).provider);
  const staleOrDelayedRows = result?.results.filter((item) => {
    const currentClass = providerClassification(item, "current");
    const candidateClass = providerClassification(item, "candidate");
    return [currentClass, candidateClass].some((value) => value === "delayed_15_min_like" || value === "stale" || value === "not_comparable");
  }).length ?? 0;

  return (
    <Card title="Freshness / Delay">
      {!result ? (
        <EmptyState title="No freshness run yet" hint="Run a comparison to measure provider timestamps against the server run time and expected latest market bar." />
      ) : (
        <>
          <div className="dp-status-grid dp-freshness-grid">
            <div><span>server run time</span><strong>{formatTimestamp(result.asOf)}</strong></div>
            <div><span>market session</span><strong>{formatValue(firstFreshness.market_session_state)}</strong></div>
            <div><span>{currentProviderName} classes</span><strong>{formatClassificationCounts(currentCounts)}</strong></div>
            <div><span>Schwab classes</span><strong>{formatClassificationCounts(schwabCounts)}</strong></div>
            <div><span>delayed/stale/not comparable rows</span><strong>{staleOrDelayedRows}</strong></div>
            <div><span>basis</span><strong>{formatValue(firstFreshness.delay_measurement_basis)}</strong></div>
          </div>
          <ResponsiveTable label="Provider freshness and delay by comparison row">
            <table className="op-table dp-freshness-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>TF</th>
                  <th>Expected latest market bar</th>
                  <th>{currentProviderName} asOf</th>
                  <th>{currentProviderName} lag vs server</th>
                  <th>{currentProviderName} lag vs expected</th>
                  <th>{currentProviderName} class</th>
                  <th>Schwab asOf</th>
                  <th>Schwab lag vs server</th>
                  <th>Schwab lag vs expected</th>
                  <th>Schwab class</th>
                  <th>Timestamp delta</th>
                  <th>Aligned latest</th>
                  <th>Verdict reason</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((item) => {
                  const freshness = freshnessRecord(item);
                  return (
                    <tr key={`${item.symbol}-${item.timeframe}-freshness`}>
                      <td>{item.symbol}</td>
                      <td>{item.timeframe}</td>
                      <td>{formatTimestamp(asRecord(freshness.expected_latest_market_bar))}</td>
                      <td>{providerAsOf(item, "current")}</td>
                      <td>{providerLagVsServer(item, "current")} min</td>
                      <td>{providerLagVsExpected(item, "current")} min</td>
                      <td><StatusBadge tone={verdictTone(providerClassification(item, "current"))}>{providerClassification(item, "current")}</StatusBadge></td>
                      <td>{providerAsOf(item, "candidate")}</td>
                      <td>{providerLagVsServer(item, "candidate")} min</td>
                      <td>{providerLagVsExpected(item, "candidate")} min</td>
                      <td><StatusBadge tone={verdictTone(providerClassification(item, "candidate"))}>{providerClassification(item, "candidate")}</StatusBadge></td>
                      <td>{timestampDeltaMinutes(item)} min</td>
                      <td>{alignedLatestTimestamp(item)}</td>
                      <td>{verdictReason(item)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </ResponsiveTable>
        </>
      )}
    </Card>
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
  const [completedBarsOnly, setCompletedBarsOnly] = useState(true);
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
      setStatusError(cleanDataParityErrorMessage(error instanceof Error ? error.message : null, "Unable to load Schwab status."));
    } finally {
      setStatusLoading(false);
    }
  }

  async function loadSnapshots() {
    setSnapshotError(null);
    try {
      setSnapshots(await fetchDataParitySnapshots());
    } catch (error) {
      setSnapshotError(cleanDataParityErrorMessage(error instanceof Error ? error.message : null, "Unable to load snapshots."));
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
        completedBarsOnly,
        saveSnapshot,
        tosReferences: normalizeTosReferenceRows(tosRows),
      });
      setResult(response);
      setExpandedKey(null);
      await loadStatus();
      if (saveSnapshot) await loadSnapshots();
    } catch (error) {
      setRunError(cleanDataParityErrorMessage(error instanceof Error ? error.message : null, "Data parity run failed."));
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
      setSnapshotError(cleanDataParityErrorMessage(error instanceof Error ? error.message : null, "Unable to open snapshot."));
    }
  }

  const schwabConnected = isSchwabConnected(schwabStatus);
  const statusBadge = statusLoading ? "loading" : schwabConnected ? "Connected" : schwabStatus?.token_status ?? "unknown";
  const statusTone = statusLoading ? "neutral" : schwabConnected ? "good" : verdictTone(schwabStatus?.token_status ?? schwabStatus?.status);
  const currentProviderName = String(asRecord(result?.providers.current).provider ?? "not run");
  const providerAName = formatProviderLabel(currentProviderName);
  const comparisonMode = String(result?.comparisonMode ?? asRecord(result?.providers.current).comparison_mode ?? "not_run");
  const noLegacyComparison = comparisonMode === "schwab_primary_no_legacy";
  const trueMismatchCount = countResults(result, (item) => TRUE_MISMATCH_VERDICTS.has(item.rootCause));
  const notComparableCount = countResults(result, (item) => NOT_COMPARABLE_VERDICTS.has(item.rootCause));
  const comparableCount = countResults(result, (item) => !NOT_COMPARABLE_VERDICTS.has(item.rootCause));

  return (
    <section className="dp-stack">
      <PageHeader
        title="Market Data Parity Lab"
        subtitle="Compare the active or legacy market-data provider against Schwab/Thinkorswim bars and derived MacMarket analytics. Read-only diagnostics only."
        actions={
          <>
            <button type="button" className="op-btn op-btn-primary" onClick={() => void loadStatus()} disabled={statusLoading}>
              Refresh Schwab status
            </button>
            {shouldShowSchwabReconnect(schwabStatus) ? (
              <button type="button" onClick={() => window.location.assign("/api/admin/schwab/start")}>
                {schwabStatus?.oauth_connected ? "Reconnect Schwab" : "Connect Schwab"}
              </button>
            ) : null}
          </>
        }
      />

      {statusError ? <ErrorState title="Schwab status unavailable" hint={statusError} /> : null}

      <Card title="Schwab connection">
        <div className="dp-status-grid">
          <div><span>status</span><StatusBadge tone={statusTone}>{statusBadge}</StatusBadge></div>
          <div><span>configured</span><strong>{schwabStatus?.configured ? "yes" : "no"}</strong></div>
          <div><span>credentials</span><strong>{schwabStatus?.credentials_present ? "present" : "missing"}</strong></div>
          <div><span>OAuth/token</span><strong>{schwabConnected ? "usable" : schwabStatus?.token_status ?? "unknown"}</strong></div>
          <div><span>access state</span><strong>{schwabStatus?.access_state ?? "-"}</strong></div>
          <div><span>refresh state</span><strong>{schwabStatus?.refresh_state ?? "-"}</strong></div>
          <div><span>last refresh</span><strong>{formatTimestamp(schwabStatus?.last_refresh_at)}</strong></div>
          <div><span>mode</span><strong>{schwabStatus?.mode ?? "diagnostic"}</strong></div>
        </div>
        <p className="dp-muted">{schwabStatus?.details ?? "Schwab diagnostics have not been loaded yet."}</p>
        <p className="dp-muted">Diagnostic pulls use the stored backend OAuth token while usable; browser code never receives Schwab tokens or secrets.</p>
        <p className="dp-muted">{schwabStatus?.operational_impact ?? "Diagnostic market-data comparison only."}</p>
      </Card>

      {noLegacyComparison ? (
        <Card title="Comparison mode">
          <EmptyState
            title="Schwab is already primary"
            hint="No legacy Polygon/Massive API key is configured, so there is no useful legacy-vs-Schwab comparison target. Saved historical snapshots remain available below."
          />
        </Card>
      ) : result?.warnings?.length ? (
        <Card title="Comparison mode">
          <div className="dp-status-grid">
            <div><span>mode</span><strong>{formatValue(comparisonMode)}</strong></div>
            <div><span>provider A</span><strong>{providerAName}</strong></div>
            <div><span>provider B</span><strong>Schwab/Thinkorswim</strong></div>
          </div>
          {result.warnings.map((warning) => (
            <p key={warning} className="dp-muted">{warning}</p>
          ))}
        </Card>
      ) : null}

      <div className="dp-summary-strip dp-cockpit-strip">
        {[
          ["Schwab status", statusBadge],
          ["Current provider", providerAName],
          ["Comparison mode", comparisonMode === "not_run" ? "-" : comparisonMode],
          ["Symbols", parseParitySymbols(symbolsText).join(", ") || "-"],
          ["Timeframes", selectedTfList.join(", ") || "-"],
          ["Comparable rows", comparableCount],
          ["True mismatches", trueMismatchCount],
          ["Not comparable", notComparableCount],
          ["Last run", result ? formatTimestamp(result.asOf) : "-"],
        ].map(([label, value]) => (
          <Card key={String(label)}>
            <div className="dp-summary-card">
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          </Card>
        ))}
      </div>

      <FreshnessDelaySection result={result} />

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
              checked={completedBarsOnly}
              onChange={(event) => setCompletedBarsOnly(event.currentTarget.checked)}
            />
            <span>Completed bars only</span>
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
          ["raw mismatches", "comparable_raw_mismatch"],
          ["normalization mismatches", "comparable_normalized_mismatch"],
          ["indicator mismatches", "comparable_indicator_mismatch"],
          ["TOS mismatches", "tos_reference_mismatch"],
          ["not comparable", "not_comparable"],
        ].map(([label, key]) => (
          <Card key={key}>
            <div className="dp-summary-card">
              <span>{label}</span>
              <strong>{key === "not_comparable" ? notComparableCount : summaryValue(result, key)}</strong>
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
                    <th>{providerAName} asOf</th>
                    <th>Schwab asOf</th>
                    <th>Timestamp delta</th>
                    <th>Aligned latest</th>
                    <th>Raw A close</th>
                    <th>Raw B close</th>
                    <th>Raw delta / tolerance</th>
                    <th>Raw verdict</th>
                    <th>Canonical A close</th>
                    <th>Canonical B close</th>
                    <th>Canonical delta / tolerance</th>
                    <th>Canonical verdict</th>
                    <th>Indicators</th>
                    <th>TOS Reference</th>
                    <th>Root Cause</th>
                    <th>Verdict reason</th>
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
                          <td>{providerAsOf(item, "current")}</td>
                          <td>{providerAsOf(item, "candidate")}</td>
                          <td>{timestampDeltaMinutes(item)} min</td>
                          <td>{alignedLatestTimestamp(item)}</td>
                          <td>{latestCommonClose(item.rawBars, "latest_common_current")}</td>
                          <td>{latestCommonClose(item.rawBars, "latest_common_candidate")}</td>
                          <td>{latestDelta(item.rawBars, "close")} / {priceTolerance(item.rawBars)}</td>
                          <td><StatusBadge tone={verdictTone(comparisonVerdict(item, "rawBars"))}>{comparisonVerdict(item, "rawBars")}</StatusBadge></td>
                          <td>{latestCommonClose(item.canonicalBars, "latest_common_current")}</td>
                          <td>{latestCommonClose(item.canonicalBars, "latest_common_candidate")}</td>
                          <td>{latestDelta(item.canonicalBars, "close")} / {priceTolerance(item.canonicalBars)}</td>
                          <td><StatusBadge tone={verdictTone(comparisonVerdict(item, "canonicalBars"))}>{comparisonVerdict(item, "canonicalBars")}</StatusBadge></td>
                          <td><StatusBadge tone={verdictTone(String(asRecord(item.indicators).verdict ?? ""))}>{formatValue(asRecord(item.indicators).verdict)}</StatusBadge></td>
                          <td><StatusBadge tone={verdictTone(item.tosReference?.verdict)}>{item.tosReference?.verdict ?? "-"}</StatusBadge></td>
                          <td><StatusBadge tone={rootCauseTone(item.rootCause)}>{item.rootCause}</StatusBadge></td>
                          <td>{verdictReason(item)}</td>
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
                            <td colSpan={19}>
                              <div className="dp-detail-grid">
                                {item.rootCause === "stale_source" ? (
                                  <section className="dp-stale-callout dp-wide-detail">
                                    <strong>Stale/as-of mismatch</strong>
                                    <p>Latest provider timestamps differ beyond tolerance, so indicators are not treated as comparable for this row.</p>
                                  </section>
                                ) : null}
                                <ComparisonDetail title="Raw provider bars" comparison={item.rawBars} />
                                <ComparisonDetail title="Canonical MacMarket bars" comparison={item.canonicalBars} />
                                <SideBySideBarsTable title="Raw aligned bars" comparison={item.rawBars} />
                                <SideBySideBarsTable title="Canonical aligned bars" comparison={item.canonicalBars} />
                                <IndicatorSideBySideTable comparison={item.indicators} />
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
