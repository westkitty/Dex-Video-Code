#!/usr/bin/env python3
"""Render a source-grounded, silent SVG explainer locally with ImageMagick + FFmpeg."""
from __future__ import annotations
import html
import json
import math
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRAMES = ROOT / "frames-svg"
OUT = ROOT / "renders"
W, H, FPS = 960, 540, 24
INK, PAPER, TEAL, MUTED, LINE = "#1c3038", "#f3f0e8", "#067f8c", "#61747a", "#d1d0c7"
GOLD, RUST, MINT, NAVY = "#d8a54c", "#b6553c", "#5e998c", "#12232b"
FONT = "/System/Library/Fonts/SFCompact.ttf"
MONO = "/System/Library/Fonts/Menlo.ttc"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def text(x, y, value, size=24, fill=INK, weight=400, family="sans", anchor="start", spacing=None):
    ff = "Menlo" if family == "mono" else "SF Compact"
    ls = f' letter-spacing="{spacing}"' if spacing is not None else ""
    return f'<text x="{x}" y="{y}" font-family="{ff}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}"{ls}>{esc(value)}</text>'


def rect(x, y, w, h, fill="none", stroke=LINE, rx=0, sw=1):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def circle(cx, cy, r, fill, stroke="none", sw=1):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def line(x1, y1, x2, y2, stroke=LINE, sw=1, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<path d="M{x1} {y1} L{x2} {y2}" fill="none" stroke="{stroke}" stroke-width="{sw}"{d}/>'


def base(index, kicker, source, title, subtitle):
    return [
        '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">',
        f'<rect width="960" height="540" fill="{PAPER}"/>',
        # restrained archive registration marks without texture that obscures copy
        f'<path d="M48 85h18 M48 85v18 M912 85h-18 M912 85v18 M48 475h18 M48 475v-18 M912 475h-18 M912 475v-18" fill="none" stroke="{LINE}" stroke-width="1"/>',
        text(52, 38, "DRAXIS  /  ADMINISTRATION MACROCRAFT ARCHIVE", 11, TEAL, 600, "mono", spacing=1.3),
        text(908, 38, f"{index:02d} / 06", 11, MUTED, 400, "mono", "end", 1),
        line(52, 52, 908, 52, LINE),
        text(52, 109, kicker.upper(), 12, TEAL, 600, "mono", spacing=1.1),
        text(52, 153, title, 36, INK, 650),
        text(52, 180, subtitle, 15, MUTED, 400),
        line(52, 493, 908, 493, LINE),
        text(52, 516, source, 10, MUTED, 400, "mono"),
        text(908, 516, "SOURCE EXPLANATION / NOT A CANON UPDATE", 9, MUTED, 400, "mono", "end", .3),
    ]


def scene1():
    s = base(1, "field guide / reading the archive", "SOURCE: PDF AUTHOR'S PREFACE + FIELD PROTOCOL, PP. 2-3", "A catalog of world-changing functions", "The compendium asks what the Drakken do to a world, not only what they look like.")
    # stylized planetary layers, an original diagram rather than source artwork
    s += [circle(730, 335, 132, "#e4d9bf", "#7b887f", 1.5), circle(730, 335, 102, "#91b6a6"), circle(730, 335, 69, "#d8b369"), circle(730, 335, 35, "#bc6748")]
    s += [f'<path d="M598 335 A132 132 0 0 1 862 335" fill="none" stroke="{TEAL}" stroke-width="4"/>',
          f'<path d="M628 272 Q730 220 832 272" fill="none" stroke="{INK}" stroke-width="2" stroke-dasharray="5 7"/>']
    s += [line(626, 335, 554, 335, TEAL, 2), text(545, 329, "CRUST", 10, TEAL, 600, "mono", "end"),
          line(663, 260, 574, 226, TEAL, 2), text(565, 222, "ATMOSPHERE", 10, TEAL, 600, "mono", "end"),
          line(688, 380, 586, 423, TEAL, 2), text(577, 428, "BIOSPHERE", 10, TEAL, 600, "mono", "end")]
    s += [rect(52, 221, 363, 178, "#fbfaf6", LINE, 8), text(76, 258, "THE EDITOR'S LENS", 12, TEAL, 600, "mono", spacing=1),
          text(76, 302, "Taxonomy is not", 27, INK, 600), text(76, 337, "absolution.", 27, INK, 600),
          text(76, 378, "Naming a catastrophe does not undo it.", 14, MUTED)]
    return s + ["</svg>"]


def scene2():
    s = base(2, "105 subjects / four evidence classes", "SOURCE: PDF FIELD PROTOCOL, P. 3; SOURCE GUIDE, CATALOG COUNTS", "The total is not 105 approved strains", "Each category has a different evidence status. The proportions below sum to 105.")
    items = [
        ("DOCUMENTED OPERATIONAL", "001-058", 58, TEAL, "functional strains"),
        ("GENESIS ENTITIES", "059-060", 2, GOLD, "Egg + Mother"),
        ("HISTORICAL PROPOSALS", "061-095", 35, RUST, "not canon-approved"),
        ("CONTEXT PLATES", "096-105", 10, MINT, "not species"),
    ]
    x0, barw = 52, 856
    for i, (label, ids, count, color, note) in enumerate(items):
        y = 217 + i * 65
        s += [text(x0, y, label, 13, INK, 600, "mono", spacing=.35), text(272, y, ids, 12, MUTED, 400, "mono")]
        s += [rect(52, y + 13, barw, 13, "#e1dfd6", "none", 6)]
        width = max(14, barw * count / 105)
        s += [rect(52, y + 13, round(width, 2), 13, color, "none", 6)]
        s += [text(790, y + 12, str(count), 22, color, 700, "mono", "end"), text(908, y + 10, note, 11, MUTED, 400, "mono", "end")]
    s += [line(52, 472, 908, 472, INK, 1.2), text(52, 465, "58 + 2 + 35 + 10", 14, INK, 600, "mono"), text(908, 465, "= 105 NUMBERED SUBJECTS", 13, TEAL, 600, "mono", "end")]
    return s + ["</svg>"]


def scene3():
    s = base(3, "operational records / eight families", "SOURCE: PDF SPECIMEN INDEX, PP. 5-6", "The 58 operational folios span eight families", "The family names organize the record; the index does not make them interchangeable.")
    families = ["CRUST-BINDERS", "ATMOS-ENGINES", "SEEDCARRIERS", "FLUXBORNE", "ORBITAL-WYRMS", "CIVIFORMERS", "NOOSPHERE-CANTORS", "GLITCH-TOUCHED"]
    accents = [RUST, TEAL, MINT, "#4776a0", GOLD, "#806e9e", "#a45465", "#687e82"]
    for i, name in enumerate(families):
        col, row = i % 2, i // 2
        x, y = 52 + col * 438, 216 + row * 62
        color = accents[i]
        s += [rect(x, y - 20, 408, 46, "#fbfaf6", LINE, 5), circle(x + 20, y + 3, 7, color),
              text(x + 42, y + 8, name, 16, INK, 600, "mono", spacing=.2),
              text(x + 389, y + 7, f"FAMILY {i+1:02d}", 9, MUTED, 400, "mono", "end")]
    s += [rect(52, 441, 856, 31, "#e4e8e0", "none", 4), text(70, 462, "FUNCTIONAL GROUPING", 11, TEAL, 600, "mono", spacing=1), text(890, 462, "8 FAMILIES  /  58 OPERATIONAL RECORDS", 11, INK, 500, "mono", "end")]
    return s + ["</svg>"]


def scene4():
    s = base(4, "terraformation / system-level effect", "SOURCE: PDF PREFACE + FIELD PROTOCOL, P. 2", "Read each strain by its effect on a world", "The dossier describes changes to the conditions that let other life survive.")
    # Earth-system cutaway with three layers and two separated states
    s += [rect(52, 218, 385, 218, "#fbfaf6", LINE, 8), rect(523, 218, 385, 218, "#fbfaf6", LINE, 8)]
    s += [text(76, 250, "BEFORE / LOCAL WORLD", 11, MUTED, 600, "mono", spacing=.7), text(547, 250, "AFTER / REWRITTEN CONDITIONS", 11, TEAL, 600, "mono", spacing=.45)]
    # left: quiet coherent planet, right: disrupted ecological rings
    s += [circle(242, 345, 82, "#b8c8b5", "#657d77", 1.5), circle(242, 345, 53, "#d4bc82"), circle(242, 345, 24, "#a97857")]
    s += [f'<path d="M161 345 A81 81 0 0 1 323 345" fill="none" stroke="#8caab0" stroke-width="5"/>',
          f'<path d="M166 326 Q240 288 314 324" fill="none" stroke="{MINT}" stroke-width="3"/>']
    s += [circle(714, 345, 82, "#738c81", "#405956", 1.5), circle(714, 345, 54, "#d9a354"), circle(714, 345, 27, "#a54f3c")]
    s += [f'<path d="M627 347 C651 280 774 282 802 347" fill="none" stroke="{TEAL}" stroke-width="4" stroke-dasharray="5 5"/>',
          f'<path d="M641 377 Q714 421 787 373" fill="none" stroke="{RUST}" stroke-width="5"/>',
          f'<path d="M645 318 Q714 341 785 304" fill="none" stroke="{GOLD}" stroke-width="3"/>']
    s += [line(345, 345, 490, 345, TEAL, 2), text(418, 330, "ECOLOGICAL", 9, TEAL, 600, "mono", "middle", .6), text(418, 362, "FUNCTION", 9, TEAL, 600, "mono", "middle", .6),
          text(80, 418, "CRUST  /  WEATHER  /  LIFE", 10, MUTED, 400, "mono"), text(550, 418, "INSTITUTIONS + ENVIRONMENT", 10, MUTED, 400, "mono")]
    return s + ["</svg>"]


def scene5():
    s = base(5, "blood-eclipse war / corrected chronology", "SOURCE: PDF WAR OVERVIEW, P. 4; SOURCE GUIDE, CORRECTED TIMELINE", "A 170-year war ends in containment", "The chronology explicitly replaces an older 17-year account.")
    x0, x1, y = 94, 866, 327
    s += [line(x0, y, x1, y, INK, 3)]
    marks = [(0, "YEAR 0", "fringe strikes"), (3, "YEAR 3", "first Blood Ring\nFallenstar Prime"), (121, "YEAR 121", "Ruby Eclipse\nPharos Nebula"), (170, "YEAR 170", "Aureal Gate\nfirst Starsilk use")]
    for i, (year, label, caption) in enumerate(marks):
        x = x0 + (x1-x0) * year/170
        color = TEAL if year < 121 else RUST if year == 121 else GOLD
        label_x = 83 if year == 0 else 215 if year == 3 else round(x, 1)
        caption_x = 84 if year == 0 else 217 if year == 3 else round(x, 1)
        caption_anchor = "start" if year == 0 else "middle"
        lines = caption.splitlines()
        s += [line(round(x, 1), y - 18, round(x, 1), y + 18, color, 2), circle(round(x, 1), y, 7, color, PAPER, 2),
              line(round(x, 1), y - 21, label_x, 276, color, 1),
              text(label_x, 265, label, 12, color, 600, "mono", "middle"),
              text(caption_x, 365, lines[0], 11, INK, 500, "mono", caption_anchor)]
        if len(lines) > 1:
            s += [text(caption_x, 384, lines[1], 10, MUTED, 400, "mono", caption_anchor)]
    # consequence follows first successful harm to Tiger
    s += [rect(565, 416, 343, 49, "#eee0d4", "none", 5), text(580, 437, "AFTER: HAL'VEN HELIOCIDE", 11, RUST, 600, "mono"),
          text(580, 455, "stellar-collapse chain -> Siege Wall", 11, INK, 400, "mono")]
    s += [text(52, 462, "THE SIEGE WALL = BLACK-HOLE CONTAINMENT LATTICE", 10, MUTED, 500, "mono")]
    return s + ["</svg>"]


def scene6():
    s = base(6, "evidence / canon boundary", "SOURCE: PDF FIELD PROTOCOL, P. 3; SOURCE GUIDE, AUTHORITY NOTICE", "A catalog entry is not an approval", "The source preserves history while keeping its status labels visible.")
    cards = [
        (52, "35 ARCHIVAL PROPOSALS", "Unapproved historical candidates", RUST),
        (342, "10 CONTEXT PLATES", "Explanatory images, not strains", TEAL),
        (632, "105 IMAGES", "Existence does not prove canonical appearance", GOLD),
    ]
    for x, title, body, color in cards:
        s += [rect(x, 229, 276, 116, "#fbfaf6", LINE, 7), rect(x, 229, 276, 5, color, "none", 2),
              text(x+18, 267, title, 13, color, 600, "mono"), text(x+18, 301, body, 12, INK, 400)]
    s += [line(52, 388, 908, 388, LINE, 1)]
    s += [text(52, 427, "READ THE LABEL. KEEP THE CONTRADICTION VISIBLE.", 20, INK, 600),
          text(52, 458, "This is a source-grounded explanation, not new canon approval.", 14, MUTED)]
    s += [rect(811, 405, 97, 44, "#e1ebe4", "none", 6), text(859, 433, "END / 30s", 10, TEAL, 600, "mono", "middle")]
    return s + ["</svg>"]


SCENES = [scene1, scene2, scene3, scene4, scene5, scene6]


def run(args):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(map(str, args))}\n{p.stderr[-3000:]}")
    return p.stdout


