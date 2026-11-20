#!/usr/bin/env python3
"""5-World Story-Driven Audio-Reactive Blender 5.2+ Scene Builder:
"The Midnight Saxophone Heist"

Builds 5 isolated 60m-separated 3D worlds toggled cleanly with hide_render and
CONSTANT Act cuts so EEVEE renders only one active world per frame:
  - Set 1 (-60,  0, 0): Royal Emerald Museum Vault (Heist f1..192 + Epilogue f1326..1386)
  - Set 2 (+60,  0, 0): Moonlit Neon Rooftop Chase & Chasm Leap (f193..396)
  - Set 3 (  0,-60, 0): Underground Neon Speakeasy & Vinyl Swap (f397..756)
  - Set 4 (  0,+60, 0): Enchanted Clockwork Astral Cosmos (f757..948)
  - Set 5 (  0,  0, 0): Grand Clockwork Ballroom 5-Piece Finale (f949..1325)
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import bpy
import bmesh
from mathutils import Matrix, Vector


# Act / Set active frame intervals (inclusive, non-overlapping)
SET_INTERVALS: dict[str, list[tuple[int, int]]] = {
    "set1": [(1, 192), (1326, 1386)],
    "set2": [(193, 396)],
    "set3": [(397, 756)],
    "set4": [(757, 948)],
    "set5": [(949, 1325)],
}


def _clear_scene_safely() -> None:
    """Clear active scene objects and unused datablocks without wm.read_factory_settings()."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.context.scene.collection.children):
        bpy.context.scene.collection.children.unlink(col)
        if col.users == 0:
            bpy.data.collections.remove(col)
    for store in (
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.materials,
        bpy.data.actions,
        bpy.data.images,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.node_groups,
        bpy.data.collections,
    ):
        for db in list(store):
            if db.users == 0:
                store.remove(db)


def _iter_action_fcurves(act: Any) -> list[Any]:
    """Yield FCurves cleanly across Blender 4.4–5.2 Action Slots or legacy Actions."""
    if hasattr(act, "fcurves"):
        return list(act.fcurves)
    out: list[Any] = []
    for layer in getattr(act, "layers", []):
        for strip in getattr(layer, "strips", []):
            for cb in getattr(strip, "channelbags", []):
                out.extend(getattr(cb, "fcurves", []))
    return out


def _make_mat(
    name: str,
    base_color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.4,
    emission_color: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
) -> tuple[bpy.types.Material, bpy.types.Node]:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Metallic"].default_value = float(metallic)
    bsdf.inputs["Roughness"].default_value = float(roughness)
    if emission_color is not None and "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = emission_color
    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = float(emission_strength)
    return mat, bsdf


def _assign_to_col(obj: bpy.types.Object, col: bpy.types.Collection) -> bpy.types.Object:
    if obj.name not in col.objects:
        col.objects.link(obj)
    for c in list(obj.users_collection):
        if c != col:
            c.objects.unlink(obj)
    return obj


def _join_parts(name: str, parts: list[bpy.types.Object], mat: bpy.types.Material, col: bpy.types.Collection, *, smooth: bool = True) -> bpy.types.Object:
    for p in parts:
        p.data.materials.clear()
        p.data.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    if len(parts) > 1:
        bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = name
    _assign_to_col(joined, col)
    if smooth and joined.type == "MESH":
        for poly in joined.data.polygons:
            poly.use_smooth = True
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return joined


def _import_glb_clean(filepath: str, col: bpy.types.Collection, root_name: str, *, gltf_bone_align: bool = False, use_euler_pose: bool = True) -> tuple[bpy.types.Object, bpy.types.Object | None, list[bpy.types.Object]]:
    before_objs = set(bpy.data.objects)
    before_actions = set(bpy.data.actions)
    gk: dict[str, Any] = {"filepath": filepath}
    if "disable_bone_shape" in bpy.ops.import_scene.gltf.get_rna_type().properties:
        gk["disable_bone_shape"] = True
    bpy.ops.import_scene.gltf(**gk)

    helper_objs = set()
    for o in bpy.data.objects:
        if o.type == "ARMATURE" and o.pose:
            for pb in o.pose.bones:
                if pb.custom_shape is not None:
                    helper_objs.add(pb.custom_shape)
    for c in bpy.data.collections:
        if c.name.startswith("glTF_not_exported"):
            helper_objs.update(c.objects)

    new_objs = [o for o in bpy.data.objects if o not in before_objs and o not in helper_objs]
    for a in list(bpy.data.actions):
        if a not in before_actions:
            bpy.data.actions.remove(a)

    new_set = set(new_objs)
    for o in new_objs:
        _assign_to_col(o, col)

    root_empty = bpy.data.objects.new(root_name, None)
    root_empty.empty_display_type = "PLAIN_AXES"
    root_empty.empty_display_size = 0.2
    _assign_to_col(root_empty, col)
    for o in new_objs:
        if o.parent is None or o.parent not in new_set:
            o.parent = root_empty
            if gltf_bone_align:
                o.rotation_mode = "XYZ"

    arm = next((o for o in new_objs if o.type == "ARMATURE"), None)
    if arm is not None and arm.pose:
        mode = "XYZ" if use_euler_pose else "QUATERNION"
        for pb in arm.pose.bones:
            pb.rotation_mode = mode
    return root_empty, arm, new_objs


def _eval_min_z(objs: list[bpy.types.Object]) -> float:
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    min_z = float("inf")
    for o in objs:
        if o.type != "MESH":
            continue
        eo = o.evaluated_get(deps)
        md = eo.to_mesh()
        try:
            mw = eo.matrix_world
            for v in md.vertices:
                min_z = min(min_z, (mw @ v.co).z)
        finally:
            eo.to_mesh_clear()
    return min_z if min_z < float("inf") else 0.0


def _import_donor_actions(glb_path: str) -> dict[str, bpy.types.Action]:
    """Import an animation pack GLB once, delete its donor meshes/armature, and keep actions."""
    before_objs = set(bpy.data.objects)
    before_acts = set(bpy.data.actions)
    before_meshes = set(bpy.data.meshes)
    before_arms = set(bpy.data.armatures)
    before_mats = set(bpy.data.materials)
    before_cols = set(bpy.data.collections)
    gk: dict[str, Any] = {"filepath": glb_path}
    if "disable_bone_shape" in bpy.ops.import_scene.gltf.get_rna_type().properties:
        gk["disable_bone_shape"] = True
    bpy.ops.import_scene.gltf(**gk)
    acts = {a.name: a for a in bpy.data.actions if a not in before_acts}
    for o in list(bpy.data.objects):
        if o not in before_objs:
            bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        if c not in before_cols and c.users == 0:
            bpy.data.collections.remove(c)
    for store, prev in ((bpy.data.meshes, before_meshes), (bpy.data.armatures, before_arms), (bpy.data.materials, before_mats)):
        for db in list(store):
            if db not in prev and db.users == 0:
                store.remove(db)
    return acts


def _bind_cloned_action(
    arm: bpy.types.Object,
    src_action: bpy.types.Action,
    *,
    tag: str,
    frame_offset: int = 0,
    cycle: bool = True,
    speed_scale: float = 1.0,
) -> bpy.types.Action:
    """Clone src_action per armature with Blender 5.2 Action Slots + optional offset/CYCLES."""
    act = src_action.copy()
    act.name = f"{src_action.name}_{tag}"[:62]
    for fc in _iter_action_fcurves(act):
        for kp in fc.keyframe_points:
            kp.co.x = kp.co.x / speed_scale + frame_offset
            kp.handle_left.x = kp.handle_left.x / speed_scale + frame_offset
            kp.handle_right.x = kp.handle_right.x / speed_scale + frame_offset
        if cycle:
            mod = fc.modifiers.new(type="CYCLES")
            mod.mode_before = "REPEAT"
            mod.mode_after = "REPEAT"
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    if hasattr(act, "slots") and hasattr(ad, "action_slot"):
        obj_slots = [s for s in act.slots if getattr(s, "target_id_type", None) == "OBJECT"]
        if obj_slots:
            ad.action_slot = obj_slots[0]
    return act


def _attach_glb_prop(
    glb_path: str,
    col: bpy.types.Collection,
    arm: bpy.types.Object,
    bone_name: str,
    tag: str,
    *,
    offset=(0.0, 0.0, 0.0),
    rot_deg=(0.0, 0.0, 0.0),
    scale: float = 1.0,
) -> bpy.types.Object:
    prop_root, _, _ = _import_glb_clean(glb_path, col, f"PropRoot_{tag}")
    bone_len = arm.data.bones[bone_name].length
    prop_root.parent = arm
    prop_root.parent_type = "BONE"
    prop_root.parent_bone = bone_name
    prop_root.matrix_parent_inverse = Matrix.Translation((0.0, -bone_len, 0.0)) @ Matrix.Rotation(-math.pi * 0.5, 4, "X")
    prop_root.location = offset
    prop_root.rotation_mode = "XYZ"
    prop_root.rotation_euler = tuple(math.radians(a) for a in rot_deg)
    prop_root.scale = (scale, scale, scale)
    return prop_root


def _attach_custom_prop(
    arm: bpy.types.Object,
    bone_name: str,
    prop_root: bpy.types.Object,
    *,
    offset=(0.0, 0.0, 0.0),
    rot_deg=(0.0, 0.0, 0.0),
    scale: float = 1.0,
) -> None:
    bone_len = arm.data.bones[bone_name].length
    prop_root.parent = arm
    prop_root.parent_type = "BONE"
    prop_root.parent_bone = bone_name
    prop_root.matrix_parent_inverse = Matrix.Translation((0.0, -bone_len, 0.0))
    prop_root.location = offset
    prop_root.rotation_mode = "XYZ"
    prop_root.rotation_euler = tuple(math.radians(a) for a in rot_deg)
    prop_root.scale = (scale, scale, scale)


def _kf_constant_visibility(col: bpy.types.Collection, intervals: list[tuple[int, int]], total_frames: int) -> None:
    """Animate hide_render on every object in col with CONSTANT interpolation across Act cuts."""
    visible_starts = {a: False for a, _ in intervals}
    hide_frames = {1: True}
    for a, b in intervals:
        hide_frames[a] = False
        if b < total_frames:
            hide_frames[b + 1] = True
    key_times = sorted(hide_frames.keys())
    for obj in list(col.objects):
        # Never insert object visibility FCurves on ARMATUREs (preserves Action Slots & NLA strips!)
        if obj.type == "ARMATURE":
            continue
        for kf in key_times:
            obj.hide_render = hide_frames[kf]
            obj.keyframe_insert(data_path="hide_render", frame=kf)
        if obj.animation_data and obj.animation_data.action:
            for fc in _iter_action_fcurves(obj.animation_data.action):
                if fc.data_path == "hide_render":
                    for kp in fc.keyframe_points:
                        kp.interpolation = "CONSTANT"


def _kf_bone_rot(arm: bpy.types.Object, bone_name: str, deg_xyz: tuple[float, float, float], frame: int) -> None:
    pb = arm.pose.bones[bone_name]
    pb.rotation_euler = tuple(math.radians(a) for a in deg_xyz)
    pb.keyframe_insert(data_path="rotation_euler", frame=frame)


def _kf_bone_loc(arm: bpy.types.Object, bone_name: str, loc_xyz: tuple[float, float, float], frame: int) -> None:
    pb = arm.pose.bones[bone_name]
    pb.location = loc_xyz
    pb.keyframe_insert(data_path="location", frame=frame)


def _spawn_band_member(glb_path: str, col: bpy.types.Collection, name: str, loc: tuple[float, float, float], yaw_deg: float, floor_z: float, *, use_euler_pose: bool = True) -> tuple[bpy.types.Object, bpy.types.Object]:
    root_e, arm, objs = _import_glb_clean(glb_path, col, name, use_euler_pose=use_euler_pose)
    root_e.location = loc
    root_e.rotation_mode = "XYZ"
    root_e.rotation_euler = (0.0, 0.0, math.radians(yaw_deg))
    bpy.context.view_layer.update()
    min_z = _eval_min_z(objs)
    root_e.location.z += (floor_z - min_z)
    bpy.context.view_layer.update()
    return root_e, arm


