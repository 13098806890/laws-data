#!/usr/bin/env python3
"""从 is_current=1 的法律中提取不重复标题，准备 LLM 翻译"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH

OUT_PATH = Path(__file__).parent.parent / 'references' / 'titles_for_translation.json'


def main():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        'SELECT DISTINCT title FROM laws WHERE is_current=1 ORDER BY title'
    ).fetchall()
    conn.close()

    titles = [r[0] for r in rows]
    print(f'不重复标题：{len(titles)} 个')

    data = {
        'count': len(titles),
        'titles': titles,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'已写入：{OUT_PATH}')


if __name__ == '__main__':
    main()
