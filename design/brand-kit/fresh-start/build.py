from pathlib import Path
import json, shutil, base64, html, zipfile, xml.etree.ElementTree as ET
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader
import pypdfium2 as pdfium
from PIL import Image

R=Path(__file__).resolve().parent
G=Path('C:/Users/harsh.DESKTOP-VE90R6D/.codex/generated_images/01a0abda-4268-7ac3-8edf-4df75e704bd5')
F=R.parent/'round-03/sources/fonts'
W,H=1200,800
K=[
dict(id='01',name='Keeper',source='exec-e910cff3-dbe7-4564-87af-ef72b22ec5b3.png',font='Manrope',fd='manrope',colors=['#EE542F','#242729','#DDE3E1','#FAFBF9'],names=['Vermilion','Carbon','Silver','White'],crop=[60,100,550,235],idea='A guardian that stays attentive.',reason='A settled watchdog communicates watchfulness and protection through a recognizable subject. Its posture is calm; the identity avoids an attacking animal or a police crest.',risk='The guardian is direct, but dogs are familiar security imagery. The final contour would need further differentiation. Recognition is not evidence of originality.',graphic='Use a stable baseline, a solid vermilion field and generous white space. Keep the guardian whole on small uses; avoid turning it into an all-over mascot pattern.',balance='White 45% / carbon 30% / vermilion 20% / silver 5%',pairidx=[(1,3),(1,2),(3,1)]),
dict(id='02',name='Intercept',source='exec-ae340765-4d45-4f64-8f30-4074b9a6ecd4.png',font='Plus Jakarta Sans',fd='plusjakartasans',colors=['#073F45','#52DDC0','#F2F4EE','#B5BDBC'],names=['Petrol','Aqua','Chalk','Warm steel'],crop=[95,80,835,180],idea='Hold the moment open.',reason='Separated solid forms and a small intervening stop express the moment before contact. The system uses visible intervals in its layouts, linking observation with a chance to respond.',risk='The mechanical construction is less literal. It must be tested for recognition without an explanation, and the small intervention element needs a one-colour solution.',graphic='Stop broad horizontal fields short of each other. Carry one consistent interval through the composition. Avoid chains, hidden initials or decorative technical grids.',balance='Chalk 40% / petrol 40% / aqua 15% / steel 5%',pairidx=[(0,2),(0,1),(2,0)]),
dict(id='03',name='Widefield',source='exec-eb3111c7-8dc6-45ba-a2d8-3c905d6d1399.png',font='DM Sans',fd='dmsans',colors=['#532C4C','#FF775B','#F5E9E9','#211E25'],names=['Mulberry','Persimmon','Blush','Onyx'],crop=[55,58,345,290],idea='Keep the wider situation in view.',reason='Three unequal planes spread into a broad field. The associated panoramic image language suggests awareness of a developing situation across space and time.',risk='The three-plane mark is abstract and may read as a fan or crown. Its relationship to surveillance needs to survive without the photographic presentation.',graphic='Use three unequal vertical crops or fields with clear intervals. Keep their rhythm consistent. A real sequence must never be implied by unrelated imagery.',balance='Blush 40% / mulberry 35% / onyx 15% / persimmon 10%',pairidx=[(3,2),(3,1),(2,0)])
]
def luminance(h):
    a=[int(h[i:i+2],16)/255 for i in [1,3,5]]
    a=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in a]
    return sum(v*w for v,w in zip(a,[.2126,.7152,.0722]))
def contrast(a,b):
    l,h=sorted([luminance(a),luminance(b)]);return (h+.05)/(l+.05)
def box(c,x,y,w,h,col):
    c.setFillColor(HexColor(col));c.rect(x,H-y-h,w,h,stroke=0,fill=1)
def text(c,k,x,y,s,size=18,weight=400,col=None):
    c.setFillColor(HexColor(col or '#202426'));c.setFont(k['id']+str(weight),size);c.drawString(x,H-y-size,s)
def paragraph(c,k,x,y,s,width,size=17,col=None):
    cur=''; lines=[]
    for word in s.split():
        nxt=(cur+' '+word).strip()
        if cur and pdfmetrics.stringWidth(nxt,k['id']+'400',size)>width:lines.append(cur);cur=word
        else:cur=nxt
    if cur:lines.append(cur)
    for row in lines:text(c,k,x,y,row,size,col=col);y+=size*1.42
    return y
def heading(c,k,title,n):
    box(c,0,0,W,H,'#FAFBF9');text(c,k,48,27,'NIVRA / '+k['name'].upper(),12,700)
    text(c,k,892,27,'IDENTITY PROPOSAL / '+k['id'],12,600)
    box(c,48,61,1104,1,k['colors'][0]);text(c,k,48,83,title,39,600)
    text(c,k,48,760,'DRAFT / NO DIRECTION APPROVED',10)
    text(c,k,1080,760,f'{n:02d} / 12',10)
