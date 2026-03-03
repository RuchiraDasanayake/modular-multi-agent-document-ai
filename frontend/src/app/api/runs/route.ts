import { NextResponse } from "next/server";
import { listRuns } from "@/server/artifacts";
import { listJobs } from "@/server/jobs";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const runs = listRuns();
    const jobs = listJobs(20);
    return NextResponse.json({ runs, jobs });
  } catch (error) {
    return apiError(error, 500);
  }
}
