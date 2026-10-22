from pathlib import Path
import json, shutil, base64, html, hashlib, zipfile
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader
import pypdfium2 as pdfium

ROOT=Path(__file__).resolve().parent
GEN=Path('C:/Users/harsh.DESKTOP-VE90R6D/.codex/generated_images/01a0abda-4268-7ac3-8edf-4df75e704bd5')
OLD=ROOT.parent/'round-03'/'sources'
QA=ROOT/'qa'; QA.mkdir(exist_ok=True)
W,H=1200,800
KITS=[
 dict(id='01',slug='insight',name='Insight',font='Manrope',fontdir='manrope',source='exec-af026935-f23a-45e6-8d10-9205cc93e268.png',colors=['#234AE8','#DFF568','#111D32','#F4F7FF'],names=['Electric blue','Lime','Ink','Cool white'],crop=[55,145,835,235],idea='A compact viewing aperture makes observation the identifying feature.',graphic='An enlarged aperture creates a window into a real place. Use one crop per composition, with a broad quiet field around it.',tone='Direct / perceptive / confident',balance='Blue 40% / white 35% / ink 15% / lime 10%',risk='The optical mark needs a final distinctiveness check. Refine the aperture and outer contour before producing master vectors.'),
 dict(id='02',slug='assurance',name='Assurance',font='Plus Jakarta Sans',fontdir='plusjakartasans',source='exec-159e193c-30ed-4123-88d2-1a639d192587.png',colors=['#5425B9','#FFB071','#211331','#FAF7FF'],names=['Violet','Apricot','Aubergine','Paper'],crop=[70,108,425,262],idea='A broad protective upper form holds a clear line of sight above a compact base.',graphic='Use a broad upper curve and an open interval. Carry that geometry into crops and separators without repeating rows of little symbols.',tone='Protective / composed / attentive',balance='Paper 40% / violet 30% / aubergine 20% / apricot 10%',risk='The protected-view symbol can suggest an eye or canopy. Keep the two parts consistent and verify recognition at small sizes.'),
 dict(id='03',slug='vigil',name='Vigil',font='DM Sans',fontdir='dmsans',source='exec-9919fd4a-bdfa-4801-b9b9-c5450b2484b7.png',colors=['#006A50','#F4F36D','#102B23','#F5FAF6'],names=['Emerald','Lemon','Deep green','Porcelain'],crop=[48,72,510,432],idea='An upright opening and observed point create a firm, watchful presence.',graphic='Use an offset plane and a generous opening. Keep the composition anchored to a steady vertical edge; one lemon detail draws attention.',tone='Watchful / capable / grounded',balance='Emerald 35% / porcelain 30% / deep green 25% / lemon 10%',risk='The upright mark may evoke camera hardware. It is a surveillance concept, not a claim that NIVRA manufactures a camera.'),
]

def lum(v):
    xs=[int(v[i:i+2],16)/255 for i in (1,3,5)]
    xs=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in xs]
    return sum(x*y for x,y in zip(xs,[.2126,.7152,.0722]))
def ratio(a,b):
    lo,hi=sorted((lum(a),lum(b)));return (hi+.05)/(lo+.05)
def rect(c,x,y,w,h,col):
    c.setFillColor(HexColor(col));c.rect(x,H-y-h,w,h,fill=1,stroke=0)
def line(c,x1,y1,x2,y2,col,width=.6):
    c.setStrokeColor(HexColor(col));c.setLineWidth(width);c.line(x1,H-y1,x2,H-y2)
def txt(c,k,x,y,s,size=16,weight=400,col=None):
    c.setFont(k['id']+'-'+str(weight),size);c.setFillColor(HexColor(col or k['colors'][2]));c.drawString(x,H-y-size,s)
def para(c,k,x,y,s,width,size=17,weight=400,col=None,leading=None):
    lead=leading or size*1.42;words=s.split();out=[];cur=''
    for word in words:
        nxt=(cur+' '+word).strip()
        if pdfmetrics.stringWidth(nxt,k['id']+'-'+str(weight),size)>width and cur: out.append(cur);cur=word
        else:cur=nxt
    if cur:out.append(cur)
    for row in out:txt(c,k,x,y,row,size,weight,col);y+=lead
    return y
