import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";
import * as jsxRuntime from "react/jsx-runtime";
import ts from "typescript";
import { ProductAutoRunRefresh } from "./product-auto-run-refresh";
import { productAutoReviewReadiness } from "./product-auto-review-readiness";
import * as runRequests from "../../lib/product-auto-run-request";
import type { ProductAutoRun } from "../../types/product-auto";
import type { ProductAutoBriefDetail, ProductAutoBriefField, ProductAutoBriefRevision } from "../../types/product-auto-brief";

const jobId = "a".repeat(32);
const fileId = "b".repeat(32);
const field: ProductAutoBriefField = {
  field_id: "invoice_id", type: "string", description: "Printed invoice identifier", example_values: ["INV-1"],
};

function brief(fields = [field], state: "draft" | "confirmed" = "draft", revision = 1): ProductAutoBriefRevision {
  return { contract_version: 1, brief_id: `brief_${"c".repeat(32)}`, owner_user_id: "owner", job_id: jobId,
    revision, audit_event_id: "d".repeat(32), previous_event_id: null, actor_user_id: "owner",
    created_at: "2026-10-14T00:00:00Z", state, intent: "Extract the invoice identifier", fields,
    sample_sources: [{ file_id: fileId, source_sha256: "e".repeat(64) }], payload_sha256: "f".repeat(64) };
}

interface Element {
  type: unknown;
  props: Record<string, unknown>;
}

function elements(node: unknown): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!node || typeof node !== "object" || !("props" in node)) return [];
  const element = node as Element;
  return [element, ...elements(element.props.children)];
}

function text(node: unknown): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(text).join("");
  return node && typeof node === "object" && "props" in node ? text((node as Element).props.children) : "";
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => { resolve = accept; });
  return { promise, resolve };
}

