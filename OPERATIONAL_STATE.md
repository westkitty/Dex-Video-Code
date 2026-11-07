# Operational state

## Studio V2 delivery integrity and bridge continuation — 2026-11-07

- Continued from clean `main` at `f00312e087338ce4b79bc14b3341a8bf1fd24227`. Hardened P1 upload bytes: delivery now copies the candidate master into a mode-0600 snapshot inside an owner-only temporary directory, hashes that exact snapshot against the verified SHA-256, uploads the snapshot, then removes it on success or failure. A new regression mutates the source path after snapshot creation and proves the uploaded chunk still matches the verified original; stale bytes are still refused before upload. `npm test` passed 65/65, including the TypeScript build and media-render/verification tests. No live Drive upload was attempted.
- Live Drive connector readback currently lists the prior MP4 in the configured folder as unshared/not public. The user separately reports that a downloaded copy matched the original SHA-256 and fully decoded; this remains user-supplied evidence, not a new download/hash performed in this pass. The connector still does not provide this CLI with its refresh credential or a content-hash readback. Locally, the destination remains configured with file mode 0600, while the app OAuth client ID, Picker key and project number are absent.
- Current Google documentation confirms desktop browser OAuth supports loopback redirects with PKCE, and `drive.file` is limited to files created by the app or selected/shared with it through Google Picker. The existing implementation uses that scope and selects the configured folder before storing refresh authorization. Live scope/folder write access remains unproven until the user completes the app-specific authorization.
- Fresh Big Mac discovery showed an online, healthy scheduler. Its current 22-tool inventory exposes only generic Desktop Commander operations and no documented HyperFrames `health`/`submit`/`status` operation; no generic shell probe or render was attempted. P3 runtime adapter remains blocked. Existing P4/P6 foundations remain as previously recorded; P5 practical filmmaking, P7 articulated 3D, and P8 comparative evidence have no new runtime, rights, approval or benchmark receipts in this pass. No artistic approval is inferred.
- Public-source privacy review found stale statements calling this GitHub repository private. GitHub currently reports it as public; those source-facing statements are corrected in this commit. No private media, account/folder IDs, OAuth configuration values, credentials or generated artifacts are included.
- Exactly one user action is required before standalone live delivery: configure a Google Cloud project with a Desktop OAuth client and restricted Picker API key (Drive API and Picker API enabled), then run the documented `director auth-google` command and complete Google sign-in/folder selection.

## Studio V2 Google OAuth and private delivery follow-up — 2026-11-07

- Continued from commit `e6b2a5c9092f4365804a1c67cff3f8236e76d6de`; checkout was clean on `main` at start. Added browser-based Google Desktop OAuth with PKCE and `127.0.0.1` loopback, least-privilege `drive.file` scope, refresh-on-expiry and one retry after a rejected API token. The refresh credential is stored in macOS Keychain through Security.framework; no credential is written to a repository file or logged. Revoked `invalid_grant` clears the stale credential and requires `director auth-google` again.
- Added `director configure-drive --folder-id <id>` to keep the destination in a mode-0600 local-only config, and `director auth-google` to sign in. OAuth uses `drive.file` with a local Google Picker folder-selection step before persisting refresh credentials; the user must select the exact configured folder. It then reads folder permissions before declaring destination access. Actual upload permission still requires a successful upload with this OAuth client; no custom-client OAuth credential is currently available.
- The installed Google Drive connector was inspected without reading its stored credentials. It could access the provided destination; metadata identified it as a folder with owner-only permission. Through that already-authorized connector, the exact locally verified Studio V2 MP4 (1,784,082 bytes; source SHA-256 `297a3a474f6fb401d4ddc86d3a06757c37fdfa32accd85b7306fbf27391cdc01`) was uploaded as a new MP4 file. Connector readback confirmed destination parent, video/mp4 MIME, exact byte count, owner-only permissions and returned a Drive viewing URL. The connector did not expose a provider content checksum, and the URL was not independently opened for playback; record this as `DELIVERED_UNVERIFIED`, not `DELIVERED_VERIFIED`. This connector grant is not available to the standalone CLI and is not imported into Keychain.
- Focused OAuth/delivery suite passed 17/17 before Picker integration; its later nine-test Picker/OAuth suite passed 9/9. The full repository suite passes 64/64, including loopback PKCE authorization, exact least-privilege scope checks, folder selection/cancel, expiry renewal, revoked refresh recovery, API 401 token refresh, interrupted resumable upload, checksum mismatch, destination privacy and no-token log assertions. The destination folder is configured locally in `~/.config/dex-video-code/config.json` with mode `0600`; that file contains only the folder ID. The Keychain helper ran on macOS and confirmed no app credential is present. No rendered media, Drive file/folder IDs, URL, client credential or token is staged.
- Current DEX//REACH discovery shows Big Mac online with an idle healthy scheduler, but its 22 exposed Desktop Commander operations contain no HyperFrames health/submit/status operation. The local `hf` executable is Hugging Face CLI, not HyperFrames. No remote render or integration attempt was made; P3 remains blocked on a documented bounded controller operation. P5 practical filmmaking and P7 native 3D remain blocked by the verified routes/gates already recorded. P4/P6/P8 foundations from the previous milestone remain unchanged; no user visual approval, asset rights or benchmark is inferred.
- Current one-time blocker: no Google Desktop OAuth client, Picker API key or refresh credential exists for this app. The single required user action is to complete Google setup once: create a Desktop OAuth client and API key in the same Google Cloud project, enable Google Drive API and Google Picker API, restrict the key to those APIs, then run `director auth-google --client-id <CLIENT_ID> --picker-api-key <KEY> --project-number <NUMBER>` and sign in/select the configured folder. Consent is accepted only when the scope set is exactly `drive.file`. The selected folder must read back as private before credentials are saved, and the first actual file create verifies upload permission. Any scope/folder mismatch fails closed. It never silently broadens to all-Drive access. A legacy access-token environment variable is ignored by the CLI.