def main():
    for cmd in ("magick", "ffmpeg", "ffprobe"):
        if shutil.which(cmd) is None:
            raise SystemExit(f"Required local executable is unavailable: {cmd}")
    for path in (FONT, MONO):
        if not Path(path).is_file():
            raise SystemExit(f"Required local font is unavailable: {path}")
    FRAMES.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    pngs = []
    for i, make in enumerate(SCENES, 1):
        svg = FRAMES / f"scene-{i:02d}.svg"
        png = OUT / f"scene-{i:02d}.png"
        svg.write_text("\n".join(make()) + "\n", encoding="utf-8")
        run(["magick", "-font", FONT, str(svg), "-depth", "8", str(png)])
        pngs.append(png)
    # Six 130-frame holds with five 12-frame crossfades produce exactly 720 frames.
    inputs = []
    for png in pngs:
        inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(png)]
    graph = []
    for i in range(len(pngs)):
        graph.append(f"[{i}:v]scale={W}:{H},setsar=1,fps={FPS},trim=duration=5.4166667,setpts=PTS-STARTPTS[v{i}]")
    last = "v0"
    for i in range(1, len(pngs)):
        out = f"x{i}"
        offset = (130 * i - 12 * (i-1)) / FPS - 0.5
        graph.append(f"[{last}][v{i}]xfade=transition=fade:duration=0.5:offset={offset:.6f}[{out}]")
        last = out
    graph.append(f"[{last}]trim=end_frame=720,setpts=PTS-STARTPTS,format=yuv420p[outv]")
    video = OUT / "drakken-compendium-explainer-30s.mp4"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
         "-filter_complex", ";".join(graph), "-map", "[outv]", "-an", "-c:v", "libx264",
         "-preset", "medium", "-crf", "19", "-movflags", "+faststart", "-t", "30", str(video)])
    probe = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)]))
    stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None)
    if not stream or stream.get("codec_name") != "h264" or stream.get("width") != W or stream.get("height") != H:
        raise SystemExit("Encoded video failed basic stream validation.")
    if abs(float(probe["format"]["duration"]) - 30) > 0.03 or any(s.get("codec_type") in ("audio", "subtitle") for s in probe.get("streams", [])):
        raise SystemExit("Encoded video failed duration/audio/subtitle validation.")
    print(json.dumps({"video": str(video), "bytes": video.stat().st_size, "duration_seconds": probe["format"]["duration"], "streams": [(s["codec_type"], s.get("codec_name")) for s in probe["streams"]], "frame_rate": stream.get("r_frame_rate"), "frame_count": stream.get("nb_frames"), "scenes": len(SCENES)}, indent=2))


if __name__ == "__main__":
    main()
