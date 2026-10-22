from pathlib import Path
import json, shutil, zipfile
from PIL import Image

R=Path(__file__).resolve().parent
G=Path('C:/Users/harsh.DESKTOP-VE90R6D/.codex/generated_images/01a0abda-4268-7ac3-8edf-4df75e704bd5')
F=R.parent/'round-03/sources/fonts'
K=[
 ('01-watchful','Watchful','exec-8397f6e3-5444-4606-ac9e-ccba205fa256.png','Manrope','manrope',{'Ember':'#FF6B3D','Aubergine':'#241D33','Ice':'#EEF2F6','Lilac':'#C9BFE8'},'A broad viewing aperture creates a watchful presence. Repeat the opening as a photographic crop; keep the silhouette whole for small uses.',[(1,2),(2,1),(1,0)],'Ice 40%, Aubergine 35%, Ember 20%, Lilac 5%'),
 ('02-peripheral','Peripheral','exec-5261e3dd-0512-4e87-9064-3dbb1bafff24.png','DM Sans','dmsans',{'Iris':'#6552E8','Midnight':'#201D36','Porcelain':'#F2F2F8','Celery':'#D5E89A'},'Two curved fields share an opening. Carry the paired contour into image crops and larger brand graphics, without introducing more shapes.',[(1,2),(2,0),(1,3)],'Porcelain 45%, Iris 30%, Midnight 20%, Celery 5%'),
 ('03-lookout','Lookout','exec-a7b385e8-db92-442b-9a99-1a0c249b2974.png','Plus Jakarta Sans','plusjakartasans',{'Evergreen':'#164B43','Volt':'#D9F36A','White':'#F5F7F2','Mist':'#B5D1CB'},'A broad protective upper form looks over an open horizon. Keep the two components in fixed proportion and use the horizon as a quiet layout rule.',[(0,2),(2,0),(0,1)],'White 45%, Evergreen 35%, Volt 15%, Mist 5%')]

def lum(h):
    v=[int(h[i:i+2],16)/255 for i in (1,3,5)]
    v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in v]
    return sum(x*w for x,w in zip(v,(.2126,.7152,.0722)))
def contrast(a,b):
    lo,hi=sorted((lum(a),lum(b)));return (hi+.05)/(lo+.05)

manifest=[]
for slug,name,source,family,fd,palette,idea,pairs,balance in K:
    d=R/slug;d.mkdir(exist_ok=True);shutil.copy2(G/source,d/'brand-kit.png')
    with Image.open(d/'brand-kit.png') as im:assert im.size==(1536,1024)
    cols=list(palette.values());checks=[dict(foreground=cols[a],background=cols[b],ratio=round(contrast(cols[a],cols[b]),2)) for a,b in pairs]
    assert all(p['ratio']>=4.5 for p in checks)
    fonts=d/'fonts';fonts.mkdir(exist_ok=True)
    for weight in (400,600,700):shutil.copy2(F/fd/f'{fd}-{weight}.ttf',fonts/f'{fd}-{weight}.ttf')
    license=(F/fd/'OFL.txt').read_text(encoding='utf-8');assert 'SIL OPEN FONT LICENSE' in license
    shutil.copy2(F/fd/'OFL.txt',fonts/'OFL.txt')
    tokens=dict(brand='NIVRA',concept=name,status='awaiting-selection',palette=palette,typography=dict(family=family,body_weight=400,heading_weight=600,emphasis_weight=700,body_min_px=16,line_height=1.5),contrast=checks)
    (d/'tokens.json').write_text(json.dumps(tokens,indent=2),encoding='utf-8')
    (d/'tokens.css').write_text(':root {\n'+''.join(f'  --nivra-{n.lower()}: {v};\n' for n,v in palette.items())+f'  --nivra-font: "{family}", sans-serif;\n'+'}\n',encoding='utf-8')
    swatches='\n'.join(f'- {n}: {v}' for n,v in palette.items())
    ratios='\n'.join(f'- {p["foreground"]} on {p["background"]}: {p["ratio"]}:1' for p in checks)
    guide=f'''# NIVRA / {name}

Full brand-kit concept. Awaiting selection; no production logo master approved.

## Identity

{idea}

NIVRA is an AI surveillance and threat-prevention company. Use the descriptor “AI surveillance & threat prevention” and the brand line “Before impact.” Supporting copy: “See the situation. Make the call.”

## Colour

{swatches}

Starting proportions: {balance}. The accent identifies NIVRA and selected actions; it is not a substitute for labelled event severity. Use exact token values, not sampled colours from mockup photography.

Verified small-text pairs:

{ratios}

These are contrast calculations for exact tokens, not an accessibility certification of the generated product illustration.

## Typography

{family}: regular 400 for body, semibold 600 for headings and supporting NIVRA text, bold 700 sparingly. Body 16 px or larger at 1.5 line height. Keep lettering upright, normal-width and readable. Font files and SIL Open Font License supplied. Generated board lettering is illustrative; these font files define the reproducible type system.

## Logo usage

Maintain the silhouette and proportions. Do not stretch, rotate, outline, add effects or combine the mark with initials. Choose a solid contrasting version. The board demonstrates colour and monochrome use; final vector geometry, clear space and minimum-size rules require the selected master. No fabricated precision from a raster concept.

## Applications included on the board

- Primary identity and supporting descriptor.
- Colour palette and typographic hierarchy.
- Monochrome and reversed logo examples.
- Campaign poster and photographic graphic language.
- Square application icon.
- NIVRA Command event-review card.
- Report-cover application.

## Product and voice

Use observations, review and decisions: “Sequence ready for review”, “Human review required”, “Response team notified”. Keep the product family NIVRA Command, Camera, Respond, Admin and Trust. Use one company identity across them.

All interface and photographic scenes are illustrative. Do not claim guaranteed prevention, proven accuracy, deployed customers or automatic policing. The company is developing the system; sample marketing copy is proposed language, not evidence of performance.

## Next production stage

After selection: refine the chosen geometry, make actual SVG masters and transparent exports, verify 16/24/32 px recognition, and produce final editable applications. This package is the complete visual concept and specifications, not that final production stage.
'''
    (d/'GUIDE.md').write_text(guide,encoding='utf-8')
    manifest.append(dict(direction=name,board=str(d/'brand-kit.png'),source=source,contrast=checks))

(R/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(R/'README.md').write_text('# NIVRA / full-colour brand-kit concepts\n\nThree complete identity proposals: Watchful (ember/aubergine), Peripheral (iris/celery), Lookout (evergreen/volt). Each folder contains a full visual board, usage guide, exact JSON/CSS palette tokens, type specifications and licensed fonts.\n\nAll three boards were visually inspected. Colour-token contrast pairs, image dimensions, font licence text and ZIP integrity were checked. Master logo vectors and final editable applications await selection. Generated text and colour pixels are illustrative; the native guides and tokens are authoritative.\n\nThe earlier isolated black logo explorations are not deliverables in this package. All preceding rounds remain rejected.\n',encoding='utf-8')
zpath=R.parent/'NIVRA-full-colour-brand-kits.zip'
with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED) as z:
    for slug,*_ in K:
        for p in (R/slug).rglob('*'):
            if p.is_file():z.write(p,p.relative_to(R))
    for name in ('README.md','manifest.json'):z.write(R/name,name)
with zipfile.ZipFile(zpath) as z:assert z.testzip() is None
print(json.dumps(dict(package=str(zpath),size=zpath.stat().st_size,directions=manifest),indent=2))
