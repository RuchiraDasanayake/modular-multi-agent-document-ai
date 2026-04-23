"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

interface JobPolicyRuntimeToggleProps {
  jobId: string;
  policyId: string;
  runtimeEnabled: boolean;
  runtimeToggleAllowed: boolean;
}

export function JobPolicyRuntimeToggle({
  jobId,
  policyId,
  runtimeEnabled,
  runtimeToggleAllowed,
}: JobPolicyRuntimeToggleProps) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [isPending, startTransition] = useTransition();

  async function handleToggle() {
    if (!runtimeToggleAllowed || isPending) {
      return;
    }

    setError("");
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/policies`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          policyId,
          enabled: !runtimeEnabled,
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { error?: string };
        throw new Error(payload.error || `Request failed (${response.status})`);
      }

      startTransition(() => {
        router.refresh();
      });
    } catch (toggleError) {
      setError(toggleError instanceof Error ? toggleError.message : "Failed to update policy runtime state");
    }
  }

  if (!runtimeToggleAllowed) {
    return <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Always on</span>;
  }

  return (
    <div className="space-y-1">
      <button
        type="button"
        onClick={handleToggle}
        disabled={isPending}
        className={
          runtimeEnabled
            ? "rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 transition hover:border-emerald-400 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-emerald-700/40 dark:bg-emerald-900/20 dark:text-emerald-200"
            : "rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 transition hover:border-cyan-300 hover:text-cyan-700 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:border-cyan-700/40 dark:hover:text-cyan-200"
        }
      >
        {isPending ? "Saving..." : runtimeEnabled ? "Disable" : "Enable"}
      </button>
      <div className="text-[11px] text-slate-500 dark:text-slate-400">{runtimeEnabled ? "Enabled for this job" : "Disabled for this job"}</div>
      {error ? <div className="text-[11px] text-rose-600 dark:text-rose-300">{error}</div> : null}
    </div>
  );
}
