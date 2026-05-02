"use client";

import { useMemo, useState } from "react";

interface JsonViewerProps {
  title?: string;
  value: unknown;
}

export function JsonViewer({ title, value }: JsonViewerProps) {
  const [copied, setCopied] = useState(false);
  const text = useMemo(() => JSON.stringify(value, null, 2), [value]);

  const onCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  };

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
        <span>{title ?? "Raw JSON"}</span>
        <button
          type="button"
          onClick={onCopy}
          className="rounded-md border border-slate-300 px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="max-h-[360px] overflow-auto bg-white p-3 text-xs leading-relaxed text-slate-700 dark:bg-slate-950 dark:text-slate-200">
        {text}
      </pre>
    </div>
  );
}
