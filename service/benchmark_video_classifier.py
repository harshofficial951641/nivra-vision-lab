"""RAM-only synthetic 4x720p40 transport/decode/classifier benchmark. No sockets.

Run from service: python benchmark_video_classifier.py --device cpu --seconds 30
Only JSON metrics may be written; encoded/decoded synthetic video stays in RAM.
"""
import argparse
import asyncio
import json
from pathlib import Path
import platform
import statistics
import sys
import time

from nivra.video_classifier import VideoClassifier

sys.path.insert(0, str(Path(__file__).parent/'tests'))
from video_classifier_fixtures import batches, synthetic_video


def percentile(values, q):
    ordered=sorted(values)
    return ordered[min(len(ordered)-1, round((len(ordered)-1)*q))] if ordered else None


async def benchmark(device, seconds):
    print('Preparing 4x720p40 synthetic RAM source', flush=True)
    _,header,frames=synthetic_video(seconds=seconds,width=1280,height=720,fps=40)
    packets=list(batches(header,frames))
    scores=[]
    previews=0
    def receive(camera,message):
        nonlocal previews
        if message['type']=='score': scores.append((time.monotonic(),camera,message))
        elif message['type']=='preview': previews+=1
    service=VideoClassifier(mode='on',device=device)
    await service.attach('benchmark',receive)
    try:
        deadline=time.monotonic()+90
        while service.status=='loading' and time.monotonic()<deadline:
            await asyncio.sleep(.025)
        if service.status!='ready': raise RuntimeError(service.snapshot('benchmark'))
        lags=[]
        running=True
        async def ticker():
            while running:
                start=time.monotonic()
                await asyncio.sleep(.01)
                lags.append(max(0,time.monotonic()-start-.01)*1000)
        tick=asyncio.create_task(ticker())
        start=time.monotonic()
        for data,packet in packets:
            due=start+data['frames'][-1]['timestampMs']/1000
            await asyncio.sleep(max(0,due-time.monotonic()))
            for camera in range(4):
                service.submit('benchmark',str(camera),'socket-1',packet,video_generation=header['generation'],
                               keyframe=any(f['keyframe'] for f in data['frames']))
        await asyncio.sleep(1)
        running=False
        await tick
        latest={camera:(t,m) for t,camera,m in scores}
        elapsed=max((t-start for t,_,_ in scores),default=seconds)
        metrics=service.worker_metrics
        inference=metrics.get('inferenceMs',[])
        rates={}
        for camera in map(str,range(4)):
            values=[t for t,c,m in scores if c==camera]
            rates[camera]=dict(windows=len(values),windowsPerSecond=(len(values)-1)/(values[-1]-values[0]) if len(values)>1 else 0)
        return dict(device=service.device,requestedDevice=device,platform=platform.platform(),python=sys.version.split()[0],
            synthetic=dict(cameras=4,width=1280,height=720,fps=40,seconds=seconds),
            status=service.status,detail=service.detail,droppedPackets=service.dropped,previews=previews,
            decodedFrames=metrics.get('decodedFrames'),workerMetrics=metrics,
            decodeCpuPercentOneCore=metrics.get('decodeCpuMs',0)/(seconds*10),
            decodeCpuPercentMachine=metrics.get('decodeCpuMs',0)/(seconds*10*(__import__('os').cpu_count() or 1)),
            inferenceMs=dict(p50=percentile(inference,.5),p95=percentile(inference,.95),samples=len(inference)),
            batchSizes=sorted({m['batchSize'] for _,_,m in scores}),perCamera=rates,
            loopLagMs=dict(p50=percentile(lags,.5),p95=percentile(lags,.95),max=max(lags,default=0)),
            scope='Real-time synthetic transport/decode/resize/model/preview IPC; excludes browser, network, rules and accuracy. Decode CPU includes ring resize, excludes model/JPEG. One-core CPU is 100% per core. Short PC run, not Mac capacity.')
    finally:
        await service.detach('benchmark')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--device',choices=['cpu','cuda','mps','auto'],default='auto')
    parser.add_argument('--seconds',type=int,default=30)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--gpu-lock-source',type=Path,help='Optional existing shared GPU-lock Python module for coordinated PC measurements')
    args=parser.parse_args()
    if not 8<=args.seconds<=900: parser.error('Use 8..900 seconds')
    from contextlib import nullcontext
    lock=nullcontext()
    if args.gpu_lock_source:
        import importlib.util
        spec=importlib.util.spec_from_file_location('nivra_benchmark_gpu_lock',args.gpu_lock_source)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        lock=module.gpu_lock('C1:browser-movinet-benchmark',timeout=3600)
    with lock:
        result=asyncio.run(benchmark(args.device,args.seconds))
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
