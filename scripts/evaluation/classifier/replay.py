"""Sequential actual-PTS OpenCV replay of the exact training input transform.

No decoded pixels are persisted. Only private timestamp/score JSON is cached.
CUDA work always holds training_v4.gpu_lock's existing FIFO lock.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import math
from pathlib import Path
import platform
import time

import cv2
import numpy as np
import torch

from .common import DOCS, MODEL, MODEL_SHA, PREPROCESSING, PRIVATE, RUN, TRAINING, digest, frozen, read, sha, write


def load_model(device):
    """Remap trace-pinned factory devices in RAM; never rewrite the artifact.

    torch.jit.load(map_location=...) relocates weights/tensor constants, but not
    the prim::Constant Device arguments used by arange/zeros in this export.
    Fresh graphs per device avoid cached execution plans from a previous run.
    """
    model = torch.jit.load(str(MODEL), map_location=device).eval()
    changed = 0
    for module in model.modules():
        for method in module._c._method_names():
            graph = module._c._get_method(method).graph
            def visit(block):
                nonlocal changed
                for node in list(block.nodes()):
                    for child in node.blocks():
                        visit(child)
                    if node.kind() != 'prim::Constant':
                        continue
                    value = node.output().toIValue()
                    if isinstance(value, torch.device) and value.type == 'cpu' and device != 'cpu':
                        replacement = graph.insertConstant(torch.device(device))
                        replacement.node().moveBefore(node)
                        node.output().replaceAllUsesWith(replacement)
                        node.destroy()
                        changed += 1
            visit(graph)
            torch._C._jit_pass_lint(graph)
    return model, changed


def schedule(duration_ms, first_pts_ms=0., last_pts_ms=None):
    upper = duration_ms if last_pts_ms is None else min(duration_ms, last_pts_ms)
    count = math.floor((upper - first_pts_ms - 4000 + 1e-4) / 1000) + 1
    return [float(first_pts_ms + 4000 + i * 1000) for i in range(max(0, count))]


def transform(bgr):
    rgb224 = cv2.cvtColor(cv2.resize(bgr, (224, 224), interpolation=cv2.INTER_LINEAR), cv2.COLOR_BGR2RGB)
    return cv2.resize(rgb224, (172, 172), interpolation=cv2.INTER_LINEAR)


def decode(record):
    cv2.setNumThreads(1)
    assert sha(record['path']) == record['sha256'], 'media changed after freeze'
    ends, tasks, images, selected_pts = [], [], [], []
    cap = cv2.VideoCapture(record['path'])
    if not cap.isOpened():
        raise ValueError('cannot decode ' + record['id'])
    previous, last_t, first_t, max_gap, cursor = None, -math.inf, None, 0., 0
    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            t = float(cap.get(cv2.CAP_PROP_POS_MSEC))
            if not math.isfinite(t) or t < 0 or t <= last_t:
                raise ValueError(('invalid/nonmonotonic actual PTS', record['id'], last_t, t))
            if first_t is None:
                first_t = t
                ends = schedule(record['durationMs'], first_t)
                tasks = sorted((end - 4000 + offset, j, i)
                               for j, end in enumerate(ends) for i, offset in enumerate(PREPROCESSING['targetOffsetsMs']))
                images = [[None] * 8 for _ in ends]
                selected_pts = [[None] * 8 for _ in ends]
            else:
                max_gap = max(max_gap, t - last_t)
                if t - last_t > 250:
                    raise ValueError(('source gap requires live epoch reset', record['id'], last_t, t))
            converted = {}
            while cursor < len(tasks) and tasks[cursor][0] <= t:
                target, j, i = tasks[cursor]
                start, end = ends[j] - 4000, ends[j]
                choices = []
                if previous is not None and start <= last_t < end:
                    choices.append((abs(last_t - target), last_t, previous))
                if start <= t < end:
                    choices.append((abs(t - target), t, bgr))
                if not choices:
                    raise ValueError(('no causal in-window sample', record['id'], target))
                _, source_t, frame = min(choices, key=lambda item: (item[0], item[1]))
                if abs(source_t - target) > 250:
                    raise ValueError(('live 250ms frame-coverage guard failed', record['id'], target, source_t))
                if source_t not in converted:
                    converted[source_t] = transform(frame)
                images[j][i] = converted[source_t]
                selected_pts[j][i] = source_t
                cursor += 1
            previous, last_t = bgr, t
        if first_t is None:
            raise ValueError(('empty video', record['id']))
        admitted = [i for i, end in enumerate(ends) if end <= last_t + 1e-4]
        if any(any(v is None for v in images[i]) for i in admitted):
            raise ValueError(('truncated actual-PTS coverage', record['id']))
    finally:
        cap.release()
    clock = dict(firstPtsMs=first_t, lastPtsMs=last_t, maxFrameGapMs=max_gap,
                 containerDurationMs=record['durationMs'], warmupEndMs=first_t + 4000,
                 admission='frame-driven: first actual PTS + 4s + k*1s <= last actual PTS; no EOF/container-duration flush')
    return ([ends[i] for i in admitted], [np.stack(images[i]) for i in admitted],
            [selected_pts[i] for i in admitted], clock)


def tensor(clips):
    return torch.from_numpy(np.stack(clips)).permute(0, 1, 4, 2, 3).contiguous().float() / 255


def cache_path(record, legacy=False):
    key = digest(dict(schema=1, sha256=record['sha256'], durationMs=record['durationMs'], model=MODEL_SHA,
                      preprocessing=PREPROCESSING, decoder='OpenCV ' + cv2.__version__, execution='trace-factory-device-remap-v1'))
    if not legacy:
        key = digest([key, 'actual-frame-clock-v2'])
    return PRIVATE / 'cache' / (key + '.json')


def cached(record):
    path = cache_path(record)
    if not path.exists():
        return None
    value = read(path)
    assert value['modelSha256'] == MODEL_SHA and value['mediaSha256'] == record['sha256']
    assert value['windowsSha256'] == digest(value['windows'])
    clock = value['sourceClock']
    assert [w['timestampMs'] for w in value['windows']] == schedule(record['durationMs'], clock['firstPtsMs'], clock['lastPtsMs'])
    for w in value['windows']:
        assert math.isfinite(w['probability']) and 0 <= w['probability'] <= 1
        assert len(w['selectedPtsMs']) == 8
        assert all(w['timestampMs'] - 4000 <= t < w['timestampMs'] for t in w['selectedPtsMs'])
        assert all(abs(t - (w['timestampMs'] - 4000 + offset)) <= 250
                   for t, offset in zip(w['selectedPtsMs'], PREPROCESSING['targetOffsetsMs']))
    assert sha(record['path']) == record['sha256']
    return value


def prepare(record):
    receipt = cached(record)
    if receipt is not None:
        return receipt, None
    decoded = decode(record)
    ends, _, pts, clock = decoded
    legacy = cache_path(record, legacy=True)
    if legacy.exists():
        old = read(legacy)
        assert old['windowsSha256'] == digest(old['windows'])
        assert old['mediaSha256'] == record['sha256'] and old['modelSha256'] == MODEL_SHA
        lookup = {w['timestampMs']: w for w in old['windows']}
        if all(end in lookup and lookup[end]['selectedPtsMs'] == selected for end, selected in zip(ends, pts)):
            receipt = {k: v for k, v in old.items() if k not in ['windows', 'windowsSha256']}
            receipt.update(schemaVersion=2, sourceClock=clock, windows=[lookup[end] for end in ends],
                           legacyContainerWindowCount=len(old['windows']), legacyCacheSha256=sha(legacy))
            receipt['windowsSha256'] = digest(receipt['windows'])
            write(cache_path(record), receipt)
            return receipt, None
    return None, decoded


def preprocessing_parity(records):
    """Bitwise compare against training's frozen 16-frame private cache."""
    lookup = {r['id']: r for r in records}
    original = read(RUN / 'windows.json')['dev']
    for window in original:
        if window['recordingId'] not in lookup or window['startMs'] != 0:
            continue
        key = digest([1, window['sha256'], window['startMs'], window['endMs'], 16, 224, 'nearest-actual-PTS-half-open'])
        path = RUN.parent / 'window-cache-v1' / key / 'frames.npy'
        if not path.exists():
            continue
        reference = np.load(path, allow_pickle=False)[np.linspace(0, 15, 8).astype(int)]
        reference = np.stack([cv2.resize(v, (172, 172)) for v in reference])
        _, actual, pts, _ = decode(lookup[window['recordingId']])
        delta = int(np.abs(reference.astype(np.int16) - actual[0].astype(np.int16)).max())
        assert delta == 0, ('training preprocessing parity failed', delta)
        return dict(reference='frozen round-1 dev training-input cache', maxAbsPixelDifference=delta,
                    comparedFrames=8, tensorShape=[1, 8, 3, 172, 172], inputCacheReceiptSha256=sha(path.with_name('complete.json')))
    raise ValueError('no frozen dev input cache available to verify exact preprocessing')


