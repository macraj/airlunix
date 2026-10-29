"""Boot-only SD inspection while already mounted read-only; never a collector."""
import json
import os
from pathlib import Path
import time
from .storage import Media

def main():
    layout=Media().inspect()
    info=os.statvfs('/state')
    layout.update(available=True,measured_boot_s=time.monotonic(),
                  filesystem_capacity_bytes=info.f_blocks*info.f_frsize,
                  free_bytes=info.f_bavail*info.f_frsize,
                  filesystem_measurement='Boot snapshot; explicit operations may change capacity')
    Path('/run/airlunix-storage.json').write_text(json.dumps(layout))

if __name__=='__main__':main()