// Exercise the real component and callbacks with deterministic hooks and API promises.
// This tests draft/admission state transitions, not browser layout or React scheduling.
function mount(getBrief: () => Promise<ProductAutoBriefDetail>, runs: ProductAutoRun[] = []) {
  const states: unknown[] = [];
  const refs: Array<{ current: unknown }> = [];
  const effects: Array<{ dependencies: unknown[]; cleanup?: () => void }> = [];
  let stateIndex = 0;
  let refIndex = 0;
  let effectIndex = 0;
  let pendingEffects: Array<() => void> = [];
  let tree: unknown;
  const calls: Array<{ method: string; args: unknown[] }> = [];
  const stored = new Map<string, string>();
  const storage = { getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => stored.set(key, value), removeItem: (key: string) => stored.delete(key) };
  const hooks = {
    useState(initial: unknown) {
      const index = stateIndex++;
      if (!(index in states)) states[index] = typeof initial === "function" ? initial() : initial;
      return [states[index], (value: unknown) => {
        states[index] = typeof value === "function" ? value(states[index]) : value;
      }];
    },
    useRef(initial: unknown) { const index = refIndex++; return refs[index] ?? (refs[index] = { current: initial }); },
    useMemo<T>(create: () => T) { return create(); },
    useCallback<T>(callback: T) { return callback; },
    useEffect(create: () => void | (() => void), dependencies: unknown[]) {
      const index = effectIndex++;
      const previous = effects[index];
      if (!previous || dependencies.some((value, position) => value !== previous.dependencies[position])) {
        effects[index] = { dependencies };
        pendingEffects.push(() => { previous?.cleanup?.(); effects[index].cleanup = create() || undefined; });
      }
    },
  };
  const record = (method: string, args: unknown[]) => { calls.push({ method, args }); };
  const idpoApi = {
    listProductAutoRuns: async () => ({ sourceFiles: [{ fileId, fileName: "sample.txt", selected: true }],
      runs, available: true, modelConfigured: true }),
    listProductAutoRecipes: async () => ({ recipes: [] }),
    getProductAutoBrief: getBrief,
    saveProductAutoBrief: async (...args: unknown[]) => {
      record("save", args);
      return { brief: { ...brief(args[3] as ProductAutoBriefField[], "draft", Number(args[1]) + 1), intent: args[2] } };
    },
    confirmProductAutoBrief: async (...args: unknown[]) => { record("confirm", args); return { brief: brief([field], "confirmed", 2) }; },
    suggestProductAutoBrief: async (...args: unknown[]) => { record("suggest", args); return null; },
    startProductAutoRun: async (...args: unknown[]) => {
      record("start", args);
      return { runId: `auto_${"1".repeat(32)}`, status: "queued", selectedCount: 1, documents: [] };
    },
  };
  const modules: Record<string, unknown> = {
    react: hooks, "react/jsx-runtime": jsxRuntime, "next/link": { default: "a" },
    "next/navigation": { useParams: () => ({ jobId }) },
    "@/components/idpo/card": { IdpoCard: "section" },
    "@/components/idpo/product-file-upload": { ProductFileUpload: "upload" },
    "@/components/idpo/product-auto-review-readiness": { productAutoReviewReadiness },
    "@/components/idpo/product-auto-run-refresh": { ProductAutoRunRefresh },
    "@/lib/api": { api: { me: async () => ({ role: "admin" }) } },
    "@/lib/idpo-api": { idpoApi }, "@/lib/product-auto-run-request": runRequests,
  };
  const source = fs.readFileSync(new URL("./product-auto-page.tsx", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  } }).outputText;
  const exports: { ProductAutoPage?: () => unknown } = {};
  vm.runInNewContext(compiled, { exports, Error, require: (name: string) => {
    if (!(name in modules)) throw new Error(`Unexpected component dependency: ${name}`);
    return modules[name];
  }, window: { sessionStorage: storage, addEventListener() {}, removeEventListener() {},
    setInterval() {}, clearInterval() {} },
  document: { visibilityState: "visible", addEventListener() {}, removeEventListener() {} } });

  function render() {
    stateIndex = refIndex = effectIndex = 0;
    tree = exports.ProductAutoPage!();
    const ready = pendingEffects;
    pendingEffects = [];
    ready.forEach((effect) => effect());
  }
  return {
    calls,
    async settle() {
      for (let turn = 0; turn < 6; turn += 1) { render(); await new Promise<void>((resolve) => setImmediate(resolve)); }
    },
    button(label: string) {
      const button = elements(tree).find((element) => element.type === "button" && text(element.props.children) === label);
      assert.ok(button, `Missing button: ${label}`);
      return button;
    },
    find(predicate: (element: Element) => boolean) { return elements(tree).find(predicate); },
    text() { return text(tree); },
    dispose() { effects.forEach((effect) => effect.cleanup?.()); },
  };
}

function change(element: Element, value: string) {
  (element.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } });
}

function click(element: Element) { (element.props.onClick as () => void)(); }

test("failed schema read blocks setup and extraction; explicit retry restores the saved schema", async () => {
  const retry = deferred<ProductAutoBriefDetail>();
  let reads = 0;
  const page = mount(async () => { if (++reads === 1) throw new Error("Temporary schema read failure"); return retry.promise; });
  try {
    await page.settle();
    assert.match(page.text(), /Temporary schema read failure/);
    assert.equal(page.find((element) => element.type === "button" && /^Extract .* selected/.test(text(element.props.children))), undefined);
    for (const label of ["Save draft", "Confirm field meanings", "Suggest fields with AI"]) {
      const button = page.button(label);
      assert.equal(button.props.disabled, true, `${label} must be blocked while the schema is unknown`);
      click(button);
    }
    await page.settle();
    assert.deepEqual(page.calls, []);
    click(page.button("Retry loading extraction setup"));
    await page.settle();
    assert.match(page.text(), /Loading automatic extraction/);
    retry.resolve({ brief: brief([field], "confirmed", 2), staleSampleFileIds: [] });
    await page.settle();
    assert.equal(reads, 2);
    assert.match(page.text(), /Confirmed revision 2/);
    assert.equal(page.button("Preview sample files").props.disabled, false);
    assert.deepEqual(page.calls, [], "Loading and retrying the schema must not incur model calls");
  } finally { page.dispose(); }
});

