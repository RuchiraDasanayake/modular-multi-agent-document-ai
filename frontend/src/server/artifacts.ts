import fs from "node:fs";
import path from "node:path";
import type {
  DocumentSummary,
  EscalationEvent,
  FieldExtraction,
  GuardrailFinding,
  ProvenanceEvent,
  RecoveryAttempt,
  RunFileInfo,
  RunOverview,
  RunSummary,
  ShadowComparison,
  ValidationError,
} from "@/types/idpo";
import { listRunDirectories, resolvePathForDisplay, resolvePrimaryRunPath, resolveRunFilePath, resolveRunRoot } from "@/server/paths";
import { asNumber, average, percentile, readJsonFile, readJsonLines, readTextFile, toIsoString } from "@/server/utils";

interface RunContext {
  runId: string;
  source: "runs" | "sample";
  rootPath: string;
  primaryPath: string;
}

interface ResultEnvelope {
  results?: unknown[];
}

interface ResultDocRecord {
  doc_id?: string;
  path?: string;
  filename?: string;
  doc_type?: string;
  vendor_cluster?: string;
  layout_cluster_id?: string;
  content_profile?: string;
  complexity_bin?: string;
  route_bin?: string;
  route_specialization?: string;
  latency_ms?: number;
  policy_id?: string;
  policy_name?: string;
  static_policy_id?: string;
  static_policy_name?: string;
  static_policy_reason?: string;
  advice_source?: string;
  advice_status?: string | null;
  advice_id?: string;
  advice_confidence?: number;
  retrieval_source?: string;
  rabi_used?: boolean;
  n_neighbors?: number | null;
  fallback_reason?: string | null;
  advice_accepted?: boolean;
  policy_changed?: boolean;
  advisor_recommendation?: Record<string, unknown> | null;
  fallback_candidates?: unknown[];
  blocked_policy?: boolean;
  rollback_reason?: string | null;
  feedback_logged?: boolean;
  feedback_error?: string | null;
  escalated?: boolean;
  validation_issues?: unknown[];
  extracted_fields?: unknown[];
  field_details?: Record<string, unknown>;
  shadow_comparisons?: unknown[];
  escalation_info?: Record<string, unknown>;
  rollback_triggered?: boolean;
  retries_count?: number;
  recovered_fields?: Record<string, unknown>;
  model_used?: string;
  model_mode?: string;
  model_reason?: string;
  ocr_engine_used?: string;
  ocr_avg_confidence?: number;
  ocr_rerun_attempted_pages?: number;
  ocr_rerun_used_pages?: number;
  fallback_path?: string;
  unresolved_field_count?: number;
  defer_status?: string | null;
  defer_reason?: string | null;
  schema_coverage?: number;
  schema_grounding_coverage?: number;
  schema_valid?: boolean;
  schema_missing_required_count?: number;
  schema_hallucinated_field_count?: number;
  transparency_path?: string;
  transparency?: Record<string, unknown>;
  llm_diagnostics?: Record<string, unknown>;
  reward?: number;
  reward_type?: string;
  reward_details?: Record<string, unknown>;
}

interface ProvenanceRaw {
  event_id?: string;
  event_type?: string;
  agent?: string;
  timestamp?: number;
  latency_ms?: number;
  cost_units?: number;
  inputs?: Record<string, unknown>;
  outputs?: Record<string, unknown>;
  parameters?: Record<string, unknown>;
}

interface ShadowSummary {
  policyId: string;
  docsCompared: number;
  avgLatencyDeltaMs: number | null;
  avgQualityDelta: number | null;
  avgRetrievalDelta: number | null;
}

function buildRunContext(runId: string): RunContext {
  const resolved = resolveRunRoot(runId);
  const primaryPath = resolvePrimaryRunPath(resolved.rootPath);
  return {
    runId,
    source: resolved.source,
    rootPath: resolved.rootPath,
    primaryPath,
  };
}

