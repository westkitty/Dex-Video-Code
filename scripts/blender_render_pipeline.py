"""Blender 5.2+ rendering quality, compositor, VFX, and performance helpers.

Designed for both headless/background Blender 5.2+ execution and unit testing
with mock ``bpy`` objects. Covers:
- Tuned EEVEE and Cycles Metal GPU profiles with adaptive sampling & OIDN
- Blender 5.2 compositor pipelines (OIDN Denoise, Mist depth blend, Bloom Glare)
- Physical motion blur, Nishita/Multiple-Scattering sky & light linking
- Procedural AO + Pointiness edge wear
- True Principled Volume fire & smoke domains (zero alpha-overdraw spheres)
- Shadow-map visibility culling on VFX/distant geometry
- Single-object Geometry Nodes ember particle burst systems
- Viewport vs. render Subsurf & Decimate LOD separation
"""

from __future__ import annotations

import math
import os
import stat
from pathlib import Path
from typing import Any

EEVEE_QUALITY_PROFILES: dict[str, dict[str, Any]] = {
    "interaction": {
        "resolution": (320, 180),
        "samples": 8,
        "use_raytracing": False,
        "shadow_ray_count": 1,
        "shadow_step_count": 4,
        "shadow_resolution_scale": 0.5,
        "volumetric_tile_size": "8",
        "volumetric_samples": 16,
        "clamp_surface_indirect": 6.0,
        "use_taa_reprojection": True,
    },
    "preview": {
        "resolution": (640, 360),
        "samples": 16,
        "use_raytracing": True,
        "shadow_ray_count": 1,
        "shadow_step_count": 6,
        "shadow_resolution_scale": 0.75,
        "volumetric_tile_size": "4",
        "volumetric_samples": 32,
        "clamp_surface_indirect": 8.0,
        "use_taa_reprojection": True,
    },
    "master": {
        "resolution": (1280, 720),
        "samples": 32,
        "use_raytracing": True,
        "shadow_ray_count": 2,
        "shadow_step_count": 8,
        "shadow_resolution_scale": 1.0,
        "volumetric_tile_size": "2",
        "volumetric_samples": 48,
        "clamp_surface_indirect": 10.0,
        "use_taa_reprojection": True,
    },
    "hero": {
        "resolution": (1280, 720),
        "samples": 48,
        "use_raytracing": True,
        "shadow_ray_count": 3,
        "shadow_step_count": 12,
        "shadow_resolution_scale": 1.0,
        "volumetric_tile_size": "2",
        "volumetric_samples": 64,
        "clamp_surface_indirect": 12.0,
        "use_taa_reprojection": True,
    },
}

CYCLES_QUALITY_PROFILES: dict[str, dict[str, Any]] = {
    "interaction": {
        "resolution": (320, 180),
        "samples": 16,
        "adaptive_threshold": 0.05,
        "max_bounces": 4,
        "volume_bounces": 1,
    },
    "preview": {
        "resolution": (640, 360),
        "samples": 32,
        "adaptive_threshold": 0.03,
        "max_bounces": 6,
        "volume_bounces": 2,
    },
    "master": {
        "resolution": (1280, 720),
        "samples": 64,
        "adaptive_threshold": 0.02,
        "max_bounces": 8,
        "volume_bounces": 2,
    },
    "hero": {
        "resolution": (1280, 720),
        "samples": 96,
        "adaptive_threshold": 0.015,
        "max_bounces": 8,
        "volume_bounces": 3,
    },
}


def _safe_set(obj: Any, attr: str, value: Any) -> bool:
    if hasattr(obj, attr):
        try:
            setattr(obj, attr, value)
            return True
        except Exception:
            return False
    return False


def _socket_by_id_or_name(sockets: Any, identifier: str, fallback_name: str) -> Any:
    for sock in sockets:
        if getattr(sock, "identifier", None) == identifier:
            return sock
    for sock in sockets:
        if getattr(sock, "name", None) == fallback_name:
            return sock
    return sockets[0]


