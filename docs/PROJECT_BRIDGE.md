# Project bridge contract v1.1

## Identity and transport

- Source: private `https://github.com/westkitty/Dex-Video-Code`, branch `main`.
- CLI: `director` (package `dex-video-code` v0.1.0), Node.js >=22. In a checkout: `npm run --silent director -- <operation>`; installed use: `director <operation>`.
- DEX//REACH Refresh is a callable transport only when an authorized node is freshly selected, fingerprinted, reports `aiAccess=on`, and its exact exposed process tool accepts the call. Historical or repository evidence does not prove a live bridge. No native ChatGPT tool is installed by this repository.
- Workstation and paths are discovered at runtime. GitHub provides source access, not execution. No public HTTP service exists.
- ChatGPT Project `code video` remains `PROJECT_ACTIVATION_PENDING` until its owner installs the supplied instructions/bootstrap and independently verifies the Project-side GitHub access and bridge handshake. Writing this repository cannot change Project settings.

## Operations

`doctor` (read-only), `plan --input TEXT [--out RELATIVE_FILE]`, `produce --job RELATIVE_MANIFEST`, `status --job RELATIVE_MANIFEST`, `verify --job RELATIVE_MANIFEST`, `pack --job RELATIVE_MANIFEST`.

Job inputs use CreativeJob schema v1.1 (`schemas/creative-job.v1.1.schema.json`). Legacy v1 manifests are migrated in memory from their original prompt and then checked against v1.1. The one interpretation pipeline preserves recognized medium, duration, aspect ratio, subject, actions, style/tone, text restrictions and uncertainty. Unsupported media or technique returns `BLOCKED`; it is never silently substituted with video.

The verified renderer supports only silent, text-free when requested, geometric motion graphics encoded as H.264 MP4, 1280×720 at 24 fps, duration 1–30 seconds. Audio, still image, narrative character animation and articulated 3D remain blocked. No route requires 3D except an explicitly 3D performance brief. ComfyUI is excluded.

## Admission and safety

- `produce` validates schema, READY route, exact allowlisted operation/adapter, captions off, empty external asset list, MP4 format and adapter-supported duration/specification before launching a process. Any `approval: required` step is rejected: a user-editable manifest cannot grant approval. The current original local geometric adapter is low-risk and needs no interruption.
- Output paths must be relative and confined beneath the job workspace with no symlink component. Plan output directories are created only inside the workspace and manifests use create-if-absent.
- The renderer writes an isolated same-directory temporary MP4 and atomically links it into place without replacement. Per-job exclusive state lock prevents concurrent production. Failed work may resume only after lock release and prior process checks. Temporary render frames are removed on completion/failure.
- `verify` checks artifact identity and required SHA-256, full decode, duration tolerance (max of 0.1 s or 0.5%), dimensions/aspect, requested frame rate, stream composition, H.264/MP4, and subtitle restrictions. Technical pass never claims human artistic approval.
- No arbitrary shell operation, network, cloud, upload, unapproved spend, model install, or voice/identity generation is part of the adapter.
- `pack` creates a new handoff directory and does not publish or upload.

## Minimal check

```sh
npm run --silent director -- doctor --json
```

## Existing HyperFrames bridge (separate from `director`)

The `director` CLI does not yet dispatch to HyperFrames. A separate bounded
HyperFrames controller was read and its `health` command was called through
the authorized DEX//REACH node on Big Mac. Its commands are limited to
`health`, `submit <project-slug> [draft|looks|delivery]`, and
`status <job-id>`; projects must already exist inside that controller's local
`runs/` directory and are limited to 30 seconds. Use only the discovered
controller path and these exact operations through the exposed DEX process
tool. Do not call the general shell with creative input or arbitrary paths.

This is a verified callable DEX//REACH path to the existing local motion
renderer, not a registered native ChatGPT tool, not a `director` adapter, and
not proof that the `code video` Project settings were changed. The
`docs/capability-baseline.md` and `OPERATIONAL_STATE.md` record current health,
scheduler and pilot results. The MacBook `director doctor` attempt was
separately refused by scheduler admission; do not treat the HyperFrames health
call as a substitute for that CLI contract.

For a GitHub + DEX//REACH handshake, read the contract, README and operational state through the authorized source connector; rediscover/fingerprint the selected node, inspect its process tool and scheduler, then run the exact read-only CLI `doctor --json` invocation and compare results. If source access, CLI or node call is denied, report `BLOCKED_BRIDGE` with the observed missing capability. Do not claim Project activation from a Git URL.
