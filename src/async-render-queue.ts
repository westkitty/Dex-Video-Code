import { lstat, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { assertNoSymlinks, ensureDirectoriesNoSymlink } from "./paths.js";
import type { EncodeProfile, RenderEngineMode, RenderQualityPreset } from "./render-optimization.js";

export type QueueJobState = "QUEUED" | "RUNNING" | "PAUSED" | "CANCELLED" | "SUCCEEDED" | "FAILED";
export type QueueChunkState = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";

export interface RenderQueueChunk {
  chunk_index: number;
  frame_start: number;
  frame_end: number;
  state: QueueChunkState;
  completed_frames: number[];
  output_relative_path?: string;
  output_sha256?: string;
  error?: string;
}

export interface AsyncRenderQueueJob {
  schema_version: "async-render-queue-job.v1";
  job_id: string;
  quality: RenderQualityPreset;
  engine: RenderEngineMode;
  encode_profile: EncodeProfile;
  frame_start: number;
  frame_end: number;
  chunk_size: number;
  state: QueueJobState;
  resume_overwrite_protected: true;
  created_at: string;
  updated_at: string;
  chunks: RenderQueueChunk[];
}

export interface EnqueueRenderJobSpec {
  job_id: string;
  quality: RenderQualityPreset;
  engine: RenderEngineMode;
  encode_profile: EncodeProfile;
  frame_start: number;
  frame_end: number;
  chunk_size?: number;
}

function assertValidJobId(jobId: string): void {
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(jobId)) {
    throw new Error(`Invalid queue job_id: ${jobId}`);
  }
}

async function resolveJobFile(queueRoot: string, jobId: string): Promise<string> {
  assertValidJobId(jobId);
  const rootStat = await lstat(queueRoot);
  if (rootStat.isSymbolicLink() || !rootStat.isDirectory()) {
    throw new Error("Queue root must be a real directory, not a symlink.");
  }
  await ensureDirectoriesNoSymlink(queueRoot, "");
  const relative = `${jobId}.queue.json`;
  await assertNoSymlinks(queueRoot, relative);
  const full = path.resolve(queueRoot, relative);
  if (!full.startsWith(path.resolve(queueRoot) + path.sep)) {
    throw new Error("Queue job path escapes queue root.");
  }
  return full;
}

async function saveAtomic(filePath: string, job: AsyncRenderQueueJob): Promise<void> {
  const dir = path.dirname(filePath);
  await mkdir(dir, { recursive: true });
  const tmpPath = path.join(dir, `.${path.basename(filePath)}.tmp-${process.pid}-${Date.now()}`);
  await writeFile(tmpPath, JSON.stringify(job, null, 2) + "\n", { encoding: "utf8", mode: 0o600 });
  await rename(tmpPath, filePath);
}

export function buildChunkPlan(frameStart: number, frameEnd: number, chunkSize: number): RenderQueueChunk[] {
  if (!Number.isInteger(frameStart) || !Number.isInteger(frameEnd) || frameStart < 1 || frameEnd < frameStart || frameEnd > 2400) {
    throw new Error("Invalid frame bounds for render queue.");
  }
  if (!Number.isInteger(chunkSize) || chunkSize < 1 || chunkSize > 48) {
    throw new Error("chunk_size must be bounded between 1 and 48 frames.");
  }
  const chunks: RenderQueueChunk[] = [];
  let cur = frameStart;
  let idx = 0;
  while (cur <= frameEnd) {
    const hi = Math.min(frameEnd, cur + chunkSize - 1);
    chunks.push({
      chunk_index: idx++,
      frame_start: cur,
      frame_end: hi,
      state: "QUEUED",
      completed_frames: [],
    });
    cur = hi + 1;
  }
  return chunks;
}

export function reconcileExistingFrames(
  job: AsyncRenderQueueJob,
  verifiedFrameNumbers: Iterable<number>,
): AsyncRenderQueueJob {
  const verifiedSet = new Set(
    Array.from(verifiedFrameNumbers).filter((n) => Number.isInteger(n) && n >= job.frame_start && n <= job.frame_end),
  );
  const nextChunks = job.chunks.map((chunk) => {
    const completed: number[] = [];
    for (let f = chunk.frame_start; f <= chunk.frame_end; f++) {
      if (verifiedSet.has(f) || chunk.completed_frames.includes(f)) {
        completed.push(f);
      }
    }
    const allDone = completed.length === chunk.frame_end - chunk.frame_start + 1;
    return {
      ...chunk,
      completed_frames: completed,
      state: allDone ? ("SUCCEEDED" as const) : chunk.state === "SUCCEEDED" ? ("QUEUED" as const) : chunk.state,
    };
  });
  const allSucceeded = nextChunks.every((c) => c.state === "SUCCEEDED");
  return {
    ...job,
    state: allSucceeded ? "SUCCEEDED" : job.state,
    updated_at: new Date().toISOString(),
    chunks: nextChunks,
  };
}

