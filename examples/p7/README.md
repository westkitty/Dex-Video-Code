# Lantern Sentinel P7 production source

`lantern_sentinel.py` builds an original, editable Blender scene from procedural
geometry. It retains the compact armored Sentinel, rounded helmet, cyan eyes,
brass trim, and amber chest lantern from the verified P7 proof. Authored head,
torso, arm, leg, finger, and foot tracks use a Blender armature. Foot and hand
targets use inverse-kinematics constraints. Animation is authored, not simulated.

The scene is a single 240-frame, 24 fps shot: quiet sentinel hold, attention turn,
two planted steps, reach/contact with the mechanism, then a caused light response
and final hold. No third-party assets, text, subtitles, or audio are used.

Run with Blender background mode and arguments after `--`:

```sh
blender --background --python lantern_sentinel.py -- \
  --output-root /absolute/production/run \
  --output-dir /absolute/production/run/interaction \
  --quality interaction --start-frame 145 --end-frame 192 --save-blend
```

Each output directory must be new and below `--output-root`; each invocation is
limited to 48 frames and refuses to overwrite frames or a saved `.blend`.
Quality settings are `interaction` (320×180), `preview` (640×360), and `master`
(1280×720). The complete 10-second preview used `interaction` quality; the full
master used `master`. Rendered media and the saved `.blend` belong in production
storage and must not be added to Git. Inspect encoded output and verify its full
decode before any master run.
