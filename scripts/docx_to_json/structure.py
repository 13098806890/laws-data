import re
from collections import defaultdict

CHAPTER_RE = re.compile(r'^第[一二三四五六七八九十百千]+章[　\s]')
SECTION_RE = re.compile(r'^第[一二三四五六七八九十百千]+节[　\s]')
PART_RE    = re.compile(r'^第[一二三四五六七八九十]+编[　\s]', re.MULTILINE)

CN_ORD = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,
          '九':9,'十':10,'百':100,'千':1000}


def _cn_to_int(s: str) -> int:
    s = s.strip()
    result = tmp = 0
    for c in s:
        v = CN_ORD.get(c, 0)
        if v >= 10:
            result += (tmp or 1) * v
            tmp = 0
        else:
            tmp = v
    return result + tmp


def normalize_title(t: str) -> str:
    t = t.strip()
    # 去除换行和由排版换行引入的多余空格
    t = re.sub(r'[\r\n]+', '', t)
    t = re.sub(r'[ \t]{2,}', ' ', t)
    # 去除两个 CJK 字符之间的多余全角空格
    return re.sub(r'(?<=[一-鿿])　{2,}(?=[一-鿿])', '', t)


def add_structure(data: dict) -> dict:
    full_text = data.get('full_text', '')
    chapters  = data.get('chapters', [])
    has_parts = bool(PART_RE.search(full_text))

    counter = [0]
    def nxt():
        counter[0] += 1
        return counter[0]

    def proc_article(art, idx):
        art['order_index']  = idx + 1
        art['global_order'] = nxt()

    def proc_section(sec, idx):
        sec['order_index']  = idx + 1
        sec['global_order'] = nxt()
        for i, a in enumerate(sec.get('articles', [])):
            proc_article(a, i)

    def proc_chapter(ch, idx):
        ch['order_index']  = idx + 1
        ch['global_order'] = nxt()
        for i, s in enumerate(ch.get('sections', [])):
            proc_section(s, i)
        for i, a in enumerate(ch.get('articles', [])):
            proc_article(a, i)

    if not has_parts:
        for i, ch in enumerate(chapters):
            proc_chapter(ch, i)
        data.pop('parts', None)
        return data

    raw_parts = []
    current = None
    for line in (l.strip() for l in full_text.split('\n')):
        if PART_RE.match(line):
            if current: raw_parts.append(current)
            m = re.match(r'^第([一二三四五六七八九十百千零]+)编', line)
            order = _cn_to_int(m.group(1)) if m else len(raw_parts) + 1
            current = {'title': normalize_title(line), 'order_index': order, 'ch_titles': []}
        elif CHAPTER_RE.match(line):
            if current is None:
                current = {'title': None, 'order_index': 1, 'ch_titles': []}
            current['ch_titles'].append(line)
    if current: raw_parts.append(current)

    seq = []
    for pi, rp in enumerate(raw_parts):
        for _ in rp['ch_titles']:
            seq.append(pi)

    part_chapters = defaultdict(list)
    for i, ch in enumerate(chapters):
        pi = seq[i] if i < len(seq) else len(raw_parts) - 1
        part_chapters[pi].append(ch)

    parts_list = []
    for pi, rp in enumerate(raw_parts):
        title = rp['title']
        if title is None and rp['order_index'] == 1:
            title = '第一编　总则'
        part_entry = {
            'title': title,
            'order_index': rp['order_index'],
            'global_order': nxt(),
            'chapters': [],
        }
        for ci, ch in enumerate(part_chapters[pi]):
            proc_chapter(ch, ci)
            part_entry['chapters'].append(ch)
        parts_list.append(part_entry)

    new_data = {}
    replaced = False
    for k, v in data.items():
        if k in ('chapters', 'parts'):
            if not replaced:
                new_data['parts'] = parts_list
                replaced = True
        else:
            new_data[k] = v
    if not replaced:
        new_data['parts'] = parts_list
    return new_data
