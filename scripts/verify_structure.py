#!/usr/bin/env python3
"""
验证数据库中每部法律的结构完整性：
1. 条文编号严格递增，无跳号
2. 同一父节点下不出现连续两个 chapter 或连续两个 section（中间没有 article）
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent.parent / 'law_content.db'


def cn_to_int(s: str) -> int:
    """汉字数字 → 整数（支持 第X条 格式，自动提取数字部分）"""
    import re
    m = re.search(r'第([零一二三四五六七八九十百千万]+)条', s or '')
    if not m:
        return -1
    s = m.group(1)
    CN = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,
          '九':9,'十':10,'百':100,'千':1000,'万':10000}
    result = tmp = 0
    for c in s:
        v = CN.get(c, 0)
        if v >= 10:
            result += (tmp or 1) * v
            tmp = 0
        else:
            tmp = v
    return result + tmp


def check_law(conn, law_id: int, law_title: str) -> list[str]:
    issues = []

    rows = conn.execute(
        """SELECT id, parent_id, type, title, article_number, article_num, global_order
           FROM nodes
           WHERE law_id = ?
           ORDER BY global_order""",
        (law_id,)
    ).fetchall()

    if not rows:
        return []

    # ── 1. 条文编号严格递增 ──────────────────────────────────────
    # 附件/多文档拼接文件（如"方案+暂行规则"）会在文档边界重置条号，
    # 只在同一父节点（章/节）内检查递增，跨父节点的重置视为正常
    article_nums = []
    for r in rows:
        if r[2] == 'article':
            num = r[5]  # article_num (INT, may be NULL)
            if num is None:
                # fallback: parse from article_number string
                num = cn_to_int(r[4] or '')
            if num and num > 0:
                article_nums.append((num, r[4] or r[3] or '', r[1]))

    for i in range(1, len(article_nums)):
        prev_num, prev_label, prev_parent = article_nums[i - 1]
        curr_num, curr_label, curr_parent = article_nums[i]
        if curr_parent != prev_parent:
            continue  # 跨章/节（附件边界），条号重置合法
        if curr_num == prev_num:
            issues.append(f'  [重复条号] {prev_label} 与 {curr_label} 均为第{curr_num}条')
        elif curr_num > prev_num + 1:
            missing = list(range(prev_num + 1, curr_num))
            if len(missing) <= 5:
                miss_str = '、'.join(f'第{n}条' for n in missing)
            else:
                miss_str = f'第{missing[0]}条…第{missing[-1]}条（共{len(missing)}条）'
            issues.append(f'  [条文跳号] {prev_label} → {curr_label}，缺失：{miss_str}')
        elif curr_num < prev_num:
            issues.append(f'  [条文倒序] {prev_label}（{prev_num}）→ {curr_label}（{curr_num}）')

    # ── 2. 不允许连续两个 chapter / section（中间无 article）──────
    # 按 global_order 扫描，跟踪上一个非 article 类型
    prev_structural = None  # (type, title)
    has_article_between = True  # 上次结构节点后是否有过 article

    for r in rows:
        node_type = r[2]
        node_title = r[3] or r[4] or ''

        if node_type in ('chapter', 'section', 'part'):
            if prev_structural is not None and not has_article_between:
                pt, ptitle = prev_structural
                if pt == node_type:
                    issues.append(
                        f'  [连续{_type_cn(node_type)}] 「{ptitle}」后紧接「{node_title}」，中间无条文'
                    )
            prev_structural = (node_type, node_title)
            has_article_between = False
        elif node_type == 'article':
            has_article_between = True

    return issues


def _type_cn(t: str) -> str:
    return {'part': '编', 'chapter': '章', 'section': '节'}.get(t, t)


def main():
    if not DB_PATH.exists():
        print(f'数据库不存在：{DB_PATH}', file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    laws = conn.execute(
        "SELECT id, title, category FROM laws ORDER BY legal_domain, title"
    ).fetchall()

    total_issues = 0
    problem_laws = 0

    for law_id, title, category in laws:
        issues = check_law(conn, law_id, title)
        if issues:
            problem_laws += 1
            total_issues += len(issues)
            print(f'\n【{category}】{title}  (id={law_id})')
            for msg in issues:
                print(msg)

    conn.close()

    print(f'\n{"─"*60}')
    print(f'共检查 {len(laws)} 部法律')
    if total_issues == 0:
        print('✓ 未发现结构问题')
        return 0
    else:
        print(f'✗ 发现 {problem_laws} 部法律存在 {total_issues} 个问题')
        return 1


if __name__ == '__main__':
    sys.exit(main())
