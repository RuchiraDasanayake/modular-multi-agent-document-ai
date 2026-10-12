import http from "node:http";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const socketPath = process.env.PRODUCT_WORKER_SOCKET || "/idpo-data/product-worker.sock";
const args = process.argv.slice(2);

export function parseArguments(values) {
  if (values.length === 1 && values[0] === "--health") return { health: true };
  if (values.length === 1 && values[0] === "--unsupported-research-runner") {
    throw new Error("Research job execution is unavailable in this Docker deployment. Use Automatic extraction or the single-host research runner.");
  }
  const allowed = new Set(["--input", "--run-id", "--model", "--api-base-url",
    "--approved-recipe-file", "--approved-recipe-sha256"]);
  const parsed = {};
  for (let index = 0; index < values.length; index += 2) {
    const flag = values[index];
    const value = values[index + 1];
    if (!allowed.has(flag) || typeof value !== "string" || !value || flag in parsed) {
      throw new Error("Invalid product worker arguments.");
    }
    parsed[flag] = value;
  }
  if (!parsed["--input"] || !parsed["--run-id"] || Boolean(parsed["--model"]) !== Boolean(parsed["--api-base-url"])) {
    throw new Error("Product worker requires an input directory, run id, and complete model settings.");
  }
  if (Boolean(parsed["--approved-recipe-file"]) !== Boolean(parsed["--approved-recipe-sha256"]) ||
    (parsed["--approved-recipe-file"] && !parsed["--model"])) {
    throw new Error("Approved recipe requires a snapshot, digest, and value model.");
  }
  return {
    input_dir: parsed["--input"],
    run_id: parsed["--run-id"],
    model: parsed["--model"] ?? null,
    api_base_url: parsed["--api-base-url"] ?? null,
    approved_recipe_file: parsed["--approved-recipe-file"] ?? null,
    approved_recipe_sha256: parsed["--approved-recipe-sha256"] ?? null,
  };
}

function callWorker(payload) {
  const health = payload.health === true;
  const body = health ? "" : JSON.stringify(payload);
  const request = http.request({
    socketPath,
    path: health ? "/health" : "/process-auto",
    method: health ? "GET" : "POST",
    headers: health ? {} : { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
  }, (response) => {
    let responseBody = "";
    response.setEncoding("utf8");
    response.on("data", (chunk) => {
      responseBody += chunk;
      if (responseBody.length > 4096) request.destroy(new Error("Worker response is too large."));
    });
    response.on("end", () => {
      if (response.statusCode !== 200) {
        let message = "Product extraction worker is unavailable.";
        try { message = JSON.parse(responseBody).error || message; } catch { /* retain generic message */ }
        process.stderr.write(`${message}\n`);
        process.exitCode = 1;
        return;
      }
      if (!health) process.stdout.write(responseBody + "\n");
    });
  });
  request.setTimeout(6 * 60 * 60 * 1000, () => request.destroy(new Error("Product worker timed out.")));
  request.on("error", (error) => {
    process.stderr.write(`Product extraction worker connection failed: ${error.code || error.name}\n`);
    process.exitCode = 1;
  });
  request.end(body);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    callWorker(parseArguments(args));
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}
