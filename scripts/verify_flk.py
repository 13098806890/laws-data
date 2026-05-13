#!/usr/bin/env python3
"""
法考数据库交叉验证脚本
======================
对比 flk_content.db（houdask 法考源）与 law_content.db（主库）中
相同法律的条文内容是否一致。

flk_content.db 的 laws.id 与主库 laws.id 对齐（由 flk_pipeline.py 建库时写入），
匹配法律直接用 id join，不再做标题模糊匹配。
未匹配主库的法律 id 为负数。

用法：
  cd /Users/doxie/laws_data
  python3 scripts/verify_flk.py                   # 完整报告（终端输出）
  python3 scripts/verify_flk.py --out report.txt  # 同时写文件
  python3 scripts/verify_flk.py --law 中华人民共和国刑法  # 只查一部法律
  python3 scripts/verify_flk.py --diff            # 显示具体条文内容差异
"""

import argparse
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
FLK_DB   = BASE_DIR / '法考' / 'flk_content.db'
MAIN_DB  = BASE_DIR / 'law_content.db'


# ── 条文内容规范化 ────────────────────────────────────────────────────────────

def _norm_content(t: str) -> str:
    """去除所有空白字符后比较，忽略换行/空格排版差异。"""
    return re.sub(r'\s+', '', t or '')


# ── 单部法律对比 ──────────────────────────────────────────────────────────────

def compare_law(flk_conn, main_conn, law_id: int, title: str,
                show_diff: bool = False) -> dict:
    """
    law_id < 0 表示主库无对应法律，直接标记未匹配。
    law_id > 0 时直接用同一 id 从主库取条文。
    """
    # 法考库条文
    flk_arts = {
        r[0]: r[1]
        for r in flk_conn.execute(
            "SELECT article_number, content FROM articles "
            "WHERE law_id=? AND article_number!='' AND article_number IS NOT NULL",
            (law_id,)
        ).fetchall()
    }

    if law_id < 0:
        return {'title': title, 'law_id': law_id, 'matched': False,
                'flk_total': len(flk_arts), 'main_total': 0}

    # 主库条文（id 对齐，直接查）
    main_row = main_conn.execute(
        "SELECT title FROM laws WHERE id=? AND is_current=1", (law_id,)
    ).fetchone()

    if not main_row:
        # id 存在于主库但 is_current=0（旧版本），或根本不存在
        return {'title': title, 'law_id': law_id, 'matched': False,
                'flk_total': len(flk_arts), 'main_total': 0,
                'note': '主库 id 存在但非 is_current'}

    main_title = main_row[0]
    main_arts = {
        r[0]: r[1]
        for r in main_conn.execute(
            "SELECT article_number, content FROM nodes "
            "WHERE law_id=? AND type='article' AND article_number!='' AND article_number IS NOT NULL",
            (law_id,)
        ).fetchall()
    }

    common   = set(flk_arts) & set(main_arts)
    only_flk  = sorted(set(flk_arts) - set(main_arts))
    only_main = sorted(set(main_arts) - set(flk_arts))

    diff_content = []
    identical = 0
    for art_num in sorted(common):
        f = _norm_content(flk_arts[art_num])
        m = _norm_content(main_arts[art_num])
        if f == m:
            identical += 1
        else:
            diff_content.append((art_num,
                                  flk_arts[art_num].strip(),
                                  main_arts[art_num].strip()))

    return {
        'title':        title,
        'main_title':   main_title,
        'law_id':       law_id,
        'matched':      True,
        'flk_total':    len(flk_arts),
        'main_total':   len(main_arts),
        'common':       len(common),
        'identical':    identical,
        'diff_content': diff_content,
        'only_flk':     only_flk,
        'only_main':    only_main,
    }


# ── 报告格式化 ────────────────────────────────────────────────────────────────

def _pct(a, b) -> str:
    return f'{a/b*100:.1f}%' if b else 'N/A'


