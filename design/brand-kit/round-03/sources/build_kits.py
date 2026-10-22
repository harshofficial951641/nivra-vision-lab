from pathlib import Path
import sys, json, urllib.request, hashlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources' / 'python-deps'))
from fontTools.ttLib import TTFont as FTFont
from fontTools.varLib.instancer import instantiateVariableFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from PIL import Image
from pypdf import PdfReader
import pypdfium2 as pdfium

KITS = [
 dict(id='01',slug='open-moment',name='Open Moment',family='Manrope',fontdir='manrope',
      palette=[('Deep petrol','#113D42'),('Sea glass','#59D8C3'),('Porcelain','#F4F7F4'),('Graphite','#172329')],
      headline='A moment to act.',
      idea='Two approaching paths bend past each other, leaving room for a different outcome.',
      rationale='The open interval is the identity: NIVRA brings attention to the moment when a person can still decide what happens next. The separate curves extend into a restrained graphic system for architecture, signage and event material.',
      character='Composed / alert / fluid',
      tradeoff='The open silhouette is expressive, but its thin middle transition needs optical testing before a final small-size master is drawn.',
      pattern='Use one enlarged trajectory crop at a time. Leave the opposing curve or its negative space visible. Keep pattern away from body copy and operational controls.',
      composition='Anchor with a calm petrol field. Use porcelain for information and turquoise for a deliberate point of attention. Photography should remain naturally lit and recognisably public.',
      app='Petrol app tile; porcelain symbol with a sea-glass terminal. Solid one-color version for small icons.',
      photography='Open campus paths and public architecture in daylight. Ordinary activity; no reenacted threat or tracking boxes.',
      ratio='Petrol 45% / Porcelain 35% / Sea glass 15% / Graphite 5%'),
 dict(id='02',slug='quiet-pivot',name='Quiet Pivot',family='Plus Jakarta Sans',fontdir='plusjakartasans',
      palette=[('Aubergine','#32233F'),('Clear lilac','#B9A0EE'),('Cool cloud','#F4F1F7'),('Softened ink','#201B25')],
      headline='People decide.',
      idea='One turning form expresses a developing situation changing course through a human decision.',
      rationale='A compact turning silhouette gives the brand a recognisable mark without relying on a camera, shield or initial. Its open notch becomes a repeatable graphic detail across a staff pass, app icon and public-space application.',
      character='Considered / contemporary / assured',
      tradeoff='The abstract hook has the strongest compact silhouette; its notch needs refinement so the form does not read as a generic link or question mark.',
      pattern='Use the single turn as a large edge crop or directional divider. Avoid repeated loops, glow effects and purple-blue gradients.',
      composition='Let cloud-white carry the name and most information. Use aubergine for anchoring panels and lilac for selected surfaces or the app tile.',
      app='Lilac app tile with an aubergine symbol. Keep state badges separate from the brand mark.',
      photography='Calm atriums and venues with people moving naturally. Soft daylight, real materials and a clear sense of shared space.',
      ratio='Cool cloud 50% / Aubergine 30% / Lilac 15% / Softened ink 5%'),
 dict(id='03',slug='common-ground',name='Common Ground',family='DM Sans',fontdir='dmsans',
      palette=[('Graphite brown','#292327'),('Apricot','#F4AA76'),('Alabaster','#F8F5F0'),('Muted clay','#BA765C')],
      headline='Shared spaces. Human decisions.',
      idea='Three complementary parts make one shared opening: observations, human judgement and response.',
      rationale='The mark derives its character from the space between its parts. Rounded geometry and a lowercase wordmark make the system approachable while the dark neutral keeps it grounded. The parts also create a useful pattern for covers and event material.',
      character='Human / grounded / clear',
      tradeoff='The three-part symbol offers the richest pattern language. Its silhouette needs distinctiveness screening because clustered marks can suggest recycling or unrelated community brands.',
      pattern='Repeat the three-part module in controlled crops. Keep the original spacing within each complete mark. Use a single crop on covers; dense patterns belong on secondary surfaces.',
      composition='Pair fresh apricot with graphite-brown, balanced by alabaster. Keep layouts contemporary with open sans typography; avoid sepia filters and heritage styling.',
      app='Graphite-brown tile with an apricot symbol. Use one-color mark for small, low-detail contexts.',
      photography='Shared campus and venue settings, approachable distance and ordinary people. Fresh daylight; warm materials without a nostalgic filter.',
      ratio='Alabaster 45% / Graphite brown 30% / Apricot 20% / Muted clay 5%'),
]

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'NIVRA-brand-kit-research'})
    with urllib.request.urlopen(req,timeout=45) as f: return f.read()

