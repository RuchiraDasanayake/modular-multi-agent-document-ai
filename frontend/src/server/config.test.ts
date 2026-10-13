import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { loadRunnerConfig, resetConfigCacheForTests } from "./config";

test("IDPO_DATA_DIR overrides the storage folders in runner.config.json", () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-config-"));
  process.env.IDPO_DATA_DIR = path.join(tmpRoot, "idpo-data");
  resetConfigCacheForTests();
  try {
    const config = loadRunnerConfig();
    assert.equal(config.runsDir, path.join(tmpRoot, "idpo-data", "runs"));
    assert.equal(config.uploadsDir, path.join(tmpRoot, "idpo-data", "frontend", "uploads"));
    assert.equal(config.jobsDir, path.join(tmpRoot, "idpo-data", "frontend", "jobs"));
  } finally {
    resetConfigCacheForTests();
    delete process.env.IDPO_DATA_DIR;
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("runner resolves a relative Python path before the process starts", () => {
  resetConfigCacheForTests();
  try {
    const config = loadRunnerConfig();
    const command = config.commands.find((entry) => entry.id === config.defaultCommandId);
    assert.ok(command);
    assert.equal(path.isAbsolute(command.program), true);
    assert.equal(fs.existsSync(command.program), true);
    const probe = spawnSync(command.program, ["-c", "print('ok')"], { encoding: "utf-8", windowsHide: true });
    assert.equal(probe.status, 0);
    assert.match(probe.stdout, /ok/);
    const cliCheck = config.backendChecks.find((check) => check.id === "idpo-cli");
    assert.ok(cliCheck?.command);
    assert.equal(path.isAbsolute(cliCheck.command), true);
  } finally {
    resetConfigCacheForTests();
  }
});

test("Docker config enables the private product worker and disables unsupported research runs", () => {
  const dockerConfig = JSON.parse(fs.readFileSync(path.join(process.cwd(), "runner.config.docker.json"), "utf8")) as {
    canonicalRunnerAvailable: boolean;
    commands: Array<{ id: string; program: string; args: string[] }>;
  };
  assert.equal(dockerConfig.canonicalRunnerAvailable, false);
  const product = dockerConfig.commands.find((command) => command.id === "idpo_process_auto");
  assert.equal(product?.program, "node");
  assert.deepEqual(product?.args.slice(0, 3), ["/app/scripts/product-worker-client.mjs", "--input", "{input_dir}"]);
  assert.ok(fs.existsSync(path.join(process.cwd(), "scripts", "product-worker-client.mjs")));
});
