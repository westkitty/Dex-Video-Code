# Studio V2 — Implementation Backlog and Dependency Gates

State: PLANNED, not implemented. Read STUDIO_V2_MASTER_PLAN.md, STUDIO_V2_VALIDATION_CONTRACT.md and OPERATIONAL_STATE.md before running a phase. This is the scoped execution ledger for Dex-Video-Code Studio V2. Keep each milestone bounded and stop when the definition of done is met. Update OPERATIONAL_STATE.md with actual results, not promises.

## Standard implementation packet

Each phase requires: objective; in-scope change set; out-of-scope protections; currently authoritative source files; live capability/rights/authorization gates; exact tests and observable evidence; rollback/reversibility; implementation result and next decision. Do not infer runtime authorizations from planning documents.

Keep each Codex work unit one cohesive patch and at most one repair pass unless the owner approves more. Do not bundle unrelated refactors. Prefer a fresh branch for invasive source changes when permitted; do not force-push. Documentation publication authorization in 2026-11-06 does not grant future code mutation, release, deployment or other-repo writes.

## Phase P0 — Reality, source and security baseline

Purpose: establish correct starting truth, eliminate stale capability claims and prevent public-source leakage.

Tasks:
P0.1 Read README, OPERATIONAL_STATE, PROJECT_BRIDGE, AGENTS, source and tests. Record exact commit and clean/dirty status. Preserve pre-existing work.
P0.2 Inspect GitHub visibility and compare docs. The GitHub API reported this repo PUBLIC on 2026-11-06, conflicting with docs claiming PRIVATE. Record verified current state and seek separate authorization for visibility change; do not change it in a normal build pass.
P0.3 Run relevant typecheck/build/tests and existing doctor, separately record host and CLI version. Node availability, FFmpeg and rasterizer are not cinematic route proof.
P0.4 Identify all existing renderer outputs, ignored assets and remote controller boundaries without uploading or committing them.
P0.5 Capture a baseline render/reference of the known circle-crossfade failure if already available and rights-safe. Otherwise record its source-level signature rather than re-render just for documentation.
P0.6 Record a minimal threat model: credential handling, remote shell/CLI trust, asset ingestion, public branch writes, cloud delivery, dependency integrity.
P0.7 Identify the smallest next mutation. No speculative setup or package install.

Exit: a factual baseline, test receipts, exact source revision, repo visibility record and distinct verified/unproven/blocked capability list. Keep historical reports as dated evidence, not "current" status.

## Phase P1 — Master delivery and real completion state

Purpose: a verified master can reach the authorized private Google Drive folder without the user moving files.

Suggested code boundary:
- Provider-neutral DeliveryAdapter with typed config/authorization state, upload verified artifact, reconcile pending session, readback, verify and return receipt.
- GoogleDriveDeliveryAdapter only after current SDK/API, quota and licensing research; do not embed secrets, folder/account identity or raw OAuth tokens in the public repository.
- Job-state extension or sidecar DeliveryReceipt with schema, migration and legacy behavior. Avoid tightly coupling current CreativeJob v1.1 validator to network resources.
- CLI integration only after type and safety tests. A delivery command should accept a previously verified, confined artifact reference, not an arbitrary path from natural language.
- Separate secret-free configuration, e.g. environment variables/keychain/authorized connector with redacted diagnostic output.

Required receipt fields:
source job id and revision; local master relative path; exact master SHA-256 and byte size; destination provider; private parent folder identity; provider file id; upload attempt/idempotency key; actual remote name; MIME; provider checksum if comparable; authenticated readback method; verified timestamp; actual provider link; privacy checks; errors/retry state. Never include bearer URLs or credentials.

State progression:
NOT_REQUESTED -> PENDING -> UPLOADING -> DELIVERED_UNVERIFIED -> DELIVERED_VERIFIED, with BLOCKED_AUTH / RETRYABLE / FAILED as explicit branches. "Rendered" and "delivered" do not imply "artistically approved".

Requirements:
- Exact binary master, not a recompressed proxy. Source hash equality when readback exists; Google MD5 may be comparable to local MD5, otherwise authenticated streaming SHA-256 readback. If only metadata size and no safe content proof is available, remain unverified.
- No overwrite, accidental public sharing or duplicate upload on uncertain retry.
- Resumable/streaming behavior for normal and large files. Avoid giant base64, chat bridges and ad hoc public HTTP endpoints.
- Credentials verified at runtime; missing auth returns BLOCKED_AUTH without trying to mint/fetch unrelated secrets.
- Provider mock tests include interrupted upload, 401/403, quota, 5xx, checksum mismatch, misleading name, parent mismatch, collision, duplicate outcome and link absent.
- Ensure the prior user Google Drive macbook/video render folder can be configured without hardcoded public account details.

