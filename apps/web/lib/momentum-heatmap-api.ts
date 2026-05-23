import { SUPPORTED_TIMEFRAME_VALUES, type SupportedTimeframe } from "@/lib/timeframes";

export type MomentumHeatmapScoreStatus = "ok" | "unavailable" | "unsupported" | "error";

export type MomentumHeatmapScoreCell = {
  value: number | null;
  status: MomentumHeatmapScoreStatus;
  reason?: string | null;
  data_source?: string | null;
  fallback_mode?: boolean | null;
  as_of?: string | null;
};

export type MomentumHeatmapSqueezeCell = {
  value: string | null;
  status: "deferred" | "ok" | "unavailable";
  reason?: string | null;
};

export type MomentumHeatmapRequestRow = {
  id: string;
  symbol: string;
  displayName?: string;
  providerSymbol?: string;
};

export type MomentumHeatmapRequestCategory = {
  categoryId: string;
  categoryLabel: string;
  rows: MomentumHeatmapRequestRow[];
};

export type MomentumHeatmapRequest = {
  categories: MomentumHeatmapRequestCategory[];
  timeframes: SupportedTimeframe[];
};

export type MomentumHeatmapResponseRow = {
  id: string;
  symbol: string;
  displayName: string;
  providerSymbol: string;
  scores: Record<SupportedTimeframe, MomentumHeatmapScoreCell>;
  long_term_score: number | null;
  short_term_score: number | null;
  strength_percent: number | null;
  squeeze: MomentumHeatmapSqueezeCell;
};

export type MomentumHeatmapResponseCategory = {
  categoryId: string;
  categoryLabel: string;
  rows: MomentumHeatmapResponseRow[];
};

export type MomentumHeatmapResponse = {
  generated_at: string;
  timeframes: SupportedTimeframe[];
  categories: MomentumHeatmapResponseCategory[];
};

export async function fetchMomentumHeatmap(categories: MomentumHeatmapRequestCategory[]): Promise<MomentumHeatmapResponse> {
  const response = await fetch("/api/charts/momentum-heatmap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      categories,
      timeframes: [...SUPPORTED_TIMEFRAME_VALUES],
    } satisfies MomentumHeatmapRequest),
  });
  if (!response.ok) {
    throw new Error(`Failed to load Momentum Heatmap: ${response.status}`);
  }
  return response.json() as Promise<MomentumHeatmapResponse>;
}
