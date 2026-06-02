import { fetchWorkflowApi } from "@/lib/api-client";

export type Watchlist = {
  id: number;
  name: string;
  description?: string | null;
  symbols: string[];
  is_default?: boolean;
  is_starter?: boolean;
  starter?: boolean;
  usage_hints?: string[];
  created_at?: string | null;
  updated_at?: string | null;
};

export type WatchlistPayload = {
  name: string;
  description?: string;
  symbols: string[];
  is_default?: boolean;
};

export async function fetchWatchlists() {
  return fetchWorkflowApi<Watchlist>("/api/user/watchlists");
}

export async function createWatchlist(payload: WatchlistPayload) {
  return fetchWorkflowApi<Watchlist>("/api/user/watchlists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateWatchlist(id: number, payload: Partial<WatchlistPayload>) {
  return fetchWorkflowApi<Watchlist>(`/api/user/watchlists/${encodeURIComponent(String(id))}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteWatchlist(id: number) {
  return fetchWorkflowApi<Record<string, unknown>>(`/api/user/watchlists/${encodeURIComponent(String(id))}`, {
    method: "DELETE",
  });
}
