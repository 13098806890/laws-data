#!/usr/bin/env python3
"""
提取法条间引用关系 → references/article_references.json

引用类型：
  - cross_law:  《中华人民共和国X法》第X条  /  刑法第X条（无书名号短标题）
  - self_ref:   本法/本条例/本规定 第X条

输出格式：
[
  {
    "from_law":     "中华人民共和国民事诉讼法",
    "from_article": "第四十四条",
    "from_node_id": 12345,
    "refs": [
      {
        "type":       "cross_law",
        "to_law":     "中华人民共和国法官法",   // 已规范化为完整标题
        "to_article": "第四十六条",
        "to_node_id": 67890,                   // null 如果找不到对应节点
        "raw_text":   "《中华人民共和国法官法》第四十六条"
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

# 匹配《X法》第X条 — 跨法引用（有书名号）
CROSS_QUOTED_RE = re.compile(
    rf'《([^》]{{2,40}})》第({CN_NUM})条'
)

# 书名号内换行符清洗：《中华人民\n共和国X》→《中华人民共和国X》
def clean_law_name(name: str) -> str:
    return re.sub(r'\s+', ' ', name).strip()

# 上下文感知的简称 → 完整标题映射
# key: (from_law_contains, short_name) → full_title
# from_law_contains 为 None 时表示无论哪部法引用均适用
CONTEXT_ALIASES = {
    # 《补充安排》引用原《安排》
    ('内地与香港特别行政区相互执行仲裁裁决的补充安排', '安排'):
        '最高人民法院关于内地与香港特别行政区相互执行仲裁裁决的安排',
    # 《强制执行房屋征收决定》引用《条例》
    ('国有土地上房屋征收补偿决定案件', '条例'):
        '国有土地上房屋征收与补偿条例',
    # 《经济纠纷涉及犯罪》自引《规定》
    ('在审理经济纠纷案件中涉及经济犯罪嫌疑若干问题的规定', '规定'):
        '最高人民法院关于在审理经济纠纷案件中涉及经济犯罪嫌疑若干问题的规定',
    # 《商品房买卖合同》引用《合同法》
    ('商品房买卖合同', '合同法'):
        '中华人民共和国合同法',
    # 《企业分立行政案件》引用《条例》（全民所有制企业转换条例）、《企业法》
    ('全民所有制工业企业分立', '条例'):
        '全民所有制工业企业转换经营机制条例',
    ('全民所有制工业企业分立', '企业法'):
        '中华人民共和国全民所有制工业企业法',
    # 《香港基本法第十三条解释》引用《基本法》
    ('香港特别行政区基本法》第十三条', '基本法'):
        '中华人民共和国香港特别行政区基本法',
}

# 匹配 本法/本条例/本规定/... 第X条  — 本法自引
SELF_RE = re.compile(
    rf'(?:本法|本条例|本规定|本办法|本规则|本决定|本解释)[^第]{{0,10}}第({CN_NUM})条'
)

ART_NUM_RE = re.compile(rf'^(第{CN_NUM}条)')


def build_law_article_index(conn):
    """
    返回两个索引：
      art_index:   {规范化法律标题 → {条号 → node_id}}
      short_to_full: {短标题 → 规范化完整标题}  用于无书名号引用解析
    """
    art_index    = {}
    short_to_full = {}

    # 收集所有 law title
    law_titles = [r[0] for r in conn.execute("SELECT DISTINCT title FROM laws").fetchall()]
    for t in law_titles:
        short = t.replace('中华人民共和国', '').strip()
        # 只有短标题不歧义时才加入映射
        if short not in short_to_full:
            short_to_full[short] = t
        else:
            # 有歧义（多部法律同短名），不映射
            short_to_full[short] = None

    rows = conn.execute(
        "SELECT n.id, n.title, l.title FROM nodes n JOIN laws l ON n.law_id=l.id WHERE n.type='article'"
    ).fetchall()
    for node_id, art_title, law_title in rows:
        m = ART_NUM_RE.match(art_title or '')
        if not m:
            continue
        art_num = m.group(1)
        for key in [law_title, law_title.replace('中华人民共和国', '').strip()]:
            key = key.strip()
            if key not in art_index:
                art_index[key] = {}
            art_index[key][art_num] = node_id

    # 构建无书名号短标题的动态正则
    # 按长度降序排列避免短名遮蔽长名
    valid_shorts = sorted(
        [s for s, full in short_to_full.items() if full and len(s) >= 2],
        key=len, reverse=True
    )
    short_re = re.compile(
        rf'(?<![》\w])({"|".join(re.escape(s) for s in valid_shorts)})第({CN_NUM})条'
    )

    return art_index, short_to_full, short_re


def _normalize_issuer(name: str) -> str:
    """把机构名之间的空格替换为顿号，正文中的空格去掉。
    例：'最高人民法院 最高人民检察院关于办理 贪污贿赂…'
      → '最高人民法院、最高人民检察院关于办理贪污贿赂…'
    """
    # 已知机构名，用于判断是否是机构间分隔
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


def resolve_to_node(art_index, law_name, art_num):
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
    for key in dict.fromkeys(candidates):  # 去重保序
        if key in art_index:
            nid = art_index[key].get(art_num)
            if nid:
                return nid
    return None


def extract_refs(content, law_title, art_index, short_to_full, short_re):
    refs = []
    seen = set()

    # 1. 有书名号跨法引用
    for m in CROSS_QUOTED_RE.finditer(content):
        raw    = m.group(0)
        to_law = clean_law_name(m.group(1))  # 清洗书名号内换行符
        to_art = f'第{m.group(2)}条'

        # 规范化：短标题映射
        full = short_to_full.get(to_law.replace('中华人民共和国', '').strip())
        if full:
            to_law = full

        # 上下文简称解析（to_law 本身就是简称如"安排"、"条例"）
        if resolve_to_node(art_index, to_law, to_art) is None:
            for (ctx, short), alias in CONTEXT_ALIASES.items():
                if short == to_law and ctx in law_title:
                    to_law = alias
                    break

        key = (to_law, to_art)
        if key in seen:
            continue
        seen.add(key)
        refs.append({
            'type':       'cross_law',
            'to_law':     to_law,
            'to_article': to_art,
            'to_node_id': resolve_to_node(art_index, to_law, to_art),
            'raw_text':   raw,
        })

    # 2. 无书名号短标题引用（如 "刑法第二百六十四条"）
    for m in short_re.finditer(content):
        raw      = m.group(0)
        short    = m.group(1)
        to_art   = f'第{m.group(2)}条'
        to_law   = short_to_full.get(short)
        if not to_law:
            continue
        # 排除自引（短标题属于本法自身）
        if to_law == law_title or to_law == law_title.replace('中华人民共和国', '').strip():
            continue
        key = (to_law, to_art)
        if key in seen:
            continue
        seen.add(key)
        refs.append({
            'type':       'cross_law',
            'to_law':     to_law,
            'to_article': to_art,
            'to_node_id': resolve_to_node(art_index, to_law, to_art),
            'raw_text':   raw,
        })

    # 3. 本法自引
    for m in SELF_RE.finditer(content):
        to_art = f'第{m.group(1)}条'
        key    = (law_title, to_art)
        if key in seen:
            continue
        seen.add(key)
        refs.append({
            'type':       'self_ref',
            'to_law':     law_title,
            'to_article': to_art,
            'to_node_id': resolve_to_node(art_index, law_title, to_art),
            'raw_text':   m.group(0),
        })

    return refs


def run():
    conn = sqlite3.connect(DB_PATH)
    print('建立条文索引…')
    art_index, short_to_full, short_re = build_law_article_index(conn)
    print(f'  覆盖 {len(art_index)} 部法律，{len([v for v in short_to_full.values() if v])} 个有效短标题映射')

    print('提取引用关系…')
    rows = conn.execute(
        "SELECT n.id, n.title, n.content, l.title FROM nodes n JOIN laws l ON n.law_id=l.id WHERE n.type='article'"
    ).fetchall()

    results    = []
    total_refs = 0
    for node_id, art_title, content, law_title in rows:
        if not content:
            continue
        refs = extract_refs(content, law_title, art_index, short_to_full, short_re)
        if not refs:
            continue
        art_num = ART_NUM_RE.match(art_title or '')
        results.append({
            'from_law':     law_title,
            'from_article': art_num.group(1) if art_num else (art_title or '').strip(),
            'from_node_id': node_id,
            'refs':         refs,
        })
        total_refs += len(refs)

    conn.close()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')

    cross    = sum(1 for r in results for ref in r['refs'] if ref['type'] == 'cross_law')
    self_    = sum(1 for r in results for ref in r['refs'] if ref['type'] == 'self_ref')
    resolved = sum(1 for r in results for ref in r['refs'] if ref['to_node_id'] is not None)
    print(f'完成：{len(results)} 个条文有引用，共 {total_refs} 条引用')
    print(f'  跨法引用：{cross}  本法自引：{self_}')
    print(f'  已解析到节点：{resolved}  未解析：{total_refs - resolved}')
    print(f'  输出：{OUT_PATH}')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    run()
