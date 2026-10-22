# Independent bounded audit of online diagnostic scoring

21 October 2026. **No material implementation finding was found within this bounded review.** The pinned JSON-only postprocessor implements the declared actual-span eligibility, episode credit, role admission and raw-window integrity rules. It is suitable for the parent's predeclared diagnostic workflow after external corpus/model admission; it does not supply missing development normal evidence or establish model quality.

Only this assigned report was written. No implementation/tests/contract changes, media reads, decoder, model import/construction, inference, fitting, CUDA work or actual prediction report access occurred. Reserved-role behavior was exercised only with synthetic fixtures. The benchmark was read as source text to inspect its schema, never imported or executed.

## Scope and pins

| File relative to service | SHA-256 |
| --- | --- |
| summarize_online_diagnostics.py | `6cead54bf4595a88819ac1cd151ae88276adbd5d4de3952783cc37b5a5b2fb58` |
| tests/test_summarize_online_diagnostics.py | `d130495ca245e625fef51e2f3aadbe39b9217eaf40f80a8a68084f1adfe339fe` |
| research/github/ONLINE-SCORING-CONTRACT.md | `439470be19ed86b0bd590bd998e36f0028f0b2f4f2a8724b3d5db67ccdedc7c8` |
| benchmark_cctv_candidates.py, schema source only | `35f95c8134ead0c496b344f221cef3cc524467d002bf5c81217cb1fbd2859ad4` |

These are working-file byte hashes, not Git revision or signed authenticity claims. All four were identical before and after independent pytest execution. The ordered paired policy SHA is `c974d6f61ab429335cd6a1d917687c6671370a6a0c0edc54633e5a869cd74ac4`.

Procedure: read the scoring contract; inspect all postprocessor functions and synthetic tests; compare raw schema/identity/score/temporal semantics with benchmark source; independently execute the focused test file under blocked model/decoder/runner imports; exercise additional independent synthetic boundary/oracle cases; verify final pins and write this report. No actual online corpus or raw scoring file was needed.

## Eligibility and annotation semantics

| Requirement | Code evidence and assessment |
| --- | --- |
| Explicit intervals only | `summarize_online_diagnostics.py:103–114` requires an events list, integer target labels exactly 0/1, finite bounds within positive declared duration, and boolean `startsInProgress` when present. Empty events remain unknown. No full-duration normal fallback. |
| Union instead of duplicate coverage | `:86–100`, `:115` sort and merge overlapping/touching same-label intervals. Overlap calculation operates on these disjoint unions. Repeated event objects do not inflate label coverage or create duplicate episodes. |
| Reject opposite-label overlap globally | `:116–123` rejects any positive-length label-0/label-1 overlap across the entire recording, including conflicts outside predicted windows. Touching boundaries are permitted. |
| Fully covered normal | `:127–134` requires a merged normal component to reach both actual window bounds. Since touching normal intervals have already merged, this is equivalent to complete normal-union coverage of the actual span. Small unknown margins stay unknown; no epsilon or boundary forgiveness. |
| Positive union at least half actual span | `:132` uses `(end-start)/2`, not a fixed 2,000 ms threshold. A 3,800 ms span with exactly 1,900 ms positive coverage qualifies; 1,899.999 ms does not. A 4,000 ms span needs 2,000 ms. Coverage from separated positive intervals can jointly qualify a window, but does not automatically create an episode hit. |
| Unknown exclusion and fixed flag | `:284–315` records unknown windows/flags separately from normal errors and eligible-positive misses. Normal/proxy decisions use raw `fightScore > .5`; exactly .5 is unflagged. No calibration, reactivation, normalization or threshold search. |

The function does not rebase clocks or extend boundaries. Parent must admit annotation/duration in the same observed decoder clock as predictions; +3 ms or +14 ms offsets are not repaired. Corpus offset/clock evidence remains metadata bound by its byte hash, not independently interpreted or verified by this tool.

Floating-point comparisons use supplied finite numeric values without an added tolerance for annotation coverage. This intentionally preserves the exact contract rather than asserting frame-accurate real-world annotation boundaries. Pixel-coordinate rounding and class-probability validation tolerances are separate runner contracts, not annotation-clock forgiveness.

## Episode credit and reporting

`positive` union components become recording-level episode observations (`:275–278`). Prediction end times must progress by at least 400 ms; rows are processed in that order. `:291–306` grants credit only when the window is both positive-proxy eligible and flagged, and the **single** episode overlaps at least half its actual span. It assigns at most one earliest unmatched compatible episode per flag, and at most one hit per episode.

