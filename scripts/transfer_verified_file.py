#!/usr/bin/env python3
"""Pull verified remote file(s) over strict SSH and verify before atomic install.

Supports both single-file transfers (--source-path / --destination / --bytes / --sha256)
and manifest-driven transfers (--manifest-path / --transfer-mode proxy|full), with
optional OpenSSH ControlMaster connection multiplexing (--multiplex).
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


REMOTE_PROBE = r'''import hashlib,json,os,stat,sys
root,source=sys.argv[1:3]
for path in (root,source):
    if not path.startswith("/") or os.path.normpath(path) != path:
        raise SystemExit("remote path is not canonical and absolute")
    current="/"
    for part in path.split("/")[1:]:
        if not part:
            continue
        current=os.path.join(current,part)
        mode=os.lstat(current).st_mode
        if stat.S_ISLNK(mode):
            raise SystemExit("remote path contains a symlink")
root_real=os.path.realpath(root)
source_real=os.path.realpath(source)
if root_real != root or os.path.commonpath((root_real,source_real)) != root_real:
    raise SystemExit("remote source escapes its approved root")
info=os.stat(source,follow_symlinks=False)
if not stat.S_ISREG(info.st_mode):
    raise SystemExit("remote source is not a regular file")
digest=hashlib.sha256()
with open(source,"rb") as stream:
    for block in iter(lambda:stream.read(1024*1024),b""):
        digest.update(block)
print(json.dumps({"bytes":info.st_size,"sha256":digest.hexdigest()}))
'''

REMOTE_CAT_MANIFEST = r'''import os,stat,sys
root,source=sys.argv[1:3]
for path in (root,source):
    if not path.startswith("/") or os.path.normpath(path) != path:
        raise SystemExit("remote manifest path is not canonical and absolute")
    current="/"
    for part in path.split("/")[1:]:
        if not part:
            continue
        current=os.path.join(current,part)
        if stat.S_ISLNK(os.lstat(current).st_mode):
            raise SystemExit("remote manifest path contains a symlink")
root_real=os.path.realpath(root)
source_real=os.path.realpath(source)
if root_real != root or os.path.commonpath((root_real,source_real)) != root_real:
    raise SystemExit("remote manifest escapes approved root")
with open(source,"r",encoding="utf-8") as stream:
    sys.stdout.write(stream.read())
'''


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-host", required=True, help="SSH config alias or known host")
    parser.add_argument("--source-user", required=True, help="authorized SSH account")
    parser.add_argument("--source-root", required=True, help="approved absolute remote source root")
    parser.add_argument("--source-path", help="regular file beneath --source-root (single-file mode)")
    parser.add_argument("--destination-root", required=True, help="existing local directory approved for output")
    parser.add_argument("--destination", help="new direct child filename under destination root (single-file mode)")
    parser.add_argument("--sha256", help="expected SHA-256 of the original bytes (single-file mode)")
    parser.add_argument("--bytes", type=int, help="expected source byte count (single-file mode)")
    parser.add_argument("--manifest-path", help="approved remote manifest.json beneath --source-root (manifest mode)")
    parser.add_argument("--transfer-mode", choices=("proxy", "full"), default="full",
                        help="manifest mode: 'proxy' pulls lightweight review files only; 'full' pulls all artifacts")
    parser.add_argument("--multiplex", action="store_true",
                        help="enable OpenSSH ControlMaster multiplexing for multi-file transfers")
    parser.add_argument("--control-persist", type=int, default=300,
                        help="ControlPersist timeout in seconds when --multiplex is enabled (1..1800)")
    parser.add_argument("--timeout", type=int, default=300, help="SSH/SCP timeout in seconds (1..3600)")
    return parser.parse_args()


def safe_token(value, label):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ValueError(f"{label} contains unsupported characters")


def safe_remote_path(value, label):
    if (not value.startswith("/") or value.startswith("//") or os.path.normpath(value) != value
            or not re.fullmatch(r"/[A-Za-z0-9._/-]+", value)
            or any(part in (".", "..") for part in PurePosixPath(value).parts)):
        raise ValueError(f"{label} must be a canonical absolute path without traversal")


def local_path_has_symlink(path):
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(info.st_mode):
            return True
    return False


def sha256_file(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("file is not a regular file")
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return info.st_size, digest.hexdigest()
    finally:
        os.close(descriptor)


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def receipt_core(receipt):
    return {key: receipt[key] for key in (
        "source_host", "source_user", "source_root", "source_path",
        "destination", "bytes", "sha256", "host_key_policy",
    )}


def write_receipt(path, payload):
    if path.is_symlink():
        raise ValueError("receipt path is a symlink; refusing overwrite")
    if path.exists():
        try:
            old = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("existing receipt is unreadable; refusing overwrite") from error
        if receipt_core(old) != receipt_core(payload) or old.get("status") not in (
                "SCP_VERIFIED", "DESTINATION_ALREADY_VERIFIED"):
            raise ValueError("existing receipt does not match this transfer")
        return old

    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as stream:
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(descriptor)
        os.link(temporary, path, follow_symlinks=False)
        fsync_directory(path.parent)
        return payload
    finally:
        os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def validate_destination_root(destination_root_str):
    root = Path(destination_root_str)
    if (not root.is_absolute() or ".." in root.parts
            or os.path.normpath(destination_root_str) != destination_root_str
            or local_path_has_symlink(root)):
        raise ValueError("destination root must be absolute and contain no symlink")
    root = Path(os.path.normpath(root))
    if not root.is_dir() or root.resolve(strict=True) != root:
        raise ValueError("destination root must be an existing canonical directory")
    return root


def validate_destination_child(root, destination):
    if not destination.is_absolute() or destination.parent != root:
        raise ValueError("destination must be a direct child of the approved root")
    if destination.name in ("", ".", "..") or not re.fullmatch(r"[A-Za-z0-9._-]+", destination.name):
        raise ValueError("destination filename contains unsupported characters")
    if local_path_has_symlink(destination) or local_path_has_symlink(root / (destination.name + ".transfer-receipt.json")):
        raise ValueError("destination or receipt path contains a symlink")


def build_ssh_options(*, multiplex=False, control_persist=300, control_path=None):
    options = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10"]
    if multiplex:
        if not 1 <= control_persist <= 1800:
            raise ValueError("control-persist must be between 1 and 1800 seconds")
        if not control_path:
            raise ValueError("control_path is required when multiplex is enabled")
        options.extend([
            "-o", "ControlMaster=auto",
            "-o", f"ControlPersist={control_persist}",
            "-o", f"ControlPath={control_path}",
        ])
    return options


def select_manifest_artifacts(artifacts, transfer_mode):
    if transfer_mode == "full":
        return list(artifacts.items())
    selected = []
    for key, info in artifacts.items():
        name = str(info.get("filename") or PurePosixPath(str(info.get("path", ""))).name).lower()
        key_l = key.lower()
        if (
            "contact_sheet" in key_l
            or "preview" in key_l
            or key_l.endswith("_proxy")
            or name.endswith(("_contact_sheet.png", "_preview.mp4", ".webp", ".jpg"))
        ):
            selected.append((key, info))
    return selected


def transfer_single_file(
    *,
    target,
    ssh_options,
    source_host,
    source_user,
    source_root,
    source_path,
    root,
    destination,
    expected_sha256,
    expected_bytes,
    timeout,
):
    safe_remote_path(source_path, "source path")
    source_root_p = PurePosixPath(source_root)
    source_path_p = PurePosixPath(source_path)
    try:
        source_path_p.relative_to(source_root_p)
    except ValueError as error:
        raise ValueError("source path escapes its approved root") from error
    if source_path == source_root:
        raise ValueError("source path must name a file beneath the approved root")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
        raise ValueError("expected SHA-256 must contain exactly 64 hexadecimal characters")
    expected_hash = expected_sha256.lower()
    if expected_bytes <= 0:
        raise ValueError("expected byte count must be positive")
    validate_destination_child(root, destination)

    remote_command = "python3 -c {} {} {}".format(
        shlex.quote(REMOTE_PROBE), shlex.quote(source_root), shlex.quote(source_path)
    )
    try:
        probe = subprocess.run(
            ["ssh", *ssh_options, target, remote_command],
            check=True, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("remote source probe timed out") from error
    except subprocess.CalledProcessError as error:
        raise ValueError(f"remote source probe failed (exit {error.returncode})") from error
    remote = json.loads(probe.stdout)
    if remote.get("bytes") != expected_bytes or remote.get("sha256") != expected_hash:
        raise ValueError("remote source byte count or SHA-256 does not match the expected master")

    receipt_path = root / (destination.name + ".transfer-receipt.json")
    core = {
        "source_host": source_host,
        "source_user": source_user,
        "source_root": source_root,
        "source_path": source_path,
        "destination": str(destination),
        "bytes": expected_bytes,
        "sha256": expected_hash,
        "host_key_policy": "StrictHostKeyChecking=yes; existing known_hosts entry required",
    }

    status = "SCP_VERIFIED"
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink():
            raise ValueError("destination is a symlink; refusing overwrite")
        size, digest = sha256_file(destination)
        if size != expected_bytes or digest != expected_hash:
            raise ValueError("destination already exists with different bytes; refusing overwrite")
        status = "DESTINATION_ALREADY_VERIFIED"
    else:
        if receipt_path.exists() or receipt_path.is_symlink():
            raise ValueError("receipt exists without its destination; refusing to overwrite")
        temporary_dir = Path(tempfile.mkdtemp(prefix=f".{destination.name}.transfer-", dir=root))
        partial = temporary_dir / destination.name
        try:
            try:
                subprocess.run(
                    ["scp", "-p", *ssh_options, f"{target}:{source_path}", str(partial)],
                    check=True, capture_output=True, text=True, timeout=timeout,
                )
            except subprocess.TimeoutExpired as error:
                raise ValueError("SCP transfer timed out") from error
            except subprocess.CalledProcessError as error:
                raise ValueError(f"SCP transfer failed (exit {error.returncode})") from error
            if partial.is_symlink():
                raise ValueError("SCP produced a symlink; refusing to finalize")
            size, digest = sha256_file(partial)
            if size != expected_bytes or digest != expected_hash:
                raise ValueError("downloaded bytes do not match the expected master")
            os.chmod(partial, 0o600, follow_symlinks=False)
            os.link(partial, destination, follow_symlinks=False)
            fsync_directory(root)
        finally:
            if temporary_dir.exists() and not temporary_dir.is_symlink():
                shutil.rmtree(temporary_dir)

    payload = {
        **core,
        "status": status,
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    return write_receipt(receipt_path, payload)


def main():
    args = parse_args()
    safe_token(args.source_host, "source host")
    safe_token(args.source_user, "source user")
    safe_remote_path(args.source_root, "source root")
    if not 1 <= args.timeout <= 3600:
        raise ValueError("timeout must be between 1 and 3600 seconds")

    root = validate_destination_root(args.destination_root)
    target = f"{args.source_user}@{args.source_host}"

    ctrl_dir = None
    ctrl_path = None
    try:
        if args.multiplex:
            mux_base = "/tmp" if Path("/tmp").is_dir() else tempfile.gettempdir()
            ctrl_dir = Path(tempfile.mkdtemp(prefix="dvc-mux-", dir=mux_base))
            os.chmod(ctrl_dir, 0o700)
            ctrl_path = str(ctrl_dir / "s")

        ssh_options = build_ssh_options(
            multiplex=args.multiplex,
            control_persist=args.control_persist,
            control_path=ctrl_path,
        )

        if args.manifest_path:
            safe_remote_path(args.manifest_path, "manifest path")
            cat_cmd = "python3 -c {} {} {}".format(
                shlex.quote(REMOTE_CAT_MANIFEST), shlex.quote(args.source_root), shlex.quote(args.manifest_path)
            )
            try:
                manifest_proc = subprocess.run(
                    ["ssh", *ssh_options, target, cat_cmd],
                    check=True, capture_output=True, text=True, timeout=args.timeout,
                )
            except subprocess.CalledProcessError as error:
                raise ValueError(f"remote manifest read failed (exit {error.returncode})") from error
            manifest = json.loads(manifest_proc.stdout)
            artifacts = manifest.get("artifacts", {})
            if not isinstance(artifacts, dict) or not artifacts:
                raise ValueError("manifest contains no artifacts")
            selected = select_manifest_artifacts(artifacts, args.transfer_mode)
            if not selected:
                raise ValueError(f"no artifacts matched transfer mode {args.transfer_mode!r}")

            receipts = []
            for key, info in selected:
                remote_path = str(info["path"])
                dest_name = PurePosixPath(remote_path).name
                receipt = transfer_single_file(
                    target=target,
                    ssh_options=ssh_options,
                    source_host=args.source_host,
                    source_user=args.source_user,
                    source_root=args.source_root,
                    source_path=remote_path,
                    root=root,
                    destination=root / dest_name,
                    expected_sha256=str(info["sha256"]),
                    expected_bytes=int(info["bytes"]),
                    timeout=args.timeout,
                )
                receipts.append({"artifact": key, **receipt})
            print(json.dumps({
                "transfer_mode": args.transfer_mode,
                "multiplex": args.multiplex,
                "receipts": receipts,
            }, indent=2, sort_keys=True))
            return 0

        if not all([args.source_path, args.destination, args.sha256, args.bytes is not None]):
            raise ValueError("single-file mode requires --source-path, --destination, --sha256, and --bytes")

        result = transfer_single_file(
            target=target,
            ssh_options=ssh_options,
            source_host=args.source_host,
            source_user=args.source_user,
            source_root=args.source_root,
            source_path=args.source_path,
            root=root,
            destination=Path(args.destination),
            expected_sha256=args.sha256,
            expected_bytes=args.bytes,
            timeout=args.timeout,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        if ctrl_path and Path(ctrl_path).exists():
            try:
                subprocess.run(
                    ["ssh", "-o", f"ControlPath={ctrl_path}", "-O", "exit", target],
                    capture_output=True, timeout=5,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        if ctrl_dir and ctrl_dir.exists() and not ctrl_dir.is_symlink():
            shutil.rmtree(ctrl_dir, ignore_errors=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"transfer failed: {error}", file=sys.stderr)
        raise SystemExit(1)
