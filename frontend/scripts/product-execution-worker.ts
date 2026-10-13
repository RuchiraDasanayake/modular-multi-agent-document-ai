import fs from "node:fs";
import path from "node:path";
import { loadRunnerConfig } from "../src/server/config";
import { productExecutionQueue } from "../src/server/product-execution-queue";
import { executePreparedProductAutoRun, failQueuedProductAutoRun,
  recoverQueuedProductAutoAdmissions } from "../src/server/product-auto";

async function main(): Promise<void> {
  if (process.env.PRODUCT_EXECUTION_MODE !== "postgres") throw new Error("Worker requires PostgreSQL execution mode.");
  const queue = productExecutionQueue();
  const healthFile = path.join(path.dirname(loadRunnerConfig().runsDir), "frontend", "execution-worker.json");
  fs.mkdirSync(path.dirname(healthFile), { recursive: true });
  let stopping = false;
  let reconciling = false;
  const reconcile = async () => {
    if (stopping || reconciling) return;
    reconciling = true;
    try {
      await recoverQueuedProductAutoAdmissions();
      await queue.reconcile(failQueuedProductAutoRun);
      const temporary = `${healthFile}.${process.pid}.tmp`;
      fs.writeFileSync(temporary, JSON.stringify({ pid: process.pid, heartbeatAt: new Date().toISOString() }), "utf8");
      fs.renameSync(temporary, healthFile);
    } finally { reconciling = false; }
  };
  await queue.start();
  await reconcile();
  await queue.work(executePreparedProductAutoRun, failQueuedProductAutoRun);
  const timer = setInterval(() => { void reconcile().catch(() => {
    console.error("Extraction worker reconciliation failed; health heartbeat was not renewed.");
  }); }, 20000);
  const stop = async () => {
    if (stopping) return;
    stopping = true;
    clearInterval(timer);
    await queue.stop();
    process.exit(0);
  };
  process.once("SIGINT", () => { void stop(); });
  process.once("SIGTERM", () => { void stop(); });
  console.log("Extraction worker ready. Failed or interrupted model attempts are not retried automatically.");
}

void main().catch(() => { console.error("Extraction worker startup failed."); process.exitCode = 1; });
