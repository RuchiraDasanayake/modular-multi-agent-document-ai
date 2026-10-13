import Link from "next/link";
import { notFound } from "next/navigation";
import { headers } from "next/headers";
import { IdpoCard } from "@/components/idpo/card";
import { getJobPolicyDetail } from "@/server/policies";
import { requireJob } from "@/server/access";
import { requireUser } from "@/server/auth";

interface PolicyFact {
  label: string;
  value: string;
}

function formatLabel(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
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

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function formatSimpleValue(value: unknown): string {
  if (value == null) {
    return "-";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatSimpleValue(item)).join(", ");
  }
  return JSON.stringify(value);
}

function listToSentence(values: unknown): string {
  if (!Array.isArray(values) || values.length === 0) {
    return "-";
  }
  return values.map((value) => String(value)).join(", ");
}

function sectionFacts(policyActions: Record<string, unknown>, key: string): PolicyFact[] {
  if (key === "preprocess") {
    const preprocess = asRecord(policyActions.preprocess);
    const ocr = asRecord(preprocess.ocr);
    const deskew = asRecord(preprocess.deskew);
    const denoise = asRecord(preprocess.denoise);
    const tableExtract = asRecord(preprocess.table_extract);
    return [
      {
        label: "OCR",
        value:
          ocr.enabled === true
            ? `${typeof ocr.passes === "number" ? `${ocr.passes} pass${ocr.passes === 1 ? "" : "es"}` : "enabled"}`
            : "off",
      },
      {
        label: "Page mode",
        value: typeof ocr.psm === "number" ? String(ocr.psm) : "-",
      },
      {
        label: "Alternate modes",
        value: listToSentence(ocr.alt_psm),
      },
      {
        label: "Deskew",
        value: deskew.enabled === true ? "on" : "off",
      },
      {
        label: "Denoise",
        value: denoise.enabled === true ? String(denoise.strength || "on") : "off",
      },
      {
        label: "Table extraction",
        value: tableExtract.enabled === true ? String(tableExtract.type || "on") : "off",
      },
    ];
  }

  if (key === "extraction") {
    const extraction = asRecord(policyActions.extraction);
    const fieldDescriptions = asRecord(extraction.field_descriptions);
    return [
      {
        label: "Model path",
        value: typeof extraction.model_tier === "string" ? extraction.model_tier : "-",
      },
      {
        label: "Ruleset",
        value: typeof extraction.ruleset === "string" ? extraction.ruleset : "-",
      },
      {
        label: "Field targets",
        value: listToSentence(extraction.explicit_entities),
      },
      {
        label: "Field notes",
        value: Object.keys(fieldDescriptions).length > 0 ? `${Object.keys(fieldDescriptions).length} custom note(s)` : "none",
      },
    ];
  }

  if (key === "recovery") {
    const recovery = asRecord(policyActions.recovery);
    return [
      {
        label: "Strategy",
        value: typeof recovery.strategy === "string" ? recovery.strategy : "-",
      },
    ];
  }

  if (key === "escalation") {
    const escalation = asRecord(policyActions.escalation);
    return [
      {
        label: "Tier",
        value: typeof escalation.tier === "string" ? escalation.tier : "-",
      },
    ];
  }

  if (key === "chunking") {
    const chunking = asRecord(policyActions.chunking);
    return [
      {
        label: "Chunk size",
        value: typeof chunking.chunk_size === "number" ? String(chunking.chunk_size) : "-",
      },
      {
        label: "Overlap",
        value: typeof chunking.chunk_overlap === "number" ? String(chunking.chunk_overlap) : "-",
      },
      {
        label: "Max chunks",
        value: typeof chunking.max_chunks === "number" ? String(chunking.max_chunks) : "-",
      },
    ];
  }

  if (key === "retrieval") {
    const retrieval = asRecord(policyActions.retrieval);
    return [
      { label: "Dense search", value: typeof retrieval.dense_k === "number" ? String(retrieval.dense_k) : "-" },
      { label: "Sparse search", value: typeof retrieval.sparse_k === "number" ? String(retrieval.sparse_k) : "-" },
      { label: "Final evidence", value: typeof retrieval.final_k === "number" ? String(retrieval.final_k) : "-" },
      { label: "MMR", value: typeof retrieval.mmr_lambda === "number" ? String(retrieval.mmr_lambda) : "-" },
      { label: "Metadata boost", value: typeof retrieval.metadata_boost === "number" ? String(retrieval.metadata_boost) : "-" },
    ];
  }

  if (key === "token_budget") {
    const tokenBudget = asRecord(policyActions.token_budget);
    return [
      { label: "Max tokens", value: typeof tokenBudget.max_tokens === "number" ? String(tokenBudget.max_tokens) : "-" },
      {
        label: "Reserved tokens",
        value: typeof tokenBudget.reserved_tokens === "number" ? String(tokenBudget.reserved_tokens) : "-",
      },
      { label: "Strategy", value: typeof tokenBudget.strategy === "string" ? tokenBudget.strategy : "-" },
    ];
  }

  const payload = asRecord(policyActions[key]);
  return Object.entries(payload).map(([entryKey, value]) => ({
    label: formatLabel(entryKey),
    value: formatSimpleValue(value),
  }));
}

