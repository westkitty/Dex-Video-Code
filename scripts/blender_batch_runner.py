#!/usr/bin/env python3
"""Optimized Blender 5.2+ batch, parallel, sliding-window, and warm render runner.

Implements:
- App-bundle binary discovery (macOS Blender.app preferred; never broken symlinks)
- Configurable scratch root (--scratch-root or DEX_RENDER_SCRATCH_ROOT) + disk guard
- Parallel chunked rendering (--parallel-workers 1..2) & thread tuning (--threads 1..16)
- Sliding-window chunked PNG -> segment MP4 cleanup (--sliding-window-chunk)
- Persistent warm Blender worker mode (--warm-worker) to amortize Metal shaders
- Frame resume (--resume, skips already-rendered valid PNG frames)
- Encode profiles: preview_hw (VideoToolbox with libx264 fallback), master_h264, master_10bit
- FFprobe + full FFmpeg decode verification + optional Frame QA Gate + SHA-256 manifest
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import resource
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from frame_qa_gate import evaluate_media_paths  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

QUALITY_PRESETS: dict[str, dict[str, Any]] = {
    "interaction": {"width": 320, "height": 180, "samples": 8},
    "preview": {"width": 640, "height": 360, "samples": 16},
    "master": {"width": 1280, "height": 720, "samples": 32},
    "hero": {"width": 1280, "height": 720, "samples": 48},
}


def resolve_blender_binary() -> str:
    env_bin = os.environ.get("BLENDER_BIN")
    if env_bin and Path(env_bin).is_file():
        return env_bin
    app_bin = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    if app_bin.is_file() and os.access(app_bin, os.X_OK):
        return str(app_bin)
    found = shutil.which("blender")
    if found:
        return str(Path(found).resolve())
    raise FileNotFoundError("No usable Blender executable found")


def resolve_ffmpeg_tools() -> tuple[str, str]:
    ff = "/opt/homebrew/bin/ffmpeg" if Path("/opt/homebrew/bin/ffmpeg").is_file() else (shutil.which("ffmpeg") or "ffmpeg")
    fp = "/opt/homebrew/bin/ffprobe" if Path("/opt/homebrew/bin/ffprobe").is_file() else (shutil.which("ffprobe") or "ffprobe")
    return ff, fp


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blk)
    return h.hexdigest()


def is_valid_png(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        if path.stat().st_size < 128:
            return False
        with path.open("rb") as f:
            return f.read(8) == PNG_MAGIC
    except OSError:
        return False


def check_disk_admission(target_dir: Path, min_free_gib: float = 1.5) -> dict[str, Any]:
    probe_target = target_dir if target_dir.exists() else target_dir.parent
    usage = shutil.disk_usage(probe_target)
    free_gib = round(usage.free / (1024 ** 3), 3)
    if free_gib < min_free_gib:
        raise RuntimeError(f"Disk admission blocked at {probe_target}: {free_gib:.3f} GiB < {min_free_gib:.3f} GiB")
    warnings = []
    if free_gib < 5.0:
        warnings.append(f"Low disk free: {free_gib:.3f} GiB (< 5.0 GiB advisory floor)")
    return {"free_gib": free_gib, "warnings": warnings}


def partition_frame_ranges(start_frame: int, end_frame: int, workers: int) -> list[tuple[int, int]]:
    total = end_frame - start_frame + 1
    if total < 1:
        raise ValueError("Invalid frame range")
    workers = max(1, min(workers, total))
    base, rem = divmod(total, workers)
    ranges: list[tuple[int, int]] = []
    cur = start_frame
    for idx in range(workers):
        size = base + (1 if idx < rem else 0)
        ranges.append((cur, cur + size - 1))
        cur += size
    return ranges


def split_sliding_windows(start_frame: int, end_frame: int, window_size: int) -> list[tuple[int, int]]:
    if window_size <= 0:
        return [(start_frame, end_frame)]
    windows: list[tuple[int, int]] = []
    cur = start_frame
    while cur <= end_frame:
        hi = min(end_frame, cur + window_size - 1)
        windows.append((cur, hi))
        cur = hi + 1
    return windows


def detect_available_encoders(ffmpeg_bin: str) -> set[str]:
    proc = subprocess.run([ffmpeg_bin, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10)
    encoders: set[str] = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith(("V", "A")):
            encoders.add(parts[1])
    return encoders


def build_encode_args(
    ffmpeg_bin: str,
    input_pattern: Path,
    start_frame: int,
    frame_count: int,
    out_path: Path,
    encode_profile: str,
    available_encoders: set[str] | None = None,
) -> tuple[list[str], str]:
    """Build argument-array FFmpeg command for preview_hw, master_h264, or master_10bit."""
    if encode_profile == "preview_hw":
        encoders = available_encoders if available_encoders is not None else detect_available_encoders(ffmpeg_bin)
        if "h264_videotoolbox" in encoders:
            codec_args = ["-c:v", "h264_videotoolbox", "-b:v", "2800k", "-pix_fmt", "yuv420p"]
            expected_codec = "h264"
        else:
            codec_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p"]
            expected_codec = "h264"
    elif encode_profile == "master_h264":
        codec_args = ["-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p"]
        expected_codec = "h264"
    elif encode_profile == "master_10bit":
        codec_args = ["-c:v", "libx265", "-crf", "16", "-pix_fmt", "yuv420p10le", "-tag:v", "hvc1"]
        expected_codec = "hevc"
    else:
        raise ValueError(f"Unsupported encode_profile: {encode_profile}")

    cmd = [
        ffmpeg_bin,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-xerror",
        "-n",
        "-framerate",
        "24",
        "-start_number",
        str(start_frame),
        "-i",
        str(input_pattern),
        "-frames:v",
        str(frame_count),
        "-threads",
        "4",
        *codec_args,
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    return cmd, expected_codec


def verify_mp4_output(
    mp4_path: Path,
    ffmpeg_bin: str,
    ffprobe_bin: str,
    expected_codec: str,
    expected_width: int,
    expected_height: int,
    expected_frames: int,
) -> dict[str, Any]:
    probe_raw = subprocess.check_output(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,nb_frames,pix_fmt:format=duration",
            "-of",
            "json",
            str(mp4_path),
        ],
        text=True,
        timeout=20,
    )
    meta = json.loads(probe_raw)
    streams = meta.get("streams", [])
    if len(streams) != 1:
        raise RuntimeError(f"Expected 1 video stream, got {len(streams)}: {meta}")
    st = streams[0]
    if (
        st.get("codec_name") != expected_codec
        or st.get("width") != expected_width
        or st.get("height") != expected_height
        or st.get("r_frame_rate") != "24/1"
        or str(st.get("nb_frames")) != str(expected_frames)
    ):
        raise RuntimeError(f"FFprobe verification failed: {meta}")

    subprocess.run(
        [ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-i", str(mp4_path), "-f", "null", "-"],
        stdin=subprocess.DEVNULL,
        check=True,
        timeout=60,
    )
    return {
        "codec": st["codec_name"],
        "pix_fmt": st.get("pix_fmt"),
        "width": st["width"],
        "height": st["height"],
        "r_frame_rate": st["r_frame_rate"],
        "nb_frames": int(st["nb_frames"]),
        "duration": meta.get("format", {}).get("duration"),
        "full_decode_passed": True,
    }


def _blender_chunk_script() -> str:
    return r"""
