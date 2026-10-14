import { AccessError, requireUser } from "@/server/auth";
import { previewPage, renderSourcePreview } from "@/server/document-preview";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const HEADERS = { "Cache-Control": "no-store, max-age=0", "X-Content-Type-Options": "nosniff" };

export async function GET(request: Request, { params }: { params: Promise<{ jobId: string; docId: string }> }) {
  try {
    const user = await requireUser(request.headers);
    const { jobId, docId } = await params;
    const page = previewPage(new URL(request.url).searchParams);
    const preview = await renderSourcePreview(jobId, docId, user, page);
    return new Response(new Uint8Array(preview.png), { headers: { ...HEADERS, "Content-Type": "image/png",
      "Content-Length": String(preview.png.length), "Content-Disposition": "inline; filename=source-page.png",
      "X-DocAI-Page": String(preview.page), "X-DocAI-Page-Count": String(preview.pageCount) } });
  } catch (error) {
    return Response.json({ error: error instanceof AccessError ? error.message : "Source preview is unavailable." },
      { status: error instanceof AccessError ? error.statusCode : 503, headers: HEADERS });
  }
}
