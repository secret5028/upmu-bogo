"""Package only the public allowlist, even after the app has been used."""
from pathlib import Path
import hashlib
import zipfile

ROOT=Path(__file__).resolve().parent
FILES=['README.md','THIRD_PARTY.md','.gitignore','requirements.txt','package.json','package-lock.json',
       'installer/bootstrap.py','installer/build.py','installer/setup.iss','setup.py','install.ps1','install.cmd','create-shortcut.ps1','make_release.py',
       'app/server.py','app/corpus.py','app/start.ps1','engine/report_loop.py',
       'assets/approved.hwpx','defaults/report-header.json','tests/test_corpus.py','tests/test_distribution.py','tests/test_installer.py']
FILES += ['app/static/'+name for name in ['index.html','app.js','style.css','report-icon.svg','report-icon.ico']]
FILES += ['examples/README.md'] + ['examples/'+stem+ext
          for stem in ['01_회의참석보고','02_현장조사결과보고']
          for ext in ['.hwpx','.txt','.svg']]

def main():
    missing=[name for name in FILES if not (ROOT/name).is_file()]
    if missing:raise SystemExit('Missing source files: '+', '.join(missing))
    out=ROOT/'dist';out.mkdir(exist_ok=True)
    target=out/'work-report-workspace-0.2.0-source.zip'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in FILES:z.write(ROOT/name,'work-report-workspace/'+name)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    (out/'SHA256SUMS.txt').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print(target)
    print(digest)

if __name__=='__main__':main()
