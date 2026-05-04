import { NextResponse } from "next/server";
import { getRunOverview } from "@/server/artifacts";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ runId: string }>;
}

export async function GET(_: Request, { params }: Params) {
  try {
    const { runId } = await params;
    const summary = getRunOverview(runId);
    return NextResponse.json(summary);
  } catch (error) {
    return apiError(error, 404);
  }
}
