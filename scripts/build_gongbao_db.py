#!/usr/bin/env python3
"""
构建公报补充数据库 law_content.db（追加公报表）
================================================
在现有 law_content.db 中新增两张表：

  gongbao_docs
    裁判文书(cpwsxd) + 指导案例(al) + 司法文件(sfwj) 三合一
    source 字段区分：'cpwsxd' / 'al' / 'sfwj'

  gongbao_case_law_links
    gongbao_docs 条目引用主库法条的关联关系

  gongbao_docs_fts
    FTS5 trigram 全文索引（外部内容表）

注：公报司法解释已在 builder.py 的 import_gongbao_sfjs() 中以结构化条文
    形式写入主库 laws/nodes 表（source='gongbao'），不再单独维护 gongbao_sfjs 表。

用法：
  cd /Users/doxie/laws_data
  python3 scripts/build_gongbao_db.py        # 建表并导入
  python3 scripts/build_gongbao_db.py --drop # 先删旧表再重建
"""

import argparse
import json
import re
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH  = BASE_DIR / 'law_content.db'

GONGBAO_DIR = BASE_DIR / '最高人民法院公报'

# source → 子目录
DOC_SOURCES = {
    'cpwsxd': GONGBAO_DIR / '裁判文书',
    'al':     GONGBAO_DIR / '指导案例',
    'sfwj':   GONGBAO_DIR / '司法文件',
}

# 引用提取正则
_CROSS_RE = re.compile(
    r'《([^》]{2,30})》第([一二三四五六七八九十百千零〇两]+)条'
)

# 汉字数字 → 整数
_CN_MAP = {
    '零':0,'〇':0,'一':1,'二':2,'三':3,'四':4,'五':5,
    '六':6,'七':7,'八':8,'九':9,'十':10,'百':100,'千':1000,'两':2
}

def cn2int(s: str):
    try:
        s = s.strip()
        result = 0
        tmp = 0
        for ch in s:
            v = _CN_MAP.get(ch)
            if v is None:
                return None
            if v >= 10:
                if tmp == 0:
                    tmp = 1
                result += tmp * v
                tmp = 0
            else:
                tmp = v
        return result + tmp
    except Exception:
        return None


# ── Schema ───────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS gongbao_docs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,        -- 'cpwsxd' | 'al' | 'sfwj'
    case_number TEXT,                 -- '指导性案例212号'，仅 al 中编号案例有值
    title       TEXT NOT NULL,
    issue       TEXT,                 -- '2024年01期'
    year        INTEGER,
    issue_num   INTEGER,
    doc_number  TEXT,
    pub_date    TEXT,
    url         TEXT,
    ruling_gist TEXT,                 -- 裁判摘要/裁判要点（从正文提取）
    keywords    TEXT,                 -- 关键词平铺字符串
    keywords_meta TEXT,               -- 结构化关键词 JSON（LLM生成，各维度分组）
    full_text   TEXT
);

