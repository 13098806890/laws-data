#!/usr/bin/env python3
"""为 is_current=1 的法律生成英文翻译模板文件到 json_en/"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import JSON_DIR, DB_PATH

JSON_EN_DIR = JSON_DIR.parent / 'json_en'
CATEGORY_DIRS = sorted(d.name for d in JSON_DIR.iterdir() if d.is_dir())


def main():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        'SELECT id, filename, category, title FROM laws WHERE is_current=1'
    ).fetchall()
    conn.close()

    print(f'现行法律：{len(rows)} 部')

    for law_id, filename, category, title in rows:
        cat_dir = JSON_EN_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        out_path = cat_dir / f'{filename}.json'

        if out_path.exists():
            continue

        # 读中文 JSON 获取条文结构
        cn_path = JSON_DIR / category / f'{filename}.json'
        if not cn_path.exists():
            continue

        cn_data = json.loads(cn_path.read_text(encoding='utf-8'))

        # 提取所有条文（平坦化，含 article_number）
        articles = []

        def collect_articles(chapters):
            for ch in chapters:
                for sec in ch.get('sections', []):
                    for a in sec.get('articles', []):
                        _add_article(a)
                for a in ch.get('articles', []):
                    _add_article(a)

        def _add_article(a):
            art_num = (a.get('title') or '').rstrip('　 ').strip()
            articles.append({
                'article_number': art_num,
                'content_en': '',
            })

        if 'parts' in cn_data:
            for pt in cn_data['parts']:
                collect_articles(pt.get('chapters', []))
        elif 'chapters' in cn_data:
            collect_articles(cn_data['chapters'])

        tmpl = {
            'law_id': law_id,
            'title_en': '',
            'promulgation_info_en': '',
            'articles': articles,
        }

        out_path.write_text(
            json.dumps(tmpl, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8'
        )

    # 统计
    total = sum(1 for _ in JSON_EN_DIR.rglob('*.json'))
    print(f'模板文件生成完成：{total} 个')


if __name__ == '__main__':
    main()
