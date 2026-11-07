# Dex-Video-Code — Studio V2 Master Plan

Status: APPROVED DIRECTION / NOT IMPLEMENTED. Planning baseline: 2026-11-06. This file governs the proposed Studio V2 uplift, not claims that its capabilities already work. Implementation phases, tests and Codex's first assignment are in STUDIO_V2_IMPLEMENTATION_BACKLOG.md, STUDIO_V2_VALIDATION_CONTRACT.md and STUDIO_V2_CODEX_START.md. The current verified behavior remains governed by actual source/tests and OPERATIONAL_STATE.md.

## 1. Mission and acceptance philosophy

Turn the existing prompt-first director into a reliable, creatively capable, medium-agnostic film studio that can accept an ordinary-language request, select a verified production route, create a visually authored film, inspect the encoded results and deliver an authentic watchable master with minimal operator intervention.

The user experience must be: "Make me this film" -> a film that respects the brief -> a direct playable private delivery link. Ordinary requests must not turn into installation lessons, command-paste sessions, repeated permission discussions or impressive technical reports without a watchable film.

Success is not a successful CLI exit, generated plan, test count, small preview, frame montage or unverified upload. Technical validity, full video delivery and explicit artistic acceptance remain distinct. Preserve the user's final creative judgment.

This project is intended to become a competitive commercial-grade creative pipeline. Claims that it surpasses another producer require blind, like-for-like evaluation of actual finished films and measured operator work.

## 2. Evidence-backed starting position

Historical source baseline: westkitty/Dex-Video-Code main at 5abbb7e865dcca56463c7b25246e4353addb771f, checked 2026-11-06. Recheck HEAD and state before any subsequent implementation. The prior date and revision are orientation, not a permanent lock.

Implemented in the existing repo:
- TypeScript director CLI: doctor, plan, produce, status, verify and pack.
- CreativeJob schema v1.1, legacy migration and a deterministic brief interpreter.
- One executable director route: locally authored silent geometric H.264 MP4, nominal 1280x720 at 24 fps, 1–30 seconds.
- Real filename/path confinement, exclusive job locking, atomic no-clobber output and hash/ffprobe/full-decode checks.
- Separate existing HyperFrames 20-second authored motion-design pilot, with recorded evidence. HyperFrames is not a director adapter.
- Separate 30-second Drakken Compendium explainer with its own programmatic SVG/FFmpeg production path and local receipt. It is not a universal illustrated-film route.
- Existing restrictions on 3D rig requests, asset rights, ComfyUI, caption defaults and claims about artistic acceptance.

Failure that prompted V2:
- A request for a luminous circle transforming continuously into a square produced a circle traveling across the screen while an independently drawn square faded in; a technically valid MP4 did not satisfy the intended visual action.
- Completing the file did not produce an immediately accessible video. A later Drive transfer required cumbersome intermediate work and yielded a viewing copy rather than a demonstrated byte-identical master.
- The user had to act as an operator for a large amount of low-value technical work.
- The current routing module effectively exposes one selected route, not a scored comparison among multiple live proven workers.
- Source files describe the repository as private but GitHub API reported visibility PUBLIC on 2026-11-06. Resolve the mismatch as an explicit security/owner decision; this plan itself must contain no secrets or private reference media.

Do not erase any of these working capabilities or misrepresent former failures as current proof. OPERATIONAL_STATE.md and the relevant real receipts remain authoritative for existing historical tests.

## 3. Product-level contracts

### 3.1 User contract

Input: one natural-language request plus optional images, audio, text, references, constraints, existing project and explicit budget.
Output: a film if and only if a verified route can produce it, or one concise, actionable explanation of the specific unavailable prerequisite.
Routine user-facing result: a playable link, one-sentence creative summary, brief caveat if relevant and an offer to revise. Detailed technical evidence remains accessible but not dumped into chat.

