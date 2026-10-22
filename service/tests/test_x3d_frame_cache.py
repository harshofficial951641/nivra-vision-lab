from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from nivra.x3d_finetune import FineTuneConfig, FrameCache
from nivra.x3d_training import preprocess_frames


def window(name='one', sha='a' * 64, start=0):
    return SimpleNamespace(path=Path(name + '.mp4'), sha256=sha,
                           start_seconds=start, end_seconds=start + 4)


def test_cached_inputs_preserve_preprocessing_and_do_not_decode_again():
    reads = []

    def reader(entry):
        reads.append(entry.path)
        return [np.full((8, 8, 3), index, np.uint8) for index in range(20)]

    expected = preprocess_frames(reader(window()))
    reads.clear()
    cache = FrameCache(reader, 1)
    frames = cache(window())
    torch.testing.assert_close(preprocess_frames(frames), expected, rtol=0, atol=0)
    torch.testing.assert_close(preprocess_frames(cache(window())), expected, rtol=0, atol=0)
    assert len(reads) == 1 and cache.summary()['hits'] == 1
    with pytest.raises(ValueError):
        frames[0][0, 0, 0] = 255


def test_lru_evicts_within_budget_and_preserves_recent_inputs():
    cache = FrameCache(lambda _: [np.zeros((256, 512, 3), np.uint8)], 1)
    first = cache(window('one'))
    cache(window('two'))
    assert cache(window('one')) is first
    cache(window('three'))
    assert cache.bytes <= cache.limit and len(cache.entries) == 2
    assert cache.summary()['evictions'] == 1
    cache(window('two'))
    assert cache.summary()['misses'] == 4


def test_cache_binds_source_hash_and_temporal_bounds_and_reads_lazily():
    seen = []
    cache = FrameCache(lambda entry: seen.append(entry) or [np.zeros((2, 2, 3), np.uint8)], 1)
    assert seen == []
    cache(window())
    cache(window(sha='b' * 64))
    cache(window(start=4))
    assert len(seen) == 3 and cache.summary()['misses'] == 3


def test_oversized_input_is_not_retained():
    cache = FrameCache(lambda _: [np.zeros((1024, 1024, 3), np.uint8)], 1)
    cache(window())
    cache(window())
    assert cache.bytes == 0 and not cache.entries
    assert cache.summary()['oversizeReads'] == 2


@pytest.mark.parametrize('value', [-1, True, 1.5, 4097])
def test_invalid_cache_budget_rejected(value):
    with pytest.raises(ValueError, match='Input cache'):
        FineTuneConfig(input_cache_mib=value).validate()


def test_cache_rejects_non_frame_data():
    with pytest.raises(ValueError, match='uint8 BGR'):
        FrameCache(lambda _: [torch.zeros(3)], 1)(window())
