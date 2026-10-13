import { NextResponse } from "next/server";
import { requireJob } from "@/server/access";
import { AccessError, requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";
import { confirmProductAutoBrief, getProductAutoBrief, saveProductAutoBrief } from "@/server/product-auto-brief";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params { params: Promise<{ jobId: string }> }

const noStore = { "Cache-Control": "no-store, max-age=0" };

export async function GET(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId } = await params;
    requireJob(jobId, user);
    return NextResponse.json(getProductAutoBrief(jobId), { headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    return NextResponse.json({ error: "Could not load extraction brief." }, { status: 500, headers: noStore });
  }
}

export async function POST(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId } = await params;
    requireJob(jobId, user);
    const input: unknown = await request.json();
    return NextResponse.json({ brief: saveProductAutoBrief(jobId, user.id, input) },
      { status: 201, headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    if (error instanceof SyntaxError) {
      return NextResponse.json({ error: "Invalid JSON request." }, { status: 400, headers: noStore });
    }
    return NextResponse.json({ error: "Could not save extraction brief." }, { status: 500, headers: noStore });
  }
}

export async function PATCH(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId } = await params;
    requireJob(jobId, user);
    const input: unknown = await request.json();
    return NextResponse.json({ brief: confirmProductAutoBrief(jobId, user.id, input) },
      { status: 201, headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    if (error instanceof SyntaxError) {
      return NextResponse.json({ error: "Invalid JSON request." }, { status: 400, headers: noStore });
    }
    return NextResponse.json({ error: "Could not confirm extraction brief." }, { status: 500, headers: noStore });
  }
}