def _build_saxophone(col: bpy.types.Collection, name: str, gold_m: bpy.types.Material, key_m: bpy.types.Material, glow_m: bpy.types.Material | None = None, *, with_rings: bool = False) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    sax_root = bpy.data.objects.new(name, None)
    sax_root.empty_display_size = 0.06
    col.objects.link(sax_root)
    parts: list[bpy.types.Object] = []
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.042, depth=0.62, location=(0.0, 0.03, -0.02), rotation=(math.radians(-14), 0.0, 0.0))
    parts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=0.028, depth=0.22, location=(0.0, -0.02, 0.34), rotation=(math.radians(42), 0.0, 0.0))
    parts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.018, depth=0.14, location=(0.0, -0.11, 0.42), rotation=(math.radians(82), 0.0, 0.0))
    parts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=0.055, depth=0.15, location=(0.0, 0.14, -0.32), rotation=(0.0, math.pi * 0.5, 0.0))
    parts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.052, depth=0.24, location=(0.0, 0.22, -0.18), rotation=(math.radians(-10), 0.0, 0.0))
    parts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.055, radius2=0.165, depth=0.24, location=(0.0, 0.26, 0.03), rotation=(math.radians(-22), 0.0, 0.0))
    parts.append(bpy.context.active_object)
    body = _join_parts(f"{name}_Body", parts, gold_m, col, smooth=True)
    body.parent = sax_root

    kparts: list[bpy.types.Object] = []
    for k in range(6):
        z_k = -0.12 + k * 0.06
        y_k = 0.065 + (0.04 * (k / 5.0) * -0.4)
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.022, depth=0.022, location=(0.0, y_k + 0.02, z_k), rotation=(math.radians(76), 0.0, 0.0))
        kparts.append(bpy.context.active_object)
    keys = _join_parts(f"{name}_Keys", kparts, key_m, col, smooth=True)
    keys.parent = sax_root

    rings: list[bpy.types.Object] = []
    if with_rings and glow_m is not None:
        for ri in range(2):
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.14 + ri * 0.08,
                minor_radius=0.018,
                major_segments=28,
                minor_segments=8,
                location=(0.0, 0.34 + ri * 0.11, -0.04 + ri * 0.03),
                rotation=(math.radians(82), 0.0, 0.0),
            )
            ring = bpy.context.active_object
            ring.name = f"{name}_Ring_{ri}"
            ring.data.materials.append(glow_m)
            _assign_to_col(ring, col)
            ring.parent = sax_root
            rings.append(ring)
    return sax_root, rings


def _build_trumpet(col: bpy.types.Collection, name: str, gold_m: bpy.types.Material, valve_m: bpy.types.Material) -> bpy.types.Object:
    root = bpy.data.objects.new(name, None)
    root.empty_display_size = 0.05
    col.objects.link(root)
    parts: list[bpy.types.Object] = []
    bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=0.024, depth=0.52, location=(0.0, 0.22, 0.04), rotation=(math.pi * 0.5, 0.0, 0.0))
    parts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.018, depth=0.34, location=(0.0, 0.16, -0.04), rotation=(math.pi * 0.5, 0.0, 0.0))
    parts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.026, radius2=0.135, depth=0.22, location=(0.0, 0.56, 0.04), rotation=(-math.pi * 0.5, 0.0, 0.0))
    parts.append(bpy.context.active_object)
    body = _join_parts(f"{name}_Body", parts, gold_m, col, smooth=True)
    body.parent = root
    vparts: list[bpy.types.Object] = []
    for vi in range(3):
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.018, depth=0.14, location=(0.0, 0.14 + vi * 0.048, 0.06))
        vparts.append(bpy.context.active_object)
    valves = _join_parts(f"{name}_Valves", vparts, valve_m, col, smooth=True)
    valves.parent = root
    return root


def _build_drumstick(col: bpy.types.Collection, name: str, stick_m: bpy.types.Material, tip_m: bpy.types.Material) -> bpy.types.Object:
    sr = bpy.data.objects.new(name, None)
    col.objects.link(sr)
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.018, depth=0.52, location=(0.0, 0.22, 0.0), rotation=(math.pi * 0.5, 0.0, 0.0))
    sh = _assign_to_col(bpy.context.active_object, col)
    sh.name = f"{name}_Shaft"
    sh.data.materials.append(stick_m)
    sh.parent = sr
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.032, location=(0.0, 0.48, 0.0))
    tp = _assign_to_col(bpy.context.active_object, col)
    tp.name = f"{name}_Tip"
    tp.data.materials.append(tip_m)
    tp.parent = sr
    return sr


def _build_gear_mesh(name: str, outer_r: float, inner_r: float, teeth: int, thickness: float, mat: bpy.types.Material, col: bpy.types.Collection) -> bpy.types.Object:
    parts: list[bpy.types.Object] = []
    bpy.ops.mesh.primitive_cylinder_add(vertices=max(24, teeth * 2), radius=outer_r, depth=thickness, location=(0, 0, 0))
    rim = bpy.context.active_object
    rim.scale = (1.0, 1.0, 0.72)
    parts.append(rim)
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=inner_r, depth=thickness * 1.15, location=(0, 0, 0))
    parts.append(bpy.context.active_object)
    tooth_w = (2.0 * math.pi * outer_r) / (teeth * 2.15)
    tooth_h = outer_r * 0.16
    for i in range(teeth):
        ang = 2.0 * math.pi * i / teeth
        tx = (outer_r + tooth_h * 0.35) * math.cos(ang)
        ty = (outer_r + tooth_h * 0.35) * math.sin(ang)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(tx, ty, 0.0), rotation=(0.0, 0.0, ang))
        tobj = bpy.context.active_object
        tobj.scale = (tooth_h, tooth_w, thickness * 0.85)
        parts.append(tobj)
    for s in range(6):
        ang = math.pi * s / 3.0
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0), rotation=(0.0, 0.0, ang))
        sp = bpy.context.active_object
        sp.scale = (outer_r * 1.88, max(0.06, outer_r * 0.09), thickness * 0.96)
        parts.append(sp)
    gear = _join_parts(name, parts, mat, col, smooth=False)
    gear.rotation_euler = (math.pi * 0.5, 0.0, 0.0)
    return gear


