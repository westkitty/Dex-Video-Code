# Temporal Precision v1 — bounded Director operation

This is an **additive experimental video-edit route**, not an expansion of the existing CreativeJob 1.1 `produce` adapter. The prior geometric renderer, source-job admission, Google Drive delivery, and Studio workflow are unchanged.

## Entry points

```sh
npm run build
npm run --silent director -- temporal resolve --contract runs/temporal/contract.json
npm run --silent director -- temporal apply --contract runs/temporal/contract.json
```

Resolve is read-only. Apply writes a new output MP4 only after checks. Source and destination must already lie within the project workspace; nested output parent directories must already exist. The source is never overwritten, and an existing output makes apply fail.

## Input contract

```json
{
  "schema_version": "temporal-precision.v1",
  "source": {
    "path": "runs/temporal/source.mp4",
    "sha256": "<lowercase actual SHA-256 of source bytes>",
    "rights": "authorized"
  },
  "alignment": {
    "source_sha256": "<same source SHA-256>",
    "method": "forced_alignment",
    "engine": "name of external aligner used",
    "evidence": "local receipt locator",
    "words": [
      { "text": "FLASH", "start_seconds": 2.2, "end_seconds": 2.51 }
    ]
  },
  "timing": {
    "fps_numerator": 24,
    "fps_denominator": 1,
    "duration_frames": 120
  },
  "edit": {
    "trigger": {
      "kind": "spoken_word_end",
      "literal": "FLASH",
      "occurrence": 1
    },
    "operation": "high_contrast_lighting",
    "allowed": ["luminance", "contrast"],
    "protected": ["audio", "geometry", "identity", "camera", "framing", "timing"],
    "transition_frames": 0
  },
  "output_path": "runs/temporal/edited.mp4",
  "captions": "off"
}
```

The supplied alignment words are **external claims**, not a built-in speech recognizer. The code checks source hash linkage, timing bounds, occurrence, ordering and required declarations; it **does not inspect an alignment evidence file or establish the words were really spoken**. Treat the declared alignment as unverified until human or independent audio alignment review. A forged timestamp may otherwise pass the contract resolver. This is not a finished fully automatic speech-trigger workflow.

## Narrow admission and validation

- Source must be MP4 with exactly one constant-frame-rate H.264 video stream and one AAC audio stream; 1–120 fps, up to 30 seconds, at most 1920×1080 and at most 256 MiB. No subtitles or extra streams. Audio and video must both start at zero. The adapter checks the actual video frame timestamps against the declared rational frame rate and refuses shifted, dropped or irregular frame timing.
- Edit begins at `ceil(word_end_seconds * fps)`, the first frame at or after the stated word end. There is no inferred timestamp fallback.
- Frame-indexed FFmpeg `eq` adjusts contrast and brightness after the boundary; it does not crop, scale, move the camera, synthesize characters, insert words, or manipulate audio.
- The output is a newly encoded H.264/AAC MP4 with source AAC stream copied. Before finalization, it must pass full decoding, matching frame count/frame rate/dimensions and every video frame timestamp, zero-based audio/video start, no added streams, decoded audio hash equality, and unchanged source file hash. Existing output paths are refused before rendering and remain protected by create-if-absent linking.
- Re-encoding can alter pixel values outside the lighting edit. **Exact pixel identity or unchanged camera/geometry/character content is not proven** merely by those checks. Visual approval remains separate.
- The alignment claim and actual visual condition must be independently reviewed before describing the job as artistically verified.
- Neither resolving nor applying performs network operations, cloud uploads, voice generation, external payments, or Drive delivery.

## Verified scope as of 2026-11-12

The isolated module and tests passed a local TypeScript build and 9/9 targeted tests. A synthetic five-second source MP4 produced a new output at declared frame 61; frame count/dimensions and decoded audio hash matched. This was a **synthetic aligned-word fixture**, not detected speech. Re-applying to an existing output was refused. No complete repository checkout was available in the isolated test environment, so **the full repository build/test suite is unverified**. Human visual review is pending.

Do not conflate these tests with production speech recognition, exact pixel preservation, source-identity guarantees, or artistic approval.

## Additional bounded regressions — 2026-11-13

An isolated Node 22 harness reproduced a concrete failure: a five-second video with its AAC audio starting about 0.48 seconds after the video was previously accepted, despite the temporal word evidence depending on synchronized audio/video origin. A new zero-start check now refuses this input. Frame-by-frame PTS checks, input resolution and byte-size limits, and early existing-output refusal were added to reduce wrong-time and excessive-work risks. The added synthetic-media regression suite passed **12/12**, comprising nine resolver tests and three actual FFmpeg-driven tests (on-frame edit, delayed audio rejection and stale source-hash rejection). With a five-second fixture, the first edited frame was 61; sampled decoded frames before the boundary showed minor re-encoding differences, while frame 61 showed a substantial contrast difference. **Exact pre-trigger pixel preservation remains unproven and is not promised.**

The isolated harness used test-only stand-ins for unchanged project path utilities; the full repository build and test suite were **not** run. There was no real word recognition or authenticated alignment receipt, no real-user video, and no human artistic approval. The PR must remain draft until the native suite and the production-evidence gates pass.
