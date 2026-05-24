import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function GET(request: Request) {
  return proxyWorkflowRequest({
    request,
    backendPath: "/user/momentum-heatmap/schedule",
    method: "GET",
  });
}

export async function PUT(request: Request) {
  return proxyWorkflowRequest({
    request,
    backendPath: "/user/momentum-heatmap/schedule",
    method: "PUT",
    bodyText: await request.text(),
  });
}
