from pathlib import Path
import json, zipfile, hashlib, xml.etree.ElementTree as ET
from pypdf import PdfReader

root=Path(__file__).resolve().parent
dirs=[root/'01-insight',root/'02-assurance',root/'03-vigil']
files=[]
for d in dirs:
    pdfs=list(d.glob('*.pdf')); assert len(pdfs)==1
    assert len(PdfReader(str(pdfs[0])).pages)==6
    svgs=list((d/'templates').glob('*.svg')); assert len(svgs)==3
    for svg in svgs:
        tree=ET.parse(svg); assert tree.getroot().tag.endswith('svg')
        raw=svg.read_text(encoding='utf-8')
        assert raw.count('@font-face')==3 and '<text ' in raw
        assert 'http://' not in raw.replace('http://www.w3.org/2000/svg','')
    files.extend(p for p in d.rglob('*') if p.is_file())
files.extend(root/n for n in ['README.md','QA.md','font-sources.json','manifest.json'])
index={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(root/'SHA256.json').write_text(json.dumps(index,indent=2),encoding='utf-8')
files.append(root/'SHA256.json')
output=root.parent/'NIVRA-brand-kit-proposals.zip'
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,'NIVRA-brand-kit-proposals/'+str(p.relative_to(root)).replace('\\','/'))
with zipfile.ZipFile(output) as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(files)
    assert len([n for n in z.namelist() if n.endswith('.svg')])==9
    assert len([n for n in z.namelist() if n.endswith('.pdf')])==3
print(json.dumps({'zip':str(output),'files':len(files),'bytes':output.stat().st_size,'pdfs':3,'svg_templates':9,'integrity':'passed'},indent=2))
