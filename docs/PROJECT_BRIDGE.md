# Project bridge contract v1

## Identity and transport

- Source: private `https://github.com/westkitty/Dex-Video-Code`, branch `main`.
- CLI: `director` (package `dex-video-code` v0.1.0), Node.js >=22. In a checkout: `npm run --silent director -- <operation>`; installed use: `director <operation>`.
- Current callable transport: authenticated DEX//REACH Refresh to a freshly selected node, using its discovered `reach_list_tools` and the exact exposed `start_process` compatibility tool through `reach_call`. This does not install a native ChatGPT tool and does not mean the target Project is activated. Use only a verified node, fresh fingerprint, `aiAccess=on`, and inspect scheduler before work. Prefer read-only `doctor`; require the owner-controlled node to authorize each call.
- Local workstation and file paths are discovered at runtime. No fixed host identity or output root is assumed by the CLI.
- GitHub is for source reading; it does not execute the CLI. No public HTTP service exists.

## Operations

`doctor` (read-only), `plan --input TEXT [--out RELATIVE_FILE]`, `produce --job RELATIVE_MANIFEST`, `status --job RELATIVE_MANIFEST`, `verify --job RELATIVE_MANIFEST`, `pack --job RELATIVE_MANIFEST`.
All outputs are JSON with `--json`; human-readable mode emits the same object in pretty JSON except help. Inputs are UTF-8 JSON CreativeJob v1 for job operations. The schema is `schemas/creative-job.v1.schema.json`.

CreativeJob IDs are `dv_<time>-<random>`. Manifest-relative artifact paths are confined beneath the manifest directory. Output root is the manifest directory plus its declared `artifacts[].path`; the motion pilot defaults to `outputs/<job-id>/master.mp4`. Existing files are never overwritten.

Capability states: `VERIFIED` means the current bounded probe passed; `AVAILABLE_UNPROVEN` means documented candidate only; `DORMANT` is intentionally gated; `BROKEN` means a current probe failed; `UNAVAILABLE` means not installed/reachable; `EXCLUDED` means policy prohibits selection. Historical receipts never make a current tool `VERIFIED`.

## Admission and safety

- `produce` accepts only the built-in `motion-graphics-local` adapter, requires a 15–30 second MP4 motion-graphics job, local FFmpeg, captions off, a relative path, and a fresh job state. It uses FFmpeg argument arrays with a 240-second timeout. No arbitrary shell, network, cloud, uploads, new voices, or spend.
- Other routes return a blocked/unavailable plan or fail closed. Explicit articulated 3D remains blocked without a verified specialist adapter and native rig proof.
- Existing output or pack paths cause a no-overwrite error. `status` is read-only. A failed or stale `RUNNING` job can resume its source-frame generation; a live recorded CLI/encoder PID blocks concurrent retry. A completed encode must be verified instead of re-rendered. There is no cancellation command; a submission is not completion.
- Errors include invalid schema/path, unallowlisted adapter, missing dependency, already-existing state/output, unsupported route/duration, FFmpeg timeout/failure, missing media, and failed verification. Errors are nonzero CLI exits and state is `FAILED` only when a started production operation persisted that result.
- `verify` reports technical state and keeps `artistic_review=PENDING_HUMAN_REVIEW`; no automated artistic pass is possible.
- `pack` creates a new manifest/proof handoff directory. It does not publish or upload.

## Minimal check

```sh
npm run --silent director -- doctor --json
```

For a GitHub + DEX//REACH handshake: read this contract and current `README.md` + `OPERATIONAL_STATE.md` from GitHub, rediscover and fingerprint the selected node, call its exact `start_process` tool with the verified CLI `doctor --json` invocation, then compare results. If source is inaccessible, CLI absent, or node call denied, return `BLOCKED_BRIDGE` with the exact missing capability. Do not claim the connection is active from a Git URL.
