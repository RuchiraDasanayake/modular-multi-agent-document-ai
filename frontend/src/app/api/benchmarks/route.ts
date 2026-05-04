import { NextResponse } from "next/server";
import { apiError } from "@/server/api/response";
import { getLatestBenchmarkRun, listBenchmarkRuns } from "@/server/benchmarks";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const runs = listBenchmarkRuns();
    const latest = getLatestBenchmarkRun();
    return NextResponse.json({ runs, latest });
  } catch (error) {
    return apiError(error, 500);
  }
}
