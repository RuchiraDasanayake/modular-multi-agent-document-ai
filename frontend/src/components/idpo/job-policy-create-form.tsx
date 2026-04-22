"use client";

import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";

interface JobPolicyCreateFormProps {
  jobId: string;
}

function splitCommaSeparated(value: string): string[] {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

export function JobPolicyCreateForm({ jobId }: JobPolicyCreateFormProps) {
  const router = useRouter();
  const [policyId, setPolicyId] = useState("");
  const [name, setName] = useState("");
  const [executionProfile, setExecutionProfile] = useState<"fast_local" | "balanced" | "heavy_cloud">("balanced");
  const [routeBins, setRouteBins] = useState("");
  const [contentProfiles, setContentProfiles] = useState("");
  const [vendorClusters, setVendorClusters] = useState("");
  const [docTypes, setDocTypes] = useState("");
  const [explicitEntities, setExplicitEntities] = useState("");
  const [instructions, setInstructions] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setSaved("");
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/policies`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          policyId,
          name,
          executionProfile,
          routeBins: splitCommaSeparated(routeBins),
          contentProfiles: splitCommaSeparated(contentProfiles),
          vendorClusters: splitCommaSeparated(vendorClusters),
          docTypes: splitCommaSeparated(docTypes),
          explicitEntities: splitCommaSeparated(explicitEntities),
          instructions: instructions.trim(),
        }),
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { error?: string };
        throw new Error(payload.error || `Request failed (${response.status})`);
      }

      setPolicyId("");
      setName("");
      setExecutionProfile("balanced");
      setRouteBins("");
      setContentProfiles("");
      setVendorClusters("");
      setDocTypes("");
      setExplicitEntities("");
      setInstructions("");
      setSaved("Custom policy added to this job.");
      router.refresh();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Failed to create policy");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <label className="text-sm">
          <span className="mb-1 block text-slate-700 dark:text-slate-300">Policy ID</span>
          <input
            value={policyId}
            onChange={(event) => setPolicyId(event.target.value)}
            placeholder="vendor_fast_local"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-slate-700 dark:text-slate-300">Name</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Vendor fast local"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-slate-700 dark:text-slate-300">Execution profile</span>
          <select
            value={executionProfile}
            onChange={(event) => setExecutionProfile(event.target.value as "fast_local" | "balanced" | "heavy_cloud")}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          >
            <option value="fast_local">fast_local</option>
            <option value="balanced">balanced</option>
            <option value="heavy_cloud">heavy_cloud</option>
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-slate-700 dark:text-slate-300">Route bins</span>
          <input
            value={routeBins}
            onChange={(event) => setRouteBins(event.target.value)}
            placeholder="standard, heavy"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-slate-700 dark:text-slate-300">Content profiles</span>
          <input
            value={contentProfiles}
            onChange={(event) => setContentProfiles(event.target.value)}
            placeholder="table-heavy, form-centric"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-slate-700 dark:text-slate-300">Vendor clusters</span>
          <input
            value={vendorClusters}
            onChange={(event) => setVendorClusters(event.target.value)}
            placeholder="acme, unknown"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-slate-700 dark:text-slate-300">Doc types</span>
          <input
            value={docTypes}
            onChange={(event) => setDocTypes(event.target.value)}
            placeholder="invoice, form"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </label>
        <label className="text-sm md:col-span-2">
          <span className="mb-1 block text-slate-700 dark:text-slate-300">Explicit fields</span>
          <input
            value={explicitEntities}
            onChange={(event) => setExplicitEntities(event.target.value)}
            placeholder="invoice_number, total_amount, due_date"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </label>
      </div>

      <label className="block text-sm">
        <span className="mb-1 block text-slate-700 dark:text-slate-300">Operator instructions</span>
        <textarea
          value={instructions}
          onChange={(event) => setInstructions(event.target.value)}
          rows={4}
          placeholder="Optional note for this job-specific policy. The actual execution path is driven by the structured profile above."
          className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
      </label>

      {error ? (
        <div className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      ) : null}
      {saved ? (
        <div className="rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:border-emerald-700/40 dark:bg-emerald-900/20 dark:text-emerald-300">
          {saved}
        </div>
      ) : null}

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {saving ? "Saving..." : "Add policy"}
        </button>
      </div>
    </form>
  );
}
