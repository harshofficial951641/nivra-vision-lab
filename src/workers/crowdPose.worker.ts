import * as ort from 'onnxruntime-web/wasm'
import { crowdPoseOutputs, type CrowdPoseModel } from '../classroom/crowdPoseGeometry'
let session:ort.InferenceSession|null=null,model:CrowdPoseModel|null=null,busy=false
const delegate='CPU' as const
self.onmessage=async({data}:{data:{type:'init';model:CrowdPoseModel}|{type:'frame';bitmap:ImageBitmap;timestampMs:number}})=>{
  if(busy){if(data.type==='frame')data.bitmap.close();return}
  busy=true
  try{
    if(data.type==='init'){
      if(!/^[a-f0-9]{64}$/.test(data.model.sha256)||![416,640].includes(data.model.inputSide))throw new Error('Invalid crowd model configuration.')
      const url=new URL(data.model.modelPath,new URL(import.meta.env.BASE_URL,self.location.origin))
      if(url.origin!==self.location.origin)throw new Error('Crowd model must use this site.')
      ort.env.wasm.wasmPaths=new URL(`${import.meta.env.BASE_URL}onnxruntime/`,self.location.origin).href
      ort.env.wasm.numThreads=typeof crossOriginIsolated!=='undefined'&&crossOriginIsolated?Math.min(2,navigator.hardwareConcurrency||1):1
      const response=await fetch(url,{cache:'force-cache'})
      if(!response.ok)throw new Error('Could not load crowd detection.')
      const bytes=await response.arrayBuffer()
      if(bytes.byteLength>64*1024*1024)throw new Error('Crowd model exceeds its size limit.')
      const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('')
      if(hash!==data.model.sha256)throw new Error('Crowd model integrity check failed.')
      session=await ort.InferenceSession.create(bytes,{executionProviders:['wasm'],graphOptimizationLevel:'all'})
      if(session.inputNames.length!==1||!session.outputNames.includes('dets')||!session.outputNames.includes('keypoints'))throw new Error('Unexpected crowd graph contract.')
      model=data.model
      self.postMessage({type:'ready',delegate})
    }else{
      if(!session||!model)throw new Error('Crowd model is not ready.')
      const began=performance.now(),side=model.inputSide,width=data.bitmap.width,height=data.bitmap.height,ratio=Math.min(side/width,side/height)
      const canvas=new OffscreenCanvas(side,side),context=canvas.getContext('2d',{willReadFrequently:true})
      if(!context)throw new Error('Crowd image canvas unavailable.')
      context.fillStyle='rgb(114,114,114)';context.fillRect(0,0,side,side)
      context.drawImage(data.bitmap,0,0,Math.max(1,Math.floor(width*ratio)),Math.max(1,Math.floor(height*ratio)))
      const rgba=context.getImageData(0,0,side,side).data,plane=side*side,input=new Float32Array(plane*3)
      for(let i=0;i<plane;i++){input[i]=rgba[i*4+2];input[plane+i]=rgba[i*4+1];input[plane*2+i]=rgba[i*4]}
      const tensor=new ort.Tensor('float32',input,[1,3,side,side])
      let outputs:ort.InferenceSession.ReturnType|null=null
      try{
        outputs=await session.run({[session.inputNames[0]]:tensor})
        const dets=outputs.dets,keypoints=outputs.keypoints
        if(dets.type!=='float32'||keypoints.type!=='float32')throw new Error('Unexpected crowd tensor type.')
        const result=crowdPoseOutputs(dets.data as Float32Array,dets.dims,keypoints.data as Float32Array,keypoints.dims,width,height,side)
        self.postMessage({type:'result',result:{timestampMs:data.timestampMs,inferenceMs:performance.now()-began,delegate,...result}})
      }finally{tensor.dispose();if(outputs)for(const output of Object.values(outputs))output.dispose()}
    }
  }catch(error){self.postMessage({type:'error',message:error instanceof Error?error.message:'Crowd detection failed.'})}
  finally{if(data.type==='frame')data.bitmap.close();busy=false}
}
