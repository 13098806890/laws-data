#!/usr/bin/env python3
"""
从 法考目录.json + laws 表生成 flk_menu.json。

格式与 law_menu.json 完全相同，但：
- groups 按法考六大科目排列（刑法、刑事诉讼法、行政法与行政诉讼法、民法、商法、民事诉讼法）
- 每个 group 只有一个 subgroup（与 group 同名），列出所有属于该科目的法律
- 法律顺序保持与 法考目录.json 中一致（不按 title 排序）

输出路径：BASE_DIR/flk_menu.json
"""

import json
import sqlite3
from datetime import date
from pathlib import Path

from config import DB_PATH, BASE_DIR

FLK_MENU_PATH = BASE_DIR / 'flk_menu.json'
FLK_DIR_PATH  = BASE_DIR / '法考目录.json'

# 法考六大科目顺序
_FLK_GROUP_ORDER = [
    '刑法',
    '刑事诉讼法',
    '行政法与行政诉讼法',
    '民法',
    '商法',
    '民事诉讼法',
]


def export_flk_menu(db_path: Path = DB_PATH,
                    flk_dir_path: Path = FLK_DIR_PATH,
                    menu_path: Path = FLK_MENU_PATH):
    if not flk_dir_path.exists():
        print(f'未找到 {flk_dir_path}，跳过法考菜单生成')
        return

    flk_data: dict[str, list[str]] = json.loads(
        flk_dir_path.read_text(encoding='utf-8')
    )

    # 从 DB 建立 title → {id, title} 映射（只取 is_current=1）
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        'SELECT id, title FROM laws WHERE is_current=1'
    ).fetchall()
    conn.close()

    title_to_law: dict[str, dict] = {r[1]: {'id': r[0], 'title': r[1]} for r in rows}

    # 规范化查找（去书名号和版本后缀）
    import re as _re
    def _norm(t: str) -> str:
        t = t.replace('《', '').replace('》', '')
        t = _re.sub(r'[\(（][^\)）]{0,8}[\)）]$', '', t).strip()
        return t

    norm_map: dict[str, dict] = {_norm(k): v for k, v in title_to_law.items()}

    groups_out = []
    total = 0
    missing = []

    for group_label in _FLK_GROUP_ORDER:
        law_titles = flk_data.get(group_label, [])
        laws_out = []
        for title in law_titles:
            law = title_to_law.get(title) or norm_map.get(_norm(title))
            if law:
                laws_out.append(law)
            else:
                missing.append((group_label, title))

        groups_out.append({
            'label': group_label,
            'subgroups': [
                {'label': group_label, 'laws': laws_out}
            ],
        })
        total += len(laws_out)

    menu = {
        'name': '法考专用',
        'version': date.today().isoformat(),
        'groups': groups_out,
    }
    menu_path.write_text(json.dumps(menu, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'flk_menu.json 导出完成：{len(groups_out)} 个科目，{total} 部法律 → {menu_path}')
    if missing:
        print(f'  未匹配 {len(missing)} 部（可能已归入其他版本或标题有差异）：')
        for grp, t in missing[:10]:
            print(f'    [{grp}] {t[:60]}')
        if len(missing) > 10:
            print(f'    ...（共 {len(missing)} 条）')


def run():
    print('\n=== 导出 flk_menu.json ===')
    export_flk_menu()


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
