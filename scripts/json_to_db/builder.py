#!/usr/bin/env python3
"""
JSON → SQLite
用法：python3 -m json_to_db.builder
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import os
import sys
import tempfile
from config import JSON_DIR, DB_PATH
from utils import pub_date_from_stem
from docx_to_json.subject_area import get_subject_area
from docx_to_json.converter import clean_article_content, extract_content
from law_aliases import ALIASES

BASE_DIR     = Path(__file__).parent.parent.parent   # laws_data/
# LAW_INDEX_PATH 统一来自 law_id_registry（见下方 import）

GONGBAO_SFJS_DIR = BASE_DIR / '最高人民法院公报' / '司法解释'


def normalize_title(title: str) -> str:
    """标题规范化：全角空格→空格、机构联合署名空格→顿号、CJK 词间空格删除。"""
    title = title.replace('　', ' ')
    title = re.sub(r'最高人民法院 +最高人民检察院', '最高人民法院、最高人民检察院', title)
    title = re.sub(r'最高人民检察院 +最高人民法院', '最高人民检察院、最高人民法院', title)
    title = re.sub(r'最高人民检察院 +公安部', '最高人民检察院、公安部', title)
    title = re.sub(r'最高人民法院 +公安部', '最高人民法院、公安部', title)
    title = re.sub(r'(最高人民法院|最高人民检察院|公安部|国家安全部|司法部) +', r'\1', title)
    title = re.sub(r'([）》」』］]) +', r'\1', title)
    title = re.sub(r'([\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])', r'\1', title)
    title = re.sub(r' +', ' ', title).strip()
    return title

# 覆盖名单：其他来源替换了主库版本的 law_id 集合
# 格式：[{laws_id, gongbao_file, title, pub_date}, ...]
# law_id 权威解析统一走 law_id_registry（禁止在此各自硬编码规则）
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))
try:
    import law_id_registry as _lid_reg
    _BLOCKLIST_PATH = _lid_reg.BLOCKLIST_PATH
    _OVERRIDE_BLOCKLIST: set = _lid_reg.blocklist_ids()
    _GONGBAO_FILE_TO_LAW_ID: dict[str, int] = _lid_reg.gongbao_file_to_law_id()
    LAW_INDEX_PATH = _lid_reg.LAW_INDEX_PATH
except ImportError:
    _BLOCKLIST_PATH = Path(__file__).parent.parent / 'source_override_blocklist.json'
    _OVERRIDE_BLOCKLIST: set = set()
    _GONGBAO_FILE_TO_LAW_ID: dict[str, int] = {}
    LAW_INDEX_PATH = BASE_DIR / 'law_index.json'

# 废止标记：已废止的司法解释在公报源 JSON（最高人民法院公报/司法解释/*.json）的
# repealed_by 字段中直接标记，导入时读取该字段设为 is_current=0（见 import_gongbao_sfjs）。
# 不再使用规则表匹配，避免标题/文号差异导致的误标或漏标。

_CN_ORD = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,
           '九':9,'十':10,'百':100,'千':1000}

def _cn_to_int(s: str) -> int:
    s = s.strip()
    result = tmp = 0
    for c in s:
        v = _CN_ORD.get(c, 0)
        if v >= 10:
            result += (tmp or 1) * v
            tmp = 0
        else:
            tmp = v
    return result + tmp

_ART_NUM_RE = re.compile(r'^第([零一二三四五六七八九十百千]+)条')

_CJK_RE = re.compile(r'[一-鿿]')

def create_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS laws (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            title_en TEXT,
            filename TEXT UNIQUE NOT NULL,
            category TEXT,
            legal_domain TEXT,
            subject_area TEXT,
            pub_date TEXT,
            effective_date TEXT,
            promulgation_info TEXT,
            issuing_org TEXT,
            doc_number TEXT,
            total_articles INTEGER,
            full_text TEXT,
            version_date TEXT,
            is_current INTEGER DEFAULT 1,
            aliases TEXT,
            source TEXT DEFAULT 'flk'  -- 'flk'=主库法律库, 'gongbao'=最高人民法院公报
        );
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY,
            law_id INTEGER NOT NULL REFERENCES laws(id),
            parent_id INTEGER REFERENCES nodes(id),
            type TEXT NOT NULL,
            title TEXT,
            article_number TEXT,
            content TEXT,
            content_en TEXT,
            order_index INTEGER,
            global_order INTEGER,
            part_num    INTEGER,
            chapter_num INTEGER,
            section_num INTEGER,
            article_num INTEGER
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
            content,
            article_number,
            content="nodes",
            content_rowid="id",
            tokenize='trigram'
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts_bigram USING fts5(
            content,
            article_number,
            content="nodes",
            content_rowid="id",
            tokenize='unicode61'
        );
        CREATE TABLE IF NOT EXISTS article_references (
            id               INTEGER PRIMARY KEY,
            from_node_id     INTEGER REFERENCES nodes(id),
            from_law_id      INTEGER REFERENCES laws(id),
            from_article_num INTEGER,
            from_chapter_num INTEGER,
            from_section_num INTEGER,
            from_part_num    INTEGER,
            to_node_id       INTEGER REFERENCES nodes(id),
            to_law_id        INTEGER REFERENCES laws(id),
            to_article_num   INTEGER,
            to_chapter_num   INTEGER,
            to_section_num   INTEGER,
            to_part_num      INTEGER,
            ref_type         TEXT,
            resolved         INTEGER,
            raw_text         TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_nodes_law    ON nodes(law_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
        CREATE INDEX IF NOT EXISTS idx_nodes_order  ON nodes(law_id, global_order);
        CREATE INDEX IF NOT EXISTS idx_laws_title   ON laws(title);
        CREATE INDEX IF NOT EXISTS idx_nodes_nums   ON nodes(law_id, part_num, chapter_num, section_num, article_num);
    """)


