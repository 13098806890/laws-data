"""
为所有 JSON 文件补充结构信息：
1. 所有文件：给 chapters / sections / articles 加 order_index 和 global_order
2. 有"编"的8个文件：在顶层加 parts 字段，每个 part 内嵌 chapters（含 sections/articles）
   顶层 chapters 字段保留但清空（兼容性），或直接移除
"""

import json
import glob
import re

CN_ORD = {
    '零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,
    '百':100,'千':1000,
}

def cn_to_int(s):
    s = s.strip()
    result = 0
    tmp = 0
    for c in s:
        v = CN_ORD.get(c, 0)
        if v >= 10:
            if tmp == 0:
                tmp = 1
            result += tmp * v
            tmp = 0
        else:
            tmp = v
    return result + tmp

def title_to_order(title):
    m = re.match(r'^第([一二三四五六七八九十百千零]+)[编章节条]', title.strip())
    if m:
        return cn_to_int(m.group(1))
    return 0

def extract_parts_from_fulltext(full_text):
    """
    从 full_text 按行顺序提取编-章结构，返回：
    [{'title': str|None, 'order_index': int, 'chapter_titles': [str, ...]}, ...]
    """
    lines = [l.strip() for l in full_text.split('\n')]
    parts = []
    current_part = None

    for line in lines:
        if re.match(r'^第[一二三四五六七八九十]+编[　\s]', line):
            if current_part is not None:
                parts.append(current_part)
            order = title_to_order(line)
            current_part = {'title': line, 'order_index': order, 'chapter_titles': []}
        elif re.match(r'^第[一二三四五六七八九十百]+章[　\s]', line):
            if current_part is None:
                current_part = {'title': None, 'order_index': 1, 'chapter_titles': []}
            current_part['chapter_titles'].append(line)

    if current_part is not None:
        parts.append(current_part)

    return parts


def process_file(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    full_text = data.get('full_text', '')
    # If chapters were already nested inside parts from a previous run, flatten them back
    chapters = data.get('chapters', [])
    if not chapters and 'parts' in data:
        for part in data['parts']:
            chapters.extend(part.get('chapters', []))

    has_parts = bool(re.search(r'^第[一二三四五六七八九十]+编[　\s]', full_text, re.MULTILINE))

    global_counter = [0]

    def next_global():
        global_counter[0] += 1
        return global_counter[0]

    def process_article(article, ai):
        article['order_index'] = ai + 1
        article['global_order'] = next_global()

    def process_section(section, si):
        section['order_index'] = si + 1
        section['global_order'] = next_global()
        for ai, article in enumerate(section.get('articles', [])):
            process_article(article, ai)

    def process_chapter(chapter, ci):
        chapter['order_index'] = ci + 1
        chapter['global_order'] = next_global()
        for si, section in enumerate(chapter.get('sections', [])):
            process_section(section, si)
        for ai, article in enumerate(chapter.get('articles', [])):
            process_article(article, ai)

    if has_parts:
        raw_parts = extract_parts_from_fulltext(full_text)

        # Build chapter_part_seq: sequential list of part indices for each chapter appearance
        chapter_part_seq = []
        for pi, part in enumerate(raw_parts):
            for _ in part['chapter_titles']:
                chapter_part_seq.append(pi)

        # Group chapters by part index first, preserving order
        part_chapters = [[] for _ in raw_parts]
        ch_seq_idx = 0
        for chapter in chapters:
            if ch_seq_idx < len(chapter_part_seq):
                part_idx = chapter_part_seq[ch_seq_idx]
                ch_seq_idx += 1
            else:
                part_idx = len(raw_parts) - 1
            chapter.pop('part_index', None)
            part_chapters[part_idx].append(chapter)

        # Build parts_list with depth-first global_order: 编 → 章 → 节/条
        parts_list = []
        for pi, raw_part in enumerate(raw_parts):
            title = raw_part['title']
            if title is None and raw_part['order_index'] == 1:
                title = '第一编　总则'
            part_entry = {
                'title': title,
                'order_index': raw_part['order_index'],
                'global_order': next_global(),
                'chapters': [],
            }
            for ci, chapter in enumerate(part_chapters[pi]):
                process_chapter(chapter, ci)
                part_entry['chapters'].append(chapter)
            parts_list.append(part_entry)

        # Build new data: drop chapters/parts, insert new parts at the right position
        # Determine insertion position: after total_articles, or before full_text
        new_data = {}
        parts_inserted = False
        for k, v in data.items():
            if k in ('chapters', 'parts'):
                if not parts_inserted:
                    new_data['parts'] = parts_list
                    parts_inserted = True
                # skip old value
            else:
                new_data[k] = v
        if not parts_inserted:
            # Neither key existed (shouldn't happen), append at end before full_text
            result = {}
            for k, v in new_data.items():
                if k == 'full_text':
                    result['parts'] = parts_list
                result[k] = v
            new_data = result

    else:
        # No parts: just add order_index / global_order to chapters/sections/articles
        for ci, chapter in enumerate(chapters):
            process_chapter(chapter, ci)
        new_data = data
        # Remove stale parts field if present
        new_data.pop('parts', None)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    return has_parts


def main():
    paths = [p for p in glob.glob('/Users/doxie/laws_data/json/**/*.json', recursive=True)
             if 'index' not in p]

    with_parts = without_parts = 0
    for path in paths:
        has_parts = process_file(path)
        if has_parts:
            with_parts += 1
        else:
            without_parts += 1

    print(f'处理完成: 共 {len(paths)} 个文件')
    print(f'  含"编"结构（parts 嵌套 chapters）: {with_parts}')
    print(f'  无"编"结构: {without_parts}')


if __name__ == '__main__':
    main()
