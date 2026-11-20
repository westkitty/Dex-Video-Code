#!/usr/bin/env python3
"""Versioned .blend asset & shader library manager with SHA-256 integrity checks.

Supports:
- Manifest creation (library-manifest.v1.json) inside a symlink-free --library-root
- Safe confined linking/appending inside Blender via bpy.data.libraries.load
- Starter procedural shader library generation (--create-starter-pack)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "library-manifest.v1.json"


def _has_symlink(path: Path) -> bool:
    cur = Path(path.anchor or "/")
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        cur = cur / part
        try:
            if stat.S_ISLNK(cur.lstat().st_mode):
                return True
        except FileNotFoundError:
            return False
    return False


def assert_confined_root(library_root: str | Path) -> Path:
    root = Path(library_root).expanduser()
    if not root.is_absolute():
        root = root.resolve()
    if _has_symlink(root):
        raise ValueError(f"Library root contains a symlink: {root}")
    if not root.is_dir():
        raise ValueError(f"Library root does not exist: {root}")
    resolved = root.resolve(strict=True)
    if resolved != root:
        raise ValueError("Library root must be canonical")
    return resolved


def assert_confined_blend(blend_path: str | Path, library_root: Path) -> Path:
    candidate = Path(blend_path)
    if not candidate.is_absolute():
        candidate = library_root / candidate
    if _has_symlink(candidate):
        raise ValueError(f"Blend path contains a symlink: {candidate}")
    resolved = candidate.resolve(strict=True)
    if os.path.commonpath((str(library_root), str(resolved))) != str(library_root):
        raise ValueError(f"Blend path escapes library root: {resolved}")
    if resolved.suffix.lower() != ".blend" or not resolved.is_file():
        raise ValueError(f"Library entry must be a regular .blend file: {resolved}")
    return resolved


def sha256_file(path: Path) -> tuple[int, str]:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for blk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blk)
    return path.stat().st_size, h.hexdigest()


def build_library_manifest(library_root: str | Path, write_file: bool = True) -> dict[str, Any]:
    root = assert_confined_root(library_root)
    entries: dict[str, dict[str, Any]] = {}
    for p in sorted(root.rglob("*.blend")):
        if _has_symlink(p):
            raise ValueError(f"Symlinked .blend file refused in library: {p}")
        rel = p.relative_to(root).as_posix()
        size, digest = sha256_file(p)
        entries[rel] = {
            "relative_path": rel,
            "bytes": size,
            "sha256": digest,
        }
    manifest = {
        "schema_version": "blender-asset-library.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "entry_count": len(entries),
        "entries": entries,
    }
    if write_file:
        out_path = root / MANIFEST_FILENAME
        if out_path.is_symlink():
            raise ValueError("Manifest path is a symlink")
        out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_library_entry(blend_path: str | Path, library_root: str | Path) -> dict[str, Any]:
    root = assert_confined_root(library_root)
    target = assert_confined_blend(blend_path, root)
    rel = target.relative_to(root).as_posix()
    manifest_path = root / MANIFEST_FILENAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError(f"Missing or invalid {MANIFEST_FILENAME} in {root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "blender-asset-library.v1":
        raise ValueError("Unsupported asset library manifest schema")
    expected = manifest.get("entries", {}).get(rel)
    if not expected:
        raise ValueError(f"Blend file {rel!r} is not registered in {MANIFEST_FILENAME}")
    size, digest = sha256_file(target)
    if size != expected.get("bytes") or digest != expected.get("sha256"):
        raise ValueError(f"Integrity check failed for {rel!r}")
    return {"path": str(target), "relative_path": rel, "bytes": size, "sha256": digest}


def link_or_append_datablocks(
    blend_path: str | Path,
    library_root: str | Path,
    *,
    materials: tuple[str, ...] = (),
    objects: tuple[str, ...] = (),
    node_groups: tuple[str, ...] = (),
    link: bool = True,
    bpy_module: Any = None,
) -> dict[str, list[str]]:
    """Verify SHA-256 against manifest and link/append datablocks inside Blender."""
    verified = verify_library_entry(blend_path, library_root)
    if bpy_module is None:
        import bpy as bpy_module  # type: ignore

    loaded: dict[str, list[str]] = {"materials": [], "objects": [], "node_groups": []}
    with bpy_module.data.libraries.load(verified["path"], link=link) as (data_from, data_to):
        for name in materials:
            if name in data_from.materials:
                data_to.materials.append(name)
                loaded["materials"].append(name)
        for name in objects:
            if name in data_from.objects:
                data_to.objects.append(name)
                loaded["objects"].append(name)
        for name in node_groups:
            if name in data_from.node_groups:
                data_to.node_groups.append(name)
                loaded["node_groups"].append(name)
    return loaded


def resolve_blender_binary() -> str:
    app_bin = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    if app_bin.is_file() and os.access(app_bin, os.X_OK):
        return str(app_bin)
    env_bin = os.environ.get("BLENDER_BIN")
    if env_bin and Path(env_bin).is_file():
        return env_bin
    raise FileNotFoundError("Blender app-bundle binary not found")


def create_starter_pack(library_root: str | Path) -> dict[str, Any]:
    """Generate a compact procedural materials_pack.blend and manifest via background Blender."""
    root_path = Path(library_root).expanduser().resolve()
    if _has_symlink(root_path):
        raise ValueError("Library root contains a symlink")
    root_path.mkdir(parents=True, exist_ok=True)
    out_blend = root_path / "materials_pack.blend"
    scripts_dir = Path(__file__).resolve().parent

    py_expr = f"""