test("a successful empty schema read retains explicit discovery extraction", async () => {
  const initial = deferred<ProductAutoBriefDetail>();
  const page = mount(() => initial.promise);
  try {
    await page.settle();
    assert.match(page.text(), /Loading automatic extraction/);
    assert.equal(page.find((element) => element.type === "button"), undefined);
    initial.resolve({ brief: null, staleSampleFileIds: [] });
    await page.settle();
    const start = page.button("Extract 1 selected");
    assert.equal(start.props.disabled, false);
    click(start);
    await page.settle();
    const call = page.calls.find((item) => item.method === "start");
    assert.ok(call);
    assert.deepEqual(call.args[1], [fileId]);
    assert.equal(call.args[3], undefined);
    assert.match(String(call.args[4]), /^[a-f0-9]{32}$/);
  } finally { page.dispose(); }
});

test("multiline examples retain typed newlines and normalize only at draft save", async () => {
  const page = mount(async () => ({ brief: brief(), staleSampleFileIds: [] }));
  try {
    await page.settle();
    const exampleInput = () => {
      const input = page.find((element) => element.type === "textarea" && element.props.rows === 2);
      assert.ok(input);
      return input;
    };
    change(exampleInput(), "INV-1\n");
    await page.settle();
    assert.equal(exampleInput().props.value, "INV-1\n");
    change(exampleInput(), " INV-1 \n\nINV-2\n INV-3 \n");
    await page.settle();
    assert.equal(exampleInput().props.value, " INV-1 \n\nINV-2\n INV-3 \n");
    click(page.button("Save draft"));
    await page.settle();
    const saved = page.calls.find((item) => item.method === "save");
    assert.ok(saved);
    assert.deepEqual(Array.from((saved.args[3] as ProductAutoBriefField[])[0].example_values), ["INV-1", "INV-2", "INV-3"]);
    assert.equal(exampleInput().props.value, "INV-1\nINV-2\nINV-3");
  } finally { page.dispose(); }
});

test("too many examples preserves the draft and rejects save without truncating or submitting", async () => {
  const page = mount(async () => ({ brief: brief(), staleSampleFileIds: [] }));
  try {
    await page.settle();
    const raw = "one\ntwo\nthree\nfour";
    const input = page.find((element) => element.type === "textarea" && element.props.rows === 2);
    assert.ok(input);
    change(input, raw);
    await page.settle();
    click(page.button("Save draft"));
    await page.settle();
    assert.match(page.text(), /at most three examples/i);
    assert.equal(page.find((element) => element.type === "textarea" && element.props.rows === 2)?.props.value, raw);
    assert.deepEqual(page.calls, []);
  } finally { page.dispose(); }
});

test("adding a table column defaults its group, then reuses the latest repeated group without saving", async () => {
  const page = mount(async () => ({ brief: brief(), staleSampleFileIds: [] }));
  try {
    await page.settle();
    click(page.button("Add table column"));
    await page.settle();
    assert.equal(page.find((element) => element.type === "select" &&
      element.props.id === `${jobId}-field-1-type`)?.props.value, "array[object]");
    const firstGroup = page.find((element) => element.type === "input" &&
      element.props.id === `${jobId}-field-1-group`);
    assert.equal(firstGroup?.props.value, "line_items");
    assert.equal(page.find((element) => element.type === "input" &&
      element.props.id === `${jobId}-field-1-id`)?.props.value, "");
    assert.equal(page.find((element) => element.type === "input" &&
      element.props.id === `${jobId}-field-1-meaning`)?.props.value, "");
    assert.ok(firstGroup);
    change(firstGroup, "charges");
    await page.settle();
    click(page.button("Add field"));
    await page.settle();
    click(page.button("Add table column"));
    await page.settle();
    assert.equal(page.find((element) => element.type === "input" &&
      element.props.id === `${jobId}-field-3-group`)?.props.value, "charges");
    assert.equal(page.button("Confirm field meanings").props.disabled, true);
    assert.deepEqual(page.calls, [], "Adding editable fields must not save a draft or call a model");
  } finally { page.dispose(); }
});

