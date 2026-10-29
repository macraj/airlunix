"""Guarded MBR persistence-media operations. No shrink/delete/move API."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import time

class StorageError(ValueError):
    pass

@contextlib.contextmanager
def storage_lock(path=Path('/run/airlunix/storage.lock')):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StorageError('Another save or storage operation is running')
        yield

def parse_mbr(data, capacity):
    if len(data) != 512 or data[510:] != b'\x55\xaa':
        raise StorageError('Only the supported DOS/MBR layout is accepted')
    parts = []
    for slot in range(4):
        entry = data[446 + slot*16:462 + slot*16]
        start, size = struct.unpack_from('<II', entry, 8)
        if not size:
            continue
        if entry[4] in (0x05, 0x0f, 0x85, 0xee) or entry[4] == 0:
            raise StorageError('Extended/GPT/unknown partition layout is unsupported')
        if start < 65536 or start + size > capacity:
            raise StorageError('Partition overlaps reserved boot area or exceeds media')
        parts.append({'number': slot+1, 'start': start, 'sectors': size,
                      'end': start+size, 'type': entry[4], 'bootable': entry[0] == 0x80})
    ordered = sorted(parts, key=lambda p:p['start'])
    if any(a['end'] > b['start'] for a,b in zip(ordered,ordered[1:])):
        raise StorageError('Overlapping partitions are unsafe')
    first = next((p for p in parts if p['number'] == 1), None)
    if not first or first['start'] != 65536 or first['type'] != 0x83 or not first['bootable']:
        raise StorageError('Expected Airlunix boot/persistence partition 1 at 32 MiB')
    gaps=[]; end=65536
    for p in ordered:
        if p['start']>end: gaps.append({'start':end,'end':p['start'],'sectors':p['start']-end})
        end=p['end']
    if end<capacity: gaps.append({'start':end,'end':capacity,'sectors':capacity-end})
    return {'partitions':parts, 'unallocated':gaps, 'reserved_sectors':65536,
            'capacity_sectors':capacity,'mbr_sha256':hashlib.sha256(data).hexdigest()}

def plan(layout, action, size_mib=None):
    p=next(p for p in layout['partitions'] if p['number']==1)
    if action == 'expand':
        limit=min([x['start'] for x in layout['partitions'] if x['start']>=p['end'] and x['number']!=1]
                  +[layout['capacity_sectors']])
        end=limit//2048*2048
        if end<=p['end']:
            if p.get('filesystem_bytes',p['sectors']*512)>=p['sectors']*512:
                raise StorageError('No suitable adjacent free space; existing partitions will not be moved')
            end=p['end']
        result={'action':action,'number':1,'start':p['start'],'old_sectors':p['sectors'],
                'sectors':end-p['start'],'filesystem_only':end==p['end'],
                'consequence':'Durably extends partition 1 and its ext4 filesystem; boot offsets are preserved.'}
    elif action=='create':
        if not isinstance(size_mib,int) or isinstance(size_mib,bool) or not 64<=size_mib<=2_000_000:
            raise StorageError('New volume size must be an integer from 64 to 2000000 MiB')
        slot=next((i for i in range(2,5) if all(p['number']!=i for p in layout['partitions'])),None)
        if slot is None: raise StorageError('No free primary partition slot')
        size=size_mib*2048
        gap=next((g for g in layout['unallocated'] if ((g['start']+2047)//2048*2048)+size<=g['end']),None)
        if gap is None: raise StorageError('No suitable unallocated region; existing data will not be overwritten')
        result={'action':action,'number':slot,'start':(gap['start']+2047)//2048*2048,
                'sectors':size,'consequence':'Durably creates a new ext4 data volume in unallocated space. Old recoverable data there is overwritten. It will not be mounted automatically.'}
    else: raise StorageError('Unsupported storage action')
    return {**result,'layout_sha256':layout['mbr_sha256'],
            'capacity_sectors':layout['capacity_sectors']}

class Media:
    def __init__(self, state_file='/run/airlunix-state-device', test_image=None):
        self.test_image=test_image
        if test_image:
            self.disk=Path(test_image); self.partition=None
        else:
            import re
            self.partition=Path(Path(state_file).read_text().strip())
            if not re.fullmatch(r'/dev/mmcblk[0-9]+p1',str(self.partition)):
                raise StorageError('Unsupported persistence device; no disk will be guessed')
            self.disk=Path(str(self.partition)[:-2])
            if not stat.S_ISBLK(self.disk.stat().st_mode): raise StorageError('Target is not a block device')

    def capacity(self):
        if self.test_image: return self.disk.stat().st_size//512
        with self.disk.open('rb',buffering=0) as f:
            return struct.unpack('Q',fcntl.ioctl(f,0x80081272,b'\0'*8))[0]//512

    def inspect(self):
        with self.disk.open('rb') as f: data=f.read(512)
        result=parse_mbr(data,self.capacity())
        with self.disk.open('rb') as f:
            for p in result['partitions']:
                f.seek(p['start']*512+1024);sb=f.read(1024)
                if len(sb)==1024 and sb[56:58]==b'\x53\xef':
                    block=1024 << struct.unpack_from('<I',sb,24)[0]
                    p['filesystem_bytes']=struct.unpack_from('<I',sb,4)[0]*block
                    p['filesystem']='ext4'
        result['device']=str(self.disk)
        result['identity']=self.identity()
        return result

    def identity(self):
        if self.test_image: return 'disposable image'
        p=Path('/sys/class/block')/self.disk.name/'device'
        return ' '.join((p/f).read_text().strip() for f in ('name','cid') if (p/f).exists())

    def check_idle(self):
        if self.test_image: return
        with self.disk.open('rb',buffering=0) as f:
            sector=struct.unpack('I',fcntl.ioctl(f,0x1268,b'\0'*4))[0]
        if sector!=512:raise StorageError('Only 512-byte logical-sector media is supported')
        mounts=Path('/proc/mounts').read_text().splitlines()
        if any(line.split()[0].startswith(str(self.disk)) for line in mounts):
            raise StorageError('A partition on this disk is mounted; unmount it before proceeding')
        for node in Path('/sys/class/block').glob(self.disk.name+'*'):
            if (node/'holders').exists() and list((node/'holders').iterdir()):
                raise StorageError('Device has active holders')
        # Verify the expected ext4 filesystem label, not just a familiar path.
        with self.disk.open('rb') as f:
            f.seek(65536*512+1024); sb=f.read(1024)
        if sb[56:58]!=b'\x53\xef' or sb[120:136].rstrip(b'\0')!=b'airlunix-state':
            raise StorageError('Persistence filesystem identity does not match Airlunix')

    def execute(self, preview):
        self.check_idle()
        layout=self.inspect()
        if layout['mbr_sha256']!=preview['layout_sha256'] or layout['capacity_sectors']!=preview['capacity_sectors']:
            raise StorageError('Layout changed since preview; request a new preview')
        expected=plan(layout,preview['action'],preview.get('sectors',0)//2048 if preview['action']=='create' else None)
        if any(expected.get(k)!=preview.get(k) for k in expected):
            raise StorageError('Preview does not match the current safe plan')
        # Only the chosen entry's length changes for expansion. Reserved boot,
        # disk identifier and every unrelated entry remain byte-for-byte intact.
        with self.disk.open('r+b',buffering=0) as f:
            data=bytearray(f.read(512)); off=446+(preview['number']-1)*16
            if preview['action']=='create':
                data[off:off+16]=struct.pack('<B3sB3sII',0,b'\0'*3,0x83,b'\0'*3,
                                           preview['start'],preview['sectors'])
            else: struct.pack_into('<I',data,off+12,preview['sectors'])
            if not preview.get('filesystem_only'):
                f.seek(0);f.write(data);os.fsync(f.fileno())
        if self.test_image:
            return self.test_filesystem(preview)
        target=Path(str(self.disk)+'p'+str(preview['number']))
        try:
            with self.disk.open('rb',buffering=0) as f: fcntl.ioctl(f,0x125f)
        except OSError:
            return {'success':False,'partition_table_changed':True,'reboot_required':True,
                    'error':'Kernel could not reread the new table. No filesystem action was attempted. Reboot explicitly, then use the documented recovery/resume procedure.'}
        for _ in range(30):
            if target.exists(): break
            time.sleep(0.1)
        if not target.exists():
            return {'success':False,'partition_table_changed':True,'reboot_required':True,'error':'New partition node unavailable; no format attempted'}
        if preview['action']=='expand':
            check=subprocess.run(['/sbin/e2fsck','-p',str(target)],capture_output=True,timeout=120)
            if check.returncode not in (0,1):
                return {'success':False,'partition_table_changed':True,'reboot_required':check.returncode==2,'error':'Filesystem check did not permit resize; existing filesystem remains at its previous size'}
            command=['/usr/sbin/resize2fs',str(target)]
        else:
            command=['/sbin/mke2fs','-t','ext4','-L','airlunix-data',str(target)]
        result=subprocess.run(command,capture_output=True,timeout=120)
        return {'success':result.returncode==0,'partition_table_changed':True,
                'reboot_required':False,'filesystem_updated':result.returncode==0,
                'error':None if result.returncode==0 else 'Filesystem operation failed; inspect via authenticated SSH before retrying',
                'mounted_after':False}

    def test_filesystem(self,preview):
        """Exercise actual filesystem tools on regular-file slices, never a host disk."""
        import tempfile
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'partition.ext4'
            length=preview['sectors']*512
            with target.open('wb') as out:
                if preview['action']=='expand':
                    with self.disk.open('rb') as source:
                        source.seek(preview['start']*512)
                        remaining=preview['old_sectors']*512
                        while remaining:
                            data=source.read(min(1024*1024,remaining))
                            if not data:raise StorageError('Truncated disposable image')
                            out.write(data);remaining-=len(data)
                out.truncate(length)
            if preview['action']=='expand':
                checked=subprocess.run([shutil.which('e2fsck'),'-p',str(target)],capture_output=True,timeout=120)
                if checked.returncode not in (0,1):raise StorageError('Disposable filesystem check failed')
                command=[shutil.which('resize2fs'),str(target)]
            else:command=[shutil.which('mke2fs'),'-q','-t','ext4','-L','airlunix-data',str(target)]
            subprocess.run(command,check=True,capture_output=True,timeout=120)
            with self.disk.open('r+b') as disk,target.open('rb') as source:
                disk.seek(preview['start']*512)
                shutil.copyfileobj(source,disk);disk.flush();os.fsync(disk.fileno())
        return {'success':True,'partition_table_changed':not preview.get('filesystem_only',False),
                'filesystem_updated':True,'reboot_required':False,'mounted_after':False}
