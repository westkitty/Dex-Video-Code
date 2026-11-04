# Operational state

Updated 2026-11-04. This file records observed state for this checkout; observations age and are not claims of future availability.

## Current milestone

- Phase 00: PARTIAL. Authorized host was MacBook-Air.local / `andrew`, arm64, Node v26.13.0, FFmpeg 9.0.2, 8 GiB RAM. Local free disk was about 10 GiB at initial probe. DEX//REACH reported a MacBook memory warning and an online, idle/healthy Big Mac; values are transient.
- Selected local clones `Image_Gen` (`8b7091d`), `StinkweaselArts` (`aa369e4`), and `Code_Video` (`44ec628`) were clean on `main` at inspection. Read relevant README/operator state directly. No other Westkitty repository was changed.
- Phase 00B: PASS. Isolated project Git root created at `Dex-Video-Code/`, branch `main`; exact new GitHub target is private `https://github.com/westkitty/Dex-Video-Code`.
- Phases 01–03: PASS for initial local slice: versioned CreativeJob schema, bounded route selection, six CLI operations, read-only capability probes, path/adapter gates, symlink confinement and regression tests. Failed job `dv_mw2k8ccp-z7k31yag` resumed after the SVG-decoder failure, then passed encoding and verification (`attempts=2`).
- Phase 04: PARTIAL. Rights/provenance schema exists; no imported private/user assets. Pilot uses original authored SVGs.
- Phase 05: TECHNICAL PASS / VISUAL PENDING. Original motion-graphics pilot is 16.000 seconds, 1280×720, 24 fps, H.264, silent, no subtitle track. Full decode passed; recorded SHA-256: `ac7232df261ddf5a0313ab4b101d9dfd149b639adea8089db4c62ec4bad519fe`. Local output is `examples/jobs/pilot-a-reviewed/outputs/dv_mw2kewjt-bdfxdmy8/master.mp4`; pack is adjacent under `handoff-dv_mw2kewjt-bdfxdmy8/`. Five encoded frames were visually inspected; human artistic acceptance remains pending.
- Phases 06–09: NOT COMPLETE. Illustrated/source import, audio, specialist adapters, three distinct pilots, and broader artistic acceptance remain open.
- Phase 10: Git commit/push pending. Project settings/user activation pending.

## Capability evidence

- `director doctor --json` observed the host at runtime, Node, FFmpeg, ffprobe and native frame rasterizer; it marks HyperFrames and Remotion `AVAILABLE_UNPROVEN`, Blender specialist route `DORMANT`, and ComfyUI `EXCLUDED`.
- MacBook DEX//REACH node was online with `aiAccess=on`. Its `read_file` tool successfully read the local README. Its `start_process` call for CLI `doctor --json` was refused because the single substantive slot was full with an uncoordinated heavy workload (`COORDINATOR_WAIT_TIMEOUT`); current CLI execution state `BLOCKED_BRIDGE`.
- Project settings and private GitHub connector access from inside the `code video` Project are not changed/proved by this checkout. Status `PROJECT_ACTIVATION_PENDING`.
- No audio, generated voices, captions, private references, credentials, model weights, or outputs are included in source control.

## Next bounded work

Repeat only the read-only bridge `doctor` after the MacBook DEX//REACH scheduler admits a task, then finish staged source review, commit/push the private repository, and compare local HEAD to remote `main`. User must install the Project instructions and confirm private GitHub access for activation.
