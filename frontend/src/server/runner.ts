import fs from "node:fs";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { loadRunnerConfig, getCommandConfig } from "@/server/config";
import { createJob, appendJobLog, setJobFailed, setJobRunning, setJobSuccess, updateJob } from "@/server/jobs";
import { ensurePathInside, resolvePathForDisplay, resolvePrimaryRunPath, resolveRunRoot } from "@/server/paths";
import { findNewestRunIdAfter } from "@/server/artifacts";

interface StartRunRequest {
  commandId?: string;
  settings: {
    configPath?: string;
    shadowMode?: boolean;
    shadowSampleRate?: number;
    policyPreference?: string;
    routingMode?: "auto" | "light" | "standard" | "heavy";
    maxCostPerDoc?: number;
    escalationEnabled?: boolean;
    report?: boolean;
    customFields?: Array<{
      key: string;
      description?: string;
      pattern?: string;
    }>;
    llmLocalModel?: string;
    llmCloudModel?: string;
    llmDefaultMode?: "local" | "cloud";
    llmUseExtraction?: boolean;
    llmUseSummarization?: boolean;
    flagshipModel?: string;
    autoInstallLocalModel?: boolean;
    apiKeys?: {
      openai?: string;
    };
  };
  files: File[];
  sourceRunId?: string;
}

interface UploadManifestFile {
  name: string;
  size: number;
  storedAs: string;
}

function validateUpload(file: File, allowedExtensions: string[], maxUploadMb: number): void {
  const ext = path.extname(file.name).toLowerCase();
  if (!allowedExtensions.includes(ext)) {
    throw new Error(`Unsupported file extension: ${ext || "(none)"}`);
  }

  const maxBytes = maxUploadMb * 1024 * 1024;
  if (file.size > maxBytes) {
    throw new Error(`File '${file.name}' exceeds ${maxUploadMb} MB limit`);
  }
}

function sanitizeFilename(name: string): string {
  return name.replace(/[^a-zA-Z0-9._-]/g, "_");
}

async function saveUploads(files: File[]): Promise<{ uploadDir: string; manifestFiles: UploadManifestFile[] }> {
  const config = loadRunnerConfig();
  const now = new Date();
  const folderName = `${now.toISOString().replace(/[:.]/g, "-")}_${Math.random().toString(36).slice(2, 8)}`;
  const uploadDir = path.join(config.uploadsDir, folderName);
  fs.mkdirSync(uploadDir, { recursive: true });

  const manifestFiles: UploadManifestFile[] = [];

  for (const file of files) {
    validateUpload(file, config.allowedExtensions, config.maxUploadMb);
    const safeName = sanitizeFilename(file.name);
    const finalName = `${Math.random().toString(36).slice(2, 8)}_${safeName}`;
    const target = path.join(uploadDir, finalName);

    const arrayBuffer = await file.arrayBuffer();
    fs.writeFileSync(target, Buffer.from(arrayBuffer));

    manifestFiles.push({
      name: file.name,
      size: file.size,
      storedAs: finalName,
    });
  }

  return { uploadDir, manifestFiles };
}

function listInputArtifacts(inputDir: string): string[] {
  if (!fs.existsSync(inputDir) || !fs.statSync(inputDir).isDirectory()) {
    return [];
  }

  const files: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.isFile()) {
        files.push(full);
      }
    }
  };
  walk(inputDir);
  return files;
}

function copySourceRunInputs(sourceRunId: string, uploadDir: string): UploadManifestFile[] {
  const config = loadRunnerConfig();
  const resolved = resolveRunRoot(sourceRunId);
  const primary = resolvePrimaryRunPath(resolved.rootPath);
  const inputDirPrimary = path.join(primary, "input");
  const inputDirRoot = path.join(resolved.rootPath, "input");
  const inputDir = fs.existsSync(inputDirPrimary) ? inputDirPrimary : inputDirRoot;
  const sourceFiles = listInputArtifacts(inputDir);

  const manifestFiles: UploadManifestFile[] = [];
  for (const sourceFile of sourceFiles) {
    const fileName = path.basename(sourceFile);
    const extension = path.extname(fileName).toLowerCase();
    if (!config.allowedExtensions.includes(extension)) {
      continue;
    }
    const finalName = `${Math.random().toString(36).slice(2, 8)}_${sanitizeFilename(fileName)}`;
    const target = path.join(uploadDir, finalName);
    fs.copyFileSync(sourceFile, target);

    const stat = fs.statSync(target);
    manifestFiles.push({
      name: fileName,
      size: stat.size,
      storedAs: finalName,
    });
  }

  return manifestFiles;
}

