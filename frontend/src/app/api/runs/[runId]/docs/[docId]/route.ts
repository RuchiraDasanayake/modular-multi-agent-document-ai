import { NextResponse } from "next/server";
import { getRunDocument } from "@/server/artifacts";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ runId: string; docId: string }>;
}

export async function GET(_: Request, { params }: Params) {
  try {
    const { runId, docId } = await params;
    const doc = getRunDocument(runId, docId);
    return NextResponse.json(doc);
  } catch (error) {
    return apiError(error, 404);
  }
}
