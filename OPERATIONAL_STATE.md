# Operational state

Updated 2026-11-04 (America/Detroit). This is current evidence for this checkout,
not a claim that all planned routes or Project settings are active.

## Drakken Compendium explainer — 2026-11-04

- Created a 30-second silent programmatic explanation from the user's supplied
  PDF and source guide. `media/drakken-compendium-explainer/generate.py` creates
  original vector diagrams; it does not reuse the PDF illustrations or execute
  the embedded production prompts. The editable beat map and input hashes are
  in `media/drakken-compendium-explainer/storyboard.json`.
- The piece distinguishes the 58 operational strains, 2 genesis entities, 35
  unapproved historical proposals, and 10 context plates; names the eight
  operational families; and explains the corrected Year 121 / Year 170 war
  anchors and containment aftermath. It also states that images do not
  establish canonical appearance and this is not canon approval.
- Locally encoded `media/drakken-compendium-explainer/renders/drakken-compendium-explainer-30s.mp4`:
  H.264 MP4, 960×540, 24fps, 720 frames, exactly 30 seconds, 685,279 bytes,
  SHA-256 `007bbf3ea316a47cd7fdc80eaf5403747ac3eeceaa6122940f98c266a68e839d`.
  `ffprobe` found one video stream and no audio/subtitle streams; FFmpeg full
  decode passed. The six-scene contact sheet was visually inspected. Receipt:
  `media/drakken-compendium-explainer/receipt.json`.
- Render used local ImageMagick and FFmpeg on MacBook Air (arm64), with no
  network calls, cloud render, spend, voice, music, or source artwork import.
  Human artistic acceptance remains pending. This is a second media artifact,
  not the blocked illustrated Pilot B and not evidence that `director` can
  execute a general HyperFrames job.
- A fresh DEX//REACH node-list request in this pass was refused with
  `UNAUTHORIZED / oauth_token_invalid_grant`; the app connection requires
  reauthentication. No remote render was attempted. Prior DEX/HyperFrames proof
  remains historical and is not promoted to a current bridge check.

## Verified local implementation

- The TypeScript build and `npm test` pass 23/23. Prompt regressions preserve
  duration, medium, subject, action, style and exclusions; unsupported
  illustrated, audio-only and articulated-3D work blocks instead of silently
  becoming the local geometric renderer.
- `director` currently executes only local authored geometric motion graphics
  as silent H.264 MP4, 1280×720 at 24fps, for 1–30 seconds. The existing
  Big Mac HyperFrames controller is a separate motion-design route and is not
  dispatched by `director`.
- A local read-only `npm run --silent director -- doctor --json` call passed.
  It reported MacBook Node v26.13.0, FFmpeg/FFprobe 9.0.2 and `sips` verified;
  no source assets were imported and spend was zero. HyperFrames remained
  `AVAILABLE_UNPROVEN` in that local report because it did not query the
  remote host; the separately verified Big Mac controller and Pilot A are
  recorded below.
- ComfyUI/Comfort UI is excluded. Captions and subtitles remain off by default.

## Pilot A — A Small Signal

- A new original 20-second HTML/CSS/SVG motion-design composition is in
  `media/pilot-a/index.html`; its brief, beat map and receipt are next to it.
- The verified production used HyperFrames 0.8.159, local `delivery` quality,
  Big Mac arm64 and the existing authenticated DEX//REACH controller. The
  controller completed job `hf-20261105t033807-a3ce89e8` after a 272.28-second
  render.
- Output `media/pilot-a/pilot-a-20s.mp4` is a local ignored artifact. Its
  SHA-256 is
  `ce1d2ac34aee1d83b78a9e02783110dd2bb174bad0b7e43616adeebec546e6bd`;
  1,534,549 bytes; H.264 MP4; 20.000 seconds; 960×540; 24fps; 480 frames;
  no audio and no subtitle stream.
