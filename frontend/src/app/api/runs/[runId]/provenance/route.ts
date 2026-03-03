import { NextResponse } from "next/server";
import { getRunProvenance } from "@/server/artifacts";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ runId: string }>;
}

export async function GET(_: Request, { params }: Params) {
  try {
    const { runId } = await params;
    const provenance = getRunProvenance(runId);
    return NextResponse.json(provenance);
  } catch (error) {
    return apiError(error, 404);
  }
}
