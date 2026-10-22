const {chromium}=require('playwright');
const fs=require('fs'); const path=require('path');
const DIR=path.resolve('test-results/browser-speed-qa'), BASE='https://nivra.tanishq.work';
fs.mkdirSync(DIR,{recursive:true,mode:0o700});fs.chmodSync(DIR,0o700);
const metadata={started:new Date().toISOString(),cycles:[],checks:[]};
function instrument(){
 const Native=window.WebSocket;const peers=[];
 window.__qa={peers,counts:{ready:0,acks:0,snapshots:0,opens:0,closes:0,reports:0,statuses:0,binary:0},lastReady:null,lastSnapshot:null,videoAcks:0,encodedFrames:0,lastModel:null,models:{}};
 window.WebSocket=class extends Native{
  constructor(url,protocols){super(url,protocols);const kind=new URL(url).pathname;peers.push({socket:this,kind});this.addEventListener('open',()=>window.__qa.counts.opens++);this.addEventListener('close',()=>window.__qa.counts.closes++);this.addEventListener('message',e=>{if(typeof e.data!=='string'){window.__qa.counts.binary++;return;}try{const m=JSON.parse(e.data);if(m.type==='ready'){window.__qa.counts.ready++;window.__qa.lastReady={cameraId:m.cameraId,generation:m.generation};}if(m.type==='accepted')window.__qa.counts.acks++;if(m.type==='video-accepted')window.__qa.videoAcks++;if(m.type==='snapshot'){window.__qa.counts.snapshots++;window.__qa.lastSnapshot=m;}}catch{}});}
  send(data){if(typeof data==='string'){try{const m=JSON.parse(data);if(m.type==='browser-video-v1')window.__qa.encodedFrames+=m.frames.length;if(m.type==='device-result'||m.type==='device-motion'){window.__qa.counts.reports++;window.__qa.lastModel=m.model;const prior=window.__qa.models[m.model]??{reports:0,lastTimestamp:-1};window.__qa.models[m.model]={reports:prior.reports+1,lastTimestamp:m.timestampMs,receivedAt:performance.now(),type:m.type};}if(m.type==='device-status'||m.type==='device-motion-status')window.__qa.counts.statuses++;}catch{}}return super.send(data);}
 };
 window.__qa.close=function(kind){let n=0;for(const p of peers)if(p.kind===kind&&p.socket.readyState===1){p.socket.close(1000,'QA transport interruption');n++;}return n;};
}
function fakeCamera(){
 navigator.mediaDevices.getUserMedia=async()=>{
  const canvas=document.createElement('canvas');canvas.width=640;canvas.height=360;const ctx=canvas.getContext('2d');let frame=0;
  const timer=setInterval(()=>{ctx.fillStyle='#23272c';ctx.fillRect(0,0,640,360);ctx.fillStyle='#ddd';ctx.fillRect((frame++*7)%600,150,40,40);ctx.fillStyle='#fff';ctx.font='20px sans-serif';ctx.fillText('Synthetic transport QA',20,35);ctx.fillText('Frame '+frame,20,80);},1000/60);
  const stream=canvas.captureStream(60);stream.getTracks().forEach(t=>t.addEventListener('ended',()=>clearInterval(timer)));return stream;
 };
}
async function safeState(page){return page.evaluate(()=>({counts:{...window.__qa.counts,videoAcks:window.__qa.videoAcks},model:window.__qa.lastModel,models:{...window.__qa.models},videoAcks:window.__qa.videoAcks,encodedFrames:window.__qa.encodedFrames,playback:[...document.querySelectorAll('canvas')].map(c=>{const m=c.__nivraVideoMetrics?.();if(!m)return null;const p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let pixelHash=0;for(let i=0;i<p.length;i+=4)pixelHash=(pixelHash+Math.imul(p[i]+p[i+1]*3+p[i+2]*7,i+1))>>>0;return {...m,pixelHash}}).filter(Boolean),open:window.__qa.peers.filter(p=>p.socket.readyState===1).map(p=>p.kind),ready:window.__qa.lastReady,cameras:window.__qa.lastSnapshot?.cameras.map(c=>({id:c.id,feed:c.feed,generation:c.generation,framesReceived:c.framesReceived,framesAnalyzed:c.framesAnalyzed}))??[]}));}
async function main(){
 if(process.env.NIVRA_QA_RELEASE_READY!=='1')throw new Error('Release-ready gate is closed.');
 const browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
 let owner,workspaceCreated=false;const contexts=[];
 try{
  owner=await browser.newContext({viewport:{width:1280,height:800}});contexts.push(owner);await owner.addInitScript(instrument);
  const post=async(p,body)=>{const r=await owner.request.post(BASE+'/api/v2'+p,{headers:{Origin:BASE},data:body??{},timeout:35000});if(!r.ok())throw new Error('QA API '+p.replace(/[0-9a-f-]{36}/g,'[id]')+' returned '+r.status());return r.json();};
  await post('/workspaces',{name:'Private browser speed QA '+Date.now()});workspaceCreated=true;
  // Recovery cookies stay in this private ignored file for cleanup only.
  await owner.storageState({path:path.join(DIR,'private-owner-storage.json')});fs.chmodSync(path.join(DIR,'private-owner-storage.json'),0o600);
  const camera=await post('/cameras',{name:'Synthetic QA camera',building:'Private QA',floor:'1'});
  const pair=await post('/cameras/'+camera.id+'/pair');
  const wall=await owner.newPage();await wall.goto(BASE+'/wall',{waitUntil:'domcontentloaded'});
  const phoneContext=await browser.newContext({viewport:{width:390,height:844}});contexts.push(phoneContext);await phoneContext.addInitScript(instrument);await phoneContext.addInitScript(fakeCamera);
  const phone=await phoneContext.newPage();
  let fullAssets=0,crowdAssets=0;phone.on('response',r=>{if(r.url().includes('pose_landmarker_full.task')&&r.ok())fullAssets++;if(r.url().includes('rtmo-t-body7-416-20aad6e2.onnx')&&r.ok())crowdAssets++;});
  await phone.goto(pair.url,{waitUntil:'domcontentloaded'});
  await phone.getByRole('button',{name:'Allow camera & start',exact:true}).click({timeout:45000});
  await phone.waitForFunction(()=>window.__qa.counts.acks>=3&&window.__qa.videoAcks>=10&&window.__qa.models['nivra-browser-rtmo-t-motion-v1']?.reports>0&&window.__qa.models['nivra-browser-motion-v1']?.reports>0,null,{timeout:120000});
  await wall.waitForFunction(()=>[...document.querySelectorAll('canvas')].some(c=>(c.__nivraVideoMetrics?.().drawn??0)>5),null,{timeout:30000});
  const baseline=await safeState(phone);const wallBaseline=await safeState(wall);
  const sampleStartedAt=Date.now();await phone.waitForTimeout(30000);
  const steady=await safeState(phone),wallSteady=await safeState(wall);
  metadata.continuous={baseline,steady,wallBaseline,wallSteady,fullModelAssetLoaded:fullAssets>0,fullModelAssetResponses:fullAssets,crowdModelAssetResponses:crowdAssets};
  const elapsed=(Date.now()-sampleStartedAt)/1000;
  metadata.speed={source:'synthetic60fps canvas, desktop Chromium',seconds:elapsed,encodedFPS:(steady.encodedFrames-baseline.encodedFrames)/elapsed,displayedFPS:((wallSteady.playback[0]?.drawn??0)-(wallBaseline.playback[0]?.drawn??0))/elapsed,videoAcks:steady.videoAcks-baseline.videoAcks};
  if(wallSteady.playback[0]?.pixelHash===wallBaseline.playback[0]?.pixelHash)throw new Error('Decoded pixels did not change');
  if(metadata.speed.videoAcks<100||metadata.speed.encodedFPS<35||metadata.speed.displayedFPS<35)throw new Error('Compressed video did not sustain35 actual displayed fps');
  if(steady.counts.ready!==baseline.counts.ready||steady.counts.opens!==baseline.counts.opens||steady.counts.closes!==baseline.counts.closes||steady.ready?.generation!==baseline.ready?.generation||steady.counts.acks<=baseline.counts.acks+15)throw new Error('Continuous stream did not remain stable for30s');
  const initialCamera=wallBaseline.cameras.find(c=>c.id===camera.id),steadyCamera=wallSteady.cameras.find(c=>c.id===camera.id);
  if(wallSteady.counts.opens!==wallBaseline.counts.opens||wallSteady.counts.closes!==wallBaseline.counts.closes)throw new Error('Wall socket churned during30s');
  if(!initialCamera||!steadyCamera||steadyCamera.feed!=='live'||steadyCamera.generation!==initialCamera.generation||steadyCamera.framesReceived<=initialCamera.framesReceived)throw new Error('Wall camera generation/feed/frame counter was not stable and advancing');
  if(wallSteady.counts.binary<=wallBaseline.counts.binary)throw new Error('Wall received no fresh preview packets during30s');
  if(steady.counts.reports<=baseline.counts.reports)throw new Error('Actual analysis reports did not advance during30s');
  for(const model of ['nivra-browser-rtmo-t-motion-v1','nivra-browser-motion-v1']){
   if(!steady.models[model]||steady.models[model].reports<=(baseline.models[model]?.reports??0)||steady.models[model].lastTimestamp<=(baseline.models[model]?.lastTimestamp??-1))throw new Error('Fresh reports did not advance for '+model);
  }
  if(!crowdAssets||!fullAssets)throw new Error('Crowd and fast motion model assets were not observed');
  if(steady.models['nivra-browser-rtmo-t-motion-v1'].type!=='device-result'||steady.models['nivra-browser-motion-v1'].type!=='device-motion')throw new Error('Expected separate crowd and fast motion report lanes');
  const initialFullAssets=fullAssets,initialCrowdAssets=crowdAssets;
  for(let cycle=1;cycle<=3;cycle++){
   const before=await safeState(phone),beforeWall=await safeState(wall);const t=Date.now();
   const closed=await phone.evaluate(()=>window.__qa.close('/api/v2/camera/stream'));
   const wallClosed=await wall.evaluate(()=>window.__qa.close('/api/v2/operator'));
   if(closed!==1||wallClosed!==1)throw new Error('Expected one open camera and wall socket to interrupt');
   await phone.waitForFunction(old=>window.__qa.counts.ready>old.ready&&window.__qa.counts.acks>old.acks&&window.__qa.videoAcks>old.videoAcks+8,before.counts,{timeout:45000});
   await wall.waitForFunction(old=>window.__qa.counts.opens>old.opens&&window.__qa.counts.snapshots>old.snapshots&&window.__qa.counts.binary>old.binary,beforeWall.counts,{timeout:45000});
   await phone.waitForFunction(models=>['nivra-browser-rtmo-t-motion-v1','nivra-browser-motion-v1'].every(model=>window.__qa.models[model]?.reports>(models[model]?.reports??0)&&window.__qa.models[model]?.lastTimestamp>(models[model]?.lastTimestamp??-1)),before.models,{timeout:45000});
   const after=await safeState(phone);
   await wall.waitForFunction(({id,gen})=>window.__qa.lastSnapshot?.cameras.some(c=>c.id===id&&c.feed==='live'&&c.generation===gen),{id:camera.id,gen:after.ready.generation},{timeout:15000});
   const afterWall=await safeState(wall);
   if(fullAssets!==initialFullAssets||crowdAssets!==initialCrowdAssets)throw new Error('Pose model asset reloaded on reconnect cycle'+cycle);
   const currentCamera=afterWall.cameras.find(c=>c.id===camera.id);
   if(!currentCamera||currentCamera.feed!=='live')throw new Error('Wall feed did not resume live after cycle'+cycle);
   metadata.cycles.push({cycle,closed,wallClosed,recoveredMs:Date.now()-t,before,after,wall:afterWall,fullModelAssetResponses:fullAssets,crowdModelAssetResponses:crowdAssets});
   await phone.waitForTimeout(2000);
  }
  const guard=await post('/guards',{callsign:'G1',name:'QA Guard',floorName:'QA floor'});
  const guardPair=await post('/guards/'+guard.callsign+'/pair');
  const guardContext=await browser.newContext({viewport:{width:390,height:844}});contexts.push(guardContext);await guardContext.addInitScript(instrument);const guardPhone=await guardContext.newPage();await guardPhone.goto(guardPair.url,{waitUntil:'domcontentloaded'});await guardPhone.getByRole('button',{name:'Start shift',exact:true}).click({timeout:30000});
  await guardPhone.waitForFunction(()=>window.__qa.peers.some(p=>p.kind==='/api/v2/guard/stream'&&p.socket.readyState===1),null,{timeout:30000});
  const beforeGuard=await safeState(guardPhone);await guardPhone.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));await guardPhone.waitForTimeout(1200);const afterGuard=await safeState(guardPhone);metadata.guard={before:beforeGuard,after:afterGuard,healthySocketPreserved:afterGuard.counts.opens===beforeGuard.counts.opens&&afterGuard.counts.closes===beforeGuard.counts.closes&&afterGuard.open.includes('/api/v2/guard/stream')};
  if(!metadata.guard.healthySocketPreserved)throw new Error('Guard resume interrupted a healthy socket');
  await phone.screenshot({path:path.join(DIR,'phone.png')});await wall.screenshot({path:path.join(DIR,'wall.png')});
  metadata.status='passed';
 }catch(e){metadata.status='failed';metadata.error=String(e.message).replace(/https?:\/\/[^\s]+/g,'[URL hidden]').replace(/pair=[A-Za-z0-9_-]+/g,'pair=[hidden]');}
 finally{
  if(workspaceCreated&&owner){
   for(let attempt=1;attempt<=3;attempt++){
    try{const r=await owner.request.delete(BASE+'/api/v2/workspaces/current',{headers:{Origin:BASE},timeout:20000});metadata.cleanup={status:r.status(),complete:r.status()===204,attempts:attempt};if(r.status()===204){fs.rmSync(path.join(DIR,'private-owner-storage.json'),{force:true});break;}}
    catch(e){metadata.cleanup={complete:false,error:e.name,attempts:attempt};}
    if(attempt<3)await new Promise(resolve=>setTimeout(resolve,attempt*1000));
   }
  }
  await browser.close();if(metadata.status!=='passed'||!metadata.cleanup?.complete)process.exitCode=1;fs.writeFileSync(path.join(DIR,'report.json'),JSON.stringify(metadata,null,2));console.log(JSON.stringify({status:metadata.status,error:metadata.error,cycles:metadata.cycles.length,cleanup:metadata.cleanup,report:path.join(DIR,'report.json')}));
 }
}
main().catch(e=>{console.error(String(e.message).replace(/https?:\/\/[^\s]+/g,'[URL hidden]'));process.exit(1)});
