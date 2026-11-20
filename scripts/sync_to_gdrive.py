#!/usr/bin/env python3
"""Sync verified local outputs into a private Google Drive for Desktop mount.

Routes verified outputs by way of the local workstation into a user-configured
Google Drive for Desktop destination folder (`~/.config/dex-video-code/gdrive-sync.json`
or `DEX_GDRIVE_SYNC_DEST`), verifying SHA-256 digests and macOS File Provider upload
status (`fileproviderctl evaluate` + `com.google.drivefs.item-id#S`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "dex-video-code" / "gdrive-sync.json"
DEFAULT_FOLDER_NAME = "Blender MCP Outputs"
ENV_CONFIG_OVERRIDE = "DEX_GDRIVE_SYNC_CONFIG"
ENV_DEST_OVERRIDE = "DEX_GDRIVE_SYNC_DEST"

_FILEPROVIDER_FLAG_MAP = (
    ("isUploaded", "is_uploaded"),
    ("isUploading", "is_uploading"),
    ("isSyncPaused", "is_sync_paused"),
    ("isTrashed", "is_trashed"),
    ("hasUnresolvedConflicts", "has_unresolved_conflicts"),
    ("isShared", "is_shared"),
)


def sha256_file(path: Path) -> tuple[int, str]:
    """Return exact byte size and lowercase SHA-256 hex digest for a regular file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return path.stat().st_size, h.hexdigest()


def assert_no_symlinks_under(root: Path, target: Path) -> None:
    """Reject if root, any path segment between root and target, or target is a symlink."""
    if root.is_symlink():
        raise ValueError(f"Symlink disallowed at root path: {root}")
    rel = target.relative_to(root)
    cur = root
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise ValueError(f"Symlink disallowed in path: {cur}")


