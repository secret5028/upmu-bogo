"""Real local HTTP generate -> HTML -> finalize, with Hancom forbidden."""
import json, os, shutil, sys, tempfile, threading, urllib.request
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import server

with tempfile.TemporaryDirectory(prefix='preview-flow-') as td:
    server.PROJECT=Path(td); system=server.PROJECT/'99_시스템'
    (system/'scripts').mkdir(parents=True)
    target=server.PROJECT/'50_문서템플릿/업무보고/기본 업무보고.hwpx'
    target.parent.mkdir(parents=True)
    shutil.copy2(ROOT/'assets/approved.hwpx',target)
    shutil.copy2(ROOT/'engine/report_loop.py',system/'scripts/report_loop.py')
    shutil.copy2(ROOT/'defaults/report-header.json',system/'report-header.json')
    (system/'kordoc-runtime.json').write_text(json.dumps({'node':shutil.which('node'),'cli':str(ROOT/'node_modules/kordoc/dist/cli.js')}),encoding='utf-8')
    server.engine('build-profiles')
    http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);server.PORT=http.server_port
    threading.Thread(target=http.serve_forever,daemon=True).start()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(route,data=None):
        req=urllib.request.Request(f'http://127.0.0.1:{server.PORT}'+route,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type':'application/json','X-Report-Token':server.TOKEN,'X-Progress-Id':'preview_flow_test_1234'})
        try:return opener.open(req,timeout=120)
        except urllib.error.HTTPError as e:raise AssertionError(e.read().decode()) from e
    try:
        with patch.object(server,'hancom_pages',side_effect=AssertionError('Default flow launched Hancom')):
            fields={'title':'미리보기 연결 검증','report_date':'2026-11-26','report_purpose':'회의자료','target_pages':'auto',
                    'report_body':'□ 확인사항\n○ **(심의방법)** 기호·공백 보존\n○ 위첨자^{*} 확인\n※ 주석 확인',
                    'reference_body':'참고 1 별도 참고자료\n○ 별도 참고자료 확인'}
            made=json.load(request('/api/generate',{'fields':fields}))
            assert not made.get('preview_error'),made
            sid=made['session']['id']
            assert made['session']['page_assessment']['pages']==1
            assert made['session']['page_assessment']['total_pages']==2
            result=request('/api/preview?id='+sid);html=result.read().decode()
            assert 'text/html' in result.headers['Content-Type'] and 'Kordoc Local Human' in html
            assert "font-src data:" in result.headers['Content-Security-Policy']
            saved=json.load(request('/api/finalize',{'id':sid,'reviewed':True,'remember_example':False}))
            assert saved['status']=='finalized' and Path(saved['web']['saved_path']).is_file()
            progress=json.load(request('/api/progress?id=preview_flow_test_1234'))
            print(json.dumps({'status':saved['status'],'pages':made['session']['page_assessment'],'progress':progress},ensure_ascii=False))
    finally:http.shutdown();http.server_close()
