import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, symlink, mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { Ajv2020 } from "ajv/dist/2020.js";
import { readFile } from "node:fs/promises";
import {
  cancelQueueJob,
  claimNextChunk,
  completeChunk,
  enqueueRenderJob,
  getQueueStatus,
  pauseQueueJob,
  reconcileExistingFrames,
  resumeQueueJob,
} from "../src/async-render-queue.js";

test("async render queue supports chunking, idempotency, pause/resume, frame-skip reconciliation, and schema check", async () => {
  const queueRoot = await mkdtemp(path.join(os.tmpdir(), "dvc-queue-"));
  try {
    const schema = JSON.parse(
      await readFile(new URL("../schemas/render-optimization.v1.schema.json", import.meta.url), "utf8"),
    );
    const ajv = new Ajv2020({ strict: false });
    const validate = ajv.compile(schema);

    const job = await enqueueRenderJob(queueRoot, {
      job_id: "dragon-v2-preview",
      quality: "preview",
      engine: "eevee",
      encode_profile: "preview_hw",
      frame_start: 1,
      frame_end: 30,
      chunk_size: 16,
    });
    assert.equal(job.chunks.length, 2);
    assert.deepEqual(
      job.chunks.map((c) => [c.frame_start, c.frame_end]),
      [
        [1, 16],
        [17, 30],
      ],
    );
    assert.equal(validate(job), true);

    const same = await enqueueRenderJob(queueRoot, {
      job_id: "dragon-v2-preview",
      quality: "preview",
      engine: "eevee",
      encode_profile: "preview_hw",
      frame_start: 1,
      frame_end: 30,
      chunk_size: 16,
    });
    assert.equal(same.created_at, job.created_at);

    await assert.rejects(
      () =>
        enqueueRenderJob(queueRoot, {
          job_id: "dragon-v2-preview",
          quality: "master",
          engine: "eevee",
          encode_profile: "master_10bit",
          frame_start: 1,
          frame_end: 30,
          chunk_size: 16,
        }),
      /conflicting specification/,
    );

    const claimed = await claimNextChunk(queueRoot, "dragon-v2-preview");
    assert.equal(claimed.chunk?.chunk_index, 0);

    await pauseQueueJob(queueRoot, "dragon-v2-preview");
    const pausedClaim = await claimNextChunk(queueRoot, "dragon-v2-preview");
    assert.equal(pausedClaim.chunk, null);

    await resumeQueueJob(queueRoot, "dragon-v2-preview");
    const afterResume = await getQueueStatus(queueRoot, "dragon-v2-preview");
    assert.equal(afterResume.chunks[0]?.state, "QUEUED");

    // Reconcile frames 1..16 already verified on disk -> chunk 0 skips cleanly
    const reconciled = reconcileExistingFrames(
      afterResume,
      Array.from({ length: 16 }, (_, i) => i + 1),
    );
    assert.equal(reconciled.chunks[0]?.state, "SUCCEEDED");
    assert.equal(reconciled.chunks[1]?.state, "QUEUED");

    await completeChunk(queueRoot, "dragon-v2-preview", 0, {
      output_relative_path: "chunks/chunk_0.mp4",
      output_sha256: "a".repeat(64),
    });
    const nextClaim = await claimNextChunk(queueRoot, "dragon-v2-preview");
    assert.equal(nextClaim.chunk?.chunk_index, 1);

    await completeChunk(queueRoot, "dragon-v2-preview", 1, {
      output_relative_path: "chunks/chunk_1.mp4",
      output_sha256: "b".repeat(64),
    });
    const done = await getQueueStatus(queueRoot, "dragon-v2-preview");
    assert.equal(done.state, "SUCCEEDED");
    assert.equal(validate(done), true);

    await cancelQueueJob(queueRoot, "dragon-v2-preview");
    await assert.rejects(() => resumeQueueJob(queueRoot, "dragon-v2-preview"), /cancelled/i);
  } finally {
    await rm(queueRoot, { recursive: true, force: true });
  }
});

test("async render queue refuses symlink escapes and invalid job IDs", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "dvc-qsec-"));
  try {
    const realDir = path.join(base, "real");
    await mkdir(realDir);
    const linkDir = path.join(base, "linked");
    await symlink(realDir, linkDir);
    await assert.rejects(
      () =>
        enqueueRenderJob(linkDir, {
          job_id: "safe-id",
          quality: "preview",
          engine: "eevee",
          encode_profile: "preview_hw",
          frame_start: 1,
          frame_end: 10,
        }),
      /real directory|symlink/i,
    );
    await assert.rejects(
      () =>
        enqueueRenderJob(realDir, {
          job_id: "../escape",
          quality: "preview",
          engine: "eevee",
          encode_profile: "preview_hw",
          frame_start: 1,
          frame_end: 10,
        }),
      /Invalid queue job_id/,
    );
  } finally {
    await rm(base, { recursive: true, force: true });
  }
});
