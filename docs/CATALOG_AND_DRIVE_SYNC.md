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
python3 scripts/dexsculpt_catalog.py import kaykit-adventurers/character/knight --clear-scene --location -1.1,0,0
python3 scripts/dexsculpt_catalog.py prune-remote-cache --dry-run
```

- **Local-first, on-demand verification**: Checks `verified_cache_dir` before touching the Drive archive; never bulk-downloads the full multi-gigabyte archive onto low-disk workstations.
- **Strict binary & duplicate disambiguation**: Validates 12-byte GLB 2.0 headers (`glTF`, version `2`, matching byte length) and exact SHA-256 checksums across all subdirectories to disambiguate colliding basenames (`quaternius-universal-base-characters-standard`).
- **Transient DriveFS stall protection**: Uses bounded subprocess reads with retries on transient File Provider hangs and optional `gdrive readonly download` fallback via `com.google.drivefs.item-id#S`.
- **Non-destructive Blender 5.2+ MCP import**: Clears only orphan scene datablocks when `--clear-scene` is passed (never `bpy.ops.wm.read_factory_settings()`), preserves rig authoring scales/rotations under `CatalogRoot_<tag>` Empty wrappers, and excludes Blender's `glTF_not_exported` / `pose.bones[].custom_shape` helper meshes (`Icosphere`) from scene geometry and bounding boxes.
- **Licensing & privacy boundaries**: Never commit private GLB assets, Drive IDs, or `~/.config/dex-video-code/*.json` files to public Git; treat packs with QAL v1.0 redistribution limits (`quaternius-ultimate-modular-men`, `quaternius-ultimate-modular-women`) as private local-use only.