export async function enqueueRenderJob(queueRoot: string, spec: EnqueueRenderJobSpec): Promise<AsyncRenderQueueJob> {
  const filePath = await resolveJobFile(queueRoot, spec.job_id);
  const chunkSize = spec.chunk_size ?? 16;
  try {
    const existing = JSON.parse(await readFile(filePath, "utf8")) as AsyncRenderQueueJob;
    if (
      existing.quality !== spec.quality ||
      existing.engine !== spec.engine ||
      existing.encode_profile !== spec.encode_profile ||
      existing.frame_start !== spec.frame_start ||
      existing.frame_end !== spec.frame_end ||
      existing.chunk_size !== chunkSize
    ) {
      throw new Error(`Job ${spec.job_id} already exists with a conflicting specification.`);
    }
    return existing;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
  }

  const now = new Date().toISOString();
  const job: AsyncRenderQueueJob = {
    schema_version: "async-render-queue-job.v1",
    job_id: spec.job_id,
    quality: spec.quality,
    engine: spec.engine,
    encode_profile: spec.encode_profile,
    frame_start: spec.frame_start,
    frame_end: spec.frame_end,
    chunk_size: chunkSize,
    state: "QUEUED",
    resume_overwrite_protected: true,
    created_at: now,
    updated_at: now,
    chunks: buildChunkPlan(spec.frame_start, spec.frame_end, chunkSize),
  };
  await saveAtomic(filePath, job);
  return job;
}

export async function getQueueStatus(queueRoot: string, jobId: string): Promise<AsyncRenderQueueJob> {
  const filePath = await resolveJobFile(queueRoot, jobId);
  return JSON.parse(await readFile(filePath, "utf8")) as AsyncRenderQueueJob;
}

export async function claimNextChunk(
  queueRoot: string,
  jobId: string,
): Promise<{ job: AsyncRenderQueueJob; chunk: RenderQueueChunk | null }> {
  const filePath = await resolveJobFile(queueRoot, jobId);
  const job = JSON.parse(await readFile(filePath, "utf8")) as AsyncRenderQueueJob;
  if (job.state === "PAUSED" || job.state === "CANCELLED" || job.state === "SUCCEEDED") {
    return { job, chunk: null };
  }
  const next = job.chunks.find((c) => c.state === "QUEUED");
  if (!next) {
    return { job, chunk: null };
  }
  next.state = "RUNNING";
  job.state = "RUNNING";
  job.updated_at = new Date().toISOString();
  await saveAtomic(filePath, job);
  return { job, chunk: next };
}

export async function completeChunk(
  queueRoot: string,
  jobId: string,
  chunkIndex: number,
  receipt: { output_relative_path: string; output_sha256: string },
): Promise<AsyncRenderQueueJob> {
  const filePath = await resolveJobFile(queueRoot, jobId);
  const job = JSON.parse(await readFile(filePath, "utf8")) as AsyncRenderQueueJob;
  const chunk = job.chunks.find((c) => c.chunk_index === chunkIndex);
  if (!chunk) {
    throw new Error(`Unknown chunk_index ${chunkIndex} for job ${jobId}`);
  }
  if (!/^[a-fA-F0-9]{64}$/.test(receipt.output_sha256)) {
    throw new Error("Chunk receipt requires a 64-hex SHA-256.");
  }
  if (receipt.output_relative_path.startsWith("/") || receipt.output_relative_path.includes("..")) {
    throw new Error("Chunk output_relative_path must be safe and relative.");
  }
  chunk.state = "SUCCEEDED";
  chunk.completed_frames = Array.from(
    { length: chunk.frame_end - chunk.frame_start + 1 },
    (_, i) => chunk.frame_start + i,
  );
  chunk.output_relative_path = receipt.output_relative_path;
  chunk.output_sha256 = receipt.output_sha256.toLowerCase();

  const allDone = job.chunks.every((c) => c.state === "SUCCEEDED");
  if (allDone) {
    job.state = "SUCCEEDED";
  } else if (job.state !== "PAUSED" && job.state !== "CANCELLED") {
    job.state = "QUEUED";
  }
  job.updated_at = new Date().toISOString();
  await saveAtomic(filePath, job);
  return job;
}

export async function pauseQueueJob(queueRoot: string, jobId: string): Promise<AsyncRenderQueueJob> {
  const filePath = await resolveJobFile(queueRoot, jobId);
  const job = JSON.parse(await readFile(filePath, "utf8")) as AsyncRenderQueueJob;
  if (job.state === "CANCELLED" || job.state === "SUCCEEDED") {
    throw new Error(`Cannot pause job in terminal state ${job.state}`);
  }
  job.state = "PAUSED";
  job.updated_at = new Date().toISOString();
  await saveAtomic(filePath, job);
  return job;
}

export async function resumeQueueJob(queueRoot: string, jobId: string): Promise<AsyncRenderQueueJob> {
  const filePath = await resolveJobFile(queueRoot, jobId);
  const job = JSON.parse(await readFile(filePath, "utf8")) as AsyncRenderQueueJob;
  if (job.state === "CANCELLED") {
    throw new Error("Cannot resume a cancelled queue job.");
  }
  if (job.state !== "SUCCEEDED") {
    for (const chunk of job.chunks) {
      if (chunk.state === "RUNNING") chunk.state = "QUEUED";
    }
    job.state = "QUEUED";
  }
  job.updated_at = new Date().toISOString();
  await saveAtomic(filePath, job);
  return job;
}

export async function cancelQueueJob(queueRoot: string, jobId: string): Promise<AsyncRenderQueueJob> {
  const filePath = await resolveJobFile(queueRoot, jobId);
  const job = JSON.parse(await readFile(filePath, "utf8")) as AsyncRenderQueueJob;
  job.state = "CANCELLED";
  job.updated_at = new Date().toISOString();
  await saveAtomic(filePath, job);
  return job;
}
