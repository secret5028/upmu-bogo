"""Exercise the installed bundle with all system Python/Node paths removed."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request

parser=argparse.ArgumentParser()
parser.add_argument('install_dir',type=Path)
args=parser.parse_args()
app=args.install_dir.resolve()
system=Path(os.environ['WINDIR'])/'System32'
env=dict(os.environ,PATH=str(system),PYTHONIOENCODING='utf-8')
env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
python=app/'runtime/python/python.exe'
pid=None
with tempfile.TemporaryDirectory(prefix='업무보고 설치 검증 ') as temp:
    data=Path(temp)/'새 데이터'
    try:
        result=subprocess.run([str(python),str(app/'bootstrap.py'),'--no-browser','--data-dir',str(data),'--port','8898'],
            env=env,capture_output=True,encoding='utf-8',timeout=90,check=True)
        state=json.loads(result.stdout);pid=state['pid'];base='http://127.0.0.1:'+str(state['port'])
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        html=opener.open(base,timeout=10).read().decode()
        token=re.search(r'name="report-token" content="([^"]+)"',html)[1]
        def request(path,payload=None):
            raw=json.dumps(payload).encode() if payload is not None else None
            req=urllib.request.Request(base+path,data=raw,headers={'X-Report-Token':token,'Content-Type':'application/json'})
            return json.load(opener.open(req,timeout=90))
        config=request('/api/config')
        assert not any(config['ai'].values()),'Test PATH must not discover external AI tools'
        assert all(not row['name'] and not row['phone'] for row in config['header']['staff'])
        corpusdir=data/'자료/기존 업무보고'
        shutil.copy2(app/'assets/approved.hwpx',corpusdir/'기본 사례.hwpx')
        request('/api/corpus/config',{'roots':[str(corpusdir)]})
        request('/api/corpus/build',{})
        for _ in range(100):
            corpus=request('/api/corpus')
            if corpus['job']['state']!='running':break
            time.sleep(.1)
        assert corpus['stats']['documents']==1 and corpus['stats']['failed']==0,corpus
        fields={'title':'설치파일 동작 검증','report_date':'2026-11-13','report_body':'□ 검증개요\n❍ 내장 실행환경으로 문서 생성\n□ 확인결과\n❍ Python과 Node 별도 설치 불필요\n- 문서 생성 및 저장 확인'}
        saved=request('/api/save',{'fields':fields});sid=saved['id']
        request('/api/generate',{'id':sid,'fields':fields})
        final=request('/api/finalize',{'id':sid,'reviewed':True,'remember_example':False})
        assert final['status']=='finalized' and Path(final['web']['saved_path']).is_file()
        preview=opener.open(base+'/api/preview?id='+sid,timeout=30).read().decode()
        assert '검증개요' in preview
        session=json.loads((data/'99_시스템/작성세션'/f'{sid}.json').read_text(encoding='utf-8'))
        assert all(session['verification'].values()),session['verification']
        runtime=json.loads((data/'99_시스템/kordoc-runtime.json').read_text(encoding='utf-8'))
        assert Path(runtime['node'])==app/'runtime/node/node.exe'
        print('PASS: isolated PATH; bundled Python/Node; blank settings; corpus; generate; format checks; save; preview')
    finally:
        if pid:
            subprocess.run([str(system/'taskkill.exe'),'/PID',str(pid),'/T','/F'],capture_output=True)
            time.sleep(.3)
