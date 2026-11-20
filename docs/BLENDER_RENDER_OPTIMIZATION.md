# Blender 5.2+ Rendering & Performance Optimization Suite

This document maps the 20 rendering quality, Apple Silicon performance, and pipeline reliability improvements implemented in `Dex-Video-Code` alongside the measured Big Mac (Apple M4, Blender 5.2.3 LTS) verification results.

## 20-Item Implementation Matrix

| # | Improvement | Implementation |
|---|---|---|
| 1 | Compositor OpenImageDenoise + AOVs | `scripts/blender_render_pipeline.py` (`configure_compositor_pipeline` enabling `use_pass_normal`, `use_pass_diffuse_color`, `CompositorNodeDenoise` with `HDR=True`, `Prefilter='Accurate'`) |
| 2 | Cycles Metal GPU + Adaptive Sampling | `scripts/blender_render_pipeline.py` (`configure_render_engine(..., engine="cycles_metal")`, `CYCLES_QUALITY_PROFILES`, `use_adaptive_sampling`, `OPENIMAGEDENOISE`) |
| 3 | Volumetric Fire (`Principled Volume`) | `scripts/blender_render_pipeline.py` (`build_volumetric_fire_material`, replaces stacked `BLENDED` alpha spheres) |
| 4 | Compositor Mist Pass Depth Blend | `scripts/blender_render_pipeline.py` (`configure_mist_pass` + `ShaderNodeMix` RGBA Mist blend in `configure_compositor_pipeline`) |
| 5 | Physical Motion Blur | `scripts/blender_render_pipeline.py` (`configure_motion_blur` setting `scene.render.use_motion_blur`, `motion_blur_shutter`, `eevee.motion_blur_steps`) |
| 6 | Physical Sky & Light Linking | `scripts/blender_render_pipeline.py` (`configure_physical_sky_world` using `MULTIPLE_SCATTERING` or confined HDRIs; `configure_light_linking` via `light_obj.light_linking`) |
| 7 | Procedural AO & Pointiness Edge Wear | `scripts/blender_render_pipeline.py` (`add_procedural_edge_wear_and_ao`) |
| 8 | 10-Bit Master Encoding (`yuv420p10le`) | `scripts/blender_batch_runner.py` & `src/render-optimization.ts` (`master_10bit` using `libx265 -crf 16 -pix_fmt yuv420p10le -tag:v hvc1`, plus optional `16`-bit PNG intermediates) |
| 9 | Shadow-Map Culling on VFX & Distant Meshes | `scripts/blender_render_pipeline.py` (`optimize_vfx_and_background_visibility` setting `visible_shadow = False` / `visible_diffuse = False`) |
| 10 | Single-Object Geometry Nodes Embers | `scripts/blender_render_pipeline.py` (`create_geonodes_ember_system` replacing 140+ F-Curve spark objects) |
| 11 | Tuned EEVEE Quality Presets | `scripts/blender_render_pipeline.py` & `src/render-optimization.ts` (`EEVEE_QUALITY_PROFILES` & `director render-profiles --json`) |
| 12 | Persistent Warm Render Worker | `scripts/blender_batch_runner.py` (`--warm-worker` JSON-lines loop inside one Blender process amortizing Metal shader compilation) |
| 13 | Viewport vs. Render LOD Separation | `scripts/blender_render_pipeline.py` (`apply_viewport_render_lod` separating `Subsurf.levels` from `render_levels` + optional background `DECIMATE`) |
| 14 | Parallel Chunked Rendering & Thread Tuning | `scripts/blender_batch_runner.py` (`--parallel-workers 1..2`, `--threads 1..16`, `partition_frame_ranges`) |
| 15 | Apple Silicon VideoToolbox HW Preview | `scripts/blender_batch_runner.py` & `src/render-optimization.ts` (`preview_hw` auto-detecting `h264_videotoolbox` with `libx264` fallback) |
| 16 | Configurable Scratch Root & Sliding-Window Cleanup | `scripts/blender_batch_runner.py` (`--scratch-root` / `DEX_RENDER_SCRATCH_ROOT`, `--min-free-gib`, `--sliding-window-chunk`) |
| 17 | Versioned `.blend` Asset & Shader Library | `scripts/blender_asset_library.py` (`library-manifest.v1.json`, SHA-256 verification, symlink-confined `bpy.data.libraries.load`, `--create-starter-pack`) |
| 18 | Automated Pre-Master Visual QA Gate | `scripts/frame_qa_gate.py` (`frame-qa-report.v1` via FFmpeg `format=yuv420p,signalstats` normalized across 8/10/16-bit streams) |
| 19 | SSH ControlMaster Multiplexing & Proxy Transfers | `scripts/transfer_verified_file.py` (`--multiplex`, `--control-persist`, `--manifest-path`, `--transfer-mode proxy|full`) |
| 20 | Resumable Async Queue & Frame-Skip Resume | `src/async-render-queue.ts`, `schemas/render-optimization.v1.schema.json`, & `--resume` (`use_overwrite = False`) |

