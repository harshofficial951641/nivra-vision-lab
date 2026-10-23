"""Build and hash the held-out pool before any classifier scores are computed."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import numpy as np

from .common import DEV_SHA, DOCS, MODEL, MODEL_SHA, PRIVATE, RUN, TRAINING, TRAIN_SHA, digest, read, sha, write
from .metrics import exposure_ms, union


class Components:
    def __init__(self):
        self.parents = {}

    def find(self, node):
        if node not in self.parents:
            self.parents[node] = node
        if self.parents[node] != node:
            self.parents[node] = self.find(self.parents[node])
        return self.parents[node]

    def connect(self, nodes):
        roots = [self.find(n) for n in nodes]
        for root in roots[1:]:
            self.parents[root] = roots[0]


def intersect(left, right):
    spans = []
    for a in left:
        for b in right:
            start, end = max(a['startMs'], b['startMs']), min(a['endMs'], b['endMs'])
            if end > start:
                spans.append(dict(startMs=start, endMs=end))
    return union(spans)


def partition(records):
    """Label-only random search for balanced whole groups; never reads scores."""
    contexts = sorted({r['context'] for r in records})
    groups = sorted({r['group'] for r in records})
    matrix = []
    for group in groups:
        rows = [r for r in records if r['group'] == group]
        vector = [len(rows), sum(len(r['events']) for r in rows), sum(exposure_ms(r['normalIntervals'], 4000, r['durationMs']) for r in rows)]
        for context in contexts:
            subset = [r for r in rows if r['context'] == context]
            vector.extend([sum(len(r['events']) for r in subset), sum(exposure_ms(r['normalIntervals'], 4000, r['durationMs']) for r in subset)])
        matrix.append(vector)
    matrix = np.asarray(matrix, dtype=float)
    target = matrix.sum(axis=0) / 2
    scale = np.maximum(target, [1, 1, 1000] + [v for _ in contexts for v in [1, 1000]])
    rng = np.random.default_rng(20261023)
    best = None
    for _ in range(8192):
        calibration = rng.permutation(len(groups))[:len(groups) // 2]
        error = float(np.square((matrix[calibration].sum(axis=0) - target) / scale).sum())
        if best is None or error < best[0]:
            best = (error, calibration)
    selected = {groups[i] for i in best[1]}
    for row in records:
        row['evaluationSplit'] = 'calibration' if row['group'] in selected else 'test'
    return dict(seed=20261023, trials=8192, objective='sum squared relative imbalance: recordings, events, actionable normal ms, per-context events and actionable normal ms', objectiveValue=best[0])


def describe(records):
    return dict(recordings=len(records), groups=len({r['group'] for r in records}),
                eventCount=sum(len(r['events']) for r in records),
                positiveRecordings=sum(bool(r['events']) for r in records),
                positiveGroups=len({r['group'] for r in records if r['events']}),
                normalGroups=len({r['group'] for r in records if r['normalIntervals']}),
                totalExplicitNormalHours=sum(exposure_ms(r['normalIntervals']) for r in records) / 3600000,
                actionableNormalHours=sum(exposure_ms(r['normalIntervals'], 4000, r['durationMs']) for r in records) / 3600000,
                sourceCounts=dict(Counter(r['poolSource'] for r in records)),
                contexts={c: dict(recordings=sum(r['context'] == c for r in records),
                                  events=sum(len(r['events']) for r in records if r['context'] == c),
                                  normalHours=sum(exposure_ms(r['normalIntervals'], 4000, r['durationMs']) for r in records if r['context'] == c) / 3600000)
                          for c in sorted({r['context'] for r in records})})


def main():
    destination = PRIVATE / 'frozen/split.json'
    if destination.exists():
        raise FileExistsError('freeze already exists; do not overwrite a scored test split')
    train_path, dev_path = RUN / 'inputs/vid-v4-train.json', RUN / 'inputs/vid-v4-dev.json'
    assert sha(train_path) == TRAIN_SHA and sha(dev_path) == DEV_SHA
    assert sha(MODEL) == MODEL_SHA
    train, dev = read(train_path)['recordings'], read(dev_path)['recordings']
    split_path = TRAINING / 'manifests/vid-v4-splits.json'
    split_doc = read(split_path)
    grouping_path = TRAINING / 'data/vid-v4-groups.json'
    assert sha(grouping_path) == split_doc['groupMethodReportSha256']
    current = {r['id']: r for r in split_doc['videos']}
    sources = [train_path, dev_path, split_path, grouping_path, RUN / 'source/probe.py', RUN / 'source/export_probe.py', RUN / 'source/movinet_export.py', RUN / 'source/movinet_benchmark.py', RUN / 'movinet/export/report.json']
    components = Components()
    for row in list(current.values()) + train + dev:
        components.connect(['id:' + row['id'], 'sha:' + row['sha256'], 'group:' + row['group']])
    train_components = {components.find('id:' + r['id']) for r in train}
    names = defaultdict(set)
    for row in list(current.values()) + train + dev:
        names[components.find('id:' + row['id'])].add(row['group'])
    group_name = {k: min(v) for k, v in names.items()}
    excluded = Counter()
    pool = {}

    def admit(row, source):
        row = dict(row)
        key = components.find('id:' + row['id'])
        if key in train_components:
            excluded[source + ':train_component'] += 1
            return
        if row['sha256'] in pool:
            excluded[source + ':duplicate_sha'] += 1
            return
        if not row['events'] and not row['normalIntervals']:
            excluded[source + ':no_explicit_labels'] += 1
            return
        if not __import__('pathlib').Path(row['path']).exists():
            candidate = current.get(row['id'])
            if candidate and candidate['sha256'] == row['sha256']:
                row['path'] = candidate['path']
        assert sha(row['path']) == row['sha256'], ('media changed', row['id'])
        row['normalIntervals'] = union(row['normalIntervals'])
        for span in row['events'] + row['normalIntervals']:
            assert 0 <= span['startMs'] < span['endMs'] <= row['durationMs'] + .01, row['id']
        for event in row['events']:
            assert not any(max(event['startMs'], n['startMs']) < min(event['endMs'], n['endMs']) for n in row['normalIntervals']), row['id']
        row['group'] = group_name[key]
        row['poolSource'] = source
        # Private freeze intentionally retains interval labels, not review text or frames.
        pool[row['sha256']] = {k: row[k] for k in ['id', 'path', 'sha256', 'durationMs', 'group', 'context', 'events', 'normalIntervals', 'poolSource']}

    for row in dev:
        admit(row, 'round1-dev')
    inventories = []
    for archive in ['nv_b_04', 'nv_b_05', 'nv_b_07']:
        path = PRIVATE.parent / 'data/vid/inventories' / (archive + '.json')
        sources.append(path)
        inventories.extend(read(path))
    inventory = {r['id']: r for r in inventories}
    reviews = defaultdict(list)
    for path in sorted((TRAINING / 'reviews').glob('shard-*/labels-new.json')):
        sources.append(path)
        for row in read(path):
            if row['id'] in inventory:
                reviews[row['id']].append(row)
    for rid, annotations in sorted(reviews.items()):
        inv, base = inventory[rid], current[rid]
        assert base['sha256'] == inv['sha256']
        if any(r.get('events') or r.get('annotationStatus') != 'reviewed' for r in annotations):
            excluded['new-normal:not_unanimously_normal_review'] += 1
            continue
        normal = annotations[0].get('normalIntervals', [])
        for annotation in annotations:
            assert annotation['sha256'] == inv['sha256']
            normal = intersect(normal, annotation.get('normalIntervals', []))
        contexts = {r['sceneContext'] for r in annotations if r.get('sceneContext')}
        row = dict(base, events=[], normalIntervals=normal, context=next(iter(contexts)) if len(contexts) == 1 else base['context'])
        admit(row, 'post-round1-normal')
    records = sorted(pool.values(), key=lambda r: r['id'])
    split_method = partition(records)
    cal = [r for r in records if r['evaluationSplit'] == 'calibration']
    test = [r for r in records if r['evaluationSplit'] == 'test']
    assert not {r['group'] for r in cal} & {r['group'] for r in test}
    assert not {r['sha256'] for r in cal} & {r['sha256'] for r in test}
    assert not {r['sha256'] for r in records} & {r['sha256'] for r in train}
    grid = dict(qualifying=[.1, .2, .3, .4, .5, .6, .7, .8, .85, .9, .95, .975, .99, .995, .999, .9999, 1.],
                strong=[.7, .9, .95, .99, .999, 1.], confirmation=[1, 2, 3], cooldownMs=8000, mergeGapMs=2000)
    result = dict(schemaVersion=1, frozenAtUtc=datetime.now(timezone.utc).isoformat(), records=records,
                  sources={str(p): sha(p) for p in sources}, modelSha256=MODEL_SHA,
                  trainingManifestSha256=TRAIN_SHA, round1DevManifestSha256=DEV_SHA,
                  splitMethod=split_method, exclusions=dict(excluded), policyGrid=grid,
                  calibrationSelection='maximize event recall subject to max(group-bootstrap upper95, exact Poisson upper97.5) <=2/h if any nonzero-recall policy qualifies; otherwise point estimate <=2/h. Ties: fewer false alerts, lower median delay, stricter thresholds, more confirmations.',
                  summary={s: describe(rows) for s, rows in [('calibration', cal), ('test', test)]})
    write(destination, result)
    split_sha = sha(destination)
    destination.with_suffix('.sha256').write_text(split_sha + '\n')
    aggregate = {k: v for k, v in result.items() if k not in ['records', 'sources']}
    aggregate.update(splitSha256=split_sha, sourceInputSha256s=list(result['sources'].values()), mediaSha256Verified=len(records), trainLeakageByIdHashOrGroup=0)
    write(DOCS / 'split-summary.json', aggregate)
    print(json.dumps(aggregate, indent=2))


if __name__ == '__main__':
    main()
