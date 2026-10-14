"use client";

import { useRef, useState } from "react";
import { idpoApi } from "@/lib/idpo-api";
import { UploadBatchError } from "@/lib/upload-batches";

const ACCEPTED_FILES = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.txt,.json,.docx,.xlsx,.pptx,.html,.eml";

export function ProductFileUpload({ jobId, disabled, onUploaded }: {
  jobId: string;
  disabled: boolean;
  onUploaded: () => Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState<{ files: File[]; key: string } | null>(null);

  async function upload(files: File[], retryKey?: string) {
    if (!files.length || inFlight.current || disabled) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    setProgress(`Uploading ${files.length} ${files.length === 1 ? "file" : "files"}…`);
    try {
      await idpoApi.uploadJobDocuments(jobId, files, ({ uploaded, total }) => {
        setProgress(`${uploaded} of ${total} files uploaded.`);
      }, retryKey);
      setPending(null);
    } catch (cause) {
      if (cause instanceof UploadBatchError) {
        setPending({ files: cause.remaining, key: cause.retryKey });
        setError(`${cause.uploaded} of ${cause.total} files confirmed. ${cause.message}`);
      } else {
        setError(cause instanceof Error ? cause.message : "Upload failed.");
        setProgress("");
      }
    } finally {
      // Reload even after a lost response: the server may already have stored that batch.
      try { await onUploaded(); }
      catch { setError((current) => `${current ? `${current} ` : ""}Could not refresh the file list. Reload this page to check stored files.`); }
      if (input.current) input.current.value = "";
      inFlight.current = false;
      setBusy(false);
    }
  }

  return <div className="mt-3 space-y-3">
    <input ref={input} type="file" multiple accept={ACCEPTED_FILES} className="sr-only"
      aria-label="Choose documents to upload" disabled={disabled || busy || !!pending}
      onChange={(event) => void upload(Array.from(event.target.files ?? []))} />
    <button type="button" disabled={disabled || busy || !!pending} onClick={() => input.current?.click()}
      className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50">
      {busy ? "Uploading…" : "Upload files"}
    </button>
    <p className="text-xs text-slate-500 dark:text-slate-400">
      PDF, images, TXT, JSON text pages, DOCX, XLSX, PPTX, HTML or EML. Up to 20 MiB per file; large selections upload in batches.
    </p>
    {progress ? <p role="status" className="text-sm text-slate-600 dark:text-slate-300">{progress}</p> : null}
    {error ? <p role="alert" className="text-sm text-rose-700 dark:text-rose-300">{error}</p> : null}
    {pending ? <div className="space-y-2">
      <p className="text-sm text-slate-600 dark:text-slate-300">
        {pending.files.length} files have an unconfirmed upload. Keep this page open and retry with the same request key to avoid duplicate uploads.
      </p>
      <button type="button" disabled={disabled || busy} onClick={() => void upload(pending.files, pending.key)}
        className="rounded-lg border border-cyan-600 px-3 py-2 text-sm font-medium text-cyan-700 disabled:opacity-50 dark:text-cyan-300">
        Retry unconfirmed uploads
      </button>
    </div> : null}
  </div>;
}