def _build_set1_museum(spec: dict[str, Any], acts_basic: dict[str, bpy.types.Action], shared_mats: dict[str, Any], frames_data: list[dict[str, Any]], total_frames: int) -> bpy.types.Collection:
    """Set 1 (-60, 0, 0): Royal Emerald Museum Vault (Heist Act 1 + Epilogue Tag Act 7)."""
    OX, OY = -60.0, 0.0
    col = bpy.data.collections.new("Set1_MuseumVault")
    bpy.context.scene.collection.children.link(col)

    marble_dark_m, _ = _make_mat("S1_MarbleDark", (0.025, 0.055, 0.048, 1.0), roughness=0.22)
    emerald_col_m, _ = _make_mat("S1_EmeraldColumn", (0.04, 0.14, 0.11, 1.0), metallic=0.15, roughness=0.28)
    crimson_velvet_m, _ = _make_mat("S1_Velvet", (0.42, 0.03, 0.06, 1.0), roughness=0.82)
    laser_m, laser_bsdf = _make_mat("S1_Laser", (1.0, 0.08, 0.14, 1.0), emission_color=(1.0, 0.08, 0.16, 1.0), emission_strength=9.0)
    alarm_m, alarm_bsdf = _make_mat("S1_Alarm", (1.0, 0.10, 0.05, 1.0), emission_color=(1.0, 0.08, 0.05, 1.0), emission_strength=0.4)
    emp_m, emp_bsdf = _make_mat("S1_EMP", (0.12, 0.94, 1.0, 1.0), emission_color=(0.14, 0.95, 1.0, 1.0), emission_strength=10.0)

    # Hall Floor & Back Wall
    bpy.ops.mesh.primitive_plane_add(size=26.0, location=(OX, OY, 0.0))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(marble_dark_m)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX, OY + 5.8, 3.5))
    bwall = _assign_to_col(bpy.context.active_object, col)
    bwall.scale = (20.0, 0.5, 7.0)
    bwall.data.materials.append(emerald_col_m)

    # Red Velvet Runner & Pedestal
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX, OY - 1.5, 0.008))
    runner = _assign_to_col(bpy.context.active_object, col)
    runner.scale = (2.6, 10.0, 0.016)
    runner.data.materials.append(crimson_velvet_m)

    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.72, depth=1.05, location=(OX, OY + 1.8, 0.525))
    ped = _assign_to_col(bpy.context.active_object, col)
    ped.data.materials.append(emerald_col_m)
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.62, depth=0.10, location=(OX, OY + 1.8, 1.08))
    ped_top = _assign_to_col(bpy.context.active_object, col)
    ped_top.data.materials.append(shared_mats["gold"])
    bpy.ops.mesh.primitive_torus_add(major_radius=0.58, minor_radius=0.04, location=(OX, OY + 1.8, 1.15))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(crimson_velvet_m)

    # Marble Columns + Gold Sconces
    for cx, cy in ((-3.4, -0.8), (3.4, -0.8), (-4.2, 2.8), (4.2, 2.8)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=18, radius=0.45, depth=6.2, location=(OX + cx, OY + cy, 3.1))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(emerald_col_m)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.52, minor_radius=0.07, location=(OX + cx, OY + cy, 0.14))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["brass"])

    # Display Showcase Frame (4 slender brass posts + openable top lid so glass never blocks colors!)
    dome_root = bpy.data.objects.new("S1_ShowcaseFrame", None)
    dome_root.location = (OX, OY + 1.8, 1.12)
    _assign_to_col(dome_root, col)
    fparts = []
    for px in (-0.42, 0.42):
        for py in (-0.42, 0.42):
            bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.025, depth=1.05, location=(px, py, 0.52))
            fparts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 1.06))
    cap = bpy.context.active_object
    cap.scale = (0.94, 0.94, 0.06)
    fparts.append(cap)
    fmesh = _join_parts("S1_ShowcaseCage", fparts, shared_mats["brass"], col, smooth=False)
    fmesh.parent = dome_root

    # 6 Glowing Crimson Security Lasers framing the Pedestal
    lasers = []
    for lx, ly, lz, rot in (
        (-0.52, 0.0, 0.55, (math.pi * 0.5, 0.0, math.radians(15))),
        (0.52, 0.0, 0.55, (math.pi * 0.5, 0.0, math.radians(-15))),
        (0.0, -0.52, 0.35, (0.0, math.pi * 0.5, math.radians(15))),
        (0.0, 0.52, 0.35, (0.0, math.pi * 0.5, math.radians(-15))),
        (-0.55, -0.35, 0.80, (0.0, math.pi * 0.5, math.radians(38))),
        (0.55, -0.35, 0.80, (0.0, math.pi * 0.5, math.radians(-38))),
    ):
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.018, depth=2.6, location=(OX + lx, OY + 1.8 + ly, 1.15 + lz), rotation=rot)
        lz_obj = _assign_to_col(bpy.context.active_object, col)
        lz_obj.data.materials.append(laser_m)
        lasers.append(lz_obj)

    # Red Spinning Alarm Beacon on top of Pedestal Canopy
    bpy.ops.mesh.primitive_uv_sphere_add(segments=14, ring_count=10, radius=0.18, location=(OX, OY + 1.8, 3.6))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(alarm_m)

    # Pedestal Target Golden Saxophone (vanishes when Mage snatches it at f176!)
    sax_ped, _ = _build_saxophone(col, "S1_PedestalSax", shared_mats["gold"], shared_mats["pearl"])
    sax_ped.location = (OX, OY + 1.8, 1.62)
    sax_ped.scale = (1.18, 1.18, 1.18)

    # Calling Card Epilogue Trophy: Golden Vinyl Record + Upright 3D Musical Note on Velvet Cushion!
    card_root = bpy.data.objects.new("S1_CallingCard", None)
    card_root.location = (OX, OY + 1.8, 1.32)
    _assign_to_col(card_root, col)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.40, depth=0.04, location=(0.0, 0.0, 0.0))
    c_disc = _assign_to_col(bpy.context.active_object, col)
    c_disc.data.materials.append(shared_mats["gold"])
    c_disc.parent = card_root
    bpy.ops.mesh.primitive_torus_add(major_radius=0.42, minor_radius=0.02, location=(0.0, 0.0, 0.02))
    c_ring = _assign_to_col(bpy.context.active_object, col)
    c_ring.data.materials.append(shared_mats["sax_glow"])
    c_ring.parent = card_root
    # 3D Golden Eighth-Note perched cleanly upright above the golden vinyl
    note_parts = []
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=0.12, location=(-0.06, 0.0, 0.24))
    nh = bpy.context.active_object
    nh.scale = (1.25, 0.75, 0.9)
    note_parts.append(nh)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.032, depth=0.46, location=(0.06, 0.0, 0.45))
    note_parts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.18, 0.0, 0.60), rotation=(0.0, math.radians(-26.0), 0.0))
    nf = bpy.context.active_object
    nf.scale = (0.26, 0.055, 0.14)
    note_parts.append(nf)
    note_mesh = _join_parts("S1_GoldenNote", note_parts, shared_mats["sax_glow"], col, smooth=True)
    note_mesh.parent = card_root

    # EMP Bomb & Shockwave Dome
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.12, location=(OX - 2.6, OY - 1.2, 1.0))
    emp_orb = _assign_to_col(bpy.context.active_object, col)
    emp_orb.data.materials.append(emp_m)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=(OX, OY + 1.8, 1.2))
    emp_wave = _assign_to_col(bpy.context.active_object, col)
    emp_wave.data.materials.append(emp_m)

    # Set 1 Lights (spot overhead on pedestal + emerald hall fill)
    for lname, ltype, loc, eng, col_rgb in (
        ("S1_VaultSpot", "SPOT", (OX, OY + 1.4, 5.2), 1400.0, (0.85, 1.0, 0.90)),
        ("S1_HallKey", "AREA", (OX - 3.5, OY - 4.5, 4.2), 620.0, (0.55, 0.95, 0.78)),
        ("S1_HallRim", "AREA", (OX + 3.5, OY - 3.0, 3.8), 460.0, (1.0, 0.72, 0.35)),
    ):
        ld = bpy.data.lights.new(lname, type=ltype)
        ld.energy = eng
        ld.color = col_rgb
        if ltype == "SPOT":
            ld.spot_size = math.radians(48)
            ld.spot_blend = 0.45
        else:
            ld.size = 3.5
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((OX, OY + 1.5, 1.2)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        _assign_to_col(lo, col)

    # Cast S1: Knight patrolling (QUATERNION Walking_A!), Rogue_Hooded throwing EMP, Mage grabbing Sax
    k_root, k_arm = _spawn_band_member(spec["cast"]["knight"], col, "S1_Knight", (OX - 2.2, OY + 0.15, 0.0), 90.0, 0.0, use_euler_pose=False)
    _attach_glb_prop(spec["cast"]["sword_1handed"], col, k_arm, "handslot.r", "S1_KnightSword")
    _attach_glb_prop(spec["cast"]["shield_round"], col, k_arm, "handslot.l", "S1_KnightShield")
    _bind_cloned_action(k_arm, acts_basic["Walking_A"], tag="S1_KnightWalk", cycle=True)

    r_root, r_arm = _spawn_band_member(spec["cast"]["rogue_hooded"], col, "S1_RogueHooded", (OX - 2.6, OY - 1.5, 0.0), -25.0, 0.0)
    m_root, m_arm = _spawn_band_member(spec["cast"]["mage"], col, "S1_Mage", (OX + 2.5, OY - 1.2, 0.0), 25.0, 0.0)
    m_sax, _ = _build_saxophone(col, "S1_MageHeldSax", shared_mats["gold"], shared_mats["pearl"])
    _attach_custom_prop(m_arm, "handslot.r", m_sax, rot_deg=(12.0, 16.0, -45.0), scale=1.18)

    # Animate Set 1 Timeline (f 1..192 & f 1326..1386)
    s1_frames = sorted(set(range(1, 193, 3)) | {1, 165, 166, 172, 174, 175, 176, 182, 192, 1326, 1350, 1370, 1386})
    for f in s1_frames:
        # Knight patrol path x: -2.4 -> +2.4 -> pause shock at 172..192
        if f <= 165:
            p = ((f - 1) / 164.0)
            kx = OX - 2.4 + 4.8 * (1.0 - abs(2.0 * p - 1.0))
            kyaw = 90.0 if p <= 0.5 else -90.0
            k_root.location = (kx, OY + 0.15, 0.0)
            k_root.rotation_euler = (0.0, 0.0, math.radians(kyaw))
        else:
            # Startle spin toward pedestal!
            u = min(1.0, (f - 165) / 15.0)
            k_root.location = (OX - 1.8, OY + 0.15, 0.0)
            k_root.rotation_euler = (0.0, 0.0, math.radians(-90.0 + 235.0 * u))
        k_root.keyframe_insert("location", frame=f)
        k_root.keyframe_insert("rotation_euler", frame=f)

        # Rogue EMP toss arc f 166..174
        if f < 166:
            r_root.location = (OX - 2.75, OY - 1.4, 0.0)
            emp_orb.location = (OX - 2.6, OY - 1.2, 0.9)
            emp_orb.scale = (0.0, 0.0, 0.0)
            _kf_bone_rot(r_arm, "upperarm.r", (-62.0, 0.0, 18.0), f)
        elif f <= 174:
            u = (f - 166) / 8.0
            r_root.location = (OX - 2.2 + 0.6 * u, OY - 1.0 + 0.8 * u, 0.0)
            emp_orb.location = (
                OX - 2.2 + 2.2 * u,
                OY - 1.0 + 2.8 * u,
                1.0 + 1.4 * math.sin(u * math.pi),
            )
            emp_orb.scale = (1.0, 1.0, 1.0)
            _kf_bone_rot(r_arm, "upperarm.r", (-15.0 + 45.0 * u, 0.0, 55.0), f)
        else:
            r_root.location = (OX - 1.2, OY + 0.5, 0.0)
            emp_orb.scale = (0.0, 0.0, 0.0)
            _kf_bone_rot(r_arm, "upperarm.r", (-45.0, 0.0, 45.0), f)
        r_root.keyframe_insert("location", frame=f)
        emp_orb.keyframe_insert("location", frame=f)
        emp_orb.keyframe_insert("scale", frame=f)

        # EMP Shockwave burst f 173..181
        if 173 <= f <= 181:
            ew = ((f - 173) / 8.0) * 3.8
            emp_wave.scale = (ew, ew, ew)
        else:
            emp_wave.scale = (0.0, 0.0, 0.0)
        emp_wave.keyframe_insert("scale", frame=f)

        # Glass Showcase lifts & Lasers kill on EMP hit (f 174..192), Lasers come back blinking in Epilogue!
        if f < 174:
            dome_root.location.z = 1.12
            laser_sc = 1.0
        elif f <= 192:
            dome_root.location.z = 1.12 + min(1.8, (f - 174) * 0.25)
            laser_sc = 0.0
        else:
            dome_root.location.z = 1.12
            laser_sc = 1.0 if (f // 12) % 2 == 0 else 0.15
        dome_root.keyframe_insert("location", frame=f)
        for lz in lasers:
            lz.scale = (laser_sc, laser_sc, 1.0 if laser_sc > 0.0 else 0.0)
            lz.keyframe_insert("scale", frame=f)

        # Pedestal Sax <-> Mage Dash & Snatch (f 174..192)
        if f < 173:
            sax_ped.rotation_euler.z = f * 0.04
            sax_ped.scale = (1.18, 1.18, 1.18)
            m_sax.scale = (0.0, 0.0, 0.0)
            m_root.location = (OX + 2.6, OY - 1.1, 0.0)
            _kf_bone_rot(m_arm, "upperarm.r", (-62.0, 0.0, 18.0), f)
            _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 35.0), f)
        elif f < 180:
            u = (f - 173) / 7.0
            sax_ped.scale = (1.18, 1.18, 1.18) if f < 177 else (0.0, 0.0, 0.0)
            m_sax.scale = (0.0, 0.0, 0.0) if f < 177 else (1.0, 1.0, 1.0)
            m_root.location = (OX + 2.6 - 2.3 * u, OY - 1.1 + 2.2 * u, 0.0)
            _kf_bone_rot(m_arm, "upperarm.r", (-35.0, 0.0, 56.0), f)
            _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 65.0), f)
        else:
            sax_ped.scale = (0.0, 0.0, 0.0)
            m_sax.scale = (1.0, 1.0, 1.0) if f <= 192 else (0.0, 0.0, 0.0)
            m_root.location = (OX + 0.35, OY + 1.0, 0.0) if f <= 192 else (OX + 12.0, OY, 0.0)
            _kf_bone_rot(m_arm, "upperarm.r", (-22.0, 0.0, 52.0), f)
            _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 74.0), f)
        sax_ped.keyframe_insert("rotation_euler", frame=f)
        sax_ped.keyframe_insert("scale", frame=f)
        m_sax.keyframe_insert("scale", frame=f)
        m_root.keyframe_insert("location", frame=f)

        # Alarm strobe & Epilogue Calling Card visibility
        al_str = 14.0 if (175 <= f <= 192 and (f // 3) % 2 == 0) else 0.4
        alarm_bsdf.inputs["Emission Strength"].default_value = al_str
        alarm_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)

        card_s = 1.0 if f >= 1326 else 0.0
        card_root.scale = (card_s, card_s, card_s)
        card_root.rotation_euler.z = f * 0.05
        card_root.keyframe_insert("scale", frame=f)
        card_root.keyframe_insert("rotation_euler", frame=f)

        # Hide all S1 performers cleanly during Epilogue f >= 1326!
        hide_actors = (f >= 1326)
        for root_act in (k_root, r_root, m_root):
            if hide_actors:
                root_act.location.z = -15.0
                root_act.keyframe_insert("location", frame=f)

    # Also pose Set 1 RogueHooded & Mage legs/left arms cleanly in Act 1
    for f in s1_frames:
        _kf_bone_rot(r_arm, "upperarm.l", (-62.0, 0.0, -20.0), f)
        _kf_bone_rot(r_arm, "lowerarm.l", (0.0, 0.0, -35.0), f)
        _kf_bone_rot(m_arm, "upperarm.l", (-54.0, 0.0, -34.0), f)
        _kf_bone_rot(m_arm, "lowerarm.l", (0.0, 0.0, -46.0), f)
        if f >= 166:
            _kf_bone_rot(r_arm, "lowerarm.r", (0.0, 0.0, 48.0), f)

    _kf_constant_visibility(col, SET_INTERVALS["set1"], total_frames)
    return col


def _build_set2_rooftop(spec: dict[str, Any], acts_basic: dict[str, bpy.types.Action], shared_mats: dict[str, Any], total_frames: int) -> bpy.types.Collection:
    """Set 2 (+60, 0, 0): Moonlit Neon Rooftop Chase & Chasm Leap (f 193..396)."""
    OX, OY = 60.0, 0.0
    col = bpy.data.collections.new("Set2_RooftopChase")
    bpy.context.scene.collection.children.link(col)

    roof_m, _ = _make_mat("S2_Rooftop", (0.04, 0.045, 0.075, 1.0), roughness=0.55)
    trim_cyan_m, _ = _make_mat("S2_NeonCyan", (0.10, 0.92, 1.0, 1.0), emission_color=(0.10, 0.92, 1.0, 1.0), emission_strength=4.5)
    win_gold_m, _ = _make_mat("S2_WinGold", (1.0, 0.78, 0.32, 1.0), emission_color=(1.0, 0.74, 0.25, 1.0), emission_strength=1.4)
    moon_m, _ = _make_mat("S2_FullMoon", (1.0, 0.96, 0.85, 1.0), emission_color=(1.0, 0.94, 0.80, 1.0), emission_strength=2.1)
    tower_m, _ = _make_mat("S2_Skyscraper", (0.025, 0.032, 0.058, 1.0), roughness=0.6)

    # Two Rooftops separated by a dramatic 5m chasm (Bldg A x: -13..-2.5, Bldg B x: +2.5..+14)
    for bx, bw, bname in ((-8.2, 11.4, "S2_BuildingA"), (8.2, 11.4, "S2_BuildingB")):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX + bx, OY, -6.0))
        bld = _assign_to_col(bpy.context.active_object, col)
        bld.name = bname
        bld.scale = (bw, 6.2, 12.0)
        bld.data.materials.append(roof_m)
        # Neon roof edge strip facing camera (-Y)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX + bx, OY - 3.12, -0.08))
        nstrip = _assign_to_col(bpy.context.active_object, col)
        nstrip.scale = (bw, 0.06, 0.14)
        nstrip.data.materials.append(trim_cyan_m)

    # Flanking Skyline Towers ONLY (leaves x=-5.5..+5.5 open behind chasm for Giant Full Moon!)
    for sx, sy, sh, sw in (
        (-13.5, 11.0, 18.0, 3.6), (-8.5, 13.0, 20.0, 3.8),
        (8.8, 12.5, 19.0, 3.8), (13.8, 11.5, 21.0, 4.0),
    ):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX + sx, OY + sy, sh * 0.5 - 8.5))
        tw = _assign_to_col(bpy.context.active_object, col)
        tw.scale = (sw, sw, sh)
        tw.data.materials.append(tower_m)
        for wz in range(4):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX + sx, OY + sy - sw * 0.51, -2.5 + wz * 2.2))
            wn = _assign_to_col(bpy.context.active_object, col)
            wn.scale = (sw * 0.72, 0.08, 0.42)
            wn.data.materials.append(win_gold_m)

    # Giant Luminous Full Moon framed cleanly inside the Chasm Corridor!
    bpy.ops.mesh.primitive_uv_sphere_add(segments=36, ring_count=20, radius=6.8, location=(OX + 0.0, OY + 26.0, 6.2))
    moon = _assign_to_col(bpy.context.active_object, col)
    moon.name = "S2_GiantMoon"
    moon.data.materials.append(moon_m)

    # Chase Lights
    for lname, loc, eng, col_rgb in (
        ("S2_MoonRim", (OX + 0.0, OY + 6.5, 5.0), 1100.0, (0.85, 0.90, 1.0)),
        ("S2_CityKey", (OX - 4.0, OY - 7.0, 4.5), 750.0, (0.55, 0.85, 1.0)),
        ("S2_NeonFill", (OX + 4.0, OY - 6.0, 3.5), 620.0, (1.0, 0.65, 0.25)),
    ):
        ld = bpy.data.lights.new(lname, type="AREA")
        ld.size = 5.0
        ld.energy = eng
        ld.color = col_rgb
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((OX, OY, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        _assign_to_col(lo, col)

    # 4 Runners with REAL QUATERNION Action Slots (Running_A loop + Jump_Full_Long across chasm)
    m_root, m_arm = _spawn_band_member(spec["cast"]["mage"], col, "S2_Mage", (OX - 9.0, OY - 0.3, 0.0), 90.0, 0.0, use_euler_pose=False)
    m_sax, _ = _build_saxophone(col, "S2_MageSax", shared_mats["gold"], shared_mats["pearl"])
    _attach_custom_prop(m_arm, "handslot.r", m_sax, rot_deg=(12.0, 16.0, -45.0), scale=1.18)

    r_root, r_arm = _spawn_band_member(spec["cast"]["rogue"], col, "S2_Rogue", (OX - 10.2, OY + 0.6, 0.0), 90.0, 0.0, use_euler_pose=False)
    k_root, k_arm = _spawn_band_member(spec["cast"]["knight"], col, "S2_Knight", (OX - 13.0, OY - 0.4, 0.0), 90.0, 0.0, use_euler_pose=False)
    _attach_glb_prop(spec["cast"]["sword_1handed"], col, k_arm, "handslot.r", "S2_KnightSword")
    _attach_glb_prop(spec["cast"]["shield_round"], col, k_arm, "handslot.l", "S2_KnightShield")
    b_root, b_arm = _spawn_band_member(spec["cast"]["barbarian"], col, "S2_Barbarian", (OX - 14.2, OY + 0.7, 0.0), 90.0, 0.0, use_euler_pose=False)
    _attach_glb_prop(spec["cast"]["axe_1handed"], col, b_arm, "handslot.r", "S2_BarbAxe")

    # Stardust Trail Gems behind Leap
    leap_sparks = []
    for i in range(14):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.09, location=(OX, OY, -5.0))
        sp = _assign_to_col(bpy.context.active_object, col)
        sp.data.materials.append(win_gold_m if i % 2 == 0 else trim_cyan_m)
        leap_sparks.append(sp)

    # Bind Running_A initially; we build separate shadow armatures? Simpler & cleaner: use Running_A across chase f 193..324 & Jump_Full_Long on 325..365 via NLA strips cleanly!
    def _setup_nla_chase(arm: bpy.types.Object, tag: str, jump_start: int) -> None:
        ad = arm.animation_data or arm.animation_data_create()
        track = ad.nla_tracks.new()
        track.name = f"ChaseNLA_{tag}"
        run_clone = acts_basic["Running_A"].copy()
        run_clone.name = f"Run_{tag}"[:62]
        st1 = track.strips.new("RunPart1", 190, run_clone)
        st1.action_frame_start = 0
        st1.action_frame_end = 19.2
        st1.repeat = max(1.0, (jump_start - 190) / 19.2)

        jmp_clone = acts_basic["Jump_Full_Long"].copy()
        jmp_clone.name = f"Jump_{tag}"[:62]
        st2 = track.strips.new("ChasmLeap", jump_start, jmp_clone)
        st2.action_frame_start = 2
        st2.action_frame_end = 56
        st2.scale = 0.72
        st2.blend_in = 3.0

        # Ensure Action Slot is picked cleanly on NLA strips if Blender 5 uses strip.action_slot
        if hasattr(st1, "action_slot") and hasattr(run_clone, "slots"):
            os1 = [s for s in run_clone.slots if getattr(s, "target_id_type", None) == "OBJECT"]
            if os1:
                st1.action_slot = os1[0]
        if hasattr(st2, "action_slot") and hasattr(jmp_clone, "slots"):
            os2 = [s for s in jmp_clone.slots if getattr(s, "target_id_type", None) == "OBJECT"]
            if os2:
                st2.action_slot = os2[0]

        run_idle = acts_basic["Idle_A"].copy() if "Idle_A" in acts_basic else acts_basic["Running_A"].copy()
        run_idle.name = f"Idle_{tag}"[:62]
        st3 = track.strips.new("Landing", jump_start + 39, run_idle)
        st3.repeat = 3.0
        st3.blend_in = 3.0
        if hasattr(st3, "action_slot") and hasattr(run_idle, "slots"):
            os3 = [s for s in run_idle.slots if getattr(s, "target_id_type", None) == "OBJECT"]
            if os3:
                st3.action_slot = os3[0]

    # Wait: NLA fallback works cleanly, and let's verify in storyboard! Note `acts_basic` is Rig_Medium_MovementBasic (`Running_A`, `Jump_Full_Long`, `Walking_A`) — use `Walking_A` slowed/paused or `Running_A` cleanly if `Idle_A` not in `acts_basic`
    _setup_nla_chase(m_arm, "S2M", 322)
    _setup_nla_chase(r_arm, "S2R", 324)
    _setup_nla_chase(k_arm, "S2K", 334)
    _setup_nla_chase(b_arm, "S2B", 336)

    for f in sorted(set(range(193, 397, 2)) | {193, 324, 342, 360, 396}):
        if f <= 324:
            u = (f - 193) / 131.0
            mx = OX - 9.8 + 7.2 * u
            mz = 0.0
            rx = mx - 1.15
            rz = 0.0
            kx = OX - 12.8 + 8.5 * u
            kz = 0.0
            bx = kx - 1.25
            bz = 0.0
        elif f <= 362:
            u = (f - 324) / 38.0
            mx = OX - 2.6 + 6.0 * u
            mz = 1.65 * math.sin(u * math.pi)
            rx = mx - 1.2
            rz = 1.55 * math.sin(u * math.pi)
            ku = max(0.0, (f - 334) / 38.0)
            kx = OX - 4.3 + 6.0 * ku
            kz = 1.45 * math.sin(min(1.0, ku) * math.pi)
            bx = kx - 1.2
            bz = 1.35 * math.sin(min(1.0, ku) * math.pi)
        else:
            u = (f - 362) / 34.0
            mx, mz = OX + 3.4 + 2.4 * u, 0.0
            rx, rz = OX + 2.3 + 2.0 * u, 0.0
            kx, kz = OX + 1.7 + 1.2 * u, 0.0
            bx, bz = OX + 0.5 + 1.0 * u, 0.0

        m_root.location = (mx, OY - 0.3, mz)
        r_root.location = (rx, OY + 0.65, rz)
        k_root.location = (kx, OY - 0.4, kz)
        b_root.location = (bx, OY + 0.75, bz)
        for obj in (m_root, r_root, k_root, b_root):
            obj.keyframe_insert("location", frame=f)

        # Leap sparks arc cleanly behind Mage across chasm on 325..365
        show_sparks = 324 <= f <= 366
        for i, sp in enumerate(leap_sparks):
            sp.location = (mx - 0.3 - i * 0.28, OY + 0.1 + 0.2 * math.sin(f * 0.3 + i), max(0.15, mz - 0.08 * i + 0.25))
            sc = 1.0 if show_sparks else 0.0
            sp.scale = (sc, sc, sc)
            sp.keyframe_insert("location", frame=f)
            sp.keyframe_insert("scale", frame=f)

    _kf_constant_visibility(col, SET_INTERVALS["set2"], total_frames)
    return col


def _build_set3_speakeasy(spec: dict[str, Any], shared_mats: dict[str, Any], frames_data: list[dict[str, Any]], bpm: float, total_frames: int) -> bpy.types.Collection:
    """Set 3 (0, -60, 0): Underground Neon Speakeasy & Vinyl Groove Transformation (f 397..756)."""
    OX, OY = 0.0, -60.0
    col = bpy.data.collections.new("Set3_Speakeasy")
    bpy.context.scene.collection.children.link(col)

    mahogany_m, _ = _make_mat("S3_Mahogany", (0.06, 0.02, 0.025, 1.0), roughness=0.25)
    crimson_wall_m, _ = _make_mat("S3_CrimsonWall", (0.14, 0.018, 0.032, 1.0), roughness=0.45)
    amber_lamp_m, _ = _make_mat("S3_AmberLamp", (1.0, 0.72, 0.24, 1.0), emission_color=(1.0, 0.68, 0.20, 1.0), emission_strength=6.5)
    shock_m, shock_bsdf = _make_mat("S3_SaxShockwave", (1.0, 0.82, 0.22, 1.0), emission_color=(1.0, 0.78, 0.18, 1.0), emission_strength=2.8)
    morph_m, _ = _make_mat("S3_MorphBurst", (0.12, 0.94, 1.0, 1.0), emission_color=(0.15, 0.94, 1.0, 1.0), emission_strength=4.8)

    bpy.ops.mesh.primitive_plane_add(size=24.0, location=(OX, OY, 0.0))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(mahogany_m)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX, OY + 4.4, 3.0))
    wall = _assign_to_col(bpy.context.active_object, col)
    wall.scale = (16.0, 0.4, 6.0)
    wall.data.materials.append(crimson_wall_m)

    # Golden Art-Deco Speakeasy Arches on Back Wall
    for ax in (-3.2, 0.0, 3.2):
        bpy.ops.mesh.primitive_torus_add(major_radius=1.35, minor_radius=0.08, location=(OX + ax, OY + 4.1, 2.2), rotation=(math.pi * 0.5, 0.0, 0.0))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["gold"])

    # Warm Amber Café Tables flanking runway
    for tx, ty in ((-3.5, -2.0), (3.5, -2.0)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.48, depth=0.06, location=(OX + tx, OY + ty, 0.82))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["brass"])
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.06, depth=0.82, location=(OX + tx, OY + ty, 0.41))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(mahogany_m)
        bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=0.22, radius2=0.08, depth=0.24, location=(OX + tx, OY + ty, 1.05))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(amber_lamp_m)

    # DJ Neon Vinyl Console stage left
    dj_root = bpy.data.objects.new("S3_DJBooth", None)
    dj_root.location = (OX - 2.1, OY + 0.5, 0.0)
    dj_root.rotation_euler = (0.0, 0.0, math.radians(24.0))
    _assign_to_col(dj_root, col)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.45))
    dped = _assign_to_col(bpy.context.active_object, col)
    dped.scale = (1.15, 0.64, 0.90)
    dped.data.materials.append(shared_mats["obsidian"])
    dped.parent = dj_root
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, -0.33, 0.72))
    dstrip = _assign_to_col(bpy.context.active_object, col)
    dstrip.scale = (1.06, 0.025, 0.07)
    dstrip.data.materials.append(shared_mats["dj_neon"])
    dstrip.parent = dj_root
    bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.24, depth=0.035, location=(0.0, 0.0, 0.92))
    s3_vinyl = _assign_to_col(bpy.context.active_object, col)
    s3_vinyl.data.materials.append(shared_mats["obsidian"])
    s3_vinyl.parent = dj_root
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.05, depth=0.042, location=(0.14, 0.0, 0.92))
    vm = _assign_to_col(bpy.context.active_object, col)
    vm.data.materials.append(shared_mats["dj_neon"])
    vm.parent = s3_vinyl

    # 3 Sleek Sax Shockwave Blast Rings + Glowing Morph Halos
    blast_rings = []
    for ri in range(3):
        bpy.ops.mesh.primitive_torus_add(major_radius=0.45 + ri * 0.20, minor_radius=0.018, major_segments=36, location=(OX, OY + 0.05, 1.15), rotation=(math.radians(-62), 0.0, math.radians(-18)))
        br = _assign_to_col(bpy.context.active_object, col)
        br.data.materials.append(shock_m)
        blast_rings.append(br)

    bpy.ops.mesh.primitive_torus_add(major_radius=0.72, minor_radius=0.035, location=(OX + 1.85, OY + 0.6, 1.05))
    morph_k = _assign_to_col(bpy.context.active_object, col)
    morph_k.data.materials.append(morph_m)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.72, minor_radius=0.035, location=(OX + 0.55, OY + 1.8, 1.05))
    morph_b = _assign_to_col(bpy.context.active_object, col)
    morph_b.data.materials.append(morph_m)

    # Lights
    for lname, loc, eng, lcol in (
        ("S3_WarmKey", (OX, OY - 4.8, 4.0), 680.0, (1.0, 0.78, 0.42)),
        ("S3_CrimsonRim", (OX + 4.0, OY + 1.0, 3.2), 450.0, (1.0, 0.20, 0.35)),
        ("S3_DJCyan", (OX - 4.0, OY - 1.5, 3.0), 420.0, (0.15, 0.90, 1.0)),
    ):
        ld = bpy.data.lights.new(lname, type="AREA")
        ld.size = 3.2
        ld.energy = eng
        ld.color = lcol
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((OX, OY, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        _assign_to_col(lo, col)

    # Characters S3: Mage (Sax blast!), Rogue (Vinyl scratch!), Knight (Sword->Trumpet!), Barbarian (Axe->Sticks!), Ranger (Café cheering!)
    m_root, m_arm = _spawn_band_member(spec["cast"]["mage"], col, "S3_Mage", (OX - 0.15, OY - 0.45, 0.0), 0.0, 0.0)
    m_sax, _ = _build_saxophone(col, "S3_MageSax", shared_mats["gold"], shared_mats["pearl"], shared_mats["sax_glow"])
    _attach_custom_prop(m_arm, "handslot.r", m_sax, rot_deg=(12.0, 16.0, -45.0), scale=1.22)

    r_root, r_arm = _spawn_band_member(spec["cast"]["rogue"], col, "S3_Rogue", (OX - 2.38, OY + 1.12, 0.0), 24.0, 0.0)
    k_root, k_arm = _spawn_band_member(spec["cast"]["knight"], col, "S3_Knight", (OX + 1.85, OY + 0.6, 0.0), -28.0, 0.0)
    k_sw = _attach_glb_prop(spec["cast"]["sword_1handed"], col, k_arm, "handslot.r", "S3_KnightSword")
    k_sh = _attach_glb_prop(spec["cast"]["shield_round"], col, k_arm, "handslot.l", "S3_KnightShield")
    k_horn = _build_trumpet(col, "S3_KnightHorn", shared_mats["gold"], shared_mats["pearl"])
    _attach_custom_prop(k_arm, "handslot.r", k_horn)

    b_root, b_arm = _spawn_band_member(spec["cast"]["barbarian"], col, "S3_Barbarian", (OX + 0.55, OY + 1.85, 0.0), 0.0, 0.0)
    b_axe = _attach_glb_prop(spec["cast"]["axe_1handed"], col, b_arm, "handslot.r", "S3_BarbAxe")
    b_st_r = _build_drumstick(col, "S3_BarbStickR", shared_mats["stick"], shared_mats["tip"])
    b_st_l = _build_drumstick(col, "S3_BarbStickL", shared_mats["stick"], shared_mats["tip"])
    _attach_custom_prop(b_arm, "handslot.r", b_st_r)
    _attach_custom_prop(b_arm, "handslot.l", b_st_l)

    ran_root, ran_arm = _spawn_band_member(spec["cast"]["ranger"], col, "S3_Ranger", (OX + 2.95, OY - 1.35, 0.0), -48.0, 0.0)

    for f in sorted(set(range(397, 757, 3)) | {397, 415, 440, 460, 528, 672, 673, 704, 705, 728, 729, 756}):
        fd = frames_data[min(len(frames_data) - 1, f - 1)]
        t, mid, bass, rms = fd["t"], fd["mid"], fd["bass"], fd["rms"]
        beat = t * bpm / 60.0
        bs = math.sin(beat * math.pi)
        bh = math.sin(beat * math.pi * 0.5)

        # Mage sax blast shockwaves (f 408..460), then runway solo strut
        _kf_bone_rot(m_arm, "spine", (-14.0 * mid, 15.0 * bh, 8.0 * bh), f)
        _kf_bone_rot(m_arm, "head", (4.0 + 10.0 * abs(bs), 0.0, -6.0 * bh), f)
        _kf_bone_rot(m_arm, "upperarm.r", (-40.0 + 6.0 * bs, 0.0, 56.0), f)
        _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 74.0 + 6.0 * mid), f)
        _kf_bone_rot(m_arm, "upperarm.l", (-42.0 - 6.0 * bs, 0.0, -50.0), f)
        _kf_bone_rot(m_arm, "lowerarm.l", (0.0, 0.0, -66.0), f)
        if 529 <= f <= 672:
            m_root.location = (OX - 0.15 + 0.35 * math.sin((f - 529) * 0.05), OY - 0.45 - 0.9 * math.sin((f - 529) / 143.0 * math.pi), 0.0)
        else:
            m_root.location = (OX - 0.15, OY - 0.45, 0.0)
        m_root.keyframe_insert("location", frame=f)

        for ri, br in enumerate(blast_rings):
            if 404 <= f <= 472:
                age = max(0.0, (f - 404 - ri * 10) / 38.0)
                sc = age * 2.5 if 0.0 < age < 1.1 else 0.0
            else:
                sc = (0.9 + 0.35 * mid) * (0.65 if ri == 0 else 0.0)
            br.scale = (sc, sc, sc)
            br.keyframe_insert("scale", frame=f)

        # Knight & Barbarian: knocked back f418..455 -> start grooving -> weapon morphs into brass/drums at f705 & f729!
        knock = math.sin(min(1.0, max(0.0, (f - 418) / 32.0)) * math.pi) if 418 <= f <= 452 else 0.0
        k_root.location = (OX + 1.85 + 0.8 * knock, OY + 0.6 + 0.9 * knock, 0.0)
        b_root.location = (OX + 0.55 + 0.2 * knock, OY + 1.85 + 1.0 * knock, 0.0)
        k_root.keyframe_insert("location", frame=f)
        b_root.keyframe_insert("location", frame=f)

        _kf_bone_rot(k_arm, "spine", (-24.0 * knock + 4.0 * abs(bs), -8.0 * bh, 0.0), f)
        _kf_bone_rot(b_arm, "spine", (-22.0 * knock + 6.0 * bs, 10.0 * bh, 0.0), f)
        _kf_bone_rot(k_arm, "upperarm.r", (-28.0 if f >= 705 else -48.0, 0.0, 58.0 if f >= 705 else 38.0), f)
        _kf_bone_rot(k_arm, "lowerarm.r", (0.0, 0.0, 78.0 if f >= 705 else 48.0), f)
        _kf_bone_rot(k_arm, "upperarm.l", (-54.0, 0.0, -40.0 if f < 705 else -26.0), f)
        _kf_bone_rot(k_arm, "lowerarm.l", (0.0, 0.0, -45.0), f)
        _kf_bone_rot(b_arm, "upperarm.r", (-36.0 + 20.0 * max(0.0, bs), 0.0, 48.0), f)
        _kf_bone_rot(b_arm, "lowerarm.r", (0.0, 0.0, 62.0), f)
        _kf_bone_rot(b_arm, "upperarm.l", (-36.0 + 20.0 * max(0.0, -bs), 0.0, -48.0), f)
        _kf_bone_rot(b_arm, "lowerarm.l", (0.0, 0.0, -62.0), f)

        # Weapon -> Instrument Swap!
        for p_old, p_new, cut in ((k_sw, k_horn, 705), (k_sh, None, 705), (b_axe, b_st_r, 729)):
            show_old = (f < cut)
            p_old.scale = (1.0, 1.0, 1.0) if show_old else (0.0, 0.0, 0.0)
            p_old.keyframe_insert("scale", frame=f)
            if p_new is not None:
                p_new.scale = (0.0, 0.0, 0.0) if show_old else (1.0, 1.0, 1.0)
                p_new.keyframe_insert("scale", frame=f)
        b_st_l.scale = (0.0, 0.0, 0.0) if f < 729 else (1.0, 1.0, 1.0)
        b_st_l.keyframe_insert("scale", frame=f)

        mk = 1.3 * math.sin(((f - 698) / 14.0) * math.pi) if 698 <= f <= 712 else 0.0
        mb = 1.3 * math.sin(((f - 722) / 14.0) * math.pi) if 722 <= f <= 736 else 0.0
        morph_k.scale = (mk, mk, mk)
        morph_b.scale = (mb, mb, mb)
        morph_k.keyframe_insert("scale", frame=f)
        morph_b.keyframe_insert("scale", frame=f)

        # Rogue turntable spin/scratch + Ranger cheering (ZERO T-pose arms!)
        is_scr = 673 <= f <= 756
        s3_vinyl.rotation_euler.z = t * 3.5 + (1.8 * math.sin(t * 20.0) if is_scr else 0.0)
        s3_vinyl.keyframe_insert("rotation_euler", frame=f)
        _kf_bone_rot(r_arm, "upperarm.r", (-42.0, 0.0, 54.0 + (24.0 * math.sin(t * 18.0) if is_scr else 8.0 * bs)), f)
        _kf_bone_rot(r_arm, "lowerarm.r", (0.0, 0.0, 62.0), f)
        _kf_bone_rot(r_arm, "upperarm.l", (-48.0, 0.0, -32.0), f)
        _kf_bone_rot(r_arm, "lowerarm.l", (0.0, 0.0, -48.0), f)
        _kf_bone_rot(ran_arm, "upperarm.r", (-54.0 + 18.0 * abs(bs), 0.0, 24.0), f)
        _kf_bone_rot(ran_arm, "lowerarm.r", (0.0, 0.0, 42.0), f)
        _kf_bone_rot(ran_arm, "upperarm.l", (-54.0 + 18.0 * abs(-bs), 0.0, -24.0), f)
        _kf_bone_rot(ran_arm, "lowerarm.l", (0.0, 0.0, -42.0), f)

    _kf_constant_visibility(col, SET_INTERVALS["set3"], total_frames)
    return col


