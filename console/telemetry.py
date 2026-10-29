"""One shared on-demand sampler; bounded history, no background collector."""
import collections
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import threading
import time

class Sampler:
    def __init__(self,interval=3,redact=False,release=None):
        self.interval=max(2,min(60,interval));self.redact=redact;self.release=release
        self.lock=threading.Lock();self.previous=None;self.cached=None
        self.history=collections.deque(maxlen=120)

    def sample(self):
        with self.lock:
            now=time.monotonic()
            if self.cached and now-self.cached['sampled_monotonic']<self.interval:return self.cached
            def text(path):
                try:return Path(path).read_text().strip()
                except OSError:return None
            cpu=list(map(int,Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
            memory={}
            for line in Path('/proc/meminfo').read_text().splitlines():
                key,value=line.split(':',1);memory[key]=int(value.split()[0])*1024
            total=sum(cpu);idle=cpu[3]+cpu[4];util=None
            if self.previous and total>self.previous['total']:
                util=round(100*(1-(idle-self.previous['idle'])/(total-self.previous['total'])),1)
            networks=[]
            try:
                result=subprocess.run(['ip','-o','addr','show','scope','global'],capture_output=True,text=True,timeout=1)
                addresses=result.stdout.splitlines() if result.returncode==0 else []
            except (OSError,subprocess.TimeoutExpired):addresses=[]
            for interface in Path('/sys/class/net').iterdir():
                if interface.name=='lo':continue
                rraw=text(interface/'statistics/rx_bytes');traw=text(interface/'statistics/tx_bytes')
                rx=int(rraw) if rraw is not None else None;tx=int(traw) if traw is not None else None
                old=self.previous['net'].get(interface.name) if self.previous else None
                dt=now-self.previous['time'] if self.previous else None
                networks.append({'name':interface.name,'link':text(interface/'operstate'),
                                 'addresses':['Hidden in privacy mode'] if self.redact else
                                 [x.split(' inet',1)[-1].strip() for x in addresses if x.split()[1]==interface.name],
                                 'rx_bytes':rx,'tx_bytes':tx,
                                 'rx_rate':max(0,(rx-old[0])/dt) if old and dt and rx is not None and old[0] is not None else None,
                                 'tx_rate':max(0,(tx-old[1])/dt) if old and dt and tx is not None and old[1] is not None else None})
            sensors=[]
            for z in Path('/sys/class/thermal').glob('thermal_zone*'):
                value=text(z/'temp')
                if value is not None:
                    try:sensors.append({'name':text(z/'type') or z.name,'celsius':round(int(value)/1000,1)})
                    except ValueError:pass
            frequencies=[]
            for p in Path('/sys/devices/system/cpu/cpufreq').glob('policy*'):
                value=text(p/'scaling_cur_freq')
                if value and value.isdecimal():frequencies.append({'policy':p.name,'mhz':int(value)/1000})
            disks=[]
            for p in Path('/sys/block').iterdir():
                if p.name.startswith(('loop','ram','zram')):continue
                raw=text(p/'stat');size=text(p/'size')
                if raw and size:
                    values=list(map(int,raw.split()))
                    disks.append({'name':p.name,'bytes':int(size)*512,'read_bytes':values[2]*512,'write_bytes':values[6]*512})
            mounts=[{'source':x.split()[0],'target':x.split()[1],'type':x.split()[2],'options':x.split()[3]}
                    for x in Path('/proc/mounts').read_text().splitlines()]
            board=text('/proc/device-tree/model')
            boot=text('/run/airlunix-boot.json');ntp=text('/run/airlunix-time/state.json')
            try:boot=json.loads(boot) if boot else None
            except ValueError:boot=None
            try:ntp=json.loads(ntp) if ntp else None
            except ValueError:ntp=None
            boot_seconds=float(Path('/proc/uptime').read_text().split()[0])
            if ntp and ntp.get('last_success_boot_s') is not None:ntp['last_success_age_s']=max(0,boot_seconds-ntp['last_success_boot_s'])
            rss=int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
            self.history.append({'t':now,'cpu':util,'available':memory.get('MemAvailable'),
                                 'rx':sum(x['rx_rate'] or 0 for x in networks) if self.previous else None,
                                 'tx':sum(x['tx_rate'] or 0 for x in networks) if self.previous else None})
            self.cached={'sampled_monotonic':now,'release':self.release or text('/etc/airlunix-release') or 'Airlunix · build unavailable',
                         'hardware':board.rstrip('\0') if board else 'Host validation · '+platform.machine(),
                         'uptime_s':boot_seconds,'cpu_percent':util,'load':list(os.getloadavg()),
                         'frequency':frequencies,'temperatures':sensors,
                         'memory':{'total':memory.get('MemTotal'),'available':memory.get('MemAvailable'),
                                   'cache':memory.get('Cached',0)+memory.get('SReclaimable',0),
                                   'buffers':memory.get('Buffers'),'shared':memory.get('Shmem')},
                         'network':networks,'disks':disks,
                         'mounts':mounts if not self.redact else [{'source':'Hidden','target':m['target'],'type':m['type']} for m in mounts if m['target'] in ('/','/run','/tmp')],
                         'sd_mounted':any(m['source'].startswith('/dev/mmc') for m in mounts),
                         'ram_resident':bool(text('/run/airlunix-residency')) and not any(m['source'].startswith('/dev/mmc') for m in mounts),
                         'time':ntp,'boot':boot,'console':{'rss_bytes':rss,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                                                    'sampler_interval_s':self.interval,'history_limit':120},
                         'history':list(self.history)}
            self.previous={'time':now,'total':total,'idle':idle,'net':{x['name']:(x['rx_bytes'],x['tx_bytes']) for x in networks}}
            return self.cached
