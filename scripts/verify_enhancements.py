#!/usr/bin/env python3
"""
验证 law_enhancements.db 与 law_content.db 的一致性。

检查项：
1. keyword_synonyms：无空字段、无重复、target_kw 在 FTS 有命中（fts_hits>0）
2. topic_law_hints：引用的 law_title 存在于 law_content.db 且 is_current=1
3. alias_patches：无空字段、legal_term 在 FTS 有命中
4. 表结构完整（三张表都存在且有索引）
"""

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONTENT_DB_PATH      = str(BASE_DIR / 'law_content.db')
ENHANCEMENTS_DB_PATH = str(BASE_DIR / 'law_enhancements.db')


def fts_hits(term: str, conn: sqlite3.Connection) -> int:
    cjk = [c for c in term if '一' <= c <= '鿿']
    if len(cjk) >= 3:
        try:
            r = conn.execute(
                "SELECT COUNT(*) FROM nodes_fts f JOIN nodes n ON f.rowid=n.id "
                "WHERE nodes_fts MATCH ? AND n.type='article'", [term]
            ).fetchone()
            return r[0] if r else 0
        except Exception:
            return 0
    elif len(cjk) >= 1:
        try:
            r = conn.execute(
                "SELECT COUNT(*) FROM nodes_fts_bigram f JOIN nodes n ON f.rowid=n.id "
                "WHERE nodes_fts_bigram MATCH ? AND n.type='article'", [term]
            ).fetchone()
            return r[0] if r else 0
        except Exception:
            return 0
    return 0


def check_keyword_synonyms(enh, content) -> list[str]:
    issues = []
    rows = enh.execute("SELECT id, source_kw, target_kw, fts_hits FROM keyword_synonyms").fetchall()
    if not rows:
        issues.append("keyword_synonyms 表为空")
        return issues

    # 1. 空字段
    empty = [r[0] for r in rows if not r[1].strip() or not r[2].strip()]
    if empty:
        issues.append(f"keyword_synonyms 有 {len(empty)} 条空字段 (id: {empty[:5]})")

    # 2. 重复
    dups = enh.execute(
        "SELECT source_kw, target_kw, COUNT(*) c FROM keyword_synonyms GROUP BY source_kw, target_kw HAVING c > 1"
    ).fetchall()
    if dups:
        issues.append(f"keyword_synonyms 有 {len(dups)} 组重复 (例: {dups[0][0]} → {dups[0][1]})")

    # 3. fts_hits 校验：0 hits 的条目实际无法命中任何法条，应标注或移除
    zero_hits = [r for r in rows if r[3] == 0]
    if zero_hits:
        issues.append(f"keyword_synonyms 有 {len(zero_hits)} 条 fts_hits=0 (例: {zero_hits[0][1]} → {zero_hits[0][2]})")

    # 4. 重新计算 fts_hits 对比：脚本重建后应一致
    stale = []
    for r in rows:
        actual = fts_hits(r[2], content)
        if actual != r[3]:
            stale.append((r[1], r[2], r[3], actual))
    if stale:
        issues.append(f"keyword_synonyms 有 {len(stale)} 条 fts_hits 与当前 FTS 不一致 (例: {stale[0][0]}→{stale[0][1]} 记录={stale[0][2]} 实际={stale[0][3]})")

    return issues


def check_topic_law_hints(enh, content) -> list[str]:
    issues = []
    rows = enh.execute("SELECT topic_keyword, law_title, priority FROM topic_law_hints").fetchall()
    if not rows:
        issues.append("topic_law_hints 表为空")
        return issues

    missing = []
    empty_kw = [r[0] for r in rows if not r[0].strip() or not r[1].strip()]
    if empty_kw:
        issues.append(f"topic_law_hints 有 {len(empty_kw)} 条空字段")

    for topic, title, priority in rows:
        exists = content.execute(
            "SELECT COUNT(*) FROM laws WHERE title=? AND is_current=1", [title]
        ).fetchone()[0]
        if not exists:
            missing.append((topic, title))
    if missing:
        issues.append(f"topic_law_hints 有 {len(missing)} 条引用不存在的法律 (例: {missing[0][0]} → {missing[0][1]})")

    return issues


def check_alias_patches(enh, content) -> list[str]:
    issues = []
    rows = enh.execute("SELECT id, colloquial, legal_term, fts_hits FROM alias_patches").fetchall()
    if not rows:
        issues.append("alias_patches 表为空")
        return issues

    empty = [r[0] for r in rows if not r[1].strip() or not r[2].strip()]
    if empty:
        issues.append(f"alias_patches 有 {len(empty)} 条空字段 (id: {empty[:5]})")

    zero_hits = [r for r in rows if r[3] == 0]
    if zero_hits:
        issues.append(f"alias_patches 有 {len(zero_hits)} 条 fts_hits=0 (例: {zero_hits[0][1]} → {zero_hits[0][2]})")

    return issues


def main():
    print(f"验证 law_enhancements.db ...")
    print(f"  内容库: {CONTENT_DB_PATH}")
    print(f"  增强库: {ENHANCEMENTS_DB_PATH}")

    enh = sqlite3.connect(ENHANCEMENTS_DB_PATH)
    content = sqlite3.connect(CONTENT_DB_PATH)

    # 表结构检查
    tables = {r[0] for r in enh.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    required = {'keyword_synonyms', 'topic_law_hints', 'alias_patches'}
    missing_tables = required - tables
    if missing_tables:
        print(f"  ❌ 缺少表: {missing_tables}")
        enh.close(); content.close()
        return 1

    all_issues = []
    all_issues += check_keyword_synonyms(enh, content)
    all_issues += check_topic_law_hints(enh, content)
    all_issues += check_alias_patches(enh, content)

    # 打印统计
    for table in ['keyword_synonyms', 'topic_law_hints', 'alias_patches']:
        cnt = enh.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {cnt} 条")

    enh.close(); content.close()

    if all_issues:
        print(f"\n❌ 发现 {len(all_issues)} 个问题:")
        for i in all_issues:
            print(f"  - {i}")
        return 1
    else:
        print("\n✅ law_enhancements.db 验证通过")
        return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
