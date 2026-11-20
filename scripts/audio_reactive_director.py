#!/usr/bin/env python3
"""Audio-reactive 3D music video director for Blender 5.2+ & DEX//SCULPT assets.

Analyzes any audio track via FFmpeg PCM + pure-Python FFT into per-frame energy,
3-band envelopes (bass/mid/high), spectral onset flux, and 16 logarithmic equalizer
bands; stages verified catalog characters onto a remote Blender host; builds an
animated .blend scene; supports a 9-shot storyboard QQQ gate before launching a
2-worker parallel streaming chunk render (<=48 frames per batch with immediate segment
encoding + PNG cleanup); muxes stereo AAC audio with explicit stream mapping; runs
FFprobe + full decode + Frame QA checks; pulls outputs via multiplexed strict SCP;
and optionally syncs to Google Drive.
"""

from __future__ import annotations

import argparse
import array
import cmath
import hashlib
import json
import math
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import dexsculpt_catalog as dc  # noqa: E402
from frame_qa_gate import evaluate_media_paths  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent
DEFAULT_BUILDER = REPO_ROOT / "examples" / "p7" / "midnight_clockwork_swing_builder.py"
MAX_CHUNK_FRAMES = 48

CAST_PRESETS: dict[str, list[str]] = {
    "band": [
        "kaykit-adventurers/character/mage",
        "kaykit-adventurers/character/barbarian",
        "kaykit-adventurers/character/rogue",
        "kaykit-adventurers/character/knight",
    ],
    "heist": [
        "kaykit-adventurers/character/mage",
        "kaykit-adventurers/character/barbarian",
        "kaykit-adventurers/character/rogue",
        "kaykit-adventurers/character/rogue_hooded",
        "kaykit-adventurers/character/knight",
        "kaykit-adventurers/character/ranger",
        "kaykit-adventurers/accessory/sword_1handed",
        "kaykit-adventurers/accessory/shield_round",
        "kaykit-adventurers/accessory/axe_1handed",
        "kaykit-adventurers/animation_pack/rig_medium_movementbasic",
        "kaykit-adventurers/animation_pack/rig_medium_general",
    ],
}


def resolve_cast_preset(preset: str) -> list[str]:
    """Return the verified catalog asset IDs for a named music-video cast preset."""
    key = preset.strip().lower()
    if key not in CAST_PRESETS:
        raise ValueError(f"Unsupported cast preset {preset!r}; choose from {sorted(CAST_PRESETS)}")
    return list(CAST_PRESETS[key])


def parse_storyboard_frames(raw: str | None, *, total_frames: int) -> list[int]:
    """Parse 9 comma-separated frame numbers clamped cleanly to 1..total_frames."""
    if not raw:
        defaults = [60, 240, 355, 480, 710, 850, 1060, 1165, 1320]
    else:
        defaults = [int(part.strip()) for part in raw.split(",") if part.strip()]
        if len(defaults) != 9:
            raise ValueError(f"--storyboard-frames must specify exactly 9 integers, got {len(defaults)}")
    return [max(1, min(total_frames, f)) for f in defaults]


def _resolve_ffmpeg_tools() -> tuple[str, str]:
    ffmpeg_bin = "ffmpeg"
    ffprobe_bin = "ffprobe"
    for cand in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if Path(cand).is_file():
            ffmpeg_bin = cand
            break
    for cand in ("/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe"):
        if Path(cand).is_file():
            ffprobe_bin = cand
            break
    return ffmpeg_bin, ffprobe_bin


def _radix2_fft(values: list[complex | float]) -> list[complex]:
    """Pure-Python Cooley-Tukey radix-2 FFT (requires power-of-two length)."""
    n = len(values)
    if n <= 1:
        return [complex(v) for v in values]
    even = _radix2_fft(values[0::2])
    odd = _radix2_fft(values[1::2])
    factor = -2j * math.pi / n
    out = [0j] * n
    half = n // 2
    for k in range(half):
        t = cmath.exp(factor * k) * odd[k]
        out[k] = even[k] + t
        out[k + half] = even[k] - t
    return out