CREATE TABLE IF NOT EXISTS gongbao_case_law_links (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id       INTEGER NOT NULL REFERENCES gongbao_docs(id),
    law_id       INTEGER REFERENCES laws(id),
    node_id      INTEGER REFERENCES nodes(id),
    article_num  INTEGER,
    raw_ref      TEXT,
    ref_law_title TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS gongbao_docs_fts USING fts5(
    title,
    ruling_gist,
    keywords,
    full_text,
    content="gongbao_docs",
    tokenize="trigram"
);
"""

DROP_SQL = """
DROP TABLE IF EXISTS gongbao_case_law_links;
DROP TABLE IF EXISTS gongbao_docs_fts;
DROP TABLE IF EXISTS gongbao_docs;
"""


# ── 字段提取辅助 ──────────────────────────────────────────────────────────────

def extract_ruling_gist(content: str) -> str:
    """提取裁判摘要/裁判要点/裁判要旨（最多500字）。"""
    for marker in ['裁判要点', '裁判摘要', '裁判要旨']:
        m = re.search(r'【' + marker + r'】\s*(.+?)(?=\n\n|\n【|$)', content, re.S)
        if m:
            return m.group(1).strip()[:500]
        m = re.search(r'(?:^|\n)' + marker + r'\s*\n(.+?)(?=\n\n(?:基本案情|裁判结果|相关法条|关键词|一、|二、)|$)',
                      content, re.S)
        if m:
            return m.group(1).strip()[:500]
    return ''


def extract_keywords(content: str) -> str:
    """提取关键词字段。"""
    m = re.search(r'【关键词】\s*(.{2,200}?)(?:\n|$)', content)
    if m:
        return m.group(1).strip()[:200]
    m = re.search(r'(?:^|\n)关键词\s*\n[\s\n]*([^\n]{2,200})', content)
    if m:
        return m.group(1).strip().replace('/', '、')[:200]
    m = re.search(r'(?:^|\n)关键词[　\s]+([^\n]{2,200})', content)
    if m:
        return m.group(1).strip().replace('/', '、')[:200]
    return ''


_KW_DICT = [
    '合同纠纷', '买卖合同', '借款合同', '租赁合同', '建设工程合同', '服务合同',
    '劳动合同', '承揽合同', '运输合同', '保险合同', '委托合同', '赠与合同',
    '民间借贷', '网络服务合同',
    '侵权责任', '人身损害赔偿', '交通事故', '医疗纠纷', '产品责任', '名誉权',
    '肖像权', '隐私权', '著作权', '专利权', '商标权', '不正当竞争',
    '物权', '房屋买卖', '土地使用权', '征收补偿', '业主权利', '抵押权', '质权',
    '婚姻', '离婚', '子女抚养', '监护权', '探望权', '遗产继承', '遗嘱',
    '股权转让', '股东权利', '公司解散', '破产', '票据', '保险理赔', '证券',
    '担保', '保证', '抵押', '质押',
    '正当防卫', '紧急避险', '故意伤害', '故意杀人', '盗窃', '诈骗',
    '贪污', '受贿', '行贿', '走私', '毒品', '强奸', '抢劫',
    '虐待', '组织卖淫',
    '行政诉讼', '行政许可', '行政处罚', '行政赔偿', '国家赔偿',
    '执行异议', '申请再审', '管辖权', '诉讼时效', '仲裁',
    '专利无效', '商标注册', '著作权侵权', '知识产权',
    '劳动争议', '工伤', '社会保险', '经济补偿',
]

def infer_keywords_from_text(title: str, gist: str, full_text: str) -> str:
    combined = f"{title} {gist} {full_text[:800]}"
    found = [kw for kw in _KW_DICT if kw in combined]
    extra = re.findall(r'[一-龥]{2,10}(?:纠纷|争议|案件)', title)
    return '、'.join(list(dict.fromkeys(found + extra))[:8])


def extract_case_number(title: str) -> str:
    m = re.search(r'指导性案例(\d+)号', title)
    return f'指导性案例{m.group(1)}号' if m else ''


# ── 导入 gongbao_docs ─────────────────────────────────────────────────────────

def import_docs(conn: sqlite3.Connection) -> int:
    total = 0
    for source, folder in DOC_SOURCES.items():
        if not folder.exists():
            print(f'  ⚠ 目录不存在：{folder}')
            continue
        files = list(folder.glob('*.json'))
        print(f'  {source}: {len(files)} 个文件')
        for f in files:
            d = json.loads(f.read_text(encoding='utf-8'))
            content       = d.get('content', '')
            title         = d.get('title', '')
            case_num      = d.get('case_number') or extract_case_number(title) or None
            gist          = d.get('ruling_gist') or extract_ruling_gist(content)
            keywords      = d.get('keywords') or extract_keywords(content)
            keywords_meta = d.get('keywords_meta')
            if not keywords:
                keywords = infer_keywords_from_text(title, gist, content)
            conn.execute(
                """INSERT INTO gongbao_docs
                   (source, case_number, title, issue, year, issue_num,
                    doc_number, pub_date, url, ruling_gist, keywords, keywords_meta, full_text)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (source, case_num or None, title, d.get('issue', ''),
                 d.get('year'), d.get('issue_num'), d.get('doc_number', ''),
                 d.get('pub_date', ''), d.get('url', ''),
                 gist, keywords,
                 json.dumps(keywords_meta, ensure_ascii=False) if keywords_meta else None,
                 content)
            )
            total += 1
    return total


# ── 建立法条关联 ──────────────────────────────────────────────────────────────

