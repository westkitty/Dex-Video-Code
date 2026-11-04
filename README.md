# Dex Video Code

Prompt-first, medium-agnostic creative production coordinator. It selects a route from creative intent and observed capability, keeps asset provenance, and runs bounded local operations. A private GitHub repository is the source of truth; it is not itself a ChatGPT tool or a render service.

## Current verified slice

- TypeScript CLI: `doctor`, `plan`, `produce`, `status`, `verify`, `pack`.
- Versioned CreativeJob v1 schema and strict path/adapter validation.
- Capability report distinguishes local probes from historical or unproven routes. ComfyUI is explicitly excluded.
- Original 16-second kinetic-graphic pilot render through local FFmpeg. Captions and audio are off. It is an authored technical/creative pilot, not evidence of general prompt-to-film or artistic acceptance.
- Local-only adapter; production never invokes arbitrary shell strings, uploads media, or incurs spend.

Requires Node.js 22+, FFmpeg/ffprobe, and a local SVG rasterizer (`sips` on macOS; `magick` elsewhere) for rendering and media verification.

## Quick start

```sh
npm ci
npm test
npm run --silent director -- doctor --json
npm run --silent director -- plan --input "A quiet signal crosses the night and finds an answer" --out examples/jobs/signal/job.json
npm run --silent director -- produce --job examples/jobs/signal/job.json
npm run --silent director -- verify --job examples/jobs/signal/job.json
npm run --silent director -- pack --job examples/jobs/signal/job.json
```

`produce` writes only beneath the job directory, refuses output overwrite, and creates durable state. A failed or stale `RUNNING` job resumes its frame generation after checking recorded process IDs; an active job is not started twice. An existing encoded output is never overwritten. `verify` checks SHA-256, ffprobe metadata, and a full FFmpeg decode. It leaves artistic review pending.

See [operational state](OPERATIONAL_STATE.md), [bridge contract](docs/PROJECT_BRIDGE.md), [Project bootstrap](docs/CHATGPT_PROJECT_BOOTSTRAP.md), [Project setup](docs/CHATGPT_PROJECT_SETUP.md), and [Project instructions](docs/CHATGPT_PROJECT_INSTRUCTIONS.md).
