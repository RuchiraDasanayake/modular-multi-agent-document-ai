import fs from "node:fs";
import path from "node:path";
import { loadRunnerConfig } from "@/server/config";
import { getJobOrThrow } from "@/server/jobs";

interface PolicyStorePayload {
  default_policy_id?: unknown;
  policies?: unknown;
}

interface RawPolicyRecord {
  policy_id: string;
  name: string;
  conditions: Record<string, unknown>;
  actions: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export type JobPolicySource = "default" | "custom";
export type JobPolicyLearningState = "promoted" | "watch" | "demoted" | "candidate" | "unused";
export type JobPolicyExecutionProfile = "fast_local" | "balanced" | "heavy_cloud";

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
  updatedAt: string;
}

export interface PolicyDetail {
  policyId: string;
  name: string;
  source: JobPolicySource;
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
  learningState: JobPolicyLearningState;
  lastUsedAt: string | null;
}

export interface JobPolicyWorkspace {
  sourcePath: string;
  defaultPolicyId: string;
  policies: JobPolicySummary[];
  leaderboard: JobPolicySummary[];
  customPolicyCount: number;
  defaultPolicyCount: number;
}

export interface JobPolicyCreateInput {
  policyId: string;
  name: string;
  executionProfile: JobPolicyExecutionProfile;
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

function buildActionsForProfile(profile: JobPolicyExecutionProfile, explicitEntities: string[]): Record<string, unknown> {
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

  if (profile === "heavy_cloud") {
    return {
      preprocess: {
        ocr: { enabled: true, passes: 3, psm: 4, alt_psm: [6, 11] },
        deskew: { enabled: true },
        denoise: { enabled: true, strength: "aggressive" },
        table_extract: { enabled: true, type: "heuristic" },
      },
      extraction: {
        explicit_entities: normalizedEntities,
        model_tier: "cloud",
        ruleset: "job_custom_heavy_cloud",
      },
      recovery: {
        strategy: "alternate_rules",
      },
      escalation: {
        tier: "tier2",
      },
      chunking: {
        chunk_size: 320,
        chunk_overlap: 48,
        max_chunks: 144,
      },
      retrieval: {
        dense_k: 10,
        sparse_k: 12,
        final_k: 10,
        mmr_lambda: 0.7,
        metadata_boost: 0.12,
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
  return {
    policy_id: policyId,
    name,
    conditions: buildConditions(input),
    actions: buildActionsForProfile(input.executionProfile, explicitEntities),
    metadata: {
      source: "job_custom",
      execution_profile: input.executionProfile,
      operator_instructions: input.instructions?.trim() || null,
      created_at: nowIso(),
    },
  };
}

function mergePolicies(jobId?: string): { defaultPolicyId: string; sourcePath: string; items: RawPolicyRecord[] } {
  const base = readBasePolicyStore();
  if (!jobId) {
    return base;
  }

  const custom = readJobCustomPolicies(jobId);
  const merged = new Map<string, RawPolicyRecord>();
  for (const policy of base.items) {
    merged.set(policy.policy_id, policy);
  }
  for (const policy of custom.policies) {
    merged.set(policy.policy_id, policy);
  }

  return {
    defaultPolicyId: base.defaultPolicyId,
    sourcePath: custom.policies.length > 0 ? `${base.sourcePath} + job_custom` : base.sourcePath,
    items: [...merged.values()],
  };
}

function sourceForPolicy(policy: RawPolicyRecord): JobPolicySource {
  return policy.metadata.source === "job_custom" ? "custom" : "default";
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

  const store = mergePolicies(jobId ?? undefined);
  const match = store.items.find((item) => item.policy_id === normalizedId);
  if (!match) {
    return null;
  }

  return {
    policyId: normalizedId,
    name: match.name,
    source: sourceForPolicy(match),
    conditions: match.conditions,
    actions: match.actions,
    metadata: match.metadata,
    defaultPolicyId: store.defaultPolicyId,
    sourcePath: store.sourcePath,
  };
}

export function listJobPolicies(jobId: string): JobPolicyWorkspace {
  const job = getJobOrThrow(jobId);
  const store = mergePolicies(jobId);
  const usageByPolicy = new Map<
    string,
    {
      processed: number;
      failed: number;
      reviewed: number;
      totalF1: number;
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
        docs: new Set<string>(),
        lastUsedAt: null,
      };
      if (outcome.status === "processed") {
        bucket.processed += 1;
        bucket.docs.add(document.fileId);
      } else if (outcome.status === "failed") {
        bucket.failed += 1;
      }
      if (typeof outcome.exactF1 === "number") {
        bucket.reviewed += 1;
        bucket.totalF1 += outcome.exactF1;
      }
      if (!bucket.lastUsedAt || document.updatedAt > bucket.lastUsedAt) {
        bucket.lastUsedAt = document.updatedAt;
      }
      usageByPolicy.set(policyId, bucket);
    }
  }

  const policies = store.items.map<JobPolicySummary>((policy) => {
    const usage = usageByPolicy.get(policy.policy_id);
    const meanExactF1 = usage && usage.reviewed > 0 ? usage.totalF1 / usage.reviewed : null;
    return {
      policyId: policy.policy_id,
      name: policy.name,
      source: sourceForPolicy(policy),
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
      learningState: learningStateForPolicy(usage?.reviewed ?? 0, meanExactF1, (usage?.processed ?? 0) + (usage?.failed ?? 0)),
      lastUsedAt: usage?.lastUsedAt ?? null,
    };
  });

  const leaderboard = [...policies].sort((left, right) => {
    const leftScore = left.meanExactF1 ?? -1;
    const rightScore = right.meanExactF1 ?? -1;
    if (rightScore !== leftScore) {
      return rightScore - leftScore;
    }
    if (right.documentsProcessed !== left.documentsProcessed) {
      return right.documentsProcessed - left.documentsProcessed;
    }
    return left.name.localeCompare(right.name);
  });

  return {
    sourcePath: store.sourcePath,
    defaultPolicyId: store.defaultPolicyId,
    policies,
    leaderboard,
    customPolicyCount: policies.filter((policy) => policy.source === "custom").length,
    defaultPolicyCount: policies.filter((policy) => policy.source === "default").length,
  };
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

  return usages.sort((left, right) => (left.updatedAt < right.updatedAt ? 1 : -1));
}

export function getJobPolicyDetail(jobId: string, policyId: string): {
  policy: PolicyDetail;
  usages: JobPolicyUsage[];
  summary: JobPolicySummary | null;
} | null {
  const policy = getPolicyDetail(jobId, policyId);
  if (!policy) {
    return null;
  }
  const workspace = listJobPolicies(jobId);
  return {
    policy,
    usages: getJobPolicyUsage(jobId, policyId),
    summary: workspace.policies.find((entry) => entry.policyId === policy.policyId) ?? null,
  };
}
