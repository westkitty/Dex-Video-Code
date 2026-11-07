# Studio V2 — Validation, Proof and Acceptance Contract

Status: PROPOSED CONTRACT. These tests are required when associated components exist; they are not historical PASS claims. Read the current actual tests and source before implementing test fixtures. Never treat a checkmark in this document as evidence that code ran.

## 1. Evidence hierarchy

Highest for implementation: current actual tracked source and reproducible tests, then verified runtime/file bytes and trusted provider readbacks, then dated logs/receipts, then operator descriptions and plans. A proposed outcome never becomes verified because a model claims it. GitHub HEAD, local checkout, built binary, remote runtime and Google Drive storage can each be different states.

Required proof record format:
- job ID and exact authorizing brief/revision
- commit/dirty state at run, host fingerprint and tool versions
- source/input identities, rights and literal requirements
- route selected and capability admission evidence with observed time
- exact local output path and SHA-256, bytes, duration, dimensions, FPS, audio/subtitle streams
- full-decode result and representative encoded-frame checks with timestamp
- delivery source hash/bytes vs remote file ID/parent/bytes/checksum/readback, precise link and privacy status
- human artistic approval reference or PENDING_HUMAN_REVIEW
- any failure and one bounded repair
- no secrets, bearer tokens, private references or payload/base64 in proofs

Use compact, structured JSON for receipts if useful, under safe ignored/local paths for media-specific proof and small portable metadata in the repository only when privacy permits. Never commit a real MP4 or private user art merely to preserve proof.

## 2. Completion state machine

Suggested independent axes:
- PRODUCTION: PLANNED, READY, RUNNING, RENDERED, FAILED, BLOCKED.
- TECHNICAL: PENDING, PASS, FAIL, UNVERIFIED.
- VISUAL: PENDING, REVIEWED_DEFECTS, REVIEWED_NO_KNOWN_DEFECTS, USER_APPROVED.
- DELIVERY: NOT_REQUESTED, PENDING, UPLOADING, RETRYABLE, BLOCKED_AUTH, FAILED, DELIVERED_UNVERIFIED, DELIVERED_VERIFIED.
- EXTERNAL_PUBLICATION: NOT_REQUESTED, APPROVAL_REQUIRED, PUBLISHED_VERIFIED (never implicit).

The application may choose other typed names compatible with v1.1, but it must never collapse these meanings into a single misleading "complete".

Example invariant: user-facing "video ready to watch" requires actual valid playback link to correctly identified video file and successful delivery proof. User-facing "artistically approved" requires an explicit human acceptance event. A preview transcode is never an exact-byte master.

Failure transitions:
- a render can pass while delivery fails: RENDERED/PASS with DELIVERY_FAILED, not COMPLETE.
- upload accepted but no comparable checksum/readback: DELIVERED_UNVERIFIED.
- uploaded wrong parent or public permissions: DELIVERY_FAILED or BLOCKED, never VERIFIED.
- a locally inspected source cannot certify cloud copy by association; verify the uploaded file or acknowledge limits.
- retry from uncertain upload must first reconcile source hash, idempotency token and provider file ID; no duplicate by default.

## 3. Legacy behavior regression

Before code changes, identify current tests and freeze:
- CreativeJob v1.1 schema and v1 legacy normalization.
- Preserve source prompt, explicit text/audio constraints, requested duration and medium.
- Existing supported geometric jobs continue to render and verify.
- Explicit unsupported articulated 3D remains blocked, not silently downgraded.
- No generated caption/subtitle tracks unless explicitly requested and supported.
- Safe project-relative paths, no symlink escape, exclusive lock and atomic no-clobber.
- Existing pack output and proof fields remain readable.
- No reliance on nonexistent future adapters.
- Failure cannot produce an artistically approved state.

After code changes run current test suite, plus targeted new tests; evidence includes exit codes and timestamps, not "tests should pass".

## 4. Phase P1 delivery matrix

Unit and mock integration cases with explicit expected outcomes:

