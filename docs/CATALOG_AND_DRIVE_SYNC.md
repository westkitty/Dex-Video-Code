# Verified Google Drive Output Sync & DEX//SCULPT Catalog Bridge

This document describes two optional workstation helpers in `scripts/` that connect verified remote Blender rendering with local Google Drive for Desktop delivery and on-demand DEX//SCULPT GLB asset retrieval, without storing private paths, host aliases, credentials, Drive IDs, or model binaries in Git.

## 1. Workstation → Google Drive Output Sync (`scripts/sync_to_gdrive.py`)

`scripts/sync_to_gdrive.py` copies verified output runs (`.blend`, hero stills, `.mp4`, contact sheets, `manifest.json`, and `.transfer-receipt.json`) from the local workstation into a user-configured Google Drive for Desktop destination folder (`~/.config/dex-video-code/gdrive-sync.json`, mode `0600`, or `DEX_GDRIVE_SYNC_CONFIG` / `DEX_GDRIVE_SYNC_DEST`):

- Rejects symlinks and skips dotfiles (`.DS_Store`, `.gdrive-sync-receipt.json`) so local sync receipts stay outside Google Drive.
- Copies files directly via `shutil.copyfile` + `os.utime` (no temporary `.tmp` staging files or macOS quarantine xattrs inside File Provider folders) and verifies exact byte count + SHA-256 checksums.
- Confirms cloud upload completion via macOS File Provider (`fileproviderctl evaluate` -> `isUploaded = 1`, `isUploading = 0`, `hasUnresolvedConflicts = 0`, `isTrashed = 0`) and `com.google.drivefs.item-id#S`.

### Private Config Template (`~/.config/dex-video-code/gdrive-sync.json`, mode `0600`)

```json
{
  "schema_version": 1,
  "delivery_mode": "google_drive_desktop",
  "drive_parent_root": "<local-drive-root>/<parent-folder>",
  "folder_name": "Blender MCP Outputs",
  "destination_dir": "<local-drive-root>/<parent-folder>/Blender MCP Outputs",
  "destination_drive_item_id": null
}
```

### Usage

```sh
# Sync one verified run directory
python3 scripts/sync_to_gdrive.py --run-dir /path/to/outputs/my_run

# Sync all run directories under an outputs root
python3 scripts/sync_to_gdrive.py --all-outputs /path/to/outputs

# Opt-in automatic sync right after strict SCP verification in transfer_verified_file.py
python3 scripts/transfer_verified_file.py \
  --source-host <ssh-host-alias> \
  --source-user <transfer-account> \
  --source-root /approved/remote/export \
  --manifest-path /approved/remote/export/manifest.json \
  --destination-root /approved/local/output/my_run \
  --gdrive-sync-config ~/.config/dex-video-code/gdrive-sync.json
```

Omitting `--gdrive-sync-config` preserves `scripts/transfer_verified_file.py`'s existing local-only behavior with zero Drive side effects.

## 2. DEX//SCULPT + Google Drive Humanoid Catalog (`scripts/dexsculpt_catalog.py`)

`scripts/dexsculpt_catalog.py` provides searchable read-only access to the DEX//SCULPT humanoid metadata (`humanoidCatalog.json`, `humanoidSources.json`, `humanoidCompatibility.json`), verified local cache resolution, bounded on-demand retrieval from a mounted Google Drive archive, verified SCP staging onto a remote Blender host, and live non-destructive import over MCP stdio.

### Private Config Template (`~/.config/dex-video-code/catalog.json`, mode `0600`)

```json
{
  "schema_version": 1,
  "metadata_dir": "<dex-sculpt-repo>/src/data",
  "verified_cache_dir": "<local-verified-models-cache>",
  "gdrive_archive_dir": "<local-drive-root>/ThreeJS_Humanoid_Library/ARCHIVE",
  "remote_host": "<ssh-host-alias>",
  "remote_staging_dir": "<remote-staging-root>",
  "mcp_launcher": "<mcp-launcher-path>",
  "max_asset_bytes": 104857600,
  "max_remote_cache_mb": 512,
  "min_local_free_gib": 2.0,
  "min_remote_free_gib": 1.5,
  "drive_read_timeout_seconds": 60
}
```

