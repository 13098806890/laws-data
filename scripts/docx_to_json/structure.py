import re
from collections import defaultdict

CHAPTER_RE = re.compile(r'^第[一二三四五六七八九十百千]+章[　\s]')
SECTION_RE = re.compile(r'^第[一二三四五六七八九十百千]+节[　\s]')
PART_RE    = re.compile(r'^第[一二三四五六七八九十]+编[　\s]', re.MULTILINE)

CN_ORD = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,
          '九':9,'十':10,'百':100,'千':1000}


def cn_to_int(s: str) -> int:
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
        # 按照章内实际出现顺序（先直属条文、后节，或交错）分配 global_order。
        # 用 _src_order 标记：converter 先写直属条文再写节，但实际正文可能是先直属后节，
        # 也可能章内条文和节交错。统一策略：按 JSON 中的原始列表顺序——
        # articles 和 sections 都带 order_index，按 order_index 混合排序。
        items = []
        for s in ch.get('sections', []):
            items.append(('section', s))
        for a in ch.get('articles', []):
            items.append(('article', a))
        # 按各自的 order_index 排序，保证直属条文在节之前（如果确实在前）
        items.sort(key=lambda x: x[1].get('_seq') or 9999)
        sec_idx = 0
        art_idx = 0
        for kind, obj in items:
            if kind == 'section':
                proc_section(obj, sec_idx)
                sec_idx += 1
            else:
                proc_article(obj, art_idx)
                art_idx += 1

    def _chapter_has_articles(ch):
        if ch.get('articles'):
            return True
        return any(s.get('articles') for s in ch.get('sections', []))

    def _dedup_chapters(chs):
        """保留同名章的最后一次出现（正文在 TOC 之后，最后一次才是真实正文章）。"""
        seen = {}
        for i, ch in enumerate(chs):
            seen[normalize_title(ch['title'])] = i
        kept = set(seen.values())
        return [ch for i, ch in enumerate(chs) if i in kept]

    if not has_parts:
        deduped = _dedup_chapters(chapters)
        real_chs = [ch for ch in deduped if _chapter_has_articles(ch)]
        for i, ch in enumerate(real_chs):
            proc_chapter(ch, i)
        data['chapters'] = real_chs
        data.pop('parts', None)
        return data

    raw_parts = []
    current = None
    for line in (l.strip() for l in full_text.split('\n')):
        if PART_RE.match(line):
            if current: raw_parts.append(current)
            m = re.match(r'^第([一二三四五六七八九十百千零]+)编', line)
            order = cn_to_int(m.group(1)) if m else len(raw_parts) + 1
            current = {'title': normalize_title(line), 'order_index': order, 'ch_titles': []}
        elif CHAPTER_RE.match(line):
            if current is None:
                current = {'title': None, 'order_index': 1, 'ch_titles': []}
            current['ch_titles'].append(line)
    if current: raw_parts.append(current)

    # 如果同一 order_index 的编出现多次（说明 full_text 包含 TOC 残片+正文），
    # 只保留最后一次出现的各编——正文总在 TOC 之后。
    seen_orders = {}
    for pi, rp in enumerate(raw_parts):
        seen_orders[rp['order_index']] = pi
    kept_pis = set(seen_orders.values())
    # 重新映射 pi，过滤掉 TOC 残片
    kept_raw = [(pi, rp) for pi, rp in enumerate(raw_parts) if pi in kept_pis]

    seq = []
    for pi, rp in kept_raw:
        for _ in rp['ch_titles']:
            seq.append(pi)

    part_chapters = defaultdict(list)
    last_pi = kept_raw[-1][0] if kept_raw else 0

    # 分离「编下直属条文占位章」和普通章
    direct_chapters = [ch for ch in chapters if ch.get('_is_direct_part')]
    regular_chapters = [ch for ch in chapters if not ch.get('_is_direct_part') and _chapter_has_articles(ch)]

    # 普通章按 TOC 序列映射到编
    for i, ch in enumerate(regular_chapters):
        pi = seq[i] if i < len(seq) else last_pi
        part_chapters[pi].append(ch)

    # 直属章按编标题匹配（_DIRECT_{part_title}）
    part_title_to_pi = {normalize_title(rp['title'] or ''): pi for pi, rp in kept_raw if rp['title']}
    for ch in direct_chapters:
        part_title = ch['title'][len('_DIRECT_'):]
        pi = part_title_to_pi.get(part_title, last_pi)
        part_chapters[pi].insert(0, ch)  # 直属章排在该编普通章之前

    parts_list = []
    for pi, rp in kept_raw:
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
