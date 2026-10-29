#!/usr/bin/env python3
"""Run on target; stream JSON to SSH or store under /run, never on SD."""
import argparse
import datetime
import json
from pathlib import Path
import time

p = argparse.ArgumentParser()
p.add_argument('--device', default='mmcblk1')
p.add_argument('--seconds', type=int, default=60)
p.add_argument('--interval', type=int, default=60)
args = p.parse_args()
if not args.device.isalnum() or args.seconds < 0 or args.interval <= 0:
    p.error('Invalid device or duration')
start = time.monotonic()
initial = None
while True:
    values = list(map(int, Path('/sys/block', args.device, 'stat').read_text().split()))
    if initial is None:
        initial = values
    record = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      'elapsed_s': round(time.monotonic() - start, 3),
                      'uptime': Path('/proc/uptime').read_text().strip(),
                      'stat': values,
                      'read_bytes_delta': (values[2] - initial[2]) * 512,
                      'write_bytes_delta': (values[6] - initial[6]) * 512}
    state = Path('/run/airlunix-time/state.json')
    if state.exists():
        record['time_sync'] = json.loads(state.read_text())
    print(json.dumps(record), flush=True)
    remaining = args.seconds - (time.monotonic() - start)
    if remaining <= 0:
        break
    time.sleep(min(args.interval, remaining))