Never:
- Turn a 3D articulated performance into a slideshow, a static illustration or an unrelated 2D approximation.
- Turn a physical/object transformation into an overlay/crossfade unless that is precisely what the user asks.
- Claim a general video capability from a health probe or a single unrelated pilot.
- Assume audio, music, captions or typography when the requested content is silent/text-free.
- Hide rights, cost, privacy, runtime or identity requirements.
- Require routine repeated approvals that follow from previously scoped authorization.
- Make the user transfer files manually as part of ordinary production.

### 3.2 Definition of "finished"

The following facts need separate durable evidence:

| Gate | Meaning | May it imply artistic approval? |
| --- | --- | --- |
| PLANNED | Validated creative contract and route selection | No |
| ADMITTED | Runtime, rights, costs, privacy, inputs and required authorization checked | No |
| RENDERED | Encoded target bytes exist on the intended node | No |
| TECHNICALLY_VERIFIED | Verified duration, dimensions, streams, full decode and hash | No |
| VISUALLY_REVIEWED | Actual encoded frames/video examined against observable scene requirements | No |
| DELIVERED_VERIFIED | Exact intended master stored privately, identity/integrity checked and link returned | No |
| ARTISTICALLY_APPROVED | User accepted creative result explicitly | Yes, only for approved scope |

A failed gate never inherits success from a previous gate. For complex films, "visual review pending" is a valid outcome after verified delivery. If a proxy/transcoded preview is delivered, label it PREVIEW and separately identify the MASTER.

### 3.3 Competing objectives and priorities

Order of precedence: explicit user brief and source protection; lawful/authorized rights and privacy; feasibility and medium fidelity; visual storytelling; reliable final delivery; performance efficiency; optional visual embellishment. Do not optimize speed at the expense of a fundamentally wrong film.

## 4. Proposed logical architecture

The following boundaries are design targets, not an assertion that modules already exist:

Conversation or CLI
  -> Intent compiler and constraint lock
  -> Creative director and shot/beat map
  -> Rights/cost/asset authorization gate
  -> Live capability registry and route selector
  -> Bounded production adapter(s)
  -> Edit/composite/encode
  -> Technical verification
  -> Visual evidence and bounded repair
  -> Private delivery adapter
  -> Source/proof archive, user link and approval receipt

Avoid coupling these lanes into one giant renderer. The job contract should own meaning, desired results and evidence; each adapter should own only its narrow execution. A director must never synthesize an arbitrary shell command from user prose.

Architecture constraints:
1. Deterministic contracts and validator are authoritative; model-proposed creative prose is advisory until compiled into checked data.
2. The original source_prompt and explicit immutable requirements survive transformations verbatim.
3. Plans are immutable snapshots or versioned; re-planning creates a new revision, not quiet edits to a signed/approved plan.
4. A render can run only when a live adapter proves relevant capabilities and required safety gates pass.
5. Adapters accept structured, allowlisted operation names and sanitized arguments, not unrestricted command strings.
6. One job's filesystem state and output are isolated; reruns are versioned and idempotent.
7. Artifacts carry lineage: source brief, selected plan, adapter/version, inputs, derived renders, verification, uploaded master identity and approval state.
8. A user's creative approval cannot be fabricated by a programmatic threshold.

## 5. Creative intent: from words to cinematic meaning

The current brief interpreter retains common literals but lacks deeper action semantics. V2 should add a versioned CreativeIntent/SceneContract layer without breaking existing v1.1 jobs.

Capture at minimum:
- Intended audience experience: e.g. awe, restraint, tenderness, dread, comedy, spectacle.
- Central dramatic proposition: what changes and why it matters.
- Subject ontology and identity: objects vs characters vs symbols; exact relations; shape permanence; canonical appearance only when verified.
- Nonnegotiable action semantics: "morph" changes the same object; "walk" requires articulated motion; "ring" requires a cause and sound only if allowed; "only these" excludes additions.
- Camera/framing: continuity, stationarity, movement, focal subject, aspect, shot scale.
- Composition and lighting: palette, contrast, hierarchy, readability, material identity.
- Temporal beat map with time ranges, start/action/end states, cause-effect and final hold.
- Sound intention: silent, supplied soundtrack, effects, dialogue; never infer captions from speech.
- Explicit negative space: absent characters, forbidden assets, no overlays, no text, prohibited effects.
- Source linkage and confidence for every nontrivial reference.
- Observable proof obligations for each mandatory creative requirement.

