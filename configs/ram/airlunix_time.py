"""Bounded one-shot NTP dispatch; existing crond performs scheduling."""
import fcntl
import json
import os
import pwd
from pathlib import Path
import signal
import subprocess
import sys
import time

def boot_seconds():
    return time.clock_gettime(time.CLOCK_BOOTTIME)

def load_state(directory):
    try:
        state = json.loads((directory / 'state.json').read_text())
        if state.get('boot_id') == Path('/proc/sys/kernel/random/boot_id').read_text().strip():
            return state
    except (FileNotFoundError, ValueError):
        pass
    return {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'ever_synchronized_this_boot': False, 'failures': 0, 'next_due_boot_s': 0}

def write_state(directory, state):
    tmp = directory / 'state.json.new'
    tmp.write_text(json.dumps(state, sort_keys=True) + '\n')
    tmp.chmod(0o644)
    tmp.replace(directory / 'state.json')

def competing_clients():
    for p in Path('/proc').glob('[0-9]*/comm'):
        try:
            if p.read_text().strip() in ('chronyd', 'ntpd'):
                return True
        except (FileNotFoundError, PermissionError):
            pass
    return False

def client_rss(pgid):
    total = 0
    for p in Path('/proc').glob('[0-9]*/stat'):
        try:
            # After final ')': state, ppid, pgrp, ... rss (field 24).
            data = p.read_text().rsplit(')', 1)[1].split()
            if int(data[2]) == pgid:
                total += int(data[21]) * os.sysconf('SC_PAGE_SIZE') // 1024
        except (FileNotFoundError, PermissionError, ValueError, IndexError):
            pass
    return total

def run_client(config, directory, command=None):
    started = time.monotonic()
    client_dir = directory / 'client'
    client_dir.mkdir(mode=0o750, exist_ok=True)
    user = pwd.getpwnam('chrony')
    os.chown(client_dir, user.pw_uid, user.pw_gid)
    command = command or ['/usr/sbin/chronyd', '-q', '-d', '-t', str(config['timeout_s']),
                          '-f', '/etc/airlunix/time-chrony.conf']
    peak = 0
    timed_out = False
    log = directory / 'last-client.log'
    with log.open('wb') as output:
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)
        while proc.poll() is None:
            peak = max(peak, client_rss(proc.pid))
            if time.monotonic() - started >= config['timeout_s']:
                timed_out = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                break
            time.sleep(0.05)
        code = proc.wait()
    # Bound stored diagnostic output; no file leaves /run.
    if log.stat().st_size > 16384:
        log.write_bytes(log.read_bytes()[-16384:])
    return {'success': code == 0 and not timed_out, 'return_code': code,
            'timed_out': timed_out, 'duration_s': round(time.monotonic() - started, 3),
            'sampled_client_peak_rss_kib': peak, 'rss_sampling_interval_s': 0.05}

def dispatch(config, directory, event=False, clock=boot_seconds, runner=run_client,
             conflict=competing_clients):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'skipped': 'attempt already running'}
        state = load_state(directory)
        now = clock()
        event_retry = (event and not state.get('last_attempt_success', False) and
                       now - state.get('last_attempt_boot_s', -1000) >=
                       config['network_event_min_interval_s'])
        if now < state.get('next_due_boot_s', 0) and not event_retry:
            return {'skipped': 'not due', 'next_due_boot_s': state['next_due_boot_s']}
        state['last_attempt_boot_s'] = now
        state['last_attempt_success'] = False
        state['attempt_running'] = True
        write_state(directory, state)
        try:
            if conflict():
                result = {'success': False, 'error': 'competing synchronizer detected'}
            else:
                result = runner(config, directory)
        except Exception as exc:
            result = {'success': False, 'error': str(exc)}
        now = clock()
        state.update(last_attempt_success=result['success'], last_result=result,
                     last_attempt_finished_boot_s=now, attempt_running=False)
        if result['success']:
            state.setdefault('first_success_boot_s', now)
            state.update(ever_synchronized_this_boot=True, failures=0,
                         last_success_boot_s=now, last_success_unix_s=time.time(),
                         next_due_boot_s=now + config['success_interval_s'])
        else:
            state['failures'] += 1
            delay = config['retry_s'][min(state['failures'] - 1, len(config['retry_s']) - 1)]
            state['next_due_boot_s'] = now + delay
        write_state(directory, state)
        return state

def status(directory):
    state = load_state(directory)
    now = boot_seconds()
    state['last_success_age_s'] = (round(now - state['last_success_boot_s'], 3)
                                   if state.get('ever_synchronized_this_boot') else None)
    state['next_due_in_s'] = max(0, round(state['next_due_boot_s'] - now, 3))
    # An observed success is not a promise about current error or authenticated NTP.
    return state

if __name__ == '__main__':
    directory = Path('/run/airlunix-time')
    action = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if action in ('status', 'summary'):
        current = status(directory)
        if action == 'summary':
            print('observed_this_boot=%s last_attempt_success=%s age_s=%s' %
                  (current['ever_synchronized_this_boot'],
                   current.get('last_attempt_success', 'not attempted'),
                   current['last_success_age_s']))
        else:
            print(json.dumps(current, sort_keys=True))
    elif action in ('attempt', 'network'):
        if os.geteuid() != 0:
            sys.exit('Root required to adjust clock')
        config = json.loads(Path('/etc/airlunix/time.json').read_text())
        print(json.dumps(dispatch(config, directory, event=action == 'network'), sort_keys=True))
    else:
        sys.exit('Usage: airlunix-time [status|attempt|network]')
