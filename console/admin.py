"""Narrow local privileged API. No command, path or shell execution endpoint."""
import collections
import ctypes
import grp
import hashlib
import hmac
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import socket
import socketserver
import struct
import subprocess
import threading
import time
from .storage import Media, StorageError, storage_lock
from .process import run as bounded_run
from .logging_ram import emit, install_output, Collector

class Denied(PermissionError): pass

class Accounts:
    def interactive(self):
        wheel=grp.getgrnam('wheel')
        return [{'name':p.pw_name,'uid':p.pw_uid,
                 'administrator':p.pw_gid==wheel.gr_gid or p.pw_name in wheel.gr_mem}
                for p in pwd.getpwall() if p.pw_uid>=1000 and p.pw_uid<60000
                and p.pw_shell in ('/bin/ash','/bin/sh','/bin/bash')]

    def verify(self, name, password):
        if not valid_name(name) or not isinstance(password,str) or not 1<=len(password)<=1024:
            return None
        user=next((u for u in self.interactive() if u['name']==name),None)
        if not user: return None
        shadow=next((line.split(':')[1] for line in Path('/etc/shadow').read_text().splitlines()
                     if line.split(':')[0]==name),'!')
        if not shadow or shadow.startswith(('!','*')): return None
        library=ctypes.CDLL(None)
        if not hasattr(library,'crypt'): library=ctypes.CDLL('libcrypt.so.1')
        library.crypt.argtypes=(ctypes.c_char_p,ctypes.c_char_p)
        library.crypt.restype=ctypes.c_char_p
        with CRYPT_LOCK:
            value=library.crypt(password.encode(),shadow.encode())
            return user if value and hmac.compare_digest(value.decode(),shadow) else None

    def change(self,name,password):
        if not isinstance(password,str) or not password or len(password)>1024 or any(c in password for c in '\r\n\0'):
            raise ValueError('A nonempty password without line breaks is required')
        subprocess.run(['/usr/sbin/chpasswd'],input=f'{name}:{password}\n',text=True,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=True)

    def create(self,name,password):
        if not valid_name(name) or name in ('root','airweb','airlunix'):
            raise ValueError('Invalid or reserved user name')
        try: pwd.getpwnam(name)
        except KeyError: pass
        else: raise ValueError('Account already exists')
        if not isinstance(password,str) or not password or len(password)>1024 or any(c in password for c in '\r\n\0'):
            raise ValueError('A nonempty password without line breaks is required')
        subprocess.run(['/usr/sbin/adduser','-D','-s','/bin/ash',name],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=True)
        # A password-setting failure leaves the newly created account locked;
        # it never grants administrative access or deletes an existing user.
        self.change(name,password)

CRYPT_LOCK=threading.Lock()
def valid_name(name): return isinstance(name,str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,30}',name) is not None

