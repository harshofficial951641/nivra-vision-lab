import type { PoseLandmarks, VisionDelegate } from '../types/vision'
import { mergePersonBoxes, type PersonBox } from './personTracking'
import type { PersonObservation } from './peopleContracts'
export interface CrowdPoseModel { modelPath:string; sha256:string; inputSide:416|640; preferredDelegate?:VisionDelegate }
export interface CrowdPoseResult { timestampMs:number; inferenceMs:number; delegate:VisionDelegate; people:PersonObservation[]; poses:PoseLandmarks[] }
// Product person admission is separate from the export's permissive .1 proposal floor.
export const CROWD_PERSON_SCORE = .25
export const COCO_TO_LANDMARK = [0,2,5,7,8,11,12,13,14,15,16,23,24,25,26,27,28] as const
/** Exported RTMO detections already have official NMS. Never invent missing joints. */
export function crowdPoseOutputs(dets:ArrayLike<number>,detDims:readonly number[],joints:ArrayLike<number>,jointDims:readonly number[],width:number,height:number,side:number): Pick<CrowdPoseResult,'people'|'poses'> {
  const slots=detDims[1]
  if(![width,height,side].every(n=>Number.isSafeInteger(n)&&n>0) || detDims.length!==3 || detDims[0]!==1 || detDims[2]!==5 || !Number.isSafeInteger(slots) || slots<0 || slots>1000 || jointDims.length!==4 || jointDims[0]!==1 || jointDims[1]!==slots || jointDims[2]!==17 || jointDims[3]!==3 || dets.length!==slots*5 || joints.length!==slots*51)throw new Error('Unexpected crowd model output geometry.')
  const ratio=Math.min(side/width,side/height)
  const people:PersonObservation[]=[],poses:PoseLandmarks[]=[]
  const order=Array.from({length:slots},(_,i)=>i).sort((a,b)=>dets[b*5+4]-dets[a*5+4])
  for(const index of order){
    const offset=index*5,score=dets[offset+4]
    if(!Number.isFinite(score)||score<0||score>1)throw new Error('Invalid crowd model confidence.')
    if(score<CROWD_PERSON_SCORE)continue
    const raw=Array.from({length:4},(_,i)=>dets[offset+i]/ratio)
    if(!raw.every(Number.isFinite))throw new Error('Invalid crowd model box.')
    const box=[Math.max(0,Math.min(width,raw[0])),Math.max(0,Math.min(height,raw[1])),Math.max(0,Math.min(width,raw[2])),Math.max(0,Math.min(height,raw[3]))]
    if(box[2]-box[0]<8||box[3]-box[1]<8)continue
    const normalized:PersonBox=[box[0]/width,box[1]/height,box[2]/width,box[3]/height]
    // SDK NMS occurs before image clipping. Apply the existing tracker admission
    // to clipped boxes AND their paired poses so coverage counts cannot diverge.
    if(mergePersonBoxes([...people,{box:normalized,score}],[]).length===people.length)continue
    const pose:PoseLandmarks=new Array(33)
    for(let source=0;source<17;source++){
      const at=index*51+source*3,x=joints[at]/ratio,y=joints[at+1]/ratio,confidence=joints[at+2]
      if(!Number.isFinite(confidence)||confidence<0||confidence>1)throw new Error('Invalid crowd joint confidence.')
      if(!Number.isFinite(x)||!Number.isFinite(y))throw new Error('Invalid crowd joint coordinates.')
      if(confidence<=0||x<0||x>=width||y<0||y>=height)continue
      pose[COCO_TO_LANDMARK[source]]={x:x/width,y:y/height,z:0,visibility:confidence,presence:confidence}
    }
    people.push({box:normalized,score})
    poses.push(pose)
    if(people.length===32)break
  }
  return {people,poses}
}
