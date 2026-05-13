#!/usr/bin/env python3
"""
docx → JSON
用法：python3 -m docx_to_json.converter
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import docx as python_docx

from config import SRC_DIRS, JSON_DIR
from utils import title_from_stem, pub_date_from_stem
from docx_to_json.domain import build_xlsx_index, build_domain_index, get_legal_domain
from docx_to_json.effective_date import extract_effective_date
from docx_to_json.structure import CHAPTER_RE, SECTION_RE, PART_RE, normalize_title, add_structure, cn_to_int
from docx_to_json.subject_area import get_subject_area

ARTICLE_RE    = re.compile(r'^第[零一二三四五六七八九十百千]+条[　\s]')

# ── 条文内容清洗 ──────────────────────────────────────────────────────────────

# PAGE/MERGEFORMAT 噪音：Word 导出的页码字段，如 "－PAGE  2－" 或 "PAGE \* MERGEFORMAT"
_PAGE_RE        = re.compile(r'[-－]\s*PAGE\s+\d+\s*[-－]')
_PAGE_MERGE_RE  = re.compile(r'\bPAGE\s*\\\*\s*MERGEFORMAT\b|\bMERGEFORMAT\b|\bPAGE\b')
# HYPERLINK 残留：如 HYPERLINK "javascript:SLC(13912,0)"
_HYPERLINK_RE   = re.compile(r'HYPERLINK\s*"[^"]*"\s*')
# 小写 l 误作数字 1：仅修正明确上下文
_L_AS_1_RE      = re.compile(r'(?<!\w)l(?=[月年日万千百元％%个项条款位]|\d)')
# 公式中 (l－ 或 (l- 的 l
_L_FORMULA_RE   = re.compile(r'(?<=[(（])l(?=[-－])')


def clean_article_content(text: str) -> str:
    """清洗条文内容中的 Word 导出噪音和明显 OCR 错误"""
    # 1. 去掉 PAGE 噪音（整段）
    text = _PAGE_RE.sub('', text)
    text = _PAGE_MERGE_RE.sub('', text)
    # 2. 去掉 HYPERLINK 标记，保留后面紧跟的正文
    text = _HYPERLINK_RE.sub('', text)
    # 3. 小写 l → 1
    text = _L_AS_1_RE.sub('1', text)
    text = _L_FORMULA_RE.sub('1', text)
    # 4. 清理多余空白（PAGE 删除后可能留下空行）
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return '\n'.join(lines)


_ART_NUM_RE   = re.compile(r'^第([零一二三四五六七八九十百千]+)条')
# 段落内嵌条文切分：匹配段落中间出现的「\n　　第X条」或「\n第X条」
_INLINE_ART_RE = re.compile(r'\n[　\s]*(?=第[零一二三四五六七八九十百千]+条[　\s])')
TOC_RE        = re.compile(r'^(?:目\s*录|附\s*录|附\s*件)$')
CN_SECTION_RE = re.compile(r'^[一二三四五六七八九十百]+(?:十[一二三四五六七八九]?)?、\S')
DOC_NUM_RE = re.compile(r'[（(]?[一-鿿]{1,8}[〔\[]\d{4}[〕\]]\d+号[）)]?')
# 白名单：只匹配已知顶级发布机构，避免误匹配法条正文
_KNOWN_ORGS = (
    '最高人民法院',
    '最高人民检察院',
    '国务院',
    '全国人民代表大会常务委员会',
    '全国人民代表大会',
    '中央军事委员会',
    '海关总署',
    '国家外汇管理局',
    '中国人民银行',
    '外交部',
    '商务部',
    '对外经济贸易部',
)
ORG_RE = re.compile(
    r'^(' + '|'.join(re.escape(o) for o in _KNOWN_ORGS) + r')$'
)


def _extract_org_and_docnum(paras: list) -> tuple[str, str]:
    """从文件头部段落提取发布机关和发文字号，搜索范围限前15段。"""
    issuing_org = ''
    doc_number  = ''
    for text in paras[:15]:
        if not doc_number:
            m = DOC_NUM_RE.search(text)
            if m and len(text) < 30:  # 发文字号是独立短行
                doc_number = m.group(0).strip('（）()')
        if not issuing_org:
            m = ORG_RE.match(text)
            if m:
                issuing_org = m.group(1)
    return issuing_org, doc_number


def extract_content(doc_path: Path) -> dict:
    if doc_path.suffix.lower() == '.txt':
        # 从网页抓取并保存的纯文本文件，直接按行读取
        paras = [l.strip() for l in doc_path.read_text(encoding='utf-8').splitlines() if l.strip()]
    elif doc_path.suffix.lower() == '.doc':
        result = subprocess.run(
            ['textutil', '-convert', 'txt', '-stdout', str(doc_path)],
            capture_output=True, text=True, timeout=30
        )
        paras = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    else:
        doc = python_docx.Document(str(doc_path))
        paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    promulgation_info = ''
    start_idx = 0
    for i, text in enumerate(paras[:5]):
        if re.search(r'通过|公布|发布|施行|颁布|批准', text):
            # 去除排版换行和多余空格
            promulgation_info = re.sub(r'[\r\n]+', '', text).strip()
            start_idx = i + 1
            break

    chapters = []
    full_text_lines = []
    current_chapter = current_section = None
    current_article = None
    in_toc = False
    pending = []
    uses_cn_sections = False  # 是否是汉字序号章节结构（一、二、三…），由目录检测设置
    _last_art_num = 0  # 上一个已处理条文的序号，用于段落内切分验证

    # 预扫：若无任何「第X条」但有「一、二、」段落，则以「一、」为条文粒度
    _body = paras[start_idx:]
    _has_art_re = any(ARTICLE_RE.match(p) for p in _body)
    uses_cn_articles = (not _has_art_re and any(CN_SECTION_RE.match(p) for p in _body))

    def _split_inline_articles(text: str) -> list[str]:
        """
        检测段落内是否包含多个连续条文（第X条紧跟第X-1条之后出现）。
        只有编号连续时才切分，避免误切正文中提到的条文引用。
        """
        nonlocal _last_art_num
        # 先按换行+缩进拆候选片段
        parts = _INLINE_ART_RE.split(text)
        if len(parts) == 1:
            return [text]

        result = []
        buf = parts[0]
        for seg in parts[1:]:
            m = _ART_NUM_RE.match(seg)
            if m:
                seg_num = cn_to_int(m.group(1))
                # 取 buf 的条号
                bm = _ART_NUM_RE.match(buf)
                buf_num = cn_to_int(bm.group(1)) if bm else _last_art_num
                if seg_num == buf_num + 1:
                    result.append(buf.strip())
                    buf = seg
                    continue
            # 编号不连续，不切分，拼回
            buf = buf + '\n' + seg
        result.append(buf.strip())

        # 更新 _last_art_num 为这批里最后一条的编号
        lm = _ART_NUM_RE.match(result[-1])
        if lm:
            _last_art_num = cn_to_int(lm.group(1))
        return result

    def _flush_pending():
        nonlocal current_chapter, current_section
        if uses_cn_sections:
            for s in pending:
                if CN_SECTION_RE.match(s):
                    full_text_lines.append(s)
                    current_chapter = {'title': normalize_title(s), 'sections': [], 'articles': []}
                    chapters.append(current_chapter)
                    current_section = None
        else:
            last_ch1 = next((j for j, s in enumerate(pending) if CHAPTER_RE.match(s)), -1)
            pend = pending[last_ch1:] if last_ch1 >= 0 else pending
            for s in pend:
                full_text_lines.append(s)
                if CHAPTER_RE.match(s):
                    current_chapter = {'title': normalize_title(s), 'sections': [], 'articles': []}
                    chapters.append(current_chapter)
                    current_section = None
                elif SECTION_RE.match(s):
                    current_section = {'title': normalize_title(s), 'articles': []}
                    if current_chapter:
                        current_chapter['sections'].append(current_section)
        pending.clear()

    _child_seq = [0]  # 章内子节点（直属条文+节）全局追加序号
    _current_part_title = None  # 最近一个编标题（用于直属编条文的占位章）

    def _next_seq():
        _child_seq[0] += 1
        return _child_seq[0]

    for raw_text in paras[start_idx:]:
        # 展开段落内嵌的连续条文（如飞行基本规则的排版方式）
        for text in _split_inline_articles(raw_text):
            if TOC_RE.match(text) or text in ('目　　录', '目  录', '目录'):
                in_toc = True
                continue

            if in_toc:
                pending_norm = {normalize_title(s) for s in pending}
                has_parts_in_pending = any(PART_RE.match(s) for s in pending)
                if PART_RE.match(text):
                    # 编标题：重复表示正文开始
                    if normalize_title(text) in pending_norm:
                        in_toc = False
                        pending.clear()
                    else:
                        pending.append(text)
                elif CHAPTER_RE.match(text):
                    # 章标题：若目录里有编，只靠编重复退出；若无编，章重复退出
                    if not has_parts_in_pending and normalize_title(text) in pending_norm:
                        in_toc = False
                        pending.clear()
                    else:
                        pending.append(text)
                elif SECTION_RE.match(text):
                    # 节标题：不用于 TOC 退出检测（节名在目录内可合法重复）
                    pending.append(text)
                elif CN_SECTION_RE.match(text):
                    if normalize_title(text) in pending_norm:
                        in_toc = False
                        pending.clear()
                    else:
                        pending.append(text)
                        uses_cn_sections = True
                elif ARTICLE_RE.match(text):
                    in_toc = False
                    _flush_pending()
                else:
                    pending.clear()
                if in_toc:
                    continue

            full_text_lines.append(text)

            if uses_cn_articles and CN_SECTION_RE.match(text):
                # 无「第X条」结构的文件：「一、二、三」各段作为独立条文
                current_article = {'title': text[:text.index('、') + 1], 'content': text}
                if not chapters:
                    chapters.append({'title': '正文', 'sections': [], 'articles': []})
                chapters[-1]['articles'].append(current_article)
            elif uses_cn_sections and CN_SECTION_RE.match(text):
                current_article = None
                current_chapter = {'title': normalize_title(text), 'sections': [], 'articles': []}
                chapters.append(current_chapter)
                current_section = None
            elif PART_RE.match(text):
                # 编标题：重置当前章/节/条。
                # 直属于编的条文（编下无章）将在遇到第一个 ARTICLE_RE 时动态创建一个
                # 占位章，以便 structure.py 的 part→chapter 映射能正确处理。
                current_article = None
                current_chapter = None
                current_section = None
                _current_part_title = normalize_title(text)  # 备用，供占位章标题
            elif CHAPTER_RE.match(text):
                current_article = None
                current_chapter = {'title': normalize_title(text), 'sections': [], 'articles': []}
                chapters.append(current_chapter)
                current_section = None
            elif SECTION_RE.match(text):
                current_article = None
                current_section = {'title': normalize_title(text), 'articles': [], '_seq': _next_seq()}
                if current_chapter:
                    current_chapter['sections'].append(current_section)
            elif ARTICLE_RE.match(text):
                m = re.match(r'^(第[一二三四五六七八九十百千]+条[　\s]?)', text)
                art_title = m.group(1) if m else (text[:text.index('　') + 1] if '　' in text else text[:8])
                current_article = {'title': art_title, 'content': text}
                target = current_section or current_chapter
                if target is None and _current_part_title is not None:
                    # 编下直属条文（无章）：创建占位章，标题用 _DIRECT_ 前缀供 structure.py 识别
                    current_chapter = {'title': f'_DIRECT_{_current_part_title}', 'sections': [], 'articles': [], '_is_direct_part': True}
                    chapters.append(current_chapter)
                    target = current_chapter
                if target:
                    target['articles'].append(current_article)
                    # 直属于章的条文（current_section is None）记录章内出现序号
                    if current_section is None and current_chapter is not None:
                        current_article['_seq'] = _next_seq()
                else:
                    if not chapters:
                        chapters.append({'title': '正文', 'sections': [], 'articles': []})
                    chapters[-1]['articles'].append(current_article)
            elif current_article is not None:
                # 续行段落（分项列举、补充说明等），追加到当前条文
                current_article['content'] += '\n' + text

    total = sum(
        len(ch.get('articles', [])) +
        sum(len(s.get('articles', [])) for s in ch.get('sections', []))
        for ch in chapters
    )
    # 清洗所有条文内容
    for ch in chapters:
        for art in ch.get('articles', []):
            art['content'] = clean_article_content(art['content'])
        for sec in ch.get('sections', []):
            for art in sec.get('articles', []):
                art['content'] = clean_article_content(art['content'])
    issuing_org, doc_number = _extract_org_and_docnum(paras)
    return {
        'promulgation_info': promulgation_info,
        'issuing_org':       issuing_org,
        'doc_number':        doc_number,
        'full_text':         '\n'.join(full_text_lines),
        'chapters':          chapters,
        'total_articles':    total,
    }


def process_docx(docx_path: Path, category: str,
                 xlsx_index: dict, domain_idx: dict) -> dict | None:
    try:
        content = extract_content(docx_path)
    except Exception as e:
        print(f'  ERROR extract {docx_path.name}: {e}')
        return None

    stem     = docx_path.stem
    title    = title_from_stem(stem)
    pub_date = pub_date_from_stem(stem)

    data = {
        'title':             title,
        'category':          category,
        'pub_date':          pub_date,
        'effective_date':    None,
        'promulgation_info': content['promulgation_info'],
        'issuing_org':       content['issuing_org'],
        'doc_number':        content['doc_number'],
        'legal_domain':      None,
        'total_articles':    content['total_articles'],
        'chapters':          content['chapters'],
        'full_text':         content['full_text'],
    }

    xlsx_key = f'{title}_{(pub_date or "").replace("-", "")}'
    if xlsx_key in xlsx_index:
        entry = xlsx_index[xlsx_key]
        if entry['effective_date']:
            data['effective_date'] = entry['effective_date']
        if entry['category']:
            data['category'] = entry['category']

    if not data['effective_date']:
        data['effective_date'] = extract_effective_date(data)

    data['legal_domain'] = get_legal_domain(title, data, domain_idx)
    data['subject_area'] = get_subject_area(title, data.get('category', ''))
    data = add_structure(data)
    return data


def run():
    print('=== 加载辅助数据 ===')
    xlsx_index = build_xlsx_index()
    domain_idx = build_domain_index()
    print(f'xlsx 索引: {len(xlsx_index)} 条')
    print(f'domain 映射: {len(domain_idx)} 条')

    print('\n=== docx → JSON ===')
    if JSON_DIR.exists():
        shutil.rmtree(JSON_DIR)
    JSON_DIR.mkdir(parents=True)

    total = errors = 0
    for category, src_dir in SRC_DIRS.items():
        if not src_dir.exists():
            print(f'  跳过（目录不存在）: {src_dir}')
            continue
        out_dir = JSON_DIR / category
        out_dir.mkdir(parents=True, exist_ok=True)

        docx_files_raw = sorted(f for f in src_dir.iterdir()
                            if f.suffix.lower() in ('.docx', '.doc'))
        # .txt（网页来源）优先于同名 .docx/.doc：如果 stem 相同，用 .txt 替换
        txt_stems = {f.stem for f in src_dir.iterdir() if f.suffix.lower() == '.txt'}
        docx_files = [f for f in docx_files_raw if f.stem not in txt_stems]
        txt_files  = sorted(f for f in src_dir.iterdir() if f.suffix.lower() == '.txt')
        all_files  = sorted(docx_files + txt_files, key=lambda f: f.stem)
        print(f'  {category}: {len(docx_files_raw)} 个 docx'
              f'（{len(txt_stems)} 个被 txt 替换），{len(txt_files)} 个 txt 新增')

        for doc_path in all_files:
            data = process_docx(doc_path, category, xlsx_index, domain_idx)
            if data is None:
                errors += 1
                continue
            out_path = out_dir / (doc_path.stem + '.json')
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            total += 1

    print(f'JSON 生成完成: {total} 个，{errors} 个错误')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
