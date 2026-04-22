import Link from "next/link";
import { notFound } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { getJobPolicyDetail } from "@/server/policies";

function formatLabel(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatValue(value: unknown): string {
  if (value == null) {
    return "-";
  }
  if (typeof value === "string") {
    return value || "-";
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function summarizePreprocess(actions: Record<string, unknown>): string {
  const preprocess = (actions.preprocess ?? {}) as Record<string, unknown>;
  const parts: string[] = [];
  const ocr = (preprocess.ocr ?? {}) as Record<string, unknown>;
  if (ocr.enabled === true) {
    const passes = typeof ocr.passes === "number" ? ` (${ocr.passes} pass${ocr.passes === 1 ? "" : "es"})` : "";
    parts.push(`OCR${passes}`);
  }
  if (((preprocess.deskew ?? {}) as Record<string, unknown>).enabled === true) {
    parts.push("deskew");
  }
  const denoise = (preprocess.denoise ?? {}) as Record<string, unknown>;
  if (denoise.enabled === true) {
    parts.push(`denoise${typeof denoise.strength === "string" ? ` (${denoise.strength})` : ""}`);
  }
  const tableExtract = (preprocess.table_extract ?? {}) as Record<string, unknown>;
  if (tableExtract.enabled === true) {
    parts.push(`table extract${typeof tableExtract.type === "string" ? ` (${tableExtract.type})` : ""}`);
  }
  return parts.length > 0 ? parts.join(", ") : "No explicit preprocessing steps";
}

function summarizeExtraction(actions: Record<string, unknown>): string {
  const extraction = (actions.extraction ?? {}) as Record<string, unknown>;
  const modelTier = typeof extraction.model_tier === "string" ? extraction.model_tier : "unspecified";
  const ruleset = typeof extraction.ruleset === "string" ? extraction.ruleset : "no ruleset";
  const explicitEntities = Array.isArray(extraction.explicit_entities) ? extraction.explicit_entities.length : 0;
  return `${modelTier} model tier, ${ruleset}, ${explicitEntities} explicit field target${explicitEntities === 1 ? "" : "s"}`;
}

function summarizeRecovery(actions: Record<string, unknown>): string {
  const recovery = (actions.recovery ?? {}) as Record<string, unknown>;
  const strategy = typeof recovery.strategy === "string" ? recovery.strategy : "none";
  const escalation = (actions.escalation ?? {}) as Record<string, unknown>;
  const tier = typeof escalation.tier === "string" ? escalation.tier : null;
  return tier ? `${strategy} recovery, ${tier} escalation` : `${strategy} recovery`;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatF1(value: number | null): string {
  return typeof value === "number" ? value.toFixed(2) : "-";
}

export default async function JobPolicyDetailPage({
  params,
}: {
  params: Promise<{ jobId: string; policyId: string }>;
}) {
  const resolved = await params;
  const jobId = decodeURIComponent(resolved.jobId);
  const policyId = decodeURIComponent(resolved.policyId);
  const detail = getJobPolicyDetail(jobId, policyId);

  if (!detail) {
    notFound();
  }

  const { policy, usages, summary } = detail;

  const actionEntries = Object.entries(policy.actions);
  const conditionEntries = Object.entries(policy.conditions);
  const isDefault = policy.policyId === policy.defaultPolicyId;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <Link
          href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}`}
          className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
        >
          Back to job
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">{policy.name}</h1>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-200">
            {policy.policyId}
          </span>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium capitalize text-slate-700 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-200">
            {policy.source}
          </span>
          {isDefault ? (
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 dark:border-emerald-700/40 dark:bg-emerald-900/20 dark:text-emerald-300">
              default policy
            </span>
          ) : null}
        </div>
        <p className="mt-2 max-w-4xl text-sm text-slate-600 dark:text-slate-300">
          This is the concrete instruction set IDPO follows for a document after AHMN or fallback routing selects the
          policy.
        </p>
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">Source: {policy.sourcePath}</p>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Preprocessing path</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{summarizePreprocess(policy.actions)}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Extraction path</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{summarizeExtraction(policy.actions)}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Recovery / escalation</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{summarizeRecovery(policy.actions)}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Conditions</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {conditionEntries.length > 0 ? `${conditionEntries.length} routing condition${conditionEntries.length === 1 ? "" : "s"}` : "Fallback policy"}
          </p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Used in job</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {summary?.documentsProcessed ?? 0} processed / {summary?.documentsFailed ?? 0} failed
          </p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Reviewed F1</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{formatF1(summary?.meanExactF1 ?? null)}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Reviewed docs</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{summary?.reviewedDocuments ?? 0}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Last used</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{formatDate(summary?.lastUsedAt ?? null)}</p>
        </IdpoCard>
      </section>

      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Execution path</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          AHMN selects the policy. IDPO then follows these instructions for preprocessing, extraction, recovery, and
          retrieval.
        </p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {actionEntries.map(([key, value]) => (
            <div key={key} className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{formatLabel(key)}</h3>
              <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs leading-6 text-slate-700 dark:text-slate-300">
                {JSON.stringify(value, null, 2)}
              </pre>
            </div>
          ))}
          {actionEntries.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">No action payload recorded for this policy.</p>
          ) : null}
        </div>
      </IdpoCard>

      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Routing conditions</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">Field</th>
                <th className="px-2 py-2">Expected value</th>
              </tr>
            </thead>
            <tbody>
              {conditionEntries.map(([key, value]) => (
                <tr key={key} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-2 font-medium text-slate-900 dark:text-white">{key}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatValue(value)}</td>
                </tr>
              ))}
              {conditionEntries.length === 0 ? (
                <tr>
                  <td colSpan={2} className="px-2 py-3 text-slate-500 dark:text-slate-400">
                    No explicit routing conditions. This policy is available as a fallback/default candidate.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </IdpoCard>

      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Policy metadata</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <tbody>
              {Object.entries(policy.metadata).map(([key, value]) => (
                <tr key={key} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-3 font-medium text-slate-900 dark:text-white">{formatLabel(key)}</td>
                  <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{formatValue(value)}</td>
                </tr>
              ))}
              {Object.keys(policy.metadata).length === 0 ? (
                <tr>
                  <td colSpan={2} className="px-2 py-3 text-slate-500 dark:text-slate-400">
                    No metadata recorded for this policy.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </IdpoCard>

      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Where this policy was used</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Each row is one document outcome in this job that executed with this policy.
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">Document</th>
                <th className="px-2 py-2">Run</th>
                <th className="px-2 py-2">Mode</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Route</th>
                <th className="px-2 py-2">Review</th>
                <th className="px-2 py-2">F1</th>
                <th className="px-2 py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {usages.map((usage) => {
                const href =
                  usage.docId && usage.runId
                    ? `/dashboard/idpo/jobs/${encodeURIComponent(jobId)}/docs/${encodeURIComponent(usage.fileId)}?mode=${encodeURIComponent(usage.mode)}&runId=${encodeURIComponent(usage.runId)}`
                    : null;
                return (
                  <tr key={`${usage.fileId}-${usage.runId}-${usage.mode}`} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-3 font-medium text-slate-900 dark:text-white">{usage.fileName}</td>
                    <td className="px-2 py-3 font-mono text-xs text-slate-600 dark:text-slate-300">{usage.runId}</td>
                    <td className="px-2 py-3 capitalize text-slate-600 dark:text-slate-300">{usage.mode}</td>
                    <td className="px-2 py-3 capitalize text-slate-600 dark:text-slate-300">{usage.status}</td>
                    <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{usage.route ?? "-"}</td>
                    <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{usage.reviewStatus ?? "-"}</td>
                    <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{formatF1(usage.exactF1)}</td>
                    <td className="px-2 py-3">
                      {href ? (
                        <Link
                          href={href}
                          className="text-xs font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                        >
                          Open document
                        </Link>
                      ) : (
                        <span className="text-xs text-slate-500 dark:text-slate-400">Unavailable</span>
                      )}
                    </td>
                  </tr>
                );
              })}
              {usages.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-2 py-3 text-slate-500 dark:text-slate-400">
                    This policy has not been used in this job yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </IdpoCard>
    </div>
  );
}
