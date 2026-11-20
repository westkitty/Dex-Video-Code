#!/usr/bin/env python3
"""5-World Beat-Locked Explosive Music Video Blender 5.2+ Scene Builder:
"The Midnight Saxophone Heist" (r3 Uplift)

Builds 5 isolated 60m-separated 3D worlds toggled cleanly with hide_render and
CONSTANT Act cuts locked to sub-frame BPM (129.14 BPM, beat0=0.2033s) and
real PCM/FFT transient impacts:
  - Set 1 (-60,  0, 0): Royal Emerald Museum Vault (f 1..228 + Epilogue f 1288..end)
  - Set 2 (+60,  0, 0): Moonlit Neon Rooftop Chase & Chasm Leap (f 229..407)
  - Set 3 (  0,-60, 0): Underground Neon Speakeasy & Weapon Morph (f 408..764)
  - Set 4 (  0,+60, 0): Enchanted Clockwork Astral Cosmos & Supernova (f 765..986)
  - Set 5 (  0,  0, 0): Grand Clockwork Ballroom Pyrotechnic Finale (f 987..1287)
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


# Default Set active frame intervals (clamped dynamically to total_frames in build_music_video_scene)
SET_INTERVALS: dict[str, list[tuple[int, int]]] = {
    "set1": [(1, 228), (1288, 1386)],
    "set2": [(229, 407)],
    "set3": [(408, 764)],
    "set4": [(765, 986)],
    "set5": [(987, 1287)],
}

# Verified PCM/FFT explosive impact frames -> (flash_ev, shake_amp, chroma_disp)
# Tuned under AgX so bursts stay vivid electric cyan/gold/magenta without white-out blowout
EXPLOSIVE_HITS: dict[int, tuple[float, float, float]] = {
    39: (0.22, 0.05, 0.008),
    112: (0.22, 0.05, 0.008),
    123: (0.24, 0.06, 0.010),
    140: (0.30, 0.08, 0.012),
    179: (0.52, 0.22, 0.026),
    218: (0.28, 0.10, 0.014),
    229: (0.42, 0.18, 0.020),
    246: (0.42, 0.18, 0.022),
    285: (0.28, 0.10, 0.012),
    319: (0.36, 0.14, 0.016),
    363: (0.48, 0.22, 0.024),
    375: (0.36, 0.15, 0.018),
    408: (0.46, 0.24, 0.026),
    469: (0.48, 0.25, 0.028),
    530: (0.26, 0.10, 0.012),
    558: (0.26, 0.10, 0.012),
    631: (0.32, 0.12, 0.014),
    692: (0.45, 0.20, 0.025),
    748: (0.48, 0.24, 0.026),
    765: (0.38, 0.16, 0.018),
    809: (0.50, 0.24, 0.028),
    898: (0.30, 0.11, 0.014),
    915: (0.34, 0.13, 0.016),
    987: (0.48, 0.22, 0.026),
    1015: (0.30, 0.12, 0.014),
    1043: (0.34, 0.14, 0.018),
    1077: (0.32, 0.12, 0.016),
    1121: (0.48, 0.24, 0.026),
    1133: (0.42, 0.18, 0.020),
    1174: (0.38, 0.16, 0.018),
    1210: (0.55, 0.28, 0.030),
    1249: (0.40, 0.18, 0.020),
    1260: (0.45, 0.22, 0.024),
    1288: (0.25, 0.04, 0.008),
}

CUT_STARTS: set[int] = {
    1, 39, 112, 140, 179, 195,
    229, 246, 285, 319, 363, 385,
    408, 469, 530, 586, 631, 692, 726,
    765, 809, 898,
    987, 1015, 1043, 1077, 1121, 1166, 1210, 1261,
    1288,
}


def _compute_set_intervals(total_frames: int) -> dict[str, list[tuple[int, int]]]:
    s1_b = min(228, total_frames)
    raw = {
        "set1": [(1, s1_b)] + ([(1288, total_frames)] if total_frames >= 1288 else []),
        "set2": [(229, min(407, total_frames))] if total_frames >= 229 else [],
        "set3": [(408, min(764, total_frames))] if total_frames >= 408 else [],
        "set4": [(765, min(986, total_frames))] if total_frames >= 765 else [],
        "set5": [(987, min(1287, total_frames))] if total_frames >= 987 else [],
    }
    return raw


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


def _set_constant_at_frames(obj: Any, data_path: str, frames_to_const: set[int]) -> None:
    if not frames_to_const or not getattr(obj, "animation_data", None) or not obj.animation_data.action:
        return
    for fc in _iter_action_fcurves(obj.animation_data.action):
        if fc.data_path == data_path or data_path == "*":
            for kp in fc.keyframe_points:
                if int(round(kp.co.x)) in frames_to_const:
                    kp.interpolation = "CONSTANT"


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


def _make_beam_mat(
    name: str,
    color_rgb: tuple[float, float, float],
    *,
    strength: float = 1.6,
    max_alpha: float = 0.09,
) -> tuple[bpy.types.Material, bpy.types.Node]:
    """Soft volumetric-style blended light cone material compatible with EEVEE 5.2."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "BLENDED"
    if hasattr(mat, "use_backface_culling"):
        mat.use_backface_culling = False
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    mix = nt.nodes.new("ShaderNodeMixShader")
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color_rgb, 1.0)
    em.inputs["Strength"].default_value = float(strength)

    tex = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    pow_z = nt.nodes.new("ShaderNodeMath")
    pow_z.operation = "POWER"
    pow_z.use_clamp = True
    pow_z.inputs[1].default_value = 1.85

    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    inv_f = nt.nodes.new("ShaderNodeMath")
    inv_f.operation = "SUBTRACT"
    inv_f.use_clamp = True
    inv_f.inputs[0].default_value = 1.0
    pow_f = nt.nodes.new("ShaderNodeMath")
    pow_f.operation = "POWER"
    pow_f.use_clamp = True
    pow_f.inputs[1].default_value = 3.2

    mul_zf = nt.nodes.new("ShaderNodeMath")
    mul_zf.operation = "MULTIPLY"
    mul_a = nt.nodes.new("ShaderNodeMath")
    mul_a.operation = "MULTIPLY"
    mul_a.use_clamp = True
    mul_a.inputs[1].default_value = float(max_alpha)

    nt.links.new(tex.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Z"], pow_z.inputs[0])
    nt.links.new(lw.outputs["Facing"], inv_f.inputs[1])
    nt.links.new(inv_f.outputs["Value"], pow_f.inputs[0])
    nt.links.new(pow_z.outputs["Value"], mul_zf.inputs[0])
    nt.links.new(pow_f.outputs["Value"], mul_zf.inputs[1])
    nt.links.new(mul_zf.outputs["Value"], mul_a.inputs[0])
    nt.links.new(mul_a.outputs["Value"], mix.inputs["Fac"])
    nt.links.new(transp.outputs["BSDF"], mix.inputs[1])
    nt.links.new(em.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat, em


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


def _create_shared_vfx_meshes() -> dict[str, bpy.types.Mesh]:
    """Create shared lightweight bmesh VFX geometry once for fast particle/blast spawning."""
    meshes: dict[str, bpy.types.Mesh] = {}

    # 1. Unit open-ended cone (apex z=0.0, wide base z=-1.0)
    cone_m = bpy.data.meshes.new("VFX_UnitConeMesh")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, cap_tris=False, segments=24, radius1=1.0, radius2=0.04, depth=1.0)
    for v in bm.verts:
        v.co.z -= 0.5
    bm.to_mesh(cone_m)
    bm.free()
    for p in cone_m.polygons:
        p.use_smooth = True
    meshes["cone"] = cone_m

    # 2. Spiky crystalline spark / firework streak shard
    shard_m = bpy.data.meshes.new("VFX_ShardMesh")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    for v in bm.verts:
        v.co.x *= 0.42
        v.co.y *= 0.42
        v.co.z *= 1.85
    bm.to_mesh(shard_m)
    bm.free()
    meshes["shard"] = shard_m

    # 3. Thin Shockwave Ring Mesh (major_radius=1.0, minor=0.026 -> crisp high-contrast neon ring)
    bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.026, major_segments=36, minor_segments=8)
    ring_tmp = bpy.context.active_object
    ring_m = ring_tmp.data
    ring_m.name = "VFX_RingMesh"
    for p in ring_m.polygons:
        p.use_smooth = True
    bpy.data.objects.remove(ring_tmp, do_unlink=True)
    meshes["ring"] = ring_m

    # 4. Spiky Starburst Core Mesh
    core_m = bpy.data.meshes.new("VFX_CoreMesh")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.85)
    for idx, v in enumerate(bm.verts):
        v.co *= (1.42 if idx % 2 == 0 else 0.70)
    bm.to_mesh(core_m)
    bm.free()
    meshes["core"] = core_m

    # 5. Thin Confetti Quad
    conf_m = bpy.data.meshes.new("VFX_ConfettiMesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= 0.14
        v.co.y *= 0.08
        v.co.z *= 0.012
    bm.to_mesh(conf_m)
    bm.free()
    meshes["confetti"] = conf_m

    # 6. Jagged Lightning Zig-Zag Bolt Mesh
    bolt_m = bpy.data.meshes.new("VFX_BoltMesh")
    bm = bmesh.new()
    pts = [(0.0, 0.0, 9.0), (-0.7, 0.0, 6.2), (0.8, 0.0, 4.4), (-0.5, 0.0, 2.2), (0.6, 0.0, 0.2), (-0.2, 0.0, -2.0)]
    w = 0.26
    for i in range(len(pts) - 1):
        p0, p1 = Vector(pts[i]), Vector(pts[i + 1])
        v0 = bm.verts.new((p0.x - w, p0.y, p0.z))
        v1 = bm.verts.new((p0.x + w, p0.y, p0.z))
        v2 = bm.verts.new((p1.x + w * 0.65, p1.y, p1.z))
        v3 = bm.verts.new((p1.x - w * 0.65, p1.y, p1.z))
        bm.faces.new((v0, v1, v2, v3))
    bm.to_mesh(bolt_m)
    bm.free()
    meshes["bolt"] = bolt_m
    return meshes


def _spawn_vfx_obj(name: str, mesh: bpy.types.Mesh, mat: bpy.types.Material, col: bpy.types.Collection, *, loc=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), rot=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, mesh.copy())
    obj.data.materials.append(mat)
    obj.location = loc
    obj.scale = scale
    obj.rotation_euler = rot
    if hasattr(obj, "visible_shadow"):
        obj.visible_shadow = False
    _assign_to_col(obj, col)
    return obj


def _spawn_light_cone(
    name: str,
    cone_mesh: bpy.types.Mesh,
    col: bpy.types.Collection,
    origin_xyz: tuple[float, float, float],
    length: float,
    radius_end: float,
    mat: bpy.types.Material,
    *,
    rot_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    return _spawn_vfx_obj(
        name,
        cone_mesh,
        mat,
        col,
        loc=origin_xyz,
        scale=(radius_end, radius_end, length),
        rot=tuple(math.radians(a) for a in rot_deg),
    )


def _spawn_shard_pool(
    prefix: str,
    count: int,
    shard_mesh: bpy.types.Mesh,
    mats: list[bpy.types.Material],
    col: bpy.types.Collection,
) -> list[bpy.types.Object]:
    pool: list[bpy.types.Object] = []
    for i in range(count):
        obj = _spawn_vfx_obj(
            f"{prefix}_{i:02d}",
            shard_mesh,
            mats[i % len(mats)],
            col,
            loc=(0.0, 0.0, -30.0),
            scale=(0.0, 0.0, 0.0),
        )
        pool.append(obj)
    return pool


def _schedule_ballistic_burst(
    schedule: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]],
    shards: list[bpy.types.Object],
    origin: tuple[float, float, float],
    start_f: int,
    duration_f: int,
    *,
    speed_min: float = 4.5,
    speed_max: float = 11.0,
    gravity: float = 8.5,
    spread_z: tuple[float, float] = (0.15, 0.95),
    base_scale: float = 0.14,
    seed: int = 1,
    total_frames: int = 1386,
) -> set[int]:
    """Populate per-frame ballistic explosion transforms into a schedule; return boundary CONSTANT frames."""
    end_f = min(total_frames, start_f + duration_f)
    const_frames: set[int] = set()
    n = len(shards)
    for i, sp in enumerate(shards):
        d = schedule.setdefault(sp.name, {})
        if start_f > 1 and (start_f - 1) not in d:
            d[start_f - 1] = ((origin[0], origin[1], origin[2] - 20.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            const_frames.add(start_f - 1)
        az = (2.0 * math.pi * i / max(1, n)) + 0.618 * ((seed * 13 + i * 7) % 19)
        frac = ((i * 37 + seed * 17) % 100) / 100.0
        vz_u = spread_z[0] + (spread_z[1] - spread_z[0]) * frac
        spd = speed_min + (speed_max - speed_min) * (((i * 23 + seed * 11) % 100) / 100.0)
        horiz = math.sqrt(max(0.05, 1.0 - vz_u * vz_u * 0.45))
        vx = spd * horiz * math.cos(az)
        vy = spd * horiz * math.sin(az)
        vz = spd * vz_u
        dir_vec = Vector((vx, vy, vz))
        base_q = dir_vec.to_track_quat("Z", "Y").to_euler() if dir_vec.length > 1e-4 else Vector((0.0, 0.0, 0.0))

        for f in range(start_f, end_f + 1):
            dt = (f - start_f) / 24.0
            u = (f - start_f) / float(max(1, duration_f))
            px = origin[0] + vx * dt
            py = origin[1] + vy * dt
            pz = origin[2] + vz * dt - 0.5 * gravity * dt * dt
            # Elastic pop-in in 2 frames, crisp taper near end
            env = min(1.0, (f - start_f + 1) / 2.0) * (1.0 - u * u)
            sc = max(0.0, base_scale * env)
            rot = (base_q[0] + dt * 4.5, base_q[1] + dt * 3.0 * ((-1) ** i), base_q[2] + az)
            d[f] = ((px, py, pz), rot, (sc * 0.72, sc * 0.72, sc * (1.35 + 0.9 * (1.0 - u))))

        if end_f < total_frames:
            d[end_f + 1] = ((origin[0], origin[1], origin[2] - 20.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            const_frames.add(end_f + 1)
    return const_frames


def _flush_vfx_schedule(
    shards: list[bpy.types.Object],
    schedule: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]],
    const_frames: set[int],
) -> None:
    for sp in shards:
        d = schedule.get(sp.name, {})
        if 1 not in d:
            d[1] = (tuple(sp.location), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            const_frames.add(1)
        for f in sorted(d.keys()):
            loc, rot, sc = d[f]
            sp.location = loc
            sp.rotation_euler = rot
            sp.scale = sc
            sp.keyframe_insert("location", frame=f)
            sp.keyframe_insert("rotation_euler", frame=f)
            sp.keyframe_insert("scale", frame=f)
        _set_constant_at_frames(sp, "scale", const_frames)
        _set_constant_at_frames(sp, "location", const_frames)


def _schedule_shockwave_blast(
    ring_sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]]],
    core_obj: bpy.types.Object | None,
    rings: list[bpy.types.Object],
    start_f: int,
    duration_f: int,
    *,
    max_radius: float = 4.6,
    max_core: float = 1.35,
    total_frames: int = 1386,
) -> set[int]:
    """Populate starburst core + expanding shockwave rings into a scale/rot schedule."""
    const_frames: set[int] = set()
    end_f = min(total_frames, start_f + duration_f)
    if core_obj is not None:
        dc = ring_sched.setdefault(core_obj.name, {})
        if start_f > 1 and (start_f - 1) not in dc:
            dc[start_f - 1] = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            const_frames.add(start_f - 1)
        for f in range(start_f, min(total_frames, start_f + 8) + 1):
            age = f - start_f
            sc = max_core * (0.65 if age == 0 else (1.0 if age == 1 else max(0.0, 1.0 - (age - 1) / 7.0)))
            dc[f] = ((sc, sc, sc), (age * 0.45, age * 0.65, age * 0.85))
        if min(total_frames, start_f + 8) < total_frames:
            dc[min(total_frames, start_f + 8) + 1] = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
            const_frames.add(min(total_frames, start_f + 8) + 1)

    for ri, r_obj in enumerate(rings):
        dr = ring_sched.setdefault(r_obj.name, {})
        st = start_f + ri * 2
        if st > 1 and (st - 1) not in dr:
            dr[st - 1] = ((0.0, 0.0, 0.0), tuple(r_obj.rotation_euler))
            const_frames.add(st - 1)
        r_end = min(total_frames, st + duration_f)
        base_r = tuple(r_obj.rotation_euler)
        for f in range(st, r_end + 1):
            u = (f - st) / float(max(1, duration_f))
            rad = 0.25 + max_radius * (1.0 - (1.0 - u) ** 2.4) * (1.0 + 0.16 * ri)
            z_thick = max(0.15, 1.45 * (1.0 - u))
            dr[f] = ((rad, rad, z_thick), (base_r[0], base_r[1], base_r[2] + u * 1.4 * (1 if ri % 2 == 0 else -1)))
        if r_end < total_frames:
            dr[r_end + 1] = ((0.0, 0.0, 0.0), base_r)
            const_frames.add(r_end + 1)
    return const_frames


