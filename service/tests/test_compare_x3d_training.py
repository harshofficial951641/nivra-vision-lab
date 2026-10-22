import json
from pathlib import Path

import cv2
import numpy as np
import pytest
import torch

import compare_x3d_training as comparison


def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(comparison.torch.cuda, 'is_available', lambda: False)
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    base, current, media = (tmp_path / name for name in ('base.pyth', 'current.pt', 'clip.avi'))
    for path in (base, current, media):
        path.write_bytes(path.name.encode())
    monkeypatch.setattr(comparison, 'BASE_SHA256', comparison.file_hash(base))
    monkeypatch.setattr(comparison, 'CHECKSUM', comparison.file_hash(current))
    head = torch.nn.Linear(2048, 2)
    artifact = {'schemaVersion': 1, 'kind': comparison.KIND,
                'baseSha256': comparison.BASE_SHA256, 'manifestSha256': 'b' * 64,
                'preprocessing': comparison.PREPROCESS, 'classNames': comparison.CLASS_NAMES,
                'threshold': .7, 'head_state': head.state_dict()}
    torch.save(artifact, run_dir / 'candidate-head.pt')
    report = {'schemaVersion': 1, 'kind': comparison.KIND,
              'base': {'sha256': comparison.BASE_SHA256}, 'manifestSha256': 'b' * 64,
              'preprocessing': comparison.PREPROCESS, 'classNames': comparison.CLASS_NAMES,
              'threshold': .7, 'candidateSha256': comparison.file_hash(run_dir / 'candidate-head.pt')}
    (run_dir / 'report.json').write_text(json.dumps(report))
    corpus = tmp_path / 'corpus.json'
    corpus.write_text(json.dumps([{'id': 'clip', 'sourceGroup': 'clip', 'split': 'holdout',
                                  'durationMs': 5000, 'path': media.name,
                                  'sha256': comparison.file_hash(media), 'annotationStatus': 'reviewed',
                                  'events': [{'startMs': 3000, 'endMs': 3200, 'label': 'brief-contact'}]}]))
    return run_dir, base, current, corpus, media


def test_missing_or_tampered_inputs_fail_before_any_model_construction(tmp_path, monkeypatch):
    run_dir, base, current, corpus, media = inputs(tmp_path, monkeypatch)
    calls = []

    def forbidden(*_args):
        calls.append(True)
        raise AssertionError('Model must not be constructed for bad inputs')

    (run_dir / 'candidate-head.pt').write_bytes(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        comparison.run(run_dir, base, corpus, tmp_path / 'output.json', community_checkpoint=current,
                       candidate_factory=forbidden, community_factory=forbidden)
    assert not calls
    (run_dir / 'report.json').unlink()
    with pytest.raises(ValueError, match='missing'):
        comparison.validate_inputs(run_dir, base, corpus, current)


def test_base_media_and_report_artifact_mismatch_rejected(tmp_path, monkeypatch):
    run_dir, base, current, corpus, media = inputs(tmp_path, monkeypatch)
    original = media.read_bytes()
    media.write_bytes(b'changed media')
    with pytest.raises(ValueError, match='media missing or checksum'):
        comparison.validate_inputs(run_dir, base, corpus, current)
    media.write_bytes(original)
    report = json.loads((run_dir / 'report.json').read_text())
    report['threshold'] = .3
    (run_dir / 'report.json').write_text(json.dumps(report))
    with pytest.raises(ValueError, match='does not match'):
        comparison.validate_inputs(run_dir, base, corpus, current)
    base.write_bytes(b'changed base')
    with pytest.raises(ValueError, match='base checkpoint checksum'):
        comparison.validate_inputs(run_dir, base, corpus, current)


def test_mock_comparison_uses_saved_threshold_and_reports_context_without_accuracy(tmp_path, monkeypatch):
    run_dir, base, current, corpus, _ = inputs(tmp_path, monkeypatch)
    frame = np.zeros((224, 224, 3), dtype=np.uint8)

    class Candidate:
        def __init__(self, *_args):
            pass

        def predict(self, frames):
            return .6

    class Current(Candidate):
        device = 'cpu'

        def predict(self, frames):
            return {'backboneScore': .6}

    report = comparison.run(run_dir, base, corpus, run_dir / 'diagnostics.json',
                            community_checkpoint=current, candidate_factory=Candidate,
                            community_factory=Current,
                            window_reader=lambda *_args: [(4000, 100, [frame])])
    row = report['clips']['clip']['samples'][0]
    assert row['current']['review'] is True
    assert row['candidate']['review'] is False
    assert row['candidate']['reviewAtPointFive'] is True
    assert row['labelledEventOverlaps'][0]['overlapMs'] == 200
    assert report['clips']['clip']['historicalSplit'] == 'holdout'
    assert report['clips']['clip']['disagreementWindows'] == 1
    assert 'accuracy' not in report['clips']['clip']
    assert report['liveModelChanged'] is False and report['thresholdFittedHere'] is False
    with pytest.raises(FileExistsError):
        comparison.run(run_dir, base, corpus, run_dir / 'diagnostics.json', community_checkpoint=current)


def test_head_candidate_has_working_cpu_prediction_with_frozen_feature_interface():
    head = torch.nn.Linear(2048, 2)
    with torch.no_grad():
        head.weight.zero_()
        head.bias.copy_(torch.tensor([0., 2.]))

    class Features:
        def __init__(self, _):
            pass

        def __call__(self, tensor):
            assert tensor.shape == (1, 3, 16, 224, 224) and tensor.device.type == 'cpu'
            return np.zeros((1, 2048), dtype=np.float32)

    candidate = comparison.HeadCandidate(None, {'head_state': head.state_dict()}, extractor_factory=Features)
    score = candidate.predict([np.zeros((32, 32, 3), dtype=np.uint8)])
    assert score == pytest.approx(.880797, abs=1e-6)


def test_decoder_pts_support_webm_with_malformed_nominal_fps_and_reject_missing_clock(monkeypatch):
    class Capture:
        def __init__(self, timestamps):
            self.timestamps = timestamps
            self.index = 0
            self.released = False

        def isOpened(self):
            return True

        def read(self):
            if self.index == len(self.timestamps):
                return False, None
            self.index += 1
            return True, np.zeros((32, 32, 3), dtype=np.uint8)

        def get(self, property_id):
            if property_id == cv2.CAP_PROP_FPS:
                return 30000
            if property_id == cv2.CAP_PROP_POS_MSEC:
                return self.timestamps[self.index - 1]
            return self.index

        def release(self):
            self.released = True

    valid = Capture([index * 33 for index in range(130)])
    monkeypatch.setattr(comparison.cv2, 'VideoCapture', lambda _: valid)
    rows = list(comparison.windows({'id': 'webm', 'path': 'local.webm'}, Path('corpus.json')))
    assert rows and 3800 <= rows[0][0] < 4100
    assert rows[0][0] == rows[0][0] // 33 * 33
    assert valid.released
    invalid = Capture([0, 0, 33])
    monkeypatch.setattr(comparison.cv2, 'VideoCapture', lambda _: invalid)
    with pytest.raises(ValueError, match='timestamp'):
        list(comparison.windows({'id': 'broken', 'path': 'local.webm'}, Path('corpus.json')))
    assert invalid.released
