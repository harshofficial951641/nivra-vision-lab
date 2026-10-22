# Bounded CCTV resolution/compression variants

Implementation: [prepare_cctv_variants.py](../../prepare_cctv_variants.py).
Tests: [test_prepare_cctv_variants.py](../../tests/test_prepare_cctv_variants.py).
Scope follows [PROTOCOL.md](PROTOCOL.md) and the resolution section of
[benchmark-readiness.md](benchmark-readiness.md), narrowed by the parent's latest
instruction to **downscaled landscape derivatives only**. No same-size re-encode,
upscale, synthetic night conversion, model invocation or live-service change.

## Current verification status

56 unit cases passed using `service/.venv/Scripts/python.exe`, from the `service`
working directory. Tests mock all FFmpeg execution. They cover bad/missing hashes,
unsafe paths, existing outputs, the initial size matrix, crop/source deduplication,
normalized crop retention, actual PTS versus wrong nominal FPS, rational gap
boundaries, every-frame pairing, process timeout/log bounds, storage/encoder
failures, quota cleanup and exclusive completion publication. Regressions also
cover bounded declared tails, negative/large mismatches, labels entering unknown
tails, every-frame backend offsets/drift, source/output runner identity and the
independent sequential OpenCV decoder's thread/hardware controls. SAR regressions
preserve unspecified metadata on original references, admit portrait skips,
explicitly skip unprovable landscape tiers, and reject negative/invalid SAR.

**Authorized full CPU matrix v2 completed:** four unique sources, eight H.264
outputs and fifteen manifest records. Every source/output passed independent
FFmpeg/OpenCV clock checks. No model, GPU or live-service operation was performed.
The earlier successful kick-only smoke remains historical evidence below.

The staged binary was independently SHA-256 checked as a file, then executed by
the authorized CPU runs. No binary is bundled or redistributed by this change.

The parent's v1 failure exposed a bad assumption in the old check: declared
container duration is not the first-to-last frame PTS span. The correction replaces
that assumption with explicit coverage and decoder-clock evidence, rather than
increasing a frame-count tolerance to pass this clip.

## Exact parent command

From `C:\Users\harsh.DESKTOP-VE90R6D\Downloads\Nivra\nivra-vision-lab`, in PowerShell:

```powershell
service/.venv/Scripts/python.exe service/prepare_cctv_variants.py `
  --manifest service/evaluation/corpus.json `
  --manifest-sha256 33d04d15bc4a6911face456fff7488320906505cc344f863042e4cae304bfb34 `
  --output-dir service/research/runs/cctv-quality-v2 `
  --ffmpeg service/research/venvs/videomae457/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe `
  --ffmpeg-sha256 2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3 `
  --timeout-seconds 120
```

This exact full-matrix command was executed under the parent's explicit CPU
authorization. Its directory now exists and must not be reused or overwritten.
A deliberate rerun requires a different new directory, for example
`cctv-quality-v3`. For a smaller parent smoke, use a different new
directory such as `cctv-quality-kick-smoke-v3` and append `--only-id kick`.
That selects only the existing short kick recording and its two derivatives;
it is not a full matrix. Repeated `--only-id` flags select explicit records,
including crop views if wanted. Unknown/duplicate IDs fail.

The manifest SHA above is the observed current corpus hash. If the manifest
changes, review the change and deliberately supply its new checksum; the CLI
does not silently accept changed input bytes. Original media SHA-256 values
come from that pinned manifest and are recomputed before any media operation.

Binary provenance supplied by the parent: `imageio-ffmpeg==0.6.0` wheel SHA-256
`02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a`, containing
the FFmpeg 7.1 Gyan GPLv3/libx264 build at the exact binary hash above. This helper
verified the binary hash, not the wheel archive. The CLI requires both an explicit
binary path and the approved binary hash, then checks version text and libx264
availability. A self-selected different binary/hash is not accepted.

## Initial matrix and lineage

