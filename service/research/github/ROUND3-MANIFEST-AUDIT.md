# Independent round-three manifest admission audit

21 October 2026. **No blocking assembly, provenance, schema, source-hash, cohort or window-coverage finding was found in this bounded audit.** The exact pinned manifest below is structurally admissible for the proposed offline provisional-label training experiment. This is not label approval by a human, a new independent dataset, or evidence of detection quality. Parent alone authorizes/schedules fitting; no fit or model execution was performed here.

Only this assigned report was written for the admission task. Existing manifests, reviews, evidence, assembly script and media were read without changes. No download, package installation, service change, GPU work or model constructor was used.

## Verified result

| Partition of selected training material | Recordings | Four-second windows |
| --- | ---: | ---: |
| Old positives not selected for the twelve-source coverage audit | 27 | 45 |
| Supported old positives, using proposed audit events only | 7 | 9 |
| New round-three positives | 21 | 37 |
| Re-reviewed legacy normals | 40 | 40 |
| Prior dense normals | 17 | 17 |
| New round-three normals | 15 | 15 |
| Total | **127** | **163** |

There are **55 positive recordings / 91 positive windows** and **72 normal recordings / 72 normal windows**. All 127 IDs and actual media SHA-256 values are distinct. All records belong to source `vid-v2`, split `train`, group `vid-v2-unresolved-session-cohort`. Calibration and holdout both have zero windows; no online development/audit footage is included.

Every normal annotation and generated normal window is exactly `[0,4]` seconds, label 0. The total explicit normal duration is **288 seconds**, without overlap within those sources. **224.01899493415962 seconds** of declared source tails after those intervals remain unannotated. None was inferred normal by this manifest. Positive intervals total 237.6307394920207 seconds before considering window context; 91 overlapping/dependent four-second rows are not 364 independently annotated positive seconds.

## Quarantine and positive overrides

All five disagreement IDs are absent from canonical recordings, selections, manifest recordings and generated windows, rather than retained under another class:

`v_c_b_117`, `v_c_b_21`, `v_c_b_48`, `v_c_b_58`, `v_c_b_71`.

The seven supported IDs are:

`v_c_b_172`, `v_c_b_174`, `v_c_b_183`, `v_c_b_190`, `v_c_b_72`, `v_c_b_78`, `v_c_b_9`.

For every one, canonical events equal the coverage audit's `proposedEvents` exactly. Original positive events are replaced, not unioned or extended. Its source SHA matches the frozen old manifest, original selected-review fields are retained, and audit evidence is added before path normalization. The canonical `eventsOverriddenByAudit` flags and receipt's override set agree exactly. The audit record includes explicitly acknowledged limitations, including threshold sensitivity for `v_c_b_183`; this assembly does not adjudicate away that uncertainty.

All 27 unaudited old positive sources retain original selected-review events. Their 45 eligible windows remain provisional sampled-review material. They have not acquired dense coverage merely by inclusion in a canonical file. The canonical limitations state this directly. Retained source notes are historical descriptions; the actual training intervals are the canonical event objects, particularly for overridden sources.

## Provenance and pointer checks

The ten canonical `inputHashes` all match actual source-file bytes. All 127 selections have unique IDs and resolve their `/recordings/N` pointer to the same recording ID in the pinned source review. Each canonical row was independently reconstructed from its pointed row, with only the declared audit override/evidence union and documented evidence-path normalization allowed. Every resulting row matched exactly; this was not limited to checking ID membership.

Selected-source counts and resulting windows were independently recomputed:

| Selected review file, relative to training | Selected recordings | Windows |
| --- | ---: | ---: |
| positive-review.json | 4 | 6 |
| reviews/positive-round2-a.json | 11 | 19 |
| reviews/positive-round2-b.json | 3 | 3 |
| reviews/positive-round2-c.json | 16 | 26 |
| reviews/normal-legacy-rereview-v1.json | 40 | 40 |
| reviews/negative-round2-existing.json | 17 | 17 |
| reviews/negative-round3-a.json | 15 | 15 |
| reviews/positive-round3-a.json | 21 | 37 |

All 57 old normal IDs are represented by the 40 legacy re-review rows plus 17 dense rows. Fifteen new normals and 21 new positives do not overlap old manifest IDs. No accepted row came from a source review's ambiguous/exclude decision. The twelve-source positive audit itself is an input providing overrides/quarantine, not an independent accepted-review pool.