def _build_set4_astral(spec: dict[str, Any], shared_mats: dict[str, Any], frames_data: list[dict[str, Any]], total_frames: int) -> bpy.types.Collection:
    """Set 4 (0, +60, 0): Enchanted Clockwork Astral Cosmos (f 757..948)."""
    OX, OY = 0.0, 60.0
    col = bpy.data.collections.new("Set4_AstralCosmos")
    bpy.context.scene.collection.children.link(col)

    plat_m, _ = _make_mat("S4_CloudDisk", (0.18, 0.25, 0.45, 1.0), metallic=0.3, roughness=0.25, emission_color=(0.35, 0.62, 1.0, 1.0), emission_strength=0.6)
    chime_m, chime_bsdf = _make_mat("S4_Chime", (0.65, 0.90, 1.0, 1.0), metallic=0.25, roughness=0.1, emission_color=(0.55, 0.88, 1.0, 1.0), emission_strength=3.5)
    star_m, star_bsdf = _make_mat("S4_Star", (1.0, 0.88, 0.48, 1.0), emission_color=(1.0, 0.85, 0.35, 1.0), emission_strength=4.5)

    # 3 Giant Tilting Golden Astrolabe Rings
    astro_rings = []
    for ri, r_rad in enumerate((4.6, 5.6, 6.6)):
        bpy.ops.mesh.primitive_torus_add(major_radius=r_rad, minor_radius=0.07, major_segments=64, minor_segments=12, location=(OX, OY + 1.5, 2.0))
        ar = _assign_to_col(bpy.context.active_object, col)
        ar.data.materials.append(shared_mats["gold"] if ri % 2 == 0 else shared_mats["brass"])
        ar.rotation_euler = (math.radians(32 * (ri + 1)), math.radians(24 * ri), 0.0)
        astro_rings.append(ar)

    # 5 Floating Luminous Stepping Platforms + Brass Trim
    plat_locs = [(0.0, -0.4, 0.55), (-2.3, 0.6, 0.25), (2.2, 0.5, 0.35), (0.2, 2.3, 0.90), (-1.4, -2.0, -0.1)]
    for px, py, pz in plat_locs:
        bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.95, depth=0.14, location=(OX + px, OY + py, pz - 0.07))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(plat_m)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.96, minor_radius=0.03, location=(OX + px, OY + py, pz))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["gold"])

    # 12 Overhead Crystal Glockenspiel Prisms + 32 Twinkling Stars
    chimes = []
    for ci in range(12):
        ang = math.radians(-65 + ci * (130.0 / 11.0))
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.18, location=(OX + 3.4 * math.sin(ang), OY + 1.0 + 2.2 * math.cos(ang), 3.1 + 0.4 * math.sin(ci)))
        ch = _assign_to_col(bpy.context.active_object, col)
        ch.scale = (0.65, 0.65, 2.4)
        ch.data.materials.append(chime_m)
        for poly in ch.data.polygons:
            poly.use_smooth = False
        chimes.append(ch)

    stars = []
    for si in range(32):
        ang = si * 0.85
        rad = 3.5 + (si % 4) * 1.4
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.09, location=(OX + rad * math.cos(ang), OY + 2.0 + rad * math.sin(ang) * 0.6, -0.5 + (si % 7) * 0.85))
        st = _assign_to_col(bpy.context.active_object, col)
        st.data.materials.append(star_m)
        stars.append(st)

    # Sapphire + Fairy Gold Lights
    for lname, loc, eng, lcol in (
        ("S4_SapphireKey", (OX - 3.5, OY - 5.5, 4.5), 620.0, (0.45, 0.72, 1.0)),
        ("S4_FairyGoldRim", (OX + 3.5, OY + 2.5, 3.8), 540.0, (1.0, 0.76, 0.30)),
    ):
        ld = bpy.data.lights.new(lname, type="AREA")
        ld.size = 4.0
        ld.energy = eng
        ld.color = lcol
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((OX, OY + 0.5, 1.2)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        _assign_to_col(lo, col)

    # Heroes floating & conducting
    m_root, m_arm = _spawn_band_member(spec["cast"]["mage"], col, "S4_Mage", (OX, OY - 0.4, 0.55), 0.0, 0.55)
    m_base_z = float(m_root.location.z)
    m_sax, _ = _build_saxophone(col, "S4_MageSax", shared_mats["gold"], shared_mats["pearl"])
    _attach_custom_prop(m_arm, "handslot.r", m_sax, rot_deg=(12.0, 16.0, -45.0), scale=1.18)
    r_root, r_arm = _spawn_band_member(spec["cast"]["rogue"], col, "S4_Rogue", (OX - 2.3, OY + 0.6, 0.25), 25.0, 0.25)
    k_root, k_arm = _spawn_band_member(spec["cast"]["knight"], col, "S4_Knight", (OX + 2.2, OY + 0.5, 0.35), -25.0, 0.35)
    k_horn = _build_trumpet(col, "S4_KnightHorn", shared_mats["gold"], shared_mats["pearl"])
    _attach_custom_prop(k_arm, "handslot.r", k_horn)
    b_root, b_arm = _spawn_band_member(spec["cast"]["barbarian"], col, "S4_Barbarian", (OX + 0.2, OY + 2.3, 0.90), 0.0, 0.90)

    for f in sorted(set(range(757, 949, 3)) | {757, 864, 948}):
        fd = frames_data[min(len(frames_data) - 1, f - 1)]
        t, high = fd["t"], fd["high"]
        lev = 0.35 * math.sin((f - 757) / 191.0 * math.pi) if f >= 864 else 0.0
        m_root.location.z = m_base_z + lev + 0.10 * math.sin(t * 2.2)
        m_root.keyframe_insert("location", frame=f)
        _kf_bone_rot(m_arm, "upperarm.r", (-64.0, 0.0, 16.0), f)
        _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 26.0), f)
        _kf_bone_rot(m_arm, "upperarm.l", (-12.0 + 25.0 * math.sin(t * 2.5), 0.0, -48.0), f)
        _kf_bone_rot(m_arm, "lowerarm.l", (0.0, 0.0, -35.0), f)
        _kf_bone_rot(k_arm, "upperarm.r", (-34.0 + 12.0 * math.sin(t * 2.0), 0.0, 52.0), f)
        _kf_bone_rot(k_arm, "lowerarm.r", (0.0, 0.0, 72.0), f)
        _kf_bone_rot(k_arm, "upperarm.l", (-56.0, 0.0, -24.0), f)
        _kf_bone_rot(k_arm, "lowerarm.l", (0.0, 0.0, -38.0), f)
        for arm_o in (r_arm, b_arm):
            sw = math.sin(t * 2.2)
            _kf_bone_rot(arm_o, "upperarm.r", (-58.0 + 14.0 * sw, 0.0, 24.0), f)
            _kf_bone_rot(arm_o, "lowerarm.r", (0.0, 0.0, 38.0), f)
            _kf_bone_rot(arm_o, "upperarm.l", (-58.0 - 14.0 * sw, 0.0, -24.0), f)
            _kf_bone_rot(arm_o, "lowerarm.l", (0.0, 0.0, -38.0), f)
            _kf_bone_rot(arm_o, "spine", (6.0 * math.cos(t * 2.0), 8.0 * sw, 0.0), f)

        for ri, ar in enumerate(astro_rings):
            ar.rotation_euler = (
                math.radians(32 * (ri + 1)) + t * (0.22 + 0.08 * ri),
                math.radians(24 * ri) + t * (0.18 - 0.1 * ri),
                t * 0.15 * (1 if ri % 2 == 0 else -1),
            )
            ar.keyframe_insert("rotation_euler", frame=f)

        chime_bsdf.inputs["Emission Strength"].default_value = 1.6 + 8.0 * high
        chime_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
        for ci, ch in enumerate(chimes):
            ch.rotation_euler.z = t * 0.9 + ci
            ch.keyframe_insert("rotation_euler", frame=f)
        star_bsdf.inputs["Emission Strength"].default_value = 2.0 + 5.5 * high
        star_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)

    _kf_constant_visibility(col, SET_INTERVALS["set4"], total_frames)
    return col


