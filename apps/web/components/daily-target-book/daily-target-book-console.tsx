"use client";

import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Card, EmptyState, ErrorState, InlineFeedback, PageHeader, ResponsiveTable, StatusBadge } from "@/components/operator-ui";
import {
  buildDailyTargetBook,
  fetchDailyTargetBookLatest,
  type DailyTargetBookResult,
  type DailyTargetBookSlot,
} from "@/lib/daily-target-book-api";

const defaultSymbols = ["SPY", "QQQ", "MTUM"];
const actionTone: Record<string, "good" | "warn" | "bad" | "neutral"> = {
  KEEP_REVIEW: "good",
  EXIT_REVIEW: "warn",
  OPEN_REVIEW: "good",
  REPLACE_REVIEW: "warn",
  SCALE_REVIEW: "warn",
  CASH_NO_TRADE: "neutral",
};

function asText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (Array.isArray(value)) return value.length ? value.map(asText).join(", ") : "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function asNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const moneyFormatter = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const numberFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

function formatMoney(value: unknown): string {
  const parsed = asNumber(value);
  return parsed === null ? "-" : moneyFormatter.format(parsed);
}

function formatPrice(value: unknown): string {
  const parsed = asNumber(value);
  return parsed === null ? "-" : parsed.toFixed(2);
}

function formatQty(value: unknown): string {
  const parsed = asNumber(value);
  return parsed === null ? "-" : numberFormatter.format(parsed);
}

function formatScore(value: unknown): string {
  const parsed = asNumber(value);
  return parsed === null ? "-" : parsed.toFixed(3);
}

function formatPercent(value: unknown): string {
  const parsed = asNumber(value);
  return parsed === null ? "-" : `${parsed.toFixed(2)}%`;
}

