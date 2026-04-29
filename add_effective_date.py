import json
import glob
import re
from pathlib import Path

# 阿拉伯数字格式：YYYY年M月D日起施行
PATTERN_ARABIC = re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日起施行')

# "自发布/公布/批准/颁布之日起施行"：找到该短语，然后在其前面取最后一个日期
# 例1：1986年1月23日国务院发布　自发布之日起施行  → 1986-01-23
# 例2：1995年11月2日...通过　1995年11月22日...发布　自发布之日起施行 → 1995-11-22（取最后一个）
PATTERN_SINCE_PUBLISH = re.compile(
    r'((?:\d{4}年\d{1,2}月\d{1,2}日[^。；]*?)*\d{4}年(\d{1,2})月(\d{1,2})日[^。；\n]*?)'
    r'自(?:发布|公布|批准|颁布)之日起施行'
)
# 用于从前缀串里提取所有日期，取最后一个
PATTERN_DATE = re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日')

# 中文数字格式：一九八四年一月一日起施行
CN_NUM = {'〇': '0', '○': '0', '零': '0',
          '一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
          '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'}

PATTERN_CN = re.compile(
    r'([一二三四五六七八九〇○零]{4})年'
    r'([一二三四五六七八九十]{1,3})月'
    r'([一二三四五六七八九十]{1,3})日.*?施行'
)


def cn_to_int(s):
    """将中文数字（年份/月/日）转为整数"""
    # 年份：四个汉字数字直接转
    if len(s) == 4:
        return int(''.join(CN_NUM.get(c, c) for c in s))
    # 月/日：十、十一、十二、一~九
    if s == '十':
        return 10
    if s.startswith('十'):
        return 10 + int(CN_NUM.get(s[1], s[1]))
    if s.endswith('十'):
        return int(CN_NUM.get(s[0], s[0])) * 10
    return int(CN_NUM.get(s, s))


def extract_effective_date(data):
    all_content = [data.get('promulgation_info', '')]
    for ch in data.get('chapters', []):
        for art in ch.get('articles', []):
            all_content.append(art.get('content', ''))

    # 1. 阿拉伯数字格式
    for text in all_content:
        m = PATTERN_ARABIC.search(text)
        if m:
            y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
            return f'{y}-{mo}-{d}'

    # 2. 中文数字格式
    for text in all_content:
        m = PATTERN_CN.search(text)
        if m:
            try:
                y = cn_to_int(m.group(1))
                mo = cn_to_int(m.group(2))
                d = cn_to_int(m.group(3))
                return f'{y}-{str(mo).zfill(2)}-{str(d).zfill(2)}'
            except Exception:
                pass

    # 3. 自发布/公布/批准/颁布之日起施行，取该短语前最后一个日期（发布日）
    for text in all_content:
        m = PATTERN_SINCE_PUBLISH.search(text)
        if m:
            # 从整个前缀串里取最后一个日期
            dates = PATTERN_DATE.findall(m.group(1))
            if dates:
                y, mo, d = dates[-1]
                return f'{y}-{mo.zfill(2)}-{d.zfill(2)}'

    # 4. 自公布之日起施行 → 用 pub_date
    for text in all_content:
        if '自公布之日起施行' in text:
            pub = data.get('pub_date', '')
            if pub:
                return pub

    return None


def process_all():
    paths = [p for p in glob.glob('/Users/doxie/laws_data/json/**/*.json', recursive=True)
             if 'index' not in p]

    updated = skipped = 0

    for path in paths:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        # 已有 effective_date 则跳过
        if 'effective_date' in data:
            skipped += 1
            continue

        date = extract_effective_date(data)
        if date:
            # 插入在 pub_date 之后
            new_data = {}
            for k, v in data.items():
                new_data[k] = v
                if k == 'pub_date':
                    new_data['effective_date'] = date
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
            updated += 1

    not_found = len(paths) - updated - skipped
    print(f'总文件: {len(paths)}')
    print(f'成功写入 effective_date: {updated}')
    print(f'已有 effective_date（跳过）: {skipped}')
    print(f'未能提取（无生效日期）: {not_found}')


if __name__ == '__main__':
    process_all()
