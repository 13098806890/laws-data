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

import law_id_registry as _lid_reg


def load_law_id_redirects() -> dict[str, int]:
    """Build {json_en filename: target law_id} from the gongbao source-override blocklist.

    The blocklist maps flk-sourced files to the law_id of their gongbao-sourced
    replacement. json_en files may still carry the old (flk) law_id — redirect
    them by filename so validation targets the current law.
    """
    return _lid_reg.gongbao_file_to_law_id()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def validate(sample_count: int = 0):
    conn = sqlite3.connect(DB_PATH)

    # Build DB lookup: law_id -> {article_number_normalized -> count}
    # Use counts (not a single value) because duplicate article numbers exist
    # (e.g. 修改决定 files that restate the amended text).
    db_article_counts: dict[int, dict] = {}
    db_content: dict[int, dict] = {}
    db_has_null_node: set[int] = set()
    rows = conn.execute(
        "SELECT law_id, article_number, content_en FROM nodes WHERE type='article' AND law_id IN (SELECT id FROM laws WHERE is_current=1)"
    ).fetchall()
    for lid, art_num, en in rows:
        key = _norm(art_num) if art_num else ""
        if key:
            if en:
                db_article_counts.setdefault(lid, {}).setdefault(key, 0)
                db_article_counts[lid][key] += 1
                db_content.setdefault(lid, {})[key] = en
        else:
            db_has_null_node.add(lid)

    # Also get all DB law titles and current-law ids
    db_titles = dict(conn.execute("SELECT id, title FROM laws WHERE is_current=1").fetchall())
    current_ids = set(db_titles.keys())
    all_law_ids = set(r[0] for r in conn.execute("SELECT id FROM laws").fetchall())
    conn.close()

    redirects = load_law_id_redirects()

    def resolve_law_id(law_id: int, fpath: Path):
        """Return target law_id or None if this json_en file has no valid DB law.

        Returns:
          - the law_id itself when it exists in laws (current or old version)
          - the blocklist-redirected id when the old id is gone
          - None when the file is an orphan (no DB law at all)
        """
        if law_id in all_law_ids:
            return law_id
        target = redirects.get(fpath.name)
        if target is not None and target in all_law_ids:
            return target
        return None

    # Iterate json_en files
    results = []
    skipped_old = 0
    skipped_orphan = 0
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
            lid = resolve_law_id(lid, fpath)
            if lid is None:
                # json_en file with no corresponding law in the DB at all
                skipped_orphan += 1
                continue
            if lid not in current_ids:
                # Superseded version: json_en keeps translations for an old
                # law that is no longer current — not a validation failure.
                skipped_old += 1
                continue
            en_articles = data.get("articles", [])
            en_total = len(en_articles)
            en_title = data.get("title_en", "")
            cn_title = db_titles.get(lid, f"law_id={lid}")

            # Match (with per-article-number occurrence counts so duplicate
            # numbers in DB nodes don't get over-matched; full_text single
            # nodes with NULL article_number accept any json_en entry)
            db_art_counts = db_article_counts.get(lid, {})
            used: dict[int, int] = {}

            def consume(art_num: str) -> bool:
                """Mark one DB occurrence of art_num as matched. Returns True if available."""
                key = _norm(art_num)
                cn_i = _cn_to_int(key) if key else None
                if key in db_art_counts:
                    if used.get(key, 0) < db_art_counts[key]:
                        used[key] = used.get(key, 0) + 1
                        return True
                    return False
                if cn_i is not None:
                    for k, cnt in db_art_counts.items():
                        if _cn_to_int(k) == cn_i and used.get(k, 0) < cnt:
                            used[k] = used.get(k, 0) + 1
                            return True
                return False

            if not db_art_counts:
                if db_has_null_node and any((a.get("content_en") or "").strip() for a in en_articles):
                    # Full-text fallback: single node with NULL article_number
                    status = "full" if en_total > 0 else "no_match"
                    results.append({
                        "law_id": lid,
                        "title": cn_title,
                        "en_title": en_title,
                        "db_count": 1,
                        "en_count": en_total,
                        "matched": en_total,
                        "status": status,
                        "diffs": [],
                    })
                    continue
                if en_total == 0:
                    # Empty json_en shell (no translation content) — not a failure
                    results.append({
                        "law_id": lid,
                        "title": cn_title,
                        "en_title": en_title,
                        "db_count": 0,
                        "en_count": 0,
                        "matched": 0,
                        "status": "no_translation",
                        "diffs": [],
                    })
                    continue
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
                if consume(art_num):
                    matched += 1
                    if sample_count > 0:
                        db_en = db_content.get(lid, {}).get(art_num) or db_content.get(lid, {}).get(next((k for k in db_content.get(lid, {}) if _cn_to_int(k) == _cn_to_int(art_num)), ""), "")
                        if db_en and _norm(content_en) != _norm(db_en):
                            content_diffs.append({
                                "article_number": art_num,
                                "en_json": content_en[:100],
                                "db_en": db_en[:100],
                            })

            if en_total == 0:
                # json_en shell with no actual translation content
                results.append({
                    "law_id": lid,
                    "title": cn_title,
                    "en_title": en_title,
                    "db_count": db_count,
                    "en_count": 0,
                    "matched": 0,
                    "status": "no_translation",
                    "diffs": [],
                })
                continue

            db_count = sum(db_art_counts.values())

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

    # 判定 stub 文件：json_en 无实际英文文本的 no_match 不算失败
    def _is_stub(r):
        for cat_dir in sorted(Path(JSON_EN_DIR).iterdir()):
            if not cat_dir.is_dir():
                continue
            for f in cat_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if data.get("law_id") == r["law_id"]:
                        return not any((a.get("content_en") or "").strip() for a in data.get("articles", []))
                except Exception:
                    continue
        return False

    real_no_match = [r for r in no_match if not _is_stub(r)]
    failure_count = len(partial) + len(real_no_match) + len(missing_db)
    failure_names = (
        [r["title"][:60] for r in sorted(partial, key=lambda x: x["en_count"] - x["matched"], reverse=True)[:20]]
        + [r["title"][:60] for r in sorted(real_no_match, key=lambda x: x["en_count"], reverse=True)[:20]]
        + [r["title"][:60] for r in sorted(missing_db, key=lambda x: x["en_count"], reverse=True)[:20]]
    )

    print(f"{'='*60}")
    print("VALIDATION: content_en vs json_en")
    print(f"{'='*60}")
    print(f"  Total json_en files:        {len(results)}")
    print(f"  ✅ Full match:               {len(full)}")
    print(f"  ⚠  Partial match:           {len(partial)}")
    print(f"  ❌ No match (0 articles):    {len(no_match)}")
    print(f"  ❌ No DB articles at all:    {len(missing_db)}")
    print(f"  ⏭  No translation content:  {sum(1 for r in results if r['status'] == 'no_translation')}")
    print(f"  ⏭  Skipped (superseded):    {skipped_old}")
    print(f"  ⏭  Skipped (orphan):        {skipped_orphan}")

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

    # ── 失败即退出：部分缺失/零匹配/DB 缺失都必须让 pipeline 报错 ──
    if failure_count > 0:
        print(f"\n❌ 验证失败：{failure_count} 部法律英文翻译缺失或有缺口：")
        for name in failure_names:
            print(f"  - {name}")
        sys.exit(1)
    return failure_count


def _cn_to_int(art_number: str):
    """Extract integer from article-number text. Returns int or None.

    Handles:
      - '第X条' (Chinese or Arabic digits inside 条 markers)
      - bare Chinese numerals with punctuation: '一、' '二十四、' '二、'
      - bare Arabic numerals with punctuation: '1、' '2.'
      - duplicate-suffix variants: '一、_2' '第1条_2' (used by json_en for
        repeated article numbers)
    """
    s = (art_number or "").strip()
    # strip duplicate suffix like '_2'
    s = re.sub(r"_?\d+$", "", s)
    m = re.search(r"第([零一二三四五六七八九十百千\d]+)条", s)
    if m:
        s = m.group(1)
    else:
        # bare numeral with trailing punctuation (、.）etc.), possibly 第 prefix without 条
        m2 = re.match(r"^第?([零一二三四五六七八九十百千\d]+)[、.．)）:：]?$", s)
        if not m2:
            return None
        s = m2.group(1)
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
    failures = validate(sample_count=args.sample)
    sys.exit(1 if failures > 0 else 0)


if __name__ == "__main__":
    main()
