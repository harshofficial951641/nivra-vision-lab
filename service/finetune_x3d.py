"""Offline X3D-M adaptation or CPU diagnostics. Never changes the live model."""
import argparse
import json
from pathlib import Path
import sys

from nivra.x3d_finetune import FineTuneConfig, ROOT, diagnose, run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    train = commands.add_parser('train', help='Parent-coordinated offline training only')
    for name in ('manifest', 'data-root', 'base-checkpoint', 'output-dir'):
        train.add_argument('--' + name, type=Path, required=True)
    train.add_argument('--seed', type=int, default=17)
    train.add_argument('--epochs', type=int, default=5)
    train.add_argument('--head-only', action='store_true', help='Adapt projected pooling and classifier; freeze all residual stages')
    train.add_argument('--backbone-learning-rate', type=float, default=1e-5)
    train.add_argument('--head-learning-rate', type=float, default=1e-4)
    train.add_argument('--weight-decay', type=float, default=.01)
    train.add_argument('--accumulation-steps', type=int, default=8)
    train.add_argument('--no-class-weight', action='store_true')
    train.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    train.add_argument('--cuda-memory-fraction', type=float, default=.4)
    train.add_argument('--no-yield-to-demo', action='store_true', help='CPU only; CUDA must cooperate with the demo')
    train.add_argument('--max-train-windows', type=int, help='Deterministic smoke subset; never truncates evaluation splits')
    train.add_argument('--input-cache-mib', type=int, default=0, help='Bounded CPU RAM cache of decoded frames; zero disables it, max 4096 MiB')
    train.add_argument('--provenance-file', type=Path, action='append', help='Snapshot additional review evidence; repeatable. VID source, rights, and original three reviews are always included')
    diagnostic = commands.add_parser('diagnose', help='CPU-only existing-corpus diagnostics; no fitting')
    diagnostic.add_argument('--run-dir', type=Path, required=True)
    diagnostic.add_argument('--corpus', type=Path, default=ROOT / 'evaluation/corpus.json')
    diagnostic.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'diagnose':
            report = diagnose(args.run_dir, args.corpus, args.output)
            result = {'status': report['status'], 'output': str(args.output), 'liveModelChanged': False,
                      'clips': {key: {'windows': value['windows'], 'candidateReviewWindows': value['candidateReviewWindows']}
                                for key, value in report['clips'].items()}}
        else:
            config = FineTuneConfig(seed=args.seed, epochs=args.epochs, train_last_stage=not args.head_only,
                                    backbone_learning_rate=args.backbone_learning_rate,
                                    head_learning_rate=args.head_learning_rate, weight_decay=args.weight_decay,
                                    accumulation_steps=args.accumulation_steps, class_weight=not args.no_class_weight,
                                    device=args.device, cuda_memory_fraction=args.cuda_memory_fraction,
                                    yield_to_demo=not args.no_yield_to_demo,
                                    input_cache_mib=args.input_cache_mib)
            evidence = [ROOT / 'training' / name for name in
                        ('vid-source.json', 'DATA-RIGHTS.md', 'positive-review.json',
                         'negative-review.json', 'campus-negative-review.json')]
            evidence.extend(args.provenance_file or [])
            report = run(args.manifest, args.data_root, args.base_checkpoint, args.output_dir,
                         config=config, provenance_files=evidence, max_train_windows=args.max_train_windows)
            result = {'status': report['status'], 'output': str(args.output_dir), 'liveModelChanged': False,
                      'gpu': report['gpu'], 'calibration': report['calibration'],
                      'metrics': {split: value['metrics'] for split, value in report['splits'].items()}}
        print(json.dumps(result, allow_nan=False), flush=True)
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
