import {describe,it,expect} from 'vitest'
import {ConflictEngine} from './originalConflictEngine'
import type {PoseLandmarks} from '../types/vision'
const person=(x:number):PoseLandmarks=>{
 const p=Array.from({length:33},()=>({x:0,y:0,z:0,visibility:0,presence:0}))
 for(const [i,dx,y] of [[11,-.065,.34],[12,.065,.34],[13,-.08,.55],[14,.08,.55],[15,-.075,.75],[16,.075,.75],[23,-.055,.60],[24,.055,.60],[25,-.055,.75],[26,.055,.75],[27,-.055,.91],[28,.055,.91]])p[i]={x:x+dx,y,z:0,visibility:.99,presence:.99}
 return p
}
function sequence(engine:ConflictEngine,kind:string,step=100,missingAt=-1){
 let snapshot=engine.snapshot(0)
 for(let t=0;t<=2400;t+=step){
  if(t===missingAt){snapshot=engine.update(t,[],1);continue}
  const movement=Math.max(0,Math.min(.15,(t-800)/600*.15))
  const pan=kind==='pan'?Math.sin(t/700)*.05:0
  const a=person(.35+pan+(kind==='dance'?movement:0)),b=person(.55+pan+(kind==='dance'||kind==='push'?movement:kind==='jitter'?Math.sin(t/47)*.005:0))
  a[16]={...a[16],x:b[11].x+.065,y:.3972};a[14]={...a[14],x:(a[12].x+a[16].x)/2,y:.44}
  if(kind==='handshake'){a[16].y=.64;a[14].y=.52}
  if(kind==='hug'){b[15]={...b[15],x:.35+pan,y:.3972};b[13]={...b[13],x:.40+pan,y:.44}}
  if(kind==='hidden')a[16].visibility=.1
  snapshot=engine.update(t,[a,b],1)
 }
 return snapshot
}
describe('opt-in torso displacement candidate',()=>{
 it('keeps the new rule disabled by default',()=>expect(sequence(new ConflictEngine(),'push').events).toHaveLength(0))
 it.each([100,333])('observes sustained one-sided reach and relative displacement at %ims cadence',step=>expect(sequence(new ConflictEngine({experimental:{contact:'conservative'}}),'push',step).events).toHaveLength(1))
 it.each(['held','handshake','hug','dance','pan','jitter','hidden'])('rejects %s',kind=>expect(sequence(new ConflictEngine({experimental:{contact:'conservative'}}),kind).events).toHaveLength(0))
 it('resets sustained contact after one missing pair observation inside the continuity window',()=>expect(sequence(new ConflictEngine({experimental:{contact:'conservative'}}),'push',100,1200).events).toHaveLength(0))
 it('uses real elapsed velocity at 800ms only with the crowd continuity flag',()=>{
  for(const maxGapMs of [600,1000] as const){
   const e=new ConflictEngine({experimental:{contact:'conservative',maxGapMs}})
   let r=e.snapshot(0)
   for(let t=0;t<=5600;t+=800){
    const dx=Math.max(0,Math.min(.20,(t-3200)/800*.20)),a=person(.35),b=person(.55+dx)
    a[16]={...a[16],x:.55+dx,y:.3972};a[14]={...a[14],x:(a[12].x+a[16].x)/2,y:.44}
    r=e.update(t,[a,b],1)
   }
   expect(r.events).toHaveLength(maxGapMs===1000?1:0)
  }
 })
 it('does not bridge missing observations',()=>{
  const e=new ConflictEngine({experimental:{contact:'conservative'}})
  sequence(e,'held');e.update(4000,[],1)
  expect(e.update(4333,[person(.35),person(.70)],1).events).toHaveLength(0)
 })
 it('exposes detached source-matched event regions and clears them on reset',()=>{
  const e=new ConflictEngine({experimental:{contact:'conservative'}}),r=sequence(e,'push'),id=r.events[0]?.id
  expect(id).toBeTruthy();const boxes=e.regionsForEvent(id!);expect(boxes).toHaveLength(2);boxes[0].x=-1;expect(e.regionsForEvent(id!)[0].x).toBeGreaterThanOrEqual(0);e.reset();expect(e.regionsForEvent(id!)).toHaveLength(0)
 })
 it('can exclude a pair already covered by the motion lane',()=>expect(sequence(new ConflictEngine({experimental:{contact:'conservative'},pairAllowed:()=>false}),'push').events).toHaveLength(0))
})

