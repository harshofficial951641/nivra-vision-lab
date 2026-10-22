import {describe,it,expect} from 'vitest'
import {ConflictEngine} from './originalConflictEngine'
import {replayBaseline,replayCandidate,boxesMatch} from '../../scripts/evaluation/detector/replayEngine'
import type {PoseLandmarks} from '../types/vision'
const person=(x:number,extension=0):PoseLandmarks=>{
 const pose=Array.from({length:33},()=>({x:0,y:0,z:0,visibility:0,presence:0}))
 const joints:Record<number,[number,number]>={11:[x-.065,.34],12:[x+.065,.34],13:[x-.08,.42],15:[x-.075,.49],14:[x+.08+extension*.08,.42-extension*.05],16:[x+.075+extension*.175,.49-extension*.09],23:[x-.055,.60],24:[x+.055,.60],27:[x-.055,.91],28:[x+.055,.91]}
 for(const [i,[px,y]] of Object.entries(joints))pose[+i]={x:px,y,z:0,visibility:.99,presence:.99}
 return pose
}
const thrust=(t:number)=>t>=700&&(t-700)%900<200?1:0
const cache=(both=true)=>({frames:Array.from({length:27},(_,i)=>i*100).flatMap(t=>{
 const frame={timestampMs:t,aspect:16/9,inferenceMs:20,elapsedMs:25,poses:[person(.35,thrust(t)),person(.65)]}
 return [{...frame,lane:'motion'},...(both?[{...frame,lane:'crowd',people:[]}]:[])]
})})
describe('experimental source-lane replay',()=>{
 it('lowers episode count only behind its explicit profile',()=>{
  const c=cache(false);c.frames=c.frames.filter(f=>f.timestampMs<=1800)
  expect(replayCandidate(c,{name:'baseline',crowd:false,motion:{}})).toHaveLength(0)
  expect(replayCandidate(c,{name:'two',crowd:false,motion:{episodes:2}})).toHaveLength(1)
 })
 it.each([{}, {episodes:2 as const}, {episodes:2 as const,armSpeedScale:.8 as const}])('keeps a single reach quiet under profile %j',motion=>{
  const c=cache(false);for(const f of c.frames)f.poses=[person(.35,f.timestampMs>=700?1:0),person(.65)]
  expect(replayCandidate(c,{name:'single',crowd:false,motion})).toHaveLength(0)
 })
 it('does not duplicate a pair already seen in the fast lane',()=>expect(replayCandidate(cache(),{name:'crowd',crowd:true,motion:{}})).toHaveLength(1))
 it('keeps independent worker histories separate instead of using cross-lane velocity',()=>{
  const c={frames:[{lane:'motion',timestampMs:0,aspect:1,inferenceMs:20,elapsedMs:20,poses:[person(.35),person(.65)]},{lane:'crowd',timestampMs:333,aspect:1,inferenceMs:300,elapsedMs:310,poses:[person(.35,1),person(.65)],people:[]}]}
  expect(replayCandidate(c,{name:'crowd',crowd:true,motion:{episodes:2,contact:'sensitive'}})).toHaveLength(0)
 })
 it('matches the baseline alert source timestamp and detail exactly',()=>{
  const c=cache(false),engine=new ConflictEngine({cooldownScope:'pair'});let last:any
  for(const f of c.frames)last=engine.update(f.timestampMs,f.poses,f.aspect)
  const alerts=replayBaseline(c);expect(alerts).toHaveLength(1);expect(alerts[0]).toMatchObject({occurredAtMs:last.events[0].occurredAtMs,detail:last.events[0].detail})
 })
 it('uses the production source aspect rather than rounded bitmap dimensions',()=>{
  const c:any=cache(false);c.sourceWidth=1920;c.sourceHeight=1080
  const expected=replayBaseline(c)
  for(const frame of c.frames)frame.aspect=.5
  expect(replayBaseline(c)).toEqual(expected)
  expect(expected).toHaveLength(1)
 })
 it('does not match separate source-space boxes',()=>expect(boxesMatch({x:0,y:0,width:.1,height:.5},{x:.7,y:0,width:.1,height:.5})).toBe(false))
})
