import {DETECTOR_EXPERIMENTS,DualLaneConflictAnalysis,detectorBoxesMatch,type DetectorRuleConfiguration} from '../../../src/classroom/deviceAnalysis'
export const CANDIDATES=DETECTOR_EXPERIMENTS
export type Candidate=DetectorRuleConfiguration
export const boxesMatch=detectorBoxesMatch
export function replayCandidate(cache:any,candidate:Candidate=CANDIDATES[0]) {
  const analysis=new DualLaneConflictAnalysis(candidate),alerts:any[]=[]
  for(const frame of cache.frames){
    if(frame.lane!=='motion'&&!candidate.crowd)continue
    const aspect=cache.sourceWidth>0&&cache.sourceHeight>0?cache.sourceWidth/cache.sourceHeight:frame.aspect
    const report=analysis.update(frame.lane,frame.timestampMs,Math.max(frame.inferenceMs,frame.elapsedMs),frame.poses,aspect,'CPU','full',frame.people)
    for(const event of report.events)alerts.push({id:event.id.slice(event.id.lastIndexOf('conflict-')),occurredAtMs:event.occurredAtMs,detail:event.detail,lane:frame.lane})
  }
  return alerts
}
export function replayBaseline(cache:any){return replayCandidate(cache,CANDIDATES[0]).map(({id,occurredAtMs,detail})=>({id,occurredAtMs,detail}))}