class Admin:
    def __init__(self,accounts=None,media=None,state=Path('/run/airlunix'),persist=None,first_marker=Path('/etc/airlunix/selected/web/first-login-completed')):
        self.accounts=accounts or Accounts();self.media=media;self.state=state
        state.mkdir(parents=True,exist_ok=True)
        keypath=state/'fingerprint.key'
        if not keypath.exists():
            fd=os.open(keypath,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as f:f.write(secrets.token_bytes(32))
        self.key=keypath.read_bytes();self.plans={};self.audit=collections.deque(maxlen=32);self.log_grants={};self.log_collector=None;self.log_reads={};self.export_lock=threading.Lock()
        self.limits=collections.OrderedDict();self.lock=threading.RLock()
        self.persist=persist or self.save_system
        self.first_marker=first_marker;self.bootstrap_grants={}
        baseline=state/'saved-fingerprint'
        self.baseline=baseline.read_text() if baseline.exists() else self.fingerprint()
        if not baseline.exists():baseline.write_text(self.baseline);baseline.chmod(0o600)
        try:self.last_save=json.loads((state/'last-save.json').read_text())
        except FileNotFoundError:self.last_save=None

    def fingerprint(self):
        digest=hashlib.sha256()
        paths=[Path('/etc/passwd'),Path('/etc/shadow'),Path('/etc/group'),Path('/etc/hostname')]
        for directory in ('/etc/airlunix/selected','/var/lib/airlunix/selected'):
            paths += sorted(p for p in Path(directory).rglob('*') if p.is_file() and not p.is_symlink())
        paths += sorted(Path('/home').glob('*/.ssh/authorized_keys'))
        for p in paths:
            if p.is_file(): digest.update(str(p).encode()+b'\0'+p.read_bytes())
        return hmac.new(self.key,digest.digest(),hashlib.sha256).hexdigest()

    def log(self,user,action,success):
        self.audit.append({'boot_s':round(time.monotonic(),3),'user':user,'action':action,'success':success})
        emit('security' if action in ('login','authentication') else 'administration',action,success,actor=user)

    def authenticate(self,name,password):
        now=time.monotonic()
        with self.lock:
            failures=[t for t in self.limits.get(name,[]) if now-t<300]
            if len(failures)>=5: raise Denied('Login temporarily throttled; retry later')
            user=self.accounts.verify(name,password)
            if not user:
                failures.append(now);self.limits[name]=failures
                while len(self.limits)>128:self.limits.popitem(last=False)
                self.log(name if valid_name(name) else '(invalid)', 'authentication', False)
                raise Denied('Authentication failed')
            self.limits.pop(name,None)
            return user

    def save_system(self):
        # The persistence command owns the shared storage lock itself.
        result=bounded_run(['/usr/sbin/airlunix-state','save'],capture_output=True,text=True,timeout=120)
        mounted=self.mounted()
        if result.returncode or mounted:
            raise StorageError('Save failed or SD remains mounted. Use authenticated SSH to inspect /state and unmount safely; do not remove media.')
        return {'success':True,'sd_unmounted':True}

    def mounted(self):
        try: device=Path('/run/airlunix-state-device').read_text().strip()
        except FileNotFoundError:return False
        return any(line.split()[0]==device for line in Path('/proc/mounts').read_text().splitlines())

    def call(self,request):
        op=request.get('op')
        operation=op if isinstance(op,str) and len(op)<40 else 'invalid'
        sensitive=operation in ('save','password','create_user','storage_preview','storage_apply','first_password','bootstrap_login')
        correlation=secrets.token_hex(8)
        if sensitive:emit('administration',operation+'_start',actor=request.get('user',''),operation=correlation)
        try:
            result=self._call(request)
            if sensitive:emit('administration',operation+'_complete',result.get('success',True),actor=request.get('user',''),operation=correlation)
            return result
        except Exception as exc:
            emit('administration' if sensitive else 'security',operation+'_failed',False,
                 actor=request.get('user',''),reason=type(exc).__name__,operation=correlation)
            raise

    def _call(self,request):
        op=request.get('op')
        if op=='log_authorize':
            user=self.authenticate(request.get('user'),request.get('password'))
            if not user['administrator']:raise Denied('Administrator required')
            now=time.monotonic()
            self.log_grants={k:v for k,v in self.log_grants.items() if v['expires']>now}
            if len(self.log_grants)>=16:raise Denied('Log grant limit')
            token=secrets.token_urlsafe(32)
            self.log_grants[hashlib.sha256(token.encode()).hexdigest()]={'user':user['name'],'expires':now+300,'last_read':0}
            emit('security','log_authorized',actor=user['name'])
            return {'grant':token,'expires_in_s':300}
        if op in ('logs','log_export'):
            token=request.get('grant','')
            if not isinstance(token,str) or len(token)>128:raise Denied('Log authorization required')
            grant=self.log_grants.get(hashlib.sha256(token.encode()).hexdigest())
            if not grant or grant['expires']<=time.monotonic():raise Denied('Fresh administrator log authorization required')
            if not self.log_collector:raise ValueError('Log collector unavailable')
            if op=='logs':
                if time.monotonic()-grant['last_read']<1:raise Denied('Log read rate limit')
                grant['last_read']=time.monotonic()
                return self.log_collector.store.query(request.get('channel','security'),request.get('cursor'),
                    request.get('limit',100),request.get('event',''),request.get('severity',''))
            exporter=self.authenticate(request.get('user'),request.get('password'))
            if not exporter['administrator'] or exporter['name']!=grant['user']:raise Denied('Fresh administrator authentication required')
            if self.log_collector.store.low_memory:raise Denied('Export unavailable under memory pressure')
            if not self.export_lock.acquire(False):raise Denied('Export already running')
            try:
                # One bounded page per channel, redacted structured records only.
                # No raw messages, identifiers, paths, command args or state files.
                import base64,gzip
                payload={'schema':1,'release':Path('/etc/airlunix-release').read_text()[:256],
                         'health':self.log_collector.store.status(),'records':[],
                         'omissions':['Older pages','Raw diagnostic messages','Private device and network state']}
                mem={}
                for line in Path('/proc/meminfo').read_text().splitlines():
                    key,value=line.split(':',1)
                    if key in ('MemTotal','MemAvailable','Shmem'):mem[key]=int(value.split()[0])
                payload['current_state']={'memory_kib':mem,'uptime_boot_s':time.clock_gettime(time.CLOCK_BOOTTIME),
                    'sd_mounted':any(x.split()[0].startswith('/dev/mmc') for x in Path('/proc/mounts').read_text().splitlines())}
                for channel in self.log_collector.store.quotas:
                    rows=self.log_collector.store.query(channel,limit=32)['records']
                    for row in rows:
                        payload['records'].append({k:v for k,v in row.items() if k in
                            ('schema','sequence','monotonic_s','boot_s','wall_utc_s','time_confidence','channel','producer','event','success','severity','reason','counts','replayed','operation')})
                raw=json.dumps(payload,separators=(',',':')).encode()
                if len(raw)>400000:raise ValueError('Export size limit')
                data=gzip.compress(raw,mtime=0)
                if len(data)>45000:raise ValueError('Export transfer limit')
                emit('administration','diagnostic_export',actor=grant['user'])
                return {'encoding':'gzip-base64','data':base64.b64encode(data).decode(),'uncompressed_bytes':len(raw)}
            finally:self.export_lock.release()
        if op=='bootstrap_login':
            token=request.get('token')
            if not isinstance(token,str) or not 32<=len(token)<=128:raise Denied('First-login link is invalid')
            with self.lock:
                path=self.state/'first-login.json'
                if self.first_marker.exists() or not path.exists():raise Denied('First-login link is unavailable or already used')
                record=json.loads(path.read_text())
                if time.monotonic()>record['expires_boot_s'] or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),record['token_sha256']):
                    raise Denied('First-login link is invalid or expired')
                user=next((u for u in self.accounts.interactive() if u['name']==record['user'] and u['administrator']),None)
                if not user:raise Denied('Provisioned administrator required')
                grant=secrets.token_urlsafe(32)
                self.bootstrap_grants={hashlib.sha256(grant.encode()).hexdigest():{'user':user['name'],'expires':time.monotonic()+600}}
                path.unlink()
                try:(Path(pwd.getpwnam(user['name']).pw_dir)/'.airlunix-web-first-login').unlink(missing_ok=True)
                except KeyError:pass
                self.log(user['name'],op,True)
                return {**user,'first_login':True,'setup_grant':grant}
        if op=='first_password':
            grant=request.get('setup_grant')
            if not isinstance(grant,str):raise Denied('Fresh first-login authorization required')
            key=hashlib.sha256(grant.encode()).hexdigest()
            with self.lock:
                record=self.bootstrap_grants.get(key)
                if not record or record['user']!=request.get('user') or time.monotonic()>record['expires'] or self.first_marker.exists():
                    raise Denied('First-login authorization expired or was already used')
                if not any(u['name']==record['user'] and u['administrator'] for u in self.accounts.interactive()):
                    raise Denied('Provisioned administrator required')
                with storage_lock(self.state/'storage.lock'):
                    self.accounts.change(record['user'],request.get('new_password'))
                    self.first_marker.parent.mkdir(parents=True,exist_ok=True)
                    self.first_marker.write_text('Password chosen after SSH-authenticated browser pairing\n');self.first_marker.chmod(0o600)
                self.bootstrap_grants.pop(key)
                self.log(record['user'],op,True)
                return {'success':True,'applied_in':'RAM','saved':False,'password_setup_complete':True}
        if op=='login':
            user=self.authenticate(request.get('user'),request.get('password'))
            self.log(user['name'],'login',True);return user
        if op not in ('users','save_status','password','create_user','save','storage','storage_preview','storage_apply'):
            raise ValueError('Unsupported operation')
        # All mutations require fresh system-password authentication. No bearer
        # token obtained by compromising the unprivileged daemon grants root.
        if op in ('password','create_user','save','storage_preview','storage_apply'):
            user=self.authenticate(request.get('user'),request.get('password'))
            if op!='password' and not user['administrator']:raise Denied('Administrator authentication required')
        else:
            user=next((u for u in self.accounts.interactive() if u['name']==request.get('user')),None)
            if not user:raise Denied('Interactive account required')
        name=user['name']
        if op=='users':return self.accounts.interactive() if user['administrator'] else [user]
        if op=='audit':return list(self.audit) if user['administrator'] else []
        if op=='save_status':
            return {'unsaved_changes':not hmac.compare_digest(self.fingerprint(),self.baseline),
                    'last_successful_save':self.last_save,'sd_mounted':self.mounted(),
                    'categories':['Device identity','Administrator keys','Accounts and passwords',
                                  'Selected configuration, including console TLS settings','Selected data']}
        if op=='password':
            with storage_lock(self.state/'storage.lock'):self.accounts.change(name,request.get('new_password'))
            self.log(name,op,True);return {'success':True,'applied_in':'RAM','saved':False}
        if op=='create_user':
            with storage_lock(self.state/'storage.lock'):self.accounts.create(request.get('name'),request.get('new_password'))
            self.log(name,op,True);return {'success':True,'administrator':False,'applied_in':'RAM','saved':False}
        if op=='save':
            result=self.persist()
            if not result.get('success') or not result.get('sd_unmounted'):raise StorageError('Save did not finish with SD unmounted')
            self.baseline=self.fingerprint();self.last_save={'unix_s':time.time(),'boot_s':time.monotonic()}
            (self.state/'saved-fingerprint').write_text(self.baseline)
            (self.state/'last-save.json').write_text(json.dumps(self.last_save))
            self.log(name,op,True);return result
        if op=='storage':
            # Monitoring never mounts or rereads the SD. Kernel-maintained
            # boundaries/counters and a boot-time filesystem snapshot are used.
            try:return {**json.loads(Path('/run/airlunix-storage.json').read_text()),'mounted':self.mounted()}
            except FileNotFoundError:return {'available':False,'reason':'Boot-time storage cache unavailable; explicit preview required to inspect media'}
        media=self.media or Media()
        if op=='storage_preview':
            with storage_lock(self.state/'storage.lock'):
                media.check_idle();layout=media.inspect();preview=plan_for(media,layout,request)
            token=secrets.token_urlsafe(24)
            with self.lock:
                self.plans={k:v for k,v in self.plans.items() if time.monotonic()<v['expires']}
                if len(self.plans)>=16:raise StorageError('Too many pending previews; wait for expiry')
                self.plans[token]={'user':name,'preview':preview,'expires':time.monotonic()+120}
            return {'token':token,'target':str(media.disk),'identity':layout['identity'],
                    'confirmation':media.disk.name,'preview':preview,'durable_immediately':True}
        with self.lock:record=self.plans.pop(request.get('token'),None)
        if not record or record['user']!=name or time.monotonic()>record['expires']:
            raise StorageError('Preview expired or was already used')
        if request.get('confirmation')!=media.disk.name:raise StorageError('Target confirmation does not match')
        with storage_lock(self.state/'storage.lock'):result=media.execute(record['preview'])
        result['durable_immediately']=True;self.log(name,op,result.get('success',False));return result

