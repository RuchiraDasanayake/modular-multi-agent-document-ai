import { NextResponse } from "next/server";
import { getRunOverview } from "@/server/artifacts";
import { requireRun } from "@/server/access";
import { requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ runId: string }>;
}

export async function GET(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { runId } = await params;
    requireRun(runId, user);
    const summary = getRunOverview(runId);
    return NextResponse.json(summary);
  } catch (error) {
    return apiError(error, 404);
  }
}