function getResults(context: RunContext): ResultDocRecord[] {
  const envelope = readJsonFile<ResultEnvelope>(path.join(context.primaryPath, "results.json"));
  const records = Array.isArray(envelope?.results) ? envelope?.results : [];
  return records.filter((entry) => typeof entry === "object" && entry !== null) as ResultDocRecord[];
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function relativeToPrimary(primaryPath: string, filePath: string): string {
  return path.relative(primaryPath, filePath).replace(/\\/g, "/");
}

function listDocsLayoutIds(primaryPath: string): string[] {
  const docsDir = path.join(primaryPath, "docs");
  if (!fs.existsSync(docsDir)) {
    return [];
  }
  return fs
    .readdirSync(docsDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort((a, b) => (a > b ? 1 : -1));
}

function readLooseJson(filePath: string): unknown {
  const asJson = readJsonFile<unknown>(filePath);
  if (asJson !== null) {
    return asJson;
  }
  const asJsonLines = readJsonLines<unknown>(filePath);
  if (asJsonLines.length === 0) {
    return null;
  }
  if (asJsonLines.length === 1) {
    return asJsonLines[0];
  }
  return asJsonLines;
}

function getDocCount(context: RunContext): number {
  const results = getResults(context);
  if (results.length > 0) {
    return results.length;
  }

  const docsLayoutCount = listDocsLayoutIds(context.primaryPath).length;
  if (docsLayoutCount > 0) {
    return docsLayoutCount;
  }

  const extractDir = path.join(context.primaryPath, "extract");
  if (!fs.existsSync(extractDir)) {
    return 0;
  }
  return fs.readdirSync(extractDir).filter((name) => name.endsWith(".json")).length;
}

function getRunStatDates(runRoot: string): { createdAt: string; updatedAt: string } {
  const stat = fs.statSync(runRoot);
  return {
    createdAt: toIsoString(stat.birthtimeMs || stat.ctimeMs),
    updatedAt: toIsoString(stat.mtimeMs),
  };
}

function computeStatus(primaryPath: string): "ready" | "running" | "failed" | "unknown" {
  if (fs.existsSync(path.join(primaryPath, "results.json"))) {
    return "ready";
  }
  if (fs.existsSync(path.join(primaryPath, "metrics.json"))) {
    return "ready";
  }
  const docsLayoutIds = listDocsLayoutIds(primaryPath);
  if (docsLayoutIds.length > 0) {
    return "ready";
  }
  if (fs.existsSync(path.join(primaryPath, "run.log"))) {
    return "running";
  }
  if (fs.existsSync(path.join(primaryPath, "run.json"))) {
    return "running";
  }
  return "unknown";
}

function mapResultToDocumentSummary(entry: ResultDocRecord): DocumentSummary {
  const docId = String(entry.doc_id ?? "unknown_doc");
  const validationIssueCount = Array.isArray(entry.validation_issues) ? entry.validation_issues.length : 0;
  const rewardDetails = asRecord(entry.reward_details) ?? {};
  return {
    docId,
    filename: String(entry.filename ?? entry.path ?? docId),
    docType: typeof entry.doc_type === "string" ? entry.doc_type : null,
    vendorCluster: typeof entry.vendor_cluster === "string" ? entry.vendor_cluster : null,
    layoutClusterId: typeof entry.layout_cluster_id === "string" ? entry.layout_cluster_id : null,
    complexityBin: typeof entry.complexity_bin === "string" ? entry.complexity_bin : null,
    routeBin: typeof entry.route_bin === "string" ? entry.route_bin : null,
    routeSpecialization: typeof (entry as Record<string, unknown>).route_specialization === "string" ? String((entry as Record<string, unknown>).route_specialization) : null,
    status: "processed",
    latencyMs: asNumber(entry.latency_ms),
    policyId: typeof entry.policy_id === "string" ? entry.policy_id : null,
    staticPolicyId: typeof (entry as Record<string, unknown>).static_policy_id === "string" ? String((entry as Record<string, unknown>).static_policy_id) : null,
    staticPolicyName: typeof (entry as Record<string, unknown>).static_policy_name === "string" ? String((entry as Record<string, unknown>).static_policy_name) : null,
    staticPolicyReason: typeof (entry as Record<string, unknown>).static_policy_reason === "string" ? String((entry as Record<string, unknown>).static_policy_reason) : null,
    advisorRecommendationPolicyId:
      typeof asRecord((entry as Record<string, unknown>).advisor_recommendation)?.policy_id === "string"
        ? String(asRecord((entry as Record<string, unknown>).advisor_recommendation)?.policy_id)
        : null,
    adviceSource: typeof entry.advice_source === "string" ? entry.advice_source : null,
    adviceStatus: typeof (entry as Record<string, unknown>).advice_status === "string" ? String((entry as Record<string, unknown>).advice_status) : null,
    adviceConfidence: asNumber(entry.advice_confidence),
    retrievalSource: typeof entry.retrieval_source === "string" ? entry.retrieval_source : null,
    fallbackReason: typeof entry.fallback_reason === "string" ? entry.fallback_reason : null,
    adviceAccepted: typeof (entry as Record<string, unknown>).advice_accepted === "boolean" ? Boolean((entry as Record<string, unknown>).advice_accepted) : null,
    policyChanged: typeof (entry as Record<string, unknown>).policy_changed === "boolean" ? Boolean((entry as Record<string, unknown>).policy_changed) : null,
    feedbackLogged: typeof entry.feedback_logged === "boolean" ? entry.feedback_logged : null,
    rollbackTriggered: typeof entry.rollback_triggered === "boolean" ? entry.rollback_triggered : null,
    rollbackReason: typeof entry.rollback_reason === "string" ? entry.rollback_reason : null,
    blockedPolicy: typeof entry.blocked_policy === "boolean" ? entry.blocked_policy : null,
    validationIssueCount,
    escalated: Boolean(entry.escalated),
    retriesCount: asNumber(entry.retries_count) ?? 0,
    modelUsed: typeof entry.model_used === "string" ? entry.model_used : null,
    modelMode: typeof entry.model_mode === "string" ? entry.model_mode : null,
    modelReason: typeof entry.model_reason === "string" ? entry.model_reason : null,
    ocrEngineUsed: typeof entry.ocr_engine_used === "string" ? entry.ocr_engine_used : null,
    ocrAvgConfidence: asNumber(entry.ocr_avg_confidence),
    ocrRerunAttemptedPages: asNumber(entry.ocr_rerun_attempted_pages),
    ocrRerunUsedPages: asNumber(entry.ocr_rerun_used_pages),
    fallbackPath: typeof entry.fallback_path === "string" ? entry.fallback_path : null,
    unresolvedFieldCount: asNumber(entry.unresolved_field_count),
    deferStatus: typeof (entry as Record<string, unknown>).defer_status === "string" ? String((entry as Record<string, unknown>).defer_status) : null,
    deferReason: typeof (entry as Record<string, unknown>).defer_reason === "string" ? String((entry as Record<string, unknown>).defer_reason) : null,
    schemaCoverage: asNumber((entry as Record<string, unknown>).schema_coverage),
    schemaGroundingCoverage: asNumber((entry as Record<string, unknown>).schema_grounding_coverage),
    schemaValid: typeof (entry as Record<string, unknown>).schema_valid === "boolean" ? Boolean((entry as Record<string, unknown>).schema_valid) : null,
    missingRequiredCount: asNumber((entry as Record<string, unknown>).schema_missing_required_count),
    hallucinatedFieldCount: asNumber((entry as Record<string, unknown>).schema_hallucinated_field_count),
    transparencyPath: typeof entry.transparency_path === "string" ? entry.transparency_path : null,
    reward: asNumber(entry.reward),
    rewardType: typeof entry.reward_type === "string" ? entry.reward_type : null,
    exactPrecision: asNumber(rewardDetails.precision),
    exactRecall: asNumber(rewardDetails.recall),
    exactF1: asNumber(rewardDetails.f1),
  };
}

function mapDocsLayoutToDocumentSummary(primaryPath: string, docId: string): DocumentSummary {
  const docDir = path.join(primaryPath, "docs", docId);
  const manifest = readJsonFile<Record<string, unknown>>(path.join(docDir, "input", "manifest.json")) ?? {};
  const dae = readJsonFile<Record<string, unknown>>(path.join(docDir, "dae", "output.json")) ?? {};
  const plan = readJsonFile<Record<string, unknown>>(path.join(docDir, "plan", "primary.json")) ?? {};
  const decisionChain = readJsonFile<Record<string, unknown>>(path.join(docDir, "decision_chain.json")) ?? {};
  const validate = readJsonFile<Record<string, unknown>>(path.join(docDir, "validation", "results.json")) ?? {};
  const transparency = readJsonFile<Record<string, unknown>>(path.join(docDir, "provenance", "transparency.json")) ?? {};
  const fieldResolution = asRecord(transparency.field_resolution) ?? {};
  const modelRoute = asRecord(transparency.model_route) ?? {};
  const ocrRoute = asRecord(transparency.ocr_route) ?? {};
  const routing = asRecord(transparency.routing) ?? asRecord(decisionChain.policy) ?? {};
  const advisorRecommendation = asRecord(routing.advisor_recommendation) ?? asRecord(plan.advisor_recommendation) ?? {};
  const feedbackStatus = asRecord(transparency.feedback_status) ?? asRecord(decisionChain.feedback_status) ?? {};
  const safetyStatus = asRecord(transparency.safety_status) ?? asRecord(decisionChain.safety_status) ?? {};
  const recoveryAttemptsRaw = readLooseJson(path.join(docDir, "recovery", "attempts.jsonl"));
  const escalationRaw = readLooseJson(path.join(docDir, "recovery", "escalations.jsonl"));
  const reward = readJsonFile<Record<string, unknown>>(path.join(docDir, "reward.json")) ?? {};
  const extractionSource = Array.isArray((readJsonFile<Record<string, unknown>>(path.join(docDir, "structuring", "extracted.json")) ?? {}).entities)
    ? ((readJsonFile<Record<string, unknown>>(path.join(docDir, "structuring", "extracted.json")) ?? {}).entities as unknown[])
    : [];
  const escalation = mapEscalation(escalationRaw);
  const rewardDetails = asRecord(reward.reward_details) ?? {};
  const validationIssues = mapValidationIssues(validate.issues);
  const fields = extractionSource.map(mapField).filter((item): item is FieldExtraction => item !== null);
  const schemaQuality = computeSchemaQuality(getExpectedFieldKeys(primaryPath), fields, validationIssues);

  const manifestPath = typeof manifest.path === "string" ? path.basename(manifest.path) : "";
  const filename = manifestPath || docId;
  const validationIssueCount = validationIssues.length;
  const retriesCount = mapRecovery(recoveryAttemptsRaw).length;
  const transparencyPath = path.join(docDir, "provenance", "transparency.json");

  return {
    docId,
    filename,
    docType: typeof dae.doc_type === "string" ? dae.doc_type : null,
    vendorCluster: typeof dae.vendor_cluster === "string" ? dae.vendor_cluster : null,
    layoutClusterId: typeof dae.layout_cluster_id === "string" ? dae.layout_cluster_id : null,
    complexityBin: typeof dae.complexity_bin === "string" ? dae.complexity_bin : null,
    routeBin: typeof dae.route_bin === "string" ? dae.route_bin : null,
    routeSpecialization: typeof routing.route_specialization === "string" ? routing.route_specialization : null,
    status: "processed",
    latencyMs: asNumber(transparency.latency_ms),
    policyId: typeof plan.policy_id === "string" ? plan.policy_id : null,
    staticPolicyId: typeof routing.static_policy_id === "string" ? routing.static_policy_id : null,
    staticPolicyName: typeof routing.static_policy_name === "string" ? routing.static_policy_name : null,
    staticPolicyReason: typeof routing.static_policy_reason === "string" ? routing.static_policy_reason : null,
    advisorRecommendationPolicyId: typeof advisorRecommendation.policy_id === "string" ? advisorRecommendation.policy_id : null,
    adviceSource: typeof routing.advice_source === "string" ? routing.advice_source : null,
    adviceStatus: typeof routing.advice_status === "string" ? routing.advice_status : null,
    adviceConfidence: asNumber(routing.advice_confidence),
    retrievalSource: typeof routing.retrieval_source === "string" ? routing.retrieval_source : null,
    fallbackReason: typeof routing.fallback_reason === "string" ? routing.fallback_reason : null,
    adviceAccepted: typeof routing.advice_accepted === "boolean" ? routing.advice_accepted : null,
    policyChanged: typeof routing.policy_changed === "boolean" ? routing.policy_changed : null,
    feedbackLogged: typeof feedbackStatus.logged === "boolean" ? feedbackStatus.logged : null,
    rollbackTriggered: typeof safetyStatus.rollback_triggered === "boolean" ? safetyStatus.rollback_triggered : null,
    rollbackReason: typeof safetyStatus.rollback_reason === "string" ? safetyStatus.rollback_reason : null,
    blockedPolicy: typeof safetyStatus.blocked_policy === "boolean" ? safetyStatus.blocked_policy : null,
    validationIssueCount,
    escalated: escalation?.escalated ?? false,
    retriesCount,
    modelUsed: typeof modelRoute.model_used === "string" ? modelRoute.model_used : null,
    modelMode: typeof modelRoute.model_mode === "string" ? modelRoute.model_mode : null,
    modelReason: typeof modelRoute.model_reason === "string" ? modelRoute.model_reason : null,
    ocrEngineUsed: typeof ocrRoute.engine === "string" ? ocrRoute.engine : null,
    ocrAvgConfidence: asNumber(ocrRoute.avg_confidence),
    ocrRerunAttemptedPages: asNumber(ocrRoute.rerun_attempted_pages),
    ocrRerunUsedPages: asNumber(ocrRoute.rerun_used_pages),
    fallbackPath: typeof modelRoute.fallback_path === "string" ? modelRoute.fallback_path : null,
    unresolvedFieldCount: asNumber(fieldResolution.unresolved_count),
    deferStatus: typeof routing.defer_status === "string" ? routing.defer_status : typeof safetyStatus.defer_status === "string" ? safetyStatus.defer_status : null,
    deferReason: typeof routing.defer_reason === "string" ? routing.defer_reason : typeof safetyStatus.defer_reason === "string" ? safetyStatus.defer_reason : null,
    schemaCoverage: schemaQuality.coverage,
    schemaGroundingCoverage: schemaQuality.groundingCoverage,
    schemaValid: schemaQuality.valid,
    missingRequiredCount: schemaQuality.missingRequiredCount,
    hallucinatedFieldCount: schemaQuality.hallucinatedFieldCount,
    transparencyPath: fs.existsSync(transparencyPath) ? relativeToPrimary(primaryPath, transparencyPath) : null,
    reward: asNumber(reward.reward),
    rewardType: typeof reward.reward_type === "string" ? reward.reward_type : null,
    exactPrecision: asNumber(rewardDetails.precision),
    exactRecall: asNumber(rewardDetails.recall),
    exactF1: asNumber(rewardDetails.f1),
  };
}

function readJsonDocFile<T>(primaryPath: string, folder: string, docId: string): T | null {
  return readJsonFile<T>(path.join(primaryPath, folder, `${docId}.json`));
}

function normalizeConfidenceType(value: unknown): "calibrated" | "heuristic" | "unknown" {
  if (value === "calibrated" || value === "heuristic") {
    return value;
  }
  return "unknown";
}

function normalizeExtractionMethod(value: unknown): "local_model" | "llm_tool" | "rule_based" | "unknown" {
  if (value === "local_model" || value === "llm_tool" || value === "rule_based") {
    return value;
  }
  return "unknown";
}

function getExpectedFieldKeys(primaryPath: string): string[] {
  const schema = readJsonFile<Record<string, unknown>>(path.join(primaryPath, "fields.json")) ?? {};
  const fields = Array.isArray(schema.fields) ? schema.fields : [];
  return fields
    .map((entry) => (entry && typeof entry === "object" ? String((entry as Record<string, unknown>).key ?? "").trim() : ""))
    .filter((value) => value.length > 0);
}

function computeSchemaQuality(
  expectedKeys: string[],
  fields: FieldExtraction[],
  validationIssues: ValidationError[],
): {
  coverage: number | null;
  groundingCoverage: number | null;
  valid: boolean | null;
  missingRequiredCount: number | null;
  hallucinatedFieldCount: number | null;
} {
  if (expectedKeys.length === 0) {
    return {
      coverage: null,
      groundingCoverage: null,
      valid: null,
      missingRequiredCount: null,
      hallucinatedFieldCount: null,
    };
  }

  const expected = new Set(expectedKeys);
  const extracted = new Set<string>();
  let groundedRequiredCount = 0;
  for (const field of fields) {
    if (field.value === null || field.value === "") {
      continue;
    }
    extracted.add(field.key);
    const grounded = field.evidence.page !== null || field.evidence.span !== null || field.evidence.bbox !== null;
    if (grounded && expected.has(field.key)) {
      groundedRequiredCount += 1;
    }
  }

  const extractedRequiredCount = expectedKeys.filter((key) => extracted.has(key)).length;
  const missingRequiredCount = Math.max(expectedKeys.length - extractedRequiredCount, 0);
  const hallucinatedFieldCount = Array.from(extracted).filter((key) => !expected.has(key)).length;

  return {
    coverage: expectedKeys.length > 0 ? extractedRequiredCount / expectedKeys.length : null,
    groundingCoverage: extractedRequiredCount > 0 ? groundedRequiredCount / extractedRequiredCount : null,
    valid: missingRequiredCount === 0 && hallucinatedFieldCount === 0 && validationIssues.length === 0,
    missingRequiredCount,
    hallucinatedFieldCount,
  };
}

function mapField(entry: unknown): FieldExtraction | null {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  const value = entry as Record<string, unknown>;
  const keyRaw = value.key ?? value.name;
  if (typeof keyRaw !== "string" || keyRaw.length === 0) {
    return null;
  }

  const spanRaw = Array.isArray(value.evidence_span)
    ? value.evidence_span
    : Array.isArray(value.span)
      ? value.span
      : null;

  const span =
    spanRaw && spanRaw.length >= 2 && typeof spanRaw[0] === "number" && typeof spanRaw[1] === "number"
      ? ([spanRaw[0], spanRaw[1]] as [number, number])
      : null;

  return {
    key: keyRaw,
    value: (value.value ?? null) as string | number | boolean | null,
    confidence: asNumber(value.confidence_score ?? value.confidence),
    confidence_type: normalizeConfidenceType(value.confidence_type),
    extraction_method: normalizeExtractionMethod(value.extraction_method),
    evidence: {
      span,
      bbox: Array.isArray(value.evidence_bbox)
        ? (value.evidence_bbox as number[])
        : Array.isArray(value.bbox)
          ? (value.bbox as number[])
          : Array.isArray((value.metadata as Record<string, unknown> | undefined)?.bbox)
            ? (((value.metadata as Record<string, unknown>).bbox as unknown[]) as number[])
            : null,
      page: asNumber(value.page),
    },
    discovered: Boolean(value.discovered),
    metadata: typeof value.metadata === "object" && value.metadata !== null ? (value.metadata as Record<string, unknown>) : {},
  };
}

function mapValidationIssues(raw: unknown): ValidationError[] {
  if (!Array.isArray(raw)) {
    return [];
  }

  const mapped: ValidationError[] = [];
  for (const issue of raw) {
    if (!issue || typeof issue !== "object") {
      continue;
    }
    const value = issue as Record<string, unknown>;
    mapped.push({
      field: typeof value.field === "string" ? value.field : "unknown",
      issue: typeof value.issue === "string" ? value.issue : "unknown",
      severity: typeof value.severity === "string" ? value.severity : "unknown",
      details: typeof value.details === "object" && value.details !== null ? (value.details as Record<string, unknown>) : {},
    });
  }
  return mapped;
}

function mapRecovery(raw: unknown): RecoveryAttempt[] {
  const list: unknown[] = [];
  if (Array.isArray(raw)) {
    list.push(...raw);
  } else if (raw && typeof raw === "object") {
    const root = raw as Record<string, unknown>;
    if (Array.isArray(root.retry_log)) {
      list.push(...root.retry_log);
    } else if (Array.isArray(root.attempts)) {
      list.push(...root.attempts);
    } else if ("field" in root || "strategy" in root || "success" in root) {
      list.push(root);
    }
  }
  if (list.length === 0) {
    return [];
  }

  const mapped: RecoveryAttempt[] = [];
  for (const attempt of list) {
    if (!attempt || typeof attempt !== "object") {
      continue;
    }
    const value = attempt as Record<string, unknown>;
    mapped.push({
      field: typeof value.field === "string" ? value.field : "unknown",
      attempt: Math.max(1, Math.trunc(asNumber(value.attempt) ?? 1)),
      strategy: typeof value.strategy === "string" ? value.strategy : "unknown",
      pattern: typeof value.pattern === "string" ? value.pattern : undefined,
      success: Boolean(value.success),
      reason: typeof value.reason === "string" ? value.reason : null,
    });
  }
  return mapped;
}

function mapEscalation(raw: unknown): EscalationEvent | null {
  const rootCandidate =
    Array.isArray(raw) && raw.length > 0 ? raw.find((item) => item && typeof item === "object") : raw;
  if (!rootCandidate || typeof rootCandidate !== "object") {
    return null;
  }

  const root = rootCandidate as Record<string, unknown>;
  const details = (root.details as Record<string, unknown> | undefined) ?? root;
  const fields = Array.isArray(details.fields)
    ? details.fields.filter((value): value is string => typeof value === "string")
    : [];
  const reason =
    typeof details.reason === "string"
      ? details.reason
      : typeof root.reason === "string"
        ? root.reason
        : "unknown";
  const targetModel =
    typeof details.target_model === "string"
      ? details.target_model
      : typeof details.targetModel === "string"
        ? details.targetModel
        : null;
  const costEstimate = asNumber(details.cost_estimate ?? details.costEstimate);
  const latencyEstimateMs = asNumber(details.latency_estimate_ms ?? details.latencyEstimateMs);

  return {
    escalated: Boolean(root.escalated ?? details.escalated),
    fields,
    reason,
    targetModel,
    costEstimate,
    latencyEstimateMs,
    escalationUnavailable: reason === "escalation_unavailable",
  };
}

function mapProvenanceEvents(rawEvents: ProvenanceRaw[]): ProvenanceEvent[] {
  return rawEvents.map((event) => {
    const payload = {
      inputs: event.inputs ?? {},
      outputs: event.outputs ?? {},
      parameters: event.parameters ?? {},
    };
    return {
      eventId: event.event_id ?? "unknown",
      eventType: event.event_type ?? "Unknown",
      agent: event.agent ?? "unknown",
      timestamp: asNumber(event.timestamp) ?? 0,
      docId: extractDocId(event),
      latencyMs: asNumber(event.latency_ms),
      costUnits: asNumber(event.cost_units),
      stage: classifyStage(event),
      payload,
    } satisfies ProvenanceEvent;
  });
}

function mapGuardrails(raw: unknown): GuardrailFinding[] {
  if (!raw || typeof raw !== "object") {
    return [];
  }

  const list = (raw as Record<string, unknown>).findings;
  if (!Array.isArray(list)) {
    return [];
  }

  const mapped: GuardrailFinding[] = [];
  for (const finding of list) {
    if (!finding || typeof finding !== "object") {
      continue;
    }
    const value = finding as Record<string, unknown>;
    mapped.push({
      rule: typeof value.rule === "string" ? value.rule : "unknown",
      result: value.result === "pass" || value.result === "warn" ? value.result : "fail",
      message: typeof value.message === "string" ? value.message : "",
      field: typeof value.field === "string" ? value.field : null,
      metadata: typeof value.metadata === "object" && value.metadata !== null ? (value.metadata as Record<string, unknown>) : {},
    });
  }
  return mapped;
}

function classifyStage(event: ProvenanceRaw): string {
  const eventType = (event.event_type ?? "").toLowerCase();
  const agent = (event.agent ?? "").toLowerCase();

  if (eventType.includes("dae") || agent.includes("document_analysis")) {
    return "dae";
  }
  if (eventType.includes("policy") || eventType.includes("route") || agent.includes("router") || agent.includes("policy")) {
    return "route";
  }
  if (eventType.includes("validation") || agent.includes("validation") || agent.includes("guardrail")) {
    return "validate";
  }
  if (eventType.includes("recovery") || agent.includes("recovery")) {
    return "recover";
  }
  if (eventType.includes("escalation") || agent.includes("escalation")) {
    return "escalate";
  }
  if (eventType.includes("rollback") || agent.includes("safety") || agent.includes("rollback")) {
    return "rollback";
  }
  if (agent.includes("retrieve") || agent.includes("index")) {
    return "retrieve";
  }
  if (agent.includes("answer")) {
    return "answer";
  }
  if (agent.includes("shadow")) {
    return "shadow";
  }
  if (agent.includes("preprocess") || agent.includes("intake") || agent.includes("table_form")) {
    return "preprocess";
  }
  if (agent.includes("extract") || agent.includes("section") || agent.includes("summary")) {
    return "extract";
  }

  return "other";
}

function extractDocId(event: ProvenanceRaw): string | null {
  const candidate = event.inputs?.doc_id;
  return typeof candidate === "string" ? candidate : null;
}

export function listRuns(): RunSummary[] {
  const dirs = listRunDirectories();

  const runs: RunSummary[] = dirs
    .map(({ runId, rootPath, source }) => {
      const primaryPath = resolvePrimaryRunPath(rootPath);
      const stats = getRunStatDates(rootPath);
      const results = getResults({ runId, source, rootPath, primaryPath });
      return {
        runId,
        displayName: runId,
        createdAt: stats.createdAt,
        updatedAt: stats.updatedAt,
        status: computeStatus(primaryPath),
        docCount: results.length > 0 ? results.length : getDocCount({ runId, source, rootPath, primaryPath }),
        source,
        rootPath: resolvePathForDisplay(rootPath),
        primaryPath: resolvePathForDisplay(primaryPath),
        hasShadow: fs.existsSync(path.join(primaryPath, "shadow")),
      } satisfies RunSummary;
    })
    .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));

  return runs;
}

