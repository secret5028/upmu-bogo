# 외부 라이브러리

소스 배포 ZIP에는 의존성 사본이 없으며 소스 설치 시 공식 패키지 저장소에서 내려받습니다. EXE 설치본에는 Python 3.13.17 임베디드 런타임, Node.js 26.13.1 및 고정된 의존성이 포함됩니다. Python 라이선스는 runtime/python/LICENSE.txt, Node.js 라이선스는 runtime/node/LICENSE, Python 패키지의 라이선스는 각 dist-info, Node 패키지의 라이선스는 각 패키지 디렉터리에 포함됩니다. Inno Setup 7.1.1은 설치파일 제작 도구입니다.

| 라이브러리 | 용도 | 라이선스 / 원본 |
|---|---|---|
| kordoc 4.24.70 | HWP 파싱, HWPX 편집·검증·렌더링 | MIT, https://github.com/chrisryugj/kordoc |
| master-of-hwp 0.2.4 | HWPX 문단 읽기·검증 | MIT, https://github.com/reallygood83/master-of-hwp |
| lxml | XML 처리 | BSD, https://lxml.de/ |
| openpyxl | 첨부 XLSX 텍스트 읽기 | MIT, https://openpyxl.readthedocs.io/ |
| pypdf | PDF 텍스트 읽기 | BSD-3-Clause, https://pypdf.readthedocs.io/ |

각 의존성과 전이 의존성의 라이선스는 해당 설치 패키지를 따릅니다. 한컴오피스·상용 글꼴·AI 계정은 포함하지 않습니다.