def section(c,k,x,y,title,body,width=500):
    txt(c,k,x,y,title,18,700);return para(c,k,x,y+31,body,width,16)+24
def page(c,k,title,n):
    p,a,i,s=k['colors'];rect(c,0,0,W,H,s)
    txt(c,k,48,29,'NIVRA / '+k['name'].upper(),12,700)
    txt(c,k,950,29,'BRAND KIT PROPOSAL',11,600)
    line(c,48,61,1152,61,p)
    txt(c,k,48,84,title,40,600)
    txt(c,k,48,758,'PROPOSAL '+k['id']+'  /  DIRECTION NOT YET SELECTED',10)
    txt(c,k,1095,758,f'{n:02d} / 06',10,600)
def board_crop(c,board,crop,x,y,w,h):
    cx,cy,cw,ch=crop;scale=min(w/cw,h/ch);dw,dh=cw*scale,ch*scale
    dx=x+(w-dw)/2;dy=y+(h-dh)/2
    c.saveState();p=c.beginPath();p.rect(dx,H-dy-dh,dw,dh);c.clipPath(p,stroke=0,fill=0)
    c.drawImage(ImageReader(str(board)),dx-cx*scale,H-(dy-cy*scale)-1024*scale,width=1536*scale,height=1024*scale)
    c.restoreState()
def motif(c,k,x,y,w,h,bg,fg):
    c.saveState();path=c.beginPath();path.rect(x,H-y-h,w,h);c.clipPath(path,stroke=0,fill=0)
    c.setFillColor(HexColor(fg))
    if k['id']=='01':
        c.ellipse(x+w*.1,H-y-h*.98,x+w*1.3,H-y+h*.4,fill=1,stroke=0)
        c.setFillColor(HexColor(bg));c.ellipse(x+w*.53,H-y-h*.55,x+w*1.09,H-y+h*.13,fill=1,stroke=0)
    elif k['id']=='02':
        path=c.beginPath();path.moveTo(x-w*.1,H-y-h*.85);path.curveTo(x+w*.4,H-y+h*.4,x+w*.62,H-y+h*.2,x+w*1.15,H-y-h*.6);path.curveTo(x+w*.7,H-y-h*.15,x+w*.25,H-y-h*.18,x-w*.1,H-y-h*.85);c.drawPath(path,fill=1,stroke=0)
    else:
        path=c.beginPath();path.moveTo(x+w*.18,H-y-h);path.lineTo(x+w*.18,H-y-h*.1);path.lineTo(x+w*.83,H-y+h*.18);path.lineTo(x+w*.83,H-y-h*.72);path.close();c.drawPath(path,fill=1,stroke=0)
        c.setFillColor(HexColor(bg));c.circle(x+w*.53,H-y-h*.44,w*.2,fill=1,stroke=0)
    c.restoreState()

