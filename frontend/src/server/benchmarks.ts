import fs from "node:fs";
import path from "node:path";
import { loadRunnerConfig } from "@/server/config";
import { readJsonFile, toIsoString } from "@/server/utils";
import type { BenchmarkEvidencePayload, BenchmarkRunSummary } from "@/types/idpo";

interface EvidenceExperiment {
  benchmark_run_id?: string;
  generated_at?: number | string;
  doc_count?: number;
  pack_name?: string;
  config_path?: string;
}

function benchmarkRoot(): string {
  const config = loadRunnerConfig();
  return path.join(config.runsDir, "benchmarks");
}

function sanitizeBenchmarkRunId(runId: string): string {
  const cleaned = runId.trim();
  if (!/^[a-zA-Z0-9_.-]+$/.test(cleaned)) {
    throw new Error("Invalid benchmarkRunId");
  }
  return cleaned;
}

function evidencePaths(runDir: string) {
  return {
    reportPath: path.join(runDir, "paper_evidence.json"),
    tablePath: path.join(runDir, "paper_table.md"),
    csvPath: path.join(runDir, "paper_table.csv"),
  };
}

export function listBenchmarkRuns(): BenchmarkRunSummary[] {
  const root = benchmarkRoot();
  if (!fs.existsSync(root)) {
    return [];
  }

  return fs
    .readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => {
      const runDir = path.join(root, entry.name);
      const { reportPath, tablePath, csvPath } = evidencePaths(runDir);
      const payload = readJsonFile<BenchmarkEvidencePayload>(reportPath);
      const experiment = (payload?.experiment ?? {}) as EvidenceExperiment;
      const stat = fs.statSync(runDir);
      return {
        benchmarkRunId: entry.name,
        generatedAt:
          typeof experiment.generated_at === "number"
            ? toIsoString(experiment.generated_at * 1000)
            : typeof experiment.generated_at === "string"
              ? experiment.generated_at
              : toIsoString(stat.mtimeMs),
        docCount: Number(experiment.doc_count ?? 0),
        packName: String(experiment.pack_name ?? "benchmark_pack"),
        configPath: typeof experiment.config_path === "string" ? experiment.config_path : null,
        reportPath,
        tablePath: fs.existsSync(tablePath) ? tablePath : null,
        csvPath: fs.existsSync(csvPath) ? csvPath : null,
      } satisfies BenchmarkRunSummary;
    })
    .filter((item) => fs.existsSync(item.reportPath))
    .sort((a, b) => (a.generatedAt < b.generatedAt ? 1 : -1));
}

export function getLatestBenchmarkRun(): BenchmarkRunSummary | null {
  const runs = listBenchmarkRuns();
  return runs[0] ?? null;
}

export function getBenchmarkEvidence(benchmarkRunId: string): BenchmarkEvidencePayload {
  const safeRunId = sanitizeBenchmarkRunId(benchmarkRunId);
  const runDir = path.join(benchmarkRoot(), safeRunId);
  const payload = readJsonFile<BenchmarkEvidencePayload>(path.join(runDir, "paper_evidence.json"));
  if (!payload) {
    throw new Error(`Benchmark '${safeRunId}' not found`);
  }
  return payload;
}
