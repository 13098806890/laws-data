#!/usr/bin/env python3
"""
法考专用 Pipeline
================
从 houdask.com 的 tree_data.js 和各法律的 jsonUrl 拉取全量法考法律，
转换为结构化 JSON，再导入独立 SQLite 数据库 flk_content.db。

目录结构（均在 BASE_DIR 下）：
  flk_source/
    tree_data.js          ← 法考目录树（已下载）
    json/                 ← 各法律 JSON（从 jsonUrl 下载，可缓存复用）
  flk_content.db          ← 法考专用数据库

用法：
  cd /Users/doxie/laws_data
  python3 scripts/flk_pipeline.py             # 完整流程
  python3 scripts/flk_pipeline.py --skip-dl   # 跳过下载（json/ 已有缓存）
  python3 scripts/flk_pipeline.py --skip-db   # 只下载，不建库
  python3 scripts/flk_pipeline.py --verify    # 只跑交叉验证
"""

import argparse
import json
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

BASE_DIR    = Path(__file__).parent.parent
FLK_SRC     = BASE_DIR / '法考' / 'flk_source'
FLK_JSON    = FLK_SRC / 'json'
TREE_JS     = FLK_SRC / 'tree_data.js'
FLK_DB      = BASE_DIR / '法考' / 'flk_content.db'
MAIN_DB     = BASE_DIR / 'law_content.db'

# ── 科目顺序 ────────────────────────────────────────────────────────────────
SUBJECT_ORDER = ['刑法', '刑事诉讼法', '行政法与行政诉讼法', '民法', '商法', '民事诉讼法']


# ════════════════════════════════════════════════════════════════════════════
# 1. 解析 tree_data.js
# ════════════════════════════════════════════════════════════════════════════

def load_tree() -> dict:
    """返回 {subject: [law_node, ...]} 按科目分组。"""
    raw = TREE_JS.read_text(encoding='utf-8')
    json_str = re.sub(r'^var zTreeJson=', '', raw.strip()).rstrip(';')
    data = json.loads(json_str)

    def find_laws(nodes):
        results = []
        for n in nodes:
            if n.get('type') == 2:
                results.append(n)
            results.extend(find_laws(n.get('children', [])))
        return results

    subjects = {}
    for top in data['data']:
        subject = top.get('content', '') or top.get('name', '')
        laws = find_laws(top.get('children', []))
        subjects[subject] = laws

    total = sum(len(v) for v in subjects.values())
    print(f'tree_data: {len(subjects)} 科目，共 {total} 部法律')
    for s, ls in subjects.items():
        print(f'  {s}: {len(ls)}')
    return subjects


# ════════════════════════════════════════════════════════════════════════════
# 2. 下载各法律 JSON
# ════════════════════════════════════════════════════════════════════════════

def download_law_json(law_node: dict) -> Path:
    """下载法律 JSON，缓存到 flk_source/json/{id}.json，返回路径。"""
    law_id  = law_node['id']
    json_url = law_node.get('jsonUrl', '')
    if not json_url:
        return None

    cache = FLK_JSON / f'{law_id}.json'
    if cache.exists():
        return cache

    for attempt in range(3):
        try:
            with urllib.request.urlopen(json_url, timeout=20) as resp:
                data = resp.read()
            cache.write_bytes(data)
            return cache
        except Exception as e:
            if attempt == 2:
                print(f'  ✗ 下载失败 id={law_id}: {e}')
                return None
            time.sleep(2)


def download_all(subjects: dict, verbose: bool = True):
    """下载全部法律 JSON，打印进度。"""
    FLK_JSON.mkdir(parents=True, exist_ok=True)
    all_laws = [law for laws in subjects.values() for law in laws]
    total = len(all_laws)
    ok = 0
    for i, law in enumerate(all_laws, 1):
        title = law.get('content', '')
        path = download_law_json(law)
        if path:
            ok += 1
            if verbose and i % 20 == 0:
                print(f'  [{i}/{total}] 已完成 {ok} 个...')
        else:
            print(f'  [{i}/{total}] ✗ {title[:50]}')
        time.sleep(0.05)   # 礼貌性延迟
    print(f'下载完成：{ok}/{total} 个成功')


# ════════════════════════════════════════════════════════════════════════════
# 3. 解析单个法律 JSON → 结构化数据
# ════════════════════════════════════════════════════════════════════════════

