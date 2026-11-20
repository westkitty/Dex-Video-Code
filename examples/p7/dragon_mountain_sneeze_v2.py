"""Optimized Dragon on Mountain Sneezing Fire scene for Blender 5.2+ (P7 reference).

Exercises all scene-level rendering & performance upgrades from
scripts/blender_render_pipeline.py:
- Cycles Metal GPU + adaptive sampling + OIDN hero rendering
- CompositorNodeDenoise (Albedo + Normal) -> Mist Pass depth blend -> Bloom Glare
- Principled Volume fire & smoke domain (zero stacked BLENDED alpha spheres)
- Single-object Geometry Nodes ember burst system
- Physical Sky (MULTIPLE_SCATTERING) + Blender 5.x Light Linking
- Procedural Ambient Occlusion + Pointiness edge wear
- Motion blur, shadow-map culling on VFX/distant peaks, Subsurf/Decimate LOD, --resume
"""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector, noise

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import blender_render_pipeline as brp  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _has_symlink(path: Path) -> bool:
    cur = Path(path.anchor or "/")
    for part in path.parts[1:]:
        cur = cur / part
        try:
            if stat.S_ISLNK(cur.lstat().st_mode):
                return True
        except FileNotFoundError:
            return False
    return False


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", choices=("interaction", "preview", "master", "hero"), default="preview")
    parser.add_argument("--engine", choices=("eevee", "cycles_metal"), default="eevee")
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--color-depth", choices=("8", "16"), default="8")
    parser.add_argument("--start-frame", type=int, default=26)
    parser.add_argument("--end-frame", type=int, default=26)
    parser.add_argument("--save-blend", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-motion-blur", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.output_root).expanduser().resolve()
    out = Path(args.output_dir).expanduser().resolve()
    if _has_symlink(root) or _has_symlink(out):
        raise SystemExit("Refusing symlink in output path")
    if root == out or root not in out.parents:
        raise SystemExit("output-dir must be a child of output-root")
    if args.start_frame < 1 or args.end_frame > 48 or args.end_frame < args.start_frame:
        raise SystemExit("frame range must be within 1..48")
    if args.end_frame - args.start_frame + 1 > 48:
        raise SystemExit("each invocation is limited to 48 frames")
    out.mkdir(parents=True, exist_ok=True)
    return args, root, out


def set_smooth(obj: bpy.types.Object) -> None:
    if obj.type == "MESH":
        for poly in obj.data.polygons:
            poly.use_smooth = True


def add_subsurf(obj: bpy.types.Object, levels: int = 1, render_levels: int = 2) -> None:
    mod = obj.modifiers.new("Subsurf", "SUBSURF")
    mod.levels = levels
    mod.render_levels = render_levels


def key_lrs(obj: bpy.types.Object, frame: int, loc=None, rot_deg=None, scale=None) -> None:
    if loc is not None:
        obj.location = Vector(loc)
        obj.keyframe_insert(data_path="location", frame=frame)
    if rot_deg is not None:
        obj.rotation_euler = Euler([math.radians(a) for a in rot_deg], "XYZ")
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = Vector(scale)
        obj.keyframe_insert(data_path="scale", frame=frame)


def create_uv_sphere(name, radius, location, segments=12, rings=8, material=None, parent=None) -> bpy.types.Object:
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = Vector(location)
    bpy.context.collection.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    set_smooth(obj)
    if parent:
        obj.parent = parent
    return obj


def create_lofted_mesh(name, rings, segments=16, material=None, parent=None, render_levels=2) -> bpy.types.Object:
    bm = bmesh.new()
    ring_verts = []
    for center, tangent, rx, rz in rings:
        t = tangent.normalized()
        up_ref = Vector((0.0, 0.0, 1.0)) if abs(t.z) < 0.92 else Vector((0.0, 1.0, 0.0))
        right = t.cross(up_ref).normalized()
        up = right.cross(t).normalized()
        verts = []
        for i in range(segments):
            ang = 2.0 * math.pi * i / segments
            verts.append(bm.verts.new(center + right * (math.cos(ang) * rx) + up * (math.sin(ang) * rz)))
        ring_verts.append(verts)
    for r_idx in range(len(ring_verts) - 1):
        r0, r1 = ring_verts[r_idx], ring_verts[r_idx + 1]
        for i in range(segments):
            j = (i + 1) % segments
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    bm.faces.new(list(reversed(ring_verts[0])))
    bm.faces.new(ring_verts[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    set_smooth(obj)
    if render_levels > 0:
        add_subsurf(obj, levels=min(1, render_levels), render_levels=render_levels)
    if parent:
        obj.parent = parent
    return obj


def add_spike(name, parent, base_pos, tip_dir, base_radius, length, material) -> bpy.types.Object:
    d = tip_dir.normalized()
    mid = base_pos + d * (length * 0.52) + Vector((-0.10 * length, 0.0, 0.06 * length))
    tip = base_pos + d * length + Vector((-0.24 * length, 0.0, 0.10 * length))
    return create_lofted_mesh(
        name,
        [
            (base_pos, d, base_radius, base_radius * 0.58),
            (mid, (tip - mid).normalized(), base_radius * 0.48, base_radius * 0.30),
            (tip, (tip - mid).normalized(), 0.006, 0.006),
        ],
        segments=10,
        material=material,
        parent=parent,
        render_levels=1,
    )


def build_materials() -> dict[str, bpy.types.Material]:
    mats: dict[str, bpy.types.Material] = {}

    # Iridescent scales with Voronoi bump + AO/Pointiness edge wear
    scale_mat = bpy.data.materials.new("Dragon_Scales_V2")
    scale_mat.use_nodes = True
    nt = scale_mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    tex_c = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = 28.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.40
    bump.inputs["Distance"].default_value = 0.03
    bsdf.inputs["Base Color"].default_value = (0.045, 0.155, 0.105, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.28
    bsdf.inputs["Roughness"].default_value = 0.42
    nt.links.new(tex_c.outputs["Object"], vor.inputs["Vector"])
    nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    brp.add_procedural_edge_wear_and_ao(scale_mat, ao_distance=0.45, crevice_darkening=0.42, wear_color=(0.35, 0.42, 0.30, 1.0), wear_strength=0.20)
    mats["scales"] = scale_mat

    belly_mat = bpy.data.materials.new("Dragon_Belly_V2")
    belly_mat.use_nodes = True
    bs_b = belly_mat.node_tree.nodes.get("Principled BSDF")
    bs_b.inputs["Base Color"].default_value = (0.34, 0.24, 0.12, 1.0)
    bs_b.inputs["Metallic"].default_value = 0.22
    bs_b.inputs["Roughness"].default_value = 0.38
    brp.add_procedural_edge_wear_and_ao(belly_mat, ao_distance=0.35, crevice_darkening=0.35, wear_strength=0.18)
    mats["belly"] = belly_mat

    horn_mat = bpy.data.materials.new("Dragon_Horn_V2")
    horn_mat.use_nodes = True
    bs_h = horn_mat.node_tree.nodes.get("Principled BSDF")
    bs_h.inputs["Base Color"].default_value = (0.64, 0.54, 0.40, 1.0)
    bs_h.inputs["Roughness"].default_value = 0.26
    brp.add_procedural_edge_wear_and_ao(horn_mat, ao_distance=0.30, crevice_darkening=0.45, wear_color=(0.82, 0.78, 0.70, 1.0), wear_strength=0.24)
    mats["horn"] = horn_mat

    wing_mat = bpy.data.materials.new("Dragon_Wing_V2")
    wing_mat.use_nodes = True
    nt = wing_mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    mix_s = nt.nodes.new("ShaderNodeMixShader")
    mix_s.inputs["Fac"].default_value = 0.42
    bs_w = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bs_w.inputs["Base Color"].default_value = (0.32, 0.070, 0.042, 1.0)
    bs_w.inputs["Roughness"].default_value = 0.40
    tr = nt.nodes.new("ShaderNodeBsdfTranslucent")
    tr.inputs["Color"].default_value = (0.88, 0.24, 0.08, 1.0)
    nt.links.new(bs_w.outputs["BSDF"], mix_s.inputs[1])
    nt.links.new(tr.outputs["BSDF"], mix_s.inputs[2])
    nt.links.new(mix_s.outputs["Shader"], out.inputs["Surface"])
    mats["wing"] = wing_mat

    eye_mat = bpy.data.materials.new("Dragon_Eye_V2")
    eye_mat.use_nodes = True
    bs_e = eye_mat.node_tree.nodes.get("Principled BSDF")
    bs_e.inputs["Base Color"].default_value = (1.0, 0.65, 0.08, 1.0)
    bs_e.inputs["Emission Color"].default_value = (1.0, 0.54, 0.04, 1.0)
    bs_e.inputs["Emission Strength"].default_value = 9.0
    mats["eye"] = eye_mat

    throat_mat = bpy.data.materials.new("Dragon_Throat_V2")
    throat_mat.use_nodes = True
    bs_t = throat_mat.node_tree.nodes.get("Principled BSDF")
    bs_t.inputs["Base Color"].default_value = (1.0, 0.45, 0.05, 1.0)
    bs_t.inputs["Emission Color"].default_value = (1.0, 0.46, 0.05, 1.0)
    bs_t.inputs["Emission Strength"].default_value = 12.0
    mats["throat"] = throat_mat

    # Granite rock + upward-slope snow mask with AO crevice darkening
    mtn_mat = bpy.data.materials.new("Mountain_Rock_Snow_V2")
    mtn_mat.use_nodes = True
    nt = mtn_mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    geom = nt.nodes.new("ShaderNodeNewGeometry")
    sep_n = nt.nodes.new("ShaderNodeSeparateXYZ")
    sep_p = nt.nodes.new("ShaderNodeSeparateXYZ")
    noise_m = nt.nodes.new("ShaderNodeTexNoise")
    noise_m.inputs["Scale"].default_value = 2.0
    noise_m.inputs["Detail"].default_value = 7.0
    h_clamp = nt.nodes.new("ShaderNodeMapRange")
    h_clamp.inputs["From Min"].default_value = 0.5
    h_clamp.inputs["From Max"].default_value = 5.5
    h_clamp.inputs["To Min"].default_value = -0.18
    h_clamp.inputs["To Max"].default_value = 0.14
    add_n = nt.nodes.new("ShaderNodeMath")
    add_n.operation = "ADD"
    n_shift = nt.nodes.new("ShaderNodeMath")
    n_shift.operation = "MULTIPLY_ADD"
    n_shift.inputs[1].default_value = 0.45
    n_shift.inputs[2].default_value = -0.22
    add_noise = nt.nodes.new("ShaderNodeMath")
    add_noise.operation = "ADD"
    snow_ramp = nt.nodes.new("ShaderNodeValToRGB")
    snow_ramp.color_ramp.elements[0].position = 0.72
    snow_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    snow_ramp.color_ramp.elements[1].position = 0.84
    snow_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    rock_bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    rock_bsdf.inputs["Base Color"].default_value = (0.075, 0.080, 0.098, 1.0)
    rock_bsdf.inputs["Roughness"].default_value = 0.86
    snow_bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    snow_bsdf.inputs["Base Color"].default_value = (0.76, 0.84, 0.96, 1.0)
    snow_bsdf.inputs["Roughness"].default_value = 0.40
    if "Subsurface Weight" in snow_bsdf.inputs:
        snow_bsdf.inputs["Subsurface Weight"].default_value = 0.18
    mix_m = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(geom.outputs["Normal"], sep_n.inputs["Vector"])
    nt.links.new(geom.outputs["Position"], sep_p.inputs["Vector"])
    nt.links.new(geom.outputs["Position"], noise_m.inputs["Vector"])
    nt.links.new(sep_p.outputs["Z"], h_clamp.inputs["Value"])
    nt.links.new(sep_n.outputs["Z"], add_n.inputs[0])
    nt.links.new(h_clamp.outputs["Result"], add_n.inputs[1])
    nt.links.new(noise_m.outputs["Fac"], n_shift.inputs[0])
    nt.links.new(add_n.outputs["Value"], add_noise.inputs[0])
    nt.links.new(n_shift.outputs["Value"], add_noise.inputs[1])
    nt.links.new(add_noise.outputs["Value"], snow_ramp.inputs["Fac"])
    nt.links.new(snow_ramp.outputs["Color"], mix_m.inputs["Fac"])
    nt.links.new(rock_bsdf.outputs["BSDF"], mix_m.inputs[1])
    nt.links.new(snow_bsdf.outputs["BSDF"], mix_m.inputs[2])
    nt.links.new(mix_m.outputs["Shader"], out.inputs["Surface"])
    mats["mountain"] = mtn_mat

    bg_mat = bpy.data.materials.new("Distant_Peak_V2")
    bg_mat.use_nodes = True
    bs_bg = bg_mat.node_tree.nodes.get("Principled BSDF")
    bs_bg.inputs["Base Color"].default_value = (0.055, 0.070, 0.115, 1.0)
    bs_bg.inputs["Roughness"].default_value = 0.90
    mats["distant_peak"] = bg_mat

    # Volumetric fire & smoke shader (replaces stacked BLENDED spheres!)
    mats["volumetric_fire"] = brp.build_volumetric_fire_material(
        "Volumetric_Fire_V2",
        bpy_module=bpy,
        temperature_k=2600.0,
        blackbody_intensity=5.2,
        density_scale=3.0,
        noise_scale=3.4,
    )

    spark_mat = bpy.data.materials.new("Fire_Sparks_V2")
    spark_mat.use_nodes = True
    bs_sp = spark_mat.node_tree.nodes.get("Principled BSDF")
    bs_sp.inputs["Base Color"].default_value = (1.0, 0.58, 0.08, 1.0)
    bs_sp.inputs["Emission Color"].default_value = (1.0, 0.48, 0.05, 1.0)
    bs_sp.inputs["Emission Strength"].default_value = 10.5
    mats["spark"] = spark_mat
    return mats


def build_mountain(mats: dict[str, bpy.types.Material]) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=96, y_segments=96, size=20.0)
    for v in bm.verts:
        x, y = v.co.x, v.co.y
        r = math.hypot(x * 0.90, y * 1.02)
        if r < 1.95:
            base_z = 5.02 - 0.14 * (r / 1.95) ** 2
            ridge = 0.08 * noise.noise(Vector((x * 1.6, y * 1.6, 2.1)))
        else:
            t = r - 1.95
            base_z = 4.88 - 0.68 * t - 0.015 * (t ** 2)
            ang = math.atan2(y, x)
            rib = abs(math.sin(ang * 6.0 + 0.7 * math.sin(t * 0.55))) * min(1.0, t / 2.2)
            mf = noise.ridged_multi_fractal(Vector((x * 0.34 + 3.1, y * 0.34 - 1.7, 0.4)), 1.0, 2.1, 4, 1.0, 1.9)
            ridge = 1.65 * rib + 1.15 * (mf - 0.55) * min(1.0, t / 1.8)
            if y < -1.6:
                front_fade = min(1.0, (-1.6 - y) / 3.5)
                base_z -= 0.75 * front_fade
                ridge *= (1.0 - 0.55 * front_fade)
        v.co.z = base_z + ridge
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    m = bpy.data.meshes.new("Mountain_Summit_V2_Mesh")
    bm.to_mesh(m)
    bm.free()
    summit = bpy.data.objects.new("Mountain_Summit_V2", m)
    summit.data.materials.append(mats["mountain"])
    set_smooth(summit)
    bpy.context.collection.objects.link(summit)

    distant_peaks: list[bpy.types.Object] = []
    for idx, (cx, cy, cz, sx, sy, height, seed) in enumerate([
        (-28.0, 42.0, -5.5, 22.0, 16.0, 18.0, 4.2),
        (4.0, 52.0, -6.5, 28.0, 18.0, 21.0, 9.8),
        (34.0, 40.0, -5.5, 22.0, 15.0, 17.0, 15.1),
    ]):
        bm_d = bmesh.new()
        bmesh.ops.create_grid(bm_d, x_segments=32, y_segments=32, size=1.0)
        for v in bm_d.verts:
            nx, ny = v.co.x * sx, v.co.y * sy
            d = math.hypot(v.co.x * 1.1, v.co.y * 1.1)
            mf = noise.ridged_multi_fractal(Vector((nx * 0.06 + seed, ny * 0.06, seed)), 1.0, 2.1, 4, 1.0, 1.9)
            z = max(0.0, (1.0 - d) * height) + 2.8 * mf * max(0.0, 1.0 - d * 0.75)
            v.co = Vector((nx, ny, z))
        bmesh.ops.recalc_face_normals(bm_d, faces=bm_d.faces)
        md = bpy.data.meshes.new(f"Distant_Peak_V2_{idx}_Mesh")
        bm_d.to_mesh(md)
        bm_d.free()
        pk = bpy.data.objects.new(f"Distant_Peak_V2_{idx}", md)
        pk.location = (cx, cy, cz)
        pk.data.materials.append(mats["distant_peak"])
        set_smooth(pk)
        bpy.context.collection.objects.link(pk)
        distant_peaks.append(pk)

    brp.optimize_vfx_and_background_visibility(distant_peaks, disable_shadow=True, disable_diffuse=True)
    brp.apply_viewport_render_lod(distant_peaks, decimate_ratio=0.6)
    return summit, distant_peaks


def build_wing(side: int, parent: bpy.types.Object, mats: dict[str, bpy.types.Material]) -> bpy.types.Object:
    tag = "L" if side > 0 else "R"
    sh = bpy.data.objects.new(f"Wing_{tag}_Shoulder", None)
    sh.parent = parent
    sh.location = Vector((0.38, side * 0.32, 1.18))
    bpy.context.collection.objects.link(sh)

    p_sh = Vector((-0.05, side * -0.10, -0.05))
    p_elb = Vector((-0.55, side * 0.85, 0.72))
    p_wri = Vector((-0.15, side * 1.95, 1.55))
    f_tips = [
        Vector((0.32, side * 2.45, 2.02)),
        Vector((-0.95, side * 3.55, 2.15)),
        Vector((-2.05, side * 3.15, 1.32)),
        Vector((-2.35, side * 2.15, 0.42)),
        Vector((-1.75, side * 1.05, -0.38)),
    ]
    f_mids = [p_wri.lerp(ft, 0.52) + Vector((0.0, 0.0, 0.16)) for ft in f_tips]

    create_lofted_mesh(f"Wing_{tag}_Arm", [(p_sh, (p_elb - p_sh).normalized(), 0.17, 0.15), (p_elb, (p_wri - p_sh).normalized(), 0.12, 0.11), (p_wri, (p_wri - p_elb).normalized(), 0.09, 0.085)], segments=12, material=mats["scales"], parent=sh, render_levels=1)
    add_spike(f"Wing_{tag}_ThumbClaw", sh, p_wri, f_tips[0] - p_wri, 0.055, 0.46, mats["horn"])
    for f_i in range(1, 5):
        create_lofted_mesh(f"Wing_{tag}_Finger_{f_i}", [(p_wri, (f_mids[f_i] - p_wri).normalized(), 0.06, 0.055), (f_mids[f_i], (f_tips[f_i] - f_mids[f_i]).normalized(), 0.036, 0.034), (f_tips[f_i], (f_tips[f_i] - f_mids[f_i]).normalized(), 0.012, 0.012)], segments=8, material=mats["scales"], parent=sh, render_levels=1)

    bm = bmesh.new()
    v_sh = bm.verts.new(p_sh)
    v_elb = bm.verts.new(p_elb)
    v_wri = bm.verts.new(p_wri)
    v_fb = bm.verts.new(Vector((-1.10, side * -0.12, -0.52)))
    v_fm = bm.verts.new(Vector((-0.55, side * -0.04, -0.24)))
    f_v = [(bm.verts.new(f_mids[i]), bm.verts.new(f_tips[i])) for i in range(1, 5)]
    sc0 = bm.verts.new(Vector((-1.10, side * -0.12, -0.52)).lerp(f_tips[4], 0.5) + Vector((0.25, side * -0.08, 0.12)))
    bm.faces.new((v_sh, v_elb, v_fm))
    bm.faces.new((v_fm, v_elb, v_fb))
    bm.faces.new((v_fb, v_elb, f_v[3][0], sc0))
    bm.faces.new((sc0, f_v[3][0], f_v[3][1]))
    bm.faces.new((v_elb, v_wri, f_v[3][0]))
    for idx in range(3):
        m_a, t_a = f_v[idx]
        m_b, t_b = f_v[idx + 1]
        sc = bm.verts.new(f_tips[idx + 1].lerp(f_tips[idx + 2], 0.5) + Vector((0.28, side * -0.15, 0.08)))
        bm.faces.new((v_wri, m_a, m_b))
        bm.faces.new((m_a, t_a, sc, m_b))
        bm.faces.new((m_b, sc, t_b))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mm = bpy.data.meshes.new(f"Wing_{tag}_Membrane_Mesh")
    bm.to_mesh(mm)
    bm.free()
    mem = bpy.data.objects.new(f"Wing_{tag}_Membrane", mm)
    mem.parent = sh
    mem.data.materials.append(mats["wing"])
    set_smooth(mem)
    mem.modifiers.new("Thick", "SOLIDIFY").thickness = 0.022
    add_subsurf(mem, 1, 2)
    bpy.context.collection.objects.link(mem)
    return sh


def build_dragon_and_vfx(mats: dict[str, bpy.types.Material]) -> tuple[dict[str, object], list[bpy.types.Object]]:
    rig: dict[str, object] = {}
    hero_lit_objects: list[bpy.types.Object] = []

    root = bpy.data.objects.new("Dragon_Root", None)
    root.location = Vector((-0.85, 0.15, 5.02))
    root.rotation_euler = Euler((0.0, 0.0, math.radians(-10.0)), "XYZ")
    bpy.context.collection.objects.link(root)
    rig["root"] = root

    arm_data = bpy.data.armatures.new("Dragon_Spine_V2")
    arm_obj = bpy.data.objects.new("Dragon_Armature_V2", arm_data)
    arm_obj.parent = root
    bpy.context.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones

    def mk_bone(name, h, t, parent_b=None, conn=True):
        b = eb.new(name)
        b.head, b.tail = h, t
        if parent_b:
            b.parent = parent_b
            b.use_connect = conn
        return b

    b_torso = mk_bone("Torso", Vector((-0.65, 0.0, 0.72)), Vector((0.85, 0.0, 1.38)))
    b_n1 = mk_bone("Neck1", Vector((0.85, 0.0, 1.38)), Vector((1.22, 0.0, 2.02)), b_torso, True)
    b_n2 = mk_bone("Neck2", Vector((1.22, 0.0, 2.02)), Vector((1.55, 0.0, 2.58)), b_n1, True)
    mk_bone("Head", Vector((1.55, 0.0, 2.58)), Vector((2.35, 0.0, 2.65)), b_n2, True)
    b_t1 = mk_bone("Tail1", Vector((-0.65, 0.0, 0.72)), Vector((-1.45, -0.18, 0.56)), b_torso, False)
    b_t2 = mk_bone("Tail2", Vector((-1.45, -0.18, 0.56)), Vector((-2.20, -0.58, 0.48)), b_t1, True)
    mk_bone("Tail3", Vector((-2.20, -0.58, 0.48)), Vector((-2.65, -1.15, 0.72)), b_t2, True)
    bpy.ops.object.mode_set(mode="OBJECT")
    rig["armature"] = arm_obj

    profile = [
        (Vector((-2.65, -1.15, 0.72)), Vector((0.40, 0.85, -0.30)), 0.045, 0.045, {"Tail3": 1.0}),
        (Vector((-2.15, -0.54, 0.48)), Vector((0.85, 0.52, 0.04)), 0.15, 0.15, {"Tail2": 0.80, "Tail3": 0.20}),
        (Vector((-1.40, -0.16, 0.56)), Vector((0.95, 0.24, 0.14)), 0.25, 0.24, {"Tail1": 0.85, "Tail2": 0.15}),
        (Vector((-0.65, 0.0, 0.72)), Vector((0.98, 0.05, 0.22)), 0.40, 0.42, {"Torso": 0.85, "Tail1": 0.15}),
        (Vector((-0.20, 0.0, 0.86)), Vector((0.95, 0.0, 0.28)), 0.45, 0.48, {"Torso": 1.0}),
        (Vector((0.28, 0.0, 1.08)), Vector((0.90, 0.0, 0.35)), 0.54, 0.62, {"Torso": 1.0}),
        (Vector((0.72, 0.0, 1.32)), Vector((0.78, 0.0, 0.52)), 0.44, 0.50, {"Torso": 0.85, "Neck1": 0.15}),
        (Vector((1.08, 0.0, 1.76)), Vector((0.46, 0.0, 0.88)), 0.28, 0.30, {"Neck1": 0.85, "Torso": 0.15}),
        (Vector((1.24, 0.0, 2.06)), Vector((0.45, 0.0, 0.89)), 0.25, 0.27, {"Neck1": 0.45, "Neck2": 0.55}),
        (Vector((1.40, 0.0, 2.34)), Vector((0.54, 0.0, 0.84)), 0.23, 0.24, {"Neck2": 0.85, "Head": 0.15}),
        (Vector((1.75, 0.0, 2.64)), Vector((0.98, 0.0, 0.12)), 0.25, 0.24, {"Head": 1.0}),
    ]
    segs = 20
    bm = bmesh.new()
    rverts, rweights = [], []
    for c, tg, rx, rz, wm in profile:
        t = tg.normalized()
        up_ref = Vector((0.0, 0.0, 1.0)) if abs(t.z) < 0.92 else Vector((0.0, 1.0, 0.0))
        right = t.cross(up_ref).normalized()
        up = right.cross(t).normalized()
        rverts.append([bm.verts.new(c + right * (math.cos(2 * math.pi * i / segs) * rx) + up * (math.sin(2 * math.pi * i / segs) * rz)) for i in range(segs)])
        rweights.append(wm)
    for idx in range(len(rverts) - 1):
        r0, r1 = rverts[idx], rverts[idx + 1]
        for i in range(segs):
            j = (i + 1) % segs
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    bm.faces.new(list(reversed(rverts[0])))
    bm.faces.new(rverts[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm_m = bpy.data.meshes.new("Dragon_Body_V2_Mesh")
    bm.to_mesh(bm_m)
    bm.free()
    body = bpy.data.objects.new("Dragon_Body_V2", bm_m)
    body.parent = arm_obj
    body.data.materials.append(mats["scales"])
    set_smooth(body)
    bpy.context.collection.objects.link(body)
    vgs = {bn: body.vertex_groups.new(name=bn) for bn in ("Torso", "Neck1", "Neck2", "Head", "Tail1", "Tail2", "Tail3")}
    for r_idx, wm in enumerate(rweights):
        vis = [r_idx * segs + i for i in range(segs)]
        for bn, wt in wm.items():
            vgs[bn].add(vis, wt, "REPLACE")
    body.modifiers.new("Arm", "ARMATURE").object = arm_obj
    add_subsurf(body, 1, 2)
    hero_lit_objects.append(body)

    def attach_bone(name, bname, pos):
        b = arm_obj.data.bones[bname]
        tail_mat = b.matrix_local @ Matrix.Translation((0.0, b.length, 0.0))
        emp = bpy.data.objects.new(name, None)
        emp.parent = arm_obj
        emp.parent_type = "BONE"
        emp.parent_bone = bname
        emp.matrix_basis = tail_mat.inverted() @ Matrix.Translation(pos)
        bpy.context.collection.objects.link(emp)
        return emp

    torso_mount = attach_bone("Torso_Mount", "Torso", Vector((0, 0, 0)))
    rig["wing_l"] = build_wing(1, torso_mount, mats)
    rig["wing_r"] = build_wing(-1, torso_mount, mats)
    hero_lit_objects.extend([o for o in bpy.data.objects if o.name.startswith("Wing_")])

    for side in (-1, 1):
        tag = "L" if side > 0 else "R"
        create_lofted_mesh(f"Hind_{tag}", [(Vector((-0.55, side * 0.34, 0.72)), Vector((0.3, side * 0.2, -0.3)), 0.27, 0.24), (Vector((-0.18, side * 0.58, 0.54)), Vector((-0.4, 0, -0.4)), 0.18, 0.17), (Vector((-0.72, side * 0.56, 0.28)), Vector((0.2, 0, -0.5)), 0.13, 0.12), (Vector((-0.56, side * 0.55, 0.02)), Vector((0, 0, -1)), 0.12, 0.11)], segments=12, material=mats["scales"], parent=root, render_levels=1)
        create_lofted_mesh(f"Fore_{tag}", [(Vector((0.46, side * 0.38, 1.08)), Vector((-0.2, side * 0.2, -0.4)), 0.25, 0.23), (Vector((0.20, side * 0.62, 0.60)), Vector((0.3, 0, -0.5)), 0.17, 0.16), (Vector((0.52, side * 0.56, 0.02)), Vector((0, 0, -1)), 0.12, 0.11)], segments=12, material=mats["scales"], parent=root, render_levels=1)
        for pfx, fx in (("H", -0.54), ("F", 0.52)):
            for t_i, ang in enumerate((-30.0, 0.0, 30.0)):
                dv = Vector((math.cos(math.radians(ang)), math.sin(math.radians(ang)), -0.1)).normalized()
                add_spike(f"{pfx}Claw_{tag}_{t_i}", root, Vector((fx, side * 0.55, 0.03)) + dv * 0.12, dv + Vector((0, 0, -0.25)), 0.05, 0.35, mats["horn"])

    head = attach_bone("Dragon_Head_Pivot", "Head", Vector((1.55, 0.0, 2.58)))
    rig["head"] = head
    skull = create_lofted_mesh("Dragon_Skull", [(Vector((-0.08, 0, 0.02)), Vector((1, 0, -0.05)), 0.30, 0.29), (Vector((0.25, 0, 0.05)), Vector((1, 0, -0.04)), 0.28, 0.29), (Vector((0.64, 0, 0.02)), Vector((1, 0, -0.04)), 0.20, 0.19), (Vector((1.04, 0, -0.01)), Vector((1, 0, -0.04)), 0.15, 0.14), (Vector((1.26, 0, -0.04)), Vector((1, 0, -0.1)), 0.10, 0.09)], segments=18, material=mats["scales"], parent=head, render_levels=2)
    hero_lit_objects.append(skull)
    add_spike("Nasal_Horn", head, Vector((1.12, 0, 0.07)), Vector((-0.38, 0, 1.0)), 0.06, 0.28, mats["horn"])

    for side in (-1, 1):
        tag = "L" if side > 0 else "R"
        create_lofted_mesh(f"Horn_{tag}", [(Vector((0.05, side * 0.18, 0.22)), Vector((-0.8, side * 0.28, 0.52)), 0.11, 0.10), (Vector((-0.42, side * 0.35, 0.52)), Vector((-0.88, side * 0.24, 0.42)), 0.072, 0.068), (Vector((-1.26, side * 0.54, 0.84)), Vector((-0.98, side * 0.08, 0.14)), 0.008, 0.008)], segments=12, material=mats["horn"], parent=head, render_levels=1)
        rig[f"eye_{tag.lower()}"] = create_uv_sphere(f"Eye_{tag}", 0.08, Vector((0.36, side * 0.22, 0.11)), material=mats["eye"], parent=head)
        for fx in (0.76, 0.94, 1.12):
            add_spike(f"UFang_{tag}_{int(fx*100)}", head, Vector((fx, side * 0.09, -0.08)), Vector((0.08, 0, -1)), 0.026, 0.12, mats["horn"])

    jaw = bpy.data.objects.new("Dragon_Jaw", None)
    jaw.parent = head
    jaw.location = Vector((0.15, 0.0, -0.12))
    bpy.context.collection.objects.link(jaw)
    rig["jaw"] = jaw
    create_lofted_mesh("Jaw_Mesh", [(Vector((0, 0, 0)), Vector((1, 0, -0.04)), 0.22, 0.13), (Vector((0.5, 0, -0.03)), Vector((1, 0, -0.02)), 0.15, 0.10), (Vector((1.10, 0, 0.01)), Vector((1, 0, 0.12)), 0.06, 0.04)], segments=14, material=mats["belly"], parent=jaw, render_levels=1)

    # Volumetric Fire Domain (Improvement #3: replaces stacked BLENDED alpha spheres!)
    anchor = bpy.data.objects.new("Fire_Anchor", None)
    anchor.parent = head
    anchor.location = Vector((1.05, 0.0, -0.12))
    anchor.rotation_euler = Euler((0.0, math.radians(-10.0), 0.0), "XYZ")
    bpy.context.collection.objects.link(anchor)

    vol_domain = create_lofted_mesh(
        "Sneeze_Fire_Volume",
        [
            (Vector((0.0, 0, 0)), Vector((1, 0, 0)), 0.22, 0.20),
            (Vector((1.8, 0, 0.08)), Vector((1, 0, 0)), 0.78, 0.70),
            (Vector((4.2, 0, 0.22)), Vector((1, 0, 0)), 1.05, 0.92),
            (Vector((6.8, 0, 0.42)), Vector((1, 0, 0)), 0.35, 0.30),
        ],
        segments=18,
        material=mats["volumetric_fire"],
        parent=anchor,
        render_levels=1,
    )
    rig["vol_fire"] = vol_domain

    # Single-object Geometry Nodes Ember System (Improvement #10: replaces 140 objects!)
    bm_em = bmesh.new()
    bmesh.ops.create_cone(bm_em, cap_ends=True, segments=12, radius1=0.14, radius2=0.65, depth=3.6)
    bmesh.ops.rotate(bm_em, verts=bm_em.verts, matrix=Matrix.Rotation(math.radians(90.0), 3, "Y"))
    bmesh.ops.translate(bm_em, verts=bm_em.verts, vec=Vector((2.0, 0.0, 0.15)))
    m_em = bpy.data.meshes.new("Ember_Emitter_Mesh")
    bm_em.to_mesh(m_em)
    bm_em.free()
    ember_obj = bpy.data.objects.new("Ember_GeoNodes_Emitter", m_em)
    ember_obj.parent = anchor
    ember_obj.hide_render = False
    bpy.context.collection.objects.link(ember_obj)
    brp.create_geonodes_ember_system("EmberBurst", ember_obj, mats["spark"], bpy_module=bpy, density=42.0, burst_start=19.0, burst_end=38.0)

    brp.optimize_vfx_and_background_visibility([vol_domain, ember_obj], disable_shadow=True)

    # Dynamic Fire Lights with Light Linking (Improvement #6)
    lc_d = bpy.data.lights.new("Fire_Core_Light", type="POINT")
    lc_d.color = (1.0, 0.56, 0.14)
    lc_d.shadow_soft_size = 1.4
    lc = bpy.data.objects.new("Fire_Core_Light", lc_d)
    lc.parent = anchor
    lc.location = Vector((1.0, -0.15, 0.12))
    bpy.context.collection.objects.link(lc)
    rig["light_core"] = lc

    lp_d = bpy.data.lights.new("Fire_Plume_Light", type="POINT")
    lp_d.color = (1.0, 0.34, 0.06)
    lp_d.shadow_soft_size = 1.8
    lp = bpy.data.objects.new("Fire_Plume_Light", lp_d)
    lp.parent = anchor
    lp.location = Vector((3.2, -0.25, 0.25))
    bpy.context.collection.objects.link(lp)
    rig["light_plume"] = lp

    # Animate armature, jaw, closed eyes, volumetric fire envelope, and lights across 1..48
    pb = arm_obj.pose.bones

    def set_b(bname, frame, pitch, yaw=0.0, roll=0.0, scale=None):
        p = pb[bname]
        p.rotation_mode = "QUATERNION"
        bm_rot = arm_obj.data.bones[bname].matrix_local.to_3x3()
        w_rot = Euler((math.radians(roll), math.radians(pitch), math.radians(yaw)), "XYZ").to_matrix()
        p.rotation_quaternion = (bm_rot.inverted() @ w_rot @ bm_rot).to_quaternion()
        p.keyframe_insert(data_path="rotation_quaternion", frame=frame)
        if scale is not None:
            p.scale = Vector(scale)
            p.keyframe_insert(data_path="scale", frame=frame)

    for f, tp, n1p, n2p, hp, ja, e_sc, vf_sc, lec, lep in [
        (1, 0.0, -2.0, 0.0, -4.0, 5.0, 1.0, 0.001, 25.0, 0.0),
        (16, -10.0, -18.0, -16.0, -22.0, 18.0, 0.85, 0.001, 160.0, 20.0),
        (18, -12.0, -20.0, -18.0, -24.0, 22.0, 0.20, 0.001, 220.0, 30.0),
        (22, 8.0, 14.0, 4.0, -30.0, 46.0, 0.15, 0.90, 3600.0, 5000.0),
        (26, 7.0, 12.0, 4.0, -28.0, 44.0, 0.15, 1.12, 4800.0, 6400.0),
        (32, 5.0, 10.0, 3.0, -24.0, 38.0, 0.15, 0.82, 2600.0, 3200.0),
        (39, 1.0, -1.0, 0.0, -6.0, 10.0, 1.0, 0.001, 120.0, 40.0),
        (48, 0.0, -2.0, 0.0, -4.0, 5.0, 1.0, 0.001, 25.0, 0.0),
    ]:
        set_b("Torso", f, tp)
        set_b("Neck1", f, n1p)
        set_b("Neck2", f, n2p)
        set_b("Head", f, hp)
        key_lrs(jaw, f, rot_deg=(0.0, ja, 0.0))
        key_lrs(rig["eye_l"], f, scale=(e_sc, e_sc, e_sc))  # type: ignore[arg-type]
        key_lrs(rig["eye_r"], f, scale=(e_sc, e_sc, e_sc))  # type: ignore[arg-type]
        key_lrs(vol_domain, f, scale=(vf_sc, vf_sc, vf_sc))
        lc.data.energy = lec
        lc.data.keyframe_insert(data_path="energy", frame=f)
        lp.data.energy = lep
        lp.data.keyframe_insert(data_path="energy", frame=f)

    for f, rx in [(1, -4.0), (16, 16.0), (22, -4.0), (26, -3.5), (48, -4.0)]:
        key_lrs(rig["wing_l"], f, rot_deg=(rx, -4.0, 4.0))  # type: ignore[arg-type]
        key_lrs(rig["wing_r"], f, rot_deg=(-rx, -4.0, -4.0))  # type: ignore[arg-type]

    return rig, hero_lit_objects


def build_scene(args, out_dir: Path) -> dict:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = 48

    mats = build_materials()
    summit, _distant = build_mountain(mats)
    rig, hero_lit = build_dragon_and_vfx(mats)
    hero_lit.append(summit)

    # Physical sky + mist + motion blur + compositor OIDN/Mist/Bloom + light linking
    brp.configure_physical_sky_world(scene, bpy_module=bpy, sun_elevation_deg=-1.8, sun_rotation_deg=135.0, air_density=1.6, ozone_density=3.2, strength=0.55)
    brp.configure_mist_pass(scene, start=16.0, depth=70.0, view_layer=bpy.context.view_layer)
    if not args.no_motion_blur:
        brp.configure_motion_blur(scene, enabled=True, shutter=0.45, steps=2)

    moon_d = bpy.data.lights.new("Moon_Rim", type="SUN")
    moon_d.color = (0.64, 0.80, 1.0)
    moon_d.energy = 2.4
    moon = bpy.data.objects.new("Moon_Rim", moon_d)
    moon.rotation_euler = Euler((math.radians(52.0), math.radians(-22.0), math.radians(-135.0)), "XYZ")
    bpy.context.collection.objects.link(moon)

    brp.configure_light_linking(rig["light_plume"], include_objects=hero_lit, bpy_module=bpy)  # type: ignore[arg-type]

    target = bpy.data.objects.new("Camera_Target", None)
    target.location = Vector((1.25, 0.25, 6.65))
    bpy.context.collection.objects.link(target)
    cam_d = bpy.data.cameras.new("Hero_Camera")
    cam_d.lens = 34.0
    cam_d.clip_end = 350.0
    cam = bpy.data.objects.new("Hero_Camera", cam_d)
    cam.location = Vector((-6.8, -11.6, 8.05))
    bpy.context.collection.objects.link(cam)
    trk = cam.constraints.new("TRACK_TO")
    trk.target = target
    trk.track_axis = "TRACK_NEGATIVE_Z"
    trk.up_axis = "UP_Y"
    scene.camera = cam

    render_cfg = brp.configure_render_engine(
        scene,
        engine=args.engine,
        quality=args.quality,
        threads=args.threads,
        color_depth=args.color_depth,
        bpy_module=bpy,
    )
    brp.configure_compositor_pipeline(
        scene,
        bpy_module=bpy,
        view_layer=bpy.context.view_layer,
        enable_denoise=True,
        enable_mist=True,
        mist_strength=0.45,
        enable_glare=True,
        glare_threshold=1.35,
        glare_strength=0.38,
    )

    scene.frame_set(args.start_frame)
    if args.save_blend:
        blend_path = out_dir / "dragon_mountain_sneeze_v2.blend"
        if blend_path.exists():
            raise SystemExit(f"Refusing overwrite of existing blend: {blend_path}")
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    timings = []
    if not args.build_only:
        scene.render.use_overwrite = not args.resume
        for f in range(args.start_frame, args.end_frame + 1):
            fp = out_dir / f"frame_{f:04d}.png"
            if args.resume and fp.is_file() and fp.stat().st_size > 128:
                with fp.open("rb") as fh:
                    if fh.read(8) == PNG_MAGIC:
                        timings.append({"frame": f, "skipped": True, "seconds": 0.0})
                        continue
            t0 = time.monotonic()
            scene.frame_set(f)
            scene.render.filepath = str(fp)
            bpy.ops.render.render(write_still=True)
            timings.append({"frame": f, "skipped": False, "seconds": round(time.monotonic() - t0, 3)})

    return {
        "schema_version": "dragon-v2-render-report.v1",
        "render_config": render_cfg,
        "build_only": args.build_only,
        "timings": timings,
    }


def main() -> int:
    args, _root, out_dir = parse_args()
    report = build_scene(args, out_dir)
    print("DRAGON_V2_REPORT_JSON:" + json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