def _flush_ring_schedule(
    objs: list[bpy.types.Object],
    sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]]],
    const_frames: set[int],
) -> None:
    for o in objs:
        d = sched.get(o.name, {})
        if 1 not in d:
            d[1] = ((0.0, 0.0, 0.0), tuple(o.rotation_euler))
            const_frames.add(1)
        for f in sorted(d.keys()):
            sc, rot = d[f]
            o.scale = sc
            o.rotation_euler = rot
            o.keyframe_insert("scale", frame=f)
            o.keyframe_insert("rotation_euler", frame=f)
        _set_constant_at_frames(o, "scale", const_frames)


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
    if not intervals:
        hide_frames = {1: True}
    else:
        hide_frames = {1: True}
        for a, b in intervals:
            if 1 <= a <= total_frames:
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


def _build_set1_museum(
    spec: dict[str, Any],
    acts_basic: dict[str, bpy.types.Action],
    shared_mats: dict[str, Any],
    vfx_meshes: dict[str, bpy.types.Mesh],
    frames_data: list[dict[str, Any]],
    intervals: list[tuple[int, int]],
    total_frames: int,
) -> bpy.types.Collection:
    """Set 1 (-60, 0, 0): Royal Emerald Museum Vault (Heist Act 1 f 1..228 + Epilogue f 1288..end)."""
    OX, OY = -60.0, 0.0
    col = bpy.data.collections.new("Set1_MuseumVault")
    bpy.context.scene.collection.children.link(col)

    marble_dark_m, _ = _make_mat("S1_MarbleDark", (0.022, 0.052, 0.045, 1.0), roughness=0.20)
    emerald_col_m, _ = _make_mat("S1_EmeraldColumn", (0.04, 0.14, 0.11, 1.0), metallic=0.15, roughness=0.28)
    crimson_velvet_m, _ = _make_mat("S1_Velvet", (0.44, 0.03, 0.06, 1.0), roughness=0.80)
    laser_m, laser_bsdf = _make_mat("S1_Laser", (1.0, 0.08, 0.14, 1.0), emission_color=(1.0, 0.08, 0.16, 1.0), emission_strength=10.5)
    alarm_m, alarm_bsdf = _make_mat("S1_Alarm", (1.0, 0.10, 0.05, 1.0), emission_color=(1.0, 0.08, 0.05, 1.0), emission_strength=0.4)
    emp_m, emp_bsdf = _make_mat("S1_EMP", (0.12, 0.94, 1.0, 1.0), emission_color=(0.12, 0.92, 1.0, 1.0), emission_strength=7.2)

    beam_em_m, beam_em_node = _make_beam_mat("S1_BeamEmerald", (0.14, 1.0, 0.72), strength=1.5, max_alpha=0.08)
    beam_red_m, beam_red_node = _make_beam_mat("S1_BeamSiren", (1.0, 0.12, 0.18), strength=1.9, max_alpha=0.10)
    beam_cyan_m, _ = _make_beam_mat("S1_BeamCyan", (0.16, 0.95, 1.0), strength=1.7, max_alpha=0.09)

    bpy.ops.mesh.primitive_plane_add(size=26.0, location=(OX, OY, 0.0))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(marble_dark_m)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX, OY + 5.8, 3.5))
    bwall = _assign_to_col(bpy.context.active_object, col)
    bwall.scale = (20.0, 0.5, 7.0)
    bwall.data.materials.append(emerald_col_m)

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX, OY - 1.5, 0.008))
    runner = _assign_to_col(bpy.context.active_object, col)
    runner.scale = (2.6, 10.0, 0.016)
    runner.data.materials.append(crimson_velvet_m)

    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.72, depth=1.05, location=(OX, OY + 1.8, 0.525))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(emerald_col_m)
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.62, depth=0.10, location=(OX, OY + 1.8, 1.08))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["gold"])
    bpy.ops.mesh.primitive_torus_add(major_radius=0.58, minor_radius=0.04, location=(OX, OY + 1.8, 1.15))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(crimson_velvet_m)

    for cx, cy in ((-3.4, -0.8), (3.4, -0.8), (-4.2, 2.8), (4.2, 2.8)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=18, radius=0.45, depth=6.2, location=(OX + cx, OY + cy, 3.1))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(emerald_col_m)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.52, minor_radius=0.07, location=(OX + cx, OY + cy, 0.14))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["brass"])

    # Sweeping Vault Security Light Cones + Whirling Emergency Siren Cones
    sec_cone_l = _spawn_light_cone("S1_SecBeamL", vfx_meshes["cone"], col, (OX - 3.0, OY + 3.2, 5.2), 6.2, 1.35, beam_em_m, rot_deg=(28.0, 0.0, -24.0))
    sec_cone_r = _spawn_light_cone("S1_SecBeamR", vfx_meshes["cone"], col, (OX + 3.0, OY + 3.2, 5.2), 6.2, 1.35, beam_cyan_m, rot_deg=(28.0, 0.0, 24.0))
    siren_cone_1 = _spawn_light_cone("S1_SirenBeam1", vfx_meshes["cone"], col, (OX, OY + 1.8, 3.6), 5.6, 1.25, beam_red_m, rot_deg=(72.0, 0.0, 0.0))
    siren_cone_2 = _spawn_light_cone("S1_SirenBeam2", vfx_meshes["cone"], col, (OX, OY + 1.8, 3.6), 5.6, 1.25, beam_red_m, rot_deg=(72.0, 0.0, 180.0))

    # Display Showcase Frame
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

    # 6 Glowing Crimson Security Lasers framing Pedestal
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

    bpy.ops.mesh.primitive_uv_sphere_add(segments=14, ring_count=10, radius=0.18, location=(OX, OY + 1.8, 3.6))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(alarm_m)

    # Pedestal Target Golden Saxophone
    sax_ped, _ = _build_saxophone(col, "S1_PedestalSax", shared_mats["gold"], shared_mats["pearl"])
    sax_ped.location = (OX, OY + 1.8, 1.62)
    sax_ped.scale = (1.18, 1.18, 1.18)

    # Calling Card Epilogue Trophy
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

    # EMP Orb + Explosive EMP Starburst Core + 2 Cross-Tilted Shockwave Rings + 32 Shards
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.13, location=(OX - 2.6, OY - 1.2, 1.0))
    emp_orb = _assign_to_col(bpy.context.active_object, col)
    emp_orb.data.materials.append(emp_m)

    emp_core = _spawn_vfx_obj("S1_EMPCore", vfx_meshes["core"], shared_mats["vfx_cyan"], col, loc=(OX, OY + 1.8, 1.55), scale=(0.0, 0.0, 0.0))
    emp_ring1 = _spawn_vfx_obj("S1_EMPRing1", vfx_meshes["ring"], emp_m, col, loc=(OX, OY + 1.8, 1.45), scale=(0.0, 0.0, 0.0), rot=(math.radians(24), math.radians(-18), 0.0))
    emp_ring2 = _spawn_vfx_obj("S1_EMPRing2", vfx_meshes["ring"], shared_mats["sax_glow"], col, loc=(OX, OY + 1.8, 1.45), scale=(0.0, 0.0, 0.0), rot=(math.radians(-32), math.radians(28), 0.4))
    s1_shards = _spawn_shard_pool("S1_Shard", 32, vfx_meshes["shard"], [shared_mats["vfx_cyan"], shared_mats["vfx_gold"], shared_mats["vfx_white"]], col)
    s1_ep_glints = _spawn_shard_pool("S1_EpGlint", 16, vfx_meshes["shard"], [shared_mats["vfx_gold"], shared_mats["vfx_white"]], col)

    # Set 1 Lights (Spot + Key + Rim + Dynamic EMP Flash Light)
    emp_flash_ld = bpy.data.lights.new("S1_EMPFlashLight", type="POINT")
    emp_flash_ld.energy = 0.0
    emp_flash_ld.color = (0.35, 0.96, 1.0)
    emp_flash_ld.shadow_soft_size = 0.4
    emp_flash_obj = bpy.data.objects.new("S1_EMPFlashLight", emp_flash_ld)
    emp_flash_obj.location = (OX, OY + 1.8, 1.8)
    _assign_to_col(emp_flash_obj, col)

    for lname, ltype, loc, eng, col_rgb in (
        ("S1_VaultSpot", "SPOT", (OX, OY + 1.4, 5.2), 1550.0, (0.85, 1.0, 0.92)),
        ("S1_HallKey", "AREA", (OX - 3.5, OY - 4.5, 4.2), 680.0, (0.55, 0.95, 0.78)),
        ("S1_HallRim", "AREA", (OX + 3.5, OY - 3.0, 3.8), 520.0, (1.0, 0.72, 0.35)),
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
    _attach_custom_prop(m_arm, "handslot.r", m_sax, rot_deg=(12.0, 16.0, -45.0), scale=1.22)

    # Schedule Laser Hit Sparks (f 39, 112, 140) & Massive EMP Detonation (f 179..204)
    s1_sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]] = {}
    s1_const: set[int] = set()
    for hf in (39, 112, 140):
        s1_const |= _schedule_ballistic_burst(s1_sched, s1_shards[:12], (OX, OY + 1.8, 1.65), hf, 14, speed_min=3.2, speed_max=6.8, base_scale=0.10, seed=hf, total_frames=total_frames)
    s1_const |= _schedule_ballistic_burst(s1_sched, s1_shards, (OX, OY + 1.8, 1.55), 179, 26, speed_min=5.5, speed_max=13.5, gravity=7.5, spread_z=(0.05, 0.95), base_scale=0.17, seed=179, total_frames=total_frames)
    _flush_vfx_schedule(s1_shards, s1_sched, s1_const)

    s1_r_sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]]] = {}
    s1_r_const = _schedule_shockwave_blast(s1_r_sched, emp_core, [emp_ring1, emp_ring2], 179, 24, max_radius=4.8, max_core=0.38, total_frames=total_frames)
    for hf in (39, 112, 140):
        s1_r_const |= _schedule_shockwave_blast(s1_r_sched, None, [emp_ring1], hf, 10, max_radius=1.8, total_frames=total_frames)
    _flush_ring_schedule([emp_core, emp_ring1, emp_ring2], s1_r_sched, s1_r_const)

    # Animate Set 1 Timeline: 1..228 and 1288..total_frames
    s1_frames = sorted(set(range(1, min(229, total_frames + 1), 2)) | set(range(168, min(229, total_frames + 1))) | set(range(1288, total_frames + 1, 2)) | {1, 39, 112, 123, 140, 172, 179, 190, 195, 218, 228, 1288, 1300, total_frames})
    actor_const: set[int] = {228, 1288} if total_frames >= 1288 else set()
    for f in s1_frames:
        fd = frames_data[min(len(frames_data) - 1, f - 1)]
        t, bpulse, bass, mid, imp = fd["t"], fd.get("beat_pulse", 0.0), fd["bass"], fd["mid"], fd.get("impact", 0.0)

        # Sweeping vault cones & emergency sirens
        sec_cone_l.rotation_euler = (math.radians(28.0 + 12.0 * math.sin(t * 2.2)), 0.0, math.radians(-24.0 + 16.0 * math.cos(t * 1.6)))
        sec_cone_r.rotation_euler = (math.radians(28.0 - 12.0 * math.sin(t * 2.2)), 0.0, math.radians(24.0 - 16.0 * math.cos(t * 1.6)))
        sec_cone_l.keyframe_insert("rotation_euler", frame=f)
        sec_cone_r.keyframe_insert("rotation_euler", frame=f)
        beam_em_node.inputs["Strength"].default_value = 1.2 + 1.1 * bpulse + 0.8 * imp
        beam_em_node.inputs["Strength"].keyframe_insert("default_value", frame=f)

        siren_active = 179 <= f <= 228
        siren_sc = (1.3, 1.3, 5.6) if siren_active else (0.0, 0.0, 0.0)
        siren_cone_1.scale = siren_sc
        siren_cone_2.scale = siren_sc
        siren_cone_1.rotation_euler = (math.radians(72.0), 0.0, t * 7.5)
        siren_cone_2.rotation_euler = (math.radians(72.0), 0.0, t * 7.5 + math.pi)
        for sc_o in (siren_cone_1, siren_cone_2):
            sc_o.keyframe_insert("scale", frame=f)
            sc_o.keyframe_insert("rotation_euler", frame=f)
        beam_red_node.inputs["Strength"].default_value = 1.8 + 1.4 * bpulse if siren_active else 0.0
        beam_red_node.inputs["Strength"].keyframe_insert("default_value", frame=f)

        # Point flash on EMP hit
        if 179 <= f <= 186:
            emp_flash_ld.energy = 900.0 * math.exp(-(f - 179) * 0.55)
        elif f in (39, 112, 140, 218):
            emp_flash_ld.energy = 380.0
        else:
            emp_flash_ld.energy = 0.0
        emp_flash_ld.keyframe_insert("energy", frame=f)

        if f <= 228:
            # Knight patrol (beat-synced stride turn) -> Spin startle on f 179!
            if f < 174:
                p = ((f - 1) / 172.0)
                kx = OX - 2.6 + 5.2 * (1.0 - abs(2.0 * p - 1.0))
                kyaw = 90.0 if p <= 0.5 else -90.0
                k_root.location = (kx, OY + 0.15, 0.0)
                k_root.rotation_euler = (0.0, 0.0, math.radians(kyaw))
            else:
                u = min(1.0, (f - 174) / 14.0)
                k_root.location = (OX - 1.85, OY + 0.15, 0.0)
                k_root.rotation_euler = (0.0, 0.0, math.radians(-90.0 + 245.0 * u))
            k_root.keyframe_insert("location", frame=f)
            k_root.keyframe_insert("rotation_euler", frame=f)

            # Rogue EMP toss arc f 168..178 -> detonates on exact beat f 179!
            if f < 168:
                r_root.location = (OX - 2.75, OY - 1.4, 0.0)
                r_root.rotation_euler = (0.0, 0.0, math.radians(-25.0))
                emp_orb.location = (OX - 2.6, OY - 1.2, 0.9)
                emp_orb.scale = (0.0, 0.0, 0.0)
                _kf_bone_rot(r_arm, "upperarm.r", (-62.0 + 8.0 * bpulse, 0.0, 18.0), f)
                _kf_bone_rot(r_arm, "lowerarm.r", (0.0, 0.0, 32.0), f)
            elif f < 179:
                u = (f - 168) / 11.0
                r_root.location = (OX - 2.2 + 0.8 * u, OY - 1.0 + 0.9 * u, 0.0)
                r_root.rotation_euler = (0.0, 0.0, math.radians(-30.0))
                emp_orb.location = (OX - 2.2 + 2.2 * u, OY - 1.0 + 2.8 * u, 1.0 + 1.55 * math.sin(u * math.pi))
                emp_orb.scale = (1.1 + 0.4 * u, 1.1 + 0.4 * u, 1.1 + 0.4 * u)
                _kf_bone_rot(r_arm, "upperarm.r", (-10.0 + 48.0 * u, 0.0, 62.0), f)
                _kf_bone_rot(r_arm, "lowerarm.r", (0.0, 0.0, 48.0), f)
            else:
                r_root.location = (OX - 1.15, OY + 0.55, 0.0)
                r_root.rotation_euler = (0.0, 0.0, math.radians(20.0 * math.sin((f - 179) * 0.1)))
                emp_orb.scale = (0.0, 0.0, 0.0)
                _kf_bone_rot(r_arm, "upperarm.r", (-28.0 + 22.0 * bpulse, 0.0, 52.0), f)
                _kf_bone_rot(r_arm, "lowerarm.r", (0.0, 0.0, 58.0), f)
            r_root.keyframe_insert("location", frame=f)
            r_root.keyframe_insert("rotation_euler", frame=f)
            emp_orb.keyframe_insert("location", frame=f)
            emp_orb.keyframe_insert("scale", frame=f)

            # Glass showcase & 6 Crimson Lasers shatter right at f 179
            if f < 179:
                dome_root.location.z = 1.12
                laser_sc = 1.0 + 0.25 * imp
            else:
                dome_root.location.z = 1.12 + min(2.3, (f - 179) * 0.35)
                laser_sc = 0.0
            dome_root.keyframe_insert("location", frame=f)
            for lz in lasers:
                lz.scale = (laser_sc, laser_sc, 1.0 if laser_sc > 0.0 else 0.0)
                lz.keyframe_insert("scale", frame=f)
            laser_bsdf.inputs["Emission Strength"].default_value = 9.0 + 9.0 * bpulse + 8.0 * imp
            laser_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)

            # Mage dash & heroic Saxophone raise on f 179..228
            if f < 178:
                sax_ped.rotation_euler.z = f * 0.05
                sax_ped.scale = (1.18, 1.18, 1.18)
                m_sax.scale = (0.0, 0.0, 0.0)
                m_root.location = (OX + 2.6, OY - 1.1, 0.0)
                _kf_bone_rot(m_arm, "upperarm.r", (-62.0 + 6.0 * bpulse, 0.0, 18.0), f)
                _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 35.0), f)
                _kf_bone_rot(m_arm, "spine", (4.0 * bpulse, 0.0, 0.0), f)
            elif f < 190:
                u = (f - 178) / 12.0
                sax_ped.scale = (1.18, 1.18, 1.18) if f < 185 else (0.0, 0.0, 0.0)
                m_sax.scale = (0.0, 0.0, 0.0) if f < 185 else (1.0, 1.0, 1.0)
                m_root.location = (OX + 2.6 - 2.3 * u, OY - 1.1 + 2.0 * u, 0.0)
                _kf_bone_rot(m_arm, "upperarm.r", (-35.0, 0.0, 62.0), f)
                _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 70.0), f)
                _kf_bone_rot(m_arm, "spine", (-12.0 * u, 0.0, 0.0), f)
            else:
                sax_ped.scale = (0.0, 0.0, 0.0)
                m_sax.scale = (1.0, 1.0, 1.0)
                m_root.location = (OX + 0.30, OY + 0.90, 0.0)
                _kf_bone_rot(m_arm, "upperarm.r", (-15.0 + 10.0 * bpulse, 0.0, 66.0), f)
                _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 78.0), f)
                _kf_bone_rot(m_arm, "spine", (-14.0 * bpulse, 8.0 * math.sin(t * 4.0), 0.0), f)

            sax_ped.keyframe_insert("rotation_euler", frame=f)
            sax_ped.keyframe_insert("scale", frame=f)
            m_sax.keyframe_insert("scale", frame=f)
            m_root.keyframe_insert("location", frame=f)

            al_str = 16.0 if (179 <= f <= 228 and (f // 2) % 2 == 0) else 0.4
            alarm_bsdf.inputs["Emission Strength"].default_value = al_str
            alarm_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)

            card_root.scale = (0.0, 0.0, 0.0)
            card_root.keyframe_insert("scale", frame=f)

            _kf_bone_rot(r_arm, "upperarm.l", (-62.0, 0.0, -20.0), f)
            _kf_bone_rot(r_arm, "lowerarm.l", (0.0, 0.0, -35.0), f)
            _kf_bone_rot(m_arm, "upperarm.l", (-52.0, 0.0, -36.0), f)
            _kf_bone_rot(m_arm, "lowerarm.l", (0.0, 0.0, -48.0), f)
            for gl in s1_ep_glints:
                gl.scale = (0.0, 0.0, 0.0)
                gl.keyframe_insert("scale", frame=f)
        else:
            # Epilogue (f >= 1288): hide S1 characters cleanly, sweep lasers & glow Calling Card!
            for root_act in (k_root, r_root, m_root):
                root_act.location.z = -15.0
                root_act.keyframe_insert("location", frame=f)
            dome_root.location.z = 1.12
            dome_root.keyframe_insert("location", frame=f)
            laser_sc = 0.85 if ((f - 1288) // 8) % 2 == 0 else 0.25
            for lz in lasers:
                lz.scale = (laser_sc, laser_sc, 1.0)
                lz.keyframe_insert("scale", frame=f)
            sax_ped.scale = (0.0, 0.0, 0.0)
            sax_ped.keyframe_insert("scale", frame=f)
            m_sax.scale = (0.0, 0.0, 0.0)
            m_sax.keyframe_insert("scale", frame=f)

            card_root.scale = (1.05, 1.05, 1.05)
            card_root.rotation_euler.z = f * 0.06
            card_root.keyframe_insert("scale", frame=f)
            card_root.keyframe_insert("rotation_euler", frame=f)

            al_str = 10.0 if (f // 6) % 2 == 0 else 1.2
            alarm_bsdf.inputs["Emission Strength"].default_value = al_str
            alarm_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)

            # Soft orbiting golden sparkle halo around Calling Card
            for gi, gl in enumerate(s1_ep_glints):
                ang_g = t * 1.4 + gi * (2.0 * math.pi / 16.0)
                rad_g = 0.62 + 0.14 * math.sin(t * 2.5 + gi)
                gl.location = (OX + rad_g * math.cos(ang_g), OY + 1.8 + rad_g * math.sin(ang_g), 1.38 + 0.38 * math.sin(t * 2.0 + gi * 0.7))
                gs = 0.055 * (0.65 + 0.6 * mid + 0.4 * math.sin(f * 0.3 + gi))
                gl.scale = (gs, gs, gs * 1.8)
                gl.rotation_euler = (0.3 * gi, t, ang_g)
                gl.keyframe_insert("location", frame=f)
                gl.keyframe_insert("scale", frame=f)
                gl.keyframe_insert("rotation_euler", frame=f)

    for root_act in (k_root, r_root, m_root):
        _set_constant_at_frames(root_act, "location", actor_const)
    _set_constant_at_frames(card_root, "scale", {228, 1288})
    _set_constant_at_frames(dome_root, "location", {228, 1288})
    for gl in s1_ep_glints:
        _set_constant_at_frames(gl, "scale", {228, 1288})

    _kf_constant_visibility(col, intervals, total_frames)
    return col


def _build_set2_rooftop(
    spec: dict[str, Any],
    acts_basic: dict[str, bpy.types.Action],
    shared_mats: dict[str, Any],
    vfx_meshes: dict[str, bpy.types.Mesh],
    frames_data: list[dict[str, Any]],
    intervals: list[tuple[int, int]],
    total_frames: int,
) -> bpy.types.Collection:
    """Set 2 (+60, 0, 0): Moonlit Neon Rooftop Chase & Chasm Leap (f 229..407)."""
    OX, OY = 60.0, 0.0
    col = bpy.data.collections.new("Set2_RooftopChase")
    bpy.context.scene.collection.children.link(col)

    roof_m, _ = _make_mat("S2_Rooftop", (0.04, 0.045, 0.075, 1.0), roughness=0.52)
    trim_cyan_m, cyan_bsdf = _make_mat("S2_NeonCyan", (0.10, 0.92, 1.0, 1.0), emission_color=(0.10, 0.92, 1.0, 1.0), emission_strength=5.2)
    trim_mag_m, mag_bsdf = _make_mat("S2_NeonMagenta", (1.0, 0.18, 0.72, 1.0), emission_color=(1.0, 0.16, 0.72, 1.0), emission_strength=4.8)
    win_gold_m, _ = _make_mat("S2_WinGold", (1.0, 0.78, 0.32, 1.0), emission_color=(1.0, 0.74, 0.25, 1.0), emission_strength=1.6)
    moon_m, _ = _make_mat("S2_FullMoon", (1.0, 0.96, 0.85, 1.0), emission_color=(1.0, 0.94, 0.80, 1.0), emission_strength=2.1)
    tower_m, _ = _make_mat("S2_Skyscraper", (0.025, 0.032, 0.058, 1.0), roughness=0.6)
    bolt_m, bolt_bsdf = _make_mat("S2_Lightning", (0.85, 0.98, 1.0, 1.0), emission_color=(0.55, 0.95, 1.0, 1.0), emission_strength=18.0)

    beam_cyan_m, beam_cyan_node = _make_beam_mat("S2_SearchCyan", (0.14, 0.92, 1.0), strength=1.6, max_alpha=0.085)
    beam_gold_m, beam_gold_node = _make_beam_mat("S2_SearchGold", (1.0, 0.78, 0.26), strength=1.5, max_alpha=0.080)

    # Rooftops separated by 5m chasm
    for bx, bw, bname in ((-8.2, 11.4, "S2_BuildingA"), (8.2, 11.4, "S2_BuildingB")):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX + bx, OY, -6.0))
        bld = _assign_to_col(bpy.context.active_object, col)
        bld.name = bname
        bld.scale = (bw, 6.2, 12.0)
        bld.data.materials.append(roof_m)
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX + bx, OY - 3.12, -0.08))
        nstrip = _assign_to_col(bpy.context.active_object, col)
        nstrip.scale = (bw, 0.06, 0.16)
        nstrip.data.materials.append(trim_cyan_m)

    # Blazing Neon Exit Portal Arch on Building B (x=+9.2)
    bpy.ops.mesh.primitive_torus_add(major_radius=1.45, minor_radius=0.09, location=(OX + 9.0, OY, 1.45), rotation=(0.0, math.pi * 0.5, 0.0))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(trim_mag_m)

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
        # Neon Billboard Accent Bar at tower cap
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX + sx, OY + sy - sw * 0.53, sh - 9.3))
        nb = _assign_to_col(bpy.context.active_object, col)
        nb.scale = (sw * 0.85, 0.10, 0.34)
        nb.data.materials.append(trim_mag_m if sx < 0 else trim_cyan_m)

    # 4 Sweeping Skyline Searchlight Cones behind flanking towers (preserving clear Moon corridor!)
    searchlights = []
    for si, (slx, sc_mat) in enumerate(((-12.2, beam_cyan_m), (-7.6, beam_gold_m), (7.6, beam_gold_m), (12.2, beam_cyan_m))):
        sc_obj = _spawn_light_cone(f"S2_Searchlight_{si}", vfx_meshes["cone"], col, (OX + slx, OY + 10.5, 3.5), 14.0, 2.1, sc_mat, rot_deg=(138.0, 0.0, 0.0))
        searchlights.append(sc_obj)

    # Skyline Lightning Bolt (flashes on f 246 & f 285!)
    bolt1 = _spawn_vfx_obj("S2_Lightning1", vfx_meshes["bolt"], bolt_m, col, loc=(OX - 6.8, OY + 9.0, 4.0), scale=(0.0, 0.0, 0.0))
    bolt2 = _spawn_vfx_obj("S2_Lightning2", vfx_meshes["bolt"], bolt_m, col, loc=(OX + 7.2, OY + 9.5, 4.5), scale=(0.0, 0.0, 0.0))

    # Giant Luminous Full Moon framed cleanly inside the Chasm Corridor!
    bpy.ops.mesh.primitive_uv_sphere_add(segments=36, ring_count=20, radius=6.8, location=(OX + 0.0, OY + 26.0, 6.2))
    moon = _assign_to_col(bpy.context.active_object, col)
    moon.name = "S2_GiantMoon"
    moon.data.materials.append(moon_m)

    # Lights + Dynamic Crater/Lightning Flash Light
    flash_ld = bpy.data.lights.new("S2_ImpactLight", type="POINT")
    flash_ld.energy = 0.0
    flash_ld.color = (0.65, 0.96, 1.0)
    flash_obj = bpy.data.objects.new("S2_ImpactLight", flash_ld)
    flash_obj.location = (OX + 3.4, OY, 2.2)
    _assign_to_col(flash_obj, col)

    for lname, loc, eng, col_rgb in (
        ("S2_MoonRim", (OX + 0.0, OY + 6.5, 5.0), 1200.0, (0.85, 0.90, 1.0)),
        ("S2_CityKey", (OX - 4.0, OY - 7.0, 4.5), 820.0, (0.55, 0.85, 1.0)),
        ("S2_NeonFill", (OX + 4.0, OY - 6.0, 3.5), 680.0, (1.0, 0.65, 0.25)),
    ):
        ld = bpy.data.lights.new(lname, type="AREA")
        ld.size = 5.0
        ld.energy = eng
        ld.color = col_rgb
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((OX, OY, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        _assign_to_col(lo, col)

    # 4 Runners with REAL QUATERNION Action Slots (re-timed to f 229..407!)
    m_root, m_arm = _spawn_band_member(spec["cast"]["mage"], col, "S2_Mage", (OX - 9.0, OY - 0.3, 0.0), 90.0, 0.0, use_euler_pose=False)
    m_sax, _ = _build_saxophone(col, "S2_MageSax", shared_mats["gold"], shared_mats["pearl"])
    _attach_custom_prop(m_arm, "handslot.r", m_sax, rot_deg=(12.0, 16.0, -45.0), scale=1.22)

    r_root, r_arm = _spawn_band_member(spec["cast"]["rogue"], col, "S2_Rogue", (OX - 10.2, OY + 0.6, 0.0), 90.0, 0.0, use_euler_pose=False)
    k_root, k_arm = _spawn_band_member(spec["cast"]["knight"], col, "S2_Knight", (OX - 13.0, OY - 0.4, 0.0), 90.0, 0.0, use_euler_pose=False)
    _attach_glb_prop(spec["cast"]["sword_1handed"], col, k_arm, "handslot.r", "S2_KnightSword")
    _attach_glb_prop(spec["cast"]["shield_round"], col, k_arm, "handslot.l", "S2_KnightShield")
    b_root, b_arm = _spawn_band_member(spec["cast"]["barbarian"], col, "S2_Barbarian", (OX - 14.2, OY + 0.7, 0.0), 90.0, 0.0, use_euler_pose=False)
    _attach_glb_prop(spec["cast"]["axe_1handed"], col, b_arm, "handslot.r", "S2_BarbAxe")

    def _setup_nla_chase(arm: bpy.types.Object, tag: str, jump_start: int) -> None:
        ad = arm.animation_data or arm.animation_data_create()
        track = ad.nla_tracks.new()
        track.name = f"ChaseNLA_{tag}"
        run_clone = acts_basic["Running_A"].copy()
        run_clone.name = f"Run_{tag}"[:62]
        st1 = track.strips.new("RunPart1", 225, run_clone)
        st1.action_frame_start = 0
        st1.action_frame_end = 19.2
        st1.repeat = max(1.0, (jump_start - 225) / 19.2)

        jmp_clone = acts_basic["Jump_Full_Long"].copy()
        jmp_clone.name = f"Jump_{tag}"[:62]
        st2 = track.strips.new("ChasmLeap", jump_start, jmp_clone)
        st2.action_frame_start = 2
        st2.action_frame_end = 56
        st2.scale = 0.74
        st2.blend_in = 3.0

        run_after = acts_basic["Running_A"].copy()
        run_after.name = f"Sprint_{tag}"[:62]
        st3 = track.strips.new("PostLandingSprint", jump_start + 42, run_after)
        st3.action_frame_start = 0
        st3.action_frame_end = 19.2
        st3.repeat = 3.5
        st3.blend_in = 3.0

        for st, cl in ((st1, run_clone), (st2, jmp_clone), (st3, run_after)):
            if hasattr(st, "action_slot") and hasattr(cl, "slots"):
                objs = [s for s in cl.slots if getattr(s, "target_id_type", None) == "OBJECT"]
                if objs:
                    st.action_slot = objs[0]

    _setup_nla_chase(m_arm, "S2M", 318)
    _setup_nla_chase(r_arm, "S2R", 320)
    _setup_nla_chase(k_arm, "S2K", 326)
    _setup_nla_chase(b_arm, "S2B", 328)

    # VFX: Breach Burst (f229), Launch Shockwave + 32 Moon Comet Shards (f319..362), Landing Crater Explosion (f363..386)!
    comet_shards = _spawn_shard_pool("S2_Comet", 32, vfx_meshes["shard"], [shared_mats["vfx_gold"], shared_mats["vfx_cyan"], shared_mats["vfx_white"]], col)
    s2_burst_shards = _spawn_shard_pool("S2_Burst", 32, vfx_meshes["shard"], [shared_mats["vfx_cyan"], shared_mats["vfx_magenta"], shared_mats["vfx_gold"]], col)
    s2_core = _spawn_vfx_obj("S2_Core", vfx_meshes["core"], shared_mats["vfx_cyan"], col, loc=(OX + 3.4, OY - 0.2, 0.20), scale=(0.0, 0.0, 0.0))
    s2_launch_ring = _spawn_vfx_obj("S2_LaunchRing", vfx_meshes["ring"], trim_cyan_m, col, loc=(OX - 2.6, OY - 0.1, 0.35), scale=(0.0, 0.0, 0.0), rot=(0.0, math.pi * 0.5, 0.0))
    s2_land_ring1 = _spawn_vfx_obj("S2_LandRing1", vfx_meshes["ring"], trim_cyan_m, col, loc=(OX + 3.4, OY - 0.1, 0.22), scale=(0.0, 0.0, 0.0), rot=(math.radians(12), 0.0, 0.0))
    s2_land_ring2 = _spawn_vfx_obj("S2_LandRing2", vfx_meshes["ring"], trim_mag_m, col, loc=(OX + 3.4, OY - 0.1, 0.25), scale=(0.0, 0.0, 0.0), rot=(math.radians(-18), math.radians(14), 0.0))

    s2_sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]] = {}
    s2_const: set[int] = set()
    s2_const |= _schedule_ballistic_burst(s2_sched, s2_burst_shards[:24], (OX - 9.5, OY + 0.1, 0.8), 229, 18, speed_min=4.5, speed_max=10.5, spread_z=(0.15, 0.9), base_scale=0.11, seed=229, total_frames=total_frames)
    s2_const |= _schedule_ballistic_burst(s2_sched, s2_burst_shards, (OX + 3.4, OY - 0.1, 0.22), 363, 22, speed_min=5.5, speed_max=12.5, gravity=10.0, spread_z=(0.25, 1.0), base_scale=0.13, seed=363, total_frames=total_frames)
    _flush_vfx_schedule(s2_burst_shards, s2_sched, s2_const)

    s2_r_sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]]] = {}
    s2_r_const = _schedule_shockwave_blast(s2_r_sched, None, [s2_launch_ring], 319, 16, max_radius=3.4, total_frames=total_frames)
    s2_r_const |= _schedule_shockwave_blast(s2_r_sched, s2_core, [s2_land_ring1, s2_land_ring2], 363, 20, max_radius=4.6, max_core=0.32, total_frames=total_frames)
    _flush_ring_schedule([s2_core, s2_launch_ring, s2_land_ring1, s2_land_ring2], s2_r_sched, s2_r_const)

    for f in range(max(1, 229), min(total_frames, 407) + 1):
        fd = frames_data[min(len(frames_data) - 1, f - 1)]
        t, bpulse, bass, rms = fd["t"], fd.get("beat_pulse", 0.0), fd["bass"], fd["rms"]

        # Runners across Building A (229..318) -> Moon Chasm Leap (319..362) -> Crater Slam & Portal Dash (363..407)
        if f <= 318:
            u = (f - 229) / 89.0
            mx = OX - 9.6 + 7.0 * u
            mz = 0.0
            rx, rz = mx - 1.15, 0.0
            kx = OX - 12.8 + 8.6 * u
            kz = 0.0
            bx, bz = kx - 1.25, 0.0
        elif f <= 362:
            u = (f - 319) / 43.0
            mx = OX - 2.6 + 6.0 * u
            mz = 1.95 * math.sin(u * math.pi)
            rx = mx - 1.25
            rz = 1.85 * math.sin(u * math.pi)
            ku = max(0.0, (f - 327) / 40.0)
            kx = OX - 4.2 + 6.0 * min(1.0, ku)
            kz = 1.65 * math.sin(min(1.0, ku) * math.pi)
            bx = kx - 1.20
            bz = 1.50 * math.sin(min(1.0, ku) * math.pi)
        else:
            u = (f - 363) / 44.0
            mx, mz = OX + 3.4 + 5.2 * u, 0.0
            rx, rz = OX + 2.2 + 4.8 * u, 0.0
            ku = max(0.0, (f - 367) / 40.0)
            kx, kz = OX + 1.8 + 4.2 * ku, 0.0
            bx, bz = OX + 0.6 + 3.8 * ku, 0.0

        m_root.location = (mx, OY - 0.3, mz)
        r_root.location = (rx, OY + 0.65, rz)
        k_root.location = (kx, OY - 0.4, kz)
        b_root.location = (bx, OY + 0.75, bz)
        for obj in (m_root, r_root, k_root, b_root):
            obj.keyframe_insert("location", frame=f)

        # 32 Comet Trail Shards arcing cleanly behind Runners during Moon Chasm Leap!
        show_comet = 319 <= f <= 366
        for ci, sp in enumerate(comet_shards):
            lag = ci * 0.16
            sp.location = (mx - 0.35 - lag, OY + 0.15 + 0.25 * math.sin(f * 0.35 + ci * 0.6), max(0.18, mz - 0.06 * ci + 0.30 + 0.18 * math.cos(f * 0.4 + ci)))
            sc = (0.09 + 0.06 * (1.0 - ci / 32.0)) if show_comet else 0.0
            sp.scale = (sc * 0.7, sc * 0.7, sc * 2.2)
            sp.rotation_euler = (0.0, math.pi * 0.42, 0.15 * math.sin(ci))
            sp.keyframe_insert("location", frame=f)
            sp.keyframe_insert("scale", frame=f)
            sp.keyframe_insert("rotation_euler", frame=f)

        # Sweeping Skyline Searchlights & Billboard Strobe
        for si, sc_obj in enumerate(searchlights):
            side = -1.0 if si < 2 else 1.0
            sc_obj.rotation_euler = (
                math.radians(134.0 + 14.0 * math.sin(t * 2.4 + si)),
                math.radians(side * (24.0 + 22.0 * math.cos(t * 1.9 + si))),
                math.radians(18.0 * math.sin(t * 1.3)),
            )
            sc_obj.keyframe_insert("rotation_euler", frame=f)
        beam_cyan_node.inputs["Strength"].default_value = 1.4 + 1.2 * bpulse
        beam_gold_node.inputs["Strength"].default_value = 1.4 + 1.0 * bass
        beam_cyan_node.inputs["Strength"].keyframe_insert("default_value", frame=f)
        beam_gold_node.inputs["Strength"].keyframe_insert("default_value", frame=f)
        cyan_bsdf.inputs["Emission Strength"].default_value = 2.8 + 3.5 * bpulse
        mag_bsdf.inputs["Emission Strength"].default_value = 2.8 + 3.8 * bass
        cyan_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
        mag_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)

        # Skyline Lightning Bolt flashes at f 246..251 and f 285..289
        b1_on = 246 <= f <= 250
        b2_on = 285 <= f <= 289
        bolt1.scale = (1.1, 1.1, 1.1) if b1_on else (0.0, 0.0, 0.0)
        bolt2.scale = (1.1, 1.1, 1.1) if b2_on else (0.0, 0.0, 0.0)
        bolt1.keyframe_insert("scale", frame=f)
        bolt2.keyframe_insert("scale", frame=f)
        if b1_on or b2_on:
            flash_obj.location = (OX, OY + 5.0, 6.0)
            flash_ld.energy = 900.0
        elif 363 <= f <= 370:
            flash_obj.location = (OX + 3.4, OY - 0.5, 1.2)
            flash_ld.energy = 850.0 * math.exp(-(f - 363) * 0.55)
        else:
            flash_ld.energy = 0.0
        flash_obj.keyframe_insert("location", frame=f)
        flash_ld.keyframe_insert("energy", frame=f)

    _kf_constant_visibility(col, intervals, total_frames)
    return col


