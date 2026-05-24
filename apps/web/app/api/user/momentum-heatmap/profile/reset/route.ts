import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function POST(request: Request) {
  return proxyWorkflowRequest({
    request,
    backendPath: "/user/momentum-heatmap/profile/reset",
    method: "POST",
    bodyText: await request.text(),
  });
}
