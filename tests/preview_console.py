"""Host-only HTTPS preview. Fake account backend, real privacy-filtered telemetry.

This file is never installed by configure-rootfs.py. It changes no host accounts.
Credentials are generated in RAM; private metadata is written mode 0600 in the
explicit temporary directory supplied by the test runner.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('airlunix',ROOT/'console/__init__.py',submodule_search_locations=[str(ROOT/'console')])
module=importlib.util.module_from_spec(spec);sys.modules['airlunix']=module;spec.loader.exec_module(module)
from airlunix.web import APIError,Application,Server
from airlunix.telemetry import Sampler

class PreviewHelper:
    def __init__(self):self.password=secrets.token_urlsafe(24)
    def call(self,r):
        if r['op']=='login':
            if r.get('user')!='preview' or r.get('password')!=self.password:raise APIError(403,'Invalid credentials')
            return {'name':'preview','administrator':True,'uid':1000}
        if r['op']=='save_status':return {'unsaved_changes':False,'last_successful_save':None,'sd_mounted':False,'categories':['Device identity','Accounts and administrator keys','Selected configuration']}
        if r['op']=='users':return [{'name':'preview','administrator':True,'uid':1000}]
        if r['op']=='storage':return {'available':False,'reason':'No supported SD media on this host validation fixture'}
        if r['op']=='audit':return []
        raise APIError(409,'Host preview never changes accounts or storage')

def make_server(directory,port=0):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    key=directory/'tls.key';cert=directory/'tls.crt'
    subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes',
                    '-subj','/CN=localhost','-keyout',str(key),'-out',str(cert),'-days','1'],check=True,capture_output=True)
    key.chmod(0o600)
    helper=PreviewHelper();config={'assets':str(ROOT/'web'),'allowed_hosts':[]}
    app=Application(config,helper,Sampler(2,True,'Airlunix 0.3.0 · host validation'))
    server=Server(('127.0.0.1',port),app)
    config['allowed_hosts']=[f'127.0.0.1:{server.server_port}']
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert,key);server.tls_context=context
    return server,helper

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args()
    server,helper=make_server(args.directory)
    p=Path(args.directory)/'fixture.json'
    fd=os.open(p,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f:json.dump({'url':f'https://127.0.0.1:{server.server_port}','user':'preview','password':helper.password},f)
    print('Host-isolated HTTPS preview ready',flush=True)
    server.serve_forever()
