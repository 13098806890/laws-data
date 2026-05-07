import re
import sqlite3
from typing import Optional

from .config import DB_PATH


def _conn():
    return sqlite3.connect(DB_PATH)


def get_law_id(title: str) -> Optional[int]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM laws WHERE title = ? AND is_current = 1 LIMIT 1", [title]
        ).fetchone()
        return row[0] if row else None


def get_law_structure(law_id: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, type, title, content, global_order
               FROM nodes
               WHERE law_id = ? AND type IN ('part','chapter','section')
               ORDER BY global_order""",
            [law_id]
        ).fetchall()
    return [
        {"id": r[0], "type": r[1], "title": r[2], "content": r[3], "order": r[4]}
        for r in rows
    ]


def get_articles_in_node(node_id: int, law_id: int = 0) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, article_number, article_num, content
               FROM nodes
               WHERE parent_id = ? AND type = 'article'
               ORDER BY global_order""",
            [node_id]
        ).fetchall()
        sub_nodes = conn.execute(
            "SELECT id FROM nodes WHERE parent_id = ? AND type = 'section'", [node_id]
        ).fetchall()
    articles = [
        {"id": r[0], "article_number": r[1], "article_num": r[2], "content": r[3]}
        for r in rows
    ]
    for (sub_id,) in sub_nodes:
        articles.extend(get_articles_in_node(sub_id, law_id))
    return articles


def fts_search_in_law(keyword: str, law_title: str,
                      categories: Optional[list[str]] = None,
                      limit: int = 10) -> list[dict]:
    cjk = [c for c in keyword if '一' <= c <= '鿿']
    if len(cjk) < 3:
        return []
    cats = categories or ["法律", "宪法", "修正案", "法律解释", "监察法规", "司法解释"]
    cat_ph = ",".join("?" * len(cats))
    with _conn() as conn:
        rows = conn.execute(
            f"""SELECT n.id, l.title, l.category, n.article_number, n.article_num, n.content
                FROM nodes_fts f
                JOIN nodes n ON f.rowid = n.id
                JOIN laws  l ON n.law_id = l.id
                WHERE nodes_fts MATCH ?
                  AND n.type = 'article' AND l.is_current = 1
                  AND l.title = ?
                  AND l.category IN ({cat_ph})
                LIMIT ?""",
            [keyword, law_title] + cats + [limit]
        ).fetchall()
    return [
        {"id": r[0], "law": r[1], "category": r[2],
         "article_number": r[3], "article_num": r[4], "content": r[5]}
        for r in rows
    ]


def fts_search_domains(keyword: str, domains: list[str],
                       categories: list[str], limit: int = 10) -> list[dict]:
    cjk = [c for c in keyword if '一' <= c <= '鿿']
    if not cjk:
        return []
    domain_ph = ",".join("?" * len(domains))
    cat_ph    = ",".join("?" * len(categories))
    fts_table = "nodes_fts" if len(cjk) >= 3 else "nodes_fts_bigram"
    kw = keyword if len(cjk) >= 3 else " ".join(c for c in keyword if '一' <= c <= '鿿')
    with _conn() as conn:
        rows = conn.execute(
            f"""SELECT n.id, l.title, l.category, n.article_number, n.article_num, n.content
                FROM {fts_table} f
                JOIN nodes n ON f.rowid = n.id
                JOIN laws  l ON n.law_id = l.id
                WHERE {fts_table} MATCH ?
                  AND n.type = 'article' AND l.is_current = 1
                  AND l.legal_domain IN ({domain_ph})
                  AND l.category IN ({cat_ph})
                LIMIT ?""",
            [kw] + domains + categories + [limit]
        ).fetchall()
    return [
        {"id": r[0], "law": r[1], "category": r[2],
         "article_number": r[3], "article_num": r[4], "content": r[5]}
        for r in rows
    ]


def find_article_by_ref(law_title_fragment: str, article_number_str: str) -> Optional[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT n.id, l.title, l.category, n.article_number, n.article_num, n.content
               FROM nodes n JOIN laws l ON n.law_id = l.id
               WHERE l.title LIKE ? AND n.article_number = ? AND l.is_current = 1
               LIMIT 1""",
            [f"%{law_title_fragment}%", article_number_str]
        ).fetchone()
    if rows:
        return {"id": rows[0], "law": rows[1], "category": rows[2],
                "article_number": rows[3], "article_num": rows[4], "content": rows[5]}
    return None


_REF_PATTERN = re.compile(
    r'《([^》]{4,30})》第([一二三四五六七八九十百千零\d]+)条'
)
_SELF_REF_PATTERN = re.compile(
    r'(?:本法|依照|适用|参照)第([一二三四五六七八九十百千零\d]+)条'
)


def expand_references(articles: list[dict], verbose: bool = False) -> list[dict]:
    seen_ids = {a["id"] for a in articles}
    new_articles: list[dict] = []
    for art in articles:
        content = art.get("content", "")
        for m in _REF_PATTERN.finditer(content):
            law_frag = m.group(1)
            art_num  = f"第{m.group(2)}条"
            ref = find_article_by_ref(law_frag, art_num)
            if ref and ref["id"] not in seen_ids:
                seen_ids.add(ref["id"])
                ref["source"] = f"引用链:{art.get('article_number','')}→{art_num}"
                ref["pinned"] = False
                new_articles.append(ref)
                if verbose:
                    print(f"      引用链: {art.get('article_number','')} → 《{law_frag}》{art_num}")
        law_title = art.get("law", "")
        for m in _SELF_REF_PATTERN.finditer(content):
            art_num = f"第{m.group(1)}条"
            ref = find_article_by_ref(law_title, art_num)
            if ref and ref["id"] not in seen_ids:
                seen_ids.add(ref["id"])
                ref["source"] = f"同法引用:{art.get('article_number','')}→{art_num}"
                ref["pinned"] = False
                new_articles.append(ref)
    if verbose and new_articles:
        print(f"      引用链扩展 +{len(new_articles)} 条")
    return articles + new_articles
