import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import Busboy from "@fastify/busboy";
import { loadRunnerConfig, type RunnerConfig } from "@/server/config";

const MIB = 1024 * 1024;
export const MAX_UPLOAD_FILE_BYTES = 20 * MIB;
export const MAX_UPLOAD_REQUEST_BYTES = 32 * MIB;
export const MAX_UPLOAD_REQUEST_FILES = 32;
const JOB_ID = /^[a-f0-9]{32}$/i;
const TEMP_FILE = /^\.upload_[a-f0-9]{32}\.part$/;

export class UploadRequestError extends Error {
  constructor(message: string, readonly status: number = 400) {
    super(message);
  }
}

export interface StagedUpload {
  name: string;
  type: string;
  size: number;
  tempPath: string;
}

export function jobUploadDirectory(jobId: string): string {
  if (!JOB_ID.test(jobId)) throw new UploadRequestError("Invalid job ID.");
  return path.join(loadRunnerConfig().uploadsDir, `job_${jobId}`);
}

export function effectiveFileLimit(config = loadRunnerConfig()): number {
  if (!Number.isFinite(config.maxUploadMb) || config.maxUploadMb <= 0) {
    throw new Error("Invalid upload size configuration.");
  }
  return Math.min(Math.floor(config.maxUploadMb * MIB), MAX_UPLOAD_FILE_BYTES);
}

export function validateUploadMetadata(name: string, type: string, config: RunnerConfig = loadRunnerConfig()): void {
  if (!name || name !== name.trim() || [...name].length > 255 || /[/\\\x00-\x1f\x7f]/.test(name)) {
    throw new UploadRequestError("File name is missing or invalid.");
  }
  const ext = path.extname(name).toLowerCase();
  if (!config.allowedExtensions.includes(ext)) {
    throw new UploadRequestError(`Unsupported file extension: ${ext || "(none)"}`);
  }
  if ([...type].length > 255 || /[\x00-\x1f\x7f]/.test(type)) {
    throw new UploadRequestError("File content type is invalid.");
  }
}

export function validateStagedUpload(jobId: string, file: StagedUpload): void {
  const directory = jobUploadDirectory(jobId);
  validateUploadMetadata(file.name, file.type);
  if (path.dirname(path.resolve(file.tempPath)) !== path.resolve(directory) ||
    !TEMP_FILE.test(path.basename(file.tempPath))) {
    throw new UploadRequestError("Upload staging path is invalid.");
  }
  const stat = fs.lstatSync(file.tempPath);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size !== file.size ||
    file.size < 1 || file.size > effectiveFileLimit()) {
    throw new UploadRequestError("Upload file size is invalid.", 413);
  }
}

export function cleanupStagedUploads(files: readonly StagedUpload[]): void {
  for (const file of files) {
    try { fs.unlinkSync(file.tempPath); } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
}

function tempPath(directory: string): string {
  fs.mkdirSync(directory, { recursive: true });
  return path.join(directory, `.upload_${randomUUID().replace(/-/g, "")}.part`);
}

function byteLimiter(limit: number, message: string): Transform {
  let total = 0;
  return new Transform({
    transform(chunk: Buffer, _encoding, callback) {
      total += chunk.length;
      callback(total > limit ? new UploadRequestError(message, 413) : null, chunk);
    },
  });
}

async function writeStagedStream(
  source: Readable, directory: string, name: string, type: string, limit: number,
  signal?: AbortSignal,
): Promise<StagedUpload> {
  const target = tempPath(directory);
  let size = 0;
  const count = new Transform({
    transform(chunk: Buffer, _encoding, callback) {
      size += chunk.length;
      callback(size > limit ? new UploadRequestError(`File '${name}' exceeds the upload limit.`, 413) : null, chunk);
    },
  });
  let truncated = false;
  source.on("limit", () => { truncated = true; });
  try {
    await pipeline(source, count, fs.createWriteStream(target, { flags: "wx" }), { signal });
    if (truncated || (source as Readable & { truncated?: boolean }).truncated) {
      throw new UploadRequestError(`File '${name}' exceeds the upload limit.`, 413);
    }
    if (size === 0) throw new UploadRequestError("Empty files cannot be uploaded.");
    return { name, type, size, tempPath: target };
  } catch (error) {
    fs.rmSync(target, { force: true });
    throw error;
  }
}

function boundedRequestBody(request: Request): Readable {
  if (!request.body) throw new UploadRequestError("Upload body is empty.");
  const declared = request.headers.get("content-length");
  if (declared !== null) {
    if (!/^\d+$/.test(declared)) throw new UploadRequestError("Invalid Content-Length header.");
    if (BigInt(declared) > BigInt(MAX_UPLOAD_REQUEST_BYTES)) {
      throw new UploadRequestError("Upload request exceeds 32 MiB.", 413);
    }
  }
  return Readable.fromWeb(request.body as Parameters<typeof Readable.fromWeb>[0]);
}

async function readBoundedJson(request: Request): Promise<Buffer> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of boundedRequestBody(request)) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk as Uint8Array);
    size += bytes.length;
    if (size > MAX_UPLOAD_REQUEST_BYTES) throw new UploadRequestError("Upload request exceeds 32 MiB.", 413);
    chunks.push(bytes);
  }
  return Buffer.concat(chunks, size);
}

