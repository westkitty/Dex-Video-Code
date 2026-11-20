#!/usr/bin/env python3
"""Hermetic unit tests for DriveFS output sync and opt-in transfer_verified_file hook."""

from __future__ import annotations

import base64
import hashlib
import json
import os
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

import sync_to_gdrive  # noqa: E402
import transfer_verified_file  # noqa: E402


SAMPLE_EVALUATE_OUTPUT = """Evaluating actions against {
    domainUserInfo =     {
        "CONTEXT_MENU_CREATE_SHARED_DRIVE" = 1;
    };
    fileproviderItems =     (
                {
            capabilities = 536870975;
            displayName = "sample_hero.png";
            hasUnresolvedConflicts = 0;
            isShared = 0;
            isSyncPaused = 0;
            isTrashed = 0;
            isUploaded = 1;
            isUploading = 0;
        }
    );
}

Actions:
ACTION_OPEN: fileproviderItems.@count == 1 - YES
"""


class SyncToGdriveTests(unittest.TestCase):
    def _write_test_config(self, root: Path) -> tuple[Path, Path, Path]:
        parent_root = root / "My Drive" / "workstation"
        parent_root.mkdir(parents=True)
        dest_dir = parent_root / "Blender MCP Outputs"
        cfg_path = root / "gdrive-sync.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "delivery_mode": "google_drive_desktop",
                    "drive_parent_root": str(parent_root),
                    "folder_name": "Blender MCP Outputs",
                    "destination_dir": str(dest_dir),
                    "destination_drive_item_id": None,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(cfg_path, 0o600)
        return parent_root, dest_dir, cfg_path

    def test_parse_fileprovider_evaluate(self) -> None:
        parsed = sync_to_gdrive.parse_fileprovider_evaluate(SAMPLE_EVALUATE_OUTPUT)
        self.assertEqual(
            parsed,
            {
                "is_uploaded": True,
                "is_uploading": False,
                "is_sync_paused": False,
                "is_trashed": False,
                "has_unresolved_conflicts": False,
                "is_shared": False,
            },
        )

        paused_sample = SAMPLE_EVALUATE_OUTPUT.replace("isSyncPaused = 0;", "isSyncPaused = 1;").replace(
            "isUploaded = 1;", "isUploaded = 0;"
        )
        paused = sync_to_gdrive.parse_fileprovider_evaluate(paused_sample)
        self.assertTrue(paused["is_sync_paused"])
        self.assertFalse(paused["is_uploaded"])

    def test_sync_all_outputs_copies_skips_dotfiles_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp).resolve()
            _, dest_dir, cfg_path = self._write_test_config(root)

            outputs_root = root / "outputs"
            run_a = outputs_root / "scene_final"
            run_a.mkdir(parents=True)
            hero = run_a / "hero.png"
            hero.write_bytes(b"png-bytes-v1")
            (run_a / ".DS_Store").write_bytes(b"finder-noise")
            (outputs_root / ".gdrive-sync-receipt.json").write_text("{}", encoding="utf-8")

            run_b = outputs_root / "qa" / "nested"
            run_b.mkdir(parents=True)
            qa_img = run_b / "qa_frame26.png"
            qa_img.write_bytes(b"qa-frame-data")

            def fake_inspector(p: Path) -> dict:
                return {
                    "is_uploaded": True,
                    "is_uploading": False,
                    "is_sync_paused": False,
                    "is_trashed": False,
                    "has_unresolved_conflicts": False,
                    "is_shared": False,
                    "drive_item_id": f"drive-id-{p.name}",
                }

            first = sync_to_gdrive.sync_all_outputs(
                outputs_root,
                config_path=cfg_path,
                wait_upload_seconds=5,
                check_drivefs=True,
                inspector=fake_inspector,
            )
            self.assertEqual(first["file_count"], 2)
            statuses = {f["relative_path"]: f["status"] for f in first["files"]}
            self.assertEqual(
                statuses,
                {
                    "scene_final/hero.png": "COPIED",
                    "qa/nested/qa_frame26.png": "COPIED",
                },
            )
            self.assertFalse((dest_dir / "scene_final" / ".DS_Store").exists())
            self.assertFalse((dest_dir / ".gdrive-sync-receipt.json").exists())
            self.assertTrue((outputs_root / ".gdrive-sync-receipt.json").is_file())
            self.assertEqual((dest_dir / "scene_final" / "hero.png").read_bytes(), b"png-bytes-v1")

            persisted = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["destination_drive_item_id"], "drive-id-Blender MCP Outputs")
            self.assertEqual(os.stat(cfg_path).st_mode & 0o777, 0o600)

            second = sync_to_gdrive.sync_all_outputs(
                outputs_root,
                config_path=cfg_path,
                wait_upload_seconds=5,
                check_drivefs=True,
                inspector=fake_inspector,
            )
            self.assertEqual(
                {f["relative_path"]: f["status"] for f in second["files"]},
                {
                    "scene_final/hero.png": "ALREADY_SYNCED",
                    "qa/nested/qa_frame26.png": "ALREADY_SYNCED",
                },
            )

            hero.write_bytes(b"png-bytes-v2-updated")
            third = sync_to_gdrive.sync_all_outputs(
                outputs_root,
                config_path=cfg_path,
                wait_upload_seconds=5,
                check_drivefs=True,
                inspector=fake_inspector,
            )
            self.assertEqual(
                {f["relative_path"]: f["status"] for f in third["files"]},
                {
                    "scene_final/hero.png": "UPDATED",
                    "qa/nested/qa_frame26.png": "ALREADY_SYNCED",
                },
            )
            self.assertEqual((dest_dir / "scene_final" / "hero.png").read_bytes(), b"png-bytes-v2-updated")

    def test_rejects_symlinks_and_paused_drivefs(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp).resolve()
            _, dest_dir, cfg_path = self._write_test_config(root)

            outputs_root = root / "outputs"
            run_dir = outputs_root / "run1"
            run_dir.mkdir(parents=True)
            real_file = root / "secret.txt"
            real_file.write_text("nope", encoding="utf-8")
            (run_dir / "link.txt").symlink_to(real_file)

            with self.assertRaises(ValueError):
                sync_to_gdrive.sync_all_outputs(
                    outputs_root,
                    config_path=cfg_path,
                    check_drivefs=False,
                )

            (run_dir / "link.txt").unlink()
            (run_dir / "good.png").write_bytes(b"good")
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / "run1").symlink_to(root)
            with self.assertRaises(ValueError):
                sync_to_gdrive.sync_all_outputs(
                    outputs_root,
                    config_path=cfg_path,
                    check_drivefs=False,
                )
            (dest_dir / "run1").unlink()

            def paused_inspector(_p: Path) -> dict:
                return {
                    "is_uploaded": False,
                    "is_uploading": False,
                    "is_sync_paused": True,
                    "is_trashed": False,
                    "has_unresolved_conflicts": False,
                    "is_shared": False,
                    "drive_item_id": None,
                }

            with self.assertRaises(RuntimeError):
                sync_to_gdrive.sync_all_outputs(
                    outputs_root,
                    config_path=cfg_path,
                    check_drivefs=True,
                    inspector=paused_inspector,
                )
            self.assertFalse((dest_dir / "run1" / "good.png").exists())

    def test_transfer_verified_file_opt_in_gdrive_sync(self) -> None:
        with tempfile.TemporaryDirectory(dir="/private/tmp") as tmp:
            root = Path(tmp).resolve()
            _, _, cfg_path = self._write_test_config(root)
            payload = b"hello-verified-render-output"
            exp_size = len(payload)
            exp_sha = hashlib.sha256(payload).hexdigest()
            manifest = {
                "artifacts": {
                    "hero_png": {
                        "path": "/remote/exports/run1/hero.png",
                        "bytes": exp_size,
                        "sha256": exp_sha,
                    }
                }
            }

            def fake_run(cmd, *args, **kwargs):
                if cmd[0] == "ssh":
                    remote_cmd = cmd[-1]
                    if "open(source,\"r\"" in remote_cmd:
                        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(manifest), stderr="")
                    return subprocess.CompletedProcess(
                        cmd, 0, stdout=json.dumps({"bytes": exp_size, "sha256": exp_sha}), stderr=""
                    )
                if cmd[0] == "scp":
                    Path(cmd[-1]).write_bytes(payload)
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                raise AssertionError(f"Unexpected command: {cmd}")

            # 1. Default behavior when --gdrive-sync-config is omitted: no Drive sync call
            dest_plain = root / "dest_plain"
            dest_plain.mkdir()
            with mock.patch.object(transfer_verified_file.subprocess, "run", side_effect=fake_run), mock.patch.object(
                transfer_verified_file, "sync_directory"
            ) as mock_dir, mock.patch.object(transfer_verified_file, "sync_file") as mock_file:
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "transfer_verified_file.py",
                        "--source-host",
                        "render-host",
                        "--source-user",
                        "transfer-user",
                        "--source-root",
                        "/remote/exports",
                        "--source-path",
                        "/remote/exports/run1/hero.png",
                        "--destination-root",
                        str(dest_plain),
                        "--destination",
                        str(dest_plain / "hero.png"),
                        "--bytes",
                        str(exp_size),
                        "--sha256",
                        exp_sha,
                    ],
                ):
                    rc = transfer_verified_file.main()
                self.assertEqual(rc, 0)
                mock_dir.assert_not_called()
                mock_file.assert_not_called()

            # 2. Opt-in single-file mode calls sync_file
            dest_single = root / "dest_single"
            dest_single.mkdir()
            with mock.patch.object(transfer_verified_file.subprocess, "run", side_effect=fake_run), mock.patch.object(
                transfer_verified_file, "sync_file", return_value={"file_count": 1}
            ) as mock_file:
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "transfer_verified_file.py",
                        "--source-host",
                        "render-host",
                        "--source-user",
                        "transfer-user",
                        "--source-root",
                        "/remote/exports",
                        "--source-path",
                        "/remote/exports/run1/hero.png",
                        "--destination-root",
                        str(dest_single),
                        "--destination",
                        str(dest_single / "hero.png"),
                        "--bytes",
                        str(exp_size),
                        "--sha256",
                        exp_sha,
                        "--gdrive-sync-config",
                        str(cfg_path),
                    ],
                ):
                    rc = transfer_verified_file.main()
                self.assertEqual(rc, 0)
                mock_file.assert_called_once_with(
                    dest_single / "hero.png",
                    subdir="dest_single",
                    config_path=cfg_path,
                    wait_upload_seconds=180,
                )

            # 3. Opt-in manifest mode calls sync_directory
            dest_manifest = root / "dest_manifest"
            dest_manifest.mkdir()
            with mock.patch.object(transfer_verified_file.subprocess, "run", side_effect=fake_run), mock.patch.object(
                transfer_verified_file, "sync_directory", return_value={"file_count": 2}
            ) as mock_dir:
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "transfer_verified_file.py",
                        "--source-host",
                        "render-host",
                        "--source-user",
                        "transfer-user",
                        "--source-root",
                        "/remote/exports",
                        "--manifest-path",
                        "/remote/exports/run1/manifest.json",
                        "--destination-root",
                        str(dest_manifest),
                        "--gdrive-sync-config",
                        str(cfg_path),
                        "--gdrive-subdir",
                        "custom_run",
                        "--gdrive-wait-seconds",
                        "45",
                    ],
                ):
                    rc = transfer_verified_file.main()
                self.assertEqual(rc, 0)
                mock_dir.assert_called_once_with(
                    dest_manifest,
                    run_name="custom_run",
                    config_path=cfg_path,
                    wait_upload_seconds=45,
                )


if __name__ == "__main__":
    unittest.main()
