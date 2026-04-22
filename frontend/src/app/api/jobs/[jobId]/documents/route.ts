import { NextResponse } from "next/server";
import { addDocumentsToJob } from "@/server/jobs";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string }>;
}

export async function POST(request: Request, { params }: Params) {
  try {
    const { jobId } = await params;
    const form = await request.formData();
    const files = form
      .getAll("files")
      .filter((entry): entry is File => entry instanceof File && entry.size > 0);
    const updated = await addDocumentsToJob(jobId, files);
    return NextResponse.json(updated, { status: 201 });
  } catch (error) {
    return apiError(error, 400);
  }
}
