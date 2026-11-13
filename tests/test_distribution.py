"""End-to-end document creation in a fresh, disposable project, without AI/network."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
node=shutil.which('node.exe') or shutil.which('node')
cli=ROOT/'node_modules/kordoc/dist/cli.js'
assert node and cli.is_file(),'Run install.cmd first.'

with zipfile.ZipFile(ROOT/'assets/approved.hwpx') as z:
    assert 'Preview/PrvImage.png' not in z.namelist()
    root=ET.fromstring(z.read('Contents/content.hpf'))
    metadata=next(e for e in root if e.tag.endswith('metadata'))
    assert len(metadata)==0,'Template metadata must be empty.'

with tempfile.TemporaryDirectory(prefix='report-install-check-') as td:
    project=Path(td)/'업무보고 설치 검증';system=project/'99_시스템'
    (system/'scripts').mkdir(parents=True)
    template=project/'50_문서템플릿/업무보고/기본 업무보고.hwpx'
    template.parent.mkdir(parents=True)
    shutil.copy2(ROOT/'assets/approved.hwpx',template)
    shutil.copy2(ROOT/'engine/report_loop.py',system/'scripts/report_loop.py')
    shutil.copy2(ROOT/'defaults/report-header.json',system/'report-header.json')
    (system/'kordoc-runtime.json').write_text(json.dumps({'node':node,'cli':str(cli)}),encoding='utf-8')
    def call(*args):
        p=subprocess.run([sys.executable,str(system/'scripts/report_loop.py'),*args],capture_output=True,encoding='utf-8',check=True,env=dict(os.environ,PYTHONIOENCODING='utf-8'))
        return json.loads(p.stdout)
    call('build-profiles')
    s=call('start','--request','배포본 설치 검증')
    sid=s['session_id']
    fields={'title':'배포본 설치 검증','report_date':'2026-11-13','report_body':'□ 검증개요\n❍ 새 설치 환경에서 보고서 생성\n□ 확인결과\n❍ 기호와 서식 보존\n- 개인정보 없는 기본 양식 사용'}
    call('update','--session',sid,'--fields-json',json.dumps(fields,ensure_ascii=False))
    made=call('generate','--session',sid)
    assert all(made['verification'].values()),made
    call('finalize','--session',sid)
    saved=json.loads((system/'작성세션'/f'{sid}.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(Path(saved['final']).read_bytes()).hexdigest()==saved['draft_sha256']
    preview=project/'preview.svg'
    subprocess.run([node,str(cli),'render',saved['final'],'-o',str(preview),'--silent'],check=True,capture_output=True)
    assert preview.is_file() and '검증개요' in preview.read_text(encoding='utf-8')
    # Switching purposes must clear the previous check; legacy sessions start unchecked.
    labels=['방침필요','상황·행사보고','결과보고(지시사항등)','회의자료']
    for selected in [*labels, '']:
        call('update','--session',sid,'--fields-json',json.dumps({'report_purpose':selected},ensure_ascii=False))
        made=call('generate','--session',sid)
        assert all(made['verification'].values()),made
        with zipfile.ZipFile(made['draft']) as z:
            section=ET.fromstring(z.read('Contents/section0.xml'))
        ns={'hp':'http://www.hancom.co.kr/hwpml/2011/paragraph'}
        assert not section.findall('.//hp:checkBtn',ns)
        text=''.join(section.itertext())
        for label in labels:
            assert ('☑' if selected==label else '☐')+' '+label in text
        assert text.count('☑') == bool(selected)
    invalid=subprocess.run([sys.executable,str(system/'scripts/report_loop.py'),'update','--session',sid,'--fields-json',json.dumps({'report_purpose':'알 수 없는 목적'},ensure_ascii=False)],capture_output=True)
    rejected=subprocess.run([sys.executable,str(system/'scripts/report_loop.py'),'generate','--session',sid],capture_output=True)
    assert rejected.returncode != 0
print('PASS: fresh project, sanitized form, HWPX generation, format checks, finalize, preview')
