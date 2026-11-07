#!/usr/bin/env python3
"""Pull one authorized remote file over strict SSH and verify it before install."""

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


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-host", required=True, help="SSH config alias or known host")
    parser.add_argument("--source-user", required=True, help="authorized SSH account")
    parser.add_argument("--source-root", required=True, help="approved absolute remote source root")
    parser.add_argument("--source-path", required=True, help="regular file beneath --source-root")
    parser.add_argument("--destination-root", required=True, help="existing local directory approved for output")
    parser.add_argument("--destination", required=True, help="new direct child filename under destination root")
    parser.add_argument("--sha256", required=True, help="expected SHA-256 of the original bytes")
    parser.add_argument("--bytes", type=int, required=True, help="expected source byte count")
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


def main():
    args = parse_args()
    safe_token(args.source_host, "source host")
    safe_token(args.source_user, "source user")
    safe_remote_path(args.source_root, "source root")
    safe_remote_path(args.source_path, "source path")
    source_root = PurePosixPath(args.source_root)
    source_path = PurePosixPath(args.source_path)
    try:
        source_path.relative_to(source_root)
    except ValueError as error:
        raise ValueError("source path escapes its approved root") from error
    if args.source_path == args.source_root:
        raise ValueError("source path must name a file beneath the approved root")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", args.sha256):
        raise ValueError("expected SHA-256 must contain exactly 64 hexadecimal characters")
    expected_hash = args.sha256.lower()
    if args.bytes <= 0:
        raise ValueError("expected byte count must be positive")
    if not 1 <= args.timeout <= 3600:
        raise ValueError("timeout must be between 1 and 3600 seconds")

    root = Path(args.destination_root)
    destination = Path(args.destination)
    if (not root.is_absolute() or ".." in root.parts
            or os.path.normpath(args.destination_root) != args.destination_root
            or local_path_has_symlink(root)):
        raise ValueError("destination root must be absolute and contain no symlink")
    root = Path(os.path.normpath(root))
    if not root.is_dir() or root.resolve(strict=True) != root:
        raise ValueError("destination root must be an existing canonical directory")
    if not destination.is_absolute() or destination.parent != root:
        raise ValueError("destination must be a direct child of the approved root")
    if destination.name in ("", ".", "..") or not re.fullmatch(r"[A-Za-z0-9._-]+", destination.name):
        raise ValueError("destination filename contains unsupported characters")
    if local_path_has_symlink(destination) or local_path_has_symlink(root / (destination.name + ".transfer-receipt.json")):
        raise ValueError("destination or receipt path contains a symlink")

    target = f"{args.source_user}@{args.source_host}"
    ssh_options = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10"]
    remote_command = "python3 -c {} {} {}".format(
        shlex.quote(REMOTE_PROBE), shlex.quote(args.source_root), shlex.quote(args.source_path)
    )
    try:
        probe = subprocess.run(
            ["ssh", *ssh_options, target, remote_command],
            check=True, capture_output=True, text=True, timeout=args.timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("remote source probe timed out") from error
    except subprocess.CalledProcessError as error:
        raise ValueError(f"remote source probe failed (exit {error.returncode})") from error
    remote = json.loads(probe.stdout)
    if remote.get("bytes") != args.bytes or remote.get("sha256") != expected_hash:
        raise ValueError("remote source byte count or SHA-256 does not match the expected master")

    receipt_path = root / (destination.name + ".transfer-receipt.json")
    core = {
        "source_host": args.source_host,
        "source_user": args.source_user,
        "source_root": args.source_root,
        "source_path": args.source_path,
        "destination": str(destination),
        "bytes": args.bytes,
        "sha256": expected_hash,
        "host_key_policy": "StrictHostKeyChecking=yes; existing known_hosts entry required",
    }

    status = "SCP_VERIFIED"
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink():
            raise ValueError("destination is a symlink; refusing overwrite")
        size, digest = sha256_file(destination)
        if size != args.bytes or digest != expected_hash:
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
                    ["scp", "-p", *ssh_options, f"{target}:{args.source_path}", str(partial)],
                    check=True, capture_output=True, text=True, timeout=args.timeout,
                )
            except subprocess.TimeoutExpired as error:
                raise ValueError("SCP transfer timed out") from error
            except subprocess.CalledProcessError as error:
                raise ValueError(f"SCP transfer failed (exit {error.returncode})") from error
            if partial.is_symlink():
                raise ValueError("SCP produced a symlink; refusing to finalize")
            size, digest = sha256_file(partial)
            if size != args.bytes or digest != expected_hash:
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
    result = write_receipt(receipt_path, payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(f"transfer failed: {error}", file=sys.stderr)
        raise SystemExit(1)
