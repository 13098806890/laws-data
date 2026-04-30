#!/usr/bin/env python3
"""
为每部法律分配稳定的整数 law_id，写入：
  - law_index.json（索引文件，所有法律汇总）
  - 每个 JSON 文件新增 law_id 字段

ID 分段规则（每档 10 万，内部按 pub_date 升序排列）：
  宪法                                100001–199999
  法律                                200001–299999
  法律解释                            300001–399999
  修正案                              400001–499999
  有关法律问题和重大问题的决定（部分）  500001–599999
  行政法规                            600001–699999
  监察法规                            700001–799999
  司法解释                            800001–899999
  地方性法规（预留）                  900001–999999
  地方性规章（预留）                 1000001–1099999

已分配的 ID 永久固定，不随重新运行改变。
新增法律追加到所属分段末尾。
"""

import json
from pathlib import Path

from config import JSON_DIR

INDEX_PATH = Path(__file__).parent.parent / 'law_index.json'

CATEGORY_BASE = {
    '宪法':                                100001,
    '法律':                                200001,
    '法律解释':                            300001,
    '修正案':                              400001,
    '有关法律问题和重大问题的决定（部分）': 500001,
    '行政法规':                            600001,
    '监察法规':                            700001,
    '司法解释':                            800001,
}
CATEGORY_CAP = 100000  # 每档 10 万个 ID


def _load_existing_index() -> dict:
    """加载已有索引，返回 {filename: law_id}"""
    if not INDEX_PATH.exists():
        return {}
    data = json.loads(INDEX_PATH.read_text(encoding='utf-8'))
    return {entry['filename']: entry['law_id'] for entry in data}


def run():
    # 扫描所有 JSON 文件
    paths = sorted(
        (p for p in JSON_DIR.rglob('*.json') if 'index' not in p.name),
        key=lambda p: p.stem
    )

    existing = _load_existing_index()

    # 按 category 分组，组内按 pub_date 升序排列（决定新 ID 顺序）
    from collections import defaultdict
    by_category = defaultdict(list)
    for path in paths:
        data = json.loads(path.read_text(encoding='utf-8'))
        cat = data.get('category', '未知')
        by_category[cat].append({
            'path':     path,
            'filename': path.stem,
            'title':    data.get('title', ''),
            'category': cat,
            'legal_domain': data.get('legal_domain', ''),
            'pub_date': data.get('pub_date') or '',
            'effective_date': data.get('effective_date') or '',
        })

    for cat in by_category:
        by_category[cat].sort(key=lambda x: x['pub_date'])

    # 分配 ID：已有的保留，新增的追加
    assigned = dict(existing)  # filename → law_id

    # 找出每个分段当前已用到的最大 ID
    max_in_seg = {}
    for filename, lid in assigned.items():
        # 通过 ID 反推分段基数
        for cat, base in CATEGORY_BASE.items():
            if base <= lid < base + CATEGORY_CAP:
                if cat not in max_in_seg or lid > max_in_seg[cat]:
                    max_in_seg[cat] = lid
                break

    for cat, entries in by_category.items():
        base = CATEGORY_BASE.get(cat)
        if base is None:
            print(f'  警告：未知分类 "{cat}"，跳过 {len(entries)} 个文件')
            continue
        next_id = max_in_seg.get(cat, base - 1) + 1
        for entry in entries:
            fn = entry['filename']
            if fn not in assigned:
                if next_id >= base + CATEGORY_CAP:
                    raise RuntimeError(f'分类 "{cat}" ID 段已满（{base}–{base+CATEGORY_CAP-1}）')
                assigned[fn] = next_id
                next_id += 1

    # 写回每个 JSON 文件的 law_id 字段
    updated = 0
    for path in paths:
        data = json.loads(path.read_text(encoding='utf-8'))
        fn = path.stem
        lid = assigned.get(fn)
        if lid is None:
            continue
        if data.get('law_id') != lid:
            # 把 law_id 插到最前面
            new_data = {'law_id': lid}
            new_data.update(data)
            path.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding='utf-8')
            updated += 1

    # 生成 law_index.json
    index_entries = []
    for cat, entries in sorted(by_category.items()):
        for entry in entries:
            fn = entry['filename']
            lid = assigned.get(fn)
            if lid is None:
                continue
            index_entries.append({
                'law_id':       lid,
                'filename':     fn,
                'title':        entry['title'],
                'category':     entry['category'],
                'legal_domain': entry['legal_domain'],
                'pub_date':     entry['pub_date'],
                'effective_date': entry['effective_date'],
            })
    index_entries.sort(key=lambda x: x['law_id'])

    INDEX_PATH.write_text(json.dumps(index_entries, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'law_index.json 生成完成：{len(index_entries)} 条，更新 JSON 文件 {updated} 个')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    run()
