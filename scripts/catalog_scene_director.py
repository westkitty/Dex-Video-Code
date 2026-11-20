#!/usr/bin/env python3
"""Declarative DEX//SCULPT catalog scene director for Blender 5.2+ MCP pipelines.

Reads a `catalog-scene.v1` JSON manifest, resolves/stages characters, bone-socket
attachments, and slotted Animation Packs across local caches or Google Drive ARCHIVE,
assembles the scene non-destructively over Blender MCP (or background Blender),
runs programmatic spatial & deformation QA (floor contact, pairwise AABB overlap,
socket proximity, evaluated vertex displacement), renders a 2x2 multi-view spatial
QA sheet + 720p Hero Still + optional bounded H.264 MP4, pulls verified outputs
via multiplexed strict SCP, and optionally syncs to Google Drive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import dexsculpt_catalog as dc  # noqa: E402

SAFE_SCENE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
ALLOWED_BACKDROPS = frozenset({"studio_dark", "studio_warm", "clay"})
MAX_ANIM_FRAMES = 48


def validate_scene_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a `catalog-scene.v1` declarative scene manifest."""
    if not isinstance(manifest, dict):
        raise ValueError("Scene manifest must be a JSON object")
    if manifest.get("schema_version") != "catalog-scene.v1":
        raise ValueError("Unsupported schema_version (expected 'catalog-scene.v1')")

    scene_name = str(manifest.get("scene_name") or "").strip()
    if not SAFE_SCENE_NAME_RE.match(scene_name) or ".." in scene_name:
        raise ValueError(f"Invalid scene_name: {scene_name!r}")

    characters = manifest.get("characters")
    if not isinstance(characters, list) or not characters:
        raise ValueError("Manifest 'characters' must be a non-empty list")

    norm_chars: list[dict[str, Any]] = []
    for idx, ch in enumerate(characters):
        if not isinstance(ch, dict) or not ch.get("asset_id"):
            raise ValueError(f"Character entry {idx} must contain 'asset_id'")
        loc = ch.get("location", [0.0, 0.0, 0.0])
        rot = ch.get("rotation_deg", [0.0, 0.0, 0.0])
        scale = float(ch.get("scale", 1.0))
        if len(loc) != 3 or len(rot) != 3 or scale <= 0.0:
            raise ValueError(f"Character entry {idx} has invalid transform or scale")
        attachments = []
        for att_idx, att in enumerate(ch.get("attachments") or []):
            if not isinstance(att, dict) or not att.get("asset_id") or not att.get("bone"):
                raise ValueError(f"Attachment {att_idx} on character {idx} requires 'asset_id' and 'bone'")
            a_off = att.get("offset", [0.0, 0.0, 0.0])
            a_rot = att.get("rotation_deg", [0.0, 0.0, 0.0])
            a_scale = float(att.get("scale", 1.0))
            if len(a_off) != 3 or len(a_rot) != 3 or a_scale <= 0.0:
                raise ValueError(f"Attachment {att_idx} on character {idx} has invalid offset/rotation/scale")
            attachments.append(
                {
                    "asset_id": str(att["asset_id"]),
                    "bone": str(att["bone"]),
                    "offset": [float(v) for v in a_off],
                    "rotation_deg": [float(v) for v in a_rot],
                    "scale": a_scale,
                    "gltf_bone_align": bool(att.get("gltf_bone_align", True)),
                }
            )
        anim = ch.get("animation")
        norm_anim = None
        if anim is not None:
            if not isinstance(anim, dict):
                raise ValueError(f"Animation config on character {idx} must be an object")
            norm_anim = {
                "asset_id": str(anim.get("asset_id") or ch["asset_id"]),
                "clip": anim.get("clip"),
                "force_skeleton": bool(anim.get("force_skeleton", False)),
                "set_frame_range": bool(anim.get("set_frame_range", False)),
            }
        norm_chars.append(
            {
                "name": str(ch.get("name") or f"char_{idx}"),
                "asset_id": str(ch["asset_id"]),
                "location": [float(v) for v in loc],
                "rotation_deg": [float(v) for v in rot],
                "scale": scale,
                "ground_on_z0": bool(ch.get("ground_on_z0", True)),
                "attachments": attachments,
                "animation": norm_anim,
            }
        )

    backdrop = str(manifest.get("backdrop", "studio_dark"))
    if backdrop not in ALLOWED_BACKDROPS:
        raise ValueError(f"Unsupported backdrop {backdrop!r}; allowed: {sorted(ALLOWED_BACKDROPS)}")

    cam = manifest.get("camera") or {}
    norm_cam = {
        "lens_mm": float(cam.get("lens_mm", 45.0)),
        "elevation_deg": float(cam.get("elevation_deg", 14.0)),
        "azimuth_deg": float(cam.get("azimuth_deg", 0.0)),
        "margin": float(cam.get("margin", 1.35)),
    }
    if norm_cam["lens_mm"] <= 5.0 or norm_cam["margin"] < 1.0:
        raise ValueError("Camera lens_mm must be > 5 and margin >= 1.0")

    rnd = manifest.get("render") or {}
    start_f = int(rnd.get("start_frame", 1))
    end_f = int(rnd.get("end_frame", 36))
    anim_mp4 = bool(rnd.get("animation_mp4", False))
    if start_f < 1 or end_f < start_f:
        raise ValueError(f"Invalid render frame range: {start_f}..{end_f}")
    if anim_mp4 and (end_f - start_f + 1) > MAX_ANIM_FRAMES:
        raise ValueError(f"Bounded render policy limits animation_mp4 to <= {MAX_ANIM_FRAMES} frames")

    norm_render = {
        "quad_qa_sheet": bool(rnd.get("quad_qa_sheet", True)),
        "hero_still": bool(rnd.get("hero_still", True)),
        "hero_frame": rnd.get("hero_frame"),
        "hero_samples": int(rnd.get("hero_samples", 48)),
        "hero_width": int(rnd.get("hero_width", 1280)),
        "hero_height": int(rnd.get("hero_height", 720)),
        "animation_mp4": anim_mp4,
        "start_frame": start_f,
        "end_frame": end_f,
        "anim_width": int(rnd.get("anim_width", 640)),
        "anim_height": int(rnd.get("anim_height", 360)),
        "anim_samples": int(rnd.get("anim_samples", 16)),
    }

    return {
        "schema_version": "catalog-scene.v1",
        "scene_name": scene_name,
        "backdrop": backdrop,
        "camera": norm_cam,
        "render": norm_render,
        "characters": norm_chars,
    }


