"""Finite tool execution with continuously bounded diagnostic capture.

Only fixed local commands call this module. No shell or user-supplied command.
"""
import os
import select
import signal
import subprocess
import time
from .logging_ram import emit


def run(args, capture_output=True, timeout=120, check=False, text=False):
    process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,start_new_session=True)
    os.set_blocking(process.stdout.fileno(),False)
    tail=bytearray();dropped=0;started=time.monotonic()
    try:
        while True:
            if time.monotonic()-started>=timeout:
                emit('administration','tool_timeout',False)
                raise subprocess.TimeoutExpired(args,timeout)
            chunk=None
            ready,_,_=select.select([process.stdout],[],[],.05)
            if ready:
                for _ in range(4):
                    try:chunk=os.read(process.stdout.fileno(),4096)
                    except BlockingIOError:break
                    if not chunk:break
                    tail.extend(chunk)
                    if len(tail)>16384:dropped+=len(tail)-16384;del tail[:-16384]
                time.sleep(.01)
            if process.poll() is not None:
                if not ready or not chunk:break
        code=process.wait(timeout=1)
        output=tail.decode(errors='replace') if text else bytes(tail)
        if code:emit('helper','tool_failed',False,reason=str(code),operation=os.path.basename(args[0]),message=tail.decode(errors='replace')[-768:])
        if dropped:emit('administration','tool_output_truncated',operation=str(dropped))
        if check and code:raise subprocess.CalledProcessError(code,args,output=output)
        return subprocess.CompletedProcess(args,code,stdout=output,stderr='' if text else b'')
    finally:
        if process.poll() is None:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:process.wait(timeout=1)
            except subprocess.TimeoutExpired:pass
        process.stdout.close()