import bpy, json, os, sys, time
sys.path.insert(0, os.environ["DEX_SCRIPTS_DIR"])
import blender_render_pipeline as brp

def render_cfg(cfg):
    scene = bpy.context.scene
    brp.configure_render_engine(
        scene,
        engine=cfg["engine"],
        quality=cfg["quality"],
        threads=cfg["threads"],
        color_depth=cfg["color_depth"],
        bpy_module=bpy,
    )
    scene.render.use_overwrite = not bool(cfg.get("resume", False))
    timings = []
    skipped = []
    for f in range(cfg["start_frame"], cfg["end_frame"] + 1):
        out_path = os.path.join(cfg["frames_dir"], f"frame_{f:04d}.png")
        if cfg.get("resume") and os.path.isfile(out_path) and os.path.getsize(out_path) > 128:
            with open(out_path, "rb") as fh:
                if fh.read(8) == b"\x89PNG\r\n\x1a\n":
                    skipped.append(f)
                    continue
        t0 = time.monotonic()
        scene.frame_set(f)
        scene.render.filepath = out_path
        bpy.ops.render.render(write_still=True)
        timings.append({"frame": f, "seconds": round(time.monotonic() - t0, 3)})
    return {
        "timings": timings,
        "skipped_frames": skipped,
        "total_seconds": round(sum(t["seconds"] for t in timings), 3),
    }