def _assert_safe_confined_file(path_value: str | Path, approved_root: str | Path) -> Path:
    root = Path(approved_root).expanduser().resolve(strict=True)
    candidate = Path(path_value).expanduser()
    if not candidate.is_absolute():
        candidate = (root / candidate)
    cur = Path("/")
    for part in candidate.parts[1:]:
        cur = cur / part
        if cur.exists() and stat.S_ISLNK(cur.lstat().st_mode):
            raise ValueError(f"Refusing symlink in asset path: {cur}")
    resolved = candidate.resolve(strict=True)
    if os.path.commonpath((str(root), str(resolved))) != str(root):
        raise ValueError(f"Asset path escapes approved root: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"Asset path is not a regular file: {resolved}")
    return resolved


def configure_render_engine(
    scene: Any,
    *,
    engine: str = "eevee",
    quality: str = "preview",
    threads: int = 6,
    color_depth: str = "8",
    bpy_module: Any = None,
) -> dict[str, Any]:
    """Configure BLENDER_EEVEE or CYCLES (Apple Metal GPU + OIDN) with bounded quality settings."""
    if quality not in EEVEE_QUALITY_PROFILES:
        raise ValueError(f"Unsupported quality preset: {quality}")
    if engine not in ("eevee", "cycles_metal"):
        raise ValueError(f"Unsupported engine: {engine}")
    if color_depth not in ("8", "16"):
        raise ValueError(f"Unsupported PNG color_depth: {color_depth}")

    threads = max(1, min(16, int(threads)))
    render = scene.render
    render.resolution_percentage = 100
    render.fps = 24
    render.threads_mode = "FIXED"
    render.threads = threads
    render.image_settings.file_format = "PNG"
    render.image_settings.color_mode = "RGB"
    render.image_settings.color_depth = color_depth
    _safe_set(render.image_settings, "compression", 15)

    _safe_set(scene.view_settings, "view_transform", "AgX")
    _safe_set(scene.view_settings, "look", "AgX - Medium High Contrast")

    applied: dict[str, Any] = {"engine": engine, "quality": quality, "threads": threads, "color_depth": color_depth}

    if engine == "eevee":
        prof = EEVEE_QUALITY_PROFILES[quality]
        render.engine = "BLENDER_EEVEE"
        render.resolution_x, render.resolution_y = prof["resolution"]
        eevee = scene.eevee
        eevee.taa_render_samples = prof["samples"]
        for key in (
            "use_raytracing",
            "shadow_ray_count",
            "shadow_step_count",
            "shadow_resolution_scale",
            "volumetric_tile_size",
            "volumetric_samples",
            "clamp_surface_indirect",
            "use_taa_reprojection",
        ):
            _safe_set(eevee, key, prof[key])
        applied["resolution"] = prof["resolution"]
        applied["samples"] = prof["samples"]
        return applied

    # Cycles Metal GPU + Adaptive Sampling + OpenImageDenoise
    prof = CYCLES_QUALITY_PROFILES[quality]
    render.engine = "CYCLES"
    render.resolution_x, render.resolution_y = prof["resolution"]
    cycles = scene.cycles
    cycles.samples = prof["samples"]
    _safe_set(cycles, "use_adaptive_sampling", True)
    _safe_set(cycles, "adaptive_threshold", prof["adaptive_threshold"])
    _safe_set(cycles, "use_denoising", True)
    _safe_set(cycles, "denoiser", "OPENIMAGEDENOISE")
    _safe_set(cycles, "max_bounces", prof["max_bounces"])
    _safe_set(cycles, "volume_bounces", prof["volume_bounces"])

    metal_enabled = False
    if bpy_module is None:
        try:
            import bpy as bpy_module  # type: ignore
        except ImportError:
            bpy_module = None
    if bpy_module is not None:
        try:
            addon = bpy_module.context.preferences.addons.get("cycles")
            if addon is not None:
                cprefs = addon.preferences
                cprefs.compute_device_type = "METAL"
                cprefs.get_devices()
                for dev in getattr(cprefs, "devices", []):
                    is_metal = getattr(dev, "type", "") == "METAL"
                    dev.use = is_metal
                    if is_metal:
                        metal_enabled = True
        except Exception:
            metal_enabled = False

    _safe_set(cycles, "device", "GPU" if metal_enabled else "CPU")
    applied["resolution"] = prof["resolution"]
    applied["samples"] = prof["samples"]
    applied["metal_gpu"] = metal_enabled
    return applied


def configure_mist_pass(
    scene: Any,
    *,
    start: float = 14.0,
    depth: float = 75.0,
    falloff: str = "QUADRATIC",
    view_layer: Any = None,
) -> None:
    """Enable View Layer Mist pass and configure world atmospheric depth range."""
    if view_layer is not None:
        _safe_set(view_layer, "use_pass_mist", True)
    world = getattr(scene, "world", None)
    if world is not None and hasattr(world, "mist_settings"):
        ms = world.mist_settings
        _safe_set(ms, "use_mist", True)
        _safe_set(ms, "start", float(start))
        _safe_set(ms, "depth", float(depth))
        _safe_set(ms, "falloff", falloff)


def configure_motion_blur(
    scene: Any,
    *,
    enabled: bool = True,
    shutter: float = 0.5,
    steps: int = 2,
) -> None:
    """Enable physical motion blur on scene and EEVEE motion steps."""
    _safe_set(scene.render, "use_motion_blur", bool(enabled))
    _safe_set(scene.render, "motion_blur_shutter", float(shutter))
    if hasattr(scene, "eevee"):
        _safe_set(scene.eevee, "motion_blur_steps", max(1, int(steps)))


def configure_compositor_pipeline(
    scene: Any,
    *,
    bpy_module: Any = None,
    view_layer: Any = None,
    enable_denoise: bool = True,
    enable_mist: bool = True,
    mist_color: tuple[float, float, float, float] = (0.04, 0.08, 0.19, 1.0),
    mist_strength: float = 0.48,
    enable_glare: bool = True,
    glare_type: str = "Bloom",
    glare_quality: str = "High",
    glare_threshold: float = 1.35,
    glare_strength: float = 0.38,
    glare_size: float = 5.5,
) -> Any:
    """Build a Blender 5.2+ compositor_node_group with OIDN Denoise -> Mist -> Bloom Glare."""
    if bpy_module is None:
        import bpy as bpy_module  # type: ignore

    if view_layer is None and hasattr(bpy_module, "context"):
        view_layer = getattr(bpy_module.context, "view_layer", None)

    if view_layer is not None:
        if enable_denoise:
            _safe_set(view_layer, "use_pass_normal", True)
            _safe_set(view_layer, "use_pass_diffuse_color", True)
        if enable_mist:
            _safe_set(view_layer, "use_pass_mist", True)

    ng = bpy_module.data.node_groups.new("DexRenderCompositor", "CompositorNodeTree")
    if hasattr(ng, "interface"):
        ng.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")

    rl = ng.nodes.new("CompositorNodeRLayers")
    out_n = ng.nodes.new("NodeGroupOutput")
    current_img = rl.outputs["Image"]

    if enable_denoise:
        dn = ng.nodes.new("CompositorNodeDenoise")
        _safe_set(dn.inputs["HDR"], "default_value", True)
        _safe_set(dn.inputs["Prefilter"], "default_value", "Accurate")
        ng.links.new(current_img, dn.inputs["Image"])
        rl_names = {o.name: o for o in rl.outputs}
        if "DiffCol" in rl_names and "Albedo" in dn.inputs:
            ng.links.new(rl_names["DiffCol"], dn.inputs["Albedo"])
        elif "Denoising Albedo" in rl_names and "Albedo" in dn.inputs:
            ng.links.new(rl_names["Denoising Albedo"], dn.inputs["Albedo"])
        if "Normal" in rl_names and "Normal" in dn.inputs:
            ng.links.new(rl_names["Normal"], dn.inputs["Normal"])
        elif "Denoising Normal" in rl_names and "Normal" in dn.inputs:
            ng.links.new(rl_names["Denoising Normal"], dn.inputs["Normal"])
        current_img = dn.outputs["Image"]

    if enable_mist:
        rl_names = {o.name: o for o in rl.outputs}
        if "Mist" in rl_names:
            mul_mist = ng.nodes.new("ShaderNodeMath")
            mul_mist.operation = "MULTIPLY"
            mul_mist.inputs[1].default_value = float(mist_strength)
            ng.links.new(rl_names["Mist"], mul_mist.inputs[0])

            mix_mist = ng.nodes.new("ShaderNodeMix")
            mix_mist.data_type = "RGBA"
            fac_sock = _socket_by_id_or_name(mix_mist.inputs, "Factor_Float", "Factor")
            a_sock = _socket_by_id_or_name(mix_mist.inputs, "A_Color", "A")
            b_sock = _socket_by_id_or_name(mix_mist.inputs, "B_Color", "B")
            res_sock = _socket_by_id_or_name(mix_mist.outputs, "Result_Color", "Result")
            b_sock.default_value = mist_color
            ng.links.new(mul_mist.outputs["Value"], fac_sock)
            ng.links.new(current_img, a_sock)
            ng.links.new(res_sock, out_n.inputs["Image"])
            current_img = res_sock

    if enable_glare:
        glare = ng.nodes.new("CompositorNodeGlare")
        glare.inputs["Type"].default_value = glare_type
        glare.inputs["Quality"].default_value = glare_quality
        glare.inputs["Threshold"].default_value = float(glare_threshold)
        glare.inputs["Strength"].default_value = float(glare_strength)
        glare.inputs["Size"].default_value = float(glare_size)
        ng.links.new(current_img, glare.inputs["Image"])
        current_img = glare.outputs["Image"]

    ng.links.new(current_img, out_n.inputs["Image"])
    if hasattr(scene, "compositing_node_group"):
        scene.compositing_node_group = ng
    return ng


def configure_physical_sky_world(
    scene: Any,
    *,
    bpy_module: Any = None,
    sun_elevation_deg: float = -1.5,
    sun_rotation_deg: float = 135.0,
    air_density: float = 1.6,
    ozone_density: float = 3.2,
    strength: float = 0.55,
    hdri_path: str | Path | None = None,
    approved_asset_root: str | Path | None = None,
) -> Any:
    """Configure physically based twilight sky (MULTIPLE_SCATTERING) or confined HDRI world."""
    if bpy_module is None:
        import bpy as bpy_module  # type: ignore

    world = bpy_module.data.worlds.new("Physical_Sky_World")
    scene.world = world
    if hasattr(world, "use_nodes"):
        world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = float(strength)

    if hdri_path is not None:
        if approved_asset_root is None:
            raise ValueError("HDRI loading requires approved_asset_root for path confinement")
        safe_hdri = _assert_safe_confined_file(hdri_path, approved_asset_root)
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy_module.data.images.load(str(safe_hdri), check_existing=True)
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    else:
        sky = nt.nodes.new("ShaderNodeTexSky")
        sky.sky_type = "MULTIPLE_SCATTERING"
        _safe_set(sky, "sun_disc", False)
        _safe_set(sky, "sun_elevation", math.radians(sun_elevation_deg))
        _safe_set(sky, "sun_rotation", math.radians(sun_rotation_deg))
        _safe_set(sky, "air_density", float(air_density))
        _safe_set(sky, "ozone_density", float(ozone_density))
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])

    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return world


