/** Reject incomplete/corrupt capture artifacts instead of scoring silent subsets. */
export function validateCache(cache,recording,{protocol='publisher-real-time-cpu-v1',requireParity=true}={}){
 if(cache.protocol!==protocol||cache.sourceSHA256!==recording.sha256)throw new Error('Cache provenance mismatch');
 if(!Number.isFinite(cache.durationMs)||cache.durationMs<=0||![cache.sourceWidth,cache.sourceHeight].every(n=>Number.isSafeInteger(n)&&n>0))throw new Error('Invalid decoded source geometry');
 if(!Array.isArray(cache.frames)||!Array.isArray(cache.liveAlerts))throw new Error('Invalid cache arrays');
 for(const lane of ['motion','crowd']){
  const frames=cache.frames.filter(f=>f.lane===lane);if(!frames.length)throw new Error('Missing lane: '+lane);
  for(let i=0;i<frames.length;i++){
   const f=frames[i];
   if(!Number.isFinite(f.timestampMs)||f.timestampMs<0||f.timestampMs>cache.durationMs+1||i&&f.timestampMs-frames[i-1].timestampMs<49.99)throw new Error('Invalid source timestamp/admission in '+lane);
   if(![f.inferenceMs,f.elapsedMs].every(n=>Number.isFinite(n)&&n>=0)||!Number.isFinite(f.aspect)||f.aspect<=0||!Array.isArray(f.poses)||f.poses.length>(lane==='motion'?4:32))throw new Error('Invalid pose frame contract in '+lane);
  }
 }
 if(cache.frames.some(f=>!['motion','crowd'].includes(f.lane)))throw new Error('Unknown lane');
 for(const interval of [...recording.events,...recording.normalIntervals])if(interval.endMs>cache.durationMs+1)throw new Error('Label interval exceeds decoded source duration');
 for(const event of cache.liveAlerts)if(!Number.isFinite(event.occurredAtMs)||event.occurredAtMs<0||event.occurredAtMs>cache.durationMs+1||typeof event.id!=='string'||typeof event.detail!=='string')throw new Error('Invalid live alert');
 if(requireParity&&cache.exactAlertParity!==true)throw new Error('Unverified alert parity');
 return true;
}
