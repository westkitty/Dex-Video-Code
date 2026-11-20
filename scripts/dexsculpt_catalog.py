#!/usr/bin/env python3
"""Sanitized DEX//SCULPT + Google Drive Humanoid Catalog bridge for Blender MCP.

Indexes DEX//SCULPT humanoid metadata (`humanoidCatalog.json`, `humanoidSources.json`,
`humanoidCompatibility.json`), checks a local verified GLB cache first, falls back
on demand to a local Google Drive for Desktop archive mount (with bounded retry and
optional `gdrive` CLI fallback), verifies exact byte count + SHA-256 + 12-byte GLB v2
headers, stages verified binaries over StrictHostKeyChecking SSH/SCP to an authorized
remote Blender host, and imports rigs/props non-destructively over MCP stdio.

All host aliases, paths, and Drive IDs live strictly in a private user-supplied JSON
config (`~/.config/dex-video-code/catalog.json` or `DEX_CATALOG_CONFIG`) outside Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DEFAULT_CATALOG_CONFIG = Path.home() / ".config" / "dex-video-code" / "catalog.json"
ENV_CATALOG_CONFIG = "DEX_CATALOG_CONFIG"
ENV_MCP_LAUNCHER = "BLENDER_MCP_LAUNCHER"
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
PRIVATE_LICENSE_NOTICE_SOURCES = frozenset(
    {
        "quaternius-ultimate-modular-men",
        "quaternius-ultimate-modular-women",
    }
)
SSH_OPTS = (
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "LogLevel=ERROR",
)

REMOTE_STAGE_PROBE = r"""import hashlib,json,os,shutil,stat,struct,sys
root,target_dir,target_file,min_gib_s,exp_bytes_s,exp_sha=sys.argv[1:7]
min_gib=float(min_gib_s)
exp_bytes=int(exp_bytes_s)
exp_sha=exp_sha.lower()
def no_symlink(path):
    cur="/"
    for part in path.split("/")[1:]:
        if not part:
            continue
        cur=os.path.join(cur,part)
        if os.path.lexists(cur) and stat.S_ISLNK(os.lstat(cur).st_mode):
            raise SystemExit(f"Symlink disallowed on remote host: {cur}")
for p in (root,target_dir,target_file):
    if not p.startswith("/") or os.path.normpath(p) != p:
        raise SystemExit(f"Invalid non-canonical remote path: {p}")
    no_symlink(p)
free_gib=shutil.disk_usage("/").free/(1024**3)
if free_gib < min_gib:
    raise SystemExit(f"Insufficient disk on remote host: {free_gib:.2f} GiB < {min_gib:.2f} GiB")
os.makedirs(target_dir,exist_ok=True)
no_symlink(target_file)
if os.path.lexists(target_file):
    st=os.lstat(target_file)
    if stat.S_ISREG(st.st_mode) and st.st_size == exp_bytes:
        h=hashlib.sha256()
        hdr=b""
        with open(target_file,"rb") as f:
            while True:
                blk=f.read(1024*1024)
                if not blk:
                    break
                if len(hdr) < 12:
                    hdr += blk[:12-len(hdr)]
                h.update(blk)
        if len(hdr) >= 12 and hdr[:4] == b"glTF":
            ver,length=struct.unpack_from("<II",hdr,4)
            if ver == 2 and length == exp_bytes and h.hexdigest() == exp_sha:
                os.utime(target_file,None)
                print(json.dumps({"exists":True,"bytes":exp_bytes,"sha256":exp_sha,"free_gib":round(free_gib,3)}))
                raise SystemExit(0)
    raise SystemExit(f"Staged target mismatch or conflict at {target_file}")
print(json.dumps({"exists":False,"free_gib":round(free_gib,3)}))
"""

REMOTE_VERIFY_PROMOTE = r"""import hashlib,json,os,shutil,stat,struct,sys
part_path,final_path,exp_bytes_s,exp_sha=sys.argv[1:5]
staging_root=sys.argv[5] if len(sys.argv) > 5 else os.path.dirname(os.path.dirname(final_path))
max_cache_mb=int(sys.argv[6]) if len(sys.argv) > 6 else 512
exp_bytes=int(exp_bytes_s)
exp_sha=exp_sha.lower()
if not os.path.isfile(part_path) or stat.S_ISLNK(os.lstat(part_path).st_mode):
    raise SystemExit(f"Missing staged part file: {part_path}")
st=os.lstat(part_path)
if st.st_size != exp_bytes:
    os.unlink(part_path)
    raise SystemExit(f"Staged size mismatch: {st.st_size} != {exp_bytes}")
h=hashlib.sha256()
hdr=b""
with open(part_path,"rb") as f:
    while True:
        blk=f.read(1024*1024)
        if not blk:
            break
        if len(hdr) < 12:
            hdr += blk[:12-len(hdr)]
        h.update(blk)
digest=h.hexdigest()
if digest != exp_sha or len(hdr) < 12 or hdr[:4] != b"glTF":
    os.unlink(part_path)
    raise SystemExit("Staged SHA-256 or GLB magic verification failed")
ver,length=struct.unpack_from("<II",hdr,4)
if ver != 2 or length != exp_bytes:
    os.unlink(part_path)
    raise SystemExit("Staged GLB v2 header verification failed")
os.chmod(part_path,0o644)
os.replace(part_path,final_path)
os.utime(final_path,None)
evicted_files=0
evicted_bytes=0
if max_cache_mb > 0 and os.path.isdir(staging_root):
    cap=max_cache_mb*1024*1024
    items=[]
    total=0
    for root,dirs,files in os.walk(staging_root,followlinks=False):
        dirs[:]=[d for d in dirs if not stat.S_ISLNK(os.lstat(os.path.join(root,d)).st_mode)]
        for fn in files:
            if not fn.lower().endswith(".glb"):
                continue
            fp=os.path.join(root,fn)
            fst=os.lstat(fp)
            if stat.S_ISLNK(fst.st_mode) or not stat.S_ISREG(fst.st_mode):
                continue
            total += fst.st_size
            if fp != final_path:
                items.append((fst.st_mtime,fst.st_size,fp))
    items.sort()
    for _,sz,fp in items:
        if total <= cap:
            break
        os.unlink(fp)
        total -= sz
        evicted_bytes += sz
        evicted_files += 1
free_gib=shutil.disk_usage("/").free/(1024**3)
print(json.dumps({"bytes":exp_bytes,"sha256":digest,"free_gib":round(free_gib,3),"evicted_files":evicted_files,"evicted_bytes":evicted_bytes}))
"""

REMOTE_PRUNE_CACHE = r"""import json,os,shutil,stat,sys
cache_dir,dry_run_s=sys.argv[1:3]
dry_run=(dry_run_s == "1")
if not cache_dir.startswith("/") or os.path.normpath(cache_dir) != cache_dir or len(cache_dir.split("/")) < 3:
    raise SystemExit(f"Refusing unsafe cache_dir: {cache_dir}")
cur="/"
for part in cache_dir.split("/")[1:]:
    if not part:
        continue
    cur=os.path.join(cur,part)
    if os.path.lexists(cur) and stat.S_ISLNK(os.lstat(cur).st_mode):
        raise SystemExit(f"Refusing symlink in cache_dir: {cur}")
if not os.path.isdir(cache_dir):
    free_gib=shutil.disk_usage("/").free/(1024**3)
    print(json.dumps({"cache_dir":cache_dir,"removed_files":0,"reclaimed_bytes":0,"free_gib":round(free_gib,3),"dry_run":dry_run}))
    raise SystemExit(0)
removed=0
reclaimed=0
for root,dirs,files in os.walk(cache_dir,followlinks=False):
    for d in list(dirs):
        dp=os.path.join(root,d)
        if stat.S_ISLNK(os.lstat(dp).st_mode):
            dirs.remove(d)
    for fn in sorted(files):
        fp=os.path.join(root,fn)
        st=os.lstat(fp)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            continue
        if fn.lower().endswith(".glb") or ".glb.part." in fn.lower():
            reclaimed += st.st_size
            removed += 1
            if not dry_run:
                os.unlink(fp)
free_gib=shutil.disk_usage("/").free/(1024**3)
print(json.dumps({"cache_dir":cache_dir,"removed_files":removed,"reclaimed_bytes":reclaimed,"free_gib":round(free_gib,3),"dry_run":dry_run}))
"""

REMOTE_STATUS_PROBE = r"""import json,os,shutil,stat,sys
cache_dir=sys.argv[1]
free_gib=round(shutil.disk_usage("/").free/(1024**3),3)
count=0
total_bytes=0
if os.path.isdir(cache_dir) and not stat.S_ISLNK(os.lstat(cache_dir).st_mode):
    for root,dirs,files in os.walk(cache_dir,followlinks=False):
        for fn in files:
            fp=os.path.join(root,fn)
            st=os.lstat(fp)
            if stat.S_ISREG(st.st_mode) and fn.lower().endswith(".glb"):
                count += 1
                total_bytes += st.st_size
