"""Parent-only real CUDA zero-step forward check; no optimizer or fitting."""
import json
from pathlib import Path
import sys

SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))


def main():
    import cv2
    import numpy as np
    import torch
    import benchmark_cctv_candidates as bench
    from nivra import community_x3d_experiments as experiment
    from nivra import community_x3d_training as base

    output = SERVICE / 'research/runs/round3-v2-zero-step-parity-v1.json'
    if output.exists():
        raise FileExistsError(output)
    manifest_sha = '68cf0c4048dcc9d4d10e5553bf5bcf9be6cd6ab36bd7aeaff23208f2b55e0970'
    experiment.validate_training_manifest(SERVICE / 'training/vid-round3-clean-v1.json',
                                         SERVICE / 'training/data/vid', manifest_sha)
    corpus = SERVICE / 'evaluation/corpus.json'
    records, corpus_sha, _, asset = bench.validate_inputs('x3d', corpus, None, bench.Limits())
    if corpus_sha != '33d04d15bc4a6911face456fff7488320906505cc344f863042e4cae304bfb34':
        raise ValueError('Development corpus changed')
    guard = base.DemoYieldGuard()
    guard()
    device = base.training_device(experiment.Config(max_epochs=20, device='cuda'))
    base.seed_everything(17, 'cuda')
    cv2.setNumThreads(1)
    control = bench.ControlCandidate('x3d', asset, device='cuda')
    guard()
    candidate = base.baseline_model(Path(asset['path'])).to(device)
    base.enable_head_only(candidate)
    frozen = base.frozen_hashes(candidate)
    rows = []
    for name in ('boxing', 'grappling', 'kick'):
        clip = next(row for row in records if row['id'] == name)
        reader = bench.windows(clip, corpus)
        try:
            window = next(reader)
            frames = [window.frames[i] for i in np.linspace(0, len(window.frames) - 1, 16).astype(int)]
            guard()
            expected = control.predict(frames)['classScores']
            with torch.no_grad():
                actual = base.probabilities(candidate, base.preprocess_frames(frames).to(device))[0].cpu().tolist()
            error = max(abs(a - b) for a, b in zip(expected, actual))
            if error > 1e-6:
                raise ValueError('Real zero-step parity failed')
            rows.append({'clip': name, 'startMs': window.start, 'endMs': window.end,
                         'controlClassScores': expected, 'zeroStepClassScores': actual,
                         'maxAbsoluteError': error})
        finally:
            reader.close()
    base.assert_frozen(candidate, frozen)
    report = {'status': 'real-cuda-zero-step-parity-passed', 'device': 'cuda',
              'trainingManifestSha256': manifest_sha, 'corpusSha256': corpus_sha,
              'v2SourceSha256': base.file_hash(Path(experiment.__file__)),
              'scriptSha256': base.file_hash(Path(__file__)), 'rows': rows,
              'tolerance': 1e-6, 'allNonHeadTensorsUnchanged': True,
              'trainingPerformed': False, 'liveModelChanged': False}
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