| Case | Stimulus | Required result |
| --- | --- | --- |
| D01 | valid verified master, authorized folder | correct new remote file, metadata and link |
| D02 | source master absent | reject before upload, no fake success |
| D03 | changed source bytes/hash | reject rather than upload stale file |
| D04 | missing or expired credential | BLOCKED_AUTH, no credential extraction/log |
| D05 | bad folder ID/parent mismatch | stop or fail; never claim destination success |
| D06 | same filename exists | collision-safe new filename, no overwrite |
| D07 | retry after uncertain success | reconcile existing provider file, no duplicate |
| D08 | network disconnect during chunk | resumable or retryable, no loss of master |
| D09 | provider 401/403/429/5xx | correct bounded backoff/status, no uncontrolled retry |
| D10 | size match but checksum mismatch | fail integrity; size not proof |
| D11 | no comparable checksum/readback | DELIVERED_UNVERIFIED, no full master claim |
| D12 | remote file is preview transcode | not interchangeable with original master |
| D13 | broad/public sharing returned | block or explicitly flag; never publish implicitly |
| D14 | link missing or access denied | no usable-link claim |
| D15 | concurrent jobs, same title | distinct source/destination identities |
| D16 | malicious path or symlink | reject outside declared root |
| D17 | upload response lost | persist safe checkpoint, query before repeat |
| D18 | partial provider metadata | fail closed or mark unverified with precise reason |
| D19 | secrets in logging error | redaction test |
| D20 | successful authenticated readback | exact local-vs-remote bytes/hash and correct parent |

A mocked provider is never live upload proof. Live P1 test requires verified authorized provider identity and an explicit target folder, known test asset, real provider ID and readback result. If no permitted live path exists, status must be "mocked tests passed, live delivery BLOCKED/UNVERIFIED" and the next narrow prerequisite.

## 5. Phase P2 geometry/film matrix

Film: The Geometry of Becoming. Required 12.000 seconds (tolerance per verifier), 1280x720, 24 FPS, 288 frames, H.264 MP4, no audio and no subtitle track, no on-frame captions/text. Sample exact frames from encoded master near 0.5, 3.5, 5.0, 6.5, 8.5 and 11.5 seconds; include any action extrema.

| Case | Requirement | Check |
| --- | --- | --- |
| M01 | one object morphs | geometry has continuous identity; no source/destination overlay opacity mix |
| M02 | initial circle is visible | initial contour curvature/equidistant radius property, visual sample |
| M03 | intermediate shape genuinely changes | distinct intermediate contour(s) with mathematically valid geometry |
| M04 | terminal square | four corners, straight edges, proper final visual sample |
| M05 | no sideways drift | centroid fixed within declared small tolerance throughout transform |
| M06 | final stationary hold | last frames unchanged except allowable subtle lighting treatment |
| M07 | timing | formation 0–3, morph 3–8, resolve/hold 8–12, no abrupt split |
| M08 | correct aesthetic | subdued luminous dark-background design with readable contrast |
| M09 | no clipping | subject remains entirely inside safe frame with declared margin |
| M10 | no accidental content | no letters, title, captions, sound or extra objects |
| M11 | encoded output valid | ffprobe, full decode, exact or justified frame-count proof, sha |
| M12 | legacy protected | preexisting geometric jobs still pass regression tests |
| M13 | output delivered | exact MP4 hash/bytes match private Drive readback, otherwise delivery separately unverified |
| M14 | human acceptance | explicitly pending until user approval, even if all machine tests pass |

Geometry proof can inspect authored paths and programmatically sampled contours, but source-level geometry cannot substitute for viewing encoded frames. Visual proxy/previews must be labeled and never silently treated as final MP4.

## 6. Phase P3 registry and bridge matrix

- VERIFIED_LIVE requires a capability probe *on the current execution node* with a timestamp and actual applicable operation. Historical health reports are HISTORICAL_ONLY.
- Unavailable renderer must not be selected READY; provided film medium/action may not be silently downgraded.
- HyperFrames adapter must restrict call surface to documented controller operations (historically health, submit, status), max 30 seconds subject to current live contract, prepared project slug confined to owned runs directory.
- Reject arbitrary shell strings in inputs, path traversal, symlink escaping, injected process arguments, user-chosen executable names and untrusted file glob expansion.
- Confirm numeric and format limits before job launch.
- 3D acting brief without verified rig/renderer remains blocked.
- Connection fails, access off, wrong machine, stale capability, unhealthy scheduler -> no job, clear blocker.
- A successful health probe does not equal rendered-film proof.
- No remote credentials/paths leaked into source Git commits.

## 7. Phase P4 creative intent regression fixtures

