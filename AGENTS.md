# Dex Video Code repository rules

- This file governs only this repository.
- Keep creative route choice medium-agnostic; 3D rig requirements apply only to explicit articulated 3D work.
- ComfyUI / Comfort UI is excluded. Do not add or recommend an adapter.
- Do not commit credentials, private references, original user media, model weights, generated pilot outputs, or local run state.
- Do not publish or modify other repositories. Keep project sources and existing Westkitty systems read-only.
- No unapproved spend, public service, upload, voice/identity generation or destructive cleanup.
- Captions and subtitles are off by default. Preserve supplied text and audio exactly.
- A probe, test, successful encode, Git push and artistic acceptance are distinct evidence states.
- New adapters must use argument arrays, explicit input/output declarations, bounded timeouts, path confinement and a current capability probe.

## Studio V2 implementation instructions

- Read docs/STUDIO_V2_MASTER_PLAN.md, docs/STUDIO_V2_IMPLEMENTATION_BACKLOG.md, docs/STUDIO_V2_VALIDATION_CONTRACT.md, and docs/STUDIO_V2_CODEX_START.md when implementing Studio V2; use current source/tests and OPERATIONAL_STATE.md as evidence of what actually exists.
- Delivery to a private user-authorized storage folder is required for final "delivered" status; a local encode, metadata-only upload or transcoded proxy does not prove the original master was delivered. Only user review can grant artistic approval.
- Prioritize P0 factual/security baseline and bounded P1 upload/verification before adding more renderers. Preserve existing legacy jobs, safe paths, locks, no-clobber outputs, schema compatibility and the exclusion of ComfyUI.
- No plan grants blanket authority for future execution, remote access, provider credentials, repository permissions, spending, public sharing or other-repo writes. Recheck current authorization and capabilities.
- A historical plan or GitHub push does not prove Studio V2 implementation. Add tests and receipts for actual changed behavior and append OPERATIONAL_STATE.md after meaningful completed units.