### Usage & Invariants

```sh
python3 scripts/dexsculpt_catalog.py status --no-remote
python3 scripts/dexsculpt_catalog.py search --query knight --limit 10
python3 scripts/dexsculpt_catalog.py compatible kaykit-adventurers/character/knight --limit 10
python3 scripts/dexsculpt_catalog.py import kaykit-adventurers/character/knight --clear-scene --ground-on-z0 --location -1.1,0,0
python3 scripts/dexsculpt_catalog.py attach-prop kaykit-adventurers/accessory/sword_1handed --target-armature Rig_Medium --bone handslot.r
python3 scripts/dexsculpt_catalog.py bind-animation kaykit-adventurers/animation_pack/rig_medium_movementbasic --target-armature Rig_Medium --target-asset-id kaykit-adventurers/character/knight --clip Walking_A
python3 scripts/dexsculpt_catalog.py prune-remote-cache --dry-run
```

- **Local-first, on-demand verification**: Checks `verified_cache_dir` before touching the Drive archive; never bulk-downloads the full multi-gigabyte archive onto low-disk workstations. Remote host staging enforces a bounded LRU cache cap (`max_remote_cache_mb`, default `512` MB) that touches `atime`/`mtime` on cache hits and evicts oldest staged `.glb` files when exceeded.
- **Strict binary & duplicate disambiguation**: Validates 12-byte GLB 2.0 headers (`glTF`, version `2`, matching byte length) and exact SHA-256 checksums across all subdirectories to disambiguate colliding basenames (`quaternius-universal-base-characters-standard`).
- **Transient DriveFS stall protection**: Uses bounded subprocess reads with retries on transient File Provider hangs and optional `gdrive readonly download` fallback via Drive item metadata.
- **Non-destructive Blender 5.2+ MCP import & rigging**: Clears only orphan scene datablocks when `--clear-scene` is passed (never `bpy.ops.wm.read_factory_settings()`), passes native `disable_bone_shape=True` when supported plus `glTF_not_exported` / `pose.bones[].custom_shape` filtering so `Icosphere` bone-shape helpers never enter scene geometry or bounding boxes, supports `--ground-on-z0`, and preserves rig authoring scales/rotations under `CatalogRoot_<tag>` Empty wrappers.
- **Native glTF bone-socket attachment (`attach-prop`)**: Parents prop roots directly with `parent_type="BONE"`, cancels Blender's bone-tail parenting offset via `Matrix.Translation((0.0, -bone_len, 0.0))`, applies `Rx(-90°)` glTF Y-up-to-bone alignment by default (`--no-gltf-bone-align` disables), and reports exact world `socket_distance_m`.
- **Blender 5.2 Action Slots & deformation proof (`bind-animation`)**: Verifies `skeleton_family` compatibility (`--force-skeleton` overrides), imports donor actions cleanly without leaving orphan armatures/meshes, binds `action_slot` (`target_id_type == "OBJECT"`), and measures real `max_vertex_displacement` across evaluated depsgraph meshes (`evaluated_get(depsgraph).to_mesh()` + `to_mesh_clear()`).
- **Licensing & privacy boundaries**: Never commit private GLB assets, Drive IDs, or `~/.config/dex-video-code/*.json` files to public Git; treat packs with QAL v1.0 redistribution limits (`quaternius-ultimate-modular-men`, `quaternius-ultimate-modular-women`) as private local-use only.

## 3. Declarative Catalog Scene Director (`scripts/catalog_scene_director.py`)