export function getRunSummary(runId: string): RunSummary {
  const context = buildRunContext(runId);
  const stats = getRunStatDates(context.rootPath);
  const docCount = getDocCount(context);

  return {
    runId: context.runId,
    displayName: context.runId,
    createdAt: stats.createdAt,
    updatedAt: stats.updatedAt,
    status: computeStatus(context.primaryPath),
    docCount,
    source: context.source,
    rootPath: resolvePathForDisplay(context.rootPath),
    primaryPath: resolvePathForDisplay(context.primaryPath),
    hasShadow: fs.existsSync(path.join(context.primaryPath, "shadow")),
  };
}

export function getRunFiles(runId: string): RunFileInfo[] {
  const context = buildRunContext(runId);
  const files: RunFileInfo[] = [];
  const maxFiles = 4000;

  const walk = (dir: string) => {
    if (files.length >= maxFiles) {
      return;
    }

    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (files.length >= maxFiles) {
        break;
      }
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(fullPath);
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }

      const relative = path.relative(context.primaryPath, fullPath).replace(/\\/g, "/");
      const extension = path.extname(entry.name).toLowerCase();
      const stat = fs.statSync(fullPath);
      const mappedType: RunFileInfo["type"] =
        extension === ".json"
          ? "json"
          : extension === ".jsonl"
            ? "jsonl"
            : extension === ".md"
              ? "md"
              : extension === ".txt"
                ? "txt"
                : extension === ".csv"
                  ? "csv"
                  : "other";

      files.push({
        path: relative,
        size: stat.size,
        modifiedAt: toIsoString(stat.mtimeMs),
        type: mappedType,
      });
    }
  };

  walk(context.primaryPath);
  return files.sort((a, b) => (a.path > b.path ? 1 : -1));
}