Inventory IDs were checked unique. Every present canonical media SHA/path/archive/duration field agrees with the inventory row; manifest values were compared to rebuilt output and actual media. Evidence paths resolve to existing files confined within `service/training`, including the special older `positive-round2-b` evidence base and repository-relative legacy paths. Normalization did not silently drop an evidence reference.

There are **517 distinct canonical evidence files: 408 JPEG and 109 JSON**. All were read and SHA-256 hashed sequentially, without executing their contents. An aggregate receipt over the mapping `{training-relative-posix-path: sha256}` is:

`c34b4e5e3b9d40ef288cb7c48e2405cbaf53b419980ad2a3fe72497695561e6a`

Reproduce by sorting mapping keys, serializing with Python `json.dumps(mapping, sort_keys=True, separators=(',', ':')).encode()` and hashing those bytes. This aggregate is an observation of current local evidence; the canonical review itself pins input review JSON but does not individually hash all image evidence. Preserve the files or their individual content map alongside the run. File existence/hashes establish evidence identity and availability, not that a visual judgment is correct.

## Window and source checks actually executed

The assembly source was inspected but **not executed**: its `main` publishes outputs, so rerunning it was inappropriate. Its pure imported `build` function was called on the current inventory plus canonical review in memory, and the resulting dictionary equaled the frozen manifest exactly. No output was published or overwritten.

`load_manifest(..., verify_files=True)` validated the real media paths and all **127 actual source hashes**, bounded schema/event ranges, explicit annotations and contradictions. `generate_windows` recomputed 163 train windows and the receipt's complete per-record window-count mapping. The receipt's script, inventory, canonical and manifest hashes also matched.

A separate interval-union calculation independently generated starts at four-second strides plus a final end-aligned start, merged same-label annotation coverage, required at least two positive seconds or four normal seconds, and omitted unknown/short windows. Every tuple `(recording ID, start, end, label)` matched the production generator, in order: **163/163**. This check used independent coverage arithmetic instead of calling production `window_label` for expected labels. All rows/events are inside declared source duration; there are no contradictory overlaps, no accepted events missing, and no negative end-aligned tail windows.

The decoder was not used to estimate labels or search for new examples. A narrow additional boundary check addressed the 17 prior dense normals' original FPS-derived source timing: one OpenCV decoder at a time, `cv2.setNumThreads(1)`, decode from frame zero through the first actual `CAP_PROP_POS_MSEC >= 4000`, finite strictly increasing PTS, bounded to at most 150 frames per source. All **2,054** resulting frames fit the originally reviewed frame counts exactly. No additional unreviewed boundary frame was required. All seventeen sources reach or bracket 4.0 seconds under their actual PTS: four have last PTS 4.02027027027027, one 4.031989336887705, and twelve exactly 4.0. The original review still used nominal frame-index/FPS annotations; this read-only numerical cross-check confirms the selected frame coverage for these actual bytes, without rewriting its method or claiming another visual review.

For the 40 legacy re-review records, recorded actual-PTS lists are finite, strictly increasing, begin at zero, reach at least four seconds, agree with frame counts, and declare every decoded frame included. For the 15 new normal records, referenced interval coverage JSON independently has matching finite/increasing PTS, first/last bounds and frame counts, with explicit every-frame inspection flags. These are receipt consistency checks; this audit did not reopen every contact sheet or independently replay those 55 videos.

For 21 new positive records, all **37 generated windows** match the review's `eligibleWindowCoverage` entries and declared >=50% positive coverage, existing evidence index, valid inclusive frame-index ranges and every-frame-inspected declarations. Referenced full PTS lists are finite/increasing, and positive annotation ends are within final observed PTS. Seventeen end-aligned windows extend slightly beyond final decoded PTS, at most **0.03639010189228564 seconds**; those tiny EOF margins are not positive or normal annotations. This preserves the stated distinction between four-second window context and observed positive coverage.

These checks are CPU/data admission checks, not a rerun of the whole project test suite. The independently rechecked frozen V2 trainer separately passed **109 guarded CPU tests** (71 V2 + 38 V1) in 38.18 seconds; see `INDEPENDENT-V2-AUDIT.md`. It has no unresolved implementation finding from that bounded review, after the runtime-provenance P2 fix. Parent/helper whole-suite counts are separate receipts and were not represented as this audit's execution.

## Pins

Paths below are relative to service. SHA values describe current working-file bytes, not a Git commit or signed attestation.

