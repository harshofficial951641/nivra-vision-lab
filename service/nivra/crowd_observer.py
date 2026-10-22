"""Isolated, bounded RTMO research observations. No tracking or fight decisions."""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import platform
from time import perf_counter

import cv2
import numpy as np


SERVICE = Path(__file__).resolve().parents[1]
MODEL_ID = 'rtmo-m-body7'
MODEL_SHA256 = '750d872151ff4652f02c738efc3a547e112ce9b688fe920bc17f948e8c3afdac'
CUDA_ARENA_BYTES = 1 << 30
MAX_MODEL_BYTES = 128 * 1024 * 1024
MAX_SLOTS = 256
MAX_PROFILE_BYTES = 64 * 1024 * 1024
MAX_PROFILE_EVENTS = 200_000
VIEWS = ((0, 0, 1, 1), (0, 0, .65, .65), (.35, 0, 1, .65),
         (0, .35, .65, 1), (.35, .35, 1, 1))
COCO17 = ('nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
          'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
          'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
          'left_knee', 'right_knee', 'left_ankle', 'right_ankle')


@dataclass(frozen=True)
class ObserverPolicy:
    max_observations: int = 100
    max_slots_per_view: int = MAX_SLOTS
    score_threshold: float = .1
    dedup_iou: float = .7
    min_box_pixels: float = 8
    max_iou_comparisons: int = 50_000

    def __post_init__(self):
        for value, lower, upper in ((self.max_observations, 1, 100),
                                    (self.max_slots_per_view, 1, MAX_SLOTS),
                                    (self.max_iou_comparisons, 1, 50_000)):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError('Invalid observer work budget')
        for value, lower, upper in ((self.score_threshold, 0, 1),
                                    (self.dedup_iou, .01, 1),
                                    (self.min_box_pixels, 1, 1920)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError('Invalid observer threshold')


def validate_dimensions(width: int, height: int) -> None:
    if (type(width) is not int or type(height) is not int or min(width, height) < 32
            or not ((width <= 1920 and height <= 1080)
                    or (width <= 1080 and height <= 1920))):
        raise ValueError('Expected at most native 1920x1080 or 1080x1920')


def validate_frame(frame: np.ndarray) -> tuple[int, int]:
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError('Expected uint8 BGR frame with three channels')
    height, width = frame.shape[:2]
    validate_dimensions(width, height)
    return width, height


def view_geometry(width: int, height: int) -> list[tuple[int, int, int, int]]:
    validate_dimensions(width, height)
    return [(round(x * width), round(y * height), round(r * width), round(b * height))
            for x, y, r, b in VIEWS]


def letterbox(frame: np.ndarray) -> tuple[np.ndarray, float]:
    """Match Models.crowd_observations: BGR, top-left padding, no normalization."""
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError('Expected uint8 BGR crop')
    height, width = frame.shape[:2]
    if min(width, height) < 1 or max(width, height) > 1920 or width * height > 1920 * 1080:
        raise ValueError('Crop dimensions exceed native frame bounds')
    ratio = min(640 / height, 640 / width)
    resized = cv2.resize(frame, (int(width * ratio), int(height * ratio)))
    padded = np.full((640, 640, 3), 114, np.uint8)
    padded[:resized.shape[0], :resized.shape[1]] = resized
    return padded.transpose(2, 0, 1)[None].astype(np.float32), ratio


def _dimension(value, expected=None, maximum=None):
    if type(value) is int:
        if value <= 0 or (expected is not None and value != expected) or (maximum is not None and value > maximum):
            raise ValueError('Incompatible static model dimension')
    elif not isinstance(value, str) or not value.strip():
        raise ValueError('Unknown model dimension without a symbolic name')


def validate_session_metadata(session, policy: ObserverPolicy) -> dict:
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if len(inputs) != 1 or inputs[0].name != 'input' or inputs[0].type != 'tensor(float)':
        raise ValueError('Unexpected RTMO input metadata')
    shape = inputs[0].shape
    if len(shape) != 4 or list(shape[1:]) != [3, 640, 640]:
        raise ValueError('RTMO input must be batch x 3 x 640 x 640')
    _dimension(shape[0], expected=1)
    by_name = {node.name: node for node in outputs}
    if len(outputs) != 2 or set(by_name) != {'dets', 'keypoints'}:
        raise ValueError('Unexpected RTMO output names')
    for name, expected in (('dets', [1, None, 5]), ('keypoints', [1, None, 17, 3])):
        node = by_name[name]
        if node.type != 'tensor(float)' or len(node.shape) != len(expected):
            raise ValueError('Invalid RTMO output rank/type')
        for index, dimension in enumerate(node.shape):
            _dimension(dimension, expected=expected[index],
                       maximum=policy.max_slots_per_view if index == 1 else None)
    det_slots, pose_slots = by_name['dets'].shape[1], by_name['keypoints'].shape[1]
    if type(det_slots) is int and type(pose_slots) is int and det_slots != pose_slots:
        raise ValueError('Model output slot counts disagree')
    return {'inputs': [{'name': n.name, 'shape': list(n.shape), 'type': n.type} for n in inputs],
            'outputs': [{'name': n.name, 'shape': list(n.shape), 'type': n.type} for n in outputs],
            'metadataJointCount': by_name['keypoints'].shape[2] if type(by_name['keypoints'].shape[2]) is int else None,
            'metadataSlotCount': det_slots if type(det_slots) is int else None,
            'symbolicDimensionsRequireRuntimeValidation': any(
                type(x) is not int for n in outputs for x in n.shape)}


def verified_model(service_root: Path = SERVICE) -> tuple[bytes, dict]:
    """Hash the exact bytes passed to ORT, avoiding path substitution after hashing."""
    root = Path(service_root).resolve(strict=True)
    manifest = json.loads((root / 'model-manifest.json').read_text(encoding='utf-8'))
    entries = [m for m in manifest['models'] if m['id'] == MODEL_ID]
    if len(entries) != 1:
        raise ValueError('Expected one pinned RTMO manifest entry')
    entry = entries[0]
    if entry['file'] != 'rtmo_m.onnx' or entry['sha256'] != MODEL_SHA256:
        raise ValueError('RTMO manifest differs from the approved asset pin')
    path = root / 'models' / entry['file']
    if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root / 'models'):
        raise ValueError('Model must remain inside local models directory')
    if not 1 <= path.stat().st_size <= MAX_MODEL_BYTES:
        raise ValueError('Model byte limit exceeded')
    with path.open('rb') as stream:
        data = stream.read(MAX_MODEL_BYTES + 1)
    if len(data) > MAX_MODEL_BYTES or hashlib.sha256(data).hexdigest() != MODEL_SHA256:
        raise ValueError('RTMO model checksum mismatch')
    return data, {'id': MODEL_ID, 'sha256': MODEL_SHA256, 'file': entry['file'],
                  'manifestSource': entry.get('source'), 'manifestLicense': entry.get('license'),
                  'rightsIndependentlyCleared': False}