export function readRunFile(runId: string, relativePath: string): { type: "json" | "text"; content: unknown } {
  const context = buildRunContext(runId);
  const safePath = resolveRunFilePath(context.primaryPath, relativePath);
  const ext = path.extname(safePath).toLowerCase();

  if (ext === ".json") {
    return { type: "json", content: readJsonFile<unknown>(safePath) ?? {} };
  }

  if (ext === ".jsonl") {
    return { type: "json", content: readJsonLines<unknown>(safePath) };
  }

  return { type: "text", content: readTextFile(safePath) ?? "" };
}

export function getRunDocuments(runId: string): DocumentSummary[] {
  const context = buildRunContext(runId);
  const results = getResults(context);
  if (results.length > 0) {
    return results.map(mapResultToDocumentSummary);
  }

  const docsLayoutIds = listDocsLayoutIds(context.primaryPath);
  if (docsLayoutIds.length > 0) {
    return docsLayoutIds.map((docId) => mapDocsLayoutToDocumentSummary(context.primaryPath, docId));
  }

  const extractDir = path.join(context.primaryPath, "extract");
  if (!fs.existsSync(extractDir)) {
    return [];
  }

  return fs
    .readdirSync(extractDir)
    .filter((name) => name.endsWith(".json"))
    .map((name) => {
      const docId = name.replace(/\.json$/i, "");
      return {
        docId,
        filename: docId,
        docType: null,
        vendorCluster: null,
        complexityBin: null,
        routeBin: null,
        status: "processed",
        latencyMs: null,
        policyId: null,
        validationIssueCount: 0,
        escalated: false,
      } satisfies DocumentSummary;
    });
}

