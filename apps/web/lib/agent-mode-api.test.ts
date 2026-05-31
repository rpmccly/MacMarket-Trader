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
import { fetchAgentModeSettings, fetchLatestAgentModeRun, runAgentMode, saveAgentModeSettings } from "@/lib/agent-mode-api";

describe("agent-mode-api", () => {
  it("uses paper-only same-origin endpoints", async () => {
    await fetchAgentModeSettings();
    await fetchLatestAgentModeRun();
    await saveAgentModeSettings({ enabled: true });
    await runAgentMode({ dry_run: true, symbols: ["SPY"] });

    expect(fetchWorkflowApi).toHaveBeenNthCalledWith(1, "/api/user/agent-mode/settings");
    expect(fetchWorkflowApi).toHaveBeenNthCalledWith(2, "/api/user/agent-mode/latest");
    expect(fetchWorkflowApi).toHaveBeenNthCalledWith(
      3,
      "/api/user/agent-mode/settings",
      expect.objectContaining({ method: "POST" }),
    );
    expect(fetchWorkflowApi).toHaveBeenNthCalledWith(
      4,
      "/api/user/agent-mode/run",
      expect.objectContaining({ method: "POST" }),
    );
    const runBody = JSON.parse(String((vi.mocked(fetchWorkflowApi).mock.calls[3][1] as RequestInit).body));
    expect(runBody.mode).toBe("paper");
    expect(runBody.dry_run).toBe(true);
  });
});
