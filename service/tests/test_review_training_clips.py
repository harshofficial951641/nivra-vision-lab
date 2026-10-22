import json
from pathlib import Path
import sys

import numpy as np
import pytest

import review_training_clips as reviewer


class Capture:
    def __init__(self, *, opened=True, seek=True, decode=True):
        self.opened = opened
        self.seek = seek
        self.decode = decode
        self.requests = []
        self.released = False
        self.reads = 0

    def isOpened(self):
        return self.opened

    def set(self, property_id, value):
        self.requests.append((property_id, value))
        return self.seek

    def read(self):
        self.reads += 1
        return self.decode, np.full((6, 8, 3), self.reads, np.uint8)

    def release(self):
        self.released = True


@pytest.mark.parametrize('options,message', [({'opened': False}, 'Cannot open'),
                                            ({'seek': False}, 'Cannot seek'),
                                            ({'decode': False}, 'Cannot decode')])
def test_failed_open_seek_or_decode_releases_capture_and_never_returns_partial_samples(monkeypatch, options, message):
    capture = Capture(**options)
    monkeypatch.setattr(reviewer.cv2, 'VideoCapture', lambda path: capture)
    with pytest.raises(ValueError, match=message):
        reviewer.read_samples(Path('clip.mp4'), [.1, 2.5], (4, 3))
    assert capture.released
    if not options.get('seek', True):
        assert capture.reads == 0, 'A failed seek must not mislabel a frame from the previous position'


def test_samples_preserve_requested_seconds_and_seek_in_milliseconds(monkeypatch):
    capture = Capture()
    monkeypatch.setattr(reviewer.cv2, 'VideoCapture', lambda path: capture)
    samples = reviewer.read_samples(Path('clip.mp4'), [.1, 2.5, 4.9], (4, 3))
    assert capture.requests == [(reviewer.cv2.CAP_PROP_POS_MSEC, value) for value in (100, 2500, 4900)]
    assert [seconds for seconds, _ in samples] == [.1, 2.5, 4.9]
    assert [frame.shape for _, frame in samples] == [(3, 4, 3)] * 3
    assert [int(frame[0, 0, 0]) for _, frame in samples] == [1, 2, 3]
    assert capture.released


def test_failed_image_write_raises_instead_of_claiming_a_review_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(reviewer.cv2, 'imwrite', lambda *args: False)
    with pytest.raises(OSError, match='could not be written'):
        reviewer.write_sheet(tmp_path / 'sheet.jpg', np.zeros((3, 4, 3), np.uint8))


def test_failed_contact_sheet_write_does_not_publish_selection(tmp_path, monkeypatch):
    (tmp_path / 'inventory.json').write_text(json.dumps([{
        'id': 'clip', 'path': 'media/clip.mp4', 'durationSeconds': 5,
        'sha256': 'a' * 64, 'publisherCategory': 'normal', 'archive': 'nv_b_01.rar',
    }]), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['review_training_clips.py', '--data-root', str(tmp_path)])
    monkeypatch.setattr(reviewer, 'read_samples', lambda path, timestamps, size: [
        (seconds, np.zeros((size[1], size[0], 3), np.uint8)) for seconds in timestamps])
    monkeypatch.setattr(reviewer.cv2, 'imwrite', lambda *args: False)
    with pytest.raises(OSError):
        reviewer.main()
    assert not (tmp_path / 'review' / 'selected.json').exists()