test("each schema field control has a unique explicit label association", async () => {
  const fields: ProductAutoBriefField[] = [field, { field_id: "line_items", type: "array[object]",
    group: "line_items", description: "Each billed row", example_values: [] }];
  const page = mount(async () => ({ brief: brief(fields), staleSampleFileIds: [] }));
  try {
    await page.settle();
    const controls = [
      { index: 0, suffix: "id", name: "Field ID", tag: "input" },
      { index: 0, suffix: "type", name: "Type", tag: "select" },
      { index: 0, suffix: "meaning", name: "Meaning", tag: "input" },
      { index: 0, suffix: "examples", name: "Example values (one per line, up to three)", tag: "textarea" },
      { index: 1, suffix: "id", name: "Field ID", tag: "input" },
      { index: 1, suffix: "type", name: "Type", tag: "select" },
      { index: 1, suffix: "group", name: "Repeated row group", tag: "input" },
      { index: 1, suffix: "meaning", name: "Meaning", tag: "input" },
      { index: 1, suffix: "examples", name: "Example values (one per line, up to three)", tag: "textarea" },
    ];
    const ids = new Set<string>();
    for (const control of controls) {
      const id = `${jobId}-field-${control.index}-${control.suffix}`;
      assert.equal(ids.has(id), false, `Duplicate control ID: ${id}`);
      ids.add(id);
      assert.ok(page.find((element) => element.type === "label" && element.props.htmlFor === id &&
        text(element.props.children) === control.name), `Missing ${control.name} label for field ${control.index}`);
      assert.ok(page.find((element) => element.type === control.tag && element.props.id === id),
        `Missing control associated with ${control.name}`);
    }
  } finally { page.dispose(); }
});

test("the preview summary shows only the unchanged confirmed field meanings", async () => {
  const page = mount(async () => ({ brief: brief([field], "confirmed", 2), staleSampleFileIds: [] }));
  try {
    await page.settle();
    assert.match(page.text(), /Confirmed schema for preview · revision 2/);
    assert.match(page.text(), /Sample files: sample\.txt/);
    assert.match(page.text(), /Printed invoice identifier/);
    assert.match(page.text(), /Examples: INV-1/);

    const meaning = page.find((element) => element.type === "input" && element.props.value === field.description);
    assert.ok(meaning);
    change(meaning, "A different invoice identifier");
    await page.settle();
    assert.doesNotMatch(page.text(), /Confirmed schema for preview/,
      "Unsaved edits must not appear as a confirmed schema");
    assert.equal(page.button("Preview sample files").props.disabled, true);
  } finally { page.dispose(); }
});

test("a reviewed JSON preview enables batch export and distinguishes results from selected files", async () => {
  const confirmed = brief([field], "confirmed", 2);
  const run: ProductAutoRun = { runId: `auto_${"1".repeat(32)}`, status: "success",
    createdAt: "2026-10-15T00:00:00Z", selectedCount: 1,
    confirmedBrief: { briefId: confirmed.brief_id, revision: confirmed.revision,
      payloadSha256: confirmed.payload_sha256, snapshotSha256: "2".repeat(64), phase: "preview" },
    documents: [0, 1].map((index) => ({ docId: `doc-${index}`, fileId, fileName: "two.json",
      status: "needs_review", fieldCount: 1, acceptedCount: 1, reviewStatus: "completed" })) };
  const page = mount(async () => ({ brief: confirmed, staleSampleFileIds: [] }), [run]);
  try {
    await page.settle();
    assert.equal(page.button("Download reviewed batch").props.disabled, false);
    assert.match(page.text(), /A reviewed sample preview is ready for the batch/);
    assert.match(page.text(), /2 of 2 results reviewed across 1 selected file\./);
    assert.match(page.text(), /Review result 1: two\.jsoncompleted/);
    assert.match(page.text(), /Review result 2: two\.jsoncompleted/);
    for (const index of [0, 1]) {
      const link = page.find((element) => element.type === "a" &&
        text(element.props.children) === `Review result ${index + 1}: two.json`);
      assert.ok(link);
      assert.equal(link.props.href, `/dashboard/idpo/jobs/${jobId}/auto/${run.runId}/docs/doc-${index}`);
    }
  } finally { page.dispose(); }
});
