"""Bundled Windows launcher. No system Python, Node, pip or npm is required."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parent
VERSION='0.2.0'
PYTHON=ROOT/'runtime/python/python.exe'
NODE=ROOT/'runtime/node/node.exe'
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)

def atomic(path,value):
    tmp=path.with_suffix('.new')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(tmp,path)

def prepare(data):
    system=data/'99_시스템';web=system/'webapp'
    for d in [web,system/'scripts',data/'50_문서템플릿/업무보고',data/'60_작성중',data/'70_완성문서',data/'자료/기존 업무보고',data/'자료/웹업로드']:
        d.mkdir(parents=True,exist_ok=True)
    for name in ['server.py','corpus.py']:shutil.copy2(ROOT/'app'/name,web/name)
    shutil.copytree(ROOT/'app/static',web/'static',dirs_exist_ok=True)
    shutil.copy2(ROOT/'engine/report_loop.py',system/'scripts/report_loop.py')
    template=data/'50_문서템플릿/업무보고/기본 업무보고.hwpx'
    if not template.exists():shutil.copy2(ROOT/'assets/approved.hwpx',template)
    if not (system/'report-header.json').exists():shutil.copy2(ROOT/'defaults/report-header.json',system/'report-header.json')
    atomic(system/'kordoc-runtime.json',{'node':str(NODE),'cli':str(ROOT/'node_modules/kordoc/dist/cli.js')})
    atomic(web/'runtime.json',{'python':str(PYTHON),'version':VERSION})
    if not (system/'업무보고_템플릿_프로필.json').exists():
        result=subprocess.run([str(PYTHON),str(system/'scripts/report_loop.py'),'build-profiles'],capture_output=True,env=environment(),creationflags=NO_WINDOW)
        if result.returncode:raise RuntimeError(result.stderr.decode('utf-8',errors='replace'))
    return web

def environment():
    return dict(os.environ,PYTHONIOENCODING='utf-8',KORDOC_OFFLINE='1',PATH=str(NODE.parent)+os.pathsep+os.environ.get('PATH',''))

def health(port):
    try:
        # Never use system HTTP proxy settings for the local app.
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/api/health',timeout=.6) as r:return json.load(r)
    except (OSError,ValueError):return None

def launch_browser(url):
    candidates=[Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe',
                Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Google/Chrome/Application/chrome.exe',
                Path(os.environ['LOCALAPPDATA'])/'Google/Chrome/Application/chrome.exe']
    chrome=next((p for p in candidates if p.is_file()),None)
    if chrome:subprocess.Popen([str(chrome),'--new-window',url])
    else:webbrowser.open(url)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--initialize',action='store_true')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--port',type=int)
    args=parser.parse_args()
    data=(args.data_dir or Path(os.environ['LOCALAPPDATA'])/'UpmuBogo/data').resolve()
    # Serialize startup so two shortcut clicks cannot start competing servers.
    import hashlib
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]
    kernel.CreateMutexW.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.ReleaseMutex.argtypes=[wintypes.HANDLE]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    mutex=kernel.CreateMutexW(None,False,'Local\\UpmuBogo-'+hashlib.sha256(str(data).encode()).hexdigest()[:16])
    if not mutex:raise ctypes.WinError(ctypes.get_last_error())
    if kernel.WaitForSingleObject(mutex,60000) not in (0,0x80):raise RuntimeError('이전 실행이 아직 준비 중입니다. 잠시 뒤 다시 실행하세요.')
    try:
        ports=[args.port] if args.port else range(8765,8785)
        found=None
        for port in ports:
            state=health(port)
            if state and state.get('app')=='work-report' and Path(state.get('project','')).resolve()==data:
                found=port;break
        if found is not None:
            if not args.initialize and not args.no_browser:launch_browser(f'http://127.0.0.1:{found}')
            print(json.dumps({'port':found,'reused':True}),flush=True);return
        web=prepare(data)
        if args.initialize:
            print('Initialized',flush=True);return
        for port in ports:
            with socket.socket() as s:
                try:s.bind(('127.0.0.1',port))
                except OSError:continue
                found=port;break
        if found is None:raise RuntimeError('8765~8784 포트가 사용 중입니다.')
        runner="import runpy,sys;p=sys.argv.pop(1);sys.path.insert(0,p);runpy.run_path(p+'/server.py',run_name='__main__')"
        with (web/'server.stdout.log').open('ab') as stdout,(web/'server.stderr.log').open('ab') as stderr:
            process=subprocess.Popen([str(PYTHON),'-c',runner,str(web),'--project',str(data),'--port',str(found)],
                cwd=data,env=environment(),stdout=stdout,stderr=stderr,creationflags=NO_WINDOW)
        for _ in range(120):
            state=health(found)
            if state and state.get('project')==str(data):break
            if process.poll() is not None:raise RuntimeError('서버 시작 실패. 로그: '+str(web/'server.stderr.log'))
            time.sleep(.25)
        else:raise RuntimeError('서버 준비 시간이 초과되었습니다. 로그를 확인하세요.')
        atomic(web/'launcher-state.json',{'pid':process.pid,'port':found,'python':str(PYTHON),'version':VERSION})
        if not args.no_browser:launch_browser(f'http://127.0.0.1:{found}')
        print(json.dumps({'port':found,'pid':process.pid,'project':str(data)},ensure_ascii=True),flush=True)
    finally:
        kernel.ReleaseMutex(mutex);kernel.CloseHandle(mutex)

if __name__=='__main__':
    try:main()
    except Exception as error:
        if '--no-browser' in sys.argv or '--initialize' in sys.argv:
            if sys.stderr:print(str(error),file=sys.stderr)
        else:ctypes.windll.user32.MessageBoxW(None,str(error),'업무보고 작업실',0x10)
        sys.exit(1)
