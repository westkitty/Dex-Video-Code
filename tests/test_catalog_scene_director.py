#!/usr/bin/env python3
"""Hermetic unit tests for declarative catalog_scene_director validation, framing, and spatial QA."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import catalog_scene_director as csd  # noqa: E402


class CatalogSceneDirectorTests(unittest.TestCase):
    def test_validate_scene_manifest_and_example(self) -> None:
        example_path = REPO_ROOT / "examples" / "p7" / "catalog_knight_goblin_scene.json"
        raw = json.loads(example_path.read_text(encoding="utf-8"))
        norm = csd.validate_scene_manifest(raw)
        self.assertEqual(norm["scene_name"], "catalog_knight_goblin_showcase")
        self.assertEqual(len(norm["characters"]), 2)
        self.assertTrue(norm["render"]["quad_qa_sheet"])
        self.assertTrue(all(a["gltf_bone_align"] is True for a in norm["characters"][0]["attachments"]))

        explicit_unaligned = json.loads(example_path.read_text(encoding="utf-8"))
        explicit_unaligned["characters"][0]["attachments"][0]["gltf_bone_align"] = False
        norm_unaligned = csd.validate_scene_manifest(explicit_unaligned)
        self.assertFalse(norm_unaligned["characters"][0]["attachments"][0]["gltf_bone_align"])

        # Reject > 48 animation frames
        over_budget = json.loads(example_path.read_text(encoding="utf-8"))
        over_budget["render"]["end_frame"] = 80
        with self.assertRaises(ValueError):
            csd.validate_scene_manifest(over_budget)

        # Reject path traversal in scene_name
        bad_name = json.loads(example_path.read_text(encoding="utf-8"))
        bad_name["scene_name"] = "../escape"
        with self.assertRaises(ValueError):
            csd.validate_scene_manifest(bad_name)

    def test_compute_auto_frame_camera(self) -> None:
        small = csd.compute_auto_frame_camera([-1.0, -0.5, 0.0], [1.0, 0.5, 2.0])
        tall = csd.compute_auto_frame_camera([-2.0, -1.0, 0.0], [2.0, 1.0, 6.0])
        self.assertEqual(small["target"], [0.0, 0.0, 1.0])
        self.assertGreater(tall["distance"], small["distance"])
        self.assertLess(small["location"][1], small["target"][1])
        self.assertGreater(small["location"][2], small["target"][2])

    def test_evaluate_spatial_qa(self) -> None:
        good_chars = [
            {
                "name": "knight",
                "ground_on_z0": True,
                "world_bbox": {"min": [-2.0, -0.6, 0.0], "max": [-0.2, 0.6, 2.5], "size": [1.8, 1.2, 2.5]},
                "attachments": [{"bone": "handslot.r", "socket_distance_m": 0.0}],
                "animation": {"max_vertex_displacement": 0.41},
            },
            {
                "name": "goblin",
                "ground_on_z0": True,
                "world_bbox": {"min": [0.5, -0.5, 0.002], "max": [1.8, 0.4, 1.6], "size": [1.3, 0.9, 1.598]},
                "attachments": [],
                "animation": {"max_vertex_displacement": 0.35},
            },
        ]
        ok = csd.evaluate_spatial_qa(good_chars)
        self.assertTrue(ok["passed"], ok)
        self.assertEqual(ok["failures"], [])

        # Detect floating mesh, socket detachment, frozen animation, and AABB overlap
        bad_chars = [
            {
                "name": "floater",
                "ground_on_z0": True,
                "world_bbox": {"min": [-1.0, -0.5, 0.45], "max": [1.0, 0.5, 2.5], "size": [2.0, 1.0, 2.05]},
                "attachments": [{"bone": "handslot.r", "socket_distance_m": 0.9}],
                "animation": {"max_vertex_displacement": 0.0},
            },
            {
                "name": "collider",
                "ground_on_z0": True,
                "world_bbox": {"min": [-0.2, -0.4, 0.0], "max": [1.5, 0.4, 1.8], "size": [1.7, 0.8, 1.8]},
                "attachments": [],
                "animation": None,
            },
        ]
        bad = csd.evaluate_spatial_qa(bad_chars)
        self.assertFalse(bad["passed"])
        self.assertEqual(len(bad["failures"]), 4)
        self.assertEqual(len(bad["metrics"]["overlap_pairs"]), 1)


if __name__ == "__main__":
    unittest.main()
