from pathlib import Path
import sys, json, shutil, hashlib, zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'round-03/sources/python-deps'))
from fontTools.ttLib import TTFont as Font
from fontTools.varLib.instancer import instantiateVariableFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from pypdf import PdfReader
import pypdfium2 as pdfium
from PIL import Image

R=Path(__file__).resolve().parent
G=Path('C:/Users/harsh.DESKTOP-VE90R6D/.codex/generated_images/01a0abda-4268-7ac3-8edf-4df75e704bd5')
F=R/'fonts'
for weight in (400,600,700):
    f=instantiateVariableFont(Font(F/'IBMPlexSans[wdth,wght].ttf'), {'wght':weight,'wdth':100}, inplace=False)
    for nid,val in ((1,'IBM Plex Sans'),(2,str(weight)),(4,f'IBM Plex Sans {weight}'),(6,f'IBMPlexSans-{weight}')):
        f['name'].setName(val,nid,3,1,0x409)
    p=F/f'IBMPlexSans-{weight}.ttf';f.save(p)
    pdfmetrics.registerFont(TTFont(f'P{weight}',str(p)))
pdfmetrics.registerFont(TTFont('Mono',str(F/'IBMPlexMono-Regular.ttf')))
K=[
dict(id='01-signal',name='Signal',source='exec-ca492cd3-a1d9-48d1-9eed-06400e52be9e.png',colors=['#1748FF','#121724','#F3F6FF','#8492A7'],names=['Signal blue','Obsidian','Cloud','Steel'],idea='Repeated observations resolve into a focused signal.',rule='Carry the interrupted scan bands into image crops and evidence strips. Use one selected frame to break the repeated rhythm.',risk='The small symbol can resemble a generic data mark. Its silhouette and internal gap need refinement after selection.',pairs=[(2,1),(1,2),(2,0)],role='Blue identifies the brand and selection. Obsidian supports long review sessions; Cloud keeps communication clear.'),
dict(id='02-context',name='Context',source='exec-c719b6a0-4b76-4a71-85a6-8a04d3fb203c.png',colors=['#35D8F2','#091A26','#EEF7F8','#6D8390'],names=['Ice cyan','Deep ink','Frost','Slate'],idea='Two observation fields form one shared window.',rule='Use paired offset crops to join a wider scene with the moment under review. The opening stays clear and consistent.',risk='The symbol may read as a general software or spatial brand. Its category fit relies more heavily on the full system.',pairs=[(1,2),(2,1),(1,0)],role='Cyan marks the selected observation. Deep ink grounds the identity; Frost gives the imagery breathing room.'),
dict(id='03-lead-time',name='Lead Time',source='exec-5ec78c63-fc85-4ca8-9813-6c8e6b39ed83.png',colors=['#FFC146','#171D24','#F5F5F1','#9BA5AF'],names=['Signal amber','Carbon','Chalk','Alloy'],idea='Consecutive moments create an interval to act.',rule='Use three consecutive frames and a visible interruption. Expand the selected moment into a human-review panel.',risk='The stepped construction feels mechanical and may resemble a media or industrial mark. Avoid hazard stripes and warning-sign styling.',pairs=[(1,2),(2,1),(1,0)],role='Amber supplies presence and selected-state emphasis. Carbon supplies structure; Chalk supports readable content.')]

def lum(h):
    vals=[int(h[i:i+2],16)/255 for i in (1,3,5)]
    vals=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in vals]
    return sum(v*w for v,w in zip(vals,(.2126,.7152,.0722)))
def contrast(a,b):
    lo,hi=sorted((lum(a),lum(b)));return (hi+.05)/(lo+.05)

W,H=1200,800
out=R/'NIVRA-AI-security-brand-proposals.pdf'
c=canvas.Canvas(str(out),pagesize=(W,H))
c.setTitle('NIVRA / AI surveillance and threat prevention / researched brand proposals')
c.setAuthor('Prepared for Harsh Jain')
def box(x,y,w,h,col):
    c.setFillColor(HexColor(col));c.rect(x,H-y-h,w,h,fill=1,stroke=0)
def txt(x,y,s,size=17,weight=400,col='#121724',font=None):
    c.setFillColor(HexColor(col));c.setFont(font or f'P{weight}',size);c.drawString(x,H-y-size,s)