export function getRunDocument(runId: string, docId: string): Record<string, unknown> {
  const context = buildRunContext(runId);
  const docsLayoutDir = path.join(context.primaryPath, "docs", docId);
  if (fs.existsSync(docsLayoutDir) && fs.statSync(docsLayoutDir).isDirectory()) {
    const dae = readJsonFile<Record<string, unknown>>(path.join(docsLayoutDir, "dae", "output.json")) ?? {};
    const extract = readJsonFile<Record<string, unknown>>(path.join(docsLayoutDir, "structuring", "extracted.json")) ?? {};
    const validate = readJsonFile<Record<string, unknown>>(path.join(docsLayoutDir, "validation", "results.json")) ?? {};
    const recover = readLooseJson(path.join(docsLayoutDir, "recovery", "attempts.jsonl")) ?? {};
    const escalate = readLooseJson(path.join(docsLayoutDir, "recovery", "escalations.jsonl")) ?? {};
    const route = readJsonFile<Record<string, unknown>>(path.join(docsLayoutDir, "plan", "primary.json")) ?? {};
    const decisionChain = readJsonFile<Record<string, unknown>>(path.join(docsLayoutDir, "decision_chain.json")) ?? {};
    const guardrails = readJsonFile<Record<string, unknown>>(path.join(docsLayoutDir, "guardrails", "results.json")) ?? {};
    const transparency = readJsonFile<Record<string, unknown>>(path.join(docsLayoutDir, "provenance", "transparency.json")) ?? {};
    const reward = readJsonFile<Record<string, unknown>>(path.join(docsLayoutDir, "reward.json")) ?? {};
    const llmDiagnostics = asRecord(extract.llm_diagnostics) ?? {};
    const modelRoute = asRecord(transparency.model_route) ?? {};
    const ocrRoute = asRecord(transparency.ocr_route) ?? {};
    const fieldResolution = asRecord(transparency.field_resolution) ?? {};
    const routing = asRecord(transparency.routing) ?? asRecord(decisionChain.policy) ?? {};
    const feedbackStatus = asRecord(transparency.feedback_status) ?? asRecord(decisionChain.feedback_status) ?? {};
    const safetyStatus = asRecord(transparency.safety_status) ?? asRecord(decisionChain.safety_status) ?? {};
    const advisorRecommendation = asRecord(routing.advisor_recommendation) ?? asRecord(route.advisor_recommendation);
    const fallbackCandidates = Array.isArray(routing.fallback_candidates)
      ? routing.fallback_candidates
      : Array.isArray(route.fallback_candidates)
        ? route.fallback_candidates
        : [];

    const extractionSource = Array.isArray(extract.entities)
      ? extract.entities
      : Array.isArray(extract.fields)
        ? extract.fields
        : [];
    const fields = extractionSource.map(mapField).filter((item): item is FieldExtraction => item !== null);
    const validationIssues = mapValidationIssues(validate.issues);
    const schemaQuality = computeSchemaQuality(getExpectedFieldKeys(context.primaryPath), fields, validationIssues);
    const recoveryAttempts = mapRecovery(recover);
    const escalation = mapEscalation(escalate);
    const guardrailFindings = mapGuardrails(guardrails);

    const docProvenancePath = path.join(docsLayoutDir, "provenance", "events.jsonl");
    const provenanceEvents = fs.existsSync(docProvenancePath)
      ? mapProvenanceEvents(readJsonLines<ProvenanceRaw>(docProvenancePath))
      : getRunProvenance(runId).events.filter((event) => event.docId === docId);

    return {
      docId,
      metadata: {
        docType: (dae.doc_type as string | undefined) ?? null,
        vendorCluster: (dae.vendor_cluster as string | undefined) ?? null,
        layoutClusterId: (dae.layout_cluster_id as string | undefined) ?? null,
        complexityBin: (dae.complexity_bin as string | undefined) ?? null,
        routeBin: (dae.route_bin as string | undefined) ?? null,
        routeSpecialization: typeof routing.route_specialization === "string" ? routing.route_specialization : null,
        profile: (dae.content_profile as string | undefined) ?? null,
        policyId: (route.policy_id as string | undefined) ?? null,
        policyName: (route.policy_name as string | undefined) ?? null,
        staticPolicyId: typeof routing.static_policy_id === "string" ? routing.static_policy_id : null,
        staticPolicyName: typeof routing.static_policy_name === "string" ? routing.static_policy_name : null,
        staticPolicyReason: typeof routing.static_policy_reason === "string" ? routing.static_policy_reason : null,
        adviceSource: typeof routing.advice_source === "string" ? routing.advice_source : null,
        adviceStatus: typeof routing.advice_status === "string" ? routing.advice_status : null,
        adviceId: typeof routing.advice_id === "string" ? routing.advice_id : null,
        adviceConfidence: asNumber(routing.advice_confidence),
        retrievalSource: typeof routing.retrieval_source === "string" ? routing.retrieval_source : null,
        rabiUsed: typeof routing.rabi_used === "boolean" ? routing.rabi_used : false,
        nNeighbors: asNumber(routing.n_neighbors),
        adviceAccepted: typeof routing.advice_accepted === "boolean" ? routing.advice_accepted : null,
        policyChanged: typeof routing.policy_changed === "boolean" ? routing.policy_changed : null,
        fallbackReason: typeof routing.fallback_reason === "string" ? routing.fallback_reason : null,
        latencyMs: asNumber(transparency.latency_ms),
        modelUsed: typeof modelRoute.model_used === "string" ? modelRoute.model_used : null,
        modelMode: typeof modelRoute.model_mode === "string" ? modelRoute.model_mode : null,
        modelReason: typeof modelRoute.model_reason === "string" ? modelRoute.model_reason : null,
        fallbackPath: typeof modelRoute.fallback_path === "string" ? modelRoute.fallback_path : null,
        unresolvedFieldCount:
          asNumber(fieldResolution.unresolved_count) ??
          asNumber(llmDiagnostics.unresolved_count) ??
          (Array.isArray(extract.unresolved_fields) ? extract.unresolved_fields.length : null),
        deferStatus: typeof routing.defer_status === "string" ? routing.defer_status : typeof safetyStatus.defer_status === "string" ? safetyStatus.defer_status : null,
        deferReason: typeof routing.defer_reason === "string" ? routing.defer_reason : typeof safetyStatus.defer_reason === "string" ? safetyStatus.defer_reason : null,
        schemaCoverage: schemaQuality.coverage,
        schemaGroundingCoverage: schemaQuality.groundingCoverage,
        schemaValid: schemaQuality.valid,
        missingRequiredCount: schemaQuality.missingRequiredCount,
        hallucinatedFieldCount: schemaQuality.hallucinatedFieldCount,
        ocrEngineUsed: typeof ocrRoute.engine === "string" ? ocrRoute.engine : null,
        ocrAvgConfidence: asNumber(ocrRoute.avg_confidence),
        ocrRerunAttemptedPages: asNumber(ocrRoute.rerun_attempted_pages),
        ocrRerunUsedPages: asNumber(ocrRoute.rerun_used_pages),
        transparencyPath: fs.existsSync(path.join(docsLayoutDir, "provenance", "transparency.json"))
          ? relativeToPrimary(context.primaryPath, path.join(docsLayoutDir, "provenance", "transparency.json"))
          : null,
      },
      advisorRecommendation,
      fallbackCandidates,
      feedbackStatus,
      safetyStatus,
      fields,
      validationIssues,
      guardrailFindings,
      recoveryAttempts,
      escalation,
      provenanceEvents,
      transparency,
      schemaQuality,
      reward: {
        reward: asNumber(reward.reward),
        rewardType: typeof reward.reward_type === "string" ? reward.reward_type : null,
        details: asRecord(reward.reward_details) ?? {},
      },
      llmDiagnostics,
      raw: {
        dae,
        extract,
        validate,
        recover,
        escalate,
        route,
        guardrails,
        transparency,
        decisionChain,
      },
    };
  }

  const results = getResults(context);
  const result = results.find((entry) => entry.doc_id === docId) ?? null;

  const dae = readJsonDocFile<Record<string, unknown>>(context.primaryPath, "dae", docId) ?? {};
  const extract = readJsonDocFile<Record<string, unknown>>(context.primaryPath, "extract", docId) ?? {};
  const validate = readJsonDocFile<Record<string, unknown>>(context.primaryPath, "validate", docId) ?? {};
  const recover = readJsonDocFile<Record<string, unknown>>(context.primaryPath, "recover", docId) ?? {};
  const escalate = readJsonDocFile<Record<string, unknown>>(context.primaryPath, "escalate", docId) ?? {};
  const route = readJsonDocFile<Record<string, unknown>>(context.primaryPath, "route", docId) ?? {};
  const guardrails = readJsonDocFile<Record<string, unknown>>(context.primaryPath, "guardrails", docId) ?? {};
  const transparency = asRecord(result?.transparency) ?? {};
  const llmDiagnostics = asRecord(result?.llm_diagnostics) ?? {};
  const feedbackStatus = asRecord((result as Record<string, unknown> | null)?.feedback_status) ?? {};
  const safetyStatus = asRecord((result as Record<string, unknown> | null)?.safety_status) ?? {};
  const advisorRecommendation = asRecord((result as Record<string, unknown> | null)?.advisor_recommendation) ?? {};
  const fallbackCandidates = Array.isArray((result as Record<string, unknown> | null)?.fallback_candidates)
    ? (((result as Record<string, unknown>).fallback_candidates as unknown[]) ?? [])
    : [];
  const reward = {
    reward: asNumber(result?.reward),
    rewardType: typeof result?.reward_type === "string" ? result.reward_type : null,
    details: asRecord(result?.reward_details) ?? {},
  };

  const extractionSource = Array.isArray(extract.fields)
    ? extract.fields
    : Array.isArray(result?.extracted_fields)
      ? result?.extracted_fields
      : [];

  const fields = extractionSource.map(mapField).filter((item): item is FieldExtraction => item !== null);

  const validationIssues = mapValidationIssues(validate.issues ?? result?.validation_issues);
  const schemaQuality = computeSchemaQuality(getExpectedFieldKeys(context.primaryPath), fields, validationIssues);
  const recoveryAttempts = mapRecovery(recover);
  const escalation = mapEscalation(escalate ?? result?.escalation_info);
  const guardrailFindings = mapGuardrails(guardrails);

  const provenanceEvents = getRunProvenance(runId).events.filter((event) => event.docId === docId);

  return {
    docId,
      metadata: {
        docType: (dae.doc_type as string | undefined) ?? (result?.doc_type ?? null),
        vendorCluster: (dae.vendor_cluster as string | undefined) ?? (result?.vendor_cluster ?? null),
        layoutClusterId: (dae.layout_cluster_id as string | undefined) ?? (result?.layout_cluster_id ?? null),
        complexityBin: (dae.complexity_bin as string | undefined) ?? (result?.complexity_bin ?? null),
        routeBin: (dae.route_bin as string | undefined) ?? (result?.route_bin ?? null),
        routeSpecialization: typeof result?.route_specialization === "string" ? result.route_specialization : null,
        profile: (dae.content_profile as string | undefined) ?? (result?.content_profile ?? null),
        policyId: result?.policy_id ?? (route.policy_id as string | undefined) ?? null,
        policyName: typeof result?.policy_name === "string" ? result.policy_name : null,
        staticPolicyId: typeof result?.static_policy_id === "string" ? result.static_policy_id : null,
        staticPolicyName: typeof result?.static_policy_name === "string" ? result.static_policy_name : null,
        staticPolicyReason: typeof result?.static_policy_reason === "string" ? result.static_policy_reason : null,
        adviceSource: typeof result?.advice_source === "string" ? result.advice_source : null,
        adviceStatus: typeof result?.advice_status === "string" ? result.advice_status : null,
        adviceId: typeof result?.advice_id === "string" ? result.advice_id : null,
        adviceConfidence: asNumber(result?.advice_confidence),
        retrievalSource: typeof result?.retrieval_source === "string" ? result.retrieval_source : null,
        rabiUsed: typeof result?.rabi_used === "boolean" ? result.rabi_used : false,
        nNeighbors: asNumber(result?.n_neighbors),
        adviceAccepted: typeof result?.advice_accepted === "boolean" ? result.advice_accepted : null,
        policyChanged: typeof result?.policy_changed === "boolean" ? result.policy_changed : null,
        fallbackReason: typeof result?.fallback_reason === "string" ? result.fallback_reason : null,
        latencyMs: result?.latency_ms ?? null,
        modelUsed: typeof result?.model_used === "string" ? result.model_used : null,
        modelMode: typeof result?.model_mode === "string" ? result.model_mode : null,
      modelReason: typeof result?.model_reason === "string" ? result.model_reason : null,
      fallbackPath: typeof result?.fallback_path === "string" ? result.fallback_path : null,
      unresolvedFieldCount: asNumber(result?.unresolved_field_count),
      deferStatus: typeof result?.defer_status === "string" ? result.defer_status : null,
      deferReason: typeof result?.defer_reason === "string" ? result.defer_reason : null,
      schemaCoverage: asNumber((result as Record<string, unknown> | null)?.schema_coverage) ?? schemaQuality.coverage,
      schemaGroundingCoverage: asNumber((result as Record<string, unknown> | null)?.schema_grounding_coverage) ?? schemaQuality.groundingCoverage,
      schemaValid: typeof result?.schema_valid === "boolean" ? result.schema_valid : schemaQuality.valid,
      missingRequiredCount: asNumber((result as Record<string, unknown> | null)?.schema_missing_required_count) ?? schemaQuality.missingRequiredCount,
      hallucinatedFieldCount: asNumber((result as Record<string, unknown> | null)?.schema_hallucinated_field_count) ?? schemaQuality.hallucinatedFieldCount,
      ocrEngineUsed: typeof result?.ocr_engine_used === "string" ? result.ocr_engine_used : null,
      ocrAvgConfidence: asNumber(result?.ocr_avg_confidence),
      ocrRerunAttemptedPages: asNumber(result?.ocr_rerun_attempted_pages),
      ocrRerunUsedPages: asNumber(result?.ocr_rerun_used_pages),
        transparencyPath: typeof result?.transparency_path === "string" ? result.transparency_path : null,
      },
    advisorRecommendation,
    fallbackCandidates,
    feedbackStatus,
    safetyStatus,
    fields,
    validationIssues,
    guardrailFindings,
    recoveryAttempts,
    escalation,
    provenanceEvents,
    transparency,
    schemaQuality,
    reward,
    llmDiagnostics,
    raw: {
      dae,
      extract,
      validate,
      recover,
      escalate,
      route,
      guardrails,
      transparency,
      result,
    },
  };
}