def format_report(results: list[dict], show_diff: bool = False) -> str:
    lines = []
    W = 60

    matched    = [r for r in results if r.get('matched')]
    unmatched  = [r for r in results if not r.get('matched')]
    perfect    = [r for r in matched
                  if not r['diff_content'] and not r['only_flk'] and not r['only_main']]
    has_issues = [r for r in matched if r not in perfect]

    lines.append('=' * W)
    lines.append('法考数据库交叉验证报告')
    lines.append('=' * W)
    lines.append(f'法考库法律总数：{len(results)}')
    lines.append(f'  主库匹配（id 对齐）：{len(matched)}  /  未匹配：{len(unmatched)}')
    lines.append(f'  完全一致：{len(perfect)}  /  存在差异：{len(has_issues)}')

    total_flk  = sum(r['flk_total']  for r in matched)
    total_main = sum(r['main_total'] for r in matched)
    total_id   = sum(r['identical']  for r in matched)
    total_diff = sum(len(r['diff_content']) for r in matched)
    total_of   = sum(len(r['only_flk'])     for r in matched)
    total_om   = sum(len(r['only_main'])    for r in matched)

    lines.append('')
    lines.append('匹配法律条文汇总：')
    lines.append(f'  法考库条文数：{total_flk}')
    lines.append(f'  主库条文数：  {total_main}')
    lines.append(f'  内容一致：    {total_id}  ({_pct(total_id, total_flk)} of 法考库)')
    lines.append(f'  内容不同：    {total_diff}')
    lines.append(f'  仅法考库有：  {total_of}')
    lines.append(f'  仅主库有：    {total_om}')

    # ── 未匹配 ──
    if unmatched:
        lines.append('')
        lines.append(f'【主库未收录 / id 未对齐】{len(unmatched)} 部：')
        for r in unmatched:
            note = f'  ({r.get("note", "id<0，建库时未找到对应主库法律")})'
            lines.append(f'  ✗  {r["title"]}  (法考库 {r["flk_total"]} 条){note}')

    # ── 完全一致 ──
    if perfect:
        lines.append('')
        lines.append(f'【完全一致】{len(perfect)} 部：')
        for r in perfect:
            lines.append(f'  ✓  {r["title"]}  ({r["flk_total"]} 条)')

    # ── 存在差异 ──
    if has_issues:
        lines.append('')
        lines.append(f'【存在差异】{len(has_issues)} 部：')
        for r in has_issues:
            lines.append('')
            lines.append(f'  ▶ {r["title"]}  (id={r["law_id"]})')
            lines.append(f'    法考库 {r["flk_total"]} 条  /  主库 {r["main_total"]} 条  '
                         f'/  共有 {r["common"]} 条  /  一致 {r["identical"]} 条')

            if r['only_flk']:
                sample = r['only_flk'][:8]
                more   = len(r['only_flk']) - 8
                s = ', '.join(sample)
                s += f'  …等共 {len(r["only_flk"])} 条' if more > 0 else f'  共 {len(r["only_flk"])} 条'
                lines.append(f'    仅法考库有：{s}')

            if r['only_main']:
                sample = r['only_main'][:8]
                more   = len(r['only_main']) - 8
                s = ', '.join(sample)
                s += f'  …等共 {len(r["only_main"])} 条' if more > 0 else f'  共 {len(r["only_main"])} 条'
                lines.append(f'    仅主库有：  {s}')

            if r['diff_content']:
                nums = [d[0] for d in r['diff_content']]
                sample = nums[:8]
                more   = len(nums) - 8
                s = ', '.join(sample)
                s += f'  …等共 {len(nums)} 条' if more > 0 else f'  共 {len(nums)} 条'
                lines.append(f'    内容不同：  {s}')

                if show_diff:
                    for art_num, flk_text, main_text in r['diff_content'][:3]:
                        lines.append('')
                        lines.append(f'      ── {art_num} ──')
                        lines.append(f'      [法考库] {flk_text[:200]}')
                        lines.append(f'      [主  库] {main_text[:200]}')

    lines.append('')
    lines.append('=' * W)
    return '\n'.join(lines)


# ── 主流程 ────────────────────────────────────────────────────────────────────

def run(law_filter: str = None, show_diff: bool = False, out_path: str = None):
    if not FLK_DB.exists():
        print(f'✗ 找不到 {FLK_DB}，请先运行 flk_pipeline.py')
        return
    if not MAIN_DB.exists():
        print(f'✗ 找不到 {MAIN_DB}')
        return

    flk_conn  = sqlite3.connect(FLK_DB)
    main_conn = sqlite3.connect(MAIN_DB)

    if law_filter:
        flk_laws = flk_conn.execute(
            "SELECT id, title FROM laws WHERE title LIKE ?",
            (f'%{law_filter}%',)
        ).fetchall()
        if not flk_laws:
            print(f'法考库中未找到包含「{law_filter}」的法律')
            flk_conn.close(); main_conn.close()
            return
    else:
        flk_laws = flk_conn.execute(
            "SELECT id, title FROM laws ORDER BY id"
        ).fetchall()

    print(f'正在比对 {len(flk_laws)} 部法律...')
    results = []
    for law_id, title in flk_laws:
        r = compare_law(flk_conn, main_conn, law_id, title, show_diff)
        results.append(r)

    flk_conn.close()
    main_conn.close()

    report = format_report(results, show_diff=show_diff)
    print(report)

    if out_path:
        Path(out_path).write_text(report, encoding='utf-8')
        print(f'报告已写入：{out_path}')


def main():
    parser = argparse.ArgumentParser(description='法考数据库交叉验证')
    parser.add_argument('--law',  metavar='关键词', help='只验证包含此关键词的法律')
    parser.add_argument('--diff', action='store_true', help='显示具体条文内容差异（前3条）')
    parser.add_argument('--out',  metavar='FILE',   help='将报告写入文件')
    args = parser.parse_args()
    run(law_filter=args.law, show_diff=args.diff, out_path=args.out)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    main()
