import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { requireJob } from "@/server/access";
import { AccessError, type AuthenticatedUser } from "@/server/auth";
import { getCommandConfig, loadRunnerConfig } from "@/server/config";

const MAX_SOURCE_BYTES = 20 * 1024 * 1024;
const MAX_OUTPUT_BYTES = 12 * 1024 * 1024;
const MAX_PNG_BYTES = 8 * 1024 * 1024;
const TIMEOUT_MS = 15_000;
const PNG_HEADER = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
let activePreviews = 0;

export type SourcePreview = { png: Buffer; page: number; pageCount: number };

export function previewEnvironment(source: Record<string, string | undefined>): NodeJS.ProcessEnv {
  const allowed = new Set(["path", "pathext", "systemroot", "windir", "comspec", "systemdrive",
    "temp", "tmp", "home", "userprofile", "appdata", "localappdata", "lang", "lc_all"]);
  return { ...Object.fromEntries(Object.entries(source).filter(([key]) => allowed.has(key.toLowerCase()))),
    NODE_ENV: "production", PYTHONNOUSERSITE: "1", PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1" };
}

export function previewPage(query: URLSearchParams): number {
  if ([...query.keys()].some((key) => key !== "page") || query.getAll("page").length > 1) {
    throw new AccessError("Invalid preview options.", 400);
  }
  const page = query.get("page") ?? "1";
  if (!/^[1-9]\d?$/.test(page) || Number(page) > 50) {
    throw new AccessError("Choose a source page from 1 to 50.", 400);
  }
  return Number(page);
}

function sourceBytes(jobId: string, fileId: string, user: AuthenticatedUser): { bytes: Buffer; kind: "pdf" | "image" } {
  const job = requireJob(jobId, user);
  const document = job.documents?.find((item) => item.fileId === fileId);
  if (!document) throw new AccessError("Document not found.", 404);
  const extension = path.extname(document.fileName).toLowerCase();
  if (![".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"].includes(extension)) {
    throw new AccessError("This file has no image preview. Use its source text or download the original.", 415);
  }
  try {
    const uploadsRoot = path.resolve(loadRunnerConfig().uploadsDir);
    const expected = path.join(uploadsRoot, `job_${jobId}`);
    if (!job.uploadsPath || path.resolve(job.uploadsPath) !== expected ||
      path.basename(document.storedName) !== document.storedName || /[/\\]/.test(document.storedName)) throw new Error();
    const realRoot = fs.realpathSync(uploadsRoot);
    const realDirectory = fs.realpathSync(expected);
    if (realDirectory !== path.join(realRoot, `job_${jobId}`)) throw new Error();
    const target = path.join(realDirectory, document.storedName);
    if (fs.lstatSync(target).isSymbolicLink() || path.dirname(fs.realpathSync(target)) !== realDirectory) throw new Error();
    const descriptor = fs.openSync(target, "r");
    try {
      const stat = fs.fstatSync(descriptor);
      if (!stat.isFile()) throw new Error();
      if (stat.size < 1 || stat.size > MAX_SOURCE_BYTES) throw new AccessError("Source exceeds the preview size limit.", 413);
      if (stat.size !== document.size) throw new AccessError("Source file changed. Upload a fresh copy before previewing.", 409);
      const bytes = Buffer.alloc(stat.size);
      let offset = 0;
      while (offset < bytes.length) {
        const read = fs.readSync(descriptor, bytes, offset, bytes.length - offset, offset);
        if (!read) throw new Error();
        offset += read;
      }
      return { bytes, kind: extension === ".pdf" ? "pdf" : "image" };
    } finally { fs.closeSync(descriptor); }
  } catch (error) {
    if (error instanceof AccessError) throw error;
    throw new AccessError("Original document is unavailable for preview.", 404);
  }
}

function parsePreview(output: Buffer, page: number): SourcePreview {
  let value: Record<string, unknown>;
  try { value = JSON.parse(output.toString("utf8")) as Record<string, unknown>; }
  catch { throw new AccessError("The source preview could not be rendered.", 422); }
  if (value?.error === "page_out_of_range") throw new AccessError("That page is not in this source document.", 404);
  if (value?.error === "renderer_unavailable") throw new AccessError("The source preview renderer is unavailable.", 503);
  if (!value || value.page !== page || !Number.isInteger(value.page_count) ||
    Number(value.page_count) < page || Number(value.page_count) > 50 || typeof value.png !== "string" ||
    !/^[A-Za-z0-9+/]+={0,2}$/.test(value.png)) {
    throw new AccessError("This source could not be previewed within the supported image and page limits. Download the original.", 422);
  }
  const png = Buffer.from(value.png, "base64");
  if (png.length < 24 || png.length > MAX_PNG_BYTES || !png.subarray(0, 8).equals(PNG_HEADER) ||
    png.readUInt32BE(16) < 1 || png.readUInt32BE(16) > 1600 || png.readUInt32BE(20) < 1 || png.readUInt32BE(20) > 1600) {
    throw new AccessError("The source preview could not be rendered.", 422);
  }
  return { png, page, pageCount: Number(value.page_count) };
}

export async function renderSourcePreview(jobId: string, fileId: string, user: AuthenticatedUser,
  page: number): Promise<SourcePreview> {
  if (!Number.isInteger(page) || page < 1 || page > 50) throw new AccessError("Invalid source page.", 400);
  // Authorize and resolve the server-owned source before starting a renderer.
  const source = sourceBytes(jobId, fileId, user);
  if (activePreviews >= 2) throw new AccessError("Source preview is busy. Try again shortly.", 503);
  const command = getCommandConfig("idpo_process_auto");
  activePreviews += 1;
  let spawned = false;
  let released = false;
  const release = () => {
    if (!released) { released = true; activePreviews -= 1; }
  };
  try {
    const output = await new Promise<Buffer>((resolve, reject) => {
      const child = spawn(command.program, ["-s", "-m", "idpo.product_auto.source_preview", "--kind", source.kind,
        "--page", String(page)], { cwd: command.cwd, env: previewEnvironment({ ...process.env, ...command.env }),
        stdio: ["pipe", "pipe", "pipe"], shell: false, windowsHide: true });
      spawned = true;
      const chunks: Buffer[] = [];
      let size = 0;
      let stderrSize = 0;
      let settled = false;
      const finish = (error?: Error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (error) reject(error); else resolve(Buffer.concat(chunks));
      };
      const stop = (message: string, status = 422) => {
        try { child.kill("SIGKILL"); } catch { /* Keep the slot until close even if termination failed. */ }
        finish(new AccessError(message, status));
      };
      const timer = setTimeout(() => stop("The source preview timed out. Download the original or try another page.", 504), TIMEOUT_MS);
      child.stdout.on("data", (chunk: Buffer) => {
        if (settled) return;
        size += chunk.length;
        if (size > MAX_OUTPUT_BYTES) stop("The source preview exceeded its output limit.");
        else chunks.push(chunk);
      });
      child.stderr.on("data", (chunk: Buffer) => {
        if (settled) return;
        stderrSize += chunk.length;
        if (stderrSize > 8192) stop("The source preview could not be rendered.");
      });
      child.on("error", () => {
        if (!child.pid) release();
        finish(new AccessError("The source preview renderer is unavailable.", 503));
      });
      child.on("close", (code) => {
        release();
        if (code === 0 || code === 2) finish();
        else finish(new AccessError("The source preview could not be rendered.", 422));
      });
      child.stdin.on("error", () => { /* A stopped renderer can close stdin before all bounded source bytes are sent. */ });
      child.stdin.end(source.bytes);
    });
    return parsePreview(output, page);
  } finally {
    // Once started, only confirmed process closure releases capacity, including after a failed kill.
    if (!spawned) release();
  }
}
