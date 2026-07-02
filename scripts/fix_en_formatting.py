#!/usr/bin/env python3
"""
修复英文翻译中的格式问题：
1. 编号列表换行：中文（一）（二）→ 英文 (1)(2) 混成一段 → 拆行为逐条
2. 后续可扩展其他格式化规则

用法：
  python3 scripts/fix_en_formatting.py              # 修复 json_en + 同步 DB + 重新生成 MD
  python3 scripts/fix_en_formatting.py --dry-run    # 预览，不做修改
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH

BASE_DIR = Path(__file__).parent.parent
JSON_EN_DIR = BASE_DIR / 'json_en'

RULES = []

def rule(pattern, replace, desc):
    """注册格式化规则"""
    RULES.append((re.compile(pattern), replace, desc))


# ── 规则定义 ──

# 1. 编号列表换行: "text. (1) item; (2) item; or (3) item" → 逐行
rule(
    r'(?<=[;:.]) (\([0-9一二三四五六七八九十]+\))',
    r'\n\1',
    '编号列表换行'
)
rule(
    r'; or (\([0-9]+\))',
    r'\n\1',
    'or (N) 换行'
)

# 2. 后续可添加更多规则：
# 如：中文标点清理（已由 translate_to_en 处理）、空格规范化等


def fix_article(en: str) -> str:
    for pat, repl, _ in RULES:
        en = pat.sub(repl, en)
    en = re.sub(r'\n +', r'\n', en)  # 去掉换行后的多余空格
    return en


def main():
    parser = argparse.ArgumentParser(description='修复英文翻译格式')
    parser.add_argument('--dry-run', action='store_true', help='仅预览，不修改')
    args = parser.parse_args()

    total_fixed = 0
    total_files = 0
    stats = {desc: 0 for _, _, desc in RULES}

    for en_path in sorted(JSON_EN_DIR.rglob('*.json')):
        data = json.loads(en_path.read_text(encoding='utf-8'))
        changed = False
        for art in data.get('articles', []):
            en = art.get('content_en', '')
            if not en:
                continue
            new_en = fix_article(en)
            if new_en != en:
                for pat, repl, desc in RULES:
                    if pat.search(en):
                        stats[desc] += 1
                art['content_en'] = new_en
                changed = True
                total_fixed += 1

        if changed and not args.dry_run:
            en_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
            total_files += 1

    if args.dry_run:
        print(f'预览: 将修复 {total_fixed} 条条文')
        for desc, cnt in stats.items():
            if cnt:
                print(f'  {desc}: {cnt} 处')
        return

    print(f'修复 json_en: {total_fixed} 条条文, {total_files} 个文件')

    # ── 同步到数据库 ──
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    updated = 0
    for en_path in JSON_EN_DIR.rglob('*.json'):
        data = json.loads(en_path.read_text(encoding='utf-8'))
        lid = data.get('law_id')
        if not lid:
            continue
        for art in data.get('articles', []):
            en = art.get('content_en', '').strip()
            an = art.get('article_number', '')
            if not an or not en:
                continue
            conn.execute(
                'UPDATE nodes SET content_en=? WHERE law_id=? AND article_number=?',
                (en, lid, an)
            )
            updated += 1
    conn.commit()
    total_laws = conn.execute(
        'SELECT COUNT(DISTINCT law_id) FROM nodes WHERE content_en IS NOT NULL AND content_en != ""'
    ).fetchone()[0]
    conn.close()
    print(f'同步 DB: {updated} 条, {total_laws} 部法律')

    # ── 重新生成 Markdown ──
    from db_to_md.renderer import build_markdown
    build_markdown()
    print('Markdown 重新生成完成')


if __name__ == '__main__':
    main()
