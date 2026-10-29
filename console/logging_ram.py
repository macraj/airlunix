"""Bounded volatile diagnostics, hosted by the administration helper.

Emitters never wait for collection. No input path or caller-chosen filename.
The only retained files are fixed channels on the dedicated logging tmpfs.
"""
import collections
import ctypes
import gzip
import io
import json
import os
from pathlib import Path
import re
import selectors
import socket
import struct
import sys
import threading
import time

ROOT = Path('/run/airlunix-log')
CHANNELS = dict(system=1048576, kernel=1048576, security=1048576, service=524288,
                network=524288, ntp=524288, cron=262144, web=262144,
                helper=262144, administration=524288, health=262144)
MAX_RECORD = 2048
EVENTS = {'web','helper','service','network','ntp','cron','administration','security'}
SAFE = re.compile(r'[^a-zA-Z0-9_.:-]')
_local_drops = 0

def clean(value, limit=80):
    return SAFE.sub('_', str(value)[:limit])

def safe_actor(value):
    return value if isinstance(value,str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,30}',value) else ''

def emit(channel, event, success=True, actor='', reason='', operation='', message='', root=ROOT):
    """Best-effort, bounded, nonblocking. Never format arbitrary request bodies."""
    global _local_drops
    data = {'channel':channel, 'event':clean(event), 'success':bool(success),
            'actor':safe_actor(actor), 'reason':clean(reason), 'operation':clean(operation,32),
            'sender_drops':_local_drops}
    if channel in ('service','ntp','helper','network') and message:data['message']=sanitize(message)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM | socket.SOCK_NONBLOCK) as s:
            encoded=json.dumps(data,separators=(',',':')).encode()
            if len(encoded)>MAX_RECORD:
                data.pop('message',None);data['truncated']=True;encoded=json.dumps(data,separators=(',',':')).encode()
            s.sendto(encoded, str(root/'events.sock'))
        _local_drops=0
    except OSError:
        _local_drops=min(_local_drops+1, 2**63-1)
        # Fixed bounded early/fallback spool; never blocks operations on a reader.
        if os.geteuid()==0 and channel in ('service','administration','helper'):
            try:
                early=root/'early.log';encoded=(json.dumps(data)+'\n').encode()[:2048]
                if not early.exists() or early.stat().st_size+len(encoded)<=32768:
                    fd=os.open(early,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'wb') as f:f.write(encoded)
            except OSError:pass

class Output:
    """No blocking file descriptor or raw exception/request text in service logs."""
    encoding='utf-8'
    def __init__(self,channel):self.channel=channel
    def write(self,text):
        if text and text.strip():emit(self.channel,'process_output',reason='output_suppressed',operation=str(len(text)))
        return len(text)
    def flush(self):pass
    def isatty(self):return False

def install_output(channel):
    sys.stdout=Output(channel);sys.stderr=Output(channel)
    def failure(kind,value,tb):
        emit(channel,'uncaught_exception',False,reason=kind.__name__)
        # Frame names/line numbers, never exception values, locals or source lines.
        for _ in range(8):
            if tb is None:break
            emit(channel,'exception_frame',False,reason=tb.tb_frame.f_code.co_name,
                 operation=str(tb.tb_lineno));tb=tb.tb_next
    sys.excepthook=failure

