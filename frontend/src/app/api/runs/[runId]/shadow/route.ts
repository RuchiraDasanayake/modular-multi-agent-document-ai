import { NextResponse } from "next/server";
import { getRunShadow } from "@/server/artifacts";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ runId: string }>;
}

export async function GET(_: Request, { params }: Params) {
  try {
    const { runId } = await params;
    const shadow = getRunShadow(runId);
    return NextResponse.json(shadow);
  } catch (error) {
    return apiError(error, 404);
  }
}