def build_links(conn: sqlite3.Connection) -> int:
    """从 gongbao_docs 全文提取《法律名》第N条引用，关联主库 nodes。"""

    law_index: dict[str, int] = {}
    for law_id, title in conn.execute(
        "SELECT id, title FROM laws WHERE is_current=1"
    ):
        short = title.replace('中华人民共和国', '')
        law_index[title] = law_id
        law_index.setdefault(short, law_id)

    art_index: dict[tuple, int] = {}
    for node_id, law_id, art_num in conn.execute(
        "SELECT id, law_id, article_num FROM nodes WHERE type='article' AND article_num IS NOT NULL"
    ):
        art_index[(law_id, art_num)] = node_id

    total_links = 0
    docs = conn.execute("SELECT id, full_text FROM gongbao_docs").fetchall()

    for doc_id, text in docs:
        if not text:
            continue
        links_for_doc = []
        seen = set()

        for m in _CROSS_RE.finditer(text):
            law_title = m.group(1).strip()
            art_num   = cn2int(m.group(2))
            if art_num is None:
                continue

            law_id = law_index.get(law_title) or law_index.get(
                law_title.replace('中华人民共和国', '')
            )
            if not law_id:
                continue

            key = (law_id, art_num)
            if key in seen:
                continue
            seen.add(key)

            node_id = art_index.get(key)
            links_for_doc.append((doc_id, law_id, node_id, art_num, m.group(0), law_title))

        if links_for_doc:
            conn.executemany(
                """INSERT INTO gongbao_case_law_links
                   (doc_id, law_id, node_id, article_num, raw_ref, ref_law_title)
                   VALUES (?,?,?,?,?,?)""",
                links_for_doc
            )
            total_links += len(links_for_doc)

    return total_links


def build_fts(conn: sqlite3.Connection):
    conn.execute("INSERT INTO gongbao_docs_fts(gongbao_docs_fts) VALUES('rebuild')")
    conn.execute("INSERT INTO gongbao_docs_fts(gongbao_docs_fts) VALUES('optimize')")


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='构建公报补充数据库')
    parser.add_argument('--drop', action='store_true', help='先删除旧表再重建')
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f'✗ 找不到 {DB_PATH}，请先运行主 pipeline')
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    if args.drop:
        print('删除旧表...')
        conn.executescript(DROP_SQL)

    print('建表...')
    conn.executescript(SCHEMA)

    existing_docs = conn.execute("SELECT COUNT(*) FROM gongbao_docs").fetchone()[0]
    if existing_docs > 0:
        print(f'⚠ 表中已有数据（gongbao_docs={existing_docs}），使用 --drop 先清空再重建')
        conn.close()
        return

    print('\n导入 gongbao_docs（裁判文书 + 指导案例 + 司法文件）...')
    n_docs = import_docs(conn)
    print(f'  共导入 {n_docs} 条')

    print('\n建立法条引用关联...')
    n_links = build_links(conn)
    print(f'  共建立 {n_links} 条法条关联')

    print('\n构建 FTS 索引...')
    build_fts(conn)

    conn.commit()
    conn.close()

    print(f'\n完成：')
    print(f'  gongbao_docs: {n_docs} 条（裁判文书+指导案例+司法文件）')
    print(f'  gongbao_case_law_links: {n_links} 条')
    print(f'  → {DB_PATH}')


def run(drop: bool = True):
    """供 pipeline.py 调用的入口。"""
    if not DB_PATH.exists():
        print(f'✗ 找不到 {DB_PATH}，请先运行主 pipeline')
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    if drop:
        print('  删除旧公报表...')
        conn.executescript(DROP_SQL)

    conn.executescript(SCHEMA)

    print('\n  导入 gongbao_docs（裁判文书 + 指导案例 + 司法文件）...')
    n_docs = import_docs(conn)
    print(f'  共导入 {n_docs} 条')

    print('\n  建立法条引用关联...')
    n_links = build_links(conn)
    print(f'  共建立 {n_links} 条法条关联')

    print('\n  构建 FTS 索引...')
    build_fts(conn)

    conn.commit()
    conn.close()

    print(f'\n  gongbao_docs: {n_docs} 条（裁判文书+指导案例+司法文件）')
    print(f'  gongbao_case_law_links: {n_links} 条')


if __name__ == '__main__':
    main()
