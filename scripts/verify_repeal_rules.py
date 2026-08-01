#!/usr/bin/env python3
"""
验证废止标记（公报源 JSON 的 repealed_by 字段）在 law_content.db 上的应用结果。

废止标记是"一次性工作"：直接在公报源 JSON（最高人民法院公报/司法解释/*.json）中
标记 repealed_by，导入时（import_gongbao_sfjs）读取该字段设为 is_current=0。
本脚本用于核对标记是否正确应用，并在后续维护时帮助发现漏标/误标。

检查项:
  1. 标记未生效:  有 repealed_by 字段的行必须 is_current=0（若仍为 1 则标记未生效）
  2. 误标新版:    被标记的行 pub_date 不得晚于废止决定生效日期
  3. 漏标:        有 repealed_by 字段但 DB 中无对应行（标题完全匹配不上）
  4. 无法解释的 is_current=0: 公报源中 is_current=0 的行，其标题对应的公报源 JSON
     没有 repealed_by 字段（非废止标记所致），提示人工确认

用法:
  python3 scripts/verify_repeal_rules.py [--db path/to/law_content.db]

退出码: 0 = 通过, 1 = 存在严重问题（标记未生效 / 误标新版）
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DEFAULT_DB = SCRIPT_DIR.parent / "law_content.db"
GONGBAO_SFJS_DIR = SCRIPT_DIR.parent / "最高人民法院公报" / "司法解释"

# 废止决定 → 生效日期，用于误标新版检查
REPEAL_EFFECTIVE_DATES = {
    "法发〔1994〕16号": "1994-07-27",
    "法发〔1996〕34号": "1996-12-31",
    "法释〔2000〕20号": "2000-07-25",
    "法释〔2001〕32号": "2001-12-28",
    "法释〔2002〕6号": "2002-03-10",
    "法释〔2002〕13号": "2002-05-29",
    "法释〔2008〕15号": "2008-12-24",
    "法释〔2012〕13号": "2012-09-29",
    "法释〔2013〕2号": "2013-01-18",
    "法释〔2015〕2号": "2015-01-19",
    "法释〔2015〕12号": "2015-07-06",
    "法释〔2017〕17号": "2017-10-01",
    "法释〔2019〕11号": "2019-07-20",
    "法释〔2020〕16号": "2021-01-01",
}


def norm(s: str) -> str:
    return re.sub(r"[\s　]", "", s or "")


def parse_repealed_by(repealed_by: str) -> str:
    """从 repealed_by 字段提取废止决定文号，如 '法释〔2020〕16号（2021-01-01施行，第6项）' → '法释〔2020〕16号'"""
    m = re.match(r"([^（(]+)", repealed_by or "")
    return m.group(1).strip() if m else ""


def load_field_marks():
    """收集公报源 JSON 中的 repealed_by 标记 → [{title, doc_number, repealed_by}, ...]
    按文件级记录，同标题多版本（如新旧修订）可区分。"""
    marks = []
    if not GONGBAO_SFJS_DIR.exists():
        print(f"  ⚠ 公报司法解释目录不存在：{GONGBAO_SFJS_DIR}")
        return marks
    for f in sorted(GONGBAO_SFJS_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        rb = d.get("repealed_by", "")
        title = d.get("title", "")
        if rb and title:
            marks.append({
                "title": title,
                "doc_number": d.get("doc_number", ""),
                "repealed_by": rb,
            })
    return marks


def find_marked_rows(conn, mark):
    """找到该标记对应的 DB 行（只查 gongbao 源）。
    doc_number + title 必须同时匹配（同标题多版本用 doc_number 区分；
    doc_number 可能被多个无关文件共享污染时，title 兜底约束避免误伤）。"""
    where, params = ["source='gongbao'"], []
    if mark["doc_number"]:
        where.append("doc_number = ?")
        params.append(mark["doc_number"])
    if mark["title"]:
        where.append("REPLACE(REPLACE(title, ' ', ''), '　', '') = ?")
        params.append(norm(mark["title"]))
    return conn.execute(
        f"SELECT id, doc_number, pub_date, is_current, title FROM laws WHERE {' AND '.join(where)}",
        params,
    ).fetchall()


def main():
    parser = argparse.ArgumentParser(description="Verify repeal marks applied to law_content.db")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to law_content.db")
    args = parser.parse_args()

    db_path = args.db
    if not db_path.exists():
        print(f"✗ 数据库不存在: {db_path}")
        sys.exit(1)

    marks = load_field_marks()
    if not marks:
        print(f"✗ 公报源中没有任何 repealed_by 标记（检查目录: {GONGBAO_SFJS_DIR}）")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    problems = []
    warnings = []

    print(f"── 废止标记验证（{len(marks)} 个公报源标记, DB: {db_path.name}）──")

    # ── 检查 1: 标记未生效 / 检查 2: 误标新版 ─────────────────────
    effective = 0
    for mark in marks:
        rows = find_marked_rows(conn, mark)
        rb = mark["repealed_by"]

        if not rows:
            warnings.append(
                f"标记但库中无对应行（漏标）: {mark['title'][:40]}（{rb[:35]}）"
            )
            continue
        effective += 1

        for r in rows:
            if r[3] != 0:
                problems.append(
                    f"标记未生效: {r[1]}（{r[2]}）仍为 is_current=1，但公报源已标 {rb[:35]}"
                )
            eff_date = REPEAL_EFFECTIVE_DATES.get(parse_repealed_by(rb))
            if eff_date and r[2] and r[2] > eff_date:
                problems.append(
                    f"疑似误标新版: {r[1]}（{r[2]}）pub_date={r[2]} 晚于废止生效 {eff_date}"
                )

    # ── 检查 3: 无法解释的 is_current=0 ───────────────────────────
    # 公报源中 is_current=0 的行，必须能对应到某个 repealed_by 标记
    #（按 doc_number+title 或 title 匹配）；否则为标题去重（多版本）或异常
    def row_covered(row_title, row_doc):
        for mark in marks:
            title_ok = norm(mark["title"]) == norm(row_title)
            if mark["doc_number"]:
                if mark["doc_number"] == row_doc and title_ok:
                    return True
            elif title_ok:
                return True
        return False

    unexplained = []
    for row in conn.execute(
        "SELECT title, doc_number, pub_date FROM laws WHERE source='gongbao' AND is_current=0"
    ).fetchall():
        if not row_covered(row[0], row[1]):
            unexplained.append((row[0], row[2]))

    if unexplained:
        warnings.append(
            f"无法解释的 is_current=0（非废止标记，可能为多版本去重）: {len(unexplained)} 条，示例: "
            + "; ".join(f"{t}@{p}" for t, p in unexplained[:5])
        )

    # ── 汇总 ───────────────────────────────────────────────────────
    total_zero = conn.execute("SELECT COUNT(*) FROM laws WHERE source='gongbao' AND is_current=0").fetchone()[0]
    print(f"  标记生效: {effective}/{len(marks)}")
    print(f"  gongbao 源 is_current=0 总数: {total_zero}")
    if warnings:
        print(f"\n  ⚠ 警告（{len(warnings)}）:")
        for w in warnings:
            print(f"    - {w}")
    if problems:
        print(f"\n  ✗ 严重问题（{len(problems)}）:")
        for p in problems:
            print(f"    - {p}")
        conn.close()
        sys.exit(1)
    print("\n  ✅ 废止标记验证通过")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