def _build_set5_ballroom(spec: dict[str, Any], shared_mats: dict[str, Any], frames_data: list[dict[str, Any]], bpm: float, total_frames: int) -> bpy.types.Collection:
    """Set 5 (0, 0, 0): Grand Clockwork Ballroom 5-Piece Finale (f 949..1325)."""
    col = bpy.data.collections.new("Set5_ClockworkBallroom")
    bpy.context.scene.collection.children.link(col)

    dark_stage_m, _ = _make_mat("S5_StageDark", (0.025, 0.028, 0.045, 1.0), metallic=0.35, roughness=0.28)
    drum_head_m, drum_head_bsdf = _make_mat("S5_DrumHeadGlow", (0.95, 0.76, 0.35, 1.0), roughness=0.35, emission_color=(1.0, 0.58, 0.14, 1.0), emission_strength=1.5)
    mirror_m, _ = _make_mat("S5_MirrorDisco", (0.92, 0.95, 1.0, 1.0), metallic=0.96, roughness=0.10, emission_color=(0.82, 0.90, 1.0, 1.0), emission_strength=0.45)

    bpy.ops.mesh.primitive_plane_add(size=80.0, location=(0.0, 0.0, -0.35))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["obsidian"])

    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=4.8, depth=0.35, location=(0.0, 0.15, -0.175))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(dark_stage_m)
    for rr, rn in ((4.76, "S5_StageRimOuter"), (2.85, "S5_StageInlay")):
        bpy.ops.mesh.primitive_torus_add(major_radius=rr, minor_radius=0.04, major_segments=64, location=(0.0, 0.15, 0.002))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["brass"])

    # Raised Riser at (0.40, 2.0, Z=0.65) + Clockwork Gears + Sunburst Rays
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=1.70, depth=0.65, location=(0.40, 2.00, 0.325))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["obsidian"])
    bpy.ops.mesh.primitive_torus_add(major_radius=1.68, minor_radius=0.03, major_segments=48, location=(0.40, 2.00, 0.65))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["brass"])

    sun_parts = []
    for si in range(-5, 6):
        ang = math.radians(si * 13.0)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(2.7 * math.sin(ang), 4.25, 1.15 + 1.7 * math.cos(ang)), rotation=(0.0, -ang, 0.0))
        ry = bpy.context.active_object
        ry.scale = (0.09, 0.09, 4.2 - abs(si) * 0.25)
        sun_parts.append(ry)
    _join_parts("S5_Sunburst", sun_parts, shared_mats["brass"], col, smooth=False)

    gear_c = _build_gear_mesh("S5_GearC", 1.75, 0.42, 16, 0.14, shared_mats["gold"], col)
    gear_c.location = (0.0, 3.95, 2.55)
    gear_l = _build_gear_mesh("S5_GearL", 1.02, 0.28, 12, 0.14, shared_mats["brass"], col)
    gear_l.location = (-2.38, 3.85, 2.05)
    gear_r = _build_gear_mesh("S5_GearR", 1.02, 0.28, 12, 0.14, shared_mats["brass"], col)
    gear_r.location = (2.38, 3.85, 2.05)

    # Sunburst Drum Kit & DJ Console
    kroot = bpy.data.objects.new("S5_DrumKit", None)
    kroot.location = (0.40, 1.38, 0.65)
    _assign_to_col(kroot, col)
    bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.44, depth=0.48, location=(0.0, 0.0, 0.48), rotation=(math.pi * 0.5, 0.0, 0.0))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["obsidian"])
    bpy.context.active_object.parent = kroot
    bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.40, depth=0.05, location=(0.0, -0.25, 0.48), rotation=(math.pi * 0.5, 0.0, 0.0))
    kick_head = _assign_to_col(bpy.context.active_object, col)
    kick_head.data.materials.append(drum_head_m)
    kick_head.parent = kroot
    for cx, cr in ((-0.68, 0.34), (0.68, 0.38)):
        bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=cr, radius2=0.03, depth=0.04, location=(cx, 0.14, 1.24))
        cm = _assign_to_col(bpy.context.active_object, col)
        cm.data.materials.append(shared_mats["gold"])
        cm.parent = kroot

    dj_root = bpy.data.objects.new("S5_DJBooth", None)
    dj_root.location = (-1.95, -0.35, 0.0)
    dj_root.rotation_euler = (0.0, 0.0, math.radians(28.0))
    _assign_to_col(dj_root, col)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.45))
    dp = _assign_to_col(bpy.context.active_object, col)
    dp.scale = (1.15, 0.64, 0.90)
    dp.data.materials.append(shared_mats["obsidian"])
    dp.parent = dj_root
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, -0.33, 0.72))
    ds = _assign_to_col(bpy.context.active_object, col)
    ds.scale = (1.06, 0.025, 0.07)
    ds.data.materials.append(shared_mats["dj_neon"])
    ds.parent = dj_root

    # 16-Band Neon EQ Wall + Overhead Disco Ball + 36 Sparks
    eq_bars, eq_bsdfs = [], []
    for i in range(16):
        frac = i / 15.0
        ang = math.radians(-68.0 + frac * 136.0)
        ex, ey = 4.35 * math.sin(ang), 0.25 + 3.45 * math.cos(ang)
        rgb = (0.08 + 0.9 * frac, 0.88 - 0.6 * max(0.0, frac - 0.5), 1.0 - 0.6 * frac)
        em, ebs = _make_mat(f"S5_EQ_{i:02d}", (*rgb, 1.0), emission_color=(*rgb, 1.0), emission_strength=2.2)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
        bar = _assign_to_col(bpy.context.active_object, col)
        bm = bmesh.new()
        bm.from_mesh(bar.data)
        for v in bm.verts:
            v.co.z += 0.5
        bm.to_mesh(bar.data)
        bm.free()
        bar.location = (ex, ey, 0.0)
        bar.rotation_euler = (0.0, 0.0, -ang)
        bar.scale = (0.28, 0.16, 1.0)
        bar.data.materials.append(em)
        eq_bars.append(bar)
        eq_bsdfs.append(ebs)

    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.50, location=(0.0, 0.45, 3.0))
    disco_ball = _assign_to_col(bpy.context.active_object, col)
    disco_ball.data.materials.append(mirror_m)
    for p in disco_ball.data.polygons:
        p.use_smooth = False

    sp_mat, sp_bsdf = _make_mat("S5_SparkMat", (1.0, 0.85, 0.32, 1.0), emission_color=(1.0, 0.80, 0.25, 1.0), emission_strength=4.5)
    sparks = []
    for si in range(36):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.085, location=(0.0, 0.0, -3.0))
        sp = _assign_to_col(bpy.context.active_object, col)
        sp.data.materials.append(sp_mat)
        sparks.append(sp)

    # Lights
    for lname, loc, eng, lcol in (
        ("S5_WarmKey", (0.0, -5.5, 4.4), 720.0, (1.0, 0.88, 0.70)),
        ("S5_CyanRim", (-4.8, 0.2, 3.2), 420.0, (0.12, 0.85, 1.0)),
        ("S5_MagentaRim", (4.8, 0.2, 3.2), 420.0, (1.0, 0.22, 0.68)),
        ("S5_HeroSpot", (0.0, -2.0, 6.2), 950.0, (1.0, 0.90, 0.72)),
    ):
        ld = bpy.data.lights.new(lname, type="AREA")
        ld.size = 3.2
        ld.energy = eng
        ld.color = lcol
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0.0, 0.5, 1.1)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        _assign_to_col(lo, col)

    # Full 5-Piece Ensemble on Set 5!
    m_root, m_arm = _spawn_band_member(spec["cast"]["mage"], col, "S5_Mage", (-0.35, -0.58, 0.0), 0.0, 0.0)
    m_sax, m_rings = _build_saxophone(col, "S5_MageSax", shared_mats["gold"], shared_mats["pearl"], shared_mats["sax_glow"], with_rings=True)
    _attach_custom_prop(m_arm, "handslot.r", m_sax, rot_deg=(12.0, 16.0, -45.0), scale=1.22)

    b_root, b_arm = _spawn_band_member(spec["cast"]["barbarian"], col, "S5_Barbarian", (0.40, 2.05, 0.65), 0.0, 0.65)
    _attach_custom_prop(b_arm, "handslot.r", _build_drumstick(col, "S5_StickR", shared_mats["stick"], shared_mats["tip"]))
    _attach_custom_prop(b_arm, "handslot.l", _build_drumstick(col, "S5_StickL", shared_mats["stick"], shared_mats["tip"]))

    r_root, r_arm = _spawn_band_member(spec["cast"]["rogue"], col, "S5_Rogue", (-2.30, 0.25, 0.0), 28.0, 0.0)
    k_root, k_arm = _spawn_band_member(spec["cast"]["knight"], col, "S5_Knight", (1.95, 0.22, 0.0), -25.0, 0.0)
    _attach_custom_prop(k_arm, "handslot.r", _build_trumpet(col, "S5_KnightHorn", shared_mats["gold"], shared_mats["pearl"]))
    ran_root, ran_arm = _spawn_band_member(spec["cast"]["ranger"], col, "S5_Ranger", (-1.35, 1.35, 0.0), 14.0, 0.0)

    for f in sorted(set(range(949, 1326, 2)) | {949, 1020, 1021, 1116, 1117, 1260, 1261, 1325}):
        fd = frames_data[min(len(frames_data) - 1, f - 1)]
        t, bass, mid, high, rms, b16 = fd["t"], fd["bass"], fd["mid"], fd["high"], fd["rms"], fd["b16"]
        beat = t * bpm / 60.0
        bs, bh = math.sin(beat * math.pi), math.sin(beat * math.pi * 0.5)

        if f >= 1261:
            # Serene finale ensemble bow with eyes visible!
            bu = min(1.0, (f - 1261) / 55.0)
            _kf_bone_rot(m_arm, "spine", (14.0 * math.sin(bu * math.pi * 0.8), 0.0, 0.0), f)
            _kf_bone_rot(m_arm, "head", (-10.0 * bu, 0.0, 0.0), f)
            _kf_bone_rot(m_arm, "upperarm.r", (-66.0, 0.0, 14.0), f)
            _kf_bone_rot(m_arm, "upperarm.l", (-62.0, 0.0, -40.0), f)
        else:
            kb = 0.2 + 0.55 * abs(bs)
            _kf_bone_loc(m_arm, "hips", (0.0, -0.06 * kb, 0.0), f)
            _kf_bone_rot(m_arm, "spine", (-12.0 * mid, 14.0 * bh, 7.0 * bh), f)
            _kf_bone_rot(m_arm, "head", (4.0 + 8.0 * abs(bs), 5.0 * bh, -5.0 * bh), f)
            _kf_bone_rot(m_arm, "upperarm.r", (-40.0 + 6.0 * bs, 0.0, 56.0), f)
            _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 74.0 + 6.0 * mid), f)
            _kf_bone_rot(m_arm, "upperarm.l", (-42.0 - 6.0 * bs, 0.0, -50.0), f)
            _kf_bone_rot(m_arm, "lowerarm.l", (0.0, 0.0, -66.0), f)

        # Knight Trumpet + Climax Jump (f 1170..1198)
        jz = 0.34 * math.sin(((f - 1170) / 28.0) * math.pi) if 1170 <= f <= 1198 else 0.0
        _kf_bone_loc(k_arm, "hips", (0.0, -0.06 * abs(bs) + jz, 0.0), f)
        _kf_bone_rot(k_arm, "spine", (-6.0 * mid, -10.0 * bh, -6.0 * bh), f)
        _kf_bone_rot(k_arm, "upperarm.r", (-28.0, 0.0, 58.0), f)
        _kf_bone_rot(k_arm, "lowerarm.r", (0.0, 0.0, 78.0), f)
        _kf_bone_rot(k_arm, "upperarm.l", (-40.0 + 30.0 * rms * bs, 0.0, -35.0), f)

        # Barbarian drums + Rogue DJ + Ranger cheering
        _kf_bone_rot(b_arm, "upperarm.r", (-34.0 + 26.0 * max(0.0, bs), 0.0, 48.0), f)
        _kf_bone_rot(b_arm, "lowerarm.r", (0.0, 0.0, 60.0 + 18.0 * bs), f)
        _kf_bone_rot(b_arm, "upperarm.l", (-34.0 + 26.0 * max(0.0, -bs), 0.0, -48.0), f)
        _kf_bone_rot(b_arm, "lowerarm.l", (0.0, 0.0, -60.0 - 18.0 * bs), f)
        _kf_bone_rot(r_arm, "upperarm.r", (-42.0, 0.0, 54.0 + 14.0 * bs), f)
        _kf_bone_rot(r_arm, "lowerarm.r", (0.0, 0.0, 62.0), f)
        _kf_bone_rot(ran_arm, "upperarm.r", (-12.0 + 24.0 * abs(bs), 0.0, 30.0), f)
        _kf_bone_rot(ran_arm, "upperarm.l", (-12.0 + 24.0 * abs(-bs), 0.0, -30.0), f)

        # Stage Reactors
        ang_c = t * 0.48
        gear_c.rotation_euler.y = ang_c
        gear_l.rotation_euler.y = -ang_c * (16.0 / 12.0)
        gear_r.rotation_euler.y = -ang_c * (16.0 / 12.0)
        for g in (gear_c, gear_l, gear_r):
            g.keyframe_insert("rotation_euler", frame=f)

        ks = 1.0 + 0.14 * bass
        kick_head.scale = (ks, ks, 1.0 + 0.4 * bass)
        kick_head.keyframe_insert("scale", frame=f)
        drum_head_bsdf.inputs["Emission Strength"].default_value = 0.8 + 4.5 * bass
        drum_head_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)

        for bi in range(16):
            eq_bars[bi].scale.z = 0.30 + 3.4 * b16[bi]
            eq_bars[bi].keyframe_insert("scale", frame=f)
            eq_bsdfs[bi].inputs["Emission Strength"].default_value = 0.6 + 5.8 * b16[bi]
            eq_bsdfs[bi].inputs["Emission Strength"].keyframe_insert("default_value", frame=f)

        for ri, ring in enumerate(m_rings):
            sc = (0.7 + 0.9 * mid) * (1.0 if f < 1261 else 0.1)
            ring.scale = (sc, sc, sc)
            ring.keyframe_insert("scale", frame=f)

        disco_ball.location.z = 2.85 + 0.12 * bass if 1117 <= f <= 1260 else 3.95
        disco_ball.rotation_euler.z = t * 1.4
        disco_ball.keyframe_insert("location", frame=f)
        disco_ball.keyframe_insert("rotation_euler", frame=f)

        sp_amt = 1.0 if 1117 <= f <= 1260 else 0.35
        for si, sp in enumerate(sparks):
            ang_s = t * (0.9 + 0.03 * si) + si * 0.7
            rad_s = 2.2 + 1.7 * math.sin(si + t * 0.5)
            sp.location = (rad_s * math.cos(ang_s), 0.35 + rad_s * math.sin(ang_s) * 0.75, 0.4 + ((t * 0.7 + si * 0.19) % 3.4))
            sc_sp = sp_amt * (0.45 + 0.85 * rms)
            sp.scale = (sc_sp, sc_sp, sc_sp)
            sp.keyframe_insert("location", frame=f)
            sp.keyframe_insert("scale", frame=f)
        sp_bsdf.inputs["Emission Strength"].default_value = 2.5 + 5.0 * rms
        sp_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)

    _kf_constant_visibility(col, SET_INTERVALS["set5"], total_frames)
    return col


