"""Bounded, data-only performance contracts and reusable Sentinel action controls.

Contracts select named, authored actions. They never contain executable code,
arbitrary coordinates, paths, external assets, or renderer command strings.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

SCHEMA_VERSION = "p7.performance.v1"
CHARACTER = "lantern_sentinel_v1"
ACTION_FIELDS = {
    "study_switch": {"target": {"switch"}},
    "prepare_step": {"target": {"switch"}},
    "step": {"target": {"switch"}, "side": {"L", "R"}},
    "reach_switch": {"target": {"switch"}, "side": {"R"}},
    "rotate_switch": {"target": {"switch"}, "side": {"R"}},
    "lamp_response": {"target": {"lamp"}},
    "look_lamp": {"target": {"lamp"}},
    "settle": {"target": {"lamp"}},
}
ROOT_KEYS = {"schema_version", "performance_id", "title", "character", "duration_seconds", "fps", "frame_count", "actions", "camera", "render", "assets"}


class ContractError(ValueError):
    pass


def validate_contract(data):
    """Validate strict shape and physical/timing bounds; return a safe copy."""
    if not isinstance(data, dict) or set(data) != ROOT_KEYS:
        raise ContractError("contract must have exactly the versioned root fields")
    if data["schema_version"] != SCHEMA_VERSION or data["performance_id"] != "the_second_light_v1":
        raise ContractError("unsupported performance contract")
    if data["title"] != "THE SECOND LIGHT" or data["character"] != {"preset": CHARACTER}:
        raise ContractError("title or approved character preset is not allowed")
    if (data["duration_seconds"], data["fps"], data["frame_count"]) != (6, 24, 144):
        raise ContractError("performance is bounded to 6 seconds at 24 fps (144 frames)")
    if data["assets"] != []:
        raise ContractError("external assets are not permitted")
    camera = data["camera"]
    if not isinstance(camera, dict) or set(camera) != {"preset", "lens_mm"} or camera["preset"] != "chamber_three_quarter_v1":
        raise ContractError("unsupported camera configuration")
    if type(camera["lens_mm"]) not in (int, float) or not 32 <= camera["lens_mm"] <= 55:
        raise ContractError("camera lens is outside the approved range")
    render = data["render"]
    if render != {"preview": [320, 180], "master": [1280, 720], "fps": 24, "codec": "h264", "audio": False, "subtitles": False, "text": False}:
        raise ContractError("unsupported render configuration")
    actions = data["actions"]
    if not isinstance(actions, list) or len(actions) != len(ACTION_FIELDS):
        raise ContractError("all eight approved action types are required exactly once")
    by_type = {}
    for action in actions:
        if not isinstance(action, dict) or not isinstance(action.get("type"), str) or action["type"] not in ACTION_FIELDS:
            raise ContractError("unknown action")
        kind = action["type"]
        expected = {"type", "start_frame", "end_frame", *ACTION_FIELDS[kind]}
        if set(action) != expected or kind in by_type:
            raise ContractError("action fields must be exact and action types unique")
        start, end = action["start_frame"], action["end_frame"]
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= 144:
            raise ContractError("action frame range must be inside 1..144")
        for field, allowed in ACTION_FIELDS[kind].items():
            if action[field] not in allowed:
                raise ContractError("unsupported action target or side")
        by_type[kind] = action
    required_order = ["study_switch", "prepare_step", "step", "reach_switch", "rotate_switch", "lamp_response", "look_lamp", "settle"]
    if [a["type"] for a in actions] != required_order:
        raise ContractError("actions must be in the approved story order")
    for before, after in zip(actions, actions[1:]):
        if before["end_frame"] > after["start_frame"]:
            raise ContractError("action intervals may not overlap")
    if by_type["reach_switch"]["end_frame"] > by_type["rotate_switch"]["start_frame"]:
        raise ContractError("reach must precede switch rotation")
    if by_type["rotate_switch"]["end_frame"] >= by_type["lamp_response"]["start_frame"]:
        raise ContractError("switch contact/rotation must precede the lamp response")
    if by_type["look_lamp"]["start_frame"] < by_type["lamp_response"]["start_frame"]:
        raise ContractError("the Sentinel can look toward the lamp only after it responds")
    if by_type["settle"]["end_frame"] != 144:
        raise ContractError("the final pose must hold through frame 144")
    return data


def load_contract(path, approved_root):
    raw_root = Path(approved_root).absolute()
    root = raw_root.resolve(strict=True)
    raw_candidate = Path(path).absolute()
    if ".." in raw_candidate.parts:
        raise ContractError("contract traversal is not allowed")
    try:
        relative = raw_candidate.relative_to(raw_root)
    except ValueError as exc:
        raise ContractError("contract must be under the approved root") from exc
    current = raw_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ContractError("contract path contains a symlink")
    resolved = raw_candidate.resolve(strict=True)
    if root not in resolved.parents:
        raise ContractError("contract must be under the approved root")
    current = root
    for part in resolved.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ContractError("contract path contains a symlink")
    if root not in resolved.parents or not resolved.is_file() or resolved.stat().st_size > 65536:
        raise ContractError("contract must be a file under the approved root and at most 64 KiB")
    try:
        return validate_contract(json.loads(resolved.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContractError("contract is not valid UTF-8 JSON") from exc


def key_track(pose_bone, frames, *, mode="rotation_euler"):
    """Key an allowlisted pose property with authored, clamped easing."""
    if mode not in {"rotation_euler", "location"} or len(frames) > 12:
        raise ContractError("unsupported pose track")
    for frame, values in frames:
        pose_bone.rotation_mode = "XYZ"
        if mode == "location":
            from mathutils import Vector
            pose_bone.location = pose_bone.bone.matrix_local.to_3x3().inverted() @ Vector(values)
        else:
            pose_bone.rotation_euler = values
        pose_bone.keyframe_insert(data_path=mode, frame=frame)


def apply_performance(namespace, contract):
    """Apply approved action primitives to the existing Sentinel rig and set."""
    import bpy
    from mathutils import Vector

    validate_contract(contract)
    scene, rig, pose = namespace["scene"], namespace["rig"], namespace["pose"]
    rig.animation_data_clear()
    # Remove only the old film's mechanism. The original scene builder, character,
    # armature, materials, chamber, lighting and camera are reused unchanged.
    for name in ("Dormant mechanism plinth", "Plinth shadow reveal", "Mechanism lower bezel", "Mechanism dark face", "Sleeping mechanism heart", "Mechanism | contact lever"):
        obj = bpy.data.objects.get(name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    for obj in list(scene.objects):
        if obj.name.startswith(("Bezel pin", "Mechanism vertical engraving")):
            bpy.data.objects.remove(obj, do_unlink=True)

    stone, brass = namespace["stone"], namespace["brass"]
    ceramic, armor = namespace["ceramic"], namespace["armor"]
    unlit, live, wake = namespace["unlit"], namespace["live"], namespace["wake"]
    cube, cyl, uv, aim, area = namespace["cube"], namespace["cyl"], namespace["uv"], namespace["aim"], namespace["area"]
    # A small workbench and a circular handwheel replace the previous lever altar.
    cube("Second Light | workbench carcass", (.88, -.72, .72), (1.62, .86, 1.42), armor, .12)
    cube("Second Light | brass work surface", (.88, -.60, 1.46), (1.58, .88, .12), brass, .05)
    cube("Second Light | dark ceramic switch plate", (.62, -.63, 1.96), (.84, .15, .74), stone, .10)
    cyl("Second Light | circular switch hub", (.62, -.73, 1.96), .105, .09, ceramic, (math.pi/2, 0, 0))
    bpy.ops.mesh.primitive_torus_add(major_radius=.285, minor_radius=.043, major_segments=48, minor_segments=12,
                                     location=(.62, -.76, 1.96), rotation=(math.pi/2, 0, 0))
    wheel = bpy.context.object
    wheel.name = "Second Light | circular brass handwheel"
    wheel.data.materials.append(brass)
    handle = cube("Second Light | radial grip", (.82, -.80, 1.96), (.23, .075, .085), ceramic, .028)
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(.62, -.80, 1.96))
    switch_pivot = bpy.context.object
    switch_pivot.name = "Second Light | handwheel axis"
    for part in (wheel, handle):
        world_matrix = part.matrix_world.copy()
        part.parent = switch_pivot
        part.matrix_world = world_matrix
    # A nearby work lamp is visually dormant until the switch is turned.
    cube("Second Light | lamp pedestal", (1.78, -.78, 1.20), (.35, .36, .44), armor, .07)
    shade = uv("Second Light | ceramic lamp shade", (1.78, -.82, 1.68), (.28, .27, .23), unlit, 32)
    shade.scale = (.28, .27, .23)
    ld = bpy.data.lights.new("Second Light | warm lamp response", "POINT")
    ld.energy, ld.color, ld.shadow_soft_size = 0.0, (1.0, .43, .17), .7
    lamp = bpy.data.objects.new("Second Light | activated lamp", ld)
    scene.collection.objects.link(lamp)
    lamp.location = (1.78, -1.08, 1.74)
    area("Second Light | focused lamp pool", (1.4, -2.8, 3.5), 95, (1.0, .48, .22), 2.2, (1.25, -1.0, 1.2))
    lamp_material = namespace["mat"]("Second Light | warm ceramic glow", (.34, .12, .035), .12, .25, (1, .23, .035), 0.0)
    shade.data.materials.clear()
    shade.data.materials.append(lamp_material)

    scene.frame_end = 144
    scene.render.fps = 24
    scene.camera.data.lens = contract["camera"]["lens_mm"]
    # Clear all legacy story actions while retaining rest-pose geometry/rig.
    for obj in scene.objects:
        if obj.animation_data:
            obj.animation_data_clear()
    # The wheel and radial grip share an axis, so the visible switch turns as one object.
    rotate = next(a for a in contract["actions"] if a["type"] == "rotate_switch")
    for f, angle in ((1, 0), (rotate["start_frame"], 0), (rotate["end_frame"], -.72), (144, -.72)):
        switch_pivot.rotation_euler.y = angle
        switch_pivot.keyframe_insert(data_path="rotation_euler", frame=f)
    events = {action["type"]: action for action in contract["actions"]}
    frame = lambda action, frac=0.0: round(action["start_frame"] + (action["end_frame"] - action["start_frame"]) * frac)
    a = events["study_switch"]
    key_track(pose["head"], [(a["start_frame"], (0, 0, 0)), (frame(a, .55), (0, .025, -.14)), (a["end_frame"], (0, 0, -.12))])
    a = events["prepare_step"]
    key_track(pose["head"], [(a["start_frame"], (0, 0, -.12)), (frame(a, .35), (0, .04, -.22)), (a["end_frame"], (0, 0, -.30))])
    key_track(pose["spine"], [(a["start_frame"], (0, 0, 0)), (frame(a, .6), (.025, 0, -.08)), (a["end_frame"], (0, 0, -.11))])
    a = events["step"]
    side = a["side"]
    support_side = "R" if side == "L" else "L"
    key_track(pose["foot_ik."+side], [(a["start_frame"], (0, 0, 0)), (frame(a, .18), (0, 0, 0)), (frame(a, .60), (0, -.34, .17)), (a["end_frame"], (0, -.40, 0)), (144, (0, -.40, 0))], mode="location")
    # Keep the support foot on an explicit IK control curve so Blender preserves
    # the authored forward knee plane while the pelvis shifts over the step.
    key_track(pose["foot_ik."+support_side], [(1, (0, 0, 0)), (144, (0, 0, 0))], mode="location")
    # The baseline uses a slight pre-load before its first explicit frame-96
    # pelvis key; preserve that vertical reach margin from frame one onward.
    key_track(pose["pelvis"], [(1, (0, 0, -.08)), (a["start_frame"], (0, 0, -.08)),
                              (frame(a, .65), (0, -.12, -.12)), (a["end_frame"], (0, -.20, -.12)),
                              (144, (0, -.20, -.12))], mode="location")
    key_track(pose["head"], [(a["start_frame"], (0, 0, -.30)), (a["end_frame"], (0, 0, -.22))])
    a = events["reach_switch"]
    key_track(pose["hand_ik.R"], [(a["start_frame"], (0, 0, 0)), (frame(a, .72), (.28, -.56, .32)), (a["end_frame"], (.28, -.56, .32))], mode="location")
    key_track(pose["upper_arm.R"], [(a["start_frame"], (0, 0, 0)), (a["end_frame"], (.04, 0, 0))])
    a = events["rotate_switch"]
    key_track(pose["hand_ik.R"], [(a["start_frame"], (.28, -.56, .32)), (a["end_frame"], (.23, -.56, .24))], mode="location")
    a = events["lamp_response"]
    for f, energy in ((a["start_frame"], 0), (frame(a, .5), 240), (a["end_frame"], 320), (144, 320)):
        lamp.data.energy = energy
        lamp.data.keyframe_insert(data_path="energy", frame=f)
        emission = lamp_material.node_tree.nodes.get("Principled BSDF").inputs["Emission Strength"]
        emission.default_value = 2.2 if energy >= 240 else 0.0
        emission.keyframe_insert(data_path="default_value", frame=f)
    a = events["look_lamp"]
    key_track(pose["head"], [(a["start_frame"], (0, 0, -.22)), (frame(a, .55), (0, .06, .18)), (a["end_frame"], (0, .035, .12))])
    a = events["settle"]
    key_track(pose["spine"], [(a["start_frame"], (0, 0, -.11)), (frame(a, .55), (0, 0, -.06)), (a["end_frame"], (0, 0, -.07))])
    for owner in (rig, switch_pivot, lamp, shade):
        if owner.animation_data and owner.animation_data.action:
            for fc in getattr(owner.animation_data.action, "fcurves", ()):
                linear = "foot_ik" in fc.data_path
                for point in fc.keyframe_points:
                    point.interpolation = "LINEAR" if linear else "BEZIER"
                    point.handle_left_type = "AUTO_CLAMPED"
                    point.handle_right_type = "AUTO_CLAMPED"
    scene.frame_set(1)
    bpy.context.view_layer.update()
    namespace["second_light_objects"] = {"wheel": wheel, "handle": handle, "lamp": lamp, "shade": shade}
    namespace["second_light_contract"] = contract
    namespace["switch_pivot"] = switch_pivot
    return namespace