Deliver a normalized typed IR with both machine-checkable invariants and a short human-facing creative treatment. Store unknowns as unknowns rather than inventing subject identity, assets, location or authorization.

Complexity scaling:
- Simple motion graphic: compact beat map and one continuous visual-object contract.
- Explainer/commercial: shot map, identity/style locks, transition and ending contracts.
- Multi-character/long cinematic sequence: storyboard, blocking, continuity, rights, asset and production feasibility gates.
Do not produce a 50-page brief for a 12-second simple animation.

## 6. Directing for visual authorship

The creative director must specify a purpose for each shot: introduce, reveal, complicate, contrast, escalate, resolve or hold. Ensure visual information changes meaningfully; avoid generic panning, perpetual zooming and randomly layered particles.

Creative acceptance considers:
- Coherent composition and focal hierarchy.
- Intentional lighting/material treatment and plausible physical cues.
- Actual actions, not proxies; object permanence and continuity across shots.
- Controlled energy and rhythm: anticipation, acceleration, pause, payoff.
- Distinctive visual language suitable to the content, not a fixed "AI cinematic" filter.
- Accessibility for viewers: legible required text, appropriate safe contrast, no unexpected flashing or unnecessary sensory overload.
- Correct aspect ratio and coherent cropping on final export.
- Memorable ending: not merely a fade because the runtime ran out of time.

Artistic scoring is a review aid, not a substitute for viewing or user acceptance. Critical violations (wrong character, omitted mandatory action, content copied without rights, broken clipping, unrequested subtitle track) block acceptance even if an aggregate score is high.

## 7. Real production routes and decision policy

A medium-agnostic studio is a dispatcher of proven capabilities. Proposed staged routes:

| Route | Intended use | Current evidence | Planned admission gate |
| --- | --- | --- | --- |
| Native vector morph | Geometry, icons, transforms, restrained motion design | Existing generic renderer currently crossfades | Explicit continuous-geometry and encoded-frame proofs |
| HyperFrames authored motion | Elegant CSS/SVG/HTML compositing, graphic motion, title systems | Historical pilot/controller, not director-connected | Fresh controller identity, bounded operations, prepared project assets, run receipt |
| Programmatic explainer | Charts, educational sequences, precise diagram animation | A distinct Drakken explainer exists | Reproducible scene contract, data/source checks, validated encoded frames |
| Remotion/editorial | Reusable coded commercials, shot assembly, previews | Available only as an external lead | Exact current local proof, license, performance and rollback decision |
| Layered 2.5D/illustrated | Parallax, paintings, animated atmospheric scenes | Not a general proven route | Authorized art, provenance, visual depth/motion proof and encoded result |
| Reusable 2D character | Strong character continuity with rig/cel workflow | Unproven for this project | Reference and motion fidelity tests, approved asset rights |
| Native articulated 3D | Complex acting, combat, real camera blocking | Specialist/other-repo leads only | Verified model, rig, articulation, runtime, camera and human review |
| Audio and finishing | Sound effects, mix, licensed music, supplied dialogue | General system not verified | Rights, source preservation, stream and mix checks; silence accepted |

The registry should distinguish VERIFIED_LIVE, HISTORICAL_ONLY, INSTALLED_UNPROVEN, DORMANT, BLOCKED, EXCLUDED and UNKNOWN or equivalent states. A static "installed" flag must not result in READY. Every capability record needs observedAt, host, adapter/version, allowed input, output, constraints, costs/rights/privacy, proof method and expiry/freshness policy.

