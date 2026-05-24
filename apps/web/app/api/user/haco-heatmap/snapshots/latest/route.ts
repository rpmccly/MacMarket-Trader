import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function GET(request: Request) {
  return proxyWorkflowRequest({
    request,
    backendPath: "/user/haco-heatmap/snapshots/latest",
    method: "GET",
    includeSearchParams: true,
  });
}
