from pathlib import Path
from PIL import Image
import shutil,json,hashlib
root=Path(__file__).resolve().parent
src=Path('C:/Users/harsh.DESKTOP-VE90R6D/.codex/generated_images/01a0abda-4268-7ac3-8edf-4df75e704bd5')
files={
'A-attentive-presence.png':'exec-51217447-d26c-4590-8d4e-489c0cdfa233.png',
'B-protected-sight.png':'exec-25bcfba0-0b68-431b-93b4-d85d93833a49.png',
'C-intervention.png':'exec-5513da07-cc32-4aa5-ab23-29fed677350b.png',
'D-overhang-experiment.png':'exec-1e56647e-2846-4711-bce7-555f4acb6d90.png'}
evidence=[]
for name,original in files.items():
    target=root/name
    shutil.copy2(src/original,target)
    with Image.open(target) as im: im.verify()
    with Image.open(target) as im:
        alpha=im.getchannel('A').getextrema() if 'A' in im.getbands() else (255,255)
        assert alpha==(255,255),(name,alpha)
        evidence.append(dict(file=name,source=original,size=list(im.size),opaque=True,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
(root/'file-verification.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps(evidence,indent=2))