def _clean_text(t: str) -> str:
    """去除多余换行和空格，保留段落间单个换行。"""
    if not t:
        return t
    # 合并连续空白行为单个换行
    t = re.sub(r'\n{2,}', '\n', t)
    # 去除行首行尾多余空格（保留换行本身）
    t = '\n'.join(line.strip() for line in t.split('\n'))
    # 去除多余空格（非换行）
    t = re.sub(r'[ \t]{2,}', ' ', t)
    return t.strip()


def _insert_article(conn, law_id, parent_id, art, oi, go, coords):
    art_title  = art.get('title', '').strip()
    content    = art.get('content', '')
    art_number = art_title.rstrip('　 ')
    m = _ART_NUM_RE.match(art_number)
    art_num = _cn_to_int(m.group(1)) if m else oi
    pt_num  = coords[0] if len(coords) > 0 else None
    ch_num  = coords[1] if len(coords) > 1 else None
    sec_num = coords[2] if len(coords) > 2 else None
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, article_number,
                              content, order_index, global_order,
                              part_num, chapter_num, section_num, article_num)
           VALUES (?,?,'article',?,?,?,?,?,?,?,?,?)""",
        (law_id, parent_id, art_title, art_number, content, oi, go,
         pt_num, ch_num, sec_num, art_num)
    )
    conn.execute(
        "INSERT INTO nodes_fts(rowid, content, article_number) VALUES(?,?,?)",
        (cur.lastrowid, content, art_number)
    )
    conn.execute(
        "INSERT INTO nodes_fts_bigram(rowid, content, article_number) VALUES(?,?,?)",
        (cur.lastrowid, content, art_number)
    )


def _insert_section(conn, law_id, parent_id, sec, coords):
    t = sec.get('title', '').strip()
    sec_num = sec.get('order_index')
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, content,
                              order_index, global_order,
                              part_num, chapter_num, section_num)
           VALUES (?,?,'section',?,?,?,?,?,?,?)""",
        (law_id, parent_id, t, t, sec.get('order_index'), sec.get('global_order'),
         coords[0], coords[1], sec_num)
    )
    child_coords = (coords[0], coords[1], sec_num)
    for a in sec.get('articles', []):
        _insert_article(conn, law_id, cur.lastrowid, a, a.get('order_index'), a.get('global_order'), child_coords)


