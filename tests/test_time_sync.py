import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('airlunix_time', Path(__file__).parents[1] / 'configs/ram/airlunix_time.py')
ntp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ntp)

class TimeSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.config = {'timeout_s': 0.2, 'success_interval_s': 86400,
                       'retry_s': [60, 300, 900, 3600, 21600],
                       'network_event_min_interval_s': 60}
        self.now = 10

    def tearDown(self):
        self.tmp.cleanup()

    def dispatch(self, success=False, event=False, conflict=False):
        return ntp.dispatch(self.config, self.directory, event=event,
                            clock=lambda: self.now,
                            runner=lambda c,d: {'success': success},
                            conflict=lambda: conflict)

    def test_success_daily_and_restart(self):
        state = self.dispatch(True)
        self.assertEqual(state['next_due_boot_s'], 86410)
        self.now = 86409
        self.assertEqual(self.dispatch(True)['skipped'], 'not due')
        # New invocation reloads saved RAM state; daily interval is boot-relative.
        self.now = 86410
        self.assertTrue(self.dispatch(True)['last_attempt_success'])

    def test_backoff_caps_and_network_recovery(self):
        for delay in [60, 300, 900, 3600, 21600, 21600, 21600]:
            result = self.dispatch(False)
            self.assertEqual(result['next_due_boot_s'] - self.now, delay)
            self.now = result['next_due_boot_s']
        self.now -= 21540
        self.assertTrue(self.dispatch(True, event=True)['last_attempt_success'])

    def test_network_events_throttled(self):
        self.dispatch(False)
        self.now += 5
        self.assertEqual(self.dispatch(True, event=True)['skipped'], 'not due')

    def test_failure_preserves_success_and_age_reference(self):
        self.dispatch(True)
        self.now += 86400
        state = self.dispatch(False)
        self.assertTrue(state['ever_synchronized_this_boot'])
        self.assertFalse(state['last_attempt_success'])
        self.assertEqual(state['last_success_boot_s'], 10)

    def test_overlap(self):
        with (self.directory / 'lock').open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.dispatch()['skipped'], 'attempt already running')

    def test_competing_client_rejected(self):
        state = self.dispatch(True, conflict=True)
        self.assertFalse(state['last_attempt_success'])
        self.assertIn('competing', state['last_result']['error'])

    def test_fresh_boot_cannot_inherit_time_trust(self):
        state = self.dispatch(True)
        state['boot_id'] = 'different-boot'
        ntp.write_state(self.directory, state)
        self.assertFalse(ntp.load_state(self.directory)['ever_synchronized_this_boot'])

    def test_process_timeout_and_exit_semantics_without_setting_clock(self):
        user = types.SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid())
        with patch.object(ntp.pwd, 'getpwnam', return_value=user):
            result = ntp.run_client(self.config, self.directory,
                                    [sys.executable, '-c', 'import time; time.sleep(10)'])
            self.assertTrue(result['timed_out'])
            self.assertFalse(result['success'])
            self.assertLess(result['duration_s'], 4)
            result = ntp.run_client(self.config, self.directory,
                                    [sys.executable, '-c', 'raise SystemExit(7)'])
            self.assertFalse(result['success'])
            result = ntp.run_client(self.config, self.directory,
                                    [sys.executable, '-c', 'raise SystemExit(0)'])
            self.assertTrue(result['success'])

if __name__ == '__main__':
    unittest.main()
