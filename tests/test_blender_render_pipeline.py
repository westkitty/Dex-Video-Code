"""Unit tests for Blender render pipeline, asset library, frame QA gate, and batch runner."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import blender_asset_library as bal  # noqa: E402
import blender_batch_runner as bbr  # noqa: E402
import blender_render_pipeline as brp  # noqa: E402
import frame_qa_gate as fqg  # noqa: E402


class FakeSocket:
    def __init__(self, name: str, identifier: str | None = None):
        self.name = name
        self.identifier = identifier or name
        self.default_value = None
        self.links: list[object] = []

    @property
    def is_linked(self) -> bool:
        return bool(self.links)


class FakeSocketCollection(list):
    def __getitem__(self, key):
        if isinstance(key, str):
            for s in self:
                if s.name == key or s.identifier == key:
                    return s
            raise KeyError(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        if isinstance(key, str):
            return any(s.name == key or s.identifier == key for s in self)
        return super().__contains__(key)


class FakeNode:
    def __init__(self, ntype: str):
        self.type = ntype
        if ntype == "CompositorNodeRLayers":
            self.outputs = FakeSocketCollection([
                FakeSocket("Image"),
                FakeSocket("DiffCol"),
                FakeSocket("Normal"),
                FakeSocket("Mist"),
            ])
            self.inputs = FakeSocketCollection()
        elif ntype == "CompositorNodeDenoise":
            self.inputs = FakeSocketCollection([
                FakeSocket("Image"), FakeSocket("Albedo"), FakeSocket("Normal"),
                FakeSocket("HDR"), FakeSocket("Prefilter"),
            ])
            self.outputs = FakeSocketCollection([FakeSocket("Image")])
        elif ntype == "CompositorNodeGlare":
            self.inputs = FakeSocketCollection([
                FakeSocket("Image"), FakeSocket("Type"), FakeSocket("Quality"),
                FakeSocket("Threshold"), FakeSocket("Strength"), FakeSocket("Size"),
            ])
            self.outputs = FakeSocketCollection([FakeSocket("Image")])
        elif ntype == "ShaderNodeMix":
            self.data_type = "RGBA"
            self.blend_type = "MIX"
            self.inputs = FakeSocketCollection([
                FakeSocket("Factor", "Factor_Float"),
                FakeSocket("A", "A_Float"),
                FakeSocket("A", "A_Color"),
                FakeSocket("B", "B_Color"),
            ])
            self.outputs = FakeSocketCollection([
                FakeSocket("Result", "Result_Float"),
                FakeSocket("Result", "Result_Color"),
            ])
        elif ntype == "ShaderNodeMath":
            self.operation = "MULTIPLY"
            self.inputs = FakeSocketCollection([FakeSocket("Value"), FakeSocket("Value", "Value_001")])
            self.outputs = FakeSocketCollection([FakeSocket("Value")])
        elif ntype == "NodeGroupOutput":
            self.inputs = FakeSocketCollection([FakeSocket("Image"), FakeSocket("Geometry")])
            self.outputs = FakeSocketCollection()
        else:
            self.inputs = FakeSocketCollection([
                FakeSocket("Base Color"), FakeSocket("Distance"), FakeSocket("Fac"),
                FakeSocket("Color"), FakeSocket("Background"), FakeSocket("Surface"),
                FakeSocket("Density"), FakeSocket("Blackbody Intensity"), FakeSocket("Emission Strength"),
                FakeSocket("Volume"), FakeSocket("Temperature"), FakeSocket("Emission Color"),
                FakeSocket("Anisotropy"), FakeSocket("Vector"), FakeSocket("Generated"),
                FakeSocket("Object"), FakeSocket("Value"), FakeSocket("Scale"),
                FakeSocket("Mesh"), FakeSocket("Geometry"), FakeSocket("Points"),
                FakeSocket("Position"), FakeSocket("Offset"), FakeSocket("Instances"),
                FakeSocket("Instance"), FakeSocket("Material"), FakeSocket("Radius"),
                FakeSocket("Subdivisions"), FakeSocket("Frame"), FakeSocket("X"), FakeSocket("Y"), FakeSocket("Z"),
                FakeSocket("Strength"), FakeSocket("From Min"), FakeSocket("From Max"),
                FakeSocket("To Min"), FakeSocket("To Max"), FakeSocket("Detail"),
                FakeSocket("Roughness"),
            ])
            self.outputs = FakeSocketCollection([
                FakeSocket("Image"), FakeSocket("Color"), FakeSocket("BSDF"),
                FakeSocket("Value"), FakeSocket("Result"), FakeSocket("AO"),
                FakeSocket("Pointiness"), FakeSocket("Normal"), FakeSocket("Position"),
                FakeSocket("Vector"), FakeSocket("Fac"), FakeSocket("Volume"),
                FakeSocket("Geometry"), FakeSocket("Points"), FakeSocket("Mesh"),
                FakeSocket("Instances"), FakeSocket("Frame"), FakeSocket("X"), FakeSocket("Y"), FakeSocket("Z"),
                FakeSocket("Generated"), FakeSocket("Object"), FakeSocket("Background"),
            ])
            self.color_ramp = SimpleNamespace(elements=[SimpleNamespace(position=0.0, color=(0, 0, 0, 1)), SimpleNamespace(position=1.0, color=(1, 1, 1, 1))])


class FakeNodeTree:
    def __init__(self, ntype: str):
        self.type = ntype
        self.links_list: list[tuple[object, object]] = []
        self.nodes = SimpleNamespace(
            items=[],
            new=lambda nt: self._add(nt),
            clear=lambda: self.nodes.items.clear(),
        )
        self.interface = SimpleNamespace(new_socket=lambda **kw: None)
        self.links = SimpleNamespace(
            new=lambda f, t: self._link(f, t),
            remove=lambda lk: None,
        )

    def _add(self, nt: str) -> FakeNode:
        n = FakeNode(nt)
        self.nodes.items.append(n)
        return n

    def _link(self, f, t):
        self.links_list.append((f, t))
        t.links.append(SimpleNamespace(from_socket=f))


def make_fake_bpy():
    devices = [
        SimpleNamespace(name="Apple M4", type="CPU", use=False),
        SimpleNamespace(name="Apple M4 GPU", type="METAL", use=False),
    ]
    cycles_prefs = SimpleNamespace(compute_device_type="", devices=devices, get_devices=lambda: devices)
    node_groups: list[FakeNodeTree] = []
    worlds: list[SimpleNamespace] = []
    materials: list[SimpleNamespace] = []
    collections: list[SimpleNamespace] = []

    def new_ng(name, ntype):
        ng = FakeNodeTree(ntype)
        node_groups.append(ng)
        return ng

    def new_world(name):
        w = SimpleNamespace(
            name=name,
            use_nodes=True,
            node_tree=FakeNodeTree("ShaderNodeTree"),
            mist_settings=SimpleNamespace(use_mist=False, start=0.0, depth=0.0, falloff=""),
        )
        worlds.append(w)
        return w

    def new_mat(name):
        m = SimpleNamespace(name=name, use_nodes=True, node_tree=FakeNodeTree("ShaderNodeTree"))
        materials.append(m)
        return m

    def new_coll(name):
        c = SimpleNamespace(name=name, objects=SimpleNamespace(items=[], link=lambda o: c.objects.items.append(o)))
        collections.append(c)
        return c

    return SimpleNamespace(
        context=SimpleNamespace(
            preferences=SimpleNamespace(addons={"cycles": SimpleNamespace(preferences=cycles_prefs)}),
            view_layer=SimpleNamespace(use_pass_normal=False, use_pass_diffuse_color=False, use_pass_mist=False),
        ),
        data=SimpleNamespace(
            node_groups=SimpleNamespace(new=new_ng, items=node_groups),
            worlds=SimpleNamespace(new=new_world, items=worlds),
            materials=SimpleNamespace(new=new_mat, items=materials),
            collections=SimpleNamespace(new=new_coll, items=collections),
        ),
    )


def make_fake_scene():
    return SimpleNamespace(
        render=SimpleNamespace(
            engine="",
            resolution_x=0,
            resolution_y=0,
            resolution_percentage=0,
            fps=0,
            threads_mode="",
            threads=0,
            use_motion_blur=False,
            motion_blur_shutter=0.0,
            image_settings=SimpleNamespace(file_format="", color_mode="", color_depth="", compression=0),
        ),
        view_settings=SimpleNamespace(view_transform="", look=""),
        eevee=SimpleNamespace(
            taa_render_samples=0,
            use_raytracing=False,
            shadow_ray_count=0,
            shadow_step_count=0,
            shadow_resolution_scale=0.0,
            volumetric_tile_size="8",
            volumetric_samples=0,
            clamp_surface_indirect=0.0,
            use_taa_reprojection=False,
            motion_blur_steps=0,
        ),
        cycles=SimpleNamespace(
            samples=0,
            use_adaptive_sampling=False,
            adaptive_threshold=0.0,
            use_denoising=False,
            denoiser="",
            max_bounces=0,
            volume_bounces=0,
            device="",
        ),
        world=None,
        compositing_node_group=None,
    )


class BlenderPipelineTests(unittest.TestCase):
    def test_configure_eevee_and_cycles_metal(self):
        bpy = make_fake_bpy()
        scene = make_fake_scene()

        eevee_cfg = brp.configure_render_engine(scene, engine="eevee", quality="preview", threads=6, bpy_module=bpy)
        self.assertEqual(scene.render.engine, "BLENDER_EEVEE")
        self.assertEqual(eevee_cfg["resolution"], (640, 360))
        self.assertEqual(scene.eevee.taa_render_samples, 16)

        cycles_cfg = brp.configure_render_engine(scene, engine="cycles_metal", quality="hero", color_depth="16", bpy_module=bpy)
        self.assertEqual(scene.render.engine, "CYCLES")
        self.assertTrue(cycles_cfg["metal_gpu"])
        self.assertEqual(scene.cycles.device, "GPU")
        self.assertEqual(scene.cycles.denoiser, "OPENIMAGEDENOISE")
        self.assertEqual(scene.render.image_settings.color_depth, "16")

    def test_compositor_mist_sky_lightlink_volumefire_geonodes_lod(self):
        bpy = make_fake_bpy()
        scene = make_fake_scene()

        brp.configure_physical_sky_world(scene, bpy_module=bpy)
        self.assertIsNotNone(scene.world)
        brp.configure_mist_pass(scene, start=10.0, depth=60.0, view_layer=bpy.context.view_layer)
        self.assertTrue(bpy.context.view_layer.use_pass_mist)
        self.assertTrue(scene.world.mist_settings.use_mist)

        brp.configure_motion_blur(scene, enabled=True, shutter=0.45, steps=2)
        self.assertTrue(scene.render.use_motion_blur)

        ng = brp.configure_compositor_pipeline(scene, bpy_module=bpy)
        self.assertIs(scene.compositing_node_group, ng)
        node_types = [n.type for n in ng.nodes.items]
        self.assertIn("CompositorNodeDenoise", node_types)
        self.assertIn("CompositorNodeGlare", node_types)
        self.assertIn("ShaderNodeMix", node_types)

        light_obj = SimpleNamespace(name="FireL", light_linking=SimpleNamespace(receiver_collection=None, blocker_collection=None))
        target_obj = SimpleNamespace(name="Dragon", visible_shadow=True, visible_diffuse=True, modifiers=[SimpleNamespace(type="SUBSURF", levels=2, render_levels=2)])
        ll_res = brp.configure_light_linking(light_obj, include_objects=[target_obj], bpy_module=bpy)
        self.assertEqual(ll_res["receiver_count"], 1)

        vol_mat = brp.build_volumetric_fire_material(bpy_module=bpy)
        self.assertIn("ShaderNodeVolumePrincipled", [n.type for n in vol_mat.node_tree.nodes.items])

        brp.optimize_vfx_and_background_visibility([target_obj], disable_shadow=True)
        self.assertFalse(target_obj.visible_shadow)
        brp.apply_viewport_render_lod([target_obj], viewport_levels=1, render_levels=2)
        self.assertEqual(target_obj.modifiers[0].levels, 1)

        emitter = SimpleNamespace(
            visible_shadow=True,
            modifiers=SimpleNamespace(new=lambda name, mtype: SimpleNamespace(name=name, type=mtype, node_group=None)),
        )
        gn_mod = brp.create_geonodes_ember_system("Embers", emitter, vol_mat, bpy_module=bpy)
        self.assertEqual(gn_mod.type, "NODES")
        self.assertFalse(emitter.visible_shadow)

    def test_asset_library_manifest_verification_and_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            blend = root / "dragon_pack.blend"
            blend.write_bytes(b"BLENDER-v502dummybytes")
            manifest = bal.build_library_manifest(root, write_file=True)
            self.assertEqual(manifest["entry_count"], 1)
            verified = bal.verify_library_entry("dragon_pack.blend", root)
            self.assertEqual(verified["bytes"], len(b"BLENDER-v502dummybytes"))

            # Tampering fails checksum verification
            blend.write_bytes(b"TAMPERED")
            with self.assertRaises(ValueError):
                bal.verify_library_entry("dragon_pack.blend", root)

            # Symlink escape fails
            link_path = root / "evil.blend"
            link_path.symlink_to(blend)
            with self.assertRaises(ValueError):
                bal.build_library_manifest(root, write_file=False)

    def test_frame_qa_gate_and_batch_chunking(self):
        # Test frame QA gate evaluator logic
        good = [
            fqg.FrameMetrics("f1.png", mean_luma=52.0, min_luma=4.0, max_luma=240.0, low_luma=5.0, high_luma=238.0, mean_sat=48.0),
            fqg.FrameMetrics("f2.png", mean_luma=76.0, min_luma=4.0, max_luma=245.0, low_luma=5.0, high_luma=242.0, mean_sat=62.0),
        ]
        self.assertEqual(fqg.evaluate_frames(good)["status"], "PASS")

        dark = [fqg.FrameMetrics("dark.png", mean_luma=1.2, min_luma=0.0, max_luma=4.0, low_luma=0.0, high_luma=3.0, mean_sat=0.0)]
        self.assertEqual(fqg.evaluate_frames(dark, require_motion=False)["status"], "FAIL")

        frozen = [
            fqg.FrameMetrics("a.png", mean_luma=55.0, min_luma=5.0, max_luma=210.0, low_luma=6.0, high_luma=205.0, mean_sat=40.0),
            fqg.FrameMetrics("b.png", mean_luma=55.1, min_luma=5.0, max_luma=210.0, low_luma=6.0, high_luma=205.0, mean_sat=40.1),
        ]
        self.assertEqual(fqg.evaluate_frames(frozen, require_motion=True)["status"], "FAIL")

        # Test partition & sliding windows
        self.assertEqual(bbr.partition_frame_ranges(19, 30, 2), [(19, 24), (25, 30)])
        self.assertEqual(bbr.split_sliding_windows(1, 20, 8), [(1, 8), (9, 16), (17, 20)])

        cmd_hw, codec_hw = bbr.build_encode_args("ffmpeg", Path("f_%04d.png"), 1, 12, Path("o.mp4"), "preview_hw", {"h264_videotoolbox"})
        self.assertEqual(codec_hw, "h264")
        self.assertIn("h264_videotoolbox", cmd_hw)

        cmd_10, codec_10 = bbr.build_encode_args("ffmpeg", Path("f_%04d.png"), 1, 12, Path("o10.mp4"), "master_10bit", set())
        self.assertEqual(codec_10, "hevc")
        self.assertIn("yuv420p10le", cmd_10)

    def test_frame_qa_gate_with_synthetic_ffmpeg_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test_bars.png"
            m10 = Path(tmp) / "test_10bit.mp4"
            ff = fqg.resolve_ffmpeg()
            subprocess.run(
                [ff, "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:duration=0.1", "-frames:v", "1", str(p)],
                check=True,
                timeout=15,
            )
            rep = fqg.evaluate_media_paths([p], require_motion=False, ffmpeg_bin=ff)
            self.assertEqual(rep["status"], "PASS")
            self.assertGreater(rep["frames"][0]["mean_luma"], 10.0)

            subprocess.run(
                [ff, "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=24:duration=0.25", "-c:v", "libx265", "-pix_fmt", "yuv420p10le", str(m10)],
                check=True,
                timeout=20,
            )
            rep10 = fqg.evaluate_media_paths([m10], require_motion=True, ffmpeg_bin=ff)
            self.assertEqual(rep10["status"], "PASS")
            self.assertLess(rep10["frames"][0]["mean_luma"], 235.0)


if __name__ == "__main__":
    unittest.main()
