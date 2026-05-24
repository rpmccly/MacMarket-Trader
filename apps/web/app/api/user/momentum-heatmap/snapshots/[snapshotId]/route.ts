import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function GET(request: Request, { params }: { params: Promise<{ snapshotId: string }> }) {
  const { snapshotId } = await params;
  return proxyWorkflowRequest({
    request,
    backendPath: `/user/momentum-heatmap/snapshots/${encodeURIComponent(snapshotId)}`,
    method: "GET",
  });
}
