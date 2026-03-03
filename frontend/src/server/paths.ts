import fs from "node:fs";
import path from "node:path";
import { loadRunnerConfig } from "@/server/config";

export function sanitizeRunId(runId: string): string {
  const cleaned = runId.trim();
  if (!/^[a-zA-Z0-9_.-]+$/.test(cleaned)) {
    throw new Error("Invalid runId");
  }
  return cleaned;
}

export function ensurePathInside(baseDir: string, target: string): string {
  const base = path.resolve(baseDir);
  const resolved = path.resolve(target);
  if (!resolved.startsWith(base + path.sep) && resolved !== base) {
    throw new Error("Path traversal blocked");
  }
  return resolved;
}

export function resolveRunRoot(runId: string): { rootPath: string; source: "runs" | "sample" } {
  const config = loadRunnerConfig();
  const safeRunId = sanitizeRunId(runId);

  const primary = path.join(config.runsDir, safeRunId);
  if (fs.existsSync(primary) && fs.statSync(primary).isDirectory()) {
    return { rootPath: primary, source: "runs" };
  }

  const sample = path.join(config.demoSampleRunsDir, safeRunId);
  if (fs.existsSync(sample) && fs.statSync(sample).isDirectory()) {
    return { rootPath: sample, source: "sample" };
  }

  throw new Error(`Run '${safeRunId}' not found`);
}

export function resolvePrimaryRunPath(runRoot: string): string {
  const candidate = path.join(runRoot, "primary");
  if (fs.existsSync(candidate) && fs.statSync(candidate).isDirectory()) {
    return candidate;
  }
  return runRoot;
}

export function resolveRunFilePath(runRoot: string, relativePath: string): string {
  const normalized = relativePath.replace(/\\/g, "/").replace(/^\/+/, "");
  if (!normalized) {
    throw new Error("Missing path");
  }

  const target = path.resolve(runRoot, normalized);
  const safe = ensurePathInside(runRoot, target);
  if (!fs.existsSync(safe) || !fs.statSync(safe).isFile()) {
    throw new Error("File not found");
  }
  return safe;
}

export function listRunDirectories(): Array<{ runId: string; rootPath: string; source: "runs" | "sample" }> {
  const config = loadRunnerConfig();

  const readDirs = (baseDir: string, source: "runs" | "sample") => {
    if (!fs.existsSync(baseDir)) {
      return [] as Array<{ runId: string; rootPath: string; source: "runs" | "sample" }>;
    }

    return fs
      .readdirSync(baseDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => ({
        runId: entry.name,
        rootPath: path.join(baseDir, entry.name),
        source,
      }));
  };

  const mainRuns = readDirs(config.runsDir, "runs");
  if (mainRuns.length > 0) {
    return mainRuns;
  }

  return readDirs(config.demoSampleRunsDir, "sample");
}

export function resolvePathForDisplay(value: string): string {
  return value.replace(/\\/g, "/");
}
