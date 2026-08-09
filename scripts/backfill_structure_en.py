#!/usr/bin/env python3
"""
补齐缺失的结构节点英文标题：
- chapter 标题为"正文" → "Main Text"
- chapter 标题与 laws.title 相同 → 复用 laws.title_en
- 其他未翻译的 part/section/chapter 标题 → 若 law 有 title_en 且标题==law.title 复用，否则跳过打印
结果写回 nodes.content_en，并追加进 heading_en_map.json 缓存。
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

LAWS_DATA = Path(__file__).parent.parent
DB_PATH = LAWS_DATA / "law_content.db"
HEADING_MAP_PATH = LAWS_DATA / "references" / "heading_en_map.json"

MAIN_TEXT = "Main Text"


def main():
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("""
        SELECT n.id, n.law_id, n.type, COALESCE(n.order_index, 0), n.title, l.title, l.title_en
        FROM nodes n JOIN laws l ON n.law_id = l.id
        WHERE n.type IN ('part','chapter','section')
          AND (n.content_en IS NULL OR n.content_en = '')
          AND l.is_current = 1
        ORDER BY n.law_id, n.global_order
    """).fetchall()

    updated = 0
    remaining = []
    heading_updates = {}
    for node_id, law_id, ntype, oi, title, law_title, law_title_en in rows:
        en = None
        if ntype == "chapter" and title == "正文":
            en = MAIN_TEXT
        elif title == law_title and law_title_en:
            en = law_title_en
        elif ntype == "part" and title == law_title and law_title_en:
            en = law_title_en
        if en is None:
            remaining.append((law_id, ntype, title[:40]))
            continue
        conn.execute("UPDATE nodes SET content_en = ? WHERE id = ?", (en, node_id))
        updated += 1
        heading_updates[f"{law_id}:{ntype}:{oi}"] = en

    conn.commit()
    conn.close()
    print(f"已写入 {updated} 条（剩余未覆盖 {len(remaining)}）")
    for m in remaining[:40]:
        print("  未覆盖:", m)
    if len(remaining) > 40:
        print(f"  ... 等共 {len(remaining)} 条")

    if heading_updates:
        if HEADING_MAP_PATH.exists():
            heading_map = json.loads(HEADING_MAP_PATH.read_text(encoding="utf-8"))
        else:
            heading_map = {}
        added = 0
        for key, en in heading_updates.items():
            if key not in heading_map:
                heading_map[key] = en
                added += 1
        HEADING_MAP_PATH.write_text(
            json.dumps(heading_map, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(f"heading_en_map.json 追加 {added} 条（现有 {len(heading_map)} 条）")


if __name__ == "__main__":
    main()
