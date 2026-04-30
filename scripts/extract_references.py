#!/usr/bin/env python3
"""
提取法条间引用关系 → references/article_references.json

引用类型：
  - cross_law:  《中华人民共和国X法》第X条  /  刑法第X条（无书名号短标题）
  - self_ref:   本法/本条例/本规定 第X条

输出格式：
[
  {
    "from_law_id":    1100001,
    "from_law":       "中华人民共和国民事诉讼法",
    "from_article":   "第四十四条",
    "from_article_num": 44,
    "from_chapter_num": 3,
    "from_section_num": null,
    "refs": [
      {
        "type":           "cross_law",
        "to_law_id":      1100002,
        "to_law":         "中华人民共和国法官法",
        "to_article":     "第四十六条",
        "to_article_num": 46,
        "to_chapter_num": 4,
        "to_section_num": null,
        "resolved":       true,
        "raw_text":       "《中华人民共和国法官法》第四十六条"
      }
    ]
  }
]
"""

import json
import re
import sqlite3
from pathlib import Path

from config import DB_PATH

OUT_PATH = Path(__file__).parent.parent / 'references' / 'article_references.json'

CN_NUM = r'[一二三四五六七八九十百千零两]+'

CROSS_QUOTED_RE = re.compile(rf'《([^》]{{2,40}})》第({CN_NUM})条')

CONTEXT_ALIASES = {
    ('内地与香港特别行政区相互执行仲裁裁决的补充安排', '安排'):
        '最高人民法院关于内地与香港特别行政区相互执行仲裁裁决的安排',
    ('国有土地上房屋征收补偿决定案件', '条例'):
        '国有土地上房屋征收与补偿条例',
    ('在审理经济纠纷案件中涉及经济犯罪嫌疑若干问题的规定', '规定'):
        '最高人民法院关于在审理经济纠纷案件中涉及经济犯罪嫌疑若干问题的规定',
    ('商品房买卖合同', '合同法'):
        '中华人民共和国合同法',
    ('全民所有制工业企业分立', '条例'):
        '全民所有制工业企业转换经营机制条例',
    ('全民所有制工业企业分立', '企业法'):
        '中华人民共和国全民所有制工业企业法',
    ('香港特别行政区基本法》第十三条', '基本法'):
        '中华人民共和国香港特别行政区基本法',
}

SELF_RE = re.compile(
    rf'(?:本法|本条例|本规定|本办法|本规则|本决定|本解释)[^第]{{0,10}}第({CN_NUM})条'
)

ART_NUM_RE = re.compile(rf'^(第{CN_NUM}条)')

CN_ORD = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,
          '九':9,'十':10,'百':100,'千':1000}

def cn_to_int(s: str) -> int:
    s = s.strip()
    result = tmp = 0
    for c in s:
        v = CN_ORD.get(c, 0)
        if v >= 10:
            result += (tmp or 1) * v
            tmp = 0
        else:
            tmp = v
    return result + tmp


def clean_law_name(name: str) -> str:
    return re.sub(r'\s+', ' ', name).strip()


def _normalize_issuer(name: str) -> str:
    ISSUERS = ('最高人民法院', '最高人民检察院', '国务院', '公安部', '司法部',
               '全国人民代表大会', '中央军事委员会')
    parts = re.split(r'\s+', name)
    result = []
    for i, part in enumerate(parts):
        if i == 0:
            result.append(part)
        elif any(part.startswith(org) for org in ISSUERS):
            result.append('、' + part)
        else:
            result[-1] += part
    return ''.join(result)