Route scoring is based on fidelity first, runtime proof second, rights/privacy third, overall art direction and available resources fourth, cost/performance last. Never select an apparently cheap route if it changes the ontology, medium or mandatory action. If no route fits, explain one missing gate.

HyperFrames integration must honor the existing documented narrow controller: health, submit and status with prepared local projects under its owned runs directory and its current duration limit. Do not turn this into arbitrary shell authority. Existing outside repositories stay read-only without separate authorization.

## 8. First-class delivery service

Delivery is a studio feature, not an optional export step.

Target user-facing destination: the user's authorized private Google Drive folder named macbook/video render. The folder ID must be supplied via configuration/connection rather than embedded in public source. The account, exact folder ID, permission scope and current credential must be verified by the running host before upload.

Delivery contract:
1. Only a technically verified existing source master may enter delivery.
2. Compute/record local byte count and SHA-256 and retain canonical source path.
3. Derive a collision-safe, versioned name from job identity plus a sanitized title; never overwrite an approved file.
4. Upload through an authenticated Drive provider with minimum suitable scopes; prefer supported resumable upload and streaming for larger files.
5. Treat upload sessions and tokens as secrets; never log bearer/session URLs.
6. Persist a nonsecret retry record and idempotency key mapping source master identity to a single destination ID. On uncertain response, query before retrying; do not create duplicate masters by default.
7. Check returned file metadata: provider ID, exact parent, filename, MIME type and size. Capture permissions/visibility when allowed; never assume a link is private without verifying scope.
8. For byte-level proof, compare a trusted remote checksum when algorithm and semantics match (e.g. Drive MD5 when available, compared with local MD5 of exact bytes), or stream authenticated readback and compare SHA-256. A metadata size match alone is not an integrity proof.
9. A generated preview/transcoded copy must have a different role/name and never satisfy master equality checks.
10. Return the exact provider-generated URL only after successful identity/readback. If provider permissions prevent a view link, report DELIVERED_UNVERIFIED and a precise missing gate.
11. Never publish an anyone-with-link permission implicitly.
12. Keep the original source master and its verification receipt, even after successful upload.

Do not transfer large binary content as chat text/base64, put private data on a public service, or work around an unavailable scope by obtaining credentials from unrelated apps. OAuth/authorized app setup is an explicit separate account action; provide a concise connection request if absent.

Proposed delivery states: NOT_REQUESTED, PENDING, UPLOADING, RETRYABLE, BLOCKED_AUTH, FAILED, DELIVERED_UNVERIFIED and DELIVERED_VERIFIED. State transitions need explicit test coverage for crashes, retries, provider 5xx, quota limits, stale sessions, duplicate names, mismatched parent, bad hashes and missing credentials. No terminal "COMPLETE" on failed delivery.

## 9. Verification and creative QA

Technical proof:
- Independent file existence and byte count.
- ffprobe duration, width/height, container, codec, frame rate, frame count where needed, declared audio/subtitle streams.
- Full decoded-frame traversal with a failing exit on error; detect black/frozen/silent stretches where relevant.
- SHA-256 recorded for actual master (and every distinct preview).
- Evidence of source/shot manifest and output correspondence.
- No incidental subtitles/captions. Audio absent for intentionally silent jobs.
- No rendered temp frames wrongly included in Git.

Visual proof:
- Inspect actual encoded frame samples across the full timeline, not static project source.
- Sample all key action transitions, beginning/end holds, scene boundaries and failure-prone moments.
- For narrative action, independently verify subject identity, movement/physical articulation, object state, continuity, spatial placement, framing and the planned causal outcome.
- Record visual defects with timestamps, severity, source action, responsible adapter, narrow correction and post-repair proof.
- Allow one bounded repair pass by default. Escalate or report partial honestly when the deeper route is unsuitable.
- Review and approval remain human-centered; an automatically computed 85/100 is a provisional showcase target, never a source of authorization.

