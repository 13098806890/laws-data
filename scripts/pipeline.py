#!/usr/bin/env python3
"""
完整 pipeline：docx → JSON → law_index → DB → Markdown
用法：python3 scripts/pipeline.py [选项]

选项：
  --skip-docx    跳过 docx → JSON 阶段
  --skip-index   跳过 law_index 生成阶段
  --skip-db      跳过 JSON → DB 阶段
  --skip-md      跳过 DB → Markdown 阶段
  --only-refs    只运行 extract_references（不跑主流程）

各阶段也可单独运行：
  cd scripts
  python3 -m docx_to_json.converter
  python3 generate_law_index.py
  python3 -m json_to_db.builder
  python3 -m db_to_md.renderer
  python3 extract_references.py
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

BASE_DIR  = Path(__file__).parent.parent
LOG_DIR   = BASE_DIR / 'logs'
INDEX_PATH = BASE_DIR / 'law_index.json'


def _snapshot_index() -> dict:
    """读取当前 law_index.json，返回 {filename: entry} 快照。"""
    if not INDEX_PATH.exists():
        return {}
    entries = json.loads(INDEX_PATH.read_text(encoding='utf-8'))
    return {e['filename']: e for e in entries}


def _snapshot_db_refs(db_path: Path) -> dict:
    """从数据库读取引用统计快照。"""
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(db_path)
        total    = conn.execute('SELECT COUNT(*) FROM article_references').fetchone()[0]
        resolved = conn.execute('SELECT COUNT(*) FROM article_references WHERE resolved=1').fetchone()[0]
        cross    = conn.execute("SELECT COUNT(*) FROM article_references WHERE ref_type='cross_law'").fetchone()[0]
        self_    = conn.execute("SELECT COUNT(*) FROM article_references WHERE ref_type='self_ref'").fetchone()[0]
        conn.close()
        return {'total': total, 'resolved': resolved, 'cross': cross, 'self': self_}
    except Exception:
        return {}


def _snapshot_db_laws(db_path: Path) -> dict:
    """从数据库读取每部法律的 is_current 快照，返回 {filename: is_current}。"""
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute('SELECT filename, is_current FROM laws').fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def _build_report(before_index: dict, before_refs: dict, before_current: dict,
                  db_path: Path) -> list[str]:
    lines = []

    # 新 index
    after_index: dict = {}
    if INDEX_PATH.exists():
        entries = json.loads(INDEX_PATH.read_text(encoding='utf-8'))
        after_index = {e['filename']: e for e in entries}

    # 新 DB
    after_refs    = _snapshot_db_refs(db_path)
    after_current = _snapshot_db_laws(db_path)

    # ── 新增法律 ──
    added = [v for k, v in after_index.items() if k not in before_index]
    if added:
        lines.append(f'\n【新增法律】{len(added)} 部')
        by_domain: dict[str, list] = {}
        for e in sorted(added, key=lambda x: (x.get('legal_domain') or '其他', x.get('pub_date') or '')):
            d = e.get('legal_domain') or '其他'
            by_domain.setdefault(d, []).append(e)
        for domain, laws in sorted(by_domain.items()):
            lines.append(f'  {domain}：')
            for e in laws:
                lines.append(f'    + [{e["law_id"]}] {e["title"]}  ({e.get("pub_date","")})  category={e.get("category","")}')
    else:
        lines.append('\n【新增法律】无')

    # ── 移除法律（index 中消失，不常见）──
    removed = [k for k in before_index if k not in after_index]
    if removed:
        lines.append(f'\n【移除法律】{len(removed)} 部')
        for k in removed:
            e = before_index[k]
            lines.append(f'    - [{e.get("law_id","")}] {e.get("title","")}')

    # ── is_current 变化 ──
    current_changes = []
    for fn, new_cur in after_current.items():
        old_cur = before_current.get(fn)
        if old_cur is not None and old_cur != new_cur:
            current_changes.append((fn, old_cur, new_cur))
    if current_changes:
        lines.append(f'\n【is_current 变化】{len(current_changes)} 条')
        for fn, old, new in sorted(current_changes):
            arrow = '1→0（旧版）' if new == 0 else '0→1（升为现行）'
            lines.append(f'  {fn}  {arrow}')
    else:
        lines.append('\n【is_current 变化】无')

    # ── 引用关系变化 ──
    if after_refs:
        if before_refs:
            dt = after_refs['total'] - before_refs['total']
            dr = after_refs['resolved'] - before_refs['resolved']
            dc = after_refs['cross'] - before_refs['cross']
            ds = after_refs['self'] - before_refs['self']
            def _fmt(n): return f'+{n}' if n >= 0 else str(n)
            lines.append(
                f'\n【引用关系】总计 {after_refs["total"]} 条'
                f'（{_fmt(dt)}）  '
                f'跨法 {after_refs["cross"]}（{_fmt(dc)}）  '
                f'自引 {after_refs["self"]}（{_fmt(ds)}）  '
                f'已解析 {after_refs["resolved"]}（{_fmt(dr)}）'
            )
        else:
            lines.append(
                f'\n【引用关系】总计 {after_refs["total"]} 条  '
                f'跨法 {after_refs["cross"]}  自引 {after_refs["self"]}  '
                f'已解析 {after_refs["resolved"]}'
            )

    # ── 汇总 ──
    lines.append(f'\n【汇总】法律总数 {len(before_index)} → {len(after_index)}')

    return lines


def _write_log(report_lines: list[str], db_path: Path):
    LOG_DIR.mkdir(exist_ok=True)
    ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = LOG_DIR / f'pipeline_{ts}.log'
    header = [
        f'pipeline 运行时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        '=' * 60,
    ]
    path.write_text('\n'.join(header + report_lines) + '\n', encoding='utf-8')
    return path


def main():
    parser = argparse.ArgumentParser(description='laws_data pipeline')
    parser.add_argument('--skip-docx',  action='store_true', help='跳过 docx → JSON')
    parser.add_argument('--skip-index', action='store_true', help='跳过 law_index 生成')
    parser.add_argument('--skip-db',    action='store_true', help='跳过 JSON → DB')
    parser.add_argument('--skip-md',    action='store_true', help='跳过 DB → Markdown')
    parser.add_argument('--only-refs',  action='store_true', help='只运行 extract_references')
    args = parser.parse_args()

    from config import DB_PATH

    if args.only_refs:
        before_refs    = _snapshot_db_refs(DB_PATH)
        before_current = _snapshot_db_laws(DB_PATH)
        from extract_references import run as extract_refs
        extract_refs()
        from json_to_db.builder import load_references
        load_references()
        report = _build_report({}, before_refs, before_current, DB_PATH)
        for line in report:
            print(line)
        log_path = _write_log(report, DB_PATH)
        print(f'\n日志已写入：{log_path}')
        return

    # 运行前快照
    before_index   = _snapshot_index()
    before_refs    = _snapshot_db_refs(DB_PATH)
    before_current = _snapshot_db_laws(DB_PATH)

    if not args.skip_docx:
        from docx_to_json.converter import run as docx_to_json
        docx_to_json()

    if not args.skip_index:
        from generate_law_index import run as gen_law_index
        gen_law_index()

    if not args.skip_db:
        from json_to_db.builder import run as json_to_db
        json_to_db()
        from json_to_db.export_menu import run as export_menu
        export_menu()

    # 引用关系提取：在数据库建好之后运行，结果直接写入 DB
    if not args.skip_db:
        from extract_references import run as extract_refs
        extract_refs()
        from json_to_db.builder import load_references
        load_references()

    if not args.skip_md:
        from db_to_md.renderer import run as db_to_md
        db_to_md()

    # 变更报告
    report = _build_report(before_index, before_refs, before_current, DB_PATH)
    print('\n' + '=' * 60)
    print('变更报告')
    print('=' * 60)
    for line in report:
        print(line)

    log_path = _write_log(report, DB_PATH)
    print(f'\n日志已写入：{log_path}')
    print('\n=== 完成 ===')


if __name__ == '__main__':
    main()
