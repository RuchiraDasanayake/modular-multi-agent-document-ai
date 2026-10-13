import { NextResponse } from "next/server";
import { requireJob } from "@/server/access";
import { AccessError, requireUser } from "@/server/auth";
import { getProductAutoReviewedBatchExport } from "@/server/product-auto";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string; runId: string }>;
}

const noStore = { "Cache-Control": "no-store, max-age=0", "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy": "sandbox" };

export async function GET(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId, runId } = await params;
    requireJob(jobId, user);
    const lines = getProductAutoReviewedBatchExport(jobId, runId);
    let next = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (next < lines.length) controller.enqueue(lines[next++]);
        else controller.close();
      },
    });
    return new Response(stream, { headers: {
      ...noStore,
      "Content-Type": "application/x-ndjson; charset=utf-8",
      "Content-Disposition": `attachment; filename="docai-${runId}-reviewed-v1.jsonl"`,
    } });
  } catch (error) {
    if (error instanceof AccessError) {
      return NextResponse.json({ error: error.message }, { status: error.statusCode, headers: noStore });
    }
    return NextResponse.json({ error: "Could not export reviewed batch." }, { status: 500, headers: noStore });
  }
}
