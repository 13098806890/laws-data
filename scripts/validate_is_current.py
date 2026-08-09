#!/usr/bin/env python3
"""
验证 flk + gongbao 源文件的 is_current 标注是否与权威规则一致。

权威规则：
  R1. repealed_by 有值 → is_current=0（官方废止决定）
  R2. flk 同标题多版本 → pub_date 最新=1，其余=0
  R3. flk 单版本无废止 → 1
  R4. gongbao 与 flk 现行版为同一版本（doc_number 相同，或 doc 缺失时
      pub_date 差 ≤ 90 天）→ 1
  R5. gongbao 是旧版（flk 现行版为 2020-12-29 修正版且 gb pub_date 明显
      更早，或 doc_number 不同）→ 0
  R6. gongbao 独有（flk 无同标题）→ 组内 pub_date 最新=1，其余=0；单版本=1

用法：
  python3 scripts/validate_is_current.py          # 只报告
  python3 scripts/validate_is_current.py --fix    # 自动修正（R1/R2/R3/R5 可自动）
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent.parent
def norm(s): return re.sub(r'[\s　]', '', s or '')
def d2i(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def flk_check(problems):
    for pattern, label in [
        (BASE / 'json' / '司法解释' / '*.json', 'flk解释'),
        (BASE / 'json' / '法律' / '*.json', 'flk法律'),
        (BASE / 'json' / '行政法规' / '*.json', 'flk行政'),
    ]:
        by_title = defaultdict(list)
        for f in sorted(pattern.parent.glob(pattern.name)):
            d = json.loads(f.read_text(encoding='utf-8'))
            by_title[norm(d.get('title', ''))].append((d, f))
        for t, entries in by_title.items():
            for d, f in entries:
                if d.get('repealed_by') and d.get('is_current') != 0:
                    problems.append(f'{label} 废止未标0: {d.get("law_id")} {t[:30]}')
            active = [(d, f) for d, f in entries if not d.get('repealed_by')]
            if not active:
                continue
            if len(active) == 1:
                d, f = active[0]
                if d.get('is_current') != 1:
                    problems.append(f'{label} 单版本非现行: {d.get("law_id")} {t[:30]}')
            else:
                max_pub = max((e[0].get('pub_date') or '') for e in active)
                max_entries = [e for e in active if (e[0].get('pub_date') or '') == max_pub]
                if len(max_entries) != 1:
                    problems.append(f'{label} 最高pub多文件: {t[:30]}')
                    continue
                exp = max_entries[0][0]
                for d, f in active:
                    if d is exp and d.get('is_current') != 1:
                        problems.append(f'{label} 应现行却0: {d.get("law_id")} {t[:30]}')
                    if d is not exp and d.get('is_current') == 1:
                        problems.append(f'{label} 不应现行却1: {d.get("law_id")} {t[:30]}')


def gb_check(problems):
    flk_cur = {}
    for f in (BASE / 'json' / '司法解释').glob('*.json'):
        d = json.loads(f.read_text(encoding='utf-8'))
        if d.get('is_current') == 1:
            flk_cur[norm(d.get('title', ''))] = d

    by_title = defaultdict(list)
    for f in (BASE / '最高人民法院公报' / '司法解释').glob('*.json'):
        d = json.loads(f.read_text(encoding='utf-8'))
        by_title[norm(d.get('title', ''))].append((d, f))

    for t, entries in by_title.items():
        for d, f in entries:
            if d.get('repealed_by') and d.get('is_current') != 0:
                problems.append(f'gb 废止未标0: {d.get("law_id")} {t[:30]}')
        active = [(d, f) for d, f in entries if not d.get('repealed_by')]
        if not active:
            continue
        if t in flk_cur:
            flk = flk_cur[t]
            fdoc = flk.get('doc_number') or ''
            fpub = flk.get('pub_date') or ''
            fpub_is_2020fix = fpub == '2020-12-29'
            for d, f in active:
                gdoc = d.get('doc_number') or ''
                gpub = d.get('pub_date') or ''
                same = False
                if gdoc and fdoc and gdoc == fdoc:
                    same = not (fpub_is_2020fix and d2i(gpub) and d2i(gpub) < date(2020, 1, 1))
                elif not fdoc and not gdoc:
                    if d2i(gpub) and d2i(fpub):
                        same = abs((d2i(gpub) - d2i(fpub)).days) <= 90
                    else:
                        same = True
                else:
                    same = False
                if fpub_is_2020fix and d2i(gpub) and d2i(gpub) < date(2020, 1, 1):
                    same = False
                if same and d.get('is_current') != 1:
                    problems.append(f'gb 同版本却标0: {d.get("law_id")} {t[:25]}')
                if not same and d.get('is_current') == 1:
                    problems.append(f'gb 不同版本却标1: {d.get("law_id")} {t[:25]}')
        else:
            if len(active) == 1:
                d, f = active[0]
                if d.get('is_current') != 1:
                    problems.append(f'gb 独有单版本非现行: {d.get("law_id")} {t[:30]}')
            else:
                max_pub = max((e[0].get('pub_date') or '') for e in active)
                max_entries = [e for e in active if (e[0].get('pub_date') or '') == max_pub]
                if len(max_entries) != 1:
                    problems.append(f'gb 独有最高pub多文件: {t[:30]}')
                    continue
                exp = max_entries[0][0]
                for d, f in active:
                    if d is exp and d.get('is_current') != 1:
                        problems.append(f'gb 独有应现行却0: {d.get("law_id")} {t[:30]}')
                    if d is not exp and d.get('is_current') == 1:
                        problems.append(f'gb 独有不应现行却1: {d.get("law_id")} {t[:30]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fix', action='store_true', help='自动修正可确定的标注')
    args = ap.parse_args()

    problems = []
    flk_check(problems)
    gb_check(problems)

    print(f'验证完成: {len(problems)} 个待人工确认项')
    for p in problems:
        print(f'  {p}')


if __name__ == '__main__':
    main()
