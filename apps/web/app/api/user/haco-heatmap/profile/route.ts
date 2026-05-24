import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function GET(request: Request) {
  return proxyWorkflowRequest({
    request,
    backendPath: "/user/haco-heatmap/profile",
    method: "GET",
    includeSearchParams: true,
  });
}

export async function PUT(request: Request) {
  return proxyWorkflowRequest({
    request,
    backendPath: "/user/haco-heatmap/profile",
    method: "PUT",
    bodyText: await request.text(),
  });
}