Further flags compatible only with already matched episodes become `duplicateCompatibleFlags`. Two separated short episodes can jointly make a positive-proxy window while neither alone meets compatibility; the flag then receives no episode hit and increments `positiveFlagsWithoutSingleEpisodeCompatibility`. A later interaction outside an earlier episode cannot credit that earlier episode. There is no three-second grace, event extension, starts-in-progress latency adjustment, cooldown simulation or historical incident forgiveness.

Compatible opportunities are recorded for unflagged eligible-positive windows too. Counts distinguish episodes with an opportunity, matched/missed episodes with opportunities and episodes without a compatible window. No opportunity does not silently become a detected or ordinary episode. Zero-prediction recordings are retained as omissions without fabricated labels, provided the overall report contains at least one valid prediction.

Per-recording, per-source-group and global counts are additive and include contributing IDs. Episode counts are explicitly recording observations: the tool does **not** deduplicate real-world incidents across uploads, crops, derivatives or shared sessions. It computes no accuracy percentage, operational alerts/hour or latency. These counts are not independent people, incidents or trials.

## Role, raw report, score and pairing validation

- `:137–170` validates a bounded corpus, unique recording IDs, nonempty identity fields, reviewed status, recognized historical split, lowercase media SHA, valid duration/crop and explicit events. Identical media cannot be assigned to different source groups. The original role must match the supplied role.
- `:82–83`, `:152–155` implement exactly first-byte SHA-256 of UTF-8 `nivra-online-wave1-v1:` plus sourceGroup: below 128 is dev, otherwise reserved. `run:366–370` admits the pinned corpus and its role before opening prediction bytes. This sequencing is independently tested with a failing raw-read sentinel.
- `:242–255` requires complete diagnostic schema/status, supported candidate, unchanged-live/unfitted-threshold flags, exact policy hash, recomputed policy content hash, valid bounded limits and exactly one raw clip per corpus ID. `run:372–373` additionally binds the report's corpus SHA to the caller's explicit corpus pin. The file-based `run`/CLI is the supported integrity boundary; calling `summarize` directly does not independently pin file bytes.
- `:258–268` requires exact sourceGroup, media SHA, historical split, duration, crop, derivative and nested `qualityVariant` agreement. It retains quality metadata without treating a derivative as independent evidence.
- `:190–206` checks 8–48 finite actual observations, nonnegative source PTS, gaps 100–1,200 ms, actual span 3,800–4,000 ms, reported first/last PTS equality, end within duration, at least 400 ms between predictions, and exact selected 16 indices/PTS/repetition count. It neither invents windows in gaps nor pads a short source.
- `:207–221` validates integer source/view dimensions and pixel budgets, normalized crop conversion using Python `round`, integer pixel bounds, matching crop-view size, buffer-pixel limits and occurrence in observed decoder dimension metadata. Portrait 720x1280 is correctly accepted; no landscape-only width rule is introduced.
- `:222–230` checks two finite probabilities in [0,1], sum tolerance 1e-5, fight-score/index tolerance 1e-6, supported score kind, finite nonnegative inference duration and exact strict flag. MC3 uses fight index 0; X3D/VideoMAE/community/community-v2 use 1. All preserve supplied raw scores and class order.
- `:231–234` reconstructs raw annotation-overlap context in corpus event order and requires exact agreement. `:269–274`, `:316`, `:334–336` validate clip/root sample and flag counts, total window budget and ordered paired-identity hash. The identity field list matches benchmark source `:575–582`; benchmark score/temporal checks at `:450–470` and raw clip/report construction at `:583–623` agree with the postprocessor's consumed schema.

These checks verify consistency of parent-admitted raw bytes and declared observed geometry/timing. They do not reread media, prove every possible decoder window was emitted or authenticate model assets. A raw row removed without updating dependent counts/hashes fails; a newly re-authored, completely repinned report can only be assessed against the available declared contract. Cross-candidate equality of paired hashes must still be enforced by the parent comparison workflow; this program consumes one candidate report at a time.

`adaptationIdentity` is copied from raw metadata (`:340`), not independently validated against a checkpoint/seal here. Actual model/epoch identity and rights are parent/benchmark admission responsibilities. No asset, model, media path or checkpoint is opened by the postprocessor. A nonempty license field is not independent rights verification, and the deterministic group hash cannot establish real actor/session independence or detect undiscovered duplicate footage.

## JSON integrity and exclusive outputs

