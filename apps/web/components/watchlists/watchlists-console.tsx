"use client";

import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Card, EmptyState, ErrorState, InlineFeedback, PageHeader, ResponsiveTable, StatusBadge } from "@/components/operator-ui";
import {
  createWatchlist,
  deleteWatchlist,
  fetchWatchlists,
  updateWatchlist,
  type Watchlist,
} from "@/lib/watchlists-api";

type Draft = {
  id: number | null;
  name: string;
  description: string;
  symbolsText: string;
  isDefault: boolean;
};

const emptyDraft: Draft = {
  id: null,
  name: "",
  description: "",
  symbolsText: "SPY, QQQ, XLK",
  isDefault: false,
};

function asText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "-";
  return String(value);
}

function parseSymbols(text: string): { symbols: string[]; duplicates: string[]; invalid: string[] } {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  const invalid: string[] = [];
  const symbols: string[] = [];
  for (const raw of text.split(/[,\s]+/)) {
    const symbol = raw.trim().toUpperCase();
    if (!symbol) continue;
    if (!/^[A-Z][A-Z0-9.-]{0,14}$/.test(symbol)) {
      invalid.push(symbol);
      continue;
    }
    if (seen.has(symbol)) {
      duplicates.add(symbol);
      continue;
    }
    seen.add(symbol);
    symbols.push(symbol);
  }
  return { symbols, duplicates: Array.from(duplicates), invalid };
}

