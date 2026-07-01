#!/usr/bin/env python3
"""
将 json_en/ 中的英文翻译导入到数据库的 nodes 表

步骤：
1. 为 nodes 表添加 content_en 字段
2. 从 json_en/ 读取所有英文翻译
3. 根据 law_id 和 article_number 匹配，更新 content_en 字段

用法：
  python3 scripts/import_en_to_db.py
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import JSON_DIR, DB_PATH

JSON_EN_DIR = JSON_DIR.parent / 'json_en'


def add_content_en_column(conn: sqlite3.Connection):
    """为 nodes 表添加 content_en 字段"""
    try:
        conn.execute('ALTER TABLE nodes ADD COLUMN content_en TEXT')
        print('✅ 已添加 content_en 字段到 nodes 表')
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e):
            print('ℹ️  content_en 字段已存在')
        else:
            raise


def get_law_mapping(conn: sqlite3.Connection) -> dict:
    """获取 filename → law_id 的映射"""
    rows = conn.execute('SELECT id, filename, category FROM laws').fetchall()
    return {(filename, category): law_id for law_id, filename, category in rows}


def import_translations(conn: sqlite3.Connection, law_mapping: dict):
    """从 json_en/ 导入英文翻译"""
    updated = 0
    skipped = 0

    for cat_dir in JSON_EN_DIR.iterdir():
        if not cat_dir.is_dir():
            continue

        category = cat_dir.name

        for json_file in cat_dir.glob('*.json'):
            filename = json_file.stem  # 不含 .json

            # 查找对应的 law_id
            law_id = law_mapping.get((filename, category))
            if not law_id:
                print(f'⚠️  未找到法律：{category}/{filename}')
                continue

            # 读取英文翻译
            try:
                en_data = json.loads(json_file.read_text(encoding='utf-8'))
            except:
                print(f'❌ 读取失败：{json_file}')
                continue

            # 更新每条条文
            for art in en_data.get('articles', []):
                art_num = art.get('article_number', '')
                content_en = art.get('content_en', '').strip()

                if not art_num or not content_en:
                    continue

                # 提取数字条号（第X条 → X）
                import re
                match = re.search(r'第([一二三四五六七八九十百千零\d]+)条', art_num)
                if not match:
                    continue

                cn_num = match.group(1)

                # 转换为阿拉伯数字
                if cn_num.isdigit():
                    article_num = int(cn_num)
                else:
                    # 简单的中文数字转换（复用 fix_translation_newlines.py 的逻辑）
                    article_num = chinese_number_to_int(cn_num)

                if article_num == 0:
                    continue

                # 更新数据库
                result = conn.execute('''
                    UPDATE nodes
                    SET content_en = ?
                    WHERE law_id = ? AND article_num = ? AND type = 'article'
                ''', (content_en, law_id, article_num))

                if result.rowcount > 0:
                    updated += 1
                else:
                    skipped += 1

    return updated, skipped


def chinese_number_to_int(cn_num: str) -> int:
    """将中文数字转换为阿拉伯数字"""
    if cn_num.isdigit():
        return int(cn_num)

    cn_map = {
        '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
        '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
        '十': 10, '百': 100, '千': 1000,
    }

    total = 0
    current = 0

    for char in cn_num:
        if char not in cn_map:
            return 0

        val = cn_map[char]

        if val >= 10:
            if current == 0:
                current = 1
            total += current * val
            current = 0
        else:
            current = val

    total += current
    return total


def main():
    print('\n🔄 导入英文翻译到数据库\n')
    print('=' * 60)

    # 连接数据库
    conn = sqlite3.connect(DB_PATH)

    # 1. 添加 content_en 字段
    print('\n步骤 1: 添加字段')
    add_content_en_column(conn)

    # 2. 获取法律映射
    print('\n步骤 2: 读取法律映射')
    law_mapping = get_law_mapping(conn)
    print(f'   找到 {len(law_mapping)} 部法律')

    # 3. 导入翻译
    print('\n步骤 3: 导入英文翻译')
    updated, skipped = import_translations(conn, law_mapping)

    # 提交更改
    conn.commit()
    conn.close()

    # 统计
    print('\n' + '=' * 60)
    print('\n📊 导入统计：')
    print(f'   已更新：{updated:,} 条')
    print(f'   已跳过：{skipped:,} 条（未找到匹配或无翻译）')

    # 验证
    print('\n🔍 验证：')
    conn = sqlite3.connect(DB_PATH)
    total = conn.execute('SELECT COUNT(*) FROM nodes WHERE type = "article"').fetchone()[0]
    with_en = conn.execute('SELECT COUNT(*) FROM nodes WHERE type = "article" AND content_en IS NOT NULL AND content_en != ""').fetchone()[0]
    conn.close()

    print(f'   总条文数：{total:,}')
    print(f'   有英文：{with_en:,} ({with_en/total*100:.1f}%)')

    print('\n✅ 导入完成！')
    print()


if __name__ == '__main__':
    main()
