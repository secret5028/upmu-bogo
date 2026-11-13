import argparse
import os
import shutil
import subprocess
import tempfile
import hashlib
from copy import deepcopy
from lxml import etree as ET
from io import BytesIO
import html
import json
import re
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "99_시스템" / "python-packages"
sys.path.insert(0, str(PKG))
from master_of_hwp import HwpDocument

PROFILE_PATH = ROOT / "99_시스템" / "업무보고_템플릿_프로필.json"
SESSION_DIR = ROOT / "99_시스템" / "작성세션"
DRAFT_DIR = ROOT / "60_작성중"
FINAL_DIR = ROOT / "70_완성문서"

FIELD_LABELS = {
    "title": "업무보고 제목",
    "report_date": "보고일자",
    "event_datetime": "업무 일시",
    "place": "장소",
    "reporter": "보고자",
    "reporter_contact": "보고자 연락처 또는 내선번호",
    "attendees": "참석자",
    "main_content": "주요 내용",
    "result_or_issue": "확인 결과 또는 문제점",
    "action_plan": "조치사항 또는 향후계획",
    "report_body": "구성된 보고서 본문",
}
QUESTIONS = {
    "title": "업무보고 제목은 무엇으로 할까요?",
    "report_date": "보고일자는 언제인가요? 예: ‘26. 7. 18.(토)",
    "event_datetime": "실제 업무 일시는 언제인가요?",
    "place": "장소 또는 대상 소재지는 어디인가요?",
    "reporter": "보고자는 누구로 할까요?",
    "reporter_contact": "보고자의 내선번호 또는 연락처는 무엇인가요? 문서에 표시하지 않으려면 '표시 안 함'이라고 해주세요.",
    "attendees": "참석자 또는 수행자는 누구인가요? 없다면 '해당 없음'이라고 해주세요.",
    "main_content": "주요 수행·확인 내용은 무엇인가요?",
    "result_or_issue": "확인 결과나 문제점은 무엇인가요?",
    "action_plan": "조치사항이나 향후계획은 무엇인가요? 없다면 '해당 없음'이라고 해주세요.",
}
REQUIRED = [k for k in FIELD_LABELS if k != "report_body"]


def load_profiles():
    if not PROFILE_PATH.exists():
        build_profiles()
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def build_profiles():
    profiles = []
    for path in sorted((ROOT / "50_문서템플릿").rglob("*.hwpx")):
        if "업무보고" not in path.name or any(x in path.parts for x in ("60_작성중", "70_완성문서", "30_정제문서")):
            continue
        try:
            doc = HwpDocument.open(path)
            paras = list(doc.iter_paragraphs())
            headings = [t.strip() for _, _, t in paras if re.match(r"^[□■]", t.strip())]
            labels = []
            for _, _, text in paras:
                m = re.match(r"^\s*[○◦]\s*\(?([^():]{1,14})\)?\s*[:：]", text)
                if m:
                    labels.append(re.sub(r"\s+", "", m.group(1)))
            profiles.append({
                "path": str(path),
                "title": path.stem,
                "summary": doc.summary(),
                "headings": headings,
                "labels": sorted(set(labels)),
                "paragraphs": [{"section": s, "index": i, "text": t} for s, i, t in paras],
            })
        except Exception as exc:
            print(f"PROFILE_FAIL {path.name}: {exc}", file=sys.stderr)
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "profiles_built", "count": len(profiles), "path": str(PROFILE_PATH)}, ensure_ascii=False))


def tokens(text):
    stop = {"업무보고", "보고", "결과", "계획", "관련", "대한", "작성", "만들어줘", "내용으로"}
    return {x for x in re.findall(r"[가-힣A-Za-z0-9]{2,}", text.lower()) if x not in stop}


def select_template(request, profiles):
    wanted = tokens(request)
    scored = []
    for p in profiles:
        corpus = " ".join([p["title"], *p["headings"], *p["labels"]])
        score = len(wanted & tokens(corpus)) * 10
        if "현장" in request and "현장" in corpus:
            score += 8
        if "예찰" in request and "예찰" in corpus:
            score += 12
        if "계획" in request and "계획" in corpus:
            score += 8
        scored.append((score, p["title"], p))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored[0][2]


