#!/usr/bin/env python3
"""
Verify law_content.db gongbao tables after rebuild.

Checks:
  1. gongbao_docs: row count per source, field completeness
  2. English columns: title_en, ruling_gist_en, keywords_en, full_text_en coverage
  3. gongbao_case_law_links: row count
  4. gongbao_docs_fts: FTS index built correctly
  5. Existing English content in nodes.content_en preserved
  6. Cross-reference: json_en_gongbao files vs DB
"""

import json
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH  = str(BASE_DIR / 'law_content.db')
GONGBAO_EN_DIR = BASE_DIR / 'json_en_gongbao'
JSON_EN_DIR    = BASE_DIR / 'json_en'


def fmt(n):
    return f"{n:,}"


def main():
    conn = sqlite3.connect(DB_PATH)

    print("=" * 60)
    print("VALIDATION: gongbao tables + English content")
    print("=" * 60)

    # ── 1. gongbao_docs basic stats ──────────────────────────────────────
    print("\n── 1. gongbao_docs 基本统计 ──")
    total = conn.execute("SELECT COUNT(*) FROM gongbao_docs").fetchone()[0]
    print(f"  总记录数: {fmt(total)}")

    by_source = conn.execute(
        "SELECT source, COUNT(*) FROM gongbao_docs GROUP BY source ORDER BY source"
    ).fetchall()
    for src, cnt in by_source:
        label = {"al": "指导案例", "cpwsxd": "裁判文书", "sfwj": "司法文件"}.get(src, src)
        print(f"    {label} ({src}): {fmt(cnt)}")

    # ── 2. English column coverage ───────────────────────────────────────
    print("\n── 2. 英文列覆盖 ──")
    for col in ["title_en", "ruling_gist_en", "keywords_en", "full_text_en"]:
        filled = conn.execute(
            f"SELECT COUNT(*) FROM gongbao_docs WHERE {col} IS NOT NULL AND {col} != ''"
        ).fetchone()[0]
        print(f"    {col}: {fmt(filled)}/{fmt(total)} ({filled / total * 100:.1f}%)" if total else "  0")

    # Per-source English coverage
    print("\n  按来源英文覆盖:")
    for src, cnt in by_source:
        src_label = {"al": "指导案例", "cpwsxd": "裁判文书", "sfwj": "司法文件"}.get(src, src)
        en_cnt = conn.execute(
            "SELECT COUNT(*) FROM gongbao_docs WHERE source = ? AND title_en IS NOT NULL AND title_en != ''",
            (src,)
        ).fetchone()[0]
        print(f"    {src_label} ({src}): {fmt(en_cnt)}/{fmt(cnt)} ({en_cnt / cnt * 100:.1f}%)" if cnt else "  0")

    # ── 3. gongbao_case_law_links ──────────────────────────────────────
    print("\n── 3. 法条引用关联 ──")
    links = conn.execute("SELECT COUNT(*) FROM gongbao_case_law_links").fetchone()[0]
    print(f"  总关联数: {fmt(links)}")

    # ── 4. FTS index ─────────────────────────────────────────────────────
    print("\n── 4. FTS 全文索引 ──")
    try:
        fts_rows = conn.execute("SELECT COUNT(*) FROM gongbao_docs_fts").fetchone()[0]
        print(f"  gongbao_docs_fts 行数: {fmt(fts_rows)}")
        # Quick query test
        test = conn.execute(
            "SELECT COUNT(*) FROM gongbao_docs_fts WHERE gongbao_docs_fts MATCH '交通肇事'"
        ).fetchone()[0]
        print(f"  FTS 搜索 '交通肇事': {test} 条命中")
        test_en = conn.execute(
            "SELECT COUNT(*) FROM gongbao_docs_fts WHERE gongbao_docs_fts MATCH 'accident'"
        ).fetchone()[0]
        print(f"  FTS 搜索 'accident': {test_en} 条命中")
    except Exception as e:
        print(f"  ⚠ FTS 检查失败: {e}")

    # ── 5. nodes.content_en preserved ────────────────────────────────────
    print("\n── 5. nodes 表英文翻译 (content_en) ──")
    total_arts = conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE type='article' AND law_id IN (SELECT id FROM laws WHERE is_current=1)"
    ).fetchone()[0]
    en_arts = conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE type='article' AND content_en IS NOT NULL AND content_en != '' AND law_id IN (SELECT id FROM laws WHERE is_current=1)"
    ).fetchone()[0]
    en_laws = conn.execute(
        "SELECT COUNT(DISTINCT law_id) FROM nodes WHERE content_en IS NOT NULL AND content_en != '' AND law_id IN (SELECT id FROM laws WHERE is_current=1)"
    ).fetchone()[0]
    print(f"  总条文数: {fmt(total_arts)}")
    print(f"  有英文翻译: {fmt(en_arts)} ({en_arts / total_arts * 100:.1f}%)")
    print(f"  覆盖法律数: {fmt(en_laws)}")

    # Check a few known laws to verify content_en intact
    print("\n  抽样验证（5部已知有翻译的法律）:")
    sample_law_ids = [1, 3, 13, 22, 98]  # 宪法, 民法典, 刑法, 劳动合同法, 著作权法
    for lid in sample_law_ids:
        row = conn.execute("SELECT title FROM laws WHERE id = ?", (lid,)).fetchone()
        if not row:
            continue
        title = row[0]
        en_cnt = conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE law_id = ? AND content_en IS NOT NULL AND content_en != ''",
            (lid,)
        ).fetchone()[0]
        total_cnt = conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE law_id = ? AND type='article'", (lid,)
        ).fetchone()[0]
        if total_cnt > 0:
            print(f"    [{lid}] {title[:40]}: {en_cnt}/{total_cnt} 条有英文")

    # ── 6. Cross-reference json_en_gongbao vs DB ─────────────────────────
    print("\n── 6. json_en_gongbao → DB 交叉验证 ──")
    if GONGBAO_EN_DIR.exists():
        json_files = 0
        db_matched = 0
        missing_in_db = 0
        for source_dir in sorted(GONGBAO_EN_DIR.iterdir()):
            if not source_dir.is_dir():
                continue
            for fpath in sorted(source_dir.glob("*.json")):
                json_files += 1
                doc_id = int(fpath.stem)
                row = conn.execute(
                    "SELECT id, title_en FROM gongbao_docs WHERE id = ?", (doc_id,)
                ).fetchone()
                if row:
                    if row[1]:
                        db_matched += 1
                else:
                    missing_in_db += 1
        print(f"  json_en_gongbao 文件数: {fmt(json_files)}")
        print(f"  DB 有匹配且有 title_en: {fmt(db_matched)}")
        if missing_in_db:
            print(f"  ⚠ DB 中找不到对应 doc_id: {fmt(missing_in_db)}")

    # ── 7. Overall assessment ────────────────────────────────────────────
    print("\n" + "=" * 60)
    issues = []
    if total == 0:
        issues.append("gongbao_docs 为空")
    if links == 0:
        issues.append("gongbao_case_law_links 为空")
    en_col_filled = conn.execute(
        "SELECT COUNT(*) FROM gongbao_docs WHERE title_en IS NOT NULL AND title_en != ''"
    ).fetchone()[0]
    if total > 0 and en_col_filled == 0:
        issues.append("英文列全部为空")
    if en_arts == 0:
        issues.append("nodes.content_en 全部为空")

    if issues:
        print("⚠ 存在问题:")
        for i in issues:
            print(f"  - {i}")
    else:
        print("✅ 全部正常")

    conn.close()


if __name__ == "__main__":
    main()