def _discover_default_drive_root() -> Path:
    cloud_dir = Path.home() / "Library" / "CloudStorage"
    candidates: list[Path] = []
    seen_real: set[Path] = set()
    for my_drive in sorted(cloud_dir.glob("GoogleDrive-*/My Drive")):
        if not my_drive.is_dir() or my_drive.is_symlink():
            continue
        for child in sorted(my_drive.iterdir()):
            if child.name.lower() == "macbook" and child.is_dir() and not child.is_symlink():
                resolved = child.resolve()
                if resolved not in seen_real:
                    seen_real.add(resolved)
                    candidates.append(child)
    if len(candidates) != 1:
        raise RuntimeError(
            f"Google Drive destination not configured. Create {DEFAULT_CONFIG_PATH} (mode 0600) or set {ENV_DEST_OVERRIDE}."
        )
    return candidates[0]


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load private Google Drive destination config, env override, or auto-discovered mount."""
    dest_override = os.environ.get(ENV_DEST_OVERRIDE, "").strip()
    if dest_override:
        dest = Path(dest_override).expanduser()
        return {
            "schema_version": 1,
            "delivery_mode": "google_drive_desktop",
            "drive_parent_root": str(dest.parent),
            "folder_name": dest.name,
            "destination_dir": str(dest),
            "destination_drive_item_id": None,
            "_config_path": None,
        }

    if config_path is not None:
        cfg_file = Path(config_path).expanduser()
        explicit = True
    else:
        env_cfg = os.environ.get(ENV_CONFIG_OVERRIDE, "").strip()
        if env_cfg:
            cfg_file = Path(env_cfg).expanduser()
            explicit = True
        else:
            cfg_file = DEFAULT_CONFIG_PATH
            explicit = False

    if cfg_file.is_file():
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        parent_raw = data.get("drive_parent_root") or data.get("macbook_drive_root")
        if not parent_raw:
            dest_raw = data.get("destination_dir")
            if not dest_raw:
                raise ValueError(f"Config {cfg_file} must specify destination_dir or drive_parent_root")
            dest_dir = Path(dest_raw).expanduser()
            parent_root = dest_dir.parent
            folder_name = data.get("folder_name") or dest_dir.name
        else:
            parent_root = Path(parent_raw).expanduser()
            folder_name = data.get("folder_name") or DEFAULT_FOLDER_NAME
            dest_dir = Path(data.get("destination_dir") or (parent_root / folder_name)).expanduser()
        data["drive_parent_root"] = str(parent_root)
        data["folder_name"] = folder_name
        data["destination_dir"] = str(dest_dir)
        data["_config_path"] = str(cfg_file)
        return data

    if explicit:
        raise FileNotFoundError(f"Google Drive sync config file not found: {cfg_file}")

    parent_root = _discover_default_drive_root()
    return {
        "schema_version": 1,
        "delivery_mode": "google_drive_desktop",
        "drive_parent_root": str(parent_root),
        "folder_name": DEFAULT_FOLDER_NAME,
        "destination_dir": str(parent_root / DEFAULT_FOLDER_NAME),
        "destination_drive_item_id": None,
        "_config_path": None,
    }


def _persist_destination_item_id(cfg: dict[str, Any], folder_item_id: str | None) -> None:
    cfg_path_raw = cfg.get("_config_path")
    if not cfg_path_raw or not folder_item_id:
        return
    cfg_file = Path(cfg_path_raw)
    if not cfg_file.is_file():
        return
    if cfg.get("destination_drive_item_id") == folder_item_id:
        return
    persisted = {k: v for k, v in cfg.items() if not k.startswith("_")}
    persisted["destination_drive_item_id"] = folder_item_id
    fd = os.open(cfg_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (json.dumps(persisted, indent=2) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(cfg_file, 0o600)


def parse_fileprovider_evaluate(output: str) -> dict[str, bool]:
    """Parse integer sync/upload flags from `fileproviderctl evaluate` within `fileproviderItems`."""
    section = output
    items_idx = output.find("fileproviderItems =")
    if items_idx != -1:
        section = output[items_idx:]
        actions_match = re.search(r"\n\s*Actions:\s*\n", section)
        if actions_match:
            section = section[: actions_match.start()]

    parsed: dict[str, bool] = {}
    for raw_key, py_key in _FILEPROVIDER_FLAG_MAP:
        match = re.search(rf"^\s*{re.escape(raw_key)}\s*=\s*(\d+)\s*;", section, re.MULTILINE)
        parsed[py_key] = bool(int(match.group(1))) if match else False
    return parsed


def inspect_drivefs_item(path: Path) -> dict[str, Any]:
    """Query macOS File Provider flags and Google Drive item ID xattr for a synced item."""
    eval_proc = subprocess.run(
        ["fileproviderctl", "evaluate", str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    flags = (
        parse_fileprovider_evaluate(eval_proc.stdout)
        if eval_proc.returncode == 0
        else {py_key: False for _, py_key in _FILEPROVIDER_FLAG_MAP}
    )
    xattr_proc = subprocess.run(
        ["xattr", "-p", "com.google.drivefs.item-id#S", str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    item_id = xattr_proc.stdout.strip() if xattr_proc.returncode == 0 and xattr_proc.stdout.strip() else None
    return {**flags, "drive_item_id": item_id}


def _drivefs_upload_complete(state: dict[str, Any]) -> bool:
    return (
        state.get("is_uploaded") is True
        and state.get("is_uploading") is False
        and state.get("has_unresolved_conflicts") is False
        and state.get("is_trashed") is False
        and bool(state.get("drive_item_id"))
    )


def wait_for_drivefs_upload(
    path: Path,
    timeout_seconds: int = 180,
    poll_interval: float = 1.0,
    inspector: Callable[[Path], dict[str, Any]] = inspect_drivefs_item,
) -> dict[str, Any]:
    """Poll macOS File Provider until Google Drive upload completes with a cloud item ID."""
    deadline = time.monotonic() + max(0, timeout_seconds)
    last_state: dict[str, Any] = {}
    while True:
        last_state = inspector(path)
        if _drivefs_upload_complete(last_state):
            return last_state
        now = time.monotonic()
        if now >= deadline:
            raise TimeoutError(f"Timed out waiting for DriveFS upload of {path}: last_state={last_state}")
        time.sleep(min(poll_interval, max(0.05, deadline - now)))


def ensure_destination_root(
    cfg: dict[str, Any],
    inspector: Callable[[Path], dict[str, Any]] = inspect_drivefs_item,
    check_drivefs: bool = True,
) -> Path:
    """Validate Google Drive parent mount health and ensure destination folder exists."""
    parent_root = Path(cfg["drive_parent_root"]).expanduser()
    if parent_root.is_symlink():
        raise ValueError(f"Google Drive parent root must not be a symlink: {parent_root}")
    if not parent_root.is_dir():
        raise FileNotFoundError(f"Google Drive parent root not found: {parent_root}")

    if check_drivefs:
        root_state = inspector(parent_root)
        if root_state.get("is_sync_paused"):
            raise RuntimeError(f"Google Drive sync is paused on {parent_root}")
        if root_state.get("is_trashed"):
            raise RuntimeError(f"Google Drive parent root is trashed: {parent_root}")

    dest_dir = Path(cfg["destination_dir"]).expanduser()
    assert_no_symlinks_under(parent_root, dest_dir)
    dest_dir.mkdir(exist_ok=True)
    assert_no_symlinks_under(parent_root, dest_dir)
    if not dest_dir.is_dir():
        raise RuntimeError(f"Destination is not a directory: {dest_dir}")
    return dest_dir


def copy_and_verify_one(src: Path, dst: Path) -> dict[str, Any]:
    """Copy one regular file directly to dst (no temp files in DriveFS) and verify SHA-256."""
    if src.is_symlink():
        raise ValueError(f"Refusing symlink source: {src}")
    src_lstat = src.lstat()
    if not stat.S_ISREG(src_lstat.st_mode):
        raise ValueError(f"Source is not a regular file: {src}")

    src_bytes, src_sha = sha256_file(src)
    dst_existed = dst.exists() or dst.is_symlink()
    if dst.is_symlink():
        raise ValueError(f"Refusing symlink destination: {dst}")
    if dst.exists():
        if not stat.S_ISREG(dst.lstat().st_mode):
            raise ValueError(f"Destination exists and is not a regular file: {dst}")
        dst_bytes, dst_sha = sha256_file(dst)
        if dst_bytes == src_bytes and dst_sha == src_sha:
            return {"bytes": src_bytes, "sha256": src_sha, "status": "ALREADY_SYNCED"}

    dst.parent.mkdir(parents=True, exist_ok=True)
    # Write directly via copyfile without xattrs so File Provider never uploads temp files or quarantine xattrs.
    shutil.copyfile(src, dst)
    os.utime(dst, (src_lstat.st_atime, src_lstat.st_mtime))

    got_bytes, got_sha = sha256_file(dst)
    if got_bytes != src_bytes or got_sha != src_sha:
        raise RuntimeError(
            f"SHA-256 verification failed after copying {src} -> {dst}: "
            f"expected=({src_bytes}, {src_sha}), got=({got_bytes}, {got_sha})"
        )

    return {
        "bytes": src_bytes,
        "sha256": src_sha,
        "status": "UPDATED" if dst_existed else "COPIED",
    }


def _iter_regular_files(base_dir: Path, prefix: str = "") -> list[tuple[Path, str]]:
    if base_dir.is_symlink():
        raise ValueError(f"Source directory must not be a symlink: {base_dir}")
    if not base_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {base_dir}")

    collected: list[tuple[Path, str]] = []
    for root, dirs, files in os.walk(base_dir, followlinks=False):
        root_path = Path(root)
        kept_dirs: list[str] = []
        for d in sorted(dirs):
            if d.startswith("."):
                continue
            d_path = root_path / d
            if d_path.is_symlink():
                raise ValueError(f"Symlink disallowed in source directory: {d_path}")
            kept_dirs.append(d)
        dirs[:] = kept_dirs

        for f in sorted(files):
            if f.startswith("."):
                continue
            f_path = root_path / f
            if f_path.is_symlink():
                raise ValueError(f"Symlink disallowed in source tree: {f_path}")
            rel = f_path.relative_to(base_dir)
            rel_str = (Path(prefix) / rel).as_posix() if prefix else rel.as_posix()
            collected.append((f_path, rel_str))
    return collected


def _sync_entries(
    entries: list[tuple[Path, str]],
    cfg: dict[str, Any],
    dest_dir: Path,
    wait_upload_seconds: int,
    check_drivefs: bool,
    inspector: Callable[[Path], dict[str, Any]],
    receipt_dir: Path | None,
) -> dict[str, Any]:
    if not entries:
        raise ValueError("No eligible files found to sync")

    copied_records: list[dict[str, Any]] = []
    for src, rel_path in entries:
        dst = dest_dir / rel_path
        assert_no_symlinks_under(dest_dir, dst)
        copy_res = copy_and_verify_one(src, dst)
        copied_records.append(
            {
                "source_path": str(src),
                "relative_path": rel_path,
                "destination_path": str(dst),
                **copy_res,
            }
        )

    dest_state: dict[str, Any] = {}
    if check_drivefs:
        if wait_upload_seconds > 0:
            dest_state = wait_for_drivefs_upload(dest_dir, timeout_seconds=wait_upload_seconds, inspector=inspector)
        else:
            dest_state = inspector(dest_dir)
        _persist_destination_item_id(cfg, dest_state.get("drive_item_id"))

        for rec in copied_records:
            dst = Path(rec["destination_path"])
            if wait_upload_seconds > 0:
                f_state = wait_for_drivefs_upload(dst, timeout_seconds=wait_upload_seconds, inspector=inspector)
            else:
                f_state = inspector(dst)
            item_id = f_state.get("drive_item_id")
            rec["drive_item_id"] = item_id
            rec["drive_url"] = f"https://drive.google.com/file/d/{item_id}/view" if item_id else None
            rec["is_uploaded"] = bool(f_state.get("is_uploaded"))
            rec["is_uploading"] = bool(f_state.get("is_uploading"))
            rec["has_unresolved_conflicts"] = bool(f_state.get("has_unresolved_conflicts"))
            rec["is_shared"] = bool(f_state.get("is_shared"))
    else:
        for rec in copied_records:
            rec["drive_item_id"] = None
            rec["drive_url"] = None
            rec["is_uploaded"] = None
            rec["is_shared"] = None

    folder_id = dest_state.get("drive_item_id") or cfg.get("destination_drive_item_id")
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else None

    summary: dict[str, Any] = {
        "schema_version": "dex-video-code-gdrive-sync.v1",
        "synced_at_utc": datetime.now(timezone.utc).isoformat(),
        "delivery_mode": cfg.get("delivery_mode", "google_drive_desktop"),
        "folder_name": cfg.get("folder_name", DEFAULT_FOLDER_NAME),
        "destination_dir": str(dest_dir),
        "destination_drive_item_id": folder_id,
        "destination_drive_url": folder_url,
        "folder_is_uploaded": dest_state.get("is_uploaded") if check_drivefs else None,
        "folder_is_shared": dest_state.get("is_shared") if check_drivefs else None,
        "file_count": len(copied_records),
        "files": copied_records,
    }

    if receipt_dir is not None:
        receipt_path = receipt_dir / ".gdrive-sync-receipt.json"
        receipt_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        summary["receipt_path"] = str(receipt_path)
    return summary


def sync_all_outputs(
    outputs_root: Path,
    config_path: Path | None = None,
    wait_upload_seconds: int = 180,
    check_drivefs: bool = True,
    inspector: Callable[[Path], dict[str, Any]] = inspect_drivefs_item,
) -> dict[str, Any]:
    """Sync every run folder under outputs_root into the configured Google Drive destination."""
    outputs_root = Path(outputs_root).expanduser().resolve()
    cfg = load_config(config_path)
    dest_dir = ensure_destination_root(cfg, inspector=inspector, check_drivefs=check_drivefs)
    entries = _iter_regular_files(outputs_root)
    return _sync_entries(
        entries=entries,
        cfg=cfg,
        dest_dir=dest_dir,
        wait_upload_seconds=wait_upload_seconds,
        check_drivefs=check_drivefs,
        inspector=inspector,
        receipt_dir=outputs_root,
    )


def sync_directory(
    run_dir: Path,
    run_name: str | None = None,
    config_path: Path | None = None,
    wait_upload_seconds: int = 180,
    check_drivefs: bool = True,
    inspector: Callable[[Path], dict[str, Any]] = inspect_drivefs_item,
) -> dict[str, Any]:
    """Sync one local run directory into `<destination_dir>/<run_name or run_dir.name>/`."""
    run_dir = Path(run_dir).expanduser().resolve()
    folder_prefix = run_name or run_dir.name
    if Path(folder_prefix).is_absolute() or ".." in Path(folder_prefix).parts:
        raise ValueError(f"Invalid run_name: {folder_prefix}")
    cfg = load_config(config_path)
    dest_dir = ensure_destination_root(cfg, inspector=inspector, check_drivefs=check_drivefs)
    entries = _iter_regular_files(run_dir, prefix=folder_prefix)
    return _sync_entries(
        entries=entries,
        cfg=cfg,
        dest_dir=dest_dir,
        wait_upload_seconds=wait_upload_seconds,
        check_drivefs=check_drivefs,
        inspector=inspector,
        receipt_dir=run_dir,
    )


def sync_file(
    file_path: Path,
    subdir: str | None = None,
    config_path: Path | None = None,
    wait_upload_seconds: int = 180,
    check_drivefs: bool = True,
    inspector: Callable[[Path], dict[str, Any]] = inspect_drivefs_item,
) -> dict[str, Any]:
    """Sync one regular local file into `<destination_dir>[/subdir]/<filename>`."""
    raw_path = Path(file_path).expanduser()
    if raw_path.is_symlink():
        raise ValueError(f"Refusing symlink source: {raw_path}")
    resolved = raw_path.resolve()
    if subdir is not None and (Path(subdir).is_absolute() or ".." in Path(subdir).parts or subdir == ""):
        raise ValueError(f"Invalid subdir: {subdir}")
    cfg = load_config(config_path)
    dest_dir = ensure_destination_root(cfg, inspector=inspector, check_drivefs=check_drivefs)
    rel_path = (Path(subdir) / resolved.name).as_posix() if subdir else resolved.name
    return _sync_entries(
        entries=[(resolved, rel_path)],
        cfg=cfg,
        dest_dir=dest_dir,
        wait_upload_seconds=wait_upload_seconds,
        check_drivefs=check_drivefs,
        inspector=inspector,
        receipt_dir=None,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--all-outputs", type=Path, help="Outputs root containing all run subfolders")
    target.add_argument("--run-dir", type=Path, help="Single local run output directory to sync")
    target.add_argument("--file", type=Path, help="Single local file to sync")
    parser.add_argument("--run-name", default=None, help="Target subfolder name under destination folder (for --run-dir)")
    parser.add_argument("--subdir", default=None, help="Optional target subfolder under destination folder (for --file)")
    parser.add_argument("--config", type=Path, default=None, help="Optional override path to gdrive-sync.json")
    parser.add_argument("--wait-upload-seconds", type=int, default=180, help="Max seconds to wait for DriveFS upload verification")
    parser.add_argument("--no-wait-upload", action="store_true", help="Copy and verify SHA-256 without waiting on DriveFS upload")
    args = parser.parse_args()

    wait_seconds = 0 if args.no_wait_upload else args.wait_upload_seconds
    if args.all_outputs is not None:
        summary = sync_all_outputs(args.all_outputs, config_path=args.config, wait_upload_seconds=wait_seconds)
    elif args.run_dir is not None:
        summary = sync_directory(args.run_dir, run_name=args.run_name, config_path=args.config, wait_upload_seconds=wait_seconds)
    else:
        summary = sync_file(args.file, subdir=args.subdir, config_path=args.config, wait_upload_seconds=wait_seconds)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
