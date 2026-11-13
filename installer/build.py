"""Build an offline x64 installer from pinned official runtimes and dependency locks."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PY_VERSION='3.13.17'
NODE_VERSION='26.13.1'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--downloads',type=Path,required=True)
    parser.add_argument('--iscc',type=Path,required=True)
    args=parser.parse_args()
    downloads=args.downloads.resolve();downloads.mkdir(parents=True,exist_ok=True)
    archives={
        f'python-{PY_VERSION}-embed-amd64.zip':f'https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip',
        f'node-v{NODE_VERSION}-win-x64.zip':f'https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip',
        'node-SHASUMS256.txt':f'https://nodejs.org/dist/v{NODE_VERSION}/SHASUMS256.txt'}
    for name,url in archives.items():
        if not (downloads/name).exists():urllib.request.urlretrieve(url,downloads/name)
    nodezip=f'node-v{NODE_VERSION}-win-x64.zip'
    expected=next(line.split()[0] for line in (downloads/'node-SHASUMS256.txt').read_text().splitlines() if line.split()[-1]==nodezip)
    assert hashlib.sha256((downloads/nodezip).read_bytes()).hexdigest()==expected,'Node SHA256 mismatch'
    payload=ROOT/'build'/datetime.now().strftime('%Y%m%d-%H%M%S')/'payload'
    payload.mkdir(parents=True,exist_ok=False)
    for folder in ['app','engine','assets','defaults']:
        shutil.copytree(ROOT/folder,payload/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copy2(ROOT/'installer/bootstrap.py',payload/'bootstrap.py')
    for name in ['README.md','THIRD_PARTY.md','requirements.txt','package.json','package-lock.json']:
        shutil.copy2(ROOT/name,payload/name)
    shutil.copytree(ROOT/'node_modules',payload/'node_modules',ignore=shutil.ignore_patterns('.bin','.cache'))
    python_dir=payload/'runtime/python';python_dir.mkdir(parents=True)
    with zipfile.ZipFile(downloads/f'python-{PY_VERSION}-embed-amd64.zip') as z:z.extractall(python_dir)
    pth=python_dir/'python313._pth'
    pth.write_text('python313.zip\n.\nLib/site-packages\n../..\nimport site\n',encoding='utf-8')
    # Include cp313 wheels, not the build machine's Python/venv.
    subprocess.run([sys.executable,'-m','pip','install','--target',str(python_dir/'Lib/site-packages'),
        '--python-version','3.13','--platform','win_amd64','--implementation','cp','--abi','cp313',
        '--only-binary=:all:','--no-compile','-r',str(ROOT/'requirements.txt')],check=True)
    node_dir=payload/'runtime/node';node_dir.mkdir(parents=True)
    with zipfile.ZipFile(downloads/nodezip) as z:
        for name in ['node.exe','LICENSE']:
            (node_dir/name).write_bytes(z.read(f'node-v{NODE_VERSION}-win-x64/{name}'))
    manifest={'version':'0.2.1','python':PY_VERSION,'node':NODE_VERSION,
              'archives':{name:hashlib.sha256((downloads/name).read_bytes()).hexdigest() for name in archives}}
    (payload/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (ROOT/'build/current.json').write_text(json.dumps({'payload':str(payload)},ensure_ascii=False),encoding='utf-8')
    out=ROOT/'dist';out.mkdir(exist_ok=True)
    compiled=subprocess.run([str(args.iscc.resolve()),'/Q','/DPayload='+str(payload),'/DOutput='+str(out),str(ROOT/'installer/setup.iss')],capture_output=True)
    (payload.parent/'compiler.log').write_bytes(compiled.stdout+compiled.stderr)
    if compiled.returncode:raise RuntimeError((compiled.stdout+compiled.stderr).decode('utf-8',errors='replace')[-4000:])
    exe=out/'UpmuBogo-Setup-0.2.1-x64.exe'
    (out/'UpmuBogo-Setup-0.2.1-x64.sha256').write_text(hashlib.sha256(exe.read_bytes()).hexdigest()+'  '+exe.name+'\n',encoding='utf-8')
    print('INSTALLER: '+str(exe),flush=True)

if __name__=='__main__':main()
