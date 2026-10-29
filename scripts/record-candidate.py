#!/usr/bin/env python3
"""Record private candidate evidence; this does not approve or publish a release."""
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess

repo=Path(__file__).resolve().parents[1]
image=repo/'output/images/airlunix-0.3.0-headless-server-a733.img'
compressed=image.with_suffix('.img.xz')
source_revision='d53541e872603788ab2f14014f596a54035ae46e'
runtime=repo/'output/images/airlunix-0.3.0-runtime.cpio.gz'
raw=gzip.decompress(runtime.read_bytes());files={};offset=0
while True:
    header=raw[offset:offset+110];assert header[:6]==b'070701'
    values=[int(header[i:i+8],16) for i in range(6,110,8)]
    size,namesize=values[6],values[11]
    name=raw[offset+110:offset+110+namesize-1].decode().removeprefix('./')
    offset=(offset+110+namesize+3)&~3;content=raw[offset:offset+size];offset=(offset+size+3)&~3
    if name=='TRAILER!!!':break
    files[name]=(values[1],content)
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
inputs=[]
for manifest in sorted((repo/'configs').glob('airlunix-*.sha256')):
    for line in manifest.read_text().splitlines():
        digest,name=line.split(maxsplit=1)
        assert sha(repo/name)==digest
        inputs.append({'file':name,'sha256':digest,'manifest':str(manifest.relative_to(repo))})
matched=[]
for source in sorted((repo/'console').glob('*.py')):
    destination='usr/lib/python3.14/site-packages/airlunix/'+source.name
    assert files[destination][1]==source.read_bytes()
    committed=subprocess.check_output(['git','show',source_revision+':'+str(source.relative_to(repo))],cwd=repo)
    assert committed==source.read_bytes()
    matched.append({'source':str(source.relative_to(repo)),'runtime':destination,'sha256':sha(source)})
for source in sorted((repo/'web').glob('*')):
    destination='usr/share/airlunix-web/'+source.name
    assert files[destination][1]==source.read_bytes()
    assert subprocess.check_output(['git','show',source_revision+':'+str(source.relative_to(repo))],cwd=repo)==source.read_bytes()
    matched.append({'source':str(source.relative_to(repo)),'runtime':destination,'sha256':sha(source)})
digest=hashlib.sha256()
build_sources=sorted([repo/'configs/distribution.json',repo/'configs/airlunix-apks.sha256',
    repo/'configs/airlunix-rootfs-input.sha256',repo/'configs/airlunix-board-artifacts.sha256',
    repo/'scripts/configure-rootfs.py',repo/'scripts/build-image.sh',
    *(repo/'console').glob('*.py'),*(repo/'web').glob('*'),*(repo/'configs/ram').glob('*')])
for path in build_sources:
    if not path.is_file():continue
    relative=str(path.relative_to(repo));content=path.read_bytes()
    assert subprocess.check_output(['git','show',source_revision+':'+relative],cwd=repo)==content
    digest.update(relative.encode()+b'\0'+content)
build_id=digest.hexdigest()[:16]
assert build_id.encode() in files['etc/airlunix-release'][1]
branding=[]
for name,(mode,content) in files.items():
    if mode&0o170000==0o100000 and name.startswith(('etc/','usr/share/','usr/sbin/airlunix','usr/lib/python3.14/site-packages/airlunix/')):
        if b'ATEBOS' in content or b'atebos' in content:branding.append(name)
assert not branding,branding
with image.open('rb') as f:
    mbr=f.read(512);start,sectors=struct.unpack_from('<II',mbr,454)
components=[]
for record in files['lib/apk/db/installed'][1].decode().strip().split('\n\n'):
    fields=dict(line.split(':',1) for line in record.splitlines() if ':' in line and line[1:2]==':')
    if 'P' not in fields:continue
    components.append({'type':'library','name':fields['P'],'version':fields.get('V','unknown'),
                       'purl':f'pkg:apk/alpine/{fields["P"]}@{fields.get("V","unknown")}?arch=aarch64',
                       'properties':[{'name':'alpine:declared-license','value':fields.get('L','unknown')},
                                     {'name':'upstream:url','value':fields.get('U','unknown')},
                                     {'name':'alpine:origin','value':fields.get('o','unknown')} ]})
