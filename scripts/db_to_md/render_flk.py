#!/usr/bin/env python3
"""
DB → 法考/ Markdown
目录结构由 flk_menu.json 驱动，输出到 BASE_DIR/法考/。

目录结构：
  法考/
    刑法/
      中华人民共和国刑法.md
      最高人民法院关于…
      ...
    刑事诉讼法/
    行政法与行政诉讼法/
    民法/
    商法/
    民事诉讼法/
"""

import json
import shutil
import sqlite3
from pathlib import Path

from config import DB_PATH, BASE_DIR
from db_to_md.renderer import law_to_md, _build_cited_by_map, LAW_KEYS

FLK_MENU_PATH = BASE_DIR / 'flk_menu.json'
FLK_MD_DIR    = BASE_DIR / '法考'


def build_flk_markdown(db_path: Path = DB_PATH,
                       flk_menu_path: Path = FLK_MENU_PATH,
                       flk_md_dir: Path = FLK_MD_DIR):
    if not flk_menu_path.exists():
        print(f'未找到 {flk_menu_path}，跳过法考 Markdown 生成')
        return

    menu = json.loads(flk_menu_path.read_text(encoding='utf-8'))

    # 清理旧目录
    if flk_md_dir.exists():
        shutil.rmtree(flk_md_dir)

    conn = sqlite3.connect(db_path)

    laws_rows = conn.execute(
        f"SELECT {', '.join(LAW_KEYS)} FROM laws WHERE is_current=1"
    ).fetchall()
    law_map: dict[int, dict] = {r[0]: dict(zip(LAW_KEYS, r)) for r in laws_rows}

    cited_by = _build_cited_by_map(conn)

    # 在法考目录内部建立 law_location（group=科目, subgroup=科目）
    flk_law_location: dict[int, tuple[str, str]] = {}
    for grp in menu['groups']:
        group = grp['label']
        for sub in grp['subgroups']:
            subgroup = sub['label']
            for law_entry in sub.get('laws', []):
                lid = law_entry['id'] if isinstance(law_entry, dict) else law_entry
                flk_law_location[lid] = (group, subgroup)

    written = 0
    for grp in menu['groups']:
        group = grp['label']
        for sub in grp['subgroups']:
            subgroup = sub['label']
            # 法考目录下每个科目就是一个文件夹，subgroup == group
            out_dir = flk_md_dir / group
            out_dir.mkdir(parents=True, exist_ok=True)

            for law_entry in sub.get('laws', []):
                law_id = law_entry['id'] if isinstance(law_entry, dict) else law_entry
                law = law_map.get(law_id)
                if law is None:
                    continue

                nodes_rows = conn.execute(
                    'SELECT type, content, article_num, content_en FROM nodes WHERE law_id=? ORDER BY global_order',
                    (law_id,)
                ).fetchall()
                node_list = [{'type': r[0], 'content': r[1], 'article_num': r[2], 'content_en': r[3]}
                             for r in nodes_rows]

                # 引用关系（法考目录内的相对链接）
                from db_to_md.renderer import _build_ref_map
                ref_map = _build_ref_map(conn, law_id, group, subgroup,
                                         flk_md_dir, flk_law_location)

                md = law_to_md(law, node_list, ref_map, cited_by, law_map,
                               flk_md_dir, group, subgroup, flk_law_location)
                (out_dir / (law['title'] + '.md')).write_text(md, encoding='utf-8')
                written += 1

    conn.close()
    print(f'法考 Markdown 生成完成：{written} 个文件，输出目录：{flk_md_dir}')
    for grp in menu['groups']:
        d = flk_md_dir / grp['label']
        total = sum(1 for _ in d.rglob('*.md')) if d.exists() else 0
        print(f'  {grp["label"]}/  共 {total} 个')


def run():
    print('\n=== 法考 Markdown ===')
    build_flk_markdown()


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
