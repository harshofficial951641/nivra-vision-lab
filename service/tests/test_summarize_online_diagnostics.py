"""Stdlib/synthetic JSON only: never read actual dev/reserved scoring reports."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

import summarize_online_diagnostics as scoring


# Independent frozen runner contract; no runner, decoder, NumPy or Torch imports.
POLICY = {'version': 'cctv-paired-v1', 'windowMs': 4000, 'sampleIntervalMs': 100,
          'predictionIntervalMs': 400, 'minimumSpanMs': 3800, 'minimumObservations': 8,
          'resetGapMs': 1200, 'framesPerWindow': 16,
          'sampling': 'uniform-linspace-floor-over-observed-gate-samples',
          'spatialBuffer': 'native source/cropped uint8 BGR; no pre-resize',
          'threshold': .5, 'comparison': 'fightScore > threshold',
          'shortClipPadding': False, 'sourceClock': 'strict decoded presentation timestamps'}
INDICES_39 = [0, 2, 5, 7, 10, 12, 15, 17, 20, 22, 25, 27, 30, 32, 35, 38]


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value):
    return hash_bytes(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def group_for(role, index=0):
    while True:
        group = f'synthetic-session-{index}'
        actual = 'dev' if hashlib.sha256(('nivra-online-wave1-v1:' + group).encode()).digest()[0] < 128 else 'reserved'
        if actual == role:
            return group
        index += 1


def event(start, end, label, **extra):
    return {'startMs': start, 'endMs': end, 'targetLabel': label, **extra}


def fixtures(events=None, windows=None, role='dev', candidate='x3d'):
    record = {'id': 'recording-0', 'sourceGroup': group_for(role), 'path': 'synthetic.avi',
              'sha256': 'a' * 64, 'license': 'synthetic-only', 'annotationStatus': 'reviewed',
              'split': 'diagnostic', 'role': role,
              'originalRole': 'development' if role == 'dev' else 'reserved-audit',
              'durationMs': 10000, 'events': events if events is not None else [event(0, 10000, 0)],
              'crop': [.25, .25, .75, .75],
              'qualityVariant': {'kind': 'synthetic-compression', 'independentEvidence': False}}
    rows = []
    identities = []
    score_kind = {'x3d': 'backbone-softmax', 'mc3': 'softmax-logits', 'videomae': 'softmax-on-logits',
                  'community': 'retained-backbone-softmax', 'community-v2': 'retained-backbone-softmax'}[candidate]
    for end, score in windows if windows is not None else [(3800, .5)]:
        pts = list(range(end - 3800, end + 1, 100))
        identity = {'clipId': record['id'], 'sourceGroup': record['sourceGroup'], 'mediaSha256': record['sha256'],
                    'crop': record['crop'], 'windowStartMs': pts[0], 'timestampMs': pts[-1],
                    'sourceDimensionsWH': [720, 1280], 'viewDimensionsWH': [360, 640],
                    'cropPixelsLTRB': [180, 320, 540, 960], 'sourceFramePTS': pts,
                    'selectedFramePTS': [pts[index] for index in INDICES_39]}
        identities.append(identity)
        index = 0 if candidate == 'mc3' else 1
        rows.append({**identity, 'selectedFrameIndices': INDICES_39, 'repeatedSelectedIndices': 0,
                     'fightScore': score, 'classScores': [score, 1 - score] if index == 0 else [1 - score, score],
                     'fightIndex': index, 'scoreKind': score_kind, 'review': score > .5, 'inferenceMs': 10.,
                     'labelledEventOverlaps': [{**annotation, 'overlapMs': min(end, annotation['endMs']) -
                                                max(end - 3800, annotation['startMs'])}
                                               for annotation in record['events'] if annotation['endMs'] > pts[0]
                                               and annotation['startMs'] < end]})
    clip = {'sourceGroup': record['sourceGroup'], 'historicalSplit': 'diagnostic', 'crop': record['crop'],
            'qualityVariant': record['qualityVariant'], 'derivative': True, 'declaredDurationMs': record['durationMs'],
            'media': {'sha256': record['sha256'], 'bytes': 10}, 'windows': len(rows),
            'reviewWindows': sum(row['review'] for row in rows), 'samples': rows,
            'decoder': {'sourceDimensions': [[720, 1280]], 'viewDimensions': [[360, 640]]}}
    report = {'schemaVersion': 1, 'complete': True, 'status': 'complete-diagnostic-only', 'candidate': candidate,
              'thresholdFittedHere': False, 'liveModelChanged': False, 'policy': deepcopy(POLICY),
              'policySha256': canonical_hash(POLICY), 'windowCount': len(rows),
              'pairedWindowSha256': canonical_hash(identities),
              'limits': {'max_source_pixels': 1920 * 1080, 'max_dimension': 3840,
                         'max_buffer_pixels': 100_000_000, 'max_windows': 1000,
                         'max_decode_frames': 100_000, 'max_clips': 100}, 'clips': {record['id']: clip}}
    return [record], report


def write_inputs(tmp_path, corpus, report):
    corpus_path, report_path = tmp_path / 'corpus.json', tmp_path / 'raw.json'
    corpus_bytes = json.dumps(corpus, indent=2).encode()
    report = deepcopy(report)
    report['corpusSha256'] = hash_bytes(corpus_bytes)
    report_bytes = json.dumps(report, indent=2).encode()
    corpus_path.write_bytes(corpus_bytes)
    report_path.write_bytes(report_bytes)
    return report_path, corpus_path, hash_bytes(report_bytes), hash_bytes(corpus_bytes)


def test_interval_union_overlap_against_independent_integer_time_coverage():
    spans = [(8, 12), (0, 4), (2, 6), (6, 8), (20, 21), (20, 24)]
    merged = scoring.interval_union(spans)
    assert merged == [(0, 12), (20, 24)]
    covered = {unit for left, right in spans for unit in range(left, right)}
    for start in range(25):
        for end in range(start + 1, 26):
            assert scoring.overlap(merged, start, end) == len(set(range(start, end)) & covered)


@pytest.mark.parametrize('normal,positive,expected', [
    ([(0, 1900), (1900, 3800)], [], 'normal'),
    ([(0, 3799.999)], [], 'unknown'),
    ([(3, 3803)], [], 'unknown'),  # Parent must rebase clocks; processor never adds 3 ms.
    ([], [(0, 1900)], 'positive-proxy'),
    ([], [(0, 1899.999)], 'unknown'),
    ([], [(0, 1000), (2000, 2900)], 'positive-proxy'),
    ([], [], 'unknown'),
])
def test_actual_span_coverage_and_exact_half_boundaries(normal, positive, expected):
    normal = scoring.interval_union(normal)
    positive = scoring.interval_union(positive)
    assert scoring.classify_window(normal, positive, 0, 3800) == expected


def test_counts_strict_threshold_unknown_exclusion_and_one_credit_per_episode(tmp_path):
    corpus, report = fixtures([event(0, 4000, 0), event(4000, 10000, 1, startsInProgress=True)],
                              [(3800, .5), (4200, .8), (6200, .8), (6600, .8), (7000, .5)])
    report_path, corpus_path, raw_sha, corpus_sha = write_inputs(tmp_path, corpus, report)
    before = (report_path.read_bytes(), corpus_path.read_bytes())
    result = scoring.run(report_path, corpus_path, tmp_path / 'new' / 'summary.json',
                          report_sha256=raw_sha, corpus_sha256=corpus_sha, role='dev')
    tally = result['counts']
    assert tally['predictionWindows'] == 5
    assert tally['normalWindows'] == 1 and tally['normalFlagged'] == 0
    assert tally['unknownWindows'] == tally['unknownFlagged'] == 1
    assert tally['positiveProxyWindows'] == 3 and tally['positiveProxyFlagged'] == 2
    assert tally['positiveProxyMissed'] == 1
    assert tally['matchedProxyEpisodeObservations'] == tally['duplicateCompatibleFlags'] == 1
    assert result['byRecording']['recording-0']['proxyEpisodeObservations'][0]['matchedWindowIndex'] == 2
    assert result['bySourceGroup'][corpus[0]['sourceGroup']]['counts'] == tally
    assert result['latencyComputed'] is False and result['thresholdFittedHere'] is False
    assert result['byRecording']['recording-0']['qualityVariant'] == corpus[0]['qualityVariant']
    assert (result['byRecording']['recording-0']['windows'][2]['classScores'] ==
            report['clips']['recording-0']['samples'][2]['classScores'])
    assert 'accuracy' not in result and 'falseAlertsPerHour' not in result
    assert before == (report_path.read_bytes(), corpus_path.read_bytes())
    assert result['rawReportSha256'] == raw_sha and result['corpusSha256'] == corpus_sha


def test_later_episode_never_credits_earlier_action_and_fragmented_union_is_not_two_hits():
    corpus, report = fixtures([event(0, 1000, 1), event(4000, 10000, 1)], [(7800, .9)])
    result = scoring.summarize(report, corpus, role='dev')
    episodes = result['byRecording']['recording-0']['proxyEpisodeObservations']
    assert episodes[0]['matchedWindowIndex'] is None and episodes[1]['matchedWindowIndex'] == 0
    assert result['counts']['proxyEpisodesWithoutCompatibleWindow'] == 1
    corpus, report = fixtures([event(0, 1000, 1), event(2000, 3000, 1)], [(3800, .9)])
    result = scoring.summarize(report, corpus, role='dev')
    assert result['counts']['positiveProxyFlagged'] == 1
    assert result['counts']['matchedProxyEpisodeObservations'] == 0
    assert result['counts']['positiveFlagsWithoutSingleEpisodeCompatibility'] == 1


def test_actual_4000_span_uses_2000_half_boundary_without_nominal_shortcuts():
    assert scoring.classify_window([], [(0, 1900)], 0, 4000) == 'unknown'
    assert scoring.classify_window([], [(0, 2000)], 0, 4000) == 'positive-proxy'


def test_touching_opposite_labels_have_no_positive_length_conflict():
    normal, positive = scoring.annotations([event(0, 1900, 0), event(1900, 3800, 1)], 3800)
    assert scoring.classify_window(normal, positive, 0, 3800) == 'positive-proxy'


def test_eight_observation_window_keeps_explicit_repeated_frame_selection():
    corpus, report = fixtures(windows=[(3850, .8)])
    row = report['clips']['recording-0']['samples'][0]
    pts = [0, 550, 1100, 1650, 2200, 2750, 3300, 3850]
    indices = [0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7]
    row.update({'sourceFramePTS': pts, 'windowStartMs': 0, 'timestampMs': 3850,
                'selectedFrameIndices': indices, 'selectedFramePTS': [pts[index] for index in indices],
                'repeatedSelectedIndices': 8,
                'labelledEventOverlaps': [{**corpus[0]['events'][0], 'overlapMs': 3850}]})
    report['pairedWindowSha256'] = canonical_hash([{name: row[name] for name in scoring.IDENTITY_FIELDS}])
    result = scoring.summarize(report, corpus, role='dev')
    assert result['counts']['normalFlagged'] == 1


def test_reserved_role_supported_only_with_matching_synthetic_admitted_corpus(tmp_path):
    corpus, report = fixtures(role='reserved')
    raw, frozen, raw_sha, corpus_sha = write_inputs(tmp_path, corpus, report)
    result = scoring.run(raw, frozen, tmp_path / 'synthetic-reserved-summary.json',
                          report_sha256=raw_sha, corpus_sha256=corpus_sha, role='reserved')
    assert result['role'] == 'reserved'
    assert result['byRecording']['recording-0']['originalRole'] == 'reserved-audit'


@pytest.mark.parametrize('candidate', ['x3d', 'mc3', 'videomae', 'community', 'community-v2'])
def test_original_class_order_and_activation_scores_are_not_transformed(candidate):
    corpus, report = fixtures(windows=[(3800, .8)], candidate=candidate)
    result = scoring.summarize(report, corpus, role='dev')
    assert result['counts']['normalFlagged'] == 1
    assert result['byRecording']['recording-0']['windows'][0]['fightScore'] == .8
    assert result['pairedWindowSha256'] == report['pairedWindowSha256']


@pytest.mark.parametrize('damage', ['conflict', 'missing-target', 'bool-target', 'zero-interval', 'outside-duration',
                                   'mixed-role', 'bad-original-role', 'wrong-group-role', 'unreviewed'])
def test_invalid_annotation_or_role_contract(damage):
    corpus, report = fixtures()
    if damage == 'conflict': corpus[0]['events'].append(event(100, 300, 1))
    if damage == 'missing-target': corpus[0]['events'][0].pop('targetLabel')
    if damage == 'bool-target': corpus[0]['events'][0]['targetLabel'] = False
    if damage == 'zero-interval': corpus[0]['events'][0]['endMs'] = 0
    if damage == 'outside-duration': corpus[0]['events'][0]['endMs'] = 10001
    if damage == 'mixed-role': corpus[0]['role'] = 'reserved'
    if damage == 'bad-original-role': corpus[0]['originalRole'] = 'reserved-audit'
    if damage == 'wrong-group-role': corpus[0]['sourceGroup'] = group_for('reserved')
    if damage == 'unreviewed': corpus[0]['annotationStatus'] = 'pending'
    with pytest.raises(ValueError):
        scoring.summarize(report, corpus, role='dev')


@pytest.mark.parametrize('damage', ['source-group', 'media', 'missing-recording', 'missing-samples', 'window-count',
                                   'root-count', 'paired-hash', 'pts-gap', 'pts-duplicate', 'span', 'timestamp',
                                   'selected-pts', 'selected-indices', 'dimensions', 'crop-pixels', 'view',
                                   'decoder-dimensions', 'nonfinite-score', 'wrong-index', 'wrong-activation',
                                   'wrong-review', 'probabilities', 'overlaps', 'policy', 'incomplete', 'after-duration'])
def test_resigned_raw_input_still_rejects_inner_contract_damage(damage):
    corpus, report = fixtures(windows=[(3800, .8)])
    clip = report['clips']['recording-0']
    row = clip['samples'][0]
    if damage == 'source-group': row['sourceGroup'] = 'other'
    if damage == 'media': clip['media']['sha256'] = 'b' * 64
    if damage == 'missing-recording': report['clips'] = {}
    if damage == 'missing-samples': clip.pop('samples')
    if damage == 'window-count': clip['windows'] = 2
    if damage == 'root-count': report['windowCount'] = 0
    if damage == 'paired-hash': report['pairedWindowSha256'] = 'b' * 64
    if damage == 'pts-gap': row['sourceFramePTS'][10] += 1300
    if damage == 'pts-duplicate': row['sourceFramePTS'][1] = 0
    if damage == 'span': row['sourceFramePTS'][-1] += 300
    if damage == 'timestamp': row['timestampMs'] = True
    if damage == 'selected-pts': row['selectedFramePTS'][-1] -= 1
    if damage == 'selected-indices': row['selectedFrameIndices'] = [0] * 16
    if damage == 'dimensions': row['sourceDimensionsWH'] = [1280, 720]
    if damage == 'crop-pixels': row['cropPixelsLTRB'][0] = 0
    if damage == 'view': row['viewDimensionsWH'] = [640, 360]
    if damage == 'decoder-dimensions': clip['decoder']['sourceDimensions'] = []
    if damage == 'nonfinite-score': row['fightScore'] = float('nan')
    if damage == 'wrong-index': row['fightIndex'] = 0
    if damage == 'wrong-activation': row['scoreKind'] = 'logits'
    if damage == 'wrong-review': row['review'] = False
    if damage == 'probabilities': row['classScores'] = [.8, .8]
    if damage == 'overlaps': row['labelledEventOverlaps'] = []
    if damage == 'policy': report['policy']['threshold'] = .4
    if damage == 'incomplete': report['complete'] = False
    if damage == 'after-duration': corpus[0]['durationMs'] = clip['declaredDurationMs'] = 3700
    with pytest.raises(ValueError):
        scoring.summarize(report, corpus, role='dev')


def test_missing_coverage_is_unknown_and_zero_prediction_recordings_are_explicit():
    corpus, report = fixtures(events=[])
    result = scoring.summarize(report, corpus, role='dev')
    assert result['counts']['unknownWindows'] == 1 and result['counts']['normalWindows'] == 0
    second = deepcopy(corpus[0])
    second['id'], second['sha256'] = 'short', 'b' * 64
    corpus.append(second)
    empty = deepcopy(report['clips']['recording-0'])
    empty.update({'samples': [], 'windows': 0, 'reviewWindows': 0, 'media': {'sha256': 'b' * 64, 'bytes': 0}})
    report['clips']['short'] = empty
    result = scoring.summarize(report, corpus, role='dev')
    assert result['counts']['noPredictionRecordings'] == 1
    assert result['byRecording']['short']['counts']['predictionWindows'] == 0
    assert result['sourceGroups'] == 1 and result['recordings'] == 2


def test_global_window_budget_applies_across_recordings():
    corpus, report = fixtures()
    other = deepcopy(corpus[0])
    other['id'], other['sha256'] = 'other', 'b' * 64
    corpus.append(other)
    clip = deepcopy(report['clips']['recording-0'])
    clip['media']['sha256'] = 'b' * 64
    clip['samples'][0]['clipId'] = 'other'
    clip['samples'][0]['mediaSha256'] = 'b' * 64
    report['clips']['other'] = clip
    report['windowCount'] = 2
    report['limits']['max_windows'] = 1
    with pytest.raises(ValueError, match='Total actual prediction window budget'):
        scoring.summarize(report, corpus, role='dev')


@pytest.mark.parametrize('damage', ['raw-bytes', 'corpus-bytes', 'report-corpus-sha', 'bad-pin'])
def test_file_tampering_or_pin_mismatch_never_writes_output(tmp_path, damage):
    corpus, report = fixtures()
    if damage == 'report-corpus-sha': report['corpusSha256'] = 'b' * 64
    raw, frozen, raw_sha, corpus_sha = write_inputs(tmp_path, corpus, report)
    if damage == 'raw-bytes': raw.write_bytes(raw.read_bytes() + b' ')
    if damage == 'corpus-bytes': frozen.write_bytes(frozen.read_bytes() + b' ')
    if damage == 'report-corpus-sha':
        value = json.loads(raw.read_text())
        value['corpusSha256'] = 'b' * 64
        raw.write_text(json.dumps(value))
        raw_sha = hash_bytes(raw.read_bytes())
    if damage == 'bad-pin': raw_sha = 'not-a-digest'
    output = tmp_path / 'never' / 'summary.json'
    with pytest.raises(ValueError):
        scoring.run(raw, frozen, output, report_sha256=raw_sha, corpus_sha256=corpus_sha, role='dev')
    assert not output.parent.exists()


def test_cross_role_admission_happens_before_opening_prediction_bytes(tmp_path, monkeypatch):
    corpus, report = fixtures(role='reserved')  # Synthetic reserved JSON only.
    raw, frozen, raw_sha, corpus_sha = write_inputs(tmp_path, corpus, report)
    original = Path.read_bytes

    def read(path):
        if path == raw:
            pytest.fail('Cross-role prediction bytes opened')
        return original(path)

    monkeypatch.setattr(Path, 'read_bytes', read)
    with pytest.raises(ValueError, match='role'):
        scoring.run(raw, frozen, tmp_path / 'none.json', report_sha256=raw_sha, corpus_sha256=corpus_sha, role='dev')


def test_no_overwrite_cli_and_inputs_changed_during_processing(tmp_path, monkeypatch):
    corpus, report = fixtures()
    raw, frozen, raw_sha, corpus_sha = write_inputs(tmp_path, corpus, report)
    output = tmp_path / 'summary.json'
    args = ['--report', str(raw), '--report-sha256', raw_sha, '--corpus', str(frozen),
            '--corpus-sha256', corpus_sha, '--role', 'dev', '--output', str(output)]
    assert scoring.main(args) == 0
    before = output.read_bytes()
    assert scoring.main(args) == 1 and output.read_bytes() == before
    original = scoring.summarize

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        raw.write_bytes(raw.read_bytes() + b' ')
        return result

    monkeypatch.setattr(scoring, 'summarize', mutate)
    with pytest.raises(ValueError, match='changed during'):
        scoring.run(raw, frozen, tmp_path / 'never' / 'result.json',
                     report_sha256=raw_sha, corpus_sha256=corpus_sha, role='dev')
    assert not (tmp_path / 'never').exists()


def test_duplicate_json_nonfinite_and_model_decoder_imports_are_rejected_or_absent():
    for value in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}'):
        with pytest.raises(ValueError):
            scoring.load_json(value)
    parsed = ast.parse(Path(scoring.__file__).read_text())
    modules = {alias.name.split('.')[0] for node in ast.walk(parsed) if isinstance(node, ast.Import) for alias in node.names}
    modules.update(node.module.split('.')[0] for node in ast.walk(parsed) if isinstance(node, ast.ImportFrom))
    assert modules <= {'argparse', 'hashlib', 'json', 'math', 'pathlib', 're', 'sys'}
    assert canonical_hash(POLICY) == scoring.POLICY_SHA256
    assert scoring.finite(10**1000) is False
