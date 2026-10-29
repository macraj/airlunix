"""Measure the isolated host preview process, not the physical board."""
import concurrent.futures
import http.client
import json
import os
from pathlib import Path
import ssl
import time

fixture=json.loads(Path('/tmp/airlunix-console-preview/fixture.json').read_text())
port=int(fixture['url'].rsplit(':',1)[1])
pid=next(int(p.name) for p in Path('/proc').iterdir() if p.name.isdecimal()
         and b'tests/preview_console.py\0' in (p/'cmdline').read_bytes())
def counters():
    fields=Path(f'/proc/{pid}/stat').read_text().split()
    io=dict(x.split(': ') for x in Path(f'/proc/{pid}/io').read_text().splitlines())
    return {'cpu_s':(int(fields[13])+int(fields[14]))/os.sysconf('SC_CLK_TCK'),
            'rss_bytes':int(fields[23])*os.sysconf('SC_PAGE_SIZE'),'write_bytes':int(io['write_bytes'])}
def request(path,body=None,cookie=None):
    connection=http.client.HTTPSConnection('127.0.0.1',port,context=ssl._create_unverified_context(),timeout=5)
    headers={'Origin':fixture['url'],'Content-Type':'application/json'}
    if cookie:headers['Cookie']=cookie
    connection.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers)
    result=connection.getresponse();data=json.loads(result.read());cookie=result.getheader('Set-Cookie');connection.close()
    if result.status!=200:raise RuntimeError('Unexpected HTTP status '+str(result.status))
    return data,cookie
_,cookie=request('/api/login',{'user':fixture['user'],'password':fixture['password']})
def phase(active):
    before=counters();start=time.monotonic();requests=0;samples=set();peak=before['rss_bytes']
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        while time.monotonic()-start<10:
            if active:
                results=list(pool.map(lambda _:request('/api/overview',cookie=cookie)[0],range(5)))
                samples.update(d['sampled_monotonic'] for d in results);requests+=5
            peak=max(peak,counters()['rss_bytes']);time.sleep(0.5)
    after=counters();elapsed=time.monotonic()-start
    return {'duration_s':round(elapsed,3),'process_cpu_percent_one_core':round((after['cpu_s']-before['cpu_s'])/elapsed*100,3),
            'rss_before_bytes':before['rss_bytes'],'peak_sampled_rss_bytes':peak,'rss_after_bytes':after['rss_bytes'],
            'process_write_bytes_delta':after['write_bytes']-before['write_bytes'],'requests':requests,'distinct_shared_samples':len(samples)}
result={'environment':'x86_64 build host; HTTPS fixture with real privacy-filtered host telemetry; no privileged production helper',
        'idle':phase(False),'five_concurrent_clients':phase(True),'physical_board_measurement':False}
target=Path(__file__).resolve().parents[1]/'docs/console-host-resources.json'
target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
