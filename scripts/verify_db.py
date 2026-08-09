"""
验证 law_content.db 与 JSON 文件的一致性
对每部法律检查：
1. 元数据（title, category, legal_domain, pub_date, effective_date, total_articles）
2. 节点数量（parts/chapters/sections/articles）
3. 条文内容逐条对比（article_number + content）
4. global_order 顺序与 JSON 深度优先顺序一致
"""

import json
import glob
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'json_to_db'))
sys.path.insert(0, str(Path(__file__).parent))
try:
    from docx_to_json.converter import clean_article_content
except ImportError:
    def clean_article_content(text: str) -> str:
        return text

BASE_DIR = Path(__file__).parent.parent
DB_PATH  = str(BASE_DIR / 'law_content.db')
JSON_DIR = str(BASE_DIR / 'json')


def _normalize_title(title: str) -> str:
    """规范化标题：去除空格/全角空格/顿号等标点，便于匹配同标题不同版本"""
    import re
    return re.sub(r'[\s\u3000、，。·:：()（）\-—]+', '', title or '')


def _count_normalized_title(conn, norm_title: str) -> int:
    if not norm_title:
        return 0
    # 全表扫描标题规范化后比较（laws 仅 ~2200 行，性能可接受）
    rows = conn.execute('SELECT title FROM laws').fetchall()
    return sum(1 for (t,) in rows if _normalize_title(t) == norm_title)


def flatten_json(data):
    """把 JSON 里的编/章/节/条按 global_order 展开，返回 list of dict"""
    nodes = []

    def add_articles(items, parent_type):
        for art in items:
            nodes.append({
                'type': 'article',
                'article_number': art.get('title', '').strip().rstrip('　 '),
                'content': art.get('content', ''),
                'global_order': art.get('global_order'),
            })

    def add_section(sec):
        nodes.append({'type': 'section', 'title': sec.get('title','').strip(), 'global_order': sec.get('global_order')})
        add_articles(sec.get('articles', []), 'section')

    def add_chapter(ch):
        # builder.py 对 _DIRECT_ 占位章不创建节点，文章直接挂到父级 → 跳过占位章本身
        if (ch.get('title') or '').startswith('_DIRECT_'):
            add_articles(ch.get('articles', []), 'chapter')
            return
        nodes.append({'type': 'chapter', 'title': ch.get('title','').strip(), 'global_order': ch.get('global_order')})
        for sec in ch.get('sections', []):
            add_section(sec)
        add_articles(ch.get('articles', []), 'chapter')

    def add_part(pt):
        nodes.append({'type': 'part', 'title': pt.get('title','').strip(), 'global_order': pt.get('global_order')})
        for ch in pt.get('chapters', []):
            add_chapter(ch)

    if 'parts' in data:
        for pt in data['parts']:
            add_part(pt)
    else:
        for ch in data.get('chapters', []):
            add_chapter(ch)

    # builder.py 按 global_order 排序写入；full_text 结构只存 1 个 article
    if not nodes:
        full_text = (data.get('full_text') or '').strip()
        if full_text:
            return [{'type': 'article', 'article_number': '',
                     'content': clean_article_content(full_text), 'global_order': 1}]
        return nodes

    return sorted(nodes, key=lambda n: n['global_order'] if n['global_order'] is not None else float('inf'))


def flatten_db(conn, law_id):
    """从数据库按 global_order 取出所有节点"""
    rows = conn.execute(
        """SELECT type, title, article_number, content, global_order
           FROM nodes WHERE law_id = ? ORDER BY global_order""",
        (law_id,)
    ).fetchall()
    result = []
    for type_, title, article_number, content, global_order in rows:
        result.append({
            'type': type_,
            'title': (title or '').strip(),
            'article_number': (article_number or '').strip(),
            'content': content or '',
            'global_order': global_order,
        })
    return result


