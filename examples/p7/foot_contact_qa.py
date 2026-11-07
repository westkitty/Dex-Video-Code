"""Evaluate actual Sentinel foot contact in Blender without rendering frames.

Run with Blender's background Python runner and a scene source path. The scene
builder is invoked in build-only mode; evaluated sole and toe vertices are then
measured in world space at every frame.
"""
import argparse
import json
import math
import runpy
import sys
from collections import defaultdict


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="lantern_sentinel.py to evaluate")
    parser.add_argument("--output-root", required=True, help="confined production root")
    parser.add_argument("--output-dir", required=True, help="new child directory for the build-only scene")
    parser.add_argument("--expect-failure", action="store_true", help="require a known-bad baseline to fail")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def build_scene(args):
    sys.argv = [
        args.source, "--", "--output-root", args.output_root,
        "--output-dir", args.output_dir, "--quality", "interaction",
        "--start-frame", "1", "--end-frame", "1", "--build-only",
    ]
    return runpy.run_path(args.source, run_name="__main__")


def world_point(rig_eval, bone, endpoint):
    return rig_eval.matrix_world @ getattr(bone, endpoint)


def evaluated_mesh(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    points = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
    normal_matrix = evaluated.matrix_world.to_3x3().inverted().transposed()
    down_faces = []
    for polygon in mesh.polygons:
        normal = (normal_matrix @ polygon.normal).normalized()
        if normal.z < -0.6:
            down_faces.append((polygon.area, normal))
    if not points:
        evaluated.to_mesh_clear()
        raise RuntimeError(f"evaluated mesh is empty: {obj.name}")
    low = min(point.z for point in points)
    center = sum(points, start=points[0] * 0) / len(points)
    tilt = 90.0
    if down_faces:
        normal = max(down_faces, key=lambda item: item[0])[1]
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, -normal.z))))
    evaluated.to_mesh_clear()
    return low, center, tilt


def phase_rows(rows):
    """Infer planted/takeoff/swing/landing/settled intervals from target motion."""
    base_z = rows[0]["target"][2]
    has_moved = False
    has_lifted = False
    previous = rows[0]["target"]
    for index, row in enumerate(rows):
        target = row["target"]
        previous_elevation = previous[2] - base_z
        elevation = target[2] - base_z
        moving = math.dist(target, previous) > 0.0005 if index else False
        if moving:
            has_moved = True
            if elevation > 0.02:
                row["phase"] = "takeoff" if not has_lifted else "swing"
                has_lifted = True
            elif has_lifted:
                row["phase"] = "landing"
            else:
                row["phase"] = "takeoff"
        else:
            row["phase"] = "settled" if has_moved else "planted"
        row["target_elevation"] = elevation
        row["previous_target_elevation"] = previous_elevation
        previous = target
    return rows


def intervals(rows):
    result = []
    for row in rows:
        if not result or result[-1]["phase"] != row["phase"]:
            result.append({"phase": row["phase"], "start": row["frame"], "end": row["frame"]})
        else:
            result[-1]["end"] = row["frame"]
    return result


def hold_drift(rows):
    values = []
    run = []
    last_phase = None
    for row in rows + [None]:
        phase = row["phase"] if row else None
        if phase not in ("planted", "settled") or phase != last_phase:
            if run:
                origin = run[0]["center"]
                values.append(max(math.dist(origin[:2], item["center"][:2]) for item in run))
                run = []
        if row and phase in ("planted", "settled"):
            run.append(row)
        last_phase = phase
    return max(values, default=0.0)


