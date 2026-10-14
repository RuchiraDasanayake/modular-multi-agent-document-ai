import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { POST as uploadRoute } from "@/app/api/jobs/[jobId]/documents/route";
import { loadRunnerConfig, resetConfigCacheForTests } from "./config";
import { addDocumentsToJob, addStagedDocumentsToJob, createWorkspaceJob, getJob } from "./jobs";
import { cleanupStagedUploads, stageFileObject } from "./upload-stream";

const MIB = 1024 * 1024;

async function withStorage(run: () => Promise<void>): Promise<void> {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "idpo-stream-upload-"));
  const oldData = process.env.IDPO_DATA_DIR;
  const oldGateway = process.env.INTERNAL_API_URL;
  const oldFetch = globalThis.fetch;
  process.env.IDPO_DATA_DIR = path.join(root, "data");
  process.env.INTERNAL_API_URL = "http://test-gateway.local";
  resetConfigCacheForTests();
  globalThis.fetch = async (input, init) => {
    if (String(input) === "http://test-gateway.local/api/auth/me") {
      const token = new Headers(init?.headers).get("authorization");
      return token === "Bearer owner" ? Response.json({ id: "owner", role: "viewer" })
        : token === "Bearer other" ? Response.json({ id: "other", role: "viewer" })
          : Response.json({ detail: "Unauthorized" }, { status: 401 });
    }
    return oldFetch(input, init);
  };
  try { await run(); } finally {
    globalThis.fetch = oldFetch;
    if (oldData === undefined) delete process.env.IDPO_DATA_DIR;
    else process.env.IDPO_DATA_DIR = oldData;
    if (oldGateway === undefined) delete process.env.INTERNAL_API_URL;
    else process.env.INTERNAL_API_URL = oldGateway;
    resetConfigCacheForTests();
    fs.rmSync(root, { recursive: true, force: true });
  }
}

function request(jobId: string, token: string, body: BodyInit, headers: Record<string, string>, signal?: AbortSignal): Request {
  return new Request(`http://localhost/api/jobs/${jobId}/documents`, {
    method: "POST", headers: { authorization: `Bearer ${token}`, ...headers }, body, signal, duplex: "half",
  } as RequestInit);
}

function streamedMiB(count: number): ReadableStream<Uint8Array> {
  let sent = 0;
  const chunk = new Uint8Array(MIB).fill(65);
  return new ReadableStream({
    pull(controller) {
      if (sent++ < count) controller.enqueue(chunk);
      else controller.close();
    },
  });
}

async function post(jobId: string, input: Request): Promise<Response> {
  return uploadRoute(input, { params: Promise.resolve({ jobId }) });
}

function assertNoArtifacts(jobId: string, uploadsPath: string): void {
  assert.equal(getJob(jobId)?.documents?.length, 0);
  assert.deepEqual(fs.readdirSync(uploadsPath), []);
}

test("streamed upload rejects oversized body with false Content-Length and leaves no files", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const result = await post(job.jobId, request(job.jobId, "owner", streamedMiB(33) as unknown as BodyInit,
      { "content-type": "application/json", "content-length": "1" }));
    assert.equal(result.status, 413);
    assertNoArtifacts(job.jobId, job.uploadsPath!);
  });
});

test("chunked octet file limit is enforced after bytes arrive", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const result = await post(job.jobId, request(job.jobId, "owner", streamedMiB(21) as unknown as BodyInit,
      { "content-type": "application/octet-stream", "x-file-name": "large.txt" }));
    assert.equal(result.status, 413);
    assertNoArtifacts(job.jobId, job.uploadsPath!);
  });
});

test("multipart file count limit rejects whole request without retained artifacts", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const form = new FormData();
    for (let index = 0; index < 33; index++) form.append("files", new File([`item ${index}`], `${index}.txt`));
    const result = await post(job.jobId, request(job.jobId, "owner", form, {}));
    assert.equal(result.status, 413);
    assertNoArtifacts(job.jobId, job.uploadsPath!);
  });
});

test("multipart file truncation rejects rather than accepting the first 20 MiB", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const form = new FormData();
    form.append("files", new File([new Uint8Array(20 * MIB + 1)], "large.txt"));
    const result = await post(job.jobId, request(job.jobId, "owner", form, {}));
    assert.equal(result.status, 413);
    assertNoArtifacts(job.jobId, job.uploadsPath!);
  });
});