def compare(json_path, conn):
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    title = data.get('title', '')
    filename = Path(json_path).stem

    # Find law in DB by filename (unique, reliable)
    row = conn.execute(
        "SELECT id FROM laws WHERE filename=?", (filename,)
    ).fetchone()
    if not row:
        # 可能是被替代的旧版本（DB 以带日期前缀、顿号/空格差异的活跃版本存储）
        norm_title = _normalize_title(data.get('title', ''))
        legacy = _count_normalized_title(conn, norm_title)
        if legacy > 0:
            return None  # 同标题活跃版本已入库，旧版本不算失败
        return f'NOT FOUND: {title} ({filename})'

    law_id = row[0]
    errors = []

    # 1. 元数据检查
    law = conn.execute(
        "SELECT category, legal_domain, pub_date, effective_date, total_articles FROM laws WHERE id=?",
        (law_id,)
    ).fetchone()
    for db_val, json_key, label in [
        (law[0], 'category', 'category'),
        (law[1], 'legal_domain', 'legal_domain'),
        (law[2], 'pub_date', 'pub_date'),
        (law[3], 'effective_date', 'effective_date'),
        (law[4], 'total_articles', 'total_articles'),
    ]:
        json_val = data.get(json_key)
        if str(db_val or '') != str(json_val or ''):
            errors.append(f'  元数据 {label}: DB={db_val!r} JSON={json_val!r}')

    # 2. 节点对比
    json_nodes = flatten_json(data)
    db_nodes = flatten_db(conn, law_id)

    if len(json_nodes) != len(db_nodes):
        errors.append(f'  节点数量不符: JSON={len(json_nodes)} DB={len(db_nodes)}')
        # 按类型细分
        for t in ['part', 'chapter', 'section', 'article']:
            jc = sum(1 for n in json_nodes if n['type'] == t)
            dc = sum(1 for n in db_nodes if n['type'] == t)
            if jc != dc:
                errors.append(f'    {t}: JSON={jc} DB={dc}')
        return '\n'.join(errors)

    # 3. 逐节点对比
    mismatch_count = 0
    for i, (jn, dn) in enumerate(zip(json_nodes, db_nodes)):
        if jn['type'] != dn['type']:
            errors.append(f'  节点[{i}] type不符: JSON={jn["type"]} DB={dn["type"]}')
            mismatch_count += 1
        elif jn['type'] == 'article':
            if jn['content'] != dn['content']:
                errors.append(f'  条文内容不符: {jn["article_number"]} (global_order={jn["global_order"]})')
                errors.append(f'    JSON: {jn["content"][:60]}')
                errors.append(f'    DB:   {dn["content"][:60]}')
                mismatch_count += 1
            if jn['article_number'] != dn['article_number']:
                errors.append(f'  条文编号不符: JSON={jn["article_number"]!r} DB={dn["article_number"]!r}')
                mismatch_count += 1
        else:
            if jn['title'] != dn['title']:
                errors.append(f'  {jn["type"]}标题不符: JSON={jn["title"]!r} DB={dn["title"]!r}')
                mismatch_count += 1
        if mismatch_count >= 5:
            errors.append('  ...(超过5处差异，停止详细对比)')
            break

    # 4. global_order 严格递增（允许 _DIRECT_ 占位章留下的空洞，但禁止重复/乱序）
    db_orders = [n['global_order'] for n in db_nodes]
    if not all(b is not None and (i == 0 or b > db_orders[i - 1]) for i, b in enumerate(db_orders)):
        errors.append(f'  global_order 非严格递增或重复')
    elif db_orders and db_orders[0] != 1:
        errors.append(f'  global_order 不从 1 开始')

    return '\n'.join(errors) if errors else None


