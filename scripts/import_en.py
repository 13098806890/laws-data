#!/usr/bin/env python3
"""
Import json_en translations into law_content.db nodes.content_en.

Reads ALL json_en files (by scanning directories), matches articles by
article_number text, and updates content_en. Idempotent — skips nodes
that already have content_en unless --force is passed.

Usage:
  python3 scripts/import_en.py                        # incremental (skip existing)
  python3 scripts/import_en.py --force                # overwrite existing
  python3 scripts/import_en.py --report               # show what would change
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH

BASE_DIR = Path(__file__).parent.parent
JSON_EN_DIR = BASE_DIR / "json_en"

# Normalize whitespace for matching
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def iter_json_en_files():
    """Yield (law_id, title_en, articles_list, filepath) for every json_en file."""
    for cat_dir in sorted(JSON_EN_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        for fpath in sorted(cat_dir.glob("*.json")):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"  ⚠  parse error: {fpath.name} — {e}")
                continue
            law_id = data.get("law_id")
            if law_id is None:
                print(f"  ⚠  no law_id: {fpath.name}")
                continue
            yield law_id, data.get("title_en", ""), data.get("articles", []), fpath


def chinese_article_num(art_number: str):
    """Extract integer article number from Chinese '第X条'. Returns int or None."""
    """Extract integer article number from Chinese '第X条'."""
    m = re.search(r"第([零一二三四五六七八九十百千\d]+)条", art_number)
    if not m:
        return None
    s = m.group(1)
    if s.isdigit():
        return int(s)
    _C = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
          "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
          "十": 10, "百": 100, "千": 1000}
    total = tmp = 0
    for ch in s:
        v = _C.get(ch, 0)
        if v >= 10:
            total += (tmp or 1) * v
            tmp = 0
        else:
            tmp = v
    return total + tmp


def import_en(dry_run: bool = False, force: bool = False):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=DELETE")
    total_updated = 0
    total_skipped = 0
    law_stats: dict[int, dict] = defaultdict(lambda: {"title": "", "matched": 0, "en_total": 0, "already_had": 0})

    for law_id, title_en, articles, fpath in iter_json_en_files():
        en_total = len(articles)
        if en_total == 0:
            continue

        # Fetch all article-type nodes for this law
        rows = conn.execute(
            "SELECT id, article_number, content_en FROM nodes WHERE law_id = ? AND type = 'article'",
            (law_id,),
        ).fetchall()

        if not rows:
            # Get law title for reporting
            title = conn.execute("SELECT title FROM laws WHERE id = ?", (law_id,)).fetchone()
            t = title[0] if title else f"law_id={law_id}"
            law_stats[law_id]["title"] = t
            continue

        # Build lookup: {article_number_text: [(node_id, existing_content_en), ...]}
        # 使用列表以支持重复 article_number（import_gongbao_sfjs 可能产生多份副本）
        db_map: dict[str, list[tuple[int, str]]] = {}
        null_nodes = []  # nodes with NULL article_number (full_text fallback)
        for nid, art_num, en_existing in rows:
            key = _norm(art_num) if art_num else ""
            if key:
                db_map.setdefault(key, []).append((nid, en_existing))
            else:
                null_nodes.append((nid, en_existing))

        matched = 0
        already = 0
        updates = []

        for art in articles:
            art_num = _norm(art.get("article_number", ""))
            content_en = (art.get("content_en") or "").strip()
            if not art_num or not content_en:
                continue

            candidates = db_map.get(art_num)
            if not candidates:
                cn_int = chinese_article_num(art_num)
                if cn_int:
                    for key, entries in db_map.items():
                        db_int = chinese_article_num(key)
                        if db_int == cn_int:
                            candidates = entries
                            break
                        # DB 可能存 '一、' '二、' 等中文数字（无第条包装）
                        if db_int is None:
                            # 去掉标点，取第一个中文数字词
                            import re as _re
                            m2 = _re.match(r'^([零一二三四五六七八九十百千\d]+)', key)
                            if m2:
                                db_int2 = chinese_article_num(f'第{m2.group(1)}条')
                                if db_int2 == cn_int:
                                    candidates = entries
                                    break

            if not candidates and null_nodes:
                # Fallback: json_en uses _1/_2 etc (full_text fallback), match to NULL-article_number nodes
                candidates = null_nodes

            if not candidates:
                continue

            for nid, en_existing in candidates:
                if en_existing and not force:
                    already += 1
                    continue

                if dry_run:
                    matched += 1
                else:
                    updates.append((content_en, nid))
                    matched += 1

        if not dry_run and updates:
            conn.executemany(
                "UPDATE nodes SET content_en = ? WHERE id = ?",
                updates,
            )
            conn.commit()

        law_stats[law_id].update({
            "title": title_en or (conn.execute("SELECT title FROM laws WHERE id = ?", (law_id,)).fetchone() or [""])[0],
            "matched": law_stats[law_id]["matched"] + matched,
            "en_total": en_total,
            "already_had": law_stats[law_id]["already_had"] + already,
        })
        total_updated += matched
        total_skipped += already

    conn.close()

    # Report
    total_laws = len(law_stats)
    # Count including already_had
    full_match = sum(1 for s in law_stats.values() if s["matched"] + s["already_had"] >= s["en_total"] and s["en_total"] > 0)
    partial = sum(1 for s in law_stats.values() if 0 < s["matched"] + s["already_had"] < s["en_total"])
    no_db_articles = sum(1 for s in law_stats.values() if s["en_total"] > 0 and s["matched"] == 0 and s["already_had"] == 0)

    print(f"\n{'='*60}")
    print(f"{'DRY RUN' if dry_run else 'IMPORT'} — en_json → content_en")
    print(f"{'='*60}")
    print(f"  Laws with json_en files:   {total_laws}")
    print(f"  ✅ Full match:             {full_match}")
    print(f"  ⚠  Partial match:          {partial}")
    print(f"  ❌ No DB articles found:    {no_db_articles}")
    print(f"  Articles newly updated:    {total_updated}")
    print(f"  Articles already had:      {total_skipped}")

    if partial > 0:
        print(f"\n  Partial matches (top 10):")
        for lid, s in sorted(law_stats.items(), key=lambda x: x[1]["en_total"] - x[1]["matched"] - x[1]["already_had"], reverse=True)[:10]:
            total_in_db = s["matched"] + s["already_had"]
            if 0 < total_in_db < s["en_total"]:
                print(f"    [{lid}] {s['title'][:50]:50s}  {total_in_db:>4}/{s['en_total']} articles")

    if no_db_articles > 0:
        print(f"\n  No DB articles (top 10):")
        shown = 0
        for lid, s in sorted(law_stats.items(), key=lambda x: x[1]["en_total"], reverse=True):
            if s["matched"] == 0 and s["already_had"] == 0 and s["en_total"] > 0:
                print(f"    [{lid}] {s['title'][:60]} ({s['en_total']} articles)")
                shown += 1
                if shown >= 10:
                    break

    if not dry_run:
        # Summary stats
        cur = conn = sqlite3.connect(DB_PATH)
        total_arts = conn.execute("SELECT COUNT(*) FROM nodes WHERE type='article' AND law_id IN (SELECT id FROM laws WHERE is_current=1)").fetchone()[0]
        en_arts = conn.execute("SELECT COUNT(*) FROM nodes WHERE type='article' AND content_en IS NOT NULL AND content_en != '' AND law_id IN (SELECT id FROM laws WHERE is_current=1)").fetchone()[0]
        en_laws = conn.execute("SELECT COUNT(DISTINCT law_id) FROM nodes WHERE content_en IS NOT NULL AND content_en != '' AND law_id IN (SELECT id FROM laws WHERE is_current=1)").fetchone()[0]
        conn.close()
        print(f"\n  DB now: {en_arts}/{total_arts} articles with English, across {en_laws} laws")

    return law_stats


def main():
    parser = argparse.ArgumentParser(description="Import json_en translations into law_content.db")
    parser.add_argument("--force", action="store_true", help="Overwrite existing content_en")
    parser.add_argument("--report", action="store_true", help="Dry run — show what would change")
    args = parser.parse_args()

    import_en(dry_run=args.report, force=args.force)


if __name__ == "__main__":
    main()