def parse_law(law_node: dict, subject: str) -> dict | None:
    """
    解析缓存的 jsonUrl JSON，返回结构化法律 dict。

    返回格式：
    {
      'flk_id':    int,          # tree_data 里的 type=2 id
      'title':     str,
      'subject':   str,          # 法考科目
      'sections':  [             # 章/节 列表（按 position 排序）
        {'id': int, 'type': int, 'content': str, 'text': str,
         'parent_id': int, 'position': int}
      ]
    }
    """
    cache = FLK_JSON / f'{law_node["id"]}.json'
    if not cache.exists():
        return None

    try:
        nodes = json.loads(cache.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'  ✗ 解析失败 {cache.name}: {e}')
        return None

    if not isinstance(nodes, list):
        nodes = [nodes]

    sections = []
    for n in nodes:
        sections.append({
            'id':        n.get('id'),
            'type':      n.get('type'),        # 3=节, 4=章
            'content':   n.get('content', ''),  # 章/节 标题
            'text':      n.get('lawWebContent', ''),  # 该章/节全文
            'parent_id': n.get('parentId'),
            'position':  n.get('position', 0),
        })

    sections.sort(key=lambda x: x['position'])

    return {
        'flk_id':   law_node['id'],
        'title':    law_node.get('content', ''),
        'subject':  subject,
        'json_url': law_node.get('jsonUrl', ''),
        'sections': sections,
    }


# ════════════════════════════════════════════════════════════════════════════
# 4. 从 lawWebContent 提取条文
# ════════════════════════════════════════════════════════════════════════════

# 匹配 "第X条" 的正则（支持汉字数字）
ARTICLE_RE = re.compile(
    r'第([一二三四五六七八九十百千零〇两]+)条'
)

def extract_articles(text: str) -> list[dict]:
    """
    从章/节全文中提取条文列表。
    返回 [{'article_number': '第一条', 'content': '第一条　...'}]
    """
    if not text:
        return []

    # 按 "第X条" 分割
    parts = ARTICLE_RE.split(text)
    if len(parts) < 3:
        # 无条文结构，整体作为一条
        stripped = text.strip()
        if stripped:
            return [{'article_number': '', 'content': stripped}]
        return []

    articles = []
    i = 1
    while i < len(parts) - 1:
        num_cn  = parts[i]        # 汉字数字
        content = parts[i + 1]   # 条文正文（到下一个"第X条"之前）
        article_number = f'第{num_cn}条'
        full = f'{article_number}　{content.strip()}'
        articles.append({
            'article_number': article_number,
            'content':        full,
        })
        i += 2

    return articles


# ════════════════════════════════════════════════════════════════════════════
# 5. 建库
# ════════════════════════════════════════════════════════════════════════════

SCHEMA = """
CREATE TABLE IF NOT EXISTS laws (
    id          INTEGER PRIMARY KEY,
    flk_id      INTEGER UNIQUE NOT NULL,   -- tree_data type=2 id
    title       TEXT    NOT NULL,
    subject     TEXT    NOT NULL,          -- 法考科目
    json_url    TEXT,
    total_sections  INTEGER DEFAULT 0,
    total_articles  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    law_id      INTEGER NOT NULL REFERENCES laws(id),
    flk_node_id INTEGER,                  -- 原始 node id
    parent_node_id INTEGER,
    type        INTEGER,                  -- 3 or 4
    title       TEXT,                     -- 章/节标题 (content字段)
    position    INTEGER,
    full_text   TEXT                      -- lawWebContent
);

CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    law_id          INTEGER NOT NULL REFERENCES laws(id),
    section_id      INTEGER REFERENCES sections(id),
    article_number  TEXT,
    content         TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    content,
    article_number,
    content="articles",
    tokenize="trigram"
);
"""


# 厚大标题 → 主库标题的手动映射（当四种规范化变体仍无法匹配时使用）
TITLE_OVERRIDES: dict[str, str] = {
    # 厚大带 (2009修正) 后缀，主库无后缀
    '全国人民代表大会常务委员会关于《中华人民共和国刑法》第二百二十八条、第三百四十二条、第四百一十条的解释(2009修正)':
        '全国人民代表大会常务委员会关于《中华人民共和国刑法》第二百二十八条、第三百四十二条、第四百一十条的解释',
    # 厚大带 (一) 序号，主库无序号
    '最高人民法院、最高人民检察院关于办理利用互联网、移动通讯终端、声讯台制作、复制、出版、贩卖、传播淫秽电子信息刑事案件具体应用法律若干问题的解释(一)':
        '最高人民法院、最高人民检察院关于办理利用互联网、移动通讯终端、声讯台制作、复制、出版、贩卖、传播淫秽电子信息刑事案件具体应用法律若干问题的解释',
}


