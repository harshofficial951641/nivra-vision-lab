"""Fixed offline V2 community-head adaptation; parent schedules actual runs."""
import argparse
import json
from pathlib import Path
import sys

from nivra.community_x3d_experiments import Config, ROOT, run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--data-root', type=Path, default=ROOT / 'training/data/vid')
    parser.add_argument('--baseline-checkpoint', type=Path, default=ROOT / 'models/x3d_rwf2000.pt')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--device', choices=('cpu', 'cuda'), required=True)
    parser.add_argument('--max-epochs', type=int, choices=(3, 10, 20), required=True)
    parser.add_argument('--input-cache-mib', type=int, default=1536)
    parser.add_argument('--yield-to-demo', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--provenance-file', type=Path, action='append', default=[])
    args = parser.parse_args(argv)
    try:
        config = Config(max_epochs=args.max_epochs, device=args.device, input_cache_mib=args.input_cache_mib,
                        yield_to_demo=args.yield_to_demo)
        report = run(args.manifest, args.data_root, args.baseline_checkpoint, args.output_dir,
                     manifest_sha256=args.manifest_sha256, config=config,
                     provenance_files=[ROOT / 'research/github/TRAINING-AND-TESTING-PLAN.md',
                                       ROOT / 'research/github/EXPANDED-TRAINING-PLAN.md', *args.provenance_file])
        print(json.dumps(report), flush=True)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
