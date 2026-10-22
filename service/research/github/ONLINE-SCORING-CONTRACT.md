# Frozen online diagnostic scoring contract

This postprocessor reads JSON only. It never imports Torch, NumPy, OpenCV, model
adapters or the benchmark; never decodes/opens media; and never runs inference,
training or threshold selection. It writes a new summary without changing raw
reports, corpora, event bounds or any live code. Implementation is
`service/summarize_online_diagnostics.py`; tests are synthetic JSON only.

## Inputs, admission and role boundary

Require one completed `benchmark_cctv_candidates.py` report, its exact frozen
parent-admitted runner-compatible corpus list, **both explicit SHA-256 pins**,
one explicit role, and a new output path. Parent admits annotation evidence,
source rights, media bytes and role assignment before scoring. This tool checks
the pinned corpus and raw report agree; it does not independently inspect footage
or establish that a `reviewed` flag reflects full continuous visual inspection.

Each corpus recording keeps runner fields `id`, `sourceGroup`, `path`, `sha256`,
`license`, `annotationStatus='reviewed'`, `split`, `durationMs`, `events`, and any
crop/quality metadata. It additionally requires:

- `role`: exactly `dev` or `reserved`, matching the one CLI role for every record.
- `originalRole`: `development` for dev, `reserved-audit` for reserved.
- Every event: finite `startMs < endMs` within the admitted duration, and integer
  `targetLabel=0` for reviewed ordinary activity or `1` for a contact/sports proxy.
  Boolean labels are rejected. Optional `startsInProgress` must be boolean.

The predeclared source-group role is unchanged: first byte of
SHA-256(UTF8(`nivra-online-wave1-v1:` + sourceGroup)) below 128 maps to dev;
otherwise reserved. Reject cross-role corpora, changed original roles, duplicate
recording IDs, identical media assigned to different groups, unreviewed records,
conflicting labels and malformed intervals. Admit the corpus and its role **before
opening prediction bytes**. The role flag is an explicit procedural gate, not an
authentication system. Only parent performs the reserved final audit. If reserved
results influence tuning, those sources become development and cannot remain a
fresh audit. This helper has read no actual reserved prediction report.

## Clock and interval semantics

Parent explicitly rebases acquired source annotations/duration to the **observed
decoder PTS clock** before admission, preserving original source bounds, offset
and clock receipt in the frozen corpus. The postprocessor never applies an offset,
rounding tolerance, frame-rate clock substitution or time-axis repair. Exact
source milliseconds are used as supplied. A +3 ms or +14 ms source-clock mismatch
is not silently corrected. Every prediction end must fit the admitted duration.
Corpus metadata and original clock receipts remain bound by the corpus byte hash;
the tool does not reinterpret an offset field or claim it verified clock evidence.

Treat annotation intervals as half-open for coverage measure. Merge overlaps and
touching same-label intervals into sorted unions, preventing duplicate coverage.
Any positive-length overlap between label-0 and label-1 unions is a conflict and
rejects the entire input, even outside predicted windows. Merely touching opposite
labels is allowed. Empty events means unknown, never implicit full-duration normal.

For each **actual** prediction window `[first observed PTS, last observed PTS]`,
with span S (normally 3800–4000 ms under the pinned policy):

1. Eligible normal only if the explicit label-0 union covers the entire span,
   with bounds reaching both actual bounds. An uninspected margin or tail remains unknown.
2. Eligible positive proxy if explicit label-1 union overlap is **at least S/2**.
   Use actual span, not a nominal 4000 ms denominator. Do not double-count overlap.
3. Everything else is unknown and excluded from eligible-label comparisons.

Mixed explicit normal/proxy windows may be proxy-eligible at the half-span rule;
they cannot be normal unless the whole span is explicitly normal. There is no
epsilon near coverage boundaries. The decision is always raw `fightScore > .5`:
exact .5 is unflagged. Scores are not reactivated, normalized, calibrated or tuned.

## Raw report integrity and paired-window contract

Require raw schema version 1, `complete=true`, `status='complete-diagnostic-only'`,
no threshold fitting/live modification, and corpus byte hash equal to the supplied
corpus SHA. Pin exact paired policy SHA:
`c974d6f61ab429335cd6a1d917687c6671370a6a0c0edc54633e5a869cd74ac4`.
Recompute both the policy hash and ordered `pairedWindowSha256` from raw identities.
No pre-resized training-window interpretation is used.

Validate every corpus recording has exactly one raw clip entry with exact group,
media hash, split, duration, crop and `qualityVariant` agreement. Check sample and
flag counts, root window count, and every identity field used by the runner:

- Clip/group/media/crop identity; native source/view dimensions and integer crop
  pixels derived from normalized coordinates using the runner's Python rounding.
  Native portrait 720x1280 is valid; no landscape-only width assumption.
- Source/view dimensions occur in the raw observed decoder metadata; actual pixel
  and sample buffers fit the report's bounded limits.
- 8–48 actual observations; strictly increasing 100–1200 ms sample gaps; actual
  span 3800–4000 ms; prediction ends separated by at least 400 ms. Source gap or
  dimension resets can yield wider prediction gaps; no unreported windows are
  invented to fill them.