def para(x,y,s,width,size=17,col='#121724'):
    line=''
    for word in s.split():
        nxt=(line+' '+word).strip()
        if line and pdfmetrics.stringWidth(nxt,'P400',size)>width:
            txt(x,y,line,size,col=col);y+=size*1.4;line=word
        else:line=nxt
    if line:txt(x,y,line,size,col=col);y+=size*1.4
    return y
def page(title,number):
    box(0,0,W,H,'#F3F6FF');txt(48,25,'NIVRA / AI SECURITY',12,600)
    txt(855,25,'RESEARCH-LED PROPOSALS / 2026',12)
    box(48,60,1104,1,'#8492A7');txt(48,87,title,40,600)
    txt(48,763,'PROPOSED IDENTITY / USER SELECTION PENDING',10)
    txt(1100,763,f'{number:02} / 08',10)

page('A company identity built around the product.',1)
txt(48,166,'AI surveillance & threat prevention',34,600)
para(48,225,'Continuous observation becomes an actionable signal. NIVRA analyses camera sequences, surfaces a developing event for human review, then supports a coordinated response.',1040,22)
refs=[('Ambient.ai','Technical precision and serious security positioning.','https://www.ambient.ai/'),('Coram','Clean spatial explanation, with the product doing the talking.','https://www.coram.ai/'),('Spot AI','A connected system of colour, video and visible analysis.','https://www.spot.ai/')]
for i,(name,desc,url) in enumerate(refs):
    x=48+i*376;box(x,352,352,172,'#FFFFFF');txt(x+20,374,name,25,600)
    para(x+20,421,desc,306,18)
    c.linkURL(url,(x,H-524,x+352,H-352),relative=0)
txt(48,567,'One premise. Three executions.',24,600)
para(48,611,'The following directions test scan rhythm, shared context and lead time. They are complete identity proposals for comparison, not approved production logos. Competitor observations are design assessments; vendor product claims are not independently verified.',1080,18)
txt(48,713,'Full seven-company audit, live-site links and historical design cases: COMPETITORS.md',12)
c.showPage()

for i,k in enumerate(K):
    d=R/k['id'];d.mkdir(exist_ok=True)
    board=d/'brand-board.png';shutil.copy2(G/k['source'],board)
    with Image.open(board) as im:assert im.size==(1536,1024)
    c.drawImage(str(board),0,0,W,H);c.showPage()
    page(k['name']+' / colour, type and use',3+i*2)
    for j,(n,col) in enumerate(zip(k['names'],k['colors'])):
        x=48+j*282;box(x,164,256,83,col);txt(x,260,n,18,600);txt(x,290,col,15,font='Mono')
    txt(48,337,'IBM Plex Sans',34,600)
    txt(48,389,'Before impact.',44,700)
    txt(48,455,'Aa Bb Cc / 0123456789',25)
    para(48,507,'Headings 600-700. Body 400, 16 px minimum with 1.5 line height. IBM Plex Mono for timestamps and compact technical labels. Keep NIVRA plain and compact; refine the oversized generated lettering after selection.',516,16)
    txt(624,338,'READABLE TEXT COMBINATIONS',12,600)
    pairs=[]
    for j,(a,b) in enumerate(k['pairs']):
        fg,bg=k['colors'][a],k['colors'][b];ratio=contrast(fg,bg);assert ratio>=4.5
        pairs.append(dict(foreground=fg,background=bg,ratio=round(ratio,2)))
        box(624,371+j*57,528,46,bg);txt(640,381+j*57,f'Review sequence / {ratio:.2f}:1',17,600,fg)
    para(624,554,k['role']+' Brand accent is not an alert severity. Status needs a label and icon as well as colour.',516,16)
    txt(48,644,k['idea'],22,600)
    para(48,687,k['rule'],1070,16)
    c.showPage()
    tokens=dict(brand='NIVRA',status='proposal-not-approved',direction=k['name'],palette=dict(zip(k['names'],k['colors'])),typography=dict(family='IBM Plex Sans',weights=[400,600,700],labels='IBM Plex Mono',body_min_px=16,line_height=1.5),contrast=pairs,logo='Generated raster concept; vector master pending selection')
    (d/'tokens.json').write_text(json.dumps(tokens,indent=2),encoding='utf-8')
    (d/'tokens.css').write_text(':root {\n'+''.join(f'  --nivra-{n.lower().replace(" ","-")}: {col};\n' for n,col in zip(k['names'],k['colors']))+'  --nivra-font: "IBM Plex Sans", sans-serif;\n  --nivra-mono: "IBM Plex Mono", monospace;\n}\n',encoding='utf-8')
    (d/'README.md').write_text(f'# NIVRA / {k["name"]}\n\nProposal, not approved.\n\n{k["idea"]}\n\n{k["rule"]}\n\n## Colour\n\n{k["role"]}\n\nUse the supplied tokens as exact values. Generated board pixels, hex lettering and font rendering are illustrative; the native PDF specification and tokens are authoritative. In particular, Context uses #35D8F2.\n\n## Honest design risk\n\n{k["risk"]}\n\n## Finalisation after selection\n\nRefine a compact supporting wordmark, draw and optically correct the selected vector symbol, check at 16/24/32 px, create tested single-colour lockups and clear-space rules. The raster board is not a production logo asset or evidence of an operating product.\n',encoding='utf-8')