async function stageJson(request: Request, directory: string, config: RunnerConfig): Promise<StagedUpload[]> {
  let payload: unknown;
  try {
    payload = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(await readBoundedJson(request)));
  } catch (error) {
    if (error instanceof UploadRequestError) throw error;
    throw new UploadRequestError("Malformed JSON upload.");
  }
  if (!payload || typeof payload !== "object" || !Array.isArray((payload as { files?: unknown }).files)) {
    throw new UploadRequestError("JSON upload requires a files array.");
  }
  const items = (payload as { files: unknown[] }).files;
  if (items.length < 1 || items.length > MAX_UPLOAD_REQUEST_FILES) {
    throw new UploadRequestError("Upload requires 1–32 files.", items.length > MAX_UPLOAD_REQUEST_FILES ? 413 : 400);
  }
  const staged: StagedUpload[] = [];
  try {
    for (const raw of items) {
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new UploadRequestError("Invalid JSON file.");
      const item = raw as Record<string, unknown>;
      const name = item.name;
      const type = item.type ?? "application/octet-stream";
      const bytes = item.bytes;
      if (typeof name !== "string" || typeof type !== "string" || !Array.isArray(bytes) ||
        bytes.length < 1 ||
        bytes.some((value) => !Number.isInteger(value) || value < 0 || value > 255)) {
        throw new UploadRequestError("JSON file bytes must be nonempty integers from 0 to 255.");
      }
      if (bytes.length > effectiveFileLimit(config)) {
        throw new UploadRequestError(`File '${name}' exceeds the upload limit.`, 413);
      }
      validateUploadMetadata(name, type, config);
      const target = tempPath(directory);
      try {
        fs.writeFileSync(target, Uint8Array.from(bytes), { flag: "wx" });
        staged.push({ name, type, size: bytes.length, tempPath: target });
      } catch (error) {
        fs.rmSync(target, { force: true });
        throw error;
      }
    }
    return staged;
  } catch (error) {
    cleanupStagedUploads(staged);
    throw error;
  }
}

async function stageMultipart(
  request: Request, directory: string, config: RunnerConfig,
): Promise<StagedUpload[]> {
  const originalType = request.headers.get("content-type") ?? "";
  let parser: ReturnType<typeof Busboy>;
  try {
    parser = new Busboy({
      headers: { "content-type": originalType },
      limits: { files: MAX_UPLOAD_REQUEST_FILES, parts: MAX_UPLOAD_REQUEST_FILES, fields: 0,
        fileSize: effectiveFileLimit(config), fieldSize: 0, headerPairs: 32, headerSize: 8192 },
    });
  } catch {
    throw new UploadRequestError("Malformed multipart upload.");
  }
  const input = boundedRequestBody(request);
  const writes: Promise<StagedUpload | null>[] = [];
  let failure: Error | null = null;
  const fail = (error: Error) => {
    failure ??= error;
    parser.destroy(error);
    input.destroy(error);
  };
  parser.on("file", (field, stream, name, _encoding, type) => {
    try {
      if (field !== "files") throw new UploadRequestError("Unexpected multipart file field.");
      validateUploadMetadata(name, type, config);
      writes.push(writeStagedStream(stream, directory, name, type, effectiveFileLimit(config), request.signal)
        .catch((error: unknown) => { fail(error instanceof Error ? error : new Error("Upload write failed.")); return null; }));
    } catch (error) {
      stream.resume();
      fail(error instanceof Error ? error : new Error("Invalid multipart file."));
    }
  });
  parser.on("field", () => fail(new UploadRequestError("Multipart fields are not supported.")));
  parser.on("filesLimit", () => fail(new UploadRequestError("Upload exceeds 32 files.", 413)));
  parser.on("partsLimit", () => fail(new UploadRequestError("Upload exceeds 32 parts.", 413)));
  parser.on("fieldsLimit", () => fail(new UploadRequestError("Multipart fields are not supported.")));
  try {
    await pipeline(input, byteLimiter(MAX_UPLOAD_REQUEST_BYTES, "Upload request exceeds 32 MiB."), parser,
      { signal: request.signal });
    const results = await Promise.all(writes);
    if (failure) throw failure;
    const staged = results.filter((result): result is StagedUpload => result !== null);
    if (!staged.length) throw new UploadRequestError("Upload requires at least one nonempty file.");
    return staged;
  } catch (error) {
    const results = await Promise.all(writes);
    cleanupStagedUploads(results.filter((result): result is StagedUpload => result !== null));
    if (failure) throw failure;
    if (error instanceof UploadRequestError) throw error;
    throw new UploadRequestError("Multipart upload was incomplete or malformed.");
  }
}

export async function stageUploadRequest(request: Request, jobId: string): Promise<StagedUpload[]> {
  const config = loadRunnerConfig();
  const directory = jobUploadDirectory(jobId);
  const type = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (type === "multipart/form-data") return stageMultipart(request, directory, config);
  if (type === "application/json") return stageJson(request, directory, config);
  if (type === "application/octet-stream") {
    const name = request.headers.get("x-file-name")?.trim() ?? "";
    const fileType = request.headers.get("x-file-type")?.trim() || "application/octet-stream";
    validateUploadMetadata(name, fileType, config);
    return [await writeStagedStream(boundedRequestBody(request), directory, name, fileType,
      effectiveFileLimit(config), request.signal)];
  }
  throw new UploadRequestError("Unsupported upload content type.", 415);
}

export async function stageFileObject(jobId: string, file: File): Promise<StagedUpload> {
  const config = loadRunnerConfig();
  validateUploadMetadata(file.name, file.type, config);
  if (file.size < 1 || file.size > effectiveFileLimit(config)) {
    throw new UploadRequestError(`File '${file.name}' exceeds the upload limit.`, 413);
  }
  return writeStagedStream(Readable.fromWeb(file.stream() as Parameters<typeof Readable.fromWeb>[0]),
    jobUploadDirectory(jobId), file.name, file.type, effectiveFileLimit(config));
}