| Original coded source | Unchanged reference | New outputs, each directly from original |
|---|---|---|
| Boxing: 1920×1080 landscape | Yes | 1280×720 and 854×480, each CRF23 and CRF35 |
| Kick: 1280×720 landscape | Yes | 854×480, CRF23 and CRF35 |
| Grappling: 880×608 landscape | Yes | 694×480, CRF23 and CRF35 |
| Squats: 720×1280 portrait | Yes | None; explicit portrait skip reason |
| Grappling crop view | Yes, same original bytes and same normalized crop | Reuses the same two encoded grappling files with the same normalized crop |

The CLI probes and verifies actual dimensions rather than trusting the size
table. The authorized v2 run confirmed this matrix for the unchanged five-row
input corpus: **8 encoded media files, 15 manifest records and 4 unique parent
inspections**, with no missing requested landscape tiers.
The cropped grappling recording contributes views, not an additional source.

Widths round to the nearest positive even integer. FFmpeg's scale filter retains
display aspect through sample-aspect ratio (SAR), including rounding at 854 or
694 pixels. The verifier checks decoded display aspect, not just coded aspect.
No stretch-to-square, padding, sharpening, denoising or frame interpolation is
introduced. Nonzero rotation metadata is rejected in this first implementation;
autorotation is disabled explicitly.

### Unspecified SAR is not square pixels

