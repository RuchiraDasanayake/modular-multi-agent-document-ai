"use client";

import { useRouter } from "next/navigation";
import type { ChangeEvent, FormEvent } from "react";
import { useState } from "react";

type ExecutionProfile = "fast_local" | "balanced" | "cloud_extension";
type ModelTier = "local" | "cloud";

interface PolicyExecutionSettings {
  ocrEnabled: boolean;
  ocrPasses: number;
  ocrPsm: number;
  ocrAltPsm: number[];
  deskewEnabled: boolean;
  denoiseEnabled: boolean;
  denoiseStrength: string;
  tableExtractEnabled: boolean;
  tableExtractType: string;
  modelTier: ModelTier;
  ruleset: string;
  recoveryStrategy: string;
  chunkSize: number;
  chunkOverlap: number;
  maxChunks: number;
  denseK: number | null;
  sparseK: number | null;
  finalK: number | null;
  mmrLambda: number | null;
  metadataBoost: number | null;
  maxTokens: number | null;
  reservedTokens: number | null;
  tokenStrategy: string | null;
  escalationTier: string | null;
}

interface PolicyTemplate {
  policyId: string;
  name: string;
  source: "default" | "custom";
  executionProfile: ExecutionProfile;
  explicitEntities: string[];
  operatorInstructions: string;
  executionSettings: PolicyExecutionSettings;
}

interface JobPolicyCreateFormProps {
  jobId: string;
  initialMatching?: {
    vendorClusters?: string[];
    docTypes?: string[];
    contentProfiles?: string[];
  };
  policyTemplates?: PolicyTemplate[];
}

