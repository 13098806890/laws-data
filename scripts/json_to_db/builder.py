#!/usr/bin/env python3
"""
JSON → SQLite
用法：python3 -m json_to_db.builder
"""

import json
import re
import sqlite3
from pathlib import Path

from config import JSON_DIR, DB_PATH
from utils import pub_date_from_stem
from docx_to_json.subject_area import get_subject_area
from docx_to_json.converter import clean_article_content
from law_aliases import ALIASES

_CN_ORD = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,
           '九':9,'十':10,'百':100,'千':1000}

def _cn_to_int(s: str) -> int:
    s = s.strip()
    result = tmp = 0
    for c in s:
        v = _CN_ORD.get(c, 0)
        if v >= 10:
            result += (tmp or 1) * v
            tmp = 0
        else:
            tmp = v
    return result + tmp

_ART_NUM_RE = re.compile(r'^第([零一二三四五六七八九十百千]+)条')

_CJK_RE = re.compile(r'[一-鿿]')

def create_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS laws (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            filename TEXT UNIQUE NOT NULL,
            category TEXT,
            legal_domain TEXT,
            subject_area TEXT,
            pub_date TEXT,
            effective_date TEXT,
            promulgation_info TEXT,
            issuing_org TEXT,
            doc_number TEXT,
            total_articles INTEGER,
            full_text TEXT,
            version_date TEXT,
            is_current INTEGER DEFAULT 1,
            aliases TEXT,
            is_flk INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY,
            law_id INTEGER NOT NULL REFERENCES laws(id),
            parent_id INTEGER REFERENCES nodes(id),
            type TEXT NOT NULL,
            title TEXT,
            article_number TEXT,
            content TEXT,
            order_index INTEGER,
            global_order INTEGER,
            part_num    INTEGER,
            chapter_num INTEGER,
            section_num INTEGER,
            article_num INTEGER
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
            content,
            article_number,
            content="nodes",
            content_rowid="id",
            tokenize='trigram'
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts_bigram USING fts5(
            content,
            article_number,
            content="nodes",
            content_rowid="id",
            tokenize='unicode61'
        );
        CREATE TABLE IF NOT EXISTS article_references (
            id               INTEGER PRIMARY KEY,
            from_node_id     INTEGER REFERENCES nodes(id),
            from_law_id      INTEGER REFERENCES laws(id),
            from_article_num INTEGER,
            from_chapter_num INTEGER,
            from_section_num INTEGER,
            from_part_num    INTEGER,
            to_node_id       INTEGER REFERENCES nodes(id),
            to_law_id        INTEGER REFERENCES laws(id),
            to_article_num   INTEGER,
            to_chapter_num   INTEGER,
            to_section_num   INTEGER,
            to_part_num      INTEGER,
            ref_type         TEXT,
            resolved         INTEGER,
            raw_text         TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_nodes_law    ON nodes(law_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_order  ON nodes(law_id, global_order);
        CREATE INDEX IF NOT EXISTS idx_laws_title   ON laws(title);
        CREATE INDEX IF NOT EXISTS idx_nodes_nums   ON nodes(law_id, part_num, chapter_num, section_num, article_num);
    """)


def _clean_text(t: str) -> str:
    """去除多余换行和空格，保留段落间单个换行。"""
    if not t:
        return t
    # 合并连续空白行为单个换行
    t = re.sub(r'\n{2,}', '\n', t)
    # 去除行首行尾多余空格（保留换行本身）
    t = '\n'.join(line.strip() for line in t.split('\n'))
    # 去除多余空格（非换行）
    t = re.sub(r'[ \t]{2,}', ' ', t)
    return t.strip()


def _insert_article(conn, law_id, parent_id, art, oi, go, coords):
    art_title  = art.get('title', '').strip()
    content    = art.get('content', '')
    art_number = art_title.rstrip('　 ')
    m = _ART_NUM_RE.match(art_number)
    art_num = _cn_to_int(m.group(1)) if m else oi
    pt_num  = coords[0] if len(coords) > 0 else None
    ch_num  = coords[1] if len(coords) > 1 else None
    sec_num = coords[2] if len(coords) > 2 else None
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, article_number,
                              content, order_index, global_order,
                              part_num, chapter_num, section_num, article_num)
           VALUES (?,?,'article',?,?,?,?,?,?,?,?,?)""",
        (law_id, parent_id, art_title, art_number, content, oi, go,
         pt_num, ch_num, sec_num, art_num)
    )
    conn.execute(
        "INSERT INTO nodes_fts(rowid, content, article_number) VALUES(?,?,?)",
        (cur.lastrowid, content, art_number)
    )
    conn.execute(
        "INSERT INTO nodes_fts_bigram(rowid, content, article_number) VALUES(?,?,?)",
        (cur.lastrowid, content, art_number)
    )


def _insert_section(conn, law_id, parent_id, sec, coords):
    t = sec.get('title', '').strip()
    sec_num = sec.get('order_index')
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, content,
                              order_index, global_order,
                              part_num, chapter_num, section_num)
           VALUES (?,?,'section',?,?,?,?,?,?,?)""",
        (law_id, parent_id, t, t, sec.get('order_index'), sec.get('global_order'),
         coords[0], coords[1], sec_num)
    )
    child_coords = (coords[0], coords[1], sec_num)
    for a in sec.get('articles', []):
        _insert_article(conn, law_id, cur.lastrowid, a, a.get('order_index'), a.get('global_order'), child_coords)


def _insert_chapter(conn, law_id, parent_id, ch, coords):
    t = ch.get('title', '').strip()
    if t.startswith('_DIRECT_'):
        # 编下直属条文占位章：不创建 chapter 节点，文章直接挂到编（parent_id）下
        for a in ch.get('articles', []):
            _insert_article(conn, law_id, parent_id, a, a.get('order_index'), a.get('global_order'), coords)
        return
    ch_num = ch.get('order_index')
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, content,
                              order_index, global_order,
                              part_num, chapter_num)
           VALUES (?,?,'chapter',?,?,?,?,?,?)""",
        (law_id, parent_id, t, t, ch.get('order_index'), ch.get('global_order'),
         coords[0], ch_num)
    )
    cid = cur.lastrowid
    child_coords = (coords[0], ch_num)
    for s in ch.get('sections', []):
        _insert_section(conn, law_id, cid, s, child_coords)
    for a in ch.get('articles', []):
        _insert_article(conn, law_id, cid, a, a.get('order_index'), a.get('global_order'), child_coords)


