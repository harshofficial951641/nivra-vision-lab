# Clean round3 training admission

Parent assembly on 21 October 2026. No V2 fitting or model promotion is recorded by this document.

The frozen manifest [vid-round3-clean-v1.json](vid-round3-clean-v1.json) contains 127 recordings and 163 eligible four-second training windows: 91 positive and 72 normal. All sources remain the single unresolved VID actor/session training cohort; calibration and holdout counts are zero. Window rows can overlap and are not independent observations.

Manifest SHA256: `68cf0c4048dcc9d4d10e5553bf5bcf9be6cd6ab36bd7aeaff23208f2b55e0970`.

Canonical selection [canonical-round3-v1.json](reviews/canonical-round3-v1.json) SHA256: `52dff3653829d64433795a7f4b9b0e58b5600957102f92ea5def8b35c7652a63`. It records original review hashes, selected JSON pointers, normalized evidence paths and audit overrides. The original reviews and old manifest remain unchanged. The reproducible assembly is [build_round3_clean.py](../research/build_round3_clean.py); existing outputs cannot be overwritten.

## Selection changes

- Quarantine entire recordings `v_c_b_117`, `v_c_b_21`, `v_c_b_48`, `v_c_b_58`, `v_c_b_71`. The audit found props in two sources and insufficient confidently supported target coverage in three.
- Retain seven audited old positive sources using only the audit's proposed events. Original intervals outside the audit are not carried forward. The narrow `v_c_b_183` interval remains boundary-sensitive.
- Retain 27 unaudited old positive sources with their original explicit provisional intervals. Their sampled-review uncertainty remains unresolved.
- Replace 40 legacy normal sources with explicit 0–4 second dense re-review intervals. Retain 17 prior dense normal sources and add 15 round3 normal sources, each annotated only for 0–4 seconds.
- Add 21 round3 positive sources with explicit accepted intervals. Do not add any online development/reserved-audit footage to training.

## Parent checks actually completed

Recomputed all 127 selected media hashes through the production manifest loader. Verified all source-review hashes, selected IDs/JSON pointers and referenced normalized evidence paths; checked exact equality of the seven audit overrides and absence of all five quarantined sources. Every normal event is explicitly 0–4 seconds with label zero. Positive windows use the existing minimum-half-coverage rule; unannotated context is not a normal label. No nontraining split or outside source cohort is present.

The ignored receipt `service/research/runs/round3-clean-admission-v1.json` preserves counts by recording and assembly/input identities. Independent admission review was requested separately; this document is parent verification, not that review's result.

All labels remain provisional assistant judgments from static source images, not independent human ground truth, full-motion interpretation, or participant-release verification. More training footage and lower training loss do not establish detection accuracy. Real near-IR, low-light colour and 50–100-person fight detection remain unverified. Preserve the live X3D model while offline candidates are tested.
