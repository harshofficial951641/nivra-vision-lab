# NIVRA operating-condition acceptance ledger

Confirmed requirements, 21 October 2026. This ledger defines what needs evidence;
it is not a statement that the current model meets these conditions.

| Dimension | Required assessment | Current evidence / gap |
|---|---|---|
| Crowd size | Real scenes with 50-100 simultaneously visible people; record count and occlusion | Existing diagnostic clips do not cover this range |
| Person size | Record person height in source pixels and visibility of the interacting people | No validated minimum usable pixel height |
| Day/normal light | Physical-fight events and ordinary interactions | A few inspected development recordings only |
| Low-light colour | Genuine camera recordings; positives and long ordinary periods | ARID is a possible licensed everyday-action sensitivity source, not fight recall evidence |
| Near-IR / monochrome CCTV | Genuine night security-camera stream; record modality evidence | No verified eligible fight/nonfight benchmark yet; grayscale transforms cannot fill this cell |
| Thermal IR | Keep separately identified if used in research | LLVIP/InfAR do not establish near-IR CCTV performance |
| Native resolution | Actual 1920x1080 and 1280x720 sources, with dimensions recorded | Upscaling lower-resolution sources cannot satisfy this cell |
| Degraded input | Fixed 480p and compression variants of verified sources | Sensitivity tests; variants share source groups and cannot be independent samples |
| Coverage | Person detection/tracking, interaction regions, service interval, skipped/starved regions | A whole-frame classifier score cannot establish which interaction was assessed |
| Compute | End-to-end latency, effective analysis FPS, queue/drop counts, total GPU memory | Classifier-only timing is insufficient for 50-100-person capacity |
| Alert behaviour | Missed events, unmatched alerts and source-time delay; camera-hour false-alert rate where duration supports it | Existing few-second diagnostics cannot establish operational false-alert rates |
| Independence | Camera/session/actor groups and candidate training-corpus overlap | Existing diagnostics influenced development; VID remains training-only |

No new numeric accuracy, latency or false-alert acceptance target has been
invented. Record observations first; runtime and detection suitability must be
assessed together on the actual PC. Missing representative footage remains an
explicit validation gap, even if a software foundation is selected.

## Candidate decision sequence

1. Audit and pin runnable GitHub/model-author releases, code, checkpoint and data
   terms separately. Reject unavailable assets and unverifiable class mappings.
2. CPU smoke-test reviewed candidate loading and preprocessing in isolation.
3. Parent schedules bounded sequential GPU comparisons with the live demo
   protected. Use the same strict source-time diagnostic windows and each
   checkpoint's own preprocessing; freeze thresholds before scoring.
4. Separate classifier quality, pipeline engineering and operating-condition
   coverage. Select useful components only where the evidence supports them.
5. Build/train an offline candidate using permitted, reviewed training data.
   Preserve independent evaluation groups; no automatic live promotion.

Night/crowd source audit: [night-crowd-evidence.md](night-crowd-evidence.md).
Shared comparison rules: [PROTOCOL.md](PROTOCOL.md).
