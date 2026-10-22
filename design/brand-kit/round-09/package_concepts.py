from pathlib import Path
import json, shutil, zipfile

ROOT=Path(__file__).resolve().parent
SOURCE=Path('C:/Users/harsh.DESKTOP-VE90R6D/.codex/generated_images/01a0abda-4268-7ac3-8edf-4df75e704bd5')
def luminance(h):
    c=[int(h[i:i+2],16)/255 for i in (1,3,5)]
    c=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in c]
    return sum(x*w for x,w in zip(c,[.2126,.7152,.0722]))
def ratio(a,b):
    x,y=sorted((luminance(a),luminance(b)))
    return round((y+.05)/(x+.05),2)
def package(items):
    for item in items:
        d=ROOT/item['slug']; d.mkdir(exist_ok=True)
        shutil.copy2(SOURCE/item['source'],d/'brand-board.png')
        c=item['colors']
        pairs=[{'foreground':a,'background':b,'ratio':ratio(a,b),'normal_text_AA':ratio(a,b)>=4.5} for a,b in [(c['ink'],c['surface']),(c['surface'],c['ink']),(c['ink'],c['primary']),(c['surface'],c['primary']),(c['ink'],c['accent']),(c['primary'],c['accent'])]]
        pairs.append({'foreground':'#000000','background':c['primary'],'ratio':ratio('#000000',c['primary']),'normal_text_AA':ratio('#000000',c['primary'])>=4.5})
        data={'brand':'NIVRA','direction':item['name'],'status':'unselected-concept','colors':c,'on_primary_text':'#000000','supporting_type_direction':item['font'],'color_pairs':pairs,'note':'Exact intended values. Generated raster pixels and lettering are illustrative. Large display lettering can use pairs >=3:1; normal text requires >=4.5:1.'}
        (d/'tokens.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
        (d/'tokens.css').write_text(':root {\n'+''.join(f'  --nivra-{k}: {v};\n' for k,v in c.items())+'  --nivra-on-primary: #000000;\n}\n',encoding='utf-8')
        (d/'GUIDELINES.md').write_text(f'''# NIVRA / {item['name']}

Concept for selection, not an approved production identity.

## Identity
{item['description']}

Use one shared identity across NIVRA Command, Camera, Respond, Admin and Trust. Retain the line Before impact. Exact vector geometry and optical small-size refinements follow selection; do not trace inconsistent photographic specimens as independent masters.

## Color and typography
Use a focused accent with generous open space and deliberate oversized lettering. The operational product should retain legible, quiet reading surfaces; brand color must not imply an urgent event on its own.

Primary {c['primary']}; secondary {c['accent']}; ink {c['ink']}; light surface {c['surface']}.

Supporting font direction: {item['font']}. This is a proposed pairing; the generated board is not an exact font specimen. Custom logo lettering requires its own master outlines.

Use the numerical contrast pairs in tokens.json. Use pure black #000000 for small text directly on the vivid primary; in Open Iris the ordinary carbon ink is only 4.40:1 on orchid and must not substitute for this semantic text token. White on ink is also suitable for buttons. Pairings below 4.5:1 are unsuitable for small text. Do not assume all color combinations or generated labels are accessible.

## Applications and language
The board demonstrates lettering, a compact eye motif, a palette, an illustrative phone alert and a proposal cover. Generated screens are concept applications, not built software. Incidental cover slogans are not approved product copy; use Before impact. in production. Use dark ink for small button text on the proposed vivid primary colours, subject to the numerical contrast checks.

Prefer Notice. Review. Respond. / Human review required. / Response requested. / Acknowledge. / Situation clear.

## Production after selection
Refine exact logo geometry and wordmark, check small sizes, produce SVG and transparent PNG families, finalize typography licensing and embedded fonts, and create reusable application templates and a final PDF guide. No vector accuracy, printing proof or trademark availability is claimed at this stage.
''',encoding='utf-8')
    out=ROOT.parent/'NIVRA-reference-led-concepts-round-09.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p in ROOT.rglob('*'):
            if p.is_file() and p.suffix!='.py' and '__pycache__' not in p.parts and 'references' not in p.parts:
                z.write(p,Path('NIVRA-round-09')/p.relative_to(ROOT))
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        assert sum(n.endswith('brand-board.png') for n in z.namelist())==3
    print(out)