def insert_nodes(conn, law_id: int, data: dict):
    if 'parts' in data:
        for pt in data['parts']:
            t = (pt.get('title') or '').strip()
            pt_num = pt.get('order_index')
            cur = conn.execute(
                """INSERT INTO nodes (law_id, parent_id, type, title, content,
                                      order_index, global_order, part_num)
                   VALUES (?,NULL,'part',?,?,?,?,?)""",
                (law_id, t, t, pt.get('order_index'), pt.get('global_order'), pt_num)
            )
            for ch in pt.get('chapters', []):
                _insert_chapter(conn, law_id, cur.lastrowid, ch, (pt_num,))
    else:
        chapters = data.get('chapters', [])
        if chapters:
            for ch in chapters:
                _insert_chapter(conn, law_id, None, ch, (None,))
        else:
            full_text = (data.get('full_text') or '').strip()
            if full_text:
                full_text = clean_article_content(full_text)
                _insert_article(conn, law_id, None,
                                {'title': '', 'content': full_text}, 1, 1, (None, None, None))


def build_db(json_dir: Path = JSON_DIR, db_path: Path = DB_PATH):
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=DELETE')  # iOS bundle 不支持 WAL（只读目录无法创建 -wal/-shm）
    conn.execute('PRAGMA foreign_keys=ON')
    create_schema(conn)

    paths = sorted(p for p in json_dir.rglob('*.json') if 'index' not in p.name)
    print(f'写入数据库: {len(paths)} 个文件')

    for i, path in enumerate(paths):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        stem         = path.stem
        version_date = pub_date_from_stem(stem)
        category     = data.get('category')
        subject_area = get_subject_area(data['title'], category)
        aliases      = ALIASES.get(data['title'], '')
        cur = conn.execute(
            """INSERT INTO laws (id, title, filename, category, legal_domain, subject_area, pub_date,
                                 effective_date, promulgation_info, issuing_org, doc_number,
                                 total_articles, full_text, version_date, is_current, aliases, is_flk)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,0)""",
            (data.get('law_id'), data['title'], stem, category, data.get('legal_domain'),
             subject_area,
             data.get('pub_date'), data.get('effective_date'),
             data.get('promulgation_info'), data.get('issuing_org'), data.get('doc_number'),
             data.get('total_articles'), _clean_text(data.get('full_text', '')),
             version_date, aliases if aliases else None)
        )
        insert_nodes(conn, data.get('law_id'), data)

        if (i + 1) % 200 == 0:
            print(f'  {i+1}/{len(paths)}')
            conn.commit()

    conn.commit()
    conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('optimize')")
    conn.execute("INSERT INTO nodes_fts_bigram(nodes_fts_bigram) VALUES('optimize')")
    conn.commit()

    # 多版本标记：同名法律只保留最新 pub_date 为 is_current=1
    conn.execute("""
        UPDATE laws SET is_current = 0
        WHERE id NOT IN (
            SELECT id FROM laws l1
            WHERE pub_date = (
                SELECT MAX(pub_date) FROM laws l2 WHERE l2.title = l1.title
            )
        )
    """)
    conn.commit()

    # 法考标记：从 法考目录.json 中读取法律标题集合，匹配并打标
    flk_path = db_path.parent / '法考' / '法考目录.json'
    if flk_path.exists():
        flk_data = json.loads(flk_path.read_text(encoding='utf-8'))
        flk_titles: set[str] = set()
        for laws_list in flk_data.values():
            flk_titles.update(laws_list)
        # 规范化：半角括号→全角括号、去书名号，用于模糊匹配
        # 不去掉末尾括号内容，否则"修正案(四)"和"修正案(十二)"会变成同一个键导致误匹配
        def _to_fw(t: str) -> str:
            return t.replace('(', '（').replace(')', '）')
        def _no_marks(t: str) -> str:
            return t.replace('《', '').replace('》', '')
        # 建立四种规范化形式的查找集合
        flk_variants: set[str] = set()
        for t in flk_titles:
            flk_variants.update([t, _to_fw(t), _no_marks(t), _no_marks(_to_fw(t))])
        # 精确匹配优先，然后规范化匹配
        all_laws = conn.execute('SELECT id, title FROM laws').fetchall()
        matched_ids = []
        for law_id, title in all_laws:
            if (title in flk_titles or title in flk_variants
                    or _to_fw(title) in flk_variants
                    or _no_marks(title) in flk_variants
                    or _no_marks(_to_fw(title)) in flk_variants):
                matched_ids.append(law_id)
        if matched_ids:
            conn.executemany('UPDATE laws SET is_flk=1 WHERE id=?', [(i,) for i in matched_ids])
            conn.commit()
        flk_count = conn.execute('SELECT COUNT(*) FROM laws WHERE is_flk=1').fetchone()[0]
        print(f'法考标记完成：{flk_count} 部法律标记为 is_flk=1')
    else:
        print('未找到 法考目录.json，跳过法考标记')

    laws     = conn.execute('SELECT COUNT(*) FROM laws').fetchone()[0]
    nodes    = conn.execute('SELECT COUNT(*) FROM nodes').fetchone()[0]
    articles = conn.execute("SELECT COUNT(*) FROM nodes WHERE type='article'").fetchone()[0]
    size_mb  = db_path.stat().st_size / 1024 / 1024
    print(f'数据库完成: laws={laws} nodes={nodes} articles={articles} {size_mb:.1f}MB')
    conn.close()


