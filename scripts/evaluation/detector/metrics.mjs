/** Interval metrics over explicit labels only. Milliseconds and half-open spans. */
export const TOLERANCE_MS = 500;
export const inInterval = (t,i) => t >= i.startMs && t < i.endMs;
export const quantile = (values,q) => {if(!values.length)return null;const a=[...values].sort((x,y)=>x-y),p=(a.length-1)*q,l=Math.floor(p);return a[l]+(a[Math.ceil(p)]-a[l])*(p-l)};
export function scoreRecording(recording,alerts){
 const ordered=[...alerts].sort((a,b)=>a.occurredAtMs-b.occurredAtMs);
 const events=[...recording.events].sort((a,b)=>a.endMs-b.endMs);
 const assigned=new Map();
 const eligible=(event,alert)=>{
  const t=alert.occurredAtMs;
  if(inInterval(t,event))return true;
  return t>=event.endMs&&t<event.endMs+TOLERANCE_MS&&!recording.normalIntervals.some(i=>inInterval(t,i))&&!events.some(i=>inInterval(t,i));
 };
 // Maximum-cardinality one-to-one event/alert matching. One alert cannot recall two events.
 const match=(e,visited)=>{for(let a=0;a<ordered.length;a++){if(visited.has(a)||!eligible(events[e],ordered[a]))continue;visited.add(a);const prior=assigned.get(a);if(prior===undefined||match(prior,visited)){assigned.set(a,e);return true}}return false};
 for(let e=0;e<events.length;e++)match(e,new Set());
 const latencies=[...assigned].map(([a,e])=>Math.max(0,ordered[a].occurredAtMs-events[e].startMs));
 return {group:recording.group,context:recording.context,recordings:1,eventCount:events.length,hits:assigned.size,
  falseAlerts:ordered.filter(a=>recording.normalIntervals.some(i=>inInterval(a.occurredAtMs,i))).length,
  normalMs:recording.normalIntervals.reduce((a,i)=>a+i.endMs-i.startMs,0),latencies,
  ignoredUnknownAlerts:ordered.filter(a=>!recording.normalIntervals.some(i=>inInterval(a.occurredAtMs,i))&&!events.some(i=>eligible(i,a))).length,
  alertCount:ordered.length};
}
const sum=(rows,key)=>rows.reduce((a,r)=>a+r[key],0);
export function pointMetrics(rows){
 const eventCount=sum(rows,'eventCount'),normalMs=sum(rows,'normalMs'),latencies=rows.flatMap(r=>r.latencies);
 return {recordings:sum(rows,'recordings'),groups:new Set(rows.map(r=>r.group)).size,positiveGroups:new Set(rows.filter(r=>r.eventCount>0).map(r=>r.group)).size,normalGroups:new Set(rows.filter(r=>r.normalMs>0).map(r=>r.group)).size,eventCount,hits:sum(rows,'hits'),
  eventRecall:eventCount?sum(rows,'hits')/eventCount:null,falseAlerts:sum(rows,'falseAlerts'),normalHours:normalMs/3600000,
  falseAlertsPerHour:normalMs?sum(rows,'falseAlerts')*3600000/normalMs:null,
  medianTimeToAlertMs:quantile(latencies,.5),p90TimeToAlertMs:quantile(latencies,.9),matchedEventCount:latencies.length,
  ignoredUnknownAlerts:sum(rows,'ignoredUnknownAlerts'),alertCount:sum(rows,'alertCount')};
}
const rng = seed => () => {let t=seed+=0x6d2b79f5;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return ((t^t>>>14)>>>0)/4294967296};
export function bootstrap(rows,pairedRows=null,{iterations=10000,seed=20261023}={}){
 if(pairedRows&&rows.some((r,i)=>r.group!==pairedRows[i]?.group))throw new Error('Paired bootstrap row/group order mismatch');
 const groups=[...new Set(rows.map(r=>r.group))],index=new Map(groups.map(g=>[g,rows.flatMap((r,i)=>r.group===g?[i]:[])]));
 const random=rng(seed),names=['eventRecall','falseAlertsPerHour','medianTimeToAlertMs'],samples=Object.fromEntries(names.map(n=>[n,[]]));
 for(let n=0;n<iterations;n++){
  const selected=[];for(let k=0;k<groups.length;k++)selected.push(...index.get(groups[Math.floor(random()*groups.length)]));
  const a=pointMetrics(selected.map(i=>rows[i])),b=pairedRows?pointMetrics(selected.map(i=>pairedRows[i])):null;
  for(const name of names){if(a[name]!==null&&(!b||b[name]!==null))samples[name].push(b?b[name]-a[name]:a[name])}
 }
 return Object.fromEntries(names.map(name=>{
  const eligibleGroups=new Set(rows.filter(r=>name==='eventRecall'?r.eventCount>0:name==='falseAlertsPerHour'?r.normalMs>0:r.latencies.length>0).map(r=>r.group)).size;
  return [name,{low:eligibleGroups>=2?quantile(samples[name],.025):null,high:eligibleGroups>=2?quantile(samples[name],.975):null,eligibleGroups,validReplicates:samples[name].length,iterations}]
 }));
}
export function summarize(rows,iterations=10000){
 const overall=pointMetrics(rows),ci95=bootstrap(rows,null,{iterations});
 const contexts=Object.fromEntries([...new Set(rows.map(r=>r.context))].sort().map(c=>{const a=rows.filter(r=>r.context===c);return[c,{...pointMetrics(a),ci95:bootstrap(a,null,{iterations})}]}));
 return {...overall,ci95,contexts};
}
export function promotionGate(before,after,deltas){
 return before.eventRecall!==null&&after.eventRecall>before.eventRecall&&after.falseAlertsPerHour!==null&&after.falseAlertsPerHour<=before.falseAlertsPerHour&&deltas.eventRecall.low>0&&deltas.falseAlertsPerHour.high!==null&&deltas.falseAlertsPerHour.high<=0;
}
