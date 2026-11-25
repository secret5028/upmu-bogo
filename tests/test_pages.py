"""Page goals use Hancom, never SVG estimates. Run --native for local Hancom QA."""
from pathlib import Path
import sys
import json
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import server

assert server.clean_fields({})['target_pages']=='auto'
assert server.clean_fields({'target_pages':'2'})['target_pages']=='2'
try:server.clean_fields({'target_pages':'3'})
except ValueError:pass
else:raise AssertionError('Invalid target accepted')
with patch.object(server,'hancom_pages',return_value=2):
    assert server.page_assessment(ROOT/'assets/approved.hwpx','1')['fits'] is False
    assert server.page_assessment(ROOT/'assets/approved.hwpx','2')['fits'] is True
with patch.object(server,'hancom_pages',side_effect=ValueError('unavailable')):
    assert server.page_assessment(ROOT/'assets/approved.hwpx','1')['fits'] is None

original=server.clean_fields({'target_pages':'1','title':'분량 검증','report_date':'2026-11-24','report_body':'□ 개요\n❍ 원문 유지'})
over={'fits':False,'pages':3,'message':'3쪽 초과'}
fits={'fits':True,'pages':1,'message':'한글 실제 1쪽'}
proposal=dict(original,report_body='□ 개요\n❍ 요약안',target_pages='2')
with patch.object(server,'measure_fields',side_effect=[over,fits]) as measure, patch.object(server,'ai_raw',return_value=json.dumps(proposal)):
    result=server.fit_draft({'fields':original,'provider':'test'})
    assert result['attempts']==1 and result['fields']['target_pages']=='1'
    assert original['report_body']=='□ 개요\n❍ 원문 유지'
with patch.object(server,'measure_fields',return_value=over), patch.object(server,'ai_raw',return_value=json.dumps(proposal)):
    assert server.fit_draft({'fields':original})['attempts']==3
with patch.object(server,'artifact',return_value=ROOT/'assets/approved.hwpx'), patch.object(server,'hancom_pages',return_value=1) as native:
    cached=server.page_assessment(ROOT/'assets/approved.hwpx','1')
    with patch.object(server,'webdata',return_value={'page_assessment':cached}):
        assert server.verified_assessment({'id':'test','fields':{'target_pages':'1'}})['fits']
        assert native.call_count==1
        cached['verified_sha256']='changed'
        server.verified_assessment({'id':'test','fields':{'target_pages':'1'}})
        assert native.call_count==2
print('Page goal, native-only verification, retry limit and original preservation: PASS')

if '--native' in sys.argv:
    import tempfile,shutil,subprocess,os
    node=shutil.which('node') or r'C:\Users\예방\AppData\Local\Programs\UpmuBogo\runtime\node\node.exe'
    with tempfile.TemporaryDirectory(prefix='native-pages-') as td:
        server.PROJECT=Path(td)
        system=server.PROJECT/'99_시스템'
        (system/'scripts').mkdir(parents=True)
        template=server.PROJECT/'50_문서템플릿/업무보고/기본 업무보고.hwpx'
        template.parent.mkdir(parents=True)
        shutil.copy2(ROOT/'assets/approved.hwpx',template)
        shutil.copy2(ROOT/'engine/report_loop.py',system/'scripts/report_loop.py')
        shutil.copy2(ROOT/'defaults/report-header.json',system/'report-header.json')
        (system/'kordoc-runtime.json').write_text(json.dumps({'node':node,'cli':str(ROOT/'node_modules/kordoc/dist/cli.js')}),encoding='utf-8')
        def call(*args):return json.loads(server.run([sys.executable,str(system/'scripts/report_loop.py'),*args]))
        call('build-profiles')
        counts=[]
        for n in (3,24):
            sid=call('start','--request','한글 쪽 수 검증')['session_id']
            fields=dict(original,report_body='□ 검증개요\n'+'\n'.join(f'❍ (확인사항) {i+1}번 항목의 내용과 조치계획을 확인합니다.' for i in range(n)))
            call('update','--session',sid,'--fields-json',json.dumps(fields,ensure_ascii=False))
            made=call('generate','--session',sid)
            assessment=server.page_assessment(made['draft'],'1')
            print(n,assessment,flush=True)
            assert assessment['pages'] is not None
            counts.append(assessment['pages'])
        assert counts[0]==1 and counts[1]>1,counts
    print('Native Hancom short/overflow HWPX verification: PASS')

