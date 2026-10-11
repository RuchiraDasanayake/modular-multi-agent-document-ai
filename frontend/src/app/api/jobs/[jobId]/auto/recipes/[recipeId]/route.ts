import { NextResponse } from "next/server";
import { requireJob } from "@/server/access";
import { AccessError, requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";
import { getProductAutoRecipe, transitionProductAutoRecipe } from "@/server/product-auto-recipes";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string; recipeId: string }>;
}

const noStore = { "Cache-Control": "no-store, max-age=0" };

export async function GET(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId, recipeId } = await params;
    requireJob(jobId, user);
    return NextResponse.json(getProductAutoRecipe(jobId, recipeId), { headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    return NextResponse.json({ error: "Could not load recipe." }, { status: 500, headers: noStore });
  }
}

export async function POST(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId, recipeId } = await params;
    requireJob(jobId, user);
    const body: unknown = await request.json();
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      throw new AccessError("Invalid recipe request.", 400);
    }
    const { action, expectedRevision, confirmedRowGroups } = body as Record<string, unknown>;
    if ((action !== "approve" && action !== "disable") || typeof expectedRevision !== "number") {
      throw new AccessError("A valid recipe action and revision are required.", 400);
    }
    const recipe = transitionProductAutoRecipe(jobId, recipeId, user.id,
      expectedRevision, action, confirmedRowGroups);
    return NextResponse.json({ recipe }, { headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    if (error instanceof SyntaxError) return NextResponse.json({ error: "Invalid JSON request." }, { status: 400, headers: noStore });
    return NextResponse.json({ error: "Could not update recipe." }, { status: 500, headers: noStore });
  }
}
