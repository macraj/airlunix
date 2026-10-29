#!/usr/bin/env python3
"""Create exact binary-release assets and the device-consumed update manifest."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

repo=Path(__file__).resolve().parents[1]
config=json.loads((repo/'configs/distribution.json').read_text())
version=config['version'];profile=config['profile'].lower().replace(' ','-')
name=f"{config['id']}-{version}-{profile}-a733.img"
image=repo/'output/images'/name
if not image.is_file():raise SystemExit('Build the exact release image first: '+str(image))
compressed=Path(str(image)+'.xz')
if not compressed.exists():subprocess.run(['xz','-T0','-6','-k',str(image)],check=True)
source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
def artifact(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return {'filename':path.name,'bytes':path.stat().st_size,'sha256':h.hexdigest()}
raw=artifact(image);packed=artifact(compressed);tag='v'+version
base=f'https://github.com/macraj/airlunix/releases/download/{tag}/'
manifest={'schema':1,'version':version,'board':'orangepi-4pro-a733','hardware':'Orange Pi 4 Pro / Allwinner A733',
          'source_commit':source,'published_at':datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
          'image':raw,'download':{**packed,'url':base+packed['filename'],'compression':'xz'}}
metadata={'schema':1,'release':tag,'version':version,'source_commit':source,
          'hardware_targets':[{'id':'orangepi-4pro-a733','name':'Orange Pi 4 Pro','soc':'Allwinner A733'}],
          'artifacts':[raw,{**packed,'compression':'xz','uncompressed_filename':raw['filename']}],
          'update_manifest':'airlunix-update.json'}
folder=repo/'output/releases'/tag;folder.mkdir(parents=True,exist_ok=True)
for path in (image,compressed):
    target=folder/path.name
    if target.exists():target.unlink()
    target.hardlink_to(path)
(folder/'airlunix-update.json').write_text(json.dumps(manifest,indent=2)+'\n')
(folder/'release-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
(folder/'SHA256SUMS').write_text(f"{raw['sha256']}  {raw['filename']}\n{packed['sha256']}  {packed['filename']}\n")
shutil.copy2(repo/'docs/install.md',folder/'INSTALL.md')
print(json.dumps({'folder':str(folder),'manifest':manifest},indent=2))
