#!/usr/bin/env python3
"""Inspect boot media and complete newc runtime without trusting filenames."""
import gzip
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import zlib

repo = Path(__file__).resolve().parents[1]
image = Path(sys.argv[1]).resolve()
assert image.stat().st_size <= 1_000_000_000
with image.open('rb') as f:
    mbr = f.read(512)
    assert mbr[510:] == b'\x55\xaa'
    entry = mbr[446:462]
    assert entry[0] == 0x80 and entry[4] == 0x83
    start, count = struct.unpack_from('<II', entry, 8)
    assert start == 65536 and (start + count) * 512 <= image.stat().st_size
    for path, offset in [('boot0_sdcard.fex', 8192), ('boot_package.fex', 2050 * 8192)]:
        expected = (repo / 'output/uboot' / path).read_bytes()
        f.seek(offset)
        assert f.read(len(expected)) == expected

def legacy(data, kind):
    fields = struct.unpack('>7I4B32s', data[:64])
    assert fields[0] == 0x27051956 and fields[8] == 2 and fields[9] == kind
    header = data[:4] + b'\0' * 4 + data[8:64]
    assert zlib.crc32(header) == fields[1]
    assert len(data) == 64 + fields[3]
    assert zlib.crc32(data[64:]) == fields[6]
    return data[64:]

with tempfile.TemporaryDirectory(dir=repo / 'build', prefix='airlunix-validate.') as tmp:
    tmp = Path(tmp)
    part = tmp / 'media.ext4'
    subprocess.run(['dd', f'if={image}', f'of={part}', 'bs=512', f'skip={start}',
                    f'count={count}', 'conv=sparse', 'status=none'], check=True)
    subprocess.run(['e2fsck', '-fn', str(part)], check=True)
    boot = {}
    for name in ('uImage', 'uInitrd', 'boot.scr', 'boot.cmd'):
        dest = tmp / name
        subprocess.run(['debugfs', '-R', f'dump /boot/{name} {dest}', str(part)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        boot[name] = dest.read_bytes()
    legacy(boot['uImage'], 2)
    compressed = legacy(boot['uInitrd'], 3)
    legacy(boot['boot.scr'], 6)
    assert b'rdinit=/init airlunix.ram=1' in boot['boot.cmd']
    assert b'root=${rootdev}' not in boot['boot.cmd']
    raw = gzip.decompress(compressed)
    files = {}
    offset = 0
    while True:
        header = raw[offset:offset+110]
        assert header[:6] == b'070701'
        values = [int(header[i:i+8], 16) for i in range(6, 110, 8)]
        mode, uid, gid, size, namesize = values[1], values[2], values[3], values[6], values[11]
        name = raw[offset+110:offset+110+namesize-1].decode()
        offset = (offset + 110 + namesize + 3) & ~3
        content = raw[offset:offset+size]
        offset = (offset + size + 3) & ~3
        if name == 'TRAILER!!!': break
        files[name.removeprefix('./')] = (mode, uid, gid, content)
    for name in ('init', 'bin/busybox', 'sbin/init', 'usr/bin/python3',
                 'usr/lib/python3.14/ssl.py', 'usr/lib/python3.14/venv/__init__.py',
                 'usr/lib/python3.14/site-packages/pip/__init__.py',
                 'usr/sbin/airlunix-state', 'usr/sbin/airlunix-provision',
                 'usr/sbin/airlunix-status', 'etc/init.d/airlunix-web',
                 'usr/lib/python3.14/site-packages/airlunix/web.py',
                 'usr/lib/python3.14/site-packages/airlunix/admin.py',
                 'usr/sbin/resize2fs', 'usr/bin/openssl',
                 'usr/share/airlunix-web/app.js'):
        assert name in files, name
    assert files['init'][0] & 0o111
    assert files['usr/bin/doas'][0] & 0o4000
    assert files['usr/bin/doas'][1:3] == (0, 0)
    assert b'nopass' not in files['etc/doas.conf'][3]
    passwd = files['etc/passwd'][3].decode()
    assert '\nmr:' not in passwd and '\nadmin:' not in passwd
    assert 'airweb:x:2000:2000:Airlunix Web Console:/nonexistent:/sbin/nologin' in passwd
    shadow = files['etc/shadow'][3].decode().splitlines()
    assert all(x.split(':')[1].startswith(('!', '*')) for x in shadow)
    assert not any('/ssh_host_' in name or name.endswith('/authorized_keys') for name in files)
    assert not any(name.endswith(('tls.key','tls.crt','selected.tar.gz')) for name in files)
    assert not any('doas.d/' in name for name in files)
    assert b'ext4' not in files['etc/fstab'][3]
    assert not any('autologin' in x for x in files['etc/inittab'][3].decode().splitlines())
    print(f'Image bytes: {image.stat().st_size}; partition start: {start}; sectors: {count}')
    print(f'Runtime compressed bytes: {len(compressed)}; cpio bytes: {len(raw)}; entries: {len(files)}')
    print('Boot CRCs, full runtime, production policy and credential exclusion: PASS')
print('SHA256:', hashlib.file_digest(image.open('rb'), 'sha256').hexdigest())
