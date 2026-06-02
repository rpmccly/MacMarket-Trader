import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyWorkflowRequest({
    request,
    backendPath: `/user/watchlists/${encodeURIComponent(id)}`,
    bodyText: await request.text(),
  });
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyWorkflowRequest({
    request,
    backendPath: `/user/watchlists/${encodeURIComponent(id)}`,
  });
}
