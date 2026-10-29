"""Run ONLY in the disposable staged AArch64 rootfs, never the host or board."""
import os
from pathlib import Path
import secrets
import subprocess
import tarfile
from airlunix.admin import Accounts,Admin,Denied

if not Path('/run/airlunix-disposable-target-test').exists():
    raise SystemExit('Explicit disposable-target marker required')
accounts=Accounts();password=secrets.token_urlsafe(24);changed=secrets.token_urlsafe(24)
accounts.create('testnormal',password)
assert accounts.verify('testnormal',password)['administrator'] is False
assert accounts.verify('testnormal',changed) is None
assert accounts.verify('airweb',password) is None
admin=Admin()
try:admin.call({'op':'save','user':'testnormal','password':password})
except Denied:pass
else:raise AssertionError('Normal user obtained administrative save')
with tarfile.open('/tmp/target-state.tar.gz','w:gz') as tar:
    for name in ('etc/passwd','etc/shadow','etc/group'):
        tar.add('/'+name,arcname=name,recursive=False)
accounts.change('testnormal',changed)
assert accounts.verify('testnormal',password) is None
subprocess.run(['/usr/bin/python3','/usr/sbin/airlunix-state','restore','/tmp/target-state.tar.gz'],check=True)
assert accounts.verify('testnormal',password) is not None
assert accounts.verify('testnormal',changed) is None
result=subprocess.run(['/bin/su','-s','/bin/sh','airweb','-c','/usr/bin/doas -n /usr/bin/id'],capture_output=True)
assert result.returncode!=0
print('AArch64 account tooling, crypt verification, normal-user authorization, selected account restore and airweb doas rejection: PASS')
