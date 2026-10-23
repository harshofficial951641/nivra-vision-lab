# Verbatim preprocessing definitions from T7 probe.py; source snapshot for parity only.
# Source SHA256: 233b55f7002be7975b9d9f81b8270407e19d35261857dfba2ab89c4c1f27fc56
def decode_record(job):
    row,windows=job;cv2.setNumThreads(1);pending=[]
    for w in windows:
        folder=CACHE/cache_key(w);file=folder/'frames.npy';receipt=folder/'complete.json'
        if receipt.exists():
            r=json.loads(receipt.read_text());assert r['source_sha256']==row['sha256'] and sha(file)==r['frames_sha256'];continue
        folder.mkdir(parents=True,exist_ok=True)
        targets=np.linspace(w['startMs'],w['endMs'],16,endpoint=False)
        pending.append({'w':w,'folder':folder,'targets':targets,'selected':{},'pts':[None]*16})
    if not pending:return {'id':row['id'],'cached':True}
    assert sha(row['path'])==row['sha256']
    tasks=sorted((float(t),j,i) for j,p in enumerate(pending) for i,t in enumerate(p['targets']))
    cap=cv2.VideoCapture(row['path']);assert cap.isOpened(),row['path'];last_t=-math.inf;previous=None;cursor=0
    try:
        while cursor<len(tasks):
            ok,bgr=cap.read()
            if not ok:break
            t=float(cap.get(cv2.CAP_PROP_POS_MSEC));assert math.isfinite(t) and t>=0 and t>last_t,('invalid PTS',row['id'],last_t,t)
            rgb=bgr;converted={}
            while cursor<len(tasks) and tasks[cursor][0]<=t:
                target,j,i=tasks[cursor];p=pending[j];w=p['w'];choices=[]
                if previous is not None and w['startMs']<=last_t<w['endMs']:choices.append((abs(last_t-target),last_t,previous))
                if w['startMs']<=t<w['endMs']:choices.append((abs(t-target),t,rgb))
                assert choices,('no in-window frame',w['id'],target,t)
                _,selected_t,image=min(choices,key=lambda z:(z[0],z[1]))
                if selected_t not in converted:converted[selected_t]=cv2.cvtColor(cv2.resize(image,(224,224)),cv2.COLOR_BGR2RGB)
                p['selected'][i]=converted[selected_t].copy();p['pts'][i]=selected_t;cursor+=1
            last_t=t;previous=rgb
        assert cursor==len(tasks),('truncated source',row['id'],cursor,len(tasks))
    finally:cap.release()
    for p in pending:
        folder=p['folder'];array=np.stack([p['selected'][i] for i in range(16)]);np.save(folder/'frames.npy',array,allow_pickle=False)
        write(folder/'complete.json',{'source_sha256':row['sha256'],'frames_sha256':sha(folder/'frames.npy'),'selected_pts_ms':p['pts'],'shape':list(array.shape),'window_id':p['w']['id'],'sampling':'16 equally spaced targets inside [start,end), nearest actual source PTS, earlier ties','decoder':cv2.__version__})
    return {'id':row['id'],'decoded':len(pending)}

class Clips(Dataset):
    def __init__(self,windows,kind,epoch=0):self.windows=windows;self.kind=kind;self.epoch=epoch
    def __len__(self):return len(self.windows)
    def __getitem__(self,i):
        w=self.windows[i];a=np.load(CACHE/cache_key(w)/'frames.npy',allow_pickle=False)
        if self.kind=='baseline':x=torch.from_numpy(a.copy()).permute(3,0,1,2).float()/255;return (x-.45)/.225,w['label'],i
        a=a[np.linspace(0,15,8).astype(int)].copy();size=224 if self.kind=='tsm' else 172
        rng=np.random.default_rng(SEED+self.epoch*100003+i)
        if self.epoch:
            if rng.random()<.5:a=a[:,:,::-1].copy()
            gamma=rng.uniform(.85,1.2);gain=rng.uniform(.75,1.15);lut=np.clip((np.arange(256)/255.)**gamma*255*gain,0,255).astype(np.uint8);a=lut[a]
            if rng.random()<.15:
                gray=np.stack([cv2.cvtColor(v,cv2.COLOR_RGB2GRAY) for v in a]);a=np.repeat(gray[:,:,:,None],3,axis=3)
            if rng.random()<.35:
                side=int(rng.integers(80,180));a=np.stack([cv2.resize(cv2.resize(v,(side,side)),(224,224)) for v in a])
            if rng.random()<.35:
                quality=int(rng.integers(40,86));images=[]
                for v in a:
                    ok,b=cv2.imencode('.jpg',cv2.cvtColor(v,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,quality]);assert ok;images.append(cv2.cvtColor(cv2.imdecode(b,cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB))
                a=np.stack(images)
        if size!=224:a=np.stack([cv2.resize(v,(size,size)) for v in a])
        x=torch.from_numpy(a.copy()).permute(0,3,1,2).float()/255
        if self.kind=='tsm':x=(x-torch.tensor([.485,.456,.406])[None,:,None,None])/torch.tensor([.229,.224,.225])[None,:,None,None]
        return x,w['label'],i