def analyze(namespace):
    import bpy
    from mathutils import Vector

    scene, rig = namespace["scene"], namespace["rig"]
    floor = bpy.data.objects.get("Endless basalt floor")
    floor_eval = floor.evaluated_get(bpy.context.evaluated_depsgraph_get())
    floor_mesh = floor_eval.to_mesh()
    floor_z = max((floor_eval.matrix_world @ vertex.co).z for vertex in floor_mesh.vertices)
    floor_eval.to_mesh_clear()

    feet = {side: [] for side in ("L", "R")}
    previous_joints = {}
    max_joint_step = {joint: 0.0 for joint in ("hip", "knee", "ankle")}
    max_chain_length_error = 0.0
    max_ankle_foot_gap = 0.0
    max_foot_toe_gap = 0.0
    min_knee_forward_offset = float("inf")

    for frame in range(1, scene.frame_end + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        rig_eval = rig.evaluated_get(depsgraph)
        pose = rig_eval.pose.bones

        for side in ("L", "R"):
            thigh = pose["thigh." + side]
            shin = pose["shin." + side]
            foot = pose["foot." + side]
            toe = pose["toe." + side]
            target = world_point(rig_eval, pose["foot_ik." + side], "head")
            ankle = world_point(rig_eval, shin, "tail")
            hip = world_point(rig_eval, thigh, "head")
            knee = world_point(rig_eval, thigh, "tail")
            sole_low, sole_center, sole_tilt = evaluated_mesh(
                bpy.data.objects["Foot | broad grounded sole " + side], depsgraph
            )
            toe_low, _, toe_tilt = evaluated_mesh(
                bpy.data.objects["Foot | toe cap " + side], depsgraph
            )

            joints = {"hip": hip, "knee": knee, "ankle": ankle}
            for name, position in joints.items():
                if (side, name) in previous_joints:
                    step = (position - previous_joints[(side, name)]).length
                    max_joint_step[name] = max(max_joint_step[name], step)
                previous_joints[(side, name)] = position.copy()

            line = ankle - hip
            line_length_squared = max(line.length_squared, 1e-12)
            knee_from_hip = knee - hip
            along = knee_from_hip.dot(line) / line_length_squared
            knee_offset = knee_from_hip - line * along
            min_knee_forward_offset = min(min_knee_forward_offset, -knee_offset.y)

            rest_thigh = rig.data.bones["thigh." + side].length
            rest_shin = rig.data.bones["shin." + side].length
            max_chain_length_error = max(
                max_chain_length_error,
                abs(thigh.length - rest_thigh),
                abs(shin.length - rest_shin),
            )
            max_ankle_foot_gap = max(max_ankle_foot_gap, (ankle - world_point(rig_eval, foot, "head")).length)
            max_foot_toe_gap = max(max_foot_toe_gap, (
                world_point(rig_eval, foot, "tail") - world_point(rig_eval, toe, "head")
            ).length)
            feet[side].append({
                "frame": frame,
                "target": [target.x, target.y, target.z],
                "residual": (ankle - target).length,
                "minz": min(sole_low, toe_low),
                "sole_minz": sole_low,
                "toe_minz": toe_low,
                "center": [sole_center.x, sole_center.y, sole_center.z],
                "tilt": max(sole_tilt, toe_tilt),
                "knee_forward_offset": -knee_offset.y,
            })

    report = {
        "source": namespace.get("__file__", "unknown"),
        "floor_z_m": floor_z,
        "frame_count": scene.frame_end,
        "tolerances": {
            "max_penetration_m": 0.01,
            "max_planted_height_error_m": 0.01,
            "max_planted_xy_drift_m": 0.02,
            "max_target_residual_m": 0.02,
            "min_swing_peak_clearance_m": 0.08,
            "max_joint_step_m": 0.15,
            "max_chain_length_error_m": 0.002,
            "max_joint_gap_m": 0.002,
            "min_knee_forward_offset_m": -0.01,
        },
        "feet": {},
        "joint_integrity": {},
        "failures": [],
    }

    for side, raw_rows in feet.items():
        rows = phase_rows(raw_rows)
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["phase"]].append(row)
        all_clearance = [row["minz"] - floor_z for row in rows]
        all_residuals = [row["residual"] for row in rows]
        foot_report = {
            "intervals": intervals(rows),
            "all_frames": {
                "max_penetration_m": max(0.0, -min(all_clearance)),
                "worst_target_residual_m": max(all_residuals),
                "min_knee_forward_offset_m": min(row["knee_forward_offset"] for row in rows),
            },
            "phase_metrics": {},
        }
        if min(all_clearance) < -0.01:
            report["failures"].append(f"{side}: foot mesh penetrates more than 0.01 m")
        if max(all_residuals) > 0.02:
            report["failures"].append(f"{side}: ankle target residual exceeds 0.02 m")
        if min(row["knee_forward_offset"] for row in rows) < -0.01:
            report["failures"].append(f"{side}: knee flips behind the leg line")

        for phase, rows_in_phase in grouped.items():
            clearance = [row["minz"] - floor_z for row in rows_in_phase]
            metric = {
                "frames": [rows_in_phase[0]["frame"], rows_in_phase[-1]["frame"]],
                "min_clearance_m": min(clearance),
                "max_clearance_m": max(clearance),
                "max_target_residual_m": max(row["residual"] for row in rows_in_phase),
                "max_sole_tilt_deg": max(row["tilt"] for row in rows_in_phase),
            }
            if phase in ("planted", "settled"):
                metric["max_abs_sole_height_error_m"] = max(abs(value) for value in clearance)
                metric["max_xy_drift_m"] = hold_drift(rows_in_phase)
                if metric["max_abs_sole_height_error_m"] > 0.01:
                    report["failures"].append(f"{side}/{phase}: sole is more than 0.01 m from floor")
                if metric["max_xy_drift_m"] > 0.02:
                    report["failures"].append(f"{side}/{phase}: planted foot drifts more than 0.02 m")
            if phase in ("takeoff", "swing", "landing") and min(clearance) < -0.01:
                report["failures"].append(f"{side}/{phase}: foot penetrates the floor")
            foot_report["phase_metrics"][phase] = metric

        swing_clearances = [
            row["minz"] - floor_z for row in rows
            if row["phase"] in ("takeoff", "swing", "landing")
        ]
        foot_report["swing_motion"] = {
            "min_clearance_m": min(swing_clearances),
            "peak_clearance_m": max(swing_clearances),
        }
        if max(swing_clearances) < 0.08:
            report["failures"].append(f"{side}: step lacks 0.08 m measured swing clearance")
        report["feet"][side] = foot_report

    report["joint_integrity"] = {
        "max_hip_step_m": max_joint_step["hip"],
        "max_knee_step_m": max_joint_step["knee"],
        "max_ankle_step_m": max_joint_step["ankle"],
        "max_chain_length_error_m": max_chain_length_error,
        "max_shin_ankle_to_foot_head_gap_m": max_ankle_foot_gap,
        "max_foot_to_toe_joint_gap_m": max_foot_toe_gap,
        "min_knee_forward_offset_m": min_knee_forward_offset,
    }
    t = report["tolerances"]
    if max_joint_step["hip"] > t["max_joint_step_m"] or max_joint_step["knee"] > t["max_joint_step_m"] or max_joint_step["ankle"] > t["max_joint_step_m"]:
        report["failures"].append("leg joint has a frame-to-frame discontinuity")
    if max_chain_length_error > t["max_chain_length_error_m"]:
        report["failures"].append("IK chain changes rest bone length")
    if max_ankle_foot_gap > t["max_joint_gap_m"] or max_foot_toe_gap > t["max_joint_gap_m"]:
        report["failures"].append("ankle/foot/toe joints detach")
    report["pass"] = not report["failures"]
    return report


def main():
    args = parse_args()
    namespace = build_scene(args)
    report = analyze(namespace)
    print("P7_FOOT_CONTACT_REPORT " + json.dumps(report, sort_keys=True), flush=True)
    if args.expect_failure and report["pass"]:
        raise SystemExit("baseline unexpectedly passed foot-contact acceptance")
    if not args.expect_failure and not report["pass"]:
        raise SystemExit("P7 foot-contact acceptance failed")


if __name__ == "__main__":
    main()