## Studio V2 implementation continuation — 2026-11-07

- Checkout remains on `main` at the verified starting commit `f628c80b3f4b0e866acf0d31d7449927ab8a5756`; implementation changes below are local and not yet committed. The public-repository privacy boundary remains in force.
- P1 source foundation is implemented as recorded below. `DEX_DRIVE_ACCESS_TOKEN` and `DEX_DRIVE_FOLDER_ID` are unset on this host; no real Drive call or upload occurred. Automated mock tests do not establish live folder authorization or working user playback.
- P2 bounded circle-to-square morph is implemented behind `continuous_circle_square_v1`, retaining legacy rendering for older manifests. Local Film A passed `director verify`: silent H.264 MP4, 1280×720, 24fps, 288 frames/12.000 seconds, full decode, SHA-256 `297a3a474f6fb401d4ddc86d3a06757c37fdfa32accd85b7306fbf27391cdc01`, 1,784,082 bytes. Six encoded frames and a contact sheet were generated and inspected locally under the ignored job workspace. This proves the bounded local geometry and technical encoding only; human artistic acceptance and delivery remain pending.
- P3 capability registry distinguishes current evidence from historical/unproven capability. The existing HyperFrames route is not integrated into `director`; current DEX//REACH access did not expose its operations, so no remote render was submitted. Stored local plans remain inspectable; production re-probes local render tools.
- P4 adds a typed creative contract to planning and handoff, plus verified-master visual sample extraction with a persisted `PENDING_VISUAL_REVIEW` receipt. It does not record human approval.
- P6 adds local asset byte/hash/path checks and a `director verify-assets` sidecar receipt. The receipt says `LOCAL_BYTES_CHECKED`, `authorization_state: NOT_ESTABLISHED_BY_THIS_CHECK`, and `production_admission: NOT_GRANTED`. Rights and consent fields are user assertions, not independently established; no assets were supplied or imported.
- P5 commercial physical filmmaking and P7 native articulated 3D remain blocked by absent verified routes and their plan gates. P8 tracking is partial; there are no approved style examples or comparable reviewed films, so no benchmark is claimed. Later filmmaking phases have not been started.
- The local full test suite is being run for this source state. No MP4, frame image, account/folder identifier, or credential is to be staged. No commit, push, installation, live service test, or human acceptance has occurred.

## Studio V2 P0 / P1 delivery foundation — 2026-11-06

- Starting source was `f628c80b3f4b0e866acf0d31d7449927ab8a5756` on `main`; the checkout was clean and matched `origin/main` before implementation. GitHub repository metadata was rechecked through the connected GitHub account and reports visibility `public`. This conflicts with older README/bridge text that calls it private; no visibility setting was changed. Keep secrets, private media and account/folder identifiers out of this public source.
- The local baseline `npm test` passed 23/23 before changes. Node was v26.13.0. The baseline renderer is still the existing local geometric route; source-level behavior remains the circle/square overlay crossfade identified above. The director still has no HyperFrames dispatch. No second render was made just to recapture the known failure.
- Added an optional Google Drive delivery adapter and `director deliver --job <manifest>`. The command confines the manifest/master, requires the manifest's technical-pass state, performs a fresh full media verification and refuses changed bytes. The adapter hashes the original file, uses a resumable Drive upload, private `appProperties` idempotency identity and provider lookup before creating a retry. It checks folder/file permissions for public access, exact parent, name, MP4 MIME type, byte size, provider MD5 and Drive viewing link. It never creates sharing permissions or overwrites an existing item. If provider bytes are not comparable or the link is absent, the receipt remains `DELIVERED_UNVERIFIED` and withholds the link.
- Delivery state/receipt is a nonsecret sidecar in ignored job `job-state.json`; current config names are `DEX_DRIVE_ACCESS_TOKEN` and `DEX_DRIVE_FOLDER_ID`. No credential values, refresh-token flow, folder identity or account identity are stored in source. Both variables were absent on this MacBook execution host, so no live upload was attempted. `BLOCKED_AUTH` is the current live delivery state; actual Drive ID, metadata readback and user-accessible playback are unverified.
- Added deterministic Drive mock coverage for exact-byte success, uncertain-upload retry reconciliation without duplicate creation, interrupted-upload status reconciliation, changed source rejection, public folder/file denial, missing provider checksum, wrong parent, authentication redaction, bounded HTTP retry, rate-limit versus storage-quota classification and missing config. A director-level integration test renders and verifies a local master, then confirms missing credentials persist `BLOCKED_AUTH` without changing the MP4. The first expanded run under host load failed three existing render/CLI tests (29/32); their targeted rerun passed 3/3, and the final complete `npm test` passed 34/34. No human artistic review or P2 work occurred.
- Threat boundary: the repository is public; no credentials/IDs/media were added. The adapter sends bearer authorization only to Google API calls and holds the resumable session URL in memory; exception messages omit tokens, response bodies and session URLs. The connected Drive app is not a credential source for the standalone local CLI.
- Files changed in this pass: `src/delivery.ts`, `src/cli.ts`, `tests/delivery.test.ts`, `README.md`, and this record. Changes remain local and uncommitted/unpushed. Live delivery additionally requires authorized API credentials and the intended private folder ID on the host that runs `director`; no upload, Drive file ID or viewing link is claimed.