| File | SHA-256 |
| --- | --- |
| research/build_round3_clean.py | `fd18251fe0015d53105249f85f99a97ac0416ffd17ed271224f30ac79df1d643` |
| training/reviews/canonical-round3-v1.json | `52dff3653829d64433795a7f4b9b0e58b5600957102f92ea5def8b35c7652a63` |
| training/vid-round3-clean-v1.json | `68cf0c4048dcc9d4d10e5553bf5bcf9be6cd6ab36bd7aeaff23208f2b55e0970` |
| research/runs/round3-clean-admission-v1.json | `354a6b1d54fee6bd75157a7be36d43865db43b906f25b0d860a625eb7d2433d0` |
| training/data/vid/inventory-round2.json | `ec47cef0eaa8b1d022fbd6bd7dbba276f85072c6d5ee6fd142f6291716e4d3e5` |
| build_training_manifest.py | `a95afe1c191942fac23fe55b0f1d3bce965943c0824dde5dfe13308355604365` |
| nivra/training_data.py | `a2df7795345838f7c890e0f2bbd4335f66e21b10981acb055bfa647bef940239` |
| nivra/community_x3d_experiments.py | `d593b45b3e5985d7c15c24311c9c3646d908b4bdaf6c84a31fcd49486638fdc4` |
| tests/test_community_x3d_experiments.py | `0181b08ec3284754ea114019f2b0345839f27659f1d5c48544d6a2b5ca76be7d` |

Canonical input hashes, all independently verified:

| File relative to training | SHA-256 |
| --- | --- |
| positive-review.json | `9cfd13947a0449c527de29e6bc04f6c4a1d0cc31245be9eba6476ac7834c4640` |
| reviews/negative-round2-existing.json | `8766e4ef4816dd0f941fcd86a53c3a706fe7326be113880b9129ff49a62b48c5` |
| reviews/negative-round3-a.json | `1b03a33620201b2b33f9562f5eece412c2bddba6fc2f94ac202a25037df71b0e` |
| reviews/normal-legacy-rereview-v1.json | `c5a3f36cdfd2403d98485cf39f352e41915db02ee76e9b7cc121c64a7d52334d` |
| reviews/positive-coverage-audit-v1.json | `feeac4977b68c6d9a04ac4d0e28c3ee63f534ca319d966be72d4d69d62a23d98` |
| reviews/positive-round2-a.json | `0eccf1faf3fe74f4b34a4372135f673ef0ed1be7e7fbaf0a43a9b3acd5efeddb` |
| reviews/positive-round2-b.json | `5f2972ad8855e712a0ac0fbf5378b1b37a521344d920af9b546d5444a764c5c6` |
| reviews/positive-round2-c.json | `42ef7f42dced4871d77ecfcb33b52d3c7324624fc93a73fcb9c7bbb4e2bbbc1e` |
| reviews/positive-round3-a.json | `5d32fea40519697ff7ee2868fd2c4b606bf5c0ab60f25602c665736a9cf83e09` |
| vid-round2-v1.json | `1a0f6fc44704b73f32c5e0ab82b607fff2a702a848186b4403ddf357a0026a84` |

## Uncertainties and admission boundary

This is a structural/provenance admission with explicit provisional-label uncertainty. It does not independently validate every visible interaction, source duration metadata, face masking, every visual-inspection claim, full-motion mechanics, participant consent or source-author/session identity. The inherited 27 sampled old positives are the principal remaining coverage distinction. Positive labels with a minimum half-window annotation also contain contextual unknown time; unknown context is not a normal annotation.

Every-frame contact-sheet review remains still-image review by assistants, not continuous playback or independent human ground truth. Threshold-sensitive/occluded contact stays uncertain. No classifier predictions were read, no labels were changed, and no success percentage is inferred from fitting eligibility. The earlier five disagreements remain quarantined without selecting a convenient class.

VID CC0 copyright evidence is separate from author-reported consent and unresolved checkpoint terms. All material remains research-only under the existing project restrictions. One unresolved training cohort, overlapping windows and repeated backgrounds cannot establish unseen transfer, false-alert rate, crowd performance or night/IR capability. No independent online audit role or new holdout was created by this assembly.

For a parent run, use the exact manifest SHA above and preserve canonical selection, all ten source reviews/manifests, assembly/builder/data-loader source and evidence content identities as additional provenance. A trainer's manifest checksum prevents byte drift; it does not replace this admission review. Actual baseline parity, CUDA behavior, real gradients, CPU reload parity and development-only diagnostic comparison remain parent empirical work. The reserved audit must remain sealed until model, threshold and alert policy are fixed.
