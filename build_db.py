"""
从 JSON 文件构建 law_content.db
表结构：laws + nodes（编/章/节/条统一节点）+ nodes_fts + article_references
"""

import json
import glob
import sqlite3
import re
from pathlib import Path

DB_PATH = Path('/Users/doxie/laws_data/law_content.db')
JSON_DIR = '/Users/doxie/laws_data/json'


def create_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS laws (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            filename TEXT UNIQUE,
            category TEXT,
            legal_domain TEXT,
            pub_date TEXT,
            effective_date TEXT,
            promulgation_info TEXT,
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

        CREATE INDEX IF NOT EXISTS idx_nodes_law_id ON nodes(law_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_parent_id ON nodes(parent_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_global_order ON nodes(law_id, global_order);
        CREATE INDEX IF NOT EXISTS idx_laws_title ON laws(title);
    """)


def extract_version_date(filename):
    """从文件名提取版本日期，如 中华人民共和国民法典_20200528 -> 2020-05-28"""
    m = re.search(r'_(\d{4})(\d{2})(\d{2})$', Path(filename).stem)
    if m:
        return f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
    return None


def insert_law(conn, data, version_date, filename):
    cur = conn.execute(
        """INSERT INTO laws (title, filename, category, legal_domain, pub_date, effective_date,
                             promulgation_info, total_articles, version_date, is_current)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (
            data.get('title', ''),
            filename,
            data.get('category'),
            data.get('legal_domain'),
            data.get('pub_date'),
            data.get('effective_date'),
            data.get('promulgation_info'),
            data.get('total_articles'),
            version_date,
        )
    )
    return cur.lastrowid


def insert_article(conn, law_id, parent_id, article, order_index, global_order):
    title = article.get('title', '').strip()
    content = article.get('content', '')
    article_number = title.rstrip('　 ')

    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, article_number, content,
                              order_index, global_order)
           VALUES (?, ?, 'article', ?, ?, ?, ?, ?)""",
        (law_id, parent_id, title, article_number, content, order_index, global_order)
    )
    node_id = cur.lastrowid
    conn.execute(
        "INSERT INTO nodes_fts(rowid, content, article_number) VALUES (?, ?, ?)",
        (node_id, content, article_number)
    )


def insert_section(conn, law_id, parent_id, section):
    title = section.get('title', '').strip()
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, content,
                              order_index, global_order)
           VALUES (?, ?, 'section', ?, ?, ?, ?)""",
        (law_id, parent_id, title, title,
         section.get('order_index'), section.get('global_order'))
    )
    section_id = cur.lastrowid
    for article in section.get('articles', []):
        insert_article(conn, law_id, section_id, article,
                       article.get('order_index'), article.get('global_order'))


def insert_chapter(conn, law_id, parent_id, chapter):
    title = chapter.get('title', '').strip()
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, content,
                              order_index, global_order)
           VALUES (?, ?, 'chapter', ?, ?, ?, ?)""",
        (law_id, parent_id, title, title,
         chapter.get('order_index'), chapter.get('global_order'))
    )
    chapter_id = cur.lastrowid
    for section in chapter.get('sections', []):
        insert_section(conn, law_id, chapter_id, section)
    for article in chapter.get('articles', []):
        insert_article(conn, law_id, chapter_id, article,
                       article.get('order_index'), article.get('global_order'))


def insert_law_nodes(conn, law_id, data):
    if 'parts' in data:
        for part in data['parts']:
            title = part.get('title', '').strip()
            cur = conn.execute(
                """INSERT INTO nodes (law_id, parent_id, type, title, content,
                                      order_index, global_order)
                   VALUES (?, NULL, 'part', ?, ?, ?, ?)""",
                (law_id, title, title,
                 part.get('order_index'), part.get('global_order'))
            )
            part_id = cur.lastrowid
            for chapter in part.get('chapters', []):
                insert_chapter(conn, law_id, part_id, chapter)
    else:
        for chapter in data.get('chapters', []):
            insert_chapter(conn, law_id, None, chapter)


def rebuild_fts(conn):
    conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild')")


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    create_schema(conn)

    paths = sorted([
        p for p in glob.glob(f'{JSON_DIR}/**/*.json', recursive=True)
        if 'index' not in p
    ])

    print(f'导入 {len(paths)} 个文件...')
    for i, path in enumerate(paths):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        version_date = extract_version_date(path)
        filename = Path(path).stem
        law_id = insert_law(conn, data, version_date, filename)
        insert_law_nodes(conn, law_id, data)

        if (i + 1) % 200 == 0:
            print(f'  {i + 1}/{len(paths)}')
            conn.commit()

    conn.commit()
    print('重建 FTS 索引...')
    # FTS is populated inline during insert, optimize index
    conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('optimize')")
    conn.commit()

    # Stats
    law_count = conn.execute('SELECT COUNT(*) FROM laws').fetchone()[0]
    node_count = conn.execute('SELECT COUNT(*) FROM nodes').fetchone()[0]
    article_count = conn.execute("SELECT COUNT(*) FROM nodes WHERE type='article'").fetchone()[0]
    print(f'\n完成:')
    print(f'  laws:    {law_count}')
    print(f'  nodes:   {node_count}')
    print(f'  articles:{article_count}')
    print(f'  DB size: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB')

    conn.close()


if __name__ == '__main__':
    main()
