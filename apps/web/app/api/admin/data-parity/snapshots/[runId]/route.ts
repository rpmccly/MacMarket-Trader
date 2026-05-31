import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function GET(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return proxyWorkflowRequest({
    request,
    backendPath: `/admin/data-parity/snapshots/${encodeURIComponent(runId)}`,
  });
}