def _build_main_title_index(main_conn) -> dict:
    """
    从主库构建标题 → id 的查找索引（只取 is_current=1）。
    每个标题建四种规范化形式，setdefault 保证精确形式优先。
    """
    rows = main_conn.execute(
        "SELECT id, title FROM laws WHERE is_current=1"
    ).fetchall()

    def _fw(t):   return t.replace('(', '（').replace(')', '）')
    def _nb(t):   return t.replace('《', '').replace('》', '')

    index: dict[str, int] = {}
    # 先用所有规范化变体填入（低优先级），再用精确标题覆盖（高优先级）
    for law_id, title in rows:
        for variant in [_fw(title), _nb(title), _nb(_fw(title))]:
            index.setdefault(variant, law_id)
    for law_id, title in rows:
        index[title] = law_id          # 精确匹配最高优先
    return index


def _lookup_main_id(index: dict, title: str) -> int | None:
    """按四种变体顺序查找主库 law_id，找不到返回 None。先查手动映射表。"""
    # 手动映射优先
    mapped = TITLE_OVERRIDES.get(title)
    if mapped:
        title = mapped
    def _fw(t): return t.replace('(', '（').replace(')', '）')
    def _nb(t): return t.replace('《', '').replace('》', '')
    for v in [title, _fw(title), _nb(title), _nb(_fw(title))]:
        if v in index:
            return index[v]
    return None


def build_db(subjects: dict):
    """建立 flk_content.db，laws.id 与主库 law_content.db 对齐。"""
    if FLK_DB.exists():
        FLK_DB.unlink()

    # 建立主库标题索引
    if MAIN_DB.exists():
        main_conn = sqlite3.connect(MAIN_DB)
        main_index = _build_main_title_index(main_conn)
        main_conn.close()
    else:
        main_index = {}
        print('  ⚠ 主库不存在，laws.id 将使用自增序号')

    conn = sqlite3.connect(FLK_DB)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")

    fallback_id = -1    # 主库无匹配时用负数，避免与正数 id 冲突
    total_laws = 0
    total_articles = 0
    unmatched_titles = []

    for subject in SUBJECT_ORDER:
        laws_list = subjects.get(subject, [])
        print(f'\n{subject} ({len(laws_list)} 部)...')
        for law_node in laws_list:
            parsed = parse_law(law_node, subject)
            if not parsed:
                print(f'  ✗ 跳过（无缓存）: {law_node.get("content","")}')
                continue

            main_id = _lookup_main_id(main_index, parsed['title'])
            if main_id is not None:
                law_row_id = main_id
            else:
                law_row_id = fallback_id
                fallback_id -= 1
                unmatched_titles.append(parsed['title'])

            conn.execute(
                "INSERT INTO laws (id, flk_id, title, subject, json_url) VALUES (?,?,?,?,?)",
                (law_row_id, parsed['flk_id'], parsed['title'],
                 parsed['subject'], parsed['json_url'])
            )

            law_articles = 0
            for sec in parsed['sections']:
                conn.execute(
                    "INSERT INTO sections (law_id, flk_node_id, parent_node_id, type, title, position, full_text) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (law_row_id, sec['id'], sec['parent_id'],
                     sec['type'], sec['content'],
                     sec['position'], sec['text'])
                )
                sec_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                arts = extract_articles(sec['text'])
                for art in arts:
                    conn.execute(
                        "INSERT INTO articles (law_id, section_id, article_number, content) VALUES (?,?,?,?)",
                        (law_row_id, sec_id, art['article_number'], art['content'])
                    )
                    conn.execute(
                        "INSERT INTO articles_fts (rowid, content, article_number) "
                        "SELECT last_insert_rowid(), content, article_number FROM articles WHERE id=last_insert_rowid()"
                    )
                law_articles += len(arts)

            conn.execute(
                "UPDATE laws SET total_sections=?, total_articles=? WHERE id=?",
                (len(parsed['sections']), law_articles, law_row_id)
            )
            total_laws    += 1
            total_articles += law_articles

    conn.execute("INSERT INTO articles_fts(articles_fts) VALUES('optimize')")
    conn.commit()
    conn.close()

    matched = total_laws - len(unmatched_titles)
    print(f'\n数据库建立完成：{total_laws} 部法律，{total_articles} 条条文 → {FLK_DB}')
    print(f'  主库 id 对齐：{matched} 部匹配，{len(unmatched_titles)} 部未匹配（使用负数 id）')
    if unmatched_titles:
        for t in unmatched_titles:
            print(f'  ✗ {t}')


# ════════════════════════════════════════════════════════════════════════════
# 6. 交叉验证：与主数据库对比
# ════════════════════════════════════════════════════════════════════════════

