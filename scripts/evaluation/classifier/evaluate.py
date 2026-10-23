"""Calibration-only selection followed by one sealed held-out test report."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from .common import DOCS, MODEL_SHA, PREPROCESSING, PRIVATE, ROOT, RUN, digest, frozen, read, sha, write
from .metrics import bootstrap, point, poisson_upper, score_recording, summary
from .policy import Policy, simulate


def load_scores(split):
    # Lazy import: pure policy/metrics tests do not load torch or a decoder.
    from .replay import cached
    data, split_sha = frozen()
    replay_receipt = read(PRIVATE / ('replay-' + split + '.json'))
    assert replay_receipt['splitSha256'] == split_sha
    rows = [r for r in data['records'] if r['evaluationSplit'] == split]
    predictions = []
    for row in rows:
        receipt = cached(row)
        if receipt is None:
            raise ValueError('incomplete replay; refusing to select or score')
        row['warmupEndMs'] = receipt['sourceClock']['warmupEndMs']
        row['replayEndMs'] = receipt['sourceClock']['lastPtsMs']
        predictions.append(receipt['windows'])
    identity = digest([dict(mediaSha256=r['sha256'], windowsSha256=digest(w)) for r, w in zip(rows, predictions)])
    assert identity == replay_receipt['cacheContentSha256']
    return data, split_sha, rows, predictions, replay_receipt


def scored(rows, predictions, policy):
    return [score_recording(r, simulate(w, policy)) for r, w in zip(rows, predictions)]


def candidate_key(candidate):
    metrics, policy = candidate['metrics'], candidate['policy']
    return (-(metrics['eventRecall'] if metrics['eventRecall'] is not None else -1),
            metrics['falseAlerts'],
            metrics['medianTimeToAlertMs'] if metrics['medianTimeToAlertMs'] is not None else math.inf,
            -policy['qualifying_threshold'], -policy['strong_threshold'], -policy['consecutive_windows'])


def calibrate():
    destination = PRIVATE / 'selected-policy.json'
    if destination.exists() or (PRIVATE / 'test-result.json').exists():
        raise FileExistsError('policy already sealed; no retuning')
    data, split_sha, rows, predictions, replay = load_scores('calibration')
    grid = data['policyGrid']
    candidates = []
    for qualifying in grid['qualifying']:
        for strong in grid['strong']:
            if strong < qualifying:
                continue
            for confirmation in grid['confirmation']:
                policy = Policy(qualifying, strong, confirmation, cooldown_ms=grid['cooldownMs'], merge_gap_ms=grid['mergeGapMs'])
                result_rows = scored(rows, predictions, policy)
                result = point(result_rows)
                upper = poisson_upper(result['falseAlerts'], result['normalHours'])
                conservative = False
                if upper is not None and upper <= 2 and result['hits']:
                    ci = bootstrap(result_rows)['falseAlertsPerHour']
                    conservative = ci['high'] is not None and max(ci['high'], upper) <= 2
                candidates.append(dict(policy=policy.json(), metrics=result, poissonUpper97_5PerHour=upper, conservativeEligible=conservative))
    conservative = [c for c in candidates if c['conservativeEligible']]
    feasible = conservative or [c for c in candidates if c['metrics']['falseAlertsPerHour'] is not None and c['metrics']['falseAlertsPerHour'] <= 2]
    calibration_feasible = bool(feasible)
    chosen = min(feasible, key=candidate_key) if feasible else min(candidates, key=lambda c: (c['metrics']['falseAlerts'], candidate_key(c)))
    selected = dict(schemaVersion=1, selectedAtUtc=datetime.now(timezone.utc).isoformat(), splitSha256=split_sha,
                    modelSha256=MODEL_SHA, policy=chosen['policy'],
                    selectionRule=('conservative_upper_bound' if conservative else 'point_estimate_fallback_insufficient_exposure') if feasible else 'no_feasible_policy_default_off',
                    calibrationFeasible=calibration_feasible,
                    conservativeMinimumPossibleUpperPerHour=poisson_upper(0, chosen['metrics']['normalHours']),
                    candidateCount=len(candidates), feasibleCandidateCount=len(feasible),
                    calibration=summary(scored(rows, predictions, Policy(**chosen['policy']))),
                    replayReceipt=replay,
                    sourceSha256={p.name: sha(p) for p in sorted((ROOT / 'scripts/evaluation/classifier').glob('*.py'))})
    write(destination, selected)
    (PRIVATE / 'selected-policy.sha256').write_text(sha(destination) + '\n')
    write(DOCS / 'calibration.json', {k: v for k, v in selected.items() if k != 'sourceSha256'})
    write(DOCS / 'calibration-candidates.json', dict(splitSha256=split_sha, candidates=candidates))
    print(json.dumps(selected, indent=2), flush=True)


def test():
    destination = PRIVATE / 'test-result.json'
    if destination.exists():
        raise FileExistsError('test result is sealed; do not rerun or tune on test')
    selected_path = PRIVATE / 'selected-policy.json'
    policy_sha = sha(selected_path)
    assert policy_sha == (PRIVATE / 'selected-policy.sha256').read_text().strip()
    selected = read(selected_path)
    data, split_sha, rows, predictions, replay = load_scores('test')
    assert selected['splitSha256'] == split_sha
    policy = Policy(**selected['policy'])
    result = summary(scored(rows, predictions, policy))
    gate_passed = result['falseAlertsPerHour'] is not None and result['falseAlertsPerHour'] <= 2
    report = dict(schemaVersion=1, evaluatedAtUtc=datetime.now(timezone.utc).isoformat(),
                  splitSha256=split_sha, selectedPolicySha256=policy_sha, modelSha256=MODEL_SHA,
                  selectionRule=selected['selectionRule'], policy=policy.json(),
                  calibration=selected['calibration'], test=result, gatePassed=gate_passed,
                  defaultEnabled=gate_passed and selected['calibrationFeasible'], replayReceipt=replay,
                  calibrationFeasible=selected['calibrationFeasible'],
                  limitations=['Assistant dense labels, not independent human-adjudicated ground truth.',
                               'Heuristic scene/duplicate groups do not establish actor/session independence.',
                               'Round-1 dev was previously inspected in fixed-epoch model comparisons; this is a new policy holdout, not a pristine external model test.',
                               'Short independent clips reset policy state; long-running camera behavior and cross-clip incidents are unverified.',
                               'Zero-count group-bootstrap CI is degenerate; the exact Poisson upper bound exposes inadequate normal exposure.',
                               'No browser people-count rule: those observations are unavailable offline.',
                               'Mac M5, live-device latency and backend integration are unverified.'])
    # Seal once; documentation rendering may be repeated without rescoring.
    write(destination, report)
    (PRIVATE / 'test-result.sha256').write_text(sha(destination) + '\n')
    write(DOCS / 'results.json', report)
    export_policy(report)
    render_readme(report)
    print(json.dumps(report, indent=2), flush=True)


def export_policy(report):
    p = Policy(**report['policy'])
    export_report = read(RUN / 'movinet/export/report.json')
    checkpoint = RUN / 'movinet/epoch-3.pt'
    checkpoint_sha = sha(checkpoint)
    assert checkpoint_sha == export_report['config']['checkpoint_sha256']
    value = dict(schemaVersion=1, model=dict(architecture='MoViNet A0, causal port, clip-reset epoch-3 fine-tune',
                                          sha256=MODEL_SHA, checkpointSha256=checkpoint_sha,
                                          inputShape=['batch', 8, 3, 172, 172], output='two logits; softmax(dim=1)[:,1] is the fight-class score',
                                          codeLicense='MIT', pretrainedWeightsLicense='Apache-2.0'),
                 preprocessing=PREPROCESSING, windowMs=4000, strideMs=p.stride_ms,
                 windowAnchor='first actual decoded source PTS',
                 windowAdmission='end = first actual PTS + 4000 + k*1000; score only when last actual decoded PTS >= end; no container-duration/EOF flush',
                 qualifyingThreshold=p.qualifying_threshold, strongThreshold=p.strong_threshold,
                 thresholdComparison='>=', confirmation=dict(consecutiveWindows=p.consecutive_windows,
                    maxGapMs=p.stride_ms, strongBypassesConfirmation=True, nonqualifyingResets=True),
                 cooldownMs=p.cooldown_ms, mergeGapMs=p.merge_gap_ms,
                 incidentMerging='one incident per episode; qualifying windows separated by <=mergeGapMs remain one episode; a longer gap rearms; camera cooldown remains in force',
                 requireTwoPeople=False, peopleCountRule='dropped: unavailable offline; do not silently enable at integration',
                 resetOn='camera/source generation change; never carry activation buffers or policy state across recordings',
                 splitSha256=report['splitSha256'], selectedPolicySha256=report['selectedPolicySha256'],
                 gate=dict(passed=report['gatePassed'], criterion='test false alerts per actionable explicit normal camera-hour <=2 (point estimate)',
                           limitFalseAlertsPerHour=2, observedFalseAlertsPerHour=report['test']['falseAlertsPerHour'],
                           normalHours=report['test']['normalHours'], ci95=report['test']['ci95']['falseAlertsPerHour'],
                           poissonUpper97_5PerHour=report['test']['poissonUpper97_5PerHour'],
                           selectionRule=report['selectionRule']), defaultEnabled=report['defaultEnabled'],
                 humanReviewRequired=True, macM5Verified=False,
                 torchscriptDeviceNote='Export pins 27 tensor-factory Device constants to CPU; CUDA replay remaps them in RAM after loading. Original model file/weights unchanged; CPU/CUDA parity passed. MPS is unverified.',
                 integration='Runtime scene decisions must reproduce the simulator, including episode merging, selected thresholds and confirmation, through Decisions.scene_update or an equivalent scene policy path; legacy hard-coded .4/.7 + people>=2 is not this policy')
    write(DOCS / 'policy.json', value)


def interval(metrics, key, scale=1, digits=2):
    value = metrics[key]
    ci = metrics['ci95'][key]
    point_text = 'n/a' if value is None else f'{value * scale:.{digits}f}'
    ci_text = 'unavailable' if ci['low'] is None else f"{ci['low'] * scale:.{digits}f}–{ci['high'] * scale:.{digits}f}"
    return f'{point_text} [{ci_text}]'


def render_readme(report):
    split = read(DOCS / 'split-summary.json')
    p, cal, test_metrics = report['policy'], report['calibration'], report['test']
    latency = read(DOCS / 'latency.json')
    lines = ['# Video classifier: held-out alert-policy evaluation', '',
             f"Result: **{'PASS' if report['gatePassed'] else 'FAIL'}** on the owner’s test point-estimate gate. **Default {'ON' if report['defaultEnabled'] else 'OFF'}**. Alerts require human review. This does not establish violence accuracy or Mac M5 performance.", '',
             '## Frozen data and leakage checks', '',
             f"Split SHA-256: `{report['splitSha256']}`. Model SHA-256: `{MODEL_SHA}`.", '',
             'A0 trained only on frozen round-1 train `bf2942793bbdfc51281c8e9c47afe1a4c566c1b0beba0fb34b5cccd8b6d4fec7`; round-1 dev is `dd215f1a8569ab7e78ae27cf94b3d6165ec21d1aef461405c1ddf4e58cc9c00e`. Those exact files were recovered from the probe inputs, not replaced with the later browser-evaluation publication.', '',
             'Pool: explicit labels from round-1 dev plus unanimously normal, densely reviewed `nv_b_04/05/07` imports. Connected components join original/current T1 groups, recording IDs and exact media SHA-256 values; every component touching round-1 train is excluded. Duplicate hashes are evaluated once. Every retained file was hashed before freezing and rechecked at replay. No train recording is evaluated.', '',
             f"Exclusions: `{json.dumps(split['exclusions'], sort_keys=True)}`. All {split['mediaSha256Verified']} retained media hashes verified; zero retained train hash/group/ID overlap. Labels-only seed 20261023 search balances recordings, events and normal exposure within contexts, never model scores. Whole groups and hashes are disjoint between calibration and test. Frozen before inference; selection sealed before test replay.", '',
             '| Split | Recordings | Groups | Events | Explicit normal h | Actionable normal h |',
             '|---|---:|---:|---:|---:|---:|']
    for name in ['calibration', 'test']:
        s = split['summary'][name]
        actual = cal if name == 'calibration' else test_metrics
        lines.append(f"| {name} | {s['recordings']} | {s['groups']} | {s['eventCount']} | {s['totalExplicitNormalHours']:.6f} | {actual['normalHours']:.6f} |")
    lines += ['', 'Actionable exposure begins 4 s after the first actual decoded PTS and ends at the last actual PTS, intersected with explicit normal intervals. The model never emits partial-window predictions or an EOF flush. All events, including early/short events that cannot be detected, remain in the recall denominator. Unknown gaps and unlabelled tails never become normal. Total explicit normal exposure is also reported above; split-summary’s predecode actionable estimate uses container bounds.', '',
              '## Exact causal replay and policy', '',
              'Sequential OpenCV decoding uses actual `CAP_PROP_POS_MSEC`, strictly increasing and finite; no nominal-FPS fallback. Scoring is anchored to the first actual PTS at +4,+5,+6… s and admitted only after an actual decoded frame reaches the score time, matching C1’s frame-driven scheduler. Container duration never supplies a final score. Use `[t−4,t)` only. Training first samples 16 equally spaced targets, endpoint excluded, then indexes `np.linspace(0,15,8).astype(int)`: `[0,2,4,6,8,10,12,15]`. The eight target offsets are `[0,.5,1,1.5,2,2.5,3,3.75]` s. Choose nearest actual in-window PTS, earlier ties. Resize full-frame BGR to 224 square, convert RGB, resize to 172 square with OpenCV linear interpolation; float32 `/255`, no mean/std. Input is `[B,8,3,172,172]`, clip reset, softmax class 1. The live 250 ms sample-coverage guard is checked, and source gaps requiring epoch reset fail closed.', '',
              'Before any test metrics were computed or inspected, live-scheduler review found that an initial container-duration replay could admit one final score beyond the last decoded PTS. The superseded calibration seal and replay receipts are retained privately in `audit-container-duration-v1/`; raw scores remain in the private cache. Admission was corrected using timestamps only on both splits; unchanged windows reuse probabilities only after exact selected-PTS equality checks. Calibration selection was repeated on corrected calibration data and sealed again before corrected test replay. The single test evaluation uses only the corrected protocol. No test outcomes informed this correction or policy selection.', '',
              f"Frozen training-input cache parity: max pixel difference {latency['preprocessingParity']['maxAbsPixelDifference']} across 8 frames. CPU/CUDA probability parity on four calibration windows: max absolute difference {latency['cpuCudaParity']['maxAbsProbability']:.9g}; tolerance 1e-4. Batch-1/batch-4 independence and repeated-forward reset checks passed.", '',
              'Export portability defect: `.cuda()` alone fails because this trace pins 27 tensor-factory device constants to CPU. Replay loads a fresh graph per device and remaps those constants to CUDA in RAM. The original model file, weights, operations and sampling are unchanged; the output parity checks above cover this remap. C1 must account for this on non-CPU TorchScript devices; MPS is unverified.', '',
              f"Chosen qualifying threshold **{p['qualifying_threshold']}**, strong threshold **{p['strong_threshold']}** (inclusive); **{p['consecutive_windows']}** consecutive qualifying windows at <=1 s gap, or one strong window. Per-camera cooldown **8 s**. One incident per continuous qualifying episode, merging gaps <=2 s; a longer gap rearms, but does not override cooldown. Any nonqualifying/invalid window breaks confirmation. State resets per camera/source generation. No offline people count is available, so the two-person requirement is dropped.", '',
              f"Calibration searched {read(DOCS / 'calibration.json')['candidateCount']} declared grid policies. Selection rule: **{report['selectionRule']}**. Maximize recall, then minimize false count and median delay, then prefer stricter thresholds and more confirmations. Conservative selection requires both group-bootstrap upper95 and exact Poisson upper97.5 <=2/h. Even zero calibration false alerts has Poisson upper {poisson_upper(0, cal['normalHours']):.2f}/h; exposure cannot support that rule, so the explicitly permitted point-estimate fallback was used. Test did not influence selection.", '',
              'Legacy `Decisions.scene_update` hard-codes .4/.7 and at least two observed people, and can alert again after cooldown. C1’s runtime scene path must apply `policy.json` and the simulator’s episode merging; this evaluation does not itself modify the backend. Interactions with other detector alerts were not simulated.', '',
              '## Results', '',
              'Values in brackets are 95% whole-group percentile bootstrap intervals, 5,000 draws, seed 20261023. Whole groups are sampled with replacement; draws without the relevant denominator are omitted and counted in JSON. Fewer than two eligible groups yields no interval. Rates use actionable explicit normal time.', '',
              '| Split | Event hits / total | Recall % [CI] | False alerts | False alerts/h [CI] | Median delay s [CI] |',
              '|---|---:|---:|---:|---:|---:|']
    for name, m in [('calibration', cal), ('test', test_metrics)]:
        lines.append(f"| {name} | {m['hits']}/{m['eventCount']} | {interval(m,'eventRecall',100)} | {m['falseAlerts']} | {interval(m,'falseAlertsPerHour')} | {interval(m,'medianTimeToAlertMs',.001)} |")
    lines += ['', f"Test p90 time-to-alert: {interval(test_metrics, 'p90TimeToAlertMs', .001)} s, conditional on detected events. Delays use annotated onset and source scoring time, excluding compute/transport; events starting at zero may already be in progress. Unknown-time alerts: {test_metrics['unknownAlerts']}; all alerts: {test_metrics['alertCount']}. Zero-count bootstrap intervals are degenerate and are not evidence of a zero underlying rate. Test exact Poisson upper97.5: **{test_metrics['poissonUpper97_5PerHour']:.2f} false alerts/h** (additional exposure diagnostic, assuming independent Poisson counts; not a replacement for the group CI).", '',
              '| Test context | Hits/events | Recall % [CI] | Normal h | False alerts | False alerts/h [CI] | Median delay s [CI] |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for context, m in test_metrics['contexts'].items():
        lines.append(f"| {context} | {m['hits']}/{m['eventCount']} | {interval(m,'eventRecall',100)} | {m['normalHours']:.6f} | {m['falseAlerts']} | {interval(m,'falseAlertsPerHour')} | {interval(m,'medianTimeToAlertMs',.001)} |")
    lines += ['', 'Classroom remains sparse/confounded: limited normal exposure, few independent positive groups, assistant labels and related settings. Per-context rates, especially street/sports/classroom, have too little exposure to establish a <=2/h operating guarantee. Missing positive classes are reported as n/a, not zero recall.', '',
              f"Gate is {'passed' if report['gatePassed'] else 'failed'} by the owner’s **test point estimate <=2/h**. `policy.json` sets `defaultEnabled` to `{str(report['defaultEnabled']).lower()}`. " + ('Recommend default ON under the owner’s rule, with human review; confidence-bound performance remains unproven.' if report['defaultEnabled'] else 'Recommend default OFF. Do not retune on this test; a new model/policy needs fresh held-out groups.'), '',
              '## Latency', '',
              f"{latency['cudaDevice']}; Windows CPU `{latency['cpu']}` with two PyTorch threads. FP32 preallocated tensor to logits; synchronized CUDA wall time. Excludes decode, preprocessing, transfers, camera transport and policy. Warmups: CPU 5 / CUDA 10; repeats: CPU 30 / CUDA 60. These are measured here, not inherited benchmark numbers.", '',
              '| Device | Batch | p50 batch ms | p95 batch ms | p50 ms/window |',
              '|---|---:|---:|---:|---:|']
    for device, batches in latency['batches'].items():
        for batch, m in batches.items():
            lines.append(f"| {device} | {batch} | {m['p50Ms']:.2f} | {m['p95Ms']:.2f} | {m['p50PerWindowMs']:.2f} |")
    lines += ['', '**Mac M5, CoreML/ANE execution, live device behavior and C1 integration are unverified.** MIT port / Apache-2.0 pretrained weights provenance follows the pinned export report. Scores are model outputs, not calibrated probabilities of violence.', '',
              '## Reproduction and files', '',
              'From repository root using the provided torch 2.5.1+cu124 Python environment:', '',
              '```powershell',
              'python -B -m unittest scripts.evaluation.classifier.test_policy_metrics scripts.evaluation.classifier.test_replay -v',
              'python -B -m scripts.evaluation.classifier.freeze',
              'python -B -m scripts.evaluation.classifier.replay --split calibration --benchmark',
              'python -B -m scripts.evaluation.classifier.evaluate calibrate',
              'python -B -m scripts.evaluation.classifier.replay --split test',
              'python -B -m scripts.evaluation.classifier.evaluate test',
              '```', '',
              'Freeze, selection and test commands deliberately refuse to overwrite their seals. Do not delete them to obtain a different test result. GPU replay/benchmark uses the existing `training_v4.gpu_lock` FIFO queue and never preempts another job.', '',
              'Repository outputs: this README, `policy.json`, `results.json`, `split-summary.json`, `calibration.json`, `calibration-candidates.json`, `latency.json`, plus scripts/tests under `scripts/evaluation/classifier/`. All repository JSON is aggregate-only. Private split/intervals, per-window probabilities and timestamps live in `D:\\nivra-work\\classifier\\` (scores in `cache/`). No footage, decoded frame, person observation or landmark is written to the repository or persisted by this replay. No services, ports, downloads, commits, pushes or branch changes.', '',
              '## Limitations', '']
    lines.extend('- ' + limitation for limitation in report['limitations'])
    lines += ['', 'Validation: policy/metrics unit tests, actual-PTS coverage assertions, all media hashes, exact training-cache pixel parity, CPU/CUDA probability parity, batch independence, frozen split disjointness and one-shot policy/test seals. Long uninterrupted negative camera footage is the next evidence needed to narrow the false-alert bound.']
    (DOCS / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['calibrate', 'test', 'render'])
    args = parser.parse_args()
    if args.action == 'calibrate':
        calibrate()
    elif args.action == 'test':
        test()
    else:
        report = read(PRIVATE / 'test-result.json')
        assert sha(PRIVATE / 'test-result.json') == (PRIVATE / 'test-result.sha256').read_text().strip()
        export_policy(report)
        render_readme(report)


if __name__ == '__main__':
    main()
