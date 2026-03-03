import { NextResponse } from "next/server";
import { readRunFile } from "@/server/artifacts";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ runId: string }>;
}

export async function GET(request: Request, { params }: Params) {
  try {
    const { runId } = await params;
    const url = new URL(request.url);
    const relativePath = url.searchParams.get("path") ?? "";
    const file = readRunFile(runId, relativePath);
    return NextResponse.json(file);
  } catch (error) {
    return apiError(error, 400);
  }
}
