const MIB = 1024 * 1024;
export const CLIENT_FILE_LIMIT = 20 * MIB;
export const CLIENT_BATCH_LIMIT = 30 * MIB;
export const CLIENT_BATCH_FILES = 8;

export interface UploadProgress<T> {
  uploaded: number;
  total: number;
  latest: T;
}

export class UploadBatchError<T> extends Error {
  constructor(
    message: string,
    readonly uploaded: number,
    readonly total: number,
    readonly remaining: File[],
    readonly latest: T | null,
    readonly retryKey: string,
  ) {
    super(message);
  }
}

export function planUploadBatches(files: readonly File[]): File[][] {
  if (files.length === 0) return [];
  const batches: File[][] = [];
  let current: File[] = [];
  let bytes = 0;
  for (const file of files) {
    if (file.size < 1 || file.size > CLIENT_FILE_LIMIT) {
      throw new Error(`File '${file.name}' must be between 1 byte and 20 MiB.`);
    }
    if (!file.name || file.name.length > 255 || /[/\\\x00-\x1f\x7f]/.test(file.name)) {
      throw new Error(`File name '${file.name}' is invalid.`);
    }
    if (current.length === CLIENT_BATCH_FILES || bytes + file.size > CLIENT_BATCH_LIMIT) {
      batches.push(current);
      current = [];
      bytes = 0;
    }
    current.push(file);
    bytes += file.size;
  }
  if (current.length) batches.push(current);
  return batches;
}

export async function uploadInBatches<T>(
  files: readonly File[],
  send: (batch: File[], idempotencyKey: string) => Promise<T>,
  onProgress?: (progress: UploadProgress<T>) => void,
  firstBatchKey?: string,
): Promise<T> {
  const batches = planUploadBatches(files);
  if (!batches.length) throw new Error("Select at least one file.");
  let uploaded = 0;
  let latest: T | null = null;
  for (const [index, batch] of batches.entries()) {
    const key = index === 0 && firstBatchKey ? firstBatchKey : crypto.randomUUID().replaceAll("-", "");
    try {
      latest = await send(batch, key);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Upload failed.";
      throw new UploadBatchError(message, uploaded, files.length, files.slice(uploaded), latest, key);
    }
    uploaded += batch.length;
    onProgress?.({ uploaded, total: files.length, latest });
  }
  return latest as T;
}
