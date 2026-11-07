"""Bounded renderer for THE SECOND LIGHT using the existing Sentinel builder."""
import argparse
import json
import os
import runpy
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from performance import ContractError, apply_performance, load_contract


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--performance", default=str(HERE / "second-light.performance.json"))
    parser.add_argument("--quality", choices=("interaction", "preview", "master"), default="interaction")
    parser.add_argument("--start-frame", type=int, default=1)
    parser.add_argument("--end-frame", type=int, default=48)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--save-blend", action="store_true")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def confined_paths(args):
    root = Path(args.output_root).expanduser().resolve(strict=True)
    raw = Path(args.output_dir).expanduser().absolute()
    if ".." in raw.parts:
        raise ContractError("output traversal is not allowed")
    cursor = Path(raw.anchor)
    for part in raw.parts[1:]:
        cursor /= part
        if cursor.is_symlink():
            raise ContractError("output path contains a symlink")
    out = raw.resolve(strict=False)
    if root == out or root not in out.parents:
        raise ContractError("output directory must be a child of output root")
    if not (1 <= args.start_frame <= args.end_frame <= 144) or args.end_frame - args.start_frame + 1 > 48:
        raise ContractError("frame range must be 1..144 and limited to 48 frames")
    return root, out


def build_scene(root, out, contract_path):
    contract = load_contract(contract_path, HERE)
    scene_dir = out / "_scene"
    scene_dir.mkdir(parents=True, exist_ok=True)
    source = HERE / "lantern_sentinel.py"
    old_argv = sys.argv
    try:
        sys.argv = [str(source), "--", "--output-root", str(root), "--output-dir", str(scene_dir),
                    "--quality", "interaction", "--start-frame", "1", "--end-frame", "1", "--build-only"]
        namespace = runpy.run_path(str(source), run_name="p7_reusable_sentinel_scene")
    finally:
        sys.argv = old_argv
    return apply_performance(namespace, contract), contract


def main():
    import bpy

    args = parse_args()
    root, out = confined_paths(args)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.glob("frame_*.png")):
        raise ContractError("output already contains frames; refusing overwrite")
    namespace, contract = build_scene(root, out, args.performance)
    scene = namespace["scene"]
    scene.render.resolution_x, scene.render.resolution_y = {
        "interaction": (320, 180), "preview": (640, 360), "master": (1280, 720)
    }[args.quality]
    scene.eevee.taa_render_samples = {"interaction": 8, "preview": 16, "master": 32}[args.quality]
    scene.render.filepath = str(out / "frame_")
    if args.save_blend:
        blend = root / "the-second-light-production.blend"
        if blend.exists():
            raise ContractError("production Blender file exists; refusing overwrite")
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    if args.build_only:
        print("P7_PERFORMANCE_SCENE", json.dumps({
            "id": contract["performance_id"], "blender": bpy.app.version_string,
            "engine": scene.render.engine, "gpu_backend": bpy.context.preferences.system.gpu_backend,
            "frames": scene.frame_end, "bones": len(namespace["arm"].bones),
            "ik_constraints": sum(1 for b in namespace["pose"] for c in b.constraints if c.type == "IK"),
            "actions": [a["type"] for a in contract["actions"]], "authored_animation": True,
            "physics_simulation": False
        }), flush=True)
        return
    records = []
    free_before = shutil.disk_usage(root).free
    for frame in range(args.start_frame, args.end_frame + 1):
        scene.frame_set(frame)
        path = out / ("frame_%04d.png" % frame)
        if path.exists():
            raise ContractError("refusing to overwrite an existing frame")
        scene.render.filepath = str(path)
        started = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        elapsed = time.perf_counter() - started
        record = {"frame": frame, "seconds": round(elapsed, 3), "bytes": path.stat().st_size}
        records.append(record)
        print("P7_PERFORMANCE_FRAME", json.dumps(record), flush=True)
        if elapsed > 60:
            raise RuntimeError("stop gate: one frame exceeded 60 seconds")
    print("P7_PERFORMANCE_RENDER", json.dumps({
        "id": contract["performance_id"], "blender": bpy.app.version_string,
        "engine": scene.render.engine, "gpu_backend": bpy.context.preferences.system.gpu_backend,
        "quality": args.quality, "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "range": [args.start_frame, args.end_frame], "frame_count": len(records),
        "seconds": round(sum(r["seconds"] for r in records), 3),
        "max_frame_seconds": max(r["seconds"] for r in records),
        "rendered_bytes": sum(r["bytes"] for r in records),
        "disk_free_before": free_before, "disk_free_after": shutil.disk_usage(root).free,
        "max_rss": __import__("resource").getrusage(__import__("resource").RUSAGE_SELF).ru_maxrss,
        "authored_animation": True, "physics_simulation": False
    }), flush=True)


if __name__ == "__main__":
    main()