`load_json:52–69` rejects duplicate keys, NaN/Infinity and nonfinite exponent values. `finite` rejects booleans and overflow-sized numeric values in relevant numeric fields. `read_pinned:72–79` requires explicit lowercase SHA pins and bounds corpus/raw JSON to 16/128 MiB. Runner limits are positive bounded integers; total window count is at most 10,000.

`run:362–383` rejects an existing output before work, validates inputs, rehashes both inputs after summary creation, serializes with `allow_nan=False`, then opens the new output in exclusive `x` mode. Invalid validation paths do not publish a successful partial summary; input raw/corpus bytes are preserved. Exclusive creation also protects against a competing output creator. This is not an fsync-backed transaction or protection against an adversarial filesystem mutation after the last hash check. A disk/write interruption may leave a partial output file that must not be interpreted as a successful parseable summary or overwritten for retry.

The summary binds raw report, corpus, policy, paired-window and postprocessor source hashes. These establish local byte identity, not signed authenticity. The source is fixed for this audit; executing source and then independently editing its on-disk file during a run is outside the immutable-input operating assumption.

## Independent execution and additional checks

Using the existing Python, with `sys.dont_write_bytecode=True`, pytest plugin autoload disabled and cache provider disabled:

```text
pytest -q --tb=short -p no:cacheprovider
  service/tests/test_summarize_online_diagnostics.py
```

**63 passed in 0.25 seconds.** Before/after hashes matched all four source/contract files listed above. The harness blocked imports rooted at `torch`, `torchvision`, `numpy`, `cv2`, `pytorchvideo` and `benchmark_cctv_candidates`. The postprocessor's AST has only standard-library imports. Pytest itself was used as an existing verification dependency; the postprocessing and additional reference calculations use standard-library code only. No packages were installed.

The tests cover independent interval union reference, exact half-span boundaries, clock margins, unknown flags, strict .5 threshold, later-action non-credit, fragmented episode coverage, duplicate compatible flags, no-opportunity episodes, all five candidate mappings, repeated selection with eight observations, portrait crop geometry, synthetic reserved-role processing, rejected roles/annotations, damaged raw contracts, zero-prediction omissions, total budgets, both input pins, duplicate/nonfinite JSON, role-before-raw-read, mutation during postprocessing, CLI success and no overwrite. Their expected intervals and raw fixtures are synthetic, not real reserved reports.

Additional independent in-memory checks, with no shared test edits:

1. Exhausted **81** four-cell annotation arrangements: each 950 ms cell independently normal, positive or unknown. Duplicate full intervals and touching half-intervals were injected for each annotated cell. A separate cell-count oracle determined eligibility; both direct classification and full synthetic report summaries agreed on every case. Each synthetic flag credited at most one episode.
2. For **all 41** allowed observation counts 8–48, compared selected-index arithmetic against exact standard-library `Fraction` floor results. All agreed. Runner NumPy was not imported; its `linspace(...).astype(int)` source was inspected separately.
3. Injected an opposite-label conflict far outside the only prediction; the whole input was rejected.
4. Constructed two distinct synthetic dev source groups, each with two separate compatible episodes and flags. Per-group counts each had two matches; global count had four, preserving recording-level episode observations.

These are additional synthetic cases, not 81 real-data trials or a substitute for model/annotation evidence. No real prediction/corpus files, media, checkpoint or decoder were opened for this task. No broad project suite was rerun because this isolated JSON-only check did not require model-adjacent execution.

## Remaining checks outside this audit

No real reserved output was inspected, created or summarized. Parent alone controls the final reserved evaluation and must freeze model/epoch, threshold and complete alert policy first. If reserved outcomes influence tuning, those sources lose fresh-audit status. The CLI role flag is a procedural guard, not an access-control/authentication mechanism.

Parent reports that wave one's retained normal windows are reserved while development intervals remain unknown; those acquisition/annotation counts were not independently reopened in this code-only audit. This postprocessor does not repair that lack of eligible development normals. Model selection must remain blocked until the parent's required development evidence is admitted, without exploring reserved scores to choose a model.

Annotation evidence, dense frame inspection, rebased clock receipts, media bytes, source rights, author/event/session grouping, cross-candidate pairing and checkpoint identity remain external admission gates. Runtime counters cannot certify visible actions or independence. Labels remain provisional assistant review; sports/contact proxies do not establish hostility, intent, injury, identity or crime. Existing few-source diagnostics and synthetic tests establish no production accuracy, operational false-alert rate, 50–100-person coverage, real near-IR, thermal or low-light-colour performance.