def analyze_audio_track(audio_path: Path, *, fps: int = 24) -> dict[str, Any]:
    """Extract per-frame RMS, bass/mid/high bands, onset flux, 16-band EQ, and BPM."""
    src = Path(audio_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Audio track not found: {src}")
    if fps <= 0 or fps > 120:
        raise ValueError(f"Unsupported fps: {fps}")

    ffmpeg_bin, ffprobe_bin = _resolve_ffmpeg_tools()
    probe = json.loads(
        subprocess.check_output(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-show_entries",
                "format=duration,bit_rate,size:stream=codec_name,sample_rate,channels",
                "-of",
                "json",
                str(src),
            ],
            text=True,
            timeout=30,
        )
    )
    duration = float(probe["format"]["duration"])
    if duration <= 0.0:
        raise ValueError(f"Invalid audio duration: {duration}")

    sample_rate = 22050
    raw_pcm = subprocess.check_output(
        [
            ffmpeg_bin,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "s16le",
            "-",
        ],
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    pcm = array.array("h")
    pcm.frombytes(raw_pcm)
    if sys.byteorder == "big":
        pcm.byteswap()
    num_samples = len(pcm)
    total_frames = max(1, int(round(duration * fps)))

    win = 1024
    hann = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / (win - 1)) for i in range(win)]
    # 16 logarithmically spaced FFT bin ranges across 43 Hz .. 9,500 Hz (~21.53 Hz/bin)
    log_edges_hz = [43.0 * ((9500.0 / 43.0) ** (i / 16.0)) for i in range(17)]
    hz_per_bin = sample_rate / float(win)
    band_bins: list[tuple[int, int]] = []
    for i in range(16):
        b0 = max(1, int(round(log_edges_hz[i] / hz_per_bin)))
        b1 = max(b0 + 1, int(round(log_edges_hz[i + 1] / hz_per_bin)))
        band_bins.append((min(b0, win // 2 - 2), min(b1, win // 2 - 1)))

    raw_frames: list[dict[str, Any]] = []
    prev_mag: list[float] | None = None
    max_rms = 1e-6
    max_bass = 1e-6
    max_mid = 1e-6
    max_high = 1e-6
    max_flux = 1e-6
    band_peaks = [1e-6] * 16

    for frame_idx in range(total_frames):
        center = int((frame_idx + 0.5) * sample_rate / float(fps))
        s0 = max(0, min(max(0, num_samples - win), center - win // 2))
        seg = [(pcm[s0 + i] / 32768.0) if (s0 + i) < num_samples else 0.0 for i in range(win)]
        rms = math.sqrt(sum(v * v for v in seg) / float(win))
        spec = _radix2_fft([seg[i] * hann[i] for i in range(win)])[: win // 2]
        mag = [abs(z) / float(win) for z in spec]

        bass = sum(mag[1:8]) / 7.0
        mid = sum(mag[12:95]) / 83.0
        high = sum(mag[116:480]) / 364.0
        flux = 0.0 if prev_mag is None else sum(max(0.0, mag[k] - prev_mag[k]) for k in range(1, 256))
        prev_mag = mag

        bands = [sum(mag[b0:b1]) / float(max(1, b1 - b0)) for b0, b1 in band_bins]
        max_rms = max(max_rms, rms)
        max_bass = max(max_bass, bass)
        max_mid = max(max_mid, mid)
        max_high = max(max_high, high)
        max_flux = max(max_flux, flux)
        for bi in range(16):
            band_peaks[bi] = max(band_peaks[bi], bands[bi])

        raw_frames.append({"rms": rms, "bass": bass, "mid": mid, "high": high, "flux": flux, "bands": bands})

    # Normalize & smooth equalizer bands with fast attack and 0.72 release
    smooth_bands = [0.0] * 16
    norm_frames: list[dict[str, Any]] = []
    impact_raw_list: list[float] = []
    max_impact_raw = 1e-6
    prev_rn = 0.0
    prev_bn = 0.0
    for f_idx, rf in enumerate(raw_frames):
        r_n = min(1.0, rf["rms"] / max_rms)
        b_n = min(1.0, rf["bass"] / max_bass)
        m_n = min(1.0, rf["mid"] / max_mid)
        h_n = min(1.0, rf["high"] / max_high)
        fl_n = min(1.0, rf["flux"] / max_flux)

        imp_raw = fl_n * 1.4 + max(0.0, r_n - prev_rn) * 1.5 + max(0.0, b_n - prev_bn) * 1.8
        prev_rn = r_n
        prev_bn = b_n
        max_impact_raw = max(max_impact_raw, imp_raw)
        impact_raw_list.append(imp_raw)

        cur_b16 = []
        for bi in range(16):
            val = min(1.0, rf["bands"][bi] / band_peaks[bi])
            # Gentle perceptual lift so high bands stay expressive alongside heavy bass
            val = val ** 0.65
            if val >= smooth_bands[bi]:
                smooth_bands[bi] = val
            else:
                smooth_bands[bi] = smooth_bands[bi] * 0.72 + val * 0.28
            cur_b16.append(round(smooth_bands[bi], 4))

        norm_frames.append(
            {
                "f": f_idx + 1,
                "t": round(f_idx / float(fps), 4),
                "rms": round(r_n, 4),
                "bass": round(b_n, 4),
                "mid": round(m_n, 4),
                "high": round(h_n, 4),
                "flux": round(fl_n, 4),
                "b16": cur_b16,
            }
        )

    # High-resolution (~200 Hz, ~5ms hop) onset envelope for sub-frame BPM & phase lock
    best_bpm = 128.0
    best_offset_s = 0.0
    hop = 110
    win_hp = 512
    n_hops = max(0, (num_samples - win_hp) // hop)
    if duration >= 2.0 and n_hops >= 80:
        hop_hz = sample_rate / float(hop)
        alpha_low = (2.0 * math.pi * 160.0) / (2.0 * math.pi * 160.0 + sample_rate)
        cs_f = [0.0] * (num_samples + 1)
        cs_l = [0.0] * (num_samples + 1)
        cs_h = [0.0] * (num_samples + 1)
        prev_lp = 0.0
        for idx_s, raw_s in enumerate(pcm):
            x = raw_s / 32768.0
            prev_lp += alpha_low * (x - prev_lp)
            hi = x - prev_lp
            cs_f[idx_s + 1] = cs_f[idx_s] + x * x
            cs_l[idx_s + 1] = cs_l[idx_s] + prev_lp * prev_lp
            cs_h[idx_s + 1] = cs_h[idx_s] + hi * hi

        inv_w = 1.0 / float(win_hp)
        full_e = [math.sqrt(max(0.0, cs_f[h * hop + win_hp] - cs_f[h * hop]) * inv_w) for h in range(n_hops)]
        low_e = [math.sqrt(max(0.0, cs_l[h * hop + win_hp] - cs_l[h * hop]) * inv_w) for h in range(n_hops)]
        hi_e = [math.sqrt(max(0.0, cs_h[h * hop + win_hp] - cs_h[h * hop]) * inv_w) for h in range(n_hops)]

        onset_hp = [0.0] * n_hops
        for i in range(1, n_hops):
            df = max(0.0, full_e[i] - full_e[i - 1])
            dl = max(0.0, low_e[i] - low_e[i - 1])
            dh = max(0.0, hi_e[i] - hi_e[i - 1])
            onset_hp[i] = dl * 2.5 + df * 1.2 + dh * 0.6

        # Coarse comb/autocorrelation scan from 80.0 to 170.0 BPM in 0.2 BPM steps
        coarse_best_bpm = 128.0
        coarse_best_score = -1.0
        for bpm10 in range(800, 1702, 2):
            bpm_c = bpm10 / 10.0
            period_h = hop_hz * 60.0 / bpm_c
            sc = 0.0
            for mult, w in ((1, 1.0), (2, 1.0), (4, 0.8), (8, 0.5)):
                lag = int(round(period_h * mult))
                if lag < n_hops:
                    acc = sum(onset_hp[i] * onset_hp[i + lag] for i in range(0, n_hops - lag, 2))
                    sc += w * acc / max(1.0, (n_hops - lag) * 0.5)
            if sc > coarse_best_score:
                coarse_best_score = sc
                coarse_best_bpm = bpm_c

        # Fine comb + 48-bin phase lock around coarse winner (±1.0 BPM in 0.02 BPM steps)
        fine_best_score = -1.0
        fine_best_bpm = coarse_best_bpm
        fine_best_offset_s = 0.0
        for step in range(-50, 51):
            bpm_f = round(coarse_best_bpm + step * 0.02, 2)
            if not 60.0 <= bpm_f <= 200.0:
                continue
            period_h = hop_hz * 60.0 / bpm_f
            n_ph = 48
            best_ph_sc = -1.0
            best_ph_s = 0.0
            for p_idx in range(n_ph):
                ph_h = (p_idx / float(n_ph)) * period_h
                pos = ph_h
                acc = 0.0
                cnt = 0
                while pos < n_hops - 2:
                    ii = int(round(pos))
                    lo_i = max(0, ii - 2)
                    hi_i = min(n_hops, ii + 3)
                    acc += max(onset_hp[lo_i:hi_i])
                    cnt += 1
                    pos += period_h
                ph_sc = acc / float(max(1, cnt))
                if ph_sc > best_ph_sc:
                    best_ph_sc = ph_sc
                    best_ph_s = ph_h / hop_hz
            if best_ph_sc > fine_best_score:
                fine_best_score = best_ph_sc
                fine_best_bpm = bpm_f
                fine_best_offset_s = best_ph_s

        best_bpm = round(fine_best_bpm, 2)
        best_offset_s = round(fine_best_offset_s, 4)

    beat_period_s = 60.0 / max(1.0, best_bpm)
    beat_frame_set: set[int] = set()
    k_idx = 0
    while True:
        t_beat = best_offset_s + k_idx * beat_period_s
        if t_beat > duration + 0.5 / float(fps):
            break
        bf = int(round(t_beat * fps)) + 1
        if 1 <= bf <= total_frames:
            beat_frame_set.add(bf)
        k_idx += 1
    beat_frames = sorted(beat_frame_set)

    frames_out: list[dict[str, Any]] = []
    norm_impacts: list[float] = []
    for idx_f, nf in enumerate(norm_frames):
        f_num = nf["f"]
        t_cur = idx_f / float(fps)
        b_phase = ((t_cur - best_offset_s) / beat_period_s) % 1.0
        b_pulse = math.exp(-6.5 * b_phase)
        imp_norm = min(1.0, impact_raw_list[idx_f] / max_impact_raw)
        norm_impacts.append(imp_norm)
        nf_out = {
            **nf,
            "beat_phase": round(b_phase, 4),
            "beat_pulse": round(b_pulse, 4),
            "is_beat": f_num in beat_frame_set,
            "impact": round(imp_norm, 4),
        }
        frames_out.append(nf_out)

    # Top 36 local-maximum impact frames with at least 8 frames separation
    local_peaks: list[tuple[float, int]] = []
    for idx_f in range(total_frames):
        left = norm_impacts[idx_f - 1] if idx_f > 0 else -1.0
        right = norm_impacts[idx_f + 1] if idx_f + 1 < total_frames else -1.0
        if norm_impacts[idx_f] > left and norm_impacts[idx_f] >= right and norm_impacts[idx_f] > 0.0:
            local_peaks.append((norm_impacts[idx_f], idx_f + 1))
    local_peaks.sort(reverse=True)
    selected_impacts: list[int] = []
    for _, f_num in local_peaks:
        if all(abs(f_num - prev_f) >= 8 for prev_f in selected_impacts):
            selected_impacts.append(f_num)
        if len(selected_impacts) >= 36:
            break
    selected_impacts.sort()
    impact_frames = [
        {"f": f_num, "t": frames_out[f_num - 1]["t"], "impact": frames_out[f_num - 1]["impact"]}
        for f_num in selected_impacts
    ]

    return {
        "schema_version": "audio-reactive-analysis.v1",
        "fps": fps,
        "duration": round(duration, 4),
        "total_frames": total_frames,
        "estimated_bpm": best_bpm,
        "beat_offset_s": best_offset_s,
        "beat_frames": beat_frames,
        "impact_frames": impact_frames,
        "frames": frames_out,
    }


def partition_chunks(start_frame: int, end_frame: int, *, max_chunk: int = MAX_CHUNK_FRAMES) -> list[tuple[int, int]]:
    """Split an inclusive frame interval into bounded chunks of <= max_chunk frames."""
    if start_frame < 1 or end_frame < start_frame:
        raise ValueError(f"Invalid frame range: {start_frame}..{end_frame}")
    if not 1 <= max_chunk <= MAX_CHUNK_FRAMES:
        raise ValueError(f"max_chunk must be between 1 and {MAX_CHUNK_FRAMES}")
    chunks: list[tuple[int, int]] = []
    cur = start_frame
    while cur <= end_frame:
        nxt = min(end_frame, cur + max_chunk - 1)
        chunks.append((cur, nxt))
        cur = nxt + 1
    return chunks


def _scp_upload(local_path: Path, host: str, remote_path: str, timeout: int = 120) -> None:
    subprocess.run(
        ["scp", "-p", *dc.SSH_OPTS, str(local_path), f"{host}:{remote_path}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


REMOTE_PREPARE_DIR = r"""import json, os, shutil, sys
out_dir = os.path.abspath(os.path.expanduser(sys.argv[1]))
min_free = float(sys.argv[2])
free_gib = shutil.disk_usage("/").free / (1024 ** 3)
if free_gib < min_free:
    raise SystemExit(f"Insufficient disk on remote host: {free_gib:.2f} GiB < {min_free:.2f} GiB")
os.makedirs(out_dir, exist_ok=True)
print(json.dumps({"out_dir": out_dir, "free_gib": round(free_gib, 3)}))
"""


REMOTE_STORYBOARD_DRIVER = r"""import hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path

cfg = json.loads(sys.argv[1])
BLENDER_BIN = "/Applications/Blender.app/Contents/MacOS/Blender"
FFMPEG_BIN = "/opt/homebrew/bin/ffmpeg"

out_dir = Path(cfg["out_dir"]).expanduser().resolve()
blend_path = Path(cfg["blend_path"]).expanduser().resolve()
if not blend_path.is_file():
    raise SystemExit(f"Missing blend file: {blend_path}")

tmp_dir = out_dir / "_storyboard_tmp"
if tmp_dir.exists():
    shutil.rmtree(tmp_dir)
tmp_dir.mkdir(parents=True, exist_ok=True)

frames = [int(f) for f in cfg["frames"]]
blender_py = r'''
import bpy, json, os, sys, time
argv = sys.argv[sys.argv.index("--") + 1:]
sc = json.loads(argv[0])
scene = bpy.context.scene
scene.render.resolution_x = int(sc["width"])
scene.render.resolution_y = int(sc["height"])
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.color_depth = "8"
timings = []
for idx, f in enumerate(sc["frames"]):
    t0 = time.monotonic()
    scene.frame_set(f)
    scene.render.filepath = os.path.join(sc["tmp_dir"], f"shot_{idx:02d}_f{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    timings.append(round(time.monotonic() - t0, 3))
print("STORYBOARD_TIMINGS:" + json.dumps({
    "timings_s": timings,
    "warm_avg_s": round(sum(timings[1:]) / max(1, len(timings) - 1), 3),
}))
'''
proc = subprocess.run(
    [BLENDER_BIN, "--background", str(blend_path), "--python-expr", blender_py, "--", json.dumps({
        "frames": frames,
        "tmp_dir": str(tmp_dir),
        "width": cfg["width"],
        "height": cfg["height"],
    })],
    check=True,
    capture_output=True,
    text=True,
    timeout=600,
)
timings_info = None
for line in proc.stdout.splitlines():
    if line.startswith("STORYBOARD_TIMINGS:"):
        timings_info = json.loads(line.split("STORYBOARD_TIMINGS:", 1)[1])

sheet_out = out_dir / "storyboard_3x3.png"
if sheet_out.exists():
    sheet_out.unlink()
subprocess.run(
    [
        FFMPEG_BIN, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-pattern_type", "glob", "-i", str(tmp_dir / "shot_*.png"),
        "-vf", "scale=480:-1,tile=3x3:padding=6:margin=6:color=0x0b0e17",
        "-frames:v", "1", str(sheet_out),
    ],
    stdin=subprocess.DEVNULL,
    check=True,
    timeout=60,
)
shutil.rmtree(tmp_dir)

def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blk)
    return h.hexdigest()

manifest = {
    "schema_version": "music-video-storyboard-manifest.v1",
    "scene_name": cfg["scene_name"],
    "timings": timings_info,
    "disk_free_gib_after": round(shutil.disk_usage("/").free / (1024 ** 3), 3),
    "artifacts": {
        "storyboard_3x3": {
            "path": str(sheet_out),
            "filename": sheet_out.name,
            "bytes": sheet_out.stat().st_size,
            "sha256": sha256_path(sheet_out),
        }
    },
}
mpath = out_dir / "storyboard_manifest.json"
mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"manifest_path": str(mpath), **manifest}, indent=2))
"""


REMOTE_PARALLEL_RENDER_DRIVER = r"""import concurrent.futures, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path

cfg = json.loads(sys.argv[1])
BLENDER_BIN = "/Applications/Blender.app/Contents/MacOS/Blender"
FFMPEG_BIN = "/opt/homebrew/bin/ffmpeg"
FFPROBE_BIN = "/opt/homebrew/bin/ffprobe"

out_dir = Path(cfg["out_dir"]).expanduser().resolve()
blend_path = Path(cfg["blend_path"]).expanduser().resolve()
audio_path = Path(cfg["audio_path"]).expanduser().resolve()
if not blend_path.is_file() or not audio_path.is_file():
    raise SystemExit("Missing blend or audio file on remote host")

free_gib = shutil.disk_usage("/").free / (1024 ** 3)
if free_gib < cfg.get("min_remote_free_gib", 1.5):
    raise SystemExit(f"Insufficient remote free disk before render: {free_gib:.2f} GiB")

segments_dir = out_dir / "_segments"
if segments_dir.exists():
    shutil.rmtree(segments_dir)
segments_dir.mkdir(parents=True, exist_ok=True)

chunks = cfg["chunks"]
threads_per_worker = int(cfg.get("threads_per_worker", 4))
width = int(cfg["width"])
height = int(cfg["height"])

worker_py = r'''
import bpy, json, os, sys
argv = sys.argv[sys.argv.index("--") + 1:]
wc = json.loads(argv[0])
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.threads_mode = "FIXED"
scene.render.threads = int(wc["threads"])
scene.render.fps = 24
scene.render.resolution_x = int(wc["width"])
scene.render.resolution_y = int(wc["height"])
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.color_depth = "8"
scene.frame_start = int(wc["start"])
scene.frame_end = int(wc["end"])
scene.render.filepath = os.path.join(wc["frames_dir"], "frame_####.png")
bpy.ops.render.render(animation=True)
'''

def run_chunk(item):
    idx, (s_f, e_f) = item
    f_dir = segments_dir / f"chunk_{idx:03d}"
    seg_mp4 = segments_dir / f"seg_{idx:03d}.mp4"
    f_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    subprocess.run(
        [
            BLENDER_BIN, "--background", str(blend_path),
            "--python-expr", worker_py, "--",
            json.dumps({"start": s_f, "end": e_f, "width": width, "height": height, "threads": threads_per_worker, "frames_dir": str(f_dir)}),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=900,
    )
    count = e_f - s_f + 1
    subprocess.run(
        [
            FFMPEG_BIN, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-y",
            "-framerate", "24", "-start_number", str(s_f),
            "-i", str(f_dir / "frame_%04d.png"),
            "-frames:v", str(count),
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
            "-threads", "2", str(seg_mp4),
        ],
        stdin=subprocess.DEVNULL,
        check=True,
        timeout=120,
    )
    shutil.rmtree(f_dir)
    return {"idx": idx, "start": s_f, "end": e_f, "seg": str(seg_mp4), "seconds": round(time.monotonic() - t0, 2)}

t_start = time.monotonic()
max_workers = max(1, min(2, int(cfg.get("parallel_workers", 2))))
chunk_stats = []
with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
    futs = [pool.submit(run_chunk, pair) for pair in enumerate(chunks)]
    for fut in concurrent.futures.as_completed(futs):
        chunk_stats.append(fut.result())
chunk_stats.sort(key=lambda r: r["idx"])

concat_list = segments_dir / "concat.txt"
concat_list.write_text("".join(f"file '{c['seg']}'\n" for c in chunk_stats), encoding="utf-8")

raw_video = out_dir / "_video_only.mp4"
if raw_video.exists():
    raw_video.unlink()
subprocess.run(
    [
        FFMPEG_BIN, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy", str(raw_video),
    ],
    stdin=subprocess.DEVNULL,
    check=True,
    timeout=120,
)
shutil.rmtree(segments_dir)

master_mp4 = out_dir / f"{cfg['scene_name']}_master.mp4"
tmp_master = out_dir / f".tmp_{cfg['scene_name']}_master.mp4"
if tmp_master.exists():
    tmp_master.unlink()
if master_mp4.exists():
    master_mp4.unlink()
subprocess.run(
    [
        FFMPEG_BIN, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-y",
        "-i", str(raw_video), "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-shortest", "-movflags", "+faststart", str(tmp_master),
    ],
    stdin=subprocess.DEVNULL,
    check=True,
    timeout=120,
)
raw_video.unlink()

# Verify encoded master stream geometry, audio stream, and full decode
probe = json.loads(subprocess.check_output(
    [FFPROBE_BIN, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", str(tmp_master)],
    text=True,
    timeout=30,
))
subprocess.run(
    [FFMPEG_BIN, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-i", str(tmp_master), "-f", "null", "-"],
    stdin=subprocess.DEVNULL,
    check=True,
    timeout=120,
)
os.link(tmp_master, master_mp4)
tmp_master.unlink()

# Extract 3x3 encoded verification contact sheet & render 1 high-sample hero frame
sheet_out = out_dir / f"{cfg['scene_name']}_encoded_3x3.png"
samples_dir = out_dir / "_enc_samples"
samples_dir.mkdir(parents=True, exist_ok=True)
for idx, t_sec in enumerate(cfg["sample_times_s"]):
    subprocess.run(
        [
            FFMPEG_BIN, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{t_sec:.3f}", "-i", str(master_mp4),
            "-frames:v", "1", str(samples_dir / f"s_{idx:02d}.png"),
        ],
        stdin=subprocess.DEVNULL,
        check=True,
        timeout=30,
    )
subprocess.run(
    [
        FFMPEG_BIN, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-pattern_type", "glob", "-i", str(samples_dir / "s_*.png"),
        "-vf", "scale=480:-1,tile=3x3:padding=6:margin=6:color=0x0b0e17",
        "-frames:v", "1", str(sheet_out),
    ],
    stdin=subprocess.DEVNULL,
    check=True,
    timeout=30,
)
shutil.rmtree(samples_dir)

hero_out = out_dir / f"{cfg['scene_name']}_hero.png"
hero_py = r'''
import bpy, json, sys
argv = sys.argv[sys.argv.index("--") + 1:]
hc = json.loads(argv[0])
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.eevee.taa_render_samples = 48
scene.frame_set(int(hc["hero_frame"]))
scene.render.filepath = hc["hero_out"]
bpy.ops.render.render(write_still=True)
'''
subprocess.run(
    [BLENDER_BIN, "--background", str(blend_path), "--python-expr", hero_py, "--", json.dumps({"hero_frame": cfg["hero_frame"], "hero_out": str(hero_out)})],
    check=True,
    capture_output=True,
    text=True,
    timeout=180,
)

def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blk)
    return h.hexdigest()

artifacts = {}
for key, p in (
    ("blend", blend_path),
    ("encoded_3x3", sheet_out),
    ("hero_png", hero_out),
    ("mp4", master_mp4),
):
    artifacts[key] = {
        "path": str(p),
        "filename": p.name,
        "bytes": p.stat().st_size,
        "sha256": sha256_path(p),
    }

manifest = {
    "schema_version": "music-video-manifest.v1",
    "scene_name": cfg["scene_name"],
    "total_wall_seconds": round(time.monotonic() - t_start, 2),
    "chunk_count": len(chunk_stats),
    "video_verification": {
        "streams": probe.get("streams", []),
        "duration": probe.get("format", {}).get("duration"),
        "full_decode_passed": True,
    },
    "disk_free_gib_after": round(shutil.disk_usage("/").free / (1024 ** 3), 3),
    "artifacts": artifacts,
}
mpath = out_dir / "manifest.json"
mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"manifest_path": str(mpath), **manifest}, indent=2))
"""


def direct_music_video(
    *,
    audio_path: Path,
    builder_script: Path,
    catalog_config: Path | None,
    remote_out_root: str,
    local_out_dir: Path,
    run_subdir: str = "midnight_clockwork_swing",
    scene_name: str = "midnight_clockwork_swing",
    remote_user: str | None = None,
    gdrive_sync_config: Path | None = None,
    storyboard_only: bool = False,
    skip_build: bool = False,
    parallel_workers: int = 2,
    width: int = 1280,
    height: int = 720,
    samples: int = 12,
    hero_frame: int = 1165,
    storyboard_frames: list[int] | None = None,
    cast_preset: str = "band",
) -> dict[str, Any]:
    """Orchestrate full audio-reactive Blender 5.2+ music video production."""
    if not dc.SAFE_NAME_RE.match(run_subdir) or not dc.SAFE_NAME_RE.match(scene_name):
        raise ValueError("Unsafe run_subdir or scene_name")

    cfg = dc.load_catalog_config(catalog_config)
    index = dc.CatalogIndex(cfg["metadata_dir"])
    host, _ = dc._require_remote_settings(cfg)
    ssh_user = remote_user or str(cfg.get("remote_user") or "").strip()
    if not ssh_user:
        raise ValueError("Remote SSH user required via --remote-user or 'remote_user' in catalog.json")

    remote_root_clean = remote_out_root.rstrip("/")
    remote_out_dir = f"{remote_root_clean}/{run_subdir}"
    remote_blend_path = f"{remote_out_dir}/{scene_name}.blend"
    remote_spec_path = f"{remote_out_dir}/scene_build_spec.json"
    remote_builder_path = f"{remote_out_dir}/scene_builder.py"
    remote_audio_path = f"{remote_out_dir}/track{audio_path.suffix or '.mp3'}"

    local_dir = Path(local_out_dir).expanduser().resolve()
    local_dir.mkdir(parents=True, exist_ok=True)

    # 1. Analyze audio on workstation
    analysis = analyze_audio_track(audio_path, fps=24)
    analysis_local = local_dir / "audio_analysis.json"
    analysis_local.write_text(json.dumps(analysis, separators=(",", ":")), encoding="utf-8")

    dc._ssh_python(host, REMOTE_PREPARE_DIR, [remote_out_dir, str(cfg.get("min_remote_free_gib", 1.5))])

    build_report: dict[str, Any] | None = None
    if not skip_build:
        cast_ids = resolve_cast_preset(cast_preset)
        staged_cast = {}
        for aid in cast_ids:
            st = dc.stage_to_remote(index, cfg, aid)
            staged_cast[aid.split("/")[-1]] = st["staging"]["remote_path"]

        spec_payload = {
            "scene_name": scene_name,
            "blend_path": remote_blend_path,
            "cast": staged_cast,
            "width": width,
            "height": height,
            "samples": samples,
            "analysis": analysis,
        }
        spec_local = local_dir / "scene_build_spec.json"
        spec_local.write_text(json.dumps(spec_payload, separators=(",", ":")), encoding="utf-8")

        _scp_upload(spec_local, host, remote_spec_path, timeout=60)
        _scp_upload(Path(builder_script).expanduser().resolve(), host, remote_builder_path, timeout=60)
        _scp_upload(Path(audio_path).expanduser().resolve(), host, remote_audio_path, timeout=60)

        proc = subprocess.run(
            [
                "ssh",
                *dc.SSH_OPTS,
                host,
                f"/Applications/Blender.app/Contents/MacOS/Blender --background --python {shlex.quote(remote_builder_path)} -- {shlex.quote(remote_spec_path)}",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        for line in proc.stdout.splitlines():
            if line.startswith("MUSIC_VIDEO_BUILD_JSON:"):
                build_report = json.loads(line.split("MUSIC_VIDEO_BUILD_JSON:", 1)[1])
                break
        if build_report is None:
            raise RuntimeError(f"Missing MUSIC_VIDEO_BUILD_JSON in builder output:\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")

    shots = parse_storyboard_frames(
        ",".join(str(f) for f in storyboard_frames) if storyboard_frames else None,
        total_frames=analysis["total_frames"],
    )

    if storyboard_only:
        sb_manifest = dc._ssh_python(
            host,
            REMOTE_STORYBOARD_DRIVER,
            [
                json.dumps(
                    {
                        "scene_name": scene_name,
                        "out_dir": remote_out_dir,
                        "blend_path": remote_blend_path,
                        "frames": shots,
                        "width": width,
                        "height": height,
                    }
                )
            ],
            timeout=600,
        )
        tr_proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "transfer_verified_file.py"),
                "--source-host",
                host,
                "--source-user",
                ssh_user,
                "--source-root",
                remote_root_clean,
                "--manifest-path",
                sb_manifest["manifest_path"],
                "--destination-root",
                str(local_dir),
                "--transfer-mode",
                "full",
                "--multiplex",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        return {
            "mode": "storyboard_only",
            "estimated_bpm": analysis["estimated_bpm"],
            "total_frames": analysis["total_frames"],
            "build_report": build_report,
            "storyboard": sb_manifest,
            "transfer": json.loads(tr_proc.stdout),
        }

    # Full parallel render
    chunks = partition_chunks(1, analysis["total_frames"], max_chunk=MAX_CHUNK_FRAMES)
    sample_times_s = [round((f - 1) / 24.0, 3) for f in shots]
    render_manifest = dc._ssh_python(
        host,
        REMOTE_PARALLEL_RENDER_DRIVER,
        [
            json.dumps(
                {
                    "scene_name": scene_name,
                    "out_dir": remote_out_dir,
                    "blend_path": remote_blend_path,
                    "audio_path": remote_audio_path,
                    "chunks": chunks,
                    "parallel_workers": parallel_workers,
                    "threads_per_worker": 4,
                    "width": width,
                    "height": height,
                    "hero_frame": max(1, min(analysis["total_frames"], hero_frame)),
                    "sample_times_s": sample_times_s,
                    "min_remote_free_gib": float(cfg.get("min_remote_free_gib", 1.5)),
                }
            )
        ],
        timeout=1800,
    )

    tr_cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "transfer_verified_file.py"),
        "--source-host",
        host,
        "--source-user",
        ssh_user,
        "--source-root",
        remote_root_clean,
        "--manifest-path",
        render_manifest["manifest_path"],
        "--destination-root",
        str(local_dir),
        "--transfer-mode",
        "full",
        "--multiplex",
    ]
    if gdrive_sync_config is not None:
        tr_cmd.extend(
            [
                "--gdrive-sync-config",
                str(Path(gdrive_sync_config).expanduser()),
                "--gdrive-subdir",
                local_dir.name,
            ]
        )
    tr_proc = subprocess.run(tr_cmd, check=True, capture_output=True, text=True, timeout=300)
    transfer_res = json.loads(tr_proc.stdout)

    local_hero = local_dir / render_manifest["artifacts"]["hero_png"]["filename"]
    qa_sheet = evaluate_media_paths(
        [local_dir / render_manifest["artifacts"]["encoded_3x3"]["filename"], local_hero],
        require_motion=True,
    )

    return {
        "mode": "render_full",
        "directed_at_utc": datetime.now(timezone.utc).isoformat(),
        "estimated_bpm": analysis["estimated_bpm"],
        "total_frames": analysis["total_frames"],
        "duration_s": analysis["duration"],
        "build_report": build_report,
        "remote_render": render_manifest,
        "transfer_and_delivery": transfer_res,
        "frame_qa_stills": {"status": qa_sheet["status"], "motion_delta": qa_sheet["motion_delta"]},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, type=Path, help="Input audio track (.mp3/.wav/.m4a)")
    parser.add_argument("--builder-script", type=Path, default=DEFAULT_BUILDER)
    parser.add_argument("--catalog-config", type=Path, default=None)
    parser.add_argument("--gdrive-sync-config", type=Path, default=None)
    parser.add_argument("--remote-out-root", required=True)
    parser.add_argument("--remote-user", default=None)
    parser.add_argument("--local-out-dir", required=True, type=Path)
    parser.add_argument("--run-subdir", default="midnight_clockwork_swing")
    parser.add_argument("--scene-name", default="midnight_clockwork_swing")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--parallel-workers", type=int, default=2)
    parser.add_argument("--cast-preset", choices=sorted(CAST_PRESETS), default="band")
    parser.add_argument("--storyboard-frames", default=None, help="9 comma-separated frames for 3x3 storyboard/encoded QA sheets")
    parser.add_argument("--hero-frame", type=int, default=1165, help="Hero high-sample frame index")
    parser.add_argument("--storyboard-only", action="store_true")
    parser.add_argument("--render-full", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    parsed_shots = None
    if args.storyboard_frames:
        parsed_shots = [int(p.strip()) for p in args.storyboard_frames.split(",") if p.strip()]
        if len(parsed_shots) != 9:
            parser.error("--storyboard-frames must contain exactly 9 comma-separated integers")

    out = direct_music_video(
        audio_path=args.audio,
        builder_script=args.builder_script,
        catalog_config=args.catalog_config,
        remote_out_root=args.remote_out_root,
        local_out_dir=args.local_out_dir,
        run_subdir=args.run_subdir,
        scene_name=args.scene_name,
        remote_user=args.remote_user,
        gdrive_sync_config=args.gdrive_sync_config,
        storyboard_only=args.storyboard_only or not args.render_full,
        skip_build=args.skip_build,
        parallel_workers=args.parallel_workers,
        width=args.width,
        height=args.height,
        samples=args.samples,
        hero_frame=args.hero_frame,
        storyboard_frames=parsed_shots,
        cast_preset=args.cast_preset,
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