def compute_auto_frame_camera(
    bbox_min: list[float] | tuple[float, float, float],
    bbox_max: list[float] | tuple[float, float, float],
    *,
    lens_mm: float = 45.0,
    sensor_width_mm: float = 36.0,
    aspect: float = 16.0 / 9.0,
    elevation_deg: float = 14.0,
    azimuth_deg: float = 0.0,
    margin: float = 1.35,
) -> dict[str, Any]:
    """Compute perspective camera location and look target from combined world AABB."""
    target = [(bbox_min[i] + bbox_max[i]) * 0.5 for i in range(3)]
    dx = max(0.25, bbox_max[0] - bbox_min[0])
    dy = max(0.25, bbox_max[1] - bbox_min[1])
    dz = max(0.25, bbox_max[2] - bbox_min[2])

    fov_x = 2.0 * math.atan(sensor_width_mm / (2.0 * lens_mm))
    fov_y = 2.0 * math.atan(math.tan(fov_x * 0.5) / aspect)

    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    width_proj = abs(dx * math.cos(az)) + abs(dy * math.sin(az))
    depth_proj = abs(dx * math.sin(az)) + abs(dy * math.cos(az))

    d_x = (width_proj * margin * 0.5) / math.tan(fov_x * 0.5) + depth_proj * 0.5
    d_z = (dz * margin * 0.5) / math.tan(fov_y * 0.5) + depth_proj * 0.5
    distance = max(2.2, d_x, d_z)

    cam_loc = [
        round(target[0] - distance * math.sin(az) * math.cos(el), 4),
        round(target[1] - distance * math.cos(az) * math.cos(el), 4),
        round(max(0.35, target[2] + distance * math.sin(el)), 4),
    ]
    return {
        "location": cam_loc,
        "target": [round(v, 4) for v in target],
        "distance": round(distance, 4),
        "lens_mm": lens_mm,
        "fov_x_deg": round(math.degrees(fov_x), 2),
        "fov_y_deg": round(math.degrees(fov_y), 2),
    }


def evaluate_spatial_qa(
    characters_report: list[dict[str, Any]],
    *,
    max_floor_error_m: float = 0.03,
    min_anim_displacement_m: float = 0.005,
    max_socket_distance_m: float = 0.25,
) -> dict[str, Any]:
    """Programmatically verify floor grounding, pairwise AABB separation, sockets, and deformation."""
    failures: list[str] = []
    max_floor_error_seen = 0.0
    max_socket_seen = 0.0
    min_anim_seen: float | None = None
    overlap_pairs: list[dict[str, Any]] = []

    for ch in characters_report:
        label = ch.get("name") or ch.get("asset_id") or "character"
        bbox = ch.get("world_bbox")
        if not bbox:
            failures.append(f"{label}: missing world_bbox")
            continue
        if ch.get("ground_on_z0", True):
            floor_err = abs(float(bbox["min"][2]))
            max_floor_error_seen = max(max_floor_error_seen, floor_err)
            if floor_err > max_floor_error_m:
                failures.append(f"{label}: floor_error_m={floor_err:.4f} > {max_floor_error_m}")

        for att in ch.get("attachments") or []:
            dist = float(att.get("socket_distance_m", 999.0))
            max_socket_seen = max(max_socket_seen, dist)
            if dist > max_socket_distance_m:
                failures.append(
                    f"{label}/{att.get('bone')}: socket_distance_m={dist:.4f} > {max_socket_distance_m}"
                )

        anim = ch.get("animation")
        if anim is not None:
            disp = float(anim.get("max_vertex_displacement", 0.0))
            min_anim_seen = disp if min_anim_seen is None else min(min_anim_seen, disp)
            if disp < min_anim_displacement_m:
                failures.append(
                    f"{label}: animation displacement={disp:.6f} < {min_anim_displacement_m}"
                )

    for i in range(len(characters_report)):
        b1 = characters_report[i].get("world_bbox")
        if not b1:
            continue
        n1 = characters_report[i].get("name") or f"char_{i}"
        for j in range(i + 1, len(characters_report)):
            b2 = characters_report[j].get("world_bbox")
            if not b2:
                continue
            n2 = characters_report[j].get("name") or f"char_{j}"
            ox = max(0.0, min(b1["max"][0], b2["max"][0]) - max(b1["min"][0], b2["min"][0]))
            oy = max(0.0, min(b1["max"][1], b2["max"][1]) - max(b1["min"][1], b2["min"][1]))
            oz = max(0.0, min(b1["max"][2], b2["max"][2]) - max(b1["min"][2], b2["min"][2]))
            if ox > 0.02 and oy > 0.02 and oz > 0.02:
                overlap_pairs.append({"pair": [n1, n2], "overlap_m": [round(ox, 4), round(oy, 4), round(oz, 4)]})
                failures.append(f"AABB overlap between {n1} and {n2}: {[round(ox, 4), round(oy, 4), round(oz, 4)]}")

    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "metrics": {
            "character_count": len(characters_report),
            "max_floor_error_m": round(max_floor_error_seen, 6),
            "max_socket_distance_m": round(max_socket_seen, 6),
            "min_anim_displacement_m": round(min_anim_seen, 6) if min_anim_seen is not None else None,
            "overlap_pairs": overlap_pairs,
        },
    }


