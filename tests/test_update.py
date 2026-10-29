"""Host-isolated release and replacement-media tests; no block device is touched."""
import hashlib
import importlib.util
import io
import json
import lzma
from pathlib import Path
import sys
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('airlunix',ROOT/'console/__init__.py',submodule_search_locations=[str(ROOT/'console')])
package=importlib.util.module_from_spec(spec);sys.modules.setdefault('airlunix',package);spec.loader.exec_module(package)
from airlunix.update import UpdateError,release_manifest,replacement_candidates,stream_image

class Response(io.BytesIO):
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def manifest(self,url='https://github.com/macraj/airlunix/releases/download/v1/airlunix.img.xz'):
        return {'schema':1,'version':'1.0.0','board':'orangepi-4pro-a733','source_commit':'a'*40,
                'image':{'filename':'airlunix.img','bytes':256*1024*1024,'sha256':'b'*64},
                'download':{'filename':'airlunix.img.xz','url':url,'bytes':1234,'sha256':'c'*64,'compression':'xz'}}

    def test_manifest_accepts_only_bounded_official_release(self):
        good=json.dumps(self.manifest()).encode()
        result=release_manifest(open_url=lambda *a,**k:Response(good))
        self.assertEqual(result['version'],'1.0.0');self.assertEqual(result['download']['compression'],'xz')
        for url in ('http://github.com/macraj/airlunix/releases/download/v1/a.img.xz',
                    'https://example.com/a.img.xz','https://github.com/other/airlunix/releases/download/v1/a.img.xz'):
            bad=json.dumps(self.manifest(url)).encode()
            with self.assertRaises(UpdateError):release_manifest(open_url=lambda *a,raw=bad,**k:Response(raw))

    def test_candidate_excludes_boot_cid_and_mounted_media(self):
        sysblock=self.root/'sys';dev=self.root/'dev';sysblock.mkdir();dev.mkdir();mounts=self.root/'mounts'
        for number,cid in ((0,'a'*32),(1,'b'*32),(2,'c'*32)):
            node=sysblock/f'mmcblk{number}';(node/'device').mkdir(parents=True);(node/'holders').mkdir()
            (node/'device/cid').write_text(cid);(node/'device/name').write_text('TEST CARD');(node/'size').write_text('2000000')
            (dev/f'mmcblk{number}').touch()
        mounts.write_text(str(dev/'mmcblk2p1')+' /state ext4 rw 0 0\n')
        found=replacement_candidates({'cid':'a'*32},dev,sysblock,mounts)
        self.assertEqual([x['cid'] for x in found],['b'*32])

    def test_streams_xz_with_bounded_memory_and_verifies_readback(self):
        size=40*1024*1024;raw=bytearray(size);raw[510:512]=b'\x55\xaa';raw[446]=0x80;raw[450]=0x83
        import struct
        struct.pack_into('<II',raw,454,65536,(size//512)-65536)
        raw=bytes(raw);packed=lzma.compress(raw,preset=0);target=self.root/'mmcblk9';target.write_bytes(b'\0'*(size+1024))
        (self.root/'mmcblk9p1').touch();sysblock=self.root/'sys';node=sysblock/'mmcblk9';(node/'device').mkdir(parents=True);(node/'holders').mkdir()
        (node/'device/cid').write_text('d'*32);(node/'device/name').write_text('TEST CARD');(node/'size').write_text(str((size+1024)//512))
        manifest={'version':'test','image':{'bytes':size,'sha256':hashlib.sha256(raw).hexdigest()},
                  'download':{'url':'https://github.com/macraj/airlunix/releases/download/v/a.img.xz','bytes':len(packed),
                              'sha256':hashlib.sha256(packed).hexdigest(),'compression':'xz'}}
        tracemalloc.start()
        with patch('airlunix.update.fcntl.ioctl',return_value=0):
            result=stream_image(target,manifest,'d'*32,open_url=lambda *a,**k:Response(packed),sys_block=sysblock)
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        self.assertTrue(result['success']);self.assertEqual(target.read_bytes()[:size],raw)
        self.assertLess(peak,8*1024*1024)

    def test_partial_or_corrupt_download_is_never_success(self):
        size=40*1024*1024;target=self.root/'mmcblk8';target.write_bytes(b'\0'*size)
        sysblock=self.root/'sys';node=sysblock/'mmcblk8';(node/'device').mkdir(parents=True)
        (node/'device/cid').write_text('e'*32);(node/'size').write_text(str(size//512))
        manifest={'version':'test','image':{'bytes':size,'sha256':'0'*64},
                  'download':{'url':'https://github.com/macraj/airlunix/releases/download/v/a.img.xz','bytes':100,
                              'sha256':'0'*64,'compression':'xz'}}
        with self.assertRaises(UpdateError):stream_image(target,manifest,'e'*32,open_url=lambda *a,**k:Response(b'bad'),sys_block=sysblock)

if __name__=='__main__':unittest.main()
