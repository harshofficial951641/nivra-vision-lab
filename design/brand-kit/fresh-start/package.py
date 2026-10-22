from pathlib import Path
import zipfile, json, hashlib
R=Path(__file__).resolve().parent
files=[R/n for n in ['NIVRA-new-brand-kit-directions.pdf','README.md','BRIEF.md','PROMPTS.md','font-sources.json','manifest.json']]
for folder in ['01-keeper','02-intercept','03-widefield']:
    files.extend(p for p in (R/folder).rglob('*') if p.is_file())
out=R.parent/'NIVRA-new-brand-kit-directions.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,'NIVRA-new-directions/'+p.relative_to(R).as_posix())
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    assert len([n for n in z.namelist() if n.endswith('.pdf')])==1
    assert len([n for n in z.namelist() if n.endswith('.svg')])==3
print(json.dumps({'path':str(out),'files':len(files),'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'integrity':'passed'},indent=2))
