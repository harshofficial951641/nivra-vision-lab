"""Local transport/scheduler smoke benchmark. Not four-classroom accuracy proof.

Run the service with NIVRA_METADATA_DB pointing to a disposable database first.
This runner refuses to replace any non-QA camera. Video is read only in memory.
"""
import argparse
import asyncio
import json
from pathlib import Path
import struct
import subprocess
import time
from urllib.parse import parse_qs, urlsplit
import cv2
import httpx
import numpy as np
from websockets.asyncio.client import connect

ORIGIN='http://127.0.0.1:8765'


async def run(source,output,duration,count):
    capture=cv2.VideoCapture(str(source));fps=capture.get(cv2.CAP_PROP_FPS)
    frames=[];index=0
    while True:
        ok,frame=capture.read()
        if not ok:break
        if index % max(1,round(fps/12)) == 0:
            h,w=frame.shape[:2];frame=cv2.resize(frame,(640,round(h*640/w)))
            frames.append(cv2.imencode('.jpg',frame,[cv2.IMWRITE_JPEG_QUALITY,72])[1].tobytes())
        index+=1
    capture.release()
    if not frames:raise ValueError('No readable frames')
    async with httpx.AsyncClient(base_url=ORIGIN,headers={'origin':ORIGIN},timeout=20) as client:
        (await client.post('/api/v2/session')).raise_for_status()
        state=(await client.get('/api/v2/state')).json()
        if any(not c['name'].startswith('QA ') for c in state['cameras']):raise ValueError('Use a disposable database with QA cameras only.')
        if state['service']!='ready':raise ValueError('Wait for models to load')
        cameras=state['cameras'][:count]
        for n in range(len(cameras),count):
            response=await client.post('/api/v2/cameras',json=dict(name=f'QA benchmark {n+1}',building='Synthetic benchmark',floor='Not a real classroom'))
            response.raise_for_status();cameras.append(response.json())
        credentials=[]
        for camera in cameras:
            await client.patch('/api/v2/cameras/'+camera['id'],json={**{k:camera[k] for k in ('name','building','floor')},'enabled':True})
            pairing=(await client.post('/api/v2/cameras/'+camera['id']+'/pair')).json()
            token=parse_qs(urlsplit(pairing['url']).fragment)['pair'][0]
            response=await client.post('/api/v2/camera/pair',json={'token':token});response.raise_for_status()
            credentials.append(response.cookies['nivra_publisher'])
        stop=asyncio.Event();started=time.perf_counter();transport=[[] for _ in cameras]
        async def publish(number,credential):
            async with connect(ORIGIN.replace('http','ws')+'/api/v2/camera/stream',origin=ORIGIN,
                               additional_headers={'Cookie':'nivra_publisher='+credential},max_size=1500000) as socket:
                await socket.recv();sequence=0
                while not stop.is_set():
                    before=time.perf_counter();timestamp=(before-started)*1000
                    header=json.dumps(dict(version=1,streamId=0,timestampMs=timestamp,maxPeople=4)).encode()
                    await socket.send(struct.pack('<I',len(header))+header+frames[sequence%len(frames)])
                    await socket.recv();transport[number].append((time.perf_counter()-before)*1000)
                    sequence+=1;await asyncio.sleep(max(0,1/12-(time.perf_counter()-before)))
        tasks=[asyncio.create_task(publish(i,credential)) for i,credential in enumerate(credentials)]
        samples=[];gpu=[]
        try:
            while time.perf_counter()-started < duration:
                await asyncio.sleep(1)
                for task in tasks:
                    if task.done(): task.result()
                state=(await client.get('/api/v2/state')).json()
                samples.append({'elapsedSeconds':time.perf_counter()-started,'cameras':[
                    {k:c.get(k) for k in ('id','feed','analysis','framesReceived','framesAnalyzed','framesReplaced','result')}
                    for c in state['cameras'] if c['id'] in {a['id'] for a in cameras}]})
                if len(samples)%5==0:
                    result=await asyncio.to_thread(subprocess.run,['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    if result.returncode==0:gpu.append(result.stdout.strip())
        finally:
            stop.set();await asyncio.gather(*tasks,return_exceptions=True)
        elapsed=time.perf_counter()-started
        summary={'durationSeconds':elapsed,'cameraCount':count,'captureTargetFps':12,'source':source.name,
            'limitation':'Repeated copies of one public two-person clip. No classroom accuracy or real mobile-network verification.',
            'runtime':state['runtime'],'gpuSamplesMiBAndUtilization':gpu,'gpuNote':'Whole GPU including desktop and other processes, sampled every five seconds.',
            'cameras':[dict(id=c['id'],received=c['framesReceived'],analyzed=c['framesAnalyzed'],replaced=c['framesReplaced'],processedFps=c['framesAnalyzed']/elapsed,
                            transportAckP95Ms=float(np.percentile(transport[i],95)) if transport[i] else None)
                       for i,c in enumerate(samples[-1]['cameras'])], 'samples':samples}
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(summary,indent=2))
        print(json.dumps({k:v for k,v in summary.items() if k!='samples'},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--seconds',type=int,default=60);parser.add_argument('--cameras',type=int,choices=(2,4),default=4)
    parser.add_argument('--confirm-disposable-db',action='store_true',required=True)
    args=parser.parse_args();asyncio.run(run(args.source,args.output,args.seconds,args.cameras))
