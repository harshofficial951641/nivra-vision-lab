"""Validated, local-only footage manifests for fitting and evaluating candidates.

Schema v1 keeps provenance, review status and recording lineage together. A
clip-level label describes the recording; only explicit temporal annotations
produce training windows. Loading does not decode media or infer consent.
"""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
from typing import Literal
from urllib.parse import urlparse


Split = Literal['train', 'calibration', 'holdout', 'diagnostic']
Label = Literal[0, 1]
SPLITS = ('train', 'calibration', 'holdout', 'diagnostic')
MODEL_SPLITS = ('train', 'calibration', 'holdout')
_EPSILON = 1e-9


class ManifestError(ValueError):
    """A manifest violates the provenance, annotation or split contract."""


@dataclass(frozen=True)
class Source:
    id: str
    url: str
    license: str
    evidence: tuple[str, ...]
    training_allowed: bool


@dataclass(frozen=True)
class Event:
    start_seconds: float
    end_seconds: float
    label: Label


@dataclass(frozen=True)
class Recording:
    id: str
    source_id: str
    recording_group: str
    path: Path
    sha256: str
    duration_seconds: float
    split: Split
    review_status: Literal['reviewed', 'pending']
    domain: str
    label: Label | None
    events: tuple[Event, ...]


@dataclass(frozen=True)
class TrainingManifest:
    schema_version: int
    data_root: Path
    sources: tuple[Source, ...]
    recordings: tuple[Recording, ...]


@dataclass(frozen=True)
class Window:
    recording_id: str
    recording_group: str
    path: Path
    sha256: str
    split: Split
    start_seconds: float
    end_seconds: float
    label: Label


def _object(value, fields, context):
    if not isinstance(value, dict):
        raise ManifestError(f'{context} must be an object')
    missing = set(fields) - value.keys()
    unknown = value.keys() - set(fields)
    if missing or unknown:
        raise ManifestError(f'{context} fields: missing {sorted(missing)}, unknown {sorted(unknown)}')
    return value


def _text(value, context):
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f'{context} must be nonempty text')
    return value.strip()


def _number(value, context):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ManifestError(f'{context} must be a finite number')
    return float(value)


