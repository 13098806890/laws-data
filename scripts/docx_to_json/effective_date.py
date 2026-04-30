import re

CN_NUM = {'〇':'0','○':'0','零':'0','一':'1','二':'2','三':'3','四':'4',
          '五':'5','六':'6','七':'7','八':'8','九':'9'}

PATTERN_ARABIC    = re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日起施行')
PATTERN_SINCE_PUB = re.compile(
    r'((?:\d{4}年\d{1,2}月\d{1,2}日[^。；]*?)*\d{4}年(?:\d{1,2})月(?:\d{1,2})日[^。；\n]*?)'
    r'自(?:发布|公布|批准|颁布)之日起施行'
)
PATTERN_DATE      = re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日')
PATTERN_CN        = re.compile(
    r'([一二三四五六七八九〇○零]{4})年'
    r'([一二三四五六七八九十]{1,3})月'
    r'([一二三四五六七八九十]{1,3})日.*?施行'
)


def _cn_num_to_int(s: str) -> int:
    if len(s) == 4:
        return int(''.join(CN_NUM.get(c, c) for c in s))
    if s == '十': return 10
    if s.startswith('十'): return 10 + int(CN_NUM.get(s[1], s[1]))
    if s.endswith('十'): return int(CN_NUM.get(s[0], s[0])) * 10
    return int(CN_NUM.get(s, s))


def extract_effective_date(data: dict) -> str | None:
    texts = [data.get('promulgation_info', '')]
    for ch in data.get('chapters', []):
        for art in ch.get('articles', []):
            texts.append(art.get('content', ''))
        for sec in ch.get('sections', []):
            for art in sec.get('articles', []):
                texts.append(art.get('content', ''))

    for text in texts:
        m = PATTERN_ARABIC.search(text)
        if m:
            return f'{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}'

    for text in texts:
        m = PATTERN_CN.search(text)
        if m:
            try:
                y  = _cn_num_to_int(m.group(1))
                mo = _cn_num_to_int(m.group(2))
                d  = _cn_num_to_int(m.group(3))
                return f'{y}-{str(mo).zfill(2)}-{str(d).zfill(2)}'
            except Exception:
                pass

    for text in texts:
        m = PATTERN_SINCE_PUB.search(text)
        if m:
            dates = PATTERN_DATE.findall(m.group(1))
            if dates:
                y, mo, d = dates[-1]
                return f'{y}-{mo.zfill(2)}-{d.zfill(2)}'

    for text in texts:
        if '自公布之日起施行' in text and data.get('pub_date'):
            return data['pub_date']

    return None
