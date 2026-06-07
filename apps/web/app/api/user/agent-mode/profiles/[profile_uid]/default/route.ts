import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

type RouteContext = { params: Promise<{ profile_uid: string }> };

export async function POST(request: Request, context: RouteContext) {
  const { profile_uid } = await context.params;
  return proxyWorkflowRequest({
    request,
    backendPath: `/user/agent-mode/profiles/${encodeURIComponent(profile_uid)}/default`,
    bodyText: await request.text(),
  });
}
