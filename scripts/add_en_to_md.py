#!/usr/bin/env python3
"""
将 json_en/ 中的英文翻译插入到现有 Markdown 文件中。

格式：
  <a id="art-1"></a>第一条　中文内容...

  **Article 1** English content...

用法：
  python3 scripts/add_en_to_md.py                    # 处理所有已翻译的法律
  python3 scripts/add_en_to_md.py --dry-run          # 预览，不写入
  python3 scripts/add_en_to_md.py --filter 民法典    # 只处理包含关键词的法律
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


def find_md_file(title: str, legal_domain: str) -> Path:
    """查找法律对应的 Markdown 文件"""
    # 标题去掉日期和版本号
    clean_title = re.sub(r'（\d{4}.*?）$', '', title).strip()

    # 搜索路径列表（按优先级）
    search_dirs = []

    # legal_domain 映射到目录名
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

    for dir_pattern in domain_map.get(legal_domain, []):
        search_dirs.append(MD_BASE_DIR / dir_pattern)

    # 全局搜索（最后兜底）
    search_dirs.append(MD_BASE_DIR)

    # 在每个目录中搜索
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        # 精确匹配
        for md_path in search_dir.rglob('*.md'):
            if md_path.stem == clean_title or md_path.stem == title:
                return md_path

    return None


def insert_en_to_md(md_path: Path, en_articles: dict, dry_run: bool = False) -> tuple[int, int]:
    """
    在 Markdown 文件中插入英文翻译。
    返回 (处理的条文数, 插入的英文条数)
    """
    if not md_path.exists():
        return 0, 0

    content = md_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    new_lines = []
    inserted = 0
    total_articles = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)

        # 匹配条文行：<a id="art-X"></a>第X条　...
        art_match = re.match(r'<a id="art-\d+"></a>(第[一二三四五六七八九十百千\d]+条)(?:　|\s)+(.*)', line)

        if art_match:
            art_num = art_match.group(1)
            total_articles += 1

            # 检查是否已有英文翻译（下一行或下几行包含 **Article**）
            has_en = False
            for j in range(i + 1, min(i + 5, len(lines))):
                if '**Article' in lines[j]:
                    has_en = True
                    break
                if lines[j].strip() and not lines[j].strip().startswith('**'):
                    break

            if not has_en and art_num in en_articles:
                # 插入空行和英文翻译
                new_lines.append('')

                # 提取 Article 编号（如 "Article 1"）
                en_content = en_articles[art_num]
                art_en_match = re.match(r'(Article \d+)', en_content)
                if art_en_match:
                    art_en_label = art_en_match.group(1)
                    en_content_body = en_content[len(art_en_label):].strip()

                    # 处理多段落情况：将换行符转换为 Markdown 换行（两个空格 + \n）
                    if '\n' in en_content_body:
                        # 将换行符替换为 Markdown 的硬换行（两个空格 + 换行）
                        en_content_body = en_content_body.replace('\n', '  \n')

                    new_lines.append(f'**{art_en_label}** {en_content_body}')
                else:
                    # 没有 Article X 前缀，提取条文编号
                    art_number = re.search(r'第(\d+)条', art_num)
                    if art_number:
                        num = art_number.group(1)
                        # 处理多段落情况
                        if '\n' in en_content:
                            en_content = en_content.replace('\n', '  \n')
                        new_lines.append(f'**Article {num}** {en_content}')
                    else:
                        # 处理多段落情况
                        if '\n' in en_content:
                            en_content = en_content.replace('\n', '  \n')
                        new_lines.append(f'{en_content}')

                inserted += 1

        i += 1

    if not dry_run and inserted > 0:
        md_path.write_text('\n'.join(new_lines), encoding='utf-8')

    return total_articles, inserted


def main():
    parser = argparse.ArgumentParser(description='将英文翻译插入到 Markdown 文件')
    parser.add_argument('--dry-run', action='store_true', help='预览，不写入文件')
    parser.add_argument('--filter', type=str, default='', help='只处理标题含此关键词的法律')
    args = parser.parse_args()

    import sqlite3
    conn = sqlite3.connect(DB_PATH)

    # 查询所有需要处理的法律
    query = "SELECT filename, category, title, legal_domain FROM laws WHERE is_current=1"
    if args.filter:
        query += f" AND title LIKE '%{args.filter}%'"

    rows = conn.execute(query).fetchall()
    conn.close()

    print(f"找到 {len(rows)} 部法律")

    total_laws = 0
    total_articles = 0
    total_inserted = 0
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

        # 插入英文翻译
        articles, inserted = insert_en_to_md(md_path, en_articles, args.dry_run)

        if inserted > 0:
            total_laws += 1
            total_articles += articles
            total_inserted += inserted

            status = "[DRY-RUN] " if args.dry_run else ""
            print(f"{status}{title}: {inserted}/{articles} 条已插入英文")
            if not args.dry_run:
                print(f"  → {md_path}")

    print(f"\n总计：")
    print(f"  处理法律：{total_laws} 部")
    print(f"  条文总数：{total_articles} 条")
    print(f"  插入英文：{total_inserted} 条")

    if not_found:
        print(f"\n未找到 Markdown 文件的法律（{len(not_found)} 部）：")
        for title in not_found[:10]:
            print(f"  - {title}")
        if len(not_found) > 10:
            print(f"  ... 还有 {len(not_found) - 10} 部")


if __name__ == "__main__":
    main()
