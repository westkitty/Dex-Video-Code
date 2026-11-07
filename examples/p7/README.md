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

## P7.1 precision gait repair

`foot_contact_qa.py` evaluates the deformed sole and toe mesh vertices, rig joints,
and IK targets on all 240 frames without rendering. Run it with Blender 5.2.3:

```sh
blender --background --python foot_contact_qa.py -- \
  --source /absolute/path/to/lantern_sentinel.py \
  --output-root /absolute/production/qa \
  --output-dir /absolute/production/qa/current-source
```

The check derives the floor surface from the evaluated floor mesh and classifies
planted, takeoff, swing, landing, and settled intervals from the authored target
tracks. It enforces 10 mm floor and planted-height tolerances, 20 mm planted XY
drift and ankle-target residual, 80 mm peak swing clearance, 150 mm maximum
frame-to-frame joint displacement, 2 mm chain-length and joint-continuity
tolerances, and a forward knee bend. `--expect-failure` verifies that a known-bad
baseline is rejected. This is authored IK animation, not a physical simulation.

## P7.3 bounded character performance

`performance.py` validates the data-only `p7.performance.v1` contract and applies
the allowlisted Sentinel action controls to the existing character builder in
`lantern_sentinel.py`. The contract rejects executable instructions, unknown
rigs/actions, external assets, unsafe contract paths and out-of-range timing.
`second_light.py` confines output below an explicit root, limits a run to 48
frames, refuses existing frame files and records frame timings/resource use.
Render in separate new output directories for each frame batch:

```sh
blender --background --python second_light.py -- \
  --output-root /absolute/production/run \
  --output-dir /absolute/production/run/frames-001 \
  --performance /path/to/approved/second-light.performance.json \
  --quality interaction --start-frame 1 --end-frame 48
```

The current implementation supports one authored story/action set: THE SECOND
LIGHT. It reuses the Sentinel rig, IK, foot-lock and scene builder, but its
prop/action choreography is still authored specifically for this film. It is
not a general multi-character or arbitrary-scene system. `foot_contact_qa.py`
accepts `--performance-contract` to test the full gait, arm reach, finger/grip
distance, switch rotation and contact-before-light ordering without rendering.
The director does not dispatch to the Big Mac specialist runner; 3D remains
blocked for Director jobs until a typed authorized bridge and receipt
reconciliation are implemented and verified end to end.
