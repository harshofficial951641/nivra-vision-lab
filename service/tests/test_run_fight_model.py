import numpy as np
import pytest

from run_fight_model import FightWindow, run


def test_window_waits_for_history_and_bounds_memory():
    history = FightWindow()
    frame = np.zeros((100, 160, 3), np.uint8)
    for timestamp in range(0, 3800, 100):
        assert history.add(timestamp, frame) is None
    assert len(history.add(3800, frame)) == 39
    assert history.add(3900, frame) is None
    for timestamp in range(4000, 10000, 100):
        history.add(timestamp, frame)
    assert len(history.frames) <= 41
    assert history.frames[-1][0] - history.frames[0][0] <= 4000


def test_gap_and_size_change_clear_old_evidence():
    history = FightWindow()
    frame = np.zeros((100, 160, 3), np.uint8)
    for timestamp in range(0, 4000, 100):
        history.add(timestamp, frame)
    assert history.add(5500, frame) is None
    assert len(history.frames) == 1
    assert history.add(5600, np.zeros((80, 100, 3), np.uint8)) is None
    assert len(history.frames) == 1
    with pytest.raises(ValueError, match='backwards'):
        history.add(5500, frame)


def test_missing_video_fails_before_loading_model(tmp_path):
    with pytest.raises(ValueError, match='does not exist'):
        run(tmp_path/'missing.mp4')