FONTROOT=ROOT/'sources'/'fonts'
FONTROOT.mkdir(parents=True,exist_ok=True)
font_sources=[]
for k in KITS:
    folder=FONTROOT/k['fontdir']; folder.mkdir(exist_ok=True)
    listing=json.loads(fetch('https://api.github.com/repos/google/fonts/contents/ofl/'+k['fontdir']))
    for name in ['OFL.txt','METADATA.pb']:
        item=next(x for x in listing if x['name']==name)
        (folder/name).write_bytes(fetch(item['download_url']))
    item=next(x for x in listing if x['name'].endswith('.ttf') and 'Italic' not in x['name'])
    variable=folder/item['name']
    if not variable.exists(): variable.write_bytes(fetch(item['download_url']))
    assert 'SIL OPEN FONT LICENSE' in (folder/'OFL.txt').read_text(encoding='utf-8')
    for w in [400,600,700]:
        target=folder/f'{k["fontdir"]}-{w}.ttf'
        f=FTFont(variable)
        axes={a.axisTag:(w if a.axisTag=='wght' else a.defaultValue) for a in f['fvar'].axes}
        instantiateVariableFont(f,axes,inplace=True)
        # Distinct PDF font identities prevent different weights being deduplicated.
        psname='NivraGuide-'+k['fontdir']+'-'+str(w)
        for rec in f['name'].names:
            if rec.nameID==6: rec.string=psname.encode(rec.getEncoding())
        f.save(target)
        pdfmetrics.registerFont(TTFont(f'{k["id"]}-{w}',str(target)))
    font_sources.append({'family':k['family'],'source':item['download_url'],'sha256':hashlib.sha256(variable.read_bytes()).hexdigest(),'license':'SIL Open Font License 1.1','google_fonts':'https://fonts.google.com/specimen/'+k['family'].replace(' ','+')})

def rgb(h): return tuple(int(h[i:i+2],16)/255 for i in (1,3,5))
def lum(h):
    v=[n/12.92 if n<=.04045 else ((n+.055)/1.055)**2.4 for n in rgb(h)]
    return .2126*v[0]+.7152*v[1]+.0722*v[2]
def contrast(a,b):
    x,y=sorted([lum(a),lum(b)])
    return (y+.05)/(x+.05)

W,H=1200,800
def rect(c,x,y,w,h,col):
    c.setFillColor(HexColor(col));c.rect(x,H-y-h,w,h,stroke=0,fill=1)
def text(c,k,x,y,s,size=16,weight=400,col=None):
    c.setFillColor(HexColor(col or k['ink']));c.setFont(k['id']+'-'+str(weight),size);c.drawString(x,H-y-size,s)
def wrap(s,font,size,width):
    words=s.split();lines=[];line=''
    for word in words:
        candidate=(line+' '+word).strip()
        if pdfmetrics.stringWidth(candidate,font,size)>width and line:
            lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    return lines
def para(c,k,x,y,s,width=500,size=17,weight=400,col=None,leading=None):
    lead=leading or size*1.45
    lines=wrap(s,k['id']+'-'+str(weight),size,width)
    for line in lines:
        text(c,k,x,y,line,size,weight,col);y+=lead
    return y