def _build_remote_assembly_script(assembly_spec: dict[str, Any]) -> str:
    """Build Blender 5.2+ scene assembly, socket attachment, Action Slot binding, lighting, and auto-frame script."""
    return f"""
import json, math, os
import bpy
from mathutils import Matrix, Vector

SPEC = json.loads({json.dumps(assembly_spec)!r})

# Clear scene datablocks without resetting addons (preserves live MCP socket).
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

def _import_glb_clean(filepath, collection_name, root_name):
    before_objs = set(bpy.data.objects)
    before_actions = set(bpy.data.actions)
    gltf_kwargs = {{"filepath": filepath}}
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
    new_set = set(new_objs)
    new_actions = [a for a in bpy.data.actions if a not in before_actions]

    col = bpy.data.collections.get(collection_name) or bpy.data.collections.new(collection_name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    for obj in new_objs:
        if obj.name not in col.objects:
            col.objects.link(obj)
        for c in list(obj.users_collection):
            if c != col:
                c.objects.unlink(obj)

    root_empty = bpy.data.objects.new(root_name, None)
    root_empty.empty_display_type = "PLAIN_AXES"
    root_empty.empty_display_size = 0.25
    col.objects.link(root_empty)
    for o in new_objs:
        if o.parent is None or o.parent not in new_set:
            o.parent = root_empty
    return col, root_empty, new_objs, new_actions

def _eval_world_bbox(objs):
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    mins = [float("inf"), float("inf"), float("inf")]
    maxs = [float("-inf"), float("-inf"), float("-inf")]
    cnt = 0
    for obj in objs:
        if obj.type != "MESH":
            continue
        cnt += 1
        eval_obj = obj.evaluated_get(deps)
        mesh_data = eval_obj.to_mesh()
        try:
            mw = eval_obj.matrix_world
            for v in mesh_data.vertices:
                wc = mw @ v.co
                for idx in range(3):
                    mins[idx] = min(mins[idx], wc[idx])
                    maxs[idx] = max(maxs[idx], wc[idx])
        finally:
            eval_obj.to_mesh_clear()
    if cnt == 0:
        return None
    return {{
        "min": [round(float(v), 4) for v in mins],
        "max": [round(float(v), 4) for v in maxs],
        "size": [round(float(maxs[i] - mins[i]), 4) for i in range(3)],
    }}

def _bind_slotted_action(arm, candidate_actions, clip_query, cleanup_unused=False):
    chosen = None
    q = (clip_query or "").strip().lower()
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
            raise ValueError(f"Clip {{q!r}} not found in {{[a.name for a in candidate_actions]}}")
    else:
        for a in candidate_actions:
            if "t-pose" not in a.name.lower():
                chosen = a
                break
        if chosen is None:
            chosen = candidate_actions[0]

    if cleanup_unused:
        for a in candidate_actions:
            if a != chosen:
                a.use_fake_user = False
                if a.users == 0:
                    bpy.data.actions.remove(a)

    ad = arm.animation_data or arm.animation_data_create()
    ad.action = chosen
    slot_id = None
    if hasattr(chosen, "slots") and hasattr(ad, "action_slot"):
        obj_slots = [s for s in chosen.slots if getattr(s, "target_id_type", None) == "OBJECT"]
        if obj_slots:
            ad.action_slot = obj_slots[0]
            slot_id = obj_slots[0].identifier
    return chosen, slot_id

def _measure_displacement(objs, f0, f1):
    deps_cache = []
    for fnum in (f0, f1):
        bpy.context.scene.frame_set(fnum)
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        pts = []
        for o in objs:
            if o.type != "MESH":
                continue
            eval_obj = o.evaluated_get(deps)
            mesh_data = eval_obj.to_mesh()
            try:
                mw = eval_obj.matrix_world
                for v in mesh_data.vertices:
                    pts.append(mw @ v.co)
            finally:
                eval_obj.to_mesh_clear()
        deps_cache.append(pts)
    max_d = 0.0
    for p0, p1 in zip(deps_cache[0], deps_cache[1]):
        d = (p1 - p0).length
        if d > max_d:
            max_d = d
    return max_d

scene = bpy.context.scene
render_cfg = SPEC["render"]
eval_frame = render_cfg.get("hero_frame") or (render_cfg["start_frame"] + max(0, (render_cfg["end_frame"] - render_cfg["start_frame"]) // 2))

char_reports = []
all_scene_objs = []
for idx, ch in enumerate(SPEC["characters"]):
    col_name = f"DirectorChar_{{idx}}_{{ch['tag']}}"[:62]
    root_name = f"DirectorRoot_{{idx}}_{{ch['tag']}}"[:62]
    _, root_empty, new_objs, embedded_actions = _import_glb_clean(ch["remote_path"], col_name, root_name)
    root_empty.location = tuple(ch["location"])
    root_empty.rotation_mode = "XYZ"
    root_empty.rotation_euler = tuple(math.radians(a) for a in ch["rotation_deg"])
    s = float(ch["scale"])
    root_empty.scale = (s, s, s)
    bpy.context.view_layer.update()

    arms = [o for o in new_objs if o.type == "ARMATURE"]
    arm = arms[0] if arms else None
    all_char_objs = list(new_objs)

    att_reports = []
    for a_idx, att in enumerate(ch.get("attachments") or []):
        if arm is None:
            raise ValueError(f"Character {{ch['asset_id']}} has no armature for attachment {{att['asset_id']}}")
        resolved_bone = None
        if att["bone"] in arm.data.bones:
            resolved_bone = att["bone"]
        else:
            bl = att["bone"].lower()
            for b in arm.data.bones:
                if b.name.lower() == bl:
                    resolved_bone = b.name
                    break
        if resolved_bone is None:
            raise ValueError(f"Bone {{att['bone']!r}} missing in {{arm.name}}")

        pcol = f"DirectorProp_{{idx}}_{{a_idx}}_{{att['tag']}}"[:62]
        proot_name = f"DirectorPropRoot_{{idx}}_{{a_idx}}_{{att['tag']}}"[:62]
        _, prop_root, p_objs, _ = _import_glb_clean(att["remote_path"], pcol, proot_name)
        bone_len = arm.data.bones[resolved_bone].length
        prop_root.parent = arm
        prop_root.parent_type = "BONE"
        prop_root.parent_bone = resolved_bone
        align = Matrix.Rotation(-math.pi * 0.5, 4, "X") if att.get("gltf_bone_align", True) else Matrix.Identity(4)
        prop_root.matrix_parent_inverse = Matrix.Translation((0.0, -bone_len, 0.0)) @ align
        prop_root.location = tuple(att["offset"])
        prop_root.rotation_mode = "XYZ"
        prop_root.rotation_euler = tuple(math.radians(a) for a in att["rotation_deg"])
        ps = float(att["scale"])
        prop_root.scale = (ps, ps, ps)
        bpy.context.view_layer.update()
        sock_world = arm.matrix_world @ arm.pose.bones[resolved_bone].head
        dist_m = round((prop_root.matrix_world.translation - sock_world).length, 6)
        att_reports.append({{
            "asset_id": att["asset_id"],
            "bone": resolved_bone,
            "socket_distance_m": dist_m,
            "gltf_bone_align": bool(att.get("gltf_bone_align", True)),
            "mesh_count": sum(1 for o in p_objs if o.type == "MESH"),
        }})
        all_char_objs.extend(p_objs)

    anim_report = None
    anim = ch.get("animation")
    if anim is not None:
        if arm is None:
            raise ValueError(f"Character {{ch['asset_id']}} has no armature to animate")
        if anim["external_remote_path"]:
            before_o = set(bpy.data.objects)
            before_a = set(bpy.data.actions)
            before_m = set(bpy.data.meshes)
            before_ar = set(bpy.data.armatures)
            before_mat = set(bpy.data.materials)
            before_c = set(bpy.data.collections)
            gk = {{"filepath": anim["external_remote_path"]}}
            if "disable_bone_shape" in bpy.ops.import_scene.gltf.get_rna_type().properties:
                gk["disable_bone_shape"] = True
            bpy.ops.import_scene.gltf(**gk)
            donor_actions = [a for a in bpy.data.actions if a not in before_a]
            for o in list(bpy.data.objects):
                if o not in before_o:
                    bpy.data.objects.remove(o, do_unlink=True)
            for c in list(bpy.data.collections):
                if c not in before_c and c.users == 0:
                    bpy.data.collections.remove(c)
            for coll, prev in (
                (bpy.data.meshes, before_m),
                (bpy.data.armatures, before_ar),
                (bpy.data.materials, before_mat),
            ):
                for db in list(coll):
                    if db not in prev and db.users == 0:
                        coll.remove(db)
            chosen, slot_id = _bind_slotted_action(arm, donor_actions, anim.get("clip"), cleanup_unused=True)
        else:
            if not embedded_actions:
                raise ValueError(f"No embedded actions imported for {{ch['asset_id']}}")
            chosen, slot_id = _bind_slotted_action(arm, embedded_actions, anim.get("clip"), cleanup_unused=False)

        f0 = int(round(chosen.frame_range[0]))
        f1 = max(f0 + 1, int(round(chosen.frame_range[1])))
        fmid = f0 + max(1, (f1 - f0) // 2)
        char_meshes = [o for o in new_objs if o.type == "MESH"]
        max_disp = _measure_displacement(char_meshes, f0, fmid)
        anim_report = {{
            "asset_id": anim["asset_id"],
            "clip_name": chosen.name,
            "action_slot": slot_id,
            "frame_start": f0,
            "frame_end": f1,
            "max_vertex_displacement": round(float(max_disp), 6),
        }}

    scene.frame_set(int(eval_frame))
    bbox = _eval_world_bbox(new_objs)
    if ch["ground_on_z0"] and bbox is not None:
        root_empty.location.z -= bbox["min"][2]
        bbox = _eval_world_bbox(new_objs)

    char_reports.append({{
        "name": ch["name"],
        "asset_id": ch["asset_id"],
        "armature": arm.name if arm else None,
        "bones": len(arm.data.bones) if arm else 0,
        "ground_on_z0": ch["ground_on_z0"],
        "world_bbox": bbox,
        "attachments": att_reports,
        "animation": anim_report,
    }})
    all_scene_objs.extend([o for o in all_char_objs if o.type == "MESH"])

scene.frame_set(int(eval_frame))
combined_bbox = _eval_world_bbox(all_scene_objs)

# Backdrop, 3-point lighting, and FOV/AABB auto-framed camera
backdrops = {{
    "studio_dark": ((0.065, 0.08, 0.11, 1.0), (0.025, 0.036, 0.055, 1.0), 0.75),
    "studio_warm": ((0.14, 0.11, 0.09, 1.0), (0.09, 0.075, 0.065, 1.0), 1.0),
    "clay": ((0.28, 0.28, 0.28, 1.0), (0.18, 0.19, 0.21, 1.0), 1.1),
}}
g_col, w_col, w_str = backdrops[SPEC["backdrop"]]

c_min = combined_bbox["min"]
c_max = combined_bbox["max"]
c_target = Vector([(c_min[i] + c_max[i]) * 0.5 for i in range(3)])
cx = c_target.x
cy = c_target.y
bpy.ops.mesh.primitive_plane_add(size=80.0, location=(cx, cy, 0.0))
ground = bpy.context.active_object
ground.name = "Director_Ground"
gmat = bpy.data.materials.new("Director_GroundMat")
gmat.use_nodes = True
gbsdf = gmat.node_tree.nodes.get("Principled BSDF")
gbsdf.inputs["Base Color"].default_value = g_col
gbsdf.inputs["Roughness"].default_value = 0.72
ground.data.materials.append(gmat)

world = scene.world or bpy.data.worlds.new("Director_World")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value = w_col
    bg.inputs["Strength"].default_value = w_str

for lname, energy, loc, color in (
    ("Director_KeyLight", 320.0, (cx - 3.0, cy - 4.8, 4.8), (1.0, 0.96, 0.90)),
    ("Director_FillLight", 130.0, (cx + 4.0, cy - 3.8, 2.9), (0.76, 0.88, 1.0)),
    ("Director_RimLight", 210.0, (cx, cy + 4.2, 3.8), (0.96, 0.98, 1.0)),
):
    ldata = bpy.data.lights.new(lname, type="AREA")
    ldata.energy = energy
    ldata.color = color
    ldata.size = 2.8
    lobj = bpy.data.objects.new(lname, ldata)
    lobj.location = Vector(loc)
    lobj.rotation_euler = (c_target - lobj.location).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(lobj)

cam_spec = SPEC["camera_plan"]
cdx = max(0.25, c_max[0] - c_min[0])
cdy = max(0.25, c_max[1] - c_min[1])
cdz = max(0.25, c_max[2] - c_min[2])
lens_mm = float(cam_spec["lens_mm"])
aspect = float(render_cfg["hero_width"]) / max(1.0, float(render_cfg["hero_height"]))
fov_x = 2.0 * math.atan(36.0 / (2.0 * lens_mm))
fov_y = 2.0 * math.atan(math.tan(fov_x * 0.5) / aspect)
az = math.radians(float(cam_spec.get("azimuth_deg", 0.0)))
el = math.radians(float(cam_spec.get("elevation_deg", 14.0)))
margin = float(cam_spec.get("margin", 1.35))
w_proj = abs(cdx * math.cos(az)) + abs(cdy * math.sin(az))
d_proj = abs(cdx * math.sin(az)) + abs(cdy * math.cos(az))
dist = max(2.2, (w_proj * margin * 0.5) / math.tan(fov_x * 0.5) + d_proj * 0.5, (cdz * margin * 0.5) / math.tan(fov_y * 0.5) + d_proj * 0.5)
cam_loc = Vector((
    c_target.x - dist * math.sin(az) * math.cos(el),
    c_target.y - dist * math.cos(az) * math.cos(el),
    max(0.35, c_target.z + dist * math.sin(el)),
))

cam_data = bpy.data.cameras.new("Director_Camera")
cam_data.lens = lens_mm
cam_obj = bpy.data.objects.new("Director_Camera", cam_data)
cam_obj.location = cam_loc
direction = c_target - cam_obj.location
cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
scene.collection.objects.link(cam_obj)
scene.camera = cam_obj

# Color, EEVEE Metal, and FPS invariants
scene.render.engine = "BLENDER_EEVEE"
scene.render.fps = 24
scene.render.threads_mode = "FIXED"
scene.render.threads = 6
scene.view_settings.view_transform = "AgX"
try:
    scene.view_settings.look = "AgX - Medium High Contrast"
except Exception:
    pass

for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        for space in area.spaces:
            if space.type == "VIEW_3D":
                space.region_3d.view_perspective = "CAMERA"
                space.shading.type = "RENDERED"

blend_path = SPEC["blend_path"]
os.makedirs(os.path.dirname(blend_path), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=blend_path)

print("DIRECTOR_ASSEMBLY_JSON:" + json.dumps({{
    "blend_path": blend_path,
    "evaluated_frame": int(eval_frame),
    "combined_bbox": combined_bbox,
    "characters": char_reports,
}}))
"""


