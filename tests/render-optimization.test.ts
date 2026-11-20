import test from "node:test";
import assert from "node:assert/strict";
import { Ajv2020 } from "ajv/dist/2020.js";
import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import {
  RENDER_OPTIMIZATION_PROFILES,
  buildFfmpegEncodeArgs,
  validateRenderOptimizationProfile,
} from "../src/render-optimization.js";

test("render-optimization.v1 schema validates all four quality profiles and rejects unknown fields", async () => {
  const schema = JSON.parse(
    await readFile(new URL("../schemas/render-optimization.v1.schema.json", import.meta.url), "utf8"),
  );
  const ajv = new Ajv2020({ strict: false });
  const validate = ajv.compile(schema);

  for (const key of ["interaction", "preview", "master", "hero"] as const) {
    const profile = RENDER_OPTIMIZATION_PROFILES[key];
    validateRenderOptimizationProfile(profile);
    assert.equal(validate(profile), true, `Schema failed for ${key}: ${JSON.stringify(validate.errors)}`);
  }

  assert.equal(validate({ ...RENDER_OPTIMIZATION_PROFILES.preview, unexpected: true }), false);
  assert.throws(() => validateRenderOptimizationProfile({ ...RENDER_OPTIMIZATION_PROFILES.preview, threads: 99 }));
  assert.throws(() => validateRenderOptimizationProfile({ ...RENDER_OPTIMIZATION_PROFILES.preview, parallel_workers: 4 }));
});

test("buildFfmpegEncodeArgs produces hardware preview, 8-bit master, and 10-bit master commands", () => {
  const hw = buildFfmpegEncodeArgs({
    inputPattern: "frames/frame_%04d.png",
    outputPath: "out/preview.mp4",
    startFrame: 1,
    frameCount: 24,
    profile: "preview_hw",
    videoToolboxAvailable: true,
  });
  assert.ok(hw.includes("h264_videotoolbox"));

  const hwFallback = buildFfmpegEncodeArgs({
    inputPattern: "frames/frame_%04d.png",
    outputPath: "out/preview.mp4",
    startFrame: 1,
    frameCount: 24,
    profile: "preview_hw",
    videoToolboxAvailable: false,
  });
  assert.ok(hwFallback.includes("libx264"));

  const m10 = buildFfmpegEncodeArgs({
    inputPattern: "frames/frame_%04d.png",
    outputPath: "out/master10.mp4",
    startFrame: 1,
    frameCount: 48,
    profile: "master_10bit",
  });
  assert.ok(m10.includes("libx265"));
  assert.ok(m10.includes("yuv420p10le"));
  assert.throws(() =>
    buildFfmpegEncodeArgs({
      inputPattern: "frames/frame_%04d.png",
      outputPath: "out/bad.mp4",
      startFrame: 1,
      frameCount: 49,
      profile: "master_h264",
    }),
  );
});

test("director CLI exposes read-only render-profiles JSON", () => {
  const res = spawnSync(process.execPath, ["dist/src/cli.js", "render-profiles", "--json"], {
    encoding: "utf8",
    timeout: 10_000,
  });
  assert.equal(res.status, 0, res.stderr);
  const parsed = JSON.parse(res.stdout) as { schema_version: string; profiles: Record<string, unknown> };
  assert.equal(parsed.schema_version, "render-optimization-profile.v1");
  assert.ok(parsed.profiles.hero);
  assert.ok(parsed.profiles.preview);
});
