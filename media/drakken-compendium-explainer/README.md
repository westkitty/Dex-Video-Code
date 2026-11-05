# Drakken Terraforming Compendium — programmatic explainer

A 30-second, silent, 16:9 explanation of the attached illustrated edition. The editable source is `generate.py`; `storyboard.json` records the source-grounded claims, timing, and motion. Version 2 adds actual movement and sequential reveals, keeps figures accurate at every point in the count scene, and fixes the transformed-world colors and label contrast found during visual review. The script creates original vector diagrams and encodes them locally with ImageMagick and FFmpeg. It does not use the archive's embedded image-generation instructions, extract or reuse its artwork, make network calls, add voice/music, or enable subtitles.

## Rebuild

From the repository root on this Mac:

```sh
python3 media/drakken-compendium-explainer/generate.py
```

Requires Python 3, ImageMagick (`magick`), FFmpeg (`ffmpeg` and `ffprobe`), and the installed macOS fonts named in the script. The generated MP4, PNG frames, SVG frames and contact sheets are local ignored outputs under `renders/`, `frames-png/` and `frames-svg/`; they are excluded from Git. `receipt.json` records the current verified delivery artifact.

## Editorial scope

The video explains how to read the catalog, how its 105 numbered subjects are classified, why the Drakken are described by terraforming function, and the corrected 170-year war anchors. It does not summarize all 58 folios or settle canon. The compendium labels itself a working source dossier, and the guide calls itself source consolidation rather than new canon approval.

On-screen text is part of the designed graphic sequence, not subtitles. Audio is intentionally absent. Historical S1 proposals remain clearly marked unapproved, and illustration existence is not presented as proof of canonical appearance.
