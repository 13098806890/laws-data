#!/usr/bin/env python3
"""
完整 pipeline：源文件(docx) → JSON → law_content.db
用法：python3 pipeline.py
支持增量：只处理新增或更新的 docx 文件
"""

import json
import re
import glob
import sqlite3
import subprocess
from pathlib import Path
from collections import defaultdict

import docx
import xlrd

# ── 路径配置 ─────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent   # laws_data/
SRC_BASE    = BASE_DIR / 'sources'
SRC_DIRS    = {
    '法律':       SRC_BASE / '法律',
    '司法解释':   SRC_BASE / '司法解释',
    '行政法规':   SRC_BASE / '行政法规',
    '宪法':       SRC_BASE / '宪法',
    '监察法规':   SRC_BASE / '监察法规',
}
JSON_DIR    = BASE_DIR / 'json'
DB_PATH     = BASE_DIR / 'law_content.db'
LAWS_REPO   = Path('/Users/doxie/Github/Laws')

# ── 正则 ──────────────────────────────────────────────────────────────────────
CHAPTER_RE  = re.compile(r'^第[一二三四五六七八九十百千]+章[　\s]')
SECTION_RE  = re.compile(r'^第[一二三四五六七八九十百千]+节[　\s]')
ARTICLE_RE  = re.compile(r'^第[一二三四五六七八九十百千]+条[　\s]')
PART_RE     = re.compile(r'^第[一二三四五六七八九十]+编[　\s]', re.MULTILINE)
TOC_RE      = re.compile(r'^(?:目\s*录|附\s*录|附\s*件)$')

PATTERN_ARABIC       = re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日起施行')
PATTERN_SINCE_PUB    = re.compile(
    r'((?:\d{4}年\d{1,2}月\d{1,2}日[^。；]*?)*\d{4}年(?:\d{1,2})月(?:\d{1,2})日[^。；\n]*?)'
    r'自(?:发布|公布|批准|颁布)之日起施行'
)
PATTERN_DATE         = re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日')
CN_NUM = {'〇':'0','○':'0','零':'0','一':'1','二':'2','三':'3','四':'4',
          '五':'5','六':'6','七':'7','八':'8','九':'9'}
PATTERN_CN = re.compile(
    r'([一二三四五六七八九〇○零]{4})年'
    r'([一二三四五六七八九十]{1,3})月'
    r'([一二三四五六七八九十]{1,3})日.*?施行'
)

CN_ORD = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,
          '九':9,'十':10,'百':100,'千':1000}


# ══════════════════════════════════════════════════════════════════════════════
# 1. docx → JSON（含 title/章节/条文/full_text）
# ══════════════════════════════════════════════════════════════════════════════

def cn_to_int(s):
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


def title_from_stem(stem: str) -> str:
    raw = re.sub(r'_\d{8}$', '', stem)
    # normalize whitespace (+ was used as space substitute in some filenames)
    return re.sub(r'[ \t]+', ' ', raw).strip()


def pub_date_from_stem(stem: str) -> str | None:
    m = re.search(r'_(\d{8})$', stem)
    if m:
        d = m.group(1)
        return f'{d[:4]}-{d[4:6]}-{d[6:]}'
    return None


def normalize_title(t: str) -> str:
    """去掉标题里用于对齐的全角空格，如'第一章　物　　权' → '第一章　物权'"""
    t = t.strip()
    # Remove 2+ consecutive full-width spaces between CJK characters (typographic padding)
    return re.sub(r'(?<=[一-鿿])　{2,}(?=[一-鿿])', '', t)


