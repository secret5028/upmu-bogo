import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import json,tempfile,time
from pathlib import Path
import server
from corpus import Corpus

def wait(c):
    deadline=time.time()+30
    while c.status()['job']['state']=='running':
        assert time.time()<deadline,'job timeout'
        time.sleep(.03)
    return c.status()

with tempfile.TemporaryDirectory() as td:
    root=Path(td);project=root/'project';(project/'99_시스템').mkdir(parents=True)
    folder=root/'reports';folder.mkdir()
    first='□ 조사개요\n❍ 화재안전조사 실시\n□ 조사결과\n❍ 폐기물 적치 확인\n□ 조치계획\n❍ 시정 요청'
    (folder/'폐기물 조사.txt').write_text(first,encoding='utf-8')
    (folder/'복사본.txt').write_text(first,encoding='utf-8')
    (folder/'긴 보고.txt').write_text('□ 긴자료\n'+('문장\n'*16000)+'❍ 끝부분고유검색어',encoding='utf-8')
    (folder/'손상.hwpx').write_bytes(b'not a zip')
    c=Corpus(project,server.extract_text,server.run);c.configure([str(folder)]);c.start();s=wait(c)
    assert s['job']['state']=='done' and s['stats']['files']==4 and s['stats']['documents']==2 and s['stats']['duplicates']==1 and s['stats']['failed']==1,s
    assert '끝부분고유검색어' in c.references('끝부분고유검색어')[0]['text']
    assert c.references('폐기물 화재안전조사')[0]['headings']==['□ 조사개요','□ 조사결과','□ 조치계획']
    c.start();s=wait(c);assert s['stats']['parsed']==0 and s['stats']['reused']==3,s
    (folder/'폐기물 조사.txt').write_text(first+'\n❍ 변경자료',encoding='utf-8')
    (folder/'복사본.txt').unlink() # Disposable test fixture only.
    c.start();s=wait(c);assert s['stats']['parsed']==1 and s['stats']['removed']==1,s
    c.start(True);s=wait(c);assert s['stats']['parsed']==2,s
    calls=[]
    def ask(prompt,provider):calls.append(prompt);return {'rules':'업무 유형별 소제목을 유지한다.','summary':'관찰한 구조 요약'}
    c.start_analysis('mock',ask);s=wait(c);assert s['analysis']['analyzed_documents']==2 and len(calls)==2,s
    assert s['analysis']['applied'] is False
    previous=c.index();folder.rename(root/'moved');c.start();s=wait(c);assert s['job']['state']=='error' and c.index()==previous
    other=root/'other';other.mkdir();c.configure([str(other)]);assert c.status()['needs_build'] and not c.references('폐기물')
print('PASS: full text, hashing, duplicate collapse, incremental update, removal, force rebuild, partial failure, inaccessible root preservation, search, all-document analysis')