def crop(c,path,region,x,y,w,h):
    cx,cy,cw,ch=region;sc=min(w/cw,h/ch);dx=x+(w-cw*sc)/2;dy=y+(h-ch*sc)/2
    c.saveState();p=c.beginPath();p.rect(dx,H-dy-ch*sc,cw*sc,ch*sc);c.clipPath(p,stroke=0,fill=0)
    c.drawImage(str(path),dx-cx*sc,H-(dy-cy*sc)-1024*sc,width=1536*sc,height=1024*sc);c.restoreState()

R.joinpath('qa').mkdir(exist_ok=True)
output=R/'NIVRA-new-brand-kit-directions.pdf'
c=canvas.Canvas(str(output),pagesize=(W,H));c.setTitle('NIVRA / Three new brand-kit directions');c.setAuthor('NIVRA brand development for Harsh Jain')
for ki,k in enumerate(K):
    d=R/(k['id']+'-'+k['name'].lower());d.mkdir(exist_ok=True);(d/'fonts').mkdir(exist_ok=True)
    board=d/'brand-board.png';shutil.copy2(G/k['source'],board)
    with Image.open(board) as im:assert im.size==(1536,1024)
    for weight in [400,600,700]:
        f=F/k['fd']/f"{k['fd']}-{weight}.ttf";shutil.copy2(f,d/'fonts'/f.name);pdfmetrics.registerFont(TTFont(k['id']+str(weight),str(f)))
    ofl=F/k['fd']/'OFL.txt';assert 'SIL OPEN FONT LICENSE' in ofl.read_text(encoding='utf-8');shutil.copy2(ofl,d/'fonts/OFL.txt')
    pairs=[(k['colors'][a],k['colors'][b]) for a,b in k['pairidx']]
    assert all(contrast(a,b)>=4.5 for a,b in pairs)
    tokens=dict(brand='NIVRA',direction=k['name'],status='proposal-not-approved',palette=dict(zip(k['names'],k['colors'])),typography=dict(family=k['font'],weights=[400,600,700],body=16,line_height=1.5),contrast=[dict(foreground=a,background=b,ratio=round(contrast(a,b),2)) for a,b in pairs],logo_status='Raster concept; final vector masters and minimum sizes pending selection')
    (d/'tokens.json').write_text(json.dumps(tokens,indent=2),encoding='utf-8')
    (d/'tokens.css').write_text(':root {\n'+''.join(f'  --nivra-{n.lower().replace(" ","-")}: {v};\n' for n,v in zip(k['names'],k['colors']))+f'  --nivra-font: "{k["font"]}", sans-serif;\n'+'}\n',encoding='utf-8')
    # 1: art-directed full kit, generated concept imagery.
    c.drawImage(str(board),0,0,width=W,height=H);c.showPage()
    # 2: precise editorial explanation and limits.
    heading(c,k,'Symbol and identity',ki*4+2)
    crop(c,board,k['crop'],48,167,620,310)
    text(c,k,710,163,k['idea'],23,700)
    yy=paragraph(c,k,710,211,k['reason'],435,18)
    text(c,k,710,yy+26,'What still needs testing',16,700)
    paragraph(c,k,710,yy+58,k['risk'],430,16)
    text(c,k,48,526,'Use the name plainly',20,700)
    paragraph(c,k,48,564,'NIVRA stays in normal uppercase supporting typography. No monograms, hidden letters or modified letterforms. Use one shared identity for Command, Camera, Respond, Admin and Trust.',510,17)
    text(c,k,645,526,'Reproduction',20,700)
    paragraph(c,k,645,564,'Provisional clear space: one-quarter of the symbol height. Do not stretch or rotate. Final geometry, single-colour variants, minimum size and small-screen recognition require a selected master.',505,17)
    c.showPage()
    # 3: authored palette and real type.
    heading(c,k,'Colour and typography',ki*4+3)
    for j,(name,col) in enumerate(zip(k['names'],k['colors'])):
        x=48+j*282;box(c,x,168,256,116,col)
        c.setStrokeColor(HexColor('#A3AAA7'));c.setLineWidth(.4);c.rect(x,H-284,256,116,fill=0,stroke=1)
        text(c,k,x,296,name,17,600);text(c,k,x,325,col,15)
    text(c,k,48,386,k['font'],37,600);text(c,k,48,448,'Before impact.',49,700)
    text(c,k,48,525,'Aa Bb Cc 0123456789',26)
    paragraph(c,k,48,581,'Headings 600 or 700. Body 400, 16 px minimum and 1.5 line height. Labels 600. No excessive tracking or decorative letter cuts. Font files and SIL OFL terms are supplied.',500,16)
    text(c,k,654,389,'VERIFIED SMALL-TEXT PAIRS',13,700)
    for j,(fg,bg) in enumerate(pairs):
        y=425+j*74;box(c,654,y,496,56,bg);text(c,k,674,y+15,f'Clear text / {contrast(fg,bg):.2f}:1',18,600,fg)
    paragraph(c,k,654,664,k['balance']+'. Starting proportions, not fixed quotas. Exact tokens govern colours; generated pixels are illustrative.',488,13)
    c.showPage()
    # 4: actual editable application layout, behaviour and voice.
    heading(c,k,'Brand in use',ki*4+4)
    if ki==0: bg,fg,accent=k['colors'][0],k['colors'][1],k['colors'][3]
    elif ki==1:bg,fg,accent=k['colors'][0],k['colors'][2],k['colors'][1]
    else:bg,fg,accent=k['colors'][0],k['colors'][2],k['colors'][1]
    box(c,48,162,1104,287,bg);text(c,k,78,188,'NIVRA',26,700,fg)
    text(c,k,78,249,'Before impact.',60,700,fg)
    text(c,k,80,340,'Human review. Coordinated response.',22,400,fg)
    if ki==0:
        box(c,850,162,22,287,accent);box(c,895,396,190,18,fg)
    elif ki==1:
        box(c,920,200,180,76,accent);box(c,970,296,130,108,accent)
    else:
        for x,y,w,h in [(900,297,40,100),(963,223,42,174),(1028,263,50,134)]:box(c,x,y,w,h,accent)
    text(c,k,48,463,'EDITABLE 1600 x 416 CAMPAIGN BANNER INCLUDED',11,700)
    text(c,k,48,508,'Graphic language',19,700);paragraph(c,k,48,543,k['graphic'],510,16)
    text(c,k,650,508,'Voice and product language',19,700)
    paragraph(c,k,650,543,'Before impact. is the leading line. Use calm observations and clear actions: Human review required; Review event; Acknowledge; On scene; Situation clear. Do not promise guaranteed prevention or automatic policing.',500,16)
    paragraph(c,k,48,678,'Image direction: real places, useful lines of sight, people kept anonymous. Board scenes are illustrative, not deployments. Brand colour does not encode urgency on its own. The PDF and tokens set copy/type/colour rules; final symbol files follow selection.',1100,13)
    c.showPage()
    # Self-contained SVG editable layout, exact same composition as PDF panel.
    style=''
    for weight in [400,600,700]:
        b=base64.b64encode((d/'fonts'/f"{k['fd']}-{weight}.ttf").read_bytes()).decode()
        style+=f"@font-face{{font-family:Kit;src:url(data:font/ttf;base64,{b}) format('truetype');font-weight:{weight};}}"
    def st(x,y,s,size,col,wt=400):return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{wt}" fill="{col}">{html.escape(s)}</text>'
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="416" viewBox="0 0 1104 287"><title>NIVRA {k["name"]} editable campaign</title><style>{style}text{{font-family:Kit,sans-serif}}</style><rect width="1104" height="287" fill="{bg}"/>'
    svg+=st(30,52,'NIVRA',26,fg,700)+st(30,147,'Before impact.',60,fg,700)+st(32,200,'Human review. Coordinated response.',22,fg)
    if ki==0:svg+=f'<rect x="802" width="22" height="287" fill="{accent}"/><rect x="847" y="234" width="190" height="18" fill="{fg}"/>'
    elif ki==1:svg+=f'<rect x="872" y="38" width="180" height="76" fill="{accent}"/><rect x="922" y="134" width="130" height="108" fill="{accent}"/>'
    else:
        for x,y,w,h in [(852,135,40,100),(915,61,42,174),(980,101,50,134)]:svg+=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{accent}"/>'
    svg+='</svg>';(d/'campaign-banner.svg').write_text(svg,encoding='utf-8');ET.fromstring(svg)
    (d/'README.md').write_text(f'# NIVRA / {k["name"]}\n\nProposal, not selected. See the comparison PDF for the full four-page guide. Board is generated raster concept artwork. campaign-banner.svg is an editable text-and-colour layout with embedded fonts; it deliberately uses the plain NIVRA name, not an approximate vector of the symbol. Install bundled fonts if your editor does not support embedded SVG fonts. External editor import and print proofs are untested. Final symbol masters require direction selection.\n',encoding='utf-8')
c.save()
assert len(PdfReader(str(output)).pages)==12
doc=pdfium.PdfDocument(str(output))
for n in range(12):doc[n].render(scale=.8).to_pil().save(R/'qa'/f'{n+1:02d}.png')
(R/'manifest.json').write_text(json.dumps(K,indent=2),encoding='utf-8')
shutil.copy2(R.parent/'round-03/sources/font-sources.json',R/'font-sources.json')
print('Created 12-page guide; three boards, three editable banners, fonts and tokens. PDF page count, nine contrast pairs, OFL text and SVG XML passed. Rendered 12 pages for visual inspection.')