Full acceptance specifics and regression fixtures belong in STUDIO_V2_VALIDATION_CONTRACT.md.

## 10. Asset, reference and IP governance

Treat every asset as a typed, versioned item with: source URI/owner, license, consent, permitted use, actual hash, resolution/duration, transformations, derivative relationship, style and identity locks, access boundary and attribution. Unknown rights block commercial publication; do not silently replace unavailable artwork with a lookalike asset.

Private and canonical artwork may be used only by explicitly authorized compatible routes with actual usable pixels. Do not infer approvals from filenames or memory. Original source materials remain intact. Voice/identity generation requires verified permission; no unverified cloning. Preserve user-supplied audio and text exactly unless edit authorization is clear.

ComfyUI/Comfort UI remains excluded. No unapproved provider spend, public processing of private media, extra third-party telemetry, model download, repository crossing or secret commits.

Commercial dependencies require current license validation. Current official leads (checked 2026-11-06; recheck at adoption):
- Google Drive resumable upload: https://developers.google.com/workspace/drive/api/guides/manage-uploads
- GSAP MorphSVG: https://gsap.com/docs/v3/Plugins/MorphSVGPlugin/
- Remotion licensing and tier conditions: https://www.remotion.dev/docs/license/pricing and https://www.remotion.dev/docs/terms
- Motion Canvas introduction: https://motioncanvas.io/docs/
Do not claim any such route is installed, entitled or usable from documentation alone.

## 11. Artistic memory without canon drift

A private reference library should contain:
- Explicitly approved style examples and film masters.
- Per-scene treatment, color, camera, lighting and timing specifications.
- Rejected variants, exact reasons and regression fixtures.
- Verified reusable effects or procedural techniques with dependency/license notes.
- Approval records with who/when/which revision/which asset hash and scope.
- Character and world locks without inventing canonical approvals.
- Source-of-truth pointers and supersession history.

Avoid training an indiscriminate model on everything. Recommendations may cite prior successful decisions but new designs are not automatically "approved". Store consent and provenance; keep approved and experimental lanes separate.

## 12. Performance and operations

Big Mac is a known remote production candidate, not a permanently authorized machine. Every session must rediscover and fingerprint a node through DEX//REACH, confirm owner-controlled access, healthy scheduler and precise checkout/branch/revision before any bounded process call.

No command authority follows from a GitHub URL or a prior successful remote session. Execute approved documented CLI/controller operations only. Side-effectful cloud uploads need separate provider credential and scope validation.

Track technical costs separately: time to first reviewable output, end-to-end delivery time, encoded bytes, retries, frames rendered, CPU/memory pressure, temporary disk use and failed-attempt burden. Set performance budgets from measured baselines; do not make unsupported timing promises. Prefer resumable jobs with safe checkpoints over rendering everything twice. Keep immutable masters while pruning only safely identified temporary intermediate data after validated preservation and explicit cleanup authority.

## 13. Demonstration program

Film A — The Geometry of Becoming: 12 seconds, one luminous shape continuously morphing from a centered circle to a stationary square against a dark background, no text, sound or captions. This is a regression for the old circle-overlay failure and the first proof of truthful delivery.

Film B — The Impossible Product: 20–30 seconds, original imaginary object, premium materials, authored camera choreography, reveal, tactile lighting, clear sellable story and finishing. Verify that it is more than a collage or product stills.

Film C — The Sunforge Requiem: approximately 35–45 seconds, mechanical cathedral surrounding a failing star, defender and warlord with causally continuous actions and emotional payoff. If the chosen brief requires articulated 3D, this film must use genuinely articulated animation; not a 2.5D substitute. Do not start full production until the corresponding route passes a minimal character/interaction/lighting proof.

All three remain separate production jobs with explicit input/rights and human artistic review. No claim of film B/C completion is justified by passing film A.

