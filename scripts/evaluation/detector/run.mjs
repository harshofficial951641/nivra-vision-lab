import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { createServer, build } from 'vite';
import { chromium } from '@playwright/test';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';
import {validateCache} from './cacheContract.mjs';

const {values:args}=parseArgs({options:{manifest:{type:'string'},'expected-sha':{type:'string'},'work-dir':{type:'string',default:'D:/nivra-work/detector'},'max-groups':{type:'string'},'max-videos':{type:'string'},port:{type:'string',default:'5199'},profile:{type:'string'},inventory:{type:'boolean'},ids:{type:'string'},'allow-partial':{type:'boolean'}}});
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const repo=path.resolve(import.meta.dirname,'../../..');
const work=path.resolve(args['work-dir']);
if(work.toLowerCase()===repo.toLowerCase()||work.toLowerCase().startsWith(repo.toLowerCase()+path.sep))throw new Error('Private cache must be outside the repository');
if(!args.manifest)throw new Error('--manifest is required');
const bytes=await fsp.readFile(args.manifest),manifestSHA256=hash(bytes),manifest=JSON.parse(bytes);
if(!['train','dev'].includes(manifest.split))throw new Error('Only train/dev manifests are accepted');
const seen=new Set();
for(const r of manifest.recordings){
 if(seen.has(r.id))throw new Error('Duplicate recording ID'); seen.add(r.id);
 if(!r.group||r.split!==manifest.split||!Number.isFinite(r.durationMs)||r.durationMs<=0||!/^[a-f0-9]{64}$/.test(r.sha256))throw new Error('Invalid recording contract');
 const all=[...r.events.map(i=>({...i,kind:'event'})),...r.normalIntervals.map(i=>({...i,kind:'normal'}))].sort((a,b)=>a.startMs-b.startMs);
 for(let n=0;n<all.length;n++){const i=all[n];if(!Number.isFinite(i.startMs)||!Number.isFinite(i.endMs)||i.startMs<0||i.endMs<=i.startMs||i.endMs>r.durationMs+1)throw new Error('Invalid label bounds: '+r.id);if(n&&i.startMs<all[n-1].endMs-.001)throw new Error('Overlapping labels: '+r.id)}
}
if(manifest.split==='dev'&&(args.ids||args['max-videos']))throw new Error('Scored dev subsampling is prohibited');
for(const key of ['max-groups','max-videos'])if(args[key]&&(!Number.isSafeInteger(Number(args[key]))||Number(args[key])<1))throw new Error('Invalid positive limit: '+key);
let recordings=manifest.recordings.filter(r=>r.events.length||r.normalIntervals.length);
if(args.ids){const ids=new Set(args.ids.split(','));recordings=recordings.filter(r=>ids.has(r.id))}
if(args['max-groups']){
 if(manifest.split!=='train')throw new Error('Dev group subsampling is prohibited');
 const groups=[...new Set(recordings.map(r=>r.group))].sort((a,b)=>hash(a).localeCompare(hash(b))).slice(0,Number(args['max-groups']));
 recordings=recordings.filter(r=>groups.includes(r.group));
}
if(args['max-videos'])recordings=recordings.slice(0,Number(args['max-videos']));
const summary={split:manifest.split,manifestSHA256,recordings:recordings.length,groups:new Set(recordings.map(r=>r.group)).size,events:recordings.reduce((a,r)=>a+r.events.length,0),normalMs:recordings.reduce((a,r)=>a+r.normalIntervals.reduce((b,i)=>b+i.endMs-i.startMs,0),0),sourceDurationMs:recordings.reduce((a,r)=>a+r.durationMs,0),missingMedia:recordings.filter(r=>!fs.existsSync(r.path)).length};
console.log(JSON.stringify({inventory:summary}));
if(args.inventory)process.exit(0);
if(!args['expected-sha']||args['expected-sha']!==manifestSHA256)throw new Error('Supply the approved exact --expected-sha; never silently substitute a snapshot');
if(summary.missingMedia)throw new Error('Media missing; do not silently score a subset');
const sibling=path.join(path.dirname(args.manifest),'vid-v4-'+(manifest.split==='train'?'dev':'train')+'.json');
const other=JSON.parse(await fsp.readFile(sibling));
const otherGroups=new Set(other.recordings.map(r=>r.group)),otherHashes=new Set(other.recordings.map(r=>r.sha256));
if(manifest.recordings.some(r=>otherGroups.has(r.group)||otherHashes.has(r.sha256)))throw new Error('Train/dev group or exact-media leakage');
await fsp.mkdir(path.join(work,'cache'),{recursive:true});
await fsp.mkdir(path.join(work,'runtime'),{recursive:true});
await build({configFile:false,logLevel:'error',build:{lib:{entry:path.join(import.meta.dirname,'replayEngine.ts'),formats:['es'],fileName:()=> 'replayEngine.mjs'},outDir:path.join(work,'runtime'),emptyOutDir:false,minify:false}});
const {replayBaseline,replayCandidate,CANDIDATES}=await import(pathToFileURL(path.join(work,'runtime/replayEngine.mjs')).href+'?t='+Date.now());
const selected=args.profile?CANDIDATES.find(c=>c.name===args.profile):null;
if(args.profile&&(!selected||manifest.split!=='train'))throw new Error('Live profile verification is train-only and requires a declared profile');
const protocol='publisher-real-time-cpu-v1'+(selected?'-'+selected.name:'');
const replayAlerts=cache=>selected?replayCandidate(cache,selected).map(({id,occurredAtMs,detail})=>({id,occurredAtMs,detail})):replayBaseline(cache);
const journal=manifest.split+(selected?'-profile-'+selected.name:'')+'-capture.private.json';
const jobs=new Map(recordings.map(r=>[r.id,r]));
const port=Number(args.port);
if(!Number.isSafeInteger(port)||port<1024||port>65535||[8765,8766,8870,8871,8872].includes(port))throw new Error('Forbidden port');
process.env.NODE_ENV = 'development';
const server=await createServer({root:repo,optimizeDeps:{include:['onnxruntime-web/wasm'],exclude:['@mediapipe/tasks-vision'],noDiscovery:true},server:{host:'127.0.0.1',port,strictPort:true,hmr:false,watch:{ignored:['**/service/**','**/mobile/**','**/docs/**','**/test-results/**']}},plugins:[{name:'private-detector-media',configureServer(server){server.middlewares.use('/__detector/video/',(req,res)=>{
 const id=decodeURIComponent((req.url??'').split('?')[0].replace(/^\//,'')); const record=jobs.get(id);
 if(!record){res.statusCode=404;res.end();return}
 const size=fs.statSync(record.path).size; const range=req.headers.range?.match(/^bytes=(\d+)-(\d*)$/);
 res.setHeader('Accept-Ranges','bytes');res.setHeader('Content-Type',record.path.endsWith('.webm')?'video/webm':'video/mp4');res.setHeader('Cache-Control','no-store');
 if(range){const start=Number(range[1]),end=range[2]?Math.min(Number(range[2]),size-1):size-1;if(start>end||start>=size){res.statusCode=416;res.end();return}res.statusCode=206;res.setHeader('Content-Range',`bytes ${start}-${end}/${size}`);res.setHeader('Content-Length',end-start+1);fs.createReadStream(record.path,{start,end}).pipe(res)}else{res.setHeader('Content-Length',size);fs.createReadStream(record.path).pipe(res)}
 })}}]});
await server.watcher.close();
await server.listen();
const browser=await chromium.launch({headless:true,args:['--disable-gpu','--autoplay-policy=no-user-gesture-required','--disable-background-timer-throttling','--disable-renderer-backgrounding']});
const networkViolations=[],pageErrors=[],failures=[],completed=[];
try{
 const context=await browser.newContext();
 await context.route('**/*',route=>{const u=new URL(route.request().url());if(u.hostname==='127.0.0.1'&&u.port===String(port))return route.continue();networkViolations.push(u.origin);return route.abort()});
 const page=await context.newPage();page.on('pageerror',e=>{pageErrors.push(e.message);console.error('Browser error:',e.message)});
 for(let n=0;n<recordings.length;n++){
  const r=recordings[n],cachePath=path.join(work,'cache',r.sha256+'-'+protocol+'.json');
  try{
   let cache;try{cache=JSON.parse(await fsp.readFile(cachePath))}catch{}
   if(cache?.sourceSHA256!==r.sha256||cache?.protocol!==protocol){
    if(hash(await fsp.readFile(r.path))!==r.sha256)throw new Error('Source SHA256 mismatch');
    await page.goto(`http://127.0.0.1:${port}/scripts/evaluation/detector/`,{waitUntil:'load'});
    await page.waitForFunction(()=>window.detectorReady,null,{timeout:60000});
    cache=await page.evaluate(job=>window.replayVideo(job),{id:r.id,url:`/__detector/video/${encodeURIComponent(r.id)}`,experimentalProfile:selected?.name??null});
    cache.protocol=protocol;cache.sourceSHA256=r.sha256;cache.capturedAt=new Date().toISOString();
    validateCache(cache,r,{protocol,requireParity:false});
    const reproduced=replayAlerts(cache);
    if(JSON.stringify(reproduced)!==JSON.stringify(cache.liveAlerts))throw new Error('Cached baseline alert replay diverged');
    cache.exactAlertParity=true;
    await fsp.writeFile(cachePath+'.partial',JSON.stringify(cache));await fsp.rename(cachePath+'.partial',cachePath);
   }
   validateCache(cache,r,{protocol});
   if(JSON.stringify(replayAlerts(cache))!==JSON.stringify(cache.liveAlerts))throw new Error('Reused cache parity mismatch');
   completed.push({...r,cachePath});
   console.log(JSON.stringify({done:n+1,total:recordings.length,id:r.id,motionFrames:cache.frames.filter(f=>f.lane==='motion').length,crowdFrames:cache.frames.filter(f=>f.lane==='crowd').length,alerts:cache.liveAlerts.length,exactAlertParity:true}));
  }catch(error){failures.push({id:r.id,error:String(error)});console.error(JSON.stringify(failures.at(-1)));if(!args['allow-partial'])throw error}
  await fsp.writeFile(path.join(work,journal),JSON.stringify({schemaVersion:1,browserVersion:browser.version(),nodeVersion:process.version,summary,manifestSHA256,protocol,completed,failures,networkViolations,pageErrors},null,2));
 }
}finally{await browser.close();await server.close()}
if(failures.length||networkViolations.length||pageErrors.length)process.exitCode=1;



