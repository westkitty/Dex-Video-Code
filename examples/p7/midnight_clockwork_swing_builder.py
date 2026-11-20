#!/usr/bin/env python3
"""Blender 5.2+ procedural stage, custom instruments, and 128-BPM choreography builder
for "The Midnight Clockwork Swing" DEX//SCULPT music video.

Run via:
  Blender --background --python midnight_clockwork_swing_builder.py -- <scene_build_spec.json>
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
from mathutils import Euler, Matrix, Vector


def _clear_scene_safely() -> None:
    """Reset active scene objects and orphans without calling wm.read_factory_settings()."""
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


def _link_obj(obj: bpy.types.Object, col: bpy.types.Collection) -> bpy.types.Object:
    if obj.name not in col.objects:
        col.objects.link(obj)
    return obj


def _join_mesh_parts(name: str, parts: list[bpy.types.Object], mat: bpy.types.Material, col: bpy.types.Collection, *, smooth: bool = True) -> bpy.types.Object:
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
    for c in list(joined.users_collection):
        c.objects.unlink(joined)
    col.objects.link(joined)
    if smooth and joined.type == "MESH":
        for poly in joined.data.polygons:
            poly.use_smooth = True
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return joined


def _import_glb_clean(filepath: str, col_name: str, root_name: str) -> tuple[bpy.types.Collection, bpy.types.Object, bpy.types.Object, list[bpy.types.Object]]:
    before_objs = set(bpy.data.objects)
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
    for col in bpy.data.collections:
        if col.name.startswith("glTF_not_exported"):
            helper_objs.update(col.objects)

    new_objs = [o for o in bpy.data.objects if o not in before_objs and o not in helper_objs]
    new_set = set(new_objs)

    col = bpy.data.collections.new(col_name)
    bpy.context.scene.collection.children.link(col)
    for o in new_objs:
        col.objects.link(o)
        for oc in list(o.users_collection):
            if oc != col:
                oc.objects.unlink(o)

    root_empty = bpy.data.objects.new(root_name, None)
    root_empty.empty_display_type = "PLAIN_AXES"
    root_empty.empty_display_size = 0.2
    col.objects.link(root_empty)
    for o in new_objs:
        if o.parent is None or o.parent not in new_set:
            o.parent = root_empty

    arm = next((o for o in new_objs if o.type == "ARMATURE"), None)
    if arm is not None and arm.pose:
        for pb in arm.pose.bones:
            pb.rotation_mode = "XYZ"
    return col, root_empty, arm, new_objs


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


def _build_gear_mesh(name: str, outer_r: float, inner_r: float, teeth: int, thickness: float, mat: bpy.types.Material, col: bpy.types.Collection) -> bpy.types.Object:
    parts: list[bpy.types.Object] = []
    # Main rim cylinder
    bpy.ops.mesh.primitive_cylinder_add(vertices=max(24, teeth * 2), radius=outer_r, depth=thickness, location=(0, 0, 0))
    rim = bpy.context.active_object
    # Hollow center by scaling? Simpler Art-Deco gear: brass wheel rim + hub + spokes + protruding teeth
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
        t_obj = bpy.context.active_object
        t_obj.scale = (tooth_h, tooth_w, thickness * 0.85)
        parts.append(t_obj)
    for s in range(6):
        ang = math.pi * s / 3.0
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0), rotation=(0.0, 0.0, ang))
        sp = bpy.context.active_object
        sp.scale = (outer_r * 1.88, max(0.06, outer_r * 0.09), thickness * 0.96)
        parts.append(sp)
    gear = _join_mesh_parts(name, parts, mat, col, smooth=False)
    gear.rotation_euler = (math.pi * 0.5, 0.0, 0.0)
    return gear


def _build_saxophone(col: bpy.types.Collection, gold_mat: bpy.types.Material, key_mat: bpy.types.Material, glow_mat: bpy.types.Material) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    """Build golden saxophone oriented in bone-local coords (+Z toward mouth, +Y forward)."""
    sax_root = bpy.data.objects.new("PropRoot_Saxophone", None)
    sax_root.empty_display_size = 0.08
    col.objects.link(sax_root)

    parts_gold: list[bpy.types.Object] = []
    # Main tilted body tube passing through hand origin (0,0,0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.042, depth=0.62, location=(0.0, 0.03, -0.02), rotation=(math.radians(-14), 0.0, 0.0))
    parts_gold.append(bpy.context.active_object)
    # Upper crook & neck leaning back toward mouth (-Y, +Z)
    bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=0.028, depth=0.22, location=(0.0, -0.02, 0.34), rotation=(math.radians(42), 0.0, 0.0))
    parts_gold.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.018, depth=0.14, location=(0.0, -0.11, 0.42), rotation=(math.radians(82), 0.0, 0.0))
    parts_gold.append(bpy.context.active_object)
    # Bottom U-bow bend
    bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=0.055, depth=0.15, location=(0.0, 0.14, -0.32), rotation=(0.0, math.pi * 0.5, 0.0))
    parts_gold.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.052, depth=0.24, location=(0.0, 0.22, -0.18), rotation=(math.radians(-10), 0.0, 0.0))
    parts_gold.append(bpy.context.active_object)
    # Flared iconic bell pointing forward & up (+Y, +Z)
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.055, radius2=0.165, depth=0.24, location=(0.0, 0.26, 0.03), rotation=(math.radians(-22), 0.0, 0.0))
    parts_gold.append(bpy.context.active_object)

    sax_body = _join_mesh_parts("Saxophone_Body", parts_gold, gold_mat, col, smooth=True)
    sax_body.parent = sax_root

    # Pearl key buttons along sax front
    key_parts: list[bpy.types.Object] = []
    for k in range(6):
        z_k = -0.12 + k * 0.06
        y_k = 0.065 + (0.04 * (k / 5.0) * -0.4)
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.022, depth=0.022, location=(0.0, y_k + 0.02, z_k), rotation=(math.radians(76), 0.0, 0.0))
        key_parts.append(bpy.context.active_object)
    sax_keys = _join_mesh_parts("Saxophone_Keys", key_parts, key_mat, col, smooth=True)
    sax_keys.parent = sax_root

    # 2 golden glowing sound-wave torus rings flaring outward below face height
    rings: list[bpy.types.Object] = []
    for r_idx in range(2):
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.14 + r_idx * 0.08,
            minor_radius=0.018,
            major_segments=28,
            minor_segments=8,
            location=(0.0, 0.34 + r_idx * 0.11, -0.04 + r_idx * 0.03),
            rotation=(math.radians(82), 0.0, 0.0),
        )
        ring = bpy.context.active_object
        ring.name = f"SaxWaveRing_{r_idx}"
        ring.data.materials.append(glow_mat)
        for c in list(ring.users_collection):
            c.objects.unlink(ring)
        col.objects.link(ring)
        ring.parent = sax_root
        rings.append(ring)

    return sax_root, rings


def _build_trumpet(col: bpy.types.Collection, gold_mat: bpy.types.Material, valve_mat: bpy.types.Material) -> bpy.types.Object:
    horn_root = bpy.data.objects.new("PropRoot_BrassHorn", None)
    horn_root.empty_display_size = 0.06
    col.objects.link(horn_root)
    parts: list[bpy.types.Object] = []
    # Leadpipe extending forward (+Y) and upper return loop
    bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=0.024, depth=0.52, location=(0.0, 0.22, 0.04), rotation=(math.pi * 0.5, 0.0, 0.0))
    parts.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.018, depth=0.34, location=(0.0, 0.16, -0.04), rotation=(math.pi * 0.5, 0.0, 0.0))
    parts.append(bpy.context.active_object)
    # Flared trumpet bell forward
    bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.026, radius2=0.135, depth=0.22, location=(0.0, 0.56, 0.04), rotation=(-math.pi * 0.5, 0.0, 0.0))
    parts.append(bpy.context.active_object)
    body = _join_mesh_parts("BrassHorn_Body", parts, gold_mat, col, smooth=True)
    body.parent = horn_root

    vparts: list[bpy.types.Object] = []
    for vi in range(3):
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.018, depth=0.14, location=(0.0, 0.14 + vi * 0.048, 0.06))
        vparts.append(bpy.context.active_object)
    valves = _join_mesh_parts("BrassHorn_Valves", vparts, valve_mat, col, smooth=True)
    valves.parent = horn_root
    return horn_root


def _build_drumstick(name: str, col: bpy.types.Collection, stick_mat: bpy.types.Material, tip_mat: bpy.types.Material) -> bpy.types.Object:
    s_root = bpy.data.objects.new(name, None)
    s_root.empty_display_size = 0.05
    col.objects.link(s_root)
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.018, depth=0.52, location=(0.0, 0.22, 0.0), rotation=(math.pi * 0.5, 0.0, 0.0))
    shaft = bpy.context.active_object
    shaft.name = f"{name}_Shaft"
    shaft.data.materials.append(stick_mat)
    for c in list(shaft.users_collection):
        c.objects.unlink(shaft)
    col.objects.link(shaft)
    shaft.parent = s_root

    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.032, location=(0.0, 0.48, 0.0))
    tip = bpy.context.active_object
    tip.name = f"{name}_Tip"
    tip.data.materials.append(tip_mat)
    for c in list(tip.users_collection):
        c.objects.unlink(tip)
    col.objects.link(tip)
    tip.parent = s_root
    return s_root


def _build_stage_and_instruments(col: bpy.types.Collection, n_frames: int) -> dict[str, Any]:
    """Create Art-Deco stage, riser, clockwork gears, 16-band EQ, chimes, disco ball, sparks, drums, and DJ booth."""
    mats: dict[str, Any] = {}
    dark_stage_m, _ = _make_mat("Mat_StageDark", (0.025, 0.028, 0.045, 1.0), metallic=0.35, roughness=0.28)
    brass_m, _ = _make_mat("Mat_ArtDecoBrass", (0.82, 0.56, 0.18, 1.0), metallic=0.88, roughness=0.38)
    bright_gold_m, _ = _make_mat("Mat_BrightGold", (0.94, 0.68, 0.20, 1.0), metallic=0.90, roughness=0.32)
    pearl_m, _ = _make_mat("Mat_PearlWhite", (0.95, 0.94, 0.90, 1.0), metallic=0.1, roughness=0.2)
    obsidian_m, _ = _make_mat("Mat_ObsidianLacquer", (0.02, 0.022, 0.03, 1.0), metallic=0.2, roughness=0.15)
    drum_head_m, drum_head_bsdf = _make_mat("Mat_DrumHeadGlow", (0.95, 0.76, 0.35, 1.0), roughness=0.35, emission_color=(1.0, 0.58, 0.14, 1.0), emission_strength=1.5)
    sax_glow_m, sax_glow_bsdf = _make_mat("Mat_SaxWaveGlow", (1.0, 0.80, 0.25, 1.0), emission_color=(1.0, 0.76, 0.18, 1.0), emission_strength=3.5)
    dj_neon_m, dj_neon_bsdf = _make_mat("Mat_DJNeon", (0.10, 0.92, 1.0, 1.0), emission_color=(0.12, 0.90, 1.0, 1.0), emission_strength=3.2)
    stick_m, _ = _make_mat("Mat_StickWood", (0.78, 0.56, 0.28, 1.0), roughness=0.4)
    tip_m, tip_bsdf = _make_mat("Mat_StickTip", (1.0, 0.85, 0.3, 1.0), emission_color=(1.0, 0.62, 0.12, 1.0), emission_strength=3.0)
    mirror_m, _ = _make_mat("Mat_MirrorDisco", (0.92, 0.95, 1.0, 1.0), metallic=0.96, roughness=0.10, emission_color=(0.82, 0.90, 1.0, 1.0), emission_strength=0.45)

    # Outer floor + circular Art-Deco stage top flush at Z=0
    bpy.ops.mesh.primitive_plane_add(size=90.0, location=(0.0, 0.0, -0.35))
    subfloor = bpy.context.active_object
    subfloor.name = "Hall_SubFloor"
    subfloor.data.materials.append(obsidian_m)
    col.objects.link(subfloor)
    for c in list(subfloor.users_collection):
        if c != col:
            c.objects.unlink(subfloor)

    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=4.8, depth=0.35, location=(0.0, 0.15, -0.175))
    stage = bpy.context.active_object
    stage.name = "ArtDeco_MainStage"
    stage.data.materials.append(dark_stage_m)
    col.objects.link(stage)
    for c in list(stage.users_collection):
        if c != col:
            c.objects.unlink(stage)

    # Flush Art-Deco brass inlay rings at Z=0.002
    for r_ring, thick, r_name in ((4.76, 0.08, "StageRimOuter"), (2.85, 0.04, "StageInlayInner")):
        bpy.ops.mesh.primitive_torus_add(major_radius=r_ring, minor_radius=thick * 0.5, major_segments=64, minor_segments=12, location=(0.0, 0.15, 0.002))
        tr = bpy.context.active_object
        tr.name = r_name
        tr.data.materials.append(brass_m)
        col.objects.link(tr)
        for c in list(tr.users_collection):
            if c != col:
                c.objects.unlink(tr)

    # Drum riser top flush at Z=0.65 (staggered slightly right of Mage for zero occlusion!)
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=1.70, depth=0.65, location=(0.40, 2.00, 0.325))
    riser = bpy.context.active_object
    riser.name = "ArtDeco_DrumRiser"
    riser.data.materials.append(obsidian_m)
    col.objects.link(riser)
    for c in list(riser.users_collection):
        if c != col:
            c.objects.unlink(riser)

    bpy.ops.mesh.primitive_torus_add(major_radius=1.68, minor_radius=0.03, major_segments=48, minor_segments=10, location=(0.40, 2.00, 0.65))
    r_trim = bpy.context.active_object
    r_trim.name = "DrumRiser_BrassTrim"
    r_trim.data.materials.append(brass_m)
    col.objects.link(r_trim)
    for c in list(r_trim.users_collection):
        if c != col:
            c.objects.unlink(r_trim)

    # Giant Art-Deco Sunburst Rays & 3 Interlocking Clockwork Gears
    sun_parts: list[bpy.types.Object] = []
    for si in range(-5, 6):
        ang = math.radians(si * 13.0)
        bx = 4.2 * math.sin(ang)
        bz = 1.6 + 2.4 * math.cos(ang)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(bx * 0.65, 4.25, bz * 0.72), rotation=(0.0, -ang, 0.0))
        ray = bpy.context.active_object
        ray.scale = (0.09, 0.09, 4.2 - abs(si) * 0.25)
        sun_parts.append(ray)
    _join_mesh_parts("ArtDeco_SunburstRays", sun_parts, brass_m, col, smooth=False)

    gear_center = _build_gear_mesh("ClockworkGear_Center", 1.75, 0.42, 16, 0.14, bright_gold_m, col)
    gear_center.location = (0.0, 3.95, 2.55)
    gear_left = _build_gear_mesh("ClockworkGear_Left", 1.02, 0.28, 12, 0.14, brass_m, col)
    gear_left.location = (-2.38, 3.85, 2.05)
    gear_right = _build_gear_mesh("ClockworkGear_Right", 1.02, 0.28, 12, 0.14, brass_m, col)
    gear_right.location = (2.38, 3.85, 2.05)

    # Art-Deco Drum Kit centered cleanly in front of Barbarian at X=0.40, Y=1.38, Z=0.65
    kick_root = bpy.data.objects.new("DrumKit_Root", None)
    kick_root.location = (0.40, 1.38, 0.65)
    col.objects.link(kick_root)

    bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.44, depth=0.48, location=(0.0, 0.0, 0.48), rotation=(math.pi * 0.5, 0.0, 0.0))
    kick_shell = bpy.context.active_object
    kick_shell.name = "KickDrum_Shell"
    kick_shell.data.materials.append(obsidian_m)
    col.objects.link(kick_shell)
    for c in list(kick_shell.users_collection):
        if c != col:
            c.objects.unlink(kick_shell)
    kick_shell.parent = kick_root

    bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.40, depth=0.05, location=(0.0, -0.25, 0.48), rotation=(math.pi * 0.5, 0.0, 0.0))
    kick_head = bpy.context.active_object
    kick_head.name = "KickDrum_GlowHead"
    kick_head.data.materials.append(drum_head_m)
    col.objects.link(kick_head)
    for c in list(kick_head.users_collection):
        if c != col:
            c.objects.unlink(kick_head)
    kick_head.parent = kick_root

    # Snare + High Tom + Floor Tom
    kit_parts: list[bpy.types.Object] = []
    for px, py, pz, pr, ph in (
        (-0.38, 0.24, 0.68, 0.20, 0.15),  # snare
        (-0.20, 0.04, 0.98, 0.16, 0.16),  # rack tom L
        (0.20, 0.04, 0.98, 0.16, 0.16),   # rack tom R
        (0.46, 0.24, 0.56, 0.24, 0.34),   # floor tom
    ):
        bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=pr, depth=ph, location=(px, py, pz))
        kit_parts.append(bpy.context.active_object)
    drums_extra = _join_mesh_parts("DrumKit_Shells", kit_parts, obsidian_m, col, smooth=True)
    drums_extra.parent = kick_root

    stand_parts: list[bpy.types.Object] = []
    for sx, sy, sz in ((-0.68, 0.14, 0.62), (0.68, 0.14, 0.62)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.02, depth=1.24, location=(sx, sy, sz))
        stand_parts.append(bpy.context.active_object)
    stands = _join_mesh_parts("DrumKit_Stands", stand_parts, brass_m, col, smooth=True)
    stands.parent = kick_root

    cymbals = []
    for cname, cx, cy, cz, cr in (("Cymbal_L", -0.68, 0.14, 1.25, 0.34), ("Cymbal_R", 0.68, 0.14, 1.22, 0.38)):
        bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=cr, radius2=0.03, depth=0.04, location=(cx, cy, cz))
        cym = bpy.context.active_object
        cym.name = cname
        cym.data.materials.append(bright_gold_m)
        col.objects.link(cym)
        for c in list(cym.users_collection):
            if c != col:
                c.objects.unlink(cym)
        cym.parent = kick_root
        cymbals.append(cym)

    # DJ Vinyl Booth cleanly placed 0.85m forward in Rogue's facing direction
    dj_root = bpy.data.objects.new("DJBooth_Root", None)
    dj_root.location = (-1.85, -0.40, 0.0)
    dj_root.rotation_euler = (0.0, 0.0, math.radians(28.0))
    col.objects.link(dj_root)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.45))
    dj_ped = bpy.context.active_object
    dj_ped.scale = (1.15, 0.64, 0.90)
    dj_ped.name = "DJBooth_Body"
    dj_ped.data.materials.append(obsidian_m)
    col.objects.link(dj_ped)
    for c in list(dj_ped.users_collection):
        if c != col:
            c.objects.unlink(dj_ped)
    dj_ped.parent = dj_root

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, -0.33, 0.72))
    dj_strip = bpy.context.active_object
    dj_strip.scale = (1.06, 0.025, 0.07)
    dj_strip.name = "DJBooth_NeonStrip"
    dj_strip.data.materials.append(dj_neon_m)
    col.objects.link(dj_strip)
    for c in list(dj_strip.users_collection):
        if c != col:
            c.objects.unlink(dj_strip)
    dj_strip.parent = dj_root

    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.24, depth=0.035, location=(0.0, 0.0, 0.92))
    vinyl = bpy.context.active_object
    vinyl.name = "DJ_VinylPlatter"
    vinyl.data.materials.append(obsidian_m)
    col.objects.link(vinyl)
    for c in list(vinyl.users_collection):
        if c != col:
            c.objects.unlink(vinyl)
    vinyl.parent = dj_root

    # Eccentric golden marker dot on vinyl so scratches/spin are super readable visually!
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.05, depth=0.042, location=(0.14, 0.0, 0.92))
    v_mark = bpy.context.active_object
    v_mark.name = "DJ_VinylScratchCue"
    v_mark.data.materials.append(dj_neon_m)
    col.objects.link(v_mark)
    for c in list(v_mark.users_collection):
        if c != col:
            c.objects.unlink(v_mark)
    v_mark.parent = vinyl

    # 16 Semicircular FFT Neon Equalizer Bars (base fixed at z=0, pivot shifted to base!)
    eq_bars = []
    eq_bsdfs = []
    for i in range(16):
        frac = i / 15.0
        ang = math.radians(-68.0 + frac * 136.0)
        ex = 4.35 * math.sin(ang)
        ey = 0.25 + 3.45 * math.cos(ang)
        # Color sweep: Electric Cyan -> Emerald -> Warm Gold -> Hot Magenta
        if frac < 0.35:
            t = frac / 0.35
            rgb = (0.08 + 0.1 * t, 0.88 - 0.1 * t, 1.0 - 0.3 * t)
        elif frac < 0.7:
            t = (frac - 0.35) / 0.35
            rgb = (0.18 + 0.82 * t, 0.78 + 0.02 * t, 0.70 - 0.55 * t)
        else:
            t = (frac - 0.7) / 0.30
            rgb = (1.0, 0.80 - 0.58 * t, 0.15 + 0.55 * t)
        emat, ebsdf = _make_mat(
            f"Mat_EQ_{i:02d}",
            (*rgb, 1.0),
            roughness=0.25,
            emission_color=(*rgb, 1.0),
            emission_strength=1.8,
        )
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
        bar = bpy.context.active_object
        bm = bmesh.new()
        bm.from_mesh(bar.data)
        for v in bm.verts:
            v.co.z += 0.5
        bm.to_mesh(bar.data)
        bm.free()
        bar.location = (ex, ey, 0.0)
        bar.rotation_euler = (0.0, 0.0, -ang)
        bar.scale = (0.28, 0.16, 1.0)
        bar.name = f"NeonEQ_{i:02d}"
        bar.data.materials.append(emat)
        col.objects.link(bar)
        for c in list(bar.users_collection):
            if c != col:
                c.objects.unlink(bar)
        eq_bars.append(bar)
        eq_bsdfs.append(ebsdf)

    # 12 Overhead Crystalline Glockenspiel Prism Chimes
    chimes = []
    chime_bsdfs = []
    for ci in range(12):
        frac = ci / 11.0
        ang = math.radians(-56.0 + frac * 112.0)
        cx_c = 3.15 * math.sin(ang)
        cy_c = 0.45 + 2.35 * math.cos(ang)
        cz_c = 3.25 + 0.38 * math.sin(frac * math.pi)
        c_col = (0.55 + 0.4 * (ci % 2), 0.85, 1.0) if ci % 3 != 1 else (1.0, 0.82, 0.38)
        cmat, cbsdf = _make_mat(
            f"Mat_Chime_{ci:02d}",
            (*c_col, 1.0),
            metallic=0.35,
            roughness=0.12,
            emission_color=(*c_col, 1.0),
            emission_strength=0.6,
        )
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.14, location=(cx_c, cy_c, cz_c))
        ch = bpy.context.active_object
        ch.scale = (0.65, 0.65, 2.35)
        ch.name = f"CrystalChime_{ci:02d}"
        ch.data.materials.append(cmat)
        for poly in ch.data.polygons:
            poly.use_smooth = False
        col.objects.link(ch)
        for c in list(ch.users_collection):
            if c != col:
                c.objects.unlink(ch)
        chimes.append(ch)
        chime_bsdfs.append(cbsdf)

    # Overhead Mirror Disco Ball
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.50, location=(0.0, 0.45, 3.95))
    disco_ball = bpy.context.active_object
    disco_ball.name = "Stage_DiscoBall"
    disco_ball.data.materials.append(mirror_m)
    for poly in disco_ball.data.polygons:
        poly.use_smooth = False
    col.objects.link(disco_ball)
    for c in list(disco_ball.users_collection):
        if c != col:
            c.objects.unlink(disco_ball)

    # 36 Swirling Climax Music Sparks
    spark_mat, spark_bsdf = _make_mat("Mat_MusicSpark", (1.0, 0.85, 0.35, 1.0), emission_color=(1.0, 0.82, 0.28, 1.0), emission_strength=4.5)
    sparks = []
    for si in range(36):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.085, location=(0.0, 0.0, -2.0))
        sp = bpy.context.active_object
        sp.name = f"MusicSpark_{si:02d}"
        sp.data.materials.append(spark_mat)
        for poly in sp.data.polygons:
            poly.use_smooth = False
        col.objects.link(sp)
        for c in list(sp.users_collection):
            if c != col:
                c.objects.unlink(sp)
        sparks.append(sp)

    return {
        "gear_center": gear_center,
        "gear_left": gear_left,
        "gear_right": gear_right,
        "kick_head": kick_head,
        "drum_head_bsdf": drum_head_bsdf,
        "sax_glow_bsdf": sax_glow_bsdf,
        "dj_neon_bsdf": dj_neon_bsdf,
        "tip_bsdf": tip_bsdf,
        "cymbals": cymbals,
        "vinyl": vinyl,
        "eq_bars": eq_bars,
        "eq_bsdfs": eq_bsdfs,
        "chimes": chimes,
        "chime_bsdfs": chime_bsdfs,
        "disco_ball": disco_ball,
        "sparks": sparks,
        "spark_bsdf": spark_bsdf,
        "mats": {
            "gold": bright_gold_m,
            "brass": brass_m,
            "pearl": pearl_m,
            "sax_glow": sax_glow_m,
            "stick": stick_m,
            "tip": tip_m,
        },
    }


def _attach_custom_prop(arm: bpy.types.Object, bone_name: str, prop_root: bpy.types.Object, *, offset=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), scale=1.0) -> None:
    bone_len = arm.data.bones[bone_name].length
    prop_root.parent = arm
    prop_root.parent_type = "BONE"
    prop_root.parent_bone = bone_name
    prop_root.matrix_parent_inverse = Matrix.Translation((0.0, -bone_len, 0.0))
    prop_root.location = offset
    prop_root.rotation_mode = "XYZ"
    prop_root.rotation_euler = tuple(math.radians(a) for a in rot_deg)
    prop_root.scale = (scale, scale, scale)


def _kf_bone_rot(arm: bpy.types.Object, bone_name: str, deg_xyz: tuple[float, float, float], frame: int) -> None:
    pb = arm.pose.bones[bone_name]
    pb.rotation_euler = tuple(math.radians(a) for a in deg_xyz)
    pb.keyframe_insert(data_path="rotation_euler", frame=frame)


def _kf_bone_loc(arm: bpy.types.Object, bone_name: str, loc_xyz: tuple[float, float, float], frame: int) -> None:
    pb = arm.pose.bones[bone_name]
    pb.location = loc_xyz
    pb.keyframe_insert(data_path="location", frame=frame)


def _shot_camera_pose(f: int, bpm: float) -> tuple[tuple[float, float, float], tuple[float, float, float], float]:
    """Compute (cam_loc, target_loc, lens_mm) across 9 musically aligned editorial shots."""
    t = (f - 1) / 24.0
    beat_p = (t * bpm / 60.0) % 1.0
    kick_zoom = 1.8 * max(0.0, 1.0 - beat_p * 3.5)

    # Shot 1 (f 1..192, 0..8s): Curtain rise dolly + whip zoom to DJ scratch at 7..8s
    if f <= 165:
        u = (f - 1) / 164.0
        return ((-2.4 + 2.4 * u, -8.8 + 2.5 * u, 2.55 - 0.35 * u), (0.0, 0.55, 1.3), 38.0 + 4.0 * u)
    if f <= 192:
        u = (f - 166) / 26.0
        return ((-3.15 + 0.5 * math.sin(u * math.pi), -2.45 + 0.25 * u, 1.65), (-2.05, -0.05, 1.10), 40.0 + 6.0 * u)
    # Shot 2 (f 193..324, 8..13.5s): Groove Drop #1 wide crane sweep across entire band
    if f <= 324:
        u = (f - 193) / 131.0
        ang = math.radians(-26.0 + 52.0 * u)
        return ((7.2 * math.sin(ang), -7.2 * math.cos(ang), 2.75 - 0.45 * math.sin(u * math.pi)), (0.0, 0.55, 1.35), 35.0 + kick_zoom)
    # Shot 3 (f 325..396, 13.5..16.5s): Overhead Crystal Chimes tilt-up (325..360) -> Barbarian Snare Roll (361..396)
    if f <= 360:
        u = (f - 325) / 35.0
        return ((-2.2 + 4.4 * u, -5.2, 2.35), (0.0, 1.3, 2.75), 34.0)
    if f <= 396:
        u = (f - 361) / 35.0
        return ((-0.45 + 1.5 * u, -0.25, 2.45 - 0.1 * u), (0.40, 1.85, 1.72), 46.0 + 6.0 * u)
    # Shot 4 (f 397..672, 16.5..28s): Saxophone Solo orbit -> brief band cut (529..576) -> tight low sax hero
    if f <= 528:
        u = (f - 397) / 131.0
        ang = math.radians(-38.0 + 76.0 * u)
        return ((-0.35 + 3.05 * math.sin(ang), -0.58 - 2.95 * math.cos(ang), 1.48 + 0.22 * math.sin(u * math.pi)), (-0.35, -0.52, 1.25), 42.0)
    if f <= 576:
        u = (f - 529) / 47.0
        return ((2.2 - 4.4 * u, -6.8, 2.45), (0.0, 0.55, 1.30), 36.0 + kick_zoom)
    if f <= 672:
        u = (f - 577) / 95.0
        return ((-1.65 + 2.85 * u, -3.15, 1.05 + 0.45 * u), (-0.35, -0.52, 1.22), 44.0 - 4.0 * u)
    # Shot 5 (f 673..756, 28..31.5s): Stutter Vinyl Scratch close-up on Rogue
    if f <= 756:
        u = (f - 673) / 83.0
        return ((-3.35 + 0.75 * u, -2.55 - 0.25 * math.sin(u * 4 * math.pi), 1.65 + 0.12 * math.cos(u * 6 * math.pi)), (-2.05, -0.05, 1.12), 38.0 + 5.0 * abs(math.sin(u * 3 * math.pi)))
    # Shot 6 (f 757..948, 31.5..39.5s): Midnight Clockwork Dream - sapphire fairy-gold floating crane
    if f <= 948:
        u = (f - 757) / 191.0
        return ((-2.9 + 5.8 * u, -6.4 + 1.2 * math.sin(u * math.pi), 2.85 + 0.45 * math.cos(u * math.pi)), (0.0, 0.95, 1.55), 32.0)
    # Shot 7 (f 949..1116, 39.5..46.5s): Virtuoso Sax (949..1020) + Knight Brass/Barbarian Fanfare (1021..1116)
    if f <= 1020:
        u = (f - 949) / 71.0
        return ((1.55 - 3.4 * u, -3.1, 1.35), (-0.35, -0.52, 1.25), 44.0)
    if f <= 1116:
        u = (f - 1021) / 95.0
        return ((3.45 - 2.1 * u, -4.15 - 1.1 * u, 1.72 + 0.45 * u), (1.15 - 0.6 * u, 0.95, 1.35), 40.0 + kick_zoom)
    # Shot 8 (f 1117..1260, 46.5..52.5s): Disco Climax Explosion - dramatic beat-synced ensemble orbit
    if f <= 1260:
        u = (f - 1117) / 143.0
        ang = math.radians(-30.0 + 60.0 * u)
        rad = 7.3 - 1.0 * math.sin(u * math.pi)
        return ((rad * math.sin(ang), 0.1 - rad * math.cos(ang), 2.15 + 1.05 * math.sin(u * math.pi)), (0.0, 0.55, 1.50), 34.0 + 2.4 * kick_zoom)
    # Shot 9 (f 1261..1386, 52.5..57.73s): Music-Box Finale gentle twilight rise & fade out
    u = (f - 1261) / max(1, 1386 - 1261)
    return ((0.0, -6.5 - 2.2 * u, 1.95 + 1.9 * u), (0.0, 0.55, 1.35 + 0.35 * u), 38.0 - 4.0 * u)


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

    stage_col = bpy.data.collections.new("Clockwork_Stage")
    scene.collection.children.link(stage_col)
    stage = _build_stage_and_instruments(stage_col, total_frames)

    # Import verified KayKit Rig_Medium band members cleanly
    cast_specs = {
        "mage": (spec["cast"]["mage"], (-0.35, -0.58, 0.0), 0.0, 0.0),
        "barbarian": (spec["cast"]["barbarian"], (0.40, 2.05, 0.65), 0.0, 0.65),
        "rogue": (spec["cast"]["rogue"], (-2.30, 0.25, 0.0), 28.0, 0.0),
        "knight": (spec["cast"]["knight"], (1.95, 0.22, 0.0), -25.0, 0.0),
    }
    arms: dict[str, bpy.types.Object] = {}
    char_objs_all: list[bpy.types.Object] = []
    for cname, (glb_path, loc, yaw_deg, floor_z) in cast_specs.items():
        ccol, root_e, arm, objs = _import_glb_clean(glb_path, f"Band_{cname.title()}", f"Root_{cname.title()}")
        root_e.location = loc
        root_e.rotation_mode = "XYZ"
        root_e.rotation_euler = (0.0, 0.0, math.radians(yaw_deg))
        bpy.context.view_layer.update()
        min_z = _eval_min_z(objs)
        root_e.location.z += (floor_z - min_z)
        bpy.context.view_layer.update()
        arms[cname] = arm
        char_objs_all.extend(objs)

    # Attach procedural custom instruments via native bone parenting!
    sax_root, sax_rings = _build_saxophone(stage_col, stage["mats"]["gold"], stage["mats"]["pearl"], stage["mats"]["sax_glow"])
    _attach_custom_prop(arms["mage"], "handslot.r", sax_root, rot_deg=(12.0, 16.0, -45.0), scale=1.22)

    stick_r = _build_drumstick("DrumStick_R", stage_col, stage["mats"]["stick"], stage["mats"]["tip"])
    stick_l = _build_drumstick("DrumStick_L", stage_col, stage["mats"]["stick"], stage["mats"]["tip"])
    _attach_custom_prop(arms["barbarian"], "handslot.r", stick_r)
    _attach_custom_prop(arms["barbarian"], "handslot.l", stick_l)

    horn_root = _build_trumpet(stage_col, stage["mats"]["gold"], stage["mats"]["pearl"])
    _attach_custom_prop(arms["knight"], "handslot.r", horn_root, rot_deg=(0.0, 0.0, 0.0), scale=1.0)

    # World & 4 Animated Concert Lights
    world = bpy.data.worlds.new("Clockwork_World")
    scene.world = world
    world.use_nodes = True
    wbg = world.node_tree.nodes.get("Background")
    wbg.inputs["Color"].default_value = (0.012, 0.016, 0.036, 1.0)
    wbg.inputs["Strength"].default_value = 0.65

    lights: dict[str, bpy.types.Object] = {}
    for lname, ltype, loc, spot_deg in (
        ("KeyLight_Warm", "AREA", (0.0, -5.5, 4.4), None),
        ("SideRim_Cyan", "AREA", (-4.8, 0.2, 3.2), None),
        ("SideRim_Magenta", "AREA", (4.8, 0.2, 3.2), None),
        ("HeroSpot", "SPOT", (0.0, -2.0, 6.2), 54.0),
    ):
        ld = bpy.data.lights.new(lname, type=ltype)
        if ltype == "AREA":
            ld.size = 3.2
        elif spot_deg is not None:
            ld.spot_size = math.radians(spot_deg)
            ld.spot_blend = 0.45
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0.0, 0.6, 1.2)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        stage_col.objects.link(lo)
        lights[lname] = lo

    # Tracked Editorial Camera
    cam_target = bpy.data.objects.new("Camera_Target", None)
    cam_target.location = (0.0, 0.4, 1.1)
    stage_col.objects.link(cam_target)

    cam_data = bpy.data.cameras.new("Director_Camera")
    cam_data.clip_start = 0.05
    cam_data.clip_end = 150.0
    cam_obj = bpy.data.objects.new("Director_Camera", cam_data)
    stage_col.objects.link(cam_obj)
    tr = cam_obj.constraints.new(type="TRACK_TO")
    tr.target = cam_target
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    scene.camera = cam_obj

    # Animate Character Choreography (every 3 frames + exact section/cut boundaries)
    cut_frames = {1, 165, 166, 192, 193, 324, 325, 360, 361, 396, 397, 528, 529, 576, 577, 672, 673, 756, 757, 948, 949, 1020, 1021, 1116, 1117, 1260, 1261, total_frames}
    pose_frames = sorted(set(range(1, total_frames + 1, 3)) | cut_frames)
    for f in pose_frames:
        fd = frames_data[min(len(frames_data) - 1, f - 1)]
        t = fd["t"]
        bass = fd["bass"]
        mid = fd["mid"]
        high = fd["high"]
        rms = fd["rms"]
        beat = (t * bpm / 60.0)
        beat_s = math.sin(beat * math.pi)          # 1-beat bounce
        beat_half = math.sin(beat * math.pi * 0.5) # left/right sway

        # ---- MAGE (Saxophone Maestro -> Dream Conductor -> Finale Bow) ----
        arm_m = arms["mage"]
        b_crouch = 0.25 + 0.45 * abs(beat_s) * (0.4 + 0.6 * bass)
        if 757 <= f <= 948:
            # Clockwork Dream conducting
            cond = math.sin(t * 2.4)
            _kf_bone_loc(arm_m, "hips", (0.0, -0.03 * b_crouch, 0.0), f)
            _kf_bone_rot(arm_m, "spine", (6.0, 0.0, 5.0 * math.sin(t * 1.4)), f)
            _kf_bone_rot(arm_m, "chest", (4.0, 10.0 * cond, 6.0 * math.sin(t * 1.4)), f)
            _kf_bone_rot(arm_m, "head", (6.0 + 4.0 * abs(cond), 0.0, -4.0 * cond), f)
            _kf_bone_rot(arm_m, "upperarm.r", (-66.0, 0.0, 16.0), f)
            _kf_bone_rot(arm_m, "lowerarm.r", (0.0, 0.0, 28.0), f)
            _kf_bone_rot(arm_m, "upperarm.l", (-10.0 + 22.0 * cond, 0.0, -48.0 - 18.0 * math.cos(t * 2.4)), f)
            _kf_bone_rot(arm_m, "lowerarm.l", (0.0, 0.0, -35.0 + 20.0 * cond), f)
            _kf_bone_rot(arm_m, "upperleg.r", (-14.0 * b_crouch, 0.0, 0.0), f)
            _kf_bone_rot(arm_m, "lowerleg.r", (28.0 * b_crouch, 0.0, 0.0), f)
            _kf_bone_rot(arm_m, "foot.r", (-14.0 * b_crouch, 0.0, 0.0), f)
            _kf_bone_rot(arm_m, "upperleg.l", (-14.0 * b_crouch, 0.0, 0.0), f)
            _kf_bone_rot(arm_m, "lowerleg.l", (28.0 * b_crouch, 0.0, 0.0), f)
            _kf_bone_rot(arm_m, "foot.l", (-14.0 * b_crouch, 0.0, 0.0), f)
        elif f >= 1261:
            # Music-Box Finale serene bow (head lifted gently so Mage's eyes remain visible!)
            bow_u = min(1.0, (f - 1261) / 72.0)
            bow_amt = 14.0 * math.sin(bow_u * math.pi * 0.85)
            _kf_bone_loc(arm_m, "hips", (0.0, -0.02, 0.0), f)
            _kf_bone_rot(arm_m, "spine", (bow_amt, 0.0, 0.0), f)
            _kf_bone_rot(arm_m, "chest", (bow_amt * 0.5, 0.0, 0.0), f)
            _kf_bone_rot(arm_m, "head", (-10.0 * bow_u, 0.0, 0.0), f)
            _kf_bone_rot(arm_m, "upperarm.r", (-66.0, 0.0, 14.0), f)
            _kf_bone_rot(arm_m, "lowerarm.r", (0.0, 0.0, 22.0), f)
            _kf_bone_rot(arm_m, "upperarm.l", (-62.0, 0.0, -18.0 - 25.0 * bow_u), f)
            _kf_bone_rot(arm_m, "lowerarm.l", (0.0, 0.0, -28.0), f)
            for side in ("r", "l"):
                _kf_bone_rot(arm_m, f"upperleg.{side}", (-6.0, 0.0, 0.0), f)
                _kf_bone_rot(arm_m, f"lowerleg.{side}", (12.0, 0.0, 0.0), f)
                _kf_bone_rot(arm_m, f"foot.{side}", (-6.0, 0.0, 0.0), f)
        else:
            # Saxophone Groove & Spotlight Swagger
            is_solo = (397 <= f <= 672) or (949 <= f <= 1020) or (1117 <= f <= 1260)
            swagger = 16.0 if is_solo else 9.0
            lean_back = -12.0 * mid if is_solo else -4.0 * mid
            _kf_bone_loc(arm_m, "hips", (0.0, -0.065 * b_crouch, 0.0), f)
            _kf_bone_rot(arm_m, "spine", (lean_back, swagger * beat_half, 8.0 * beat_half), f)
            _kf_bone_rot(arm_m, "chest", (lean_back * 0.6, 8.0 * beat_half, 6.0 * beat_half), f)
            _kf_bone_rot(arm_m, "head", (6.0 + 8.0 * abs(beat_s), 5.0 * beat_half, -6.0 * beat_half), f)
            _kf_bone_rot(arm_m, "upperarm.r", (-40.0 + 6.0 * beat_s, 0.0, 56.0), f)
            _kf_bone_rot(arm_m, "lowerarm.r", (0.0, 0.0, 74.0 + 6.0 * mid), f)
            _kf_bone_rot(arm_m, "upperarm.l", (-42.0 - 6.0 * beat_s, 0.0, -50.0), f)
            _kf_bone_rot(arm_m, "lowerarm.l", (0.0, 0.0, -66.0 - 6.0 * mid), f)
            for side in ("r", "l"):
                _kf_bone_rot(arm_m, f"upperleg.{side}", (-20.0 * b_crouch, 0.0, 0.0), f)
                _kf_bone_rot(arm_m, f"lowerleg.{side}", (40.0 * b_crouch, 0.0, 0.0), f)
                _kf_bone_rot(arm_m, f"foot.{side}", (-20.0 * b_crouch, 0.0, 0.0), f)

        # ---- BARBARIAN (Drummer behind Art-Deco Kit) ----
        arm_b = arms["barbarian"]
        if 757 <= f <= 948 or f >= 1261:
            # Soft brushwork / rest pose in bridge & finale
            gentle = math.sin(t * 3.0)
            _kf_bone_loc(arm_b, "hips", (0.0, -0.02, 0.0), f)
            _kf_bone_rot(arm_b, "spine", (6.0, 0.0, 0.0), f)
            _kf_bone_rot(arm_b, "head", (4.0 * gentle, 0.0, 0.0), f)
            _kf_bone_rot(arm_b, "upperarm.r", (-48.0 + 6.0 * gentle, 0.0, 42.0), f)
            _kf_bone_rot(arm_b, "lowerarm.r", (0.0, 0.0, 54.0), f)
            _kf_bone_rot(arm_b, "upperarm.l", (-48.0 - 6.0 * gentle, 0.0, -42.0), f)
            _kf_bone_rot(arm_b, "lowerarm.l", (0.0, 0.0, -54.0), f)
        else:
            roll = 2.0 if (360 <= f <= 396 or 1117 <= f <= 1260) else 1.0
            hit_r = math.sin(beat * math.pi * roll)
            hit_l = -hit_r
            _kf_bone_loc(arm_b, "hips", (0.0, -0.04 * abs(beat_s), 0.0), f)
            _kf_bone_rot(arm_b, "spine", (8.0 + 5.0 * bass, 10.0 * hit_r, 0.0), f)
            _kf_bone_rot(arm_b, "head", (12.0 * abs(beat_s), 0.0, 6.0 * beat_half), f)
            _kf_bone_rot(arm_b, "upperarm.r", (-34.0 + 26.0 * max(0.0, hit_r), 0.0, 48.0), f)
            _kf_bone_rot(arm_b, "lowerarm.r", (0.0, 0.0, 60.0 + 18.0 * hit_r), f)
            _kf_bone_rot(arm_b, "upperarm.l", (-34.0 + 26.0 * max(0.0, hit_l), 0.0, -48.0), f)
            _kf_bone_rot(arm_b, "lowerarm.l", (0.0, 0.0, -60.0 - 18.0 * hit_l), f)

        # ---- ROGUE (Turntablist DJ) ----
        arm_r = arms["rogue"]
        is_scratch = (165 <= f <= 192) or (673 <= f <= 756)
        scratch_wiggle = 36.0 * math.sin(t * 22.0) if is_scratch else 10.0 * math.sin(beat * math.pi)
        dj_bounce = 0.25 + 0.55 * abs(beat_s)
        _kf_bone_loc(arm_r, "hips", (0.0, -0.05 * dj_bounce, 0.0), f)
        _kf_bone_rot(arm_r, "spine", (14.0 if is_scratch else 8.0, 8.0 * beat_half, 0.0), f)
        _kf_bone_rot(arm_r, "head", (10.0 * abs(beat_s), 0.0, 8.0 * beat_half), f)
        _kf_bone_rot(arm_r, "upperarm.r", (-42.0, 0.0, 56.0 + scratch_wiggle * 0.4), f)
        _kf_bone_rot(arm_r, "lowerarm.r", (0.0, 0.0, 58.0 + scratch_wiggle * 0.5), f)
        _kf_bone_rot(arm_r, "upperarm.l", (-25.0 + 35.0 * (1.0 if is_scratch else rms), 0.0, -28.0), f)
        _kf_bone_rot(arm_r, "lowerarm.l", (0.0, 0.0, -45.0), f)
        for side in ("r", "l"):
            _kf_bone_rot(arm_r, f"upperleg.{side}", (-16.0 * dj_bounce, 0.0, 0.0), f)
            _kf_bone_rot(arm_r, f"lowerleg.{side}", (32.0 * dj_bounce, 0.0, 0.0), f)
            _kf_bone_rot(arm_r, f"foot.{side}", (-16.0 * dj_bounce, 0.0, 0.0), f)

        # ---- KNIGHT (Brass Horn & Swing Dancer) ----
        arm_k = arms["knight"]
        is_horn_play = (18 <= f <= 165) or (1021 <= f <= 1260)
        jump_z = 0.32 * math.sin((f - 1170) / 28.0 * math.pi) if 1170 <= f <= 1198 else 0.0
        kb = 0.2 + 0.6 * abs(beat_s)
        _kf_bone_loc(arm_k, "hips", (0.0, -0.065 * kb + jump_z, 0.0), f)
        _kf_bone_rot(arm_k, "spine", (-6.0 * mid if is_horn_play else 4.0, -10.0 * beat_half, -6.0 * beat_half), f)
        _kf_bone_rot(arm_k, "head", (-5.0 + 8.0 * abs(beat_s), 0.0, -6.0 * beat_half), f)
        if is_horn_play:
            _kf_bone_rot(arm_k, "upperarm.r", (-28.0, 0.0, 58.0), f)
            _kf_bone_rot(arm_k, "lowerarm.r", (0.0, 0.0, 78.0), f)
        else:
            _kf_bone_rot(arm_k, "upperarm.r", (-58.0 + 18.0 * beat_s, 0.0, 18.0), f)
            _kf_bone_rot(arm_k, "lowerarm.r", (0.0, 0.0, 34.0), f)
        _kf_bone_rot(arm_k, "upperarm.l", (-48.0 + 36.0 * rms * beat_s, 0.0, -24.0 - 15.0 * abs(beat_half)), f)
        _kf_bone_rot(arm_k, "lowerarm.l", (0.0, 0.0, -40.0), f)
        for side in ("r", "l"):
            _kf_bone_rot(arm_k, f"upperleg.{side}", (-20.0 * kb, 0.0, 0.0), f)
            _kf_bone_rot(arm_k, f"lowerleg.{side}", (40.0 * kb, 0.0, 0.0), f)
            _kf_bone_rot(arm_k, f"foot.{side}", (-20.0 * kb, 0.0, 0.0), f)

    # Animate Stage Elements, 16-Band FFT Equalizer, Chimes, Sax Rings, Disco Ball, Sparks & Lights (every 2 frames)
    stage_frames = sorted(set(range(1, total_frames + 1, 2)) | cut_frames)
    for f in stage_frames:
        fd = frames_data[min(len(frames_data) - 1, f - 1)]
        t = fd["t"]
        bass = fd["bass"]
        mid = fd["mid"]
        high = fd["high"]
        rms = fd["rms"]
        b16 = fd["b16"]

        # 1. Exposure Fade-In (1..18) & Fade-Out (1345..1386)
        if f <= 18:
            exp_val = -7.5 * (1.0 - (f - 1) / 17.0)
        elif f >= 1345:
            exp_val = -8.0 * ((f - 1345) / max(1, total_frames - 1345))
        else:
            exp_val = 0.0
        scene.view_settings.exposure = exp_val
        scene.view_settings.keyframe_insert(data_path="exposure", frame=f)

        # 2. Clockwork Gears rotating smoothly with beat steps
        ang_c = t * 0.45 + 0.08 * math.sin(t * bpm / 60.0 * math.pi * 2.0)
        stage["gear_center"].rotation_euler.y = ang_c
        stage["gear_center"].keyframe_insert(data_path="rotation_euler", frame=f)
        stage["gear_left"].rotation_euler.y = -ang_c * (16.0 / 12.0)
        stage["gear_left"].keyframe_insert(data_path="rotation_euler", frame=f)
        stage["gear_right"].rotation_euler.y = -ang_c * (16.0 / 12.0)
        stage["gear_right"].keyframe_insert(data_path="rotation_euler", frame=f)

        # 3. Kick Drum Pulse, Cymbal Wobble & Vinyl Spin/Scratch
        k_s = 1.0 + 0.14 * bass
        stage["kick_head"].scale = (k_s, k_s, 1.0 + 0.45 * bass)
        stage["kick_head"].keyframe_insert(data_path="scale", frame=f)
        stage["drum_head_bsdf"].inputs["Emission Strength"].default_value = 0.8 + 4.5 * bass
        stage["drum_head_bsdf"].inputs["Emission Strength"].keyframe_insert(data_path="default_value", frame=f)

        for ci, cym in enumerate(stage["cymbals"]):
            wob = math.radians((6.0 if ci == 0 else -5.0) * high * math.sin(t * 14.0))
            cym.rotation_euler = (wob, wob * 0.7, 0.0)
            cym.keyframe_insert(data_path="rotation_euler", frame=f)

        is_scratch = (165 <= f <= 192) or (673 <= f <= 756)
        v_rot = t * 3.5 + (1.8 * math.sin(t * 20.0) if is_scratch else 0.0)
        stage["vinyl"].rotation_euler.z = v_rot
        stage["vinyl"].keyframe_insert(data_path="rotation_euler", frame=f)
        stage["dj_neon_bsdf"].inputs["Emission Strength"].default_value = (12.0 if is_scratch else 2.2) + 4.0 * bass
        stage["dj_neon_bsdf"].inputs["Emission Strength"].keyframe_insert(data_path="default_value", frame=f)

        # 4. Saxophone Sound-Wave Rings pulsing during solo moments
        sax_active = 1.0 if ((18 <= f <= 324) or (397 <= f <= 672) or (949 <= f <= 1260)) else 0.08
        for ri, ring in enumerate(sax_rings):
            sc = sax_active * (0.7 + 0.9 * mid + 0.3 * math.sin(t * 10.0 - ri * 1.1))
            ring.scale = (sc, sc, sc)
            ring.keyframe_insert(data_path="scale", frame=f)
        stage["sax_glow_bsdf"].inputs["Emission Strength"].default_value = sax_active * (1.5 + 8.5 * mid)
        stage["sax_glow_bsdf"].inputs["Emission Strength"].keyframe_insert(data_path="default_value", frame=f)

        # 5. 16-Column Neon Equalizer Wall driven directly by b16[0..15]
        for bi in range(16):
            bar = stage["eq_bars"][bi]
            val = b16[bi]
            bar.scale.z = 0.28 + 3.4 * val
            bar.keyframe_insert(data_path="scale", frame=f)
            stage["eq_bsdfs"][bi].inputs["Emission Strength"].default_value = 0.5 + 5.8 * val
            stage["eq_bsdfs"][bi].inputs["Emission Strength"].keyframe_insert(data_path="default_value", frame=f)

        # 6. Overhead Crystal Chimes ripple from high FFT band
        is_chime_chapter = (325 <= f <= 360) or (757 <= f <= 948) or (f >= 1261)
        chime_boost = 1.8 if is_chime_chapter else 0.85
        for ci, ch in enumerate(stage["chimes"]):
            wave = 0.5 + 0.5 * math.sin(t * 4.5 - ci * 0.55)
            ch.location.z = 2.85 + 0.35 * math.sin((ci / 11.0) * math.pi) + 0.14 * math.sin(t * 2.2 + ci)
            ch.rotation_euler.z = t * 0.8 + ci
            ch.keyframe_insert(data_path="location", frame=f)
            ch.keyframe_insert(data_path="rotation_euler", frame=f)
            stage["chime_bsdfs"][ci].inputs["Emission Strength"].default_value = chime_boost * (0.6 + 6.5 * high * wave)
            stage["chime_bsdfs"][ci].inputs["Emission Strength"].keyframe_insert(data_path="default_value", frame=f)

        # 7. Mirror Disco Ball & Swirling Climax Sparkles
        db_z = 2.85 if (1117 <= f <= 1260) else 3.95
        stage["disco_ball"].location.z = db_z + 0.12 * bass
        stage["disco_ball"].rotation_euler.z = t * 1.4
        stage["disco_ball"].keyframe_insert(data_path="location", frame=f)
        stage["disco_ball"].keyframe_insert(data_path="rotation_euler", frame=f)

        spark_amt = 1.0 if (1117 <= f <= 1260) else (0.55 if (397 <= f <= 672) or (757 <= f <= 948) else 0.0)
        for si, sp in enumerate(stage["sparks"]):
            ang_s = t * (0.9 + 0.03 * si) + si * 0.7
            rad_s = 2.1 + 1.8 * math.sin(si * 1.3 + t * 0.5)
            sp.location = (rad_s * math.cos(ang_s), 0.35 + rad_s * math.sin(ang_s) * 0.75, 0.4 + ((t * 0.7 + si * 0.19) % 3.4))
            sc_sp = spark_amt * (0.4 + 0.85 * rms)
            sp.scale = (sc_sp, sc_sp, sc_sp)
            sp.keyframe_insert(data_path="location", frame=f)
            sp.keyframe_insert(data_path="scale", frame=f)
        stage["spark_bsdf"].inputs["Emission Strength"].default_value = 2.0 + 5.0 * rms
        stage["spark_bsdf"].inputs["Emission Strength"].keyframe_insert(data_path="default_value", frame=f)

        # 8. Chapter-Shifting Stage Lights
        if 757 <= f <= 948:
            # Clockwork Dream: deep sapphire + fairy amber
            key_c, rim_l_c, rim_r_c = (0.55, 0.74, 1.0), (0.18, 0.42, 1.0), (1.0, 0.72, 0.25)
            key_e = 420.0 + 180.0 * rms
            spot_e = 650.0 + 300.0 * high
        elif f >= 1261:
            # Finale Twilight: warm amber glow
            key_c, rim_l_c, rim_r_c = (1.0, 0.80, 0.52), (0.45, 0.68, 1.0), (1.0, 0.62, 0.25)
            key_e = 380.0
            spot_e = 550.0
        else:
            # Electro-Swing Concert: warm gold key + electric cyan + hot magenta rims
            key_c, rim_l_c, rim_r_c = (1.0, 0.90, 0.74), (0.12, 0.85, 1.0), (1.0, 0.22, 0.68)
            key_e = 560.0 + 260.0 * rms
            spot_e = 780.0 + 520.0 * bass

        for lname, lcol, lenergy in (
            ("KeyLight_Warm", key_c, key_e),
            ("SideRim_Cyan", rim_l_c, 280.0 + 240.0 * high),
            ("SideRim_Magenta", rim_r_c, 260.0 + 260.0 * bass),
            ("HeroSpot", key_c, spot_e),
        ):
            ld = lights[lname].data
            ld.color = lcol
            ld.energy = lenergy
            ld.keyframe_insert(data_path="color", frame=f)
            ld.keyframe_insert(data_path="energy", frame=f)

    # Animate Tracked Camera across 9 Musical Cuts with crisp CONSTANT holds at boundaries
    cut_starts = {1, 166, 193, 325, 361, 397, 529, 577, 673, 757, 949, 1021, 1117, 1261}
    cut_ends = {cs - 1 for cs in cut_starts if cs > 1}
    cam_frames = sorted(set(range(1, total_frames + 1, 3)) | cut_starts | cut_ends | {total_frames})
    for f in cam_frames:
        cloc, tloc, lens = _shot_camera_pose(f, bpm)
        cam_obj.location = cloc
        cam_target.location = tloc
        cam_data.lens = lens
        cam_obj.keyframe_insert(data_path="location", frame=f)
        cam_target.keyframe_insert(data_path="location", frame=f)
        cam_data.keyframe_insert(data_path="lens", frame=f)

    for obj_anim in (cam_obj, cam_target, cam_data):
        if obj_anim.animation_data and obj_anim.animation_data.action:
            act = obj_anim.animation_data.action
            for fc in _iter_action_fcurves(act):
                for kp in fc.keyframe_points:
                    if int(round(kp.co.x)) in cut_ends:
                        kp.interpolation = "CONSTANT"

    # Configure EEVEE + AgX + Compositor Bloom Glare (Blender 5.2)
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

    ng = bpy.data.node_groups.new("ClockworkCompositor", "CompositorNodeTree")
    if hasattr(ng, "interface"):
        ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")
    glare = ng.nodes.new("CompositorNodeGlare")
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Quality"].default_value = "High"
    glare.inputs["Threshold"].default_value = 1.15
    glare.inputs["Strength"].default_value = 0.35
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
        "characters": {k: {"armature": v.name, "bones": len(v.data.bones)} for k, v in arms.items()},
        "mesh_count": sum(1 for o in bpy.data.objects if o.type == "MESH"),
    }


def _iter_action_fcurves(act: Any) -> list[Any]:
    """Yield FCurves cleanly in Blender 4.4–5.2 Action Slots or legacy Actions."""
    if hasattr(act, "fcurves"):
        return list(act.fcurves)
    out = []
    for layer in getattr(act, "layers", []):
        for strip in getattr(layer, "strips", []):
            for cb in getattr(strip, "channelbags", []):
                out.extend(getattr(cb, "fcurves", []))
    return out


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1 :]
    spec_data = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    summary = build_music_video_scene(spec_data)
    print("MUSIC_VIDEO_BUILD_JSON:" + json.dumps(summary))
