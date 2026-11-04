# Operational state

Updated 2026-11-04. This file records observed facts for this checkout; capabilities and remote states can change.

## Repair milestone

- Target checkout `Dex-Video-Code` under the verified authorized workspace, branch `main`; repair began from HEAD `7e71d9808122e1aa684a60f3913f185eeb537409`, clean and tracking `origin/main` at inspection.
- Confirmed the three audit prompts had all been routed to the same 16-second signal animation. The v1.1 interpreter now preserves their requested durations, deliverable/subject/action/technique and restrictions and explicitly blocks unsupported illustrated narrative, audio-only and articulated 3D work.
- Local renderer now consumes the validated geometric plan, supports silent 1280×720/24 fps H.264 MP4 for 1–30 seconds, and writes to an atomic no-replace destination with a per-job process lock. It removes temporary frames after rendering.
- A 1-second no-text shape transformation was produced in an isolated temporary directory. `ffprobe` read 1.000 seconds, 1280×720 and 24 fps; full decode and the spec check reported `TECHNICAL_PASS_VISUAL_PENDING`. A frame was inspected. Artistic acceptance remains pending.
- Fresh validation after the renderer correction: TypeScript build and `npm test` passed 23/23. The documented nested `plan --out` flow, no-overwrite behavior, v1 migration, path/symlink gate (including refusal before creating outside directories), approval rejection, unsupported-route handling, no-clobber race, failed-job resume, and media metadata checks are covered.
- Final bounded 1-second production smoke: H.264 MP4, 1280×720, 24 fps, 1.000 seconds, silent, no subtitle stream; full decode and SHA-256/spec verification passed as `TECHNICAL_PASS_VISUAL_PENDING` (SHA-256 `daa1cbcc56b39179453737b8f609a478d06f75dd08b729572c4a9416a7ec7432`). A frame extracted from the encoded MP4 was inspected after the background rasterization fix. This is a renderer smoke, not a finished film or artistic approval.
- Existing recorded 16-second pilot SHA `ac7232df261ddf5a0313ab4b101d9dfd149b639adea8089db4c62ec4bad519fe` is historical proof for the earlier renderer, not proof of this changed renderer.
- Audio, still image, narrative illustration/character motion and articulated 3D remain blocked. No spend, cloud, uploads, private assets, voice/identity generation or subtitles were used.

## Integration status

- The source repo alone is not a registered ChatGPT tool. `PROJECT_ACTIVATION_PENDING` remains until the owner installs the existing Project instructions and independently verifies settings/access.
- GitHub connector listed `westkitty/Dex-Video-Code` as private and permitted source access. DEX//REACH listed `macbook-air.local` online, `aiAccess=on`, but the exact `start_process` invocation for read-only CLI `doctor --json` returned `COORDINATOR_WAIT_TIMEOUT: substantive slots exhausted (2/1, including 2 uncoordinated heavy workload(s))`. No successful remote CLI handshake occurred. Status `BLOCKED_BRIDGE`; retry after the scheduler admits a bounded task.

## Remaining original studio gates

- Phases 04 and 06–09 remain partial/not complete: asset-rights intake, audio and specialist routes, distinct production pilots, and human creative acceptance are not implemented or verified. This repair does not turn the coordinator into a finished studio.
- The repair passed diff/privacy review, was committed and pushed to private `origin/main`, and the remote ref readback matched local `main`. The working tree was clean immediately after publication. The current Git history is the source for the exact publication SHA.
