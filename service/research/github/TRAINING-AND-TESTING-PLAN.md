# Expanded training and independent testing

Harsh requested substantially more training and rigorous helper-chat testing on
21 October 2026. This extends the existing GitHub-first comparison; it does not
authorize treating training fit as deployment accuracy or changing the live model
without verification. Current experimental foundation remains community X3D-M.

## Ordered work

1. Finish the conservative three-epoch community-head pilot already in progress,
   prove zero-update equivalence to its baseline, then run GPU training and paired
   development diagnostics. Preserve the baseline activation/pooling path.
2. Expand model-blind review of previously unreviewed, already imported VID
   recordings. Separate positive/normal reviewers; retain uncertain intervals.
   Never turn archive names or teacher predictions into ground truth.
3. Independently acquire new public footage with explicit source rights and saved
   attribution. Separate contact-action proxies, ordinary interactions, real
   low-light colour and sensor-verified near-IR. Keep unknown modality unknown.
4. Freeze source-group roles and annotation files before candidate scoring. Use
   development groups for model selection; reserve audit groups for one final
   selected comparison. Existing four-source diagnostics remain development-only.
5. Run bounded larger experiments after data validation. Initial candidate budget:
   conservative head adaptation at 3, 10 and 20 epochs, with settings/configs
   recorded before scoring. Do not blindly run every configuration if the pilot
   reveals a loader, annotation, gradient or transfer failure. Additional backbone
   adaptation requires its own fixed experiment and unchanged-BN checks.
6. Select using development performance and resource cost, then freeze the model,
   threshold and alert policy. Run the reserved audit once. If its results drive
   further tuning, it becomes development material and a fresh audit is required.

Only the parent schedules actual GPU jobs, sequentially, with explicit devices,
allocator caps and demo yielding. Helpers may review/download bounded permitted
media, prepare CPU evidence, implement tests or audit code within assigned paths.
No helper changes the live service, threshold or model. More epochs are a budget,
not evidence of improvement. Perfect training fit is insufficient for promotion.

## Grouping and blinding

Independent review found a legacy builder fallback that inferred full-duration
normal spans when accepted reviews omitted `events`. Parent removed that fallback:
all accepted records now require explicit intervals. The frozen old manifest is
not rewritten. Its completed pilot is legacy sampled-label research, not fully
observed normal evidence. A ninth helper is densely re-reviewing 40 existing normal
records with weaker coverage; these are not new sources or independent tests.
Larger fitting waits for the cleaned canonical review selection and manifest.

Independent quantification of the frozen old91 normal windows:60 arose from26
implicit legacy records,2 from explicit but sampled legacy intervals,12 from
dense-sampled expansion and17 from every-frame-reviewed intervals. The implicit
source intervals total186.5854709113521 seconds;60 overlapping four-second rows
are not240 independent reviewed seconds. Preserve this distinction in all reports.

Harsh is asleep and explicitly requested no questions. Make routine decisions
within the authorized local training/research scope, preserve evidence and surface
remaining gaps in reports; do not treat this as permission for purchases, accounts,
external messages or unrelated deployment/production changes.

VID remains a single unresolved actor/session cohort and training-only. A new
filename, scene tag, crop, codec variant or archive cannot establish independence.
Reviewers exclude every ID already present in prior review files, including
ambiguous/excluded decisions; those are not new clips. Recompute source hashes.

For new online footage, group conservatively by event/session and source author
where actor/session independence is unknown. Keep source URLs, author/upload
metadata and exact media hashes. Different uploads of the same event and all
derivatives stay together. Publisher-model training overlap remains unknown unless
independently established, so even new NIVRA recordings are not certified unseen
to every pretrained model.

The predeclared role rule for each new `sourceGroup` is the first byte of
SHA-256(UTF8(`nivra-online-wave1-v1:` + sourceGroup)): values <128 are development;
others are reserved audit. Assign roles before predictions. Do not change group
names, omit hard clips or reshuffle roles to improve a measured result. If a role
lacks sufficient eligible examples, report the gap and acquire new independent
groups without examining reserved predictions.

New evaluation reviewers must not open classifier scores, execute detectors or
choose clips based on model outputs. Labels remain provisional assistant review,
with evidence coverage, uncertainty and exact inspected intervals recorded. A
sport/staged contact action is a proxy for visible physical interaction, not proof
of hostile intent. No identity, crime, injury or guilt labels are introduced.

## Evidence and reporting

- Report event-compatible detections/misses and unmatched alerts with the exact
  matching policy. Do not credit a later kick as distinct recognition of an
  earlier takedown. Account for cooldown-suppressed episodes and duplicate alerts.
- Separate verified normal time from unknown intervals. False alerts per hour need
  the actual reviewed duration and event/episode definitions; a short clip with
  zero alerts does not establish a low operational rate.
- Report sample/source-group counts, class mix, selection bias and uncertainty.
  Overlapping windows and synthetic variants are dependent observations.
- Stratify by person pixel height, occlusion, visible crowd count, native dimensions,
  compression and sensor/illumination. Missing conditions remain unverified.
- Preserve real near-IR, thermal and low-light colour as separate modalities.
  Darkening/grayscale transformations are sensitivity tests, not true night data.
- Measure classifier cost separately from complete person/region scheduling and
  source-to-alert delay. A 100-observation cap is not 100-person recall or fight
  coverage. Include omissions, saturation, stale regions and dropped frames.

The completed 67-window comparison and its limitations remain in
[PAIRED-RESULTS.md](PAIRED-RESULTS.md). The full quality v2 corpus is available for
parent validation and scoring; it adds codec/resolution sensitivity, not new
independent recordings. No target accuracy percentage is asserted in advance.
