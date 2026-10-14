import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { AccessError } from "./auth";
import { MAX_PRODUCT_LOGICAL_DOCUMENTS, MAX_PRODUCT_SOURCE_BYTES,
  plannedProductLogicalDocuments } from "./product-auto-budget";

function withSources(run: (write: (name: string, bytes: string | Buffer) => { name: string; path: string }) => void): void {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-logical-budget-"));
  try {
    run((name, bytes) => {
      const file = path.join(root, name);
      fs.writeFileSync(file, bytes);
      return { name, path: file };
    });
  } finally {
    assert.equal(path.dirname(root), os.tmpdir());
    assert.ok(path.basename(root).startsWith("idpo-logical-budget-"));
    fs.rmSync(root, { recursive: true, force: true });
  }
}

const hasStatus = (status: number) => (error: unknown) => error instanceof AccessError && error.statusCode === status;

test("logical budget counts JSON entries conservatively and native sources once", () => withSources((write) => {
  const json = write("five.JSON", JSON.stringify(Array.from({ length: 5 }, () => ({ pages: [] }))));
  const native = write("source.txt", "[]");
  assert.equal(plannedProductLogicalDocuments([json, native]), 6);
  assert.equal(plannedProductLogicalDocuments([write("object.json", '{"pages":[]}')]), 1);
  assert.equal(plannedProductLogicalDocuments([write("empty.json", "[]")]), 1);
  assert.equal(plannedProductLogicalDocuments([write("malformed.json", "[{]")]), 1);
  assert.equal(plannedProductLogicalDocuments([write("empty-file.json", "")]), 1);
  assert.equal(plannedProductLogicalDocuments([write("nonstandard.json", "[NaN,Infinity]")]), 1);
  assert.equal(plannedProductLogicalDocuments([write("invalid-utf8.json", Buffer.from([91, 34, 255, 34, 93]))]), 1);
}));

test("logical budget enforces both one-container and aggregate run limits", () => withSources((write) => {
  const first = write("first.json", JSON.stringify(Array(3000).fill(null)));
  const exact = write("exact.json", JSON.stringify(Array(2000).fill(null)));
  const extra = write("extra.json", JSON.stringify(Array(2001).fill(null)));
  assert.equal(plannedProductLogicalDocuments([first, exact]), MAX_PRODUCT_LOGICAL_DOCUMENTS);
  assert.throws(() => plannedProductLogicalDocuments([first, extra]), hasStatus(413));
  const oversized = write("oversized.json", JSON.stringify(Array(MAX_PRODUCT_LOGICAL_DOCUMENTS + 1).fill(null)));
  assert.throws(() => plannedProductLogicalDocuments([oversized]), hasStatus(413));
  assert.throws(() => plannedProductLogicalDocuments([]), hasStatus(400));
}));

test("logical budget rejects a JSON source above the byte bound before reading its body", () => withSources((write) => {
  const source = write("large.json", "[]");
  fs.truncateSync(source.path, MAX_PRODUCT_SOURCE_BYTES + 1);
  const read = fs.readSync;
  fs.readSync = (() => { throw new Error("Oversized body must not be read."); }) as typeof fs.readSync;
  try { assert.throws(() => plannedProductLogicalDocuments([source]), hasStatus(413)); }
  finally { fs.readSync = read; }
}));

test("an excessive original count fails before reading any JSON sources", () => withSources((write) => {
  const source = write("source.json", "[]");
  const read = fs.readSync;
  fs.readSync = (() => { throw new Error("An impossible run budget must not read source bodies."); }) as typeof fs.readSync;
  try {
    assert.throws(() => plannedProductLogicalDocuments(Array(MAX_PRODUCT_LOGICAL_DOCUMENTS + 1).fill(source)), hasStatus(413));
  } finally { fs.readSync = read; }
}));

test("logical budget rejects a source that changes size while its admitted bytes are counted", () => withSources((write) => {
  const source = write("changed.json", "[{},{}]");
  const read = fs.readSync;
  fs.readSync = ((descriptor: number, buffer: NodeJS.ArrayBufferView, offset: number, length: number, position: number) => {
    const count = read(descriptor, buffer, offset, length, position);
    fs.appendFileSync(source.path, " ");
    return count;
  }) as typeof fs.readSync;
  try { assert.throws(() => plannedProductLogicalDocuments([source]), hasStatus(409)); }
  finally { fs.readSync = read; }
}));