def write_templates(k,d):
    p,a,ink,s=k['colors'];font=k['font'];styles=''
    for weight in [400,600,700]:
        raw=(d/'fonts'/f"{k['fontdir']}-{weight}.ttf").read_bytes()
        styles+=f"@font-face{{font-family:'NivraKit';font-weight:{weight};src:url(data:font/ttf;base64,{base64.b64encode(raw).decode()}) format('truetype');}}"
    def start(w,h,bg):return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><title>NIVRA {k["name"]} editable proposal template</title><style>{styles}text{{font-family:NivraKit,sans-serif;}}</style><rect width="{w}" height="{h}" fill="{bg}"/>'
    def t(x,y,content,size,col,weight=400):return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{col}">{html.escape(content)}</text>'
    (d/'templates').mkdir(exist_ok=True)
    # Plain NIVRA name deliberately uses normal font letters. No letter-derived logo.
    poster=start(1080,1350,p)+t(80,130,'NIVRA',50,s,700)+t(80,470,'Before',148,s,700)+t(80,635,'impact.',148,s,700)+f'<rect x="80" y="735" width="140" height="15" fill="{a}"/>'+t(80,1010,'Human-reviewed observations.',35,s)+t(80,1070,'Coordinated response.',35,s)+t(80,1230,'SURVEILLANCE & RESPONSE',23,s,600)+'</svg>'
    (d/'templates'/'campaign-poster.svg').write_text(poster,encoding='utf-8')
    cover=start(1600,900,ink)+f'<path d="M1110 0H1600V900H1380Q1100 440 1110 0Z" fill="{p}"/>'+t(92,126,'NIVRA',49,s,700)+t(90,440,'Before impact.',110,s,700)+t(94,544,'Human review. Coordinated response.',37,s)+t(94,790,'CAPABILITIES OVERVIEW',24,a,600)+'</svg>'
    (d/'templates'/'presentation-cover.svg').write_text(cover,encoding='utf-8')
    card=start(900,570,s)+f'<rect x="0" y="0" width="900" height="16" fill="{p}"/>'+t(48,90,'NIVRA Command',33,ink,700)+t(48,228,'Human review required',44,ink,600)+t(48,292,'Review the sequence before deciding.',27,ink)+f'<rect x="48" y="385" width="804" height="105" rx="16" fill="{p}"/>'+t(84,452,'Review event',32,s,600)+'</svg>'
    (d/'templates'/'review-card.svg').write_text(card,encoding='utf-8')