def _build_set3_speakeasy(
    spec: dict[str, Any],
    shared_mats: dict[str, Any],
    vfx_meshes: dict[str, bpy.types.Mesh],
    frames_data: list[dict[str, Any]],
    bpm: float,
    intervals: list[tuple[int, int]],
    total_frames: int,
) -> bpy.types.Collection:
    """Set 3 (0, -60, 0): Underground Neon Speakeasy & Weapon-to-Instrument Explosions (f 408..764)."""
    OX, OY = 0.0, -60.0
    col = bpy.data.collections.new("Set3_Speakeasy")
    bpy.context.scene.collection.children.link(col)

    mahogany_m, _ = _make_mat("S3_Mahogany", (0.06, 0.02, 0.025, 1.0), roughness=0.22)
    crimson_wall_m, _ = _make_mat("S3_CrimsonWall", (0.14, 0.018, 0.032, 1.0), roughness=0.45)
    amber_lamp_m, _ = _make_mat("S3_AmberLamp", (1.0, 0.72, 0.24, 1.0), emission_color=(1.0, 0.68, 0.20, 1.0), emission_strength=6.8)
    shock_m, shock_bsdf = _make_mat("S3_SaxShockwave", (1.0, 0.72, 0.14, 1.0), emission_color=(1.0, 0.68, 0.12, 1.0), emission_strength=6.2)
    morph_m, _ = _make_mat("S3_MorphBurst", (0.10, 0.90, 1.0, 1.0), emission_color=(0.10, 0.88, 1.0, 1.0), emission_strength=6.8)
    fire_m, _ = _make_mat("S3_FireMorph", (1.0, 0.24, 0.08, 1.0), emission_color=(1.0, 0.22, 0.08, 1.0), emission_strength=6.8)

    beam_gold_m, beam_gold_n = _make_beam_mat("S3_ClubGold", (1.0, 0.76, 0.22), strength=1.5, max_alpha=0.075)
    beam_ruby_m, beam_ruby_n = _make_beam_mat("S3_ClubRuby", (1.0, 0.14, 0.42), strength=1.6, max_alpha=0.075)

    bpy.ops.mesh.primitive_plane_add(size=24.0, location=(OX, OY, 0.0))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(mahogany_m)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(OX, OY + 4.4, 3.0))
    wall = _assign_to_col(bpy.context.active_object, col)
    wall.scale = (16.0, 0.4, 6.0)
    wall.data.materials.append(crimson_wall_m)

    for ax in (-3.2, 0.0, 3.2):
        bpy.ops.mesh.primitive_torus_add(major_radius=1.35, minor_radius=0.08, location=(OX + ax, OY + 4.1, 2.2), rotation=(math.pi * 0.5, 0.0, 0.0))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["gold"])

    # Sweeping Club Light Cones + Pulsing Mahogany Floor Rings
    club_cones = []
    for ci, (cx, cm) in enumerate(((-3.4, beam_ruby_m), (-1.2, beam_gold_m), (1.2, beam_gold_m), (3.4, beam_ruby_m))):
        cc = _spawn_light_cone(f"S3_ClubBeam_{ci}", vfx_meshes["cone"], col, (OX + cx, OY + 3.6, 5.2), 7.2, 1.45, cm, rot_deg=(-22.0, 0.0, 0.0))
        club_cones.append(cc)

    floor_ring1 = _spawn_vfx_obj("S3_FloorRing1", vfx_meshes["ring"], shock_m, col, loc=(OX - 0.1, OY - 0.2, 0.03), scale=(1.0, 1.0, 0.4))
    floor_ring2 = _spawn_vfx_obj("S3_FloorRing2", vfx_meshes["ring"], morph_m, col, loc=(OX - 0.1, OY - 0.2, 0.03), scale=(1.6, 1.6, 0.4))

    for tx, ty in ((-3.5, -2.0), (3.5, -2.0)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.48, depth=0.06, location=(OX + tx, OY + ty, 0.82))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["brass"])
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.06, depth=0.82, location=(OX + tx, OY + ty, 0.41))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(mahogany_m)
        bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=0.22, radius2=0.08, depth=0.24, location=(OX + tx, OY + ty, 1.05))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(amber_lamp_m)

    # DJ Neon Vinyl Console + 8-bar front live EQ
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
    dj_eq_bars = []
    for di in range(8):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-0.42 + di * 0.12, -0.34, 0.36))
        db = _assign_to_col(bpy.context.active_object, col)
        db.scale = (0.07, 0.025, 0.45)
        db.data.materials.append(shared_mats["dj_neon"] if di % 2 == 0 else shared_mats["sax_glow"])
        db.parent = dj_root
        dj_eq_bars.append(db)

    bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.24, depth=0.035, location=(0.0, 0.0, 0.92))
    s3_vinyl = _assign_to_col(bpy.context.active_object, col)
    s3_vinyl.data.materials.append(shared_mats["obsidian"])
    s3_vinyl.parent = dj_root
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.05, depth=0.042, location=(0.14, 0.0, 0.92))
    vm = _assign_to_col(bpy.context.active_object, col)
    vm.data.materials.append(shared_mats["dj_neon"])
    vm.parent = s3_vinyl

    # Aimed Sax Sonic Cannon Core + 3 Tilted Blast Rings + Morph Explosions (Knight f692, Barbarian f748)
    sax_core = _spawn_vfx_obj("S3_SaxCore", vfx_meshes["core"], shared_mats["vfx_gold"], col, loc=(OX + 0.55, OY - 0.15, 1.15), scale=(0.0, 0.0, 0.0))
    blast_rings = [
        _spawn_vfx_obj(f"S3_BlastRing_{ri}", vfx_meshes["ring"], shock_m if ri % 2 == 0 else fire_m, col, loc=(OX + 0.55, OY + 0.05, 1.15), scale=(0.0, 0.0, 0.0), rot=(math.radians(78), 0.0, math.radians(-35 + ri * 14)))
        for ri in range(3)
    ]
    mk_core = _spawn_vfx_obj("S3_MorphKCore", vfx_meshes["core"], shared_mats["vfx_cyan"], col, loc=(OX + 1.85, OY + 0.6, 1.85), scale=(0.0, 0.0, 0.0))
    morph_k1 = _spawn_vfx_obj("S3_MorphK1", vfx_meshes["ring"], morph_m, col, loc=(OX + 1.85, OY + 0.6, 0.95), scale=(0.0, 0.0, 0.0))
    morph_k2 = _spawn_vfx_obj("S3_MorphK2", vfx_meshes["ring"], shared_mats["sax_glow"], col, loc=(OX + 1.85, OY + 0.6, 1.10), scale=(0.0, 0.0, 0.0), rot=(math.radians(54), math.radians(-28), 0.0))
    mb_core = _spawn_vfx_obj("S3_MorphBCore", vfx_meshes["core"], shared_mats["vfx_gold"], col, loc=(OX + 0.55, OY + 1.85, 1.90), scale=(0.0, 0.0, 0.0))
    morph_b1 = _spawn_vfx_obj("S3_MorphB1", vfx_meshes["ring"], fire_m, col, loc=(OX + 0.55, OY + 1.85, 1.00), scale=(0.0, 0.0, 0.0))
    morph_b2 = _spawn_vfx_obj("S3_MorphB2", vfx_meshes["ring"], shared_mats["sax_glow"], col, loc=(OX + 0.55, OY + 1.85, 1.15), scale=(0.0, 0.0, 0.0), rot=(math.radians(-48), math.radians(32), 0.0))

    s3_shards = _spawn_shard_pool("S3_Shard", 32, vfx_meshes["shard"], [shared_mats["vfx_gold"], shared_mats["vfx_cyan"], shared_mats["vfx_magenta"]], col)

    # Lights
    s3_flash_ld = bpy.data.lights.new("S3_FlashLight", type="POINT")
    s3_flash_ld.energy = 0.0
    s3_flash_ld.color = (1.0, 0.85, 0.35)
    s3_flash_obj = bpy.data.objects.new("S3_FlashLight", s3_flash_ld)
    s3_flash_obj.location = (OX, OY, 1.8)
    _assign_to_col(s3_flash_obj, col)

    for lname, loc, eng, lcol in (
        ("S3_WarmKey", (OX, OY - 4.8, 4.0), 760.0, (1.0, 0.78, 0.42)),
        ("S3_CrimsonRim", (OX + 4.0, OY + 1.0, 3.2), 520.0, (1.0, 0.20, 0.35)),
        ("S3_DJCyan", (OX - 4.0, OY - 1.5, 3.0), 500.0, (0.15, 0.90, 1.0)),
    ):
        ld = bpy.data.lights.new(lname, type="AREA")
        ld.size = 3.2
        ld.energy = eng
        ld.color = lcol
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((OX, OY, 1.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        _assign_to_col(lo, col)

    # Characters S3
    m_root, m_arm = _spawn_band_member(spec["cast"]["mage"], col, "S3_Mage", (OX - 0.15, OY - 0.45, 0.0), 0.0, 0.0)
    m_sax, m_rings = _build_saxophone(col, "S3_MageSax", shared_mats["gold"], shared_mats["pearl"], shared_mats["sax_glow"], with_rings=True)
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

    _, ran_arm = _spawn_band_member(spec["cast"]["ranger"], col, "S3_Ranger", (OX + 2.95, OY - 1.35, 0.0), -48.0, 0.0)

    # VFX Schedules: Sonic Cannon (f408, f469), Knight Morph (f692), Barbarian Fire Morph (f748)
    s3_sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]] = {}
    s3_const: set[int] = set()
    s3_const |= _schedule_ballistic_burst(s3_sched, s3_shards, (OX + 0.55, OY + 0.05, 1.20), 408, 22, speed_min=5.0, speed_max=11.5, base_scale=0.11, seed=408, total_frames=total_frames)
    s3_const |= _schedule_ballistic_burst(s3_sched, s3_shards, (OX + 0.55, OY + 0.05, 1.20), 469, 22, speed_min=5.5, speed_max=12.5, base_scale=0.12, seed=469, total_frames=total_frames)
    s3_const |= _schedule_ballistic_burst(s3_sched, s3_shards[:28], (OX + 1.85, OY + 0.6, 1.15), 692, 22, speed_min=5.0, speed_max=11.5, base_scale=0.12, seed=692, total_frames=total_frames)
    s3_const |= _schedule_ballistic_burst(s3_sched, s3_shards[:28], (OX + 0.55, OY + 1.85, 1.20), 748, 16, speed_min=5.5, speed_max=12.5, base_scale=0.13, seed=748, total_frames=total_frames)
    _flush_vfx_schedule(s3_shards, s3_sched, s3_const)

    s3_r_sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]]] = {}
    s3_r_const: set[int] = set()
    for hf, dur in ((408, 24), (469, 24), (530, 14), (558, 14), (631, 16)):
        s3_r_const |= _schedule_shockwave_blast(s3_r_sched, sax_core, blast_rings, hf, dur, max_radius=3.5 if hf in (408, 469) else 2.0, max_core=0.28, total_frames=total_frames)
    s3_r_const |= _schedule_shockwave_blast(s3_r_sched, mk_core, [morph_k1, morph_k2], 692, 22, max_radius=2.9, max_core=0.25, total_frames=total_frames)
    s3_r_const |= _schedule_shockwave_blast(s3_r_sched, mb_core, [morph_b1, morph_b2], 748, 16, max_radius=3.2, max_core=0.26, total_frames=total_frames)
    _flush_ring_schedule([sax_core, *blast_rings, mk_core, morph_k1, morph_k2, mb_core, morph_b1, morph_b2], s3_r_sched, s3_r_const)

    # Frame-accurate beat-locked S3 performance
    s3_start = max(1, 408)
    s3_end = min(total_frames, 764)
    for f in range(s3_start, s3_end + 1):
        fd = frames_data[min(len(frames_data) - 1, f - 1)]
        t, mid, bass, rms, bpulse, b16 = fd["t"], fd["mid"], fd["bass"], fd["rms"], fd.get("beat_pulse", 0.0), fd["b16"]
        beat = (t - 0.2033) * bpm / 60.0
        bs = math.sin(beat * math.pi)
        bh = math.sin(beat * math.pi * 0.5)

        # Sweeping Club Light Cones + Pulsing Mahogany Floor Rings
        for ci, cc in enumerate(club_cones):
            cc.rotation_euler = (math.radians(-22.0 + 18.0 * math.sin(t * 2.5 + ci)), math.radians(20.0 * math.cos(t * 2.0 + ci * 0.9)), 0.0)
            cc.keyframe_insert("rotation_euler", frame=f)
        beam_gold_n.inputs["Strength"].default_value = 1.2 + 1.2 * bpulse
        beam_ruby_n.inputs["Strength"].default_value = 1.2 + 1.4 * bass
        beam_gold_n.inputs["Strength"].keyframe_insert("default_value", frame=f)
        beam_ruby_n.inputs["Strength"].keyframe_insert("default_value", frame=f)

        fr1 = 0.8 + 1.8 * bpulse
        fr2 = 1.4 + 2.2 * bass
        floor_ring1.scale = (fr1, fr1, 0.35)
        floor_ring2.scale = (fr2, fr2, 0.35)
        floor_ring1.keyframe_insert("scale", frame=f)
        floor_ring2.keyframe_insert("scale", frame=f)

        # DJ front 8-bar mini EQ
        for di, db in enumerate(dj_eq_bars):
            val = b16[di * 2]
            db.scale.z = 0.12 + 0.52 * val
            db.keyframe_insert("scale", frame=f)

        # Mage beat-locked Sax solo
        _kf_bone_rot(m_arm, "spine", (-15.0 * bpulse - 8.0 * mid, 15.0 * bh, 8.0 * bh), f)
        _kf_bone_rot(m_arm, "head", (4.0 + 12.0 * bpulse, 0.0, -6.0 * bh), f)
        _kf_bone_rot(m_arm, "upperarm.r", (-40.0 + 8.0 * bpulse, 0.0, 56.0), f)
        _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 74.0 + 8.0 * mid), f)
        _kf_bone_rot(m_arm, "upperarm.l", (-42.0 - 6.0 * bs, 0.0, -50.0), f)
        _kf_bone_rot(m_arm, "lowerarm.l", (0.0, 0.0, -66.0), f)
        if 530 <= f <= 665:
            m_root.location = (OX - 0.15 + 0.45 * math.sin((f - 530) * 0.06), OY - 0.45 - 0.85 * math.sin((f - 530) / 135.0 * math.pi), 0.0)
        else:
            m_root.location = (OX - 0.15, OY - 0.45, 0.0)
        m_root.keyframe_insert("location", frame=f)
        for ring in m_rings:
            rs = 0.75 + 0.95 * bpulse
            ring.scale = (rs, rs, rs)
            ring.keyframe_insert("scale", frame=f)

        # Double-Stage Knockback (f 408..438 and f 469..495)
        k1 = math.sin(min(1.0, max(0.0, (f - 408) / 30.0)) * math.pi) if 408 <= f <= 438 else 0.0
        k2 = math.sin(min(1.0, max(0.0, (f - 469) / 26.0)) * math.pi) if 469 <= f <= 495 else 0.0
        knock = max(k1, k2)
        k_root.location = (OX + 1.85 + 0.95 * knock, OY + 0.6 + 1.05 * knock, 0.0)
        b_root.location = (OX + 0.55 + 0.25 * knock, OY + 1.85 + 1.15 * knock, 0.0)
        k_root.keyframe_insert("location", frame=f)
        b_root.keyframe_insert("location", frame=f)

        _kf_bone_rot(k_arm, "spine", (-26.0 * knock + 5.0 * bpulse, -8.0 * bh, 0.0), f)
        _kf_bone_rot(b_arm, "spine", (-24.0 * knock + 7.0 * bs, 10.0 * bh, 0.0), f)
        _kf_bone_rot(k_arm, "upperarm.r", (-26.0 if f >= 692 else -48.0, 0.0, 58.0 if f >= 692 else 38.0), f)
        _kf_bone_rot(k_arm, "lowerarm.r", (0.0, 0.0, 78.0 if f >= 692 else 48.0), f)
        _kf_bone_rot(k_arm, "upperarm.l", (-54.0, 0.0, -40.0 if f < 692 else -26.0), f)
        _kf_bone_rot(k_arm, "lowerarm.l", (0.0, 0.0, -45.0), f)
        _kf_bone_rot(b_arm, "upperarm.r", (-34.0 + 24.0 * max(0.0, bs), 0.0, 48.0), f)
        _kf_bone_rot(b_arm, "lowerarm.r", (0.0, 0.0, 62.0), f)
        _kf_bone_rot(b_arm, "upperarm.l", (-34.0 + 24.0 * max(0.0, -bs), 0.0, -48.0), f)
        _kf_bone_rot(b_arm, "lowerarm.l", (0.0, 0.0, -62.0), f)

        # Weapon -> Instrument Swaps RIGHT ON EXACT IMPACT PEAKS f 692 & f 748!
        for p_old, p_new, cut in ((k_sw, k_horn, 692), (k_sh, None, 692), (b_axe, b_st_r, 748)):
            show_old = (f < cut)
            p_old.scale = (1.0, 1.0, 1.0) if show_old else (0.0, 0.0, 0.0)
            p_old.keyframe_insert("scale", frame=f)
            if p_new is not None:
                p_new.scale = (0.0, 0.0, 0.0) if show_old else (1.0, 1.0, 1.0)
                p_new.keyframe_insert("scale", frame=f)
        b_st_l.scale = (0.0, 0.0, 0.0) if f < 748 else (1.0, 1.0, 1.0)
        b_st_l.keyframe_insert("scale", frame=f)

        # Point Flash Lights on f 408, 469, 692, 748
        if 408 <= f <= 415 or 469 <= f <= 476:
            s3_flash_obj.location = (OX + 0.5, OY + 0.1, 1.4)
            s3_flash_ld.color = (1.0, 0.78, 0.20)
            s3_flash_ld.energy = 750.0
        elif 692 <= f <= 699:
            s3_flash_obj.location = (OX + 1.85, OY + 0.6, 1.4)
            s3_flash_ld.color = (0.14, 0.92, 1.0)
            s3_flash_ld.energy = 750.0
        elif 748 <= f <= 755:
            s3_flash_obj.location = (OX + 0.55, OY + 1.85, 1.5)
            s3_flash_ld.color = (1.0, 0.30, 0.10)
            s3_flash_ld.energy = 850.0
        else:
            s3_flash_ld.energy = 0.0
        s3_flash_obj.keyframe_insert("location", frame=f)
        s3_flash_ld.keyframe_insert("color", frame=f)
        s3_flash_ld.keyframe_insert("energy", frame=f)

        is_scr = 586 <= f <= 764
        s3_vinyl.rotation_euler.z = t * 4.2 + (2.0 * math.sin(t * 22.0) if is_scr else 0.0)
        s3_vinyl.keyframe_insert("rotation_euler", frame=f)
        _kf_bone_rot(r_arm, "upperarm.r", (-42.0, 0.0, 54.0 + (26.0 * math.sin(t * 18.0) if is_scr else 10.0 * bpulse)), f)
        _kf_bone_rot(r_arm, "lowerarm.r", (0.0, 0.0, 62.0), f)
        _kf_bone_rot(r_arm, "upperarm.l", (-48.0, 0.0, -32.0), f)
        _kf_bone_rot(r_arm, "lowerarm.l", (0.0, 0.0, -48.0), f)
        _kf_bone_rot(ran_arm, "upperarm.r", (-48.0 + 26.0 * bpulse, 0.0, 26.0), f)
        _kf_bone_rot(ran_arm, "lowerarm.r", (0.0, 0.0, 44.0), f)
        _kf_bone_rot(ran_arm, "upperarm.l", (-48.0 + 26.0 * abs(bh), 0.0, -26.0), f)
        _kf_bone_rot(ran_arm, "lowerarm.l", (0.0, 0.0, -44.0), f)

    _kf_constant_visibility(col, intervals, total_frames)
    return col


