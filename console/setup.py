"""Explicit device TLS setup. Default access is loopback through SSH forwarding."""
import argparse
import grp
import hashlib
import json
import os
import re
from pathlib import Path
import ssl
import subprocess
import secrets
import time
from .admin import Accounts

def private_file(path,data,uid=0,gid=0):
    temporary=path.with_name(path.name+'.'+secrets.token_hex(8))
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        os.fchown(f.fileno(),uid,gid);f.write(data)
    os.replace(temporary,path)

def issue_first_login(folder,administrator=None):
    if not (folder/'first-login-completed').exists():
        users=[u for u in Accounts().interactive() if u['administrator'] and (not administrator or u['name']==administrator)]
        if len(users)!=1:raise SystemExit('Use --admin to choose one provisioned administrator')
        user=users[0];token=secrets.token_urlsafe(32)
        runtime=Path('/run/airlunix');runtime.mkdir(parents=True,exist_ok=True)
        record={'user':user['name'],'token_sha256':hashlib.sha256(token.encode()).hexdigest(),'expires_boot_s':time.monotonic()+300}
        target=runtime/'first-login.json';private_file(target,json.dumps(record).encode())
        import pwd
        account=pwd.getpwnam(user['name']);target=Path(account.pw_dir)/'.airlunix-web-first-login'
        private_file(target,(token+'\n').encode(),account.pw_uid,account.pw_gid)
        print('Passwordless first-browser login prepared for '+user['name']+'; retrieve its one-use link through authenticated SSH. Expires in 5 minutes. No token is printed or persisted.')


def main():
    if os.geteuid()!=0:raise SystemExit('Run through authenticated doas')
    p=argparse.ArgumentParser(description='Provision Airlunix Web Console HTTPS locally; does not save automatically')
    p.add_argument('--bind',default='127.0.0.1',choices=['127.0.0.1','0.0.0.0'])
    p.add_argument('--lan-address',help='Interface address included in TLS certificate and allowed management hosts')
    p.add_argument('--admin',help='Provisioned administrator for passwordless first browser login')
    p.add_argument('--issue-first-login',action='store_true',help='Issue only a volatile first-login link for already provisioned HTTPS')
    args=p.parse_args()
    if not Path('/etc/airlunix-provisioned').exists():raise SystemExit('Provision an administrator first')
    if args.issue_first_login:
        folder=Path('/etc/airlunix/selected/web')
        if not (folder/'config.json').exists():raise SystemExit('HTTPS has not been provisioned')
        issue_first_login(folder,args.admin);return
    if args.bind=='0.0.0.0' and (not args.lan_address or not re.fullmatch(r'(?:\d{1,3}\.){3}\d{1,3}',args.lan_address)):
        raise SystemExit('--lan-address with the intended management IPv4 address is required for LAN binding')
    group=grp.getgrnam('airweb').gr_gid
    parent=Path('/etc/airlunix/selected');parent.mkdir(parents=True,exist_ok=True);parent.chmod(0o711)
    folder=parent/'web';folder.mkdir(mode=0o750,exist_ok=True);os.chown(folder,0,group)
    key=folder/'tls.key';cert=folder/'tls.crt'
    if key.exists()!=cert.exists():raise SystemExit('Incomplete TLS state; inspect manually before replacing keys')
    renew=args.lan_address and cert.exists() and subprocess.run(['/usr/bin/openssl','x509','-in',str(cert),'-noout','-checkip',args.lan_address],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0
    if not key.exists() or renew:
        key_tmp=key.with_suffix('.key.new');cert_tmp=cert.with_suffix('.crt.new')
        subprocess.run(['/usr/bin/openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256',
                        '-sha256','-days','365','-nodes','-subj','/CN=airlunix.local',
                        '-addext','subjectAltName=DNS:airlunix.local,DNS:localhost,IP:127.0.0.1'+(',IP:'+args.lan_address if args.lan_address else ''),
                        '-keyout',str(key_tmp),'-out',str(cert_tmp)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
        if key.exists():key_tmp.replace(key);cert_tmp.replace(cert)
        else:key_tmp.replace(key);cert_tmp.replace(cert)
    for f in (key,cert):os.chown(f,0,group);f.chmod(0o640)
    allowed=['127.0.0.1:8443','localhost:8443','airlunix.local:8443']
    if args.lan_address:allowed.append(args.lan_address+':8443')
    config={'enabled':True,'bind':args.bind,'port':8443,'refresh_s':3,
            'allowed_hosts':allowed,
            'certificate':str(cert),'private_key':str(key)}
    path=folder/'config.json';path.write_text(json.dumps(config,indent=2)+'\n');os.chown(path,0,group);path.chmod(0o640)
    der=ssl.PEM_cert_to_DER_cert(cert.read_text())
    print('SHA-256 TLS certificate fingerprint:',hashlib.sha256(der).hexdigest())
    print('Configured in RAM. Verify this fingerprint over SSH before using the browser.')
    print('Start: doas rc-service airlunix-admin start; doas rc-service airlunix-web start')
    print('Tunnel: ssh -L 8443:127.0.0.1:8443 YOUR_ADMIN@DEVICE_ADDRESS')
    print('Then open https://127.0.0.1:8443 . Persist explicitly with: doas airlunix-state save')
    issue_first_login(folder,args.admin)

if __name__=='__main__':main()
