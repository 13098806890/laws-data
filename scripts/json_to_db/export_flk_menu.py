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

FLK_MENU_PATH = BASE_DIR / '法考' / 'flk_menu.json'
FLK_DIR_PATH  = BASE_DIR / '法考' / '法考目录.json'

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

    # 规范化查找：
    #   1. 精确匹配
    #   2. 半角括号 → 全角括号（法考目录用半角，DB 用全角）
    #   3. 去书名号（《》）后匹配
    # 注意：不能去掉末尾括号内容，否则"修正案(四)"和"修正案(十二)"会变成同一个键导致冲突
    def _to_fullwidth_bracket(t: str) -> str:
        return t.replace('(', '（').replace(')', '）')

    def _strip_book_marks(t: str) -> str:
        return t.replace('《', '').replace('》', '')

    # 建立多种规范化形式的查找映射（后建的不覆盖先建的，用 setdefault）
    norm_map: dict[str, dict] = {}
    for db_title, law in title_to_law.items():
        for variant in [
            _strip_book_marks(db_title),
            _to_fullwidth_bracket(db_title),
            _strip_book_marks(_to_fullwidth_bracket(db_title)),
        ]:
            norm_map.setdefault(variant, law)

    def _lookup(title: str):
        """按优先级查找：精确 → 半角转全角 → 去书名号 → 两者组合"""
        return (
            title_to_law.get(title)
            or norm_map.get(_to_fullwidth_bracket(title))
            or norm_map.get(_strip_book_marks(title))
            or norm_map.get(_strip_book_marks(_to_fullwidth_bracket(title)))
        )

    groups_out = []
    total = 0
    missing = []

    for group_label in _FLK_GROUP_ORDER:
        law_titles = flk_data.get(group_label, [])
        laws_out = []
        for title in law_titles:
            law = _lookup(title)
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