## Studio V2 documentation handoff — 2026-11-06 (America/Detroit)

- Four **planning-only** files prepared for the authorized GitHub documentation publication: docs/STUDIO_V2_MASTER_PLAN.md, docs/STUDIO_V2_IMPLEMENTATION_BACKLOG.md, docs/STUDIO_V2_VALIDATION_CONTRACT.md, docs/STUDIO_V2_CODEX_START.md. README.md and AGENTS.md link to and govern the new plan. This is not an implementation claim.
- Source/checkout baseline checked at commit 5abbb7e865dcca56463c7b25246e4353addb771f on main; Big Mac checkout was clean and origin/main matched at inspection. GitHub API reported repository visibility **PUBLIC** on this date, conflicting with older "private" text in README/bridge/Project instructions; privacy and owner decision remain OPEN. Do not publish private media, personal account identifiers, credentials or copyrighted references in this public branch.
- Recent 12-second circle-to-square renderer test: a silent H.264 MP4 technically passed 12.000 seconds, 1280x720, 24fps, 288 frames, no audio/subtitles, full decode and master SHA; actual visual behavior crossfaded an independently drawn circle/square while moving, not a genuine geometric morph. This is the explicit V2 regression.
- A playable viewing copy was later uploaded to a private macbook/video render Google Drive folder and the provider returned a file ID/readback metadata, but this did **not** prove that the cloud copy was byte-identical to the Big Mac original master. V2 P1 must solve reliable authenticated upload and checksum/readback before claiming master delivery.
- Current director supports only one executable local geometric route. The existing HyperFrames pilot is separate and not integrated. Film B, Film C, a general audio system, new canonical/reference ingestion and automated studio delivery are all NOT IMPLEMENTED.
- Direct Big Mac git push dry-run failed because Git HTTPS credentials were unavailable on that node. Use authenticated GitHub connector for documentation publication when available. Verify GitHub HEAD after any update; do not claim the local Big Mac checkout automatically updated from remote.
- Plan execution order: P0 baseline -> P1 delivery foundation -> P2 genuine morph/Film A -> P3 verified capability registry/HyperFrames -> P4 director/QA -> P5 commercial -> P6 references/illustration -> P7 conditional articulated 3D/Sunforge -> P8 measured business comparisons. Each phase requires separate validation and appropriate authorization.
- ChatGPT Project activation remains PROJECT_ACTIVATION_PENDING and user-owned; repository documentation cannot activate it.


Updated 2026-11-05 (America/Detroit). This is current evidence for this checkout,
not a claim that all planned routes or Project settings are active.

## Drakken explainer refinement — 2026-11-05

- Rebuilt the six-scene explanation as an animated 30-second local MP4. The
  sequence animates orbital traces, category bars, family reveals, world-system
  transformation, chronology and containment, and evidence cards. Exact
  category values remain fixed while bars animate, so intermediate frames do
  not imply a false subtotal.
- Visual review found and corrected a black SVG overlay, low-contrast body and
  diagram labels, and overlapping count annotations. The rebuilt encoded
  contact sheet and representative full-size frames were inspected after the
  final encode. Current media and source hashes are recorded in
  `media/drakken-compendium-explainer/receipt.json`.
- Technical media checks pass: H.264 960x540, 24 fps, 720 frames, 30 seconds,
  video-only; `ffprobe`, full `ffmpeg -xerror` decode, Python syntax, and JSON
  parse all pass. Human artistic acceptance remains pending. Drive replacement
  is pending until upload and metadata readback complete.
- No audio, captions/subtitles, source illustration, ComfyUI, remote rendering,
  cloud/API calls or spend were used. This remains an explainer, not a canon
  update or a complete film adaptation.

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
