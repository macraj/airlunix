"""Offline checks inside the final candidate's disposable AArch64 rootfs copy."""
import ctypes
import json
import os
from pathlib import Path
import pip
import ssl
import subprocess
import sys
import venv
import airlunix.web
import airlunix.admin
import airlunix.boot_storage

assert sys.version_info[:3]==(3,14,10)
target='/tmp/final-candidate-venv'
os.environ['PIP_NO_INDEX']='1'
venv.create(target,with_pip=True,clear=True)
result=subprocess.run([target+'/bin/python','-m','pip','--version'],check=True,capture_output=True,text=True)
libraries=[]
for name in ('libVIPhal.so','libNBGlinker.so'):
    ctypes.CDLL('/usr/lib/'+name);libraries.append({'name':name,'aarch64_loader':'passed','hardware_execution':'not tested'})
print(json.dumps({'python':sys.version,'ssl':ssl.OPENSSL_VERSION,'pip':pip.__version__,
                  'venv_with_pip_offline':True,'venv_pip':result.stdout.strip(),
                  'console_module_imports':'passed','npu_libraries':libraries,
                  'network_downloads':False,'environment':'disposable final-candidate rootfs under host AArch64 emulation; not board boot'}))
