import { NextResponse } from "next/server";
import { AccessError, requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";
import { suggestProductAutoBrief } from "@/server/product-auto-brief-suggest";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params { params: Promise<{ jobId: string }> }
const noStore = { "Cache-Control": "no-store, max-age=0" };

async function boundedJson(request: Request): Promise<unknown> {
  if (!request.body) throw new AccessError("A pinned draft request is required.", 400);
  const reader = request.body.getReader();
  const chunks: Buffer[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > 2048) {
      await reader.cancel();
      throw new AccessError("Schema suggestion request is too large.", 413);
    }
    chunks.push(Buffer.from(value));
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown;
}

export async function POST(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId } = await params;
    const input = await boundedJson(request);
    return NextResponse.json(await suggestProductAutoBrief(jobId, user, input), { headers: noStore });
  } catch (error) {
    if (error instanceof AccessError) return apiError(error);
    if (error instanceof SyntaxError) {
      return NextResponse.json({ error: "Invalid JSON request." }, { status: 400, headers: noStore });
    }
    return NextResponse.json({ error: "Could not draft AI field suggestions." }, { status: 500, headers: noStore });
  }
}
