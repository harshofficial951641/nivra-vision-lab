"""Fit an offline binary head on frozen official X3D-M features.

Requires an already downloaded, pinned official checkpoint and a reviewed local
manifest. CUDA requires --device cuda. No downloads, publishing or live changes.
"""
import argparse
import json
from pathlib import Path
import sys

from nivra.x3d_training import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--base-checkpoint', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='New directory; existing runs are never overwritten')
    parser.add_argument('--seed', type=int, default=17)
    parser.add_argument('--epochs', type=int, default=100)
    parser.add_argument('--learning-rate', type=float, default=.01)
    parser.add_argument('--class-weight', action='store_true', help='Compute weights from training labels only')
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu', help='Explicit compute device; CUDA never silently falls back')
    parser.add_argument('--cuda-memory-fraction', type=float, default=.4, help='Per-process CUDA allocator cap, fraction of GPU memory (default .4)')
    parser.add_argument('--yield-to-demo', action='store_true', help='Wait up to 60 seconds while the local public demo is busy; fail if its health cannot be verified')
    parser.add_argument('--max-windows-per-split', type=int, help='Bounded smoke run; records exact subset and marks partial evaluation')
    args = parser.parse_args()
    try:
        report = run(args.manifest, args.data_root, args.base_checkpoint, args.output_dir,
                     seed=args.seed, epochs=args.epochs, learning_rate=args.learning_rate,
                     class_weight=args.class_weight,
                     device=args.device, cuda_memory_fraction=args.cuda_memory_fraction,
                     yield_to_demo=args.yield_to_demo,
                     max_windows_per_split=args.max_windows_per_split)
        print(json.dumps({'status': report['status'], 'output': str(args.output_dir),
                          'device': report['device'], 'gpu': report['gpu'],
                          'threshold': report['threshold'], 'calibration': report['calibration'],
                          'metrics': {split: value['metrics'] for split, value in report['splits'].items()},
                          'liveModelChanged': False}), flush=True)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