def _build_set4_astral(
    spec: dict[str, Any],
    shared_mats: dict[str, Any],
    vfx_meshes: dict[str, bpy.types.Mesh],
    frames_data: list[dict[str, Any]],
    intervals: list[tuple[int, int]],
    total_frames: int,
) -> bpy.types.Collection:
    """Set 4 (0, +60, 0): Enchanted Clockwork Astral Cosmos & Supernova (f 765..986)."""
    OX, OY = 0.0, 60.0
    col = bpy.data.collections.new("Set4_AstralCosmos")
    bpy.context.scene.collection.children.link(col)

    plat_m, plat_bsdf = _make_mat("S4_CloudDisk", (0.18, 0.25, 0.45, 1.0), metallic=0.3, roughness=0.22, emission_color=(0.35, 0.62, 1.0, 1.0), emission_strength=0.9)
    chime_m, chime_bsdf = _make_mat("S4_Chime", (0.65, 0.90, 1.0, 1.0), metallic=0.25, roughness=0.1, emission_color=(0.55, 0.88, 1.0, 1.0), emission_strength=4.5)
    star_m, star_bsdf = _make_mat("S4_Star", (1.0, 0.88, 0.48, 1.0), emission_color=(1.0, 0.85, 0.35, 1.0), emission_strength=5.5)
    nova_ring_m, _ = _make_mat("S4_NovaRing", (0.25, 0.82, 1.0, 1.0), emission_color=(0.22, 0.78, 1.0, 1.0), emission_strength=6.8)
    beam_astro_m, beam_astro_n = _make_beam_mat("S4_GodRay", (0.55, 0.80, 1.0), strength=1.4, max_alpha=0.065)

    # 3 Giant Tilting Golden Astrolabe Rings
    astro_rings = []
    for ri, r_rad in enumerate((4.6, 5.6, 6.6)):
        bpy.ops.mesh.primitive_torus_add(major_radius=r_rad, minor_radius=0.075, major_segments=64, minor_segments=12, location=(OX, OY + 1.5, 2.0))
        ar = _assign_to_col(bpy.context.active_object, col)
        ar.data.materials.append(shared_mats["gold"] if ri % 2 == 0 else shared_mats["brass"])
        ar.rotation_euler = (math.radians(32 * (ri + 1)), math.radians(24 * ri), 0.0)
        astro_rings.append(ar)

    # 4 Radiant God-Ray Light Cones
    for gi, gx in enumerate((-3.2, -1.1, 1.1, 3.2)):
        _spawn_light_cone(f"S4_GodRay_{gi}", vfx_meshes["cone"], col, (OX + gx, OY + 3.2, 6.8), 10.5, 1.85, beam_astro_m, rot_deg=(18.0, 0.0, -gx * 5.0))

    # 5 Floating Luminous Stepping Platforms + Brass Trim
    plat_locs = [(0.0, -0.4, 0.55), (-2.3, 0.6, 0.25), (2.2, 0.5, 0.35), (0.2, 2.3, 0.90), (-1.4, -2.0, -0.1)]
    for px, py, pz in plat_locs:
        bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.95, depth=0.14, location=(OX + px, OY + py, pz - 0.07))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(plat_m)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.96, minor_radius=0.032, location=(OX + px, OY + py, pz))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["gold"])

    # 12 Overhead Crystal Glockenspiel Prisms + 48 Stars
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

    for si in range(48):
        ang = si * 0.72
        rad = 3.2 + (si % 5) * 1.4
        st = _spawn_vfx_obj(f"S4_Star_{si}", vfx_meshes["shard"], star_m, col, loc=(OX + rad * math.cos(ang), OY + 2.0 + rad * math.sin(ang) * 0.6, -0.8 + (si % 7) * 0.9), scale=(0.08, 0.08, 0.08))

    # Supernova Blast @ f 809 (#2 LOUDEST HIT IN SONG!) & Portal Burst @ f 765
    s4_core = _spawn_vfx_obj("S4_NovaCore", vfx_meshes["core"], shared_mats["vfx_gold"], col, loc=(OX, OY + 2.2, 2.85), scale=(0.0, 0.0, 0.0))
    s4_ring1 = _spawn_vfx_obj("S4_NovaRing1", vfx_meshes["ring"], nova_ring_m, col, loc=(OX, OY + 1.5, 2.1), scale=(0.0, 0.0, 0.0), rot=(math.radians(28), math.radians(-22), 0.0))
    s4_ring2 = _spawn_vfx_obj("S4_NovaRing2", vfx_meshes["ring"], shared_mats["sax_glow"], col, loc=(OX, OY + 1.5, 2.1), scale=(0.0, 0.0, 0.0), rot=(math.radians(-35), math.radians(30), 0.5))
    s4_shards = _spawn_shard_pool("S4_NovaShard", 48, vfx_meshes["shard"], [shared_mats["vfx_cyan"], shared_mats["vfx_gold"], shared_mats["vfx_white"]], col)

    s4_sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]] = {}
    s4_const = _schedule_ballistic_burst(s4_sched, s4_shards[:24], (OX, OY - 0.4, 1.3), 765, 20, speed_min=5.0, speed_max=11.0, gravity=2.5, spread_z=(-0.4, 0.9), base_scale=0.11, seed=765, total_frames=total_frames)
    s4_const |= _schedule_ballistic_burst(s4_sched, s4_shards, (OX, OY + 1.5, 2.3), 809, 34, speed_min=6.5, speed_max=15.0, gravity=1.8, spread_z=(-0.6, 1.0), base_scale=0.13, seed=809, total_frames=total_frames)
    s4_const |= _schedule_ballistic_burst(s4_sched, s4_shards[:32], (OX, OY + 1.5, 2.3), 915, 22, speed_min=5.5, speed_max=12.5, gravity=2.0, spread_z=(-0.5, 0.95), base_scale=0.12, seed=915, total_frames=total_frames)
    _flush_vfx_schedule(s4_shards, s4_sched, s4_const)

    s4_r_sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]]] = {}
    s4_r_const = _schedule_shockwave_blast(s4_r_sched, s4_core, [s4_ring1, s4_ring2], 765, 18, max_radius=4.2, max_core=0.30, total_frames=total_frames)
    s4_r_const |= _schedule_shockwave_blast(s4_r_sched, s4_core, [s4_ring1, s4_ring2], 809, 32, max_radius=7.5, max_core=0.38, total_frames=total_frames)
    s4_r_const |= _schedule_shockwave_blast(s4_r_sched, s4_core, [s4_ring1], 915, 20, max_radius=5.2, max_core=0.30, total_frames=total_frames)
    _flush_ring_schedule([s4_core, s4_ring1, s4_ring2], s4_r_sched, s4_r_const)

    s4_flash_ld = bpy.data.lights.new("S4_NovaLight", type="POINT")
    s4_flash_ld.energy = 0.0
    s4_flash_ld.color = (0.55, 0.90, 1.0)
    s4_flash_obj = bpy.data.objects.new("S4_NovaLight", s4_flash_ld)
    s4_flash_obj.location = (OX, OY + 1.2, 2.2)
    _assign_to_col(s4_flash_obj, col)

    for lname, loc, eng, lcol in (
        ("S4_SapphireKey", (OX - 3.5, OY - 5.5, 4.5), 680.0, (0.45, 0.72, 1.0)),
        ("S4_FairyGoldRim", (OX + 3.5, OY + 2.5, 3.8), 580.0, (1.0, 0.76, 0.30)),
    ):
        ld = bpy.data.lights.new(lname, type="AREA")
        ld.size = 4.0
        ld.energy = eng
        ld.color = lcol
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((OX, OY + 0.5, 1.2)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        _assign_to_col(lo, col)

    m_root, m_arm = _spawn_band_member(spec["cast"]["mage"], col, "S4_Mage", (OX, OY - 0.4, 0.55), 0.0, 0.55)
    m_base_z = float(m_root.location.z)
    m_sax, _ = _build_saxophone(col, "S4_MageSax", shared_mats["gold"], shared_mats["pearl"])
    _attach_custom_prop(m_arm, "handslot.r", m_sax, rot_deg=(12.0, 16.0, -45.0), scale=1.22)
    _, r_arm = _spawn_band_member(spec["cast"]["rogue"], col, "S4_Rogue", (OX - 2.3, OY + 0.6, 0.25), 25.0, 0.25)
    _, k_arm = _spawn_band_member(spec["cast"]["knight"], col, "S4_Knight", (OX + 2.2, OY + 0.5, 0.35), -25.0, 0.35)
    _attach_custom_prop(k_arm, "handslot.r", _build_trumpet(col, "S4_KnightHorn", shared_mats["gold"], shared_mats["pearl"]))
    _, b_arm = _spawn_band_member(spec["cast"]["barbarian"], col, "S4_Barbarian", (OX + 0.2, OY + 2.3, 0.90), 0.0, 0.90)

    for f in range(max(1, 765), min(total_frames, 986) + 1):
        fd = frames_data[min(len(frames_data) - 1, f - 1)]
        t, high, rms, bpulse = fd["t"], fd["high"], fd["rms"], fd.get("beat_pulse", 0.0)
        vortex = max(0.0, (f - 898) / 88.0)
        lev = 0.42 * math.sin(min(1.0, max(0.0, (f - 809) / 140.0)) * math.pi)
        m_root.location.z = m_base_z + lev + 0.14 * math.sin(t * 2.5) + 0.25 * vortex
        m_root.keyframe_insert("location", frame=f)

        _kf_bone_rot(m_arm, "upperarm.r", (-64.0, 0.0, 16.0), f)
        _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 26.0), f)
        _kf_bone_rot(m_arm, "upperarm.l", (-12.0 + 30.0 * bpulse, 0.0, -48.0), f)
        _kf_bone_rot(m_arm, "lowerarm.l", (0.0, 0.0, -35.0), f)
        _kf_bone_rot(k_arm, "upperarm.r", (-34.0 + 16.0 * bpulse, 0.0, 52.0), f)
        _kf_bone_rot(k_arm, "lowerarm.r", (0.0, 0.0, 72.0), f)
        _kf_bone_rot(k_arm, "upperarm.l", (-56.0, 0.0, -24.0), f)
        _kf_bone_rot(k_arm, "lowerarm.l", (0.0, 0.0, -38.0), f)
        for arm_o in (r_arm, b_arm):
            sw = math.sin(t * 2.4)
            _kf_bone_rot(arm_o, "upperarm.r", (-58.0 + 18.0 * bpulse, 0.0, 24.0), f)
            _kf_bone_rot(arm_o, "lowerarm.r", (0.0, 0.0, 38.0), f)
            _kf_bone_rot(arm_o, "upperarm.l", (-58.0 - 18.0 * bpulse, 0.0, -24.0), f)
            _kf_bone_rot(arm_o, "lowerarm.l", (0.0, 0.0, -38.0), f)
            _kf_bone_rot(arm_o, "spine", (6.0 * math.cos(t * 2.0), 8.0 * sw, 0.0), f)

        spin_mult = 1.0 + 3.2 * vortex * vortex
        for ri, ar in enumerate(astro_rings):
            ar.rotation_euler = (
                math.radians(32 * (ri + 1)) + t * (0.25 + 0.1 * ri) * spin_mult,
                math.radians(24 * ri) + t * (0.20 - 0.1 * ri) * spin_mult,
                t * 0.18 * spin_mult * (1 if ri % 2 == 0 else -1),
            )
            ar.keyframe_insert("rotation_euler", frame=f)

        chime_bsdf.inputs["Emission Strength"].default_value = 2.0 + 10.0 * high + 6.0 * bpulse
        chime_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
        for ci, ch in enumerate(chimes):
            ch.rotation_euler.z = t * (1.2 + 2.5 * vortex) + ci
            ch.keyframe_insert("rotation_euler", frame=f)
        star_bsdf.inputs["Emission Strength"].default_value = 2.5 + 7.5 * high + 5.0 * rms
        star_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
        plat_bsdf.inputs["Emission Strength"].default_value = 0.8 + 1.8 * bpulse
        plat_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
        beam_astro_n.inputs["Strength"].default_value = 1.1 + 1.4 * rms + 1.2 * vortex
        beam_astro_n.inputs["Strength"].keyframe_insert("default_value", frame=f)

        if 809 <= f <= 820:
            s4_flash_ld.energy = 950.0 * math.exp(-(f - 809) * 0.45)
        elif f >= 942:
            s4_flash_ld.energy = 850.0 * ((f - 942) / 44.0)
        else:
            s4_flash_ld.energy = 0.0
        s4_flash_ld.keyframe_insert("energy", frame=f)

    _kf_constant_visibility(col, intervals, total_frames)
    return col


