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
from docx_to_json.structure import CHAPTER_RE, SECTION_RE, normalize_title, add_structure

ARTICLE_RE    = re.compile(r'^第[一二三四五六七八九十百千]+条[　\s]')
TOC_RE        = re.compile(r'^(?:目\s*录|附\s*录|附\s*件)$')
CN_SECTION_RE = re.compile(r'^[一二三四五六七八九十百]+(?:十[一二三四五六七八九]?)?、\S')
DOC_NUM_RE    = re.compile(r'[（(]?[一-鿿]{1,8}[〔\[]\d{4}[〕\]]\d+号[）)]?')
ORG_RE        = re.compile(r'^(最高人民法院|最高人民检察院|国务院|全国人民代表大会[一-鿿]*|'
                           r'中华人民共和国[一-鿿]{2,8}(?:部|委|局|署)|'
                           r'[一-鿿]{2,10}(?:部|委员会|局|署|总局)(?:、[一-鿿]{2,10}(?:部|委员会|局|署|总局))*)')


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
            if m and len(text) < 40:
                issuing_org = m.group(0)
    return issuing_org, doc_number


def extract_content(doc_path: Path) -> dict:
    if doc_path.suffix.lower() == '.doc':
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
            promulgation_info = text
            start_idx = i + 1
            break

    chapters = []
    full_text_lines = []
    current_chapter = current_section = None
    in_toc = False
    pending = []
    uses_cn_sections = False  # 是否是汉字序号章节结构（一、二、三…）

    for text in paras[start_idx:]:
        if TOC_RE.match(text) or text in ('目　　录', '目  录', '目录'):
            in_toc = True
            continue

        if in_toc:
            if CHAPTER_RE.match(text) or SECTION_RE.match(text):
                pending.append(text)
            elif CN_SECTION_RE.match(text):
                pending.append(text)
                uses_cn_sections = True
            elif ARTICLE_RE.match(text):
                in_toc = False
                if uses_cn_sections:
                    # 汉字序号结构：TOC 里收集到的是章节名，直接从 pending 建章
                    for s in pending:
                        if CN_SECTION_RE.match(s):
                            full_text_lines.append(s)
                            current_chapter = {'title': normalize_title(s), 'sections': [], 'articles': []}
                            chapters.append(current_chapter)
                            current_section = None
                else:
                    last_ch1 = next((j for j, s in enumerate(pending) if CHAPTER_RE.match(s)), -1)
                    if last_ch1 >= 0:
                        pending = pending[last_ch1:]
                    for s in pending:
                        full_text_lines.append(s)
                        if CHAPTER_RE.match(s):
                            current_chapter = {'title': normalize_title(s), 'sections': [], 'articles': []}
                            chapters.append(current_chapter)
                            current_section = None
                        elif SECTION_RE.match(s):
                            current_section = {'title': normalize_title(s), 'articles': []}
                            if current_chapter:
                                current_chapter['sections'].append(current_section)
                pending = []
            else:
                pending = []
            if in_toc:
                continue

        full_text_lines.append(text)

        if uses_cn_sections and CN_SECTION_RE.match(text):
            current_chapter = {'title': normalize_title(text), 'sections': [], 'articles': []}
            chapters.append(current_chapter)
            current_section = None
        elif CHAPTER_RE.match(text):
            current_chapter = {'title': normalize_title(text), 'sections': [], 'articles': []}
            chapters.append(current_chapter)
            current_section = None
        elif SECTION_RE.match(text):
            current_section = {'title': normalize_title(text), 'articles': []}
            if current_chapter:
                current_chapter['sections'].append(current_section)
        elif ARTICLE_RE.match(text):
            art_title = text[:text.index('　') + 1] if '　' in text else text[:6]
            article = {'title': art_title, 'content': text}
            target = current_section or current_chapter
            if target:
                target['articles'].append(article)
            else:
                if not chapters:
                    chapters.append({'title': '正文', 'sections': [], 'articles': []})
                chapters[-1]['articles'].append(article)

    total = sum(
        len(ch.get('articles', [])) +
        sum(len(s.get('articles', [])) for s in ch.get('sections', []))
        for ch in chapters
    )
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

        docx_files = sorted(f for f in src_dir.iterdir()
                            if f.suffix.lower() in ('.docx', '.doc'))
        print(f'  {category}: {len(docx_files)} 个文件')

        for docx_path in docx_files:
            data = process_docx(docx_path, category, xlsx_index, domain_idx)
            if data is None:
                errors += 1
                continue
            out_path = out_dir / (docx_path.stem + '.json')
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            total += 1

    print(f'JSON 生成完成: {total} 个，{errors} 个错误')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
