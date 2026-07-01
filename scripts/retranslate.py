#!/usr/bin/env python3
"""
重新翻译已有的英文翻译，用于修复质量问题。

用法：
  export ANTHROPIC_API_KEY=sk-ant-... 或 DEEPSEEK_API_KEY=sk-...

  # 重新翻译所有已翻译的法律
  python3 scripts/retranslate.py

  # 只重新翻译特定法律
  python3 scripts/retranslate.py --filter 民法典

  # 预览待重新翻译的法律
  python3 scripts/retranslate.py --dry-run
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import JSON_DIR, DB_PATH

JSON_EN_DIR = JSON_DIR.parent / 'json_en'


def clear_translations(filename: str, category: str):
    """清空已有翻译，准备重新翻译"""
    en_path = JSON_EN_DIR / category / f'{filename}.json'
    if not en_path.exists():
        return False

    try:
        en_data = json.loads(en_path.read_text(encoding='utf-8'))
    except:
        return False

    # 检查是否有英文内容
    articles = en_data.get('articles', [])
    has_en = any(a.get('content_en', '').strip() for a in articles)

    if not has_en:
        return False

    # 清空所有英文内容
    for art in articles:
        art['content_en'] = ''

    en_path.write_text(json.dumps(en_data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return True


def main():
    parser = argparse.ArgumentParser(description='重新翻译已有的法律')
    parser.add_argument('--dry-run', action='store_true', help='预览，不清空翻译')
    parser.add_argument('--filter', type=str, default='', help='只处理标题含此关键词的法律')
    args = parser.parse_args()

    import sqlite3
    conn = sqlite3.connect(DB_PATH)

    query = "SELECT filename, category, title FROM laws WHERE is_current=1"
    if args.filter:
        query += f" AND title LIKE '%{args.filter}%'"

    rows = conn.execute(query).fetchall()
    conn.close()

    print(f"扫描 {len(rows)} 部法律...\n")

    to_retranslate = []

    for filename, category, title in rows:
        en_path = JSON_EN_DIR / category / f'{filename}.json'
        if not en_path.exists():
            continue

        try:
            en_data = json.loads(en_path.read_text(encoding='utf-8'))
            articles = en_data.get('articles', [])
            en_count = sum(1 for a in articles if a.get('content_en', '').strip())

            if en_count > 0:
                to_retranslate.append((filename, category, title, en_count))
        except:
            continue

    if not to_retranslate:
        print("没有找到已翻译的法律")
        return

    print(f"找到 {len(to_retranslate)} 部已翻译的法律：\n")

    total_articles = 0
    for filename, category, title, count in to_retranslate:
        print(f"  - {title} ({count} 条)")
        total_articles += count

    print(f"\n总计：{len(to_retranslate)} 部法律，{total_articles} 条条文")

    if args.dry_run:
        print("\n[DRY-RUN] 未执行清空操作")
        print("\n下一步：运行不带 --dry-run 的命令清空翻译，然后运行 translate_to_en.py 重新翻译")
        return

    print("\n⚠️  警告：即将清空这些法律的英文翻译！")
    print("清空后，需要运行 translate_to_en.py 重新翻译")
    print("\n输入 'yes' 确认继续：", end=' ')

    confirmation = input().strip().lower()
    if confirmation != 'yes':
        print("已取消")
        return

    print("\n清空翻译中...")

    cleared = 0
    for filename, category, title, _ in to_retranslate:
        if clear_translations(filename, category):
            cleared += 1
            print(f"  ✓ {title}")

    print(f"\n完成！已清空 {cleared} 部法律的翻译")
    print("\n下一步：运行以下命令重新翻译：")
    if args.filter:
        print(f"  python3 scripts/translate_to_en.py --filter {args.filter}")
    else:
        print("  python3 scripts/translate_to_en.py")


if __name__ == "__main__":
    main()
