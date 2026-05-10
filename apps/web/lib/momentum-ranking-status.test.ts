import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMomentumRankingStatus } from "@/lib/momentum-ranking-status";

vi.mock("@/lib/api-client", () => ({
  fetchWorkflowApi: vi.fn(),
}));

import * as apiClient from "@/lib/api-client";

const mockedFetchWorkflow = apiClient.fetchWorkflowApi as unknown as ReturnType<typeof vi.fn>;

describe("fetchMomentumRankingStatus", () => {
  beforeEach(() => {
    mockedFetchWorkflow.mockReset();
  });
  afterEach(() => {
    mockedFetchWorkflow.mockReset();
  });

  it("delegates to fetchWorkflowApi against the protected status route", async () => {
    mockedFetchWorkflow.mockResolvedValue({
      ok: true,
      status: 200,
      data: {
        mode: "shadow",
        default_mode: "shadow",
        env_var: "MACMARKET_MOMENTUM_RANKING_MODE",
        enabled: true,
        applied_by_default: false,
        parity_status: "pending_thinkorswim_fixture_validation",
        parity_fixture_manifest_present: false,
        parity_required_for_active: false,
        real_thinkorswim_parity_pending: true,
        reason_codes: ["thinkorswim_parity_pending"],
        guardrails: ["Shadow mode computes contribution but does not alter final ranking."],
      },
    });

    const result = await fetchMomentumRankingStatus();
    expect(mockedFetchWorkflow).toHaveBeenCalledWith("/api/user/momentum-ranking-status");
    expect(result.ok).toBe(true);
    expect(result.data?.mode).toBe("shadow");
  });

  it("surfaces non-OK responses without throwing", async () => {
    mockedFetchWorkflow.mockResolvedValue({ ok: false, status: 503, error: "Provider initializing" });
    const result = await fetchMomentumRankingStatus();
    expect(result.ok).toBe(false);
    expect(result.error).toBe("Provider initializing");
  });

  it("surfaces auth-pending state through the normalized result", async () => {
    mockedFetchWorkflow.mockResolvedValue({ ok: false, status: 425, authPending: true });
    const result = await fetchMomentumRankingStatus();
    expect(result.ok).toBe(false);
    expect(result.authPending).toBe(true);
  });
});
