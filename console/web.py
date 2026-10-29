"""Unprivileged HTTPS control plane with a deliberately narrow local helper."""
import collections
import hashlib
import hmac
from http import cookies
from http.server import BaseHTTPRequestHandler,HTTPServer
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import socketserver
import ssl
import threading
import time
from urllib.parse import urlsplit
from .telemetry import Sampler
from .logging_ram import emit, install_output
http.client._MAXLINE=8192
http.client._MAXHEADERS=32

class APIError(Exception):
    def __init__(self,code,message):self.code=code;self.message=message

class Helper:
    def __init__(self,path='/run/airlunix-admin/control.sock'):self.path=path
    def call(self,request):
        with socket.socket(socket.AF_UNIX) as sock:
            sock.settimeout(260);sock.connect(self.path)
            sock.sendall(json.dumps(request).encode()+b'\n')
            f=sock.makefile('rb');raw=f.readline(262145)
        if len(raw)>262144:raise APIError(502,'Helper response exceeded limit')
        data=json.loads(raw)
        if not data['ok']:raise APIError(data.get('code',500),data['error'])
        return data['result']

class Sessions:
    def __init__(self,clock=time.monotonic,idle=900,absolute=3600):
        self.clock=clock;self.idle=idle;self.absolute=absolute;self.values={};self.lock=threading.Lock()
    def create(self,user):
        with self.lock:
            now=self.clock()
            self.values={k:v for k,v in self.values.items() if now-v['seen']<self.idle and now-v['created']<self.absolute}
            if len(self.values)>=64:raise APIError(503,'Session limit reached')
            token=secrets.token_urlsafe(32);key=hashlib.sha256(token.encode()).hexdigest()
            self.values[key]={'user':user,'csrf':secrets.token_urlsafe(32),'created':now,'seen':now,'id':secrets.token_hex(12)}
            return token,self.values[key]
    def get(self,token):
        with self.lock:
            key=hashlib.sha256(token.encode()).hexdigest();v=self.values.get(key);now=self.clock()
            if not v:return None
            if now-v['seen']>=self.idle or now-v['created']>=self.absolute:
                self.values.pop(key);emit('security','session_expired');return None
            v['seen']=now;return v
    def remove(self,token):
        with self.lock:self.values.pop(hashlib.sha256(token.encode()).hexdigest(),None)

