# Dex Video Code

Prompt-first, medium-agnostic creative production coordinator. The CLI interprets a brief, records supported and unsupported intent, and only executes a bounded local adapter when the whole plan is eligible. A public GitHub repository is source control; it is not itself a registered ChatGPT tool or a render service.

## Studio V2 — Implementation in progress

The product's full next-generation filmmaking plan is tracked in:
- [Studio V2 Master Plan](docs/STUDIO_V2_MASTER_PLAN.md) — detailed artistic vision, system design, security, media routes, delivery, business benchmarks and risks.
- [Implementation Backlog](docs/STUDIO_V2_IMPLEMENTATION_BACKLOG.md) — staged execution with exact scope and acceptance gates.
- [Validation Contract](docs/STUDIO_V2_VALIDATION_CONTRACT.md) — proof standards, negative regression tests, delivery integrity and independent visual review.
- [Codex Start](docs/STUDIO_V2_CODEX_START.md) — self-contained first implementation handoff.

**Use [Codex Start](docs/STUDIO_V2_CODEX_START.md) for the phase gates.** These files describe the plan; consult current code and [OPERATIONAL_STATE.md](OPERATIONAL_STATE.md) for implemented behavior and proof. The bounded P1 Drive adapter is implemented, but a live delivery still requires authorized credentials and destination configuration on the execution host.

## Verified implementation

- TypeScript CLI: `doctor`, `plan`, `produce`, `status`, `verify`, `pack`.
- Versioned CreativeJob 1.1 schema with a compatibility migration for v1 manifests.
- Deterministic brief interpretation for medium, duration, aspect ratio, subject, actions, style, text restrictions and selected constraints. Ambiguous or unsupported production is blocked instead of silently routed to a different medium.
- The `director` CLI's only executable renderer is local authored geometric motion graphics: silent H.264 MP4, 1280×720, 24 fps, 1–30 seconds, captions off. It does not dispatch narrative illustration, character performance, audio, stills or 3D. P7.3 now has a standalone, bounded Blender specialist runner and one verified Sentinel performance; director admission for native 3D remains blocked because no typed authorized worker dispatch or output-reconciliation adapter exists. This one scene does not establish a general multi-character route.
- Pilot A is an independently authored 20-second HyperFrames motion-design film. It used the existing Big Mac controller through DEX//REACH; that controller is not integrated into `director`. See [`media/pilot-a/README.md`](media/pilot-a/README.md) and the evidence-limited [capability baseline](docs/capability-baseline.md). The MP4 and frame review remain local, ignored outputs.
- A 30-second animated explainer of the user-supplied Drakken Terraforming Compendium is in [`media/drakken-compendium-explainer/`](media/drakken-compendium-explainer/). It uses locally generated SVG diagrams and FFmpeg, has no audio or subtitles, keeps the 35 historical proposals distinct from approved/documented categories, and labels illustrations as non-canonical evidence. The MP4 and frame proofs are local, ignored outputs; see its receipt and storyboard for sources and limits.
- Output finalization uses a same-directory temporary encode and atomic create-if-absent linking. State locking prevents concurrent producers. Technical verification checks duration, dimensions, frame rate, streams, codec/container, subtitles, full decode and manifest SHA-256. Artistic review remains human and pending.
- `director auth-google --client-id <id> --picker-api-key <key> --project-number <number>` uses browser-based desktop OAuth with PKCE and a loopback callback, then Google Picker to authorize the selected folder under least-privilege `drive.file`. Refresh credentials go to macOS Keychain. `director configure-drive --folder-id <id>` saves a local-only destination. `director deliver --job <manifest>` renews expired tokens, retries a rejected access token once, and re-verifies the original MP4 before resumable upload. It never grants link-sharing permissions. The ignored job receipt marks `DELIVERED_VERIFIED` only after comparable provider checksum, private parent/permissions and viewing-link readback. OAuth client and Picker API configuration plus user sign-in are required; no client secret is used.
- An opt-in `continuous_circle_square_v1` geometry mode renders a continuous circle-to-square contour with fixed centroid, staged timing and a held final square; old manifests retain their prior rendering. `visual-samples` extracts hashed frames only after a verified master and records pending review without claiming human approval.
- Authored motion scenes use the versioned `authored-motion.v1` composition format for layered geometry, hierarchical object groups, independent eased element/group tracks, camera motion, material-like gradients, reveals, contiguous beats and review sample times. Pass a scene with `director plan --input "<matching silent MP4 brief>" --scene <scene.json> --out <job.json>`; production, integrity verification and visual sampling then use the existing director workflow. Examples include `examples/films/the-last-signal.scene.json` (20-second abstract motion design) and `examples/films/the-impossible-product.scene.json` (24-second authored 2.5D mechanical product commercial). Their rendered masters and review images are local ignored outputs, not repository assets. The commercial's narrow admission requires its explicit authored scene; prompt-only cinematic jobs and native 3D remain blocked.
- `doctor` and planning expose an evidence-backed capability registry and typed creative contract. `verify-assets --job ... --assets ...` checks local asset hashes and confines paths; its receipt does not establish rights, consent or production admission. HyperFrames, general narrative production, live/practical commercial filming and articulated 3D remain unproven or blocked as documented in the operational state; The Aperture is a narrow, authored vector 2.5D scene.
- Earlier private MP4 delivery used the already-authorized Google Drive connector; the standalone CLI still lacks its own Google OAuth authorization. No video was published publicly, and this pass installed no model and incurred no additional spend. ComfyUI is excluded.

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

