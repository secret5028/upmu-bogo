"""Install the source distribution into ./data without overwriting user settings."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def run(args):
    subprocess.run([str(a) for a in args],check=True,cwd=ROOT)

def configure(data,python,node):
    system=data/'99_시스템';web=system/'webapp'
    for folder in [web,system/'scripts',data/'50_문서템플릿/업무보고',data/'60_작성중',data/'70_완성문서',data/'자료/기존 업무보고',data/'자료/웹업로드']:
        folder.mkdir(parents=True,exist_ok=True)
    for name in ['server.py','corpus.py','start.ps1']:shutil.copy2(ROOT/'app'/name,web/name)
    shutil.copytree(ROOT/'app/static',web/'static',dirs_exist_ok=True)
    shutil.copy2(ROOT/'engine/report_loop.py',system/'scripts/report_loop.py')
    template=data/'50_문서템플릿/업무보고/기본 업무보고.hwpx'
    if not template.exists():shutil.copy2(ROOT/'assets/approved.hwpx',template)
    if not (system/'report-header.json').exists():shutil.copy2(ROOT/'defaults/report-header.json',system/'report-header.json')
    (web/'runtime.json').write_text(json.dumps({'python':str(python)},ensure_ascii=False),encoding='utf-8')
    (system/'kordoc-runtime.json').write_text(json.dumps({'node':str(node),'cli':str(ROOT/'node_modules/kordoc/dist/cli.js')},ensure_ascii=False),encoding='utf-8')
    # Use the private data folder's launcher so the existing start.ps1 root logic applies.
    launcher='''Set fs = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fs.GetParentFolderName(WScript.ScriptFullName)
script = fs.BuildPath(root, "data\\99_시스템\\webapp\\start.ps1")
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & script & Chr(34), 0, False
'''
    (ROOT/'업무보고 실행.vbs').write_text(launcher,encoding='utf-16')
    # Windows PowerShell 5.1 requires a BOM for Korean paths in scripts.
    start=web/'start.ps1'
    start.write_text(start.read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
    run([python,system/'scripts/report_loop.py','build-profiles'])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--skip-dependencies',action='store_true',help='Developer verification only; dependencies must already be installed.')
    parser.add_argument('--no-shortcut',action='store_true')
    args=parser.parse_args()
    if sys.version_info<(3,11):raise SystemExit('Python 3.11 이상이 필요합니다.')
    if os.name!='nt':raise SystemExit('이 배포본의 실행기와 폴더 기능은 Windows용입니다.')
    node=shutil.which('node.exe');npm=shutil.which('npm.cmd')
    if not node or not npm:raise SystemExit('Node.js 20 이상을 설치한 뒤 설치를 다시 실행하세요: https://nodejs.org/')
    version=subprocess.check_output([node,'--version'],text=True).strip()
    if int(version.lstrip('v').split('.')[0])<20:raise SystemExit('Node.js 20 이상이 필요합니다.')
    python=Path(sys.executable)
    if not args.skip_dependencies:
        venv=ROOT/'.venv'
        if not (venv/'Scripts/python.exe').exists():run([sys.executable,'-m','venv',venv])
        python=venv/'Scripts/python.exe'
        run([python,'-m','pip','install','-r',ROOT/'requirements.txt'])
        # Calling npm's JS entry avoids cmd.exe quoting of Unicode/spaced paths.
        npmcli=Path(npm).parent/'node_modules/npm/bin/npm-cli.js'
        if not npmcli.exists():raise SystemExit('표준 Node.js/npm 설치 경로를 찾을 수 없습니다.')
        run([node,npmcli,'ci','--omit=optional','--ignore-scripts','--no-fund','--no-audit'])
    if not (ROOT/'node_modules/kordoc/dist/cli.js').exists():raise SystemExit('kordoc 설치가 완료되지 않았습니다.')
    configure(ROOT/'data',python,node)
    if not args.no_shortcut:
        run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',ROOT/'create-shortcut.ps1'])
    print('설치 완료. 업무보고 실행.vbs 또는 바탕화면 아이콘을 실행하세요.',flush=True)

if __name__=='__main__':main()