function toDraft(row: Watchlist): Draft {
  return {
    id: row.id,
    name: row.name,
    description: row.description ?? "",
    symbolsText: (row.symbols ?? []).join(", "),
    isDefault: Boolean(row.is_default),
  };
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

export function WatchlistsConsole() {
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [feedback, setFeedback] = useState<{ state: "idle" | "loading" | "success" | "error"; message?: string }>({ state: "idle" });

  const parsed = useMemo(() => parseSymbols(draft.symbolsText), [draft.symbolsText]);
  const selected = watchlists.find((row) => row.id === draft.id) ?? null;
  const isSaving = feedback.state === "loading";

  const load = useCallback(async (selectId?: number) => {
    setLoadState("loading");
    const response = await fetchWatchlists();
    if (!response.ok) {
      setLoadState("error");
      setFeedback({ state: "error", message: response.error ?? "Watchlists are unavailable." });
      return;
    }
    const rows = response.items;
    setWatchlists(rows);
    const next = rows.find((row) => row.id === selectId) ?? rows[0] ?? null;
    setDraft(next ? toDraft(next) : emptyDraft);
    setLoadState("ready");
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function beginCreate() {
    setDraft(emptyDraft);
    setFeedback({ state: "idle" });
  }

  function moveSymbol(index: number, direction: -1 | 1) {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= parsed.symbols.length) return;
    const symbols = [...parsed.symbols];
    [symbols[index], symbols[nextIndex]] = [symbols[nextIndex], symbols[index]];
    setDraft({ ...draft, symbolsText: symbols.join(", ") });
  }

  function removeSymbol(symbolToRemove: string) {
    const next = parsed.symbols.filter((symbol) => symbol !== symbolToRemove);
    setDraft({ ...draft, symbolsText: next.join(", ") });
  }

  async function setDefault() {
    if (!draft.id) {
      setDraft({ ...draft, isDefault: true });
      setFeedback({ state: "success", message: "Default selected for the draft. Save the watchlist to apply it." });
      return;
    }
    setFeedback({ state: "loading", message: "Setting default watchlist." });
    const response = await updateWatchlist(draft.id, { is_default: true });
    if (!response.ok || !response.data) {
      setFeedback({ state: "error", message: response.error ?? "Default update failed." });
      return;
    }
    setFeedback({ state: "success", message: "Default watchlist updated." });
    await load(response.data.id);
  }

  async function save() {
    if (!draft.name.trim()) {
      setFeedback({ state: "error", message: "Watchlist name is required." });
      return;
    }
    if (!parsed.symbols.length) {
      setFeedback({ state: "error", message: "Add at least one valid symbol before saving." });
      return;
    }
    if (parsed.invalid.length) {
      setFeedback({ state: "error", message: `Unsupported symbol format: ${parsed.invalid.join(", ")}` });
      return;
    }
    setFeedback({ state: "loading", message: draft.id ? "Saving watchlist." : "Creating watchlist." });
    const payload = {
      name: draft.name.trim(),
      description: draft.description.trim(),
      symbols: parsed.symbols,
      is_default: draft.isDefault,
    };
    const response = draft.id
      ? await updateWatchlist(draft.id, payload)
      : await createWatchlist(payload);
    if (!response.ok || !response.data) {
      setFeedback({ state: "error", message: response.error ?? "Watchlist save failed." });
      return;
    }
    setFeedback({ state: "success", message: "Watchlist saved. Existing recommendation and schedule logic is unchanged." });
    await load(response.data.id);
  }

  async function remove() {
    if (!draft.id) return;
    const confirmed = window.confirm(`Delete ${draft.name}? This does not auto-reseed the starter watchlist.`);
    if (!confirmed) return;
    setFeedback({ state: "loading", message: "Deleting watchlist." });
    const response = await deleteWatchlist(draft.id);
    if (!response.ok) {
      setFeedback({ state: "error", message: response.error ?? "Watchlist delete failed." });
      return;
    }
    setFeedback({ state: "success", message: "Watchlist deleted. Empty accounts are not reseeded by listing watchlists." });
    await load();
  }

  if (loadState === "error") {
    return (
      <div className="op-stack">
        <PageHeader title="Watchlists" subtitle="User-scoped symbol universe management." />
        <ErrorState title="Watchlists unavailable" hint={feedback.message ?? "Refresh after backend health recovers."} />
      </div>
    );
  }

  return (
    <div className="op-stack">
      <PageHeader
        title="Watchlists"
        subtitle="Manage editable user-scoped symbol universes for Recommendations, Agent Mode, Daily Target Book, and Scheduled Reports."
        actions={<button className="op-btn op-btn-secondary" type="button" onClick={beginCreate}>New watchlist</button>}
      />

      <InlineFeedback state={feedback.state} message={feedback.message} />

      <div className="watchlist-layout">
        <Card title="Your watchlists">
          {loadState === "loading" ? (
            <EmptyState title="Loading watchlists" hint="Fetching user-scoped watchlists." />
          ) : watchlists.length ? (
            <div className="watchlist-master-list" role="list">
              {watchlists.map((row) => (
                <button
                  key={row.id}
                  className={`watchlist-card-button ${row.id === draft.id ? "is-selected" : ""}`}
                  type="button"
                  onClick={() => setDraft(toDraft(row))}
                >
                  <span className="watchlist-card-title">
                    <strong>{row.name}</strong>
                    <span>{row.symbols?.length ?? 0} symbols</span>
                  </span>
                  <span className="watchlist-card-badges">
                    {row.is_default ? <StatusBadge tone="good">default</StatusBadge> : null}
                    {row.is_starter || row.starter ? <StatusBadge tone="neutral">starter</StatusBadge> : null}
                    <StatusBadge tone="neutral">Agent Mode</StatusBadge>
                    <StatusBadge tone="neutral">Scheduled Reports</StatusBadge>
                  </span>
                  <span className="watchlist-chip-preview">
                    {(row.symbols ?? []).slice(0, 8).map((symbol) => <span key={`${row.id}-${symbol}`} className="watchlist-symbol-chip">{symbol}</span>)}
                    {(row.symbols?.length ?? 0) > 8 ? <span className="watchlist-symbol-chip">+{(row.symbols?.length ?? 0) - 8}</span> : null}
                  </span>
                  <span className="watchlist-card-meta">Updated {formatDate(row.updated_at ?? row.created_at)}</span>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState title="No watchlists" hint="Create a list to use as an Agent Mode or scheduled-report universe. Deleted starter lists are not recreated from this page." />
          )}
        </Card>

        <Card title={draft.id ? "Edit watchlist" : "Create watchlist"}>
          <div className="op-stack">
            <div className="watchlist-summary-strip">
              <StatusBadge tone="neutral">{parsed.symbols.length} symbols</StatusBadge>
              {draft.isDefault ? <StatusBadge tone="good">default</StatusBadge> : null}
              {selected?.is_starter || selected?.starter ? <StatusBadge tone="neutral">editable starter list</StatusBadge> : null}
              <StatusBadge tone="neutral">Used by Agent Mode</StatusBadge>
              <StatusBadge tone="neutral">Used by schedules/reports</StatusBadge>
              <StatusBadge tone="neutral">Last updated {formatDate(selected?.updated_at ?? selected?.created_at)}</StatusBadge>
            </div>
            <label>
              <span>Name</span>
              <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
            </label>
            <label>
              <span>Description</span>
              <textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} rows={2} />
            </label>
            <label>
              <span>Symbols</span>
              <textarea className="watchlist-symbol-editor" value={draft.symbolsText} onChange={(event) => setDraft({ ...draft, symbolsText: event.target.value })} rows={7} />
            </label>
            <label className="dtb-checkbox">
              <input type="checkbox" checked={draft.isDefault} onChange={(event) => setDraft({ ...draft, isDefault: event.target.checked })} />
              <span>Default watchlist</span>
            </label>

            <div className="op-row">
              <StatusBadge tone="neutral">{parsed.symbols.length} valid symbols</StatusBadge>
              {parsed.duplicates.length ? <StatusBadge tone="warn">duplicates ignored: {parsed.duplicates.join(", ")}</StatusBadge> : null}
              {parsed.invalid.length ? <StatusBadge tone="bad">unsupported: {parsed.invalid.join(", ")}</StatusBadge> : null}
              {selected?.is_starter || selected?.starter ? <StatusBadge tone="neutral">editable starter list</StatusBadge> : null}
            </div>

            {parsed.symbols.length ? (
              <div className="watchlist-symbol-grid" aria-label="Editable symbol chips">
                {parsed.symbols.map((symbol) => (
                  <span key={symbol} className="watchlist-symbol-chip">
                    {symbol}
                    <button type="button" aria-label={`Remove ${symbol}`} onClick={() => removeSymbol(symbol)}>x</button>
                  </span>
                ))}
              </div>
            ) : null}

            {parsed.symbols.length ? (
              <ResponsiveTable label="Symbol order">
                <table className="op-table">
                  <thead><tr><th>#</th><th>Symbol</th><th>Order</th></tr></thead>
                  <tbody>{parsed.symbols.map((symbol, index) => (
                    <tr key={`${symbol}-${index}`}>
                      <td>{index + 1}</td>
                      <td><strong>{symbol}</strong></td>
                      <td>
                        <button className="op-btn op-btn-ghost" type="button" disabled={index === 0} onClick={() => moveSymbol(index, -1)}>Up</button>
                        <button className="op-btn op-btn-ghost" type="button" disabled={index === parsed.symbols.length - 1} onClick={() => moveSymbol(index, 1)}>Down</button>
                      </td>
                    </tr>
                  ))}</tbody>
                </table>
              </ResponsiveTable>
            ) : null}

            <div className="agent-paper-warning">
              Watchlists are editable research universes. Saving a watchlist does not create orders, change paper positions, or call a broker.
            </div>

            <div className="op-row">
              <button className="op-btn op-btn-primary" type="button" onClick={save} disabled={isSaving}>Save watchlist</button>
              <button className="op-btn op-btn-secondary" type="button" onClick={setDefault} disabled={isSaving}>Set default</button>
              <button className="op-btn op-btn-ghost" type="button" onClick={beginCreate} disabled={isSaving}>Clear form</button>
              {draft.id ? <button className="op-btn op-btn-destructive" type="button" onClick={remove} disabled={isSaving}>Delete</button> : null}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
