import fs from "node:fs";
import path from "node:path";
import { getJobOrThrow } from "@/server/jobs";
import { requireJob } from "@/server/access";
import { requireUser } from "@/server/auth";
import { loadRunnerConfig } from "@/server/config";
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
    case ".xlsx":
      return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    case ".pptx":
      return "application/vnd.openxmlformats-officedocument.presentationml.presentation";
    case ".html":
      return "text/html; charset=utf-8";
    case ".eml":
      return "message/rfc822";
    default:
      return "application/octet-stream";
  }
}

export async function GET(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId, docId } = await params;
    requireJob(jobId, user);
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

    const uploadsRoot = path.resolve(loadRunnerConfig().uploadsDir);
    const expectedUploadsPath = ensurePathInside(uploadsRoot, path.resolve(uploadsRoot, `job_${jobId}`));
    if (path.resolve(uploadsPath) !== expectedUploadsPath) {
      throw new Error("Job uploads path is invalid");
    }
    const target = ensurePathInside(expectedUploadsPath, path.resolve(expectedUploadsPath, document.storedName));
    if (!fs.existsSync(target)) {
      return new Response(JSON.stringify({ error: "Original document not found" }), {
        status: 404,
        headers: {
          "Content-Type": "application/json",
          ...NO_STORE_HEADERS,
        },
      });
    }
    const realUploadsRoot = fs.realpathSync(uploadsRoot);
    const realUploadsPath = ensurePathInside(realUploadsRoot, fs.realpathSync(expectedUploadsPath));
    if (realUploadsPath !== path.join(realUploadsRoot, `job_${jobId}`)) {
      throw new Error("Job uploads path is invalid");
    }
    const realTarget = ensurePathInside(realUploadsPath, fs.realpathSync(target));
    if (!fs.statSync(realTarget).isFile()) {
      return new Response(JSON.stringify({ error: "Original document not found" }), {
        status: 404,
        headers: {
          "Content-Type": "application/json",
          ...NO_STORE_HEADERS,
        },
      });
    }

    const url = new URL(request.url);
    const nativeFormat = /\.(docx|xlsx|pptx|html|eml)$/i.test(document.fileName);
    const download = nativeFormat || url.searchParams.get("download") === "1";
    const body = fs.readFileSync(realTarget);

    return new Response(body, {
      status: 200,
      headers: {
        ...NO_STORE_HEADERS,
        "Content-Type": guessContentType(document.fileName),
        "X-Content-Type-Options": "nosniff",
        ...(nativeFormat ? { "Content-Security-Policy": "sandbox" } : {}),
        "Content-Length": String(body.byteLength),
        "Content-Disposition": `${download ? "attachment" : "inline"}; filename="${encodeURIComponent(document.fileName)}"`,
      },
    });
  } catch (error) {
    return apiError(error, 400);
  }
}
