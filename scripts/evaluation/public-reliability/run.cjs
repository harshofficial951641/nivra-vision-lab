const {chromium}=require('playwright');
const fs=require('fs'); const path=require('path');
const DIR=path.resolve('test-results/public-reliability-qa'), BASE='https://nivra.tanishq.work';
fs.mkdirSync(DIR,{recursive:true,mode:0o700});fs.chmodSync(DIR,0o700);
const metadata={started:new Date().toISOString(),cycles:[],checks:[]};
function instrument(){
 const Native=window.WebSocket;const peers=[];
 window.__qa={peers,counts:{ready:0,acks:0,snapshots:0,opens:0,closes:0,reports:0,statuses:0,binary:0},lastReady:null,lastSnapshot:null};
 window.WebSocket=class extends Native{
  constructor(url,protocols){super(url,protocols);const kind=new URL(url).pathname;peers.push({socket:this,kind});this.addEventListener('open',()=>window.__qa.counts.opens++);this.addEventListener('close',()=>window.__qa.counts.closes++);this.addEventListener('message',e=>{if(typeof e.data!=='string'){window.__qa.counts.binary++;return;}try{const m=JSON.parse(e.data);if(m.type==='ready'){window.__qa.counts.ready++;window.__qa.lastReady={cameraId:m.cameraId,generation:m.generation};}if(m.type==='accepted')window.__qa.counts.acks++;if(m.type==='snapshot'){window.__qa.counts.snapshots++;window.__qa.lastSnapshot=m;}}catch{}});}
  send(data){if(typeof data==='string'){try{const m=JSON.parse(data);if(m.type==='device-result'||m.type==='device-motion')window.__qa.counts.reports++;if(m.type==='device-status'||m.type==='device-motion-status')window.__qa.counts.statuses++;}catch{}}return super.send(data);}
 };
 window.__qa.close=function(kind){let n=0;for(const p of peers)if(p.kind===kind&&p.socket.readyState===1){p.socket.close(1000,'QA transport interruption');n++;}return n;};
}
function fakeCamera(){
 navigator.mediaDevices.getUserMedia=async()=>{
  const canvas=document.createElement('canvas');canvas.width=640;canvas.height=360;const ctx=canvas.getContext('2d');let frame=0;
  const timer=setInterval(()=>{ctx.fillStyle='#23272c';ctx.fillRect(0,0,640,360);ctx.fillStyle='#ddd';ctx.fillRect((frame++*7)%600,150,40,40);ctx.fillStyle='#fff';ctx.font='20px sans-serif';ctx.fillText('Synthetic transport QA',20,35);},80);
  const stream=canvas.captureStream(12);stream.getTracks().forEach(t=>t.addEventListener('ended',()=>clearInterval(timer)));return stream;
 };
}
async function safeState(page){return page.evaluate(()=>({counts:{...window.__qa.counts},open:window.__qa.peers.filter(p=>p.socket.readyState===1).map(p=>p.kind),ready:window.__qa.lastReady,cameras:window.__qa.lastSnapshot?.cameras.map(c=>({id:c.id,feed:c.feed,generation:c.generation,framesReceived:c.framesReceived,framesAnalyzed:c.framesAnalyzed}))??[]}));}
async function main(){
 if(process.env.NIVRA_QA_RELEASE_READY!=='1')throw new Error('Release-ready gate is closed.');
 const browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
 let owner,workspaceCreated=false;const contexts=[];
 try{
  owner=await browser.newContext({viewport:{width:1280,height:800}});contexts.push(owner);await owner.addInitScript(instrument);
  const post=async(p,body)=>{const r=await owner.request.post(BASE+'/api/v2'+p,{headers:{Origin:BASE},data:body??{},timeout:35000});if(!r.ok())throw new Error('QA API '+p.replace(/[0-9a-f-]{36}/g,'[id]')+' returned '+r.status());return r.json();};
  await post('/workspaces',{name:'Private reliability QA '+Date.now()});workspaceCreated=true;
  // Recovery cookies stay in this private ignored file for cleanup only.
  await owner.storageState({path:path.join(DIR,'private-owner-storage.json')});
  const camera=await post('/cameras',{name:'Synthetic QA camera',building:'Private QA',floor:'1'});
  const pair=await post('/cameras/'+camera.id+'/pair');
  const wall=await owner.newPage();await wall.goto(BASE+'/wall',{waitUntil:'domcontentloaded'});
  const phoneContext=await browser.newContext({viewport:{width:390,height:844}});contexts.push(phoneContext);await phoneContext.addInitScript(instrument);await phoneContext.addInitScript(fakeCamera);
  const phone=await phoneContext.newPage();
  let fullAssets=0;phone.on('response',r=>{if(r.url().includes('pose_landmarker_full.task')&&r.ok())fullAssets++;});
  await phone.goto(pair.url,{waitUntil:'domcontentloaded'});
  await phone.getByRole('button',{name:'Allow camera & start',exact:true}).click({timeout:45000});
  await phone.waitForFunction(()=>window.__qa.counts.acks>=10,null,{timeout:60000});
  const baseline=await safeState(phone);const wallBaseline=await safeState(wall);
  await phone.waitForTimeout(60000);
  const steady=await safeState(phone),wallSteady=await safeState(wall);
  metadata.continuous={baseline,steady,wallBaseline,wallSteady,fullModelAssetLoaded:fullAssets>0,fullModelAssetResponses:fullAssets};
  if(steady.counts.ready!==baseline.counts.ready||steady.counts.acks<=baseline.counts.acks+50)throw new Error('Continuous stream did not remain stable for60s');
  const initialCamera=wallBaseline.cameras.find(c=>c.id===camera.id),steadyCamera=wallSteady.cameras.find(c=>c.id===camera.id);
  if(wallSteady.counts.opens!==wallBaseline.counts.opens||wallSteady.counts.closes!==wallBaseline.counts.closes)throw new Error('Wall socket churned during60s');
  if(!initialCamera||!steadyCamera||steadyCamera.feed!=='live'||steadyCamera.generation!==initialCamera.generation||steadyCamera.framesReceived<=initialCamera.framesReceived)throw new Error('Wall camera generation/feed/frame counter was not stable and advancing');
  if(wallSteady.counts.binary<=wallBaseline.counts.binary)throw new Error('Wall received no fresh preview packets during60s');
  if(steady.counts.reports<=baseline.counts.reports)throw new Error('Actual analysis reports did not advance during60s');
  if(!fullAssets)throw new Error('Full model asset was not observed loading');
  const initialFullAssets=fullAssets;
  for(let cycle=1;cycle<=3;cycle++){
   const before=await safeState(phone),beforeWall=await safeState(wall);const t=Date.now();
   const closed=await phone.evaluate(()=>window.__qa.close('/api/v2/camera/stream'));
   const wallClosed=await wall.evaluate(()=>window.__qa.close('/api/v2/operator'));
   await phone.waitForFunction(old=>window.__qa.counts.ready>old.ready&&window.__qa.counts.acks>old.acks+8,before.counts,{timeout:45000});
   await wall.waitForFunction(old=>window.__qa.counts.opens>old.opens&&window.__qa.counts.snapshots>old.snapshots&&window.__qa.counts.binary>old.binary,beforeWall.counts,{timeout:45000});
   await phone.waitForFunction(old=>window.__qa.counts.reports>old.reports,before.counts,{timeout:45000});
   const after=await safeState(phone);
   await wall.waitForFunction(({id,gen})=>window.__qa.lastSnapshot?.cameras.some(c=>c.id===id&&c.feed==='live'&&c.generation===gen),{id:camera.id,gen:after.ready.generation},{timeout:15000});
   const afterWall=await safeState(wall);
   if(fullAssets!==initialFullAssets)throw new Error('Full model asset reloaded on reconnect cycle'+cycle);
   const currentCamera=afterWall.cameras.find(c=>c.id===camera.id);
   if(!currentCamera||currentCamera.feed!=='live')throw new Error('Wall feed did not resume live after cycle'+cycle);
   metadata.cycles.push({cycle,closed,wallClosed,recoveredMs:Date.now()-t,before,after,wall:afterWall,fullModelAssetResponses:fullAssets});
   await phone.waitForTimeout(2000);
  }
  const guard=await post('/guards',{callsign:'G1',name:'QA Guard',floorName:'QA floor'});
  const guardPair=await post('/guards/'+guard.callsign+'/pair');
  const guardContext=await browser.newContext({viewport:{width:390,height:844}});contexts.push(guardContext);await guardContext.addInitScript(instrument);const guardPhone=await guardContext.newPage();await guardPhone.goto(guardPair.url,{waitUntil:'domcontentloaded'});await guardPhone.getByRole('button',{name:'Start shift',exact:true}).click({timeout:30000});
  await guardPhone.waitForFunction(()=>window.__qa.peers.some(p=>p.kind==='/api/v2/guard/stream'&&p.socket.readyState===1),null,{timeout:30000});
  const beforeGuard=await safeState(guardPhone);await guardPhone.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));await guardPhone.waitForTimeout(1200);const afterGuard=await safeState(guardPhone);metadata.guard={before:beforeGuard,after:afterGuard,healthySocketPreserved:afterGuard.counts.opens===beforeGuard.counts.opens};
  await phone.screenshot({path:path.join(DIR,'phone.png')});await wall.screenshot({path:path.join(DIR,'wall.png')});
  metadata.status='passed';
 }catch(e){metadata.status='failed';metadata.error=String(e.message).replace(/https?:\/\/[^\s]+/g,'[URL hidden]').replace(/pair=[A-Za-z0-9_-]+/g,'pair=[hidden]');}
 finally{
  if(workspaceCreated&&owner){try{const r=await owner.request.delete(BASE+'/api/v2/workspaces/current',{headers:{Origin:BASE},timeout:35000});metadata.cleanup={status:r.status(),complete:r.status()===204};if(r.status()===204)fs.rmSync(path.join(DIR,'private-owner-storage.json'),{force:true});}catch(e){metadata.cleanup={complete:false,error:e.name};}}
  await browser.close();if(metadata.status!=='passed'||!metadata.cleanup?.complete)process.exitCode=1;fs.writeFileSync(path.join(DIR,'report.json'),JSON.stringify(metadata,null,2));console.log(JSON.stringify({status:metadata.status,error:metadata.error,cycles:metadata.cycles.length,cleanup:metadata.cleanup,report:path.join(DIR,'report.json')}));
 }
}
main().catch(e=>{console.error(String(e.message).replace(/https?:\/\/[^\s]+/g,'[URL hidden]'));process.exit(1)});
