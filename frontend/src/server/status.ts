import { spawnSync } from "node:child_process";
import { loadRunnerConfig } from "@/server/config";
import type { SystemStatus } from "@/types/idpo";

async function checkHttp(url: string, timeoutMs: number): Promise<{ ok: boolean; detail: string }> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { method: "GET", signal: controller.signal, cache: "no-store" });
    return {
      ok: response.ok,
      detail: `HTTP ${response.status}`,
    };
  } catch (error) {
    return {
      ok: false,
      detail: error instanceof Error ? error.message : "request failed",
    };
  } finally {
    clearTimeout(timeout);
  }
}

function checkCli(command: string, args: string[] | undefined, cwd: string): { ok: boolean; detail: string } {
  const result = spawnSync(command, args ?? [], {
    cwd,
    timeout: 8000,
    encoding: "utf-8",
    windowsHide: true,
  });

  if (result.error) {
    return { ok: false, detail: result.error.message };
  }

  const ok = result.status === 0;
  const stderr = (result.stderr ?? "").toString().trim();
  const stdout = (result.stdout ?? "").toString().trim();
  const detail = ok ? (stdout.slice(0, 80) || "ok") : stderr.slice(0, 120) || `exit ${result.status}`;
  return { ok, detail };
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const config = loadRunnerConfig();
  const checks = [] as SystemStatus["checks"];

  for (const check of config.backendChecks) {
    if (check.kind === "http") {
      const url = check.url ?? "";
      if (!url) {
        checks.push({ id: check.id, kind: "http", ok: false, detail: "missing url" });
        continue;
      }
      const result = await checkHttp(url, check.timeoutMs ?? 2000);
      checks.push({ id: check.id, kind: "http", ok: result.ok, detail: result.detail });
      continue;
    }

    if (!check.command) {
      checks.push({ id: check.id, kind: "cli", ok: false, detail: "missing command" });
      continue;
    }

    const result = checkCli(check.command, check.args, config.workspaceRoot);
    checks.push({ id: check.id, kind: "cli", ok: result.ok, detail: result.detail });
  }

  return {
    timestamp: new Date().toISOString(),
    checks,
    defaultCommandId: config.defaultCommandId,
  };
}
