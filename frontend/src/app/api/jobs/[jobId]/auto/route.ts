import { NextResponse } from "next/server";
import { requireJob } from "@/server/access";
import { AccessError, requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";
import { listProductAutoRuns, productAutoAvailability, startProductAutoRun } from "@/server/product-auto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string }>;
}

const noStore = { "Cache-Control": "no-store, max-age=0" };

export async function GET(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId } = await params;
    const job = requireJob(jobId, user);
    const sourceFiles = (job.documents ?? []).map((document) => ({
      fileId: document.fileId, fileName: document.fileName, selected: document.selected,
    }));
    return NextResponse.json({ ...productAutoAvailability(), sourceFiles, runs: listProductAutoRuns(jobId) }, { headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    return NextResponse.json({ error: "Could not load automatic extraction." }, { status: 500, headers: noStore });
  }
}

export async function POST(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId } = await params;
    requireJob(jobId, user);
    const body: unknown = await request.json();
    const selectedFileIds = body && typeof body === "object" && !Array.isArray(body) &&
      Array.isArray((body as Record<string, unknown>).selectedFileIds)
      ? (body as { selectedFileIds: unknown[] }).selectedFileIds
      : [];
    if (!selectedFileIds.every((item): item is string => typeof item === "string")) {
      return NextResponse.json({ error: "Selected document IDs must be strings." }, { status: 400, headers: noStore });
    }
    const rawSelection = body && typeof body === "object" && !Array.isArray(body)
      ? (body as Record<string, unknown>).approvedRecipe : undefined;
    let approvedRecipe: { recipeId: string; expectedRevision: number } | undefined;
    if (rawSelection !== undefined) {
      if (!rawSelection || typeof rawSelection !== "object" || Array.isArray(rawSelection) ||
        typeof (rawSelection as Record<string, unknown>).recipeId !== "string" ||
        !Number.isSafeInteger((rawSelection as Record<string, unknown>).expectedRevision)) {
        throw new AccessError("Choose an approved recipe and its current revision.", 400);
      }
      approvedRecipe = rawSelection as { recipeId: string; expectedRevision: number };
    }
    const run = await startProductAutoRun(jobId, selectedFileIds, user.role === "admin", approvedRecipe);
    return NextResponse.json(run, { status: 202, headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    if (error instanceof SyntaxError) return NextResponse.json({ error: "Invalid JSON request." }, { status: 400, headers: noStore });
    return NextResponse.json({ error: "Could not start automatic extraction." }, { status: 500, headers: noStore });
  }
}
