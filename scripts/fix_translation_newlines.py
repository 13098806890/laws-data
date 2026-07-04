#!/usr/bin/env python3
"""
修复已有英文翻译的换行符问题

策略：
1. 读取中文原文的段落数（按 \\n 分割）
2. 读取英文翻译（单段）
3. 通过句号（.）分割英文，尝试与中文段落对齐
4. 如果数量匹配，按中文段落结构插入换行符

用法：
  python3 scripts/fix_translation_newlines.py                    # 修复所有
  python3 scripts/fix_translation_newlines.py --dry-run          # 预览
  python3 scripts/fix_translation_newlines.py --filter 民法典     # 只修复指定法律
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import JSON_DIR, DB_PATH

JSON_EN_DIR = JSON_DIR.parent / 'json_en'


def chinese_number_to_int(cn_num: str) -> int:
    """将中文数字转换为阿拉伯数字"""
    if cn_num.isdigit():
        return int(cn_num)

    # 中文数字映射
    cn_map = {
        '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
        '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
        '十': 10, '百': 100, '千': 1000,
    }

    # 简单规则：
    # 十四 → 14
    # 三十四 → 34
    # 一百零一 → 101
    # 三百五十 → 350

    total = 0
    current = 0

    for char in cn_num:
        if char not in cn_map:
            return 0

        val = cn_map[char]

        if val >= 10:  # 十、百、千
            if current == 0:
                current = 1  # "十四" 的 "十" 前面隐含 1
            total += current * val
            current = 0
        else:
            current = val

    total += current
    return total


def get_zh_paragraphs(law_id: int, article_num: str) -> list[str]:
    """从数据库获取中文条文的段落列表"""
    conn = sqlite3.connect(DB_PATH)

    # 提取数字条号
    match = re.search(r'第([一二三四五六七八九十百千零\d]+)条', article_num)
    if not match:
        conn.close()
        return []

    # 转换为阿拉伯数字
    cn_num = match.group(1)
    num = chinese_number_to_int(cn_num)

    if num == 0:
        conn.close()
        return []

    result = conn.execute(
        'SELECT content FROM nodes WHERE law_id = ? AND article_num = ?',
        (law_id, num)
    ).fetchone()

    conn.close()

    if not result or not result[0]:
        return []

    # 移除条文标题（第X条）
    content = result[0]
    content = re.sub(r'^第[一二三四五六七八九十百千零\d]+条[　\s]*', '', content)

    return [p.strip() for p in content.split('\n') if p.strip()]


def split_english_into_paragraphs(en_text: str, target_count: int):
    """
    尝试将英文文本分割成指定数量的段落

    策略：
    1. 先尝试按句号（. ）分割
    2. 如果数量匹配，返回结果
    3. 如果不匹配，尝试合并短句或其他启发式方法
    """
    # 移除 Article X 前缀
    en_text = re.sub(r'^Article \d+\s*', '', en_text).strip()

    # 策略1：按句号分割（保留句号）
    # 使用正则：句号后跟空格，且后面是大写字母
    parts = re.split(r'\.(\s+)(?=[A-Z])', en_text)

    # 重组句子（保留句号和空格）
    sentences = []
    i = 0
    while i < len(parts):
        if i + 2 < len(parts):
            # parts[i] 是句子主体，parts[i+1] 是空格，parts[i+2] 是下一句开头
            sentences.append(parts[i] + '.')
            i += 2
        else:
            # 最后一个句子
            sentences.append(parts[i])
            i += 1

    sentences = [s.strip() for s in sentences if s.strip()]

    # 如果数量完全匹配
    if len(sentences) == target_count:
        return sentences

    # 策略2：如果句子数比目标多，尝试合并短句
    if len(sentences) > target_count:
        # 找出短句（长度 < 50 字符），与前一句合并
        merged = []
        i = 0
        while i < len(sentences):
            if i + 1 < len(sentences) and len(sentences[i]) < 50:
                # 短句，与下一句合并
                merged.append(sentences[i] + ' ' + sentences[i + 1])
                i += 2
            else:
                merged.append(sentences[i])
                i += 1

        if len(merged) == target_count:
            return merged

    # 策略3：如果句子数比目标少，可能某个句子包含多个段落
    # 尝试在特定关键词处分割（Where, If, When 等）
    if len(sentences) < target_count and len(sentences) > 0:
        # 暂不实现，先返回 None
        pass

    # 无法匹配
    return None


def fix_article_newlines(law_id: int, article: dict) -> dict:
    """
    修复单个条文的换行符
    返回修改后的 article dict，如果无需修改则返回 None
    """
    art_num = article.get('article_number', '')
    en_text = article.get('content_en', '').strip()

    if not en_text or '\n' in en_text:
        # 已经有换行符，跳过
        return None

    # 获取中文段落
    zh_paras = get_zh_paragraphs(law_id, art_num)
    if not zh_paras or len(zh_paras) == 1:
        # 中文本身就是单段，无需修复
        return None

    # 尝试分割英文
    en_paras = split_english_into_paragraphs(en_text, len(zh_paras))

    if not en_paras:
        # 无法分割，跳过
        return None

    # 检查是否需要添加 Article X 前缀
    match = re.match(r'^Article \d+', article['content_en'])
    if match:
        prefix = match.group(0)
        fixed_text = prefix + ' ' + '\n'.join(en_paras)
    else:
        fixed_text = '\n'.join(en_paras)

    # 返回修改后的 article
    fixed_article = article.copy()
    fixed_article['content_en'] = fixed_text
    return fixed_article


def fix_law_file(json_en_path: Path, dry_run: bool = False) -> tuple[int, int, int]:
    """
    修复一个法律文件的换行符
    返回 (总条文数, 修复数, 跳过数)
    """
    if not json_en_path.exists():
        return 0, 0, 0

    try:
        data = json.loads(json_en_path.read_text(encoding='utf-8'))
    except:
        return 0, 0, 0

    law_id = data.get('law_id')
    if not law_id:
        return 0, 0, 0

    articles = data.get('articles', [])
    if not articles:
        return 0, 0, 0

    total = 0
    fixed = 0
    skipped = 0

    for i, art in enumerate(articles):
        if not art.get('content_en', '').strip():
            continue

        total += 1
        fixed_art = fix_article_newlines(law_id, art)

        if fixed_art:
            articles[i] = fixed_art
            fixed += 1
        else:
            skipped += 1

    # 写回文件
    if not dry_run and fixed > 0:
        json_en_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8'
        )

    return total, fixed, skipped


def main():
    parser = argparse.ArgumentParser(description='修复已有英文翻译的换行符')
    parser.add_argument('--dry-run', action='store_true', help='预览，不写入文件')
    parser.add_argument('--filter', type=str, default='', help='只处理标题含此关键词的法律')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    query = "SELECT id, filename, category, title FROM laws WHERE is_current=1"
    if args.filter:
        query += f" AND title LIKE '%{args.filter}%'"

    rows = conn.execute(query).fetchall()
    conn.close()

    print(f"找到 {len(rows)} 部法律\n")

    total_laws = 0
    total_articles = 0
    total_fixed = 0
    total_skipped = 0

    for law_id, filename, category, title in rows:
        json_en_path = JSON_EN_DIR / category / f'{filename}.json'

        if not json_en_path.exists():
            continue

        articles, fixed, skipped = fix_law_file(json_en_path, args.dry_run)

        if articles > 0:
            total_laws += 1
            total_articles += articles
            total_fixed += fixed
            total_skipped += skipped

            if fixed > 0:
                status = "[DRY-RUN] " if args.dry_run else ""
                print(f"{status}{title}: {fixed}/{articles} 条已修复，{skipped} 条跳过")

                if args.verbose:
                    print(f"  → {json_en_path}")

    print(f"\n总计：")
    print(f"  处理法律：{total_laws} 部")
    print(f"  条文总数：{total_articles} 条")
    print(f"  已修复：{total_fixed} 条")
    print(f"  已跳过：{total_skipped} 条（单段或已有换行）")

    if args.dry_run:
        print(f"\n⚠️  这是预览模式，未写入文件")
        print(f"   移除 --dry-run 参数以应用修复")


if __name__ == "__main__":
    main()