npu=[]
for name,(_,data) in files.items():
    if name.endswith(('vipcore.ko','libVIPhal.so','libNBGlinker.so','opi-vpm-run','network_binary.nb','input_0.dat')):
        npu.append({'file':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                    'validation':'image presence/hash only; hardware execution not tested on this candidate'})
tested_root=repo/'build/airlunix-build.bGtP0g/rootfs'
target_matches=[]
for name,(mode,data) in files.items():
    if mode&0o170000==0o100000 and (name.startswith('usr/lib/python3.14/') or name.startswith('usr/lib/libpython3.14') or name=='usr/bin/python3.14'):
        assert (tested_root/name).read_bytes()==data,name
        target_matches.append(name)
artifacts=[]
for path in (image,compressed,runtime):
    artifacts.append({'file':path.name,'bytes':path.stat().st_size,'MiB':path.stat().st_size/1048576,'sha256':sha(path)})
baseline=repo/'build/baseline-comparable.img.xz'
result={'status':'private developer-preview candidate; not accepted or cleared for publication',
    'source_revision':source_revision,'source_relation':'Build-input source bytes match committed source; retrospective recording after assembly, not a signed at-build attestation',
    'build_id':build_id,'artifacts':artifacts,'compression':'XZ, xz -T2 -6 -k; raw image retained',
    'partition':{'table':'DOS/MBR','logical_sector_bytes':512,'start_sector':start,'sectors':sectors,'bytes':sectors*512,
                 'label':'airlunix-state','filesystem':'ext4','block_size':4096,'blocks':188416,'used_blocks':27373,
                 'free_blocks':188416-27373,'automatic_expansion':False},
    'minimum_card_bytes_by_layout':image.stat().st_size,'physical_minimum_card_test':'not performed; actual card must expose at least image bytes',
    'board_ram_requirement':'new candidate not booted on board; minimum unmeasured',
    'console_included':True,'console_source_runtime_matches':matched,
    'target_python_image_file_matches':len(target_matches),
    'locked_inputs':inputs,'npu_components':npu,'branding_scan':'no prior product marketing references in inspected user-facing runtime paths; legal notices retained',
    'raw_size_delta_vs_previous_base':0,'runtime_cpio_delta_vs_previous_base':len(raw)-172524544,
    'runtime_gzip_delta_vs_previous_base':runtime.stat().st_size-56706640,
    'compressed_delta_vs_previous_base_same_settings':compressed.stat().st_size-baseline.stat().st_size if baseline.exists() else None,
    'limits':['No physical board boot or console resource/SD-I/O test for this image',
              'Private historical rootfs snapshot remains an input; public clean bootstrap and source closure incomplete',
              'Not all prebuilt board artifacts have independently reconstructed source-to-binary provenance',
              'Component redistribution rights and project-owned-code licence remain unresolved',
              'Bit-for-bit second-build reproducibility not tested']}
(repo/'docs/candidate-provenance.json').write_text(json.dumps(result,indent=2)+'\n')
sbom={'bomFormat':'CycloneDX','specVersion':'1.6','version':1,'metadata':{'component':{'type':'operating-system','name':'Airlunix Headless Server','version':'0.3.0'}},'components':components}
(repo/'docs/candidate-sbom.cdx.json').write_text(json.dumps(sbom,indent=2)+'\n')
(repo/'output/images/SHA256SUMS').write_text(''.join(f'{a["sha256"]}  {a["file"]}\n' for a in artifacts))
print(json.dumps({'build_id':build_id,'artifacts':artifacts,'packages':len(components),'npu_files':len(npu)},indent=2))
