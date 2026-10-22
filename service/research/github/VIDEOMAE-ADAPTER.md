# Offline cliffer1 adapter handoff

`nivra.videomae_candidate.VideoMAECandidate(snapshot, *, device='cpu')` supports
only `cliffer1/videomae-base-finetuned-kinetics-violence-nonviolence-tuned` revision
`613844b1d2d27f68944619bf91885a9befb101ac`. No live adapter is registered or changed.

The constructor hashes all four audited required files (README, config,
preprocessor config and safetensors) before importing Transformers. The hash
allowlist is embedded in the new adapter. Additional staging metadata is ignored;
required files must be regular local files, not symlinks. It requires exactly
Transformers 4.57.1, verifies saved and loaded class/config/processor contracts,
and rejects any nonempty loading diagnostic. Loading is local-only, with no
remote custom code, safe-format weights only, `weights_only=True` and eager
attention. Mean pooling remains enabled. Labels are 0 NonViolence, 1 Violence.

Parent staged the snapshot under
`service/research/cache/cliffer1-videomae/613844b1d2d27f68944619bf91885a9befb101ac`
and supplies its own isolated environment. This task did not rerun the parent's
real CPU smoke test or install dependencies. There is no CPU/CUDA auto-selection
or fallback; only literal `cpu` and `cuda` are accepted. CPU construction does
not probe CUDA. No GPU memory policy or live-service coordination is introduced.

`predict(BGR_frames)` accepts a list/sequence or an N,H,W,C numpy array of at least
eight observed frames, each nonempty uint8 BGR HWC with identical dimensions.
All frames are validated, including those not selected for inference. Select
`floor(linspace(0, N-1, 16))`; indices repeat for 8–15 observed frames, as explicitly
allowed by the existing sampling policy. Convert selected frames to contiguous
RGB arrays without resizing, then use the saved processor: PIL bilinear short
edge 224, centre crop 224 square, scale 1/255 and ImageNet mean/std. Inputs are
not modified. The processor tensor must be finite float32 `(1,16,3,224,224)`.

Two finite logits are required; one softmax produces:

```python
{
    'fightScore': float,                    # classScores[1]
    'classScores': [nonviolence, violence],  # Python floats
    'scoreKind': 'softmax-on-logits',
    'fightIndex': 1,
}
```

The adapter supplies no threshold, cooldown, event aggregation, duration check,
decoder, tracking, localization or detection-quality claim. Caller must verify
source timestamps and continuity; eight frames or repeated sample indices do
not prove four seconds of observation. `metadata()` returns fresh nested copies
of source revision, hashes, preprocessing, class order and provenance limitations.

Training dataset is unknown per the author card, checkpoint card carries
CC-BY-NC-4.0, and training code/split lineage is unverified. Existing diagnostics
are development-only; 50–100-person scenes, genuine near-IR, low-light colour,
native resolutions and degraded-camera robustness remain unverified. See
[transformer audit](transformer-repos.md), [protocol](PROTOCOL.md) and
[operating conditions](OPERATING-CONDITIONS.md).

## Verification

Run from `service` using the existing Python environment:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.venv/Scripts/python.exe -m pytest tests/test_videomae_candidate.py -q -p no:cacheprovider
```

Tests replace Transformers with stubs and use tiny synthetic source images and
tensor views. They never deserialize checkpoint bytes, perform real inference,
download assets or touch CUDA. They verify required-file hashing before loading,
lazy dependencies, exact versions and safe-loading arguments, device behavior,
saved/loaded contracts, RGB selection and dimensions, immutable metadata copies,
bad inputs, and nonfinite/wrong outputs. The symlink rejection test may skip on
Windows without symlink privileges. Actual library/model integration and GPU
comparison remain parent-owned.