def build_law_article_index(conn):
    """
    返回：
      art_index:    {法律标题 → {条号文字 → {law_id, article_num, chapter_num, section_num, part_num}}}
      short_to_full: {短标题 → 完整标题}
      law_title_to_id: {法律标题 → law_id}（取 is_current=1 优先，否则最新版）
    """
    art_index      = {}
    short_to_full  = {}
    law_title_to_id = {}

    # 优先取 is_current=1，否则取最新版
    law_rows = conn.execute(
        "SELECT id, title, pub_date, is_current FROM laws WHERE is_current=1 ORDER BY pub_date"
    ).fetchall()
    for law_id, title, pub_date, is_current in law_rows:
        if title not in law_title_to_id or is_current == 1:
            law_title_to_id[title] = law_id
        short = title.replace('中华人民共和国', '').strip()
        if short not in short_to_full:
            short_to_full[short] = title
        else:
            short_to_full[short] = None  # 歧义，不映射

    rows = conn.execute(
        """SELECT n.title, n.law_id, n.article_num, n.chapter_num, n.section_num, n.part_num,
                  l.title as law_title
           FROM nodes n JOIN laws l ON n.law_id = l.id
           WHERE n.type='article'"""
    ).fetchall()

    for art_title, law_id, article_num, chapter_num, section_num, part_num, law_title in rows:
        m = ART_NUM_RE.match(art_title or '')
        if not m:
            continue
        art_num_str = m.group(1)
        loc = {
            'law_id':      law_id,
            'article_num': article_num,
            'chapter_num': chapter_num,
            'section_num': section_num,
            'part_num':    part_num,
        }
        for key in [law_title, law_title.replace('中华人民共和国', '').strip()]:
            key = key.strip()
            if key not in art_index:
                art_index[key] = {}
            # 同一条文可能多版本，优先保留 is_current 版本（law_title_to_id 已处理）
            preferred_id = law_title_to_id.get(law_title)
            if art_num_str not in art_index[key] or law_id == preferred_id:
                art_index[key][art_num_str] = loc

    valid_shorts = sorted(
        [s for s, full in short_to_full.items() if full and len(s) >= 2],
        key=len, reverse=True
    )
    short_re = re.compile(
        rf'(?<![》\w])({"|".join(re.escape(s) for s in valid_shorts)})第({CN_NUM})条'
    )

    return art_index, short_to_full, short_re, law_title_to_id


def resolve_loc(art_index, law_name, art_num_str):
    """返回 loc dict 或 None"""
    no_space   = re.sub(r'\s+', '', law_name)
    normalized = _normalize_issuer(law_name)
    first_sep  = re.sub(r'\s+', '、', law_name, count=1)
    candidates = [
        law_name,
        law_name.replace('中华人民共和国', '').strip(),
        no_space,
        no_space.replace('中华人民共和国', '').strip(),
        normalized,
        normalized.replace('中华人民共和国', '').strip(),
        first_sep,
        first_sep.replace('中华人民共和国', '').strip(),
    ]
    for key in dict.fromkeys(candidates):
        if key in art_index:
            loc = art_index[key].get(art_num_str)
            if loc:
                return loc
    return None