def _insert_chapter(conn, law_id, parent_id, ch, coords):
    t = ch.get('title', '').strip()
    if t.startswith('_DIRECT_'):
        # 编下直属条文占位章：不创建 chapter 节点，文章直接挂到编（parent_id）下
        for a in ch.get('articles', []):
            _insert_article(conn, law_id, parent_id, a, a.get('order_index'), a.get('global_order'), coords)
        return
    ch_num = ch.get('order_index')
    cur = conn.execute(
        """INSERT INTO nodes (law_id, parent_id, type, title, content,
                              order_index, global_order,
                              part_num, chapter_num)
           VALUES (?,?,'chapter',?,?,?,?,?,?)""",
        (law_id, parent_id, t, t, ch.get('order_index'), ch.get('global_order'),
         coords[0], ch_num)
    )
    cid = cur.lastrowid
    child_coords = (coords[0], ch_num)
    for s in ch.get('sections', []):
        _insert_section(conn, law_id, cid, s, child_coords)
    for a in ch.get('articles', []):
        _insert_article(conn, law_id, cid, a, a.get('order_index'), a.get('global_order'), child_coords)


def insert_nodes(conn, law_id: int, data: dict):
    if 'parts' in data:
        for pt in data['parts']:
            t = (pt.get('title') or '').strip()
            pt_num = pt.get('order_index')
            cur = conn.execute(
                """INSERT INTO nodes (law_id, parent_id, type, title, content,
                                      order_index, global_order, part_num)
                   VALUES (?,NULL,'part',?,?,?,?,?)""",
                (law_id, t, t, pt.get('order_index'), pt.get('global_order'), pt_num)
            )
            for ch in pt.get('chapters', []):
                _insert_chapter(conn, law_id, cur.lastrowid, ch, (pt_num,))
    else:
        chapters = data.get('chapters', [])
        if chapters:
            for ch in chapters:
                _insert_chapter(conn, law_id, None, ch, (None,))
        else:
            full_text = (data.get('full_text') or '').strip()
            if full_text:
                full_text = clean_article_content(full_text)
                _insert_article(conn, law_id, None,
                                {'title': '', 'content': full_text}, 1, 1, (None, None, None))