export function getRunProvenance(runId: string): {
  events: ProvenanceEvent[];
  stageCounts: Record<string, number>;
  files: { events: string | null; graph: string | null; summary: string | null };
} {
  const context = buildRunContext(runId);
  const provenanceDir = path.join(context.primaryPath, "provenance");
  const eventsCandidates = [path.join(provenanceDir, "events.jsonl"), path.join(context.primaryPath, "events.jsonl")];
  const graphCandidates = [
    path.join(provenanceDir, "graph.json"),
    path.join(provenanceDir, "provenance_graph.json"),
    path.join(context.primaryPath, "provenance_graph.json"),
  ];
  const summaryCandidates = [path.join(provenanceDir, "summary.md"), path.join(context.primaryPath, "summary.md")];

  const eventsFile = eventsCandidates.find((candidate) => fs.existsSync(candidate)) ?? eventsCandidates[0];
  const graphFile = graphCandidates.find((candidate) => fs.existsSync(candidate)) ?? null;
  const summaryFile = summaryCandidates.find((candidate) => fs.existsSync(candidate)) ?? null;

  const rawEvents = readJsonLines<ProvenanceRaw>(eventsFile);
  const events = mapProvenanceEvents(rawEvents);

  const stageCounts = events.reduce<Record<string, number>>((acc, event) => {
    acc[event.stage] = (acc[event.stage] ?? 0) + 1;
    return acc;
  }, {});

  return {
    events,
    stageCounts,
    files: {
      events: fs.existsSync(eventsFile) ? relativeToPrimary(context.primaryPath, eventsFile) : null,
      graph: graphFile ? relativeToPrimary(context.primaryPath, graphFile) : null,
      summary: summaryFile ? relativeToPrimary(context.primaryPath, summaryFile) : null,
    },
  };
}

