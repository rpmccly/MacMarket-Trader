import { beforeEach, describe, expect, it, vi } from "vitest";

const proxyWorkflowRequestMock = vi.fn();

vi.mock("@/app/api/_utils/workflow-proxy", () => ({
  proxyWorkflowRequest: proxyWorkflowRequestMock,
}));

describe("/api/user/daily-target-book/latest", () => {
  beforeEach(() => {
    proxyWorkflowRequestMock.mockReset();
  });

  it("exists and proxies to the backend latest endpoint", async () => {
    proxyWorkflowRequestMock.mockResolvedValue(Response.json({ result: null }));
    const { GET } = await import("./route");

    const response = await GET(new Request("http://localhost/api/user/daily-target-book/latest"));

    expect(response.status).toBe(200);
    expect(proxyWorkflowRequestMock).toHaveBeenCalledWith({
      request: expect.any(Request),
      backendPath: "/user/daily-target-book/latest",
    });
  });
});