To render an authored example, use a prompt that matches its medium and duration, pass the corresponding `--scene` file, and choose a new ignored `runs/.../job.json` output path. The Aperture example uses a silent 24-second 2.5D product prompt; it is vector composition with hierarchical transforms, not simulated or articulated 3D.

Planning creates missing parent directories inside the current project workspace, refuses symlink escapes, and never overwrites an existing manifest. `produce` refuses unsupported or blocked jobs. The renderer's title text is omitted when the brief prohibits text. Verification records technical status only; `PENDING_HUMAN_REVIEW` is not an artistic pass.

See [operational state](OPERATIONAL_STATE.md), [bridge contract](docs/PROJECT_BRIDGE.md), [Project bootstrap](docs/CHATGPT_PROJECT_BOOTSTRAP.md), [Project setup](docs/CHATGPT_PROJECT_SETUP.md), and [Project instructions](docs/CHATGPT_PROJECT_INSTRUCTIONS.md).

# Verified binary transfer

`scripts/transfer_verified_file.py` pulls one file from an explicitly named
SSH host/account into an existing local destination directory. Supply approved
remote and local roots, expected byte count, and SHA-256. It requires an
existing trusted host-key entry (`StrictHostKeyChecking=yes`), probes the
remote source for symlinks and exact bytes, downloads to a private temporary
directory, verifies the local bytes, then atomically creates the destination
name without replacing an existing file. A JSON receipt is written beside the
destination. Interrupted attempts can be rerun; an exact existing destination
is reverified without being overwritten, and a mismatching destination fails.

Example (replace every path and identity with values already authorized on the
current machines):

```sh
python3 scripts/transfer_verified_file.py \
  --source-host ssh-config-alias \
  --source-user transfer-account \
  --source-root /approved/remote/export \
  --source-path /approved/remote/export/master.mp4 \
  --destination-root /approved/local/output \
  --destination /approved/local/output/master.mp4 \
  --bytes 1013755 \
  --sha256 <expected-sha256>
```

The helper stores no machine-specific configuration or credentials. It does
not create host keys, modify SSH configuration, grant remote permissions, or
alter the source. A remote account must already be authorized to read the
source path. Python 3, OpenSSH `ssh`/`scp`, and an existing known-host entry are
required.

Run the focused helper regressions with `python3 tests/test_transfer_verified_file.py`.