def _shot_camera_pose(f: int, bpm: float) -> tuple[tuple[float, float, float], tuple[float, float, float], float]:
    """Compute (cam_loc, target_loc, lens_mm) across all 5 sets & 1,386 frames."""
    t = (f - 1) / 24.0
    bp = (t * bpm / 60.0) % 1.0
    kick_z = 1.6 * max(0.0, 1.0 - bp * 3.5)

    # SET 1 (-60, 0, 0) - ACT 1: MUSEUM HEIST (f 1..192)
    if f <= 165:
        u = (f - 1) / 164.0
        return ((-63.5 + 3.0 * u, -6.2 + 1.8 * u, 2.25 - 0.3 * u), (-60.0, 1.6, 1.45), 38.0 + 4.0 * u)
    if f <= 192:
        u = (f - 166) / 26.0
        return ((-63.4 + 2.0 * u, -4.5 + 0.3 * u, 2.35), (-60.2, 1.0, 1.35), 36.0 + 4.0 * u)

    # SET 2 (+60, 0, 0) - ACT 2: MOONLIT ROOFTOP CHASE & CHASM LEAP (f 193..396)
    if f <= 324:
        u = (f - 193) / 131.0
        track_x = 60.0 - 10.6 + 8.0 * u
        return ((track_x - 0.5, -8.8 + 1.0 * u, 2.05), (track_x + 0.5, 0.2, 1.25), 34.0 + kick_z)
    if f <= 360:
        u = (f - 325) / 35.0
        return ((60.0 - 1.5 + 2.8 * u, -9.6, 1.45), (60.0 + 0.1, 0.5, 1.85), 32.0)
    if f <= 396:
        u = (f - 361) / 35.0
        return ((60.0 + 5.8 - 2.4 * u, -5.2, 1.85), (60.0 + 2.8, 0.0, 1.20), 38.0)

    # SET 3 (0, -60, 0) - ACTS 3 & 4: SPEAKEASY SAX BLAST & DJ TRANSFORMATION (f 397..756)
    if f <= 528:
        u = (f - 397) / 131.0
        return ((-3.2 + 5.8 * u, -66.0, 2.05), (0.3, -59.5, 1.35), 34.0)
    if f <= 672:
        u = (f - 529) / 143.0
        return ((2.8 - 5.2 * u, -65.2 - 0.8 * math.sin(u * math.pi), 2.05), (0.3, -59.8, 1.25), 36.0 + kick_z)
    if f <= 756:
        u = (f - 673) / 83.0
        return ((-1.6 + 2.4 * u, -65.4, 2.05), (-0.2, -59.5, 1.25), 34.0 + 2.5 * abs(math.sin(u * 3 * math.pi)))

    # SET 4 (0, +60, 0) - ACT 5: ENCHANTED CLOCKWORK ASTRAL COSMOS (f 757..948)
    if f <= 948:
        u = (f - 757) / 191.0
        ang = math.radians(-24.0 + 48.0 * u)
        return ((7.4 * math.sin(ang), 60.0 - 7.4 * math.cos(ang), 2.75 + 0.65 * math.sin(u * math.pi)), (0.0, 60.5, 1.65), 30.0)

    # SET 5 (0, 0, 0) - ACT 6 & ACT 7 BOW: GRAND BALLROOM FINALE (f 949..1325)
    if f <= 1020:
        u = (f - 949) / 71.0
        return ((1.6 - 3.2 * u, -3.4, 1.45), (-0.35, -0.5, 1.25), 42.0)
    if f <= 1116:
        u = (f - 1021) / 95.0
        return ((3.4 - 2.0 * u, -4.4, 1.85), (0.8, 0.8, 1.35), 38.0 + kick_z)
    if f <= 1260:
        u = (f - 1117) / 143.0
        ang = math.radians(-28.0 + 56.0 * u)
        rad = 7.4 - 0.9 * math.sin(u * math.pi)
        return ((rad * math.sin(ang), 0.1 - rad * math.cos(ang), 2.25 + 0.85 * math.sin(u * math.pi)), (0.0, 0.55, 1.45), 34.0 + kick_z)
    if f <= 1325:
        u = (f - 1261) / 64.0
        return ((0.0, -6.2 - 1.2 * u, 1.95 + 0.6 * u), (0.0, 0.45, 1.30), 36.0)

    # SET 1 (-60, 0, 0) - ACT 7 EPILOGUE TWIST: GOLDEN VINYL CALLING CARD (f 1326..1386)
    u = (f - 1326) / max(1, 1386 - 1326)
    return ((-61.4 + 2.2 * u, -1.8, 1.95 + 0.45 * u), (-60.0, 1.8, 1.45), 42.0 + 4.0 * u)


