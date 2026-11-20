#!/usr/bin/env python3
"""Hermetic unit tests for DEX//SCULPT + Google Drive Humanoid Catalog bridge."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import dexsculpt_catalog as dc  # noqa: E402


def make_fake_glb(payload: bytes) -> tuple[bytes, int, str]:
    total = 12 + len(payload)
    blob = b"glTF" + struct.pack("<II", 2, total) + payload
    return blob, len(blob), hashlib.sha256(blob).hexdigest()


class DexsculptCatalogTests(unittest.TestCase):
    def _build_temp_catalog_env(self, root: Path) -> tuple[dc.CatalogIndex, dict]:
        blob_knight, size_knight, sha_knight = make_fake_glb(b"KNIGHT_CHARACTER")
        blob_sword, size_sword, sha_sword = make_fake_glb(b"SWORD_ACCESSORY")
        blob_a, size_a, sha_a = make_fake_glb(b"ORIGIN_ZERO_HAIR_A")
        blob_b, size_b, sha_b = make_fake_glb(b"RIGGED_HEAD_HAIR_B_LONGER")
        blob_goblin, size_goblin, sha_goblin = make_fake_glb(b"GOBLIN_VOXEL_CHAR")
        blob_big, _, sha_big = make_fake_glb(b"TOO_BIG")

        meta_dir = root / "data"
        meta_dir.mkdir(parents=True)
        (meta_dir / "humanoidCatalog.json").write_text(
            json.dumps(
                {
                    "summary": {"total_catalog_assets": 6},
                    "records": [
                        {
                            "asset_id": "kaykit-adventurers/character/knight",
                            "display_name": "Knight",
                            "source_id": "kaykit-adventurers",
                            "asset_type": "character",
                            "category": "kaykit_adventurers",
                            "style_tags": ["cc0", "fantasy"],
                            "license_id": "CC0-1.0",
                            "skeleton_family": "kaykit-rig-medium",
                            "joint_count": 23,
                            "processed_glb_basename": "Knight.glb",
                            "processed_glb_bytes": size_knight,
                            "processed_glb_sha256": sha_knight,
                        },
                        {
                            "asset_id": "kaykit-adventurers/accessory/sword_1handed",
                            "display_name": "Sword",
                            "source_id": "kaykit-adventurers",
                            "asset_type": "accessory",
                            "category": "kaykit_adventurers",
                            "style_tags": ["cc0", "weapon"],
                            "license_id": "CC0-1.0",
                            "skeleton_family": None,
                            "joint_count": 0,
                            "processed_glb_basename": "sword_1handed.glb",
                            "processed_glb_bytes": size_sword,
                            "processed_glb_sha256": sha_sword,
                        },
                        {
                            "asset_id": "kaykit-character-animations/rig_medium/rig_medium_general",
                            "display_name": "Rig Medium General",
                            "source_id": "kaykit-character-animations",
                            "asset_type": "animation_pack",
                            "category": "animations",
                            "style_tags": ["cc0", "animations"],
                            "license_id": "CC0-1.0",
                            "skeleton_family": "kaykit-rig-medium",
                            "joint_count": 23,
                            "processed_glb_basename": "Rig_Medium_General.glb",
                            "processed_glb_bytes": size_sword,
                            "processed_glb_sha256": sha_sword,
                        },
                        {
                            "asset_id": "quaternius-universal-base-characters-standard/hairstyle_origin_0/hair_long",
                            "display_name": "Hair Long Origin 0",
                            "source_id": "quaternius-universal-base-characters-standard",
                            "asset_type": "hairstyle_origin_0",
                            "skeleton_family": "None",
                            "processed_glb_basename": "hair_long.glb",
                            "processed_glb_bytes": size_a,
                            "processed_glb_sha256": sha_a,
                        },
                        {
                            "asset_id": "quaternius-universal-base-characters-standard/hairstyle_rigged_head/hair_long",
                            "display_name": "Hair Long Rigged",
                            "source_id": "quaternius-universal-base-characters-standard",
                            "asset_type": "hairstyle_rigged_head",
                            "skeleton_family": "quaternius-universal-65",
                            "processed_glb_basename": "hair_long.glb",
                            "processed_glb_bytes": size_b,
                            "processed_glb_sha256": sha_b,
                        },
                        {
                            "asset_id": "quaternius-cube-world-kit/character/goblin",
                            "display_name": "Goblin",
                            "source_id": "quaternius-cube-world-kit",
                            "asset_type": "character",
                            "skeleton_family": "quaternius-cube-biped-7",
                            "processed_glb_basename": "goblin.glb",
                            "processed_glb_bytes": size_goblin,
                            "processed_glb_sha256": sha_goblin,
                        },
                        {
                            "asset_id": "test/oversize",
                            "display_name": "Too Big",
                            "source_id": "quaternius-cube-world-kit",
                            "asset_type": "character",
                            "skeleton_family": "None",
                            "processed_glb_basename": "big.glb",
                            "processed_glb_bytes": 999999,
                            "processed_glb_sha256": sha_big,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        (meta_dir / "humanoidSources.json").write_text(
            json.dumps(
                {
                    "sources": [
                        {
                            "id": "kaykit-adventurers",
                            "name": "KayKit Adventurers",
                            "license": "CC0-1.0",
                            "official_url": "https://example.org/kaykit",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (meta_dir / "humanoidCompatibility.json").write_text(
            json.dumps(
                {
                    "skeleton_families": {
                        "kaykit-rig-medium": {
                            "joint_count": 23,
                            "member_sources": [
                                "kaykit-adventurers",
                                "kaykit-character-animations (Rig_Medium & Mannequin_Medium)",
                            ],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        cache_dir = root / "VerifiedModels"
        (cache_dir / "kaykit-adventurers").mkdir(parents=True)
        (cache_dir / "kaykit-adventurers" / "Knight.glb").write_bytes(blob_knight)
        (cache_dir / "kaykit-adventurers" / "sword_1handed.glb").write_bytes(blob_sword)

        archive_dir = root / "ARCHIVE"
        ubc_dir = archive_dir / "2026-11-14" / "processed-glb" / "quaternius" / "universal-base-characters-standard"
        (ubc_dir / "hair_origin_0").mkdir(parents=True)
        (ubc_dir / "hair_rigged_head").mkdir(parents=True)
        (ubc_dir / "hair_origin_0" / "hair_long.glb").write_bytes(blob_a)
        (ubc_dir / "hair_rigged_head" / "hair_long.glb").write_bytes(blob_b)
        cube_dir = archive_dir / "2026-11-14_expansion" / "processed-glb" / "quaternius-cube-world-kit"
        cube_dir.mkdir(parents=True)
        (cube_dir / "goblin.glb").write_bytes(blob_goblin)

        launcher = root / "fake-mcp-launcher.sh"
        launcher.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")

        cfg = {
            "schema_version": 1,
            "metadata_dir": str(meta_dir),
            "verified_cache_dir": str(cache_dir),
            "gdrive_archive_dir": str(archive_dir),
            "remote_host": "render-host",
            "remote_staging_dir": "/remote/catalog-cache",
            "mcp_launcher": str(launcher),
            "max_asset_bytes": 500,
            "min_local_free_gib": 0.01,
            "min_remote_free_gib": 0.01,
            "drive_read_timeout_seconds": 10,
        }
        return dc.CatalogIndex(meta_dir), cfg

    def test_archive_candidate_roots_mapping(self) -> None:
        base = Path("/archive")
        self.assertEqual(
            dc.archive_candidate_roots(base, "microsoft-rocketbox"),
            [base / "2026-11-13" / "processed-glb"],
        )
        self.assertEqual(
            dc.archive_candidate_roots(base, "kaykit-adventurers"),
            [base / "2026-11-14" / "processed-glb" / "kaykit" / "adventurers"],
        )
        self.assertEqual(
            dc.archive_candidate_roots(base, "quaternius-cube-world-kit"),
            [
                base / "2026-11-14" / "processed-glb" / "quaternius" / "cube-world-kit",
                base / "2026-11-14_expansion" / "processed-glb" / "quaternius-cube-world-kit",
            ],
        )
        self.assertEqual(
            dc.archive_candidate_roots(base, "polygonalmind-100-avatars-r2"),
            [base / "2026-11-14_expansion" / "processed-glb" / "polygonalmind-100-avatars-r2"],
        )

    def test_search_sources_info_and_compatible_lookup(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp).resolve()
            index, cfg = self._build_temp_catalog_env(root)
            cache_dir = Path(cfg["verified_cache_dir"])

            knights = index.search(query="knight", source_id="kaykit-adventurers", cache_dir=cache_dir)
            self.assertEqual(len(knights), 1)
            self.assertEqual(knights[0]["availability"], "CACHED_LOCAL")

            cached_only = index.search(cached_only=True, cache_dir=cache_dir)
            self.assertEqual(len(cached_only), 2)

            info = index.info("kaykit-adventurers/character/knight", cache_dir=cache_dir)
            self.assertEqual(info["compatibility"]["joint_count"], 23)
            self.assertEqual(info["source_info"]["license"], "CC0-1.0")

            compat = index.compatible("kaykit-adventurers/character/knight", limit=50, cache_dir=cache_dir)
            self.assertEqual(compat["skeleton_family"], "kaykit-rig-medium")
            compat_ids = {r["asset_id"] for r in compat["items"]}
            self.assertIn("kaykit-adventurers/accessory/sword_1handed", compat_ids)
            self.assertIn("kaykit-character-animations/rig_medium/rig_medium_general", compat_ids)

            sources = index.sources(cache_dir=cache_dir)
            by_sid = {s["source_id"]: s for s in sources}
            self.assertEqual(by_sid["kaykit-adventurers"]["cached_local"], 2)

    def test_validate_glb_v2_header(self) -> None:
        good, _, _ = make_fake_glb(b"JSON{}")
        dc.validate_glb_v2_header(good)

        with self.assertRaises(ValueError):
            dc.validate_glb_v2_header(b"BAD!" + good[4:])
        with self.assertRaises(ValueError):
            dc.validate_glb_v2_header(b"glTF" + struct.pack("<II", 1, len(good)) + b"JSON{}")
        with self.assertRaises(ValueError):
            dc.validate_glb_v2_header(b"glTF" + struct.pack("<II", 2, len(good) + 4) + b"JSON{}")

    def test_resolve_prefers_local_cache_and_disambiguates_duplicate_basenames(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp).resolve()
            index, cfg = self._build_temp_catalog_env(root)

            with self.assertRaises(ValueError):
                dc.resolve_asset(index, cfg, "test/oversize")

            res_b = dc.resolve_asset(
                index,
                cfg,
                "quaternius-universal-base-characters-standard/hairstyle_rigged_head/hair_long",
                cache_local=True,
            )
            self.assertEqual(res_b["resolution_source"], "ARCHIVE_GOOGLE_DRIVE")
            self.assertIn("hair_rigged_head", res_b["source_path"])
            cached_file = (
                Path(cfg["verified_cache_dir"])
                / "quaternius-universal-base-characters-standard"
                / "hair_long.glb"
            )
            self.assertTrue(cached_file.is_file())

            with mock.patch.object(dc, "find_named_files", side_effect=AssertionError("Archive scanned unexpectedly")):
                res_b_cached = dc.resolve_asset(
                    index,
                    cfg,
                    "quaternius-universal-base-characters-standard/hairstyle_rigged_head/hair_long",
                )
                self.assertEqual(res_b_cached["resolution_source"], "CACHED_LOCAL")

            res_a = dc.resolve_asset(
                index,
                cfg,
                "quaternius-universal-base-characters-standard/hairstyle_origin_0/hair_long",
                cache_local=False,
            )
            self.assertEqual(res_a["resolution_source"], "ARCHIVE_GOOGLE_DRIVE")
            self.assertIn("hair_origin_0", res_a["source_path"])
            with self.assertRaises(ValueError):
                dc.resolve_asset(
                    index,
                    cfg,
                    "quaternius-universal-base-characters-standard/hairstyle_origin_0/hair_long",
                    cache_local=True,
                )

            sym_src = Path(cfg["verified_cache_dir"]) / "evil"
            sym_src.mkdir(parents=True)
            (sym_src / "link.glb").symlink_to(cached_file)
            cached_file.unlink()
            cached_file.symlink_to(sym_src / "link.glb")
            archive_file_b = Path(res_b["source_path"])
            archive_file_b.unlink()
            archive_file_b.symlink_to(sym_src / "link.glb")
            with self.assertRaises(FileNotFoundError):
                dc.resolve_asset(
                    index,
                    cfg,
                    "quaternius-universal-base-characters-standard/hairstyle_rigged_head/hair_long",
                )

    def test_bounded_read_retries_after_timeout_and_gdrive_fallback(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp).resolve()
            blob, exp_bytes, exp_sha = make_fake_glb(b"RETRY_AND_GDRIVE_OK")
            src = root / "goblin.glb"
            src.write_bytes(blob)

            attempts = []

            def fake_retry_run(cmd, *args, **kwargs):
                attempts.append(cmd)
                if len(attempts) == 1:
                    raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{exp_bytes} {exp_sha}\n", stderr="")

            with mock.patch.object(dc.subprocess, "run", side_effect=fake_retry_run), mock.patch.object(dc.time, "sleep"):
                got_bytes, got_sha = dc.read_verified_file_bounded(src, exp_bytes, exp_sha, 15, max_attempts=3)
            self.assertEqual((got_bytes, got_sha), (exp_bytes, exp_sha))
            self.assertEqual(len(attempts), 2)

            dest = root / "staged_goblin.glb"
            seen_cmds = []

            def fake_fallback_run(cmd, *args, **kwargs):
                seen_cmds.append(cmd)
                if cmd[0] == sys.executable:
                    raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)
                if cmd[0] == "xattr":
                    return subprocess.CompletedProcess(cmd, 0, stdout="drive-item-id-123\n", stderr="")
                if cmd[0] == "/usr/local/bin/gdrive":
                    out_idx = cmd.index("--out") + 1
                    Path(cmd[out_idx]).write_bytes(blob)
                    return subprocess.CompletedProcess(cmd, 0, stdout="downloaded\n", stderr="")
                raise AssertionError(f"Unexpected command: {cmd}")

            with mock.patch.object(dc.shutil, "which", return_value="/usr/local/bin/gdrive"), mock.patch.object(
                dc.subprocess, "run", side_effect=fake_fallback_run
            ), mock.patch.object(dc.time, "sleep"):
                got_bytes2, got_sha2 = dc.read_verified_file_bounded(
                    src, exp_bytes, exp_sha, 15, dest_copy=dest, max_attempts=3
                )
            self.assertEqual((got_bytes2, got_sha2), (exp_bytes, exp_sha))
            self.assertEqual(dest.read_bytes(), blob)
            self.assertEqual(sum(1 for c in seen_cmds if c[0] == sys.executable), 3)
            self.assertTrue(any(c[0] == "/usr/local/bin/gdrive" and "drive-item-id-123" in c for c in seen_cmds))

    def test_stage_to_remote_and_import_to_blender_mocked(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp).resolve()
            index, cfg = self._build_temp_catalog_env(root)
            asset_id = "quaternius-cube-world-kit/character/goblin"
            rec = index.get(asset_id)

            scp_calls = []

            def fake_ssh_miss(host, script, args, timeout=60):
                if script is dc.REMOTE_STAGE_PROBE:
                    return {"exists": False, "free_gib": 6.0}
                if script is dc.REMOTE_VERIFY_PROMOTE:
                    return {"bytes": rec["processed_glb_bytes"], "sha256": rec["processed_glb_sha256"], "free_gib": 6.0}
                raise AssertionError("Unexpected script")

            def fake_subproc_run(cmd, *args, **kwargs):
                if cmd[0] == "scp":
                    scp_calls.append(cmd)
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

            with mock.patch.object(dc, "_ssh_python", side_effect=fake_ssh_miss), mock.patch.object(
                dc.subprocess, "run", side_effect=fake_subproc_run
            ):
                staged = dc.stage_to_remote(index, cfg, asset_id)
            self.assertEqual(staged["staging"]["status"], "REMOTE_SCP_VERIFIED")
            self.assertEqual(staged["resolution"]["resolution_source"], "ARCHIVE_GOOGLE_DRIVE")
            self.assertEqual(len(scp_calls), 1)

            executed_codes = []

            class FakeMCPClient:
                def __init__(self, *_a, **_kw):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *_a):
                    return None

                def initialize(self):
                    return {}

                def call_tool(self, _name, arguments):
                    executed_codes.append(arguments["code"])
                    return {
                        "isError": False,
                        "content": [
                            {
                                "type": "text",
                                "text": 'CATALOG_IMPORT_JSON:{"collection":"Catalog_Goblin","root_empty":"CatalogRoot_Goblin","imported_object_count":2,"mesh_count":1,"armatures":[{"name":"EnemyArmature","bones":7}],"new_actions":[],"world_bbox":{"min":[0,0,0],"max":[1,1,1],"size":[1,1,1]},"saved_blend":null}',
                            }
                        ],
                    }

            with mock.patch.object(
                dc,
                "_ssh_python",
                return_value={
                    "exists": True,
                    "bytes": rec["processed_glb_bytes"],
                    "sha256": rec["processed_glb_sha256"],
                    "free_gib": 6.0,
                },
            ), mock.patch.object(dc.subprocess, "run", side_effect=AssertionError("SCP should be skipped")), mock.patch.object(
                dc, "StdioMCPClient", FakeMCPClient
            ):
                imp = dc.import_to_blender(
                    index,
                    cfg,
                    asset_id,
                    clear_scene=True,
                    location=(1.2, 0.0, 0.0),
                    scale=0.55,
                )
            self.assertEqual(imp["staging"]["status"], "REMOTE_ALREADY_STAGED")
            self.assertEqual(imp["blender_import"]["mesh_count"], 1)
            self.assertEqual(len(executed_codes), 1)
            self.assertNotIn("read_factory_settings", executed_codes[0])
            self.assertIn("CatalogRoot_", executed_codes[0])
            self.assertIn("Catalog_", executed_codes[0])
            self.assertIn("glTF_not_exported", executed_codes[0])
            self.assertIn("custom_shape", executed_codes[0])

            # Missing MCP launcher fails loudly
            cfg_no_launcher = dict(cfg)
            cfg_no_launcher.pop("mcp_launcher", None)
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError):
                    dc.import_to_blender(index, cfg_no_launcher, asset_id)


if __name__ == "__main__":
    unittest.main()