function normalizeShadowComparison(entry: unknown): ShadowComparison | null {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  const value = entry as Record<string, unknown>;
  if (typeof value.doc_id !== "string" || typeof value.policy_id !== "string") {
    return null;
  }

  return {
    docId: value.doc_id,
    policyId: value.policy_id,
    canonicalLatencyMs: asNumber(value.canonical_latency_ms),
    shadowLatencyMs: asNumber(value.shadow_latency_ms),
    canonicalValidationFailure: asNumber(value.canonical_validation_failure),
    shadowValidationFailure: asNumber(value.shadow_validation_failure),
    canonicalQualityProxy: asNumber(value.canonical_quality_proxy),
    shadowQualityProxy: asNumber(value.shadow_quality_proxy),
    canonicalRetrievalProxy: asNumber(value.canonical_retrieval_proxy),
    shadowRetrievalProxy: asNumber(value.shadow_retrieval_proxy),
  };
}

export function getRunShadow(runId: string): {
  enabled: boolean;
  comparisons: ShadowComparison[];
  policySummaries: ShadowSummary[];
} {
  const context = buildRunContext(runId);
  const comparisonsRaw = readJsonFile<unknown>(path.join(context.primaryPath, "metrics", "comparisons.json"));
  const comparisons = Array.isArray(comparisonsRaw)
    ? comparisonsRaw.map(normalizeShadowComparison).filter((item): item is ShadowComparison => item !== null)
    : [];

  const grouped = new Map<string, ShadowComparison[]>();
  for (const comparison of comparisons) {
    const list = grouped.get(comparison.policyId) ?? [];
    list.push(comparison);
    grouped.set(comparison.policyId, list);
  }

  const policySummaries: ShadowSummary[] = [];
  for (const [policyId, list] of grouped.entries()) {
    const latencyDeltas = list
      .map((item) =>
        item.canonicalLatencyMs !== null && item.shadowLatencyMs !== null
          ? item.shadowLatencyMs - item.canonicalLatencyMs
          : null,
      )
      .filter((value): value is number => value !== null);
    const qualityDeltas = list
      .map((item) =>
        item.canonicalQualityProxy !== null && item.shadowQualityProxy !== null
          ? item.shadowQualityProxy - item.canonicalQualityProxy
          : null,
      )
      .filter((value): value is number => value !== null);
    const retrievalDeltas = list
      .map((item) =>
        item.canonicalRetrievalProxy !== null && item.shadowRetrievalProxy !== null
          ? item.shadowRetrievalProxy - item.canonicalRetrievalProxy
          : null,
      )
      .filter((value): value is number => value !== null);

    policySummaries.push({
      policyId,
      docsCompared: list.length,
      avgLatencyDeltaMs: average(latencyDeltas),
      avgQualityDelta: average(qualityDeltas),
      avgRetrievalDelta: average(retrievalDeltas),
    });
  }

  return {
    enabled: comparisons.length > 0 || fs.existsSync(path.join(context.primaryPath, "shadow")),
    comparisons,
    policySummaries: policySummaries.sort((a, b) => (a.policyId > b.policyId ? 1 : -1)),
  };
}