The parent's full v1 matrix failed only after eight encodes, at the squats
reference. Replaying its pinned FFmpeg source-decode command confirmed **65 frames,
720x1280 coded dimensions, time base 1/10240, PTS ticks 0..131072 (0..12.8 s),
with SAR 0/1 on every frame**. This is actual source metadata, not a guessed
square-pixel display aspect. FFmpeg 7.1's
[AVFrame definition](https://github.com/FFmpeg/FFmpeg/blob/n7.1/libavutil/frame.h#L465)
defines 0/1 as unknown/unspecified, and
[showinfo](https://github.com/FFmpeg/FFmpeg/blob/n7.1/libavfilter/vf_showinfo.c#L700)
prints that frame's numerator/denominator directly.

Zero SAR is therefore accepted by timestamp validation and represented explicitly
as `sampleAspectRatio="0/1"`, `sampleAspectRatioStatus="unknown-unspecified"`,
`displayAspectRatio=null` in the receipt. Original-reference rows retain the
explicit SAR/status in `qualityVariant`. It is never converted to 1:1. A negative
numerator or non-positive denominator is invalid, including a double-negative
ratio that ordinary fraction reduction would otherwise make positive.

Coded portrait references still follow the initial portrait-derivative skip and
receive independent OpenCV/FFmpeg clock checks. If a coded landscape parent has
unknown SAR, requested derivatives are explicitly skipped because display aspect
cannot be proved. The receipt retains requested/generated/skipped derivative
heights and the reason. Direct encoding and source/output aspect verification
also reject unspecified SAR. All-frame timestamp checks remain applicable to the
original independently of display aspect; known-SAR derivatives retain the same
strict aspect/PTS validation as before. Consumers must inspect skipped heights
before claiming every matrix tier exists.

Each unique source hash is inspected once and encoded once per size/CRF pair.
Every encode's `-i` is the original source, never a previously encoded derivative.
Duplicate source bytes with contradictory sourceGroup/split fail. SourceGroup,
historical split, attribution, events, duration and normalized crop coordinates
are retained. `qualityVariant` marks all output records as development-only and
not independent evidence. Historical `holdout` strings are preserved for validator
compatibility; they do not become unseen evaluation by passing this tool.

Original references keep their IDs/hashes and point back to unchanged original
files with paths relative to the new corpus. Derivative IDs append
`--h{height}-crf{23|35}`. The result is checked with existing `validate_manifest`.
No original corpus, media, scripts, model settings or source labels are rewritten.

## Clock contract

FFmpeg metadata probing uses stream copy with zero output frames before any
full decode. It rejects oversized/rotated sources first. The decoder then runs
`showinfo` and captures **every decoded integer presentation timestamp and its
rational time base**, with actual dimensions/SAR/pixel format and keyframe flags.
The nominal header FPS and `pts_time`'s rounded text are not used to construct a
timeline. Thus boxing's nominal 30000 FPS and kick's nominal 24000 FPS do not
determine source duration, sample timestamps or GOP.

The target GOP is `round(2 / median(consecutive decoded PTS differences))` frames.
For millisecond-rounded clocks this can be 61 rather than assuming 60. The receipt
records both the requested GOP and actual decoded keyframe times/intervals.
This is a two-second target, not a promise that every VFR GOP lasts exactly two
seconds. Scene-cut variation is disabled.

Encoding uses `-copyts`, `-fps_mode passthrough`, explicit encoder time base
`1/1000000` and MP4 video timescale `1000000`, with negative-timestamp avoidance
disabled. There is no `-r`, FPS filter, `setpts`, `start_at_zero`, interpolation or
frame-number/FPS clock reconstruction. MP4/B-frame muxing can still affect clocks:
the output is **fully decoded again** rather than assuming these flags worked.

Acceptance requires matching decoded frame counts and corresponding PTS within
**1 ms for every frame**, unchanged display aspect, expected coded size, decoded
H.264 and yuv420p. Missing/non-monotonic PTS, changing dimensions/SAR/pixel format,
gaps over 1200 ms, excessive source times or inadequate annotation coverage fail
closed. Frame counts and FFmpeg source/output PTS must still match within 1 ms
for every frame; the duration correction does not weaken that contract.

An **independent OpenCV sequential decode** is performed in a timeout-bounded
child Python process on the source and each output. It uses explicit FFmpeg
backend selection, no hardware acceleration, two decoder threads and
`cv2.setNumThreads(1)`. Every actual `CAP_PROP_POS_MSEC` is saved; nominal FPS is
never queried. Each file must prove `OpenCV_PTS[i] = FFmpeg_PTS[i] + constant`
within 1 ms across all frames, not merely match endpoints. The receipt records
the measured signed offset, exact rational offset and maximum residual. Backend
versions/build hash, dimensions and frame counts are retained.

The source and output OpenCV clocks must additionally match each other within
1 ms across every frame, so existing runner event coordinates remain unchanged.
A common verified -3 ms backend offset is acceptable; a new output-only 3 ms
rebase is rejected rather than silently moving events. A future FFmpeg-based
consumer must apply the recorded backend-to-runner mapping when comparing these
events; it must not assume the two backends have the same zero point.

Declared container duration is preserved as metadata, separately from observed
OpenCV first/last PTS and frame-span. A declared end before the last observed PTS
is rejected. A positive unobserved tail (or head) is permitted only up to **1200
ms**, the runner's maximum gap bound, and is explicitly recorded as unknown.
This is a bounded metadata discrepancy, not observed motion or normal footage.
Events must lie within the actual first/last observed PTS endpoints; they may not
extend into an unobserved tail. The CLI does not infer a last-frame duration,
pad frames, extend labels or shorten the original declared duration to make a
comparison pass. Comparisons/exposure denominators must use observed coverage,
not count the declared unknown tail as normal time. Each output row includes
`qualityVariant.observedCoverage` so consumers can enforce that distinction.

## Resource and filesystem limits

- Native Windows, CPU `libx264`, preset `medium`, CRF23/35, yuv420p. Encoder and
  decoder threads are capped at two; filter threads at one. No hardware
  acceleration or model/framework import is needed for encoding. The independent
  runner-clock worker uses the existing OpenCV installation, without Torch.
- Maximum 60 seconds and 2000 decoded frames per media; the decoder requests at
  most 2001 frames and rejects that overflow rather than treating a truncated
  prefix as a full recording. Frame clocks are checked as exact rational values.
- Coded landscape bounds 1920×1080; portrait bounds 1080×1920. Decoder
  `max_pixels=2073600` also caps pixel allocations. Supported forced local
  containers are MP4/MOV, WebM/MKV and AVI; protocol whitelist is file/pipe.
  Decode errors are fatal. No network stream or shell invocation is accepted.
- Per-process timeout defaults to 120 seconds, configurable only within 1–300
  seconds. Timeout kills and reaps only that CLI child. Combined diagnostic log
  capture is capped at 2 MB. Work is sequential, not parallel decoders/encoders.
- New artifacts are capped at 200,000,000 bytes, with an 8 MB metadata/mux reserve
  and a per-encode `-fs` allowance from the remaining budget. FFmpeg can overshoot
  `-fs` slightly; post-encode checks reject excess, and failure cleanup discards
  this run's largest partial media if needed to leave room for a failed receipt.
  It records those discarded files instead of claiming success.
- Output must be a fresh child of ignored `service/research/runs/`; symlink/output
  escape paths and pre-existing directories/files fail. Inputs must resolve
  inside the repository and match their supplied hashes. All subprocesses use
  argument lists, `shell=False`, `-nostdin` and `-n`.

The pin identifies the exact encoder build; it does not establish bit-identical
encoding across CPUs, runtime/library changes or future tool modifications.
Reuse the same generated file hashes for every model comparison.

## Receipt and publication rules

`receipt.started.json` is an exclusive incomplete marker. Encodes initially use
`*.partial.mp4`. Only after **all** selected outputs pass full pairing and all input
hashes are rechecked are verified files promoted and `corpus.json` published.
`receipt.complete.json` is a new exclusive completion marker, published last.
JSON publication uses an exclusive pending file plus an atomic no-clobber hard
link; Windows NTFS supports that operation. Unsupported filesystems fail closed.

Failures leave `receipt.failed.json`, with `status=failed`,
`eligibleForComparison=false` and no published corpus/complete receipt. If a
late storage error happens, the CLI removes only its own new corpus and demotes
its own promoted media back to partial names. Existing shared artifacts are never
deleted. Started and failed receipts are distinct files; no earlier receipt is
overwritten. Consumers must require the complete marker **and** its output corpus
SHA-256; an isolated media file or started receipt is not an eligible comparison.
If the filesystem cannot accept even failure metadata, the CLI raises and leaves
no complete marker; missing receipts must never be interpreted as success.

The complete receipt includes binary/version/hash; version/encoder-check commands;
every metadata/decode/encode argument list; log hashes; source/output SHA-256;
transform/hash; actual header/codec/dimensions/SAR/pixel format; all PTS ticks/time
bases; paired error bound; all independent OpenCV PTS, backend offsets and runner
identity checks; declared-versus-observed coverage; keyframe timing; libx264 version/profile log evidence;
byte count and an explicitly labelled container-bitrate estimate. Sensor,
illumination, visible-person count and occlusion remain unknown for this corpus.
These transforms do not produce genuine near-IR, thermal, night or crowd evidence.

Relevant option semantics were checked against the primary
[FFmpeg command documentation](https://ffmpeg.org/ffmpeg.html#Advanced-options)
and [codec options](https://ffmpeg.org/ffmpeg-codecs.html#Codec-Options).
Those references do not replace per-run real encode/decode validation.

## Authorized kick-only v2 measurements

Historical results: [complete receipt](../runs/cctv-quality-kick-smoke-v2/receipt.complete.json)
and [three-row corpus](../runs/cctv-quality-kick-smoke-v2/corpus.json), both ignored
local artifacts. These precede the newly authorized full matrix below.

- Source: 111 frames, FFmpeg 3..4591 ms; OpenCV 0..4588 ms. Measured median
  inter-frame delta 42 ms gives GOP **48 frames**, independent of nominal 24000 FPS.
- Declared duration 4675 ms; observed frame-span 4588 ms; **87 ms unobserved tail**
  `[4588,4675]` in existing OpenCV runner coordinates. Neither original event is
  in that tail, and no event/declared duration was changed.
- Both outputs: 111 frames, H.264/yuv420p, 854x480, SAR 1280/1281. Actual keyframe
  PTS are 3, 2005 and 4007 ms (2002 ms spacings).
- FFmpeg source/output pairing: **0 ms** maximum error for all 111 frames.
  Source and both outputs independently prove a **-3 ms** FFmpeg-to-OpenCV offset;
  maximum backend residual is at most `1e-12` ms (floating-point representation).
  Source/output OpenCV pairing also has at most `1e-12` ms error for every frame.
- CRF23: 484,726 bytes; SHA-256
  `afa96a990a5976725bbbb1d3f20c4fa7c9feb1fef535a5285b39b0bc7de7bb36`.
- CRF35: 124,748 bytes; SHA-256
  `b4041586915e53f4c9d975d2029de287b74fd7ba4fa1d529b75f0f74d4b70825`.
- Total new v2 artifacts: **663,330 bytes**, including receipts/corpus. No partial
  media or failed receipt was left in v2. Input media/corpus hashes were rechecked.
  Failed v1 receipt remains unchanged, SHA-256
  `450d7461ab9a478721dbf512692050568528d9b563fa52adf565e99740b2d83f`.

Exact command executed for the kick-only v2 was the full command above with output directory
`service/research/runs/cctv-quality-kick-smoke-v2` and `--only-id kick` appended.
That directory now exists and cannot be reused or overwritten. This smoke verifies
only the kick recording's codec/clock path, not boxing, grappling/crops, portrait
skips on real data or model quality. The subsequent full matrix verifies those
other codec/clock paths as recorded below; neither run measures model quality.

## Authorized full CPU matrix v2

Ready artifacts: [complete receipt](../runs/cctv-quality-v2/receipt.complete.json)
and [15-row corpus](../runs/cctv-quality-v2/corpus.json). They are ignored local
artifacts for the parent's model comparison, not independently sampled footage.

| Source | Decoded frames | Source SAR | Generated tiers at both CRF23/35 | Declared unobserved tail |
|---|---:|---|---|---:|
| Boxing | 304 | specified 1:1 | 1280x720, 854x480 | 3 ms |
| Grappling, shared with crop view | 289 | specified 1:1 | 694x480 | 40 ms |
| Kick | 111 | specified 1:1 | 854x480 | 87 ms |
| Squats | 65 | **0/1 unknown/unspecified** | original reference only; coded portrait skip | 200 ms |

All **eight requested landscape size/CRF cells exist**. No unspecified-SAR
landscape input occurred in this actual corpus, so no additional requested tier
was skipped. The unit test independently verifies that such a source would be
explicitly skipped rather than encoded using assumed square pixels. No portrait
derivative, same-size re-encode or upscale was requested/generated.

Actual GOP targets were 61 frames (boxing), 50 (grappling) and 48 (kick), derived
from median decoded PTS spacings. All eight outputs have **0 ms maximum FFmpeg
source/output PTS error**, equal decoded counts and verified display aspect/SAR.
Every file also passed the independent OpenCV decode: source/output OpenCV error
was at most **2e-12 ms** across all frames. Measured FFmpeg-to-OpenCV source offsets
were -3 ms for boxing/kick and 0 for grappling/squats, each verified across all
frames within the unchanged 1 ms tolerance. No event offset was guessed/applied.

All fifteen manifest rows passed existing `validate_manifest`; every referenced
media hash was recomputed. Original/derived event arrays, duration, normalized
crop, sourceGroup and historical split exactly match their corresponding source
record. Cropped grappling shares the same two derivative files with its uncropped
view. All unknown tails remain explicit, with no normal-label or exposure claim.
Squats' original reference preserves unknown SAR and null display aspect.

- New v2 artifact total: **6,867,172 bytes** (well below 200,000,000).
- Corpus SHA-256:
  `c274ce34b0395ce6c0f20d6dbfbd3bb6a98d58c56c1eba783a7e17066ab8b7cd`.
- Complete receipt SHA-256:
  `9a785759885eff3dbf13b7c79ae443eb4e94acee527565b72ce62ddc99b52d0e`.
- CLI implementation hash equals the receipt's pinned implementation hash.
  No partial media or failed receipt exists in full v2.
- Original corpus SHA remains
  `33d04d15bc4a6911face456fff7488320906505cc344f863042e4cae304bfb34`;
  all four original source hashes match it.
- Failed full v1 receipt remains unchanged, SHA-256
  `1361af0e5d3d891834c31135d3ef8823ee0fe57da23e2e625b7f4a493df671a0`.
  The earlier failed kick-only v1 receipt also retains its recorded hash above.

The parent may now use the pinned full-v2 corpus for the separately coordinated
model/GPU quality comparison. This task performed only media preparation and
validation; no model accuracy, crowd, IR/night or live-system claim follows.

## Re-run unit checks

From `service/`:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_prepare_cctv_variants.py -q
```

The first invocation from repository root lacked the service module import path;
using the service working directory matches existing test imports. No shared test
configuration was changed. Parent can inspect the full-v2 complete receipt,
all-frame PTS/SAR evidence and media hashes before its separate model comparison.
The helper ran only the explicitly authorized CPU media operations.
