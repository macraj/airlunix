"""Explicit device TLS setup. Default access is loopback through SSH forwarding."""
import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess

def main():
    if os.geteuid()!=0:raise SystemExit('Run through authenticated doas')
    p=argparse.ArgumentParser(description='Provision Airlunix Web Console HTTPS locally; does not save automatically')
    p.add_argument('--bind',default='127.0.0.1',choices=['127.0.0.1'])
    args=p.parse_args()
    if not Path('/etc/airlunix-provisioned').exists():raise SystemExit('Provision an administrator first')
    # Preview deliberately supports only an SSH tunnel. No firewall opening or
    # all-network listener is inferred from enabling the web service.
    group=grp.getgrnam('airweb').gr_gid
    parent=Path('/etc/airlunix/selected');parent.mkdir(parents=True,exist_ok=True);parent.chmod(0o711)
    folder=parent/'web';folder.mkdir(mode=0o750,exist_ok=True);os.chown(folder,0,group)
    key=folder/'tls.key';cert=folder/'tls.crt'
    if key.exists()!=cert.exists():raise SystemExit('Incomplete TLS state; inspect manually before replacing keys')
    if not key.exists():
        subprocess.run(['/usr/bin/openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256',
                        '-sha256','-days','365','-nodes','-subj','/CN=airlunix.local',
                        '-addext','subjectAltName=DNS:airlunix.local,DNS:localhost,IP:127.0.0.1',
                        '-keyout',str(key),'-out',str(cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
    for f in (key,cert):os.chown(f,0,group);f.chmod(0o640)
    config={'enabled':True,'bind':args.bind,'port':8443,'refresh_s':3,
            'allowed_hosts':['127.0.0.1:8443','localhost:8443','airlunix.local:8443'],
            'certificate':str(cert),'private_key':str(key)}
    path=folder/'config.json';path.write_text(json.dumps(config,indent=2)+'\n');os.chown(path,0,group);path.chmod(0o640)
    der=ssl.PEM_cert_to_DER_cert(cert.read_text())
    print('SHA-256 TLS certificate fingerprint:',hashlib.sha256(der).hexdigest())
    print('Configured in RAM. Verify this fingerprint over SSH before using the browser.')
    print('Start: doas rc-service airlunix-admin start; doas rc-service airlunix-web start')
    print('Tunnel: ssh -L 8443:127.0.0.1:8443 YOUR_ADMIN@DEVICE_ADDRESS')
    print('Then open https://127.0.0.1:8443 . Persist explicitly with: doas airlunix-state save')

if __name__=='__main__':main()