function splitCommaSeparated(value: string): string[] {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

function joinCommaSeparated(values: string[]): string {
  return values.join(", ");
}

function parseInteger(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseOptionalNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function presetSettings(profile: ExecutionProfile): PolicyExecutionSettings {
  if (profile === "fast_local") {
    return {
      ocrEnabled: true,
      ocrPasses: 1,
      ocrPsm: 6,
      ocrAltPsm: [],
      deskewEnabled: false,
      denoiseEnabled: false,
      denoiseStrength: "light",
      tableExtractEnabled: false,
      tableExtractType: "heuristic",
      modelTier: "local",
      ruleset: "job_custom_fast_local",
      recoveryStrategy: "regex",
      chunkSize: 240,
      chunkOverlap: 32,
      maxChunks: 64,
      denseK: null,
      sparseK: null,
      finalK: null,
      mmrLambda: null,
      metadataBoost: null,
      maxTokens: null,
      reservedTokens: null,
      tokenStrategy: null,
      escalationTier: null,
    };
  }

  if (profile === "cloud_extension") {
    return {
      ocrEnabled: true,
      ocrPasses: 2,
      ocrPsm: 6,
      ocrAltPsm: [4, 11],
      deskewEnabled: true,
      denoiseEnabled: true,
      denoiseStrength: "standard",
      tableExtractEnabled: true,
      tableExtractType: "heuristic",
      modelTier: "cloud",
      ruleset: "job_custom_cloud_extension",
      recoveryStrategy: "alternate_rules",
      chunkSize: 320,
      chunkOverlap: 48,
      maxChunks: 128,
      denseK: 10,
      sparseK: 10,
      finalK: 10,
      mmrLambda: 0.68,
      metadataBoost: 0.12,
      maxTokens: 1800,
      reservedTokens: 240,
      tokenStrategy: "simple",
      escalationTier: "tier2",
    };
  }

  return {
    ocrEnabled: true,
    ocrPasses: 2,
    ocrPsm: 6,
    ocrAltPsm: [4, 11],
    deskewEnabled: true,
    denoiseEnabled: true,
    denoiseStrength: "standard",
    tableExtractEnabled: true,
    tableExtractType: "heuristic",
    modelTier: "local",
    ruleset: "job_custom_balanced",
    recoveryStrategy: "regex",
    chunkSize: 280,
    chunkOverlap: 40,
    maxChunks: 96,
    denseK: 8,
    sparseK: 8,
    finalK: 8,
    mmrLambda: 0.6,
    metadataBoost: 0.08,
    maxTokens: null,
    reservedTokens: null,
    tokenStrategy: null,
    escalationTier: null,
  };
}

function checkboxClassName(): string {
  return "h-4 w-4 rounded border-slate-300 text-cyan-600 focus:ring-cyan-500 dark:border-slate-700 dark:bg-slate-950";
}

function textInputClassName(): string {
  return "w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white";
}

function numberInputValue(value: number | null): string {
  return value == null ? "" : String(value);
}

export function JobPolicyCreateForm({ jobId, initialMatching, policyTemplates = [] }: JobPolicyCreateFormProps) {
  const router = useRouter();
  const [basePolicyId, setBasePolicyId] = useState("");
  const [policyId, setPolicyId] = useState("");
  const [name, setName] = useState("");
  const [executionProfile, setExecutionProfile] = useState<ExecutionProfile>("balanced");
  const [executionSettings, setExecutionSettings] = useState<PolicyExecutionSettings>(presetSettings("balanced"));
  const [contentProfiles, setContentProfiles] = useState(joinCommaSeparated(initialMatching?.contentProfiles ?? []));
  const [vendorClusters, setVendorClusters] = useState(joinCommaSeparated(initialMatching?.vendorClusters ?? []));
  const [docTypes, setDocTypes] = useState(joinCommaSeparated(initialMatching?.docTypes ?? []));
  const [explicitEntities, setExplicitEntities] = useState("");
  const [instructions, setInstructions] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  function applyTemplate(templateId: string) {
    setBasePolicyId(templateId);
    const template = policyTemplates.find((entry) => entry.policyId === templateId);
    if (!template) {
      return;
    }
    setExecutionProfile(template.executionProfile);
    setExecutionSettings(template.executionSettings);
    setExplicitEntities(joinCommaSeparated(template.explicitEntities));
    setInstructions(template.operatorInstructions);
    setPolicyId((current) => current || `${template.policyId}_custom`);
    setName((current) => current || `${template.name} copy`);
  }

  function updateExecutionSetting<K extends keyof PolicyExecutionSettings>(key: K, value: PolicyExecutionSettings[K]) {
    setExecutionSettings((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function handleExecutionProfileChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextProfile = event.target.value as ExecutionProfile;
    setExecutionProfile(nextProfile);
    setBasePolicyId("");
    setExecutionSettings(presetSettings(nextProfile));
  }

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
          basePolicyId: basePolicyId || undefined,
          executionProfile,
          executionSettings,
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

      setBasePolicyId("");
      setPolicyId("");
      setName("");
      setExecutionProfile("balanced");
      setExecutionSettings(presetSettings("balanced"));
      setContentProfiles(joinCommaSeparated(initialMatching?.contentProfiles ?? []));
      setVendorClusters(joinCommaSeparated(initialMatching?.vendorClusters ?? []));
      setDocTypes(joinCommaSeparated(initialMatching?.docTypes ?? []));
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
      <div className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Start from an existing policy</h3>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Clone a policy first if you want to build on what already works. The executable settings below will be filled in and can then be changed.
          </p>
        </div>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-700 dark:text-slate-300">Base policy</span>
          <select value={basePolicyId} onChange={(event) => applyTemplate(event.target.value)} className={textInputClassName()}>
            <option value="">Start from scratch</option>
            {policyTemplates.map((template) => (
              <option key={template.policyId} value={template.policyId}>
                {template.policyId} - {template.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Policy identity</h3>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Give the new policy its own ID and name. If you cloned an existing policy, these settings already reflect that base policy.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Policy ID</span>
            <input value={policyId} onChange={(event) => setPolicyId(event.target.value)} placeholder="vendor_fast_local" className={textInputClassName()} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Vendor fast local" className={textInputClassName()} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Execution profile</span>
            <select value={executionProfile} onChange={handleExecutionProfileChange} className={textInputClassName()}>
              <option value="fast_local">Fast local</option>
              <option value="balanced">Balanced local</option>
              <option value="cloud_extension">Cloud extension (paid)</option>
            </select>
          </label>
          <label className="text-sm md:col-span-2 xl:col-span-3">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Field targets</span>
            <input value={explicitEntities} onChange={(event) => setExplicitEntities(event.target.value)} placeholder="invoice_number, total_amount, due_date" className={textInputClassName()} />
          </label>
        </div>
      </div>

      <div className="space-y-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-950/30">
        <div>
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Executable IDPO settings</h3>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            These settings are the actual runtime instructions that will be saved into the new policy. Free-text notes do not drive execution.
          </p>
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">OCR passes</span>
            <input type="number" min={1} value={executionSettings.ocrPasses} onChange={(event) => updateExecutionSetting("ocrPasses", parseInteger(event.target.value, executionSettings.ocrPasses))} className={textInputClassName()} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">OCR PSM</span>
            <input type="number" min={1} value={executionSettings.ocrPsm} onChange={(event) => updateExecutionSetting("ocrPsm", parseInteger(event.target.value, executionSettings.ocrPsm))} className={textInputClassName()} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Alt PSMs</span>
            <input value={joinCommaSeparated(executionSettings.ocrAltPsm.map(String))} onChange={(event) => updateExecutionSetting("ocrAltPsm", splitCommaSeparated(event.target.value).map((entry) => Number(entry)).filter((value) => Number.isFinite(value)))} placeholder="4, 11" className={textInputClassName()} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Model tier</span>
            <select value={executionSettings.modelTier} onChange={(event) => updateExecutionSetting("modelTier", event.target.value === "cloud" ? "cloud" : "local")} className={textInputClassName()}>
              <option value="local">Local</option>
              <option value="cloud">Cloud</option>
            </select>
          </label>

          <label className="text-sm md:col-span-2">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Ruleset</span>
            <input value={executionSettings.ruleset} onChange={(event) => updateExecutionSetting("ruleset", event.target.value)} className={textInputClassName()} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Recovery strategy</span>
            <input value={executionSettings.recoveryStrategy} onChange={(event) => updateExecutionSetting("recoveryStrategy", event.target.value)} className={textInputClassName()} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Escalation tier</span>
            <input value={executionSettings.escalationTier ?? ""} onChange={(event) => updateExecutionSetting("escalationTier", event.target.value || null)} placeholder="tier2" className={textInputClassName()} />
          </label>

          <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" checked={executionSettings.ocrEnabled} onChange={(event) => updateExecutionSetting("ocrEnabled", event.target.checked)} className={checkboxClassName()} />
            OCR enabled
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" checked={executionSettings.deskewEnabled} onChange={(event) => updateExecutionSetting("deskewEnabled", event.target.checked)} className={checkboxClassName()} />
            Deskew
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" checked={executionSettings.denoiseEnabled} onChange={(event) => updateExecutionSetting("denoiseEnabled", event.target.checked)} className={checkboxClassName()} />
            Denoise
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" checked={executionSettings.tableExtractEnabled} onChange={(event) => updateExecutionSetting("tableExtractEnabled", event.target.checked)} className={checkboxClassName()} />
            Table extract
          </label>

          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Denoise strength</span>
            <input value={executionSettings.denoiseStrength} onChange={(event) => updateExecutionSetting("denoiseStrength", event.target.value)} className={textInputClassName()} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Table extract type</span>
            <input value={executionSettings.tableExtractType} onChange={(event) => updateExecutionSetting("tableExtractType", event.target.value)} className={textInputClassName()} />
          </label>
        </div>

        <details className="rounded-xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-950/40">
          <summary className="cursor-pointer list-none text-sm font-semibold text-slate-900 dark:text-white">Chunking, retrieval, and token budget</summary>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Chunk size</span>
              <input type="number" min={64} value={executionSettings.chunkSize} onChange={(event) => updateExecutionSetting("chunkSize", parseInteger(event.target.value, executionSettings.chunkSize))} className={textInputClassName()} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Chunk overlap</span>
              <input type="number" min={0} value={executionSettings.chunkOverlap} onChange={(event) => updateExecutionSetting("chunkOverlap", parseInteger(event.target.value, executionSettings.chunkOverlap))} className={textInputClassName()} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Max chunks</span>
              <input type="number" min={1} value={executionSettings.maxChunks} onChange={(event) => updateExecutionSetting("maxChunks", parseInteger(event.target.value, executionSettings.maxChunks))} className={textInputClassName()} />
            </label>
            <div />

            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Dense k</span>
              <input type="number" min={0} value={numberInputValue(executionSettings.denseK)} onChange={(event) => updateExecutionSetting("denseK", parseOptionalNumber(event.target.value))} className={textInputClassName()} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Sparse k</span>
              <input type="number" min={0} value={numberInputValue(executionSettings.sparseK)} onChange={(event) => updateExecutionSetting("sparseK", parseOptionalNumber(event.target.value))} className={textInputClassName()} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Final k</span>
              <input type="number" min={0} value={numberInputValue(executionSettings.finalK)} onChange={(event) => updateExecutionSetting("finalK", parseOptionalNumber(event.target.value))} className={textInputClassName()} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">MMR lambda</span>
              <input type="number" step="0.01" min={0} max={1} value={numberInputValue(executionSettings.mmrLambda)} onChange={(event) => updateExecutionSetting("mmrLambda", parseOptionalNumber(event.target.value))} className={textInputClassName()} />
            </label>

            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Metadata boost</span>
              <input type="number" step="0.01" min={0} value={numberInputValue(executionSettings.metadataBoost)} onChange={(event) => updateExecutionSetting("metadataBoost", parseOptionalNumber(event.target.value))} className={textInputClassName()} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Max tokens</span>
              <input type="number" min={0} value={numberInputValue(executionSettings.maxTokens)} onChange={(event) => updateExecutionSetting("maxTokens", parseOptionalNumber(event.target.value))} className={textInputClassName()} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Reserved tokens</span>
              <input type="number" min={0} value={numberInputValue(executionSettings.reservedTokens)} onChange={(event) => updateExecutionSetting("reservedTokens", parseOptionalNumber(event.target.value))} className={textInputClassName()} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Token strategy</span>
              <input value={executionSettings.tokenStrategy ?? ""} onChange={(event) => updateExecutionSetting("tokenStrategy", event.target.value || null)} placeholder="simple" className={textInputClassName()} />
            </label>
          </div>
        </details>
      </div>

      <details className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-950/30">
        <summary className="cursor-pointer list-none text-sm font-semibold text-slate-900 dark:text-white">
          Advanced matching
        </summary>
        <div className="mt-3 space-y-3">
          <div>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              These hints help AHMN and fallback routing decide when this policy should be considered. They are
              prefilled from the current job context so you only need to change them if the default match is wrong.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Vendor match</span>
              <input value={vendorClusters} onChange={(event) => setVendorClusters(event.target.value)} placeholder="acme, unknown" className={textInputClassName()} />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Document types</span>
              <input value={docTypes} onChange={(event) => setDocTypes(event.target.value)} placeholder="invoice, form" className={textInputClassName()} />
            </label>
            <label className="text-sm md:col-span-2">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Page shape hints</span>
              <input value={contentProfiles} onChange={(event) => setContentProfiles(event.target.value)} placeholder="table-heavy, form-centric" className={textInputClassName()} />
            </label>
          </div>
        </div>
      </details>

      <label className="block text-sm">
        <span className="mb-1 block text-slate-700 dark:text-slate-300">Operator instructions</span>
        <textarea
          value={instructions}
          onChange={(event) => setInstructions(event.target.value)}
          rows={4}
          placeholder="Optional note for the team. This is stored as metadata only."
          className={textInputClassName()}
        />
      </label>

      {executionProfile === "cloud_extension" ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-700/40 dark:bg-amber-900/20 dark:text-amber-200">
          This is an explicit paid extension policy. It will use cloud inference when selected. It is not part of the free local-first default path.
        </div>
      ) : null}

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
