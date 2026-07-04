#!/usr/bin/env python3
"""
Validate content_en in law_content.db against json_en files.

Reports:
  1. Laws that have json_en but ZERO content_en in DB (fully missing)
  2. Laws where content_en article count < json_en article count (partial)
  3. Laws where content fully matches
  4. Content sampling — spot-check actual translation differences

Usage:
  python3 scripts/validate_en.py
  python3 scripts/validate_en.py --sample 20    # sample N laws for content diff
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


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def validate(sample_count: int = 0):
    conn = sqlite3.connect(DB_PATH)

    # Build DB lookup: law_id -> {article_number_normalized -> content_en}
    db_articles: dict[int, dict] = {}
    rows = conn.execute(
        "SELECT law_id, article_number, content_en FROM nodes WHERE type='article' AND law_id IN (SELECT id FROM laws WHERE is_current=1)"
    ).fetchall()
    for lid, art_num, en in rows:
        key = _norm(art_num) if art_num else ""
        if key:
            db_articles.setdefault(lid, {})[key] = en or ""

    # Also get all DB law titles
    db_titles = dict(conn.execute("SELECT id, title FROM laws WHERE is_current=1").fetchall())
    conn.close()

    # Iterate json_en files
    results = []
    for cat_dir in sorted(JSON_EN_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        for fpath in sorted(cat_dir.glob("*.json")):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
            except Exception:
                continue
            lid = data.get("law_id")
            if lid is None:
                continue
            en_articles = data.get("articles", [])
            en_total = len(en_articles)
            en_title = data.get("title_en", "")
            cn_title = db_titles.get(lid, f"law_id={lid}")

            # Match
            db_art_map = db_articles.get(lid, {})
            if not db_art_map:
                results.append({
                    "law_id": lid,
                    "title": cn_title,
                    "en_title": en_title,
                    "db_count": 0,
                    "en_count": en_total,
                    "matched": 0,
                    "status": "missing_db_articles",
                })
                continue

            matched = 0
            content_diffs = []
            for art in en_articles:
                art_num = _norm(art.get("article_number", ""))
                content_en = (art.get("content_en") or "").strip()
                if not art_num or not content_en:
                    continue
                db_en = db_art_map.get(art_num)
                if db_en is not None:
                    matched += 1
                    if content_en and db_en and _norm(content_en) != _norm(db_en) and sample_count > 0:
                        content_diffs.append({
                            "article_number": art_num,
                            "en_json": content_en[:100],
                            "db_en": db_en[:100],
                        })
                else:
                    # Try integer match
                    cn_i = _cn_to_int(art_num)
                    if cn_i:
                        for k, v in db_art_map.items():
                            if _cn_to_int(k) == cn_i and v is not None:
                                matched += 1
                                break

            db_count = len(db_art_map)

            if matched == 0:
                status = "no_match"
            elif matched < en_total:
                status = "partial"
            else:
                status = "full"

            results.append({
                "law_id": lid,
                "title": cn_title,
                "en_title": en_title,
                "db_count": db_count,
                "en_count": en_total,
                "matched": matched,
                "status": status,
                "diffs": content_diffs[:sample_count] if sample_count else [],
            })

    # Generate report
    full = [r for r in results if r["status"] == "full"]
    partial = [r for r in results if r["status"] == "partial"]
    no_match = [r for r in results if r["status"] == "no_match"]
    missing_db = [r for r in results if r["status"] == "missing_db_articles"]

    print(f"{'='*60}")
    print("VALIDATION: content_en vs json_en")
    print(f"{'='*60}")
    print(f"  Total json_en files:        {len(results)}")
    print(f"  ✅ Full match:               {len(full)}")
    print(f"  ⚠  Partial match:           {len(partial)}")
    print(f"  ❌ No match (0 articles):    {len(no_match)}")
    print(f"  ❌ No DB articles at all:    {len(missing_db)}")

    if partial:
        print(f"\n{'─'*60}")
        print(f"Partial matches (sorted by gap size):")
        print(f"{'Gap':>5} {'Matched/en':>12} {'Law ID':>8}  Title")
        print(f"{'─'*60}")
        for r in sorted(partial, key=lambda x: x["en_count"] - x["matched"], reverse=True)[:30]:
            gap = r["en_count"] - r["matched"]
            print(f"{gap:>5} {r['matched']:>4}/{r['en_count']:<4} {r['law_id']:>8}  {r['title'][:50]}")

    if no_match:
        print(f"\n{'─'*60}")
        print(f"No match — json_en has structure but no actual translation content:")
        # Check if these are actually stub files (no content_en in json_en)
        stub_count = 0
        for r in sorted(no_match, key=lambda x: x["en_count"], reverse=True):
            # Verify: check the json_en file for actual content
            en_path = None
            for cat_dir in sorted(Path(JSON_EN_DIR).iterdir()):
                if not cat_dir.is_dir():
                    continue
                for f in cat_dir.glob("*.json"):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        if data.get("law_id") == r["law_id"]:
                            en_path = f
                            break
                    except:
                        pass
            if en_path:
                with open(en_path) as f:
                    data = json.load(f)
                has_content = any((a.get("content_en") or "").strip() for a in data.get("articles", []))
                if not has_content:
                    stub_count += 1
        print(f"  Likely stub files (no actual English text): {stub_count}/{len(no_match)}")

        for r in sorted(no_match, key=lambda x: x["en_count"], reverse=True)[:8]:
            print(f"  [{r['law_id']}] {r['title'][:60]}  ({r['en_count']} articles)")

    if missing_db:
        print(f"\n{'─'*60}")
        print(f"No DB articles at all (law not in DB?):")
        for r in sorted(missing_db, key=lambda x: x["en_count"], reverse=True)[:10]:
            print(f"  [{r['law_id']}] {r['title'][:60]}  ({r['en_count']} articles)")

    # Content diff sampling
    if sample_count:
        diff_laws = [r for r in partial + full if r["diffs"]]
        if diff_laws:
            print(f"\n{'─'*60}")
            print(f"Content difference samples (up to {sample_count} per law):")
            for r in diff_laws[:5]:
                print(f"\n  [{r['law_id']}] {r['title'][:50]}")
                for d in r["diffs"][:3]:
                    print(f"    art={d['article_number']}")
                    print(f"      json_en: {d['en_json']}")
                    print(f"      db_en:   {d['db_en']}")
                    if d['en_json'] != d['db_en']:
                        print(f"      >>> CONTENT DIFFERENCE")
        else:
            print(f"\n  No content differences found in sample ✅")

    print(f"\n{'='*60}")


def _cn_to_int(art_number: str):
    """Extract integer from '第X条'. Returns int or None."""
    """Extract integer from '第X条'."""
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


def main():
    parser = argparse.ArgumentParser(description="Validate content_en vs json_en")
    parser.add_argument("--sample", type=int, default=0, help="Sample N content differences per law")
    args = parser.parse_args()
    validate(sample_count=args.sample)


if __name__ == "__main__":
    main()
