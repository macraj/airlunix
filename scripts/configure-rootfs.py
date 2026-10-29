#!/usr/bin/env python3
"""Configure a staged rootfs inside the subordinate-ID build namespace."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

repo = Path(__file__).resolve().parents[1]
root = Path(sys.argv[1]).resolve()
assert root != Path('/') and root.is_relative_to(repo / 'build')
cfg = json.loads((repo / 'configs/distribution.json').read_text())

def write(name, text, mode=0o644):
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    p.chmod(mode)
    os.chown(p, 0, 0)

for name in ('etc/passwd', 'etc/shadow', 'etc/group'):
    p = root / name
    lines = [x for x in p.read_text().splitlines() if x.split(':')[0] not in ('admin', 'mr', 'airlunix', 'airweb')]
    if name.endswith('passwd'):
        lines.append('airweb:x:2000:2000:Airlunix Web Console:/nonexistent:/sbin/nologin')
    elif name.endswith('shadow'):
        lines = ['root:!:0:0:99999:7:::' if x.startswith('root:') else x for x in lines]
        lines.append('airweb:!:0:0:99999:7:::')
    else:
        lines.append('airweb:x:2000:')
    p.write_text('\n'.join(lines) + '\n')
for name in ('home/admin', 'home/mr', 'etc/doas.d', 'root/.ssh',
             'var/cache/apk', 'etc/runlevels/default/opi-firstboot-ssh',
             'etc/runlevels/default/chronyd', 'etc/runlevels/default/ntpd'):
    p = root / name
    if p.is_symlink() or p.is_file(): p.unlink()
    elif p.exists(): shutil.rmtree(p)
for p in (root / 'etc/ssh').glob('ssh_host_*'): p.unlink()
for p in (root / 'var/log').rglob('*'):
    if p.is_file(): p.unlink()
for name in ('etc/airlunix-provisioned', 'etc/init.d/opi-firstboot-ssh',
             'etc/opi4pro-alpine-firstboot', 'usr/bin/qemu-aarch64-static'):
    (root / name).unlink(missing_ok=True)
write('etc/doas.conf', '# Authentication required; no passwordless exceptions.\npermit :wheel as root\n', 0o600)
# APK hooks are deliberately disabled during the cross build; materialize the
# doas package's root ownership/setuid requirement explicitly.
os.chown(root / 'usr/bin/doas', 0, 0)
(root / 'usr/bin/doas').chmod(0o4755)
write('etc/fstab', 'proc /proc proc nosuid,nodev,noexec 0 0\nsysfs /sys sysfs nosuid,nodev,noexec 0 0\ntmpfs /tmp tmpfs nosuid,nodev 0 0\n')
write('etc/hostname', cfg['id'] + '\n')
write('etc/os-release', f'NAME="{cfg["name"]}"\nID={cfg["id"]}\nVERSION_ID={cfg["version"]}\nPRETTY_NAME="{cfg["name"]} {cfg["version"]} ({cfg["profile"]})"\n')
digest = hashlib.sha256()
for source in sorted([repo / 'configs/distribution.json',
                      repo / 'configs/airlunix-apks.sha256',
                      repo / 'configs/airlunix-rootfs-input.sha256',
                      repo / 'configs/airlunix-board-artifacts.sha256',
                      repo / 'scripts/configure-rootfs.py',
                      repo / 'scripts/build-image.sh',
                      *(repo / 'console').glob('*.py'),
                      *(repo / 'web').glob('*'),
                      *(repo / 'configs/ram').glob('*')]):
    if source.is_file():
        digest.update(str(source.relative_to(repo)).encode() + b'\0' + source.read_bytes())
buildid = digest.hexdigest()[:16]
write('etc/airlunix-release', f'{cfg["name"]} {cfg["version"]} — {cfg["profile"]}\nBuild configuration: {buildid}\n')
write('etc/inittab', '::sysinit:/sbin/openrc sysinit\n::sysinit:/sbin/openrc boot\n::wait:/sbin/openrc default\ntty1::respawn:/usr/sbin/airlunix-status\ntty2::respawn:/usr/sbin/airlunix-console tty2\nttyS7::respawn:/usr/sbin/airlunix-console ttyS7\n::ctrlaltdel:/sbin/reboot\n::shutdown:/sbin/openrc shutdown\n')
for name, dest in {'init': 'init', 'sshd_config': 'etc/ssh/sshd_config',
                   'web.initd': 'etc/init.d/airlunix-web',
                   'admin.initd': 'etc/init.d/airlunix-admin',
                   'airlunix-web-setup': 'usr/sbin/airlunix-web-setup',
                   'identity.initd': 'etc/init.d/airlunix-identity',
                   'airlunix-status': 'usr/sbin/airlunix-status',
                   'airlunix-console': 'usr/sbin/airlunix-console',
                   'airlunix-state': 'usr/sbin/airlunix-state',
                   'airlunix-provision': 'usr/sbin/airlunix-provision',
                   'airlunix_time.py': 'usr/lib/airlunix_time.py',
                   'airlunix-time': 'usr/sbin/airlunix-time',
                   'time.json': 'etc/airlunix/time.json',
                   'time-chrony.conf': 'etc/airlunix/time-chrony.conf',
                   'time.initd': 'etc/init.d/airlunix-time',
                   'time-network-hook': 'etc/udhcpc/post-bound/airlunix-time',
                   'boot-measure.json': 'etc/airlunix/boot-measure.json',
                   'airlunix-boot-probe': 'usr/sbin/airlunix-boot-probe'}.items():
    write(dest, (repo / 'configs/ram' / name).read_text(),
          0o644 if name in ('sshd_config', 'time.json', 'time-chrony.conf', 'boot-measure.json', 'airlunix_time.py') else 0o755)
write('etc/udhcpc/post-renew/airlunix-time', (repo / 'configs/ram/time-network-hook').read_text(), 0o755)
write('etc/conf.d/crond', 'CRON_OPTS="-c /etc/crontabs -L /run/crond.log"\n')
cron_service = root / 'etc/init.d/crond'
cron_service.write_text(cron_service.read_text().replace('need logger', 'use logger'))
with (root / 'etc/crontabs/root').open('a') as cron:
    cron.write('\n* * * * * /usr/sbin/airlunix-time attempt >/dev/null 2>&1\n')
for service in ('crond', 'airlunix-time', 'airlunix-admin', 'airlunix-web'):
    link = root / 'etc/runlevels/default' / service
    if not link.is_symlink(): link.symlink_to('/etc/init.d/' + service)
write('etc/modprobe.d/opi-blacklist.conf', 'blacklist goodix_ts\n')
write('etc/profile.d/airlunix-python.sh', 'export PYTHONDONTWRITEBYTECODE=1\nexport PIP_CACHE_DIR=/tmp/pip-cache\n')
write('etc/pip.conf', '[global]\nno-cache-dir = true\n')
for name in ('var/lib/airlunix', 'etc/airlunix/selected', 'var/lib/airlunix/selected', 'state'):
    p = root / name
    p.mkdir(parents=True, exist_ok=True)
    p.chmod(0o700 if name != 'state' else 0o755)
for source in (repo / 'console').glob('*.py'):
    write('usr/lib/python3.14/site-packages/airlunix/' + source.name, source.read_text())
for source in (repo / 'web').glob('*'):
    if source.is_file():write('usr/share/airlunix-web/' + source.name, source.read_text())
(root / 'etc/airlunix/selected').chmod(0o711)
# Application cannot change persisted selection; root explicitly installs selected data.
os.chown(root / 'var/lib/airlunix/selected', 0, 0)
link = root / 'etc/runlevels/default/airlunix-identity'
link.symlink_to('/etc/init.d/airlunix-identity') if not link.exists() else None
# The console starts only after explicit device-specific HTTPS provisioning.
for p in (root / 'etc/runlevels/shutdown').glob('mount-ro'):
    p.unlink()
print(buildid)