page('What I would take forward.',8)
for i,k in enumerate(K):
    y=170+i*142;txt(48,y,f'{i+1:02} / {k["name"]}',25,600)
    para(338,y,k['risk'],798,18)
    box(48,y+111,1104,1,'#B8C1D0')
txt(48,619,'Recommendation: Signal',27,600)
para(48,664,'Its graphic language connects most consistently to observation and review. This is a design recommendation, not proof of distinctiveness. Selection comes before vector finalisation, small-size testing and a dedicated similarity search.',1080,18)
c.showPage();c.save()

reader=PdfReader(str(out));assert len(reader.pages)==8
assert 'IBM Plex Sans' in reader.pages[2].extract_text()
qa=R/'qa';qa.mkdir(exist_ok=True)
doc=pdfium.PdfDocument(str(out))
for i in range(len(doc)):doc[i].render(scale=.8).to_pil().save(qa/f'{i+1:02}.png')
for f in F.glob('*OFL.txt'):assert 'SIL OPEN FONT LICENSE' in f.read_text(encoding='utf-8')
(R/'font-sources.json').write_text(json.dumps(dict(source='https://github.com/google/fonts',families=['ofl/ibmplexsans','ofl/ibmplexmono'],retrieved='2026-09-17',license='SIL Open Font License 1.1',files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in F.iterdir()}),indent=2),encoding='utf-8')
(R/'README.md').write_text('# NIVRA / AI security identity proposals\n\nResearched and prepared 17 September 2026 for Harsh Jain. Three independently generated, visually inspected directions grounded in AI surveillance and threat prevention. All previous concepts are rejected; none of this round is approved yet.\n\n## Contents\n\n- Eight-page review PDF: research, three full identity boards, exact colour and typography pages, and candid comparison.\n- Three direction folders: raster board, precise JSON/CSS colour tokens and usage notes.\n- Licensed IBM Plex Sans and Mono fonts plus sources and hashes.\n- COMPETITORS.md: seven-company audit, official links and historical design sources.\n- PROMPTS.md: generation provenance; build.py: reproducible document authoring.\n\n## Scope and verification\n\nAll PDF pages rendered for review. Native text extracted successfully. Listed small-text colour pairs exceed 4.5:1; this is not an accessibility audit of generated UI. Font licences and package integrity checked. Generated UI, people and surveillance scenes are illustrative. No deployed product, performance or customer claim is made.\n\nLogo geometry, exact generated typography, 16-pixel recognition and trademark/similarity clearance remain unverified. Final editable logo masters and final brand applications follow selection. The review is deliberately candid about each concept\'s limitations.\n',encoding='utf-8')
archive=R.parent/'NIVRA-AI-security-brand-proposals.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in R.rglob('*'):
        if p.is_file() and 'qa' not in p.parts:z.write(p,p.relative_to(R))
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
print(json.dumps(dict(pdf=str(out),pages=8,zip=str(archive),bytes=archive.stat().st_size,contrast={k['name']:[round(contrast(k['colors'][a],k['colors'][b]),2) for a,b in k['pairs']] for k in K}),indent=2))