def _label(value, context, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not int or value not in (0, 1):
        raise ManifestError(f'{context} must be 0 or 1' + (' or null' if nullable else ''))
    return value


def _list(value, context):
    if not isinstance(value, list):
        raise ManifestError(f'{context} must be an array')
    return value


def _local_path(value, root, context):
    raw = _text(value, context)
    # Reject Windows drives and UNC paths even if validation runs on Linux.
    portable = raw.replace('\\', '/')
    relative = Path(portable)
    if relative.is_absolute() or PureWindowsPath(raw).drive or '..' in relative.parts:
        raise ManifestError(f'{context} must be a relative path within data root')
    resolved = (root / relative).resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ManifestError(f'{context} escapes data root')
    return resolved


def load_manifest(path: str | Path, data_root: str | Path, verify_files: bool = False) -> TrainingManifest:
    """Read schema v1 and reject unlicensed, unreviewed or leaking model data.

    ``path`` fields are relative to ``data_root``. Resolution checks existing
    symlinks even when media has not been downloaded yet. ``verify_files`` adds
    file existence and SHA-256 checks; duration remains declared metadata and
    must be checked by the media ingestion/decoding step.
    """
    root = Path(data_root).resolve()
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ManifestError(f'Cannot read manifest: {error}') from error
    _object(raw, ('schemaVersion', 'sources', 'recordings'), 'manifest')
    if type(raw['schemaVersion']) is not int or raw['schemaVersion'] != 1:
        raise ManifestError('schemaVersion must be 1')
    sources = {}
    for item in _list(raw['sources'], 'sources'):
        _object(item, ('id', 'url', 'license', 'evidence', 'trainingAllowed'), 'source')
        source_id = _text(item['id'], 'source.id')
        if source_id in sources:
            raise ManifestError(f'Duplicate source id: {source_id}')
        url = _text(item['url'], f'{source_id}.url')
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ('http', 'https') or not parsed_url.netloc:
            raise ManifestError(f'{source_id}.url must be an HTTP(S) source URL')
        license_name = _text(item['license'], f'{source_id}.license')
        raw_evidence = item['evidence']
        if isinstance(raw_evidence, str):
            raw_evidence = [raw_evidence]
        evidence = tuple(_text(value, f'{source_id}.evidence')
                         for value in _list(raw_evidence, f'{source_id}.evidence'))
        if not evidence:
            raise ManifestError(f'{source_id}.evidence must document the media licence')
        if type(item['trainingAllowed']) is not bool:
            raise ManifestError(f'{source_id}.trainingAllowed must be an explicit boolean')
        sources[source_id] = Source(source_id, url, license_name, evidence, item['trainingAllowed'])

    recordings = []
    recording_ids = set()
    groups = {}
    hashes = {}
    for item in _list(raw['recordings'], 'recordings'):
        _object(item, ('id', 'sourceId', 'recordingGroup', 'path', 'sha256',
                       'durationSeconds', 'split', 'reviewStatus', 'domain', 'label', 'events'), 'recording')
        recording_id = _text(item['id'], 'recording.id')
        if recording_id in recording_ids:
            raise ManifestError(f'Duplicate recording id: {recording_id}')
        recording_ids.add(recording_id)
        source_id = _text(item['sourceId'], f'{recording_id}.sourceId')
        if source_id not in sources:
            raise ManifestError(f'{recording_id} references unknown source {source_id}')
        split = item['split']
        if split not in SPLITS:
            raise ManifestError(f'{recording_id}.split must be one of {SPLITS}')
        review = item['reviewStatus']
        if review not in ('reviewed', 'pending'):
            raise ManifestError(f'{recording_id}.reviewStatus must be reviewed or pending')
        label = _label(item['label'], f'{recording_id}.label', nullable=True)
        if split in MODEL_SPLITS:
            if not sources[source_id].training_allowed:
                raise ManifestError(f'{recording_id}: source permission does not allow model training/evaluation')
            if review != 'reviewed' or label is None:
                raise ManifestError(f'{recording_id}: model splits require reviewed, known labels')
        group = _text(item['recordingGroup'], f'{recording_id}.recordingGroup')
        digest = _text(item['sha256'], f'{recording_id}.sha256').lower()
        if not re.fullmatch('[0-9a-f]{64}', digest):
            raise ManifestError(f'{recording_id}.sha256 must contain 64 hexadecimal characters')
        for values, key, reason in ((groups, group, 'recordingGroup'), (hashes, digest, 'SHA-256')):
            if key in values and values[key] != split:
                raise ManifestError(f'{recording_id}: split leakage through {reason}')
            values[key] = split
        duration = _number(item['durationSeconds'], f'{recording_id}.durationSeconds')
        if duration <= 0:
            raise ManifestError(f'{recording_id}.durationSeconds must be positive')
        media_path = _local_path(item['path'], root, f'{recording_id}.path')
        events = []
        for event in _list(item['events'], f'{recording_id}.events'):
            _object(event, ('startSeconds', 'endSeconds', 'label'), f'{recording_id}.event')
            start = _number(event['startSeconds'], f'{recording_id}.event.startSeconds')
            end = _number(event['endSeconds'], f'{recording_id}.event.endSeconds')
            event_label = _label(event['label'], f'{recording_id}.event.label')
            if start < 0 or start >= end or end > duration:
                raise ManifestError(f'{recording_id}: event interval is invalid or out of bounds')
            events.append(Event(start, end, event_label))
        events.sort(key=lambda event: (event.start_seconds, event.end_seconds, event.label))
        for index, event in enumerate(events):
            for previous in events[:index]:
                if previous.end_seconds > event.start_seconds and previous.label != event.label:
                    raise ManifestError(f'{recording_id}: overlapping contradictory event intervals')
        if label == 0 and any(event.label == 1 for event in events):
            raise ManifestError(f'{recording_id}: normal recording label contradicts positive event')
        if split in MODEL_SPLITS and (not events or (label == 1 and not any(event.label == 1 for event in events))):
            raise ManifestError(f'{recording_id}: model data requires explicit temporal annotations matching label')
        domain = _text(item['domain'], f'{recording_id}.domain')
        if verify_files:
            if not media_path.is_file():
                raise ManifestError(f'{recording_id}: media file is missing')
            with media_path.open('rb') as stream:
                actual_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual_digest != digest:
                raise ManifestError(f'{recording_id}: media SHA-256 mismatch')
        recordings.append(Recording(recording_id, source_id, group, media_path, digest,
                                    duration, split, review, domain, label, tuple(events)))
    return TrainingManifest(1, root, tuple(sources.values()), tuple(recordings))


def _coverage(events, start, end, label):
    intervals = sorted((max(start, event.start_seconds), min(end, event.end_seconds))
                       for event in events if event.label == label
                       and event.end_seconds > start and event.start_seconds < end)
    total = 0.0
    previous_end = start
    for interval_start, interval_end in intervals:
        total += max(0.0, interval_end - max(interval_start, previous_end))
        previous_end = max(previous_end, interval_end)
    return total


def window_label(recording: Recording, start_seconds: float, end_seconds: float,
                 positive_fraction: float = .5) -> Label | None:
    """Label explicit temporal coverage; return None for ambiguous windows.

    At least half of a window must be explicitly positive (inclusive boundary).
    A negative requires complete explicit normal coverage. Unannotated gaps and
    short positive overlaps never silently become normal examples.
    """
    start = _number(start_seconds, 'window.startSeconds')
    end = _number(end_seconds, 'window.endSeconds')
    fraction = _number(positive_fraction, 'positive_fraction')
    if not .5 <= fraction <= 1:
        raise ManifestError('positive_fraction must be between .5 and 1')
    if start < 0 or end <= start or end > recording.duration_seconds:
        raise ManifestError('Window interval is invalid or out of bounds')
    if recording.review_status != 'reviewed' or recording.split not in MODEL_SPLITS:
        return None
    duration = end - start
    positive = _coverage(recording.events, start, end, 1)
    if positive + _EPSILON >= duration * fraction:
        return 1
    normal = _coverage(recording.events, start, end, 0)
    if normal + _EPSILON >= duration:
        return 0
    return None


def generate_windows(manifest: TrainingManifest, split: Split, window_seconds: float = 4.0,
                     stride_seconds: float = 4.0, positive_fraction: float = .5) -> tuple[Window, ...]:
    """Return full windows only, with a final end-aligned window when needed.

    Clips shorter than the window are omitted, rather than stretched/repeated.
    The diagnostic split cannot enter fitting or model-selection evaluation.
    """
    if split not in MODEL_SPLITS:
        raise ManifestError('Windows may only be generated for train, calibration or holdout')
    length = _number(window_seconds, 'window_seconds')
    stride = _number(stride_seconds, 'stride_seconds')
    fraction = _number(positive_fraction, 'positive_fraction')
    if length <= 0 or stride <= 0:
        raise ManifestError('Window length and stride must be positive')
    if not .5 <= fraction <= 1:
        raise ManifestError('positive_fraction must be between .5 and 1')
    windows = []
    for recording in manifest.recordings:
        if recording.split != split or recording.review_status != 'reviewed':
            continue
        if recording.duration_seconds < length:
            continue
        last_start = recording.duration_seconds - length
        count = int(math.floor(last_start / stride)) + 1
        starts = [index * stride for index in range(count)]
        if last_start - starts[-1] > _EPSILON:
            starts.append(last_start)
        for start in starts:
            end = min(start + length, recording.duration_seconds)
            label = window_label(recording, start, end, fraction)
            if label is not None:
                windows.append(Window(recording.id, recording.recording_group, recording.path,
                                      recording.sha256, split, start, end, label))
    return tuple(windows)