REMOTE_RENDER_SCENE_DRIVER = r"""import hashlib,json,math,os,resource,shutil,subprocess,sys,time
from pathlib import Path

cfg = json.loads(sys.argv[1])
BLENDER_BIN = "/Applications/Blender.app/Contents/MacOS/Blender"
FFMPEG_BIN = "/opt/homebrew/bin/ffmpeg"
FFPROBE_BIN = "/opt/homebrew/bin/ffprobe"

out_dir = Path(cfg["out_dir"]).expanduser().resolve()
blend_path = Path(cfg["blend_path"]).expanduser().resolve()
if not blend_path.is_file():
    raise SystemExit(f"Blend not found: {blend_path}")

free_gib = shutil.disk_usage("/").free / (1024 ** 3)
if free_gib < cfg.get("min_remote_free_gib", 1.5):
    raise SystemExit(f"Insufficient disk on remote host: {free_gib:.2f} GiB")

def sha256_path(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blk)
    return h.hexdigest()

blender_py = r'''
import bpy, json, math, os, sys, time
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
rcfg = json.loads(argv[0])
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.threads_mode = "FIXED"
scene.render.threads = 6
scene.render.fps = 24
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.color_depth = "8"
scene.view_settings.view_transform = "AgX"
try:
    scene.view_settings.look = "AgX - Medium High Contrast"
except Exception:
    pass

stats = {}
if rcfg.get("quad_views_dir"):
    qdir = rcfg["quad_views_dir"]
    os.makedirs(qdir, exist_ok=True)
    bbox = rcfg["combined_bbox"]
    center = Vector([(bbox["min"][i] + bbox["max"][i]) * 0.5 for i in range(3)])
    span = max(2.0, max(bbox["size"])) * 1.45
    scene.render.resolution_x = 640
    scene.render.resolution_y = 360
    scene.render.resolution_percentage = 100
    scene.eevee.taa_render_samples = 16
    scene.frame_set(rcfg["hero_frame"])

    orig_cam = scene.camera
    tmp_cam_data = bpy.data.cameras.new("QA_OrthoCam")
    tmp_cam = bpy.data.objects.new("QA_OrthoCam", tmp_cam_data)
    scene.collection.objects.link(tmp_cam)
    tmp_cam_data.lens = 45.0

    # View 0: Hero camera perspective
    scene.camera = orig_cam
    scene.render.filepath = os.path.join(qdir, "view_0_hero.png")
    bpy.ops.render.render(write_still=True)

    # Views 1-3: Front, Side (+X), Top
    view_specs = [
        ("view_1_front.png", Vector((center.x, center.y - span * 1.4, center.z))),
        ("view_2_side.png", Vector((center.x + span * 1.4, center.y, center.z))),
        ("view_3_top.png", Vector((center.x, center.y - 0.02, bbox["max"][2] + span * 1.35))),
    ]
    scene.camera = tmp_cam
    for fname, loc in view_specs:
        tmp_cam.location = loc
        tmp_cam.rotation_euler = (center - loc).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(qdir, fname)
        bpy.ops.render.render(write_still=True)
    scene.camera = orig_cam
    bpy.data.objects.remove(tmp_cam, do_unlink=True)
    bpy.data.cameras.remove(tmp_cam_data)
    stats["quad_rendered"] = True

if rcfg.get("hero_out"):
    scene.render.resolution_x = rcfg["hero_width"]
    scene.render.resolution_y = rcfg["hero_height"]
    scene.render.resolution_percentage = 100
    scene.eevee.taa_render_samples = rcfg["hero_samples"]
    t0 = time.monotonic()
    scene.frame_set(rcfg["hero_frame"])
    scene.render.filepath = rcfg["hero_out"]
    bpy.ops.render.render(write_still=True)
    stats["hero_seconds"] = round(time.monotonic() - t0, 3)

if rcfg.get("frames_dir"):
    os.makedirs(rcfg["frames_dir"], exist_ok=True)
    scene.render.resolution_x = rcfg["anim_width"]
    scene.render.resolution_y = rcfg["anim_height"]
    scene.eevee.taa_render_samples = rcfg["anim_samples"]
    timings = []
    for f in range(rcfg["start_frame"], rcfg["end_frame"] + 1):
        t0 = time.monotonic()
        scene.frame_set(f)
        scene.render.filepath = os.path.join(rcfg["frames_dir"], f"frame_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        timings.append(round(time.monotonic() - t0, 3))
    stats["anim_frames"] = len(timings)
    stats["anim_seconds"] = round(sum(timings), 3)

print("REMOTE_RENDER_STATS:" + json.dumps(stats))
'''

prefix = cfg["scene_name"]
quad_dir = out_dir / "_quad_tmp" if cfg["quad_qa_sheet"] else None
quad_out = out_dir / f"{prefix}_quad_qa.png"
hero_out = out_dir / f"{prefix}_hero.png" if cfg["hero_still"] else None
frames_dir = out_dir / "frames" if cfg["animation_mp4"] else None
mp4_out = out_dir / f"{prefix}_anim.mp4" if cfg["animation_mp4"] else None

if quad_dir and quad_dir.exists():
    shutil.rmtree(quad_dir)
if frames_dir and frames_dir.exists() and any(frames_dir.iterdir()):
    raise SystemExit(f"Refusing to clobber non-empty frames dir: {frames_dir}")
for p in (quad_out, hero_out, mp4_out):
    if p is not None and p.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {p}")

rcfg = {
    "combined_bbox": cfg["combined_bbox"],
    "hero_frame": cfg["hero_frame"],
    "hero_width": cfg["hero_width"],
    "hero_height": cfg["hero_height"],
    "hero_samples": cfg["hero_samples"],
    "quad_views_dir": str(quad_dir) if quad_dir else None,
    "hero_out": str(hero_out) if hero_out else None,
    "frames_dir": str(frames_dir) if frames_dir else None,
    "anim_width": cfg["anim_width"],
    "anim_height": cfg["anim_height"],
    "anim_samples": cfg["anim_samples"],
    "start_frame": cfg["start_frame"],
    "end_frame": cfg["end_frame"],
}

t0 = time.monotonic()
proc = subprocess.run(
    [BLENDER_BIN, "--background", str(blend_path), "--threads", "2", "--python-expr", blender_py, "--", json.dumps(rcfg)],
    capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=900,
)
if proc.returncode != 0:
    raise SystemExit(f"Blender background render failed:\n{proc.stderr[-1500:]}\n{proc.stdout[-1500:]}")

rstats = None
for line in proc.stdout.splitlines():
    if line.startswith("REMOTE_RENDER_STATS:"):
        rstats = json.loads(line.split("REMOTE_RENDER_STATS:", 1)[1])
        break
if rstats is None:
    raise SystemExit("Missing REMOTE_RENDER_STATS in Blender output")
rstats["wall_seconds"] = round(time.monotonic() - t0, 3)

if quad_dir:
    view_files = [
        quad_dir / "view_0_hero.png",
        quad_dir / "view_1_front.png",
        quad_dir / "view_2_side.png",
        quad_dir / "view_3_top.png",
    ]
    inputs = []
    for vf in view_files:
        if not vf.is_file():
            raise SystemExit(f"Missing quad view file: {vf}")
        inputs.extend(["-i", str(vf)])
    filter_complex = (
        "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0,tile=2x2:padding=4:margin=4:color=black[out]"
    )
    subprocess.run(
        [FFMPEG_BIN, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", filter_complex, "-map", "[out]", "-frames:v", "1", str(quad_out)],
        stdin=subprocess.DEVNULL, check=True, timeout=60,
    )
    shutil.rmtree(quad_dir)

video_meta = None
if frames_dir and mp4_out:
    frame_count = cfg["end_frame"] - cfg["start_frame"] + 1
    tmp_mp4 = mp4_out.with_name(f".{mp4_out.name}.tmp.mp4")
    if tmp_mp4.exists():
        tmp_mp4.unlink()
    subprocess.run(
        [
            FFMPEG_BIN, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-n",
            "-framerate", "24", "-start_number", str(cfg["start_frame"]),
            "-i", str(frames_dir / "frame_%04d.png"),
            "-frames:v", str(frame_count), "-c:v", "libx264", "-threads", "4",
            "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", str(tmp_mp4),
        ],
        stdin=subprocess.DEVNULL, check=True, timeout=120,
    )
    probe_raw = subprocess.check_output(
        [FFPROBE_BIN, "-v", "error", "-show_entries", "stream=codec_name,width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", str(tmp_mp4)],
        text=True, timeout=30,
    )
    meta = json.loads(probe_raw)
    st = meta["streams"][0]
    if st.get("codec_name") != "h264" or st.get("width") != cfg["anim_width"] or st.get("height") != cfg["anim_height"] or int(st.get("nb_frames", 0)) != frame_count:
        raise SystemExit(f"FFprobe verification mismatch: {meta}")
    subprocess.run(
        [FFMPEG_BIN, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror", "-i", str(tmp_mp4), "-f", "null", "-"],
        stdin=subprocess.DEVNULL, check=True, timeout=60,
    )
    os.link(tmp_mp4, mp4_out)
    tmp_mp4.unlink()
    shutil.rmtree(frames_dir)
    video_meta = {
        "codec": st["codec_name"],
        "width": st["width"],
        "height": st["height"],
        "nb_frames": int(st["nb_frames"]),
        "duration": meta.get("format", {}).get("duration"),
        "full_decode_passed": True,
    }

artifacts = {}
for key, path_obj in (
    ("blend", blend_path),
    ("quad_qa_contact_sheet", quad_out if cfg["quad_qa_sheet"] else None),
    ("hero_png", hero_out),
    ("mp4", mp4_out),
):
    if path_obj is not None and path_obj.is_file():
        artifacts[key] = {
            "path": str(path_obj),
            "filename": path_obj.name,
            "bytes": path_obj.stat().st_size,
            "sha256": sha256_path(path_obj),
        }

manifest = {
    "schema_version": "catalog-director-manifest.v1",
    "scene_name": cfg["scene_name"],
    "spatial_qa": cfg["spatial_qa"],
    "render_stats": rstats,
    "video_verification": video_meta,
    "disk_free_gib_after": round(shutil.disk_usage("/").free / (1024 ** 3), 3),
    "artifacts": artifacts,
}
mpath = out_dir / "manifest.json"
mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"manifest_path": str(mpath), **manifest}, indent=2))
"""


