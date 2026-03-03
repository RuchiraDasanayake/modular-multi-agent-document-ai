import { NextResponse } from "next/server";
import { getJob } from "@/server/jobs";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string }>;
}

export async function GET(_: Request, { params }: Params) {
  try {
    const { jobId } = await params;
    const job = getJob(jobId);
    if (!job) {
      return NextResponse.json({ error: "Job not found" }, { status: 404 });
    }
    return NextResponse.json(job);
  } catch (error) {
    return apiError(error, 400);
  }
}