def benchmark(records):
    result = dict(torch=torch.__version__, opencv=cv2.__version__, python=platform.python_version(),
                  platform=platform.platform(), cpu=platform.processor(), cpuThreads=2,
                  cudaDevice=torch.cuda.get_device_name(), scope='FP32 preallocated tensor to logits, synchronized wall time; excludes decode, resize, host/device transfers; each forward is a reset clip', batches={})
    clips = []
    for row in records:
        _, values, _, _ = decode(row)
        clips.extend(values[:1])
        if len(clips) >= 4:
            break
    x = tensor(clips[:4])
    assert x.shape == (4, 8, 3, 172, 172)
    references = {}
    with torch.inference_mode():
        for device in ['cpu', 'cuda']:
            model, remapped = load_model(device)
            result[device + 'FactoryDeviceConstantsRemapped'] = remapped
            inputs = x.to(device)
            result['batches'][device] = {}
            for batch in [1, 4]:
                value = inputs[:batch]
                for _ in range(5 if device == 'cpu' else 10):
                    model(value)
                samples = []
                for _ in range(30 if device == 'cpu' else 60):
                    if device == 'cuda':
                        torch.cuda.synchronize()
                    start = time.perf_counter()
                    output = model(value)
                    if device == 'cuda':
                        torch.cuda.synchronize()
                    samples.append((time.perf_counter() - start) * 1000)
                assert output.shape == (batch, 2) and bool(torch.isfinite(output).all())
                result['batches'][device][str(batch)] = dict(p50Ms=float(np.quantile(samples, .5)),
                    p95Ms=float(np.quantile(samples, .95)), meanMs=float(np.mean(samples)),
                    p50PerWindowMs=float(np.quantile(samples, .5)) / batch, repeats=len(samples))
            references[device] = model(inputs).softmax(1).cpu()
            solo = torch.cat([model(inputs[i:i+1]).softmax(1) for i in range(4)]).cpu()
            difference = float((references[device] - solo).abs().max())
            assert difference < 1e-4
            result[device + 'BatchIndependenceMaxAbsProbability'] = difference
            repeated = model(inputs).softmax(1).cpu()
            assert torch.allclose(repeated, references[device], atol=1e-6, rtol=1e-5), 'clip-reset parity failed'
        difference = float((references['cpu'] - references['cuda']).abs().max())
        assert difference < 1e-4
        result['cpuCudaParity'] = dict(windows=4, maxAbsProbability=difference, tolerance=1e-4, passed=True)
    result['executionTransform'] = 'Original artifact unchanged; trace-pinned CPU factory-device constants remapped to CUDA in memory. Weights/operators otherwise unchanged; probability parity checked.'
    result['preprocessingParity'] = preprocessing_parity(records)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', required=True, choices=['calibration', 'test'])
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args()
    data, split_sha = frozen()
    assert sha(MODEL) == MODEL_SHA
    if args.split == 'test':
        selected = PRIVATE / 'selected-policy.json'
        assert selected.exists(), 'select/freeze policy before reading test predictions'
        assert read(selected)['splitSha256'] == split_sha
        assert not (PRIVATE / 'test-result.json').exists(), 'test already reported; no rerun/tuning'
    records = [r for r in data['records'] if r['evaluationSplit'] == args.split]
    torch.set_num_threads(2)
    cv2.setNumThreads(1)
    spec = importlib.util.spec_from_file_location('classifier_gpu_lock', TRAINING / 'gpu_lock.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    started = time.perf_counter()
    complete, windows_count = 0, 0
    with module.gpu_lock('classifier-evaluation:' + args.split, timeout=7200):
        if args.benchmark:
            assert args.split == 'calibration', 'benchmark uses calibration footage only'
            report = benchmark(records)
            write(DOCS / 'latency.json', report)
            print('benchmark', json.dumps(report), flush=True)
        model, remapped = load_model('cuda')
        with torch.inference_mode(), ThreadPoolExecutor(max_workers=2) as pool:
            pending = {}
            for index, record in enumerate(records):
                # Bounded decode pipeline: at most four recordings of pixels in RAM.
                for j in range(index, min(len(records), index + 4)):
                    if j not in pending:
                        pending[j] = pool.submit(prepare, records[j])
                receipt, decoded = pending.pop(index).result()
                if receipt is None:
                    ends, clips, pts, clock = decoded
                    windows = []
                    for offset in range(0, len(clips), 4):
                        probabilities = model(tensor(clips[offset:offset+4]).cuda()).softmax(1)[:, 1].cpu().tolist()
                        for k, probability in enumerate(probabilities, start=offset):
                            assert math.isfinite(probability) and 0 <= probability <= 1
                            windows.append(dict(timestampMs=ends[k], evidenceStartMs=ends[k]-4000,
                                                probability=probability, selectedPtsMs=pts[k]))
                    receipt = dict(schemaVersion=2, mediaSha256=record['sha256'], modelSha256=MODEL_SHA, sourceClock=clock,
                                   preprocessing=PREPROCESSING, decoder='OpenCV ' + cv2.__version__,
                                   device='cuda', factoryDeviceConstantsRemapped=remapped,
                                   windows=windows, windowsSha256=digest(windows))
                    write(cache_path(record), receipt)
                    del clips
                del decoded
                complete += 1
                windows_count += len(receipt['windows'])
                if complete % 20 == 0:
                    print(json.dumps(dict(split=args.split, recordings=complete, total=len(records), windows=windows_count,
                                          seconds=round(time.perf_counter()-started, 2))), flush=True)
        model.cpu()
        torch.cuda.empty_cache()
    receipts = [cached(r) for r in records]
    report = dict(split=args.split, splitSha256=split_sha, modelSha256=MODEL_SHA,
                  recordings=complete, windows=windows_count, elapsedSeconds=time.perf_counter()-started,
                  clockAdmission='actual-frame-clock-v2',
                  containerEndWindowsRemoved=sum(r.get('legacyContainerWindowCount', len(r['windows'])) - len(r['windows']) for r in receipts),
                  maximumActualFrameGapMs=max(r['sourceClock']['maxFrameGapMs'] for r in receipts),
                  firstActualPtsRangeMs=[min(r['sourceClock']['firstPtsMs'] for r in receipts), max(r['sourceClock']['firstPtsMs'] for r in receipts)],
                  cacheContentSha256=digest([dict(mediaSha256=r['sha256'], windowsSha256=c['windowsSha256']) for r, c in zip(records, receipts)]))
    write(PRIVATE / ('replay-' + args.split + '.json'), report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