function actionLabel(action: string): string {
  return action
    .replace("KEEP_REVIEW", "keep review")
    .replace("EXIT_REVIEW", "exit review")
    .replace("OPEN_REVIEW", "open review")
    .replace("REPLACE_REVIEW", "replace review")
    .replace("SCALE_REVIEW", "scale review")
    .replace("CASH_NO_TRADE", "cash/no trade");
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: string | number; tone?: "good" | "warn" | "bad" | "neutral" }) {
  return (
    <div className={`agent-metric agent-metric-${tone}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function SlotActionBadge({ action }: { action: string }) {
  return <StatusBadge tone={actionTone[action] ?? "neutral"}>{actionLabel(action)}</StatusBadge>;
}

function getBest(group: Record<string, unknown>): Record<string, unknown> {
  const best = group.best;
  return best && typeof best === "object" && !Array.isArray(best) ? (best as Record<string, unknown>) : {};
}

export function dailyTargetBookErrorMessage(error: string | null | undefined, fallback: string): string {
  const message = (error ?? "").trim();
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

export function DailyTargetBookConsole() {
  const [result, setResult] = useState<DailyTargetBookResult | null>(null);
  const [symbolsText, setSymbolsText] = useState(defaultSymbols.join(", "));
  const [universeSource, setUniverseSource] = useState("manual");
  const [scanDepth, setScanDepth] = useState(12);
  const [includeExistingPositions, setIncludeExistingPositions] = useState(true);
  const [includeReplacementReviews, setIncludeReplacementReviews] = useState(true);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [feedback, setFeedback] = useState<{ state: "idle" | "loading" | "success" | "error"; message?: string }>({ state: "idle" });

  const load = useCallback(async () => {
    setLoadState("loading");
    const response = await fetchDailyTargetBookLatest();
    if (!response.ok || !response.data) {
      setLoadState("error");
      setFeedback({
        state: "error",
        message: dailyTargetBookErrorMessage(response.error, "Daily Target Book is unavailable."),
      });
      return;
    }
    setSymbolsText((response.data.defaults?.symbols ?? defaultSymbols).join(", "));
    setScanDepth(response.data.defaults?.scanDepth ?? 12);
    setUniverseSource(response.data.defaults?.universeSource ?? "manual");
    setIncludeExistingPositions(response.data.defaults?.includeExistingPositions ?? true);
    setIncludeReplacementReviews(response.data.defaults?.includeReplacementReviews ?? true);
    setResult(response.data.latest ?? null);
    setLoadState("ready");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const parsedSymbols = useMemo(
    () => symbolsText.split(/[,\s]+/).map((item) => item.trim().toUpperCase()).filter(Boolean),
    [symbolsText],
  );

  const targetSymbols = useMemo(
    () => new Set((result?.targetBook ?? []).map((slot) => String(slot.symbol ?? "").toUpperCase()).filter(Boolean)),
    [result?.targetBook],
  );
  const currentSymbols = useMemo(
    () => new Set((result?.currentPaperBook ?? []).map((row) => String(row.symbol ?? "").toUpperCase()).filter(Boolean)),
    [result?.currentPaperBook],
  );
  const currentOnly = useMemo(() => Array.from(currentSymbols).filter((symbol) => !targetSymbols.has(symbol)), [currentSymbols, targetSymbols]);
  const targetOnly = useMemo(() => Array.from(targetSymbols).filter((symbol) => !currentSymbols.has(symbol)), [currentSymbols, targetSymbols]);

  async function buildBook() {
    setFeedback({ state: "loading", message: "Building read-only target book." });
    const response = await buildDailyTargetBook({
      universeSource,
      symbols: parsedSymbols,
      scanDepth,
      includeExistingPositions,
      includeReplacementReviews,
    });
    if (!response.ok || !response.data) {
      setFeedback({
        state: "error",
        message: dailyTargetBookErrorMessage(
          response.error,
          "Target book build failed. Refresh after the latest deployment if this route was just released.",
        ),
      });
      return;
    }
    setResult(response.data);
    setFeedback({ state: "success", message: "Target book built. No paper orders were created and no positions were changed." });
  }

  if (loadState === "error") {
    return (
      <div className="op-stack">
        <PageHeader
          title="Daily Target Book"
          subtitle="Manual-review 5-position target book"
          actions={<StatusBadge tone="warn">Read-only. No orders are created. Operator review required.</StatusBadge>}
        />
        <ErrorState title="Daily Target Book unavailable" hint={feedback.message ?? "Refresh after backend health recovers."} />
      </div>
    );
  }

  const summary = result?.summary;

  return (
    <div className="op-stack">
      <PageHeader
        title="Daily Target Book"
        subtitle="Manual-review 5-position target book"
        actions={<StatusBadge tone="warn">Read-only. No orders are created. Operator review required.</StatusBadge>}
      />

      <InlineFeedback state={feedback.state} message={feedback.message} />

      <Card title="Build controls">
        <div className="dtb-readonly-banner">
          Read-only manual review. This page never creates paper orders, changes paper positions, starts schedules, or touches broker routing.
        </div>
        <div className="dtb-control-grid">
          <label>
            <span>Universe source</span>
            <select value={universeSource} onChange={(event) => setUniverseSource(event.target.value)}>
              <option value="manual">Manual symbols</option>
              <option value="watchlist">Watchlist</option>
              <option value="watchlist_plus_manual">Watchlist plus manual</option>
              <option value="profile">Default profile</option>
              <option value="default">Default symbols</option>
              <option value="all_active">All active user symbols</option>
            </select>
          </label>
          <label>
            <span>Scan depth</span>
            <input type="number" min={1} max={25} value={scanDepth} onChange={(event) => setScanDepth(Number(event.target.value))} />
          </label>
          <label className="dtb-checkbox">
            <input type="checkbox" checked={includeExistingPositions} onChange={(event) => setIncludeExistingPositions(event.target.checked)} />
            <span>Include existing positions</span>
          </label>
          <label className="dtb-checkbox">
            <input type="checkbox" checked={includeReplacementReviews} onChange={(event) => setIncludeReplacementReviews(event.target.checked)} />
            <span>Include replacement reviews</span>
          </label>
        </div>
        <label>
          <span>Symbols</span>
          <textarea value={symbolsText} onChange={(event) => setSymbolsText(event.target.value)} rows={3} />
        </label>
        <div className="op-row">
          <button className="op-btn op-btn-primary" type="button" onClick={buildBook} disabled={feedback.state === "loading"}>
            Build target book
          </button>
          <StatusBadge tone="neutral">manual review only</StatusBadge>
        </div>
      </Card>

      <Card title="Overview">
        {loadState === "loading" ? (
          <EmptyState title="Loading Daily Target Book" hint="Fetching read-only defaults and the latest target-book state." />
        ) : result ? (
          <div className="op-grid op-grid-4">
            <Metric label="Target slots" value={`${summary?.slotsReturned ?? 0}/${summary?.targetSlots ?? 5}`} />
            <Metric label="Current paper book" value={summary?.currentPaperBookCount ?? 0} />
            <Metric label="Keep reviews" value={summary?.keepReviews ?? 0} tone="good" />
            <Metric label="Open reviews" value={summary?.openReviews ?? 0} tone="good" />
            <Metric label="Exit reviews" value={summary?.exitReviews ?? 0} tone="warn" />
            <Metric label="Replace reviews" value={summary?.replaceReviews ?? 0} tone="warn" />
            <Metric label="Scale reviews" value={summary?.scaleReviews ?? 0} tone="warn" />
            <Metric label="Cash/no trade" value={summary?.cashNoTrade ?? 0} />
            <Metric label="Candidate groups" value={summary?.candidateGroupCount ?? 0} />
            <Metric label="Raw candidates" value={summary?.rawCandidateCount ?? 0} />
            <Metric label="Read-only" value={result.noOrdersCreated && result.noPositionsChanged ? "confirmed" : "check"} tone={result.noOrdersCreated && result.noPositionsChanged ? "good" : "bad"} />
            <Metric label="Universe" value={result.universe.source} />
          </div>
        ) : (
          <EmptyState title="No target book yet" hint="Build the read-only target book to compare Current Book vs Target Book." />
        )}
      </Card>

      <Card title="Target Book">
        {result?.targetBook?.length ? (
          <ResponsiveTable label="Daily Target Book slots">
            <table className="op-table dtb-target-table">
              <thead>
                <tr>
                  <th>Slot</th>
                  <th>Symbol</th>
                  <th>Action</th>
                  <th>Position</th>
                  <th>Qty / avg</th>
                  <th>Mark</th>
                  <th>P&L</th>
                  <th>Rank / score</th>
                  <th>Best strategy</th>
                  <th>RR / confidence</th>
                  <th>Risk</th>
                  <th>Operator action</th>
                </tr>
              </thead>
              <tbody>
                {result.targetBook.map((slot: DailyTargetBookSlot) => (
                  <tr key={slot.slot}>
                    <td>{slot.slot}</td>
                    <td><strong>{slot.symbol ?? "Cash"}</strong></td>
                    <td><SlotActionBadge action={slot.action} /></td>
                    <td>{slot.alreadyOpen ? `open #${slot.positionId ?? "-"}` : "not open"}</td>
                    <td>{formatQty(slot.quantity)} / {formatPrice(slot.averageEntry)}</td>
                    <td>{formatPrice(slot.mark)}</td>
                    <td>{formatMoney(slot.unrealizedPnl)} ({formatPercent(slot.unrealizedReturnPct)})</td>
                    <td>{asText(slot.rank)} / {formatScore(slot.score)}</td>
                    <td>{asText(slot.bestStrategy)}</td>
                    <td>{formatQty(slot.expectedRr)} / {formatScore(slot.confidence)}</td>
                    <td>{asText(slot.riskState)}</td>
                    <td>{asText(slot.suggestedOperatorAction)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ResponsiveTable>
        ) : (
          <EmptyState title="Target book empty" hint="Build the target book to populate five read-only review slots." />
        )}
      </Card>

      <Card title="Current Paper Book">
        {result?.currentPaperBook?.length ? (
          <ResponsiveTable label="Current paper book">
            <table className="op-table">
              <thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Avg entry</th><th>Mark</th><th>Unrealized P&L</th><th>Return</th><th>Days held</th><th>Review</th></tr></thead>
              <tbody>{result.currentPaperBook.map((row, index) => (
                <tr key={`${asText(row.positionId)}-${index}`}>
                  <td><strong>{asText(row.symbol)}</strong></td>
                  <td>{asText(row.side)}</td>
                  <td>{formatQty(row.quantity)}</td>
                  <td>{formatPrice(row.averageEntry)}</td>
                  <td>{formatPrice(row.mark)}</td>
                  <td>{formatMoney(row.unrealizedPnl)}</td>
                  <td>{formatPercent(row.unrealizedReturnPct)}</td>
                  <td>{asText(row.daysHeld)}</td>
                  <td>{asText(row.reviewSummary)}</td>
                </tr>
              ))}</tbody>
            </table>
          </ResponsiveTable>
        ) : (
          <EmptyState title="No current paper positions" hint="The target book can still show open reviews or cash/no-trade slots." />
        )}
      </Card>

      <Card title="Candidate Queue">
        {result?.candidateGroups?.length ? (
          <ResponsiveTable label="Grouped candidate queue">
            <table className="op-table">
              <thead><tr><th>Symbol</th><th>Best strategy</th><th>Rank</th><th>Score</th><th>Status</th><th>Supporting strategies</th><th>Reason</th></tr></thead>
              <tbody>{result.candidateGroups.map((group) => {
                const best = getBest(group);
                return (
                  <tr key={asText(group.symbol)}>
                    <td><strong>{asText(group.symbol)}</strong></td>
                    <td>{asText(best.strategy)}</td>
                    <td>{asText(best.rank)}</td>
                    <td>{formatScore(best.score)}</td>
                    <td>{asText(best.status)}</td>
                    <td>{asText(group.supportingStrategies)}</td>
                    <td>{asText(best.reason_text)}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </ResponsiveTable>
        ) : (
          <EmptyState title="Candidate queue empty" hint="Failed gates and missing bars become cash/no-trade review slots." />
        )}
      </Card>

      <Card title="Differences / Required Review">
        {result ? (
          <div className="op-stack">
            <div className="op-row">
              <StatusBadge tone={currentOnly.length ? "warn" : "neutral"}>Current Book only: {currentOnly.join(", ") || "none"}</StatusBadge>
              <StatusBadge tone={targetOnly.length ? "good" : "neutral"}>Target Book only: {targetOnly.join(", ") || "none"}</StatusBadge>
              <StatusBadge tone="warn">operator review required</StatusBadge>
            </div>
            <ResponsiveTable label="Current Book vs Target Book">
              <table className="op-table">
                <thead><tr><th>Target symbol</th><th>Action</th><th>Already open</th><th>Reason</th><th>Warnings</th></tr></thead>
                <tbody>{result.targetBook.map((slot) => (
                  <tr key={`diff-${slot.slot}`}>
                    <td>{slot.symbol ?? "Cash"}</td>
                    <td>{actionLabel(slot.action)}</td>
                    <td>{slot.alreadyOpen ? "yes" : "no"}</td>
                    <td>{asText(slot.reason)}</td>
                    <td>{asText(slot.warnings)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </ResponsiveTable>
          </div>
        ) : (
          <EmptyState title="No comparison yet" hint="Build the target book to see Current Book vs Target Book differences." />
        )}
      </Card>

      <div className="op-grid op-grid-2">
        <Card title="Decision Memo">
          {result?.decisionMemo?.length ? (
            <ul className="dtb-memo-list">
              {result.decisionMemo.map((item) => <li key={item}>{item}</li>)}
            </ul>
          ) : (
            <EmptyState title="No memo yet" hint="A deterministic read-only memo appears after building." />
          )}
        </Card>

        <Card title="Data Quality">
          {result?.dataQuality?.length ? (
            <ResponsiveTable label="Data quality">
              <table className="op-table">
                <thead><tr><th>Symbol</th><th>Status</th><th>Source</th><th>Fallback</th><th>Bars</th><th>Warnings</th></tr></thead>
                <tbody>{result.dataQuality.map((row, index) => (
                  <tr key={`${asText(row.symbol)}-${index}`}>
                    <td>{asText(row.symbol)}</td>
                    <td>{asText(row.status)}</td>
                    <td>{asText(row.source)}</td>
                    <td>{asText(row.fallbackMode)}</td>
                    <td>{asText(row.barCount)}</td>
                    <td>{asText(row.warnings)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </ResponsiveTable>
          ) : (
            <EmptyState title="No data quality report yet" hint="The build labels provider, fallback, and missing data for each symbol." />
          )}
        </Card>
      </div>

      {result?.warnings?.length ? (
        <Card title="Warnings">
          <ul className="dtb-memo-list">
            {result.warnings.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
