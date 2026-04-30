#!/usr/bin/env python3
"""
JSON → SQLite
用法：python3 -m json_to_db.builder
"""

import json
import sqlite3
from pathlib import Path

from config import JSON_DIR, DB_PATH
from utils import pub_date_from_stem


def create_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS laws (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            filename TEXT UNIQUE NOT NULL,
            category TEXT,
            legal_domain TEXT,
            pub_date TEXT,
            effective_date TEXT,
            promulgation_info TEXT,
            issuing_org TEXT,
            doc_number TEXT,
            total_articles INTEGER,
            version_date TEXT,
            is_current INTEGER DEFAULT 1
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
            global_order INTEGER
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
            content,
            article_number,
            tokenize='trigram'
        );
        CREATE TABLE IF NOT EXISTS article_references (
            from_id INTEGER REFERENCES nodes(id),
            to_id INTEGER REFERENCES nodes(id),
            PRIMARY KEY (from_id, to_id)
        );
        CREATE INDEX IF NOT EXISTS idx_nodes_law    ON nodes(law_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_order  ON nodes(law_id, global_order);
        CREATE INDEX IF NOT EXISTS idx_laws_title   ON laws(title);
    """)


def _insert_article(conn, law_id, parent_id, art, oi, go):
    art_title  = art.get('title', '').strip()
    content    = art.get('content', '')
    art_number = art_title.rstrip('　 ')
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, article_number,
                              content, order_index, global_order)
           VALUES (?,?,'article',?,?,?,?,?)""",
        (law_id, parent_id, art_title, art_number, content, oi, go)
    )
    conn.execute(
        "INSERT INTO nodes_fts(rowid, content, article_number) VALUES(?,?,?)",
        (cur.lastrowid, content, art_number)
    )


def _insert_section(conn, law_id, parent_id, sec):
    t = sec.get('title', '').strip()
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, content,
                              order_index, global_order)
           VALUES (?,?,'section',?,?,?,?)""",
        (law_id, parent_id, t, t, sec.get('order_index'), sec.get('global_order'))
    )
    for a in sec.get('articles', []):
        _insert_article(conn, law_id, cur.lastrowid, a, a.get('order_index'), a.get('global_order'))


def _insert_chapter(conn, law_id, parent_id, ch):
    t = ch.get('title', '').strip()
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, content,
                              order_index, global_order)
           VALUES (?,?,'chapter',?,?,?,?)""",
        (law_id, parent_id, t, t, ch.get('order_index'), ch.get('global_order'))
    )
    cid = cur.lastrowid
    for s in ch.get('sections', []):
        _insert_section(conn, law_id, cid, s)
    for a in ch.get('articles', []):
        _insert_article(conn, law_id, cid, a, a.get('order_index'), a.get('global_order'))


def insert_nodes(conn, law_id: int, data: dict):
    if 'parts' in data:
        for pt in data['parts']:
            t = (pt.get('title') or '').strip()
            cur = conn.execute(
                """INSERT INTO nodes (law_id, parent_id, type, title, content,
                                      order_index, global_order)
                   VALUES (?,NULL,'part',?,?,?,?)""",
                (law_id, t, t, pt.get('order_index'), pt.get('global_order'))
            )
            for ch in pt.get('chapters', []):
                _insert_chapter(conn, law_id, cur.lastrowid, ch)
    else:
        chapters = data.get('chapters', [])
        if chapters:
            for ch in chapters:
                _insert_chapter(conn, law_id, None, ch)
        else:
            full_text = (data.get('full_text') or '').strip()
            if full_text:
                _insert_article(conn, law_id, None,
                                {'title': '', 'content': full_text}, 1, 1)


def build_db(json_dir: Path = JSON_DIR, db_path: Path = DB_PATH):
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    create_schema(conn)

    paths = sorted(p for p in json_dir.rglob('*.json') if 'index' not in p.name)
    print(f'写入数据库: {len(paths)} 个文件')

    for i, path in enumerate(paths):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        stem         = path.stem
        version_date = pub_date_from_stem(stem)
        cur = conn.execute(
            """INSERT INTO laws (title, filename, category, legal_domain, pub_date,
                                 effective_date, promulgation_info, issuing_org, doc_number,
                                 total_articles, version_date, is_current)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""",
            (data['title'], stem, data.get('category'), data.get('legal_domain'),
             data.get('pub_date'), data.get('effective_date'),
             data.get('promulgation_info'), data.get('issuing_org'), data.get('doc_number'),
             data.get('total_articles'), version_date)
        )
        insert_nodes(conn, cur.lastrowid, data)

        if (i + 1) % 200 == 0:
            print(f'  {i+1}/{len(paths)}')
            conn.commit()

    conn.commit()
    conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('optimize')")
    conn.commit()

    laws     = conn.execute('SELECT COUNT(*) FROM laws').fetchone()[0]
    nodes    = conn.execute('SELECT COUNT(*) FROM nodes').fetchone()[0]
    articles = conn.execute("SELECT COUNT(*) FROM nodes WHERE type='article'").fetchone()[0]
    size_mb  = db_path.stat().st_size / 1024 / 1024
    print(f'数据库完成: laws={laws} nodes={nodes} articles={articles} {size_mb:.1f}MB')
    conn.close()


def run():
    print('\n=== JSON → 数据库 ===')
    build_db()


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