def create_observer(device: str, *, service_root: Path = SERVICE,
                    policy: ObserverPolicy | None = None, preload_torch_dlls: bool = False,
                    allow_cpu_operators: bool = False, profile_prefix: Path | None = None,
                    yield_guard=None, ort_module=None) -> 'CrowdObserver':
    if device not in ('cpu', 'cuda') or type(preload_torch_dlls) is not bool:
        raise ValueError('Explicit cpu or cuda device required')
    if preload_torch_dlls and (device != 'cuda' or platform.system() != 'Windows'):
        raise ValueError('Torch DLL preload is only permitted for explicit Windows CUDA')
    if type(allow_cpu_operators) is not bool or (allow_cpu_operators and device != 'cuda'):
        raise ValueError('CPU operators are an explicit CUDA research policy only')
    if allow_cpu_operators and profile_prefix is None:
        raise ValueError('Mixed CUDA/CPU operators require operator profiling')
    if profile_prefix is not None:
        profile_prefix = validate_profile_prefix(profile_prefix, service_root)
    data, provenance = verified_model(service_root)
    if ort_module is None:
        import onnxruntime as ort_module
    required = 'CUDAExecutionProvider' if device == 'cuda' else 'CPUExecutionProvider'
    if required not in ort_module.get_available_providers():
        raise RuntimeError(f'Required provider unavailable: {required}')
    options = ort_module.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    options.execution_mode = ort_module.ExecutionMode.ORT_SEQUENTIAL
    if profile_prefix is not None:
        options.enable_profiling = True
        options.profile_file_prefix = str(profile_prefix)
    if device == 'cuda':
        if not allow_cpu_operators:
            options.add_session_config_entry('session.disable_cpu_ep_fallback', '1')
        if platform.system() == 'Windows':
            if preload_torch_dlls:
                # Explicit opt-in only: import for DLL discovery, never call torch.cuda.
                import torch  # noqa: F401
            if hasattr(ort_module, 'preload_dlls'):
                ort_module.preload_dlls()
        providers = [(required, {'device_id': 0, 'gpu_mem_limit': CUDA_ARENA_BYTES,
                                  'arena_extend_strategy': 'kSameAsRequested',
                                  'do_copy_in_default_stream': True})]
        if allow_cpu_operators:
            if 'CPUExecutionProvider' not in ort_module.get_available_providers():
                raise RuntimeError('Explicit CPU operator provider unavailable')
            providers.append('CPUExecutionProvider')
    else:
        providers = [required]
    try:
        session = ort_module.InferenceSession(data, sess_options=options, providers=providers)
    except Exception as error:
        # ORT's pybind Fail is not reliably a RuntimeError; preserve readable CLI failure.
        raise RuntimeError(f'ORT session initialization failed: {str(error)[:2000]}') from error
    session.disable_fallback()
    actual = session.get_providers()
    if not actual or actual[0] != required or (device == 'cpu' and actual != [required]):
        raise RuntimeError('ORT did not activate the requested provider; refusing fallback')
    if allow_cpu_operators and set(actual) != {'CUDAExecutionProvider', 'CPUExecutionProvider'}:
        raise RuntimeError('Mixed policy requires CUDA first and explicit CPU operator provider')
    runtime = {'device': device, 'providers': actual, 'ortVersion': ort_module.__version__,
               'cudaArenaLimitBytes': CUDA_ARENA_BYTES if device == 'cuda' else None,
               'allowCpuOperators': allow_cpu_operators,
               'cpuExecutionFallbackDisabled': device == 'cuda' and not allow_cpu_operators,
               'pythonProviderFallbackDisabled': True,
               'gpuVerified': False, 'gpuVerification': 'operator-execution-not-profiled',
               'gpuPeakMemoryBytes': None,
               'memoryScope': 'ORT arena limit is not a total GPU/process allocation limit; device peak not measured',
               'provenance': provenance}
    return CrowdObserver(session, policy=policy, runtime=runtime,
                         profile_prefix=profile_prefix, yield_guard=yield_guard)


