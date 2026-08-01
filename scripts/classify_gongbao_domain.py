#!/usr/bin/env python3
"""为 gongbao 来源的司法解释分配 legal_domain 和 subject_area。"""

import sqlite3, sys, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / 'docx_to_json'))

import domain

DB_PATH = Path(__file__).parent.parent / 'law_content.db'

def main():
    conn = sqlite3.connect(DB_PATH)
    domain_idx = domain.build_domain_index()

    rows = conn.execute(
        "SELECT id, title, category, legal_domain FROM laws WHERE source = 'gongbao' AND is_current = 1"
    ).fetchall()
    
    if not rows:
        print("  无需分类")
        conn.close()
        return

    updated = 0
    for law_id, title, category, old_domain in rows:
        # 标题规范化（与 builder.normalize_title 同款规则）
        new_title = title.replace('　', ' ')
        new_title = re.sub(r'最高人民法院 +最高人民检察院', '最高人民法院、最高人民检察院', new_title)
        new_title = re.sub(r'最高人民检察院 +最高人民法院', '最高人民检察院、最高人民法院', new_title)
        new_title = re.sub(r'最高人民法院 +公安部', '最高人民法院、公安部', new_title)
        new_title = re.sub(r'最高人民检察院 +公安部', '最高人民检察院、公安部', new_title)
        new_title = re.sub(r'(最高人民法院|最高人民检察院|公安部|国家安全部|司法部) +', r'\1', new_title)
        new_title = re.sub(r'([）》」』］]) +', r'\1', new_title)
        new_title = re.sub(r'([\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])', r'\1', new_title)
        new_title = re.sub(r' +', ' ', new_title).strip()
        if new_title != title:
            conn.execute("UPDATE laws SET title = ? WHERE id = ?", (new_title, law_id))

        data = {'category': category, 'promulgation_info': ''}
        new_domain = domain.get_legal_domain(new_title, data, domain_idx)
        if not new_domain:
            if category in ('司法解释', '法律解释'):
                new_domain = '诉讼与非诉讼程序法'
            elif category == '行政法规':
                new_domain = '行政法'
            else:
                continue
        conn.execute("UPDATE laws SET legal_domain = ? WHERE id = ?", (new_domain, law_id))
        updated += 1

    conn.commit()
    print(f"  更新 legal_domain: {updated} 条")
    conn.close()

if __name__ == '__main__':
    main()