## Usage Examples

Inspect bounded profiles from the Director CLI:

```sh
npm run --silent director -- render-profiles --json
```

Run the optimized reference scene (`examples/p7/dragon_mountain_sneeze_v2.py`) or batch runner with an explicit output/scratch root:

```sh
/Applications/Blender.app/Contents/MacOS/Blender --background \
  --python examples/p7/dragon_mountain_sneeze_v2.py -- \
  --output-root /approved/render/root \
  --output-dir /approved/render/root/hero \
  --quality hero --engine cycles_metal --color-depth 16 --start-frame 26 --end-frame 26 --save-blend

python3 scripts/blender_batch_runner.py \
  --blend /approved/render/root/hero/dragon_mountain_sneeze_v2.blend \
  --scratch-root /approved/render/root \
  --job-name preview_run \
  --engine eevee --quality preview --start-frame 19 --end-frame 30 \
  --parallel-workers 2 --threads 4 --encode-profile preview_hw \
  --sliding-window-chunk 6 --run-qa-gate --contact-sheet --resume
```

## Measured Empirical Verification (Apple M4 / Blender 5.2.3 LTS)

- **Cycles Metal Hero (`1280x720`, 96 samples, 16-bit PNG, OIDN + Volumetric Fire + GeoNodes Embers + Mist + Motion Blur)**: `metal_gpu: true`, rendered Frame 26 in `160.419s` (`3,494,251` bytes, verified visually).
- **Optimized EEVEE Climax Batch (`640x360`, Frames 19..30, `--parallel-workers 2 --sliding-window-chunk 6 --encode-profile preview_hw --run-qa-gate`)**:
  - Warm climax frame times dropped from `7.70–8.33s/frame` (stacked `BLENDED` alpha fire spheres) to **`0.50–0.59s/frame`** (over 14x faster per warm frame).
  - Complete 12-frame parallel + sliding-window + VideoToolbox H.264 encode + full FFmpeg decode + Frame QA Gate (`status: PASS`, `motion_delta: 37.997`) + 3x2 contact sheet finished in **`11.762s` total wall time** (`658,898,944` bytes peak child RSS).
- **10-bit Master (`master_10bit`, 16-bit PNG -> `libx265 yuv420p10le`, Frames 25..28)**: `3.031s` wall time, `ffprobe` confirmed `hevc` `yuv420p10le`, full decode passed, Frame QA Gate `PASS`.
- **Frame Resume & Warm Worker**: Re-running Frames 25..28 with `--resume` skipped `4/4` frames (`0.0s` render); `--warm-worker` executed JSON-lines render (`0.647s`) and cleanly exited on `quit`.
- **Asset Library & Multiplexed Proxy Transfer**: `materials_pack.blend` (`103,215` bytes) verified via `library-manifest.v1.json`; `transfer_verified_file.py --multiplex --transfer-mode proxy` verified `SCP_VERIFIED` over `StrictHostKeyChecking=yes` with temporary `/tmp` ControlPath sockets.