print(json.dumps({"staging_dir":cache_dir,"staged_files":count,"staged_bytes":total_bytes,"free_gib":free_gib}))
"""

_BOUNDED_READ_HELPER = r"""import hashlib,os,stat,struct,sys
src,exp_bytes_s,exp_sha,dest=sys.argv[1:5]
exp_bytes=int(exp_bytes_s)
exp_sha=exp_sha.lower()
st=os.lstat(src)
if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
    print("Source is not a regular file",file=sys.stderr)
    raise SystemExit(2)
with open(src,"rb") as f:
    data=f.read()
if len(data) != exp_bytes:
    print(f"Byte length mismatch: {len(data)} != {exp_bytes}",file=sys.stderr)
    raise SystemExit(2)
if len(data) < 12 or data[:4] != b"glTF":
    print("Invalid GLB magic header",file=sys.stderr)
    raise SystemExit(2)
ver,length=struct.unpack_from("<II",data,4)
if ver != 2 or length != len(data):
    print(f"Invalid GLB v2 header: version={ver} length={length} actual={len(data)}",file=sys.stderr)
    raise SystemExit(2)
digest=hashlib.sha256(data).hexdigest()
if digest != exp_sha:
    print(f"SHA-256 mismatch: {digest} != {exp_sha}",file=sys.stderr)
    raise SystemExit(2)
