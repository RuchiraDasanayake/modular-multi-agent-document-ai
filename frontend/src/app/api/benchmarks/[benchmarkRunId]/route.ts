import { NextResponse } from "next/server";
import { apiError } from "@/server/api/response";
import { getBenchmarkEvidence } from "@/server/benchmarks";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ benchmarkRunId: string }>;
}

export async function GET(_: Request, { params }: Params) {
  try {
    const { benchmarkRunId } = await params;
    const evidence = getBenchmarkEvidence(benchmarkRunId);
    return NextResponse.json(evidence);
  } catch (error) {
    return apiError(error, 404);
  }
}
