# Dex Video Code

Prompt-first, medium-agnostic creative production coordinator. The CLI interprets a brief, records supported and unsupported intent, and only executes a bounded local adapter when the whole plan is eligible. A private GitHub repository is source control; it is not itself a registered ChatGPT tool or a render service.

## Verified implementation

- TypeScript CLI: `doctor`, `plan`, `produce`, `status`, `verify`, `pack`.
- Versioned CreativeJob 1.1 schema with a compatibility migration for v1 manifests.
- Deterministic brief interpretation for medium, duration, aspect ratio, subject, actions, style, text restrictions and selected constraints. Ambiguous or unsupported production is blocked instead of silently routed to a different medium.
- The `director` CLI's only executable renderer is local authored geometric motion graphics: silent H.264 MP4, 1280×720, 24 fps, 1–30 seconds, captions off. It does not render narrative illustration, character performance, audio, stills or 3D. Explicit 3D performance is blocked unless a future verified specialist route is added.
- Pilot A is an independently authored 20-second HyperFrames motion-design film. It used the existing Big Mac controller through DEX//REACH; that controller is not integrated into `director`. See [`media/pilot-a/README.md`](media/pilot-a/README.md) and the evidence-limited [capability baseline](docs/capability-baseline.md). The MP4 and frame review remain local, ignored outputs.
- Output finalization uses a same-directory temporary encode and atomic create-if-absent linking. State locking prevents concurrent producers. Technical verification checks duration, dimensions, frame rate, streams, codec/container, subtitles, full decode and manifest SHA-256. Artistic review remains human and pending.
- Production stayed on the authorized local hosts; no public upload, cloud call, model install or additional spend occurred. ComfyUI is excluded.

Requires Node.js 22+, FFmpeg/ffprobe, and an SVG rasterizer (`sips` on macOS; `magick` elsewhere) for rendering and media verification.

## Quick start

```sh
npm ci
npm test
npm run --silent director -- doctor --json
npm run --silent director -- plan --input "A 12-second geometric motion graphic showing circles transforming without text" --out examples/jobs/signal/job.json
npm run --silent director -- produce --job examples/jobs/signal/job.json
npm run --silent director -- verify --job examples/jobs/signal/job.json
npm run --silent director -- pack --job examples/jobs/signal/job.json
```

Planning creates missing parent directories inside the current project workspace, refuses symlink escapes, and never overwrites an existing manifest. `produce` refuses unsupported or blocked jobs. The renderer's title text is omitted when the brief prohibits text. Verification records technical status only; `PENDING_HUMAN_REVIEW` is not an artistic pass.

See [operational state](OPERATIONAL_STATE.md), [bridge contract](docs/PROJECT_BRIDGE.md), [Project bootstrap](docs/CHATGPT_PROJECT_BOOTSTRAP.md), [Project setup](docs/CHATGPT_PROJECT_SETUP.md), and [Project instructions](docs/CHATGPT_PROJECT_INSTRUCTIONS.md).