def configure_light_linking(
    light_obj: Any,
    *,
    include_objects: list[Any] | None = None,
    exclude_objects: list[Any] | None = None,
    collection_prefix: str = "LightLink",
    bpy_module: Any = None,
) -> dict[str, Any]:
    """Attach receiver/blocker collections via Blender 5.x light_linking."""
    if bpy_module is None:
        import bpy as bpy_module  # type: ignore

    result: dict[str, Any] = {"receiver_count": 0, "blocker_count": 0}
    if not hasattr(light_obj, "light_linking"):
        return result

    ll = light_obj.light_linking
    if include_objects:
        rec_coll = bpy_module.data.collections.new(f"{collection_prefix}_{light_obj.name}_Receivers")
        for obj in include_objects:
            rec_coll.objects.link(obj)
        ll.receiver_collection = rec_coll
        result["receiver_count"] = len(include_objects)

    if exclude_objects:
        blk_coll = bpy_module.data.collections.new(f"{collection_prefix}_{light_obj.name}_Blockers")
        for obj in exclude_objects:
            blk_coll.objects.link(obj)
        ll.blocker_collection = blk_coll
        result["blocker_count"] = len(exclude_objects)

    return result


def add_procedural_edge_wear_and_ao(
    material: Any,
    *,
    ao_distance: float = 0.45,
    crevice_darkening: float = 0.42,
    wear_color: tuple[float, float, float, float] = (0.58, 0.56, 0.50, 1.0),
    wear_strength: float = 0.25,
) -> bool:
    """Layer procedural Ambient Occlusion crevices and Pointiness edge wear into Principled BSDF."""
    nt = getattr(material, "node_tree", None)
    if nt is None:
        return False
    bsdf = next((n for n in nt.nodes if getattr(n, "type", "") == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return False

    base_inp = bsdf.inputs["Base Color"]
    prev_link = base_inp.links[0].from_socket if base_inp.is_linked else None
    base_default = tuple(base_inp.default_value) if not prev_link else (0.5, 0.5, 0.5, 1.0)
    if prev_link:
        nt.links.remove(base_inp.links[0])

    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = float(ao_distance)

    ao_ramp = nt.nodes.new("ShaderNodeValToRGB")
    ao_ramp.color_ramp.elements[0].position = 0.18
    ao_ramp.color_ramp.elements[0].color = (1.0 - crevice_darkening, 1.0 - crevice_darkening, 1.0 - crevice_darkening, 1.0)
    ao_ramp.color_ramp.elements[1].position = 0.85
    ao_ramp.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    nt.links.new(ao.outputs["AO"], ao_ramp.inputs["Fac"])

    mul_ao = nt.nodes.new("ShaderNodeMix")
    mul_ao.data_type = "RGBA"
    mul_ao.blend_type = "MULTIPLY"
    mul_ao_fac = _socket_by_id_or_name(mul_ao.inputs, "Factor_Float", "Factor")
    mul_ao_a = _socket_by_id_or_name(mul_ao.inputs, "A_Color", "A")
    mul_ao_b = _socket_by_id_or_name(mul_ao.inputs, "B_Color", "B")
    mul_ao_res = _socket_by_id_or_name(mul_ao.outputs, "Result_Color", "Result")
    mul_ao_fac.default_value = 1.0
    if prev_link:
        nt.links.new(prev_link, mul_ao_a)
    else:
        mul_ao_a.default_value = base_default
    nt.links.new(ao_ramp.outputs["Color"], mul_ao_b)

    geom = nt.nodes.new("ShaderNodeNewGeometry")
    pt_ramp = nt.nodes.new("ShaderNodeValToRGB")
    pt_ramp.color_ramp.elements[0].position = 0.52
    pt_ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    pt_ramp.color_ramp.elements[1].position = 0.68
    pt_ramp.color_ramp.elements[1].color = (float(wear_strength), float(wear_strength), float(wear_strength), 1.0)
    nt.links.new(geom.outputs["Pointiness"], pt_ramp.inputs["Fac"])

    mix_wear = nt.nodes.new("ShaderNodeMix")
    mix_wear.data_type = "RGBA"
    wear_fac = _socket_by_id_or_name(mix_wear.inputs, "Factor_Float", "Factor")
    wear_a = _socket_by_id_or_name(mix_wear.inputs, "A_Color", "A")
    wear_b = _socket_by_id_or_name(mix_wear.inputs, "B_Color", "B")
    wear_res = _socket_by_id_or_name(mix_wear.outputs, "Result_Color", "Result")
    wear_b.default_value = wear_color
    nt.links.new(pt_ramp.outputs["Color"], wear_fac)
    nt.links.new(mul_ao_res, wear_a)
    nt.links.new(wear_res, base_inp)
    return True


def build_volumetric_fire_material(
    name: str = "Volumetric_Fire_Mat",
    *,
    bpy_module: Any = None,
    temperature_k: float = 2500.0,
    blackbody_intensity: float = 4.2,
    density_scale: float = 2.6,
    noise_scale: float = 3.2,
) -> Any:
    """Create a Principled Volume fire & smoke shader (replaces stacked BLENDED meshes)."""
    if bpy_module is None:
        import bpy as bpy_module  # type: ignore

    mat = bpy_module.data.materials.new(name)
    if hasattr(mat, "use_nodes"):
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    pv = nt.nodes.new("ShaderNodeVolumePrincipled")
    pv.inputs["Color"].default_value = (0.28, 0.24, 0.24, 1.0)
    pv.inputs["Anisotropy"].default_value = 0.35
    pv.inputs["Temperature"].default_value = float(temperature_k)
    pv.inputs["Emission Color"].default_value = (1.0, 0.36, 0.04, 1.0)

    tex_c = nt.nodes.new("ShaderNodeTexCoord")
    # Generated coordinates run 0..1; compute distance from cone centerline (0.5, 0.5) & fade along X
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    sub_y = nt.nodes.new("ShaderNodeMath")
    sub_y.operation = "SUBTRACT"
    sub_y.inputs[1].default_value = 0.5
    sub_z = nt.nodes.new("ShaderNodeMath")
    sub_z.operation = "SUBTRACT"
    sub_z.inputs[1].default_value = 0.5
    sq_y = nt.nodes.new("ShaderNodeMath")
    sq_y.operation = "MULTIPLY"
    sq_z = nt.nodes.new("ShaderNodeMath")
    sq_z.operation = "MULTIPLY"
    add_yz = nt.nodes.new("ShaderNodeMath")
    add_yz.operation = "ADD"
    rad_fall = nt.nodes.new("ShaderNodeMapRange")
    rad_fall.inputs["From Min"].default_value = 0.02
    rad_fall.inputs["From Max"].default_value = 0.24
    rad_fall.inputs["To Min"].default_value = 1.0
    rad_fall.inputs["To Max"].default_value = 0.0

    # Fade smoothly along X (0..1 from snout to tip)
    x_fade = nt.nodes.new("ShaderNodeMapRange")
    x_fade.inputs["From Min"].default_value = 0.0
    x_fade.inputs["From Max"].default_value = 1.0
    x_fade.inputs["To Min"].default_value = 1.0
    x_fade.inputs["To Max"].default_value = 0.05

    noise_v = nt.nodes.new("ShaderNodeTexNoise")
    noise_v.inputs["Scale"].default_value = float(noise_scale)
    noise_v.inputs["Detail"].default_value = 5.0
    noise_v.inputs["Roughness"].default_value = 0.65

    mul_env = nt.nodes.new("ShaderNodeMath")
    mul_env.operation = "MULTIPLY"
    mul_turb = nt.nodes.new("ShaderNodeMath")
    mul_turb.operation = "MULTIPLY"

    dens_ramp = nt.nodes.new("ShaderNodeMapRange")
    dens_ramp.inputs["From Min"].default_value = 0.14
    dens_ramp.inputs["From Max"].default_value = 0.55
    dens_ramp.inputs["To Min"].default_value = 0.0
    dens_ramp.inputs["To Max"].default_value = float(density_scale)

    bb_ramp = nt.nodes.new("ShaderNodeMapRange")
    bb_ramp.inputs["From Min"].default_value = 0.22
    bb_ramp.inputs["From Max"].default_value = 0.62
    bb_ramp.inputs["To Min"].default_value = 0.0
    bb_ramp.inputs["To Max"].default_value = float(blackbody_intensity)

    em_ramp = nt.nodes.new("ShaderNodeMapRange")
    em_ramp.inputs["From Min"].default_value = 0.24
    em_ramp.inputs["From Max"].default_value = 0.68
    em_ramp.inputs["To Min"].default_value = 0.0
    em_ramp.inputs["To Max"].default_value = float(blackbody_intensity * 0.65)

    nt.links.new(tex_c.outputs["Generated"], sep.inputs["Vector"])
    nt.links.new(tex_c.outputs["Object"], noise_v.inputs["Vector"])
    nt.links.new(sep.outputs["Y"], sub_y.inputs[0])
    nt.links.new(sep.outputs["Z"], sub_z.inputs[0])
    nt.links.new(sub_y.outputs["Value"], sq_y.inputs[0])
    nt.links.new(sub_y.outputs["Value"], sq_y.inputs[1])
    nt.links.new(sub_z.outputs["Value"], sq_z.inputs[0])
    nt.links.new(sub_z.outputs["Value"], sq_z.inputs[1])
    nt.links.new(sq_y.outputs["Value"], add_yz.inputs[0])
    nt.links.new(sq_z.outputs["Value"], add_yz.inputs[1])
    nt.links.new(add_yz.outputs["Value"], rad_fall.inputs["Value"])
    nt.links.new(sep.outputs["X"], x_fade.inputs["Value"])
    nt.links.new(rad_fall.outputs["Result"], mul_env.inputs[0])
    nt.links.new(x_fade.outputs["Result"], mul_env.inputs[1])
    nt.links.new(mul_env.outputs["Value"], mul_turb.inputs[0])
    nt.links.new(noise_v.outputs["Fac"], mul_turb.inputs[1])
    nt.links.new(mul_turb.outputs["Value"], dens_ramp.inputs["Value"])
    nt.links.new(mul_turb.outputs["Value"], bb_ramp.inputs["Value"])
    nt.links.new(mul_turb.outputs["Value"], em_ramp.inputs["Value"])
    nt.links.new(dens_ramp.outputs["Result"], pv.inputs["Density"])
    nt.links.new(bb_ramp.outputs["Result"], pv.inputs["Blackbody Intensity"])
    nt.links.new(em_ramp.outputs["Result"], pv.inputs["Emission Strength"])
    nt.links.new(pv.outputs["Volume"], out.inputs["Volume"])
    return mat


def optimize_vfx_and_background_visibility(
    objects: list[Any],
    *,
    disable_shadow: bool = True,
    disable_diffuse: bool = False,
) -> int:
    """Disable shadow-map and optional diffuse ray evaluations on VFX and distant meshes."""
    updated = 0
    for obj in objects:
        if disable_shadow:
            _safe_set(obj, "visible_shadow", False)
        if disable_diffuse:
            _safe_set(obj, "visible_diffuse", False)
        updated += 1
    return updated


def create_geonodes_ember_system(
    name: str,
    emitter_obj: Any,
    ember_material: Any,
    *,
    bpy_module: Any = None,
    density: float = 38.0,
    burst_start: float = 19.0,
    burst_end: float = 38.0,
    speed: float = 0.38,
    ember_radius: float = 0.032,
) -> Any:
    """Replace hundreds of separate ember objects with one Geometry Nodes burst system."""
    if bpy_module is None:
        import bpy as bpy_module  # type: ignore

    ng = bpy_module.data.node_groups.new(f"{name}_GeoNodes", "GeometryNodeTree")
    if hasattr(ng, "interface"):
        ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    n_in = ng.nodes.new("NodeGroupInput")
    n_out = ng.nodes.new("NodeGroupOutput")
    dist = ng.nodes.new("GeometryNodeDistributePointsOnFaces")
    dist.inputs["Density"].default_value = float(density)

    time_n = ng.nodes.new("GeometryNodeInputSceneTime")
    sub_t = ng.nodes.new("ShaderNodeMath")
    sub_t.operation = "SUBTRACT"
    sub_t.inputs[1].default_value = float(burst_start)
    clamp_t = ng.nodes.new("ShaderNodeMath")
    clamp_t.operation = "MAXIMUM"
    clamp_t.inputs[1].default_value = 0.0

    # Envelope scales embers to 0 before burst_start and fades out after burst_end
    env_in = ng.nodes.new("ShaderNodeMapRange")
    env_in.inputs["From Min"].default_value = float(burst_start)
    env_in.inputs["From Max"].default_value = float(burst_start + 3.0)
    env_in.inputs["To Min"].default_value = 0.0
    env_in.inputs["To Max"].default_value = 1.0

    env_out = ng.nodes.new("ShaderNodeMapRange")
    env_out.inputs["From Min"].default_value = float(burst_end - 4.0)
    env_out.inputs["From Max"].default_value = float(burst_end + 8.0)
    env_out.inputs["To Min"].default_value = 1.0
    env_out.inputs["To Max"].default_value = 0.0

    mul_env = ng.nodes.new("ShaderNodeMath")
    mul_env.operation = "MULTIPLY"

    # Forward + upward curl drift along local +X
    pos_n = ng.nodes.new("GeometryNodeInputPosition")
    noise_n = ng.nodes.new("ShaderNodeTexNoise")
    noise_n.inputs["Scale"].default_value = 1.8
    noise_n.inputs["Detail"].default_value = 2.0
    sub_noise = ng.nodes.new("ShaderNodeVectorMath")
    sub_noise.operation = "SUBTRACT"
    sub_noise.inputs[1].default_value = (0.5, 0.5, 0.35)

    add_fwd = ng.nodes.new("ShaderNodeVectorMath")
    add_fwd.operation = "ADD"
    add_fwd.inputs[1].default_value = (1.0, 0.0, 0.16)

    scale_vel = ng.nodes.new("ShaderNodeVectorMath")
    scale_vel.operation = "SCALE"
    mul_spd = ng.nodes.new("ShaderNodeMath")
    mul_spd.operation = "MULTIPLY"
    mul_spd.inputs[1].default_value = float(speed)

    set_pos = ng.nodes.new("GeometryNodeSetPosition")
    ico = ng.nodes.new("GeometryNodeMeshIcoSphere")
    ico.inputs["Radius"].default_value = float(ember_radius)
    ico.inputs["Subdivisions"].default_value = 1
    set_mat = ng.nodes.new("GeometryNodeSetMaterial")
    set_mat.inputs["Material"].default_value = ember_material

    inst = ng.nodes.new("GeometryNodeInstanceOnPoints")
    sc_inst = ng.nodes.new("GeometryNodeScaleInstances")
    comb_sc = ng.nodes.new("ShaderNodeCombineXYZ")
    mul_x = ng.nodes.new("ShaderNodeMath")
    mul_x.operation = "MULTIPLY"
    mul_x.inputs[1].default_value = 3.2

    ng.links.new(n_in.outputs["Geometry"], dist.inputs["Mesh"])
    ng.links.new(time_n.outputs["Frame"], sub_t.inputs[0])
    ng.links.new(sub_t.outputs["Value"], clamp_t.inputs[0])
    ng.links.new(clamp_t.outputs["Value"], mul_spd.inputs[0])
    ng.links.new(time_n.outputs["Frame"], env_in.inputs["Value"])
    ng.links.new(time_n.outputs["Frame"], env_out.inputs["Value"])
    ng.links.new(env_in.outputs["Result"], mul_env.inputs[0])
    ng.links.new(env_out.outputs["Result"], mul_env.inputs[1])

    ng.links.new(pos_n.outputs["Position"], noise_n.inputs["Vector"])
    ng.links.new(noise_n.outputs["Color"], sub_noise.inputs[0])
    ng.links.new(sub_noise.outputs["Vector"], add_fwd.inputs[0])
    ng.links.new(add_fwd.outputs["Vector"], scale_vel.inputs[0])
    ng.links.new(mul_spd.outputs["Value"], scale_vel.inputs["Scale"])

    ng.links.new(dist.outputs["Points"], set_pos.inputs["Geometry"])
    ng.links.new(scale_vel.outputs["Vector"], set_pos.inputs["Offset"])
    ng.links.new(ico.outputs["Mesh"], set_mat.inputs["Geometry"])
    ng.links.new(set_pos.outputs["Geometry"], inst.inputs["Points"])
    ng.links.new(set_mat.outputs["Geometry"], inst.inputs["Instance"])

    ng.links.new(mul_env.outputs["Value"], mul_x.inputs[0])
    ng.links.new(mul_x.outputs["Value"], comb_sc.inputs["X"])
    ng.links.new(mul_env.outputs["Value"], comb_sc.inputs["Y"])
    ng.links.new(mul_env.outputs["Value"], comb_sc.inputs["Z"])
    ng.links.new(inst.outputs["Instances"], sc_inst.inputs["Instances"])
    ng.links.new(comb_sc.outputs["Vector"], sc_inst.inputs["Scale"])
    ng.links.new(sc_inst.outputs["Instances"], n_out.inputs["Geometry"])

    mod = emitter_obj.modifiers.new(name, "NODES")
    mod.node_group = ng
    _safe_set(emitter_obj, "visible_shadow", False)
    return mod


def apply_viewport_render_lod(
    objects: list[Any],
    *,
    viewport_levels: int = 1,
    render_levels: int = 2,
    decimate_ratio: float | None = None,
) -> int:
    """Separate interactive Subsurf levels from render levels and optionally decimate background meshes."""
    changed = 0
    for obj in objects:
        for mod in getattr(obj, "modifiers", []):
            if getattr(mod, "type", "") == "SUBSURF":
                mod.levels = max(0, int(viewport_levels))
                mod.render_levels = max(0, int(render_levels))
                changed += 1
        if decimate_ratio is not None and 0.05 <= decimate_ratio < 1.0:
            dec = obj.modifiers.new("BackgroundDecimate", "DECIMATE")
            dec.ratio = float(decimate_ratio)
            changed += 1
    return changed
