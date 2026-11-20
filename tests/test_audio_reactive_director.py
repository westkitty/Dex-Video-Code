#!/usr/bin/env python3
"""Hermetic unit tests for scripts/audio_reactive_director.py."""

from __future__ import annotations

import math
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audio_reactive_director as ard  # noqa: E402


def _write_test_wav(path: Path, *, duration_s: float = 4.0, sr: int = 22050, bpm: float = 120.0) -> None:
    """Synthesize a clean 4s WAV: first 2s strong 65 Hz kick pulses at BPM, last 2s bright 4 kHz bell tone."""
    total = int(duration_s * sr)
    beat_period = 60.0 / bpm
    samples = bytearray()
    for i in range(total):
        t = i / float(sr)
        if t < duration_s * 0.5:
            phase_in_beat = t % beat_period
            env = math.exp(-phase_in_beat * 10.0)
            val = 0.8 * env * math.sin(2.0 * math.pi * 65.0 * t)
        else:
            val = 0.55 * math.sin(2.0 * math.pi * 4000.0 * t)
        pcm = max(-32767, min(32767, int(val * 32767.0)))
        samples.extend(struct.pack("<h", pcm))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(samples))


class AudioReactiveDirectorTests(unittest.TestCase):
    def test_analyze_audio_track_and_band_separation(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            wav_path = Path(tmp) / "test_120bpm.wav"
            _write_test_wav(wav_path, duration_s=4.0, bpm=120.0)
            res = ard.analyze_audio_track(wav_path, fps=24)

            self.assertEqual(res["schema_version"], "audio-reactive-analysis.v1")
            self.assertEqual(res["total_frames"], 96)
            self.assertAlmostEqual(res["duration"], 4.0, delta=0.1)
            self.assertEqual(len(res["frames"]), 96)
            self.assertEqual(len(res["frames"][0]["b16"]), 16)

            # First half is 65 Hz kick, second half is 4 kHz chime -> clear bass vs high separation
            early_bass = sum(f["bass"] for f in res["frames"][:40]) / 40.0
            late_bass = sum(f["bass"] for f in res["frames"][56:]) / 40.0
            early_high = sum(f["high"] for f in res["frames"][:40]) / 40.0
            late_high = sum(f["high"] for f in res["frames"][56:]) / 40.0
            self.assertGreater(early_bass, late_bass * 3.0)
            self.assertGreater(late_high, early_high * 3.0)

    def test_partition_chunks_respects_48_frame_bound(self) -> None:
        chunks = ard.partition_chunks(1, 1386, max_chunk=48)
        self.assertEqual(chunks[0], (1, 48))
        self.assertEqual(chunks[-1][1], 1386)
        self.assertTrue(all((e - s + 1) <= 48 for s, e in chunks))
        covered = sum((e - s + 1) for s, e in chunks)
        self.assertEqual(covered, 1386)
        with self.assertRaises(ValueError):
            ard.partition_chunks(1, 100, max_chunk=60)


if __name__ == "__main__":
    unittest.main()