export function getRunMetrics(runId: string): Record<string, unknown> {
  const context = buildRunContext(runId);
  const metrics =
    readJsonFile<Record<string, unknown>>(path.join(context.primaryPath, "metrics", "metrics.json")) ??
    readJsonFile<Record<string, unknown>>(path.join(context.primaryPath, "metrics.json")) ??
    {};
  const comparisons =
    readJsonFile<unknown>(path.join(context.primaryPath, "metrics", "comparisons.json")) ??
    readJsonFile<unknown>(path.join(context.primaryPath, "comparisons.json")) ??
    [];
  const policySafety =
    readJsonFile<Record<string, unknown>>(path.join(context.primaryPath, "metrics", "policy_safety.json")) ??
    readJsonFile<Record<string, unknown>>(path.join(context.primaryPath, "policy_rollbacks.json")) ??
    {};
  const queueMetrics = readJsonFile<Record<string, unknown>>(path.join(context.primaryPath, "metrics", "queue_metrics.json")) ?? {};
  const runInfo = readJsonFile<Record<string, unknown>>(path.join(context.primaryPath, "run.json")) ?? {};

  return {
    metrics,
    comparisons,
    policySafety,
    queueMetrics,
    runInfo,
  };
}

export function getRunOverview(runId: string): RunOverview {
  const run = getRunSummary(runId);
  const context = buildRunContext(runId);
  const results = getResults(context);
  const docs = getRunDocuments(runId);
  const metrics = getRunMetrics(runId);
  const provenance = getRunProvenance(runId);

  const latencies = docs.map((doc) => doc.latencyMs).filter((value): value is number => value !== null);
  const validationTotals = docs.map((doc) => doc.validationIssueCount);
  const validationPassRate = docs.length === 0 ? null : Math.max(0, 1 - validationTotals.filter((count) => count > 0).length / docs.length);
  const retriesFromResults = results.reduce((sum, item) => {
    const retries = Array.isArray((item as Record<string, unknown>).recovery_log)
      ? ((item as Record<string, unknown>).recovery_log as unknown[]).length
      : 0;
    return sum + retries;
  }, 0);
  const retriesCount =
    retriesFromResults > 0
      ? retriesFromResults
      : docs.reduce((sum, doc) => sum + (asNumber((doc as Record<string, unknown>).retriesCount) ?? 0), 0);

  const rollbackCount = provenance.events.filter((event) => event.eventType.toLowerCase().includes("rollback")).length;
  const escalationsCount = docs.filter((doc) => doc.escalated).length;
  const adviceAcceptedCount = docs.filter((doc) => doc.adviceAccepted).length;
  const policyChangedCount = docs.filter((doc) => doc.policyChanged).length;
  const directScoredDocCount = docs.filter((doc) => typeof doc.exactF1 === "number").length;

  const estimatedCost =
    asNumber((metrics.metrics as Record<string, unknown> | undefined)?.estimated_cost) ??
    asNumber((metrics.metrics as Record<string, unknown> | undefined)?.cost_estimate) ??
    null;

  return {
    run,
    metrics: metrics.metrics as Record<string, number | string | boolean | null>,
    documents: docs,
    retriesCount,
    escalationsCount,
    rollbackCount,
    validationPassRate,
    p95LatencyMs: percentile(latencies, 95),
    estimatedCost,
    adviceAcceptedCount,
    policyChangedCount,
    directScoredDocCount,
  };
}

export function findNewestRunIdAfter(startedAtMs: number): string | null {
  const runs = listRuns();
  const candidate = runs.find((run) => Date.parse(run.createdAt) >= startedAtMs - 5000 || Date.parse(run.updatedAt) >= startedAtMs - 5000);
  return candidate?.runId ?? null;
}
