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
    fields={'title':'배포본 설치 검증','report_date':'2026-11-13','report_body':'□ 검증개요\n❍ 새 설치 환경에서 보고서 생성\n□ 확인결과\n❍ 기호와 서식 보존\n- 개인정보 없는 기본 양식 사용\n※ 주석의  공백·기호 보존\n※**강조 주석** 확인\n❍ 주석 뒤의 항목도 보존\n❍ **반복** 반복\n❍ 반복\n□ **강조 소제목**\n- **세부 강조**'}
    call('update','--session',sid,'--fields-json',json.dumps(fields,ensure_ascii=False))
    made=call('generate','--session',sid)
    assert all(made['verification'].values()),made
    ns={'hp':'http://www.hancom.co.kr/hwpml/2011/paragraph'}
    with zipfile.ZipFile(made['draft']) as z:
        document=ET.fromstring(z.read('Contents/section0.xml'))
    body=[p for p in document if p.tag.endswith('}p')]
    text=lambda p: ''.join(p.itertext())
    note=next(p for p in body if '※ 주석의  공백·기호 보존' in text(p))
    detail=next(p for p in body if '- 개인정보 없는 기본 양식 사용' in text(p))
    assert note.get('paraPrIDRef')==detail.get('paraPrIDRef')
    assert [r.get('charPrIDRef') for r in note.findall('hp:run',ns)]==[r.get('charPrIDRef') for r in detail.findall('hp:run',ns)]
    with zipfile.ZipFile(made['draft']) as z:
        head=ET.fromstring(z.read('Contents/header.xml'))
    hn={'hh':'http://www.hancom.co.kr/hwpml/2011/head'}
    styles={p.get('id'):p for p in head.findall('.//hh:charPr',hn)}
    repeated=[p for p in body if '반복' in text(p)]
    boldtexts=lambda p: ''.join(''.join(r.itertext()) for r in p.findall('hp:run',ns) if styles[r.get('charPrIDRef')].find('hh:bold',hn) is not None)
    assert len(repeated)==2 and boldtexts(repeated[0])=='반복' and boldtexts(repeated[1])==''
    with zipfile.ZipFile(template) as z:
        originalhead=ET.fromstring(z.read('Contents/header.xml'))
    originalstyles={p.get('id'):p for p in originalhead.findall('.//hh:charPr',hn)}
    body_style_ids={r.get('charPrIDRef') for p in body if text(p).strip().startswith(('□','❍','-','※')) for r in p.findall('hp:run',ns)}
    for identifier,style in styles.items():
        if identifier not in body_style_ids or identifier in originalstyles or style.find('hh:bold',hn) is None:continue
        # New emphasis styles may differ only in id/bold from an approved style.
        def signature(element):
            clone=ET.fromstring(ET.tostring(element));clone.attrib.pop('id',None)
            bold=clone.find('hh:bold',hn)
            if bold is not None:clone.remove(bold)
            return ET.tostring(clone)
        assert any(signature(style)==signature(base) for base in originalstyles.values())
    call('finalize','--session',sid)
    saved=json.loads((system/'작성세션'/f'{sid}.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(Path(saved['final']).read_bytes()).hexdigest()==saved['draft_sha256']
    preview=project/'preview.svg'
    subprocess.run([node,str(cli),'render',saved['final'],'-o',str(preview),'--silent'],check=True,capture_output=True)
    assert '※' in preview.read_text(encoding='utf-8')
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
    # Persisted rule works without markup and on fresh sessions; parentheses are bold too.
    (system/'report-memory.json').write_text(json.dumps({'formatting':{'bold_item_labels':True}}),encoding='utf-8')
    for request in ['첫 보고서','새 보고서']:
        rule_sid=call('start','--request',request)['session_id']
        call('update','--session',rule_sid,'--fields-json',json.dumps({'title':request,'report_date':'2026-11-23','report_body':'□ 개요\n❍ (대    상) 일반 본문 (추가 설명)\n❍ **(검토목적)** 일반 본문\n❍ (2026. 11. 23.) 날짜\n※ 주석 유지'},ensure_ascii=False))
        rule=call('generate','--session',rule_sid)
        assert all(rule['verification'].values())
        with zipfile.ZipFile(rule['draft']) as z:
            section=ET.fromstring(z.read('Contents/section0.xml'));head=ET.fromstring(z.read('Contents/header.xml'))
        styles={p.get('id'):p for p in head.findall('.//hh:charPr',hn)}
        for label in ['대    상','검토목적']:
            paragraph=next(p for p in section if '('+label+')' in ''.join(p.itertext()))
            assert boldtexts(paragraph)=='('+label+')'
        paragraph=next(p for p in section if '날짜' in ''.join(p.itertext()))
        assert not boldtexts(paragraph)
    # Native HWPX objects, not detached tiny text or Unicode substitutes.
    (system/'report-memory.json').write_text(json.dumps({'formatting':{'scan_model_style':True,'circle_font':'바탕'}}),encoding='utf-8')
    annotated=call('start','--request','모범 서식 검증')['session_id']
    call('update','--session',annotated,'--fields-json',json.dumps({'title':'모범 서식 검증','report_date':'2026-11-25','report_body':'□ 개요\n○ {{센터|해킹메일 열람 탐지 확인}}에서 자료^{*} 전달\n○ 보안검토^{**} **강조** 및 일반 자료*\n* 주석 설명\n※ 근거 보존'},ensure_ascii=False))
    made=call('generate','--session',annotated)
    assert made['status']=='draft_ready',made
    with zipfile.ZipFile(made['draft']) as z:
        section=ET.fromstring(z.read('Contents/section0.xml'));head=ET.fromstring(z.read('Contents/header.xml'))
    styles={c.get('id'):c for c in head.findall('.//hh:charPr',hn)}
    ruby=section.find('.//hp:run/hp:dutmal',ns)
    assert ruby is not None and ruby.get('posType')=='TOP'
    assert ruby.find('hp:mainText',ns).text=='센터' and ruby.find('hp:subText',ns).text=='해킹메일 열람 탐지 확인'
    sup=[r.find('hp:t',ns).text for r in section.findall('.//hp:run',ns) if styles[r.get('charPrIDRef')].find('hh:supscript',hn) is not None]
    assert sup==['*','**'],sup
    circle=next(r for r in section.findall('.//hp:run',ns) if ''.join(r.itertext())=='○')
    ref=styles[circle.get('charPrIDRef')].find('hh:fontRef',hn).get('hangul')
    assert head.find('.//hh:fontface[@lang="HANGUL"]/hh:font[@id="'+ref+'"]',hn).get('face')=='바탕'
    assert '❍' not in ''.join(section.itertext()) and '^{' not in ''.join(section.itertext())
    invalid=subprocess.run([sys.executable,str(system/'scripts/report_loop.py'),'update','--session',sid,'--fields-json',json.dumps({'report_purpose':'알 수 없는 목적'},ensure_ascii=False)],capture_output=True)
    rejected=subprocess.run([sys.executable,str(system/'scripts/report_loop.py'),'generate','--session',sid],capture_output=True)
    assert rejected.returncode != 0
    call('update','--session',sid,'--fields-json',json.dumps({'report_purpose':'결과보고(지시사항등)','reference_body':'참고 1 상세 확인내역\n□ 세부사항\n○ (확인내용) 제공된 자료만 수록\n참고 4 추진일정\n□ 일정\n○ 후속 확인 예정'},ensure_ascii=False))
    appendix=call('generate','--session',sid)
    assert all(appendix['verification'].values()) and appendix['reference_count']==2
    with zipfile.ZipFile(appendix['draft']) as z:appendix_root=ET.fromstring(z.read('Contents/section0.xml'))
    titles=[p for p in appendix_root if ''.join(p.itertext()).strip().startswith('참고 ')]
    assert len(titles)==2 and all(p.get('pageBreak')=='1' for p in titles)
    assert '참고 2 추진일정' in ''.join(titles[1].itertext())
print('PASS: fresh project, sanitized form, HWPX generation, format checks, finalize, preview')
