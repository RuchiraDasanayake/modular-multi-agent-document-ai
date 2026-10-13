import { NextResponse } from "next/server";
import { recoveryReadOnlyResponse } from "@/lib/recovery-access";
import { addStagedDocumentsToJob } from "@/server/jobs";
import { requireJob } from "@/server/access";
import { requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";
import { cleanupStagedUploads, stageUploadRequest, type StagedUpload, UploadRequestError } from "@/server/upload-stream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string }>;
}

export async function POST(request: Request, { params }: Params) {
  // Uploads deliberately bypass the proxy to preserve streaming, so enforce the
  // passive recovery boundary here before authentication or body parsing.
  const blocked = recoveryReadOnlyResponse(request);
  if (blocked) return blocked;
  let staged: StagedUpload[] = [];
  try {
    const user = await requireUser(request.headers);
    const { jobId } = await params;
    requireJob(jobId, user);
    staged = await stageUploadRequest(request, jobId);
    const key = request.headers.get("idempotency-key") ?? undefined;
    const updated = addStagedDocumentsToJob(jobId, staged, key);
    return NextResponse.json(updated, { status: 201 });
  } catch (error) {
    return apiError(error, error instanceof UploadRequestError ? error.status : 400);
  } finally {
    cleanupStagedUploads(staged);
  }
}
