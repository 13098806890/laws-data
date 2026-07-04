#!/usr/bin/env python3
"""
将 json_en/ 中的英文翻译插入到 Markdown 文件中（正确版本）

核心逻辑：
1. 从数据库读取中文条文（完整的，包含所有段落）
2. 从 json_en 读取英文翻译
3. 重新生成 Markdown（中文 + 英文），不是"更新"已有文件

用法：
  python3 scripts/add_en_to_md_v2.py                    # 处理所有
  python3 scripts/add_en_to_md_v2.py --dry-run          # 预览
  python3 scripts/add_en_to_md_v2.py --filter 民法典     # 只处理指定法律
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


def rebuild_md_with_en(md_path: Path, en_articles: dict, dry_run: bool = False) -> tuple[int, int]:
    """
    重建 Markdown 文件，确保中文完整 + 英文正确
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

        # 匹配条文行：<a id="art-X"></a>第X条　...
        art_match = re.match(r'<a id="art-\d+"></a>(第[一二三四五六七八九十百千零\d]+条)(?:　|\s)+(.*)', line)

        if art_match:
            art_num = art_match.group(1)
            total_articles += 1

            # 1. 添加条文的第一行（中文）
            new_lines.append(line)
            i += 1

            # 2. 收集中文的后续段落（直到遇到空行、英文翻译或下一个条文）
            zh_lines = []
            while i < len(lines):
                curr = lines[i]

                # 遇到空行，停止
                if not curr.strip():
                    break

                # 遇到英文翻译（**Article），跳过旧英文
                if curr.strip().startswith('**Article'):
                    # 跳过旧的英文翻译（到下一个空行或条文）
                    while i < len(lines):
                        if not lines[i].strip() or lines[i].strip().startswith('<a id="art-'):
                            break
                        i += 1
                    break

                # 遇到下一个条文，停止
                if curr.strip().startswith('<a id="art-'):
                    break

                # 否则，这是中文的后续段落
                zh_lines.append(curr)
                i += 1

            # 添加收集到的中文段落
            for zh_line in zh_lines:
                new_lines.append(zh_line)

            # 3. 添加空行
            new_lines.append('')

            # 4. 添加英文翻译（如果有）
            if art_num in en_articles:
                en_content = en_articles[art_num]

                # 处理换行符
                if '\n' in en_content:
                    en_content = en_content.replace('\n', '  \n')

                # 提取 Article X 前缀
                art_en_match = re.match(r'(Article \d+)', en_content)
                if art_en_match:
                    art_en_label = art_en_match.group(0)
                    en_body = en_content[len(art_en_label):].strip()
                    new_lines.append(f'**{art_en_label}** {en_body}')
                else:
                    # 没有 Article 前缀，提取条号
                    art_number = re.search(r'第(\d+)条', art_num)
                    if art_number:
                        num = art_number.group(1)
                        new_lines.append(f'**Article {num}** {en_content}')
                    else:
                        new_lines.append(en_content)

                inserted += 1
        else:
            # 非条文行，直接添加
            new_lines.append(line)
            i += 1

    # 写回文件
    if not dry_run and inserted >= 0:  # 即使 inserted=0 也写入，因为可能清理了旧英文
        md_path.write_text('\n'.join(new_lines), encoding='utf-8')

    return total_articles, inserted


def main():
    parser = argparse.ArgumentParser(description='将英文翻译插入到 Markdown 文件（正确版本）')
    parser.add_argument('--dry-run', action='store_true', help='预览，不写入文件')
    parser.add_argument('--filter', type=str, default='', help='只处理标题含此关键词的法律')
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

        # 重建 Markdown
        articles, inserted = rebuild_md_with_en(md_path, en_articles, args.dry_run)

        if articles > 0:
            total_laws += 1
            total_articles += articles
            total_inserted += inserted

            status = "[DRY-RUN] " if args.dry_run else ""
            if inserted > 0:
                print(f"{status}{title}: {inserted}/{articles} 条已插入英文")
            else:
                print(f"{status}{title}: {articles} 条（无新英文）")

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

    if args.dry_run:
        print(f"\n⚠️  这是预览模式，未写入文件")
        print(f"   移除 --dry-run 参数以应用修复")


if __name__ == "__main__":
    main()
