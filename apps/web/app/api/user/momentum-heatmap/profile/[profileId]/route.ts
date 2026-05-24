import { proxyWorkflowRequest } from "@/app/api/_utils/workflow-proxy";

export async function DELETE(request: Request, { params }: { params: Promise<{ profileId: string }> }) {
  const { profileId } = await params;
  return proxyWorkflowRequest({
    request,
    backendPath: `/user/momentum-heatmap/profile/${encodeURIComponent(profileId)}`,
    method: "DELETE",
  });
}
