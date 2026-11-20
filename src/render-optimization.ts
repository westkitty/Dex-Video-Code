export type RenderQualityPreset = "interaction" | "preview" | "master" | "hero";
export type RenderEngineMode = "eevee" | "cycles_metal";
export type EncodeProfile = "preview_hw" | "master_h264" | "master_10bit";

export interface QAThresholds {
  min_mean_luma: number;
  max_mean_luma: number;
  min_dynamic_range: number;
  min_motion_delta: number;
}

export interface RenderOptimizationProfile {
  schema_version: "render-optimization-profile.v1";
  quality: RenderQualityPreset;
  engine: RenderEngineMode;
  width: 320 | 640 | 1280;
  height: 180 | 360 | 720;
  samples: number;
  color_depth: "8" | "16";
  encode_profile: EncodeProfile;
  threads: number;
  parallel_workers: 1 | 2;
  sliding_window_chunk: number;
  min_free_gib: number;
  compositor_denoise: boolean;
  mist_pass: boolean;
  motion_blur: boolean;
  bloom_glare: boolean;
  volumetric_fire: boolean;
  geonodes_embers: boolean;
  shadow_cull_vfx: boolean;
  viewport_subsurf_levels: number;
  render_subsurf_levels: number;
  qa_thresholds: QAThresholds;
}

const BASE_QA_THRESHOLDS: QAThresholds = {
  min_mean_luma: 8.0,
  max_mean_luma: 235.0,
  min_dynamic_range: 18.0,
  min_motion_delta: 0.5,
};

export const RENDER_OPTIMIZATION_PROFILES: Record<RenderQualityPreset, RenderOptimizationProfile> = {
  interaction: {
    schema_version: "render-optimization-profile.v1",
    quality: "interaction",
    engine: "eevee",
    width: 320,
    height: 180,
    samples: 8,
    color_depth: "8",
    encode_profile: "preview_hw",
    threads: 6,
    parallel_workers: 1,
    sliding_window_chunk: 0,
    min_free_gib: 1.5,
    compositor_denoise: false,
    mist_pass: true,
    motion_blur: false,
    bloom_glare: true,
    volumetric_fire: true,
    geonodes_embers: true,
    shadow_cull_vfx: true,
    viewport_subsurf_levels: 0,
    render_subsurf_levels: 1,
    qa_thresholds: BASE_QA_THRESHOLDS,
  },
  preview: {
    schema_version: "render-optimization-profile.v1",
    quality: "preview",
    engine: "eevee",
    width: 640,
    height: 360,
    samples: 16,
    color_depth: "8",
    encode_profile: "preview_hw",
    threads: 6,
    parallel_workers: 2,
    sliding_window_chunk: 16,
    min_free_gib: 1.5,
    compositor_denoise: true,
    mist_pass: true,
    motion_blur: true,
    bloom_glare: true,
    volumetric_fire: true,
    geonodes_embers: true,
    shadow_cull_vfx: true,
    viewport_subsurf_levels: 1,
    render_subsurf_levels: 2,
    qa_thresholds: BASE_QA_THRESHOLDS,
  },
  master: {
    schema_version: "render-optimization-profile.v1",
    quality: "master",
    engine: "eevee",
    width: 1280,
    height: 720,
    samples: 32,
    color_depth: "16",
    encode_profile: "master_10bit",
    threads: 6,
    parallel_workers: 2,
    sliding_window_chunk: 16,
    min_free_gib: 3.0,
    compositor_denoise: true,
    mist_pass: true,
    motion_blur: true,
    bloom_glare: true,
    volumetric_fire: true,
    geonodes_embers: true,
    shadow_cull_vfx: true,
    viewport_subsurf_levels: 1,
    render_subsurf_levels: 2,
    qa_thresholds: BASE_QA_THRESHOLDS,
  },
  hero: {
    schema_version: "render-optimization-profile.v1",
    quality: "hero",
    engine: "cycles_metal",
    width: 1280,
    height: 720,
    samples: 96,
    color_depth: "16",
    encode_profile: "master_10bit",
    threads: 6,
    parallel_workers: 1,
    sliding_window_chunk: 0,
    min_free_gib: 3.0,
    compositor_denoise: true,
    mist_pass: true,
    motion_blur: true,
    bloom_glare: true,
    volumetric_fire: true,
    geonodes_embers: true,
    shadow_cull_vfx: true,
    viewport_subsurf_levels: 1,
    render_subsurf_levels: 2,
    qa_thresholds: BASE_QA_THRESHOLDS,
  },
};