function resolveConfigPathFromSettings(settings: StartRunRequest["settings"]): string {
  const config = loadRunnerConfig();
  const defaultConfig = path.join(config.workspaceRoot, "configs", "idpo_research_config.json");

  if (!settings.configPath || settings.configPath.trim().length === 0) {
    return defaultConfig;
  }

  const candidate = path.resolve(config.workspaceRoot, settings.configPath);
  return ensurePathInside(config.workspaceRoot, candidate);
}

function patchConfig(baseConfig: Record<string, unknown>, settings: StartRunRequest["settings"]): Record<string, unknown> {
  const updated = structuredClone(baseConfig);

  if (settings.shadowMode !== undefined) {
    const shadow = ((updated.shadow as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    shadow.enabled = settings.shadowMode;
    if (typeof settings.shadowSampleRate === "number" && Number.isFinite(settings.shadowSampleRate)) {
      shadow.sample_rate = Math.max(0, Math.min(1, settings.shadowSampleRate));
    }
    updated.shadow = shadow;
  }

  if (settings.policyPreference && settings.policyPreference !== "auto" && settings.policyPreference !== "baseline") {
    const ahmn = ((updated.ahmn as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    ahmn.policy_override_id = settings.policyPreference;
    updated.ahmn = ahmn;
  }

  if (settings.routingMode && settings.routingMode !== "auto") {
    const routing = ((updated.routing as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    routing.force_route_bin = settings.routingMode;
    updated.routing = routing;
  }

  if (typeof settings.maxCostPerDoc === "number" && Number.isFinite(settings.maxCostPerDoc)) {
    const budget = ((updated.budget as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    budget.max_cost_per_doc = settings.maxCostPerDoc;
    updated.budget = budget;
  }

  if (settings.escalationEnabled !== undefined) {
    const escalation = ((updated.escalation as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    escalation.enabled = settings.escalationEnabled;
    updated.escalation = escalation;
  }

  if (settings.flagshipModel && settings.flagshipModel.trim()) {
    const escalation = ((updated.escalation as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    escalation.flagship_model = settings.flagshipModel.trim();
    updated.escalation = escalation;
  }

  if (
    (settings.llmLocalModel && settings.llmLocalModel.trim()) ||
    (settings.llmCloudModel && settings.llmCloudModel.trim()) ||
    settings.llmDefaultMode ||
    settings.llmUseExtraction !== undefined ||
    settings.llmUseSummarization !== undefined
  ) {
    const llm = ((updated.llm as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    if (settings.llmLocalModel && settings.llmLocalModel.trim()) {
      llm.local_model = settings.llmLocalModel.trim();
    }
    if (settings.llmCloudModel && settings.llmCloudModel.trim()) {
      llm.cloud_model = settings.llmCloudModel.trim();
    }
    if (settings.llmDefaultMode) {
      llm.default_mode = settings.llmDefaultMode;
    }
    if (settings.llmUseExtraction !== undefined) {
      llm.use_extraction = settings.llmUseExtraction;
    }
    if (settings.llmUseSummarization !== undefined) {
      llm.use_summarization = settings.llmUseSummarization;
    }
    updated.llm = llm;
  }

  if (Array.isArray(settings.customFields) && settings.customFields.length > 0) {
    const structuring = ((updated.structuring as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    const currentRules = Array.isArray(structuring.extraction_rules)
      ? [...(structuring.extraction_rules as Array<Record<string, unknown>>)]
      : [];
    const descriptions =
      typeof structuring.field_descriptions === "object" && structuring.field_descriptions !== null
        ? ({ ...(structuring.field_descriptions as Record<string, unknown>) } as Record<string, unknown>)
        : {};

    for (const field of settings.customFields) {
      const key = (field.key || "").trim().toLowerCase().replace(/\s+/g, "_");
      if (!key) {
        continue;
      }
      const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
      const escapedLabel = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const pattern = field.pattern?.trim() || `${escapedLabel}\\s*[:=\\-]\\s*(.+)`;
      currentRules.push({
        key,
        label,
        pattern,
      });
      if (field.description?.trim()) {
        descriptions[key] = field.description.trim();
      }
    }

    structuring.extraction_rules = currentRules;
    structuring.field_descriptions = descriptions;
    updated.structuring = structuring;
  }

  return updated;
}

function prepareRuntimeConfig(baseConfigPath: string, jobId: string, settings: StartRunRequest["settings"]): string {
  let baseConfig: Record<string, unknown> = {};
  if (fs.existsSync(baseConfigPath)) {
    try {
      baseConfig = JSON.parse(fs.readFileSync(baseConfigPath, "utf-8")) as Record<string, unknown>;
    } catch {
      baseConfig = {};
    }
  }

  const finalConfig = patchConfig(baseConfig, settings);
  const runtimeConfigPath = path.join(loadRunnerConfig().jobsDir, `${jobId}_runtime_config.json`);
  fs.writeFileSync(runtimeConfigPath, JSON.stringify(finalConfig, null, 2), "utf-8");
  return runtimeConfigPath;
}

function redactSettings(settings: StartRunRequest["settings"]): Record<string, unknown> {
  const redacted: Record<string, unknown> = { ...settings };
  if (settings.apiKeys?.openai) {
    redacted.apiKeys = { openai: "***" };
  }
  return redacted;
}

function maybeInstallLocalModel(jobId: string, settings: StartRunRequest["settings"]): void {
  if (!settings.autoInstallLocalModel || !settings.llmLocalModel?.trim()) {
    return;
  }
  const model = settings.llmLocalModel.trim();
  appendJobLog(jobId, `[runner] checking local model '${model}'`);

  const listResult = spawnSync("ollama", ["list"], {
    encoding: "utf-8",
    timeout: 15000,
    windowsHide: true,
  });

  if (listResult.error) {
    appendJobLog(jobId, `[runner] ollama not available: ${listResult.error.message}`);
    return;
  }

  const listOutput = `${listResult.stdout ?? ""}\n${listResult.stderr ?? ""}`;
  if (listOutput.toLowerCase().includes(model.toLowerCase())) {
    appendJobLog(jobId, `[runner] local model already present: ${model}`);
    return;
  }

  appendJobLog(jobId, `[runner] pulling local model: ${model}`);
  const pull = spawnSync("ollama", ["pull", model], {
    encoding: "utf-8",
    timeout: 20 * 60 * 1000,
    windowsHide: true,
  });
  const pullOut = `${pull.stdout ?? ""}\n${pull.stderr ?? ""}`.trim();
  if (pull.status === 0) {
    appendJobLog(jobId, `[runner] model pull complete: ${model}`);
  } else {
    appendJobLog(jobId, `[runner] model pull failed (${pull.status ?? "unknown"}): ${pullOut.slice(0, 300)}`);
  }
}

function buildCommandArgs(
  commandArgsTemplate: string[],
  placeholders: Record<string, string>,
): string[] {
  return commandArgsTemplate.map((value) => value.replace(/\{([a-z_]+)\}/g, (_, key) => placeholders[key] ?? ""));
}

function parseRunInfoFromLog(line: string): { runId: string | null; runPath: string | null } {
  const runDirMatch = line.match(/"run_dir"\s*:\s*"([^"]+)"/i);
  if (!runDirMatch) {
    return { runId: null, runPath: null };
  }

  const runPath = runDirMatch[1].replace(/\\\\/g, "\\");
  const runId = path.basename(runPath);
  return { runId, runPath };
}

export async function startRunJob(payload: StartRunRequest) {
  const hasFiles = Array.isArray(payload.files) && payload.files.length > 0;
  if (!hasFiles && !payload.sourceRunId) {
    throw new Error("Upload files or provide sourceRunId");
  }

  const commandConfig = getCommandConfig(payload.commandId);
  const { uploadDir, manifestFiles: uploadedFiles } = hasFiles
    ? await saveUploads(payload.files)
    : await saveUploads([]);
  const replayFiles = payload.sourceRunId ? copySourceRunInputs(payload.sourceRunId, uploadDir) : [];
  const manifestFiles = [...uploadedFiles, ...replayFiles];

  if (manifestFiles.length === 0) {
    throw new Error("No input artifacts found for run start");
  }

  const job = createJob(commandConfig.id, redactSettings(payload.settings), resolvePathForDisplay(uploadDir));
  const startedAtMs = Date.now();

  const baseConfigPath = resolveConfigPathFromSettings(payload.settings);
  const runtimeConfigPath = prepareRuntimeConfig(baseConfigPath, job.jobId, payload.settings);

  updateJob(job.jobId, {
    logs: [
      `Queued ${manifestFiles.length} file(s)`,
      `Input directory: ${resolvePathForDisplay(uploadDir)}`,
      payload.sourceRunId ? `Source run replay: ${payload.sourceRunId}` : "Source run replay: none",
      `Runtime config: ${resolvePathForDisplay(runtimeConfigPath)}`,
    ],
  });

  maybeInstallLocalModel(job.jobId, payload.settings);

  const placeholders = {
    input_dir: uploadDir,
    config_path: runtimeConfigPath,
    workspace_root: loadRunnerConfig().workspaceRoot,
  };

  const args = buildCommandArgs(commandConfig.args, placeholders);

  setJobRunning(job.jobId);

  const child = spawn(commandConfig.program, args, {
    cwd: commandConfig.cwd,
    env: {
      ...process.env,
      ...commandConfig.env,
      ...(payload.settings.apiKeys?.openai?.trim()
        ? {
            OPENAI_API_KEY: payload.settings.apiKeys.openai.trim(),
          }
        : {}),
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  let discoveredRunId: string | null = null;
  let discoveredRunPath: string | null = null;

  const handleChunk = (chunk: Buffer, stream: "stdout" | "stderr") => {
    const text = chunk.toString("utf-8");
    const lines = text.split(/\r?\n/).filter(Boolean);
    for (const line of lines) {
      appendJobLog(job.jobId, `[${stream}] ${line}`);
      const parsed = parseRunInfoFromLog(line);
      if (parsed.runId) {
        discoveredRunId = parsed.runId;
      }
      if (parsed.runPath) {
        discoveredRunPath = parsed.runPath;
      }
    }
  };

  child.stdout.on("data", (chunk) => handleChunk(chunk as Buffer, "stdout"));
  child.stderr.on("data", (chunk) => handleChunk(chunk as Buffer, "stderr"));

  child.on("error", (error) => {
    appendJobLog(job.jobId, `[runner] process error: ${error.message}`);
    setJobFailed(job.jobId, error.message);
  });

  child.on("close", (code) => {
    if (code !== 0) {
      const message = `Command failed with exit code ${code ?? "unknown"}`;
      appendJobLog(job.jobId, `[runner] ${message}`);
      setJobFailed(job.jobId, message);
      return;
    }

    let resolvedRunId = discoveredRunId;
    if (!resolvedRunId) {
      resolvedRunId = findNewestRunIdAfter(startedAtMs);
    }

    const resolvedRunPath = discoveredRunPath ?? (resolvedRunId ? path.join(loadRunnerConfig().runsDir, resolvedRunId) : null);

    appendJobLog(job.jobId, `[runner] completed successfully`);
    if (resolvedRunId) {
      appendJobLog(job.jobId, `[runner] resolved runId=${resolvedRunId}`);
    }
    setJobSuccess(job.jobId, resolvedRunId, resolvedRunPath ? resolvePathForDisplay(resolvedRunPath) : null);
  });

  return updateJob(job.jobId, {
    logs: [`Executing: ${commandConfig.program} ${args.join(" ")}`, ...job.logs],
  });
}
