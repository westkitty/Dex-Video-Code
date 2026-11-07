# Studio V2 — Codex Start Here

This is the entry point for a fresh Codex agent. Primary mission: begin Studio V2 implementation in the *existing* westkitty/Dex-Video-Code repository, not a new project. Read the three neighboring documents first:

1. docs/STUDIO_V2_MASTER_PLAN.md — the complete product/design/technical vision.
2. docs/STUDIO_V2_IMPLEMENTATION_BACKLOG.md — each build phase, dependencies, acceptance and stop rule.
3. docs/STUDIO_V2_VALIDATION_CONTRACT.md — precise proof requirements and regression fixtures.

Also read AGENTS.md, README.md, OPERATIONAL_STATE.md, docs/PROJECT_BRIDGE.md before source edits. These governing files constrain everything in the broader plan. Locate current source from HEAD; prior observed planning baseline was 5abbb7e865dcca56463c7b25246e4353addb771f, not an assumed current revision.

## Assignment 01 — P0 + bounded P1

**Do real implementation, not another planning-only essay.** First build the secure, testable master-delivery foundation. The first functional question is "can a verified original MP4 be reliably delivered as the same bytes to the user's authorized private Google Drive destination and a usable link returned?"

Scope:
- P0 exact repo/security/capability baseline.
- P1 a typed provider-neutral delivery interface, Google Drive adapter if feasible, durable nonsecret delivery states/receipts, collision-safe idempotence, safe retry reconciliation and unit/integration mocks.
- Wire this into existing verified-video workflow with the smallest compatible API/CLI extension. Do not degrade existing doctor/plan/produce/status/verify/pack.
- Add tests for all P1 negative/error/privacy paths in validation contract.
- Implement a genuine end-to-end test **only** if authorized credentials, runtime scope and private folder are actually available; otherwise mark live delivery blocked without making up a cloud success.
- A second bounded unit, P2 geometry morph for Film A, may be started *only after* P1's code/tests are complete and if time/runtime/resource constraints justify it; do not dilute P1 deliverables to squeeze both into one pass.
- Do not begin P3–P8 production work in this assignment. Leave precise handoff for later stages.

Important current reality:
- One executable director built-in renderer performs SVG circle/square crossfade and moves shapes; not a genuine contour morph.
- HyperFrames is historically proven for separate motion work but is NOT integrated with director.
- Last known GitHub API visibility was PUBLIC even though docs describe PRIVATE. Recheck visibility and **do not** alter account or repository permissions.
- Last known direct Big Mac git push lacked credentials. You may use the authorized Codex Git integration/workflow if available. Never copy credentials across machines or bypass permission.
- Google Drive destination configuration must not hardcode personal folder/account data into the public repository. Require authorized environment config. Do not use upload-base64-through-chat hacks.
- Projects elsewhere in Westkitty are independent and read-only unless separately authorized.
- Original MP4 master, technical verification, Drive upload and user artistic approval are **four distinct evidence states**.
- No ComfyUI, unapproved spend, user reference uploads, external public render services, identity/voice generation, unexpected captions or destructive cleanup.
- Preserve existing user changes, verified behavior and source assets. Do not upload/push generated master media to GitHub.

## Expected implementation process

1. Read controlling docs and take a repo/current-source snapshot (branch, status, HEAD).
2. Inspect src/cli.ts, src/job.ts, src/render.ts, src/verification.ts, src/types.ts, schema, existing tests and nearest related source.
3. Confirm what delivery facilities already exist; do not reinvent a proven safe route.
4. Freeze a minimal bounded change set for P1; no unrelated modernization.
5. Implement code and provider mocks.
6. Run focused checks, npm test and relevant build/integration tests. Run full live readback only under actual authorized credentials.
7. Review changed-file scope/security and redact all secrets from receipts.
8. Append precise actual results to OPERATIONAL_STATE.md. Include new architecture/usage documentation where necessary.
9. Commit/push implementation only if the *current Codex execution* has explicit authorization, appropriate provider permission and working Git. Otherwise return a verified local patch and exact limitation. Do not force push.
10. Stop and report real evidence; do not continue to the next phase automatically.

Default one primary implementation pass plus at most one bounded repair pass. Do not ask the user to run commands for you when you have a working execution tool. If blocked, preserve working changes and state one specific next prerequisite.

## Delivery adapter acceptance

- Prevent uploading missing/unverified or modified masters.
- Preserve exact bytes; do not use a proxy as a master.
- Support current safe provider-auth setup only; never prompt the user to paste secrets into Git or chat.
- New file is private and stored under intended verified parent folder; version names instead of overwrite.
- Retry after an uncertain result queries the provider first.
- Provider ID, parent, MIME, bytes, checksum/readback method, access status and actual link persist in a sanitized receipt.
- Do not report DELIVERED_VERIFIED from file-size match alone.
- Unit/mock suite passes cancellation, network faults, provider auth errors, duplicate name, hash mismatch, partial readback and public-sharing denial.
- Original remains accessible on verified rendering node.

## Final reply to the owner

Short, plain language. Include:
- STATUS: COMPLETE (for P1 only), PARTIAL or BLOCKED.
- WHAT CHANGED: meaningful feature, not generic progress.
- REAL TESTS: names/counts/pass/failure, and whether remote/Drive calls were actually made.
- LOCATION: real user-facing link only on verified upload.
- REMAINING: one specific next step.
- COMMIT: actual Git SHA/push receipt if authorized and successful; otherwise not pushed.

The goal is a studio that produces film, not a studio that produces explanations of why it cannot deliver film.
