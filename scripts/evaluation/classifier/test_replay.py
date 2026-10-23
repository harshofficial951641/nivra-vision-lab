"""Timestamp/transform tests with in-memory synthetic pixels only."""
from unittest import TestCase
from unittest.mock import patch

import cv2
import numpy as np

from .common import PREPROCESSING
from .replay import decode, schedule, transform


class Capture:
    def __init__(self, times):
        self.times = times
        self.cursor = -1
        self.closed = False

    def isOpened(self):
        return True

    def read(self):
        self.cursor += 1
        if self.cursor == len(self.times):
            return False, None
        return True, np.full((12, 16, 3), self.cursor, np.uint8)

    def get(self, key):
        assert key == cv2.CAP_PROP_POS_MSEC
        return self.times[self.cursor]

    def release(self):
        self.closed = True


class ReplayTests(TestCase):
    def test_schedule_no_partial_warmup_or_future_window(self):
        self.assertEqual(schedule(3999), [])
        self.assertEqual(schedule(4000), [4000])
        self.assertEqual(schedule(5999.9), [4000, 5000])
        self.assertEqual(PREPROCESSING['selectedIndices'], np.linspace(0, 15, 8).astype(int).tolist())

    def test_irregular_actual_pts_ties_and_half_open_window(self):
        cap = Capture([t for t in range(0, 5100, 100) if t not in [500, 1000, 1500, 2000, 2500, 3000]])
        with patch('scripts.evaluation.classifier.replay.sha', return_value='test'), patch('cv2.VideoCapture', return_value=cap):
            ends, clips, pts, clock = decode(dict(id='synthetic', path='synthetic', sha256='test', durationMs=5100))
        self.assertEqual(ends, [4000, 5000])
        self.assertEqual(pts[0], [0, 400, 900, 1400, 1900, 2400, 2900, 3700])
        self.assertEqual(pts[1][0], 1100)  # 900 is outside [1000,5000).
        self.assertEqual(pts[1][-1], 4700)  # Earlier tie at 4750 target.
        self.assertEqual(clips[0].shape, (8, 172, 172, 3))
        self.assertTrue(cap.closed)
        self.assertTrue(all(end - 4000 <= t < end for end, values in zip(ends, pts) for t in values))

    def test_nonmonotonic_pts_fail_closed(self):
        cap = Capture([0, 100, 100, 200])
        with patch('scripts.evaluation.classifier.replay.sha', return_value='test'), patch('cv2.VideoCapture', return_value=cap):
            with self.assertRaisesRegex(ValueError, 'nonmonotonic'):
                decode(dict(id='synthetic', path='synthetic', sha256='test', durationMs=4000))
        self.assertTrue(cap.closed)

    def test_container_duration_cannot_supply_final_score(self):
        cap = Capture(list(range(0, 5000, 100)))
        with patch('scripts.evaluation.classifier.replay.sha', return_value='test'), patch('cv2.VideoCapture', return_value=cap):
            ends, _, _, clock = decode(dict(id='synthetic', path='synthetic', sha256='test', durationMs=5000))
        self.assertEqual(ends, [4000])
        self.assertEqual(clock['lastPtsMs'], 4900)

    def test_scoring_anchors_to_first_actual_pts(self):
        cap = Capture(list(range(100, 5200, 100)))
        with patch('scripts.evaluation.classifier.replay.sha', return_value='test'), patch('cv2.VideoCapture', return_value=cap):
            ends, _, _, clock = decode(dict(id='synthetic', path='synthetic', sha256='test', durationMs=5200))
        self.assertEqual(ends, [4100, 5100])
        self.assertEqual(clock['warmupEndMs'], 4100)

    def test_live_frame_coverage_guard(self):
        cap = Capture([0, 900, 1000, 2000, 3000, 4000])
        with patch('scripts.evaluation.classifier.replay.sha', return_value='test'), patch('cv2.VideoCapture', return_value=cap):
            with self.assertRaisesRegex(ValueError, 'source gap'):
                decode(dict(id='synthetic', path='synthetic', sha256='test', durationMs=4000))

    def test_exact_two_stage_rgb_resize(self):
        image = np.random.default_rng(17).integers(0, 256, (45, 83, 3), dtype=np.uint8)
        expected = cv2.resize(cv2.cvtColor(cv2.resize(image, (224, 224)), cv2.COLOR_BGR2RGB), (172, 172))
        np.testing.assert_array_equal(transform(image), expected)
        direct = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), (172, 172))
        self.assertFalse(np.array_equal(expected, direct))