def _build_set5_ballroom(
    spec: dict[str, Any],
    shared_mats: dict[str, Any],
    vfx_meshes: dict[str, bpy.types.Mesh],
    frames_data: list[dict[str, Any]],
    bpm: float,
    intervals: list[tuple[int, int]],
    total_frames: int,
) -> bpy.types.Collection:
    """Set 5 (0, 0, 0): Grand Clockwork Ballroom Pyrotechnic Supernova Finale (f 987..1287)."""
    col = bpy.data.collections.new("Set5_ClockworkBallroom")
    bpy.context.scene.collection.children.link(col)

    dark_stage_m, _ = _make_mat("S5_StageDark", (0.025, 0.028, 0.045, 1.0), metallic=0.35, roughness=0.26)
    drum_head_m, drum_head_bsdf = _make_mat("S5_DrumHeadGlow", (0.95, 0.76, 0.35, 1.0), roughness=0.35, emission_color=(1.0, 0.58, 0.14, 1.0), emission_strength=1.5)
    mirror_m, _ = _make_mat("S5_MirrorDisco", (0.92, 0.95, 1.0, 1.0), metallic=0.96, roughness=0.10, emission_color=(0.82, 0.90, 1.0, 1.0), emission_strength=0.65)
    ring_gold_m, _ = _make_mat("S5_FloorRingGold", (1.0, 0.72, 0.14, 1.0), emission_color=(1.0, 0.68, 0.12, 1.0), emission_strength=6.5)
    ring_cyan_m, _ = _make_mat("S5_FloorRingCyan", (0.10, 0.88, 1.0, 1.0), emission_color=(0.10, 0.88, 1.0, 1.0), emission_strength=6.5)
    ring_mag_m, _ = _make_mat("S5_FloorRingMag", (1.0, 0.14, 0.68, 1.0), emission_color=(1.0, 0.14, 0.68, 1.0), emission_strength=6.5)

    beam_cyan_m, beam_cyan_n = _make_beam_mat("S5_BeamCyan", (0.10, 0.90, 1.0), strength=1.5, max_alpha=0.075)
    beam_mag_m, beam_mag_n = _make_beam_mat("S5_BeamMag", (1.0, 0.16, 0.68), strength=1.5, max_alpha=0.075)
    beam_gold_m, beam_gold_n = _make_beam_mat("S5_BeamGold", (1.0, 0.78, 0.20), strength=1.4, max_alpha=0.070)
    disco_shaft_m, _ = _make_beam_mat("S5_DiscoShaft", (0.78, 0.92, 1.0), strength=1.4, max_alpha=0.055)

    bpy.ops.mesh.primitive_plane_add(size=80.0, location=(0.0, 0.0, -0.35))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["obsidian"])

    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=4.8, depth=0.35, location=(0.0, 0.15, -0.175))
    _assign_to_col(bpy.context.active_object, col).data.materials.append(dark_stage_m)
    for rr in (4.76, 2.85):
        bpy.ops.mesh.primitive_torus_add(major_radius=rr, minor_radius=0.04, major_segments=64, location=(0.0, 0.15, 0.002))
        _assign_to_col(bpy.context.active_object, col).data.materials.append(shared_mats["brass"])

    # Raised Riser + Sunburst Rays + 3 Interlocking Clockwork Gears
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

    # 6 Sweeping Overhead Concert Laser/Spotlight Cones
    spot_cones = []
    spot_specs = [
        (-3.8, beam_cyan_m), (-2.2, beam_mag_m), (-0.8, beam_gold_m),
        (0.8, beam_gold_m), (2.2, beam_mag_m), (3.8, beam_cyan_m),
    ]
    for si, (sx, smat) in enumerate(spot_specs):
        sc_o = _spawn_light_cone(f"S5_SpotCone_{si}", vfx_meshes["cone"], col, (sx, 3.5, 5.6), 8.2, 1.55, smat, rot_deg=(-28.0, 0.0, 0.0))
        spot_cones.append(sc_o)

    # Drum Kit & DJ Console
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

    # 24-Band High-Contrast Neon EQ Wall + Floating Peak-Hold Caps!
    eq_bars, eq_caps, eq_bsdfs = [], [], []
    for i in range(24):
        frac = i / 23.0
        ang = math.radians(-70.0 + frac * 140.0)
        ex, ey = 4.42 * math.sin(ang), 0.25 + 3.55 * math.cos(ang)
        rgb = (0.08 + 0.92 * frac, 0.92 - 0.68 * max(0.0, frac - 0.45), 1.0 - 0.65 * frac)
        em, ebs = _make_mat(f"S5_EQ_{i:02d}", (*rgb, 1.0), emission_color=(*rgb, 1.0), emission_strength=3.0)
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
        bar.scale = (0.20, 0.14, 1.0)
        bar.data.materials.append(em)
        eq_bars.append(bar)
        eq_bsdfs.append(ebs)

        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(ex, ey, 1.2))
        cap = _assign_to_col(bpy.context.active_object, col)
        cap.rotation_euler = (0.0, 0.0, -ang)
        cap.scale = (0.22, 0.16, 0.08)
        cap.data.materials.append(shared_mats["flash_white"])
        eq_caps.append(cap)

    # Pulsing LED Floor Shockwave Rings
    s5_floor_r1 = _spawn_vfx_obj("S5_FloorRing1", vfx_meshes["ring"], ring_cyan_m, col, loc=(0.0, 0.15, 0.03), scale=(1.5, 1.5, 0.4))
    s5_floor_r2 = _spawn_vfx_obj("S5_FloorRing2", vfx_meshes["ring"], ring_mag_m, col, loc=(0.0, 0.15, 0.03), scale=(2.5, 2.5, 0.4))

    # Descending Mirror Disco Ball + 8 Rotating Volumetric Light Shafts (snap on @ f 1121!)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.52, location=(0.0, 0.45, 3.0))
    disco_ball = _assign_to_col(bpy.context.active_object, col)
    disco_ball.data.materials.append(mirror_m)
    for p in disco_ball.data.polygons:
        p.use_smooth = False
    disco_shafts = []
    for di in range(8):
        phi = 2.0 * math.pi * di / 8.0
        tilt = 52.0 if di % 2 == 0 else 72.0
        sh = _spawn_light_cone(f"S5_DiscoShaft_{di:02d}", vfx_meshes["cone"], col, (0.0, 0.0, 0.0), 6.2, 0.48, disco_shaft_m, rot_deg=(tilt, 0.0, math.degrees(phi)))
        sh.parent = disco_ball
        sh.scale = (0.0, 0.0, 0.0)
        disco_shafts.append(sh)

    # Stage Pyrotechnic Fountains (3 emitters x 18 = 54 shared sparks), Nuclear Firework Supernova (64 shards @ f1210), & 36 Confetti Quads!
    pyro_pool = _spawn_shard_pool("S5_Pyro", 54, vfx_meshes["shard"], [shared_mats["vfx_gold"], shared_mats["vfx_cyan"], shared_mats["vfx_magenta"]], col)
    nuke_pool = _spawn_shard_pool("S5_Nuke", 64, vfx_meshes["shard"], [shared_mats["vfx_gold"], shared_mats["vfx_cyan"], shared_mats["vfx_magenta"], shared_mats["vfx_white"]], col)
    confetti_pool = _spawn_shard_pool("S5_Confetti", 36, vfx_meshes["confetti"], [shared_mats["vfx_gold"], shared_mats["vfx_cyan"], shared_mats["vfx_magenta"]], col)

    nuke_core = _spawn_vfx_obj("S5_NukeCore", vfx_meshes["core"], shared_mats["vfx_gold"], col, loc=(0.0, 3.3, 3.65), scale=(0.0, 0.0, 0.0))
    nuke_r1 = _spawn_vfx_obj("S5_NukeRing1", vfx_meshes["ring"], ring_gold_m, col, loc=(0.0, 3.2, 3.2), scale=(0.0, 0.0, 0.0), rot=(math.radians(65), math.radians(-18), 0.0))
    nuke_r2 = _spawn_vfx_obj("S5_NukeRing2", vfx_meshes["ring"], ring_cyan_m, col, loc=(0.0, 3.2, 3.2), scale=(0.0, 0.0, 0.0), rot=(math.radians(45), math.radians(32), 0.5))
    nuke_r3 = _spawn_vfx_obj("S5_NukeRing3", vfx_meshes["ring"], ring_mag_m, col, loc=(0.0, 3.2, 3.2), scale=(0.0, 0.0, 0.0), rot=(math.radians(85), 0.0, 0.0))

    s5_sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]] = {}
    s5_const: set[int] = set()
    # Nuclear Firework Detonations at f 987, f 1121, f 1210 (#1 BIGGEST IMPACT!), f 1260
    s5_const |= _schedule_ballistic_burst(s5_sched, nuke_pool[:36], (0.0, 2.8, 3.1), 987, 24, speed_min=6.0, speed_max=13.5, gravity=6.0, spread_z=(0.1, 1.0), base_scale=0.12, seed=987, total_frames=total_frames)
    s5_const |= _schedule_ballistic_burst(s5_sched, nuke_pool[:48], (0.0, 2.5, 3.2), 1121, 28, speed_min=6.5, speed_max=15.0, gravity=5.5, spread_z=(-0.2, 1.0), base_scale=0.13, seed=1121, total_frames=total_frames)
    s5_const |= _schedule_ballistic_burst(s5_sched, nuke_pool, (0.0, 3.2, 3.4), 1210, 40, speed_min=7.5, speed_max=17.5, gravity=4.8, spread_z=(-0.35, 1.0), base_scale=0.14, seed=1210, total_frames=total_frames)
    s5_const |= _schedule_ballistic_burst(s5_sched, nuke_pool[:40], (0.0, 2.8, 3.1), 1260, 24, speed_min=5.5, speed_max=13.0, gravity=6.5, spread_z=(0.05, 1.0), base_scale=0.12, seed=1260, total_frames=total_frames)
    _flush_vfx_schedule(nuke_pool, s5_sched, s5_const)

    s5_r_sched: dict[str, dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]]] = {}
    s5_r_const = _schedule_shockwave_blast(s5_r_sched, nuke_core, [nuke_r1, nuke_r2], 987, 22, max_radius=5.2, max_core=0.35, total_frames=total_frames)
    s5_r_const |= _schedule_shockwave_blast(s5_r_sched, nuke_core, [nuke_r1, nuke_r2, nuke_r3], 1121, 26, max_radius=6.8, max_core=0.38, total_frames=total_frames)
    s5_r_const |= _schedule_shockwave_blast(s5_r_sched, nuke_core, [nuke_r1, nuke_r2, nuke_r3], 1210, 36, max_radius=8.5, max_core=0.42, total_frames=total_frames)
    s5_r_const |= _schedule_shockwave_blast(s5_r_sched, nuke_core, [nuke_r1, nuke_r2], 1260, 20, max_radius=5.8, max_core=0.35, total_frames=total_frames)
    _flush_ring_schedule([nuke_core, nuke_r1, nuke_r2, nuke_r3], s5_r_sched, s5_r_const)

    # Lights + Explosive Point Strobe
    s5_flash_ld = bpy.data.lights.new("S5_PyroLight", type="POINT")
    s5_flash_ld.energy = 0.0
    s5_flash_ld.color = (1.0, 0.85, 0.35)
    s5_flash_obj = bpy.data.objects.new("S5_PyroLight", s5_flash_ld)
    s5_flash_obj.location = (0.0, 2.2, 3.2)
    _assign_to_col(s5_flash_obj, col)

    for lname, loc, eng, lcol in (
        ("S5_WarmKey", (0.0, -5.5, 4.4), 760.0, (1.0, 0.88, 0.70)),
        ("S5_CyanRim", (-4.8, 0.2, 3.2), 480.0, (0.12, 0.85, 1.0)),
        ("S5_MagentaRim", (4.8, 0.2, 3.2), 480.0, (1.0, 0.22, 0.68)),
        ("S5_HeroSpot", (0.0, -2.0, 6.2), 1020.0, (1.0, 0.90, 0.72)),
    ):
        ld = bpy.data.lights.new(lname, type="AREA")
        ld.size = 3.2
        ld.energy = eng
        ld.color = lcol
        lo = bpy.data.objects.new(lname, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0.0, 0.5, 1.1)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        _assign_to_col(lo, col)

    # Full 5-Piece Ensemble on Set 5
    _, m_arm = _spawn_band_member(spec["cast"]["mage"], col, "S5_Mage", (-0.35, -0.58, 0.0), 0.0, 0.0)
    m_sax, m_rings = _build_saxophone(col, "S5_MageSax", shared_mats["gold"], shared_mats["pearl"], shared_mats["sax_glow"], with_rings=True)
    _attach_custom_prop(m_arm, "handslot.r", m_sax, rot_deg=(12.0, 16.0, -45.0), scale=1.22)

    _, b_arm = _spawn_band_member(spec["cast"]["barbarian"], col, "S5_Barbarian", (0.40, 2.05, 0.65), 0.0, 0.65)
    _attach_custom_prop(b_arm, "handslot.r", _build_drumstick(col, "S5_StickR", shared_mats["stick"], shared_mats["tip"]))
    _attach_custom_prop(b_arm, "handslot.l", _build_drumstick(col, "S5_StickL", shared_mats["stick"], shared_mats["tip"]))

    _, r_arm = _spawn_band_member(spec["cast"]["rogue"], col, "S5_Rogue", (-2.30, 0.25, 0.0), 28.0, 0.0)
    _, k_arm = _spawn_band_member(spec["cast"]["knight"], col, "S5_Knight", (1.95, 0.22, 0.0), -25.0, 0.0)
    _attach_custom_prop(k_arm, "handslot.r", _build_trumpet(col, "S5_KnightHorn", shared_mats["gold"], shared_mats["pearl"]))
    _, ran_arm = _spawn_band_member(spec["cast"]["ranger"], col, "S5_Ranger", (-1.35, 1.35, 0.0), 14.0, 0.0)

    peak_caps = [0.5] * 24
    fountain_origins = [(-3.2, 0.8, 0.0), (0.0, 2.8, 0.65), (3.2, 0.8, 0.0)]

    for f in range(max(1, 987), min(total_frames, 1287) + 1):
        fd = frames_data[min(len(frames_data) - 1, f - 1)]
        t, bass, mid, high, rms, bpulse, b16 = (
            fd["t"], fd["bass"], fd["mid"], fd["high"], fd["rms"], fd.get("beat_pulse", 0.0), fd["b16"]
        )
        beat = (t - 0.2033) * bpm / 60.0
        bs, bh = math.sin(beat * math.pi), math.sin(beat * math.pi * 0.5)

        if f >= 1261:
            # Theatrical ensemble bow + gentle falling golden confetti
            bu = min(1.0, (f - 1261) / 24.0)
            _kf_bone_rot(m_arm, "spine", (16.0 * math.sin(bu * math.pi * 0.8), 0.0, 0.0), f)
            _kf_bone_rot(m_arm, "head", (-10.0 * bu, 0.0, 0.0), f)
            _kf_bone_rot(m_arm, "upperarm.r", (-66.0, 0.0, 14.0), f)
            _kf_bone_rot(m_arm, "upperarm.l", (-62.0, 0.0, -40.0), f)
        else:
            _kf_bone_loc(m_arm, "hips", (0.0, -0.07 * bpulse, 0.0), f)
            _kf_bone_rot(m_arm, "spine", (-15.0 * bpulse - 6.0 * mid, 15.0 * bh, 8.0 * bh), f)
            _kf_bone_rot(m_arm, "head", (4.0 + 12.0 * bpulse, 6.0 * bh, -6.0 * bh), f)
            _kf_bone_rot(m_arm, "upperarm.r", (-40.0 + 8.0 * bpulse, 0.0, 56.0), f)
            _kf_bone_rot(m_arm, "lowerarm.r", (0.0, 0.0, 74.0 + 8.0 * mid), f)
            _kf_bone_rot(m_arm, "upperarm.l", (-42.0 - 6.0 * bs, 0.0, -50.0), f)
            _kf_bone_rot(m_arm, "lowerarm.l", (0.0, 0.0, -66.0), f)

        # Knight Trumpet + Dual Climax Jumps (f 1121..1148 & f 1210..1238)
        jz1 = 0.40 * math.sin(((f - 1121) / 27.0) * math.pi) if 1121 <= f <= 1148 else 0.0
        jz2 = 0.45 * math.sin(((f - 1210) / 28.0) * math.pi) if 1210 <= f <= 1238 else 0.0
        _kf_bone_loc(k_arm, "hips", (0.0, -0.06 * bpulse + max(jz1, jz2), 0.0), f)
        _kf_bone_rot(k_arm, "spine", (-8.0 * bpulse, -10.0 * bh, -6.0 * bh), f)
        _kf_bone_rot(k_arm, "upperarm.r", (-28.0, 0.0, 58.0), f)
        _kf_bone_rot(k_arm, "lowerarm.r", (0.0, 0.0, 78.0), f)
        _kf_bone_rot(k_arm, "upperarm.l", (-40.0 + 34.0 * bpulse, 0.0, -35.0), f)

        _kf_bone_rot(b_arm, "upperarm.r", (-34.0 + 32.0 * bpulse, 0.0, 48.0), f)
        _kf_bone_rot(b_arm, "lowerarm.r", (0.0, 0.0, 60.0 + 22.0 * bs), f)
        _kf_bone_rot(b_arm, "upperarm.l", (-34.0 + 32.0 * max(0.0, -bs), 0.0, -48.0), f)
        _kf_bone_rot(b_arm, "lowerarm.l", (0.0, 0.0, -60.0 - 22.0 * bs), f)
        _kf_bone_rot(r_arm, "upperarm.r", (-42.0, 0.0, 54.0 + 18.0 * bpulse), f)
        _kf_bone_rot(r_arm, "lowerarm.r", (0.0, 0.0, 62.0), f)
        _kf_bone_rot(ran_arm, "upperarm.r", (-10.0 + 28.0 * bpulse, 0.0, 30.0), f)
        _kf_bone_rot(ran_arm, "upperarm.l", (-10.0 + 28.0 * abs(bh), 0.0, -30.0), f)

        # Stage Gear Rotation + Concert Sweeping Cones
        ang_c = t * (0.55 if f < 1121 else 0.95)
        gear_c.rotation_euler.y = ang_c
        gear_l.rotation_euler.y = -ang_c * (16.0 / 12.0)
        gear_r.rotation_euler.y = -ang_c * (16.0 / 12.0)
        for g in (gear_c, gear_l, gear_r):
            g.keyframe_insert("rotation_euler", frame=f)

        rave_spd = 2.4 if f < 1121 else 5.2
        for si, sc_o in enumerate(spot_cones):
            sc_o.rotation_euler = (math.radians(-26.0 + 18.0 * math.sin(t * rave_spd + si * 0.9)), math.radians(24.0 * math.cos(t * rave_spd * 0.85 + si)), 0.0)
            sc_o.keyframe_insert("rotation_euler", frame=f)
        beam_cyan_n.inputs["Strength"].default_value = 1.2 + 1.4 * bpulse
        beam_mag_n.inputs["Strength"].default_value = 1.2 + 1.5 * bass
        beam_gold_n.inputs["Strength"].default_value = 1.2 + 1.3 * mid
        for bn in (beam_cyan_n, beam_mag_n, beam_gold_n):
            bn.inputs["Strength"].keyframe_insert("default_value", frame=f)

        # Kick Drum + Floor Shockwave Rings
        ks = 1.0 + 0.16 * bass + 0.08 * bpulse
        kick_head.scale = (ks, ks, 1.0 + 0.45 * bass)
        kick_head.keyframe_insert("scale", frame=f)
        drum_head_bsdf.inputs["Emission Strength"].default_value = 1.0 + 6.5 * bass + 3.0 * bpulse
        drum_head_bsdf.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)

        fr1_s = 1.6 + 2.4 * bpulse
        fr2_s = 2.6 + 2.2 * bass
        s5_floor_r1.scale = (fr1_s, fr1_s, 0.35)
        s5_floor_r2.scale = (fr2_s, fr2_s, 0.35)
        s5_floor_r1.keyframe_insert("scale", frame=f)
        s5_floor_r2.keyframe_insert("scale", frame=f)

        # 24-Band Neon EQ with Floating Peak-Hold Caps
        for bi in range(24):
            b_idx = min(15, int(bi * 16 / 24))
            next_idx = min(15, b_idx + 1)
            frac_i = (bi * 16.0 / 24.0) - b_idx
            val = b16[b_idx] * (1.0 - frac_i) + b16[next_idx] * frac_i
            h_bar = 0.35 + 3.65 * val
            peak_caps[bi] = max(h_bar + 0.16, peak_caps[bi] - 0.065)
            eq_bars[bi].scale.z = h_bar
            eq_bars[bi].keyframe_insert("scale", frame=f)
            eq_bsdfs[bi].inputs["Emission Strength"].default_value = 0.8 + 4.8 * val + 1.4 * bpulse
            eq_bsdfs[bi].inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
            eq_caps[bi].location.z = peak_caps[bi]
            eq_caps[bi].keyframe_insert("location", frame=f)

        for ring in m_rings:
            sc = (0.75 + 1.05 * bpulse + 0.3 * mid) * (1.0 if f < 1261 else 0.1)
            ring.scale = (sc, sc, sc)
            ring.keyframe_insert("scale", frame=f)

        # Disco Ball + 8 Rotating Volumetric Light Shafts on Super-Drop f 1121..1260
        disco_on = 1121 <= f <= 1260
        disco_ball.location.z = 2.80 + 0.15 * bpulse if disco_on else 4.15
        disco_ball.rotation_euler.z = t * (2.2 if disco_on else 1.1)
        disco_ball.keyframe_insert("location", frame=f)
        disco_ball.keyframe_insert("rotation_euler", frame=f)
        sh_sc = (0.48 + 0.15 * bpulse, 0.48 + 0.15 * bpulse, 6.2) if disco_on else (0.0, 0.0, 0.0)
        for sh in disco_shafts:
            sh.scale = sh_sc
            sh.keyframe_insert("scale", frame=f)

        # Stage Pyro Fountains (erupting f 987..1014 and f 1121..1260!)
        pyro_on = (987 <= f <= 1014) or (1121 <= f <= 1260)
        for pi, sp in enumerate(pyro_pool):
            fo = fountain_origins[pi // 18]
            local_i = pi % 18
            if pyro_on:
                phase = ((f - 987) * 0.085 + local_i * (1.0 / 18.0)) % 1.0
                ang_p = local_i * 2.1 + f * 0.12
                rad_p = 0.65 * phase
                pz = fo[2] + (4.4 + 1.2 * bass + 0.8 * bpulse) * phase * (1.0 - 0.55 * phase)
                sp.location = (fo[0] + rad_p * math.cos(ang_p), fo[1] + rad_p * math.sin(ang_p), pz)
                sc_p = 0.085 * math.sin(phase * math.pi) * (0.8 + 0.5 * bass)
                sp.scale = (sc_p * 0.7, sc_p * 0.7, sc_p * 2.2)
                sp.rotation_euler = (0.25 * phase, 0.25 * math.cos(ang_p), ang_p)
            else:
                sp.scale = (0.0, 0.0, 0.0)
            sp.keyframe_insert("location", frame=f)
            sp.keyframe_insert("scale", frame=f)
            sp.keyframe_insert("rotation_euler", frame=f)

        # Confetti Rain during Ensemble Bow f 1261..1287
        for ci, cf in enumerate(confetti_pool):
            if f >= 1261:
                u_c = (f - 1261) / 26.0
                cx = -3.8 + (ci % 9) * 0.95 + 0.35 * math.sin(t * 2.5 + ci)
                cy = -1.2 + (ci // 9) * 1.1 + 0.25 * math.cos(t * 2.1 + ci)
                cz = 3.8 - 3.6 * ((u_c + (ci * 0.07)) % 1.0)
                cf.location = (cx, cy, cz)
                cf.scale = (1.1, 1.1, 1.1)
                cf.rotation_euler = (t * 4.0 + ci, t * 3.0, ci * 0.8)
            else:
                cf.scale = (0.0, 0.0, 0.0)
            cf.keyframe_insert("location", frame=f)
            cf.keyframe_insert("scale", frame=f)
            cf.keyframe_insert("rotation_euler", frame=f)

        # Pyro Strobe Point Light
        if 1210 <= f <= 1220:
            s5_flash_ld.energy = 950.0 * math.exp(-(f - 1210) * 0.45)
        elif 1121 <= f <= 1128 or 987 <= f <= 994 or 1260 <= f <= 1265:
            s5_flash_ld.energy = 750.0
        else:
            s5_flash_ld.energy = 260.0 * bpulse * bass if 1121 <= f <= 1260 else 0.0
        s5_flash_ld.keyframe_insert("energy", frame=f)

    _kf_constant_visibility(col, intervals, total_frames)
    return col


def _base_camera_shot(f: int) -> tuple[tuple[float, float, float], tuple[float, float, float], float, float]:
    """Return (cam_loc, target_loc, lens_mm, dutch_deg) for 31 beat-locked cuts across 5 worlds."""
    # SET 1 (-60, 0, 0) - ACT 1: EMERALD MUSEUM HEIST (f 1..228)
    if f <= 38:
        u = (f - 1) / 37.0
        return ((-63.4 + 1.2 * u, -6.2 + 0.9 * u, 2.25 - 0.15 * u), (-60.0, 1.6, 1.45), 36.0 + 3.0 * u, 0.0)
    if f <= 111:
        u = (f - 39) / 72.0
        return ((-62.0 + 2.6 * u, -4.4 + 0.8 * u, 1.75), (-60.0, 1.8, 1.50), 42.0 + 4.0 * u, -2.5 * math.sin(u * math.pi))
    if f <= 139:
        u = (f - 112) / 27.0
        return ((-63.6 + 0.9 * u, -3.5 + 0.5 * u, 1.05), (-62.0, -0.5, 1.15), 40.0 + 3.0 * u, -4.5)
    if f <= 178:
        u = (f - 140) / 38.0
        return ((-60.6 + 2.2 * u, -4.2 + 0.6 * u, 1.65), (-60.2, 1.0, 1.35), 38.0, 3.5)
    if f <= 194:
        u = (f - 179) / 15.0
        return ((-63.0 + 1.2 * u, -5.8 + 0.3 * u, 2.20), (-60.2, 1.2, 1.35), 31.0 + 3.0 * u, -5.5)
    if f <= 228:
        u = (f - 195) / 33.0
        return ((-59.2 + 0.8 * u, -2.4, 1.15), (-59.7, 0.9, 1.25), 44.0 + 5.0 * u, 4.5)

    # SET 2 (+60, 0, 0) - ACT 2: MOONLIT ROOFTOP CHASE & CHASM LEAP (f 229..407)
    if f <= 245:
        u = (f - 229) / 16.0
        tx = 60.0 - 9.4 + 1.4 * u
        return ((tx - 2.0, -7.8, 1.85), (tx + 0.6, 0.2, 1.25), 33.0, -4.0)
    if f <= 284:
        u = (f - 246) / 38.0
        tx = 60.0 - 8.0 + 2.8 * u
        return ((tx + 0.8, -6.2, 1.20), (tx - 0.5, 0.2, 1.25), 38.0, 6.5)
    if f <= 318:
        u = (f - 285) / 33.0
        tx = 60.0 - 5.2 + 2.6 * u
        return ((tx + 3.8, -4.2, 1.35), (tx - 0.8, 0.1, 1.15), 40.0, -5.0)
    if f <= 362:
        u = (f - 319) / 43.0
        return ((60.0 - 1.6 + 3.2 * u, -9.8, 1.35), (60.0 + 0.2, 0.5, 1.95), 31.0, -3.5 + 7.0 * u)
    if f <= 384:
        u = (f - 363) / 21.0
        return ((63.8 + 1.2 * u, -5.8, 1.55), (63.4 + 1.0 * u, 0.2, 1.05), 35.0, 5.5)
    if f <= 407:
        u = (f - 385) / 22.0
        return ((66.5 - 1.0 * u, -4.4, 1.45), (68.2, 0.0, 1.25), 38.0, -4.5)

    # SET 3 (0, -60, 0) - ACTS 3 & 4: SPEAKEASY SONIC CANNON & WEAPON MORPH (f 408..764)
    if f <= 468:
        u = (f - 408) / 60.0
        return ((-2.8 + 4.4 * u, -64.8, 1.35), (0.5, -59.5, 1.25), 32.0, -5.0)
    if f <= 529:
        u = (f - 469) / 60.0
        return ((2.6 - 5.0 * u, -65.8, 1.95), (0.2, -59.5, 1.35), 32.0, 4.5)
    if f <= 585:
        u = (f - 530) / 55.0
        return ((-1.2 + 2.4 * u, -63.4, 1.18), (-0.1, -60.6, 1.20), 42.0, -3.0)
    if f <= 630:
        u = (f - 586) / 44.0
        return ((-3.8 + 1.2 * u, -62.2, 1.45), (-2.2, -59.2, 1.10), 44.0, 5.0)
    if f <= 691:
        u = (f - 631) / 60.0
        return ((2.6 - 4.8 * u, -65.5, 2.05), (0.2, -59.6, 1.30), 35.0, 0.0)
    if f <= 725:
        u = (f - 692) / 33.0
        return ((0.4 + 0.8 * u, -64.4, 1.48), (1.5, -59.6, 1.18), 38.0, -4.5)
    if f <= 764:
        u = (f - 726) / 38.0
        return ((-0.8 + 1.8 * u, -63.6, 1.55), (0.55, -58.2, 1.20), 40.0, 6.0)

    # SET 4 (0, +60, 0) - ACT 5: ASTRAL COSMOS & SUPERNOVA (f 765..986)
    if f <= 808:
        u = (f - 765) / 43.0
        return ((-4.2 + 3.2 * u, 52.8, 2.55), (0.0, 60.5, 1.60), 30.0, 0.0)
    if f <= 897:
        u = (f - 809) / 88.0
        ang = math.radians(-26.0 + 52.0 * u)
        return ((7.6 * math.sin(ang), 60.0 - 7.6 * math.cos(ang), 2.35 + 0.9 * math.sin(u * math.pi)), (0.0, 60.6, 1.85), 29.0, 4.5 * math.sin(u * 2 * math.pi))
    if f <= 986:
        u = (f - 898) / 88.0
        ang = math.radians(26.0 - 38.0 * u)
        rad = 7.2 - 1.8 * u
        return ((rad * math.sin(ang), 60.0 - rad * math.cos(ang), 2.80 - 0.6 * u), (0.0, 60.5, 1.65), 31.0 + 8.0 * u, -5.0 * u)

    # SET 5 (0, 0, 0) - ACT 6 & ACT 7: PYROTECHNIC CLOCKWORK BALLROOM FINALE (f 987..1287)
    if f <= 1014:
        u = (f - 987) / 27.0
        return ((0.0, -7.8 + 1.2 * u, 2.35), (0.0, 0.6, 1.50), 30.0, 0.0)
    if f <= 1042:
        u = (f - 1015) / 27.0
        return ((1.2 - 2.4 * u, -3.1, 1.25), (-0.35, -0.5, 1.20), 43.0, -4.5)
    if f <= 1076:
        u = (f - 1043) / 33.0
        return ((3.2 - 1.4 * u, -3.8, 1.65), (1.1, 1.1, 1.30), 39.0, 5.0)
    if f <= 1120:
        u = (f - 1077) / 43.0
        return ((-3.6 + 1.0 * u, -3.4, 2.15), (-1.4, 0.5, 1.15), 37.0, -4.0)
    if f <= 1165:
        u = (f - 1121) / 44.0
        ang = math.radians(-22.0 + 44.0 * u)
        return ((7.2 * math.sin(ang), 0.1 - 7.2 * math.cos(ang), 2.65 - 0.4 * u), (0.0, 0.65, 1.55), 31.0, 5.5)
    if f <= 1209:
        u = (f - 1166) / 43.0
        return ((-2.4 + 4.8 * u, -4.2, 1.25), (0.1, 0.5, 1.35), 36.0, -5.5)
    if f <= 1260:
        u = (f - 1210) / 50.0
        ang = math.radians(-38.0 + 76.0 * u)
        rad = 7.6 - 1.1 * math.sin(u * math.pi)
        return ((rad * math.sin(ang), 0.1 - rad * math.cos(ang), 2.05 + 1.05 * math.sin(u * math.pi)), (0.0, 0.75, 1.65), 29.0, 7.5 * math.cos(u * math.pi))
    if f <= 1287:
        u = (f - 1261) / 26.0
        return ((0.0, -6.4 - 1.0 * u, 1.95 + 0.45 * u), (0.0, 0.45, 1.30), 36.0, 0.0)

    # SET 1 (-60, 0, 0) - ACT 7 EPILOGUE: GOLDEN VINYL & EIGHTH-NOTE CALLING CARD (f 1288..end)
    u = (f - 1288) / max(1, 1386 - 1288)
    return ((-61.4 + 2.2 * u, -1.8, 1.95 + 0.35 * u), (-60.0, 1.8, 1.48), 42.0 + 5.0 * u, 0.0)


def _prebake_impact_envelopes(frames_data: list[dict[str, Any]], total_frames: int) -> list[dict[str, Any]]:
    """Combine explicit musical hits with strong FFT impacts to prebake flash/shake/chroma per frame."""
    hits: dict[int, tuple[float, float, float]] = {k: v for k, v in EXPLOSIVE_HITS.items() if 1 <= k <= total_frames}
    for fd in frames_data:
        fno = int(fd["f"])
        if fno >= 1288:
            continue
        imp = float(fd.get("impact", 0.0))
        if imp > 0.72 and all(abs(fno - hk) >= 6 for hk in hits):
            hits[fno] = (0.30 * imp, 0.09 * imp, 0.012 * imp)

    hit_items = sorted(hits.items())
    out: list[dict[str, Any]] = []
    for f in range(1, total_frames + 1):
        fd = frames_data[min(len(frames_data) - 1, f - 1)]
        flash_ev = 0.0
        sx = sy = sz = 0.0
        chroma = 0.0
        for hf, (fev, samp, cdisp) in hit_items:
            age = f - hf
            if 0 <= age <= 14:
                flash_ev += fev * math.exp(-age * 1.1)
                damp = samp * math.exp(-age * 0.42)
                sx += damp * math.sin(f * 13.7 + hf)
                sy += damp * math.cos(f * 19.3 + hf)
                sz += damp * math.sin(f * 23.1 + hf) * 0.75
                if age <= 3:
                    chroma = max(chroma, cdisp * math.exp(-age * 0.85))
        bpulse = float(fd.get("beat_pulse", 0.0))
        bass = float(fd["bass"])
        out.append({
            "f": f,
            "flash_ev": min(0.58, flash_ev + 0.12 * bpulse * bass),
            "shake": (sx, sy, sz),
            "chroma": min(0.032, chroma),
            "bpulse": bpulse,
            "bass": bass,
            "rms": float(fd["rms"]),
        })
    return out


def build_music_video_scene(spec: dict[str, Any]) -> dict[str, Any]:
    _clear_scene_safely()
    scene = bpy.context.scene
    analysis = spec["analysis"]
    frames_data = analysis["frames"]
    total_frames = int(analysis["total_frames"])
    bpm = float(analysis.get("estimated_bpm", 129.14))
    intervals_map = _compute_set_intervals(total_frames)

    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.render.fps = int(analysis.get("fps", 24))

    # Shared PBR & Emissive VFX Library
    gold_m, _ = _make_mat("Shared_Gold", (0.94, 0.68, 0.20, 1.0), metallic=0.90, roughness=0.28)
    brass_m, _ = _make_mat("Shared_Brass", (0.82, 0.56, 0.18, 1.0), metallic=0.88, roughness=0.36)
    pearl_m, _ = _make_mat("Shared_Pearl", (0.95, 0.94, 0.90, 1.0), metallic=0.1, roughness=0.2)
    obs_m, _ = _make_mat("Shared_Obsidian", (0.02, 0.022, 0.032, 1.0), metallic=0.2, roughness=0.18)
    sax_glow_m, _ = _make_mat("Shared_SaxGlow", (1.0, 0.82, 0.26, 1.0), emission_color=(1.0, 0.78, 0.20, 1.0), emission_strength=6.5)
    dj_neon_m, _ = _make_mat("Shared_DJNeon", (0.10, 0.94, 1.0, 1.0), emission_color=(0.12, 0.92, 1.0, 1.0), emission_strength=6.0)
    stick_m, _ = _make_mat("Shared_Stick", (0.78, 0.56, 0.28, 1.0), roughness=0.4)
    tip_m, _ = _make_mat("Shared_StickTip", (1.0, 0.85, 0.3, 1.0), emission_color=(1.0, 0.58, 0.12, 1.0), emission_strength=6.0)

    vfx_gold_m, _ = _make_mat("Shared_VFXGold", (1.0, 0.72, 0.14, 1.0), emission_color=(1.0, 0.68, 0.12, 1.0), emission_strength=6.8)
    vfx_cyan_m, _ = _make_mat("Shared_VFXCyan", (0.10, 0.90, 1.0, 1.0), emission_color=(0.10, 0.88, 1.0, 1.0), emission_strength=7.2)
    vfx_mag_m, _ = _make_mat("Shared_VFXMag", (1.0, 0.14, 0.68, 1.0), emission_color=(1.0, 0.14, 0.68, 1.0), emission_strength=7.0)
    vfx_white_m, _ = _make_mat("Shared_VFXWhite", (1.0, 0.96, 0.84, 1.0), emission_color=(1.0, 0.92, 0.78, 1.0), emission_strength=7.5)

    shared_mats = {
        "gold": gold_m, "brass": brass_m, "pearl": pearl_m, "obsidian": obs_m,
        "sax_glow": sax_glow_m, "dj_neon": dj_neon_m, "stick": stick_m, "tip": tip_m,
        "vfx_gold": vfx_gold_m, "vfx_cyan": vfx_cyan_m, "vfx_magenta": vfx_mag_m,
        "vfx_white": vfx_white_m, "flash_white": vfx_white_m,
    }

    vfx_meshes = _create_shared_vfx_meshes()
    acts_basic = _import_donor_actions(spec["cast"]["rig_medium_movementbasic"])

    _build_set1_museum(spec, acts_basic, shared_mats, vfx_meshes, frames_data, intervals_map["set1"], total_frames)
    _build_set2_rooftop(spec, acts_basic, shared_mats, vfx_meshes, frames_data, intervals_map["set2"], total_frames)
    _build_set3_speakeasy(spec, shared_mats, vfx_meshes, frames_data, bpm, intervals_map["set3"], total_frames)
    _build_set4_astral(spec, shared_mats, vfx_meshes, frames_data, intervals_map["set4"], total_frames)
    _build_set5_ballroom(spec, shared_mats, vfx_meshes, frames_data, bpm, intervals_map["set5"], total_frames)

    # Dynamic World Color per Act (CONSTANT shifts right on bar/act downbeats)
    world = bpy.data.worlds.new("Heist_World")
    scene.world = world
    world.use_nodes = True
    wbg = world.node_tree.nodes.get("Background")
    world_palettes = [
        (1, (0.010, 0.028, 0.022, 1.0), 0.72),
        (229, (0.010, 0.015, 0.048, 1.0), 0.82),
        (408, (0.032, 0.010, 0.016, 1.0), 0.72),
        (765, (0.008, 0.016, 0.058, 1.0), 0.88),
        (987, (0.014, 0.016, 0.038, 1.0), 0.74),
        (1288, (0.010, 0.028, 0.022, 1.0), 0.72),
    ]
    for wf, wcol, wstr in world_palettes:
        if wf <= total_frames:
            wbg.inputs["Color"].default_value = wcol
            wbg.inputs["Color"].keyframe_insert("default_value", frame=wf)
            wbg.inputs["Strength"].default_value = wstr
            wbg.inputs["Strength"].keyframe_insert("default_value", frame=wf)
    if world.node_tree.animation_data and world.node_tree.animation_data.action:
        for fc in _iter_action_fcurves(world.node_tree.animation_data.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"

    # Pre-baked Impact Envelopes -> Every-Frame Camera + Impact Shake + Dutch Tilt + Exposure + Compositor!
    env_frames = _prebake_impact_envelopes(frames_data, total_frames)

    # Tracked Camera Rig with Child Director Camera for real Dutch Tilt
    cam_col = bpy.data.collections.new("Heist_CameraRig")
    scene.collection.children.link(cam_col)
    cam_target = bpy.data.objects.new("Camera_Target", None)
    cam_target.location = (-60.0, 1.6, 1.45)
    cam_col.objects.link(cam_target)

    cam_rig = bpy.data.objects.new("Camera_Rig", None)
    cam_rig.empty_display_type = "ARROWS"
    cam_col.objects.link(cam_rig)
    tr = cam_rig.constraints.new(type="TRACK_TO")
    tr.target = cam_target
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"

    cam_data = bpy.data.cameras.new("Director_Camera")
    cam_data.clip_start = 0.05
    cam_data.clip_end = 180.0
    cam_obj = bpy.data.objects.new("Director_Camera", cam_data)
    cam_col.objects.link(cam_obj)
    cam_obj.parent = cam_rig
    cam_obj.location = (0.0, 0.0, 0.0)
    cam_obj.rotation_mode = "XYZ"
    scene.camera = cam_obj

    # Compositor: Bloom + Anamorphic Streaks + Impact Chromatic Dispersion
    ng = bpy.data.node_groups.new("HeistCompositor", "CompositorNodeTree")
    if hasattr(ng, "interface"):
        ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers")

    bloom = ng.nodes.new("CompositorNodeGlare")
    bloom.inputs["Type"].default_value = "Bloom"
    bloom.inputs["Quality"].default_value = "High"
    bloom.inputs["Threshold"].default_value = 1.25
    bloom.inputs["Strength"].default_value = 0.30
    bloom.inputs["Size"].default_value = 5.2

    streaks = ng.nodes.new("CompositorNodeGlare")
    streaks.inputs["Type"].default_value = "Streaks"
    streaks.inputs["Quality"].default_value = "Medium"
    streaks.inputs["Threshold"].default_value = 1.80
    streaks.inputs["Streaks"].default_value = 2
    streaks.inputs["Streaks Angle"].default_value = 0.0
    streaks.inputs["Fade"].default_value = 0.88
    streaks.inputs["Color Modulation"].default_value = 0.22
    streaks.inputs["Strength"].default_value = 0.03

    lensd = ng.nodes.new("CompositorNodeLensdist")
    lensd.inputs["Distortion"].default_value = 0.0
    lensd.inputs["Dispersion"].default_value = 0.0
    lensd.inputs["Fit"].default_value = True

    out_n = ng.nodes.new("NodeGroupOutput")
    ng.links.new(rl.outputs["Image"], bloom.inputs["Image"])
    ng.links.new(bloom.outputs["Image"], streaks.inputs["Image"])
    ng.links.new(streaks.outputs["Image"], lensd.inputs["Image"])
    ng.links.new(lensd.outputs["Image"], out_n.inputs["Image"])
    if hasattr(scene, "compositing_node_group"):
        scene.compositing_node_group = ng

    cut_starts = {c for c in CUT_STARTS if 1 <= c <= total_frames}
    cut_ends = {cs - 1 for cs in cut_starts if cs > 1}

    for f in range(1, total_frames + 1):
        ev = env_frames[f - 1]
        cloc, tloc, lens, dutch_deg = _base_camera_shot(f)
        sx, sy, sz = ev["shake"]
        zoom_punch = (3.6 * ev["bpulse"] * ev["bass"]) + (4.2 * min(1.0, ev["flash_ev"]))
        if f >= 1288:
            zoom_punch *= 0.25

        cam_rig.location = (cloc[0] + sx, cloc[1] + sy, cloc[2] + sz)
        cam_target.location = (tloc[0] + sx * 0.45, tloc[1] + sy * 0.45, tloc[2] + sz * 0.45)
        cam_data.lens = max(24.0, lens - zoom_punch)
        cam_obj.rotation_euler = (0.0, 0.0, math.radians(dutch_deg))

        cam_rig.keyframe_insert("location", frame=f)
        cam_target.keyframe_insert("location", frame=f)
        cam_data.keyframe_insert("lens", frame=f)
        cam_obj.keyframe_insert("rotation_euler", frame=f)

        # Exposure Flash + Smooth Curtain Fade-In (f1..14) and Audio-Matched Fade-Out (f1346..1376)
        if f <= 14:
            exp_v = -6.5 * (1.0 - (f - 1) / 13.0)
        elif f >= 1346:
            exp_v = -8.0 * min(1.0, (f - 1346) / 30.0)
        else:
            exp_v = ev["flash_ev"]
        scene.view_settings.exposure = exp_v
        scene.view_settings.keyframe_insert("exposure", frame=f)

        bloom.inputs["Strength"].default_value = min(0.54, 0.30 + 0.12 * ev["bass"] + 0.22 * ev["flash_ev"])
        bloom.inputs["Strength"].keyframe_insert("default_value", frame=f)
        streaks.inputs["Strength"].default_value = min(0.22, 0.03 + 0.26 * ev["flash_ev"])
        streaks.inputs["Strength"].keyframe_insert("default_value", frame=f)
        lensd.inputs["Dispersion"].default_value = ev["chroma"]
        lensd.inputs["Dispersion"].keyframe_insert("default_value", frame=f)

    for obj_anim in (cam_rig, cam_target, cam_data, cam_obj, scene):
        _set_constant_at_frames(obj_anim, "*", cut_ends)

    # EEVEE Metal-Fast Settings + AgX
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

    blend_path = spec["blend_path"]
    os.makedirs(os.path.dirname(blend_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    return {
        "blend_path": blend_path,
        "total_frames": total_frames,
        "estimated_bpm": bpm,
        "beat_offset_s": float(analysis.get("beat_offset_s", 0.2033)),
        "sets": 5,
        "cuts": len(cut_starts),
        "armatures": sum(1 for o in bpy.data.objects if o.type == "ARMATURE"),
        "mesh_count": sum(1 for o in bpy.data.objects if o.type == "MESH"),
    }


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1 :]
    spec_data = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    summary = build_music_video_scene(spec_data)
    print("MUSIC_VIDEO_BUILD_JSON:" + json.dumps(summary))