def section(c,k,x,y,title,body,width=500):
    text(c,k,x,y,title,19,700,k['palette'][0][1]);return para(c,k,x,y+32,body,width,16)+25
def page(c,k,title,num):
    c.setPageSize((W,H));rect(c,0,0,W,H,k['palette'][2][1]);rect(c,0,0,12,H,k['palette'][1][1])
    text(c,k,48,32,'NIVRA  /  '+k['name'].upper(),13,700)
    text(c,k,48,72,title,38,600)
    c.setStrokeColor(HexColor(k['palette'][0][1]));c.setLineWidth(.5);c.line(48,62,W-48,62)
    text(c,k,48,752,'IDENTITY CONCEPT 03  /  17 SEPTEMBER 2026  /  SELECTION PENDING',10,400)
    text(c,k,W-90,752,f'{num:02d} / 04',10,600)

allchecks=[]
for k in KITS:
    folder=ROOT/(k['id']+'-'+k['slug']);board=folder/'brand-board.png'
    primary,accent,bg,ink=[x[1] for x in k['palette']]
    if contrast(ink,bg)<4.5: ink=primary
    k['ink']=ink
    assert all(contrast(a,b)>=4.5 for a,b in [(ink,bg),(bg,primary),(primary,accent)])
    checks=[{'foreground':a,'background':b,'ratio':round(contrast(a,b),2),'normal_text_AA':contrast(a,b)>=4.5} for a,b in [(ink,bg),(bg,primary),(primary,accent),(bg,accent),(accent,primary)]]
    allchecks.append({'direction':k['name'],'pairs':checks})
    tokens={'status':'concept-awaiting-selection','brand':'NIVRA','direction':k['name'],'colors':{'primary':primary,'accent':accent,'surface':bg,'text':ink},'palette':dict(k['palette']),'typography':{'family':k['family'],'weights':[400,600,700],'fallback':'Arial, sans-serif','body_px':16,'body_line_height':1.5,'caption_px':12,'heading_px':[24,36,48]},'layout':{'spacing_px':[4,8,12,16,24,32,48,64],'logo_clear_space':'provisional: 0.25 x symbol width','minimum_size':'not yet validated; determine from final vector proofs'},'color_pairs':checks,'operational_semantics':{'rule':'Brand accent is not an urgency level. Pair state color with text and an icon.','review_label':'Human review required','dispatch_label':'Response requested','resolution_label':'Situation clear'}}
    (folder/'tokens.json').write_text(json.dumps(tokens,indent=2),encoding='utf-8')
    css='/* NIVRA concept tokens; selection pending. */\n:root {\n'+''.join(f'  --nivra-{name}: {value};\n' for name,value in tokens['colors'].items())+f'  --nivra-font: "{k["family"]}", Arial, sans-serif;\n'+'}\n'
    (folder/'tokens.css').write_text(css,encoding='utf-8')
    guide=f'''# NIVRA / {k['name']}

Status: full visual identity concept, not approved production artwork.

## Strategic idea
{k['idea']}

{k['rationale']}

Character: {k['character']}.

## Color
'''+ '\n'.join(f'- {name}: {value}' for name,value in k['palette'])+f'''

Suggested composition balance: {k['ratio']}. This is a layout starting point, not a mandatory quota.

Use {ink} for body text on {bg}; {bg} on {primary}; and {primary} on {accent}. Do not use light text on the accent for small copy. Tokens are authoritative; generated pixels are illustrative. These are sRGB values; CMYK and physical print proofing remain pending.

## Typography
{k['family']}: 600 for headings, 400 for body, 700 sparingly for labels. Body 16 px/1.5, captions at least 12 px, headline scale 24/36/48 px. Use sentence case for instructions. The wordmark is custom artwork, not a font substitution. Google Fonts source and OFL licence are recorded in ../sources/font-sources.json and ../sources/fonts/.

## Logo system
Primary lockup, standalone symbol, reversed and single-color treatments are shown on the board. Clear-space starting rule: 0.25 times the symbol width on each side. Final SVG masters and measured minimum sizes follow selection. Do not stretch, mirror, rotate, recolor individual parts arbitrarily, add shadows or reconstruct the wordmark in a nearby font.

{k['tradeoff']}

## Graphic and image system
{k['pattern']}

{k['composition']}

Photography: {k['photography']}

App icon: {k['app']}

## Product family and language
Use NIVRA Command, NIVRA Camera, NIVRA Respond, NIVRA Admin and NIVRA Trust in prose. Keep one shared symbol; do not create five unrelated sub-brands.

Product line: Before impact.
Campaign specimen: {k['headline']}
Descriptor: Human-reviewed observations. Coordinated response.

Operator candidate: Human review required.
Responder assignment: Response requested.
Responder action: Acknowledge.
Field state: On scene.
Resolution: Situation clear.
Quality limitation: Analysis limited by poor visibility.

Never claim crime prediction, intent detection, guaranteed prevention or automatic policing. No impact recorded is a recorded workflow outcome, not proof of causation.

## Applications and production boundary
The board shows concept applications of the identity on phones, public-space notices and staff materials. They are generated scenes, not existing deployments or functional product screens. Public notices are visual mockups, not complete operational/privacy signage: the real operator, site policy, retention details and contact route must be supplied for an actual site. No legal-compliance claim is made.

Delivered now: board PNG, four-page PDF guide, color/type/usage specification, CSS and JSON tokens. Pending selection: refined vector geometry, outlined logo masters, transparent logo/icon export pack, exact small-size tests and print proofs. Generated letterforms may differ from the real licensed font used in the PDF guide.
'''
    (folder/'GUIDELINES.md').write_text(guide,encoding='utf-8')

    output=folder/f'NIVRA-{k["slug"]}-brand-kit.pdf'
    c=canvas.Canvas(str(output),pagesize=(W,H));c.setTitle('NIVRA / '+k['name']+' / Brand kit concept');c.setAuthor('NIVRA identity exploration for Harsh Jain')
    rect(c,0,0,W,H,bg);c.drawImage(ImageReader(str(board)),0,0,width=W,height=H,mask='auto');c.showPage()
    page(c,k,'Color and type',2)
    for i,(name,hexcode) in enumerate(k['palette']):
        x=48+i*282;rect(c,x,146,258,122,hexcode);text(c,k,x,282,name,16,600);text(c,k,x,310,hexcode,15)
    text(c,k,48,368,k['family'],44,600)
    para(c,k,48,432,k['headline'],535,31,600,primary,38)
    text(c,k,48,539,'Aa  Bb  Cc  0123456789',27,400)
    text(c,k,48,585,'HEADINGS 600  /  BODY 400  /  LABELS 700',12,600)
    para(c,k,48,618,'Body: 16 px / 1.5. Captions: 12 px minimum. Headings: 24, 36 and 48 px. Sentence case for instructions.',520,16)
    text(c,k,666,372,'TEXT PAIRINGS',14,700)
    for j,(a,b) in enumerate([(ink,bg),(bg,primary),(primary,accent)]):
        yy=410+j*77;rect(c,666,yy,482,57,b);text(c,k,684,yy+16,f'Readable text   {contrast(a,b):.2f}:1',17,600,a)
    para(c,k,666,658,'Ratios use the exact sRGB tokens. Light text on the accent is excluded for small copy.',480,13)
    c.showPage()
    page(c,k,'Meaning and visual system',3)
    para(c,k,48,146,k['idea'],1088,28,600,primary,38)
    y=256
    y=section(c,k,48,y,'The brand idea',k['rationale'],510)
    y=section(c,k,48,y,'Composition',k['composition'],510)
    section(c,k,48,y,'Photography',k['photography'],510)
    y=256
    y=section(c,k,638,y,'Graphic language',k['pattern'],510)
    y=section(c,k,638,y,'App icon',k['app'],510)
    section(c,k,638,y,'Refinement before production',k['tradeoff'],510)
    c.showPage()
    page(c,k,'Use the identity responsibly',4)
    y=148
    y=section(c,k,48,y,'One name, five surfaces','NIVRA Command / Camera / Respond / Admin / Trust. Keep one shared symbol; use product names as readable descriptors.',516)
    y=section(c,k,48,y,'Logo rules','Allow 0.25 x symbol width as provisional clear space. Use supplied proportions, single-color and reverse treatments. No stretching, rotation, added shadows or casual redrawing. Exact minimum sizes follow vector tests.',516)
    y=section(c,k,48,y,'Operational wording','Operator: Human review required. Responder: Response requested. Action: Acknowledge. Field state: On scene. Resolution: Situation clear.',516)
    section(c,k,48,y,'Tone','Plain, specific and calm. Describe observations and human decisions. Avoid crime prediction, inferred intent and guaranteed prevention claims.',516)
    y=148
    y=section(c,k,638,y,'What is delivered','Full-color board, this guide, editable written specification, CSS and JSON color/type tokens. The guide uses the actual licensed typeface; generated board lettering is illustrative.',510)
    y=section(c,k,638,y,'What follows selection','Refined master vectors, outlined logo typography, transparent PNG and icon export pack, small-size proofs and print validation. These are not included as finished assets yet.',510)
    y=section(c,k,638,y,'Application boundary','Phones, notices and staff materials are generated concept applications. They are not live screens, deployed signage or compliance evidence. An actual site notice needs operator and policy details.',510)
    section(c,k,638,y,'Evidence','Competitor review: Oddity, BriefCam / Milestone, Isarsoft and Omnilert, inspected 17 September 2026. See COMPETITOR-RESEARCH.md. Font source: Google Fonts, SIL Open Font License 1.1.',510)
    c.save()
    reader=PdfReader(str(output));assert len(reader.pages)==4
    assert 'Color and type' in reader.pages[1].extract_text()
    assert 'Use the identity responsibly' in reader.pages[3].extract_text()
    doc=pdfium.PdfDocument(str(output))
    for i in range(4):
        doc[i].render(scale=1).to_pil().save(ROOT/'qa'/f'{k["id"]}-page-{i+1}.png')
    print(output.name, '4 pages; rendered and text-checked', flush=True)

