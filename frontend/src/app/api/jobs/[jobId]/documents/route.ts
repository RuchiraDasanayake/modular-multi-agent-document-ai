import { NextResponse } from "next/server";
import { addDocumentsToJob } from "@/server/jobs";
import { requireJob } from "@/server/access";
import { requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string }>;
}

async function readFiles(request: Request): Promise<File[]> {
  const contentType = request.headers.get("content-type")?.toLowerCase() ?? "";
  if (contentType.includes("application/octet-stream")) {
    const name = request.headers.get("x-file-name")?.trim() ?? "";
    if (!name) {
      return [];
    }
    const buffer = await request.arrayBuffer();
    if (buffer.byteLength === 0) {
      return [];
    }
    return [
      new File([buffer], name, {
        type: request.headers.get("x-file-type")?.trim() || "application/octet-stream",
      }),
    ];
  }
  if (contentType.includes("application/json")) {
    const payload = (await request.json()) as { files?: Array<{ name?: string; type?: string; bytes?: number[] }> };
    const items = Array.isArray(payload.files) ? payload.files : [];
    return items
      .map((item) => {
        const name = typeof item?.name === "string" ? item.name.trim() : "";
        const bytes = Array.isArray(item?.bytes) ? item.bytes : [];
        if (!name || bytes.length === 0) {
          return null;
        }
        const normalizedBytes = Uint8Array.from(
          bytes.filter((value): value is number => Number.isInteger(value) && value >= 0 && value <= 255),
        );
        if (normalizedBytes.length === 0) {
          return null;
        }
        return new File([normalizedBytes], name, {
          type: typeof item?.type === "string" ? item.type : "application/octet-stream",
        });
      })
      .filter((entry): entry is File => entry instanceof File && entry.size > 0);
  }

  const form = await request.formData();
  return form
    .getAll("files")
    .filter((entry): entry is File => entry instanceof File && entry.size > 0);
}

export async function POST(request: Request, { params }: Params) {
  try {
    const user = await requireUser(request.headers);
    const { jobId } = await params;
    requireJob(jobId, user);
    const files = await readFiles(request);
    const updated = await addDocumentsToJob(jobId, files);
    return NextResponse.json(updated, { status: 201 });
  } catch (error) {
    return apiError(error, 400);
  }
}
