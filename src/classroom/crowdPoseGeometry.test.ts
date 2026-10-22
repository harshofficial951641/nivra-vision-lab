import {describe,expect,it} from 'vitest'
import {COCO_TO_LANDMARK,crowdPoseOutputs} from './crowdPoseGeometry'
function tensors(count=1){
  const dets=new Float32Array(count*5),joints=new Float32Array(count*51)
  for(let p=0;p<count;p++){
    dets.set(count===1?[100,50,200,300,.9]:[(p%8)*70,Math.floor(p/8)*90,(p%8)*70+50,Math.floor(p/8)*90+70,.9],p*5)
    for(let k=0;k<17;k++)joints.set([120+k,100+k,.8],p*51+k*3)
  }
  return {dets,joints,detDims:[1,count,5],jointDims:[1,count,17,3]}
}
describe('observed crowd geometry',()=>{
  it('preserves all32 real detections and only17 observed COCO joints per person',()=>{
    const t=tensors(32),result=crowdPoseOutputs(t.dets,t.detDims,t.joints,t.jointDims,640,480,640)
    expect(result.people).toHaveLength(32);expect(result.poses).toHaveLength(32)
    expect(result.poses[0].filter(Boolean)).toHaveLength(17)
    expect(result.poses[0][11]).toMatchObject({x:125/640,y:105/480})
    expect(result.poses[0][1]).toBeUndefined()
    expect(result.poses[0][29]).toBeUndefined()
    expect(COCO_TO_LANDMARK).toHaveLength(17)
  })
  it('undoes top-left letterboxing and omits out-of-image joints instead of clamping them',()=>{
    const t=tensors()
    t.joints.set([416,100,.9],0)
    const result=crowdPoseOutputs(t.dets,t.detDims,t.joints,t.jointDims,1280,720,416)
    expect(result.people[0].box[0]).toBeCloseTo(100/416)
    expect(result.people[0].box[1]).toBeCloseTo(50/(416/1280)/720)
    expect(result.poses[0][0]).toBeUndefined()
    expect(result.poses[0][11]?.x).toBeCloseTo(125/416)
  })
  it('bounds output, rejects invalid tensors, and filters padding or sub-eight-pixel boxes',()=>{
    const t=tensors(40)
    expect(crowdPoseOutputs(t.dets,t.detDims,t.joints,t.jointDims,640,480,640).people).toHaveLength(32)
    expect(()=>crowdPoseOutputs(t.dets,[1,40,4],t.joints,t.jointDims,640,480,640)).toThrow('geometry')
    const one=tensors();one.joints[2]=NaN
    expect(()=>crowdPoseOutputs(one.dets,one.detDims,one.joints,one.jointDims,640,480,640)).toThrow('confidence')
    one.dets.set([0,0,2,2,.9])
    expect(crowdPoseOutputs(one.dets,one.detDims,one.joints,one.jointDims,640,480,640).people).toEqual([])
  })
  it('admits only product-confidence detections and removes clipped duplicate boxes with their poses',()=>{
    const t=tensors(3)
    t.dets.set([0,50,100,300,.9,-100,50,100,300,.8,200,50,300,300,.15])
    const result=crowdPoseOutputs(t.dets,t.detDims,t.joints,t.jointDims,640,480,640)
    expect(result.people).toHaveLength(1)
    expect(result.poses).toHaveLength(1)
  })

})
