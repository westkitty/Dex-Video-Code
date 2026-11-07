"""Procedural Lantern Sentinel production scene for Blender 5.x.

This is authored character animation, not a physics simulation. It preserves the
P7 proof character's compact armored body, rounded helmet, cyan eyes, brass trim
and amber chest lantern while adding contact-aware authored foot and hand IK.
Run in Blender background mode; all output paths must remain under --output-root.
"""
import argparse
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


def arguments():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--quality", choices=("interaction", "preview", "master"), default="interaction")
    parser.add_argument("--start-frame", type=int, default=1)
    parser.add_argument("--end-frame", type=int, default=48)
    parser.add_argument("--save-blend", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.output_root).expanduser().resolve()
    out = Path(args.output_dir).expanduser().resolve()
    if root == out or root not in out.parents:
        raise SystemExit("output-dir must be a child of output-root")
    if args.start_frame < 1 or args.end_frame > 240 or args.end_frame < args.start_frame:
        raise SystemExit("frame range must be within 1..240")
    if args.end_frame - args.start_frame + 1 > 48:
        raise SystemExit("each invocation is limited to 48 frames")
    out.mkdir(parents=True, exist_ok=True)
    return args, root, out


args, ROOT, OUT = arguments()
if any(OUT.glob("frame_*.png")):
    raise SystemExit("output directory already contains frames; refusing overwrite")

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = {
    "interaction": (320, 180), "preview": (640, 360), "master": (1280, 720)
}[args.quality]
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.color_depth = "8"
scene.render.film_transparent = False
scene.render.threads_mode = "FIXED"
scene.render.threads = 6
scene.render.use_file_extension = True
scene.render.image_settings.compression = 18
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.render.fps = 24
scene.frame_start, scene.frame_end = 1, 240
scene.render.filepath = str(OUT / "frame_")
scene.eevee.taa_render_samples = {"interaction": 8, "preview": 16, "master": 32}[args.quality]