def infer_fields(request):
    fields = {}
    date = re.search(r"(?:20\d{2}[.년\-/ ]*)?\d{1,2}[.월\-/ ]+\d{1,2}(?:일)?(?:\s*\([^)]*\))?(?:\s*\d{1,2}(?::\d{2})?\s*(?:시|분)?)?", request)
    if date:
        fields["event_datetime"] = date.group(0).strip()
    title = re.sub(r"(?:한글|hwpx?|업무보고|파일|문서|만들어줘|작성해줘)", " ", request, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" ,")
    if title:
        fields["title"] = title[:80] + " 업무보고"
    fields["main_content"] = request.strip()
    return fields


def session_path(sid):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
        raise ValueError("잘못된 세션 ID")
    return SESSION_DIR / f"{sid}.json"


def save_session(data):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_path(data["id"]).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(sid):
    return json.loads(session_path(sid).read_text(encoding="utf-8"))


def missing_fields(session):
    if str(session['fields'].get('report_body','')).strip():
        return [k for k in ('title','report_date') if not str(session['fields'].get(k,'')).strip()]
    fixed = {"reporter", "reporter_contact"} if (ROOT / "99_시스템/report-header.json").exists() else set()
    return [x for x in REQUIRED if x not in fixed and not str(session["fields"].get(x, "")).strip()]


def response(session):
    missing = missing_fields(session)
    return {
        "status": "need_input" if missing else "ready",
        "session_id": session["id"],
        "selected_template": session["template"]["path"],
        "fields": session["fields"],
        "missing_fields": missing,
        "questions": [QUESTIONS[x] for x in missing],
    }


def start(request):
    profiles = load_profiles()
    chosen = next((p for p in profiles if Path(p["path"]).name == APPROVED_RELATIVE.name), None)
    if chosen is None:
        raise RuntimeError("승인 양식 프로필이 없습니다. build-profiles를 실행하세요.")
    session = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "request": request,
        "template": chosen,
        "fields": infer_fields(request),
        "history": [{"role": "user", "text": request}],
        "iterations": 0,
    }
    save_session(session)
    print(json.dumps(response(session), ensure_ascii=False, indent=2))


def update(sid, fields_json):
    session = load_session(sid)
    incoming = json.loads(fields_json)
    for key, value in incoming.items():
        if key in FIELD_LABELS and value is not None:
            session["fields"][key] = str(value).strip()
    session["history"].append({"role": "user", "fields": incoming})
    session["iterations"] += 1
    session["status"] = "edited"
    for key in ("verification", "draft_sha256"):
        session.pop(key, None)
    save_session(session)
    print(json.dumps(response(session), ensure_ascii=False, indent=2))


def split_items(text):
    # Split Korean prose sentences, but never split numeric dates such as
    # "2026. 7. 21." at the spaces following their dots.
    parts = re.split(r"(?:\r?\n|(?<=[가-힣]\.)\s+|(?<=[!?])\s+|\s*[;]\s*)", text)
    return [re.sub(r"^[\-○•·]\s*", "", x).strip() for x in parts if x.strip()]


_HP_TOKEN_RE = re.compile(rb"<hp:p\b[^>]*>|</hp:p>|<hp:t\b[^>]*>|</hp:t>")


def _paragraph_byte_ranges(xml_bytes):
    """Return hp:p ranges in document order without rewriting XML."""
    ranges = []
    stack = []
    for match in _HP_TOKEN_RE.finditer(xml_bytes):
        token = match.group(0)
        if token.startswith(b"<hp:p"):
            index = len(ranges)
            ranges.append([match.start(), None])
            stack.append(index)
        elif token == b"</hp:p>":
            if not stack:
                raise RuntimeError("HWPX hp:p 닫기 태그 불균형")
            index = stack.pop()
            ranges[index][1] = match.end()
    if stack or any(end is None for _, end in ranges):
        raise RuntimeError("HWPX hp:p 태그 불균형")
    return [(start, end) for start, end in ranges]