def extract_content(doc_path: Path) -> dict:
    if doc_path.suffix.lower() == '.doc':
        result = subprocess.run(
            ['textutil', '-convert', 'txt', '-stdout', str(doc_path)],
            capture_output=True, text=True, timeout=30
        )
        paras = [l.strip() for l in result.stdout.splitlines() if l.strip()]
    else:
        doc = docx.Document(str(doc_path))
        paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    # 跳过第一段（标题已从文件名取），找 promulgation_info
    promulgation_info = ''
    start_idx = 0
    for i, text in enumerate(paras[:5]):
        if re.search(r'通过|公布|发布|施行|颁布|批准', text):
            promulgation_info = text
            start_idx = i + 1
            break

    chapters = []
    full_text_lines = []
    current_chapter = current_section = None
    in_toc = False
    pending = []

    for text in paras[start_idx:]:
        # 目录检测
        if TOC_RE.match(text) or text in ('目　　录', '目  录', '目录'):
            in_toc = True
            continue

        if in_toc:
            if CHAPTER_RE.match(text) or SECTION_RE.match(text):
                pending.append(text)
            elif ARTICLE_RE.match(text):
                in_toc = False
                # 找最后一次出现第一章的起始位置，去掉目录重复
                last_ch1 = next((j for j, s in enumerate(pending) if CHAPTER_RE.match(s)), -1)
                if last_ch1 >= 0:
                    pending = pending[last_ch1:]
                for s in pending:
                    full_text_lines.append(s)
                    if CHAPTER_RE.match(s):
                        current_chapter = {'title': normalize_title(s), 'sections': [], 'articles': []}
                        chapters.append(current_chapter)
                        current_section = None
                    elif SECTION_RE.match(s):
                        current_section = {'title': normalize_title(s), 'articles': []}
                        if current_chapter:
                            current_chapter['sections'].append(current_section)
                pending = []
            else:
                pending = []
            if in_toc:
                continue

        full_text_lines.append(text)

        if CHAPTER_RE.match(text):
            current_chapter = {'title': normalize_title(text), 'sections': [], 'articles': []}
            chapters.append(current_chapter)
            current_section = None
        elif SECTION_RE.match(text):
            current_section = {'title': normalize_title(text), 'articles': []}
            if current_chapter:
                current_chapter['sections'].append(current_section)
        elif ARTICLE_RE.match(text):
            art_title = text[:text.index('　') + 1] if '　' in text else text[:6]
            article = {'title': art_title, 'content': text}
            target = current_section or current_chapter
            if target:
                target['articles'].append(article)
            else:
                if not chapters:
                    chapters.append({'title': '正文', 'sections': [], 'articles': []})
                chapters[-1]['articles'].append(article)

    total = sum(
        len(ch.get('articles', [])) +
        sum(len(s.get('articles', [])) for s in ch.get('sections', []))
        for ch in chapters
    )
    return {
        'promulgation_info': promulgation_info,
        'full_text': '\n'.join(full_text_lines),
        'chapters': chapters,
        'total_articles': total,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. 提取生效日期
# ══════════════════════════════════════════════════════════════════════════════

def cn_num_to_int(s):
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
                y = cn_num_to_int(m.group(1))
                mo = cn_num_to_int(m.group(2))
                d = cn_num_to_int(m.group(3))
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
        if '自公布之日起施行' in text:
            pub = data.get('pub_date', '')
            if pub:
                return pub

    return None


# ══════════════════════════════════════════════════════════════════════════════
# 3. 从 xlsx 建立 effective_date / category 权威索引
# ══════════════════════════════════════════════════════════════════════════════

def build_xlsx_index() -> dict:
    index = {}
    for path in glob.glob(str(SRC_BASE / '**/*.xlsx'), recursive=True):
        try:
            wb = xlrd.open_workbook(path)
        except Exception:
            continue
        for sheet in wb.sheets():
            for i in range(1, sheet.nrows):
                row = sheet.row_values(i)
                title = str(row[0]).strip()
                pub   = str(row[1]).strip()
                eff   = str(row[2]).strip()
                cat   = str(row[3]).strip()
                key   = f'{title}_{pub.replace("-", "")}'
                if key not in index:
                    index[key] = {'effective_date': eff, 'category': cat}
    return index


# ══════════════════════════════════════════════════════════════════════════════
# 4. legal_domain 映射
# ══════════════════════════════════════════════════════════════════════════════

DEPT_DIRS = ['宪法','宪法相关法','民法商法','民法典','行政法','经济法','社会法','刑法','诉讼与非诉讼程序法']

MANUAL_DOMAINS = {
    '中华人民共和国民法典': '民法典',
    '全国人民代表大会常务委员会关于《中华人民共和国刑事诉讼法》第二百九十二条的解释': '宪法相关法',
    '全国人民代表大会常务委员会关于《中华人民共和国刑事诉讼法》第二百五十四条第五款、第二百五十七条第二款的解释': '宪法相关法',
    '全国人民代表大会常务委员会关于《中华人民共和国香港特别行政区基本法》第十三条第一款和第十九条的解释': '宪法相关法',
    '全国人民代表大会常务委员会关于在沿海港口城市设立海事法院的决定': '宪法相关法',
    '全国人民代表大会常务委员会关于中国人民解放军现役士兵衔级制度的决定': '宪法相关法',
    '全国人民代表大会常务委员会关于加强中央预算审查监督的决定': '经济法',
    '全国人民代表大会常务委员会关于惩治骗购外汇、逃汇和非法买卖外汇犯罪的决定': '经济法',
    '第五届全国人民代表大会常务委员会关于批准《国务院关于职工探亲待遇的规定》的决议': '社会法',
    '第五届全国人民代表大会常务委员会关于批准《国务院关于安置老弱病残干部的暂行办法》的决议': '社会法',
    '第五届全国人民代表大会常务委员会关于批准《国务院关于老干部离职休养的暂行规定》的决议': '社会法',
    '第五届全国人民代表大会常务委员会关于批准《国务院关于工人退休、退职的暂行办法》的决议': '社会法',
    '第五届全国人民代表大会常务委员会关于批准广东省经济特区条例的决议': '经济法',
    '中华人民共和国突发公共卫生事件应对法': '社会法',
    '中华人民共和国国家发展规划法': '经济法',
    '中华人民共和国民营经济促进法': '经济法',
    '中华人民共和国法治宣传教育法': '宪法相关法',
    '中华人民共和国原子能法': '经济法',
    '中华人民共和国国家公园法': '社会法',
}

KEYWORD_RULES = [
    ('刑法',              ['刑法','刑事','犯罪','罪名','量刑','追诉','减刑','假释','定罪','逮捕','起诉','盗窃','贪污','挪用','渎职','走私','毒品']),
    ('诉讼与非诉讼程序法',['诉讼','仲裁','调解','证据','执行','管辖','审判程序','司法鉴定','公证','法律援助','立案','侦查','批准逮捕','法律监督']),
    ('宪法相关法',        ['人民代表大会','选举','国家机构','立法','国防','军队','武装','国旗','国徽','国歌','监察','特别行政区','自治','外交','勋章']),
    ('民法商法',          ['民法','合同','物权','婚姻','继承','侵权','知识产权','专利','商标','著作权','公司','企业破产','票据','保险','信托','证券','海商','不动产登记','外商投资']),
    ('经济法',            ['税','财政','预算','审计','会计','金融','银行','价格','反垄断','反不正当竞争','统计','招标','政府采购','国有资产','对外贸易','海关','外汇','能源','矿产','农业','渔业','林业','交通','铁路','公路','港口','电力','煤炭','石油']),
    ('社会法',            ['劳动','工会','社会保险','教育','医疗','卫生','食品安全','药品','环境','生态','野生动物','文物','文化','体育','残疾人','妇女','未成年人','老年人','慈善','消防','安全生产','职业病','禁毒','传染病','疫苗']),
    ('行政法',            ['行政','公务员','警察','出入境','国家秘密','档案','网络安全','数据安全','个人信息','密码','广播','出版','土地管理','城乡规划','建设','房地产','道路交通','枪支','爆炸物','危险品','口岸']),
]


def build_domain_index() -> dict:
    idx = {}
    for dept in DEPT_DIRS:
        dept_path = LAWS_REPO / dept
        if not dept_path.is_dir():
            continue
        for fname in dept_path.iterdir():
            if not fname.suffix == '.md' or fname.name.startswith('_'):
                continue
            raw = re.sub(r'\(\d{4}-\d{2}-\d{2}\)', '', fname.stem).strip()
            for variant in [raw, raw.replace('中华人民共和国', '').strip()]:
                key = re.sub(r'\s+', '', variant)
                idx[key] = dept

    for title, dept in MANUAL_DOMAINS.items():
        for variant in [title, title.replace('中华人民共和国', '').strip()]:
            idx[re.sub(r'\s+', '', variant)] = dept

    return idx


def get_legal_domain(title: str, data: dict, domain_idx: dict) -> str | None:
    clean = lambda s: re.sub(r'\s+', '', s)
    for key in [clean(title), clean(title.replace('中华人民共和国', ''))]:
        if key in domain_idx:
            return domain_idx[key]

    combined = title + ' ' + data.get('promulgation_info', '')
    for dept, keywords in KEYWORD_RULES:
        if any(kw in combined for kw in keywords):
            return dept

    # 行政法规无法匹配关键词时，兜底归入行政法
    if data.get('category') == '行政法规':
        return '行政法'
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 5. 添加结构信息（order_index / global_order / parts 嵌套）
# ══════════════════════════════════════════════════════════════════════════════

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

    # 解析编结构
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

    # 按顺序把章分配到编
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

    # 重建 data，保持字段顺序，用 parts 替换 chapters
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


# ══════════════════════════════════════════════════════════════════════════════
# 6. 完整处理单个 docx → dict
# ══════════════════════════════════════════════════════════════════════════════

def process_docx(docx_path: Path, category: str,
                 xlsx_index: dict, domain_idx: dict) -> dict | None:
    try:
        content = extract_content(docx_path)
    except Exception as e:
        print(f'  ERROR extract {docx_path.name}: {e}')
        return None

    stem    = docx_path.stem
    title   = title_from_stem(stem)         # 从文件名取，不用 docx 里的截断标题
    pub_date = pub_date_from_stem(stem)

    data = {
        'title':             title,
        'category':          category,
        'pub_date':          pub_date,
        'effective_date':    None,
        'promulgation_info': content['promulgation_info'],
        'legal_domain':      None,
        'total_articles':    content['total_articles'],
        'chapters':          content['chapters'],
        'full_text':         content['full_text'],
    }

    # xlsx 覆盖 effective_date / category
    xlsx_key = f'{title}_{(pub_date or "").replace("-", "")}'
    if xlsx_key in xlsx_index:
        entry = xlsx_index[xlsx_key]
        if entry['effective_date']:
            data['effective_date'] = entry['effective_date']
        if entry['category']:
            data['category'] = entry['category']

    # 从正文提取 effective_date（xlsx 未覆盖时）
    if not data['effective_date']:
        data['effective_date'] = extract_effective_date(data)

    # legal_domain
    data['legal_domain'] = get_legal_domain(title, data, domain_idx)

    # 结构信息
    data = add_structure(data)

    return data


# ══════════════════════════════════════════════════════════════════════════════
# 7. 写入 JSON
# ══════════════════════════════════════════════════════════════════════════════

def write_json(data: dict, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


# ══════════════════════════════════════════════════════════════════════════════
# 8. 构建数据库
# ══════════════════════════════════════════════════════════════════════════════

def create_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS laws (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            filename TEXT UNIQUE NOT NULL,
            category TEXT,
            legal_domain TEXT,
            pub_date TEXT,
            effective_date TEXT,
            promulgation_info TEXT,
            total_articles INTEGER,
            version_date TEXT,
            is_current INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY,
            law_id INTEGER NOT NULL REFERENCES laws(id),
            parent_id INTEGER REFERENCES nodes(id),
            type TEXT NOT NULL,
            title TEXT,
            article_number TEXT,
            content TEXT,
            order_index INTEGER,
            global_order INTEGER
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
            content,
            article_number,
            tokenize='trigram'
        );
        CREATE TABLE IF NOT EXISTS article_references (
            from_id INTEGER REFERENCES nodes(id),
            to_id INTEGER REFERENCES nodes(id),
            PRIMARY KEY (from_id, to_id)
        );
        CREATE INDEX IF NOT EXISTS idx_nodes_law     ON nodes(law_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_parent  ON nodes(parent_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_order   ON nodes(law_id, global_order);
        CREATE INDEX IF NOT EXISTS idx_laws_title    ON laws(title);
    """)


def insert_law(conn, data: dict, filename: str, version_date: str) -> int:
    cur = conn.execute(
        """INSERT INTO laws (title, filename, category, legal_domain, pub_date,
                             effective_date, promulgation_info, total_articles,
                             version_date, is_current)
           VALUES (?,?,?,?,?,?,?,?,?,1)""",
        (data['title'], filename, data.get('category'), data.get('legal_domain'),
         data.get('pub_date'), data.get('effective_date'),
         data.get('promulgation_info'), data.get('total_articles'), version_date)
    )
    return cur.lastrowid


def _insert_article(conn, law_id, parent_id, art, oi, go):
    art_title  = art.get('title', '').strip()
    content    = art.get('content', '')
    art_number = art_title.rstrip('　 ')
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, article_number,
                              content, order_index, global_order)
           VALUES (?,?,'article',?,?,?,?,?)""",
        (law_id, parent_id, art_title, art_number, content, oi, go)
    )
    conn.execute(
        "INSERT INTO nodes_fts(rowid, content, article_number) VALUES(?,?,?)",
        (cur.lastrowid, content, art_number)
    )


def _insert_section(conn, law_id, parent_id, sec):
    t = sec.get('title', '').strip()
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, content,
                              order_index, global_order)
           VALUES (?,?,'section',?,?,?,?)""",
        (law_id, parent_id, t, t, sec.get('order_index'), sec.get('global_order'))
    )
    sid = cur.lastrowid
    for a in sec.get('articles', []):
        _insert_article(conn, law_id, sid, a, a.get('order_index'), a.get('global_order'))


def _insert_chapter(conn, law_id, parent_id, ch):
    t = ch.get('title', '').strip()
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, content,
                              order_index, global_order)
           VALUES (?,?,'chapter',?,?,?,?)""",
        (law_id, parent_id, t, t, ch.get('order_index'), ch.get('global_order'))
    )
    cid = cur.lastrowid
    for s in ch.get('sections', []):
        _insert_section(conn, law_id, cid, s)
    for a in ch.get('articles', []):
        _insert_article(conn, law_id, cid, a, a.get('order_index'), a.get('global_order'))


def insert_nodes(conn, law_id: int, data: dict):
    if 'parts' in data:
        for pt in data['parts']:
            t = (pt.get('title') or '').strip()
            cur = conn.execute(
                """INSERT INTO nodes (law_id, parent_id, type, title, content,
                                      order_index, global_order)
                   VALUES (?,NULL,'part',?,?,?,?)""",
                (law_id, t, t, pt.get('order_index'), pt.get('global_order'))
            )
            pid = cur.lastrowid
            for ch in pt.get('chapters', []):
                _insert_chapter(conn, law_id, pid, ch)
    else:
        chapters = data.get('chapters', [])
        if chapters:
            for ch in chapters:
                _insert_chapter(conn, law_id, None, ch)
        else:
            # 无条文结构（法律解释、决定等），将 full_text 整体作为单条 article 写入
            full_text = (data.get('full_text') or '').strip()
            if full_text:
                art = {'title': '', 'content': full_text}
                _insert_article(conn, law_id, None, art, 1, 1)


def build_db(json_dir: Path, db_path: Path):
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    create_schema(conn)

    paths = sorted(p for p in json_dir.rglob('*.json') if 'index' not in p.name)
    print(f'写入数据库: {len(paths)} 个文件')

    for i, path in enumerate(paths):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        stem         = path.stem
        version_date = pub_date_from_stem(stem)
        law_id       = insert_law(conn, data, stem, version_date)
        insert_nodes(conn, law_id, data)

        if (i + 1) % 200 == 0:
            print(f'  {i+1}/{len(paths)}')
            conn.commit()

    conn.commit()
    conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('optimize')")
    conn.commit()

    laws    = conn.execute('SELECT COUNT(*) FROM laws').fetchone()[0]
    nodes   = conn.execute('SELECT COUNT(*) FROM nodes').fetchone()[0]
    articles= conn.execute("SELECT COUNT(*) FROM nodes WHERE type='article'").fetchone()[0]
    size_mb = db_path.stat().st_size / 1024 / 1024
    print(f'数据库完成: laws={laws} nodes={nodes} articles={articles} {size_mb:.1f}MB')
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print('=== 加载辅助数据 ===')
    xlsx_index = build_xlsx_index()
    domain_idx = build_domain_index()
    print(f'xlsx 索引: {len(xlsx_index)} 条')
    print(f'domain 映射: {len(domain_idx)} 条')

    print('\n=== docx → JSON ===')
    # Clean json output dir to avoid stale files from renamed/removed docx
    import shutil
    if JSON_DIR.exists():
        shutil.rmtree(JSON_DIR)
    JSON_DIR.mkdir(parents=True)

    total = errors = 0
    for category, src_dir in SRC_DIRS.items():
        if not src_dir.exists():
            print(f'  跳过（目录不存在）: {src_dir}')
            continue
        out_dir = JSON_DIR / category
        out_dir.mkdir(parents=True, exist_ok=True)

        docx_files = sorted(f for f in src_dir.iterdir()
                            if f.suffix.lower() in ('.docx', '.doc'))
        print(f'  {category}: {len(docx_files)} 个文件')

        for docx_path in docx_files:
            data = process_docx(docx_path, category, xlsx_index, domain_idx)
            if data is None:
                errors += 1
                continue
            out_path = out_dir / (docx_path.stem + '.json')
            write_json(data, out_path)
            total += 1

    print(f'JSON 生成完成: {total} 个，{errors} 个错误')

    print('\n=== JSON → 数据库 ===')
    build_db(JSON_DIR, DB_PATH)

    print('\n=== 数据库 → Markdown ===')
    build_markdown(DB_PATH, BASE_DIR / 'markdown')

    print('\n=== 完成 ===')


def law_to_md(law: dict, nodes: list) -> str:
    lines = []
    lines.append(f'# {law["title"]}')
    lines.append('')

    meta = []
    if law.get('category'):       meta.append(f'**分类**：{law["category"]}')
    if law.get('legal_domain'):   meta.append(f'**法律部门**：{law["legal_domain"]}')
    if law.get('pub_date'):       meta.append(f'**公布日期**：{law["pub_date"]}')
    if law.get('effective_date'): meta.append(f'**生效日期**：{law["effective_date"]}')
    if law.get('total_articles'): meta.append(f'**条文数**：{law["total_articles"]}')
    if meta:
        lines.append('  \n'.join(meta))
        lines.append('')

    if law.get('promulgation_info'):
        lines.append(f'> {law["promulgation_info"]}')
        lines.append('')

    lines.append('---')
    lines.append('')

    for node in nodes:
        t = node['type']
        content = (node['content'] or '').strip()
        if not content:
            continue
        if t == 'part':
            lines.append(f'## {content}')
            lines.append('')
        elif t == 'chapter':
            lines.append(f'### {content}')
            lines.append('')
        elif t == 'section':
            lines.append(f'#### {content}')
            lines.append('')
        else:  # article
            lines.append(content)
            lines.append('')

    return '\n'.join(lines)


def build_markdown(db_path: Path, md_dir: Path):
    import shutil
    if md_dir.exists():
        shutil.rmtree(md_dir)

    conn = sqlite3.connect(db_path)
    laws = conn.execute(
        'SELECT id, title, filename, category, legal_domain, pub_date, '
        'effective_date, promulgation_info, total_articles FROM laws ORDER BY id'
    ).fetchall()
    law_keys = ['id', 'title', 'filename', 'category', 'legal_domain',
                'pub_date', 'effective_date', 'promulgation_info', 'total_articles']

    domain_unknown = 0
    for row in laws:
        law = dict(zip(law_keys, row))
        domain = law['legal_domain'] or '其他'
        if not law['legal_domain']:
            domain_unknown += 1

        category = law['category'] or ''
        if category in ('司法解释', '法律解释'):
            out_dir = md_dir / domain / category
        else:
            out_dir = md_dir / domain
        out_dir.mkdir(parents=True, exist_ok=True)

        nodes = conn.execute(
            'SELECT type, content FROM nodes WHERE law_id=? ORDER BY global_order',
            (law['id'],)
        ).fetchall()
        node_list = [{'type': r[0], 'content': r[1]} for r in nodes]

        (out_dir / (law['filename'] + '.md')).write_text(
            law_to_md(law, node_list), encoding='utf-8'
        )

    conn.close()
    print(f'Markdown 生成完成，输出目录：{md_dir}')
    print(f'  未知 legal_domain（归入"其他"）：{domain_unknown}')
    for d in sorted(md_dir.iterdir()):
        md_count = len(list(d.glob('*.md')))
        sub_count = sum(len(list(s.glob('*.md'))) for s in d.iterdir() if s.is_dir())
        total_str = f'{md_count} 个' if not sub_count else f'{md_count} 个 + 子分类 {sub_count} 个'
        print(f'  {d.name}/  {total_str}')


if __name__ == '__main__':
    main()