class Application:
    def __init__(self,config,helper=None,sampler=None):
        self.config=config;self.helper=helper or Helper();self.sampler=sampler or Sampler(config.get('refresh_s',3),config.get('privacy_mode',False))
        self.sessions=Sessions();self.login_limits=collections.OrderedDict();self.jobs={};self.audit=collections.deque(maxlen=32)
        self.lock=threading.Lock();self.job_slots=threading.BoundedSemaphore(2)
    def log(self,action,success):
        self.audit.append({'boot_s':round(time.monotonic(),3),'action':action,'success':success})
        emit('security',action,success)
    def login(self,ip,body):
        now=time.monotonic()
        with self.lock:
            attempts=[x for x in self.login_limits.get(ip,[]) if now-x<300]
            if len(attempts)>=5:raise APIError(429,'Too many login attempts; retry after five minutes')
            attempts.append(now);self.login_limits[ip]=attempts
            while len(self.login_limits)>256:self.login_limits.popitem(last=False)
        request=({'op':'bootstrap_click'} if body.get('first_visit') is True and self.config.get('bind')=='127.0.0.1' and ip=='127.0.0.1' else {'op':'bootstrap_login','token':body['bootstrap_token']} if 'bootstrap_token' in body else
                 {'op':'login','user':body.get('user'),'password':body.get('password')})
        try:user=self.helper.call(request)
        except Exception:self.log('login',False);raise APIError(403,'Authentication failed or temporarily throttled')
        with self.lock:self.login_limits.pop(ip,None)
        grant=user.pop('setup_grant',None);first=user.pop('first_login',False)
        token,session=self.sessions.create(user);session['setup_grant']=grant;session['first_login']=first;self.log('login',True)
        return token,{'user':user,'csrf':session['csrf'],'refresh_s':self.sampler.interval,'first_login':first}
    def job(self,session,op,body):
        if not session['user']['administrator'] and op!='password':raise APIError(403,'Administrative access required')
        if session.get('first_login') and op!='first_password':raise APIError(403,'Choose your administrator password first')
        if not self.job_slots.acquire(False):raise APIError(409,'Another administrative action is running; retry after completion')
        key=secrets.token_hex(16)
        with self.lock:
            self.jobs={k:v for k,v in self.jobs.items() if time.monotonic()-v['created']<600}
            if len(self.jobs)>=32:self.job_slots.release();raise APIError(503,'Job limit reached')
            self.jobs[key]={'id':key,'owner':session['id'],'created':time.monotonic(),'state':'pending','action':op}
        request={**body,'op':op,'user':session['user']['name']}
        if op=='first_password':request['setup_grant']=session.get('setup_grant')
        def work():
            self.jobs[key]['state']='running'
            try:
                result=self.helper.call(request)
                self.jobs[key].update(state='success' if result.get('success',True) else 'error',result=result)
                if op=='first_password' and result.get('success'):
                    session['setup_grant']=None;session['first_login']=False
                self.log(op,result.get('success',True))
            except Exception as exc:
                self.jobs[key].update(state='error',error=exc.message if isinstance(exc,APIError) else 'Operation unavailable; inspect via authenticated SSH')
                self.log(op,False)
            finally:
                request.clear();self.job_slots.release()
        threading.Thread(target=work,daemon=True).start();return {'job':key,'state':'pending'}

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.0'
    server_version='Airlunix'
    def log_message(self,*args):pass # Never log tokens, paths or request bodies.
    def setup(self):super().setup();self.connection.settimeout(10)
    def send(self,code,data,kind='application/json',cookie=None):
        body=json.dumps(data).encode() if kind=='application/json' else data
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Referrer-Policy','no-referrer');self.send_header('Strict-Transport-Security','max-age=86400')
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(body)
    def token(self):
        try:
            c=cookies.SimpleCookie(self.headers.get('Cookie',''));return c['airlunix_session'].value
        except (KeyError,cookies.CookieError):return ''
    def run_request(self,post=False):
        app=self.server.app;host=self.headers.get('Host','')
        if host not in app.config['allowed_hosts']:raise APIError(403,'Unrecognized management host')
        path=urlsplit(self.path).path
        if len(self.path)>1024:raise APIError(414,'Request target too long')
        if post:
            if self.headers.get('Origin')!='https://'+host:raise APIError(403,'Same-origin HTTPS request required')
            if self.headers.get_content_type()!='application/json':raise APIError(415,'JSON required')
            try:length=int(self.headers.get('Content-Length','0'))
            except ValueError:raise APIError(400,'Invalid body length')
            if not 0<length<=8192:raise APIError(413,'Request body limit exceeded')
            try:body=json.loads(self.rfile.read(length))
            except ValueError:raise APIError(400,'Invalid JSON')
            if not isinstance(body,dict):raise APIError(400,'JSON object required')
            if path=='/api/login':
                token,result=app.login(self.client_address[0],body)
                return self.send(200,result,cookie='airlunix_session='+token+'; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=3600')
        if path=='/api/first-login' and not post:
            available=app.config.get('bind')=='127.0.0.1' and self.client_address[0]=='127.0.0.1'
            return self.send(200,app.helper.call({'op':'first_login_status'}) if available else {'available':False})
        if path in ('/','/app.js','/app.css') and not post:
            name={'/':'index.html','/app.js':'app.js','/app.css':'app.css'}[path]
            kinds={'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/app.css':'text/css; charset=utf-8'}
            return self.send(200,(Path(app.config['assets'])/name).read_bytes(),kinds[path])
        session=app.sessions.get(self.token())
        if not session:raise APIError(401,'Sign in with a provisioned local account')
        user=session['user']['name']
        if post:
            if not hmac.compare_digest(str(self.headers.get('X-CSRF-Token','')),session['csrf']):raise APIError(403,'CSRF validation failed')
            if path=='/api/logout':
                emit('security','logout',actor=user)
                app.sessions.remove(self.token());return self.send(200,{'success':True},cookie='airlunix_session=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0')
            if path=='/api/first-password':
                if not session.get('first_login'):raise APIError(403,'First-login authorization required')
                return self.send(202,app.job(session,'first_password',body))
            if session.get('first_login'):raise APIError(403,'Choose your administrator password first')
            if path=='/api/log-authorize':
                if not session['user']['administrator']:raise APIError(403,'Administrator required')
                result=app.helper.call({'op':'log_authorize','user':user,'password':body.get('password')})
                session['log_grant']=result['grant'];return self.send(200,{'expires_in_s':result['expires_in_s']})
            if path=='/api/log-export':
                if not session['user']['administrator']:raise APIError(403,'Administrator required')
                return self.send(200,app.helper.call({'op':'log_export','grant':session.get('log_grant',''),'user':user,'password':body.get('password')}))
            op={'/api/password':'password','/api/users':'create_user','/api/save':'save',
                '/api/storage/preview':'storage_preview','/api/storage/apply':'storage_apply'}.get(path)
            if not op:raise APIError(404,'Unknown action')
            if not isinstance(body.get('password'),str) or not body['password']:raise APIError(400,'Fresh password authentication required')
            if op=='storage_preview':
                if not session['user']['administrator']:raise APIError(403,'Administrative access required')
                return self.send(200,app.helper.call({**body,'op':op,'user':user}))
            return self.send(202,app.job(session,op,body))
        if path=='/api/session':return self.send(200,{'user':session['user'],'csrf':session['csrf'],'refresh_s':app.sampler.interval,'first_login':session.get('first_login',False)})
        if path=='/api/overview':return self.send(200,app.sampler.sample())
        if path=='/api/users':return self.send(200,app.helper.call({'op':'users','user':user}))
        if path=='/api/save-status':return self.send(200,app.helper.call({'op':'save_status','user':user}))
        if path=='/api/storage':return self.send(200,app.helper.call({'op':'storage','user':user}))
        if path=='/api/logs':
            if not session['user']['administrator']:raise APIError(403,'Administrator required')
            from urllib.parse import parse_qs
            params=parse_qs(urlsplit(self.path).query)
            return self.send(200,app.helper.call({'op':'logs','grant':session.get('log_grant',''),
                'channel':params.get('channel',['security'])[0],'limit':100,
                'event':params.get('event',[''])[0],'severity':params.get('severity',[''])[0],
                'cursor':json.loads(params['cursor'][0]) if 'cursor' in params else None}))
        if path.startswith('/api/jobs/'):
            job=app.jobs.get(path.rsplit('/',1)[-1])
            if not job or job['owner']!=session['id']:raise APIError(404,'Job unavailable')
            return self.send(200,{k:v for k,v in job.items() if k!='owner'})
        raise APIError(404,'Not found')
    def handle_api(self,post=False):
        try:self.run_request(post)
        except APIError as e:
            if e.code>=400:
                reason=next((label for text,label in [('CSRF','csrf'),('Same-origin','origin'),('management host','host'),('Administrative','role'),('Sign in','session')] if text in e.message),str(e.code))
                emit('security','http_rejected',False,reason=reason)
            self.send(e.code,{'error':e.message})
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:
            emit('web','request_failed',False,reason=type(exc).__name__)
            self.send(503,{'error':'Information or operation unavailable; no result has been assumed'})
    def do_GET(self):self.handle_api()
    def do_POST(self):self.handle_api(True)

