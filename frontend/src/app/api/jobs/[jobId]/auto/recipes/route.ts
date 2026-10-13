import { NextResponse } from "next/server";
import { requireJob } from "@/server/access";
import { AccessError, requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";
import { createProductAutoRecipeDraft, listProductAutoRecipes } from "@/server/product-auto-recipes";

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
    requireJob(jobId, user);
    return NextResponse.json({ recipes: listProductAutoRecipes(jobId) }, { headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    return NextResponse.json({ error: "Could not load recipes." }, { status: 500, headers: noStore });
  }
}

export async function POST(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId } = await params;
    requireJob(jobId, user);
    const body: unknown = await request.json();
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      throw new AccessError("Invalid recipe request.", 400);
    }
    const { runId, docId, expectedReviewRevision, familyName } = body as Record<string, unknown>;
    if (typeof runId !== "string" || typeof docId !== "string" ||
      typeof expectedReviewRevision !== "number") {
      throw new AccessError("A source document and review revision are required.", 400);
    }
    const recipe = createProductAutoRecipeDraft(jobId, runId, docId, user.id,
      expectedReviewRevision, familyName);
    return NextResponse.json({ recipe }, { status: 201, headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    if (error instanceof SyntaxError) return NextResponse.json({ error: "Invalid JSON request." }, { status: 400, headers: noStore });
    return NextResponse.json({ error: "Could not create recipe draft." }, { status: 500, headers: noStore });
  }
}