test("multipart total request limit includes framing and rejects two individually valid large files", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const form = new FormData();
    const large = new Uint8Array(17 * MIB);
    form.append("files", new File([large], "first.txt"));
    form.append("files", new File([large], "second.txt"));
    const result = await post(job.jobId, request(job.jobId, "owner", form, {}));
    assert.equal(result.status, 413);
    assertNoArtifacts(job.jobId, job.uploadsPath!);
  });
});

test("aborted multipart request removes an incomplete staged file", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const boundary = "abort-boundary";
    const abort = new AbortController();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="partial.txt"\r\nContent-Type: text/plain\r\n\r\npartial`,
        ));
      },
    });
    const pending = post(job.jobId, request(job.jobId, "owner", body as unknown as BodyInit,
      { "content-type": `multipart/form-data; boundary=${boundary}` }, abort.signal));
    setTimeout(() => abort.abort(), 10);
    const result = await pending;
    assert.equal(result.status, 400);
    assertNoArtifacts(job.jobId, job.uploadsPath!);
  });
});

test("valid multipart commits exactly two files in request order", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const form = new FormData();
    form.append("files", new File(["alpha"], "first.txt"));
    form.append("files", new File(["beta"], "second.txt"));
    const result = await post(job.jobId, request(job.jobId, "owner", form, {}));
    assert.equal(result.status, 201, result.status === 201 ? undefined : await result.text());
    const updated = getJob(job.jobId);
    assert.deepEqual(updated?.documents?.map((item) => item.fileName), ["first.txt", "second.txt"]);
    assert.equal(fs.readdirSync(job.uploadsPath!).length, 2);
    assert.equal(fs.readFileSync(path.join(job.uploadsPath!, updated!.documents[0]!.storedName), "utf8"), "alpha");
    assert.equal(fs.readFileSync(path.join(job.uploadsPath!, updated!.documents[1]!.storedName), "utf8"), "beta");
  });
});

test("lost upload response can be retried with the same key without a second document", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const key = "a".repeat(32);
    const send = () => {
      const form = new FormData();
      form.append("files", new File(["invoice bytes"], "invoice.txt", { type: "text/plain" }));
      return post(job.jobId, request(job.jobId, "owner", form, { "idempotency-key": key }));
    };
    const first = await send();
    assert.equal(first.status, 201);
    const originalId = getJob(job.jobId)?.documents?.[0]?.fileId;
    assert.ok(originalId);
    const retry = await send();
    assert.equal(retry.status, 201);
    assert.deepEqual((await retry.json()).documents.map((item: { fileId: string }) => item.fileId), [originalId]);
    assert.deepEqual(getJob(job.jobId)?.documents?.map((item) => item.fileId), [originalId]);
    assert.equal(fs.readdirSync(job.uploadsPath!).length, 1);
    assert.equal(getJob(job.jobId)?.uploadReceipts?.[key]?.files[0]?.fileId, originalId);
  });
});

test("concurrent retries with one key commit one batch", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const key = "b".repeat(32);
    const send = () => {
      const form = new FormData();
      form.append("files", new File(["same bytes"], "invoice.txt"));
      return post(job.jobId, request(job.jobId, "owner", form, { "idempotency-key": key }));
    };
    const responses = await Promise.all([send(), send()]);
    assert.deepEqual(responses.map((response) => response.status), [201, 201]);
    assert.equal(getJob(job.jobId)?.documents?.length, 1);
    assert.equal(fs.readdirSync(job.uploadsPath!).length, 1);
  });
});

test("upload retry key cannot be reused with different bytes or by another owner", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const key = "c".repeat(32);
    const send = (token: string, content: string) => {
      const form = new FormData();
      form.append("files", new File([content], "invoice.txt"));
      return post(job.jobId, request(job.jobId, token, form, { "idempotency-key": key }));
    };
    assert.equal((await send("owner", "original")).status, 201);
    assert.equal((await send("owner", "different")).status, 409);
    assert.equal((await send("other", "original")).status, 404);
    assert.equal(getJob(job.jobId)?.documents?.length, 1);
    assert.equal(fs.readdirSync(job.uploadsPath!).length, 1);
  });
});

test("upload replay refuses a changed original and invalid keys", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const key = "d".repeat(32);
    const send = (retryKey: string) => {
      const form = new FormData();
      form.append("files", new File(["original"], "invoice.txt"));
      return post(job.jobId, request(job.jobId, "owner", form, { "idempotency-key": retryKey }));
    };
    assert.equal((await send("invalid-key")).status, 400);
    assertNoArtifacts(job.jobId, job.uploadsPath!);
    assert.equal((await send(key)).status, 201);
    const original = getJob(job.jobId)!.documents![0]!;
    fs.writeFileSync(path.join(job.uploadsPath!, original.storedName), "changed!");
    assert.equal((await send(key)).status, 409);
    assert.deepEqual(getJob(job.jobId)?.documents?.map((item) => item.fileId), [original.fileId]);
  });
});

test("malformed multipart removes completed and incomplete request files", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const boundary = "test-boundary";
    const body = `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="one.txt"\r\nContent-Type: text/plain\r\n\r\none\r\n` +
      `--${boundary}\r\nContent-Disposition: form-data; name="files"; filename="two.txt"\r\nContent-Type: text/plain\r\n\r\ntwo`;
    const result = await post(job.jobId, request(job.jobId, "owner", body,
      { "content-type": `multipart/form-data; boundary=${boundary}` }));
    assert.equal(result.status, 400);
    assertNoArtifacts(job.jobId, job.uploadsPath!);
  });
});

test("invalid JSON byte values reject the entire request", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const result = await post(job.jobId, request(job.jobId, "owner",
      JSON.stringify({ files: [{ name: "valid.txt", bytes: [65] }, { name: "invalid.txt", bytes: [66, 999] }] }),
      { "content-type": "application/json" }));
    assert.equal(result.status, 400);
    assertNoArtifacts(job.jobId, job.uploadsPath!);
  });
});

test("nonowner cannot create staging files", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const result = await post(job.jobId, request(job.jobId, "other", "private",
      { "content-type": "application/octet-stream", "x-file-name": "private.txt" }));
    assert.equal(result.status, 404);
    assertNoArtifacts(job.jobId, job.uploadsPath!);
  });
});

test("concurrent uploads append against the latest job document list", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const [first, second] = await Promise.all([
      addDocumentsToJob(job.jobId, [new File(["first"], "first.txt")]),
      addDocumentsToJob(job.jobId, [new File(["second"], "second.txt")]),
    ]);
    assert.equal((first.documents?.length ?? 0) + (second.documents?.length ?? 0), 3);
    const finalJob = getJob(job.jobId);
    assert.deepEqual(finalJob?.documents?.map((item) => item.fileName).sort(), ["first.txt", "second.txt"]);
    assert.equal(fs.readdirSync(job.uploadsPath!).length, 2);
  });
});

test("failed job commit rolls back only the current request's moved file", async () => {
  await withStorage(async () => {
    const job = createWorkspaceJob({ ownerUserId: "owner" });
    const existing = path.join(job.uploadsPath!, "existing.txt");
    fs.writeFileSync(existing, "keep");
    const staged = await stageFileObject(job.jobId, new File(["new"], "new.txt"));
    const jobFile = path.join(loadRunnerConfig().jobsDir, `${job.jobId}.json`);
    const jobBytes = fs.readFileSync(jobFile);
    const originalRename = fs.renameSync;
    let sabotaged = false;
    try {
      fs.renameSync = (oldPath, newPath) => {
        originalRename(oldPath, newPath);
        if (!sabotaged) {
          sabotaged = true;
          fs.writeFileSync(jobFile, "{invalid-json");
        }
      };
      assert.throws(() => addStagedDocumentsToJob(job.jobId, [staged]), /not found/);
    } finally {
      fs.renameSync = originalRename;
      fs.writeFileSync(jobFile, jobBytes);
      cleanupStagedUploads([staged]);
    }
    assert.deepEqual(fs.readdirSync(job.uploadsPath!), ["existing.txt"]);
    assert.equal(fs.readFileSync(existing, "utf8"), "keep");
    assert.equal(getJob(job.jobId)?.documents?.length, 0);
  });
});
