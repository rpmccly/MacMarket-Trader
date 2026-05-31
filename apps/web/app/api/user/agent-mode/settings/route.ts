import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function GET(request: Request) {
  return proxyWorkflowRequest({ request, backendPath: "/user/agent-mode/settings" });
}

export async function POST(request: Request) {
  return proxyWorkflowRequest({
    request,
    backendPath: "/user/agent-mode/settings",
    bodyText: await request.text(),
  });
}