def _estimate_scene_bounds(index: dc.CatalogIndex, manifest: dict[str, Any]) -> tuple[list[float], list[float]]:
    mins = [float("inf"), float("inf"), float("inf")]
    maxs = [float("-inf"), float("-inf"), float("-inf")]
    for ch in manifest["characters"]:
        rec = index.get(ch["asset_id"])
        dims = rec.get("dimensions_m") or [1.5, 2.0, 1.5]
        # Catalog dimensions_m are [width_X, height_Y, depth_Z] in glTF Y-up -> map to Blender Z-up
        sx = float(dims[0]) * float(ch["scale"])
        sy = float(dims[2]) * float(ch["scale"])
        sz = float(dims[1]) * float(ch["scale"])
        lx, ly, lz = ch["location"]
        z0 = 0.0 if ch["ground_on_z0"] else lz
        mins[0] = min(mins[0], lx - sx * 0.5)
        maxs[0] = max(maxs[0], lx + sx * 0.5)
        mins[1] = min(mins[1], ly - sy * 0.5)
        maxs[1] = max(maxs[1], ly + sy * 0.5)
        mins[2] = min(mins[2], z0)
        maxs[2] = max(maxs[2], z0 + sz)
    return mins, maxs


def direct_scene(
    *,
    manifest_path: Path,
    catalog_config: Path | None,
    remote_out_root: str,
    local_out_dir: Path,
    remote_user: str | None = None,
    gdrive_sync_config: Path | None = None,
    run_subdir: str | None = None,
    headless_only: bool = False,
    allow_qa_fail: bool = False,
    cache_local: bool = False,
    launcher: str | None = None,
) -> dict[str, Any]:
    """Orchestrate full catalog scene assembly, QA gate, remote render, verified pull, and Drive sync."""
    raw_manifest = json.loads(Path(manifest_path).expanduser().read_text(encoding="utf-8"))
    manifest = validate_scene_manifest(raw_manifest)
    cfg = dc.load_catalog_config(catalog_config)
    index = dc.CatalogIndex(cfg["metadata_dir"])
    host, _ = dc._require_remote_settings(cfg)
    ssh_user = remote_user or str(cfg.get("remote_user") or "").strip()
    if not ssh_user:
        raise ValueError("Remote SSH user required via --remote-user or 'remote_user' in catalog.json")

    remote_root_clean = remote_out_root.rstrip("/")
    remote_dir_name = run_subdir or manifest["scene_name"]
    if not dc.SAFE_NAME_RE.match(remote_dir_name):
        raise ValueError(f"Unsafe run_subdir: {remote_dir_name!r}")
    remote_out_dir = f"{remote_root_clean}/{remote_dir_name}"
    remote_blend_path = f"{remote_out_dir}/{manifest['scene_name']}.blend"

    # 1. Stage all character, prop, and external animation pack GLBs onto remote host.
    staged_characters: list[dict[str, Any]] = []
    for ch in manifest["characters"]:
        ch_stage = dc.stage_to_remote(index, cfg, ch["asset_id"], cache_local=cache_local)
        staged_atts = []
        for att in ch["attachments"]:
            a_stage = dc.stage_to_remote(index, cfg, att["asset_id"], cache_local=cache_local)
            staged_atts.append(
                {
                    **att,
                    "tag": dc._safe_blender_tag(a_stage["resolution"]["record"], a_stage["staging"]["sha256"]),
                    "remote_path": a_stage["staging"]["remote_path"],
                }
            )
        anim_spec = None
        if ch["animation"] is not None:
            anim = ch["animation"]
            if not anim["force_skeleton"] and anim["asset_id"] != ch["asset_id"]:
                c_fam = index.get(ch["asset_id"]).get("skeleton_family")
                a_fam = index.get(anim["asset_id"]).get("skeleton_family")
                if c_fam and a_fam and c_fam != "None" and a_fam != "None" and c_fam != a_fam:
                    raise ValueError(f"Incompatible skeleton families: {c_fam} vs {a_fam}")
            ext_path = None
            if anim["asset_id"] != ch["asset_id"]:
                an_stage = dc.stage_to_remote(index, cfg, anim["asset_id"], cache_local=cache_local)
                ext_path = an_stage["staging"]["remote_path"]
            anim_spec = {**anim, "external_remote_path": ext_path}

        staged_characters.append(
            {
                **ch,
                "tag": dc._safe_blender_tag(ch_stage["resolution"]["record"], ch_stage["staging"]["sha256"]),
                "remote_path": ch_stage["staging"]["remote_path"],
                "attachments": staged_atts,
                "animation": anim_spec,
            }
        )

    est_min, est_max = _estimate_scene_bounds(index, manifest)
    cam_plan = {
        **compute_auto_frame_camera(
            est_min,
            est_max,
            lens_mm=manifest["camera"]["lens_mm"],
            aspect=manifest["render"]["hero_width"] / max(1, manifest["render"]["hero_height"]),
            elevation_deg=manifest["camera"]["elevation_deg"],
            azimuth_deg=manifest["camera"]["azimuth_deg"],
            margin=manifest["camera"]["margin"],
        ),
        "elevation_deg": manifest["camera"]["elevation_deg"],
        "azimuth_deg": manifest["camera"]["azimuth_deg"],
        "margin": manifest["camera"]["margin"],
    }

    assembly_spec = {
        "scene_name": manifest["scene_name"],
        "backdrop": manifest["backdrop"],
        "blend_path": remote_blend_path,
        "camera_plan": cam_plan,
        "render": manifest["render"],
        "characters": staged_characters,
    }
    assembly_script = _build_remote_assembly_script(assembly_spec)

    if headless_only:
        proc = subprocess.run(
            [
                "ssh",
                *dc.SSH_OPTS,
                host,
                f"/Applications/Blender.app/Contents/MacOS/Blender --background --python-expr {shlex.quote(assembly_script)}",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assembly_report = None
        for line in proc.stdout.splitlines():
            if line.startswith("DIRECTOR_ASSEMBLY_JSON:"):
                assembly_report = json.loads(line.split("DIRECTOR_ASSEMBLY_JSON:", 1)[1])
                break
        if assembly_report is None:
            raise RuntimeError(f"Missing DIRECTOR_ASSEMBLY_JSON in headless output:\n{proc.stdout[-1500:]}")
    else:
        mcp_launcher = dc._resolve_launcher(cfg, launcher)
        assembly_report = dc._run_blender_mcp(mcp_launcher, assembly_script, "DIRECTOR_ASSEMBLY_JSON:")

    # 2. Programmatic spatial & deformation QA gate before heavy rendering
    qa_report = evaluate_spatial_qa(assembly_report["characters"])
    if not qa_report["passed"] and not allow_qa_fail:
        raise RuntimeError(f"Spatial/deformation QA gate failed: {json.dumps(qa_report)}")

    # Refine camera exact position from actual evaluated scene bounding box before render
    combined_bbox = assembly_report["combined_bbox"]
    exact_cam = compute_auto_frame_camera(
        combined_bbox["min"],
        combined_bbox["max"],
        lens_mm=manifest["camera"]["lens_mm"],
        elevation_deg=manifest["camera"]["elevation_deg"],
        azimuth_deg=manifest["camera"]["azimuth_deg"],
        margin=manifest["camera"]["margin"],
    )

    # 3. Background Blender render (2x2 Quad Sheet + Hero + Optional Bounded MP4) + Manifest
    render_cfg = {
        "scene_name": manifest["scene_name"],
        "out_dir": remote_out_dir,
        "blend_path": remote_blend_path,
        "combined_bbox": combined_bbox,
        "hero_frame": assembly_report["evaluated_frame"],
        "hero_width": manifest["render"]["hero_width"],
        "hero_height": manifest["render"]["hero_height"],
        "hero_samples": manifest["render"]["hero_samples"],
        "quad_qa_sheet": manifest["render"]["quad_qa_sheet"],
        "hero_still": manifest["render"]["hero_still"],
        "animation_mp4": manifest["render"]["animation_mp4"],
        "start_frame": manifest["render"]["start_frame"],
        "end_frame": manifest["render"]["end_frame"],
        "anim_width": manifest["render"]["anim_width"],
        "anim_height": manifest["render"]["anim_height"],
        "anim_samples": manifest["render"]["anim_samples"],
        "min_remote_free_gib": float(cfg.get("min_remote_free_gib", 1.5)),
        "exact_camera": exact_cam,
        "spatial_qa": qa_report,
    }
    remote_manifest = dc._ssh_python(host, REMOTE_RENDER_SCENE_DRIVER, [json.dumps(render_cfg)], timeout=900)

    # 4. Pull verified artifacts back to MacBook Air using transfer_verified_file.py --multiplex
    local_dir = Path(local_out_dir).expanduser().resolve()
    local_dir.mkdir(parents=True, exist_ok=True)
    transfer_cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "transfer_verified_file.py"),
        "--source-host",
        host,
        "--source-user",
        ssh_user,
        "--source-root",
        remote_root_clean,
        "--manifest-path",
        remote_manifest["manifest_path"],
        "--destination-root",
        str(local_dir),
        "--transfer-mode",
        "full",
        "--multiplex",
    ]
    if gdrive_sync_config is not None:
        transfer_cmd.extend(
            [
                "--gdrive-sync-config",
                str(Path(gdrive_sync_config).expanduser()),
                "--gdrive-subdir",
                local_dir.name,
            ]
        )
    tr_proc = subprocess.run(transfer_cmd, check=True, capture_output=True, text=True, timeout=300)
    transfer_result = json.loads(tr_proc.stdout)

    return {
        "schema_version": "catalog-director-result.v1",
        "directed_at_utc": datetime.now(timezone.utc).isoformat(),
        "scene_name": manifest["scene_name"],
        "assembly": assembly_report,
        "spatial_qa": qa_report,
        "remote_render": remote_manifest,
        "transfer_and_delivery": transfer_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Path to catalog-scene.v1 JSON manifest")
    parser.add_argument("--catalog-config", type=Path, default=None, help="Path to private catalog.json")
    parser.add_argument("--gdrive-sync-config", type=Path, default=None, help="Optional private gdrive-sync.json for Drive delivery")
    parser.add_argument("--remote-out-root", required=True, help="Approved remote output root directory")
    parser.add_argument("--remote-user", default=None, help="SSH user on remote host (or remote_user in catalog.json)")
    parser.add_argument("--local-out-dir", required=True, type=Path, help="Local destination folder for verified outputs")
    parser.add_argument("--run-subdir", default=None, help="Optional unique remote run folder name (defaults to scene_name)")
    parser.add_argument("--headless-only", action="store_true", help="Assemble via background Blender instead of live MCP")
    parser.add_argument("--allow-qa-fail", action="store_true", help="Proceed to render even if spatial QA reports a warning")
    parser.add_argument("--cache-local", action="store_true", help="Cache newly fetched Drive GLBs locally")
    parser.add_argument("--launcher", default=None, help="Optional MCP launcher path")
    args = parser.parse_args()

    result = direct_scene(
        manifest_path=args.manifest,
        catalog_config=args.catalog_config,
        remote_out_root=args.remote_out_root,
        local_out_dir=args.local_out_dir,
        remote_user=args.remote_user,
        gdrive_sync_config=args.gdrive_sync_config,
        run_subdir=args.run_subdir,
        headless_only=args.headless_only,
        allow_qa_fail=args.allow_qa_fail,
        cache_local=args.cache_local,
        launcher=args.launcher,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
