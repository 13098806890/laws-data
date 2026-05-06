#!/usr/bin/env python3
"""
Translate law_content.db into English, producing law_content_en.db.

Schema of law_content_en.db:
  law_translations  (law_id, title_en, category_en, legal_domain_en,
                     subject_area_en, issuing_org_en)
  node_translations (node_id, law_id, title_en, article_number_en, content_en)
  meta              (key, value)   — stores progress so runs are resumable

Usage:
  export ANTHROPIC_API_KEY=sk-ant-...
  cd /Users/doxie/laws_data
  python3 scripts/translate_to_en.py [--batch-size 20] [--workers 4] [--dry-run]

The script is fully resumable: already-translated rows are skipped.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SRC_DB  = Path("/Users/doxie/laws_data/law_content.db")
DST_DB  = Path("/Users/doxie/laws_data/law_content_en.db")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-haiku-4-5"

# Static enum translations (no API needed)
CN_DIGITS = {
    "零":0,"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,
    "十":10,"百":100,"千":1000,"万":10000,
}

def cn_to_int(s: str) -> int | None:
    """Convert a Chinese numeral string to an integer, e.g. '一百二十三' → 123."""
    if not s:
        return None
    result = 0
    current = 0
    for ch in s:
        v = CN_DIGITS.get(ch)
        if v is None:
            return None
        if v >= 10:
            if current == 0:
                current = 1
            result += current * v
            current = 0
        else:
            current = v
    result += current
    return result if result else None

def cn_article_number_to_en(an: str | None) -> str:
    """Convert '第一百二十三条' → 'Article 123', pass through non-Chinese."""
    if not an:
        return an or ""
    import re
    m = re.match(r"第([零一二三四五六七八九十百千]+)条", an.strip())
    if m:
        n = cn_to_int(m.group(1))
        if n is not None:
            return f"Article {n}"
    return an


CATEGORY_MAP = {
    "宪法":    "Constitution",
    "法律":    "Law",
    "修正案":  "Amendment",
    "决定":    "Decision",
    "法律解释": "Legal Interpretation",
    "司法解释": "Judicial Interpretation",
    "行政法规": "Administrative Regulation",
    "监察法规": "Supervisory Regulation",
}

DOMAIN_MAP = {
    "宪法相关法":        "Constitutional Law",
    "民法典":            "Civil Code",
    "民法商法":          "Civil & Commercial Law",
    "刑法":              "Criminal Law",
    "行政法":            "Administrative Law",
    "经济法":            "Economic Law",
    "社会法":            "Social Law",
    "诉讼与非诉讼程序法": "Procedural Law",
}

ORG_MAP = {
    "最高人民法院":             "Supreme People's Court",
    "最高人民检察院":           "Supreme People's Procuratorate",
    "国务院":                   "State Council",
    "全国人民代表大会常务委员会": "NPC Standing Committee",
    "全国人民代表大会":          "National People's Congress",
    "国家监察委员会":            "National Supervisory Commission",
}


def api_call(api_key: str, messages: list[dict], system: str = "") -> str:
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 4096,
        "system": system,
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())["content"][0]["text"]


TITLE_SYSTEM = """You are a professional legal translator specializing in Chinese law.
Translate the given Chinese law title into English accurately and concisely.
Output only the translated title, nothing else."""

ARTICLE_SYSTEM = """You are a professional legal translator specializing in Chinese law.
Translate the given Chinese legal article into English.
Preserve legal precision, article numbers (第X条 → Article X), and structure.
Output only the translated text, nothing else."""

BATCH_ARTICLE_SYSTEM = """You are a professional legal translator specializing in Chinese law.
You will receive a JSON array of objects, each with "id" and "text" fields containing Chinese legal article text.
Translate each article into English. Preserve legal precision, article numbers (第X条 → Article X), and structure.
Return a JSON array with the same objects, adding an "en" field with the English translation.
Output only the JSON array, nothing else."""


def translate_title(api_key: str, title: str) -> str:
    return api_call(api_key, [{"role": "user", "content": f"Translate this Chinese law title:\n{title}"}], TITLE_SYSTEM)


def translate_articles_batch(api_key: str, items: list[tuple[int, str]]) -> dict[int, str]:
    """Translate a batch of (node_id, content) pairs. Returns {node_id: translated_text}."""
    payload = json.dumps([{"id": nid, "text": text} for nid, text in items], ensure_ascii=False)
    raw = api_call(api_key, [{"role": "user", "content": payload}], BATCH_ARTICLE_SYSTEM)
    # parse JSON from response
    s = raw.find("[")
    e = raw.rfind("]") + 1
    if s < 0 or e <= s:
        raise ValueError(f"No JSON array in response: {raw[:200]}")
    result = json.loads(raw[s:e])
    return {obj["id"]: obj["en"] for obj in result if "id" in obj and "en" in obj}


def init_dst_db(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS law_translations (
        law_id          INTEGER PRIMARY KEY,
        title_en        TEXT,
        category_en     TEXT,
        legal_domain_en TEXT,
        subject_area_en TEXT,
        issuing_org_en  TEXT
    );
    CREATE TABLE IF NOT EXISTS node_translations (
        node_id         INTEGER PRIMARY KEY,
        law_id          INTEGER,
        title_en        TEXT,
        article_number_en TEXT,
        content_en      TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_node_trans_law ON node_translations(law_id);
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    conn.commit()


def get_done_ids(conn: sqlite3.Connection, table: str, id_col: str) -> set[int]:
    return {row[0] for row in conn.execute(f"SELECT {id_col} FROM {table}")}


def static_translate_law(row) -> dict:
    law_id, title, category, legal_domain, subject_area, issuing_org = row
    return {
        "law_id":          law_id,
        "category_en":     CATEGORY_MAP.get(category, category),
        "legal_domain_en": DOMAIN_MAP.get(legal_domain, legal_domain),
        "subject_area_en": subject_area or "",
        "issuing_org_en":  ORG_MAP.get(issuing_org or "", issuing_org or ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=20, help="Articles per API call")
    parser.add_argument("--workers",    type=int, default=4,  help="Parallel API workers")
    parser.add_argument("--dry-run",    action="store_true",  help="Count work without calling API")
    parser.add_argument("--laws-only",  action="store_true",  help="Translate law titles only")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY not set. Export it and retry.", file=sys.stderr)
        sys.exit(1)

    src = sqlite3.connect(SRC_DB)
    dst = sqlite3.connect(DST_DB)
    init_dst_db(dst)

    # ── 1. Law titles ──────────────────────────────────────────────────
    all_laws = src.execute(
        "SELECT id, title, category, legal_domain, subject_area, issuing_org "
        "FROM laws WHERE is_current=1"
    ).fetchall()

    done_law_ids = get_done_ids(dst, "law_translations", "law_id")
    pending_laws = [r for r in all_laws if r[0] not in done_law_ids]
    print(f"Laws: {len(all_laws)} total, {len(done_law_ids)} done, {len(pending_laws)} pending")

    if args.dry_run:
        all_nodes = src.execute(
            "SELECT id, law_id, title, article_number, content, type FROM nodes "
            "WHERE law_id IN (SELECT id FROM laws WHERE is_current=1)"
        ).fetchall()
        done_node_ids = get_done_ids(dst, "node_translations", "node_id")
        pending_nodes = [r for r in all_nodes if r[0] not in done_node_ids]
        total_chars = sum(len(r[4] or "") for r in pending_nodes if r[5] == "article")
        print(f"Nodes: {len(all_nodes)} total, {len(done_node_ids)} done, {len(pending_nodes)} pending")
        print(f"Article chars to translate: ~{total_chars:,}")
        print(f"Estimated batches: {len([r for r in pending_nodes if r[5]=='article']) // args.batch_size + 1}")
        src.close(); dst.close()
        return

    # Fill static fields for all laws first (no API)
    for row in pending_laws:
        d = static_translate_law(row)
        dst.execute(
            "INSERT OR IGNORE INTO law_translations(law_id,category_en,legal_domain_en,subject_area_en,issuing_org_en) "
            "VALUES(?,?,?,?,?)",
            (d["law_id"], d["category_en"], d["legal_domain_en"], d["subject_area_en"], d["issuing_org_en"])
        )
    dst.commit()
    print(f"Static fields filled for {len(pending_laws)} laws.")

    # Translate law titles via API
    title_pending = [r for r in all_laws if r[0] not in done_law_ids or
                     dst.execute("SELECT title_en FROM law_translations WHERE law_id=?", [r[0]]).fetchone()[0] is None]
    print(f"Translating {len(title_pending)} law titles...")

    def translate_one_title(row):
        law_id, title = row[0], row[1]
        try:
            title_en = translate_title(api_key, title)
            return law_id, title_en.strip()
        except Exception as e:
            return law_id, f"[Translation error: {e}]"

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(translate_one_title, r): r for r in title_pending}
        for fut in as_completed(futures):
            law_id, title_en = fut.result()
            dst.execute("UPDATE law_translations SET title_en=? WHERE law_id=?", [title_en, law_id])
            done += 1
            if done % 50 == 0:
                dst.commit()
                print(f"  Titles: {done}/{len(title_pending)}")
    dst.commit()
    print(f"Law titles done.")

    if args.laws_only:
        src.close(); dst.close()
        return

    # ── 2. Nodes ───────────────────────────────────────────────────────
    all_nodes = src.execute(
        "SELECT id, law_id, title, article_number, content, type FROM nodes "
        "WHERE law_id IN (SELECT id FROM laws WHERE is_current=1)"
    ).fetchall()

    done_node_ids = get_done_ids(dst, "node_translations", "node_id")
    pending_nodes = [r for r in all_nodes if r[0] not in done_node_ids]
    articles  = [r for r in pending_nodes if r[5] == "article"]
    non_arts  = [r for r in pending_nodes if r[5] != "article"]
    print(f"Nodes pending: {len(pending_nodes)} ({len(articles)} articles, {len(non_arts)} structural)")

    # Non-article nodes (chapter/section/part titles) — translate in batches too
    def insert_node(node_id, law_id, title_en, article_number_en, content_en):
        dst.execute(
            "INSERT OR IGNORE INTO node_translations(node_id,law_id,title_en,article_number_en,content_en) "
            "VALUES(?,?,?,?,?)",
            (node_id, law_id, title_en, article_number_en, content_en)
        )

    # Translate structural node titles (chapter/section titles are short, batch them)
    structural_items = [(r[0], r[2] or "") for r in non_arts]  # (node_id, title)
    print(f"Translating {len(structural_items)} structural titles...")
    done = 0
    for i in range(0, len(structural_items), args.batch_size):
        batch = structural_items[i:i + args.batch_size]
        try:
            translations = translate_articles_batch(api_key, batch)
            for node_id, title_zh in batch:
                row = next(r for r in non_arts if r[0] == node_id)
                title_en = translations.get(node_id, title_zh)
                insert_node(node_id, row[1], title_en, cn_article_number_to_en(row[3]), title_en)
        except Exception as e:
            print(f"  Structural batch {i} error: {e}, inserting raw")
            for node_id, title_zh in batch:
                row = next(r for r in non_arts if r[0] == node_id)
                insert_node(node_id, row[1], title_zh, row[3], title_zh)
        done += len(batch)
        if done % 200 == 0:
            dst.commit()
            print(f"  Structural: {done}/{len(structural_items)}")
    dst.commit()

    # Translate article content in batches
    article_items = [(r[0], r[4] or "") for r in articles]  # (node_id, content)
    total_batches = (len(article_items) + args.batch_size - 1) // args.batch_size
    print(f"Translating {len(article_items)} articles in {total_batches} batches (workers={args.workers})...")

    batches = [article_items[i:i+args.batch_size] for i in range(0, len(article_items), args.batch_size)]
    node_lookup = {r[0]: r for r in articles}

    done_batches = 0
    errors = 0
    lock_results = []

    def translate_batch(batch):
        for attempt in range(3):
            try:
                return translate_articles_batch(api_key, batch)
            except Exception as e:
                if attempt == 2:
                    return {nid: text for nid, text in batch}  # fallback: keep Chinese
                time.sleep(2 ** attempt)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(translate_batch, b): b for b in batches}
        for fut in as_completed(futures):
            translations = fut.result()
            batch = futures[fut]
            for node_id, _ in batch:
                row = node_lookup[node_id]
                content_en = translations.get(node_id, row[4] or "")
                an_en = cn_article_number_to_en(row[3])
                insert_node(node_id, row[1], row[2], an_en, content_en)
            done_batches += 1
            if done_batches % 10 == 0:
                dst.commit()
                pct = done_batches * 100 // total_batches
                print(f"  Batches: {done_batches}/{total_batches} ({pct}%)")

    dst.commit()
    print("All translations complete.")

    # ── 3. FTS index for English ───────────────────────────────────────
    print("Building English FTS index...")
    dst.executescript("""
    DROP TABLE IF EXISTS node_translations_fts;
    CREATE VIRTUAL TABLE node_translations_fts USING fts5(
        content_en,
        article_number_en,
        content='node_translations',
        content_rowid='node_id',
        tokenize='porter unicode61'
    );
    INSERT INTO node_translations_fts(rowid, content_en, article_number_en)
    SELECT node_id, content_en, article_number_en FROM node_translations;
    """)
    dst.commit()
    print("FTS index built.")

    src.close()
    dst.close()
    print(f"Done. Output: {DST_DB}")


if __name__ == "__main__":
    main()