def build_music_video_scene(spec: dict[str, Any]) -> dict[str, Any]:
    _clear_scene_safely()
    scene = bpy.context.scene
    analysis = spec["analysis"]
    frames_data = analysis["frames"]
    total_frames = int(analysis["total_frames"])
    bpm = float(analysis.get("estimated_bpm", 128.0))
    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.render.fps = int(analysis.get("fps", 24))

    # Shared PBR Material Library
    gold_m, _ = _make_mat("Shared_Gold", (0.94, 0.68, 0.20, 1.0), metallic=0.90, roughness=0.30)
    brass_m, _ = _make_mat("Shared_Brass", (0.82, 0.56, 0.18, 1.0), metallic=0.88, roughness=0.38)
    pearl_m, _ = _make_mat("Shared_Pearl", (0.95, 0.94, 0.90, 1.0), metallic=0.1, roughness=0.2)
    obs_m, _ = _make_mat("Shared_Obsidian", (0.02, 0.022, 0.032, 1.0), metallic=0.2, roughness=0.18)
    sax_glow_m, _ = _make_mat("Shared_SaxGlow", (1.0, 0.80, 0.25, 1.0), emission_color=(1.0, 0.76, 0.18, 1.0), emission_strength=4.5)
    dj_neon_m, _ = _make_mat("Shared_DJNeon", (0.10, 0.92, 1.0, 1.0), emission_color=(0.12, 0.90, 1.0, 1.0), emission_strength=4.5)
    stick_m, _ = _make_mat("Shared_Stick", (0.78, 0.56, 0.28, 1.0), roughness=0.4)
    tip_m, _ = _make_mat("Shared_StickTip", (1.0, 0.85, 0.3, 1.0), emission_color=(1.0, 0.62, 0.12, 1.0), emission_strength=3.5)
    shared_mats = {
        "gold": gold_m, "brass": brass_m, "pearl": pearl_m, "obsidian": obs_m,
        "sax_glow": sax_glow_m, "dj_neon": dj_neon_m, "stick": stick_m, "tip": tip_m,
    }

    acts_basic = _import_donor_actions(spec["cast"]["rig_medium_movementbasic"])

    _build_set1_museum(spec, acts_basic, shared_mats, frames_data, total_frames)
    _build_set2_rooftop(spec, acts_basic, shared_mats, total_frames)
    _build_set3_speakeasy(spec, shared_mats, frames_data, bpm, total_frames)
    _build_set4_astral(spec, shared_mats, frames_data, total_frames)
    _build_set5_ballroom(spec, shared_mats, frames_data, bpm, total_frames)

    # Dynamic World Color per Act + Smooth Curtain Fade-In/Out via Exposure
    world = bpy.data.worlds.new("Heist_World")
    scene.world = world
    world.use_nodes = True
    wbg = world.node_tree.nodes.get("Background")
    world_palettes = [
        (1, (0.010, 0.028, 0.022, 1.0), 0.7),     # Set 1 Emerald Vault
        (193, (0.010, 0.015, 0.048, 1.0), 0.8),   # Set 2 Moonlit Rooftop
        (397, (0.032, 0.010, 0.016, 1.0), 0.7),   # Set 3 Crimson Speakeasy
        (757, (0.008, 0.016, 0.058, 1.0), 0.85),  # Set 4 Astral Sapphire
        (949, (0.014, 0.016, 0.038, 1.0), 0.7),   # Set 5 Grand Ballroom
        (1326, (0.010, 0.028, 0.022, 1.0), 0.7),  # Set 1 Epilogue
    ]
    for wf, wcol, wstr in world_palettes:
        wbg.inputs["Color"].default_value = wcol
        wbg.inputs["Color"].keyframe_insert("default_value", frame=wf)
        wbg.inputs["Strength"].default_value = wstr
        wbg.inputs["Strength"].keyframe_insert("default_value", frame=wf)
    if world.node_tree.animation_data and world.node_tree.animation_data.action:
        for fc in _iter_action_fcurves(world.node_tree.animation_data.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"

    for f in sorted(set(range(1, 20)) | set(range(1348, total_frames + 1)) | {193, 397, 757, 949, 1326}):
        if f <= 18:
            exp_v = -7.0 * (1.0 - (f - 1) / 17.0)
        elif f >= 1352:
            exp_v = -8.0 * ((f - 1352) / max(1, total_frames - 1352))
        else:
            exp_v = 0.0
        scene.view_settings.exposure = exp_v
        scene.view_settings.keyframe_insert("exposure", frame=f)

    # Tracked Director Camera across all 5 Worlds with CONSTANT cut holds
    cam_col = bpy.data.collections.new("Heist_CameraRig")
    scene.collection.children.link(cam_col)
    cam_target = bpy.data.objects.new("Camera_Target", None)
    cam_target.location = (-60.0, 1.6, 1.45)
    cam_col.objects.link(cam_target)

    cam_data = bpy.data.cameras.new("Director_Camera")
    cam_data.clip_start = 0.05
    cam_data.clip_end = 180.0
    cam_obj = bpy.data.objects.new("Director_Camera", cam_data)
    cam_col.objects.link(cam_obj)
    tr = cam_obj.constraints.new(type="TRACK_TO")
    tr.target = cam_target
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    scene.camera = cam_obj

    cut_starts = {1, 166, 193, 325, 361, 397, 529, 673, 757, 949, 1021, 1117, 1261, 1326}
    cut_ends = {cs - 1 for cs in cut_starts if cs > 1}
    cam_frames = sorted(set(range(1, total_frames + 1, 3)) | cut_starts | cut_ends | {total_frames})
    for f in cam_frames:
        cloc, tloc, lens = _shot_camera_pose(f, bpm)
        cam_obj.location = cloc
        cam_target.location = tloc
        cam_data.lens = lens
        cam_obj.keyframe_insert("location", frame=f)
        cam_target.keyframe_insert("location", frame=f)
        cam_data.keyframe_insert("lens", frame=f)

    for obj_anim in (cam_obj, cam_target, cam_data):
        if obj_anim.animation_data and obj_anim.animation_data.action:
            for fc in _iter_action_fcurves(obj_anim.animation_data.action):
                for kp in fc.keyframe_points:
                    if int(round(kp.co.x)) in cut_ends:
                        kp.interpolation = "CONSTANT"

    # EEVEE Metal-Fast Settings + AgX + Blender 5.2 Compositor Bloom
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = int(spec.get("width", 1280))
    scene.render.resolution_y = int(spec.get("height", 720))
    scene.render.resolution_percentage = 100
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    eevee = scene.eevee
    eevee.taa_render_samples = int(spec.get("samples", 12))
    for k, v in (
        ("use_raytracing", False),
        ("use_taa_reprojection", True),
        ("shadow_ray_count", 1),
        ("shadow_step_count", 4),
        ("shadow_resolution_scale", 0.5),
    ):
        if hasattr(eevee, k):
            try:
                setattr(eevee, k, v)
            except Exception:
                pass
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass

    ng = bpy.data.node_groups.new("HeistCompositor", "CompositorNodeTree")
    if hasattr(ng, "interface"):
        ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    glare = ng.nodes.new("CompositorNodeGlare")
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Quality"].default_value = "High"
    glare.inputs["Threshold"].default_value = 1.15
    glare.inputs["Strength"].default_value = 0.36
    glare.inputs["Size"].default_value = 5.5
    out_n = ng.nodes.new("NodeGroupOutput")
    ng.links.new(rl.outputs["Image"], glare.inputs["Image"])
    ng.links.new(glare.outputs["Image"], out_n.inputs["Image"])
    if hasattr(scene, "compositing_node_group"):
        scene.compositing_node_group = ng

    blend_path = spec["blend_path"]
    os.makedirs(os.path.dirname(blend_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    return {
        "blend_path": blend_path,
        "total_frames": total_frames,
        "estimated_bpm": bpm,
        "sets": 5,
        "armatures": sum(1 for o in bpy.data.objects if o.type == "ARMATURE"),
        "mesh_count": sum(1 for o in bpy.data.objects if o.type == "MESH"),
    }


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1 :]
    spec_data = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    summary = build_music_video_scene(spec_data)
    print("MUSIC_VIDEO_BUILD_JSON:" + json.dumps(summary))