def _direct_text_content_ranges(xml_bytes, paragraph_range):
    """Return content spans of hp:t nodes belonging directly to one hp:p."""
    start, end = paragraph_range
    depth = 0
    open_t = None
    spans = []
    for match in _HP_TOKEN_RE.finditer(xml_bytes, start, end):
        token = match.group(0)
        if token.startswith(b"<hp:p"):
            depth += 1
        elif token == b"</hp:p>":
            depth -= 1
        elif token.startswith(b"<hp:t") and depth == 1:
            open_t = match.end()
        elif token == b"</hp:t>" and depth == 1 and open_t is not None:
            spans.append((open_t, match.start()))
            open_t = None
    return spans


def _replace_section_bytes(xml_bytes, changes):
    paragraphs = _paragraph_byte_ranges(xml_bytes)
    operations = []
    for index, new_text in changes.items():
        if not 0 <= index < len(paragraphs):
            raise IndexError(f"paragraph_index {index} out of range")
        spans = _direct_text_content_ranges(xml_bytes, paragraphs[index])
        if not spans:
            raise RuntimeError(f"문단 {index}에 직접 hp:t 노드가 없어 안전 교체 불가")
        safe_text = new_text if new_text else " "
        replacement = html.escape(safe_text, quote=False).encode("utf-8")
        operations.append((spans[0][0], spans[0][1], replacement))
        for extra_start, extra_end in spans[1:]:
            operations.append((extra_start, extra_end, b" "))
        para_start, para_end = paragraphs[index]
        para_bytes = xml_bytes[para_start:para_end]
        for match in re.finditer(rb"<hp:linesegarray\b[^>]*>.*?</hp:linesegarray>", para_bytes, re.S):
            operations.append((para_start + match.start(), para_start + match.end(), b""))
    result = xml_bytes
    for start, end, replacement in sorted(operations, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result


def replace_hwpx_preserving_package(template, replacements):
    """Replace paragraph text without reserializing Hancom XML.

    master-of-hwp 0.2.4 uses xml.etree for writes, which rewrites the original
    hp/hs/hc prefixes to ns0/ns1. Hancom Office rejects some such documents.
    Only byte spans inside existing hp:t elements are changed. All tags,
    namespace declarations, whitespace, attribute order, and unused namespace
    declarations remain byte-identical to the source document.
    """
    template = Path(template)
    with zipfile.ZipFile(template, "r") as src:
        entries = [(info, src.read(info.filename)) for info in src.infolist()]
        section_names = sorted(
            [n for n in src.namelist() if re.fullmatch(r"Contents/section\d+\.xml", n, re.I)],
            key=lambda n: int(re.search(r"(\d+)", n).group(1)),
        )
    grouped = {}
    for section, index, text in replacements:
        grouped.setdefault(section, {})[index] = text

    updated = []
    for info, data in entries:
        if info.filename not in section_names:
            updated.append((info, data))
            continue
        section_index = section_names.index(info.filename)
        changes = grouped.get(section_index, {})
        if not changes:
            updated.append((info, data))
            continue
        data = _replace_section_bytes(data, changes)
        updated.append((info, data))

    output = BytesIO()
    with zipfile.ZipFile(output, "w") as dst:
        for info, data in updated:
            dst.writestr(info, data)
    return output.getvalue()


def find_header_indices(paras):
    result = {"title": None, "report_date": None, "reporter": None, "reporter_contact": None}
    first_body_pos = next((pos for pos, (_, _, text) in enumerate(paras) if re.match(r"^[□■]", text.strip())), len(paras))
    title_candidates = []
    for pos, (s, i, text) in enumerate(paras):
        t = text.strip()
        if t in {"일자", "일시", "보고일자"} and pos + 1 < len(paras):
            result["report_date"] = paras[pos + 1][:2]
        if t == "보고자":
            # Last staff-name slot before the '보고' header.
            for ss, ii, tt in paras[pos + 1:]:
                if tt.strip() == "보고":
                    break
                if re.search(r"[가-힣]{2,4}\s*\(\d+\)", tt):
                    result["reporter"] = (ss, ii)
                    # The next paragraph is normally the contact/extension cell.
                    next_pos = next((k for k, (xs, xi, _) in enumerate(paras) if xs == ss and xi == ii), None)
                    if next_pos is not None and next_pos + 1 < len(paras):
                        result["reporter_contact"] = paras[next_pos + 1][:2]
        if 14 < pos < first_body_pos and t and not re.match(r"^(보고목적|방침필요|일자|일시|보고)$", t) and not t.startswith("방침필요"):
            title_candidates.append((s, i))
    if title_candidates:
        result["title"] = title_candidates[-1]
    return result


# Kordoc output pipeline. The approved HWPX is the formatting authority.
NS = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph", "hh": "http://www.hancom.co.kr/hwpml/2011/head"}
HP = "{" + NS["hp"] + "}"
APPROVED_RELATIVE = Path("50_문서템플릿/업무보고/기본 업무보고.hwpx")


def direct_text(p):
    return "".join(p.xpath("./hp:run/hp:t//text()", namespaces=NS))


def visible(value):
    return "" if value in {"표시 안 함", "공란"} else value


def normalize_date(value):
    # Normalize only full-year dates; do not infer an omitted year.
    m = re.match(r"^(20\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})\.?\s*(?:\(([월화수목금토일])\))?", value)
    if not m:
        return value
    day = datetime(int(m[1]), int(m[2]), int(m[3]))
    weekday = "월화수목금토일"[day.weekday()]
    if m[4] and m[4] != weekday:
        raise ValueError(f"날짜와 요일 불일치: {value} → {weekday}요일")
    tail = value[m.end():].strip()
    return f"{day.year}. {day.month}. {day.day}.({weekday})" + (" " + tail if tail else "")


def body_lines(fields):
    if fields.get('report_body') and fields['report_body'] != '[확인 필요]':
        lines=[]
        for raw in fields['report_body'].splitlines():
            text=html.unescape(raw).strip()
            if not text:continue
            text=re.sub(r'\*\*(.*?)\*\*',r'\1',text)
            if text.startswith('□'):lines.append('□ '+text[1:].lstrip())
            elif text.startswith(('❍','○','◦','•')):lines.append('  ❍ '+text[1:].lstrip())
            elif re.match(r'^[-–]\s',text):lines.append('    - '+text[1:].lstrip())
            else:raise ValueError('보고서 본문의 각 항목은 □, ❍, - 기호로 시작해야 합니다: '+text[:60])
        if not lines or not lines[0].startswith('□'):raise ValueError('보고서 본문에 소제목이 필요합니다.')
        return lines
    lines = ["□ 보고개요", f"  ❍ 일    시: {fields['event_datetime']}",
             f"  ❍ 장    소: {fields['place']}",
             f"  ❍ 참 석 자: {fields['attendees']}", "□ 주요내용"]
    for heading, key in [(None, "main_content"), ("□ 확인 결과 및 문제점", "result_or_issue"),
                         ("□ 조치사항 및 향후계획", "action_plan")]:
        if heading:
            lines.append(heading)
        for item in fields[key].splitlines():
            item = item.strip()
            if not item:
                continue
            if re.match(r"^[-–]\s", item):
                lines.append("    - " + re.sub(r"^[-–]\s*", "", item))
            else:
                lines.append("  ❍ " + re.sub(r"^[❍○◦•·]\s*", "", item))
    return lines


def kordoc_cli(*args):
    cfgpath = ROOT / "99_시스템/kordoc-runtime.json"
    cfg = json.loads(cfgpath.read_text(encoding="utf-8")) if cfgpath.exists() else {}
    node = cfg.get("node") or shutil.which("node.exe") or shutil.which("node")
    cli = Path(cfg.get("cli", ROOT / "99_시스템/kordoc/node_modules/kordoc/dist/cli.js"))
    if not node or not cli.is_file():
        raise RuntimeError("kordoc 실행환경이 없습니다. 99_시스템/kordoc-runtime.json을 확인하세요.")
    env = dict(os.environ, KORDOC_OFFLINE="1", NO_COLOR="1")
    completed = subprocess.run([node, str(cli), *map(str, args)], capture_output=True,
                               encoding="utf-8", errors="replace", timeout=180, env=env)
    if completed.returncode:
        raise RuntimeError(f"kordoc 실패({completed.returncode}): {completed.stderr[-2000:]} {completed.stdout[-2000:]}")
    return completed.stdout


def _package(entries, section, preview=None):
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as z:
        for info, data in entries:
            if info.filename == "Contents/section0.xml":
                data = section
            elif info.filename == "Preview/PrvText.txt" and preview is not None:
                data = preview.encode("utf-8")
            elif info.filename == "Preview/PrvImage.png":
                continue  # Never show an unrelated template thumbnail.
            z.writestr(info, data)
    return output.getvalue()


def _xml(root):
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)


