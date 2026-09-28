"""Reproducible local evaluation. Calibration and holdout recordings never mix."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
import cv2
import numpy as np
from nivra.decision import Thresholds

ROOT = Path(__file__).resolve().parent


def validate_manifest(records):
    groups = {}
    ids = set()
    for clip in records:
        if clip['id'] in ids:
            raise ValueError('Duplicate clip ID')
        ids.add(clip['id'])
        if clip['annotationStatus'] != 'reviewed':
            raise ValueError(f"Unreviewed labels: {clip['id']}")
        group, split = clip['sourceGroup'], clip['split']
        if split not in ('calibration', 'holdout'):
            raise ValueError('Unknown split')
        if group in groups and groups[group] != split:
            raise ValueError('Recording leakage across calibration and holdout')
        groups[group] = split
        for event in clip['events']:
            if not 0 <= event['startMs'] <= event['endMs'] <= clip['durationMs']:
                raise ValueError('Invalid event interval')


def score_clip(clip, result):
    predictions = sorted(result['events'], key=lambda e: e['occurredAtMs'])
    matched = set()
    delays = []
    for truth in clip['events']:
        candidates = [i for i, p in enumerate(predictions) if i not in matched and
                      truth['startMs'] <= p['occurredAtMs'] <= truth['endMs'] + 3000]
        if candidates:
            index = candidates[0]
            matched.add(index)
            delays.append(max(0, predictions[index]['occurredAtMs'] - truth['startMs']))
    return dict(events=len(clip['events']), detected=len(matched), missed=len(clip['events'])-len(matched),
                falseAlerts=len(predictions)-len(matched), minutes=clip['durationMs']/60000,
                delayMs=delays, split=clip['split'], conditions=clip.get('conditions', []),
                synthetic=bool(clip.get('crop')), trackingMetrics='unavailable: person-level ground truth not annotated')


def run(manifest, output, person_model='yolox', max_people=4, regional_actions=False, fight_model='ava'):
    from nivra.models import Models
    from nivra.pipeline import Pipeline
    records = json.loads(manifest.read_text())
    validate_manifest(records)
    models = Models(person_model=person_model, fight_model=fight_model)
    report = dict(schemaVersion=1, backend='local-ai', runtime=models.runtime,
                  manifestSha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                  pipelineSha256=hashlib.sha256((ROOT/'nivra/pipeline.py').read_bytes()).hexdigest(),
                  implementationHashes={name:hashlib.sha256((ROOT/'nivra'/name).read_bytes()).hexdigest() for name in ('pipeline.py','decision.py','models.py','regions.py','x3d_candidate.py')},
                  x3dPolicy=dict(windowMs=4000,minimumSpanMs=3800,threshold=.4,strongThreshold=.7,confirmationGapMs=1000),
                  modelManifestSha256=hashlib.sha256((ROOT/'model-manifest.json').read_bytes()).hexdigest(),
                  maxPeople=max_people,
                  regionalActions=regional_actions,
                  thresholds=asdict(Thresholds()), thresholdSha256=hashlib.sha256(json.dumps(asdict(Thresholds()), sort_keys=True).encode()).hexdigest(),
                  validation='experimental; small smoke corpus, not representative accuracy proof', clips={})
    for clip in records:
        path = (manifest.parent / clip['path']).resolve()
        if hashlib.sha256(path.read_bytes()).hexdigest() != clip['sha256']:
            raise ValueError(f"Clip checksum mismatch: {clip['id']}")
        capture = cv2.VideoCapture(str(path))
        pipeline = Pipeline(models, regional_actions=regional_actions)
        observations, latencies, events = [], [], {}
        last = -1e9
        start = time.perf_counter()
        while True:
            ok, frame = capture.read()
            if not ok: break
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC)
            if timestamp - last < 65: continue
            last = timestamp
            if clip.get('crop'):
                h,w = frame.shape[:2]
                x,y,right,bottom = clip['crop']
                frame = frame[round(y*h):round(bottom*h),round(x*w):round(right*w)]
            h,w = frame.shape[:2]
            factor = min(1, 960/max(h,w))
            frame = cv2.resize(frame,(round(w*factor),round(h*factor)))
            result = pipeline.process(frame, timestamp, max_people)
            latencies.append(result['inferenceMs'])
            observations.append(dict(timestampMs=timestamp, tracks=result['tracks'], actions=result['actions'], status=result['conflict']['status']))
            events.update({e['id']:e for e in result['conflict']['events']})
        capture.release()
        report['clips'][clip['id']] = dict(events=list(events.values()), samples=observations,
                                         p50InferenceMs=float(np.percentile(latencies,50)), p95InferenceMs=float(np.percentile(latencies,95)),
                                         processedFps=len(latencies)/(time.perf_counter()-start))
        report['clips'][clip['id']]['metrics'] = score_clip(clip,report['clips'][clip['id']])
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2))
        print(clip['id'],report['clips'][clip['id']]['metrics'],flush=True)
    import torch
    report['peakTorchAllocatedMiB'] = torch.cuda.max_memory_allocated()/1024**2 if torch.cuda.is_available() else 0
    report['memoryNote'] = 'PyTorch allocator only; ONNX Runtime memory is additional. Not a system VRAM peak.'
    output.write_text(json.dumps(report,indent=2))


def compare(manifest, before_path, after_path, output):
    records = json.loads(manifest.read_text()); validate_manifest(records)
    before, after = json.loads(before_path.read_text()), json.loads(after_path.read_text())
    expected = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if any(report.get('manifestSha256') != expected for report in (before,after)):
        raise ValueError('Both runs must use this exact frozen manifest')
    rows=[]
    for clip in records:
        rows.append(dict(id=clip['id'],before=score_clip(clip,before['clips'][clip['id']]),after=score_clip(clip,after['clips'][clip['id']])))
    held=[row for row in rows if row['before']['split']=='holdout' and not row['before']['synthetic']]
    missed_before=sum(r['before']['missed'] for r in held); missed_after=sum(r['after']['missed'] for r in held)
    false_before=sum(r['before']['falseAlerts'] for r in held); false_after=sum(r['after']['falseAlerts'] for r in held)
    result=dict(rows=rows,holdoutMissedReduction=(missed_before-missed_after)/missed_before if missed_before else None,
                noMoreFalseAlerts=false_after<=false_before,
                releaseGate='NOT PASSED: corpus coverage, live delay, and tracking ground truth remain incomplete',
                limitations=['No representative webcam holdout', 'No slap/shove/handshake/hug/crossing coverage',
                             'Offline source-time delay is not live end-to-end latency', 'No identity-switch ground truth'])
    output.write_text(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--person-model', choices=('yolox', 'rtmo'), default='yolox')
    parser.add_argument('--max-people', type=int, choices=range(2, 51), default=4)
    parser.add_argument('--regional-actions', action='store_true')
    parser.add_argument('--fight-model', choices=('ava','x3d'), default='ava')
    parser.add_argument('--compare',nargs=2,type=Path,metavar=('BASELINE','CANDIDATE'))
    args=parser.parse_args()
    if args.compare: compare(args.manifest,*args.compare,args.output)
    else: run(args.manifest,args.output,args.person_model,args.max_people,args.regional_actions,args.fight_model)