# Automatic decisions use native pages, and sparse second pages trigger a retry.
with patch.object(server,'hancom_pages',return_value=1):
    a=server.page_assessment(ROOT/'assets/approved.hwpx','auto')
    assert a['target']==1 and a['fits'] and a['mode']=='auto'
with patch.object(server,'hancom_pages',return_value=3):
    a=server.page_assessment(ROOT/'assets/approved.hwpx','auto')
    assert a['target']==2 and not a['fits']
automatic=dict(original,target_pages='auto')
with patch.object(server,'measure_fields',return_value=fits) as measure, patch.object(server,'ai_raw',return_value=json.dumps(proposal)):
    result=server.fit_draft({'fields':automatic,'_assessment':dict(over,target=2)})
    assert result['fields']['target_pages']=='auto' and result['attempts']==1
    assert measure.call_args.args[0]['report_body']=='□ 개요\n❍ 요약안'
with patch.object(server,'measure_fields',return_value=dict(fits,target=1)), patch.object(server,'ai_raw') as ai:
    assert server.fit_draft({'fields':automatic})['attempts']==0
    ai.assert_not_called()
with patch.object(server,'measure_fields',return_value=dict(over,target=2)), patch.object(server,'ai_raw',side_effect=ValueError('offline')):
    try:server.fit_draft({'fields':automatic})
    except ValueError:pass
    else:raise AssertionError('AI failure was hidden')
    assert automatic['report_body']==original['report_body']
print('Automatic page choice, summary retries, AI failure preservation: PASS')

import tempfile, hashlib
from unittest.mock import MagicMock
with tempfile.TemporaryDirectory() as td, patch.object(server,'PROJECT',Path(td)), patch.object(server,'hancom_pages',return_value=2):
    pdf=Path(td)/'99_시스템/웹미리보기'/(hashlib.sha256((ROOT/'assets/approved.hwpx').read_bytes()).hexdigest()+'.pdf')
    pdf.parent.mkdir(parents=True);pdf.touch()
    page=MagicMock();page.extract_text.return_value='짧게 넘친 마지막 항목'
    with patch('pypdf.PdfReader') as reader:
        reader.return_value.pages=[page,page]
        result=server.page_assessment(ROOT/'assets/approved.hwpx','auto')
        assert result['target']==1 and not result['fits']
        page.extract_text.return_value='상세 일정 및 역할 분담 '*60
        result=server.page_assessment(ROOT/'assets/approved.hwpx','auto')
        assert result['target']==2 and result['fits']
print('Sparse second page versus substantial second page: PASS')

if '--engine' in sys.argv:
    import shutil
    with tempfile.TemporaryDirectory() as td, patch.object(server,'PROJECT',Path(td)), patch.object(server,'hancom_pages',return_value=1):
        project=Path(td);system=project/'99_시스템';(system/'scripts').mkdir(parents=True)
        template=project/'50_문서템플릿/업무보고/기본 업무보고.hwpx';template.parent.mkdir(parents=True)
        shutil.copy2(ROOT/'assets/approved.hwpx',template)
        shutil.copy2(ROOT/'engine/report_loop.py',system/'scripts/report_loop.py')
        (system/'kordoc-runtime.json').write_text(json.dumps({'node':shutil.which('node'),'cli':str(ROOT/'node_modules/kordoc/dist/cli.js')}),encoding='utf-8')
        result=server.measure_fields(automatic)
        assert result['pages']==1 and result['fits']
    print('Fresh measurement project with real engine: PASS')