def _clear_layout(root):
    for node in list(root.findall(".//hp:linesegarray", NS)):
        node.getparent().remove(node)


def _plain(p, text):
    runs = p.findall("hp:run", NS)
    candidates = [r for r in runs if r.find("hp:t", NS) is not None]
    if not candidates:
        raise RuntimeError("승인 양식에 글자 서식 슬롯이 없습니다.")
    # Select an existing content run, not an empty leading run or symbol run.
    chosen = max(candidates, key=lambda r: len("".join(r.itertext()).strip()))
    for run in candidates:
        for t in run.findall("hp:t", NS):
            for c in list(t):
                t.remove(c)
            t.text = " "
    chosen.find("hp:t", NS).text = text or " "


def _styled(proto, text):
    """Reuse exact approved paragraph/run attributes; change text only."""
    p = deepcopy(proto)
    runs = p.findall("hp:run", NS)
    if any(any(c.tag != HP + "t" for c in r) for r in runs):
        raise RuntimeError("본문 원형에 개체가 포함되어 있습니다.")
    glyph = "□" if text.startswith("□") else "❍" if text.lstrip().startswith("❍") else None
    if glyph:
        symbol = next((r for r in runs if "".join(r.itertext()).strip() == glyph), None)
        if symbol is None:
            raise RuntimeError(f"승인 양식에 {glyph} 기호 전용 서식이 없습니다.")
        body = max((r for r in runs if r is not symbol), key=lambda r: len("".join(r.itertext()).strip()))
        prefix, suffix = text.split(glyph, 1)
        for r in runs:
            p.remove(r)
        for ref, value in [(body, prefix), (symbol, glyph), (body, suffix)]:
            r = ET.Element(HP + "run", attrib=dict(ref.attrib))
            ET.SubElement(r, HP + "t").text = value
            p.append(r)
    else:
        _plain(p, text)
    p.set("id", "0")
    _clear_layout(p)
    return p


