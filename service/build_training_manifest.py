"""Build the train-only VID pilot from explicit provisional visual-review decisions.

The unresolved VID recording/session cohort is kept entirely in training. This
command cannot generate a calibration or holdout split from these reviews.
"""
import argparse
import json
import math
from pathlib import Path
import tempfile

from nivra.training_data import generate_windows, load_manifest

ROOT = Path(__file__).resolve().parent / 'training'


def build(inventory, reviews):
    indexed = {row['id']: row for row in inventory}
    if len(indexed) != len(inventory):
        raise ValueError('Duplicate inventory recording id')
    recordings = []
    seen = set()
    for review in reviews:
        if not review.get('reviewMethod') or not review.get('limitations'):
            raise ValueError('Review method and limitations must be explicit')
        for item in review['recordings']:
            recording_id = item['id']
            if recording_id in seen:
                raise ValueError(f'Duplicate review for {recording_id}')
            seen.add(recording_id)
            if recording_id not in indexed:
                raise ValueError(f'Unknown review recording id: {recording_id}')
            row = indexed[recording_id]
            for key, expected in (('sha256', row['sha256']), ('sourcePath', row['path']),
                                  ('sourceArchive', row.get('archive')), ('archive', row.get('archive'))):
                if key in item and item[key] != expected:
                    raise ValueError(f'{recording_id}: review {key} does not match inventory')
            if 'durationSeconds' in item and (type(item['durationSeconds']) not in (int, float)
                    or not math.isfinite(item['durationSeconds'])
                    or abs(item['durationSeconds'] - row['durationSeconds']) > 1e-6):
                raise ValueError(f'{recording_id}: review duration does not match inventory')
            decision = item['decision']
            if decision in ('ambiguous', 'exclude'):
                continue
            if decision not in ('train-normal', 'train-positive'):
                raise ValueError('Unknown review decision')
            label = int(decision == 'train-positive')
            if 'events' not in item:
                raise ValueError(f'{recording_id}: accepted {decision} requires explicit reviewed intervals; '
                                 'unannotated time cannot be filled from recording duration')
            events = item['events']
            recordings.append({
                'id': recording_id, 'sourceId': 'vid-v2',
                'recordingGroup': 'vid-v2-unresolved-session-cohort',
                'path': row['path'], 'sha256': row['sha256'],
                'durationSeconds': row['durationSeconds'], 'split': 'train',
                'reviewStatus': 'reviewed', 'domain': 'staged-rgb:' + item['sceneGroup'],
                'label': label, 'events': events,
            })
    return {'schemaVersion': 1, 'sources': [{
        'id': 'vid-v2',
        'url': 'https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/N4LNZD&version=2.0',
        'license': 'CC0-1.0', 'trainingAllowed': True,
        'evidence': [
            'https://dataverse.harvard.edu/api/datasets/:persistentId/versions/2.0?persistentId=doi:10.7910/DVN/N4LNZD',
            'service/training/vid-source.json: explicit deposit copyright permission; consent author-reported; not complete non-copyright clearance',
        ],
    }], 'recordings': recordings}


def write_manifest(manifest, output, data_root):
    """Validate a private temporary copy before creating the final artifact."""
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    text = json.dumps(manifest, indent=2) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.json',
                                         prefix='nivra-manifest-', dir=output.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        validated = load_manifest(temporary, data_root, verify_files=True)
        windows = generate_windows(validated, 'train')
        with output.open('x', encoding='utf-8') as stream:
            stream.write(text)
        return validated, windows
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, default=ROOT / 'data' / 'vid')
    parser.add_argument('--inventory', type=Path, action='append',
                        help='Inventory JSON path; repeat to merge archives without changing the original inventory')
    parser.add_argument('--review', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inventory = []
    for path in args.inventory or [args.data_root / 'inventory.json']:
        inventory.extend(json.loads(path.read_text(encoding='utf-8')))
    reviews = [json.loads(path.read_text(encoding='utf-8')) for path in args.review]
    manifest = build(inventory, reviews)
    validated, windows = write_manifest(manifest, args.output, args.data_root)
    print(json.dumps({'recordings': len(validated.recordings), 'trainWindows': len(windows),
                      'positiveWindows': sum(window.label for window in windows),
                      'calibrationWindows': 0, 'holdoutWindows': 0}))


if __name__ == '__main__':
    main()
