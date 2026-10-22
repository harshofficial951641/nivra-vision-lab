import fs from 'node:fs/promises';import path from 'node:path';import crypto from 'node:crypto';import {build} from 'vite';import {pathToFileURL} from 'node:url';import {parseArgs} from 'node:util';
import {validateCache} from './cacheContract.mjs';
import {scoreRecording,pointMetrics,summarize,bootstrap,promotionGate,quantile,TOLERANCE_MS} from './metrics.mjs';
const {values:args}=parseArgs({options:{split:{type:'string'},'work-dir':{type:'string',default:'D:/nivra-work/detector'},out:{type:'string'},tune:{type:'boolean'},iterations:{type:'string',default:'10000'}}});
if(!['train','dev'].includes(args.split))throw new Error('--split train|dev required');if(args.tune&&args.split!=='train')throw new Error('Tuning on dev is prohibited');
const work=path.resolve(args['work-dir']),repo=path.resolve(import.meta.dirname,'../../..');
const capture=JSON.parse(await fs.readFile(path.join(work,args.split+'-capture.private.json')));
if(capture.protocol!=='publisher-real-time-cpu-v1')throw new Error('Scoring requires the baseline publisher capture protocol');
if(capture.completed.length!==capture.summary.recordings||capture.failures.length||capture.networkViolations.length||capture.pageErrors?.length)throw new Error('Capture is incomplete or invalid; no scored subset fallback');
await build({configFile:false,logLevel:'error',build:{lib:{entry:path.join(import.meta.dirname,'replayEngine.ts'),formats:['es'],fileName:()=> 'scoreEngine.mjs'},outDir:path.join(work,'runtime'),emptyOutDir:false,minify:false}});
const {CANDIDATES,replayCandidate,replayBaseline}=await import(pathToFileURL(path.join(work,'runtime/scoreEngine.mjs')).href+'?t='+Date.now());
const sha=file=>fs.readFile(file).then(b=>crypto.createHash('sha256').update(b).digest('hex'));
const analysisSHA256=await sha(path.join(repo,'src/classroom/deviceAnalysis.ts'));
const metricsSHA256=await sha(path.join(import.meta.dirname,'metrics.mjs'));
const ruleSHA256=await sha(path.join(repo,'src/lib/originalConflictEngine.ts')),candidateSHA256=await sha(path.join(import.meta.dirname,'replayEngine.ts'));
let selection;
if(args.split==='dev'){
 selection=JSON.parse(await fs.readFile(path.join(work,'selection.json')));
 if(selection.ruleSHA256!==ruleSHA256||selection.candidateSHA256!==candidateSHA256||selection.metricsSHA256!==metricsSHA256||selection.analysisSHA256!==analysisSHA256)throw new Error('Rules/candidates changed after train freeze');
 if(selection.frozenAt>new Date().toISOString())throw new Error('Invalid freeze timestamp');
}
const rows=Object.fromEntries(CANDIDATES.map(c=>[c.name,[]])),coverage=[];
for(const r of capture.completed){
 const cache=JSON.parse(await fs.readFile(r.cachePath));
 validateCache(cache,r);
 if(JSON.stringify(replayBaseline(cache))!==JSON.stringify(cache.liveAlerts)||!cache.exactAlertParity)throw new Error('Baseline alert parity failed');
 for(const candidate of CANDIDATES)rows[candidate.name].push(scoreRecording(r,replayCandidate(cache,candidate)));
 const crowd=cache.frames.filter(f=>f.lane==='crowd'),motion=cache.frames.filter(f=>f.lane==='motion');
 const deltas=lane=>lane.slice(1).map((f,i)=>f.timestampMs-lane[i].timestampMs);
 coverage.push({context:r.context,group:r.group,crowdFrames:crowd.length,crowdOverFour:crowd.filter(f=>f.people.length>4).length,peakCrowd:Math.max(0,...crowd.map(f=>f.people.length)),motionFrames:motion.length,motionAtCap:motion.filter(f=>f.poses.length===4).length,durationMs:cache.durationMs,crowdGaps:deltas(crowd),motionGaps:deltas(motion),crowdInference:crowd.map(f=>f.inferenceMs),motionInference:motion.map(f=>f.inferenceMs)});
}
const points=Object.fromEntries(CANDIDATES.map(c=>[c.name,pointMetrics(rows[c.name])]));
if(args.tune){
 const baseline=points.baseline,ranked=CANDIDATES.filter(c=>c.name!=='baseline').sort((a,b)=>(points[b.name].eventRecall??0)-(points[a.name].eventRecall??0)||(points[a.name].falseAlertsPerHour??Infinity)-(points[b.name].falseAlertsPerHour??Infinity)||CANDIDATES.indexOf(a)-CANDIDATES.indexOf(b));
 const eligible=ranked.filter(c=>points[c.name].eventRecall>baseline.eventRecall&&points[c.name].falseAlertsPerHour<=baseline.falseAlertsPerHour);
 const chosen=eligible[0]??ranked[0];
 selection={schemaVersion:1,frozenAt:new Date().toISOString(),ruleSHA256,candidateSHA256,metricsSHA256,analysisSHA256,trainManifestSHA256:capture.manifestSHA256,trainGroups:capture.summary.groups,trainRecordings:capture.summary.recordings,chosen:chosen.name,trainGatePointEstimateEligible:eligible.length>0,candidates:CANDIDATES,trainPoints:points,selectionRule:'Highest train event recall among candidates with no increase in train false-alert rate; ties: fewer false alerts, then predeclared candidate order. If none qualifies, highest recall is evaluated descriptively and cannot promote.'};
 await fs.writeFile(path.join(work,'selection.json'),JSON.stringify(selection,null,2));
 console.log(JSON.stringify(selection,null,2));
}
const iterations=Number(args.iterations),results={};
for(const c of CANDIDATES){
 const summary=summarize(rows[c.name],iterations),delta=bootstrap(rows.baseline,rows[c.name],{iterations});
 results[c.name]={...summary,pairedDifferenceCI95:delta,recallDifference:summary.eventRecall===null?null:summary.eventRecall-points.baseline.eventRecall,falseAlertsPerHourDifference:summary.falseAlertsPerHour===null?null:summary.falseAlertsPerHour-points.baseline.falseAlertsPerHour,
  eligibleDefault:args.split==='dev'&&selection.chosen===c.name&&selection.trainGatePointEstimateEligible&&promotionGate(points.baseline,summary,delta)};
}
const coverageSummary=data=>({recordings:data.length,crowdFrames:data.reduce((a,r)=>a+r.crowdFrames,0),crowdFramesOverFour:data.reduce((a,r)=>a+r.crowdOverFour,0),fractionCrowdFramesOverFour:data.reduce((a,r)=>a+r.crowdOverFour,0)/data.reduce((a,r)=>a+r.crowdFrames,0),maximumCrowdObservations:Math.max(0,...data.map(r=>r.peakCrowd)),motionFrames:data.reduce((a,r)=>a+r.motionFrames,0),motionAtFourPoseCap:data.reduce((a,r)=>a+r.motionAtCap,0),medianCrowdGapMs:quantile(data.flatMap(r=>r.crowdGaps),.5),p90CrowdGapMs:quantile(data.flatMap(r=>r.crowdGaps),.9),fractionCrowdGapsOver600ms:data.flatMap(r=>r.crowdGaps).filter(t=>t>600).length/data.flatMap(r=>r.crowdGaps).length,medianMotionGapMs:quantile(data.flatMap(r=>r.motionGaps),.5),medianCrowdInferenceMs:quantile(data.flatMap(r=>r.crowdInference),.5),medianMotionInferenceMs:quantile(data.flatMap(r=>r.motionInference),.5)});
const output={schemaVersion:1,createdAt:new Date().toISOString(),models:{mediaPipeFullSHA256:await sha(path.join(repo,'public/models/pose_landmarker_full.task')),rtmoSHA256:await sha(path.join(repo,'public/models/rtmo-t-body7-416-20aad6e2.onnx'))},crowdContinuityMs:1000,defaultMotionContinuityMs:600,split:args.split,manifestSHA256:capture.manifestSHA256,protocol:capture.protocol,ruleSHA256,candidateSHA256,metricsSHA256,analysisSHA256,toleranceMs:TOLERANCE_MS,bootstrap:{unit:'source group',iterations,seed:20261023,ci:'percentile 95%',paired:true},selection:args.split==='dev'?{chosen:selection.chosen,frozenAt:selection.frozenAt,trainGatePointEstimateEligible:selection.trainGatePointEstimateEligible}:null,validatedCaptureRecordings:capture.completed.length,exactAlertParityRecordings:capture.completed.length,networkViolations:capture.networkViolations.length,browserPageErrors:capture.pageErrors?.length??0,results,coverage:{overall:coverageSummary(coverage),contexts:Object.fromEntries([...new Set(coverage.map(r=>r.context))].sort().map(c=>[c,coverageSummary(coverage.filter(r=>r.context===c))]))}};
const outputPath=args.out?path.resolve(args.out):path.join(work,args.split+'-aggregate.json');
if(!outputPath.toLowerCase().startsWith(path.join(repo,'docs/evaluations/detector-accuracy').toLowerCase())&&!outputPath.toLowerCase().startsWith(work.toLowerCase()+path.sep))throw new Error('Unexpected aggregate output path');
await fs.writeFile(outputPath,JSON.stringify(output,null,2));
await fs.writeFile(path.join(work,args.split+'-scores.private.json'),JSON.stringify({rows,coverage},null,2));
console.log(JSON.stringify({output:outputPath,points,selection:selection?.chosen,defaultCandidates:Object.entries(results).filter(([,r])=>r.eligibleDefault).map(([name])=>name)}));