def verify():
    """
    对比 flk_content.db 与 law_content.db 中相同法律的条文内容。
    输出：匹配率、典型差异。
    """
    if not FLK_DB.exists():
        print('flk_content.db 不存在，请先运行 pipeline。')
        return
    if not MAIN_DB.exists():
        print('law_content.db 不存在。')
        return

    flk  = sqlite3.connect(FLK_DB)
    main = sqlite3.connect(MAIN_DB)

    # 从法考库取所有法律标题
    flk_laws = flk.execute("SELECT id, title FROM laws ORDER BY id").fetchall()

    matched_laws   = 0
    unmatched_laws = 0
    report = []

    for flk_law_id, title in flk_laws:
        # 在主库里找同名法律（标题可能有半角/全角差异）
        norm_title = title.replace('(', '（').replace(')', '）')
        main_rows = main.execute(
            "SELECT id, title FROM laws WHERE (title=? OR title=?) AND is_current=1",
            (title, norm_title)
        ).fetchall()

        if not main_rows:
            unmatched_laws += 1
            report.append(('未匹配', title, None, None))
            continue

        main_law_id, main_title = main_rows[0]
        matched_laws += 1

        # 取两库条文（按条号）
        flk_arts = {
            row[0]: row[1]
            for row in flk.execute(
                "SELECT article_number, content FROM articles WHERE law_id=? AND article_number!=''",
                (flk_law_id,)
            ).fetchall()
        }
        main_arts = {
            row[0]: row[1]
            for row in main.execute(
                "SELECT article_number, content FROM nodes WHERE law_id=? AND type='article' AND article_number!=''",
                (main_law_id,)
            ).fetchall()
        }

        if not flk_arts and not main_arts:
            continue

        # 对比
        common = set(flk_arts) & set(main_arts)
        only_flk  = set(flk_arts) - set(main_arts)
        only_main = set(main_arts) - set(flk_arts)

        diff_content = []
        for art_num in sorted(common):
            f_text = flk_arts[art_num].strip()
            m_text = main_arts[art_num].strip()
            # 去掉空白差异后比较
            if re.sub(r'\s+', '', f_text) != re.sub(r'\s+', '', m_text):
                diff_content.append(art_num)

        if only_flk or only_main or diff_content:
            report.append(('差异', title, {
                'only_flk':      sorted(only_flk)[:5],
                'only_main':     sorted(only_main)[:5],
                'diff_content':  diff_content[:5],
                'flk_total':     len(flk_arts),
                'main_total':    len(main_arts),
            }, None))

    flk.close()
    main.close()

    # 输出报告
    print(f'\n{'='*60}')
    print(f'交叉验证报告')
    print(f'{'='*60}')
    print(f'法考库法律总数：{len(flk_laws)}')
    print(f'  主库匹配：{matched_laws}')
    print(f'  主库未匹配：{unmatched_laws}')

    diffs = [r for r in report if r[0] == '差异']
    unmatched = [r for r in report if r[0] == '未匹配']

    if unmatched:
        print(f'\n【主库未收录】{len(unmatched)} 部：')
        for _, title, _, _ in unmatched:
            print(f'  - {title}')

    if diffs:
        print(f'\n【存在差异】{len(diffs)} 部：')
        for _, title, d, _ in diffs:
            print(f'\n  {title}')
            if d['only_flk']:
                print(f'    仅法考库有：{d["only_flk"]}')
            if d['only_main']:
                print(f'    仅主库有：{d["only_main"]}')
            if d['diff_content']:
                print(f'    内容不同的条：{d["diff_content"]}')
            print(f'    条文数：法考库={d["flk_total"]}  主库={d["main_total"]}')
    else:
        print('\n【无差异】所有匹配法律条文内容一致。')


# ════════════════════════════════════════════════════════════════════════════
# main
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='法考专用 Pipeline')
    parser.add_argument('--skip-dl', action='store_true', help='跳过下载（使用缓存）')
    parser.add_argument('--skip-db', action='store_true', help='只下载，不建库')
    parser.add_argument('--verify',  action='store_true', help='只跑交叉验证')
    args = parser.parse_args()

    if args.verify:
        verify()
        return

    print('=== 解析 tree_data.js ===')
    subjects = load_tree()

    if not args.skip_dl:
        print('\n=== 下载法律 JSON ===')
        download_all(subjects)
    else:
        print('\n[跳过下载]')

    if not args.skip_db:
        print('\n=== 建立 flk_content.db ===')
        build_db(subjects)

    print('\n=== 交叉验证 ===')
    verify()

    print('\n=== 完成 ===')


if __name__ == '__main__':
    main()