if dest:
    part=f"{dest}.part.{os.getpid()}"
    fd=os.open(part,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    try:
        os.write(fd,data)
    finally:
        os.close(fd)
    os.replace(part,dest)
print(f"{len(data)} {digest}")
"""


class StdioMCPClient:
    """Minimal newline-delimited JSON-RPC 2.0 client for MCP over stdio."""

    def __init__(self, command: list[str], timeout: float = 180.0):
        self.command = command
        self.timeout = timeout
        self.proc: subprocess.Popen[str] | None = None
        self._next_id = 1

    def __enter__(self) -> "StdioMCPClient":
        self.proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not self.proc:
            return
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def _send(self, payload: dict[str, Any]) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def _recv_until(self, target_id: int) -> dict[str, Any]:
        assert self.proc and self.proc.stdout
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                stderr_tail = self.proc.stderr.read() if self.proc.stderr else ""
                raise RuntimeError(f"MCP server closed stdout unexpectedly. stderr:\n{stderr_tail}")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Non-JSON line on MCP stdout: {line[:300]}") from exc
            if msg.get("id") == target_id:
                if "error" in msg:
                    raise RuntimeError(f"MCP JSON-RPC error: {json.dumps(msg['error'])}")
                return msg.get("result", {})
        raise TimeoutError(f"Timed out waiting {self.timeout}s for MCP response id={target_id}")

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        req_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)
        return self._recv_until(req_id)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)

    def initialize(self) -> dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "dex-video-code-catalog-client", "version": "1.0.0"},
            },
        )
        self.notify("notifications/initialized")
        return result

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})


def load_catalog_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load private catalog configuration from explicit path, env override, or ~/.config."""
    if config_path is not None:
        cfg_file = Path(config_path).expanduser()
    else:
        env_raw = os.environ.get(ENV_CATALOG_CONFIG, "").strip()
        cfg_file = Path(env_raw).expanduser() if env_raw else DEFAULT_CATALOG_CONFIG
    if not cfg_file.is_file():
        raise FileNotFoundError(
            f"Catalog config file not found: {cfg_file}. Create a private mode-0600 JSON config or set {ENV_CATALOG_CONFIG}."
        )
    raw = json.loads(cfg_file.read_text(encoding="utf-8"))
    for key in ("metadata_dir", "verified_cache_dir", "gdrive_archive_dir", "mcp_launcher"):
        if raw.get(key):
            raw[key] = str(Path(raw[key]).expanduser())
    if not raw.get("metadata_dir"):
        raise ValueError(f"Catalog config {cfg_file} must specify metadata_dir")
    raw["_config_path"] = str(cfg_file)
    return raw


def validate_glb_v2_header(data: bytes) -> None:
    """Validate 12-byte GLB 2.0 container magic, version, and declared byte length."""
    if len(data) < 12 or data[:4] != b"glTF":
        raise ValueError("Invalid GLB header: expected 'glTF' magic")
    version, declared_len = struct.unpack_from("<II", data, 4)
    if version != 2:
        raise ValueError(f"Unsupported GLB version {version} (expected 2)")
    if declared_len != len(data):
        raise ValueError(f"GLB header length {declared_len} disagrees with actual size {len(data)}")


def assert_no_symlinks_under(root: Path, target: Path) -> None:
    """Reject symlinks at root or any component between root and target."""
    if root.is_symlink():
        raise ValueError(f"Symlink disallowed at root: {root}")
    rel = target.relative_to(root)
    cur = root
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise ValueError(f"Symlink disallowed in path: {cur}")


def _validate_safe_token(value: str, label: str, *, glb_only: bool = False) -> str:
    if not value or "/" in value or "\\" in value or ".." in value or not SAFE_NAME_RE.match(value):
        raise ValueError(f"Unsafe {label}: {value!r}")
    if glb_only and not value.lower().endswith(".glb"):
        raise ValueError(f"{label} must end with .glb: {value!r}")
    return value


def archive_candidate_roots(archive_dir: Path, source_id: str) -> list[Path]:
    """Map catalog source_id to expected directories inside a mounted Drive ARCHIVE."""
    _validate_safe_token(source_id, "source_id")
    roots: list[Path] = []
    if source_id == "microsoft-rocketbox":
        roots.append(archive_dir / "2026-11-13" / "processed-glb")
    elif source_id.startswith("kaykit-"):
        roots.append(archive_dir / "2026-11-14" / "processed-glb" / "kaykit" / source_id[7:])
    elif source_id.startswith("quaternius-"):
        roots.append(archive_dir / "2026-11-14" / "processed-glb" / "quaternius" / source_id[11:])
        roots.append(archive_dir / "2026-11-14_expansion" / "processed-glb" / source_id)
    else:
        roots.append(archive_dir / "2026-11-14_expansion" / "processed-glb" / source_id)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for p in roots:
        if p not in seen:
            seen.add(p)
            deduped.append(p)
    return deduped


def find_named_files(directory: Path, basename: str, max_depth: int = 3) -> list[Path]:
    """Find all case-insensitive basename matches under directory up to max_depth without skipping sibling matches."""
    if max_depth < 0 or not directory.is_dir() or directory.is_symlink():
        return []
    target_lower = basename.lower()
    matches: list[Path] = []
    seen: set[Path] = set()

    def _walk(cur_dir: Path, remaining_depth: int) -> None:
        try:
            entries = sorted(cur_dir.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_file() and entry.name.lower() == target_lower:
                if entry not in seen:
                    seen.add(entry)
                    matches.append(entry)
        if remaining_depth <= 0:
            return
        for entry in entries:
            if entry.is_dir() and not entry.is_symlink() and not entry.name.startswith("."):
                _walk(entry, remaining_depth - 1)

    _walk(directory, max_depth)
    return matches


def is_cached_fast(record: dict[str, Any], cache_dir: Path | None) -> Path | None:
    """Return local cached GLB path when present as a regular file with exact byte size."""
    if cache_dir is None or not cache_dir.is_dir():
        return None
    source_id = record.get("source_id") or ""
    basename = record.get("processed_glb_basename") or ""
    expected_bytes = record.get("processed_glb_bytes")
    if not source_id or not basename or not expected_bytes:
        return None
    try:
        _validate_safe_token(source_id, "source_id")
        _validate_safe_token(basename, "processed_glb_basename", glb_only=True)
    except ValueError:
        return None
    candidate = cache_dir / source_id / basename
    try:
        assert_no_symlinks_under(cache_dir, candidate)
        st = candidate.lstat()
    except (OSError, ValueError):
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_size != int(expected_bytes):
        return None
    return candidate


def _download_via_gdrive_fallback(
    path: Path,
    expected_bytes: int,
    expected_sha256: str,
    dest_copy: Path | None,
    *,
    drivefs_error: str,
    timeout_seconds: int,
) -> tuple[int, str]:
    gdrive_bin = shutil.which("gdrive")
    if not gdrive_bin:
        raise TimeoutError(f"DriveFS read failed for {path} ({drivefs_error}); gdrive CLI fallback unavailable")

    x_proc = subprocess.run(
        ["xattr", "-p", "com.google.drivefs.item-id#S", str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    item_id = x_proc.stdout.strip() if x_proc.returncode == 0 and x_proc.stdout.strip() else ""
    if not item_id:
        raise TimeoutError(f"DriveFS read failed for {path} ({drivefs_error}); no Drive item ID xattr available")

    with tempfile.TemporaryDirectory(prefix="dexsculpt-gdrive-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        os.chmod(tmp_dir, 0o700)
        tmp_dl = tmp_dir / path.name
        dl_proc = subprocess.run(
            [gdrive_bin, "readonly", "download", item_id, "--out", str(tmp_dl)],
            capture_output=True,
            text=True,
            check=False,
            timeout=max(30, timeout_seconds),
        )
        if dl_proc.returncode != 0 or not tmp_dl.is_file():
            err_detail = (dl_proc.stderr or dl_proc.stdout or f"exit={dl_proc.returncode}").strip()
            raise RuntimeError(
                f"DriveFS read failed for {path} ({drivefs_error}); gdrive fallback failed for item {item_id}: {err_detail}"
            )
        return read_verified_file_bounded(tmp_dl, expected_bytes, expected_sha256, 0, dest_copy=dest_copy)


def read_verified_file_bounded(
    path: Path,
    expected_bytes: int,
    expected_sha256: str,
    timeout_seconds: int,
    dest_copy: Path | None = None,
    *,
    max_attempts: int = 3,
    retry_sleep_seconds: float = 1.5,
) -> tuple[int, str]:
    """Read, GLB-v2-validate, and SHA-256-verify a file (with bounded DriveFS retries and gdrive CLI fallback)."""
    exp_sha = expected_sha256.lower()
    if timeout_seconds > 0:
        attempts = max(1, max_attempts)
        per_attempt = timeout_seconds if attempts == 1 else min(25, max(5, timeout_seconds // attempts))
        dest_arg = str(dest_copy) if dest_copy is not None else ""
        last_err = "unknown error"
        for attempt in range(1, attempts + 1):
            try:
                proc = subprocess.run(
                    [sys.executable, "-c", _BOUNDED_READ_HELPER, str(path), str(expected_bytes), exp_sha, dest_arg],
                    capture_output=True,
                    text=True,
                    timeout=per_attempt,
                )
                if proc.returncode == 0:
                    return expected_bytes, exp_sha
                msg = (proc.stderr or proc.stdout or f"exit={proc.returncode}").strip()
                if proc.returncode == 2:
                    raise ValueError(f"Verified read failed for {path}: {msg}")
                last_err = msg
            except subprocess.TimeoutExpired:
                last_err = f"timed out after {per_attempt}s (attempt {attempt}/{attempts})"
            if attempt < attempts and retry_sleep_seconds > 0:
                time.sleep(retry_sleep_seconds)

        return _download_via_gdrive_fallback(
            path,
            expected_bytes,
            exp_sha,
            dest_copy,
            drivefs_error=last_err,
            timeout_seconds=timeout_seconds,
        )

    st = path.lstat()
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ValueError(f"Source is not a regular file: {path}")
    data = path.read_bytes()
    if len(data) != expected_bytes:
        raise ValueError(f"Byte length mismatch for {path}: {len(data)} != {expected_bytes}")
    validate_glb_v2_header(data)
    digest = hashlib.sha256(data).hexdigest()
    if digest != exp_sha:
        raise ValueError(f"SHA-256 mismatch for {path}: {digest} != {exp_sha}")
    if dest_copy is not None:
        part = dest_copy.with_name(f"{dest_copy.name}.part.{os.getpid()}")
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
        os.replace(part, dest_copy)
    return len(data), digest


class CatalogIndex:
    """Indexed view over DEX//SCULPT's humanoidCatalog, humanoidSources, and humanoidCompatibility."""

    def __init__(self, metadata_dir: str | Path):
        meta = Path(metadata_dir).expanduser().resolve()
        cat_doc = json.loads((meta / "humanoidCatalog.json").read_text(encoding="utf-8"))
        src_doc = json.loads((meta / "humanoidSources.json").read_text(encoding="utf-8"))
        compat_doc = json.loads((meta / "humanoidCompatibility.json").read_text(encoding="utf-8"))

        self.metadata_dir = meta
        self.summary: dict[str, Any] = cat_doc.get("summary", {})
        self.records: list[dict[str, Any]] = cat_doc.get("records", [])
        self.by_id: dict[str, dict[str, Any]] = {r["asset_id"]: r for r in self.records}
        self.sources_by_id: dict[str, dict[str, Any]] = {s["id"]: s for s in src_doc.get("sources", [])}
        self.compatibility_doc: dict[str, Any] = compat_doc
        self.skeleton_families: dict[str, dict[str, Any]] = compat_doc.get("skeleton_families", {})

    def get(self, asset_id: str) -> dict[str, Any]:
        rec = self.by_id.get(asset_id)
        if not rec:
            raise KeyError(f"Asset not found in catalog: {asset_id}")
        return rec

    def _license_notice(self, source_id: str) -> str | None:
        if source_id in PRIVATE_LICENSE_NOTICE_SOURCES:
            return (
                "Private use warning: pack pages label CC0, but publisher's QAL v1.0 restricts redistribution; "
                "keep binaries private and out of public repositories."
            )
        return None

    def _enrich_record(self, rec: dict[str, Any], cache_dir: Path | None) -> dict[str, Any]:
        cached_path = is_cached_fast(rec, cache_dir)
        out = dict(rec)
        out["cached_local"] = cached_path is not None
        out["availability"] = "CACHED_LOCAL" if cached_path is not None else "ARCHIVE_GOOGLE_DRIVE"
        return out

    def search(
        self,
        *,
        query: str | None = None,
        source_id: str | None = None,
        asset_type: str | None = None,
        skeleton_family: str | None = None,
        license_query: str | None = None,
        cached_only: bool = False,
        max_mb: float | None = None,
        limit: int = 25,
        cache_dir: Path | None = None,
    ) -> list[dict[str, Any]]:
        q = query.strip().lower() if query else None
        lic_q = license_query.strip().lower() if license_query else None
        max_bytes = int(max_mb * 1024 * 1024) if max_mb is not None else None
        matches: list[dict[str, Any]] = []

        for rec in self.records:
            if source_id and rec.get("source_id") != source_id:
                continue
            if asset_type and rec.get("asset_type") != asset_type:
                continue
            if skeleton_family and rec.get("skeleton_family") != skeleton_family:
                continue
            if lic_q and lic_q not in (rec.get("license_id") or "").lower():
                continue
            if max_bytes is not None and (rec.get("processed_glb_bytes") or 0) > max_bytes:
                continue
            if q:
                haystack = " ".join(
                    [
                        rec.get("asset_id") or "",
                        rec.get("display_name") or "",
                        rec.get("category") or "",
                        rec.get("source_id") or "",
                        " ".join(rec.get("style_tags") or ()),
                    ]
                ).lower()
                if q not in haystack:
                    continue
            cached_hit = is_cached_fast(rec, cache_dir) is not None
            if cached_only and not cached_hit:
                continue
            item = dict(rec)
            item["cached_local"] = cached_hit
            item["availability"] = "CACHED_LOCAL" if cached_hit else "ARCHIVE_GOOGLE_DRIVE"
            matches.append(item)

        matches.sort(key=lambda r: (not r["cached_local"], r["asset_id"]))
        return matches[: max(0, limit)]

    def info(self, asset_id: str, cache_dir: Path | None = None) -> dict[str, Any]:
        rec = self.get(asset_id)
        enriched = self._enrich_record(rec, cache_dir)
        fam = rec.get("skeleton_family")
        return {
            "record": enriched,
            "source_info": self.sources_by_id.get(rec["source_id"]),
            "compatibility": self.skeleton_families.get(fam) if fam else None,
            "license_notice": self._license_notice(rec["source_id"]),
        }

    def compatible(self, asset_id: str, limit: int = 50, cache_dir: Path | None = None) -> dict[str, Any]:
        rec = self.get(asset_id)
        fam = rec.get("skeleton_family")
        fam_info = self.skeleton_families.get(fam) if fam else None
        member_sources: set[str] = {rec["source_id"]}
        if fam_info:
            for ms in fam_info.get("member_sources", []):
                member_sources.add(ms.split(" (", 1)[0].strip())

        priority = {
            "animation_pack": 0,
            "accessory": 1,
            "modular_part": 2,
            "modular_outfit": 3,
            "hairstyle_rigged_head": 4,
            "hairstyle_origin_0": 5,
            "character": 6,
            "specialized_skeletal_humanoid": 7,
            "mannequin": 8,
        }
        has_rig = bool(fam and fam not in ("None", "none-static-pose"))
        out: list[dict[str, Any]] = []
        for other in self.records:
            if other["asset_id"] == asset_id:
                continue
            same_family = has_rig and other.get("skeleton_family") == fam
            attach_match = (
                other.get("asset_type") in ("accessory", "hairstyle_origin_0")
                and other.get("source_id") in member_sources
            )
            if same_family or attach_match:
                out.append(self._enrich_record(other, cache_dir))

        out.sort(
            key=lambda r: (
                not r["cached_local"],
                priority.get(r.get("asset_type") or "", 99),
                r["asset_id"],
            )
        )
        return {
            "asset": self._enrich_record(rec, cache_dir),
            "skeleton_family": fam,
            "compatibility": fam_info,
            "total_compatible": len(out),
            "items": out[: max(0, limit)],
        }

    def sources(self, cache_dir: Path | None = None) -> list[dict[str, Any]]:
        totals: dict[str, int] = {}
        cached_counts: dict[str, int] = {}
        for rec in self.records:
            sid = rec["source_id"]
            totals[sid] = totals.get(sid, 0) + 1
            if is_cached_fast(rec, cache_dir) is not None:
                cached_counts[sid] = cached_counts.get(sid, 0) + 1
        rows: list[dict[str, Any]] = []
        for sid in sorted(totals):
            src = self.sources_by_id.get(sid, {})
            rows.append(
                {
                    "source_id": sid,
                    "name": src.get("name", sid),
                    "total_assets": totals[sid],
                    "cached_local": cached_counts.get(sid, 0),
                    "license": src.get("license"),
                    "official_url": src.get("official_url"),
                    "license_notice": self._license_notice(sid),
                }
            )
        return rows


def _atomic_install_local_cache(
    *,
    source_bytes_path: Path,
    cache_target: Path,
    cache_dir: Path,
    expected_bytes: int,
    expected_sha256: str,
    min_free_gib: float,
) -> None:
    check_dir = cache_dir if cache_dir.exists() else cache_dir.parent
    free_gib = shutil.disk_usage(check_dir).free / (1024 ** 3)
    if free_gib < min_free_gib:
        raise RuntimeError(f"Insufficient local disk to cache GLB: {free_gib:.2f} GiB < {min_free_gib:.2f} GiB")

    assert_no_symlinks_under(cache_dir, cache_target)
    if cache_target.is_symlink():
        raise ValueError(f"Refusing symlink in local cache: {cache_target}")
    if cache_target.exists():
        got_bytes = cache_target.stat().st_size
        got_sha = hashlib.sha256(cache_target.read_bytes()).hexdigest()
        if got_bytes == expected_bytes and got_sha == expected_sha256.lower():
            return
        raise ValueError(f"Refusing to overwrite conflicting cached file with different SHA-256: {cache_target}")

    cache_target.parent.mkdir(parents=True, exist_ok=True)
    part = cache_target.with_name(f"{cache_target.name}.part.{os.getpid()}")
    try:
        shutil.copyfile(source_bytes_path, part)
        os.chmod(part, 0o644)
        os.replace(part, cache_target)
    finally:
        if part.exists():
            part.unlink()


def resolve_asset(
    index: CatalogIndex,
    cfg: dict[str, Any],
    asset_id: str,
    *,
    cache_local: bool = False,
    copy_to: Path | None = None,
) -> dict[str, Any]:
    """Resolve a catalog asset from local cache first, else on demand from Google Drive ARCHIVE."""
    rec = index.get(asset_id)
    source_id = _validate_safe_token(rec.get("source_id") or "", "source_id")
    basename = _validate_safe_token(rec.get("processed_glb_basename") or "", "processed_glb_basename", glb_only=True)
    expected_bytes = rec.get("processed_glb_bytes")
    expected_sha256 = (rec.get("processed_glb_sha256") or "").lower()
    if not expected_bytes or not expected_sha256:
        raise ValueError(f"Catalog record lacks size or SHA-256 verification metadata: {asset_id}")
    expected_bytes = int(expected_bytes)
    max_bytes = int(cfg.get("max_asset_bytes", 104857600))
    if expected_bytes > max_bytes:
        raise ValueError(f"Asset {asset_id} exceeds max_asset_bytes ({expected_bytes} > {max_bytes})")

    cache_dir_raw = cfg.get("verified_cache_dir")
    cache_dir = Path(cache_dir_raw).expanduser() if cache_dir_raw else None
    archive_raw = cfg.get("gdrive_archive_dir")
    archive_dir = Path(archive_raw).expanduser() if archive_raw else None
    timeout_s = int(cfg.get("drive_read_timeout_seconds", 60))

    # 1. Verified Local Cache priority (never scans Google Drive when local cache matches).
    cached_candidate = is_cached_fast(rec, cache_dir)
    if cached_candidate is not None:
        try:
            read_verified_file_bounded(cached_candidate, expected_bytes, expected_sha256, 0, dest_copy=copy_to)
            return {
                "asset_id": asset_id,
                "resolution_source": "CACHED_LOCAL",
                "local_path": str(copy_to or cached_candidate),
                "source_path": str(cached_candidate),
                "bytes": expected_bytes,
                "sha256": expected_sha256,
                "glb_v2_verified": True,
                "source_info": index.sources_by_id.get(source_id),
                "compatibility": index.skeleton_families.get(rec.get("skeleton_family") or ""),
                "license_notice": index._license_notice(source_id),
                "record": rec,
            }
        except ValueError:
            # Size collision or mismatch in local cache: fall through to authoritative Drive archive.
            pass

    # 2. On-demand Google Drive ARCHIVE lookup & disambiguation.
    if archive_dir is None or archive_dir.is_symlink() or not archive_dir.is_dir():
        raise FileNotFoundError(f"Google Drive archive root not accessible: {archive_dir}")

    candidate_paths: list[Path] = []
    seen: set[Path] = set()
    for root in archive_candidate_roots(archive_dir, source_id):
        if root.is_symlink() or not root.is_dir():
            continue
        assert_no_symlinks_under(archive_dir, root)
        for match in find_named_files(root, basename, max_depth=3):
            if match not in seen:
                seen.add(match)
                candidate_paths.append(match)

    matched_path: Path | None = None
    size_matched = False
    for cand in candidate_paths:
        assert_no_symlinks_under(archive_dir, cand)
        try:
            st = cand.lstat()
        except OSError:
            continue
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode) or st.st_size != expected_bytes:
            continue
        size_matched = True
        try:
            read_verified_file_bounded(cand, expected_bytes, expected_sha256, timeout_s, dest_copy=copy_to)
            matched_path = cand
            break
        except ValueError:
            continue

    if matched_path is None:
        if size_matched:
            raise RuntimeError(
                f"Found byte-size match for {asset_id} in Google Drive archive, but SHA-256/GLB validation failed."
            )
        raise FileNotFoundError(f"Could not locate {basename} ({expected_bytes} bytes) for {asset_id} in {archive_dir}")

    effective_local = copy_to or matched_path
    if cache_local:
        if cache_dir is None:
            raise ValueError("Cannot cache locally without verified_cache_dir configured")
        if cache_dir.is_symlink():
            raise ValueError(f"Symlink disallowed at verified_cache_dir: {cache_dir}")
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_target = cache_dir / source_id / basename
        min_local_gib = float(cfg.get("min_local_free_gib", cfg.get("min_macbook_free_gib", 2.0)))
        if copy_to is None:
            with tempfile.TemporaryDirectory(prefix="dexsculpt-cache-") as tmp:
                tmp_file = Path(tmp) / basename
                read_verified_file_bounded(matched_path, expected_bytes, expected_sha256, timeout_s, dest_copy=tmp_file)
                _atomic_install_local_cache(
                    source_bytes_path=tmp_file,
                    cache_target=cache_target,
                    cache_dir=cache_dir,
                    expected_bytes=expected_bytes,
                    expected_sha256=expected_sha256,
                    min_free_gib=min_local_gib,
                )
        else:
            _atomic_install_local_cache(
                source_bytes_path=copy_to,
                cache_target=cache_target,
                cache_dir=cache_dir,
                expected_bytes=expected_bytes,
                expected_sha256=expected_sha256,
                min_free_gib=min_local_gib,
            )
        effective_local = copy_to or cache_target

    return {
        "asset_id": asset_id,
        "resolution_source": "ARCHIVE_GOOGLE_DRIVE",
        "local_path": str(effective_local),
        "source_path": str(matched_path),
        "cached_local_path": str(cache_dir / source_id / basename) if cache_local and cache_dir else None,
        "bytes": expected_bytes,
        "sha256": expected_sha256,
        "glb_v2_verified": True,
        "source_info": index.sources_by_id.get(source_id),
        "compatibility": index.skeleton_families.get(rec.get("skeleton_family") or ""),
        "license_notice": index._license_notice(source_id),
        "record": rec,
    }


def _ssh_python(host: str, script: str, args: list[str], timeout: int = 60) -> dict[str, Any]:
    arg_str = " ".join(shlex.quote(a) for a in args)
    cmd_str = f"/usr/bin/python3 -c {shlex.quote(script)} {arg_str}".rstrip()
    proc = subprocess.run(
        ["ssh", *SSH_OPTS, host, cmd_str],
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return json.loads(proc.stdout)


def _require_remote_settings(cfg: dict[str, Any]) -> tuple[str, str]:
    host = str(cfg.get("remote_host") or "").strip()
    staging_raw = str(cfg.get("remote_staging_dir") or "").strip()
    if not host or not staging_raw:
        raise ValueError(
            "Remote staging requires remote_host and remote_staging_dir in your private catalog config JSON"
        )
    return host, staging_raw.rstrip("/")


def stage_to_remote(
    index: CatalogIndex,
    cfg: dict[str, Any],
    asset_id: str,
    *,
    cache_local: bool = False,
) -> dict[str, Any]:
    """Ensure a verified GLB is staged in the remote host's bounded catalog cache."""
    rec = index.get(asset_id)
    source_id = _validate_safe_token(rec.get("source_id") or "", "source_id")
    basename = _validate_safe_token(rec.get("processed_glb_basename") or "", "processed_glb_basename", glb_only=True)
    expected_bytes = int(rec["processed_glb_bytes"])
    expected_sha = str(rec["processed_glb_sha256"]).lower()
    max_bytes = int(cfg.get("max_asset_bytes", 104857600))
    if expected_bytes > max_bytes:
        raise ValueError(f"Asset {asset_id} exceeds max_asset_bytes ({expected_bytes} > {max_bytes})")

    host, staging_root = _require_remote_settings(cfg)
    remote_dir = f"{staging_root}/{source_id}"
    remote_path = f"{remote_dir}/{expected_sha[:12]}_{basename}"
    min_remote_gib = str(cfg.get("min_remote_free_gib", 1.5))

    cache_raw = cfg.get("verified_cache_dir")
    cache_dir = Path(cache_raw).expanduser() if cache_raw else None
    fast_cached = is_cached_fast(rec, cache_dir)

    probe = _ssh_python(
        host,
        REMOTE_STAGE_PROBE,
        [staging_root, remote_dir, remote_path, min_remote_gib, str(expected_bytes), expected_sha],
    )
    if probe.get("exists"):
        res_info = (
            resolve_asset(index, cfg, asset_id, cache_local=False)
            if fast_cached is not None
            else {
                "asset_id": asset_id,
                "resolution_source": "REMOTE_STAGING_CACHE",
                "local_path": None,
                "bytes": expected_bytes,
                "sha256": expected_sha,
                "glb_v2_verified": True,
                "source_info": index.sources_by_id.get(source_id),
                "compatibility": index.skeleton_families.get(rec.get("skeleton_family") or ""),
                "license_notice": index._license_notice(source_id),
                "record": rec,
            }
        )
        return {
            "resolution": res_info,
            "staging": {
                "status": "REMOTE_ALREADY_STAGED",
                "host": host,
                "remote_path": remote_path,
                "bytes": expected_bytes,
                "sha256": expected_sha,
                "remote_free_gib": probe.get("free_gib"),
            },
        }

    with tempfile.TemporaryDirectory(prefix="dexsculpt-stage-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        os.chmod(tmp_dir, 0o700)
        stage_local_copy = tmp_dir / basename if fast_cached is None else None
        resolved = resolve_asset(index, cfg, asset_id, cache_local=cache_local, copy_to=stage_local_copy)
        scp_source = Path(resolved["local_path"])
        remote_part = f"{remote_path}.part.{os.getpid()}"
        try:
            subprocess.run(
                ["scp", "-p", *SSH_OPTS, str(scp_source), f"{host}:{remote_part}"],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
            verified = _ssh_python(
                host,
                REMOTE_VERIFY_PROMOTE,
                [
                    remote_part,
                    remote_path,
                    str(expected_bytes),
                    expected_sha,
                    staging_root,
                    str(int(cfg.get("max_remote_cache_mb", 512))),
                ],
            )
        except Exception:
            subprocess.run(
                ["ssh", *SSH_OPTS, host, f"rm -f {shlex.quote(remote_part)}"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            raise

    return {
        "resolution": resolved,
        "staging": {
            "status": "REMOTE_SCP_VERIFIED",
            "host": host,
            "remote_path": remote_path,
            "bytes": verified["bytes"],
            "sha256": verified["sha256"],
            "remote_free_gib": verified.get("free_gib"),
            "evicted_files": verified.get("evicted_files", 0),
            "evicted_bytes": verified.get("evicted_bytes", 0),
        },
    }


def _parse_vec3(raw: str) -> tuple[float, float, float]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        raise ValueError(f"Expected x,y,z triplet, got: {raw!r}")
    return (float(parts[0]), float(parts[1]), float(parts[2]))


def _safe_blender_tag(record: dict[str, Any], sha256: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", (record.get("display_name") or record["asset_id"])).strip("_")
    base = (base or "Asset")[:36]
    return f"{base}_{sha256[:6]}"


def build_blender_import_script(
    *,
    remote_path: str,
    tag: str,
    collection_name: str | None,
    location: tuple[float, float, float],
    rotation_deg: tuple[float, float, float],
    scale: float,
    clear_scene: bool,
    save_blend: str | None,
    ground_on_z0: bool = False,
) -> str:
    """Build a Blender 5.2+ MCP script that imports a GLB while excluding bone-shape helper meshes."""
    col_name = (collection_name or f"Catalog_{tag}")[:62]
    root_name = f"CatalogRoot_{tag}"[:62]
    return f"""
import json, math, os
import bpy
from mathutils import Vector

if {bool(clear_scene)!r}:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.context.scene.collection.children):
        bpy.context.scene.collection.children.unlink(col)
        if col.users == 0:
            bpy.data.collections.remove(col)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.materials,
        bpy.data.actions,
        bpy.data.images,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.collections,
    ):
        for db in list(datablocks):
            if db.users == 0:
                datablocks.remove(db)

before_objs = set(bpy.data.objects)
before_actions = set(bpy.data.actions)
gltf_kwargs = {{"filepath": {remote_path!r}}}
if "disable_bone_shape" in bpy.ops.import_scene.gltf.get_rna_type().properties:
    gltf_kwargs["disable_bone_shape"] = True
bpy.ops.import_scene.gltf(**gltf_kwargs)
helper_objs = set()
for o in bpy.data.objects:
    if o.type == "ARMATURE" and o.pose:
        for pb in o.pose.bones:
            if pb.custom_shape is not None:
                helper_objs.add(pb.custom_shape)
for col in bpy.data.collections:
    if col.name.startswith("glTF_not_exported"):
        helper_objs.update(col.objects)
new_objs = [o for o in bpy.data.objects if o not in before_objs and o not in helper_objs]
new_obj_set = set(new_objs)
new_actions = sorted(a.name for a in bpy.data.actions if a not in before_actions)

col_name = {col_name!r}
target_col = bpy.data.collections.get(col_name)
if target_col is None:
    target_col = bpy.data.collections.new(col_name)
    bpy.context.scene.collection.children.link(target_col)
elif target_col.name not in bpy.context.scene.collection.children:
    bpy.context.scene.collection.children.link(target_col)

for obj in new_objs:
    if obj.name not in target_col.objects:
        target_col.objects.link(obj)
    for col in list(obj.users_collection):
        if col != target_col:
            col.objects.unlink(obj)

root_empty = bpy.data.objects.new({root_name!r}, None)
root_empty.empty_display_type = "PLAIN_AXES"
root_empty.empty_display_size = 0.25
target_col.objects.link(root_empty)

roots = [o for o in new_objs if o.parent is None or o.parent not in new_obj_set]
for r in roots:
    r.parent = root_empty

root_empty.location = {tuple(location)!r}
root_empty.rotation_mode = "XYZ"
root_empty.rotation_euler = tuple(math.radians(a) for a in {tuple(rotation_deg)!r})
root_empty.scale = ({float(scale)!r}, {float(scale)!r}, {float(scale)!r})
bpy.context.view_layer.update()

def _compute_world_bbox():
    mins = [float("inf"), float("inf"), float("inf")]
    maxs = [float("-inf"), float("-inf"), float("-inf")]
    cnt = 0
    arms = []
    for obj in new_objs:
        if obj.type == "MESH":
            cnt += 1
            for corner in obj.bound_box:
                wc = obj.matrix_world @ Vector(corner)
                for idx in range(3):
                    mins[idx] = min(mins[idx], wc[idx])
                    maxs[idx] = max(maxs[idx], wc[idx])
        elif obj.type == "ARMATURE":
            arms.append({{"name": obj.name, "bones": len(obj.data.bones)}})
    bb = None if cnt == 0 else {{
        "min": [round(v, 4) for v in mins],
        "max": [round(v, 4) for v in maxs],
        "size": [round(maxs[i] - mins[i], 4) for i in range(3)],
    }}
    return cnt, arms, bb

mesh_count, armatures, bbox = _compute_world_bbox()
if {bool(ground_on_z0)!r} and bbox is not None:
    root_empty.location.z -= bbox["min"][2]
    bpy.context.view_layer.update()
    mesh_count, armatures, bbox = _compute_world_bbox()

saved_blend = None
if {save_blend!r}:
    save_path = {save_blend!r}
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=save_path)
    saved_blend = save_path

print("CATALOG_IMPORT_JSON:" + json.dumps({{
    "collection": target_col.name,
    "root_empty": root_empty.name,
    "imported_object_count": len(new_objs),
    "mesh_count": mesh_count,
    "armatures": armatures,
    "new_actions": new_actions,
    "grounded_on_z0": {bool(ground_on_z0)!r},
    "world_bbox": bbox,
    "saved_blend": saved_blend,
}}))
"""


def build_attach_prop_script(
    *,
    remote_path: str,
    tag: str,
    target_armature: str,
    bone_name: str,
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: float = 1.0,
    gltf_bone_align: bool = True,
    save_blend: str | None = None,
) -> str:
    """Build a Blender 5.2+ MCP script that attaches a prop GLB to an armature bone socket."""
    col_name = f"Prop_{tag}"[:62]
    root_name = f"PropRoot_{tag}"[:62]
    return f"""
import json, math, os
import bpy
from mathutils import Matrix, Vector

arm = bpy.data.objects.get({target_armature!r})
if arm is None or arm.type != "ARMATURE":
    raise ValueError(f"Target armature not found or not an ARMATURE: {target_armature!r}")

resolved_bone = None
if {bone_name!r} in arm.data.bones:
    resolved_bone = {bone_name!r}
else:
    target_lower = {bone_name!r}.lower()
    for b in arm.data.bones:
        if b.name.lower() == target_lower:
            resolved_bone = b.name
            break
if resolved_bone is None:
    raise ValueError(f"Bone {bone_name!r} not found in {{arm.name}}. Available: {{[b.name for b in arm.data.bones]}}")

before_objs = set(bpy.data.objects)
gltf_kwargs = {{"filepath": {remote_path!r}}}
if "disable_bone_shape" in bpy.ops.import_scene.gltf.get_rna_type().properties:
    gltf_kwargs["disable_bone_shape"] = True
bpy.ops.import_scene.gltf(**gltf_kwargs)
helper_objs = set()
for o in bpy.data.objects:
    if o.type == "ARMATURE" and o.pose:
        for pb in o.pose.bones:
            if pb.custom_shape is not None:
                helper_objs.add(pb.custom_shape)
for col in bpy.data.collections:
    if col.name.startswith("glTF_not_exported"):
        helper_objs.update(col.objects)
new_objs = [o for o in bpy.data.objects if o not in before_objs and o not in helper_objs]
new_obj_set = set(new_objs)

target_col = bpy.data.collections.get({col_name!r})
if target_col is None:
    target_col = bpy.data.collections.new({col_name!r})
    bpy.context.scene.collection.children.link(target_col)
for obj in new_objs:
    if obj.name not in target_col.objects:
        target_col.objects.link(obj)
    for col in list(obj.users_collection):
        if col != target_col:
            col.objects.unlink(obj)

prop_root = bpy.data.objects.new({root_name!r}, None)
prop_root.empty_display_type = "PLAIN_AXES"
prop_root.empty_display_size = 0.15
target_col.objects.link(prop_root)

roots = [o for o in new_objs if o.parent is None or o.parent not in new_obj_set]
for r in roots:
    r.parent = prop_root

bone_len = arm.data.bones[resolved_bone].length
prop_root.parent = arm
prop_root.parent_type = "BONE"
prop_root.parent_bone = resolved_bone
align = Matrix.Rotation(-math.pi * 0.5, 4, "X") if {bool(gltf_bone_align)!r} else Matrix.Identity(4)
prop_root.matrix_parent_inverse = Matrix.Translation((0.0, -bone_len, 0.0)) @ align
prop_root.location = {tuple(offset)!r}
prop_root.rotation_mode = "XYZ"
prop_root.rotation_euler = tuple(math.radians(a) for a in {tuple(rotation_deg)!r})
prop_root.scale = ({float(scale)!r}, {float(scale)!r}, {float(scale)!r})
bpy.context.view_layer.update()

socket_world = arm.matrix_world @ arm.pose.bones[resolved_bone].head
socket_distance_m = round((prop_root.matrix_world.translation - socket_world).length, 6)
mesh_count = sum(1 for o in new_objs if o.type == "MESH")

saved_blend = None
if {save_blend!r}:
    save_path = {save_blend!r}
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=save_path)
    saved_blend = save_path

print("CATALOG_ATTACH_JSON:" + json.dumps({{
    "target_armature": arm.name,
    "bone_name": resolved_bone,
    "collection": target_col.name,
    "prop_root": prop_root.name,
    "imported_object_count": len(new_objs),
    "mesh_count": mesh_count,
    "socket_world": [round(float(v), 4) for v in socket_world],
    "prop_world": [round(float(v), 4) for v in prop_root.matrix_world.translation],
    "socket_distance_m": socket_distance_m,
    "gltf_bone_align": {bool(gltf_bone_align)!r},
    "saved_blend": saved_blend,
}}))
"""


def build_bind_animation_script(
    *,
    remote_path: str | None,
    target_armature: str,
    clip_query: str | None = None,
    frame: int | None = None,
    set_frame_range: bool = True,
    save_blend: str | None = None,
) -> str:
    """Build a Blender 5.2+ MCP script that binds a slotted Action and measures mesh deformation."""
    return f"""
import json, os
import bpy

arm = bpy.data.objects.get({target_armature!r})
if arm is None or arm.type != "ARMATURE":
    raise ValueError(f"Target armature not found or not an ARMATURE: {target_armature!r}")

def _descendant_meshes(root_obj):
    out = []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        cur = o.parent
        while cur is not None:
            if cur == root_obj:
                out.append(o)
                break
            cur = cur.parent
    return out

skinned_meshes = _descendant_meshes(arm)
candidate_actions = []
if {remote_path!r}:
    before_objs = set(bpy.data.objects)
    before_actions = set(bpy.data.actions)
    before_meshes = set(bpy.data.meshes)
    before_armatures = set(bpy.data.armatures)
    before_materials = set(bpy.data.materials)
    before_cols = set(bpy.data.collections)
    gltf_kwargs = {{"filepath": {remote_path!r}}}
    if "disable_bone_shape" in bpy.ops.import_scene.gltf.get_rna_type().properties:
        gltf_kwargs["disable_bone_shape"] = True
    bpy.ops.import_scene.gltf(**gltf_kwargs)
    candidate_actions = [a for a in bpy.data.actions if a not in before_actions]
    for o in list(bpy.data.objects):
        if o not in before_objs:
            bpy.data.objects.remove(o, do_unlink=True)
    for col in list(bpy.data.collections):
        if col not in before_cols and col.users == 0:
            bpy.data.collections.remove(col)
    for coll, prev in (
        (bpy.data.meshes, before_meshes),
        (bpy.data.armatures, before_armatures),
        (bpy.data.materials, before_materials),
    ):
        for db in list(coll):
            if db not in prev and db.users == 0:
                coll.remove(db)
else:
    candidate_actions = list(bpy.data.actions)

if not candidate_actions:
    raise ValueError("No animation actions found to bind")

chosen = None
q = ({clip_query!r} or "").strip().lower()
if q:
    for a in candidate_actions:
        if a.name.lower() == q:
            chosen = a
            break
    if chosen is None:
        for a in candidate_actions:
            if q in a.name.lower():
                chosen = a
                break
    if chosen is None:
        raise ValueError(f"Clip matching {{q!r}} not found. Available: {{[a.name for a in candidate_actions]}}")
else:
    for a in candidate_actions:
        if "t-pose" not in a.name.lower():
            chosen = a
            break
    if chosen is None:
        chosen = candidate_actions[0]

available_clips = sorted(a.name for a in candidate_actions)
if {remote_path!r}:
    for a in candidate_actions:
        if a != chosen:
            a.use_fake_user = False
            if a.users == 0:
                bpy.data.actions.remove(a)

ad = arm.animation_data or arm.animation_data_create()
ad.action = chosen
assigned_slot = None
if hasattr(chosen, "slots") and hasattr(ad, "action_slot"):
    obj_slots = [s for s in chosen.slots if getattr(s, "target_id_type", None) == "OBJECT"]
    if obj_slots:
        ad.action_slot = obj_slots[0]
        assigned_slot = obj_slots[0].identifier

f_start = int(round(chosen.frame_range[0]))
f_end = int(round(chosen.frame_range[1]))
if f_end <= f_start:
    f_end = f_start + 1
if {bool(set_frame_range)!r}:
    bpy.context.scene.frame_start = f_start
    bpy.context.scene.frame_end = f_end

def _sample_positions(frame_num):
    bpy.context.scene.frame_set(frame_num)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    pts = []
    for m in skinned_meshes:
        eval_obj = m.evaluated_get(deps)
        mesh_data = eval_obj.to_mesh()
        try:
            mw = eval_obj.matrix_world
            for v in mesh_data.vertices:
                pts.append(mw @ v.co)
        finally:
            eval_obj.to_mesh_clear()
    return pts

mid_frame = f_start + max(1, (f_end - f_start) // 2)
pts_a = _sample_positions(f_start)
pts_b = _sample_positions(mid_frame)
max_disp = 0.0
for p0, p1 in zip(pts_a, pts_b):
    d = (p1 - p0).length
    if d > max_disp:
        max_disp = d

target_frame = {frame!r} if {frame!r} is not None else mid_frame
bpy.context.scene.frame_set(int(target_frame))
bpy.context.view_layer.update()

saved_blend = None
if {save_blend!r}:
    save_path = {save_blend!r}
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=save_path)
    saved_blend = save_path

print("CATALOG_ANIM_JSON:" + json.dumps({{
    "target_armature": arm.name,
    "clip_name": chosen.name,
    "action_slot": assigned_slot,
    "frame_start": f_start,
    "frame_end": f_end,
    "evaluated_frame": int(target_frame),
    "max_vertex_displacement": round(float(max_disp), 6),
    "available_clips": available_clips,
    "saved_blend": saved_blend,
}}))
"""


def _resolve_launcher(cfg: dict[str, Any], explicit_launcher: str | None) -> str:
    candidate = (
        explicit_launcher
        or cfg.get("mcp_launcher")
        or os.environ.get(ENV_MCP_LAUNCHER, "").strip()
    )
    if not candidate:
        raise ValueError(
            f"MCP launcher not configured; pass --launcher, set {ENV_MCP_LAUNCHER}, or set mcp_launcher in catalog.json"
        )
    return str(Path(candidate).expanduser())


def _run_blender_mcp(mcp_launcher: str, code: str, marker_prefix: str) -> dict[str, Any]:
    with StdioMCPClient([mcp_launcher], timeout=180.0) as client:
        client.initialize()
        mcp_result = client.call_tool("execute_blender_code", {"code": code})

    if mcp_result.get("isError"):
        texts = [c.get("text", "") for c in mcp_result.get("content", []) if c.get("type") == "text"]
        raise RuntimeError(f"Blender MCP execution failed: {' '.join(texts)}")

    combined_text = "\n".join(
        c.get("text", "") for c in mcp_result.get("content", []) if c.get("type") == "text"
    )
    for line in combined_text.splitlines():
        if line.startswith(marker_prefix):
            return json.loads(line.split(marker_prefix, 1)[1])
    raise RuntimeError(f"Missing {marker_prefix} in Blender MCP output:\n{combined_text[-1500:]}")


def import_to_blender(
    index: CatalogIndex,
    cfg: dict[str, Any],
    asset_id: str,
    *,
    clear_scene: bool = False,
    collection: str | None = None,
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: float = 1.0,
    save_blend: str | None = None,
    ground_on_z0: bool = False,
    cache_local: bool = False,
    launcher: str | None = None,
) -> dict[str, Any]:
    """Resolve, stage to remote host, and import a catalog asset into live Blender via MCP."""
    mcp_launcher = _resolve_launcher(cfg, launcher)
    staged = stage_to_remote(index, cfg, asset_id, cache_local=cache_local)
    res = staged["resolution"]
    rec = res["record"]
    tag = _safe_blender_tag(rec, res["sha256"])
    code = build_blender_import_script(
        remote_path=staged["staging"]["remote_path"],
        tag=tag,
        collection_name=collection,
        location=location,
        rotation_deg=rotation_deg,
        scale=scale,
        clear_scene=clear_scene,
        save_blend=save_blend,
        ground_on_z0=ground_on_z0,
    )
    import_info = _run_blender_mcp(mcp_launcher, code, "CATALOG_IMPORT_JSON:")
    return {
        "asset_id": asset_id,
        "resolution": res,
        "staging": staged["staging"],
        "blender_import": import_info,
    }


def attach_prop_to_bone(
    index: CatalogIndex,
    cfg: dict[str, Any],
    asset_id: str,
    *,
    target_armature: str,
    bone_name: str,
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotation_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: float = 1.0,
    gltf_bone_align: bool = True,
    save_blend: str | None = None,
    cache_local: bool = False,
    launcher: str | None = None,
) -> dict[str, Any]:
    """Resolve, stage, and natively attach a prop GLB to an armature bone socket via MCP."""
    mcp_launcher = _resolve_launcher(cfg, launcher)
    staged = stage_to_remote(index, cfg, asset_id, cache_local=cache_local)
    res = staged["resolution"]
    tag = _safe_blender_tag(res["record"], res["sha256"])
    code = build_attach_prop_script(
        remote_path=staged["staging"]["remote_path"],
        tag=tag,
        target_armature=target_armature,
        bone_name=bone_name,
        offset=offset,
        rotation_deg=rotation_deg,
        scale=scale,
        gltf_bone_align=gltf_bone_align,
        save_blend=save_blend,
    )
    attach_info = _run_blender_mcp(mcp_launcher, code, "CATALOG_ATTACH_JSON:")
    return {
        "asset_id": asset_id,
        "resolution": res,
        "staging": staged["staging"],
        "attachment": attach_info,
    }


def bind_animation_to_armature(
    index: CatalogIndex,
    cfg: dict[str, Any],
    asset_id: str,
    *,
    target_armature: str,
    target_asset_id: str | None = None,
    clip_query: str | None = None,
    frame: int | None = None,
    set_frame_range: bool = True,
    force_skeleton: bool = False,
    save_blend: str | None = None,
    cache_local: bool = False,
    launcher: str | None = None,
) -> dict[str, Any]:
    """Bind a compatible animation pack (or embedded character clip) using Blender 5.2 Action Slots."""
    mcp_launcher = _resolve_launcher(cfg, launcher)
    anim_rec = index.get(asset_id)
    if target_asset_id and not force_skeleton:
        target_rec = index.get(target_asset_id)
        anim_fam = anim_rec.get("skeleton_family")
        target_fam = target_rec.get("skeleton_family")
        if anim_fam and target_fam and anim_fam != "None" and target_fam != "None" and anim_fam != target_fam:
            raise ValueError(
                f"Incompatible skeleton families: target {target_asset_id!r} ({target_fam}) != {asset_id!r} ({anim_fam}). Pass --force-skeleton to override."
            )

    staged = stage_to_remote(index, cfg, asset_id, cache_local=cache_local)
    remote_path = staged["staging"]["remote_path"]
    # If the caller targets the same embedded character GLB (e.g. goblin Attack), avoid re-importing duplicate objects
    if target_asset_id and target_asset_id == asset_id:
        remote_path = None
    code = build_bind_animation_script(
        remote_path=remote_path,
        target_armature=target_armature,
        clip_query=clip_query,
        frame=frame,
        set_frame_range=set_frame_range,
        save_blend=save_blend,
    )
    anim_info = _run_blender_mcp(mcp_launcher, code, "CATALOG_ANIM_JSON:")
    return {
        "asset_id": asset_id,
        "resolution": staged["resolution"],
        "staging": staged["staging"],
        "animation": anim_info,
    }


def cmd_status(index: CatalogIndex, cfg: dict[str, Any], *, no_remote: bool = False) -> dict[str, Any]:
    cache_raw = cfg.get("verified_cache_dir")
    cache_dir = Path(cache_raw).expanduser() if cache_raw else None
    archive_raw = cfg.get("gdrive_archive_dir")
    archive_dir = Path(archive_raw).expanduser() if archive_raw else None
    cached_count = 0
    cached_bytes = 0
    for rec in index.records:
        if is_cached_fast(rec, cache_dir) is not None:
            cached_count += 1
            cached_bytes += int(rec.get("processed_glb_bytes") or 0)

    archive_item_id = None
    if archive_dir is not None and archive_dir.is_dir() and not archive_dir.is_symlink():
        x_proc = subprocess.run(
            ["xattr", "-p", "com.google.drivefs.item-id#S", str(archive_dir)],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if x_proc.returncode == 0 and x_proc.stdout.strip():
            archive_item_id = x_proc.stdout.strip()

    remote_status: dict[str, Any] | None = None
    if not no_remote:
        host, staging_root = _require_remote_settings(cfg)
        remote_status = _ssh_python(host, REMOTE_STATUS_PROBE, [staging_root])

    return {
        "total_records": len(index.records),
        "source_count": len({r["source_id"] for r in index.records}),
        "cached_local_count": cached_count,
        "cached_local_bytes": cached_bytes,
        "cached_local_mb": round(cached_bytes / (1024 * 1024), 2),
        "verified_cache_dir": str(cache_dir) if cache_dir else None,
        "gdrive_archive_mounted": bool(archive_dir and archive_dir.is_dir()),
        "gdrive_archive_dir": str(archive_dir) if archive_dir else None,
        "gdrive_archive_item_id": archive_item_id or cfg.get("gdrive_archive_item_id"),
        "remote": remote_status,
    }


def prune_remote_cache(cfg: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    host, staging_root = _require_remote_settings(cfg)
    return _ssh_python(
        host,
        REMOTE_PRUNE_CACHE,
        [staging_root, "1" if dry_run else "0"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="Optional path to private catalog.json")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Inspect catalog, local cache, Drive archive, and remote staging")
    p_status.add_argument("--no-remote", action="store_true", help="Skip SSH probe to remote host")

    p_search = sub.add_parser("search", help="Search the humanoid catalog")
    p_search.add_argument("--query", default=None)
    p_search.add_argument("--source", default=None)
    p_search.add_argument("--type", dest="asset_type", default=None)
    p_search.add_argument("--skeleton", default=None)
    p_search.add_argument("--license", dest="license_query", default=None)
    p_search.add_argument("--cached-only", action="store_true")
    p_search.add_argument("--max-mb", type=float, default=None)
    p_search.add_argument("--limit", type=int, default=25)

    sub.add_parser("sources", help="List all catalog sources and cached counts")

    p_info = sub.add_parser("info", help="Show full catalog, source, and compatibility details for an asset")
    p_info.add_argument("asset_id")

    p_compat = sub.add_parser("compatible", help="Find compatible animations, accessories, modular parts, and rigs")
    p_compat.add_argument("asset_id")
    p_compat.add_argument("--limit", type=int, default=50)

    p_resolve = sub.add_parser("resolve", help="Resolve and SHA-256 + GLB v2 verify an asset")
    p_resolve.add_argument("asset_id")
    p_resolve.add_argument("--cache-local", action="store_true", help="Persist verified GLB into local verified cache")

    p_stage = sub.add_parser("stage", help="Verify and stage an asset onto the remote Blender host")
    p_stage.add_argument("asset_id")
    p_stage.add_argument("--cache-local", action="store_true")

    p_import = sub.add_parser("import", help="Resolve, stage, and import an asset into live Blender MCP")
    p_import.add_argument("asset_id")
    p_import.add_argument("--clear-scene", action="store_true")
    p_import.add_argument("--collection", default=None)
    p_import.add_argument("--location", default="0,0,0")
    p_import.add_argument("--rotation-deg", default="0,0,0")
    p_import.add_argument("--scale", type=float, default=1.0)
    p_import.add_argument("--ground-on-z0", action="store_true", help="Shift root Empty in Z so world bbox sits flush on Z=0")
    p_import.add_argument("--save-blend", default=None)
    p_import.add_argument("--cache-local", action="store_true")
    p_import.add_argument("--launcher", default=None, help="Optional MCP stdio launcher executable path")

    p_attach = sub.add_parser("attach-prop", help="Attach a catalog prop/accessory GLB to an armature bone socket")
    p_attach.add_argument("asset_id")
    p_attach.add_argument("--target-armature", required=True)
    p_attach.add_argument("--bone", required=True)
    p_attach.add_argument("--offset", default="0,0,0")
    p_attach.add_argument("--rotation-deg", default="0,0,0")
    p_attach.add_argument("--scale", type=float, default=1.0)
    p_attach.add_argument("--no-gltf-bone-align", action="store_true", help="Skip -90 deg X alignment from glTF Y-up prop space into Blender bone space")
    p_attach.add_argument("--save-blend", default=None)
    p_attach.add_argument("--cache-local", action="store_true")
    p_attach.add_argument("--launcher", default=None)

    p_anim = sub.add_parser("bind-animation", help="Bind a compatible animation pack/clip using Blender 5.2 Action Slots")
    p_anim.add_argument("asset_id")
    p_anim.add_argument("--target-armature", required=True)
    p_anim.add_argument("--target-asset-id", default=None, help="Optional catalog asset_id of target armature for skeleton check")
    p_anim.add_argument("--clip", default=None, help="Optional clip name or substring (default: first non-T-Pose)")
    p_anim.add_argument("--frame", type=int, default=None, help="Optional frame to leave evaluated (default: midpoint)")
    p_anim.add_argument("--no-set-frame-range", action="store_true")
    p_anim.add_argument("--force-skeleton", action="store_true")
    p_anim.add_argument("--save-blend", default=None)
    p_anim.add_argument("--cache-local", action="store_true")
    p_anim.add_argument("--launcher", default=None)

    p_prune = sub.add_parser("prune-remote-cache", help="Remove staged GLBs from configured remote staging cache")
    p_prune.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    cfg = load_catalog_config(args.config)
    index = CatalogIndex(cfg["metadata_dir"])
    cache_raw = cfg.get("verified_cache_dir")
    cache_dir = Path(cache_raw).expanduser() if cache_raw else None

    if args.command == "status":
        out = cmd_status(index, cfg, no_remote=args.no_remote)
    elif args.command == "search":
        out = index.search(
            query=args.query,
            source_id=args.source,
            asset_type=args.asset_type,
            skeleton_family=args.skeleton,
            license_query=args.license_query,
            cached_only=args.cached_only,
            max_mb=args.max_mb,
            limit=args.limit,
            cache_dir=cache_dir,
        )
    elif args.command == "sources":
        out = index.sources(cache_dir=cache_dir)
    elif args.command == "info":
        out = index.info(args.asset_id, cache_dir=cache_dir)
    elif args.command == "compatible":
        out = index.compatible(args.asset_id, limit=args.limit, cache_dir=cache_dir)
    elif args.command == "resolve":
        out = resolve_asset(index, cfg, args.asset_id, cache_local=args.cache_local)
    elif args.command == "stage":
        out = stage_to_remote(index, cfg, args.asset_id, cache_local=args.cache_local)
    elif args.command == "import":
        out = import_to_blender(
            index,
            cfg,
            args.asset_id,
            clear_scene=args.clear_scene,
            collection=args.collection,
            location=_parse_vec3(args.location),
            rotation_deg=_parse_vec3(args.rotation_deg),
            scale=args.scale,
            save_blend=args.save_blend,
            ground_on_z0=args.ground_on_z0,
            cache_local=args.cache_local,
            launcher=args.launcher,
        )
    elif args.command == "attach-prop":
        out = attach_prop_to_bone(
            index,
            cfg,
            args.asset_id,
            target_armature=args.target_armature,
            bone_name=args.bone,
            offset=_parse_vec3(args.offset),
            rotation_deg=_parse_vec3(args.rotation_deg),
            scale=args.scale,
            gltf_bone_align=not args.no_gltf_bone_align,
            save_blend=args.save_blend,
            cache_local=args.cache_local,
            launcher=args.launcher,
        )
    elif args.command == "bind-animation":
        out = bind_animation_to_armature(
            index,
            cfg,
            args.asset_id,
            target_armature=args.target_armature,
            target_asset_id=args.target_asset_id,
            clip_query=args.clip,
            frame=args.frame,
            set_frame_range=not args.no_set_frame_range,
            force_skeleton=args.force_skeleton,
            save_blend=args.save_blend,
            cache_local=args.cache_local,
            launcher=args.launcher,
        )
    elif args.command == "prune-remote-cache":
        out = prune_remote_cache(cfg, dry_run=args.dry_run)
    else:
        parser.error(f"Unknown command: {args.command}")
        return 2

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
