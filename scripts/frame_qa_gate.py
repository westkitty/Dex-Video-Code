#!/usr/bin/env python3
"""Automated pre-master visual & histogram QA gate using FFmpeg/FFprobe.

Checks rendered PNG frames or encoded MP4 files without external Python deps:
- Rejects pitch-black / blank frames (low mean/max luma)
- Rejects blown-out / clipped white frames (excessive high luma ratio or clipped max)
- Detects frozen/static sequences (near-zero inter-frame motion delta across key frames)
- Emits a structured frame-qa-report.v1 JSON receipt (PASS or FAIL)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SIGNAL_RE = re.compile(
    r"lavfi\.signalstats\.(YAVG|YMIN|YMAX|YLOW|YHIGH|SATAVG)=([0-9]+(?:\.[0-9]+)?)"
)


@dataclass(frozen=True)
class FrameMetrics:
    source: str
    mean_luma: float
    min_luma: float
    max_luma: float
    low_luma: float
    high_luma: float
    mean_sat: float


@dataclass(frozen=True)
class QAThresholds:
    min_mean_luma: float = 8.0
    max_mean_luma: float = 235.0
    min_dynamic_range: float = 18.0
    max_high_luma: float = 254.0
    min_motion_delta: float = 0.5


def resolve_ffmpeg() -> str:
    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"):
        p = Path(candidate)
        if candidate == "ffmpeg" or p.is_file():
            return candidate
    return "ffmpeg"


def probe_luma_stats(media_path: Path, ffmpeg_bin: str | None = None) -> list[FrameMetrics]:
    """Extract per-frame signalstats metrics via FFmpeg lavfi metadata print."""
    if not media_path.is_file():
        raise FileNotFoundError(f"Media file not found: {media_path}")
    ff = ffmpeg_bin or resolve_ffmpeg()
    proc = subprocess.run(
        [
            ff,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media_path),
            "-vf",
            "format=yuv420p,signalstats,metadata=mode=print:file=-",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg signalstats failed for {media_path}: {proc.stderr}")

    frames: list[FrameMetrics] = []
    cur: dict[str, float] = {}
    for line in proc.stdout.splitlines():
        if line.startswith("frame:"):
            if cur:
                frames.append(_to_frame_metrics(media_path.name, cur))
                cur = {}
        m = SIGNAL_RE.search(line)
        if m:
            cur[m.group(1)] = float(m.group(2))
    if cur:
        frames.append(_to_frame_metrics(media_path.name, cur))
    if not frames:
        raise RuntimeError(f"No signalstats frames parsed from {media_path}")
    return frames


def _to_frame_metrics(source: str, values: dict[str, float]) -> FrameMetrics:
    return FrameMetrics(
        source=source,
        mean_luma=round(values.get("YAVG", 0.0), 3),
        min_luma=round(values.get("YMIN", 0.0), 3),
        max_luma=round(values.get("YMAX", 0.0), 3),
        low_luma=round(values.get("YLOW", 0.0), 3),
        high_luma=round(values.get("YHIGH", 0.0), 3),
        mean_sat=round(values.get("SATAVG", 0.0), 3),
    )


def evaluate_frames(
    metrics: list[FrameMetrics],
    thresholds: QAThresholds = QAThresholds(),
    *,
    require_motion: bool = True,
) -> dict[str, Any]:
    failures: list[str] = []
    for idx, fm in enumerate(metrics):
        if fm.mean_luma < thresholds.min_mean_luma:
            failures.append(f"frame[{idx}] ({fm.source}) too dark: mean_luma={fm.mean_luma} < {thresholds.min_mean_luma}")
        if fm.mean_luma > thresholds.max_mean_luma:
            failures.append(f"frame[{idx}] ({fm.source}) overexposed: mean_luma={fm.mean_luma} > {thresholds.max_mean_luma}")
        if (fm.max_luma - fm.min_luma) < thresholds.min_dynamic_range:
            failures.append(
                f"frame[{idx}] ({fm.source}) flat dynamic range: {(fm.max_luma - fm.min_luma):.2f} < {thresholds.min_dynamic_range}"
            )
        if fm.low_luma > thresholds.max_high_luma and fm.mean_luma > 220.0:
            failures.append(f"frame[{idx}] ({fm.source}) severe highlight clipping")

    motion_delta = 0.0
    if len(metrics) >= 2:
        lumas = [m.mean_luma for m in metrics]
        max_sats = [m.mean_sat for m in metrics]
        motion_delta = round(max(max(lumas) - min(lumas), max(max_sats) - min(max_sats)), 3)
        if require_motion and motion_delta < thresholds.min_motion_delta:
            failures.append(f"sequence appears static/frozen: motion_delta={motion_delta} < {thresholds.min_motion_delta}")

    return {
        "schema_version": "frame-qa-report.v1",
        "status": "PASS" if not failures else "FAIL",
        "frame_count": len(metrics),
        "motion_delta": motion_delta,
        "thresholds": asdict(thresholds),
        "failures": failures,
        "frames": [asdict(m) for m in metrics],
    }


def evaluate_media_paths(
    paths: list[Path],
    thresholds: QAThresholds = QAThresholds(),
    *,
    require_motion: bool = True,
    ffmpeg_bin: str | None = None,
) -> dict[str, Any]:
    all_metrics: list[FrameMetrics] = []
    for p in paths:
        all_metrics.extend(probe_luma_stats(p, ffmpeg_bin=ffmpeg_bin))
    return evaluate_frames(all_metrics, thresholds=thresholds, require_motion=(require_motion and len(all_metrics) >= 2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="PNG frames or MP4 media to inspect")
    parser.add_argument("--no-motion-check", action="store_true", help="Skip inter-frame motion delta gate")
    parser.add_argument("--min-mean-luma", type=float, default=8.0)
    parser.add_argument("--max-mean-luma", type=float, default=235.0)
    parser.add_argument("--min-dynamic-range", type=float, default=18.0)
    parser.add_argument("--min-motion-delta", type=float, default=0.5)
    parser.add_argument("--out", type=Path, help="Optional JSON receipt output path")
    args = parser.parse_args()

    thresholds = QAThresholds(
        min_mean_luma=args.min_mean_luma,
        max_mean_luma=args.max_mean_luma,
        min_dynamic_range=args.min_dynamic_range,
        min_motion_delta=args.min_motion_delta,
    )
    report = evaluate_media_paths(
        [p.resolve() for p in args.inputs],
        thresholds=thresholds,
        require_motion=not args.no_motion_check,
    )
    payload = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