Benchmark against another workflow only with equivalent briefs, similar review constraints, preserved outputs and independent/blind human evaluation. Track per-film creative quality, repeatability, actual editing burden, operator interruptions, end-to-end delivery and failure/rework. Do not announce competitive victory without comparable data.

## 14. Delivery roadmap and prioritization

See the detailed backlog for exact tasks and tests. Critical dependency order:
P0 — Source/security/reality baseline; non-invasive checks.
P1 — Master delivery adapter and truthful end-to-end status.
P2 — Real vector morphology and authored timing; deliver film A.
P3 — Capability registry and bounded HyperFrames integration with proof.
P4 — Creative intent/shot contract and stable visual QA.
P5 — Reusable commercials and finishing; deliver film B.
P6 — Asset/reference and illustrated/character routes with rights gates.
P7 — Articulated 3D proof and Sunforge Pilot C when explicitly warranted.
P8 — Benchmarks, approved reference memory, user experience and robustness.

Only advance after acceptance evidence. Each completed milestone updates OPERATIONAL_STATE.md; incomplete experiments remain labeled UNKNOWN or BLOCKED. Another agent must be able to resume cold from repository files without chat memory.

## 15. Business-grade decision gates

Before adding a route or package, compare:
- Fidelity to current briefs and quality gain over existing methods.
- Maintenance and license burden.
- Hardware and resource requirements.
- Privacy/data egress.
- Determinism, portability and editing/reproduction.
- Runtime integration complexity and error recovery.
- Cost to verify and repair.
- Capability to preserve existing working output.

The decision may be "do not add". A technically sound specialized tool is not automatically a studio-wide default. The least complicated route that can truly deliver the requested film wins.

## 16. Risk register

| Risk | Early indicator | Prevention / stop condition |
| --- | --- | --- |
| Impressive docs but no playable films | Status ends at RENDERED or tests | Require verified link and viewing evidence |
| Unwanted creative substitution | One object becomes two, 3D becomes slides | Typed action semantics and frame-specific invariants |
| Unknown source privacy | Repo documented private but API public | Audit actual visibility; avoid private content, seek owner action |
| Token/file-transfer hacks | Huge base64, manual copy, inconsistent sizes | Native streaming/resumable Drive adapter; master equality proof |
| Live route claimed from history | Old health receipt used as availability | Probe identity and worker at time of admission |
| Arbitrary shell injection | Natural-language brief reaches process shell | Allowlisted structured operations/argument arrays |
| Secret or media leak | Token, sessions or user media in Git/logs | Scoped credentials, ignore rules, diff/privacy gate |
| Expensive render without visual proof | More time spent re-rendering same defect | Early representative proof, one bounded repair, stop |
| Too many runtimes | Duplicate capabilities, opaque licenses | Capability comparison and dependency decision gate |
| Generated-looking commercial work | Generic lighting/stock effects | Authored composition, independent human comparison |
| False artistic approval | Machine metric equals "approved" | Explicit human consent and approval event |
| User becomes operator | Repeated commands and approval prompts | Silent internal workflow, clear one-line blocker only |

## 17. Governance, authority and migration

Existing CLI, contracts and outputs are incumbent behavior to preserve. Future changes should be introduced under versioned compatible schemas or migration tests, never by rewriting v1.1 manifests in place. Old jobs remain readable. Technical receipts and artistic approvals must persist separately.

Source-of-truth order: current actual code/tests and verified render bytes; OPERATIONAL_STATE.md; docs/PROJECT_BRIDGE.md; this proposed master plan and backlog for future work; older historical notes as evidence leads. If newer approved decisions supersede this roadmap, record the delta explicitly.

User authorization for committing this documentation does not authorize automatic repository code edits, cloud authentication setup, destructive cleanup, production spend, publication of films or changes to other repositories. Future Codex runs inherit only authorization explicitly given for their own execution.

The final product is not "a renderer with 50 features". It is an authored, reliable studio in which the person asks for a film and receives one.
