import fs from "node:fs";
import path from "node:path";
import { getJobOrThrow } from "@/server/jobs";
import { ensurePathInside } from "@/server/paths";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
};

interface Params {
  params: Promise<{ jobId: string; docId: string }>;
}

function guessContentType(filename: string): string {
  switch (path.extname(filename).toLowerCase()) {
    case ".pdf":
      return "application/pdf";
    case ".png":
      return "image/png";
    case ".jpg":
    case ".jpeg":
      return "image/jpeg";
    case ".gif":
      return "image/gif";
    case ".webp":
      return "image/webp";
    case ".bmp":
      return "image/bmp";
    case ".tif":
    case ".tiff":
      return "image/tiff";
    case ".txt":
      return "text/plain; charset=utf-8";
    case ".json":
      return "application/json; charset=utf-8";
    case ".docx":
      return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    default:
      return "application/octet-stream";
  }
}

export async function GET(request: Request, { params }: Params) {
  try {
    const { jobId, docId } = await params;
    const job = getJobOrThrow(jobId);
    const document = (job.documents ?? []).find((entry) => entry.fileId === docId);
    if (!document) {
      return new Response(JSON.stringify({ error: "Document not found" }), {
        status: 404,
        headers: {
          "Content-Type": "application/json",
          ...NO_STORE_HEADERS,
        },
      });
    }

    const uploadsPath = job.uploadsPath?.trim();
    if (!uploadsPath) {
      throw new Error("Job uploads path is missing");
    }

    const target = ensurePathInside(uploadsPath, path.join(uploadsPath, document.storedName));
    if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
      return new Response(JSON.stringify({ error: "Original document not found" }), {
        status: 404,
        headers: {
          "Content-Type": "application/json",
          ...NO_STORE_HEADERS,
        },
      });
    }

    const url = new URL(request.url);
    const download = url.searchParams.get("download") === "1";
    const body = fs.readFileSync(target);

    return new Response(body, {
      status: 200,
      headers: {
        ...NO_STORE_HEADERS,
        "Content-Type": guessContentType(document.fileName),
        "Content-Length": String(body.byteLength),
        "Content-Disposition": `${download ? "attachment" : "inline"}; filename="${encodeURIComponent(document.fileName)}"`,
      },
    });
  } catch (error) {
    return apiError(error, 400);
  }
}