P1 acceptance:
A. All mocked cases pass deterministically.
B. At least one known verified, small MP4 is delivered by an authorized route to a private test destination after a real preflight, or live delivery remains transparently BLOCKED with mock coverage passing.
C. Actual source master and returned remote metadata/readback agree; document exact proof.
D. Original remains intact; no public permissions; correct link opens for intended account.
E. Normal user report is short and includes link only on real success.

Rollback: preserve existing CLI; turn off optional delivery adapter without losing original file or job data.

Do not advance to a claim of end-to-end studio success without P1 live proof.

## Phase P2 — True vector morphing, Film A

Purpose: make a single circle become a square continuously, with authored timing and real encoded evidence. Do not replace all historical geometric jobs with new timing; introduce explicit route/variant or compatible versioned behavior.

Detailed 12-second film "The Geometry of Becoming":
- 16:9, 1280x720, 24 fps; H.264 MP4; 288 frames; absolutely silent; no captions, subtitles, words or title overlays.
- Centered subject against deep navy/near-black backdrop with restrained luminous turquoise / pale highlight accent.
- 0–3s: a circle emerges cleanly and becomes visually legible; no shape drift.
- 3–8s: actual outline points/curvature/interpolation change coherently into a square; same subject/continuity, no second overlapping object, opacity crossfade, random rotation or premature snapping.
- 8–12s: motion slows to controlled square with a settled stationary final hold. Avoid clumsy full-duration travel.
- Natural anticipation, easing and smooth corners without overshooting into broken geometry; no pointless particle storm.
- Choose the simplest capable implementation: explicit path segment interpolation/matched topology, GSAP MorphSVG if current installation/license and offline rendering support prove fit, or a better verified approach. Do not adopt a library for its name alone.
- Preserve the baseline original as evidence, not as approved output.

Test geometry with representative timestamps and intermediate contour properties. Explicitly reject old implementation signatures (two simultaneous SVG shape elements opacity-mixing across the entire animation). Encode and examine samples from the real MP4: 0.5, 3.5, 5, 6.5, 8.5, 11.5 sec plus any clipping-prone transitions. Technical checks: ffprobe, full decode, dimensions, 288 frames, stream restrictions, hash.
Human visual approval pending until user reviews. Deliver exact master through P1 only if that route is live and separately authorized.

P2 acceptance: actual morph exists; named original visual action is fulfilled; technical verification passes; frame proof; no loss to older geometric jobs; honest user-facing preview/master delivery state.

## Phase P3 — Typed capability registry and HyperFrames adapter

Purpose: select among genuinely executable routes rather than misleading single-score alternatives.

Plan:
- Define capability identity, host, version, last proof, fresh admission checks, duration/sizing, assets/rights, privacy/cost, format, verification and failure handling.
- Keep statuses for VERIFIED_LIVE, HISTORICAL_ONLY, INSTALLED_UNPROVEN, BLOCKED, DORMANT, UNKNOWN, EXCLUDED.
- Route choice must preserve medium/action requirements and avoid degraded silent fallback. Test nonavailability.
- Build a bounded external-controller adapter only after verifying the live HyperFrames controller contract. Known historical API: health, submit prepared local project slug and tier, status job id; no arbitrary natural-language shell injection. Respect per-host allowed runs root, max length and owner-controlled DEX access.
- Perform one controlled integration proof with a prepared rights-safe project, avoiding duplicate production merely to claim readiness.
- Preserve prior director geometric adapter and existing receipt and recovery behavior.

Exit: route registry reports accurate health, named worker can be invoked by documented allowlisted operation, no unsafe fallback, end-to-end film proof distinct from health. Mark unavailable if bridge is blocked.

## Phase P4 — Creative director and visual QA

Purpose: a "film" is a sequence of intentional actions, not a generic procedural screensaver.

Tasks:
- Versioned, typed intent compiler with preserved source and explicit negative constraints.
- Object identity and type contracts; subject/action/recipient relationships; no invented population or literalization.
- Shot/beat sequencing with begin/change/resolve causal states, camera, continuity and exact timing.
- Scaled complexity: compact simple graphic; shot manifest for commercial/explainer; storyboards and fidelity gate for characters.
- Visual evidence manifest that indexes encoded timeline samples without implying that a montage equals a film.
- Defect classes for wrong action, clipping, overdraw, poor contrast, missing hold, bad framing, continuity drift, incorrect ending.
- One bounded repair pass and recorded post-repair differences.
- Separate machine-inspectable checks from human artistic review.

