import { NextResponse } from "next/server";
import { requireJob } from "@/server/access";
import { AccessError, requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";
import { getProductAutoReviewedExport } from "@/server/product-auto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string; runId: string; docId: string }>;
}

const noStore = { "Cache-Control": "no-store, max-age=0", "X-Content-Type-Options": "nosniff" };

export async function GET(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId, runId, docId } = await params;
    requireJob(jobId, user);
    const result = getProductAutoReviewedExport(jobId, runId, docId);
    return NextResponse.json(result, { headers: {
      ...noStore,
      "Content-Disposition": `attachment; filename="docai-${docId}-reviewed-v1.json"`,
    } });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    return NextResponse.json({ error: "Could not export reviewed result." }, { status: 500, headers: noStore });
  }
}
