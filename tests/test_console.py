"""Host-isolated tests: never alter host accounts, clocks or block devices."""
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import http.client
import ssl
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('airlunix',ROOT/'console/__init__.py',submodule_search_locations=[str(ROOT/'console')])
module=importlib.util.module_from_spec(spec);sys.modules['airlunix']=module;spec.loader.exec_module(module)
from airlunix.admin import Admin,Denied,valid_name,Accounts
from airlunix.storage import Media,StorageError,parse_mbr,plan,storage_lock
from airlunix.web import Sessions,Application,APIError

class FakeAccounts:
    def __init__(self):self.passwords={'operator':'initial','reader':'initial'}
    def interactive(self):return [{'name':name,'uid':1000+i,'administrator':name=='operator'} for i,name in enumerate(self.passwords)]
    def verify(self,name,password):return next((u for u in self.interactive() if u['name']==name),None) if self.passwords.get(name)==password and name in self.passwords else None
    def change(self,name,password):self.passwords[name]=password
    def create(self,name,password):
        if not valid_name(name):raise ValueError('Invalid name')
        self.passwords[name]=password

class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.accounts=FakeAccounts();self.saved=False
        class IsolatedAdmin(Admin):
            def fingerprint(inner):return json.dumps(inner.accounts.passwords,sort_keys=True)
        self.admin=IsolatedAdmin(self.accounts,state=Path(self.temp.name),persist=lambda:{'success':True,'sd_unmounted':True})
    def call(self,op,user='operator',**kwargs):return self.admin.call({'op':op,'user':user,'password':'initial',**kwargs})
    def test_password_reauthentication_and_normal_user_boundary(self):
        with self.assertRaises(Denied):self.call('password',password='wrong',new_password='changed')
        with self.assertRaises(Denied):self.call('create_user',user='reader',name='third',new_password='changed')
        self.assertFalse(self.call('create_user',name='third',new_password='changed')['administrator'])
        self.assertFalse(self.accounts.verify('third','changed')['administrator'])
        self.assertFalse(self.call('password',new_password='changed')['saved'])
        self.assertIsNone(self.accounts.verify('operator','initial'))
    def test_login_throttle_and_bounded_audit(self):
        for _ in range(5):
            with self.assertRaises(Denied):self.call('login',password='wrong')
        with self.assertRaisesRegex(Denied,'throttled'):self.call('login')
        self.assertFalse(self.admin.audit[-1]['success'])
        for _ in range(300):self.admin.log('operator','test',True)
        self.assertEqual(len(self.admin.audit),200)
        self.assertNotIn('initial',json.dumps(list(self.admin.audit)))
    def test_save_failure_and_unmount_failure_do_not_mark_saved(self):
        for result in ({'success':False,'sd_unmounted':True},{'success':True,'sd_unmounted':False}):
            self.admin.persist=lambda:result
            with self.assertRaises(StorageError):self.call('save')
            self.assertIsNone(self.admin.last_save)
    def test_save_and_storage_share_exclusive_lock(self):
        with storage_lock(Path(self.temp.name)/'storage.lock'):
            with self.assertRaises(StorageError):self.call('password',new_password='changed')
    def test_sessions_idle_absolute_logout_and_no_plain_token_storage(self):
        now=[0];sessions=Sessions(clock=lambda:now[0],idle=5,absolute=10)
        token,_=sessions.create({'name':'operator'})
        self.assertNotIn(token,sessions.values)
        now[0]=4;self.assertIsNotNone(sessions.get(token))
        now[0]=8;self.assertIsNotNone(sessions.get(token))
        now[0]=10;self.assertIsNone(sessions.get(token))
        token,_=sessions.create({});sessions.remove(token);self.assertIsNone(sessions.get(token))
        token,_=sessions.create({});now[0]=16;self.assertIsNone(sessions.get(token))
    def test_no_generic_privileged_operation(self):
        for op in ('shell','write_file','delete_user','grant_admin','format','remove_partition'):
            with self.assertRaises(ValueError):self.call(op)
    def test_account_input_validation_before_process_execution(self):
        with patch('airlunix.admin.subprocess.run') as run:
            for name in ('root','airweb','-x','a;id','../root','a\nroot'):
                with self.assertRaises(ValueError):Accounts().create(name,'password')
            with self.assertRaises(ValueError):Accounts().change('operator','line\nbreak')
            run.assert_not_called()