class Server(socketserver.ThreadingMixIn,HTTPServer):
    daemon_threads=True;request_queue_size=8
    def __init__(self,address,app):self.app=app;self.slots=threading.BoundedSemaphore(8);super().__init__(address,Handler)
    def get_request(self):
        request,address=self.socket.accept();request.settimeout(10)
        context=getattr(self,'tls_context',None)
        if context:request=context.wrap_socket(request,server_side=True,do_handshake_on_connect=False)
        return request,address
    def process_request(self,request,address):
        if not self.slots.acquire(False):
            emit('security','http_capacity',False);request.close();return
        super().process_request(request,address)
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()

def serve(config,helper=None,sampler=None):
    if os.geteuid()==0:raise SystemExit('The HTTPS service must run as an unprivileged account')
    app=Application(config,helper,sampler);server=Server((config['bind'],config.get('port',8443)),app)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(config['certificate'],config['private_key'])
    server.tls_context=context
    print('Airlunix Web Console HTTPS listener ready',flush=True);server.serve_forever()

if __name__=='__main__':
    install_output('web')
    config=json.loads(Path('/etc/airlunix/selected/web/config.json').read_text())
    if not config.get('enabled'):raise SystemExit('Web Console has not been explicitly provisioned')
    config['assets']='/usr/share/airlunix-web';serve(config)
