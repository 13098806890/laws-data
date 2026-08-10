#!/usr/bin/env python3
"""
将 build_gongbao_db.py 提取/推导的字段回写到源 JSON 文件。

增量策略：JSON 中已有非空值的字段不覆盖，只补充空缺字段。

运行：
    cd path/to/laws_data
    python3 scripts/enrich_gongbao_json.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_gongbao_db import (
    GONGBAO_DIR, DOC_SOURCES,
    extract_ruling_gist, extract_keywords,
    extract_case_number, infer_keywords_from_text,
)


def enrich_file(path: Path, source: str) -> tuple[bool, str]:
    """处理单个 JSON 文件，返回 (changed, reason)。"""
    d = json.loads(path.read_text(encoding='utf-8'))
    content = d.get('content', '')
    title   = d.get('title', '')
    changed = False
    reasons = []

    # --- ruling_gist ---
    if not d.get('ruling_gist'):
        gist = extract_ruling_gist(content)
        if gist:
            d['ruling_gist'] = gist
            changed = True
            reasons.append('ruling_gist')

    # --- keywords ---
    if not d.get('keywords'):
        kw = extract_keywords(content)
        if not kw:
            gist = d.get('ruling_gist', '')
            kw = infer_keywords_from_text(title, gist, content)
        if kw:
            d['keywords'] = kw
            changed = True
            reasons.append('keywords')

    # --- case_number (al 专属) ---
    if source == 'al' and not d.get('case_number'):
        cn = extract_case_number(title)
        if cn:
            d['case_number'] = cn
            changed = True
            reasons.append('case_number')

    if changed:
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')

    return changed, ', '.join(reasons)


def main():
    total = changed = 0
    for source, folder in DOC_SOURCES.items():
        if not folder.exists():
            print(f'⚠ 目录不存在：{folder}')
            continue
        files = list(folder.glob('*.json'))
        src_changed = 0
        for f in files:
            total += 1
            ok, reason = enrich_file(f, source)
            if ok:
                changed += 1
                src_changed += 1
        print(f'  {source:10s}: {len(files)} 个文件，{src_changed} 个更新')

    print(f'\n完成：共 {total} 个文件，{changed} 个已更新。')


if __name__ == '__main__':
    main()