argv = sys.argv[sys.argv.index("--") + 1:]
if argv[0] == "--warm-worker":
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        req = json.loads(raw)
        if req.get("op") == "quit":
            print(json.dumps({"ok": True, "op": "quit"}), flush=True)
            break
        if req.get("blend_path"):
            bpy.ops.wm.open_mainfile(filepath=req["blend_path"])
        res = render_cfg(req)
        print(json.dumps({"ok": True, **res}), flush=True)
else:
    cfg = json.loads(argv[0])
    print("CHUNK_STATS_JSON:" + json.dumps(render_cfg(cfg)))
"""


def run_blender_chunk(
    blender_bin: str,
    blend_path: Path,
    frames_dir: Path,
    start_frame: int,
    end_frame: int,
    *,
    engine: str,
    quality: str,
    threads: int,
    color_depth: str,
    resume: bool,
) -> dict[str, Any]:
    cfg = {
        "frames_dir": str(frames_dir),
        "start_frame": start_frame,
        "end_frame": end_frame,
        "engine": engine,
        "quality": quality,
        "threads": threads,
        "color_depth": color_depth,
        "resume": resume,
    }
    env = os.environ.copy()
    env["DEX_SCRIPTS_DIR"] = str(SCRIPTS_DIR)
    t0 = time.monotonic()
    proc = subprocess.run(
        [
            blender_bin,
            "--background",
            str(blend_path),
            "--threads",
            str(threads),
            "--python-expr",
            _blender_chunk_script(),
            "--",
            json.dumps(cfg),
        ],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=env,
        timeout=900,
    )
    wall = round(time.monotonic() - t0, 3)
    if proc.returncode != 0:
        raise RuntimeError(f"Blender chunk {start_frame}..{end_frame} failed (rc={proc.returncode}):\n{proc.stderr[-1500:]}")
    stats = None
    for line in proc.stdout.splitlines():
        if line.startswith("CHUNK_STATS_JSON:"):
            stats = json.loads(line.split("CHUNK_STATS_JSON:", 1)[1])
            break
    if not stats:
        raise RuntimeError(f"Missing CHUNK_STATS_JSON for {start_frame}..{end_frame}:\n{proc.stdout[-1000:]}")
    stats["wall_seconds"] = wall
    stats["chunk"] = [start_frame, end_frame]
    return stats


def make_contact_sheet(ffmpeg_bin: str, frame_paths: list[Path], out_path: Path) -> None:
    if not frame_paths:
        return
    if out_path.exists():
        raise RuntimeError(f"Refusing to overwrite contact sheet: {out_path}")
    inputs: list[str] = []
    filters: list[str] = []
    for idx, fp in enumerate(frame_paths[:6]):
        inputs.extend(["-i", str(fp)])
        filters.append(f"[{idx}:v]scale=426:240[v{idx}]")
    n = min(6, len(frame_paths))
    cols = min(3, n)
    rows = 2 if n > 3 else 1
    scaled = "".join(f"[v{i}]" for i in range(n))
    fc = ";".join(filters) + f";{scaled}concat=n={n}:v=1:a=0,tile={cols}x{rows}:padding=4:margin=4:color=black[out]"
    subprocess.run(
        [ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", fc, "-map", "[out]", "-frames:v", "1", str(out_path)],
        stdin=subprocess.DEVNULL,
        check=True,
        timeout=60,
    )


def concat_segments(ffmpeg_bin: str, segments: list[Path], out_mp4: Path) -> None:
    if out_mp4.exists():
        raise RuntimeError(f"Refusing to overwrite MP4: {out_mp4}")
    list_file = out_mp4.with_name(f".{out_mp4.stem}.concat.txt")
    list_file.write_text("".join(f"file '{seg.as_posix()}'\n" for seg in segments), encoding="utf-8")
    tmp_mp4 = out_mp4.with_name(f".{out_mp4.name}.tmp.mp4")
    try:
        subprocess.run(
            [
                ffmpeg_bin,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-xerror",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(tmp_mp4),
            ],
            stdin=subprocess.DEVNULL,
            check=True,
            timeout=60,
        )
        os.link(tmp_mp4, out_mp4)
        tmp_mp4.unlink()
    finally:
        if list_file.exists():
            list_file.unlink()
        if tmp_mp4.exists():
            tmp_mp4.unlink()


def run_warm_worker_session(blend_path: Path, threads: int = 6) -> int:
    """Start a persistent Blender background process executing JSON-lines render requests."""
    blender_bin = resolve_blender_binary()
    env = os.environ.copy()
    env["DEX_SCRIPTS_DIR"] = str(SCRIPTS_DIR)
    proc = subprocess.run(
        [
            blender_bin,
            "--background",
            str(blend_path),
            "--threads",
            str(threads),
            "--python-expr",
            _blender_chunk_script(),
            "--",
            "--warm-worker",
        ],
        env=env,
    )
    return proc.returncode


def run_batch_pipeline(
    *,
    blend_path: Path,
    out_dir: Path,
    name_prefix: str,
    engine: str,
    quality: str,
    start_frame: int,
    end_frame: int,
    threads: int,
    parallel_workers: int,
    encode_profile: str,
    color_depth: str,
    sliding_window_chunk: int,
    resume: bool,
    keep_frames: bool,
    run_qa_gate: bool,
    contact_sheet: bool,
    min_free_gib: float,
) -> dict[str, Any]:
    frame_count = end_frame - start_frame + 1
    if start_frame < 1 or end_frame < start_frame or frame_count > 48:
        raise ValueError("Batch frame range must be bounded to 1..48 frames")
    if parallel_workers < 1 or parallel_workers > 2:
        raise ValueError("parallel_workers must be 1 or 2")
    if threads < 1 or threads > 16:
        raise ValueError("threads must be between 1 and 16")

    out_dir = out_dir.expanduser().resolve()
    if any(stat.S_ISLNK(p.lstat().st_mode) for p in [out_dir] + list(out_dir.parents) if p.exists()):
        raise ValueError("Refusing symlink in output directory path")
    out_dir.mkdir(parents=True, exist_ok=True)
    disk_before = check_disk_admission(out_dir, min_free_gib=min_free_gib)

    blender_bin = resolve_blender_binary()
    ffmpeg_bin, ffprobe_bin = resolve_ffmpeg_tools()
    encoders = detect_available_encoders(ffmpeg_bin)
    preset = QUALITY_PRESETS[quality]
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    mp4_path = out_dir / f"{name_prefix}.mp4"
    sheet_path = out_dir / f"{name_prefix}_contact_sheet.png"
    if mp4_path.exists():
        raise RuntimeError(f"Refusing to overwrite existing output MP4: {mp4_path}")

    windows = split_sliding_windows(start_frame, end_frame, sliding_window_chunk)
    all_chunk_stats: list[dict[str, Any]] = []
    segment_paths: list[Path] = []
    qa_sample_frames: list[Path] = []
    expected_codec = "hevc" if encode_profile == "master_10bit" else "h264"

    t_wall0 = time.monotonic()
    for w_idx, (w_start, w_end) in enumerate(windows):
        sub_ranges = partition_frame_ranges(w_start, w_end, parallel_workers)
        if len(sub_ranges) == 1:
            all_chunk_stats.append(
                run_blender_chunk(
                    blender_bin,
                    blend_path,
                    frames_dir,
                    sub_ranges[0][0],
                    sub_ranges[0][1],
                    engine=engine,
                    quality=quality,
                    threads=threads,
                    color_depth=color_depth,
                    resume=resume,
                )
            )
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(sub_ranges)) as pool:
                futs = [
                    pool.submit(
                        run_blender_chunk,
                        blender_bin,
                        blend_path,
                        frames_dir,
                        s,
                        e,
                        engine=engine,
                        quality=quality,
                        threads=threads,
                        color_depth=color_depth,
                        resume=resume,
                    )
                    for s, e in sub_ranges
                ]
                for fut in futs:
                    all_chunk_stats.append(fut.result())

        # Save up to 6 key sample frames across windows before sliding cleanup removes PNGs
        for f in range(w_start, w_end + 1):
            fp = frames_dir / f"frame_{f:04d}.png"
            if not is_valid_png(fp):
                raise RuntimeError(f"Missing or corrupt rendered frame: {fp}")
        if contact_sheet or run_qa_gate:
            sample_dir = out_dir / "_qa_samples"
            sample_dir.mkdir(parents=True, exist_ok=True)
            for pick in sorted({w_start, (w_start + w_end) // 2, w_end}):
                src_p = frames_dir / f"frame_{pick:04d}.png"
                dst_p = sample_dir / src_p.name
                if not dst_p.exists():
                    shutil.copy2(src_p, dst_p)
                    qa_sample_frames.append(dst_p)

        if len(windows) > 1:
            seg_path = out_dir / f".segment_{w_idx:03d}.mp4"
            cmd, expected_codec = build_encode_args(
                ffmpeg_bin,
                frames_dir / "frame_%04d.png",
                w_start,
                w_end - w_start + 1,
                seg_path,
                encode_profile,
                encoders,
            )
            subprocess.run(cmd, stdin=subprocess.DEVNULL, check=True, timeout=90)
            segment_paths.append(seg_path)
            if not keep_frames:
                for f in range(w_start, w_end + 1):
                    (frames_dir / f"frame_{f:04d}.png").unlink(missing_ok=True)

    if len(windows) > 1:
        concat_segments(ffmpeg_bin, segment_paths, mp4_path)
        for seg in segment_paths:
            seg.unlink(missing_ok=True)
    else:
        tmp_mp4 = mp4_path.with_name(f".{mp4_path.name}.tmp.mp4")
        cmd, expected_codec = build_encode_args(
            ffmpeg_bin,
            frames_dir / "frame_%04d.png",
            start_frame,
            frame_count,
            tmp_mp4,
            encode_profile,
            encoders,
        )
        subprocess.run(cmd, stdin=subprocess.DEVNULL, check=True, timeout=90)
        os.link(tmp_mp4, mp4_path)
        tmp_mp4.unlink()
        if not keep_frames:
            shutil.rmtree(frames_dir, ignore_errors=True)

    if frames_dir.exists() and not keep_frames and not any(frames_dir.iterdir()):
        frames_dir.rmdir()

    video_meta = verify_mp4_output(
        mp4_path,
        ffmpeg_bin,
        ffprobe_bin,
        expected_codec,
        preset["width"],
        preset["height"],
        frame_count,
    )

    qa_report = None
    if run_qa_gate:
        qa_report = evaluate_media_paths([mp4_path], require_motion=(frame_count >= 2), ffmpeg_bin=ffmpeg_bin)
        if qa_report["status"] != "PASS":
            raise RuntimeError(f"Frame QA gate failed: {qa_report['failures']}")

    if contact_sheet and qa_sample_frames:
        step = max(1, len(qa_sample_frames) // 6)
        chosen = sorted(qa_sample_frames)[::step][:6]
        make_contact_sheet(ffmpeg_bin, chosen, sheet_path)

    qa_dir = out_dir / "_qa_samples"
    if qa_dir.exists() and not keep_frames:
        shutil.rmtree(qa_dir, ignore_errors=True)

    disk_after = check_disk_admission(out_dir, min_free_gib=1.0)
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)

    artifacts: dict[str, dict[str, Any]] = {
        "blend": {"path": str(blend_path.resolve()), "filename": blend_path.name, "bytes": blend_path.stat().st_size, "sha256": sha256_file(blend_path)},
        "mp4": {"path": str(mp4_path), "filename": mp4_path.name, "bytes": mp4_path.stat().st_size, "sha256": sha256_file(mp4_path)},
    }
    if sheet_path.exists():
        artifacts["contact_sheet_png"] = {
            "path": str(sheet_path),
            "filename": sheet_path.name,
            "bytes": sheet_path.stat().st_size,
            "sha256": sha256_file(sheet_path),
        }

    manifest = {
        "schema_version": "blender-batch-manifest.v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "engine": engine,
        "quality": quality,
        "encode_profile": encode_profile,
        "color_depth": color_depth,
        "threads": threads,
        "parallel_workers": parallel_workers,
        "sliding_window_chunk": sliding_window_chunk,
        "resume": resume,
        "frame_start": start_frame,
        "frame_end": end_frame,
        "wall_seconds": round(time.monotonic() - t_wall0, 3),
        "peak_child_rss_bytes": int(ru.ru_maxrss),
        "disk_free_gib_before": disk_before["free_gib"],
        "disk_free_gib_after": disk_after["free_gib"],
        "disk_warnings": disk_before["warnings"],
        "chunks": all_chunk_stats,
        "video_verification": video_meta,
        "qa_report": qa_report,
        "artifacts": artifacts,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blend", required=True, type=Path, help="Input .blend file")
    parser.add_argument("--out-dir", type=Path, help="Output directory (overrides --scratch-root + --job-name)")
    parser.add_argument("--scratch-root", type=Path, help="Optional scratch volume root (or DEX_RENDER_SCRATCH_ROOT)")
    parser.add_argument("--job-name", default="render_job", help="Subdirectory name under --scratch-root")
    parser.add_argument("--name-prefix", default="render_output", help="Output filename prefix")
    parser.add_argument("--engine", choices=("eevee", "cycles_metal"), default="eevee")
    parser.add_argument("--quality", choices=("interaction", "preview", "master", "hero"), default="preview")
    parser.add_argument("--start-frame", type=int, default=1)
    parser.add_argument("--end-frame", type=int, default=24)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--parallel-workers", type=int, default=1)
    parser.add_argument("--encode-profile", choices=("preview_hw", "master_h264", "master_10bit"), default="preview_hw")
    parser.add_argument("--color-depth", choices=("8", "16"), default="8")
    parser.add_argument("--sliding-window-chunk", type=int, default=0, help="Encode & clean chunks of N frames (0=disabled)")
    parser.add_argument("--resume", action="store_true", help="Skip already-rendered valid PNG frames")
    parser.add_argument("--keep-frames", action="store_true")
    parser.add_argument("--run-qa-gate", action="store_true")
    parser.add_argument("--contact-sheet", action="store_true")
    parser.add_argument("--min-free-gib", type=float, default=1.5)
    parser.add_argument("--warm-worker", action="store_true", help="Run persistent stdin/stdout warm worker mode")
    args = parser.parse_args()

    if args.warm_worker:
        return run_warm_worker_session(args.blend.resolve(), threads=args.threads)

    scratch_env = os.environ.get("DEX_RENDER_SCRATCH_ROOT")
    if args.out_dir:
        out_dir = args.out_dir
    elif args.scratch_root or scratch_env:
        base = (args.scratch_root or Path(scratch_env)).expanduser().resolve()
        out_dir = base / args.job_name
    else:
        raise SystemExit("Either --out-dir or --scratch-root / DEX_RENDER_SCRATCH_ROOT is required")

    manifest = run_batch_pipeline(
        blend_path=args.blend.resolve(),
        out_dir=out_dir,
        name_prefix=args.name_prefix,
        engine=args.engine,
        quality=args.quality,
        start_frame=args.start_frame,
        end_frame=args.end_frame,
        threads=args.threads,
        parallel_workers=args.parallel_workers,
        encode_profile=args.encode_profile,
        color_depth=args.color_depth,
        sliding_window_chunk=args.sliding_window_chunk,
        resume=args.resume,
        keep_frames=args.keep_frames,
        run_qa_gate=args.run_qa_gate,
        contact_sheet=args.contact_sheet,
        min_free_gib=args.min_free_gib,
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
