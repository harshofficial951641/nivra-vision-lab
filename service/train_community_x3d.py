"""Predeclared three-epoch research-only community X3D Linear-head adaptation."""
import argparse
import json
from pathlib import Path
import sys

from nivra.community_x3d_training import Config, ROOT, run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'training/vid-round2-v1.json')
    parser.add_argument('--data-root', type=Path, default=ROOT / 'training/data/vid')
    parser.add_argument('--baseline-checkpoint', type=Path, default=ROOT / 'models/x3d_rwf2000.pt')
    parser.add_argument('--output-dir', type=Path, required=True, help='New run directory only')
    parser.add_argument('--device', choices=('cpu', 'cuda'), required=True)
    parser.add_argument('--input-cache-mib', type=int, default=1536)
    parser.add_argument('--yield-to-demo', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--provenance-file', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    try:
        config = Config(device=args.device, input_cache_mib=args.input_cache_mib, yield_to_demo=args.yield_to_demo)
        evidence = [ROOT / 'training/ROUND2-RESULTS.md', ROOT / 'research/github/PAIRED-RESULTS.md',
                    ROOT / 'research/github/3d-cnn-repos.md', *args.provenance_file]
        report = run(args.manifest, args.data_root, args.baseline_checkpoint, args.output_dir,
                     config=config, provenance_files=evidence)
        print(json.dumps({'status': report['status'], 'output': str(args.output_dir),
                          'candidateSha256': report['candidateSha256'], 'gpu': report['gpu'],
                          'training': {key: report['training'][key] for key in
                                       ('optimizerSteps', 'epochWeightedNLL', 'nonHeadUnchanged')},
                          'liveModelChanged': False}), flush=True)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
