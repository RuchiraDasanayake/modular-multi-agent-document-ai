"use client";

import { useEffect, useState } from "react";
import { idpoApi } from "@/lib/idpo-api";

export function DocumentSourcePreview({ jobId, fileId, fileName, page, onPageChange }: {
  jobId: string; fileId: string; fileName: string; page: number; onPageChange: (page: number) => void;
}) {
  const [preview, setPreview] = useState<{ key: string; url?: string; pageCount?: number; error?: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const key = `${jobId}/${fileId}/${page}/${attempt}`;

  useEffect(() => {
    const controller = new AbortController();
    let imageUrl: string | undefined;
    void idpoApi.getDocumentPreview(jobId, fileId, page, controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      imageUrl = URL.createObjectURL(result.image);
      setPreview({ key, url: imageUrl, pageCount: result.pageCount });
    }).catch((cause) => {
      if (!controller.signal.aborted) setPreview({ key,
        error: cause instanceof Error ? cause.message : "Source preview is unavailable." });
    });
    return () => {
      controller.abort();
      if (imageUrl) URL.revokeObjectURL(imageUrl);
    };
  }, [jobId, fileId, page, key]);

  const current = preview?.key === key ? preview : null;
  return <div className="mt-4 space-y-3">
    {!current ? <p role="status" className="text-sm text-slate-600 dark:text-slate-300">Loading source page {page}…</p> : null}
    {current?.error ? <div className="rounded-lg border border-amber-300 p-3 text-sm dark:border-amber-700">
      <p role="alert">{current.error}</p>
      <p className="mt-1">You can inspect the extracted text below or open the original file.</p>
      <button type="button" onClick={() => setAttempt((value) => value + 1)} className="mt-2 rounded-lg border px-3 py-2">Retry source preview</button>
    </div> : null}
    {current?.url ? <>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <button type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}
          className="rounded-lg border border-slate-300 px-3 py-2 disabled:opacity-40 dark:border-slate-700">Previous page</button>
        <span>Page {page} of {current.pageCount}</span>
        <button type="button" onClick={() => setZoomed((value) => !value)} aria-pressed={zoomed}
          className="rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700">{zoomed ? "Fit width" : "Zoom in"}</button>
        <button type="button" disabled={page >= (current.pageCount ?? page)} onClick={() => onPageChange(page + 1)}
          className="rounded-lg border border-slate-300 px-3 py-2 disabled:opacity-40 dark:border-slate-700">Next page</button>
      </div>
      <div className="max-h-[65vh] overflow-auto rounded-xl border border-slate-200 bg-white dark:border-slate-700">
        {/* Authenticated raster bytes stay in a private browser blob; no public image optimizer is used. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={current.url} alt={`Source page ${page}: ${fileName}`} className="h-auto max-w-none"
          style={{ width: zoomed ? "auto" : "100%" }}
          onError={() => setPreview({ key, error: "The browser could not display this source page." })} />
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400">Local page preview. Use the original file when you need its full resolution.</p>
    </> : null}
  </div>;
}