def mat(name, color, metallic=0.0, rough=0.5, emission=None, power=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    bs = m.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (*color, 1)
    bs.inputs["Metallic"].default_value = metallic
    bs.inputs["Roughness"].default_value = rough
    if emission:
        bs.inputs["Emission Color"].default_value = (*emission, 1)
        bs.inputs["Emission Strength"].default_value = power
    return m


armor = mat("Sentinel | blackened iron", (0.028, .046, .058), .82, .27)
armor_edge = mat("Sentinel | satin steel", (.19, .24, .24), .78, .24)
brass = mat("Sentinel | aged brass", (.42, .22, .075), .8, .29)
ceramic = mat("Sentinel | ivory ceramic", (.49, .46, .36), .24, .32)
jointmat = mat("Sentinel | joint graphite", (.009, .014, .017), .35, .39)
amber = mat("Sentinel | living amber", (.95, .25, .025), .05, .22, (1, .16, .015), 2.1)
cyan = mat("Sentinel | watchful eyes", (.02, .27, .34), .15, .19, (.015, .53, .72), 2.4)
stone = mat("Chamber | basalt", (.027, .035, .039), .18, .76)
stone_edge = mat("Chamber | worn edges", (.12, .105, .078), .48, .47)
unlit = mat("Mechanism | sleeping glass", (.055, .085, .075), .42, .28)
live = mat("Mechanism | awakened gold", (.8, .34, .055), .12, .22, (1, .42, .07), 4.2)
wake = mat("Mechanism | authored light response", (.04, .055, .045), .2, .22, (.01, .015, .01), .0)


def cube(name, loc, scale, material, bevel=.04):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.data.materials.append(material)
    if bevel:
        b = ob.modifiers.new("Soft-cut machined edges", "BEVEL")
        b.width, b.segments = bevel, 3
        ob.modifiers.new("Corner normals", "WEIGHTED_NORMAL")
    return ob


def uv(name, loc, scale, material, segments=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=16, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    ob.data.materials.append(material)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def cyl(name, loc, radius, depth, material, rotation=(0, 0, 0), vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation)
    ob = bpy.context.object
    ob.name = name
    ob.data.materials.append(material)
    bevel = ob.modifiers.new("Turned rim", "BEVEL")
    bevel.width, bevel.segments = .018, 2
    ob.modifiers.new("Machined normals", "WEIGHTED_NORMAL")
    return ob


def aim(ob, target):
    ob.rotation_euler = (Vector(target) - ob.location).to_track_quat("-Z", "Y").to_euler()


# Twelve-segment chamber: broad dark walls, aged ribs, an aperture behind the altar.
cube("Endless basalt floor", (0, 0, -.13), (30, 30, .25), stone, 0)
cube("Rear chamber wall", (0, 3.2, 3.4), (11, .35, 7), stone, .08)
for x in (-4.8, -3.2, -1.6, 0, 1.6, 3.2, 4.8):
    cube("Ancient wall pilaster", (x, 2.96, 3.35), (.13, .19, 6.55), stone_edge, .045)
    cyl("Pilaster collar", (x, 2.82, 4.9), .14, .09, brass, (math.pi / 2, 0, 0))
for x in (-4, -2, 0, 2, 4):
    cube("Floor joint | worn brass", (x, -.1, .004), (.018, 12, .008), stone_edge, 0)

# The one external mechanism is both visually distinct and reachable from the final stance.
altar_y, altar_x = -.75, .62
cube("Dormant mechanism plinth", (altar_x, altar_y, .80), (1.2, .86, 1.6), stone_edge, .14)
cube("Plinth shadow reveal", (altar_x, altar_y - .02, 1.62), (1.08, .77, .13), armor, .045)
cyl("Mechanism lower bezel", (altar_x, altar_y - .12, 1.95), .40, .15, brass, (math.pi / 2, 0, 0))
cyl("Mechanism dark face", (altar_x, altar_y - .205, 1.95), .33, .045, unlit, (math.pi / 2, 0, 0))
for a in range(8):
    angle = a * math.tau / 8
    uv("Bezel pin", (altar_x + math.cos(angle)*.35, altar_y - .24, 1.95 + math.sin(angle)*.35), (.028,.018,.028), brass, 12)
mechanism_lens = uv("Sleeping mechanism heart", (altar_x, altar_y - .255, 1.95), (.16,.045,.16), wake)
mechanism_lens.name = "Mechanism response | gold wakes at contact"
for x in (-.13, 0, .13):
    cube("Mechanism vertical engraving", (altar_x+x, altar_y-.25, 1.95), (.018,.012,.20), stone_edge, .006)
lever = cube("Mechanism | contact lever", (altar_x, altar_y-.32, 1.95), (.54,.075,.09), brass, .035)
for frame, angle in ((1,0.0),(168,0.0),(169,-.04),(176,-.56),(192,-.56),(240,-.56)):
    lever.rotation_euler.y=angle
    lever.keyframe_insert(data_path="rotation_euler",frame=frame)

# Armature preserves the proof identity and makes every visible limb a real bone-driven part.
arm = bpy.data.armatures.new("Sentinel performance skeleton")
rig = bpy.data.objects.new("Lantern Sentinel | articulated original", arm)
scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
eb = {}
def bone(name, head, tail, parent=None, connected=False):
    b = arm.edit_bones.new(name)
    b.head, b.tail = head, tail
    if parent:
        b.parent = eb[parent]
        b.use_connect = connected
    eb[name] = b

bone("root", (0,0,0), (0,0,.3))
bone("pelvis", (0,0,1.45), (0,0,1.85), "root")
bone("spine", (0,0,1.85), (0,0,2.68), "pelvis", True)
bone("neck", (0,0,2.68), (0,0,3.00), "spine", True)
bone("head", (0,0,3.00), (0,0,3.48), "neck", True)
for side, sign in (("L", -1), ("R", 1)):
    bone("clavicle."+side, (0,0,2.56), (sign*.43,0,2.56), "spine")
    bone("upper_arm."+side, (sign*.43,0,2.56), (sign*.55,-.02,2.04), "clavicle."+side)
    bone("forearm."+side, (sign*.55,-.02,2.04), (sign*.54,-.06,1.61), "upper_arm."+side, True)
    bone("hand."+side, (sign*.54,-.06,1.61), (sign*.54,-.24,1.58), "forearm."+side, True)
    for f in range(3):
        bone(f"finger{f}.{side}", (sign*.54+(f-1)*.09,-.20,1.58), (sign*.54+(f-1)*.11,-.34,1.55), "hand."+side)
    bone("thigh."+side, (sign*.20,0,1.46), (sign*.20,0,.82), "pelvis")
    bone("shin."+side, (sign*.20,0,.82), (sign*.20,0,.17), "thigh."+side, True)
    bone("foot."+side, (sign*.20,0,.17), (sign*.20,-.34,.14), "shin."+side, True)
    bone("toe."+side, (sign*.20,-.34,.14), (sign*.20,-.49,.13), "foot."+side, True)
    # IK controls are independent root children, making authored foot plants explicit.
    bone("foot_ik."+side, (sign*.20,-.06,.14), (sign*.20,-.30,.14), "root")
    bone("knee_pole."+side, (sign*.20,-1.0,.82), (sign*.20,-1.15,.82), "root")
bone("hand_ik.R", (.54,-.24,1.58), (.54,-.45,1.58), "root")
bone("hand_ik.L", (-.54,-.24,1.58), (-.54,-.45,1.58), "root")
bpy.ops.object.mode_set(mode="OBJECT")
rig.show_in_front = True
pose = rig.pose.bones
for p in pose:
    p.rotation_mode = "XYZ"

def add_ik(chain, target, count, pole=None):
    c = pose[chain].constraints.new("IK")
    c.target, c.subtarget, c.chain_count = rig, target, count
    c.use_stretch = False
    c.iterations = 64
    if pole:
        c.pole_target, c.pole_subtarget = rig, pole
        c.pole_angle = math.pi / 2

add_ik("shin.L", "foot_ik.L", 2, "knee_pole.L")
add_ik("shin.R", "foot_ik.R", 2, "knee_pole.R")
add_ik("forearm.R", "hand_ik.R", 2)

def bind_mesh(ob, bone_name):
    group = ob.vertex_groups.new(name=bone_name)
    group.add([v.index for v in ob.data.vertices], 1.0, "REPLACE")
    mod = ob.modifiers.new("Driven by Sentinel skeleton", "ARMATURE")
    mod.object = rig
    return ob

def partbox(name, loc, dims, material, bone_name, bevel=.045):
    return bind_mesh(cube(name, loc, dims, material, bevel), bone_name)

def partuv(name, loc, scale, material, bone_name, segments=20):
    return bind_mesh(uv(name, loc, scale, material, segments), bone_name)

def partsegment(name, a, b, dims, material, bone_name, bevel=.04):
    a, b = Vector(a), Vector(b)
    ob = cube(name, (a+b)*.5, (dims[0], dims[1], (b-a).length), material, bevel)
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Vector((0,0,1)).rotation_difference((b-a).normalized())
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    return bind_mesh(ob, bone_name)

# Deliberate layered silhouette: domed helmet, brow, shoulder pauldrons and tapered shin guards.
partbox("Torso | compact cuirass", (0,0,2.29), (.78,.48,.77), armor, "spine", .13)
partbox("Torso | raised shoulder yoke", (0,-.005,2.56), (.93,.50,.22), armor_edge, "spine", .09)
partbox("Chest | beveled brass bezel", (0,-.253,2.34), (.58,.045,.59), brass, "spine", .085)
partuv("Chest | lantern housing", (0,-.295,2.35), (.218,.065,.235), jointmat, "spine")
partuv("Chest | living amber lens", (0,-.350,2.35), (.148,.035,.166), amber, "spine")
for z in (2.08, 2.62):
    partbox("Chest | engraved reveal", (0,-.284,z), (.38,.026,.018), armor_edge, "spine", .008)
partbox("Pelvis | articulated waist", (0,0,1.63), (.59,.44,.38), armor, "pelvis", .09)
partbox("Pelvis | brass front plate", (0,-.229,1.64), (.40,.035,.24), brass, "pelvis", .05)
partuv("Helmet | rounded cranial shell", (0,0,3.20), (.355,.315,.35), armor, "head", 32)
partuv("Helmet | ceramic crown", (0,.015,3.37), (.25,.26,.15), ceramic, "head", 24)
partbox("Helmet | brow guard", (0,-.282,3.20), (.48,.075,.12), brass, "head", .045)
partbox("Helmet | dark visor", (0,-.326,3.18), (.39,.045,.105), jointmat, "head", .028)
for side, x in (("L",-.105),("R",.105)):
    partuv("Optic | " + side, (x,-.356,3.18), (.057,.026,.038), cyan, "head", 20)
    partuv("Helmet | side hinge " + side, (x*2.2,0,3.19), (.065,.30,.075), brass, "head")
partuv("Neck | turned collar", (0,0,2.88), (.235,.22,.10), brass, "neck")
for side, s in (("L",-1),("R",1)):
    partuv("Shoulder | spherical bearing " + side, (s*.47,0,2.52), (.19,.205,.19), brass, "clavicle."+side)
    partsegment("Upper arm | ceramic shell "+side,(s*.48,0,2.48),(s*.55,-.02,2.04),(.25,.30),ceramic,"upper_arm."+side,.06)
    partuv("Elbow | exposed bearing "+side,(s*.55,-.02,2.04),(.125,.14,.125),jointmat,"upper_arm."+side)
    partsegment("Forearm | tapered gauntlet "+side,(s*.55,-.02,2.02),(s*.54,-.06,1.62),(.22,.26),armor_edge,"forearm."+side,.055)
    partbox("Gauntlet | brass cuff "+side,(s*.54,-.055,1.73),(.25,.29,.11),brass,"forearm."+side,.035)
    partuv("Hand | palm "+side,(s*.54,-.15,1.58),(.135,.17,.105),armor,"hand."+side)
    for f in range(3):
        x=s*.54+(f-1)*.09
        partsegment(f"Hand | articulated finger {f+1} {side}",(x,-.21,1.56),(x,-.32,1.52),(.052,.060),brass,f"finger{f}.{side}",.016)
    partsegment("Thigh | armored greave "+side,(s*.20,0,1.45),(s*.20,0,.83),(.31,.34),armor,"thigh."+side,.065)
    partuv("Knee | brass bearing "+side,(s*.20,-.015,.82),(.17,.18,.15),brass,"thigh."+side)
    partsegment("Shin | ivory guard "+side,(s*.20,0,.80),(s*.20,-.015,.18),(.245,.29),ceramic,"shin."+side,.045)
    partbox("Foot | broad grounded sole "+side,(s*.20,-.16,.105),(.37,.55,.17),armor,"foot."+side,.055)
    partbox("Foot | toe cap "+side,(s*.20,-.39,.15),(.34,.18,.12),brass,"toe."+side,.04)
    partbox("Shin | brass front inlay "+side,(s*.20,-.155,.51),(.06,.025,.34),brass,"shin."+side,.012)

# Restrained room accents: two lamps only wake after the central mechanism is touched.
chamber_lamps = []
for x in (-3.2, 3.2):
    p = uv("Wall sconce | dormant", (x,2.78,2.65), (.18,.065,.26), unlit)
    chamber_lamps.append(p)
    ld = bpy.data.lights.new("Wall sconce | warm response", "POINT")
    ld.energy, ld.color, ld.shadow_soft_size = 0.0, (1.0,.39,.12), .8
    lo = bpy.data.objects.new("Wall sconce | response light", ld)
    scene.collection.objects.link(lo)
    lo.location = (x,2.45,2.6)
    chamber_lamps.append(lo)

# Camera: a single composed three-quarter shot; gentle authored push, no shake.
cam_data = bpy.data.cameras.new("Chamber portrait camera")
cam = bpy.data.objects.new("Chamber portrait camera", cam_data)
scene.collection.objects.link(cam)
cam.location = (-4.5,-10.8,3.8)
aim(cam,(.35,-.35,1.75))
cam_data.lens = 40
scene.camera = cam
for frame, lens in ((1,40),(240,43)):
    cam_data.lens = lens
    cam_data.keyframe_insert(data_path="lens", frame=frame)

def area(name, loc, power, color, size, target):
    ld = bpy.data.lights.new(name,"AREA")
    ld.energy, ld.color, ld.shape, ld.size = power,color,"DISK",size
    lo = bpy.data.objects.new(name,ld)
    scene.collection.objects.link(lo)
    lo.location=loc
    aim(lo,target)
    return lo

area("Cool moon shaft",(-4,-5,6),780,(.46,.64,.78),5,(0,0,2))
area("Old brass bounce",(3,-3,3.6),260,(1,.48,.20),3,(.5,-1,1.4))
area("Silhouette rim",(0,2.35,5),920,(.40,.62,.78),3,(0,0,2))
world=bpy.data.worlds.new("Abandoned chamber | near darkness")
scene.world=world
world.use_nodes=True
world.node_tree.nodes["Background"].inputs["Color"].default_value=(.012,.018,.023,1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value=.16

# World-coordinate foot and hand targets. Their contact holds are explicit keyframed poses.
def keyloc(name, frame, loc):
    b=pose[name]
    b.location=b.bone.matrix_local.to_3x3().inverted() @ (Vector(loc)-Vector(b.bone.head_local))
    b.keyframe_insert(data_path="location",frame=frame)

def keyrot(name, frame, rot):
    pose[name].rotation_euler=rot
    pose[name].keyframe_insert(data_path="rotation_euler",frame=frame)

def keyed(name, frames, mode="location"):
    b=pose[name]
    for frame, value in frames:
        if mode=="location":
            b.location=b.bone.matrix_local.to_3x3().inverted() @ Vector(value)
        else:
            b.rotation_euler=value
        b.keyframe_insert(data_path=mode,frame=frame)

# Quiet sentinel hold, then head leads the body turn toward the sleeping altar.
for f in (1,48,96,110,128,144,192,240):
    pose["hand_ik.L"].keyframe_insert(data_path="location",frame=f)
for n in ("pelvis","spine","neck","head","upper_arm.R","forearm.R","hand.R"):
    pose[n].keyframe_insert(data_path="rotation_euler",frame=1)

# Attention: eyes/head move first; shoulders and torso follow, with a settling overshoot.
keyed("head",[(48,(0,0,0)),(54,(0,.04,-.12)),(66,(0,.02,-.30)),(82,(0,0,-.24)),(96,(0,0,-.24))],"rotation_euler")
keyed("neck",[(48,(0,0,0)),(60,(0,0,-.10)),(78,(0,0,-.13)),(96,(0,0,-.12))],"rotation_euler")
keyed("spine",[(48,(0,0,0)),(72,(0,0,-.10)),(88,(0,0,-.14)),(96,(0,0,-.12))],"rotation_euler")
keyed("pelvis",[(48,(0,0,0)),(80,(0,.02,-.08)),(96,(0,0,-.08))],"rotation_euler")

# A short two-step approach: IK targets lift/advance/plant; feet remain still between steps.
# The torso leans and translates only after each foot starts its swing.
for name, seq in {
    "foot_ik.L":[(96,(0,0,0)),(98,(0,0,0)),(104,(0,-.27,.18)),(110,(0,-.55,0)),(144,(0,-.55,0)),(240,(0,-.55,0))],
    "foot_ik.R":[(96,(0,0,0)),(112,(0,0,0)),(116,(0,-.03,0)),(122,(0,-.30,.18)),(128,(0,-.60,0)),(144,(0,-.60,0)),(240,(0,-.60,0))],
}.items():
    keyed(name,seq)
keyed("pelvis",[(96,(0,0,-.08)),(104,(0,-.22,-.04)),(110,(0,-.55,.02)),(122,(0,-.56,-.015)),(128,(0,-.60,.025)),(144,(0,-.60,0)),(240,(0,-.60,0))],"location")
keyed("spine",[(96,(0,0,-.12)),(106,(.035,0,-.18)),(112,(0,0,-.12)),(124,(.025,0,-.16)),(132,(0,0,-.10)),(144,(0,0,-.08)),(240,(0,0,-.08))],"rotation_euler")
keyed("head",[(96,(0,0,-.24)),(112,(0,0,-.31)),(128,(0,0,-.22)),(144,(0,0,-.18)),(192,(0,0,-.18)),(204,(0,.03,-.10)),(218,(0,0,.04)),(240,(0,0,.04))],"rotation_euler")

# Reach IK is eased into a real contact point; the mechanism response begins at frame 169.
keyed("hand_ik.R",[(1,(0,0,0)),(144,(0,0,0)),(150,(.05,-.12,.08)),(158,(.12,-.34,.22)),(166,(.28,-.88,.37)),(168,(.28,-.88,.37)),(174,(.28,-.88,.37)),(184,(.26,-.86,.35)),(192,(.26,-.86,.35)),(240,(.26,-.86,.35))])
keyed("upper_arm.R",[(144,(0,0,0)),(152,(.05,0,-.05)),(160,(.08,0,-.08)),(166,(.06,0,-.04)),(168,(.04,0,0)),(180,(0,0,-.015)),(192,(0,0,0))],"rotation_euler")
keyed("head",[(144,(0,0,-.18)),(154,(.06,0,-.30)),(168,(.08,0,-.32)),(184,(.03,0,-.25)),(192,(0,0,-.18))],"rotation_euler")

def animate_scalar(obj, prop, values):
    for frame,val in values:
        setattr(obj,prop,val)
        obj.keyframe_insert(data_path=prop,frame=frame)

mechanism_lens.data.materials.clear()
mechanism_lens.data.materials.append(wake)
for frame, color, strength in ((1,(.04,.055,.045,1),0.0),(168,(.04,.055,.045,1),0.0),(169,(.8,.34,.055,1),.35),(176,(.95,.42,.08,1),4.2),(192,(.95,.42,.08,1),4.2),(240,(.95,.42,.08,1),4.2)):
    wake.diffuse_color=color
    wake.keyframe_insert(data_path="diffuse_color",frame=frame)
    bs=wake.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Emission Color"].default_value=color
    bs.inputs["Emission Color"].keyframe_insert(data_path="default_value",frame=frame)
    bs.inputs["Emission Strength"].default_value=strength
    bs.inputs["Emission Strength"].keyframe_insert(data_path="default_value",frame=frame)
for o in chamber_lamps:
    if o.type=="LIGHT":
        for f,val in ((1,0.0),(168,0.0),(169,280.0),(184,390.0),(240,390.0)):
            o.data.energy=val
            o.data.keyframe_insert(data_path="energy",frame=f)
    else:
        o.data.materials.clear()
        o.data.materials.append(wake)

# Use cubic easing for deliberate anticipation/follow-through; retain linear foot swing to avoid overshoot.
for owner in (rig, cam, wake):
    if owner.animation_data and owner.animation_data.action:
        for fc in getattr(owner.animation_data.action, "fcurves", ()):
            control = "foot_ik" in fc.data_path
            for point in fc.keyframe_points:
                point.interpolation = "LINEAR" if control else "BEZIER"
                point.handle_left_type = "AUTO_CLAMPED"
                point.handle_right_type = "AUTO_CLAMPED"

# Blender 5.2 removed the legacy scene compositor tree API used in the proof.
# Emissive eyes, chest core and mechanism remain direct, restrained light sources.

scene.frame_set(1)
if args.save_blend:
    blend=ROOT / "lantern-sentinel-production.blend"
    if blend.exists():
        raise SystemExit("production .blend already exists; refusing overwrite")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
if args.build_only:
    print("P7_SCENE_REPORT",json.dumps({"blender":bpy.app.version_string,"engine":scene.render.engine,"gpu_backend":bpy.context.preferences.system.gpu_backend,"frames":scene.frame_end,"bones":len(arm.bones),"objects":len(scene.objects),"ik_constraints":sum(1 for b in pose for c in b.constraints if c.type=="IK"),"authored_animation":True,"physics_simulation":False}),flush=True)
    for frame in (1,110,128,145,166,169,192):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        evaluated=rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        ep=evaluated.pose.bones
        point=lambda name,attr: tuple(round(float(v),3) for v in (evaluated.matrix_world @ getattr(ep[name],attr)))
        print("P7_RIG_CHECK",json.dumps({"frame":frame,"pelvis":point("pelvis","head"),"left_ankle":point("shin.L","tail"),"left_foot_target":point("foot_ik.L","head"),"right_wrist":point("forearm.R","tail"),"right_hand_target":point("hand_ik.R","head")}),flush=True)
else:
    records=[]
    free_start=shutil.disk_usage(ROOT).free
    for frame in range(args.start_frame,args.end_frame+1):
        scene.frame_set(frame)
        path=OUT / ("frame_%04d.png" % frame)
        if path.exists():
            raise RuntimeError("refusing to overwrite existing rendered frame")
        scene.render.filepath=str(path)
        started=time.perf_counter()
        bpy.ops.render.render(write_still=True)
        elapsed=time.perf_counter()-started
        size=path.stat().st_size
        records.append({"frame":frame,"seconds":round(elapsed,3),"bytes":size})
        print("P7_FRAME",json.dumps(records[-1]),flush=True)
        if elapsed>60:
            raise RuntimeError("stop gate: one preview frame exceeded 60 seconds")
    print("P7_RENDER_REPORT",json.dumps({
        "blender":bpy.app.version_string,"engine":scene.render.engine,
        "gpu_backend":bpy.context.preferences.system.gpu_backend,
        "quality":args.quality,"resolution":[scene.render.resolution_x,scene.render.resolution_y],
        "range":[args.start_frame,args.end_frame],"seconds":round(sum(x["seconds"] for x in records),3),
        "frame_count":len(records),"rendered_bytes":sum(x["bytes"] for x in records),
        "disk_free_before":free_start,"disk_free_after":shutil.disk_usage(ROOT).free,
        "max_rss":__import__("resource").getrusage(__import__("resource").RUSAGE_SELF).ru_maxrss,
        "bones":len(arm.bones),"authored_animation":True,"physics_simulation":False
    }),flush=True)