def load_references(db_path: Path = DB_PATH,
                    refs_path: Path = Path(__file__).parent.parent.parent / 'references' / 'article_references.json'):
    """将 article_references.json 填入 article_references 表。"""
    if not refs_path.exists():
        print(f'  引用文件不存在：{refs_path}')
        return

    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys=ON')

    # 建立坐标 → node_id 索引：(law_id, article_num) → node_id
    rows = conn.execute(
        "SELECT law_id, article_num, id FROM nodes WHERE type='article' AND article_num IS NOT NULL"
    ).fetchall()
    node_index = {}
    for law_id, article_num, node_id in rows:
        node_index[(law_id, article_num)] = node_id

    conn.execute('DELETE FROM article_references')

    data = json.loads(refs_path.read_text(encoding='utf-8'))
    batch = []
    for entry in data:
        from_law_id      = entry.get('from_law_id')
        from_article_num = entry.get('from_article_num')
        from_chapter_num = entry.get('from_chapter_num')
        from_section_num = entry.get('from_section_num')
        from_part_num    = entry.get('from_part_num')
        from_node_id     = node_index.get((from_law_id, from_article_num))

        for ref in entry.get('refs', []):
            to_law_id      = ref.get('to_law_id')
            to_article_num = ref.get('to_article_num')
            to_chapter_num = ref.get('to_chapter_num')
            to_section_num = ref.get('to_section_num')
            to_part_num    = ref.get('to_part_num')
            to_node_id     = node_index.get((to_law_id, to_article_num)) if to_law_id and to_article_num else None

            batch.append((
                from_node_id, from_law_id, from_article_num, from_chapter_num, from_section_num, from_part_num,
                to_node_id,   to_law_id,   to_article_num,   to_chapter_num,   to_section_num,   to_part_num,
                ref.get('type'), 1 if ref.get('resolved') else 0, ref.get('raw_text'),
            ))

    conn.executemany(
        """INSERT INTO article_references
           (from_node_id, from_law_id, from_article_num, from_chapter_num, from_section_num, from_part_num,
            to_node_id,   to_law_id,   to_article_num,   to_chapter_num,   to_section_num,   to_part_num,
            ref_type, resolved, raw_text)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        batch
    )
    conn.commit()

    total    = conn.execute('SELECT COUNT(*) FROM article_references').fetchone()[0]
    resolved = conn.execute('SELECT COUNT(*) FROM article_references WHERE resolved=1').fetchone()[0]
    cross    = conn.execute("SELECT COUNT(*) FROM article_references WHERE ref_type='cross_law'").fetchone()[0]
    self_    = conn.execute("SELECT COUNT(*) FROM article_references WHERE ref_type='self_ref'").fetchone()[0]
    conn.close()
    print(f'引用关系写入完成：共 {total} 条（跨法 {cross} / 自引 {self_}），已解析 {resolved} 条')


def run():
    print('\n=== JSON → 数据库 ===')
    build_db()
    print('\n=== 写入引用关系 ===')
    try:
        load_references()
    except Exception as e:
        print(f'  引用关系写入失败（非致命）: {e}')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
