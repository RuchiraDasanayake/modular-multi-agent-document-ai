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
    if (body && typeof body === "object" && !Array.isArray(body) &&
      Object.keys(body).some((key) => !["selectedFileIds", "approvedRecipe", "confirmedBrief"].includes(key))) {
      throw new AccessError("Extraction options must be configured on the server.", 400);
    }
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
    const rawBrief = body && typeof body === "object" && !Array.isArray(body)
      ? (body as Record<string, unknown>).confirmedBrief : undefined;
    let confirmedBrief: { expectedRevision: number; payloadSha256: string;
      phase: "preview" | "batch"; previewRunId?: string } | undefined;
    if (rawBrief !== undefined) {
      if (!rawBrief || typeof rawBrief !== "object" || Array.isArray(rawBrief)) {
        throw new AccessError("Choose a confirmed schema revision.", 400);
      }
      const selection = rawBrief as Record<string, unknown>;
      if (Object.keys(selection).some((key) => !["expectedRevision", "payloadSha256", "phase", "previewRunId"].includes(key)) ||
        !Number.isSafeInteger(selection.expectedRevision) || typeof selection.expectedRevision !== "number" ||
        selection.expectedRevision < 2 || typeof selection.payloadSha256 !== "string" ||
        !/^[a-f0-9]{64}$/.test(selection.payloadSha256) ||
        !["preview", "batch"].includes(String(selection.phase)) ||
        selection.previewRunId !== undefined && typeof selection.previewRunId !== "string") {
        throw new AccessError("Choose a confirmed schema revision and phase.", 400);
      }
      confirmedBrief = selection as typeof confirmedBrief;
    }
    const requestKey = request.headers.get("idempotency-key");
    if (process.env.IDPO_AUTO_MODEL?.trim() && user.role === "admin" && requestKey === null) {
      throw new AccessError("An Idempotency-Key header is required for model-backed extraction.", 400);
    }
    const run = await startProductAutoRun(jobId, selectedFileIds, user.role === "admin",
      approvedRecipe, confirmedBrief,
      requestKey === null ? undefined : { key: requestKey, actorUserId: user.id });
    return NextResponse.json(run, { status: 202, headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    if (error instanceof SyntaxError) return NextResponse.json({ error: "Invalid JSON request." }, { status: 400, headers: noStore });
    return NextResponse.json({ error: "Could not start automatic extraction." }, { status: 500, headers: noStore });
  }
}
