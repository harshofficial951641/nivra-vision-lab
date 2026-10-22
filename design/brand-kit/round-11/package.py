from pathlib import Path
from PIL import Image
import json, shutil, hashlib, zipfile

root=Path(__file__).resolve().parent
source=Path('C:/Users/harsh.DESKTOP-VE90R6D/.codex/generated_images/01a0abda-4268-7ac3-8edf-4df75e704bd5')
def lum(h):
    v=[int(h[i:i+2],16)/255 for i in (1,3,5)]
    v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in v]
    return sum(x*y for x,y in zip(v,[.2126,.7152,.0722]))
def contrast(a,b):
    lo,hi=sorted([lum(a),lum(b)])
    return round((hi+.05)/(lo+.05),2)

items=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
validation=[]
for item in items:
    folder=root/item['slug'];folder.mkdir(exist_ok=True)
    board=folder/'brand-board.png'
    shutil.copy2(source/item['source'],board)
    with Image.open(board) as im: im.verify()
    with Image.open(board) as im:
        alpha=im.getchannel('A').getextrema() if 'A' in im.getbands() else (255,255)
        assert alpha==(255,255)
        assert im.width>=1500 and im.height>=1000
        validation.append(dict(concept=item['name'],size=list(im.size),opaque=True,sha256=hashlib.sha256(board.read_bytes()).hexdigest()))
    pairs=[dict(foreground=a,background=b,ratio=contrast(a,b),normal_text_AA=contrast(a,b)>=4.5) for a,b in item['text_pairs']]
    assert all(p['normal_text_AA'] for p in pairs),pairs
    data=dict(brand='NIVRA',direction=item['name'],status='unselected-concept',colors=item['colors'],supporting_type_proposal=item['font'],checked_text_pairs=pairs)
    (folder/'tokens.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    (folder/'tokens.css').write_text(':root {\n'+''.join(f'  --nivra-{k}: {v};\n' for k,v in item['colors'].items())+'}\n',encoding='utf-8')
    (folder/'GUIDELINES.md').write_text(f'''# NIVRA / {item['name']}

Unselected identity concept. Exact vector geometry and production use are pending selection.

{item['description']}

## Colour and type

{json.dumps(item['colors'],indent=2)}

Typography proposal: {item['font']}, used plainly for NIVRA and supporting text. The raster board is not an exact font specimen. Actual font files, licensing and symbol outlines must be finalized after selection. There is no custom wordmark concept: do not modify letters, add monograms or hide initials.

Checked intended small-text pairs are in tokens.json. They meet 4.5:1 numerically; arbitrary other combinations and generated pixel colours are not certified. Brand colour alone must not communicate event urgency. Use labels and distinct operational states.

## Composition and language

Use generous clear space, precise alignment, sparse hierarchy and flat colour. Keep the symbol/wordmark primary. The line is Before impact. The descriptor Surveillance & response is proposed, not a changed product name. Incidental generated copy is not approved copy.

Use one identity across NIVRA Command, Camera, Respond, Admin and Trust. The board's app icon and presentation cover are illustrative applications, not built software or evidence of real surveillance deployment. Describe human review and coordinated response without guaranteed prevention, crime prediction or identity inference.

## After selection

Refine one vector master; verify small-size and one-colour behavior; create SVG/PNG families; finalize font licensing, clear space, minimum size, voice, reusable templates and the final PDF brand guide. No final approval or trademark availability is implied.
''',encoding='utf-8')
    print(item['name'],[(p['foreground'],p['background'],p['ratio']) for p in pairs])
(root/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
out=root.parent/'NIVRA-standalone-symbol-concepts-round-11.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p in root.rglob('*'):
        if p.is_file() and p.suffix!='.py' and '__pycache__' not in p.parts:
            z.write(p,Path('NIVRA-round-11')/p.relative_to(root))
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    assert sum(n.endswith('brand-board.png') for n in z.namelist())==3
print(out)
