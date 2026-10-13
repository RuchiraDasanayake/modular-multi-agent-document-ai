import assert from "node:assert/strict";
import test from "node:test";
import { CLIENT_BATCH_FILES, CLIENT_BATCH_LIMIT, CLIENT_FILE_LIMIT, planUploadBatches, uploadInBatches, UploadBatchError } from "./upload-batches";

function file(name: string, bytes = 1): File {
  return new File([new Uint8Array(bytes)], name);
}

test("client plans small sequential batches below request and file limits", () => {
  const files = Array.from({ length: 18 }, (_, index) => file(`${index}.txt`));
  assert.deepEqual(planUploadBatches(files).map((batch) => batch.length), [CLIENT_BATCH_FILES, CLIENT_BATCH_FILES, 2]);
  const large = [file("a.txt", 18 * 1024 * 1024), file("b.txt", 18 * 1024 * 1024)];
  assert.deepEqual(planUploadBatches(large).map((batch) => batch.length), [1, 1]);
  assert.ok(large[0]!.size <= CLIENT_FILE_LIMIT);
  assert.ok(large[0]!.size + large[1]!.size > CLIENT_BATCH_LIMIT);
});

test("invalid selected file fails before any batch is submitted", async () => {
  let sent = 0;
  await assert.rejects(uploadInBatches([file("ok.txt"), file("empty.txt", 0)], async () => {
    sent++;
    return 1;
  }), /between 1 byte and 20 MiB/);
  assert.equal(sent, 0);
});

test("failed later batch reports only unconfirmed files without replaying successful batch", async () => {
  const files = Array.from({ length: 10 }, (_, index) => file(`${index}.txt`));
  const calls: string[][] = [];
  const progress: number[] = [];
  await assert.rejects(
    uploadInBatches(files, async (batch) => {
      calls.push(batch.map((item) => item.name));
      if (calls.length === 2) throw new Error("Server refused second batch");
      return { count: batch.length };
    }, (update) => progress.push(update.uploaded)),
    (error: unknown) => {
      assert.ok(error instanceof UploadBatchError);
      assert.equal(error.uploaded, 8);
      assert.equal(error.total, 10);
      assert.deepEqual(error.remaining.map((item) => item.name), ["8.txt", "9.txt"]);
      assert.deepEqual(error.latest, { count: 8 });
      return true;
    },
  );
  assert.deepEqual(calls.map((batch) => batch.length), [8, 2]);
  assert.deepEqual(progress, [8]);
});
