import { NextResponse } from "next/server";
import { requireJob } from "@/server/access";
import { AccessError, requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";
import { getProductAutoDocument, saveProductAutoReview } from "@/server/product-auto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string; runId: string; docId: string }>;
}

const noStore = { "Cache-Control": "no-store, max-age=0" };

export async function GET(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId, runId, docId } = await params;
    requireJob(jobId, user);
    return NextResponse.json(getProductAutoDocument(jobId, runId, docId), { headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    return NextResponse.json({ error: "Could not load document result." }, { status: 500, headers: noStore });
  }
}

export async function POST(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId, runId, docId } = await params;
    requireJob(jobId, user);
    const body: unknown = await request.json();
    const fields = body && typeof body === "object" && !Array.isArray(body) ? (body as Record<string, unknown>).fields : null;
    const addedFields = body && typeof body === "object" && !Array.isArray(body)
      ? (body as Record<string, unknown>).added_fields ?? [] : [];
    const expectedRevision = body && typeof body === "object" && !Array.isArray(body)
      ? (body as Record<string, unknown>).expected_revision : null;
    const reportedActiveReviewSeconds = body && typeof body === "object" && !Array.isArray(body)
      ? (body as Record<string, unknown>).reported_active_review_seconds : undefined;
    const review = saveProductAutoReview(jobId, runId, docId, user.id, expectedRevision, fields, addedFields,
      reportedActiveReviewSeconds);
    const detail = getProductAutoDocument(jobId, runId, docId);
    return NextResponse.json({ review, correctedResult: detail.correctedResult }, { headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    if (error instanceof SyntaxError) return NextResponse.json({ error: "Invalid JSON request." }, { status: 400, headers: noStore });
    return NextResponse.json({ error: "Could not save review." }, { status: 500, headers: noStore });
  }
}
