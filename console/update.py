"""Bounded GitHub Release discovery and verified streaming to replacement media."""
import fcntl
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY='macraj/airlunix'
RELEASES_URL='https://api.github.com/repos/macraj/airlunix/releases?per_page=20'
MAX_MANIFEST=16384
MIN_IMAGE=256*1024*1024
MAX_IMAGE=1_000_000_000
ALLOWED_IMAGE=re.compile(r'https://github\.com/macraj/airlunix/releases/download/[^/]+/[^/?#]+\.img\.xz')

class UpdateError(ValueError):pass

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    hosts={'api.github.com','github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        target=urllib.parse.urlsplit(newurl)
        if target.scheme!='https' or target.hostname not in self.hosts:
            raise UpdateError('Release redirect left the approved GitHub hosts')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def opener():return urllib.request.build_opener(SafeRedirect())

def release_options(open_url=None):
    fetch=open_url or opener().open
    try:
        with fetch(urllib.request.Request(RELEASES_URL,headers={'User-Agent':'Airlunix-update/1','Accept':'application/vnd.github+json'}),timeout=20) as response:raw=response.read(128*1024+1)
    except (OSError,urllib.error.URLError) as exc:raise UpdateError('No installable Airlunux release is currently reachable') from exc
    if len(raw)>128*1024:raise UpdateError('GitHub release list exceeds the size limit')
    try:releases=json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise UpdateError('GitHub release list is invalid') from exc
    if not isinstance(releases,list):raise UpdateError('GitHub release list is invalid')
    options=[]
    for release in releases:
        if not isinstance(release,dict) or release.get('draft'):continue
        if any(isinstance(a,dict) and a.get('name')=='airlunix-update.json' for a in release.get('assets',[])):
            options.append({'tag':release.get('tag_name'),'name':release.get('name') or release.get('tag_name'),
                            'prerelease':bool(release.get('prerelease')),'published_at':release.get('published_at')})
    return options

def release_manifest(version=None,open_url=None):
    fetch=open_url or opener().open
    try:
        with fetch(urllib.request.Request(RELEASES_URL,headers={'User-Agent':'Airlunix-update/1','Accept':'application/vnd.github+json'}),timeout=20) as response:
            raw=response.read(128*1024+1)
    except (OSError,urllib.error.URLError) as exc:raise UpdateError('No installable Airlunix release is currently reachable') from exc
    if len(raw)>128*1024:raise UpdateError('GitHub release list exceeds the size limit')
    try:data=json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise UpdateError('Release manifest is invalid') from exc
    if not isinstance(data,list):raise UpdateError('GitHub release list is invalid')
    candidates=[]
    for release in data:
        if not isinstance(release,dict) or release.get('draft'):continue
        assets=release.get('assets',[])
        asset=next((a for a in assets if isinstance(a,dict) and a.get('name')=='airlunix-update.json'),None)
        if asset and isinstance(asset.get('browser_download_url'),str):candidates.append((release,asset))
    if version is not None:candidates=[item for item in candidates if item[0].get('tag_name')==version or item[0].get('name')==version]
    if not candidates:raise UpdateError('No installable Airlunix release is currently reachable')
    release,asset=candidates[0]
    manifest_url=asset['browser_download_url']
    if not re.fullmatch(r'https://github\.com/macraj/airlunix/releases/download/[^/]+/airlunix-update\.json',manifest_url):
        raise UpdateError('Release manifest URL is outside the approved repository')
    try:
        with fetch(urllib.request.Request(manifest_url,headers={'User-Agent':'Airlunix-update/1','Accept':'application/json'}),timeout=20) as response:
            raw=response.read(MAX_MANIFEST+1)
    except (OSError,urllib.error.URLError) as exc:raise UpdateError('Selected release manifest could not be downloaded') from exc
    if len(raw)>MAX_MANIFEST:raise UpdateError('Release manifest exceeds the size limit')
    try:data=json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise UpdateError('Release manifest is invalid') from exc
    image=data.get('image',{}) if isinstance(data,dict) else {}
    download=data.get('download',{}) if isinstance(data,dict) else {}
    if data.get('schema')!=1 or data.get('board')!='orangepi-4pro-a733' or not isinstance(data.get('version'),str):
        raise UpdateError('Release manifest does not target this Airlunix board')
    if not isinstance(image.get('bytes'),int) or not MIN_IMAGE<=image['bytes']<=MAX_IMAGE:
        raise UpdateError('Release image size is outside the supported bounds')
    if not isinstance(image.get('sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',image['sha256']):
        raise UpdateError('Release image SHA-256 is invalid')
    if download.get('compression')!='xz' or not isinstance(download.get('bytes'),int) or not 1<=download['bytes']<=MAX_IMAGE:
        raise UpdateError('Release download size or compression is invalid')
    if not isinstance(download.get('sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',download['sha256']):
        raise UpdateError('Release download SHA-256 is invalid')
    if not isinstance(download.get('url'),str) or not ALLOWED_IMAGE.fullmatch(download['url']):
        raise UpdateError('Release image URL is outside the approved repository')
    return {'version':data['version'],'tag':release['tag_name'],'published_at':data.get('published_at'),
            'source_commit':data.get('source_commit'),'image':image,'download':download}

def boot_identity(path=Path('/run/airlunix-boot-media.json')):
    try:data=json.loads(path.read_text())
    except (OSError,ValueError) as exc:raise UpdateError('Boot-media identity is unavailable; replacement is disabled this boot') from exc
    if not re.fullmatch(r'[0-9a-fA-F]{16,64}',str(data.get('cid',''))):raise UpdateError('Boot-media identity is invalid')
    return data

def _device_info(node,sys_block=Path('/sys/class/block')):
    name=node.name;root=sys_block/name
    cid=(root/'device/cid').read_text().strip().lower()
    sectors=int((root/'size').read_text())
    model=' '.join((root/'device/name').read_text().split()) if (root/'device/name').exists() else 'microSD'
    return {'device':str(node),'name':name,'cid':cid,'sectors':sectors,'bytes':sectors*512,'model':model}

def replacement_candidates(boot=None,dev=Path('/dev'),sys_block=Path('/sys/class/block'),mounts=Path('/proc/mounts')):
    boot=boot or boot_identity();mounted=mounts.read_text().splitlines();found=[]
    for root in sorted(sys_block.glob('mmcblk[0-9]*')):
        if not (root/'device/cid').exists():continue
        node=dev/root.name
        try:info=_device_info(node,sys_block)
        except (OSError,ValueError):continue
        if info['cid']==str(boot['cid']).lower():continue
        if any(line.split()[0].startswith(str(node)) for line in mounted):continue
        if (root/'holders').exists() and any((root/'holders').iterdir()):continue
        found.append(info)
    return found

def validate_target(info,expected_cid,image_bytes,sys_block=Path('/sys/class/block')):
    current=_device_info(Path(info['device']),sys_block)
    if current['cid']!=expected_cid or current['bytes']<image_bytes:raise UpdateError('Replacement media changed or is too small')
    if current['device']!=info['device']:raise UpdateError('Replacement device path changed')
    return current

def _validate_image_prefix(prefix,image_bytes):
    if len(prefix)<512 or prefix[510:512]!=b'\x55\xaa':raise UpdateError('Downloaded file is not a supported MBR image')
    entry=prefix[446:462];start,sectors=struct.unpack_from('<II',entry,8)
    if entry[0]!=0x80 or entry[4]!=0x83 or start!=65536 or (start+sectors)*512>image_bytes:
        raise UpdateError('Downloaded image does not have the Airlunix media layout')

def stream_image(target,manifest,expected_cid,open_url=None,sys_block=Path('/sys/class/block'),progress=None):
    image=manifest['image'];download=manifest['download']
    # Re-resolve identity immediately before the first destructive byte.
    current=_device_info(Path(target),sys_block)
    if current['cid']!=expected_cid or current['bytes']<image['bytes']:raise UpdateError('Replacement media changed or is too small')
    fetch=open_url or opener().open
    request=urllib.request.Request(download['url'],headers={'User-Agent':'Airlunix-update/1','Accept':'application/octet-stream'})
    digest=hashlib.sha256();compressed_digest=hashlib.sha256();written=0;received=0;prefix=bytearray()
    decompressor=lzma.LZMADecompressor(format=lzma.FORMAT_XZ)
    with fetch(request,timeout=60) as response:
        with Path(target).open('r+b',buffering=0) as output:
            def write_raw(chunk):
                nonlocal written
                if written+len(chunk)>image['bytes']:raise UpdateError('Decompressed image exceeds its declared size')
                if len(prefix)<65536:
                    take=min(65536-len(prefix),len(chunk));prefix.extend(chunk[:take])
                    if len(prefix)==65536:_validate_image_prefix(prefix,image['bytes'])
                output.write(chunk);digest.update(chunk);written+=len(chunk)
            while received<download['bytes']:
                packed=response.read(min(256*1024,download['bytes']-received))
                if not packed:raise UpdateError('Release download ended before its declared size')
                received+=len(packed);compressed_digest.update(packed);data=packed
                while data or not decompressor.needs_input:
                    raw=decompressor.decompress(data,max_length=1024*1024);data=b''
                    if raw:write_raw(raw)
                    if decompressor.eof:
                        if decompressor.unused_data:raise UpdateError('Compressed release contains trailing data')
                        break
                if progress:progress('download_write',received,download['bytes'])
            if response.read(1):raise UpdateError('Release download exceeds its declared size')
            if not decompressor.eof or written!=image['bytes'] or len(prefix)<65536:
                raise UpdateError('Decompressed image ended before its declared size')
            os.fsync(output.fileno())
    if compressed_digest.hexdigest()!=download['sha256']:raise UpdateError('Downloaded .img.xz SHA-256 does not match the release manifest')
    if digest.hexdigest()!=image['sha256']:raise UpdateError('Downloaded image SHA-256 does not match the release manifest')
    verify=hashlib.sha256();remaining=image['bytes']
    with Path(target).open('rb',buffering=0) as source:
        verified=0
        while remaining:
            chunk=source.read(min(1024*1024,remaining))
            if not chunk:raise UpdateError('Replacement media readback ended early')
            verify.update(chunk);remaining-=len(chunk);verified+=len(chunk)
            if progress:progress('verify_readback',verified,image['bytes'])
    if verify.hexdigest()!=image['sha256']:raise UpdateError('Replacement media readback SHA-256 does not match')
    with Path(target).open('rb',buffering=0) as disk:
        try:fcntl.ioctl(disk,0x125f)
        except OSError as exc:raise UpdateError('Image is verified, but the kernel could not reread its partition table; reboot is required before saving configuration') from exc
    partition=Path(str(target)+'p1')
    for _ in range(50):
        if partition.exists():break
        time.sleep(.1)
    if not partition.exists():raise UpdateError('Image is verified, but its persistence partition is unavailable')
    return {'success':True,'device':str(target),'partition':str(partition),'bytes':written,'sha256':image['sha256'],'version':manifest['version']}
