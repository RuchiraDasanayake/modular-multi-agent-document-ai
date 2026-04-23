import fs from "node:fs";
import path from "node:path";
import { getRunDocument } from "@/server/artifacts";
import { loadRunnerConfig } from "@/server/config";
import { getJobOrThrow } from "@/server/jobs";
import { readJobValidationContext } from "@/server/review-context";

interface PolicyStorePayload {
  default_policy_id?: unknown;
  policies?: unknown;
}

interface ExtensionPolicyStorePayload extends PolicyStorePayload {
  enabled_by_default?: unknown;
  extension_type?: unknown;
}

interface RawPolicyRecord {
  policy_id: string;
  name: string;
  conditions: Record<string, unknown>;
  actions: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export type JobPolicySource = "default" | "custom";
export type JobPolicyAvailability = "active" | "active_extension" | "inactive" | "inactive_extension";
export type JobPolicyLearningState = "promoted" | "watch" | "demoted" | "candidate" | "unused";
export type JobPolicyExecutionProfile = "fast_local" | "balanced" | "cloud_extension";

export interface JobPolicyUsage {
  fileId: string;
  fileName: string;
  runId: string;
  docId: string | null;
  mode: "adaptive" | "strict";
  status: "loaded" | "processing" | "processed" | "failed";
  route: string | null;
  exactF1: number | null;
  reviewStatus: string | null;
  adviceSource?: string | null;
  adviceStatus?: string | null;
  adviceConfidence?: number | null;
  retrievalSource?: string | null;
  rabiUsed?: boolean;
  nNeighbors?: number | null;
  reviewedLearningLogged?: boolean | null;
  reviewedLearningError?: string | null;
  updatedAt: string;
}

export interface JobPolicyLearningSummary {
  selectionMode: "thompson_sampling";
  ahmnRouteCount: number;
  jobOverlayRouteCount: number;
  fallbackRouteCount: number;
  staticRouteCount: number;
  warmStartCount: number;
  meanNeighborCount: number | null;
  maxNeighborCount: number | null;
  reviewedLearningLoggedCount: number;
  reviewedLearningPendingCount: number;
  rabiDecayState: "active" | "unused";
  driftAwarenessState: "active";
}

export interface PolicyDetail {
  policyId: string;
  name: string;
  source: JobPolicySource;
  availability: JobPolicyAvailability;
  runtimeEnabled: boolean;
  runtimeToggleAllowed: boolean;
  conditions: Record<string, unknown>;
  actions: Record<string, unknown>;
  metadata: Record<string, unknown>;
  defaultPolicyId: string;
  sourcePath: string;
}

export interface JobPolicySummary extends PolicyDetail {
  documentsProcessed: number;
  documentsFailed: number;
  uniqueDocumentsUsed: number;
  reviewedDocuments: number;
  meanExactF1: number | null;
  ahmnConfidence: number | null;
  autoReviewedDocuments: number;
  meanAutoReviewF1: number | null;
  learningState: JobPolicyLearningState;
  lastUsedAt: string | null;
  learning: JobPolicyLearningSummary;
  leaderboardRank: number | null;
}

export interface JobPolicyWorkspace {
  sourcePath: string;
  defaultPolicyId: string;
  policies: JobPolicySummary[];
  leaderboard: JobPolicySummary[];
  customPolicyCount: number;
  defaultPolicyCount: number;
}

export interface JobPolicySuggestedMatching {
  vendorClusters: string[];
  docTypes: string[];
  contentProfiles: string[];
}

export interface JobPolicyExecutionSettings {
  ocrEnabled: boolean;
  ocrPasses: number;
  ocrPsm: number;
  ocrAltPsm: number[];
  deskewEnabled: boolean;
  denoiseEnabled: boolean;
  denoiseStrength: string;
  tableExtractEnabled: boolean;
  tableExtractType: string;
  modelTier: "local" | "cloud";
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

export interface JobPolicyTemplate {
  policyId: string;
  name: string;
  source: JobPolicySource;
  executionProfile: JobPolicyExecutionProfile;
  explicitEntities: string[];
  operatorInstructions: string;
  executionSettings: JobPolicyExecutionSettings;
}

export interface JobPolicyCreateInput {
  policyId: string;
  name: string;
  executionProfile: JobPolicyExecutionProfile;
  basePolicyId?: string | null;
  executionSettings?: Partial<JobPolicyExecutionSettings> | Record<string, unknown> | null;
  instructions?: string | null;
  routeBins?: string[];
  contentProfiles?: string[];
  vendorClusters?: string[];
  docTypes?: string[];
  explicitEntities?: string[];
}

interface StoredCustomPolicies {
  updated_at: string;
  policies: RawPolicyRecord[];
}

interface StoredPolicyActivationState {
  updated_at: string;
  overrides: Record<string, boolean>;
}

function nowIso(): string {
  return new Date().toISOString();
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
    .filter((entry) => entry.length > 0);
}

function readJsonFile(filePath: string): unknown {
  if (!fs.existsSync(filePath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8"));
  } catch {
    return null;
  }
}

function normalizePolicyId(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "_");
}

function titleCase(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function arrayIfPresent(values: string[]): string[] | undefined {
  return values.length > 0 ? values : undefined;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function uniqueStrings(values: Iterable<string>, limit = 8): string[] {
  const items: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const text = value.trim();
    if (!text) {
      continue;
    }
    const key = text.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    items.push(text);
    seen.add(key);
    if (items.length >= limit) {
      break;
    }
  }
  return items;
}

function normalizeExecutionProfile(value: unknown): JobPolicyExecutionProfile {
  return value === "fast_local" || value === "balanced" || value === "cloud_extension" ? value : "balanced";
}

function toPolicyRecord(value: unknown): RawPolicyRecord | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const policyId = typeof record.policy_id === "string" ? record.policy_id.trim() : "";
  if (!policyId) {
    return null;
  }
  return {
    policy_id: policyId,
    name: typeof record.name === "string" && record.name.trim() ? record.name.trim() : policyId,
    conditions: asRecord(record.conditions) ?? {},
    actions: asRecord(record.actions) ?? {},
    metadata: asRecord(record.metadata) ?? {},
  };
}

function resolvePolicyStoreConfig(): { policyStorePath: string; defaultPolicyId: string } {
  const { workspaceRoot } = loadRunnerConfig();
  const researchConfigPath = path.join(workspaceRoot, "configs", "idpo_research_config.json");
  const researchConfig = asRecord(readJsonFile(researchConfigPath)) ?? {};
  const knowledge = asRecord(researchConfig.knowledge) ?? {};
  const configuredPolicyPath =
    typeof knowledge.policy_store_path === "string" && knowledge.policy_store_path.trim()
      ? path.resolve(workspaceRoot, knowledge.policy_store_path.trim())
      : null;
  const defaultPolicyId =
    typeof knowledge.default_policy_id === "string" && knowledge.default_policy_id.trim()
      ? knowledge.default_policy_id.trim()
      : "default";

  const fallbackCandidates = [
    configuredPolicyPath,
    path.join(workspaceRoot, "configs", "policy_store_research.json"),
    path.join(workspaceRoot, "configs", "policy_store.json"),
  ].filter((candidate): candidate is string => Boolean(candidate));

  const policyStorePath = fallbackCandidates.find((candidate) => fs.existsSync(candidate)) ?? fallbackCandidates[0];
  return { policyStorePath, defaultPolicyId };
}

function readBasePolicyStore(): { defaultPolicyId: string; sourcePath: string; items: RawPolicyRecord[] } {
  const { workspaceRoot } = loadRunnerConfig();
  const { policyStorePath, defaultPolicyId } = resolvePolicyStoreConfig();
  const raw = readJsonFile(policyStorePath);

  let items: unknown[] = [];
  let resolvedDefault = defaultPolicyId;
  if (Array.isArray(raw)) {
    items = raw;
  } else {
    const payload = asRecord(raw) as PolicyStorePayload | null;
    if (payload) {
      items = Array.isArray(payload.policies) ? payload.policies : [];
      if (typeof payload.default_policy_id === "string" && payload.default_policy_id.trim()) {
        resolvedDefault = payload.default_policy_id.trim();
      }
    }
  }

  return {
    defaultPolicyId: resolvedDefault,
    sourcePath: path.relative(workspaceRoot, policyStorePath).replace(/\\/g, "/"),
    items: items.map((item) => toPolicyRecord(item)).filter((item): item is RawPolicyRecord => item !== null),
  };
}

function readExtensionPolicyStore(): {
  enabledByDefault: boolean;
  extensionType: string | null;
  sourcePath: string | null;
  items: RawPolicyRecord[];
} {
  const { workspaceRoot } = loadRunnerConfig();
  const extensionPath = path.join(workspaceRoot, "configs", "policy_store_cloud_extensions.json");
  const raw = asRecord(readJsonFile(extensionPath)) as ExtensionPolicyStorePayload | null;

  if (!raw || !fs.existsSync(extensionPath)) {
    return {
      enabledByDefault: false,
      extensionType: null,
      sourcePath: null,
      items: [],
    };
  }

  const extensionType =
    typeof raw.extension_type === "string" && raw.extension_type.trim() ? raw.extension_type.trim() : "cloud_optional";
  const items = (Array.isArray(raw.policies) ? raw.policies : [])
    .map((item) => toPolicyRecord(item))
    .filter((item): item is RawPolicyRecord => item !== null)
    .map((item) => ({
      ...item,
      metadata: {
        ...item.metadata,
        extension_type: typeof item.metadata.extension_type === "string" ? item.metadata.extension_type : extensionType,
      },
    }));

  return {
    enabledByDefault: raw.enabled_by_default === true,
    extensionType,
    sourcePath: path.relative(workspaceRoot, extensionPath).replace(/\\/g, "/"),
    items,
  };
}

function getJobCustomPolicyFile(jobId: string): string {
  return path.join(loadRunnerConfig().jobsDir, `${jobId}_policies.json`);
}

function readJobCustomPolicies(jobId: string): StoredCustomPolicies {
  const filePath = getJobCustomPolicyFile(jobId);
  const raw = asRecord(readJsonFile(filePath)) ?? {};
  const items = Array.isArray(raw.policies) ? raw.policies : [];
  return {
    updated_at: typeof raw.updated_at === "string" ? raw.updated_at : nowIso(),
    policies: items.map((item) => toPolicyRecord(item)).filter((item): item is RawPolicyRecord => item !== null),
  };
}

function writeJobCustomPolicies(jobId: string, payload: StoredCustomPolicies): void {
  const filePath = getJobCustomPolicyFile(jobId);
  fs.writeFileSync(filePath, JSON.stringify(payload, null, 2), "utf-8");
}

function getJobPolicyActivationFile(jobId: string): string {
  return path.join(loadRunnerConfig().jobsDir, `${jobId}_policy_activation.json`);
}

function readJobPolicyActivationState(jobId: string): StoredPolicyActivationState {
  const raw = asRecord(readJsonFile(getJobPolicyActivationFile(jobId))) ?? {};
  const overridesRaw = asRecord(raw.overrides) ?? {};
  const overrides: Record<string, boolean> = {};

  for (const [key, value] of Object.entries(overridesRaw)) {
    if (typeof value !== "boolean") {
      continue;
    }
    const normalizedKey = normalizePolicyId(key);
    if (!normalizedKey) {
      continue;
    }
    overrides[normalizedKey] = value;
  }

  return {
    updated_at: typeof raw.updated_at === "string" ? raw.updated_at : nowIso(),
    overrides,
  };
}

function writeJobPolicyActivationState(jobId: string, payload: StoredPolicyActivationState): void {
  fs.writeFileSync(getJobPolicyActivationFile(jobId), JSON.stringify(payload, null, 2), "utf-8");
}

function resolveRuntimeEnabled(
  policyId: string,
  enabledByDefault: boolean,
  overrides: Record<string, boolean>,
): boolean {
  const override = overrides[normalizePolicyId(policyId)];
  return typeof override === "boolean" ? override : enabledByDefault;
}

function defaultActionsForProfile(profile: JobPolicyExecutionProfile, explicitEntities: string[]): Record<string, unknown> {
  const normalizedEntities = explicitEntities.length > 0 ? explicitEntities : ["record_id", "document_date", "total_amount"];

  if (profile === "fast_local") {
    return {
      preprocess: {
        ocr: { enabled: true, passes: 1, psm: 6 },
        deskew: { enabled: false },
        denoise: { enabled: false, strength: "light" },
        table_extract: { enabled: false, type: "heuristic" },
      },
      extraction: {
        explicit_entities: normalizedEntities,
        model_tier: "local",
        ruleset: "job_custom_fast_local",
      },
      recovery: {
        strategy: "regex",
      },
      chunking: {
        chunk_size: 240,
        chunk_overlap: 32,
        max_chunks: 64,
      },
    };
  }

  if (profile === "cloud_extension") {
    return {
      preprocess: {
        ocr: { enabled: true, passes: 2, psm: 6, alt_psm: [4, 11] },
        deskew: { enabled: true },
        denoise: { enabled: true, strength: "standard" },
        table_extract: { enabled: true, type: "heuristic" },
      },
      extraction: {
        explicit_entities: normalizedEntities,
        model_tier: "cloud",
        ruleset: "job_custom_cloud_extension",
      },
      recovery: {
        strategy: "alternate_rules",
      },
      chunking: {
        chunk_size: 320,
        chunk_overlap: 48,
        max_chunks: 128,
      },
      retrieval: {
        dense_k: 10,
        sparse_k: 10,
        final_k: 10,
        mmr_lambda: 0.68,
        metadata_boost: 0.12,
      },
      token_budget: {
        max_tokens: 1800,
        reserved_tokens: 240,
        strategy: "simple",
      },
      escalation: {
        tier: "tier2",
      },
    };
  }

  return {
    preprocess: {
      ocr: { enabled: true, passes: 2, psm: 6, alt_psm: [4, 11] },
      deskew: { enabled: true },
      denoise: { enabled: true, strength: "standard" },
      table_extract: { enabled: true, type: "heuristic" },
    },
    extraction: {
      explicit_entities: normalizedEntities,
      model_tier: "local",
      ruleset: "job_custom_balanced",
    },
    recovery: {
      strategy: "regex",
    },
    chunking: {
      chunk_size: 280,
      chunk_overlap: 40,
      max_chunks: 96,
    },
    retrieval: {
      dense_k: 8,
      sparse_k: 8,
      final_k: 8,
      mmr_lambda: 0.6,
      metadata_boost: 0.08,
    },
  };
}

function extractExecutionSettings(actions: Record<string, unknown>, profile: JobPolicyExecutionProfile): JobPolicyExecutionSettings {
  const preprocess = asRecord(actions.preprocess) ?? {};
  const ocr = asRecord(preprocess.ocr) ?? {};
  const deskew = asRecord(preprocess.deskew) ?? {};
  const denoise = asRecord(preprocess.denoise) ?? {};
  const tableExtract = asRecord(preprocess.table_extract) ?? {};
  const extraction = asRecord(actions.extraction) ?? {};
  const recovery = asRecord(actions.recovery) ?? {};
  const chunking = asRecord(actions.chunking) ?? {};
  const retrieval = asRecord(actions.retrieval) ?? {};
  const tokenBudget = asRecord(actions.token_budget) ?? {};
  const escalation = asRecord(actions.escalation) ?? {};

  return {
    ocrEnabled: typeof ocr.enabled === "boolean" ? ocr.enabled : true,
    ocrPasses: Math.max(1, asNumber(ocr.passes) ?? (profile === "fast_local" ? 1 : 2)),
    ocrPsm: asNumber(ocr.psm) ?? 6,
    ocrAltPsm: Array.isArray(ocr.alt_psm) ? ocr.alt_psm.map((value) => asNumber(value)).filter((value): value is number => value != null) : [],
    deskewEnabled: typeof deskew.enabled === "boolean" ? deskew.enabled : profile !== "fast_local",
    denoiseEnabled: typeof denoise.enabled === "boolean" ? denoise.enabled : profile !== "fast_local",
    denoiseStrength: typeof denoise.strength === "string" && denoise.strength.trim() ? denoise.strength : profile === "fast_local" ? "light" : "standard",
    tableExtractEnabled: typeof tableExtract.enabled === "boolean" ? tableExtract.enabled : profile !== "fast_local",
    tableExtractType: typeof tableExtract.type === "string" && tableExtract.type.trim() ? tableExtract.type : "heuristic",
    modelTier: extraction.model_tier === "cloud" ? "cloud" : "local",
    ruleset: typeof extraction.ruleset === "string" && extraction.ruleset.trim() ? extraction.ruleset : `job_custom_${profile}`,
    recoveryStrategy: typeof recovery.strategy === "string" && recovery.strategy.trim() ? recovery.strategy : "regex",
    chunkSize: Math.max(64, asNumber(chunking.chunk_size) ?? (profile === "fast_local" ? 240 : profile === "cloud_extension" ? 320 : 280)),
    chunkOverlap: Math.max(0, asNumber(chunking.chunk_overlap) ?? (profile === "fast_local" ? 32 : profile === "cloud_extension" ? 48 : 40)),
    maxChunks: Math.max(1, asNumber(chunking.max_chunks) ?? (profile === "fast_local" ? 64 : profile === "cloud_extension" ? 128 : 96)),
    denseK: asNumber(retrieval.dense_k),
    sparseK: asNumber(retrieval.sparse_k),
    finalK: asNumber(retrieval.final_k),
    mmrLambda: asNumber(retrieval.mmr_lambda),
    metadataBoost: asNumber(retrieval.metadata_boost),
    maxTokens: asNumber(tokenBudget.max_tokens),
    reservedTokens: asNumber(tokenBudget.reserved_tokens),
    tokenStrategy: typeof tokenBudget.strategy === "string" && tokenBudget.strategy.trim() ? tokenBudget.strategy : null,
    escalationTier: typeof escalation.tier === "string" && escalation.tier.trim() ? escalation.tier : null,
  };
}

function normalizeExecutionSettings(
  value: Partial<JobPolicyExecutionSettings> | null | undefined,
  profile: JobPolicyExecutionProfile,
): JobPolicyExecutionSettings {
  const defaults = extractExecutionSettings(defaultActionsForProfile(profile, []), profile);
  return {
    ocrEnabled: typeof value?.ocrEnabled === "boolean" ? value.ocrEnabled : defaults.ocrEnabled,
    ocrPasses: Math.max(1, typeof value?.ocrPasses === "number" ? value.ocrPasses : defaults.ocrPasses),
    ocrPsm: typeof value?.ocrPsm === "number" ? value.ocrPsm : defaults.ocrPsm,
    ocrAltPsm: Array.isArray(value?.ocrAltPsm) ? value.ocrAltPsm.map((item) => Number(item)).filter((item) => Number.isFinite(item)) : defaults.ocrAltPsm,
    deskewEnabled: typeof value?.deskewEnabled === "boolean" ? value.deskewEnabled : defaults.deskewEnabled,
    denoiseEnabled: typeof value?.denoiseEnabled === "boolean" ? value.denoiseEnabled : defaults.denoiseEnabled,
    denoiseStrength: typeof value?.denoiseStrength === "string" && value.denoiseStrength.trim() ? value.denoiseStrength.trim() : defaults.denoiseStrength,
    tableExtractEnabled: typeof value?.tableExtractEnabled === "boolean" ? value.tableExtractEnabled : defaults.tableExtractEnabled,
    tableExtractType: typeof value?.tableExtractType === "string" && value.tableExtractType.trim() ? value.tableExtractType.trim() : defaults.tableExtractType,
    modelTier: value?.modelTier === "cloud" ? "cloud" : value?.modelTier === "local" ? "local" : defaults.modelTier,
    ruleset: typeof value?.ruleset === "string" && value.ruleset.trim() ? value.ruleset.trim() : defaults.ruleset,
    recoveryStrategy: typeof value?.recoveryStrategy === "string" && value.recoveryStrategy.trim() ? value.recoveryStrategy.trim() : defaults.recoveryStrategy,
    chunkSize: Math.max(64, typeof value?.chunkSize === "number" ? value.chunkSize : defaults.chunkSize),
    chunkOverlap: Math.max(0, typeof value?.chunkOverlap === "number" ? value.chunkOverlap : defaults.chunkOverlap),
    maxChunks: Math.max(1, typeof value?.maxChunks === "number" ? value.maxChunks : defaults.maxChunks),
    denseK: typeof value?.denseK === "number" ? value.denseK : defaults.denseK,
    sparseK: typeof value?.sparseK === "number" ? value.sparseK : defaults.sparseK,
    finalK: typeof value?.finalK === "number" ? value.finalK : defaults.finalK,
    mmrLambda: typeof value?.mmrLambda === "number" ? value.mmrLambda : defaults.mmrLambda,
    metadataBoost: typeof value?.metadataBoost === "number" ? value.metadataBoost : defaults.metadataBoost,
    maxTokens: typeof value?.maxTokens === "number" ? value.maxTokens : defaults.maxTokens,
    reservedTokens: typeof value?.reservedTokens === "number" ? value.reservedTokens : defaults.reservedTokens,
    tokenStrategy: typeof value?.tokenStrategy === "string" && value.tokenStrategy.trim() ? value.tokenStrategy.trim() : defaults.tokenStrategy,
    escalationTier: typeof value?.escalationTier === "string" && value.escalationTier.trim() ? value.escalationTier.trim() : defaults.escalationTier,
  };
}

function buildActionsFromSettings(settings: JobPolicyExecutionSettings, explicitEntities: string[]): Record<string, unknown> {
  const actions: Record<string, unknown> = {
    preprocess: {
      ocr: {
        enabled: settings.ocrEnabled,
        passes: settings.ocrPasses,
        psm: settings.ocrPsm,
        ...(settings.ocrAltPsm.length > 0 ? { alt_psm: settings.ocrAltPsm } : {}),
      },
      deskew: {
        enabled: settings.deskewEnabled,
      },
      denoise: {
        enabled: settings.denoiseEnabled,
        strength: settings.denoiseStrength,
      },
      table_extract: {
        enabled: settings.tableExtractEnabled,
        type: settings.tableExtractType,
      },
    },
    extraction: {
      explicit_entities: explicitEntities.length > 0 ? explicitEntities : ["record_id", "document_date", "total_amount"],
      model_tier: settings.modelTier,
      ruleset: settings.ruleset,
    },
    recovery: {
      strategy: settings.recoveryStrategy,
    },
    chunking: {
      chunk_size: settings.chunkSize,
      chunk_overlap: settings.chunkOverlap,
      max_chunks: settings.maxChunks,
    },
  };

  if (
    settings.denseK != null ||
    settings.sparseK != null ||
    settings.finalK != null ||
    settings.mmrLambda != null ||
    settings.metadataBoost != null
  ) {
    actions.retrieval = {
      ...(settings.denseK != null ? { dense_k: settings.denseK } : {}),
      ...(settings.sparseK != null ? { sparse_k: settings.sparseK } : {}),
      ...(settings.finalK != null ? { final_k: settings.finalK } : {}),
      ...(settings.mmrLambda != null ? { mmr_lambda: settings.mmrLambda } : {}),
      ...(settings.metadataBoost != null ? { metadata_boost: settings.metadataBoost } : {}),
    };
  }

  if (settings.maxTokens != null || settings.reservedTokens != null || settings.tokenStrategy) {
    actions.token_budget = {
      ...(settings.maxTokens != null ? { max_tokens: settings.maxTokens } : {}),
      ...(settings.reservedTokens != null ? { reserved_tokens: settings.reservedTokens } : {}),
      ...(settings.tokenStrategy ? { strategy: settings.tokenStrategy } : {}),
    };
  }

  if (settings.escalationTier) {
    actions.escalation = {
      tier: settings.escalationTier,
    };
  }

  return actions;
}

function buildMetadataForProfile(profile: JobPolicyExecutionProfile, instructions?: string | null): Record<string, unknown> {
  const metadata: Record<string, unknown> = {
    source: "job_custom",
    execution_profile: profile,
    operator_instructions: instructions?.trim() || null,
    created_at: nowIso(),
  };

  if (profile === "cloud_extension") {
    metadata.extension_type = "cloud_optional";
    metadata.cost_profile = "high cost optional extension";
    metadata.when_used = "Optional paid extension for this job when local policies are not enough.";
    metadata.why = "Uses the same policy-selection system but allows an explicit cloud execution path when the operator chooses to pay for stronger inference.";
    metadata.tradeoff = "Higher cost and latency than local policies.";
  }

  return metadata;
}

function buildConditions(input: JobPolicyCreateInput): Record<string, unknown> {
  const conditions: Record<string, unknown> = {};
  const routeBins = asStringArray(input.routeBins);
  const contentProfiles = asStringArray(input.contentProfiles);
  const vendorClusters = asStringArray(input.vendorClusters);
  const docTypes = asStringArray(input.docTypes);

  if (routeBins.length > 0) {
    conditions.route_bin = routeBins;
  }
  if (contentProfiles.length > 0) {
    conditions.content_profile = contentProfiles;
  }
  if (vendorClusters.length > 0) {
    conditions.vendor_cluster = vendorClusters;
  }
  if (docTypes.length > 0) {
    conditions.doc_type = docTypes;
  }
  return conditions;
}

function buildCustomPolicyRecord(input: JobPolicyCreateInput): RawPolicyRecord {
  const policyId = normalizePolicyId(input.policyId);
  const name = input.name.trim() || titleCase(policyId);
  const explicitEntities = asStringArray(input.explicitEntities);
  const executionProfile = normalizeExecutionProfile(input.executionProfile);
  const executionSettings = normalizeExecutionSettings(input.executionSettings ?? null, executionProfile);
  return {
    policy_id: policyId,
    name,
    conditions: buildConditions(input),
    actions: buildActionsFromSettings(executionSettings, explicitEntities),
    metadata: {
      ...buildMetadataForProfile(executionProfile, input.instructions),
      ...(input.basePolicyId ? { base_policy_id: normalizePolicyId(input.basePolicyId) } : {}),
      execution_settings: executionSettings,
    },
  };
}

function policyAvailability(isExtension: boolean, runtimeEnabled: boolean): JobPolicyAvailability {
  if (isExtension) {
    return runtimeEnabled ? "active_extension" : "inactive_extension";
  }
  return runtimeEnabled ? "active" : "inactive";
}

function buildPolicyCatalog(jobId?: string): {
  defaultPolicyId: string;
  sourcePath: string;
  extensionSourcePath: string | null;
  items: Array<{
    policy: RawPolicyRecord;
    isExtension: boolean;
    runtimeEnabled: boolean;
  }>;
} {
  const base = readBasePolicyStore();
  const custom = jobId ? readJobCustomPolicies(jobId) : { updated_at: nowIso(), policies: [] };
  const extensions = readExtensionPolicyStore();
  const activationOverrides = jobId ? readJobPolicyActivationState(jobId).overrides : {};
  const items = new Map<
    string,
    {
      policy: RawPolicyRecord;
      isExtension: boolean;
      defaultRuntimeEnabled: boolean;
    }
  >();

  for (const policy of base.items) {
    items.set(policy.policy_id, {
      policy,
      isExtension: false,
      defaultRuntimeEnabled: true,
    });
  }

  for (const policy of custom.policies) {
    items.set(policy.policy_id, {
      policy,
      isExtension: false,
      defaultRuntimeEnabled: true,
    });
  }

  for (const policy of extensions.items) {
    if (items.has(policy.policy_id)) {
      continue;
    }
    items.set(policy.policy_id, {
      policy,
      isExtension: true,
      defaultRuntimeEnabled: extensions.enabledByDefault,
    });
  }

  const catalogItems = [...items.values()].map(({ policy, isExtension, defaultRuntimeEnabled }) => ({
    policy,
    isExtension,
    runtimeEnabled: resolveRuntimeEnabled(policy.policy_id, defaultRuntimeEnabled, activationOverrides),
  }));

  const activeItems = catalogItems.filter((entry) => entry.runtimeEnabled);
  const defaultPolicyId = activeItems.some((entry) => entry.policy.policy_id === base.defaultPolicyId)
    ? base.defaultPolicyId
    : activeItems[0]?.policy.policy_id ?? base.defaultPolicyId;

  return {
    defaultPolicyId,
    sourcePath: custom.policies.length > 0 ? `${base.sourcePath} + job_custom` : base.sourcePath,
    extensionSourcePath: extensions.sourcePath,
    items: catalogItems,
  };
}

function mergePolicies(jobId?: string): { defaultPolicyId: string; sourcePath: string; items: RawPolicyRecord[] } {
  const catalog = buildPolicyCatalog(jobId);
  return {
    defaultPolicyId: catalog.defaultPolicyId,
    sourcePath: catalog.sourcePath,
    items: catalog.items.filter((entry) => entry.runtimeEnabled).map((entry) => entry.policy),
  };
}

function listVisiblePolicies(jobId?: string): {
  defaultPolicyId: string;
  sourcePath: string;
  items: Array<{
    policy: RawPolicyRecord;
    availability: JobPolicyAvailability;
    runtimeEnabled: boolean;
    runtimeToggleAllowed: boolean;
  }>;
} {
  const catalog = buildPolicyCatalog(jobId);
  const sourceParts = [catalog.sourcePath];
  const extensionItems = catalog.items.filter((entry) => entry.isExtension);
  if (extensionItems.length > 0 && catalog.extensionSourcePath) {
    const enabledCount = extensionItems.filter((entry) => entry.runtimeEnabled).length;
    const disabledCount = Math.max(extensionItems.length - enabledCount, 0);
    sourceParts.push(`${catalog.extensionSourcePath} (${enabledCount} enabled, ${disabledCount} disabled cloud extensions)`);
  }

  return {
    defaultPolicyId: catalog.defaultPolicyId,
    sourcePath: sourceParts.join(" + "),
    items: catalog.items.map(({ policy, isExtension, runtimeEnabled }) => ({
      policy,
      availability: policyAvailability(isExtension, runtimeEnabled),
      runtimeEnabled,
      runtimeToggleAllowed: true,
    })),
  };
}

function sourceForPolicy(policy: RawPolicyRecord): JobPolicySource {
  return policy.metadata.source === "job_custom" ? "custom" : "default";
}

function availabilityRank(value: JobPolicyAvailability): number {
  if (value === "inactive" || value === "inactive_extension") {
    return 1;
  }
  return 0;
}

function learningStateForPolicy(reviewedDocuments: number, meanExactF1: number | null, totalUses: number): JobPolicyLearningState {
  if (totalUses === 0) {
    return "unused";
  }
  if (reviewedDocuments === 0 || meanExactF1 == null) {
    return "candidate";
  }
  if (reviewedDocuments >= 2 && meanExactF1 >= 0.75) {
    return "promoted";
  }
  if (reviewedDocuments >= 2 && meanExactF1 < 0.5) {
    return "demoted";
  }
  return "watch";
}

function isAhmnAdviceSource(source: string | null | undefined, adviceStatus: string | null | undefined, mode: "adaptive" | "strict"): boolean {
  const normalizedSource = (source ?? "").trim().toLowerCase();
  if (normalizedSource === "job_overlay" || normalizedSource === "fallback" || normalizedSource === "static_fallback" || normalizedSource === "static") {
    return false;
  }
  if (mode === "strict" || adviceStatus === "static") {
    return false;
  }
  return true;
}

function meanAhmnConfidence(usages: JobPolicyUsage[]): number | null {
  const confidences = usages
    .filter((usage) => isAhmnAdviceSource(usage.adviceSource, usage.adviceStatus, usage.mode))
    .map((usage) => (typeof usage.adviceConfidence === "number" ? usage.adviceConfidence : null))
    .filter((value): value is number => value != null);

  if (confidences.length === 0) {
    return null;
  }
  const mean = confidences.reduce((total, value) => total + value, 0) / confidences.length;
  return Math.round(mean * 100) / 100;
}

export function ensureJobEffectivePolicyStore(jobId: string): string {
  const merged = mergePolicies(jobId);
  const outPath = path.join(loadRunnerConfig().jobsDir, `${jobId}_effective_policies.json`);
  fs.writeFileSync(
    outPath,
    JSON.stringify(
      {
        default_policy_id: merged.defaultPolicyId,
        policies: merged.items,
      },
      null,
      2,
    ),
    "utf-8",
  );
  return outPath;
}

export function setJobPolicyRuntimeEnabled(jobId: string, policyId: string, enabled: boolean): PolicyDetail {
  getJobOrThrow(jobId);
  const normalizedId = normalizePolicyId(policyId);
  if (!normalizedId) {
    throw new Error("policyId is required");
  }

  const current = getPolicyDetail(jobId, normalizedId);
  if (!current) {
    throw new Error(`Unknown policy '${normalizedId}'`);
  }
  const activationState = readJobPolicyActivationState(jobId);
  activationState.overrides[normalizedId] = enabled;

  const nextVisible = listVisiblePolicies(jobId).items.map((item) =>
    item.policy.policy_id === normalizedId
      ? {
          ...item,
          runtimeEnabled: enabled,
        }
      : item,
  );
  const enabledCount = nextVisible.filter((item) => item.runtimeEnabled).length;
  if (enabledCount === 0) {
    throw new Error("At least one policy must stay enabled for a job");
  }

  activationState.updated_at = nowIso();
  writeJobPolicyActivationState(jobId, activationState);
  ensureJobEffectivePolicyStore(jobId);
  return getPolicyDetail(jobId, normalizedId)!;
}

export function createJobCustomPolicy(jobId: string, input: JobPolicyCreateInput): PolicyDetail {
  getJobOrThrow(jobId);
  const policyRecord = buildCustomPolicyRecord(input);
  if (!policyRecord.policy_id) {
    throw new Error("policyId is required");
  }

  const stored = readJobCustomPolicies(jobId);
  const existing = stored.policies.find((policy) => policy.policy_id === policyRecord.policy_id);
  if (existing) {
    throw new Error(`Policy '${policyRecord.policy_id}' already exists for this job`);
  }

  stored.policies.push(policyRecord);
  stored.updated_at = nowIso();
  writeJobCustomPolicies(jobId, stored);
  ensureJobEffectivePolicyStore(jobId);
  return getPolicyDetail(jobId, policyRecord.policy_id)!;
}

export function getPolicyDetail(jobId: string | null, policyId: string): PolicyDetail | null {
  const normalizedId = normalizePolicyId(policyId);
  if (!normalizedId) {
    return null;
  }

  const store = listVisiblePolicies(jobId ?? undefined);
  const match = store.items.find((item) => item.policy.policy_id === normalizedId);
  if (!match) {
    return null;
  }

  return {
    policyId: normalizedId,
    name: match.policy.name,
    source: sourceForPolicy(match.policy),
    availability: match.availability,
    runtimeEnabled: match.runtimeEnabled,
    runtimeToggleAllowed: match.runtimeToggleAllowed,
    conditions: match.policy.conditions,
    actions: match.policy.actions,
    metadata: match.policy.metadata,
    defaultPolicyId: store.defaultPolicyId,
    sourcePath: store.sourcePath,
  };
}

export function listJobPolicies(jobId: string): JobPolicyWorkspace {
  const job = getJobOrThrow(jobId);
  const store = listVisiblePolicies(jobId);
  const usageByPolicy = new Map<
    string,
    {
      processed: number;
      failed: number;
      reviewed: number;
      totalF1: number;
      autoReviewed: number;
      totalAutoF1: number;
      reviewedScores: Array<{ exactF1: number; updatedAt: string }>;
      docs: Set<string>;
      lastUsedAt: string | null;
    }
  >();

  for (const document of job.documents ?? []) {
    for (const outcome of document.outcomes) {
      const policyId = typeof outcome.policy === "string" ? normalizePolicyId(outcome.policy) : "";
      if (!policyId) {
        continue;
      }
      const bucket = usageByPolicy.get(policyId) ?? {
        processed: 0,
        failed: 0,
        reviewed: 0,
        totalF1: 0,
        autoReviewed: 0,
        totalAutoF1: 0,
        reviewedScores: [],
        docs: new Set<string>(),
        lastUsedAt: null,
      };
      if (outcome.status === "processed") {
        bucket.processed += 1;
        bucket.docs.add(document.fileId);
      } else if (outcome.status === "failed") {
        bucket.failed += 1;
      }
      if (outcome.reviewStatus === "human_reviewed" && typeof outcome.exactF1 === "number") {
        bucket.reviewed += 1;
        bucket.totalF1 += outcome.exactF1;
        bucket.reviewedScores.push({ exactF1: outcome.exactF1, updatedAt: document.updatedAt });
      } else if (outcome.reviewStatus === "ai_validated" && typeof outcome.exactF1 === "number") {
        bucket.autoReviewed += 1;
        bucket.totalAutoF1 += outcome.exactF1;
      }
      if (!bucket.lastUsedAt || document.updatedAt > bucket.lastUsedAt) {
        bucket.lastUsedAt = document.updatedAt;
      }
      usageByPolicy.set(policyId, bucket);
    }
  }

  const policies = store.items.map<JobPolicySummary>(({ policy, availability, runtimeEnabled, runtimeToggleAllowed }) => {
    const usage = usageByPolicy.get(policy.policy_id);
    const meanExactF1 = usage && usage.reviewed > 0 ? usage.totalF1 / usage.reviewed : null;
    const meanAutoReviewF1 = usage && usage.autoReviewed > 0 ? usage.totalAutoF1 / usage.autoReviewed : null;
    const policyUsages = getJobPolicyUsage(jobId, policy.policy_id);
    const learning = summarizeJobPolicyLearning(policyUsages);
    return {
      policyId: policy.policy_id,
      name: policy.name,
      source: sourceForPolicy(policy),
      availability,
      runtimeEnabled,
      runtimeToggleAllowed,
      conditions: policy.conditions,
      actions: policy.actions,
      metadata: policy.metadata,
      defaultPolicyId: store.defaultPolicyId,
      sourcePath: store.sourcePath,
      documentsProcessed: usage?.processed ?? 0,
      documentsFailed: usage?.failed ?? 0,
      uniqueDocumentsUsed: usage?.docs.size ?? 0,
      reviewedDocuments: usage?.reviewed ?? 0,
      meanExactF1,
      ahmnConfidence: meanAhmnConfidence(policyUsages),
      autoReviewedDocuments: usage?.autoReviewed ?? 0,
      meanAutoReviewF1,
      learningState: learningStateForPolicy(usage?.reviewed ?? 0, meanExactF1, (usage?.processed ?? 0) + (usage?.failed ?? 0)),
      lastUsedAt: usage?.lastUsedAt ?? null,
      learning,
      leaderboardRank: null,
    };
  });

  const leaderboard = [...policies].sort((left, right) => {
    const leftF1 = left.meanExactF1 ?? -1;
    const rightF1 = right.meanExactF1 ?? -1;
    if (rightF1 !== leftF1) {
      return rightF1 - leftF1;
    }
    if (right.reviewedDocuments !== left.reviewedDocuments) {
      return right.reviewedDocuments - left.reviewedDocuments;
    }
    if (right.documentsProcessed !== left.documentsProcessed) {
      return right.documentsProcessed - left.documentsProcessed;
    }
    const leftConfidence = left.ahmnConfidence ?? -1;
    const rightConfidence = right.ahmnConfidence ?? -1;
    if (rightConfidence !== leftConfidence) {
      return rightConfidence - leftConfidence;
    }
    const leftAvailabilityRank = availabilityRank(left.availability);
    const rightAvailabilityRank = availabilityRank(right.availability);
    if (leftAvailabilityRank !== rightAvailabilityRank) {
      return leftAvailabilityRank - rightAvailabilityRank;
    }
    return left.name.localeCompare(right.name);
  });

  const rankedPolicies = policies.map((policy) => {
    const rank = leaderboard.findIndex((entry) => entry.policyId === policy.policyId);
    return {
      ...policy,
      leaderboardRank: rank >= 0 ? rank + 1 : null,
    };
  });

  return {
    sourcePath: store.sourcePath,
    defaultPolicyId: store.defaultPolicyId,
    policies: rankedPolicies,
    leaderboard: rankedPolicies
      .filter((policy) => policy.leaderboardRank != null)
      .sort((left, right) => (left.leaderboardRank ?? 999) - (right.leaderboardRank ?? 999)),
    customPolicyCount: policies.filter((policy) => policy.source === "custom").length,
    defaultPolicyCount: policies.filter((policy) => policy.source === "default").length,
  };
}

export function getSuggestedJobPolicyMatching(jobId: string): JobPolicySuggestedMatching {
  const job = getJobOrThrow(jobId);
  const reviewContext = readJobValidationContext(jobId);
  const vendorClusters = uniqueStrings(reviewContext?.current.summary.knownVendors ?? [], 8);
  const docTypes: string[] = [];
  const contentProfiles: string[] = [];

  for (const document of job.documents ?? []) {
    if (!document.latestRunId || !document.latestDocId) {
      continue;
    }
    try {
      const detail = getRunDocument(document.latestRunId, document.latestDocId);
      const metadata = asRecord(detail.metadata) ?? {};
      if (typeof metadata.vendorCluster === "string") {
        vendorClusters.push(metadata.vendorCluster);
      }
      if (typeof metadata.docType === "string") {
        docTypes.push(metadata.docType);
      }
      if (typeof metadata.profile === "string") {
        contentProfiles.push(metadata.profile);
      }
    } catch {
      continue;
    }
  }

  return {
    vendorClusters: uniqueStrings(vendorClusters, 8),
    docTypes: uniqueStrings(docTypes, 8),
    contentProfiles: uniqueStrings(contentProfiles, 8),
  };
}

export function getJobPolicyTemplates(jobId: string): JobPolicyTemplate[] {
  const store = listVisiblePolicies(jobId);
  return store.items.map(({ policy }) => {
    const extraction = asRecord(policy.actions.extraction) ?? {};
    const explicitEntities = asStringArray(extraction.explicit_entities);
    const executionProfile = normalizeExecutionProfile(policy.metadata.execution_profile);
    return {
      policyId: policy.policy_id,
      name: policy.name,
      source: sourceForPolicy(policy),
      executionProfile,
      explicitEntities,
      operatorInstructions:
        typeof policy.metadata.operator_instructions === "string" ? policy.metadata.operator_instructions : "",
      executionSettings: normalizeExecutionSettings(
        asRecord(policy.metadata.execution_settings) as Partial<JobPolicyExecutionSettings> | null,
        executionProfile,
      ),
    };
  });
}

export function getJobPolicyUsage(jobId: string, policyId: string): JobPolicyUsage[] {
  const normalizedId = normalizePolicyId(policyId);
  const job = getJobOrThrow(jobId);
  const usages: JobPolicyUsage[] = [];

  for (const document of job.documents ?? []) {
    for (const outcome of document.outcomes) {
      const outcomePolicy = typeof outcome.policy === "string" ? normalizePolicyId(outcome.policy) : "";
      if (outcomePolicy !== normalizedId) {
        continue;
      }
      usages.push({
        fileId: document.fileId,
        fileName: document.fileName,
        runId: outcome.runId,
        docId: outcome.docId,
        mode: outcome.mode,
        status: outcome.status,
        route: outcome.route,
        exactF1: outcome.exactF1 ?? null,
        reviewStatus: outcome.reviewStatus ?? null,
        updatedAt: document.updatedAt,
      });
    }
  }

  for (const usage of usages) {
    if (!usage.runId || !usage.docId) {
      continue;
    }
    try {
      const detail = getRunDocument(usage.runId, usage.docId);
      const metadata = asRecord(detail.metadata) ?? {};
      const review = asRecord(detail.review) ?? {};
      const ahmnFeedback = asRecord(review.ahmnReviewFeedback) ?? {};
      usage.adviceSource = typeof metadata.adviceSource === "string" ? metadata.adviceSource : null;
      usage.adviceStatus = typeof metadata.adviceStatus === "string" ? metadata.adviceStatus : null;
      usage.adviceConfidence = typeof metadata.adviceConfidence === "number" ? metadata.adviceConfidence : null;
      usage.retrievalSource = typeof metadata.retrievalSource === "string" ? metadata.retrievalSource : null;
      usage.rabiUsed = typeof metadata.rabiUsed === "boolean" ? metadata.rabiUsed : false;
      usage.nNeighbors = typeof metadata.nNeighbors === "number" ? metadata.nNeighbors : null;
      usage.reviewedLearningLogged =
        typeof ahmnFeedback.logged === "boolean" ? ahmnFeedback.logged : null;
      usage.reviewedLearningError =
        typeof ahmnFeedback.error === "string" ? ahmnFeedback.error : null;
    } catch {
      usage.adviceSource = null;
      usage.adviceStatus = null;
      usage.adviceConfidence = null;
      usage.retrievalSource = null;
      usage.rabiUsed = false;
      usage.nNeighbors = null;
      usage.reviewedLearningLogged = null;
      usage.reviewedLearningError = null;
    }
  }

  return usages.sort((left, right) => (left.updatedAt < right.updatedAt ? 1 : -1));
}

export function summarizeJobPolicyLearning(usages: JobPolicyUsage[]): JobPolicyLearningSummary {
  let ahmnRouteCount = 0;
  let jobOverlayRouteCount = 0;
  let fallbackRouteCount = 0;
  let staticRouteCount = 0;
  let warmStartCount = 0;
  let neighborTotal = 0;
  let neighborCount = 0;
  let maxNeighborCount = 0;
  let reviewedLearningLoggedCount = 0;
  let reviewedLearningPendingCount = 0;

  for (const usage of usages) {
    const source = (usage.adviceSource ?? "").trim().toLowerCase();
    if (source === "job_overlay") {
      jobOverlayRouteCount += 1;
    } else if (source === "fallback" || source === "static_fallback") {
      fallbackRouteCount += 1;
    } else if (source === "static" || usage.adviceStatus === "static" || usage.mode === "strict") {
      staticRouteCount += 1;
    } else {
      ahmnRouteCount += 1;
    }

    if (usage.rabiUsed) {
      warmStartCount += 1;
    }
    if (typeof usage.nNeighbors === "number") {
      neighborTotal += usage.nNeighbors;
      neighborCount += 1;
      if (usage.nNeighbors > maxNeighborCount) {
        maxNeighborCount = usage.nNeighbors;
      }
    }
    if (usage.reviewStatus && usage.reviewStatus !== "unreviewed") {
      if (usage.reviewedLearningLogged) {
        reviewedLearningLoggedCount += 1;
      } else {
        reviewedLearningPendingCount += 1;
      }
    }
  }

  return {
    selectionMode: "thompson_sampling",
    ahmnRouteCount,
    jobOverlayRouteCount,
    fallbackRouteCount,
    staticRouteCount,
    warmStartCount,
    meanNeighborCount: neighborCount > 0 ? neighborTotal / neighborCount : null,
    maxNeighborCount: neighborCount > 0 ? maxNeighborCount : null,
    reviewedLearningLoggedCount,
    reviewedLearningPendingCount,
    rabiDecayState: warmStartCount > 0 ? "active" : "unused",
    driftAwarenessState: "active",
  };
}

export function getJobPolicyDetail(jobId: string, policyId: string): {
  policy: PolicyDetail;
  usages: JobPolicyUsage[];
  summary: JobPolicySummary | null;
  learning: JobPolicyLearningSummary;
} | null {
  const policy = getPolicyDetail(jobId, policyId);
  if (!policy) {
    return null;
  }
  const workspace = listJobPolicies(jobId);
  const usages = getJobPolicyUsage(jobId, policyId);
  return {
    policy,
    usages,
    summary: workspace.policies.find((entry) => entry.policyId === policy.policyId) ?? null,
    learning: summarizeJobPolicyLearning(usages),
  };
}
