import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function DELETE(request: Request, { params }: { params: Promise<{ rowId: string }> }) {
  const { rowId } = await params;
  return proxyWorkflowRequest({
    request,
    backendPath: `/user/haco-heatmap/rows/${encodeURIComponent(rowId)}`,
    method: "DELETE",
    includeSearchParams: true,
  });
}
