from package_concepts import package, ROOT
from PIL import Image
import json, hashlib

items = [
    dict(slug='01-apricot-aperture',name='Apricot Aperture',source='exec-e983299c-9432-4f53-a35f-7483b8d18768.png',colors=dict(primary='#FF673D',accent='#FFD1B7',ink='#191B1A',surface='#F7F6F2'),font='Manrope, proposed for supporting text',description='A bold lowercase wordmark replaces the i dot with a simple attentive eye. The eye is an integrated identifying detail, with a dimensional interpretation reserved for campaign imagery. Its main risk is the literal eye silhouette; refine its proportion rather than adding more symbolism.'),
    dict(slug='02-open-iris',name='Open Iris',source='exec-e97ac8a9-6b5a-4224-af45-392ed32479aa.png',colors=dict(primary='#9959F5',accent='#EEE7FF',ink='#17151C',surface='#FBFAFF'),font='Sora, proposed for supporting text',description='Two curved forms leave a vertical sight aperture, echoed in the shaped n and a counters. A square i dot preserves readability. This is the most abstract eye direction: the aperture could also suggest a seed or leaf, so category recognition needs the name and descriptor.'),
    dict(slug='03-clear-view',name='Clear View',source='exec-02da8775-e9ae-474f-982f-88909cafb34b.png',colors=dict(primary='#18D6B0',accent='#D6F7EB',ink='#10231E',surface='#F7FAF7'),font='Plus Jakarta Sans, proposed for supporting text',description='A connected eyelid and pupil above a short baseline create a compact eye gesture. Rounded lowercase lettering and a dark field give the identity a calm security presence. It has the clearest eye reading but is a more familiar standalone symbol than the integrated first concept.'),
]

package(items)
evidence=[]
for item in items:
    path=ROOT/item['slug']/'brand-board.png'
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        alpha=im.getchannel('A').getextrema() if 'A' in im.getbands() else (255,255)
        assert alpha==(255,255), (path,alpha)
        assert im.width>=1500 and im.height>=1000
        evidence.append(dict(concept=item['name'],size=list(im.size),mode=im.mode,opaque=True,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    tokens=json.loads((path.parent/'tokens.json').read_text())
    assert all(pair['normal_text_AA'] for pair in tokens['color_pairs'][:2]+[tokens['color_pairs'][-1]]), tokens
    print(item['name'],[(p['foreground'],p['background'],p['ratio']) for p in tokens['color_pairs'][:3]])
(ROOT/'validation.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
package(items)
