#!/usr/bin/env python3
"""Finite on-board test; synthetic events, no configuration/storage changes."""
import json
import os
from pathlib import Path
import time
from airlunix.logging_ram import emit

P=Path
TARGET=P('/run/logging-hardware-measure.json')
PHASES=[('idle',300,0),('normal',600,2),('noisy',600,2000)]

def stats():
    processes={}
    for name in ('airlunix-admin','airlunix-web'):
        pid=int(P('/run/'+name+'.pid').read_text().strip())
        data=P('/proc/'+str(pid)+'/stat').read_text().rsplit(')',1)[1].split()
        processes[name]={'pid':pid,'ticks':int(data[11])+int(data[12]),'rss':int(data[21])*os.sysconf('SC_PAGE_SIZE')}
    root=P('/run/airlunix-log');v=os.statvfs(root)
    return {'monotonic':time.monotonic(),'processes':processes,
            'log_payload':sum(p.stat().st_size for p in root.glob('*.jsonl*')),
            'log_allocated':(v.f_blocks-v.f_bfree)*v.f_frsize,
            'sd':list(map(int,P('/sys/block/mmcblk1/stat').read_text().split()))}

def save(result):
    tmp=TARGET.with_suffix('.new');tmp.write_text(json.dumps(result,indent=2));tmp.chmod(0o600);tmp.replace(TARGET)

result={'release':P('/etc/airlunix-release').read_text(),'phases':[],'complete':False}
try:
    for name,duration,rate in PHASES:
        before=stats();started=time.monotonic();peak={k:v['rss'] for k,v in before['processes'].items()};sent=0;maxpayload=0;maxallocated=0
        result['active_phase']=name;save(result)
        while time.monotonic()-started<duration:
            batch=100 if rate>100 else rate
            for i in range(batch):
                emit(('web','security','administration','network','ntp','helper','service')[sent%7],
                     'synthetic_volume_'+str(sent%10000),reason='controlled_test',operation=str(sent))
                sent+=1
            snapshot=stats();maxpayload=max(maxpayload,snapshot['log_payload']);maxallocated=max(maxallocated,snapshot['log_allocated'])
            for k,v in snapshot['processes'].items():peak[k]=max(peak[k],v['rss'])
            time.sleep(.05 if rate>100 else 1)
        after=stats();elapsed=after['monotonic']-before['monotonic']
        result['phases'].append({'name':name,'elapsed_s':elapsed,'synthetic_send_calls':sent,'before':before,'after':after,
            'peak_rss':peak,'max_log_payload':maxpayload,'max_log_allocated':maxallocated,
            'cpu_percent_one_core':{k:100*(after['processes'][k]['ticks']-v['ticks'])/os.sysconf('SC_CLK_TCK')/elapsed for k,v in before['processes'].items()}})
        save(result)
    result['complete']=True;result.pop('active_phase',None)
except Exception as exc:
    result['error']=type(exc).__name__
finally:save(result)