def build_db(json_dir: Path = JSON_DIR, db_path: Path = DB_PATH):
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=DELETE')  # iOS bundle 不支持 WAL（只读目录无法创建 -wal/-shm）
    conn.execute('PRAGMA foreign_keys=ON')
    create_schema(conn)

    paths = sorted(p for p in json_dir.rglob('*.json') if 'index' not in p.name)
    print(f'写入数据库: {len(paths)} 个文件')

    for i, path in enumerate(paths):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        stem         = path.stem
        version_date = pub_date_from_stem(stem)
        category     = data.get('category')

        # 标题规范化：机构名称间空格→顿号、多余空格清理
        title = data['title']
        # 机构联合署名间的空格 → 顿号（优先替换，避免被后续规则破坏）
        title = re.sub(r'最高人民法院 +最高人民检察院', '最高人民法院、最高人民检察院', title)
        title = re.sub(r'最高人民检察院 +最高人民法院', '最高人民检察院、最高人民法院', title)
        title = re.sub(r'最高人民检察院 +公安部', '最高人民检察院、公安部', title)
        title = re.sub(r'最高人民法院 +公安部', '最高人民法院、公安部', title)
        # 机构名后跟文本时，去掉多余空格（此时多机构组合已被替换为顿号版本）
        title = re.sub(r'[ \t]{2,}', ' ', title).strip()
        # 全角空格 → 普通空格
        title = title.replace('　', ' ')
        title = re.sub(r'(最高人民法院|最高人民检察院|公安部|国家安全部|司法部) +', r'\1', title)
        # 书名号/引号后的空格（排版换行残留）
        title = re.sub(r'([）》」』］]) +', r'\1', title)
        title = re.sub(r'  +', ' ', title).strip()

        # 跳过已被其他来源覆盖的条目（在覆盖名单中的 law_id 由其他来源写入）
        if data.get('law_id') in _OVERRIDE_BLOCKLIST:
            continue

        subject_area = get_subject_area(title, category)
        aliases      = ALIASES.get(title, '')
        # 源 JSON 显式声明的 is_current（多版本法律：非最新版标 0，脚本可据此忽略）
        src_current = data.get('is_current')
        is_current = 1 if src_current is None else (1 if src_current else 0)
        cur = conn.execute(
            """INSERT INTO laws (id, title, filename, category, legal_domain, subject_area, pub_date,
                                 effective_date, promulgation_info, issuing_org, doc_number,
                                 total_articles, full_text, version_date, is_current, aliases, source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'flk')""",
            (data.get('law_id'), title, stem, category, data.get('legal_domain'),
             subject_area,
             data.get('pub_date'), data.get('effective_date'),
             data.get('promulgation_info'), data.get('issuing_org'), data.get('doc_number'),
             data.get('total_articles'), _clean_text(data.get('full_text', '')),
             version_date, is_current, aliases if aliases else None)
        )
        insert_nodes(conn, data.get('law_id'), data)

        if (i + 1) % 200 == 0:
            print(f'  {i+1}/{len(paths)}')
            conn.commit()

    conn.commit()
    conn.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('optimize')")
    conn.execute("INSERT INTO nodes_fts_bigram(nodes_fts_bigram) VALUES('optimize')")
    conn.commit()

    laws     = conn.execute('SELECT COUNT(*) FROM laws').fetchone()[0]
    nodes    = conn.execute('SELECT COUNT(*) FROM nodes').fetchone()[0]
    articles = conn.execute("SELECT COUNT(*) FROM nodes WHERE type='article'").fetchone()[0]
    size_mb  = db_path.stat().st_size / 1024 / 1024
    print(f'数据库完成: laws={laws} nodes={nodes} articles={articles} {size_mb:.1f}MB')
    conn.close()


