import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function GET(request: Request) {
  return proxyWorkflowRequest({ request, backendPath: "/user/agent-mode/profiles" });
}

export async function POST(request: Request) {
  return proxyWorkflowRequest({
    request,
    backendPath: "/user/agent-mode/profiles",
    bodyText: await request.text(),
  });
}
