#!/usr/bin/env python3
"""
更新 Markdown 中已有的英文翻译

适用场景：
- 英文翻译已经插入到 Markdown，但需要更新内容（如修复换行符）
- 不会重复插入，会替换现有的英文翻译

用法：
  python3 scripts/update_en_in_md.py                    # 更新所有
  python3 scripts/update_en_in_md.py --dry-run          # 预览
  python3 scripts/update_en_in_md.py --filter 民法典     # 只更新指定法律
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import JSON_DIR, DB_PATH

JSON_EN_DIR = JSON_DIR.parent / 'json_en'
MD_BASE_DIR = JSON_DIR.parent


def load_en_articles(filename: str, category: str) -> dict:
    """从 json_en/ 加载英文翻译，返回 {article_number: content_en}"""
    en_path = JSON_EN_DIR / category / f'{filename}.json'
    if not en_path.exists():
        return {}

    try:
        en_data = json.loads(en_path.read_text(encoding='utf-8'))
    except:
        return {}

    result = {}
    for art in en_data.get('articles', []):
        art_num = art.get('article_number', '')
        content_en = art.get('content_en', '').strip()
        if art_num and content_en:
            result[art_num] = content_en

    return result


def find_md_file(title: str, legal_domain: str) -> Path | None:
    """查找法律对应的 Markdown 文件"""
    clean_title = re.sub(r'（\d{4}.*?）$', '', title).strip()

    domain_map = {
        '民法典': ['民事与商事/民法典', '法考/民法'],
        '民法商法': ['民事与商事/民法', '民事与商事/商法', '法考/民法'],
        '刑法': ['刑事/刑法', '法考/刑法'],
        '行政法': ['行政/行政法', '法考/行政法'],
        '经济法': ['经济、税务与金融', '法考/经济法'],
        '社会法': ['劳动与社会保障', '法考/社会法'],
        '诉讼与非诉讼程序法': ['诉讼与司法程序', '法考/诉讼法'],
        '宪法相关法': ['宪法与立法', '法考/宪法'],
    }

    search_dirs = []
    for dir_pattern in domain_map.get(legal_domain, []):
        search_dirs.append(MD_BASE_DIR / dir_pattern)
    search_dirs.append(MD_BASE_DIR)

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        for md_path in search_dir.rglob('*.md'):
            if md_path.stem == clean_title or md_path.stem == title:
                return md_path

    return None


def update_en_in_md(md_path: Path, en_articles: dict, dry_run: bool = False) -> tuple[int, int]:
    """
    更新 Markdown 文件中的英文翻译
    返回 (处理的条文数, 更新的英文条数)
    """
    if not md_path.exists():
        return 0, 0

    content = md_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    new_lines = []
    updated = 0
    total_articles = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        # 匹配条文行：<a id="art-X"></a>第X条　...
        art_match = re.match(r'<a id="art-\d+"></a>(第[一二三四五六七八九十百千零\d]+条)(?:　|\s)+(.*)', line)

        if art_match:
            art_num = art_match.group(1)
            total_articles += 1

            # 添加条文行（中文）
            new_lines.append(line)
            i += 1

            # 查找现有的英文翻译（紧跟在后面，或在空行之后）
            en_start = -1
            en_end = -1

            # 跳过空行
            while i < len(lines) and not lines[i].strip():
                new_lines.append(lines[i])
                i += 1

            # 检查是否有英文翻译（以 **Article 开头）
            if i < len(lines) and lines[i].strip().startswith('**Article'):
                en_start = i
                # 找到英文翻译的结束位置（下一个空行或下一个条文）
                while i < len(lines):
                    if not lines[i].strip():
                        # 空行，英文结束
                        en_end = i
                        break
                    if lines[i].strip().startswith('<a id="art-'):
                        # 下一个条文，英文结束
                        en_end = i
                        break
                    i += 1

                if en_end == -1:
                    en_end = i  # 文件结尾

            # 如果有新翻译，更新
            if art_num in en_articles:
                new_en = en_articles[art_num]

                # 处理多段落：将换行符转换为 Markdown 硬换行
                if '\n' in new_en:
                    new_en = new_en.replace('\n', '  \n')

                # 提取 Article 编号
                art_en_match = re.match(r'(Article \d+)', new_en)
                if art_en_match:
                    art_en_label = art_en_match.group(1)
                    en_content_body = new_en[len(art_en_label):].strip()
                    formatted_en = f'**{art_en_label}** {en_content_body}'
                else:
                    # 没有 Article X 前缀
                    art_number = re.search(r'第(\d+)条', art_num)
                    if art_number:
                        num = art_number.group(1)
                        formatted_en = f'**Article {num}** {new_en}'
                    else:
                        formatted_en = new_en

                # 插入或替换英文翻译
                if en_start >= 0:
                    # 已有英文，替换
                    new_lines.append('')
                    new_lines.append(formatted_en)
                    updated += 1
                    # 跳过旧的英文内容
                    i = en_end
                else:
                    # 无英文，插入
                    new_lines.append('')
                    new_lines.append(formatted_en)
                    updated += 1
            else:
                # 没有新翻译，保留原有内容
                while en_start >= 0 and i < en_end:
                    new_lines.append(lines[i])
                    i += 1
        else:
            # 非条文行，直接添加
            new_lines.append(line)
            i += 1

    # 写回文件
    if not dry_run and updated > 0:
        md_path.write_text('\n'.join(new_lines), encoding='utf-8')

    return total_articles, updated


def main():
    parser = argparse.ArgumentParser(description='更新 Markdown 文件中的英文翻译')
    parser.add_argument('--dry-run', action='store_true', help='预览，不写入文件')
    parser.add_argument('--filter', type=str, default='', help='只处理标题含此关键词的法律')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    args = parser.parse_args()

    import sqlite3
    conn = sqlite3.connect(DB_PATH)

    query = "SELECT filename, category, title, legal_domain FROM laws WHERE is_current=1"
    if args.filter:
        query += f" AND title LIKE '%{args.filter}%'"

    rows = conn.execute(query).fetchall()
    conn.close()

    print(f"找到 {len(rows)} 部法律\n")

    total_laws = 0
    total_articles = 0
    total_updated = 0
    not_found = []

    for filename, category, title, legal_domain in rows:
        # 加载英文翻译
        en_articles = load_en_articles(filename, category)
        if not en_articles:
            continue

        # 查找 Markdown 文件
        md_path = find_md_file(title, legal_domain)
        if not md_path:
            not_found.append(title)
            continue

        # 更新英文翻译
        articles, updated = update_en_in_md(md_path, en_articles, args.dry_run)

        if updated > 0:
            total_laws += 1
            total_articles += articles
            total_updated += updated

            status = "[DRY-RUN] " if args.dry_run else ""
            print(f"{status}{title}: {updated}/{articles} 条已更新")

            if args.verbose:
                print(f"  → {md_path}")

    print(f"\n总计：")
    print(f"  处理法律：{total_laws} 部")
    print(f"  条文总数：{total_articles} 条")
    print(f"  已更新：{total_updated} 条")

    if not_found:
        print(f"\n未找到 Markdown 文件的法律（{len(not_found)} 部）：")
        for title in not_found[:10]:
            print(f"  - {title}")
        if len(not_found) > 10:
            print(f"  ... 还有 {len(not_found) - 10} 部")

    if args.dry_run:
        print(f"\n⚠️  这是预览模式，未写入文件")
        print(f"   移除 --dry-run 参数以应用更新")


if __name__ == "__main__":
    main()
