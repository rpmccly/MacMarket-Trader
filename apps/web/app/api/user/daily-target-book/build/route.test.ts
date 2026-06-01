import { beforeEach, describe, expect, it, vi } from "vitest";

const proxyWorkflowRequestMock = vi.fn();

vi.mock("@/app/api/_utils/workflow-proxy", () => ({
  proxyWorkflowRequest: proxyWorkflowRequestMock,
}));

describe("/api/user/daily-target-book/build", () => {
  beforeEach(() => {
    proxyWorkflowRequestMock.mockReset();
  });

  it("accepts POST and proxies to the backend build endpoint", async () => {
    proxyWorkflowRequestMock.mockResolvedValue(Response.json({ ok: true }));
    const { POST } = await import("./route");
    const bodyText = JSON.stringify({ symbols: ["SPY"] });

    const response = await POST(
      new Request("http://localhost/api/user/daily-target-book/build", {
        method: "POST",
        body: bodyText,
      }),
    );

    expect(response.status).toBe(200);
    expect(proxyWorkflowRequestMock).toHaveBeenCalledWith({
      request: expect.any(Request),
      backendPath: "/user/daily-target-book/build",
      bodyText,
    });
  });

  it("returns structured JSON errors from the proxy", async () => {
    proxyWorkflowRequestMock.mockResolvedValue(
      Response.json(
        { detail: "Route not found (404). Refresh after the latest deployment or try again after the app restarts." },
        { status: 404 },
      ),
    );
    const { POST } = await import("./route");

    const response = await POST(
      new Request("http://localhost/api/user/daily-target-book/build", {
        method: "POST",
        body: "{}",
      }),
    );

    expect(response.status).toBe(404);
    const body = (await response.json()) as { detail?: string };
    expect(body.detail).toContain("Route not found");
    expect(body.detail).not.toContain("<html");
  });
});