def validate_profile_prefix(prefix: Path, service_root: Path) -> Path:
    prefix = Path(prefix).absolute()
    allowed = Path(service_root).resolve() / 'research' / 'runs'
    if ('..' in prefix.parts or not prefix.resolve().is_relative_to(allowed)
            or not prefix.parent.is_dir() or prefix.name != 'ort'):
        raise ValueError('Profile prefix must be ort inside a new local research/runs directory')
    for parent in (prefix, *prefix.parents):
        if parent.is_symlink():
            raise ValueError('Symlink profiling paths are forbidden')
        if parent == Path(service_root).absolute():
            break
    if any(prefix.parent.iterdir()):
        raise FileExistsError('Profiling directory must be new and empty')
    return prefix


def summarize_operator_profile(path: Path, prefix: Path) -> dict:
    """Read a bounded local ORT trace; counters concern executed nodes, not accuracy."""
    raw_path, prefix = Path(path).absolute(), Path(prefix).absolute()
    if any(parent.is_symlink() for parent in raw_path.parents):
        raise ValueError('Symlink profile parents are forbidden')
    if (raw_path.is_symlink() or raw_path.resolve().parent != prefix.parent.resolve()
            or not raw_path.name.startswith(prefix.name + '_') or raw_path.suffix != '.json'
            or not raw_path.is_file()):
        raise ValueError('ORT returned an unexpected profile path')
    if raw_path.stat().st_size > MAX_PROFILE_BYTES:
        raise ValueError('ORT profile byte budget exceeded')
    with raw_path.open('rb') as stream:
        data = stream.read(MAX_PROFILE_BYTES + 1)
    if len(data) > MAX_PROFILE_BYTES:
        raise ValueError('ORT profile byte budget exceeded')
    try:
        events = json.loads(data)
    except (ValueError, RecursionError) as error:
        raise ValueError('Invalid ORT profiling JSON') from error
    if not isinstance(events, list) or len(events) > MAX_PROFILE_EVENTS:
        raise ValueError('ORT profile event budget exceeded or trace is not an array')
    providers, operators, unique = Counter(), defaultdict(Counter), defaultdict(set)
    cuda_compute = 0
    for event in events:
        if not isinstance(event, dict) or event.get('cat') != 'Node':
            continue
        args = event.get('args')
        if not isinstance(args, dict) or not args.get('provider'):
            continue  # Fences and session events do not prove provider compute.
        provider, op, name = args['provider'], args.get('op_name'), event.get('name')
        if any(not isinstance(x, str) or not 1 <= len(x) <= 1024 for x in (provider, op, name)):
            raise ValueError('Invalid provider/operator fields in ORT profile')
        if not name.endswith('_kernel_time'):
            continue
        providers[provider] += 1
        operators[provider][op] += 1
        unique[provider].add((name, op))
        if provider == 'CUDAExecutionProvider' and 'memcpy' not in op.lower() and 'memcpy' not in name.lower():
            cuda_compute += 1
    for provider in ('CUDAExecutionProvider', 'CPUExecutionProvider'):
        providers.setdefault(provider, 0)
        operators.setdefault(provider, Counter())
        unique.setdefault(provider, set())
    return {'path': str(raw_path.resolve()), 'sha256': hashlib.sha256(data).hexdigest(),
            'bytes': len(data), 'traceEvents': len(events),
            'nodeExecutionCountsByProvider': dict(sorted(providers.items())),
            'uniqueExecutedNodeCountsByProvider': {p: len(v) for p, v in sorted(unique.items())},
            'operatorExecutionCountsByProvider': {p: dict(sorted(v.items())) for p, v in sorted(operators.items())},
            'cudaNonMemcpyComputeEvents': cuda_compute, 'gpuComputeObserved': cuda_compute > 0,
            'scope': 'executed kernel events and unique profiled node names, not all graph nodes; memcpy alone does not verify CUDA compute'}


