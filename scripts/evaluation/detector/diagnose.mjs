import fs from 'node:fs/promises';import path from 'node:path';import {parseArgs} from 'node:util';import {pathToFileURL} from 'node:url';import {build} from 'vite';import {validateCache} from './cacheContract.mjs';
const {values:args}=parseArgs({options:{split:{type:'string',default:'train'},'work-dir':{type:'string',default:'D:/nivra-work/detector'},out:{type:'string'}}});
if(!['train','dev'].includes(args.split))throw new Error('Invalid split');
const work=path.resolve(args['work-dir']),repo=path.resolve(import.meta.dirname,'../../..'),capture=JSON.parse(await fs.readFile(path.join(work,args.split+'-capture.private.json')));
if(capture.completed.length!==capture.summary.recordings||capture.failures.length)throw new Error('Incomplete capture');
await build({configFile:false,logLevel:'error',build:{lib:{entry:path.join(repo,'src/lib/originalConflictEngine.ts'),formats:['es'],fileName:()=> 'diagnosticEngine.mjs'},outDir:path.join(work,'runtime'),emptyOutDir:false,minify:false}});
const {ConflictEngine}=await import(pathToFileURL(path.join(work,'runtime/diagnosticEngine.mjs')));
const count=(object,key)=>{object[key]=(object[key]??0)+1};
const empty=()=>({motionFrames:0,poseCountHistogram:{},usablePeopleHistogram:{},reasonHistogram:{},framesWithNearbyPair:0,framesWithDirectedPulse:0,maximumProgress:0});
const total={recordings:capture.completed.length,...empty()},eventIntervals=empty();
const observe=(target,s,frame)=>{target.motionFrames++;count(target.poseCountHistogram,frame.poses.length);count(target.usablePeopleHistogram,s.people);count(target.reasonHistogram,s.diagnostics.reason);target.framesWithNearbyPair+=s.diagnostics.nearbyPairs>0;target.framesWithDirectedPulse+=s.progress>0;target.maximumProgress=Math.max(target.maximumProgress,s.progress)};
for(const r of capture.completed){
 const c=JSON.parse(await fs.readFile(r.cachePath));validateCache(c,r);const engine=new ConflictEngine({cooldownScope:'pair'});
 for(const frame of c.frames.filter(f=>f.lane==='motion')){const s=engine.update(frame.timestampMs,frame.poses,c.sourceWidth/c.sourceHeight);observe(total,s,frame);if(r.events.some(i=>frame.timestampMs>=i.startMs&&frame.timestampMs<i.endMs))observe(eventIntervals,s,frame)}
}
const result={schemaVersion:1,split:args.split,manifestSHA256:capture.manifestSHA256,meaning:'Aggregate original-rule diagnostics over admitted motion samples; model observations, not verified people or action ground truth.',...total,eventIntervals};
if(args.out){const out=path.resolve(args.out);if(!out.toLowerCase().startsWith(path.join(repo,'docs/evaluations/detector-accuracy').toLowerCase()+path.sep))throw new Error('Unexpected aggregate path');await fs.writeFile(out,JSON.stringify(result,null,2))}
console.log(JSON.stringify(result,null,2));
