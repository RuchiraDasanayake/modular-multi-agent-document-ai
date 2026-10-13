import { NextResponse } from "next/server";
import { readRunOcrText } from "@/server/artifacts";
import { apiError } from "@/server/api/response";
import { getJobOrThrow } from "@/server/jobs";
import { requireJob } from "@/server/access";
import { requireUser } from "@/server/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_TEXT_CHARS = 20_000;

interface Params {
  params: Promise<{ jobId: string; docId: string }>;
}

export async function GET(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId, docId } = await params;
    requireJob(jobId, user);
    const document = (getJobOrThrow(jobId).documents ?? []).find((entry) => entry.fileId === docId);
    if (!document) {
      return NextResponse.json({ error: "Document not found" }, { status: 404 });
    }
    const text =
      document.latestRunId && document.latestDocId ? readRunOcrText(document.latestRunId, document.latestDocId) : "";
    return NextResponse.json(
      {
        jobId,
        fileId: document.fileId,
        fileName: document.fileName,
        runId: document.latestRunId,
        text: text.slice(0, MAX_TEXT_CHARS),
        truncated: text.length > MAX_TEXT_CHARS,
      },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  } catch (error) {
    return apiError(error, 400);
  }
}
