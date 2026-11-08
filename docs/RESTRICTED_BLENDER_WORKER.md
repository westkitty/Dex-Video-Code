# Restricted Blender Worker — P7.4 (integration pending)

This is the source for the limited, non-root, no-service Blender worker. It has been smoke-tested locally on Big Mac, **not** connected to a dedicated SSH credential or admitted as a Director production route.

## Approved operations

The fixed command accepts one bounded JSON request on standard input: `health`, `submit-approved-job`, `status` or `read-receipt`. Only the pinned original Second Light performance, approved contract SHA-256, 1–48 frame interaction/preview batches and pinned local Blender sources are accepted. The worker never interprets creative text as commands. All job outputs remain under its private per-user root. Repeated job IDs are idempotent only when their bound contract and frame range match. It does not expose a network listener.

The installed worker launches the actual Blender **app-bundle binary**, not a symlink to it: calling the symlink directly failed to locate Blender's bundled Python runtime in the first test. The next one-frame job succeeded and was encoded, fully decoded and hashed.

## Security / deployment gate

The worker code alone does not grant access. A new dedicated Ed25519 key must be generated **on the MacBook** and registered as a unique, tagged forced-command `authorized_keys` entry for the worker's existing non-root user. Apply OpenSSH `restrict` and the fixed command. Disable TTY, agent/X11 forwarding and port forwarding, keep all existing keys and SSH configuration intact, preserve StrictHostKeyChecking, and validate that requesting a shell is rejected. Do not reuse an unrestricted SSH key for this route, store private keys in Git or open a public port.

A Director client must use **only** that dedicated key through its own private SSH configuration, validate the exact worker response and artifact hash, reconcile retries and verify the downloaded output independently. Existing SCP delivery remains a separate tested route. Do not mark native 3D production READY before a fresh Director-originated end-to-end run passes.

## Current proof (Big Mac direct invocation only)

- Seven nonrendering regression tests passed and eight additional contract/receipt checks passed.
- One original 320x180, 24 fps H.264 frame was rendered and decoded successfully. SHA-256: `721830a5515c73c98d6527aed6e4bdc3999ecc5a7b3bf9daf69e1d1aead70b94` (3,805 bytes).
- Worker script SHA-256: `5d4c52fe75c1bd55c7d96c6de1eca363464e2d080ca0e90ec073df9acb041e72`.
- MacBook process admission was denied under saturated CPU/memory; no new key or authorized_keys change was made.

## Rollback

If the dedicated entry is eventually installed, revoke it by removing only its exact tagged line from the worker user's `authorized_keys`, confirming the original lines are unchanged, and disabling the dedicated client configuration. Do not remove unrelated keys or modify sshd-wide policy. Preserve existing output evidence and rollback receipts.
