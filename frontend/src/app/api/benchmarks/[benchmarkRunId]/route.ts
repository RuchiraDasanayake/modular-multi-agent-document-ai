import { NextResponse } from "next/server";
import { apiError } from "@/server/api/response";
import { getBenchmarkEvidence } from "@/server/benchmarks";
import { requireAdmin, requireUser } from "@/server/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ benchmarkRunId: string }>;
}

export async function GET(request: Request, { params }: Params) {
  try {
    requireAdmin(await requireUser(request.headers));
    const { benchmarkRunId } = await params;
    const evidence = getBenchmarkEvidence(benchmarkRunId);
    return NextResponse.json(evidence);
  } catch (error) {
    return apiError(error, 404);
  }
}