checks=[]
for k in KITS:
    d=ROOT/(k['id']+'-'+k['slug']);d.mkdir(exist_ok=True)
    shutil.copy2(GEN/k['source'],d/'brand-board.png');board=d/'brand-board.png'
    with Image.open(board) as im:
        assert im.size==(1536,1024)
        assert 'A' not in im.getbands() or im.getchannel('A').getextrema()==(255,255)
    (d/'fonts').mkdir(exist_ok=True)
    for weight in [400,600,700]:
        f=OLD/'fonts'/k['fontdir']/f"{k['fontdir']}-{weight}.ttf"
        shutil.copy2(f,d/'fonts'/f.name);pdfmetrics.registerFont(TTFont(k['id']+'-'+str(weight),str(f)))
    licence=OLD/'fonts'/k['fontdir']/'OFL.txt';assert 'SIL OPEN FONT LICENSE' in licence.read_text(encoding='utf-8');shutil.copy2(licence,d/'fonts'/'OFL.txt')
    p,a,ink,s=k['colors'];pairs=[(ink,s),(s,p),(ink,a)]
    actual=[dict(foreground=x,background=y,ratio=round(ratio(x,y),2)) for x,y in pairs];assert all(r['ratio']>=4.5 for r in actual)
    checks.append(dict(direction=k['name'],text_pairs=actual))
    data=dict(brand='NIVRA',status='complete-identity-proposal-awaiting-selection',direction=k['name'],colors=dict(primary=p,accent=a,ink=ink,surface=s),typography=dict(family=k['font'],weights=[400,600,700],body_px=16,line_height=1.5,caption_px=12,heading_px=[24,36,48,64]),text_pairs=actual,spacing_px=[4,8,16,24,32,48,64],logo=dict(clear_space='Provisional: at least 0.25 times symbol height',minimum_size='Not yet validated; requires selected master geometry'),operational_state_rule='Colour never replaces a text label. Brand accent does not mean urgency.')
    (d/'tokens.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    (d/'tokens.css').write_text(':root {\n'+''.join(f'  --nivra-{key}: {v};\n' for key,v in data['colors'].items())+f'  --nivra-font: "{k["font"]}", Arial, sans-serif;\n'+'}\n',encoding='utf-8')
    write_templates(k,d)
    c=canvas.Canvas(str(d/f'NIVRA-{k["slug"]}-brand-kit.pdf'),pagesize=(W,H));c.setTitle('NIVRA / '+k['name']+' / Brand kit proposal');c.setAuthor('NIVRA brand development for Harsh Jain')
    # 1: complete visual identity overview.
    c.drawImage(ImageReader(str(board)),0,0,width=W,height=H);c.showPage()
    # 2: the identity, with a focused close-up rather than another moodboard.
    page(c,k,'Identity and logo',2)
    rect(c,48,168,578,336,p if k['id']=='01' else s if k['id']=='02' else ink)
    board_crop(c,board,k['crop'],65,190,544,290)
    txt(c,k,672,166,k['tone'],16,700,p)
    y=para(c,k,672,210,k['idea'],475,27,600,ink,37)
    para(c,k,672,y+25,'NIVRA supports people who review developing camera events and coordinate a response. The identity should feel protective, watchful and effective.',475,17)
    section(c,k,48,544,'One symbol, one plain name','Use the standalone mark with NIVRA in straightforward lettering. No hidden initials, altered letters or separate product logos.',510)
    section(c,k,648,544,'Space and reproduction','Start with clear space of one-quarter of the symbol height. Use a single-colour or reversed version on busy surfaces. Do not stretch, rotate, shadow or redraw.',504)
    para(c,k,48,686,k['risk']+' Exact minimum sizes follow selection.',1090,13)
    c.showPage()
    # 3: exact palette and licensed typography.
    page(c,k,'Colour and typography',3)
    for j,(name,v) in enumerate(zip(k['names'],k['colors'])):
        xx=48+j*282;rect(c,xx,166,258,105,v)
        if j==3:
            c.setStrokeColor(HexColor(ink));c.setLineWidth(.5);c.rect(xx,H-271,258,105,fill=0,stroke=1)
        txt(c,k,xx,283,name,17,600);txt(c,k,xx,312,v,15)
    txt(c,k,48,381,k['font'],38,600)
    txt(c,k,48,443,'Notice. Review.',35,600)
    txt(c,k,48,491,'Respond.',35,600)
    txt(c,k,48,554,'Aa Bb Cc 0123456789',26)
    para(c,k,48,607,'Headings 600 / body 400 / labels 700. Body 16 px with 1.5 line height; captions 12 px minimum. Sentence case for instructions. Use normal font letters for the NIVRA name.',525,15)
    txt(c,k,654,381,'CHECKED TEXT PAIRS',13,700)
    for j,(x,y) in enumerate(pairs):
        yy=418+j*74;rect(c,654,yy,498,56,y);txt(c,k,671,yy+15,f'Clear text / {ratio(x,y):.2f}:1',18,600,x)
    para(c,k,654,654,'Exact sRGB values govern the kit. Generated pixels are illustrative. Licensed font files and OFL terms are included.',480,13)
    c.showPage()
    # 4: graphic system and scalable native application compositions.
    page(c,k,'Graphics and applications',4)
    rect(c,48,164,397,474,p);txt(c,k,73,192,'NIVRA',23,700,s)
    txt(c,k,73,274,'Before',65,700,s);txt(c,k,73,349,'impact.',65,700,s)
    motif(c,k,48,444,397,194,p,a)
    txt(c,k,48,656,'COMPOSITION STUDIES / SVG TEMPLATES INCLUDED',10,700)
    rect(c,482,164,670,237,ink);txt(c,k,507,186,'NIVRA',20,700,s);txt(c,k,507,247,'Before impact.',44,600,s);txt(c,k,507,330,'Human review. Coordinated response.',18,400,s)
    rect(c,482,428,670,210,'#FFFFFF');txt(c,k,506,447,'NIVRA Command',20,700);txt(c,k,506,491,'Human review required',26,600)
    rect(c,506,550,622,60,p);txt(c,k,526,566,'Review event',19,600,s)
    para(c,k,48,697,k['graphic'],1090,14)
    c.showPage()
    # 5: real product language and behavior.
    page(c,k,'Voice and product language',5)
    txt(c,k,48,165,'Watchful technology.',39,600);txt(c,k,48,217,'Human decisions.',39,600,p)
    para(c,k,48,286,'Use plain, calm language. State what was observed, what needs review and who acts next. Be specific about uncertainty.',1040,21)
    y=390
    y=section(c,k,48,y,'Core line','Before impact. Keep this as the leading brand line. Supporting description: Human-reviewed observations. Coordinated response.',520)
    section(c,k,48,y,'Product family','NIVRA Command / Camera / Respond / Admin / Trust. One shared identity, with the product name as a readable descriptor.',520)
    y=390
    y=section(c,k,654,y,'Operational copy','Human review required. Response requested. Acknowledge. On scene. Situation clear. Analysis limited by poor visibility.',498)
    section(c,k,654,y,'Claims and restraint','Do not infer intent, guilt or identity. Do not promise crime prediction, guaranteed prevention or automatic policing. Brand colour alone must not indicate urgency.',498)
    c.showPage()
    # 6: practical use and file index, with clear production boundaries.
    page(c,k,'Use the kit',6)
    y=164
    y=section(c,k,48,y,'Included files','Six-page guide, visual identity board, CSS/JSON colour and type tokens, licensed supporting fonts, and three editable SVG application templates.',515)
    y=section(c,k,48,y,'Editable applications','campaign-poster.svg / presentation-cover.svg / review-card.svg. Text remains editable and fonts are embedded. Templates use the plain NIVRA name and exact tokens.',515)
    y=section(c,k,48,y,'Composition','Use a clear dominant colour field and one deliberate graphic crop. '+k['balance']+'. Treat these as starting proportions, not fixed quotas.',515)
    section(c,k,48,y,'Image direction','Use real places, natural architectural light and useful lines of sight. Keep people anonymous. Avoid staged threats, weapon imagery and decorative tracking boxes.',515)
    y=164
    y=section(c,k,654,y,'Application status','Board photography, credentials and screens are generated concept applications. Names and event details in them are illustrative. They are not a working app or deployment evidence.',498)
    y=section(c,k,654,y,'Before final production','Select a direction, refine one exact symbol master, verify small-size and one-colour use, then export SVG/PNG logo families and print proofs. No final vector logo is claimed here.',498)
    y=section(c,k,654,y,'Copy and colour authority','Use the wording on page 5 and exact tokens on page 3. Incidental slogans in the generated overview are not approved copy. Print CMYK values require a chosen profile and proof.',498)
    section(c,k,654,y,'Typography provenance',k['font']+' from Google Fonts, licensed under SIL Open Font License 1.1. Font files and licence are included. The PDF uses the actual fonts; board lettering is illustrative.',498)
    c.showPage();c.save()
    pdf=d/f'NIVRA-{k["slug"]}-brand-kit.pdf';reader=PdfReader(str(pdf));assert len(reader.pages)==6
    for n,heading in enumerate(['Identity and logo','Colour and typography','Graphics and applications','Voice and product language','Use the kit'],1):assert heading in reader.pages[n].extract_text()
    doc=pdfium.PdfDocument(str(pdf))
    for n in range(6):doc[n].render(scale=.9).to_pil().save(QA/f'{k["id"]}-{n+1}.png')
    (d/'README.md').write_text(f'''# NIVRA / {k['name']}

Complete brand-kit proposal for review; no direction is selected yet.

Start with NIVRA-{k['slug']}-brand-kit.pdf. The six pages cover the visual identity, logo rules, exact colours and typography, graphics/applications, voice, product language and practical file use.

The three editable SVG templates contain real text and embedded licensed fonts. They intentionally use NIVRA as plain lettering; no monogram or letter trick is introduced. These are reusable draft layouts, not vector logo masters. The logo concept is presented in the raster board and PDF; the final independently reusable symbol family follows selection.

Source image: {k['source']}. Palette/type tokens govern exact values; generated board pixels and incidental slogans are illustrative. No working app, real credential, deployment, trademark clearance or CMYK print proof is claimed.
''',encoding='utf-8')
    print(pdf,flush=True)

shutil.copy2(OLD/'font-sources.json',ROOT/'font-sources.json')
(QA/'contrast.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
(ROOT/'manifest.json').write_text(json.dumps(KITS,indent=2),encoding='utf-8')
print('18 pages rendered; exact intended text pairs passed; local OFL files verified.')
