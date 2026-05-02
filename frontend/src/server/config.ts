import fs from "node:fs";
import path from "node:path";

export interface RunnerCommandConfig {
  id: string;
  description: string;
  program: string;
  args: string[];
  cwd: string;
  env?: Record<string, string>;
}

export interface BackendCheckConfig {
  id: string;
  kind: "cli" | "http";
  command?: string;
  args?: string[];
  url?: string;
  timeoutMs?: number;
}

export interface RunnerConfig {
  workspaceRoot: string;
  runsDir: string;
  uploadsDir: string;
  jobsDir: string;
  demoSampleRunsDir: string;
  maxUploadMb: number;
  allowedExtensions: string[];
  defaultCommandId: string;
  commands: RunnerCommandConfig[];
  backendChecks: BackendCheckConfig[];
}

const CONFIG_FILE = "runner.config.json";

let cachedConfig: RunnerConfig | null = null;

function resolvePath(baseDir: string, value: string): string {
  return path.resolve(baseDir, value);
}

function resolveStorageRoot(workspaceRoot: string): string {
  const configured = process.env.IDPO_DATA_DIR?.trim();
  if (!configured) {
    return path.resolve(workspaceRoot, "..", "idpo-data");
  }
  return path.isAbsolute(configured) ? configured : path.resolve(workspaceRoot, configured);
}

function assertConfig(config: Partial<RunnerConfig>): asserts config is RunnerConfig {
  if (!config.commands || config.commands.length === 0) {
    throw new Error("runner.config.json must define at least one command");
  }
  if (!config.defaultCommandId) {
    throw new Error("runner.config.json must set defaultCommandId");
  }
}

export function loadRunnerConfig(): RunnerConfig {
  if (cachedConfig) {
    return cachedConfig;
  }

  const appRoot = process.cwd();
  const configPath = path.join(appRoot, CONFIG_FILE);
  if (!fs.existsSync(configPath)) {
    throw new Error(`Missing ${CONFIG_FILE} at ${configPath}`);
  }

  const raw = JSON.parse(fs.readFileSync(configPath, "utf-8")) as Partial<RunnerConfig>;
  assertConfig(raw);

  const workspaceRoot = resolvePath(appRoot, raw.workspaceRoot ?? "..");
  const storageRoot = resolveStorageRoot(workspaceRoot);
  const config: RunnerConfig = {
    workspaceRoot,
    runsDir: resolvePath(appRoot, raw.runsDir ?? path.relative(appRoot, path.join(storageRoot, "runs"))),
    uploadsDir: resolvePath(appRoot, raw.uploadsDir ?? path.relative(appRoot, path.join(storageRoot, "frontend", "uploads"))),
    jobsDir: resolvePath(appRoot, raw.jobsDir ?? path.relative(appRoot, path.join(storageRoot, "frontend", "jobs"))),
    demoSampleRunsDir: resolvePath(appRoot, raw.demoSampleRunsDir ?? "./demo_sample_runs"),
    maxUploadMb: raw.maxUploadMb ?? 20,
    allowedExtensions: (raw.allowedExtensions ?? [".pdf", ".png", ".jpg", ".jpeg", ".docx", ".txt", ".json"]).map((ext) =>
      ext.toLowerCase(),
    ),
    defaultCommandId: raw.defaultCommandId,
    commands: raw.commands.map((cmd) => ({
      ...cmd,
      cwd: resolvePath(appRoot, cmd.cwd),
      env: cmd.env ?? {},
    })),
    backendChecks:
      raw.backendChecks ?? [
        {
          id: "idpo-cli",
          kind: "cli",
          command: "python",
          args: ["-m", "idpo.cli", "--help"],
        },
      ],
  };

  fs.mkdirSync(config.uploadsDir, { recursive: true });
  fs.mkdirSync(config.jobsDir, { recursive: true });
  fs.mkdirSync(config.demoSampleRunsDir, { recursive: true });

  cachedConfig = config;
  return config;
}

export function getCommandConfig(commandId?: string): RunnerCommandConfig {
  const config = loadRunnerConfig();
  const selected = config.commands.find((cmd) => cmd.id === (commandId ?? config.defaultCommandId));
  if (!selected) {
    throw new Error(`Unknown commandId '${commandId}'`);
  }
  return selected;
}

export function resetConfigCacheForTests(): void {
  cachedConfig = null;
}