export interface FfmpegEncodeArgsOptions {
  inputPattern: string;
  outputPath: string;
  startFrame: number;
  frameCount: number;
  fps?: 24;
  profile: EncodeProfile;
  videoToolboxAvailable?: boolean;
}

export function buildFfmpegEncodeArgs(opts: FfmpegEncodeArgsOptions): string[] {
  if (!Number.isInteger(opts.startFrame) || opts.startFrame < 1) {
    throw new Error("startFrame must be a positive integer.");
  }
  if (!Number.isInteger(opts.frameCount) || opts.frameCount < 1 || opts.frameCount > 48) {
    throw new Error("frameCount must be bounded between 1 and 48.");
  }
  const fps = opts.fps ?? 24;
  let codecArgs: string[];
  if (opts.profile === "preview_hw") {
    codecArgs = opts.videoToolboxAvailable
      ? ["-c:v", "h264_videotoolbox", "-b:v", "2800k", "-pix_fmt", "yuv420p"]
      : ["-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p"];
  } else if (opts.profile === "master_h264") {
    codecArgs = ["-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p"];
  } else if (opts.profile === "master_10bit") {
    codecArgs = ["-c:v", "libx265", "-crf", "16", "-pix_fmt", "yuv420p10le", "-tag:v", "hvc1"];
  } else {
    throw new Error(`Unsupported encode profile: ${String(opts.profile)}`);
  }

  return [
    "-nostdin",
    "-hide_banner",
    "-loglevel",
    "error",
    "-xerror",
    "-n",
    "-framerate",
    String(fps),
    "-start_number",
    String(opts.startFrame),
    "-i",
    opts.inputPattern,
    "-frames:v",
    String(opts.frameCount),
    "-threads",
    "4",
    ...codecArgs,
    "-movflags",
    "+faststart",
    opts.outputPath,
  ];
}

const VALID_KEYS = new Set<string>(Object.keys(RENDER_OPTIMIZATION_PROFILES.preview));

export function validateRenderOptimizationProfile(value: unknown): asserts value is RenderOptimizationProfile {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Render optimization profile must be an object.");
  }
  const obj = value as Record<string, unknown>;
  for (const key of VALID_KEYS) {
    if (!Object.hasOwn(obj, key)) throw new Error(`Missing profile property: ${key}`);
  }
  for (const key of Object.keys(obj)) {
    if (!VALID_KEYS.has(key)) throw new Error(`Unexpected profile property: ${key}`);
  }
  if (obj.schema_version !== "render-optimization-profile.v1") {
    throw new Error("Invalid render optimization profile schema_version.");
  }
  if (!["interaction", "preview", "master", "hero"].includes(String(obj.quality))) {
    throw new Error("Unsupported quality tier.");
  }
  if (!["eevee", "cycles_metal"].includes(String(obj.engine))) {
    throw new Error("Unsupported engine.");
  }
  if (!["preview_hw", "master_h264", "master_10bit"].includes(String(obj.encode_profile))) {
    throw new Error("Unsupported encode_profile.");
  }
  if (!Number.isInteger(obj.threads) || Number(obj.threads) < 1 || Number(obj.threads) > 16) {
    throw new Error("threads must be 1..16.");
  }
  if (obj.parallel_workers !== 1 && obj.parallel_workers !== 2) {
    throw new Error("parallel_workers must be 1 or 2.");
  }
  if (!Number.isInteger(obj.sliding_window_chunk) || Number(obj.sliding_window_chunk) < 0 || Number(obj.sliding_window_chunk) > 48) {
    throw new Error("sliding_window_chunk must be 0..48.");
  }
}