def import_gongbao_sfjs(db_path: Path = DB_PATH):
    """将公报司法解释（927个JSON文件）解析为结构化条文，写入 laws/nodes 表（source='gongbao'）。

    每个文件的 law_id 已在预处理阶段写入 JSON，本函数直接读取使用。
    与主库重复的条目（id 已存在）通过 INSERT OR IGNORE 跳过。
    """
    if not GONGBAO_SFJS_DIR.exists():
        print(f'  ⚠ 公报司法解释目录不存在：{GONGBAO_SFJS_DIR}')
        return

    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=OFF')   # 批量插入时临时关闭外键检查

    # 清空旧数据，确保本次写入覆盖之前可能错误的条目
    conn.execute("DELETE FROM nodes WHERE law_id IN (SELECT id FROM laws WHERE source='gongbao')")
    conn.execute("DELETE FROM laws WHERE source='gongbao'")
    conn.commit()

    # 从 json/司法解释/ 目录预建 law_id → (legal_domain, subject_area) 映射
    # 公报原始文件不含这两个字段，需从 pipeline 生成的结构化 JSON 补充
    _domain_map: dict[int, tuple[str, str]] = {}
    json_sfjs_dir = BASE_DIR / 'json' / '司法解释'
    if json_sfjs_dir.exists():
        for jf in json_sfjs_dir.glob('*.json'):
            try:
                jd = json.loads(jf.read_text('utf-8'))
                lid = jd.get('law_id')
                if lid:
                    _domain_map[lid] = (jd.get('legal_domain', '') or '', jd.get('subject_area', '') or '')
            except Exception:
                pass

    files = sorted(GONGBAO_SFJS_DIR.glob('*.json'))
    print(f'\n导入公报司法解释：{len(files)} 个文件')

    inserted = parse_errors = 0

    # 跟踪新条目用于写入 law_index.json
    gongbao_index_entries: list[dict] = []

    for i, f in enumerate(files):
        d = json.loads(f.read_text(encoding='utf-8'))
        law_id = d.get('law_id')
        title = normalize_title(d.get('title', ''))
        if not law_id:
            # 权威映射：source_override_blocklist 的 gongbao_file → laws_id（flk 源跳过这些
            # law_id，必须由公报源用同一 id 覆盖，否则该司法解释会整体丢失）
            law_id = _GONGBAO_FILE_TO_LAW_ID.get(f.name)
        if not law_id:
            # 源文件必须显式携带 law_id（或由 blocklist 权威映射）。
            # 缺失时直接报错，禁止静默分配新 ID（会掩盖数据错误、导致 law_id 漂移）。
            raise ValueError(
                f'公报文件缺少 law_id 且不在 blocklist 权威映射中: {f.name}'
            )

        pub_date = d.get('pub_date', '')

        # 用临时 txt 文件让 extract_content 解析条文结构
        # 公报 content 字段中条文号后可能缺少空白，补全以确保 ARTICLE_RE 能识别
        # 同时清理条号数字与“条”之间的噪声空白（如“第二十五 条”）
        content_text = re.sub(
            r'^(第[零一二三四五六七八九十百千]+)\s+条',
            r'\1条', d.get('content', ''), flags=re.MULTILINE
        )
        # 决定/批复类文本中行首“第X条增加第二款/删除/修改为”等是对其他条文
        # 的引用而非新条文开头，补全空格时排除这些动词，避免误识别为条文标题
        content_text = re.sub(
            r'^(第[零一二三四五六七八九十百千]+条)(?![　\s]|增加|删除|删去|修改|改为|废止|并入|调整为|未变|的规定|的内容)',
            lambda m: m.group(1) + '　', content_text, flags=re.MULTILINE
        )
        with tempfile.NamedTemporaryFile(
            suffix='.txt', mode='w', encoding='utf-8', delete=False
        ) as tmp:
            tmp.write(content_text)
            tmp_path = Path(tmp.name)

        try:
            content_data = extract_content(tmp_path)
            if content_data.get('total_articles', 0) == 0:
                raise ValueError(f'total_articles=0 after extract_content')
        except Exception as e:
            print(f'  ⚠ extract_content 失败 [{f.name}]: {e}')
            # fallback: 作为一条纯文本条文插入
            content_data = {
                'full_text': content_text,
                'total_articles': 1,
                'chapters': [{
                    'title': title,
                    'order_index': 1,
                    'global_order': 1,
                    'articles': [{
                        'title': '',
                        'content': content_text,
                        'order_index': 1,
                        'global_order': 1,
                    }],
                }],
                'promulgation_info': '',
                'issuing_org': '',
                'doc_number': '',
            }
        finally:
            tmp_path.unlink(missing_ok=True)

        full_text  = _clean_text(content_data.get('full_text', content_text))
        total_arts = content_data.get('total_articles', 0)
        prom_info  = content_data.get('promulgation_info', '')
        issuing    = content_data.get('issuing_org', '') or '最高人民法院'
        doc_num    = d.get('doc_number', '') or content_data.get('doc_number', '')
        eff_date   = d.get('effective_date', '')
        filename   = f.stem   # 用文件 stem 作 filename（唯一键）
        # 源 JSON 中的废止标记（repealed_by 非空 → 该司法解释已被废止决定明确废止，导入时直接标 is_current=0）
        repealed_by = d.get('repealed_by', '')
        # 源 JSON 中显式声明的 is_current（重复/历史版本文件标 0，仅登记不插入节点）
        src_current = d.get('is_current')
        is_current = 0 if repealed_by else (1 if src_current is None else (1 if src_current else 0))

        try:
            conn.execute(
                """INSERT OR IGNORE INTO laws
                   (id, title, filename, category, legal_domain, subject_area, pub_date,
                    effective_date, promulgation_info, issuing_org, doc_number,
                    total_articles, full_text, version_date, is_current, aliases, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,'gongbao')""",
                (law_id, title, filename, '司法解释',
                 _domain_map.get(law_id, ('', ''))[0],
                 _domain_map.get(law_id, ('', ''))[1],
                 pub_date, eff_date, prom_info, issuing, doc_num,
                 total_arts, full_text, pub_date, is_current)
            )
            # 如果法律已存在于主库（source='flk'），跳过节点插入避免重复
            existing_nodes = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE law_id=?", (law_id,)
            ).fetchone()[0]
            # 源 JSON 标记为非现行的重复/历史版本：只登记 laws 元数据，不插入节点
            # （同一 law_id 的现行版本文件会提供实际条文内容）
            if not is_current:
                continue
            if existing_nodes > 0:
                continue
            insert_nodes(conn, law_id, content_data)
            inserted += 1
            # 记录新发条目供写入 law_index.json
            gongbao_index_entries.append({
                'law_id':       law_id,
                'filename':     filename,
                'title':        title,
                'category':     '司法解释',
                'legal_domain': _domain_map.get(law_id, ('', ''))[0],
                'pub_date':     pub_date,
                'effective_date': eff_date,
            })
        except Exception as e:
            parse_errors += 1
            print(f'  ERROR [{f.name}]: {e}')

        if (i + 1) % 200 == 0:
            print(f'  {i+1}/{len(files)} (inserted={inserted})')
            conn.commit()

    conn.commit()

    conn.execute('PRAGMA foreign_keys=ON')
    conn.close()

    print(f'  公报司法解释：插入 {inserted} 条，解析错误 {parse_errors} 条')

    if gongbao_index_entries:
        # 追加到 law_index.json
        if LAW_INDEX_PATH.exists():
            existing = json.loads(LAW_INDEX_PATH.read_text(encoding='utf-8'))
        else:
            existing = []
        existing_ids = {e['law_id'] for e in existing}
        new_entries = [e for e in gongbao_index_entries if e['law_id'] not in existing_ids]
        if new_entries:
            existing.extend(new_entries)
            existing.sort(key=lambda x: x['law_id'])
            LAW_INDEX_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'  law_index.json 追加 {len(new_entries)} 条（共 {len(existing)} 条）')