Exit: multiple fixtures show the system honors subject/action, omission, framing, audio/text defaults and designed ending; visual QA honestly reports limitations.

## Phase P5 — Original commercial, Film B

Purpose: prove nontrivial cinematic scene authoring and commercially presentable visual continuity in a 20–30-second original imaginary product advertisement.

Design gates:
- Product silhouette, value proposition, world, light/material laws, shot identities and reveal treatment.
- Full sequence with opening curiosity, tactile close-up, useful feature/reveal, premium finishing shot.
- No unlicensed trademarks, product logos or real-person appearances.
- Use motion graphics, authored 2.5D or proven compositing route based on intent, not obligatory 3D.
- Preserve reproducibility, editable source and versioned cut history.
- QA shadows/material coherence, camera spatial direction, continuity, framing, scene transitions, no accidental captions.

Exit: 20–30s encoded original film, review frames, editable source, actual private master delivery and human review request. Do not self-approve.

## Phase P6 — References and illustrated/character routes

Purpose: original/canonical art, 2.5D and recurring characters without random identity drift or rights compromise.

Tasks:
- Asset manifest with hash, rights, source, revision, consent, transforms, allowed use and attribution.
- Approved/reference/experimental categories with immutable user approval events.
- Declared use of real approved image pixels for identity-sensitive work; fail closed when source isn't available to renderer.
- Reference rejections and per-shot continuity checks.
- Prove one bounded illustrated or rigged character motion sample before production-level promises.
- Avoid source asset uploads to unapproved external providers.

Exit: proof that route uses permitted real references, actual video shows intended motion and continuity, privacy/rights reviewed.

## Phase P7 — Articulated 3D and Film C

Purpose: build a real cinematic character-performance route only when a brief demands it and after artistic feasibility proof.

Required staged proof before full film:
1. Character/model appearance and source fidelity.
2. Correct topology, physically usable articulation/rig and control.
3. Walk/turn/strike/contact/motion continuity as needed.
4. Camera and set scale, lighting and materials.
5. Short interaction slice with collision, impact and readable cause/effect.
6. Encode, technical proof, independent human visual sign-off.

Film C: "The Sunforge Requiem," 35–45 seconds, mechanical cathedral with captured star, fading artificial dawn, defender against an armored warlord, physical struggle and final visual payoff. Do not substitute static concept panels for requested 3D animation. Live worker, asset rights, budget and user review are independent admission gates.

Exit: only actual full 3D rendered sequence after proof, never claim completion from rig demo or concept art.

## Phase P8 — Benchmarks, memory, studio interface

Purpose: evidence-backed competitive capability and low-friction repeatability.

Tasks:
- Standardized comparable briefs and blinded human preference rubric.
- Measure quality, fidelity, operator interruptions, editing time, failures, output delivery, cost and repeatability.
- Approved style/shot-effect reference library with rejection and supersession.
- User experience: "Make this" -> "Watch this", accessible controls, preview vs original clearly labeled, optional detailed receipts.
- Runtime lifecycle, disk-space and error budgets backed by actual measurements; do not promise arbitrary speed.

Exit: three independent showcase films with honest creative/human status, comparable alternative results, measured friction reduction and a repeatable service process.

## Cross-phase dependencies and invariants

- No ComfyUI/Comfort UI.
- Captions/subtitles OFF by default, including track metadata and burned text.
- Supplied text/audio preserved unless edit explicitly authorized.
- No public uploads of private media, no credential leaks, no unapproved spend, no cross-repo writes.
- Big Mac/MacBook/other endpoints need fresh fingerprint, job admission, explicit commands and current permissions for every separate execution.
- Technical tests, encoded film visual review, successful upload, Git commit/push and user artistic approval are separate.
- Existing jobs, SHA receipts, legacy schema compatibility, no-clobber and lock behavior must not regress.
- Archive precise source/output lineage for successful deliverables, but keep video masters and user media out of Git.

## Required after-phase reporting

For each completed unit, append to OPERATIONAL_STATE.md:
- baseline HEAD and resulting revision when applicable;
- files changed;
- implemented capability only;
- tests/build exact results;
- runtime/host and actual media/hash evidence;
- upload/readback or concrete blocker;
- artistic review state;
- regressions checked and known failures;
- next small work unit.

One concise user report: outcome, verified film link if available, blockers and next action. No lengthy implementation lecture.

## Phase sequencing stop rule

Do not turn one Codex task into a multi-month autonomous program. First Codex assignment is P0 plus P1 delivery foundation and a *bounded* P2 morph only if P1 exits without a capability issue or is independently mock-complete. It must not begin P3–P8 code until later explicit authorization. The owner can advance phases after reading evidence; this roadmap itself is not universal permission.