(ROOT/'sources'/'font-sources.json').write_text(json.dumps(font_sources,indent=2),encoding='utf-8')
(ROOT/'qa'/'contrast.json').write_text(json.dumps(allchecks,indent=2),encoding='utf-8')
(ROOT/'README.md').write_text('''# NIVRA: three full-color brand-kit concepts

Status: awaiting selection. Previous rounds are rejected. These concepts have been researched, visually inspected and packaged; they are not approved production identities.

- 01-open-moment: petrol / sea glass, paired diverted trajectories, Manrope.
- 02-quiet-pivot: aubergine / lilac, single turning form, Plus Jakarta Sans.
- 03-common-ground: graphite / apricot, shared-space geometry, DM Sans.

Each folder includes a board PNG, four-page PDF guide, GUIDELINES.md, tokens.json and tokens.css. Exact color/type specifications are in the tokens and guidelines. The generated board is visual exploration, not a vector master or exact font reference. Each PDF uses licensed font outlines from Google Fonts.

Competitor sources and implications: COMPETITOR-RESEARCH.md. Font source URLs, hashes and OFL licences: sources/. Palette checks: qa/contrast.json. Generation prompts: PROMPTS.md.

Final SVG logos, separately exported transparent logos/icons, vector small-size validation and production print assets follow selection. Generated application scenes are not operational interfaces or deployment evidence.
''',encoding='utf-8')
