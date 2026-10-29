"""Focused isolated tests for RAM quotas, restarts, malformed input and grants."""
from test_console import *
from airlunix.logging_ram import Store, Collector, emit, CHANNELS
import concurrent.futures
import socket
import os

class LoggingTests(unittest.TestCase):
    def test_channel_rotation_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d,quotas={'health':4096,'system':4096})
            for i in range(100):store.append('system',{'event':'failure','operation':str(i)},'fixture',force=True)
            self.assertLessEqual(store.status()['sizes']['system'],4096)
            self.assertGreater(store.counts['rotation'],0)
            sequence=store.sequence
            second=Store(d,quotas={'health':4096,'system':4096})
            self.assertGreater(second.sequence,sequence)
            self.assertTrue(second.query('system')['records'])
            self.assertEqual(sum(CHANNELS.values()),6*1024*1024)
    def test_nonblocking_unavailable_and_malformed(self):
        with tempfile.TemporaryDirectory(prefix='logtest-') as d:
            root=Path(d);collector=Collector(root,syslog_path=root/'syslog',kernel=False,web_uid=os.getuid()).start()
            try:
                for raw in (b'{',b'[]',b'null',b'"x"',b'{"channel":"../../etc"}'):
                    collector.ingest(raw,os.getpid(),os.getuid(),'events')
                self.assertGreaterEqual(collector.store.counts['malformed'],5)
                # Collector not draining: emitter must still return promptly.
                collector.stop_event.set();collector.thread.join(2)
                started=time.monotonic()
                for _ in range(2000):emit('web','test',root=root)
                self.assertLess(time.monotonic()-started,2)
            finally:collector.close()
            started=time.monotonic()
            for _ in range(100):emit('web','test',root=root/'absent')
            self.assertLess(time.monotonic()-started,1)
    def test_bounded_tool_output_and_timeout(self):
        from airlunix.process import run
        r=run([sys.executable,'-c','import os;os.write(1,b"x"*200000)'],timeout=3)
        self.assertEqual(r.returncode,0);self.assertLessEqual(len(r.stdout),16384)
        started=time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            run([sys.executable,'-c','import os; b=b"x"*4096;\nwhile True: os.write(1,b)'],timeout=.2)
        self.assertLess(time.monotonic()-started,2)
    def test_low_memory_enospc_and_reader_limits(self):
        import errno
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            store=Store(d);store.low_memory=True
            self.assertFalse(store.append('web',{'event':'diagnostic'},'fixture'))
            self.assertTrue(store.append('security',{'event':'authentication'},'fixture'))
            with patch('airlunix.logging_ram.os.open',side_effect=OSError(errno.ENOSPC,'fixture full')):
                self.assertFalse(store.append('administration',{'event':'failed_save'},'fixture'))
            self.assertEqual(store.counts['write_error'],1)
            self.assertTrue(store.read_slots.acquire(False));self.assertTrue(store.read_slots.acquire(False))
            with self.assertRaises(ValueError):store.query()
            store.read_slots.release();store.read_slots.release()
    def test_partial_record_recovery_and_clock_step(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            now=[0.0];store=Store(d,clock=lambda:now[0])
            store.append('service',{'event':'before_failure'},'fixture',force=True)
            with (Path(d)/'service.jsonl').open('ab') as f:f.write(b'{"partial":')
            restored=Store(d,clock=lambda:now[0])
            self.assertTrue(restored.query('service')['records'])
            now[0]=10
            with patch('airlunix.logging_ram.time.time',return_value=1000):restored.health()
            events=restored.query('health')['records']
            self.assertTrue(any(r['event']=='clock_discontinuity' for r in events))
            self.assertTrue(all(r['time_confidence']=='unsynchronized' for r in events))
    def test_parser_flood_and_locked_store_do_not_block_admin(self):
        from unittest.mock import patch
        from airlunix.logging_ram import emit as real_emit
        with tempfile.TemporaryDirectory(prefix='logtest-') as d:
            root=Path(d);collector=Collector(root,syslog_path=root/'syslog',kernel=False,web_uid=os.getuid()).start()
            class Isolated(Admin):
                def fingerprint(self):return 'fixture'
            admin=Isolated(FakeAccounts(),state=root/'state');admin.log_collector=collector
            try:
                collector.store.lock.acquire()
                with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM|socket.SOCK_NONBLOCK) as s:
                    for i in range(1000):
                        try:s.sendto(b'['*1000+b']'*1000,str(root/'events.sock'))
                        except BlockingIOError:pass
                started=time.monotonic()
                with patch('airlunix.admin.emit',side_effect=lambda *a,**kw:real_emit(*a,**kw,root=root)):
                    result=admin.call({'op':'create_user','user':'operator','password':'initial','name':'newuser','new_password':'fixture'})
                self.assertTrue(result['success']);self.assertLess(time.monotonic()-started,1)
                self.assertTrue(collector.thread.is_alive())
            finally:
                collector.store.lock.release();collector.close()
    def test_persistence_allowlist_excludes_logs(self):
        import importlib.machinery,importlib.util
        loader=importlib.machinery.SourceFileLoader('isolated_state',str(ROOT/'configs/ram/airlunix-state'))
        spec=importlib.util.spec_from_loader(loader.name,loader);mod=importlib.util.module_from_spec(spec);loader.exec_module(mod)
        for name in ('run/airlunix-log/security.jsonl','var/log/messages','run/airlunix-early.log'):
            self.assertFalse(mod.allowed(name))
        self.assertTrue(mod.allowed('etc/airlunix/selected/web/config.json'))
    def test_pagination_crosses_rotation_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d,quotas={'health':4096,'system':4096})
            for i in range(12):store.append('system',{'event':'item','operation':str(i)},'fixture',force=True)
            cursor=None;seen=[]
            for _ in range(12):
                page=store.query('system',cursor=cursor,limit=1)
                if not page['records']:break
                seen.extend(r['sequence'] for r in page['records']);cursor=page['cursor']
            self.assertGreater(len(seen),3)
            self.assertEqual(len(seen),len(set(seen)))
    def test_rate_limits_and_queries(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d)
            for _ in range(300):store.append('security',{'event':'rejected'},'fixture')
            self.assertGreater(store.counts['rate_drop'],0)
            for i in range(1000):store.append('system',{'event':'output','message':'x'*4000},'fixture',force=True)
            page=store.query('system',limit=10000)
            self.assertLessEqual(len(page['records']),200)
            self.assertLessEqual(page['scanned_bytes'],524288)
            self.assertTrue(store.counts['truncated'])
            with self.assertRaises(ValueError):store.query('/etc/shadow')
    def test_grants_require_real_admin_password(self):
        with tempfile.TemporaryDirectory() as d:
            class Isolated(Admin):
                def fingerprint(self):return 'fixture'
            admin=Isolated(FakeAccounts(),state=Path(d))
            with self.assertRaises(Denied):admin.call({'op':'logs','user':'operator'})
            with self.assertRaises(Denied):admin.call({'op':'log_authorize','user':'reader','password':'initial'})
            grant=admin.call({'op':'log_authorize','user':'operator','password':'initial'})
            self.assertNotIn(grant['grant'],admin.log_grants)
            collector=type('Fixture',(),{'store':Store(Path(d)/'logs')})()
            admin.log_collector=collector
            self.assertIn('records',admin.call({'op':'logs','grant':grant['grant']}))
            admin.log_grants[next(iter(admin.log_grants))]['expires']=0
            with self.assertRaises(Denied):admin.call({'op':'logs','grant':grant['grant']})
    def test_noisy_ntp_output_is_drained_without_logfile_growth(self):
        import importlib.util
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('candidate_time',ROOT/'configs/ram/airlunix_time.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            fixture=type('User',(),{'pw_uid':os.getuid(),'pw_gid':os.getgid()})()
            with patch.object(mod.pwd,'getpwnam',return_value=fixture):
                started=time.monotonic()
                result=mod.run_client({'timeout_s':0.3},Path(d),[sys.executable,'-c',
                    'import os; b=b"x"*4096;\nwhile True: os.write(1,b)'])
            self.assertTrue(result['timed_out'])
            self.assertLess(time.monotonic()-started,2)
            self.assertFalse((Path(d)/'last-client.log').exists())
    def test_auth_syslog_never_stores_command_arguments(self):
        with tempfile.TemporaryDirectory(prefix='logtest-') as d:
            collector=Collector(Path(d),syslog_path=Path(d)/'syslog',kernel=False)
            try:
                collector.ingest(b'<86>doas: operator ran command tool password=CANARYSECRET as root',os.getpid(),0,'syslog')
                records=collector.store.query('security')['records']
                self.assertEqual(records[0]['event'],'elevation_allowed')
                self.assertNotIn('CANARYSECRET',json.dumps(records))
            finally:
                collector.thread.start();collector.close()

if __name__=='__main__':unittest.main()
