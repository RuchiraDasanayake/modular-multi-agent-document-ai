import { NextResponse } from "next/server";
import { apiError } from "@/server/api/response";
import { getLatestBenchmarkRun, listBenchmarkRuns } from "@/server/benchmarks";
import { requireAdmin, requireUser } from "@/server/auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    requireAdmin(await requireUser(request.headers));
    const runs = listBenchmarkRuns();
    const latest = getLatestBenchmarkRun();
    return NextResponse.json({ runs, latest });
  } catch (error) {
    return apiError(error, 500);
  }
}