- HyperFrames verified the encoded file and full decode. After authenticated
  private SSH transfer, the local file had the same SHA-256 and independently
  passed `ffprobe` and full FFmpeg decode. An encoded-frame contact sheet at
  0, 5, 10, 14, 17 and 19.5 seconds was inspected; signal movement and the
  linked ending are visible. This is a technical pass, not a full playback or
  explicit artistic acceptance. Human review remains pending.
- The first render attempt failed at its final correctness gate because the
  HyperFrames asset server returned HTTP 404 for a symlinked GSAP dependency.
  The isolated pilot runtime was repaired with a regular local copy of the
  existing installed dependency, then the new job completed. The failed job
  was not treated as an output. See `media/pilot-a/receipt.json`.
- The composition uses no acquired/private reference media, external asset,
  voice, music, cloud render, additional spend, or 3D rig. The MP4 and contact
  sheet are ignored and must not be staged.

## Live integration state

- GitHub source access to private `westkitty/Dex-Video-Code` was verified in
  the preceding publication check; this repository is not itself a registered
  ChatGPT tool.
- A fresh Big Mac fingerprint, live DEX scheduler check and bounded
  HyperFrames `health` call succeeded. Its existing controller supports only
  `health`, `submit`, and `status` for projects confined to its local `runs/`
  directory and at most 30 seconds. This proves a callable DEX//REACH path to
  that renderer, not to the `director` CLI.
- The MacBook `director doctor --json` call was denied by DEX//REACH scheduler
  admission with `COORDINATOR_WAIT_TIMEOUT` (6/1 uncoordinated heavy workloads
  and CPU saturation). `director doctor` has no successful live bridge
  receipt. Retry only after scheduler capacity changes.
- Read-only DexDiffusion status, backend health, capability gaps and model
  status returned `UNTRUSTED_BACKEND_IDENTITY`; no DexDiffusion generation was
  attempted. The illustrated/hybrid route therefore has no authorized image
  source/runtime proof in this pass.
- Existing ChatGPT Project `code video` settings were not changed. State is
  `PROJECT_ACTIVATION_PENDING`; the setup and replacement instructions are
  user-managed.

## Remaining phase gates

| Phase | State | Open evidence |
|---|---|---|
| 00 — Baseline | PARTIAL | Relevant read-only capability snapshot only; no portfolio-wide or complete rights inventory. |
| 00B — Repo and Project handoff | PARTIAL | Private source repo and handoff docs exist; Project settings/attachments remain user-managed. |
| 01 — Job contract | PARTIAL | v1.1 schema, v1 migration and tests exist; complete portable asset/proof receipt and signed-plan contract are incomplete. |
| 02 — Capability registry | PARTIAL | Local geometric adapter and controller probes exist; `director` does not dispatch to HyperFrames, and its live doctor is blocked. |
| 03 — Creative direction | PARTIAL | Deterministic parser and route gates work; scored alternatives and rich treatment review are not general. |
| 04 — Asset handoff | BLOCKED | No import/provenance subsystem; DexDiffusion identity is untrusted and no supplied artwork was present. |
| 05 — Motion design Pilot A | PARTIAL | Technical media gate passed; explicit human artistic review remains. |
| 06 — Illustrated/hybrid Pilot B | BLOCKED | No authorized image source and verified production route. |
| 07 — Specialist routes | PARTIAL | Explicit 3D gates exist; VFX, Blender, performance capture and 2D-rig adapters are not integrated/proven. |
| 08 — Sound/assembly | PARTIAL | Pilot A is intentionally silent; general audio workers and mix checks are not verified. |
| 09 — Verify/package/three pilots | PARTIAL | One playable technical pilot exists; three distinct route pilots and artistic reviews are incomplete. |
| 10 — Publication/Project activation | PARTIAL | Prior code milestone is published; current pilot/source changes require their own reviewed commit and push. Project activation remains pending. |

No other Westkitty repository or service was edited. No private media, model,
credential, key or generated video is staged for Git.
