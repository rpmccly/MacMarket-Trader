import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function POST(request: Request) {
  return proxyWorkflowRequest({
    request,
    backendPath: "/charts/atr-heatmap/report/csv",
    bodyText: await request.text(),
  });
}