`scripts/catalog_scene_director.py` orchestrates multi-character catalog scenes from versioned `catalog-scene.v1` JSON manifests (for example `examples/p7/catalog_knight_goblin_scene.json`):

1. Validates manifest bounds (maximum `48` frames for bounded MP4 renders, safe scene/run names) and stages character, prop, and compatible animation-pack GLBs to the remote staging cache.
2. Assembles characters, sockets, and slotted animations in Blender 5.2+ over MCP (or `--headless-only`), adds backdrop lighting tracking the scene center, and computes an exact FOV/AABB `Director_Camera` framing.
3. Enforces programmatic spatial & deformation QA (`evaluate_spatial_qa`) *before* rendering: floor grounding (`max_floor_error_m`), pairwise AABB separation (`overlap_pairs`), bone socket proximity (`max_socket_distance_m`), and minimum animated vertex displacement (`min_anim_displacement_m`).
4. Renders a `2x2` multi-view spatial QA contact sheet (`Hero`, `Front`, `Side`, `Top`), a `720p` `AgX` hero still, and an optional bounded H.264 MP4 (verified with `ffprobe` and full `ffmpeg -xerror -f null -` decode, with intermediate PNGs cleaned up).
5. Pulls verified artifacts back via `transfer_verified_file.py --multiplex --transfer-mode full` and optionally syncs them via `sync_to_gdrive.py`.

```sh
python3 scripts/catalog_scene_director.py \
  --manifest examples/p7/catalog_knight_goblin_scene.json \
  --catalog-config ~/.config/dex-video-code/catalog.json \
  --remote-out-root <approved-remote-runs-root> \
  --local-out-dir <approved-local-output-dir> \
  --gdrive-sync-config ~/.config/dex-video-code/gdrive-sync.json
```

## 4. Audio-Reactive Music Video Director (`scripts/audio_reactive_director.py`)

`scripts/audio_reactive_director.py` (with scene builder example `examples/p7/midnight_clockwork_swing_builder.py`) drives Blender 5.2+ concert stages and DEX//SCULPT `Rig_Medium` performers directly from music tracks:

1. Decodes any audio file via FFmpeg mono PCM (`22050 Hz`) and runs a pure-Python radix-2 FFT to extract per-frame normalized `rms`, `bass`/`mid`/`high` envelopes, spectral onset `flux`, 16 logarithmic equalizer bands (`b16`), and estimated BPM.
2. Stages catalog performers safely, transfers compact `scene_build_spec.json` data, and supports a `--storyboard-only` 9-shot `3x3` visual QQQ pre-flight gate before full rendering.
3. With `--render-full`, partitions long songs into `<= 48` frame chunks across two parallel warm background Blender 5.2+ workers, encodes each chunk immediately to H.264 segment MP4s while purging chunk PNGs to bound remote scratch disk usage, muxes stereo AAC audio with explicit `-map 0:v:0 -map 1:a:0` stream selection, runs `ffprobe` + full `ffmpeg -xerror -f null -` decode + `frame_qa_gate.py` luma/motion checks, and pulls verified outputs via multiplexed SCP + optional `sync_to_gdrive.py`.

```sh
# 1) Build scene & visually inspect 9-shot storyboard
python3 scripts/audio_reactive_director.py \
  --audio <local-audio-track> \
  --catalog-config ~/.config/dex-video-code/catalog.json \
  --remote-out-root <approved-remote-runs-root> \
  --local-out-dir <approved-local-output-dir> \
  --storyboard-only

# 2) Full parallel streaming render, audio mux, and Drive sync
python3 scripts/audio_reactive_director.py \
  --audio <local-audio-track> \
  --catalog-config ~/.config/dex-video-code/catalog.json \
  --remote-out-root <approved-remote-runs-root> \
  --local-out-dir <approved-local-output-dir> \
  --gdrive-sync-config ~/.config/dex-video-code/gdrive-sync.json \
  --render-full --skip-build
```
