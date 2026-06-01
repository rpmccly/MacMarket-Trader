import { fetchWorkflowApi } from "@/lib/api-client";

export type DailyTargetBookBuildRequest = {
  universeSource: string;
  symbols: string[];
  scanDepth: number;
  includeExistingPositions: boolean;
  includeReplacementReviews: boolean;
};

export type DailyTargetBookSlot = {
  slot: number;
  symbol?: string | null;
  side?: string | null;
  action: "KEEP_REVIEW" | "EXIT_REVIEW" | "OPEN_REVIEW" | "REPLACE_REVIEW" | "SCALE_REVIEW" | "CASH_NO_TRADE" | string;
  alreadyOpen: boolean;
  positionId?: number | null;
  quantity?: number | null;
  averageEntry?: number | null;
  mark?: number | null;
  unrealizedPnl?: number | null;
  unrealizedReturnPct?: number | null;
  rank?: number | null;
  score?: number | null;
  bestStrategy?: string | null;
  supportingStrategies?: Array<Record<string, unknown>>;
  confidence?: number | null;
  expectedRr?: number | null;
  entryZone?: string | null;
  stopInvalidation?: unknown;
  targets?: unknown;
  daysHeld?: number | null;
  maxHoldDays?: number | null;
  riskState?: string | null;
  source?: string | null;
  warnings?: string[];
  missingData?: string[];
  reason?: string | null;
  suggestedOperatorAction?: string | null;
};

export type DailyTargetBookResult = {
  runId: string;
  generatedAt: string;
  asOf: string;
  mode: string;
  readOnly: boolean;
  paperOnly: boolean;
  executionMode: string;
  noOrdersCreated: boolean;
  noPositionsChanged: boolean;
  universe: {
    symbols: string[];
    source: string;
    resolvedSource?: string;
    scanDepth: number;
    timeframe: string;
    provenance?: Record<string, unknown>;
  };
  summary: {
    targetSlots: number;
    slotsReturned: number;
    currentPaperBookCount: number;
    candidateGroupCount: number;
    rawCandidateCount: number;
    actions: Record<string, number>;
    keepReviews: number;
    exitReviews: number;
    openReviews: number;
    replaceReviews: number;
    scaleReviews: number;
    cashNoTrade: number;
    operatorReviewRequired: boolean;
    readOnly: boolean;
    paperOnly: boolean;
  };
  targetBook: DailyTargetBookSlot[];
  currentPaperBook: Array<Record<string, unknown>>;
  candidateQueue: Array<Record<string, unknown>>;
  candidateGroups: Array<Record<string, unknown>>;
  differences: Record<string, unknown>;
  decisionMemo: string[];
  dataQuality: Array<Record<string, unknown>>;
  warnings: string[];
};

export type DailyTargetBookLatestResponse = {
  latest: DailyTargetBookResult | null;
  empty: boolean;
  readOnly: boolean;
  paperOnly: boolean;
  executionMode: string;
  defaults: {
    symbols: string[];
    scanDepth: number;
    targetSlots: number;
    universeSource: string;
    includeExistingPositions: boolean;
    includeReplacementReviews: boolean;
  };
  sourceOptions: string[];
};

export async function fetchDailyTargetBookLatest() {
  return fetchWorkflowApi<DailyTargetBookLatestResponse>("/api/user/daily-target-book/latest");
}

export async function buildDailyTargetBook(payload: DailyTargetBookBuildRequest) {
  return fetchWorkflowApi<DailyTargetBookResult>("/api/user/daily-target-book/build", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