def _iou(a, b):
    intersection = max(0., min(a[2], b[2]) - max(a[0], b[0])) * max(0., min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union


def _cells(box):
    # Input dimensions are bounded, so even a full-scene box covers <= 31*31 cells.
    return [(x, y) for x in range(int(box[0] // 64), int(math.ceil(box[2] / 64)))
            for y in range(int(box[1] // 64), int(math.ceil(box[3] / 64)))]


def deduplicate(candidates: list[dict], policy: ObserverPolicy) -> tuple[list[dict], int]:
    if len(candidates) > 5 * policy.max_slots_per_view:
        raise ValueError('Candidate work limit exceeded')
    kept, grid, comparisons = [], {}, 0
    for person in sorted(candidates, key=lambda p: (-p['confidence'], p['sourceView'], p['sourceSlot'])):
        cells = _cells(person['boxPixels'])
        neighbours = set()
        for cell in cells:
            neighbours.update(grid.get(cell, ()))
        duplicate = False
        for index in sorted(neighbours):
            if comparisons >= policy.max_iou_comparisons:
                raise ValueError('Dedup comparison budget exceeded; coverage result unavailable')
            comparisons += 1
            if _iou(person['boxPixels'], kept[index]['boxPixels']) >= policy.dedup_iou:
                duplicate = True
                break
        if not duplicate:
            index = len(kept)
            kept.append(person)
            for cell in cells:
                grid.setdefault(cell, []).append(index)
    return kept, comparisons


class CrowdObserver:
    """One reusable batch-one session, exactly five view calls per frame."""

    def __init__(self, session, *, policy: ObserverPolicy | None = None, runtime: dict | None = None,
                 profile_prefix: Path | None = None, yield_guard=None):
        self.policy = policy or ObserverPolicy()
        self.session = session
        self.metadata = validate_session_metadata(session, self.policy)
        self.runtime = runtime or {'device': 'stub', 'gpuPeakMemoryBytes': None}
        self.profile_prefix = profile_prefix
        self.yield_guard = yield_guard
        self._profile_finished = False

    def finish_profile(self):
        if self.profile_prefix is None:
            return None
        if self._profile_finished:
            raise RuntimeError('Operator profile already finalized')
        self._profile_finished = True
        try:
            path = self.session.end_profiling()
        except Exception as error:
            raise RuntimeError(f'ORT profile finalization failed: {str(error)[:2000]}') from error
        summary = summarize_operator_profile(Path(path), self.profile_prefix)
        verified = self.runtime.get('device') == 'cuda' and summary['gpuComputeObserved']
        self.runtime.update(gpuVerified=verified,
                            gpuVerification='profiled-cuda-compute' if verified else 'no-cuda-compute-proven')
        return summary

    def _map_outputs(self, outputs, geometry, width, height, ratio, view_index):
        if not isinstance(outputs, (list, tuple)) or len(outputs) != 2:
            raise ValueError('Expected two RTMO output tensors')
        dets, joints = outputs
        if (not isinstance(dets, np.ndarray) or not isinstance(joints, np.ndarray)
                or dets.dtype != np.float32 or joints.dtype != np.float32
                or dets.ndim != 3 or dets.shape[0] != 1 or dets.shape[2] != 5
                or joints.shape != (1, dets.shape[1], 17, 3)
                or dets.shape[1] > self.policy.max_slots_per_view):
            raise ValueError('Invalid runtime RTMO shape/type: require [1,S,5], [1,S,17,3] within slot budget')
        if not np.isfinite(dets).all() or not np.isfinite(joints).all():
            raise ValueError('Non-finite RTMO output')
        declared_slots = self.metadata['metadataSlotCount']
        if declared_slots is not None and dets.shape[1] != declared_slots:
            raise ValueError('Runtime slot count contradicts static model metadata')
        if ((dets[..., 4] < 0).any() or (dets[..., 4] > 1).any()
                or (joints[..., 2] < 0).any() or (joints[..., 2] > 1).any()):
            raise ValueError('Confidence must be in [0,1]')
        x, y, right, bottom = geometry
        vw, vh = right - x, bottom - y
        mapped, score_eligible, invalid_geometry = [], 0, 0
        for slot, (det, pose) in enumerate(zip(dets[0], joints[0])):
            if det[4] < self.policy.score_threshold:
                continue
            score_eligible += 1
            box = det[:4].astype(np.float64) / ratio
            clipped = box.copy()
            clipped[[0, 2]] = clipped[[0, 2]].clip(0, vw)
            clipped[[1, 3]] = clipped[[1, 3]].clip(0, vh)
            if np.any(clipped[2:] - clipped[:2] < self.policy.min_box_pixels):
                invalid_geometry += 1
                continue
            was_clipped = bool(np.any(box != clipped))
            kp = pose.astype(np.float64).copy()
            kp[:, :2] /= ratio
            outside = (kp[:, 0] < 0) | (kp[:, 0] >= vw) | (kp[:, 1] < 0) | (kp[:, 1] >= vh)
            kp[outside, 2] = 0
            kp[:, 0] = kp[:, 0].clip(0, vw) + x
            kp[:, 1] = kp[:, 1].clip(0, vh) + y
            clipped += [x, y, x, y]
            normalized = kp.copy()
            normalized[:, :2] /= [width, height]
            mapped.append({'category': 'person', 'boxPixels': clipped.tolist(),
                           'boxNormalized': (clipped / [width, height, width, height]).tolist(),
                           'confidence': float(det[4]), 'keypointsPixels': kp.tolist(),
                           'keypointsNormalized': normalized.tolist(),
                           'personPixelHeight': float(clipped[3] - clipped[1]),
                           'clippedByView': was_clipped,
                           'sourceView': view_index, 'sourceSlot': slot})
        slots = dets.shape[1]
        return mapped, {'rawSlots': slots, 'scoreEligibleSlots': score_eligible,
                        'eligibleObservations': len(mapped), 'rejectedGeometry': invalid_geometry,
                        'allReturnedSlotsEligible': slots > 0 and len(mapped) == slots,
                        'atConfiguredSlotSafetyLimit': slots == self.policy.max_slots_per_view,
                        'modelTopKLimitKnown': False,
                        'runtimeDetectionShape': list(dets.shape), 'runtimeKeypointShape': list(joints.shape)}

    def observe(self, frame: np.ndarray, timestamp_ms: float) -> dict:
        if isinstance(timestamp_ms, bool) or not isinstance(timestamp_ms, (int, float)) or not math.isfinite(timestamp_ms) or timestamp_ms < 0:
            raise ValueError('Invalid source timestamp')
        cv2.setNumThreads(1)
        started = perf_counter()
        width, height = validate_frame(frame)
        views, candidates = [], []
        yield_ms = 0.
        for index, geometry in enumerate(view_geometry(width, height)):
            guard_started = perf_counter()
            if self.yield_guard is not None:
                self.yield_guard()
            view_yield_ms = (perf_counter() - guard_started) * 1000
            yield_ms += view_yield_ms
            x, y, right, bottom = geometry
            tensor, ratio = letterbox(frame[y:bottom, x:right])
            call_started = perf_counter()
            try:
                outputs = self.session.run(['dets', 'keypoints'], {'input': tensor})
            except Exception as error:
                raise RuntimeError(f'ORT observer view {index} failed: {str(error)[:2000]}') from error
            elapsed_ms = (perf_counter() - call_started) * 1000
            mapped, telemetry = self._map_outputs(outputs, geometry, width, height, ratio, index)
            candidates.extend(mapped)
            views.append({'viewIndex': index, 'kind': 'global' if index == 0 else 'native-tile',
                          'geometryPixels': list(geometry), 'letterboxRatio': ratio,
                          'demoYieldHostWallMs': view_yield_ms,
                          'ortRunHostWallMs': elapsed_ms, **telemetry})
        unique, comparisons = deduplicate(candidates, self.policy)
        retained = unique[:self.policy.max_observations]
        for person in retained:
            # A tensor slot is not a temporal track or identity; do not export it as one.
            person.pop('sourceSlot')
        return {'timestampMs': float(timestamp_ms), 'frameWidth': width, 'frameHeight': height,
                'observations': retained, 'views': views,
                'coverage': {'status': 'observer-only', 'analyzedViews': len(views), 'requiredViews': 5,
                             'rawReturnedSlots': sum(v['rawSlots'] for v in views),
                             'eligibleBeforeDedup': len(candidates), 'deduplicatedBeforeCap': len(unique),
                             'duplicateObservationsRemoved': len(candidates) - len(unique),
                             'returnedObservations': len(retained),
                             'omittedByCap': max(0, len(unique) - len(retained)),
                             'observationCap': self.policy.max_observations,
                             'dedupIoUThreshold': self.policy.dedup_iou,
                             'dedupIoUComparisons': comparisons,
                             'dedupComparisonBudget': self.policy.max_iou_comparisons,
                             'visibleHumanCount': None, 'visibleHumanRecall': None,
                             'fightAnalyzedPeople': None, 'fightAnalysisStatus': 'not-run',
                             'localizationOfFight': None},
                'timing': {'totalObserverHostWallMs': (perf_counter() - started) * 1000,
                           'demoYieldHostWallMs': yield_ms,
                           'scope': 'total includes demo yielding, preprocessing, synchronous ORT calls, CPU outputs and mapping/dedup; per-view ORT time excludes demo yielding; not isolated GPU kernel time',
                           'gpuPeakMemoryBytes': None}}