def main():
    conn = sqlite3.connect(DB_PATH)
    paths = sorted([
        p for p in glob.glob(f'{JSON_DIR}/**/*.json', recursive=True)
        if 'index' not in p
    ])

    ok = error = not_found = 0
    error_details = []

    for path in paths:
        result = compare(path, conn)
        if result is None:
            ok += 1
        elif result.startswith('NOT FOUND'):
            not_found += 1
            error_details.append(f'{Path(path).name}:\n  {result}')
        else:
            error += 1
            error_details.append(f'{Path(path).name}:\n{result}')

    conn.close()

    print(f'验证完成: 共 {len(paths)} 个文件')
    print(f'  ✓ 一致: {ok}')
    print(f'  ✗ 有差异: {error}')
    print(f'  ? 未找到: {not_found}')

    if error_details:
        print(f'\n差异详情（共 {len(error_details)} 个）:')
        for d in error_details[:30]:
            print(d)
        if len(error_details) > 30:
            print(f'...（共 {len(error_details)} 个）')

    # ── 英文覆盖率检查 ──
    print(f'\n英文覆盖率检查:')
    conn2 = sqlite3.connect(DB_PATH)
    en_failures = []
    # laws.title_en (只统计现行法律)
    total_laws = conn2.execute("SELECT COUNT(*) FROM laws WHERE source='flk' AND is_current=1").fetchone()[0]
    en_laws = conn2.execute("SELECT COUNT(*) FROM laws WHERE source='flk' AND is_current=1 AND title_en IS NOT NULL AND title_en != ''").fetchone()[0]
    pct_laws = round(100.0 * en_laws / total_laws, 1) if total_laws else 0
    flag_laws = '⚠️' if pct_laws < 95 else '✅'
    print(f'  {flag_laws} laws.title_en (active): {en_laws}/{total_laws} ({pct_laws}%)')
    if pct_laws < 95:
        en_failures.append(f'laws.title_en 覆盖率 {pct_laws}% < 95%（{en_laws}/{total_laws}）')

    # 结构节点 content_en (part/chapter/section)
    for ntype in ('part', 'chapter', 'section'):
        total_n = conn2.execute("SELECT COUNT(*) FROM nodes WHERE type=? AND law_id IN (SELECT id FROM laws WHERE is_current=1)", (ntype,)).fetchone()[0]
        en_n = conn2.execute("SELECT COUNT(*) FROM nodes WHERE type=? AND content_en IS NOT NULL AND content_en != '' AND law_id IN (SELECT id FROM laws WHERE is_current=1)", (ntype,)).fetchone()[0]
        pct_n = round(100.0 * en_n / total_n, 1) if total_n else 0
        flag_n = '⚠️' if pct_n < 95 else '✅'
        print(f'  {flag_n} nodes.content_en ({ntype}): {en_n}/{total_n} ({pct_n}%)')
        if pct_n < 95:
            en_failures.append(f'nodes.content_en ({ntype}) 覆盖率 {pct_n}% < 95%（{en_n}/{total_n}）')

    # 文章节点 content_en
    total_arts = conn2.execute("SELECT COUNT(*) FROM nodes WHERE type='article' AND law_id IN (SELECT id FROM laws WHERE is_current=1)").fetchone()[0]
    en_arts = conn2.execute("SELECT COUNT(*) FROM nodes WHERE type='article' AND content_en IS NOT NULL AND content_en != '' AND law_id IN (SELECT id FROM laws WHERE is_current=1)").fetchone()[0]
    pct_arts = round(100.0 * en_arts / total_arts, 1) if total_arts else 0
    flag_arts = '⚠️' if pct_arts < 95 else '✅'
    print(f'  {flag_arts} nodes.content_en (article): {en_arts}/{total_arts} ({pct_arts}%)')
    if pct_arts < 95:
        en_failures.append(f'nodes.content_en (article) 覆盖率 {pct_arts}% < 95%（{en_arts}/{total_arts}）')

    conn2.close()

    # ── 失败即退出：任何校验失败都必须让 pipeline 报错，不能静默通过 ──
    all_failures = []
    if error > 0:
        all_failures.append(f'DB 与 JSON 有 {error} 处差异')
    if not_found > 0:
        all_failures.append(f'DB 中找不到 {not_found} 部 JSON 中的法律')
    if en_failures:
        all_failures.extend(en_failures)
    if all_failures:
        print(f'\n❌ 验证失败：')
        for f in all_failures:
            print(f'  - {f}')
        sys.exit(1)
    print('\n✅ 全部验证通过')


if __name__ == '__main__':
    main()
