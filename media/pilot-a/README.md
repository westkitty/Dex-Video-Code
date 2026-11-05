# Pilot A — A Small Signal

An original 20-second silent motion-design piece about a signal finding another point in the dark. The sequence is made from authored HTML, CSS and SVG; it uses no external media, generated voice, subtitles, captions, cloud services or 3D rig.

The editable composition is `index.html`. Its only runtime dependency is GSAP from the existing local HyperFrames installation; do not fetch a copy from a CDN. The source does not include the installed renderer or its dependency. To reproduce, copy this project into the discovered controller's `runs/` directory, place the already-installed local GSAP file in its `assets/` directory as a regular file (the HyperFrames server refused a symlink), then use only the documented controller `submit <project-slug> delivery` operation. Do not run unreviewed shell input.

Planned beats: first pulse (0–5s), path through the field (5–14s), distant answer (14–17s), linked payoff (17–20s). Designed title/copy is part of the composition, not captions. Silence is intentional.

The verified local encode is described in `receipt.json`; `shot-manifest.json` records the brief and beat map. The MP4 and contact sheet are intentionally ignored Git outputs. Artistic acceptance remains separate from technical verification.