def load_references(db_path: Path = DB_PATH,
                    refs_path: Path = Path(__file__).parent.parent.parent / 'references' / 'article_references.json'):
    """将 article_references.json 填入 article_references 表。"""
    if not refs_path.exists():
        print(f'  引用文件不存在：{refs_path}')
        return

    conn = sqlite3.connect(db_path)
    # 暂时关闭外键约束，避免导入时因节点ID不存在而失败
    # 这些引用可能指向已删除的法律或条文
    conn.execute('PRAGMA foreign_keys=OFF')

    # 建立坐标 → node_id 索引：(law_id, article_num) → node_id
    rows = conn.execute(
        "SELECT law_id, article_num, id FROM nodes WHERE type='article' AND article_num IS NOT NULL"
    ).fetchall()
    node_index = {}
    for law_id, article_num, node_id in rows:
        node_index[(law_id, article_num)] = node_id

    conn.execute('DELETE FROM article_references')

    data = json.loads(refs_path.read_text(encoding='utf-8'))
    batch = []
    skipped = 0
    for entry in data:
        from_law_id      = entry.get('from_law_id')
        from_article_num = entry.get('from_article_num')
        from_chapter_num = entry.get('from_chapter_num')
        from_section_num = entry.get('from_section_num')
        from_part_num    = entry.get('from_part_num')
        from_node_id     = node_index.get((from_law_id, from_article_num))

        # 跳过 from_node_id 不存在的引用（源法律可能不在数据库中）
        if not from_node_id:
            skipped += 1
            continue

        for ref in entry.get('refs', []):
            to_law_id      = ref.get('to_law_id')
            to_article_num = ref.get('to_article_num')
            to_chapter_num = ref.get('to_chapter_num')
            to_section_num = ref.get('to_section_num')
            to_part_num    = ref.get('to_part_num')
            to_node_id     = node_index.get((to_law_id, to_article_num)) if to_law_id and to_article_num else None

            # 跳过 to_node_id 不存在的跨法引用（目标法律可能不在数据库中）
            # 但保留 to_node_id 为 None 的情况（未解析的引用）
            if ref.get('type') == 'cross_law' and to_law_id and to_article_num and not to_node_id:
                skipped += 1
                continue

            batch.append((
                from_node_id, from_law_id, from_article_num, from_chapter_num, from_section_num, from_part_num,
                to_node_id,   to_law_id,   to_article_num,   to_chapter_num,   to_section_num,   to_part_num,
                ref.get('type'), 1 if ref.get('resolved') else 0, ref.get('raw_text'),
            ))

    if skipped:
        print(f'  跳过 {skipped} 条无效引用（法律或节点不在数据库中）')

    conn.executemany(
        """INSERT INTO article_references
           (from_node_id, from_law_id, from_article_num, from_chapter_num, from_section_num, from_part_num,
            to_node_id,   to_law_id,   to_article_num,   to_chapter_num,   to_section_num,   to_part_num,
            ref_type, resolved, raw_text)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        batch
    )
    try:
        conn.commit()
    except sqlite3.IntegrityError as e:
        print(f'  外键约束失败，检查节点ID...')
        # 验证所有 node_id 是否存在
        node_ids_in_db = set(r[0] for r in conn.execute('SELECT id FROM nodes').fetchall())
        for i, row in enumerate(batch):
            from_node_id, to_node_id = row[0], row[6]
            if from_node_id and from_node_id not in node_ids_in_db:
                print(f'    batch[{i}]: from_node_id={from_node_id} 不存在')
            if to_node_id and to_node_id not in node_ids_in_db:
                print(f'    batch[{i}]: to_node_id={to_node_id} 不存在')
        raise

    total    = conn.execute('SELECT COUNT(*) FROM article_references').fetchone()[0]
    resolved = conn.execute('SELECT COUNT(*) FROM article_references WHERE resolved=1').fetchone()[0]
    cross    = conn.execute("SELECT COUNT(*) FROM article_references WHERE ref_type='cross_law'").fetchone()[0]
    self_    = conn.execute("SELECT COUNT(*) FROM article_references WHERE ref_type='self_ref'").fetchone()[0]
    conn.close()
    print(f'引用关系写入完成：共 {total} 条（跨法 {cross} / 自引 {self_}），已解析 {resolved} 条')


def run():
    print('\n=== JSON → 数据库 ===')
    build_db()
    print('\n=== 导入公报司法解释 ===')
    import_gongbao_sfjs()
    print('\n=== 写入引用关系 ===')
    try:
        load_references()
    except Exception as e:
        print(f'  引用关系写入失败（非致命）: {e}')
    # 写入 db 版本戳（YYYYMMDD 整数），供 iOS 端判断是否需要重新复制
    version = int(datetime.now().strftime('%Y%m%d'))
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f'PRAGMA user_version = {version}')
    conn.commit()
    conn.close()
    print(f'\n  DB user_version 设为 {version}')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