function sectionHelpText(key: string): string {
  switch (key) {
    case "preprocess":
      return "This cleans or reshapes the document before extraction. More cleanup usually helps noisy scans, but it costs more time.";
    case "extraction":
      return "This controls which model path runs and which fields the extractor targets.";
    case "recovery":
      return "This runs after validation when fields are weak or missing.";
    case "escalation":
      return "This allows a stronger path when the first extraction result is not good enough.";
    case "chunking":
      return "This breaks larger documents into smaller parts. More overlap preserves context but costs more.";
    case "retrieval":
      return "This controls how much evidence is pulled into the model context before extraction.";
    case "token_budget":
      return "This limits how much context and output the model can use.";
    default:
      return "This is part of the policy instruction set used by IDPO during execution.";
  }
}

function sectionTitle(key: string): string {
  if (key === "token_budget") {
    return "Token budget";
  }
  return formatLabel(key);
}

function metadataText(metadata: Record<string, unknown>, key: string): string | null {
  const value = metadata[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function PolicySectionCard({
  sectionKey,
  facts,
}: {
  sectionKey: string;
  facts: PolicyFact[];
}) {
  if (facts.length === 0) {
    return null;
  }
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{sectionTitle(sectionKey)}</h3>
        <details className="max-w-[18rem] text-right">
          <summary className="cursor-pointer text-xs font-medium text-cyan-700 marker:hidden hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200">
            What this changes
          </summary>
          <p className="mt-2 text-left text-xs leading-5 text-slate-600 dark:text-slate-300">{sectionHelpText(sectionKey)}</p>
        </details>
      </div>
      <dl className="mt-3 space-y-2">
        {facts.map((fact) => (
          <div key={`${sectionKey}-${fact.label}`} className="grid gap-1 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-3">
            <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{fact.label}</dt>
            <dd className="text-sm text-slate-800 dark:text-slate-200">{fact.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default async function JobPolicyDetailPage({
  params,
}: {
  params: Promise<{ jobId: string; policyId: string }>;
}) {
  const resolved = await params;
  const jobId = decodeURIComponent(resolved.jobId);
  try {
    requireJob(jobId, await requireUser(await headers()));
  } catch {
    notFound();
  }
  const policyId = decodeURIComponent(resolved.policyId);
  const detail = getJobPolicyDetail(jobId, policyId);

  if (!detail) {
    notFound();
  }

  const { policy } = detail;

  const sectionOrder = ["preprocess", "extraction", "recovery", "escalation", "chunking", "retrieval", "token_budget"];
  const knownSections = sectionOrder.filter((key) => key in policy.actions);
  const extraSections = Object.keys(policy.actions).filter((key) => !sectionOrder.includes(key));
  const orderedSections = [...knownSections, ...extraSections];
  const isDefault = policy.policyId === policy.defaultPolicyId;
  const operatorInstructions =
    typeof policy.metadata.operator_instructions === "string" && policy.metadata.operator_instructions.trim()
      ? policy.metadata.operator_instructions.trim()
      : null;
  const policyFamily = metadataText(policy.metadata, "family");
  const policyVariant = metadataText(policy.metadata, "variant");
  const whenUsed = metadataText(policy.metadata, "when_used");
  const whyItHelps = metadataText(policy.metadata, "why");
  const tradeoff = metadataText(policy.metadata, "tradeoff");
  const costProfile = metadataText(policy.metadata, "cost_profile");
  const siblingPolicyId = metadataText(policy.metadata, "sibling_policy_id");
  const activeExtension = policy.availability === "active_extension";
  const inactiveLocalPolicy = policy.availability === "inactive";
  const inactiveExtension = policy.availability === "inactive_extension";

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <Link
          href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}/policies`}
          className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
        >
          Back to policy workspace
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">{policy.name}</h1>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-200">
            {policy.policyId}
          </span>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium capitalize text-slate-700 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-200">
            {policy.source}
          </span>
          {inactiveExtension ? (
            <span className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-xs font-medium text-violet-700 dark:border-violet-700/40 dark:bg-violet-900/20 dark:text-violet-300">
              inactive extension
            </span>
          ) : null}
          {inactiveLocalPolicy ? (
            <span className="rounded-full border border-slate-300 bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
              disabled for this job
            </span>
          ) : null}
          {activeExtension ? (
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 dark:border-emerald-700/40 dark:bg-emerald-900/20 dark:text-emerald-300">
              cloud extension enabled
            </span>
          ) : null}
          {isDefault ? (
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 dark:border-emerald-700/40 dark:bg-emerald-900/20 dark:text-emerald-300">
              default policy
            </span>
          ) : null}
        </div>
        <p className="mt-2 max-w-4xl text-sm text-slate-600 dark:text-slate-300">
          This page only shows what the policy tells IDPO to do. Learning, ranking, and reviewed performance stay in
          the job policy workspace.
        </p>
        {inactiveExtension ? (
          <p className="mt-2 max-w-4xl text-sm text-slate-600 dark:text-slate-300">
            This policy is shipped as an optional paid cloud extension. It is visible here for planning, but it is not
            included in the active runtime bank by default.
          </p>
        ) : null}
        {inactiveLocalPolicy ? (
          <p className="mt-2 max-w-4xl text-sm text-slate-600 dark:text-slate-300">
            This policy exists in the job workspace, but it is currently disabled for this job and excluded from the
            active runtime bank.
          </p>
        ) : null}
        {activeExtension ? (
          <p className="mt-2 max-w-4xl text-sm text-slate-600 dark:text-slate-300">
            This policy is an optional paid cloud extension and is currently enabled for this job.
          </p>
        ) : null}
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">Source: {policy.sourcePath}</p>
      </section>

      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">What this policy does</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          This is the strict IDPO instruction set. Once the system selects this policy, this is the path it follows.
        </p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {(policyFamily || whenUsed || whyItHelps || tradeoff || costProfile) ? (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Policy intent</h3>
              <dl className="mt-3 space-y-2 text-sm">
                {policyFamily ? (
                  <div className="grid gap-1 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-3">
                    <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Family</dt>
                    <dd className="text-slate-800 dark:text-slate-200">
                      {policyFamily}
                      {policyVariant ? ` (${policyVariant})` : ""}
                    </dd>
                  </div>
                ) : null}
                {whenUsed ? (
                  <div className="grid gap-1 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-3">
                    <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">When used</dt>
                    <dd className="text-slate-800 dark:text-slate-200">{whenUsed}</dd>
                  </div>
                ) : null}
                {whyItHelps ? (
                  <div className="grid gap-1 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-3">
                    <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Why</dt>
                    <dd className="text-slate-800 dark:text-slate-200">{whyItHelps}</dd>
                  </div>
                ) : null}
                {tradeoff ? (
                  <div className="grid gap-1 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-3">
                    <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Tradeoff</dt>
                    <dd className="text-slate-800 dark:text-slate-200">{tradeoff}</dd>
                  </div>
                ) : null}
                {costProfile ? (
                  <div className="grid gap-1 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-3">
                    <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Cost</dt>
                    <dd className="text-slate-800 dark:text-slate-200">{costProfile}</dd>
                  </div>
                ) : null}
                {siblingPolicyId ? (
                  <div className="grid gap-1 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-3">
                    <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Sibling</dt>
                    <dd className="text-slate-800 dark:text-slate-200">{siblingPolicyId}</dd>
                  </div>
                ) : null}
              </dl>
            </div>
          ) : null}
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Path summary</h3>
            <div className="mt-3 space-y-2 text-sm text-slate-700 dark:text-slate-300">
              <p><span className="font-medium text-slate-900 dark:text-white">Preprocessing:</span> {summarizePreprocess(policy.actions)}</p>
              <p><span className="font-medium text-slate-900 dark:text-white">Extraction:</span> {summarizeExtraction(policy.actions)}</p>
              <p><span className="font-medium text-slate-900 dark:text-white">Recovery:</span> {summarizeRecovery(policy.actions)}</p>
            </div>
          </div>
          {operatorInstructions ? (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Operator note</h3>
              <p className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-300">{operatorInstructions}</p>
            </div>
          ) : null}
          {orderedSections.map((sectionKey) => (
            <PolicySectionCard
              key={sectionKey}
              sectionKey={sectionKey}
              facts={sectionFacts(policy.actions, sectionKey)}
            />
          ))}
          {orderedSections.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">No action payload recorded for this policy.</p>
          ) : null}
        </div>
      </IdpoCard>
    </div>
  );
}
