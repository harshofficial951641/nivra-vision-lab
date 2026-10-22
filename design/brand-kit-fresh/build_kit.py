from pathlib import Path
import json, io, zipfile
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
import pypdfium2 as pdfium
from PIL import Image

ROOT=Path(__file__).parent
OUT=ROOT/'final'; OUT.mkdir(exist_ok=True)
AS=OUT/'logos'; AS.mkdir(exist_ok=True)
QA=ROOT/'qa'; QA.mkdir(exist_ok=True)
NAVY='#172C40'; TEAL='#167D8D'; WHITE='#F5F4EF'; MIST='#DCECEE'
pdfmetrics.registerFont(TTFont('Brand','C:/Windows/Fonts/bahnschrift.ttf'))
pdfmetrics.registerFont(TTFont('Body','C:/Windows/Fonts/segoeui.ttf'))
# Original vector refinement of the Signal concept. Coordinates are top-down.
paths=[
 [('M',0,160),('L',0,94),('C',0,56,21,36,60,36),('C',99,36,120,56,120,94),('L',120,160),('L',88,160),('L',88,94),('C',88,75,79,66,60,66),('C',41,66,32,75,32,94),('L',32,160),('Z',)],
 [('M',148,38),('L',180,38),('L',180,160),('L',148,160),('Z',)],
 [('M',148,0),('L',180,0),('L',180,28),('L',148,28),('Z',)],
 [('M',201,38),('L',236,38),('L',270,123),('L',305,38),('L',340,38),('L',292,151),('C',289,158,284,160,277,160),('L',263,160),('C',256,160,251,158,248,151),('Z',)],
 [('M',359,160),('L',359,88),('C',359,53,378,36,411,36),('L',442,36),('L',442,66),('L',412,66),('C',398,66,391,73,391,88),('L',391,160),('Z',)],
 [('M',463,75),('C',467,48,488,36,525,36),('C',567,36,587,54,587,88),('L',587,160),('L',557,160),('L',557,148),('C',546,159,531,164,512,164),('C',478,164,459,150,459,126),('C',459,101,478,89,511,89),('L',555,89),('L',555,86),('C',555,70,545,63,525,63),('C',508,63,498,67,495,75),('Z',)],
]
# The a counter is cut out explicitly, avoiding SVG winding inconsistencies.
counter=[('M',555,112),('L',515,112),('C',499,112,491,116,491,125),('C',491,134,499,138,514,138),('C',538,138,555,129,555,116),('Z',)]
def svgpath(p): return ' '.join(a[0]+' '+ ' '.join(str(x) for x in a[1:]) for a in p)
def logo_svg(color,bg=None,icon=False):
    ps=paths[:1] if icon else paths
    vb='-28 8 176 176' if icon else '-24 -24 635 212'
    body=''.join(f'<path d="{svgpath(p)}"/>' for p in ps)
    # use a mask for the transparent counter
    mask='' if icon else f'<defs><mask id="cut"><rect x="-30" y="-30" width="660" height="240" fill="white"/><path d="{svgpath(counter)}" fill="black"/></mask></defs>'
    rect=f'<rect x="-30" y="-30" width="660" height="240" fill="{bg}"/>' if bg else ''
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" role="img" aria-label="Nivra">{mask}{rect}<g fill="{color}"'+('' if icon else ' mask="url(#cut)"')+f'>{body}</g></svg>'
def pathdraw(c,p):
    q=c.beginPath()
    for a in p:
        {'M':q.moveTo,'L':q.lineTo,'C':q.curveTo,'Z':q.close}[a[0]](*a[1:])
    c.drawPath(q,fill=1,stroke=0)
def logo(c,x,y,width,color=NAVY,bg=WHITE,icon=False):
    c.saveState(); c.translate(x,y); c.scale(width/(120 if icon else 587),-width/(120 if icon else 587)); c.setFillColor(HexColor(color))
    for p in paths[:1] if icon else paths: pathdraw(c,p)
    if not icon: c.setFillColor(HexColor(bg)); pathdraw(c,counter)
    c.restoreState()
def render(data,scale=2):
    doc=pdfium.PdfDocument(data)
    return [doc[i].render(scale=scale).to_pil().convert('RGB') for i in range(len(doc))]
for name,col,bg in [('navy',NAVY,None),('teal',TEAL,None),('black','#000000',None),('white','#FFFFFF',None)]:
    (AS/f'nivra-{name}.svg').write_text(logo_svg(col),encoding='utf-8')
    # Raster exports rendered at 2400 px wide with transparent ground.
    ground='#000000' if name=='white' else '#FFFFFF'
    b=io.BytesIO(); c=canvas.Canvas(b,pagesize=(635,212)); c.setFillColor(HexColor(ground)); c.rect(0,0,635,212,fill=1,stroke=0); logo(c,24,188,587,col,ground);c.save()
    im=render(b.getvalue(),2400/635)[0].convert('RGBA')
    pix=im.load(); rgb=tuple(int(col[j:j+2],16) for j in (1,3,5))
    for yy in range(im.height):
        for xx in range(im.width):
            v=pix[xx,yy]
            if name=='white': alpha=max(v[:3])
            else: alpha=round(max((255-v[k])/(255-rgb[k]) if rgb[k]<255 else 0 for k in range(3))*255)
            pix[xx,yy]=(*rgb,max(0,min(255,alpha)))
    im.save(AS/f'nivra-{name}.png')
(AS/'nivra-icon.svg').write_text(logo_svg(WHITE,icon=True).replace('<g fill=',f'<rect x="-28" y="8" width="176" height="176" rx="36" fill="{NAVY}"/><g fill='),encoding='utf-8')
b=io.BytesIO();c=canvas.Canvas(b,pagesize=(176,176));c.setFillColor(HexColor(NAVY));c.rect(0,0,176,176,fill=1,stroke=0);logo(c,28,184,120,WHITE,NAVY,True);c.save()
render(b.getvalue(),1024/176)[0].save(AS/'nivra-icon.png')

W,H=1000,700
c=canvas.Canvas(str(OUT/'Nivra-Brand-Kit.pdf'),pagesize=(W,H))
c.setTitle('Nivra | Brand Kit');c.setAuthor('Nivra')
def rect(x,y,w,h,color):c.setFillColor(HexColor(color));c.rect(x,y,w,h,fill=1,stroke=0)
def text(x,y,s,size=14,color=NAVY,font='Body'):
    c.setFillColor(HexColor('#FFFFFF' if color==WHITE else '#126F7D' if color==TEAL else color));c.setFont(font,size);c.drawString(x,y,s)
def lines(x,y,arr,size=15,color=NAVY,leading=24):
    for i,s in enumerate(arr):text(x,y-i*leading,s,size,color)
def page(n,label,dark=False):
    rect(0,0,W,H,NAVY if dark else WHITE)
    text(48,652,'NIVRA  /  IDENTITY SYSTEM',10,WHITE if dark else NAVY,'Brand')
    text(48,30,label,10,WHITE if dark else NAVY)
    text(925,30,f'{n:02d}',10,WHITE if dark else NAVY)
def title(s):text(48,577,s,44,NAVY,'Brand')
page(1,'SIGNAL / BRAND OVERVIEW')
logo(c,48,508,650)
text(52,264,'Quiet attention. Clear action.',30,NAVY,'Brand')
lines(52,226,['Human-supervised safety intelligence for schools.', 'A precise identity, built around the people who decide.'],15)
for x,w,col,name,code in [(48,365,NAVY,'Ink Navy',NAVY),(425,282,TEAL,'Attentive Teal',TEAL),(719,233,MIST,'Warm White',WHITE)]:
    rect(x,85,w,70,WHITE if name=='Warm White' else col)
    if name=='Warm White':rect(x,85,w,2,NAVY)
    text(x+12,126,name,13,NAVY if name=='Warm White' else WHITE,'Brand');text(x+12,102,code,12,NAVY if name=='Warm White' else WHITE)
c.showPage()
page(2,'POSITIONING / VOICE');title('Watch carefully. Act thoughtfully.')
lines(48,505,['Nivra helps school safety teams review visible activity and coordinate', 'a human response. The identity should feel modern, composed and clear.'],20,leading=30)
for x,h,arr in [(48,'PRECISE',['Explain what was observed.', 'Use plain, specific language.', '“Movement near the east gate.”']), (370,'HUMAN',['Keep the operator in control.','Describe choices, not verdicts.', '“Review before dispatch.”']), (690,'CALM',['Normal operation stays quiet.','Make attention purposeful.', '“All cameras connected.”'])]:
    rect(x,359,55,4,TEAL);text(x,316,h,17,NAVY,'Brand');lines(x,276,arr,14)
text(48,143,'Avoid',18,NAVY,'Brand');lines(48,111,['Fear-based slogans, “crime prediction”, facial-identification claims, or guaranteed protection.', '“Quiet attention. Clear action.” is proposed brand copy, not a performance claim.'],13,leading=22)
c.showPage()
page(3,'LOGO / CONSTRUCTION & USE');title('One word. A clear signal.')
logo(c,48,490,470)
rect(625,325,327,170,NAVY);logo(c,650,451,273,WHITE,NAVY)
lines(48,284,['Custom outlined lowercase lettering; no font is required to use the logo.', 'The square i-dot is the signal. Open counters keep the wordmark approachable.', 'The compact n is for app icons and already-labelled product contexts.'],15)
lines(48,174,['Clear space: at least one i-stem width on every side.', 'Minimum wordmark width: 120 px digitally / 30 mm in print.', 'Minimum icon size: 24 px. Below that, use a text label.', 'Never stretch, rotate, outline, add shadows, or recolour individual letters.'],14)
c.showPage()
page(4,'COLOUR / MEANING & ACCESSIBILITY');title('Colour with a job to do.')
sw=[(NAVY,'INK NAVY','Responsibility and composure.'),(TEAL,'ATTENTIVE TEAL','Purposeful focus and action.'),(WHITE,'WARM WHITE','Clarity and breathing room.')]
for i,(col,name,meaning) in enumerate(sw):
    x=48+i*310;rect(x,325,285,185,col if col!=WHITE else MIST)
    if col==WHITE:rect(x+2,327,281,181,WHITE)
    text(x+18,472,name,15,WHITE if i<2 else NAVY,'Brand');text(x+18,443,col,20,WHITE if i<2 else NAVY,'Brand');text(x,289,meaning,14)
lines(48,220,['Use warm white for most surfaces, navy for text and identity, and teal sparingly.', 'Suggested balance: 70% warm white / 25% navy / 5% teal.', 'Use navy or deep teal #126F7D text on warm white; use pure white text on teal.', 'Do not place navy text on teal. Colour must never be the only status cue.'],15)
lines(48,95,['Amber #A65B00 = review needed. Red #B63D3D = urgent attention. Green #23734D = resolved.', 'These are functional states, not extra brand accents. Pair each with words and an icon.'],12,leading=20)
c.showPage()
page(5,'TYPOGRAPHY / VISUAL LANGUAGE');title('Strong type. Generous space.')
text(48,473,'Bahnschrift',57,NAVY,'Brand');text(51,435,'HEADLINES / SIGNAGE / SHORT LABELS',11,TEAL,'Brand')
text(48,361,'Segoe UI',38,NAVY);text(51,328,'BODY COPY / INTERFACES / LONGER READING',11,TEAL,'Brand')
lines(520,472,['Use sentence case for messages.', 'Keep headlines brief and direct.', 'Use 1.4-1.6 line height for body text.', 'Align content to a simple left edge.', 'Give the logo room; avoid crowded panels.'],16,leading=31)
lines(48,228,['Spacing rhythm: 8 / 16 / 24 / 40 / 64. Prefer open layouts and flat colour.', 'Photography: real school spaces, natural light, respectful distance.', 'Avoid targeting reticles, face boxes, weapons, neon cyber effects and stock shields.'],15)
lines(48,100,['Fonts are available in this Windows environment and are not redistributed in this kit.', 'For web or third-party delivery, confirm font licensing or commission a licensed substitution.'],12,leading=21)
c.showPage()
page(6,'APPLICATIONS / DESIGN EXAMPLES');title('Ready for school environments.')
rect(48,154,416,345,NAVY);logo(c,78,463,218,WHITE,NAVY)
text(78,337,'Video monitoring',26,WHITE,'Brand');text(78,305,'in this area',26,WHITE,'Brand')
lines(78,253,['For site policies and enquiries,', 'contact the school reception.'],15,WHITE)
text(78,179,'ILLUSTRATIVE NOTICE / NOT A COMPLIANCE TEMPLATE',8,WHITE)
rect(500,297,452,202,MIST);logo(c,528,468,170)
text(528,375,'School safety,',26,NAVY,'Brand');text(528,342,'with people in control.',26,NAVY,'Brand')
rect(500,154,452,117,TEAL);text(528,220,'Nivra Respond',24,WHITE,'Brand');text(528,184,'Clear information. Coordinated action.',14,WHITE)
text(48,94,'Concept applications only. Confirm site-specific notice wording before installation.',12)
c.showPage();c.save()
pages=render((OUT/'Nivra-Brand-Kit.pdf').read_bytes(),1.4)
for i,im in enumerate(pages):im.save(QA/f'page-{i+1}.png')
pages[0].save(OUT/'Nivra-Brand-Overview.png')
sheet=Image.new('RGB',(1200,1260),'#dddddd')
for i,im in enumerate(pages):im.thumbnail((600,420));sheet.paste(im,((i%2)*600,(i//2)*420))
sheet.save(QA/'contact-sheet.png')
def lum(h):
    a=[int(h[i:i+2],16)/255 for i in (1,3,5)]
    a=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in a]
    return sum(x*y for x,y in zip(a,[.2126,.7152,.0722]))
ratios={}
for a,b in [(NAVY,WHITE),(TEAL,WHITE),(NAVY,TEAL),('#FFFFFF',TEAL),('#126F7D',WHITE)]:
    lo,hi=sorted([lum(a),lum(b)]);ratios[a+' on '+b]=round((hi+.05)/(lo+.05),2)
(OUT/'brand-tokens.json').write_text(json.dumps({'brand':{'ink':NAVY,'teal':TEAL,'paper':WHITE,'mist':MIST,'tealText':'#126F7D'},'status':{'review':'#A65B00','urgent':'#B63D3D','resolved':'#23734D'},'typography':{'display':'Bahnschrift','body':'Segoe UI'},'contrast':ratios},indent=2))
(OUT/'README.txt').write_text('NIVRA / SIGNAL\nFresh brand kit for school-safety applications.\n\nNivra-Brand-Kit.pdf: six-page guidelines.\nNivra-Brand-Overview.png: quick visual overview.\nlogos/: original outlined SVG and transparent PNG wordmarks; app icon.\nbrand-tokens.json: exact colour values and calculated contrast.\n\nSVG wordmarks require no fonts. Fonts themselves are not distributed.\nThe logo is a vector refinement of the Signal concept, not an exact raster trace.\nThe icon is square in PNG and rounded in SVG; platform masks may alter corners.\nRGB/sRGB delivery. Printer-specific CMYK conversion and trademark clearance are not included.\nSchool applications are design examples, not a live deployment or legal notice approval.\n')
print(json.dumps({'pages':len(pages),'contrast':ratios,'out':str(OUT)},indent=2))