- First/last PTS equal reported actual bounds; selected 16 indices reproduce the
  runner's uniform-linspace-floor sampling; selected PTS and repetition count match.
- Finite two-class probability vector sums to one within the runner's tolerance;
  raw fight score/index/order and score kind match the selected candidate. MC3's
  fight index is 0; all other supported candidates use index 1. Retain the exact
  recorded score and strict flag; no extra Softmax.
- Raw annotation overlap context exactly agrees with corpus events on the actual
  window. A row removed without updating all counts/identity pins fails; any raw
  byte change without the explicitly supplied report pin also fails.

Corpora are bounded to 16 MiB and raw reports to 128 MiB, with runner limits
validated and at most 10000 total windows. Reject duplicate JSON keys and nonfinite
JSON numbers. Media paths are metadata only: no media/decoder/checkpoint is opened.
Raw media hashes are compared to the admitted corpus, not recomputed from footage.

A raw clip explicitly containing zero predictions is retained as
`noPredictionRecordings=1`, with no fabricated window labels. An entirely empty
prediction report, missing sample arrays/clip entries or inconsistent counts is
rejected. Legitimate zero-prediction records are omissions, not normal coverage.

## Counts and compatible-event matching

Provide global, per-recording and per-source-group counts of eligible proxy
windows flagged/missed, eligible normal windows flagged/unflagged, and unknown
windows/flags. Unknown flags are visible but not relabeled as normal errors.
Source groups also list contributing recording IDs. All counts are observations,
not independent examples or people. No accuracy percentage or alerts/hour is
computed. The tool does not turn short zero-alert footage into an operational
false-alert-rate claim.

Proxy episodes are connected components of the explicit label-1 union within a
recording. Process prediction windows chronologically. Only a flagged eligible
proxy window can credit an episode, and that **single** episode must overlap at
least half that actual window span. Credit the earliest unmatched compatible
episode, at most once; each flag credits at most one episode. Further compatible
flags are counted as duplicates. Report compatible-window indices and matched
window index for auditability, but no latency estimate.

Two separated short episodes may jointly make a proxy-eligible window while
neither individually meets the compatibility rule: count its positive flag, give
neither episode a hit, and expose `positiveFlagsWithoutSingleEpisodeCompatibility`.
A later kick/interaction cannot credit an earlier event outside its window. No
three-second forgiveness, event-bound expansion, startsInProgress latency, cooldown
simulation or greedy historical incident credit is introduced.

Separate episode observations with compatible prediction opportunity from those
with none. Group sums of episode observations are **not** deduplicated real-world
incidents across uploads/crops/derivatives; matching is once per recording episode.
Without admitted cross-record event identity and shared clocks, do not invent
incident independence or silently merge different recordings into one event.
Overlapping windows, common actors/session, crops and variants remain dependent.

## Parent invocation and output

From `service`, after freezing the admitted corpus and completed benchmark bytes:

```powershell
.venv/Scripts/python.exe summarize_online_diagnostics.py --report research/runs/<COMPLETED-DEV-REPORT>.json --report-sha256 '<RAW-REPORT-SHA256>' --corpus evaluation/<FROZEN-DEV-CORPUS>.json --corpus-sha256 '<CORPUS-SHA256>' --role dev --output research/runs/<NEW-DEV-SUMMARY>.json
```

Names above are placeholders, not claims that those files exist. Parent alone may
use `--role reserved` for the final frozen audit. Do not generate a reserved report
to choose model/epoch/threshold. This helper executes only synthetic fixtures.

The output identifies raw report, corpus, postprocessor, policy and paired-window
hashes, candidate, role, counts, per-window eligibility/coverage, and episode
matching. Raw bytes are preserved. Recheck input hashes after summarizing, then
create the new output exclusively; never overwrite an existing output, report or
corpus. No successful partial summary is written if validation fails.

The labels are provisional assistant annotations, not human ground truth. Sports
proxies do not establish intent, crime, injury or hostile fights. These few-source
diagnostics do not establish production accuracy, crowd coverage, real near-IR,
thermal, low-light-colour performance, incident recall or live capacity. Parent's
frozen model-selection policy remains external and unchanged.

## Verification

`service/tests/test_summarize_online_diagnostics.py` uses only synthetic JSON and
stdlib interval references. It checks independent interval coverage, exact half
boundaries, clock-margin non-correction, unknown exclusion, strict threshold,
episode duplicates/later-action non-credit, all candidate score mappings,
portrait/crop/PTS identities, conflicts, missing windows, counts, role admission
before report reads, input/hash tampering, nonfinite/duplicate JSON, mutation
during postprocessing, no overwrite and absence of model/decoder imports.
Final focused checks: **63 passed in 0.29 seconds**. This includes successful
CLI processing of synthetic JSON, synthetic reserved-role processing only, and
an AST check limiting imports to the standard library. Python syntax and final
source hashes are checked in the completion handoff. No full project suite was
rerun for this standalone JSON-only task while parent's model job was active;
no actual prediction/benchmark report, media, checkpoint or GPU was accessed.