def extract_refs(content, law_title, law_id, from_art_num_str,
                 art_index, short_to_full, short_re, law_title_to_id):
    refs = []
    seen = set()

    # 1. 有书名号跨法引用
    for m in CROSS_QUOTED_RE.finditer(content):
        raw    = m.group(0)
        to_law = clean_law_name(m.group(1))
        to_art_str = f'第{m.group(2)}条'

        full = short_to_full.get(to_law.replace('中华人民共和国', '').strip())
        if full:
            to_law = full

        loc = resolve_loc(art_index, to_law, to_art_str)
        if loc is None:
            for (ctx, short), alias in CONTEXT_ALIASES.items():
                if short == to_law and ctx in law_title:
                    to_law = alias
                    loc = resolve_loc(art_index, to_law, to_art_str)
                    break

        key = (to_law, to_art_str)
        if key in seen:
            continue
        seen.add(key)

        to_law_id = law_title_to_id.get(to_law)
        refs.append({
            'type':           'cross_law',
            'to_law_id':      loc['law_id'] if loc else to_law_id,
            'to_law':         to_law,
            'to_article':     to_art_str,
            'to_article_num': loc['article_num'] if loc else None,
            'to_chapter_num': loc['chapter_num'] if loc else None,
            'to_section_num': loc['section_num'] if loc else None,
            'to_part_num':    loc['part_num']    if loc else None,
            'resolved':       loc is not None,
            'raw_text':       raw,
        })

    # 2. 无书名号短标题引用
    for m in short_re.finditer(content):
        raw    = m.group(0)
        short  = m.group(1)
        to_art_str = f'第{m.group(2)}条'
        to_law = short_to_full.get(short)
        if not to_law:
            continue
        if to_law == law_title or to_law == law_title.replace('中华人民共和国', '').strip():
            continue
        key = (to_law, to_art_str)
        if key in seen:
            continue
        seen.add(key)

        loc = resolve_loc(art_index, to_law, to_art_str)
        to_law_id = law_title_to_id.get(to_law)
        refs.append({
            'type':           'cross_law',
            'to_law_id':      loc['law_id'] if loc else to_law_id,
            'to_law':         to_law,
            'to_article':     to_art_str,
            'to_article_num': loc['article_num'] if loc else None,
            'to_chapter_num': loc['chapter_num'] if loc else None,
            'to_section_num': loc['section_num'] if loc else None,
            'to_part_num':    loc['part_num']    if loc else None,
            'resolved':       loc is not None,
            'raw_text':       raw,
        })

    # 3. 本法自引
    for m in SELF_RE.finditer(content):
        to_art_str = f'第{m.group(1)}条'
        key = (law_title, to_art_str)
        if key in seen:
            continue
        seen.add(key)
        loc = resolve_loc(art_index, law_title, to_art_str)
        refs.append({
            'type':           'self_ref',
            'to_law_id':      law_id,
            'to_law':         law_title,
            'to_article':     to_art_str,
            'to_article_num': loc['article_num'] if loc else None,
            'to_chapter_num': loc['chapter_num'] if loc else None,
            'to_section_num': loc['section_num'] if loc else None,
            'to_part_num':    loc['part_num']    if loc else None,
            'resolved':       loc is not None,
            'raw_text':       m.group(0),
        })

    return refs


def run():
    conn = sqlite3.connect(DB_PATH)
    print('建立条文索引…')
    art_index, short_to_full, short_re, law_title_to_id = build_law_article_index(conn)
    print(f'  覆盖 {len(art_index)} 部法律，{len([v for v in short_to_full.values() if v])} 个有效短标题映射')

    print('提取引用关系…')
    rows = conn.execute(
        """SELECT n.law_id, n.title, n.content, n.article_num,
                  n.chapter_num, n.section_num, n.part_num, l.title
           FROM nodes n JOIN laws l ON n.law_id = l.id
           WHERE n.type='article' AND l.is_current=1"""
    ).fetchall()

    results    = []
    total_refs = 0
    for law_id, art_title, content, article_num, chapter_num, section_num, part_num, law_title in rows:
        if not content:
            continue
        m = ART_NUM_RE.match(art_title or '')
        from_art_str = m.group(1) if m else (art_title or '').strip()
        refs = extract_refs(content, law_title, law_id, from_art_str,
                            art_index, short_to_full, short_re, law_title_to_id)
        if not refs:
            continue
        results.append({
            'from_law_id':      law_id,
            'from_law':         law_title,
            'from_article':     from_art_str,
            'from_article_num': article_num,
            'from_chapter_num': chapter_num,
            'from_section_num': section_num,
            'from_part_num':    part_num,
            'refs':             refs,
        })
        total_refs += len(refs)

    conn.close()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')

    cross    = sum(1 for r in results for ref in r['refs'] if ref['type'] == 'cross_law')
    self_    = sum(1 for r in results for ref in r['refs'] if ref['type'] == 'self_ref')
    resolved = sum(1 for r in results for ref in r['refs'] if ref['resolved'])
    print(f'完成：{len(results)} 个条文有引用，共 {total_refs} 条引用')
    print(f'  跨法引用：{cross}  本法自引：{self_}')
    print(f'  已解析：{resolved}  未解析：{total_refs - resolved}')
    print(f'  输出：{OUT_PATH}')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    run()
