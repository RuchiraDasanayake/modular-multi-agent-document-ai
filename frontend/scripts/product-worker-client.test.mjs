import assert from "node:assert/strict";
import test from "node:test";
import { parseArguments } from "./product-worker-client.mjs";

test("Docker bridge forwards a complete approved recipe snapshot reference", () => {
  const parsed = parseArguments([
    "--input", "/idpo-data/frontend/auto_inputs/auto_" + "a".repeat(32),
    "--run-id", "auto_" + "a".repeat(32),
    "--model", "local-model", "--api-base-url", "http://localhost:8000/v1",
    "--approved-recipe-file", "/idpo-data/frontend/auto_inputs/auto_" + "a".repeat(32) + ".recipe.json",
    "--approved-recipe-sha256", "b".repeat(64),
  ]);
  assert.equal(parsed.approved_recipe_sha256, "b".repeat(64));
  assert.match(parsed.approved_recipe_file, /\.recipe\.json$/);
  assert.equal(parsed.model, "local-model");
});

test("Docker bridge rejects a partial recipe or recipe without a value model", () => {
  const base = ["--input", "/stage", "--run-id", "auto_" + "a".repeat(32)];
  assert.throws(() => parseArguments([...base, "--approved-recipe-file", "/stage.recipe.json"]),
    /Approved recipe requires/);
  assert.throws(() => parseArguments([...base, "--approved-recipe-file", "/stage.recipe.json",
    "--approved-recipe-sha256", "b".repeat(64)]), /Approved recipe requires/);
});

test("Docker bridge forwards only a complete bounded model budget", () => {
  const base = ["--input", "/stage", "--run-id", "auto_" + "a".repeat(32),
    "--model", "local-model", "--api-base-url", "http://localhost:8000/v1"];
  const parsed = parseArguments([...base, "--max-tokens", "8192", "--timeout-s", "180"]);
  assert.equal(parsed.max_tokens, 8192);
  assert.equal(parsed.timeout_s, 180);
  assert.equal(parseArguments(base).max_tokens, null, "old dispatches preserve worker defaults");
  for (const extra of [["--max-tokens", "8192"], ["--timeout-s", "180"],
    ["--max-tokens", "16385", "--timeout-s", "180"],
    ["--max-tokens", "8192", "--timeout-s", "601"],
    ["--max-tokens", "1e3", "--timeout-s", "180"]]) {
    assert.throws(() => parseArguments([...base, ...extra]), /model budget/i);
  }
});
