import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

type RouteContext = { params: Promise<{ profile_uid: string }> };

export async function GET(request: Request, context: RouteContext) {
  const { profile_uid } = await context.params;
  return proxyWorkflowRequest({
    request,
    backendPath: `/user/agent-mode/profiles/${encodeURIComponent(profile_uid)}`,
  });
}

export async function PUT(request: Request, context: RouteContext) {
  const { profile_uid } = await context.params;
  return proxyWorkflowRequest({
    request,
    backendPath: `/user/agent-mode/profiles/${encodeURIComponent(profile_uid)}`,
    bodyText: await request.text(),
  });
}

export async function DELETE(request: Request, context: RouteContext) {
  const { profile_uid } = await context.params;
  return proxyWorkflowRequest({
    request,
    backendPath: `/user/agent-mode/profiles/${encodeURIComponent(profile_uid)}`,
  });
}