def plan_for(media,layout,request):
    from .storage import plan
    result=plan(layout,request.get('action'),request.get('size_mib'))
    result['device']=str(media.disk)
    return result

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        _,uid,_=struct.unpack('3i',self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if uid not in (0,self.server.allowed_uid):
            emit('security','helper_peer_denied',False);return
        line=self.rfile.readline(16385)
        if len(line)>16384:
            emit('security','helper_body_limit',False);return
        try:
            request=json.loads(line)
            if not isinstance(request,dict):raise ValueError('Object required')
            result={'ok':True,'result':self.server.admin.call(request)}
        except Denied as e:
            emit('security','helper_denied',False);result={'ok':False,'code':403,'error':str(e)}
        except (ValueError,StorageError) as e:
            emit('helper','rpc_rejected',False,reason=type(e).__name__);result={'ok':False,'code':409,'error':str(e)}
        except Exception as e:
            emit('helper','rpc_failed',False,reason=type(e).__name__);result={'ok':False,'code':500,'error':'Operation failed; inspect via authenticated SSH. Check SD mount state before removal.'}
        self.wfile.write(json.dumps(result).encode()+b'\n')

class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    def __init__(self,path,admin,allowed_uid):
        self.admin=admin;self.allowed_uid=allowed_uid;self.slots=threading.BoundedSemaphore(4)
        super().__init__(path,Handler)
    def process_request(self,request,address):
        if not self.slots.acquire(False):
            emit('security','helper_capacity',False);request.close();return
        super().process_request(request,address)
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit('Privileged helper requires root')
    install_output('helper')
    collector=Collector().start()
    user=pwd.getpwnam('airweb');directory=Path('/run/airlunix-admin')
    directory.mkdir(mode=0o750,exist_ok=True);os.chown(directory,0,user.pw_gid)
    path=directory/'control.sock'
    if path.exists():path.unlink()
    admin=Admin();admin.log_collector=collector
    with Server(str(path),admin,user.pw_uid) as server:
        os.chown(path,0,user.pw_gid);path.chmod(0o660);server.serve_forever()
