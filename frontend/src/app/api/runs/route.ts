import { NextResponse } from "next/server";
import { listRuns } from "@/server/artifacts";
import { accessibleRunIds, listAccessibleJobs } from "@/server/access";
import { requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const user = await requireUser(request.headers);
    const allowedRunIds = user.role === "admin" ? null : accessibleRunIds(user);
    const runs = listRuns().filter((run) => !allowedRunIds || allowedRunIds.has(run.runId));
    const jobs = listAccessibleJobs(user, 20);
    return NextResponse.json({ runs, jobs });
  } catch (error) {
    return apiError(error, 500);
  }
}