import sys
sys.path.insert(0, {str(scripts_dir)!r})
import bpy
import blender_render_pipeline as brp

for m in list(bpy.data.materials):
    bpy.data.materials.remove(m)

# 1. Iridescent Scale Material with AO & Pointiness Wear
sc = bpy.data.materials.new("Lib_Dragon_Scales")
sc.use_nodes = True
bs = sc.node_tree.nodes.get("Principled BSDF")
bs.inputs["Base Color"].default_value = (0.045, 0.16, 0.105, 1.0)
bs.inputs["Metallic"].default_value = 0.28
bs.inputs["Roughness"].default_value = 0.40
brp.add_procedural_edge_wear_and_ao(sc, wear_color=(0.38, 0.44, 0.34, 1.0), wear_strength=0.22)
sc.use_fake_user = True

# 2. Alpine Basalt & Snow Shader
rk = bpy.data.materials.new("Lib_Alpine_Basalt")
rk.use_nodes = True
bs_r = rk.node_tree.nodes.get("Principled BSDF")
bs_r.inputs["Base Color"].default_value = (0.08, 0.085, 0.10, 1.0)
bs_r.inputs["Roughness"].default_value = 0.86
brp.add_procedural_edge_wear_and_ao(rk, crevice_darkening=0.5, wear_color=(0.55, 0.62, 0.72, 1.0), wear_strength=0.28)
rk.use_fake_user = True

# 3. Volumetric Fire Material
vf = brp.build_volumetric_fire_material("Lib_Volumetric_Fire")
vf.use_fake_user = True

bpy.ops.wm.save_as_mainfile(filepath={str(out_blend)!r})
print("STARTER_PACK_SAVED")
"""
    blender_bin = resolve_blender_binary()
    proc = subprocess.run(
        [blender_bin, "--background", "--python-expr", py_expr],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )
    if proc.returncode != 0 or "STARTER_PACK_SAVED" not in proc.stdout:
        raise RuntimeError(f"Starter pack creation failed: {proc.stderr[-1000:]}")
    return build_library_manifest(root_path, write_file=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library-root", required=True, help="Symlink-free asset library directory")
    parser.add_argument("--build-manifest", action="store_true", help="Scan .blend files and write manifest")
    parser.add_argument("--verify", help="Verify relative .blend entry against manifest")
    parser.add_argument("--create-starter-pack", action="store_true", help="Generate starter materials_pack.blend via Blender")
    args = parser.parse_args()

    if args.create_starter_pack:
        print(json.dumps(create_starter_pack(args.library_root), indent=2))
        return 0
    if args.build_manifest:
        print(json.dumps(build_library_manifest(args.library_root, write_file=True), indent=2))
        return 0
    if args.verify:
        if not re.fullmatch(r"[A-Za-z0-9._/-]+\.blend", args.verify):
            raise ValueError("Invalid relative .blend entry name")
        print(json.dumps(verify_library_entry(args.verify, args.library_root), indent=2))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