def generate(sid, force=False):
    session = load_session(sid)
    missing = missing_fields(session)
    if missing and not force:
        print(json.dumps(response(session), ensure_ascii=False, indent=2))
        raise SystemExit(2)
    fields = {k: str(session["fields"].get(k, "") or "[확인 필요]") for k in FIELD_LABELS}
    for key in ["report_date", "event_datetime"]:
        fields[key] = normalize_date(fields[key])
    lines = body_lines(fields)
    # A single explicitly approved form prevents unrelated forms from silently changing fonts.
    template = ROOT / APPROVED_RELATIVE
    with zipfile.ZipFile(template) as z:
        entries = [(i, z.read(i.filename)) for i in z.infolist()]
    original = {i.filename: data for i, data in entries}
    root = ET.fromstring(original["Contents/section0.xml"])
    allp = root.findall(".//hp:p", NS)
    paras = [(0, i, direct_text(p)) for i, p in enumerate(allp)]
    headers = find_header_indices(paras)
    first = next(p for p in root if p.tag == HP + "p" and direct_text(p).strip().startswith("□"))
    prototypes = {
        "□": first,
        "❍": next(p for p in root if direct_text(p).strip().startswith("❍") and any("".join(r.itertext()).strip() == "❍" for r in p.findall("hp:run", NS))),
        "-": next(p for p in root if direct_text(p).strip().startswith("-")),
    }
    # Explicit user emphasis uses a bold variant of the approved body font.
    emphasis=set(re.findall(r'\*\*([^*\r\n]+)\*\*',fields.get('report_body','')))
    bold_id=None
    if emphasis:
        head=ET.fromstring(original['Contents/header.xml'])
        charprs=head.find('.//hh:charProperties',NS)
        body_run=max(prototypes['❍'].findall('hp:run',NS),key=lambda r:len(''.join(r.itertext()).strip()))
        base=next(c for c in charprs if c.get('id')==body_run.get('charPrIDRef'))
        bold=deepcopy(base);bold_id=str(max(int(c.get('id')) for c in charprs)+1);bold.set('id',bold_id)
        if bold.find('hh:bold',NS) is None:ET.SubElement(bold,'{'+NS['hh']+'}bold')
        charprs.append(bold);charprs.set('itemCnt',str(len(charprs)))
        original['Contents/header.xml']=_xml(head)
        entries=[(i,original['Contents/header.xml'] if i.filename=='Contents/header.xml' else data) for i,data in entries]
    for key in ["title", "report_date", "reporter", "reporter_contact"]:
        if headers[key] is None:
            raise RuntimeError(f"승인 양식의 {key} 입력란을 찾지 못했습니다.")
    # A configured reporting header is reusable; the report date remains dynamic.
    header_config = ROOT / "99_시스템/report-header.json"
    fixed_header = json.loads(header_config.read_text(encoding="utf-8")) if header_config.exists() else None
    firstpos = allp.index(first)
    if fixed_header:
        for anchor, staff in zip(["예방안전과장", "예방지도팀장", "예방지도주임"], fixed_header["staff"]):
            slots = [i for i, p in enumerate(allp[:firstpos]) if direct_text(p).strip() == anchor]
            if len(slots) != 1 or slots[0] + 2 >= firstpos:
                raise RuntimeError("고정 보고자 양식 입력란을 찾지 못했습니다: " + staff["role"])
            _plain(allp[slots[0]], staff["role"])
            _plain(allp[slots[0]+1], staff["name"])
            _plain(allp[slots[0]+2], staff["phone"])
        purpose = next((i for i,p in enumerate(allp[:firstpos]) if direct_text(p).strip()=="보고목적"), None)
        if purpose is None:raise RuntimeError("보고목적 입력란을 찾지 못했습니다.")
        _plain(allp[purpose+1], fixed_header["purpose"])
    else:
        for p in allp[:firstpos]:
            val = direct_text(p).strip()
            if re.fullmatch(r"[가-힣]{2,4}\s*\(\d+\)", val) or re.fullmatch(r"\d{2,3}-\d{3,4}-\d{4}", val):
                _plain(p, "")
    for key in (["title", "report_date"] if fixed_header else ["title", "report_date", "reporter", "reporter_contact"]):
        _plain(allp[headers[key][1]], visible(fields[key]))
    # The original short-year date used a narrow cell. Use its existing 9pt
    # header font variant for a full-year date, without changing table geometry.
    if len(fields['report_date'])>14:
        head=ET.fromstring(original['Contents/header.xml'])
        styles={c.get('id'):c for c in head.findall('.//hh:charPr',NS)}
        for run in allp[headers['report_date'][1]].findall('hp:run',NS):
            base=styles.get(run.get('charPrIDRef'))
            if base is None:continue
            face=base.find('hh:fontRef',NS).get('hangul')
            candidate=next((c for c in styles.values() if c.get('height')=='900' and c.find('hh:fontRef',NS).get('hangul')==face),None)
            if candidate is None:
                candidate=deepcopy(base);candidate.set('id',str(max(int(k) for k in styles)+1));candidate.set('height','900')
                props=head.find('.//hh:charProperties',NS);props.append(candidate);props.set('itemCnt',str(len(props)))
                styles[candidate.get('id')]=candidate
            run.set('charPrIDRef',candidate.get('id'))
        original['Contents/header.xml']=_xml(head)
        entries=[(i,original['Contents/header.xml'] if i.filename=='Contents/header.xml' else data) for i,data in entries]
    # Keep header/title tables; discard old report body. Expand by role, not fixed indices.
    start_index = list(root).index(first)
    for child in list(root)[start_index:]:
        root.remove(child)
    expected = []
    markers = {}
    for i, line in enumerate(lines):
        role = "□" if line.startswith("□") else "❍" if line.lstrip().startswith("❍") else "-"
        target = _styled(prototypes[role], line)
        if bold_id:
            for run in list(target.findall('hp:run',NS)):
                text=''.join(run.xpath('./hp:t//text()',namespaces=NS))
                matches=list(re.finditer('|'.join(re.escape(x) for x in sorted(emphasis,key=len,reverse=True)),text))
                if not matches:continue
                pos=list(target).index(run);target.remove(run);cursor=0
                parts=[]
                for match in matches:
                    parts.extend([(text[cursor:match.start()],False),(match.group(),True)]);cursor=match.end()
                parts.append((text[cursor:],False))
                for value,is_bold in parts:
                    if not value:continue
                    new=ET.Element(HP+'run',attrib=dict(run.attrib))
                    if is_bold:new.set('charPrIDRef',bold_id)
                    ET.SubElement(new,HP+'t').text=value;target.insert(pos,new);pos+=1
        expected.append(target)
        marker = f"KORDOCBODY{i:05d}TOKEN"
        prefix = "□ " if role == "□" else "  ❍ " if role == "❍" else "    - "
        root.append(_styled(prototypes[role], prefix + marker))
        markers[marker] = line[len(prefix):]
    _clear_layout(root)
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kordoc-report-") as temp:
        temp = Path(temp)
        skeleton, md, raw = temp / "approved.hwpx", temp / "content.md", temp / "generated.hwpx"
        skeleton.write_bytes(_package(entries, _xml(root), ""))
        kordoc_cli(skeleton, "--keep-layout-tables", "--keep-empty-cols", "-o", md)
        markdown = md.read_text(encoding="utf-8")
        for marker, text in markers.items():
            if markdown.count(marker) != 1:
                raise RuntimeError("kordoc 문단 매핑 오류")
            escaped = "".join(f"&#{ord(c)};" if c in "&<>[]*_{}`~|\\" else c for c in text)
            markdown = markdown.replace(marker, escaped)
        md.write_text(markdown, encoding="utf-8")
        patch_result = json.loads(kordoc_cli("patch", skeleton, md, "-o", raw, "--json", "--silent"))
        if not patch_result.get("success") or patch_result.get("skipped"):
            raise RuntimeError("kordoc이 일부 내용을 반영하지 못했습니다.")
        with zipfile.ZipFile(raw) as z:
            produced = [(i, z.read(i.filename)) for i in z.infolist()]
        output_data = {i.filename: d for i, d in produced}
        if output_data["Contents/header.xml"] != original["Contents/header.xml"]:
            raise RuntimeError("kordoc이 승인 양식의 서식 정의를 변경했습니다.")
        made = ET.fromstring(output_data["Contents/section0.xml"])
        body = [p for p in made if direct_text(p).strip().startswith(("□", "❍", "-"))]
        compact = lambda s: re.sub(r"\s+", "", s)
        if len(body) != len(expected) or any(compact(html.unescape(direct_text(p))) != compact(line) for p, line in zip(body, lines)):
            raise RuntimeError("kordoc 생성 내용 불일치: 서식 보정 중단 " + repr([(direct_text(p), line) for p, line in zip(body, lines) if compact(html.unescape(direct_text(p))) != compact(line)]))
        # Content has been produced and checked. Restore whitespace and role-specific runs.
        for actual, formatted in zip(body, expected):
            made.replace(actual, formatted)
        # Preserve blank staff rows, title runs and header whitespace exactly.
        original_prefix = list(root)[:start_index]
        first_body = list(made).index(expected[0])
        for p in list(made)[:first_body]:
            made.remove(p)
        for i, p in enumerate(original_prefix):
            made.insert(i, deepcopy(p))
        _clear_layout(made)
        preview = "\r\n".join(direct_text(p) for p in made.findall(".//hp:p", NS))
        ready = temp / "verified.hwpx"
        ready.write_bytes(_package(produced, _xml(made), preview))
        kordoc_cli("validate", ready)
        reopened = HwpDocument.open(ready)
        with zipfile.ZipFile(ready) as checked_zip:
            checked_root = ET.fromstring(checked_zip.read("Contents/section0.xml"))
            definitions_match = checked_zip.read("Contents/header.xml") == original["Contents/header.xml"]
        checked_body = [p for p in checked_root if direct_text(p).strip().startswith(("□", "❍", "-"))]
        def signature(p):
            return (p.get("paraPrIDRef"), p.get("styleIDRef"),
                    [(dict(r.attrib), "".join(r.xpath("./hp:t//text()", namespaces=NS))) for r in p.findall("hp:run", NS)])
        planned = deepcopy(root)
        for p in list(planned)[start_index:]:
            planned.remove(p)
        for p in expected:
            planned.append(deepcopy(p))
        verification = {
            "kordoc_content_verified": True,
            "approved_fonts_and_spacing": definitions_match and [signature(p) for p in checked_body] == [signature(p) for p in expected],
            "exact_body_text_and_spaces": [direct_text(p) for p in checked_body] == lines,
            "table_count_preserved": reopened.summary()["table_count"] == HwpDocument.open(template).summary()["table_count"],
            "no_old_body": [direct_text(p) for p in checked_root.findall(".//hp:p", NS)] == [direct_text(p) for p in planned.findall(".//hp:p", NS)],
            "missing_fields_resolved": not missing,
        }
        name = re.sub(r"[^0-9A-Za-z가-힣._ -]", "_", fields["title"])[:70].strip()
        draft = DRAFT_DIR / f"{datetime.now():%Y%m%d}_{name}_{sid[-6:]}.hwpx"
        draft.write_bytes(ready.read_bytes())
    result = {"status": "draft_ready" if all(verification.values()) else "verification_failed",
              "session_id": sid, "draft": str(draft), "template": str(template),
              "engine": "kordoc 4.24.70 + approved-format restoration",
              "verification": verification, "visual_verification": "한글 화면 줄바꿈·쪽 나눔 확인 필요",
              "body_paragraphs": len(lines), "kordoc_applied": patch_result.get("applied")}
    result["draft_sha256"] = hashlib.sha256(draft.read_bytes()).hexdigest()
    draft.with_suffix(".verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    session.update({k: v for k, v in result.items() if k != "template"})
    session["output_template"] = str(template)
    save_session(session)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def finalize(sid):
    session = load_session(sid)
    if session.get("status") != "draft_ready" or not session.get("verification") or not all(session["verification"].values()):
        raise SystemExit("현재 입력으로 생성·검증한 초안만 확정할 수 있습니다.")
    draft = Path(session["draft"])
    if hashlib.sha256(draft.read_bytes()).hexdigest() != session.get("draft_sha256"):
        raise SystemExit("초안이 생성 이후 변경되었습니다. 재생성·검증 후 확정하세요.")
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    target = FINAL_DIR / draft.name
    target.write_bytes(draft.read_bytes())
    session.update(status="finalized", final=str(target))
    save_session(session)
    print(json.dumps({"status": "finalized", "file": str(target), "session_id": sid}, ensure_ascii=False, indent=2))





def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build-profiles")
    p = sub.add_parser("start"); p.add_argument("--request", required=True)
    p = sub.add_parser("update"); p.add_argument("--session", required=True); p.add_argument("--fields-json", required=True)
    p = sub.add_parser("status"); p.add_argument("--session", required=True)
    p = sub.add_parser("generate"); p.add_argument("--session", required=True); p.add_argument("--force", action="store_true")
    p = sub.add_parser("finalize"); p.add_argument("--session", required=True)
    a = ap.parse_args()
    if a.cmd == "build-profiles": build_profiles()
    elif a.cmd == "start": start(a.request)
    elif a.cmd == "update": update(a.session, a.fields_json)
    elif a.cmd == "status": print(json.dumps(response(load_session(a.session)), ensure_ascii=False, indent=2))
    elif a.cmd == "generate": generate(a.session, a.force)
    elif a.cmd == "finalize": finalize(a.session)


if __name__ == "__main__":
    main()


