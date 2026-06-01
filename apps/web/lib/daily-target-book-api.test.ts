import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-client", () => ({
  fetchWorkflowApi: vi.fn(async (_input: string, init?: RequestInit) => ({
    ok: true,
    status: 200,
    data: init?.body ? JSON.parse(String(init.body)) : {},
    items: [],
    error: null,
    raw: {},
  })),
}));

import { fetchWorkflowApi } from "@/lib/api-client";
import { buildDailyTargetBook, fetchDailyTargetBookLatest } from "@/lib/daily-target-book-api";

describe("daily-target-book-api", () => {
  it("uses read-only same-origin endpoints", async () => {
    await fetchDailyTargetBookLatest();
    await buildDailyTargetBook({
      universeSource: "manual",
      symbols: ["SPY", "QQQ"],
      scanDepth: 12,
      includeExistingPositions: true,
      includeReplacementReviews: true,
    });

    expect(fetchWorkflowApi).toHaveBeenNthCalledWith(1, "/api/user/daily-target-book/latest");
    expect(fetchWorkflowApi).toHaveBeenNthCalledWith(
      2,
      "/api/user/daily-target-book/build",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse(String((vi.mocked(fetchWorkflowApi).mock.calls[1][1] as RequestInit).body));
    expect(body).toEqual(expect.objectContaining({
      universeSource: "manual",
      symbols: ["SPY", "QQQ"],
      scanDepth: 12,
      includeExistingPositions: true,
      includeReplacementReviews: true,
    }));
  });
});
