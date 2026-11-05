# Capability baseline

Snapshot: 2026-11-04 (America/Detroit). Live observations are bounded to the
selected DEX//REACH nodes and tool calls named below; repository documentation
is not live runtime proof. Refresh before using a route.

## Machines and runtime

| Capability | State | Evidence and limit |
|---|---|---|
| Big Mac DEX//REACH | `VERIFIED` | Online, macOS arm64, `aiAccess=on`; fresh scheduler observation had 2 substantive/heavy slots, zero active/queued work, healthy memory and CPU. Fresh fingerprint identified host `bigmac`, user `bigmac`. |
| MacBook DEX//REACH | `AVAILABLE_UNPROVEN` for execution | Online, `aiAccess=on`; memory warning and 3–5 observed uncoordinated heavy workloads. The bounded read-only coordinator doctor call was refused with `COORDINATOR_WAIT_TIMEOUT` (6/1 plus CPU saturation). Do not retry until scheduler state changes. |
| HyperFrames local controller on Big Mac | `VERIFIED` for its documented controller | Read-only `health` succeeded through DEX//REACH `start_process`; its existing sample had full decode and SHA verification. A current `hyperframes --version` call returned 0.8.159. The controller is restricted to local `runs/` projects, 30s maximum and `health`/`submit`/`status`. This is separate from the `director` CLI. |
| Dex Video Code `director` through DEX//REACH | `BLOCKED` on MacBook at snapshot | Exact `npm run --silent director -- doctor --json` call returned `COORDINATOR_WAIT_TIMEOUT: substantive slots exhausted (6/1, including 6 uncoordinated heavy workload(s)); CPU saturated (1m load >= logical CPUs)`. No successful `director doctor` handshake yet. |
| DexDiffusion / Image_Gen worker | `UNKNOWN` | Read-only operator status, backend health, capability gaps and model status all returned `UNTRUSTED_BACKEND_IDENTITY`. No generation or worker call is permitted on that evidence. |

## Relevant Westkitty routes

| Route | State | Evidence boundary |
|---|---|---|
| Motion design | `PARTIAL` for Pilot A | The new 20-second encode completed on HyperFrames 0.8.159 at 960×540/24fps, full decode and SHA verification passed; the output is available locally. Artistic acceptance is pending. |
| Remotion | `AVAILABLE_UNPROVEN` | [`DexDictate_MacOS/marketing/remotion`](https://github.com/westkitty/DexDictate_MacOS/tree/main/marketing/remotion) documents an isolated Remotion project. No live runner proof was performed; the Swift app is a separate owner. |
| Illustrated / 2.5D | `BLOCKED` pending authorized image source/runtime | DexDiffusion identity was untrusted. No supplied source art was present in the handoff workspace. Do not invent a generated-image route or use private references. |
| Specialist Blender / 3D | `AVAILABLE_UNPROVEN` for this coordinator | [`Code_Video`](https://github.com/westkitty/Code_Video) documents native Blender film/rig fixtures, with its operational evidence dated 2026-10-17. No new Blender job was needed or run. Rig proof remains conditional on an explicitly 3D brief. |
| Procedural VFX | `AVAILABLE_UNPROVEN` | [`3js-VFX-platform`](https://github.com/westkitty/3js-VFX-platform) documents deterministic Three.js systems; its operational state reports a prior implemented-but-unverified baseline. No offline video capture was proven. |
| Audio production | `UNAVAILABLE` for this pilot | [`BigMac_Voice_Tools`](https://github.com/westkitty/BigMac_Voice_Tools) documents a local split runtime, but no current backend identity or render was verified. Pilot A is intentionally silent. |
| ComfyUI / Comfort UI | `EXCLUDED` | Prohibited by the controlling contract; no probe, install, adapter or fallback. |

## Rights and resource boundary

Pilot A contains only original HTML, CSS and SVG authored in this repository.
It uses no private or canonical imagery, generated identity, acquired source
media, voice, music, captions, cloud service or incremental spend. It references
the already-installed local GSAP file from the existing HyperFrames runtime;
that dependency is not copied into the repository. The local HyperFrames
controller's runtime output remains in its owned `runs/` area and is not a Git
asset.

No other Westkitty repository or service was changed. This baseline does not
prove Pilot B, a general studio, or ChatGPT Project activation.