def make_image(path,size=192*1024*1024,part=64*1024*1024):
    mbr=bytearray(512);mbr[:20]=b'Airlunix test guard!!';mbr[510:]=b'\x55\xaa'
    mbr[446:462]=struct.pack('<B3sB3sII',0x80,b'\0'*3,0x83,b'\0'*3,65536,part//512)
    with path.open('wb') as f:f.write(mbr);f.truncate(size)
    fs=path.with_suffix('.ext4')
    with fs.open('wb') as f:f.truncate(part)
    subprocess.run(['mke2fs','-q','-F','-t','ext4','-L','airlunix-state',str(fs)],check=True,capture_output=True)
    with path.open('r+b') as out,fs.open('rb') as source:
        out.seek(65536*512)
        import shutil
        shutil.copyfileobj(source,out)
    fs.unlink()

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.image=Path(self.temp.name)/'disposable.img';make_image(self.image)
        self.media=Media(test_image=self.image)
    def test_actual_ext4_expansion_and_reserved_boot_preserved(self):
        with self.image.open('rb') as f:before=f.read(65536*512)
        result=self.media.execute(plan(self.media.inspect(),'expand'))
        self.assertTrue(result['filesystem_updated'])
        layout=self.media.inspect();p=layout['partitions'][0]
        self.assertEqual(p['filesystem_bytes'],p['sectors']*512)
        with self.image.open('rb') as f:after=f.read(65536*512)
        self.assertEqual(before[:458],after[:458]);self.assertEqual(before[462:],after[462:])
        with self.assertRaises(StorageError):plan(layout,'expand')
    def test_actual_new_filesystem_leaves_existing_partition_intact(self):
        before=self.media.inspect()['partitions'][0].copy()
        result=self.media.execute(plan(self.media.inspect(),'create',64))
        self.assertTrue(result['filesystem_updated'])
        parts=self.media.inspect()['partitions'];self.assertEqual(parts[0],before)
        self.assertEqual(parts[1]['filesystem_bytes'],64*1024*1024)
    def test_stale_preview_and_unsafe_layout_rejected(self):
        preview=plan(self.media.inspect(),'expand');preview['layout_sha256']='wrong'
        with self.assertRaises(StorageError):self.media.execute(preview)
        for kind in (0xee,0x05,0x0f):
            data=bytearray(self.image.read_bytes()[:512]);data[450]=kind
            with self.assertRaises(StorageError):parse_mbr(data,self.media.capacity())
    def test_filesystem_resize_resume_after_durable_partition_growth(self):
        preview=plan(self.media.inspect(),'expand')
        with self.image.open('r+b') as f:f.seek(458);f.write(struct.pack('<I',preview['sectors']))
        retry=plan(self.media.inspect(),'expand');self.assertTrue(retry['filesystem_only'])
        self.assertTrue(self.media.execute(retry)['filesystem_updated'])

class HTTPSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from preview_console import make_server
        cls.temp=tempfile.TemporaryDirectory();cls.server,cls.helper=make_server(cls.temp.name)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()
    def request(self,path,body=None,cookie=None,csrf=None,origin=True):
        c=http.client.HTTPSConnection('127.0.0.1',self.server.server_port,context=ssl._create_unverified_context(),timeout=5)
        headers={}
        if cookie:headers['Cookie']=cookie
        if csrf:headers['X-CSRF-Token']=csrf
        if body is not None:
            headers['Content-Type']='application/json'
            if origin:headers['Origin']=f'https://127.0.0.1:{self.server.server_port}'
        c.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,headers)
        response=c.getresponse();raw=response.read();status=response.status;cookie=response.getheader('Set-Cookie');c.close()
        return status,json.loads(raw),cookie
    def login(self):return self.request('/api/login',{'user':'preview','password':self.helper.password})
    def test_unauthorized_origin_csrf_logout_and_cookie_flags(self):
        self.assertEqual(self.request('/api/overview')[0],401)
        self.assertEqual(self.request('/api/login',{'user':'preview','password':self.helper.password},origin=False)[0],403)
        status,data,cookie=self.login();self.assertEqual(status,200)
        for flag in ('Secure','HttpOnly','SameSite=Strict'):self.assertIn(flag,cookie)
        self.assertEqual(self.request('/api/overview',cookie=cookie)[0],200)
        self.assertEqual(self.request('/api/logout',{},cookie=cookie)[0],403)
        self.assertEqual(self.request('/api/logout',{},cookie=cookie,csrf=data['csrf'])[0],200)
        self.assertEqual(self.request('/api/overview',cookie=cookie)[0],401)
    def test_session_expiry_and_server_authorization(self):
        _,data,cookie=self.login()
        token=cookie.split(';')[0].split('=',1)[1]
        session=self.server.app.sessions.get(token);session['user']['administrator']=False
        self.assertEqual(self.request('/api/storage/preview',{'password':'fresh','action':'expand'},cookie,data['csrf'])[0],403)
        self.assertEqual(self.request('/api/save',{'password':'fresh'},cookie,data['csrf'])[0],403)
        session['created']-=4000
        self.assertEqual(self.request('/api/overview',cookie=cookie)[0],401)

if __name__=='__main__':unittest.main()
