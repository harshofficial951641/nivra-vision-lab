"""Pure JSON postprocessing of frozen provisional online diagnostic annotations.

No media access, decoder, model, Torch, benchmark import or threshold fitting.
Reserved reports are for the parent's one final audit, never helper exploration.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

POLICY_SHA256 = 'c974d6f61ab429335cd6a1d917687c6671370a6a0c0edc54633e5a869cd74ac4'
ROLE_PREFIX = 'nivra-online-wave1-v1:'
IDENTITY_FIELDS = ('clipId', 'sourceGroup', 'mediaSha256', 'crop', 'windowStartMs', 'timestampMs',
                   'sourceDimensionsWH', 'viewDimensionsWH', 'cropPixelsLTRB', 'sourceFramePTS', 'selectedFramePTS')
SCORE_KINDS = {'x3d': 'backbone-softmax', 'mc3': 'softmax-logits', 'videomae': 'softmax-on-logits',
               'community': 'retained-backbone-softmax', 'community-v2': 'retained-backbone-softmax'}
LIMIT_CEILINGS = {'max_source_pixels': 3840 * 2160, 'max_dimension': 7680,
                  'max_buffer_pixels': 200_000_000, 'max_windows': 10_000,
                  'max_decode_frames': 1_000_000, 'max_clips': 1000}
COUNT_FIELDS = ('predictionWindows', 'positiveProxyWindows', 'positiveProxyFlagged', 'positiveProxyMissed',
                'normalWindows', 'normalFlagged', 'normalUnflagged', 'unknownWindows', 'unknownFlagged',
                'noPredictionRecordings', 'proxyEpisodeObservations', 'proxyEpisodesWithCompatibleWindow',
                'matchedProxyEpisodeObservations', 'missedProxyEpisodesWithCompatibleWindow',
                'proxyEpisodesWithoutCompatibleWindow', 'duplicateCompatibleFlags',
                'positiveFlagsWithoutSingleEpisodeCompatibility')


def finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def content_hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Expected explicit lowercase SHA-256')
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def load_json(data):
    def invalid(value):
        raise ValueError('Nonfinite JSON value: ' + value)
    def real(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('Nonfinite JSON number')
        return parsed
    return json.loads(data, object_pairs_hook=_object, parse_constant=invalid, parse_float=real)


def read_pinned(path, expected_sha256, max_bytes):
    digest(expected_sha256)
    if Path(path).stat().st_size > max_bytes:
        raise ValueError('JSON input exceeds bounded size')
    data = Path(path).read_bytes()
    if len(data) > max_bytes or sha256(data) != expected_sha256:
        raise ValueError('Input SHA-256/size mismatch: ' + str(path))
    return data


def role_for_group(group):
    return 'dev' if hashlib.sha256((ROLE_PREFIX + group).encode()).digest()[0] < 128 else 'reserved'


def interval_union(intervals):
    """Half-open intervals; touching same-label annotations form one component."""
    result = []
    for start, end in sorted(intervals):
        if not finite(start) or not finite(end) or not 0 <= start < end:
            raise ValueError('Invalid explicit annotation interval')
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def overlap(intervals, start, end):
    return sum(max(0, min(end, right) - max(start, left)) for left, right in intervals)


def annotations(events, duration):
    if not isinstance(events, list):
        raise ValueError('Explicit events array required; no implicit normal labels')
    groups = {0: [], 1: []}
    for event in events:
        if (not isinstance(event, dict) or type(event.get('targetLabel')) is not int or
                event['targetLabel'] not in (0, 1) or not finite(event.get('startMs')) or
                not finite(event.get('endMs')) or not 0 <= event['startMs'] < event['endMs'] <= duration):
            raise ValueError('Invalid explicit targetLabel interval')
        if 'startsInProgress' in event and type(event['startsInProgress']) is not bool:
            raise ValueError('startsInProgress must be boolean')
        groups[event['targetLabel']].append((event['startMs'], event['endMs']))
    normal, positive = interval_union(groups[0]), interval_union(groups[1])
    left = right = 0
    while left < len(normal) and right < len(positive):
        if max(normal[left][0], positive[right][0]) < min(normal[left][1], positive[right][1]):
            raise ValueError('Conflicting normal/positive annotations')
        if normal[left][1] <= positive[right][1]:
            left += 1
        else:
            right += 1
    return normal, positive


def classify_window(normal, positive, start, end):
    if not finite(start) or not finite(end) or start >= end:
        raise ValueError('Invalid actual window span')
    if any(left <= start and right >= end for left, right in normal):
        return 'normal'
    if overlap(positive, start, end) >= (end - start) / 2:
        return 'positive-proxy'
    return 'unknown'


def validate_corpus(corpus, role):
    if role not in ('dev', 'reserved'):
        raise ValueError('One explicit dev/reserved role required')
    if not isinstance(corpus, list) or not 1 <= len(corpus) <= 1000:
        raise ValueError('Nonempty bounded runner-compatible corpus list required')
    ids, media_groups, prepared = set(), {}, {}
    for record in corpus:
        if not isinstance(record, dict):
            raise ValueError('Corpus recording must be an object')
        for name in ('id', 'sourceGroup', 'path', 'license'):
            if not isinstance(record.get(name), str) or not record[name].strip():
                raise ValueError('Missing corpus field: ' + name)
        if record['id'] in ids:
            raise ValueError('Duplicate recording ID')
        ids.add(record['id'])
        if record.get('role') != role or role_for_group(record['sourceGroup']) != role:
            raise ValueError('Cross-role corpus or predeclared sourceGroup role mismatch')
        if record.get('originalRole') != {'dev': 'development', 'reserved': 'reserved-audit'}[role]:
            raise ValueError('Original predeclared role mismatch')
        if record.get('annotationStatus') != 'reviewed' or record.get('split') not in ('diagnostic', 'calibration', 'holdout'):
            raise ValueError('Reviewed diagnostic corpus contract required')
        media_sha = digest(record.get('sha256'))
        if media_sha in media_groups and media_groups[media_sha] != record['sourceGroup']:
            raise ValueError('Identical media assigned to different source groups')
        media_groups[media_sha] = record['sourceGroup']
        duration = record.get('durationMs')
        if not finite(duration) or duration <= 0:
            raise ValueError('Invalid recording duration')
        crop = record.get('crop')
        if crop is not None and (not isinstance(crop, list) or len(crop) != 4 or
                not all(finite(value) for value in crop) or not 0 <= crop[0] < crop[2] <= 1 or
                not 0 <= crop[1] < crop[3] <= 1):
            raise ValueError('Invalid corpus crop')
        prepared[record['id']] = annotations(record.get('events'), duration)
    return prepared


def dimensions(value, limits):
    if (not isinstance(value, list) or len(value) != 2 or
            any(type(item) is not int or item <= 0 for item in value) or
            max(value) > limits['max_dimension'] or value[0] * value[1] > limits['max_source_pixels']):
        raise ValueError('Invalid observed dimensions')
    return value


def validate_window(row, record, clip, previous_end, limits, candidate):
    if not isinstance(row, dict) or any(name not in row for name in IDENTITY_FIELDS):
        raise ValueError('Missing actual window identity fields')
    if (row['clipId'] != record['id'] or row['sourceGroup'] != record['sourceGroup'] or
            row['mediaSha256'] != record['sha256'] or row['crop'] != record.get('crop')):
        raise ValueError('Window source group/media/crop mismatch')
    if row['crop'] is not None and (not isinstance(row['crop'], list) or not all(finite(value) for value in row['crop'])):
        raise ValueError('Invalid window crop identity')
    pts = row['sourceFramePTS']
    if (not isinstance(pts, list) or not 8 <= len(pts) <= 48 or
            any(not finite(value) or value < 0 for value in pts) or
            any(not 100 <= right - left <= 1200 for left, right in zip(pts, pts[1:])) or
            not 3800 <= pts[-1] - pts[0] <= 4000 or not finite(row['windowStartMs']) or
            not finite(row['timestampMs']) or row['windowStartMs'] != pts[0] or
            row['timestampMs'] != pts[-1] or pts[-1] > record['durationMs'] or pts[-1] - previous_end < 400):
        raise ValueError('Actual window violates strict paired PTS/span policy')
    selected = [int(index * ((len(pts) - 1) / 15)) for index in range(15)] + [len(pts) - 1]
    actual_indices = row.get('selectedFrameIndices')
    if (not isinstance(actual_indices, list) or any(type(value) is not int for value in actual_indices) or
            actual_indices != selected or not isinstance(row['selectedFramePTS'], list) or
            not all(finite(value) for value in row['selectedFramePTS']) or
            row['selectedFramePTS'] != [pts[index] for index in selected] or
            type(row.get('repeatedSelectedIndices')) is not int or
            row['repeatedSelectedIndices'] != 16 - len(set(selected))):
        raise ValueError('Selected frame PTS/indices mismatch')
    width, height = dimensions(row['sourceDimensionsWH'], limits)
    view = dimensions(row['viewDimensionsWH'], limits)
    crop = record.get('crop') or [0., 0., 1., 1.]
    expected_crop = [round(crop[0] * width), round(crop[1] * height),
                     round(crop[2] * width), round(crop[3] * height)]
    pixels = row['cropPixelsLTRB']
    if (not isinstance(pixels, list) or any(type(value) is not int for value in pixels) or pixels != expected_crop or
            len(pixels) != 4 or not 0 <= pixels[0] < pixels[2] <= width or
            not 0 <= pixels[1] < pixels[3] <= height or view != [pixels[2] - pixels[0], pixels[3] - pixels[1]] or
            len(pts) * view[0] * view[1] > limits['max_buffer_pixels']):
        raise ValueError('Actual window source/view/crop geometry mismatch')
    decoder = clip.get('decoder')
    if (not isinstance(decoder, dict) or row['sourceDimensionsWH'] not in decoder.get('sourceDimensions', []) or
            view not in decoder.get('viewDimensions', [])):
        raise ValueError('Window dimensions absent from observed decoder metadata')
    scores, index = row.get('classScores'), 0 if candidate == 'mc3' else 1
    if (not isinstance(scores, list) or len(scores) != 2 or
            not all(finite(value) and 0 <= value <= 1 for value in scores) or abs(sum(scores) - 1) > 1e-5 or
            not finite(row.get('fightScore')) or not 0 <= row['fightScore'] <= 1 or
            type(row.get('fightIndex')) is not int or row['fightIndex'] != index or
            abs(row['fightScore'] - scores[index]) > 1e-6 or row.get('scoreKind') != SCORE_KINDS[candidate] or
            type(row.get('review')) is not bool or row['review'] != (row['fightScore'] > .5) or
            not finite(row.get('inferenceMs')) or row['inferenceMs'] < 0):
        raise ValueError('Invalid retained score/class/strict-threshold contract')
    overlaps = [{**event, 'overlapMs': min(pts[-1], event['endMs']) - max(pts[0], event['startMs'])}
                for event in record['events'] if event['endMs'] > pts[0] and event['startMs'] < pts[-1]]
    if row.get('labelledEventOverlaps') != overlaps:
        raise ValueError('Raw annotation overlap context mismatch')
    return {name: row[name] for name in IDENTITY_FIELDS}


def counts():
    return dict.fromkeys(COUNT_FIELDS, 0)


def summarize(report, corpus, *, role):
    prepared = validate_corpus(corpus, role)
    if (not isinstance(report, dict) or report.get('schemaVersion') != 1 or report.get('complete') is not True or
            report.get('status') != 'complete-diagnostic-only' or report.get('candidate') not in SCORE_KINDS or
            report.get('thresholdFittedHere') is not False or report.get('liveModelChanged') is not False or
            report.get('policySha256') != POLICY_SHA256 or content_hash(report.get('policy')) != POLICY_SHA256):
        raise ValueError('Incomplete or incompatible raw benchmark report/policy')
    limits = report.get('limits')
    if (not isinstance(limits, dict) or any(type(limits.get(name)) is not int or
            not 0 < limits[name] <= ceiling for name, ceiling in LIMIT_CEILINGS.items())):
        raise ValueError('Missing/invalid raw benchmark limits')
    raw_clips = report.get('clips')
    if not isinstance(raw_clips, dict) or set(raw_clips) != set(prepared) or len(corpus) > limits['max_clips']:
        raise ValueError('Missing/extra benchmark recordings')
    identities, records, groups = [], {}, {}
    total = counts()
    for record in corpus:
        clip = raw_clips[record['id']]
        variant = record.get('qualityVariant')
        derivative = bool(record.get('crop') or record.get('derivative') or record.get('parentSha256') or
                          (isinstance(variant, dict) and variant.get('kind') not in (None, 'original-reference')))
        if (not isinstance(clip, dict) or clip.get('sourceGroup') != record['sourceGroup'] or
                clip.get('historicalSplit') != record['split'] or clip.get('crop') != record.get('crop') or
                clip.get('declaredDurationMs') != record['durationMs'] or not isinstance(clip.get('media'), dict) or
                clip['media'].get('sha256') != record['sha256'] or clip.get('qualityVariant') != variant or
                type(clip.get('derivative')) is not bool or clip['derivative'] != derivative):
            raise ValueError('Recording source group/media/corpus metadata mismatch')
        rows = clip.get('samples')
        if (not isinstance(rows, list) or type(clip.get('windows')) is not int or clip['windows'] != len(rows) or
                type(clip.get('reviewWindows')) is not int or len(rows) > limits['max_windows']):
            raise ValueError('Missing actual prediction windows or count mismatch')
        if len(identities) + len(rows) > limits['max_windows']:
            raise ValueError('Total actual prediction window budget exceeded')
        normal, positive = prepared[record['id']]
        tally, results = counts(), []
        episodes = [{'startMs': start, 'endMs': end, 'compatibleWindowIndices': [], 'matchedWindowIndex': None}
                    for start, end in positive]
        previous_end = -math.inf
        for index, row in enumerate(rows):
            identities.append(validate_window(row, record, clip, previous_end, limits, report['candidate']))
            start, end, flagged = row['windowStartMs'], row['timestampMs'], row['review']
            previous_end = end
            label = classify_window(normal, positive, start, end)
            tally['predictionWindows'] += 1
            matched = None
            compatible = []
            if label == 'normal':
                tally['normalWindows'] += 1
                tally['normalFlagged' if flagged else 'normalUnflagged'] += 1
            elif label == 'positive-proxy':
                tally['positiveProxyWindows'] += 1
                tally['positiveProxyFlagged' if flagged else 'positiveProxyMissed'] += 1
                compatible = [item for item, episode in enumerate(episodes)
                              if overlap([(episode['startMs'], episode['endMs'])], start, end) >= (end - start) / 2]
                for item in compatible:
                    episodes[item]['compatibleWindowIndices'].append(index)
                if flagged:
                    available = [item for item in compatible if episodes[item]['matchedWindowIndex'] is None]
                    if available:
                        matched = available[0]  # Chronological windows, earliest unmatched compatible episode.
                        episodes[matched]['matchedWindowIndex'] = index
                    elif compatible:
                        tally['duplicateCompatibleFlags'] += 1
                    else:
                        tally['positiveFlagsWithoutSingleEpisodeCompatibility'] += 1
            else:
                tally['unknownWindows'] += 1
                tally['unknownFlagged'] += int(flagged)
            results.append({'windowIndex': index, 'windowStartMs': start, 'timestampMs': end,
                            'actualSpanMs': end - start, 'eligibility': label, 'fightScore': row['fightScore'],
                            'classScores': row['classScores'], 'scoreKind': row['scoreKind'], 'fightIndex': row['fightIndex'],
                            'flagged': flagged, 'normalCoverageMs': overlap(normal, start, end),
                            'positiveProxyCoverageMs': overlap(positive, start, end),
                            'compatibleProxyEpisodeIndices': compatible, 'matchedProxyEpisodeIndex': matched})
        if clip['reviewWindows'] != sum(row['review'] for row in rows):
            raise ValueError('Raw strict flag count mismatch')
        tally['noPredictionRecordings'] = int(not rows)
        tally['proxyEpisodeObservations'] = len(episodes)
        tally['proxyEpisodesWithCompatibleWindow'] = sum(bool(episode['compatibleWindowIndices']) for episode in episodes)
        tally['matchedProxyEpisodeObservations'] = sum(episode['matchedWindowIndex'] is not None for episode in episodes)
        tally['missedProxyEpisodesWithCompatibleWindow'] = (tally['proxyEpisodesWithCompatibleWindow'] -
                                                           tally['matchedProxyEpisodeObservations'])
        tally['proxyEpisodesWithoutCompatibleWindow'] = len(episodes) - tally['proxyEpisodesWithCompatibleWindow']
        records[record['id']] = {'sourceGroup': record['sourceGroup'], 'role': role,
                                'originalRole': record['originalRole'], 'mediaSha256': record['sha256'],
                                'derivative': derivative, 'crop': record.get('crop'), 'qualityVariant': variant,
                                'counts': tally, 'windows': results, 'proxyEpisodeObservations': episodes}
        group = groups.setdefault(record['sourceGroup'], {'role': role, 'recordingIds': [], 'counts': counts()})
        group['recordingIds'].append(record['id'])
        for name in COUNT_FIELDS:
            group['counts'][name] += tally[name]
            total[name] += tally[name]
    if (type(report.get('windowCount')) is not int or not 0 < report['windowCount'] <= limits['max_windows'] or
            report['windowCount'] != len(identities) or report.get('pairedWindowSha256') != content_hash(identities)):
        raise ValueError('Missing windows or paired window identity checksum mismatch')
    return {'schemaVersion': 1, 'complete': True, 'status': 'provisional-online-diagnostic-summary',
            'role': role, 'candidate': report['candidate'], 'recordings': len(records), 'sourceGroups': len(groups),
            'policySha256': POLICY_SHA256, 'pairedWindowSha256': report['pairedWindowSha256'],
            'rawWindowPolicy': report['policy'], 'adaptationIdentity': report.get('adaptationIdentity'),
            'threshold': .5, 'comparison': 'fightScore > .5', 'counts': total,
            'byRecording': records, 'bySourceGroup': groups,
            'matchingPolicy': 'Chronological actual windows; positive union >= half actual span. One flag per '
                              'unmatched connected proxy interval with >= half-span overlap; no tolerance; '
                              'earliest compatible interval first; one credit per recording episode.',
            'latencyComputed': False, 'thresholdFittedHere': False,
            'annotationClock': 'Parent-admitted observed decoder milliseconds; no offset, rounding or rebasing applied here',
            'eligibilityPolicy': {'normal': 'entire actual observed span covered by explicit targetLabel0 union',
                                  'positiveProxyMinimumSpanFraction': .5,
                                  'otherWindows': 'unknown, excluded from eligible-label comparisons',
                                  'intervals': 'half-open; same-label overlaps/touches merged', 'epsilonMs': 0},
            'limitations': ['Labels are provisional assistant review, not human ground truth or intent.',
                            'Sports/contact proxies are not evidence of hostile physical fights.',
                            'Unknown windows are excluded from eligible label comparisons, never treated normal.',
                            'Overlapping windows, derivatives and recording episodes within groups are dependent.',
                            'Group episode sums are recording observations, not deduplicated real-world incidents.',
                            'No production accuracy, incident recall, false-alerts/hour or crowd/night claim.',
                            'No latency from annotation starts or startsInProgress; no three-second credit.',
                            'Reserved role is for parent final audit only; using it to tune makes it development.']}


def run(report_path, corpus_path, output_path, *, report_sha256, corpus_sha256, role):
    output = Path(output_path)
    if output.exists():
        raise FileExistsError(output)
    # Admit corpus role before opening prediction bytes, avoiding accidental cross-role reads.
    corpus_bytes = read_pinned(corpus_path, corpus_sha256, 16 * 1024**2)
    corpus = load_json(corpus_bytes)
    validate_corpus(corpus, role)
    report_bytes = read_pinned(report_path, report_sha256, 128 * 1024**2)
    report = load_json(report_bytes)
    if not isinstance(report, dict) or report.get('corpusSha256') != corpus_sha256:
        raise ValueError('Raw report does not match frozen corpus SHA-256')
    result = summarize(report, corpus, role=role)
    result.update({'rawReportSha256': report_sha256, 'corpusSha256': corpus_sha256,
                   'postprocessorSha256': sha256(Path(__file__).read_bytes())})
    if sha256(Path(report_path).read_bytes()) != report_sha256 or sha256(Path(corpus_path).read_bytes()) != corpus_sha256:
        raise ValueError('Inputs changed during postprocessing; no summary written')
    payload = json.dumps(result, indent=2, allow_nan=False) + '\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(payload)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--report-sha256', required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--corpus-sha256', required=True)
    parser.add_argument('--role', choices=('dev', 'reserved'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args.report, args.corpus, args.output, report_sha256=args.report_sha256,
                     corpus_sha256=args.corpus_sha256, role=args.role)
        print(json.dumps({'status': result['status'], 'role': result['role'], 'counts': result['counts']}))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