def bound_datagrams(sock):
    # Unix SOCK_DGRAM SO_RCVBUF does not bound queued payload bytes. Reject
    # oversized frames in the kernel BEFORE they can occupy the receive queue.
    # Classic socket BPF uses existing Linux APIs; no eBPF loader/dependency.
    class Instruction(ctypes.Structure):
        _fields_=[('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint)]
    class Program(ctypes.Structure):
        _fields_=[('length',ctypes.c_ushort),('instructions',ctypes.POINTER(Instruction))]
    instructions=(Instruction*4)(Instruction(0x80,0,0,0),Instruction(0x25,1,0,MAX_RECORD),
                                  Instruction(0x06,0,0,0xffffffff),Instruction(0x06,0,0,0))
    program=Program(4,instructions)
    sock.setsockopt(socket.SOL_SOCKET,26,bytes(program))  # SO_ATTACH_FILTER

class Bucket:
    def __init__(self,rate,burst,now):self.rate=rate;self.burst=burst;self.tokens=float(burst);self.at=now
    def take(self,n,now):
        self.tokens=min(self.burst,self.tokens+max(0,now-self.at)*self.rate);self.at=now
        if n>self.tokens:return False
        self.tokens-=n;return True

class Store:
    def __init__(self,root=ROOT,quotas=None,clock=time.monotonic):
        self.root=Path(root);self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.quotas=quotas or CHANNELS;self.clock=clock;self.lock=threading.Lock()
        self.instance=os.urandom(8).hex();self.sequence=0;self.generation={}
        self.counts=collections.Counter();self.buckets={};self.repeats=collections.OrderedDict()
        self.boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.last_wall=time.time();self.last_mono=clock();self.last_health=clock();self.last_health_check=clock()
        self.low_memory=False
        self.global_record=Bucket(100,100,clock());self.global_bytes=Bucket(131072,131072,clock())
        self.worker_alive=lambda:None
        try:self.release=Path('/etc/airlunix-release').read_text()[:256]
        except OSError:self.release='isolated fixture'
        self.last_status={};self.read_slots=threading.BoundedSemaphore(2)
        for c in self.quotas:
            # Recovery reads a fixed tail, never a full file. Rename generations
            # remain on tmpfs across helper restarts, but not reboots.
            for suffix in ('.1',''):
                p=self.root/(c+'.jsonl'+suffix)
                if p.exists():
                    with p.open('rb') as f:
                        size=f.seek(0,2);f.seek(max(0,size-8192));tail=f.read(8192)
                    for line in tail.splitlines():
                        try:
                            r=json.loads(line);self.sequence=max(self.sequence,int(r.get('sequence',0)))
                        except (ValueError,TypeError):pass
                    if tail and not tail.endswith(b'\n'):
                        # Discard interrupted suffix; no forged complete record.
                        with p.open('r+b') as f:f.truncate(size-len(tail)+max(0,tail.rfind(b'\n')+1))
        self.append('health',{'event':'collector_started','success':True},'collector',force=True)

    def count(self,key,n=1):self.counts[key]=min(2**63-1,self.counts[key]+n)

    def append(self,channel,data,producer,force=False):
        if channel not in self.quotas:return False
        now=self.clock()
        if not self.lock.acquire(False):self.count('lock_drop');return False
        try:
            # Byte/rate limits by fixed channel + trusted service identity,
            # never caller-controlled arbitrary tags or PID churn.
            key=(channel,producer)
            if key not in self.buckets:
                if len(self.buckets)>=63:key=('system','overflow')
                if key not in self.buckets:
                    secure=channel in ('security','administration')
                    self.buckets[key]=(Bucket(5 if secure else 10,20 if secure else 40,now),Bucket(8192 if secure else 16384,16384 if secure else 32768,now))
            if self.low_memory and channel not in ('health','security','administration'):
                self.count('low_memory_drop');return False
            if not force:
                a,b=self.buckets[key]
                if not a.take(1,now) or not b.take(MAX_RECORD,now):self.count('rate_drop');return False
                if channel not in ('health','security','administration') and (not self.global_record.take(1,now) or not self.global_bytes.take(MAX_RECORD,now)):
                    self.count('global_rate_drop');return False
            if not force and channel not in ('security','administration','health'):
                repeat_key=(channel,producer,data.get('event'),data.get('message','')[:80])
                previous=self.repeats.get(repeat_key)
                if previous and now-previous[0]<10:
                    self.repeats[repeat_key]=(previous[0],previous[1]+1);self.count('repeat_suppressed');return False
                if previous and previous[1]:data={**data,'repeat_count':previous[1]}
                self.repeats[repeat_key]=(now,0);self.repeats.move_to_end(repeat_key)
                while len(self.repeats)>128:self.repeats.popitem(last=False)
            # Retain only fields created by normalizers, never request dictionaries.
            r={'schema':1,'boot_id':self.boot,'instance':self.instance,'sequence':self.sequence+1,
               'boot_s':round(time.clock_gettime(time.CLOCK_BOOTTIME),6),
               'monotonic_s':round(now,6),'wall_utc_s':time.time(),'time_confidence':self.time_confidence(),'last_sync_age_s':self.last_sync_age,
               'channel':channel,'producer':producer,'severity':data.get('severity','info'),**data}
            encoded=(json.dumps(r,ensure_ascii=True,separators=(',',':'))+'\n').encode()
            if len(encoded)>MAX_RECORD:
                r.pop('message',None);r['truncated']=True;self.count('truncated');encoded=(json.dumps(r,separators=(',',':'))+'\n').encode()
                if len(encoded)>MAX_RECORD:self.count('oversize_drop');return False
            limit=(self.quotas[channel]-(32768 if channel=='service' and self.quotas[channel]>32768 else 0))//2;p=self.root/(channel+'.jsonl');old=self.root/(channel+'.jsonl.1')
            size=p.stat().st_size if p.exists() else 0
            if size+len(encoded)>limit:
                old.unlink(missing_ok=True)
                if p.exists():p.rename(old)
                self.count('rotation');self.generation[channel]=self.generation.get(channel,0)+1
            fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb',buffering=0) as f:f.write(encoded)
            self.sequence+=1;return True
        except OSError:self.count('write_error');return False
        finally:self.lock.release()

    def time_confidence(self):
        self.last_sync_age=None
        try:
            p=Path('/run/airlunix-time/state.json')
            if p.stat().st_size>4096:return 'unsynchronized'
            s=json.loads(p.read_text())
            if s.get('boot_id')==self.boot and s.get('ever_synchronized_this_boot'):
                self.last_sync_age=max(0,round(time.clock_gettime(time.CLOCK_BOOTTIME)-s.get('last_success_boot_s',0),3))
                return 'observed-sync-this-boot'
        except (OSError,ValueError):pass
        return 'unsynchronized'

    def query(self,channel='security',cursor=None,limit=200,event='',severity=''):
        if channel not in self.quotas:raise ValueError('Unknown channel')
        if not self.read_slots.acquire(False):raise ValueError('Log reader limit')
        try:
            limit=max(1,min(200,int(limit)));records=[];scanned=0;gap=False;next_cursor=None;matched=cursor is None
            for suffix in ('','.1'):
                p=self.root/(channel+'.jsonl'+suffix)
                try:
                    with p.open('rb') as f:
                        inode=os.fstat(f.fileno()).st_ino;end=f.seek(0,2)
                        if cursor:
                            if cursor.get('inode')!=inode:continue
                            matched=True
                            end=min(end,max(0,int(cursor['offset'])))
                        start=max(0,end-(524288-scanned));f.seek(start);raw=f.read(end-start);scanned+=len(raw)
                    lines=raw.splitlines(keepends=True)
                    if start and lines:lines=lines[1:]
                    offset=start+len(raw)
                    for line in reversed(lines):
                        offset-=len(line)
                        try:r=json.loads(line)
                        except ValueError:continue
                        if event and r.get('event')!=event:continue
                        if severity and r.get('severity')!=severity:continue
                        records.append(r);next_cursor={'inode':inode,'offset':offset}
                        if len(records)>=limit or sum(len(json.dumps(x)) for x in records)>=245760:break
                    if records or scanned>=524288:
                        if not records:next_cursor={'inode':inode,'offset':start}
                        break
                    cursor=None
                except FileNotFoundError:continue
            if not matched:gap=True
            return {'records':records,'cursor':next_cursor,'gap':gap,'health':self.status(),'scanned_bytes':scanned}
        finally:self.read_slots.release()

    def status(self):
        sizes={}
        for c in self.quotas:
            sizes[c]=0
            for p in (self.root/(c+'.jsonl'),self.root/(c+'.jsonl.1')):
                try:sizes[c]+=p.stat().st_size
                except FileNotFoundError:pass
        return {'instance':self.instance,'boot_id':self.boot,'release':self.release,'sequence':self.sequence,
                'collection_alive':self.worker_alive(),'kernel_frame_limit_bytes':MAX_RECORD,'loss_counts_are_lower_bounds':True,'health_age_s':round(self.clock()-self.last_health_check,3),'counters':dict(self.counts),
                'sizes':sizes,'limits':self.quotas,'low_memory':self.low_memory,'volatile':True}

    def health(self):
        now=self.clock()
        if now-self.last_health_check<1:return
        self.last_health_check=now;wall=time.time()
        if abs((wall-self.last_wall)-(now-self.last_mono))>1:
            self.append('health',{'event':'clock_discontinuity','success':True},'collector',force=True)
        self.last_wall=wall;self.last_mono=now
        try:
            mem=Path('/proc/meminfo').read_text();available=int(re.search(r'MemAvailable:\s+(\d+)',mem)[1])*1024
            self.low_memory=available<128*1024*1024
        except (OSError,TypeError):pass
        if now-self.last_health>=60:
            self.last_health=now
            self.append('health',{'event':'loss_summary','counts':dict(self.counts),'success':True},'collector',force=True)

class Collector:
    def __init__(self,root=ROOT,syslog_path='/dev/log',kernel=True,web_uid=2000):
        self.store=Store(root);self.root=Path(root);self.selector=selectors.DefaultSelector()
        self.web_uid=web_uid;self.stop_event=threading.Event();self.sockets=[];self.kernel_fd=None;self.kernel_replay=True
        # Directory traversal permitted, contents private. Only socket is public.
        self.root.chmod(0o711)
        for name,kind in [(str(self.root/'events.sock'),'events'),(str(syslog_path),'syslog')]:
            Path(name).unlink(missing_ok=True)
            s=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM|socket.SOCK_NONBLOCK)
            s.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1);bound_datagrams(s);s.bind(name);os.chmod(name,0o666)
            self.selector.register(s,selectors.EVENT_READ,kind);self.sockets.append(s)
        if kernel:
            try:
                self.kernel_fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK)
                self.selector.register(self.kernel_fd,selectors.EVENT_READ,'kernel')
            except OSError:self.store.count('kernel_unavailable')
        self.last_service=0;self.service_states={}
        # Finite early-boot transcript, capped by the transient OpenRC adapter.
        early=self.root/'early.log'
        try:
            with early.open('rb') as f:initial=f.read(32768)
            for line in initial.splitlines():self.store.append('service',{'event':'early_boot_output','message':sanitize(line.decode(errors='replace'))},'boot',force=True)
            early.unlink()
        except OSError:pass
        self.thread=threading.Thread(target=self.run,name='ramlog',daemon=True)
        self.store.worker_alive=self.thread.is_alive

    def start(self):self.thread.start();return self
    def close(self):
        self.stop_event.set();self.thread.join(2)
        self.selector.close()
        for s in self.sockets:s.close()
        if self.kernel_fd is not None:os.close(self.kernel_fd)

    def ingest(self,raw,pid,uid,kind):
        if kind=='events':
            if uid not in (0,self.web_uid):self.store.count('unauthorized_sender');return
            try:
                r=json.loads(raw)
                if not isinstance(r,dict):raise ValueError()
                c=r.get('channel')
                if c not in EVENTS or uid!=0 and c not in ('web','security'):raise ValueError()
                record={k:clean(r.get(k,''),80) for k in ('event','actor','reason','operation')}
                if c in ('service','ntp','helper','network') and uid==0 and isinstance(r.get('message'),str):record['message']=sanitize(r['message'])
                if r.get('truncated') is True:self.store.count('input_truncated');record['truncated']=True
                record['actor']=safe_actor(r.get('actor'))
                record['success']=r.get('success') is True
                record['severity']='info' if record['success'] else 'warning'
                self.store.count('sender_reported_drop',min(2**31,max(0,int(r.get('sender_drops',0)))))
                self.store.append(c,record,'web' if uid else 'root-event')
            except (ValueError,TypeError,AttributeError):self.store.count('malformed')
            return
        try:exe=Path(os.readlink('/proc/%d/exe'%pid)).name
        except OSError:exe='exited'
        text=raw.decode(errors='replace')[:2048]
        # Credentials, not claimed tags, decide security admission. Never retain
        # arbitrary doas command arguments/cwd or unparseable auth text.
        pri=re.match(r'<(\d{1,3})>',text)
        auth=bool(pri and int(pri[1])//8 in (4,10))
        if uid==0 and (auth or exe in ('sshd','sshd-session','doas')):
            event='authentication_event'
            for needle,label in [('Accepted ','ssh_accepted'),('Failed ','ssh_failed'),('Disconnected','ssh_disconnected'),('session opened','session_opened'),('session closed','session_closed'),('command not permitted','elevation_denied'),('ran command','elevation_allowed'),('authentication failed','authentication_failed')]:
                if needle in text:event=label;break
            actor_match=re.search(r'(?:for (?:invalid user )?|doas: )([a-z][a-z0-9_-]{0,30})(?: |$)',text)
            actor=actor_match[1] if actor_match else ''
            self.store.append('security',{'event':event,'actor':actor,'success':event in ('ssh_accepted','elevation_allowed','session_opened','session_closed')},exe if exe in ('sshd','sshd-session','doas') else 'auth-syslog')
        elif uid==0 and ('udhcpc' in text or exe=='udhcpc'):
            self.store.append('network',{'event':'dhcp_output','message':sanitize(text)},'dhcp')
        elif uid==0 and ('crond' in text or exe=='crond'):
            if 'airlunix-time attempt' in text:self.store.count('cron_routine');return
            self.store.append('cron',{'event':'cron_output','message':sanitize(text)},'cron')
        elif uid==0:self.store.append('system',{'event':'system_output','message':'Unclassified producer output omitted','severity':'warning'},'root-syslog')
        else:self.store.count('untrusted_syslog_drop')

    def run(self):
        while not self.stop_event.is_set():
            try:
                for key,_ in self.selector.select(1):
                    for _ in range(2):
                        try:
                            if key.data=='kernel':
                                raw=os.read(key.fileobj,4096)
                                if not raw:break
                                # Kernel sequence/time survive independently of wall time.
                                head,_,msg=raw.partition(b';')
                                if head.split(b',')[0].isdigit() and int(head.split(b',')[0])%8==7:continue
                                self.store.append('kernel',{'event':'kernel_message','replayed':self.kernel_replay,'kernel_header':head.decode(errors='replace')[:96],'message':sanitize(msg.decode(errors='replace'))},'kernel')
                            else:
                                raw,anc,flags,_=key.fileobj.recvmsg(2048,socket.CMSG_SPACE(12))
                                if flags&socket.MSG_TRUNC:self.store.count('input_truncated')
                                cred=next((data for level,typ,data in anc if level==socket.SOL_SOCKET and typ==socket.SCM_CREDENTIALS),None)
                                if cred is None:self.store.count('no_credentials');continue
                                pid,uid,gid=struct.unpack('3i',cred[:12]);self.ingest(raw,pid,uid,key.data)
                        except BlockingIOError:
                            if key.data=='kernel':self.kernel_replay=False
                            break
                        except OSError:self.store.count('read_error');break
                        except Exception:self.store.count('parser_error')
                self.store.health()
                if time.monotonic()-self.last_service>=5:
                    self.last_service=time.monotonic()
                    for service in ('airlunix-web','airlunix-admin','sshd','crond'):
                        try:
                            pid=int(Path('/run/'+service+'.pid').read_text().strip());alive=Path('/proc/'+str(pid)).exists()
                        except (OSError,ValueError):alive=False
                        if self.service_states.get(service)!=alive:
                            self.service_states[service]=alive
                            self.store.append('service',{'event':'service_state','service':service,'success':alive},'lifecycle')
                # Bound flood drain work; producers use nonblocking datagrams.
                self.stop_event.wait(.05)
            except Exception:
                self.store.count('worker_error');self.stop_event.wait(.1)

def sanitize(text):
    text=re.sub(r'[\x00-\x1f\x7f]',' ',text[:1024])
    text=re.sub(r'(?i)(password|token|cookie|authorization|secret|hash|key)[=: ]+\S+',r'\1=[redacted]',text)
    return text[:768]

def main():
    # Fixed CLI events only. No paths, passwords, arguments or raw bodies.
    if len(sys.argv)==4:emit(sys.argv[1],sys.argv[2],sys.argv[3]=='ok')

if __name__=='__main__':main()
