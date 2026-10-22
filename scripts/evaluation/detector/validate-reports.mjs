import fs from 'node:fs/promises';import path from 'node:path';import {spawn} from 'node:child_process';import {once} from 'node:events';import {pathToFileURL} from 'node:url';import {parseArgs} from 'node:util';import {build} from 'vite';import {validateCache} from './cacheContract.mjs';
const {values:args}=parseArgs({options:{split:{type:'string',default:'train'},'work-dir':{type:'string',default:'D:/nivra-work/detector'},python:{type:'string',default:'C:/Users/harsh.DESKTOP-VE90R6D/Downloads/Nivra/nivra-vision-lab/service/.venv/Scripts/python.exe'},out:{type:'string'}}});
if(!['train','dev'].includes(args.split))throw new Error('Invalid split');
const work=path.resolve(args['work-dir']),repo=path.resolve(import.meta.dirname,'../../..'),capture=JSON.parse(await fs.readFile(path.join(work,args.split+'-capture.private.json'))),selection=JSON.parse(await fs.readFile(path.join(work,'selection.json')));
if(capture.completed.length!==capture.summary.recordings||capture.failures.length||capture.pageErrors?.length)throw new Error('Incomplete capture');
await build({configFile:false,logLevel:'error',build:{lib:{entry:path.join(repo,'src/classroom/deviceAnalysis.ts'),formats:['es'],fileName:()=> 'contractAnalysis.mjs'},outDir:path.join(work,'runtime'),emptyOutDir:false,minify:false}});
const {DualLaneConflictAnalysis,DETECTOR_EXPERIMENTS}=await import(pathToFileURL(path.join(work,'runtime/contractAnalysis.mjs')));
const configuration=DETECTOR_EXPERIMENTS.find(p=>p.name===selection.chosen);if(!configuration)throw new Error('Unknown frozen profile');
const source=String.raw`import sys,json,importlib.util,collections
spec=importlib.util.spec_from_file_location('nivra_device_contract',sys.argv[1]);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
validated=0;rejected=0;max_bytes=0;errors=collections.Counter()
for line in sys.stdin:
    if not line.strip(): continue
    max_bytes=max(max_bytes,len(line.encode('utf-8')))
    try:
        data=json.loads(line)
        if len(line.encode('utf-8'))>module.MAX_REPORT_BYTES: raise ValueError('report-byte-limit')
        cls=module.DeviceMotion if data['type']=='device-motion' else module.DeviceResult
        cls.model_validate(data);validated+=1
    except Exception as error:
        rejected+=1;errors[type(error).__name__]+=1
print(json.dumps(dict(validatedReports=validated,rejectedReports=rejected,maxReportBytes=max_bytes,errorTypes=dict(errors))))
`;
const python=spawn(args.python,['-c',source,path.join(repo,'service/nivra/device_analysis.py')],{stdio:['pipe','pipe','inherit']});let output='';python.stdout.on('data',bytes=>output+=bytes);const finished=once(python,'exit');
for(const r of capture.completed){const cache=JSON.parse(await fs.readFile(r.cachePath));validateCache(cache,r);const analysis=new DualLaneConflictAnalysis(configuration);for(const frame of cache.frames){const report=analysis.update(frame.lane,frame.timestampMs,Math.max(frame.inferenceMs,frame.elapsedMs),frame.poses,cache.sourceWidth/cache.sourceHeight,'CPU','full',frame.people);report.type=frame.lane==='motion'?'device-motion':'device-result';if(!python.stdin.write(JSON.stringify(report)+'\n'))await once(python.stdin,'drain')}}
python.stdin.end();const [exitCode]=await finished;if(exitCode!==0)throw new Error('Python schema validator failed');
const result={schemaVersion:1,split:args.split,manifestSHA256:capture.manifestSHA256,profile:configuration.name,recordings:capture.completed.length,...JSON.parse(output)};
if(args.out){const out=path.resolve(args.out);if(!out.toLowerCase().startsWith(path.join(repo,'docs/evaluations/detector-accuracy').toLowerCase()+path.sep))throw new Error('Unexpected aggregate output path');await fs.writeFile(out,JSON.stringify(result,null,2))}
console.log(JSON.stringify(result,null,2));if(result.rejectedReports)process.exitCode=1;