Use a mixture of examples and negative cases:
- "A luminous circle morphs into a square" -> one single contour changes across time; not fade between two.
- "A robot walks, stops and points" -> genuine locomotion and pose changes; no horizontal sliding proxy.
- "An articulated 3D puppet fight" -> explicit 3D route with rig and contact checks; block if absent.
- "Silence, no text or subtitles" -> zero audio/subtitle streams, no title rasterized.
- "Only a dog and a chair" -> no extra person, animal or invented props.
- "A symbolic Blood Ring" -> preserve ontology and source constraints; avoid guessing canon appearance.
- "The hero catches an opponent's arm" -> spatial and causal contact, no unrelated action substitute.
- "Exact supplied narration" -> preserve original words/audio, no captions unless explicit.
- "30-second multi-shot commercial" -> brief-to-shot timing, consistent product and visual payoff.
- "Unknown referenced character" -> fail closed for identity-sensitive generation without authorized pixels.
- "12s clip but renderer supports only 10s" -> reject or explicitly revise under new authorization; do not truncate silently.
- "No private uploads" -> prohibit unauthorized remote provider despite a tempting fast external alternative.

Check source-intent fidelity with deterministic test assertions where possible. Human visual inspection remains required for more nuanced motion, acting, continuity and emotional impact.

## 8. Showcase and independent comparison

Film A: genuine morph, controlled graphic composition, correct silent master, private playable link.
Film B: 20–30 seconds, commercial story arc, coherent physical product, deliberate lighting, tactile close-up, camera continuity, finished editable source, private verified master.
Film C: 35–45 seconds; only after verified route to required character/rig motion; concrete start/action/end causality and readable payoffs, encoded master, private verification.

Creative scorecard (human-facing, provisional):
- Visual originality and authorship 25.
- Animation and physical believability 20.
- Composition, lighting and polish 20.
- Story and emotional impact 20.
- Fidelity to brief, character, references 15.
An exploratory target >=85/100 is not a pass if any critical semantic, identity, rights, privacy or mechanical requirement fails. No machine score promotes an artistic approval event.

Business comparison:
- Pre-register equivalent briefs and constraints for competitor and Dex pipeline.
- Blind/randomized human reviewers when feasible, with consistent viewing conditions.
- Track winner/preference, artistic dimension scores, operator interventions, time to verified delivery, edit iterations, failure burden, spend and privacy compromises.
- Report sample size and limits; do not overclaim from 1–3 cherry-picked jobs.

## 9. Security/provenance gate

- Confirm actual GitHub visibility independently; if public, keep all new docs and assets public-safe and flag the documentation mismatch.
- Inspect staged diff for credentials, authentication tokens, real private source images, account identifiers, unnecessary personal data, local absolute paths in released source, downloaded models and MP4s.
- Exclude ComfyUI everywhere.
- No unapproved provider spend, paid package enrollment, public upload, identity/voice generation, third-party telemetry or unrelated repo changes.
- Preserve supplied text/audio and references.
- No deletion/cleanup merely because a backup or source is presumed rebuildable.
- Git commit and push require explicit user authorization and actual proof of resulting GitHub HEAD.
- A pushed documentation plan is not evidence that Studio V2 code was implemented.

## 10. Minimal operator-facing report

Regular successful delivery:
"Your film is ready: [provider-verified link]. [Optional one-line factual note]."
Partial:
"Film made, delivery blocked: [single specific prerequisite]. Original preserved at [verified location]."
Failure:
"Couldn't make the requested film because [specific missing approved route]. Nothing was silently substituted."

Never dump manifest dumps, FFmpeg logs, huge base64 or internal implementation steps in a routine answer. Make detail available when requested.

## 11. Audit trail, maintenance and release checks

At each phase completion:
1. Record pre-change source SHA/status and post-change changed files.
2. Show tests actually run with result.
3. Inspect diff and source privacy.
4. Cite runtime job receipts and encoded-frame proof for renders; upload verification for delivery.
5. Append OPERATIONAL_STATE.md with precise statuses.
6. Commit/push only under that phase's authorization; verify returned GitHub HEAD.
7. Preserve existing known-good examples and rollback path.
8. Stop when current acceptance passes. Do not automatically take the next milestone because it appears in this document.

Review debt monthly: old "verified" capabilities become historical unless a fresh adapter check refreshes them; rights and license claims need current sources before commercial use.
