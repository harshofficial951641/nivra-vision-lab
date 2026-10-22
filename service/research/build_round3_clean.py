"""Assemble explicit provisional training reviews; never run a model or fit.

Run from repository root. Existing inputs and outputs are never overwritten.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))
from build_training_manifest import build, write_manifest

ROOT = SERVICE / 'training'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(relative, expected=None):
    path = ROOT / relative
    if expected and digest(path) != expected:
        raise ValueError('Changed frozen input: ' + relative)
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    old = read('vid-round2-v1.json', '1a0f6fc44704b73f32c5e0ab82b607fff2a702a848186b4403ddf357a0026a84')
    audit = read('reviews/positive-coverage-audit-v1.json', 'feeac4977b68c6d9a04ac4d0e28c3ee63f534ca319d966be72d4d69d62a23d98')
    legacy = read('reviews/normal-legacy-rereview-v1.json', 'c5a3f36cdfd2403d98485cf39f352e41915db02ee76e9b7cc121c64a7d52334d')
    pos3 = read('reviews/positive-round3-a.json', '5d32fea40519697ff7ee2868fd2c4b606bf5c0ab60f25602c665736a9cf83e09')
    neg3 = read('reviews/negative-round3-a.json', '1b03a33620201b2b33f9562f5eece412c2bddba6fc2f94ac202a25037df71b0e')
    prior_paths = ['positive-review.json', 'reviews/positive-round2-a.json',
                   'reviews/positive-round2-b.json', 'reviews/positive-round2-c.json']
    prior = {}
    for name in prior_paths:
        for i, row in enumerate(read(name)['recordings']):
            if row['id'] in prior:
                raise ValueError('Duplicate positive review ID')
            prior[row['id']] = (row, name, i)
    decisions = {r['id']: r for r in audit['recordings']}
    if len(decisions) != 12:
        raise ValueError('Expected twelve audited sources')
    quarantine = sorted(k for k, v in decisions.items() if v['auditDecision'] != 'supported')
    if quarantine != sorted(['v_c_b_117', 'v_c_b_21', 'v_c_b_58', 'v_c_b_71', 'v_c_b_48']):
        raise ValueError('Unexpected audit disagreements')
    rows, selections, inputs = [], [], set(prior_paths)

    def retain(row, source, index, override=None):
        item = copy.deepcopy(row)
        if override is not None:
            item['events'] = copy.deepcopy(override)
        normalized_evidence = []
        for name in item.get('evidenceFiles', []):
            path = (ROOT / name).resolve()
            if name.startswith('service/training/'):
                path = (SERVICE.parent / name).resolve()
            # This legacy review explicitly uses the VID directory as its base.
            if source == 'reviews/positive-round2-b.json' and name.startswith('review-round2-b/'):
                path = (ROOT / 'data/vid' / name).resolve()
            if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
                raise ValueError('Missing/confined evidence: ' + name)
            normalized_evidence.append(path.relative_to(ROOT.resolve()).as_posix())
        item['evidenceFiles'] = normalized_evidence
        inputs.add(source)
        selections.append({'id': item['id'], 'reviewFile': source,
                           'jsonPointer': f'/recordings/{index}',
                           'eventsOverriddenByAudit': override is not None})
        rows.append(item)

    old_positive_ids = {r['id'] for r in old['recordings'] if r['label'] == 1}
    old_rows = {r['id']: r for r in old['recordings']}
    if len(old_positive_ids) != 39 or not set(decisions).issubset(old_positive_ids):
        raise ValueError('Unexpected old positive cohort')
    for recording_id in sorted(old_positive_ids - set(quarantine)):
        row, name, index = prior[recording_id]
        if row['decision'] != 'train-positive':
            raise ValueError('Prior positive selection mismatch')
        override = None
        if recording_id in decisions:
            checked = decisions[recording_id]
            if old_rows[recording_id]['sha256'] != checked['sha256']:
                raise ValueError('Audit media mismatch')
            override = checked['proposedEvents']
            row = dict(row, evidenceFiles=list(dict.fromkeys(
                row.get('evidenceFiles', []) + checked['evidenceFiles'])))
        retain(row, name, index, override)

    normal_sources = [('reviews/normal-legacy-rereview-v1.json', legacy),
                      ('reviews/negative-round2-existing.json', read('reviews/negative-round2-existing.json')),
                      ('reviews/negative-round3-a.json', neg3)]
    for name, review in [*normal_sources, ('reviews/positive-round3-a.json', pos3)]:
        for index, row in enumerate(review['recordings']):
            if row['decision'] in ('train-normal', 'train-positive'):
                retain(row, name, index)
    inputs.update(['vid-round2-v1.json', 'reviews/positive-coverage-audit-v1.json'])
    normal_old = {r['id'] for r in old['recordings'] if r['label'] == 0}
    selected_normal = {r['id'] for r in rows if r['decision'] == 'train-normal'}
    if len(normal_old) != 57 or not normal_old.issubset(selected_normal):
        raise ValueError('Old normal canonical replacement mismatch')
    if len(rows) != 127 or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Canonical selection must contain 127 unique sources')
    canonical = {
        'schemaVersion': 1,
        'reviewMethod': 'Parent canonical selection of pinned provisional assistant reviews. Five audit disagreements quarantined; seven audited positives use proposed audit intervals only. Forty legacy normals are replaced by explicit every-frame-reviewed 0-4 second spans. Seventeen prior dense normals and round3 accepted reviews are retained without extrapolation.',
        'limitations': [
            'All labels remain provisional assistant still-image judgments, not human ground truth or full-motion review.',
            'Unaudited old positive intervals retain sampled-review uncertainty. Audited events do not validate original boundaries outside inspected spans.',
            'Unknown tails remain unknown. Positive window eligibility requires at least half annotated coverage; contextual frames outside events are not normal labels.',
            'All VID is one unresolved actor/session training cohort. No calibration, holdout, night/IR or 50-100-person accuracy evidence is supplied.',
            'Original source reviews preserve detailed methods, rights, notes and limitations; their hashes and selected JSON pointers are recorded here.'],
        'inputHashes': {name: digest(ROOT / name) for name in sorted(inputs)},
        'quarantinedRecordingIds': quarantine,
        'selections': selections, 'recordings': rows}
    target = ROOT / 'reviews/canonical-round3-v1.json'
    manifest_path = ROOT / 'vid-round3-clean-v1.json'
    receipt_path = SERVICE / 'research/runs/round3-clean-admission-v1.json'
    if any(p.exists() for p in (target, manifest_path, receipt_path)):
        raise FileExistsError('Clean round3 outputs already exist')
    inventory_path = ROOT / 'data/vid/inventory-round2.json'
    inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    manifest = build(inventory, [canonical])
    # Media and schema validated before publishing the canonical selection.
    validated, windows = write_manifest(manifest, manifest_path, ROOT / 'data/vid')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(canonical, stream, indent=2, ensure_ascii=False); stream.write('\n')
    receipt = {'manifestSha256': digest(manifest_path), 'canonicalReviewSha256': digest(target),
               'inventorySha256': digest(inventory_path), 'assemblyScriptSha256': digest(Path(__file__)),
               'recordings': len(validated.recordings), 'trainWindows': len(windows),
               'positiveWindows': sum(w.label for w in windows),
               'normalWindows': sum(w.label == 0 for w in windows),
               'quarantinedRecordingIds': quarantine,
               'auditedPositiveOverrides': sorted(set(decisions) - set(quarantine)),
               'calibrationWindows': 0, 'holdoutWindows': 0,
               'labelStatus': 'provisional-assistant-review', 'modelRuns': 0,
               'windowCountsByRecording': {r.id: sum(w.recording_id == r.id for w in windows)
                                            for r in validated.recordings}}
    with receipt_path.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2); stream.write('\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'windowCountsByRecording'}))


if __name__ == '__main__':
    main()
