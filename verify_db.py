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
from pathlib import Path

DB_PATH = '/Users/doxie/laws_data/law_content.db'
JSON_DIR = '/Users/doxie/laws_data/json'


def flatten_json(data):
    """把 JSON 里的编/章/节/条按深度优先顺序展开，返回 list of dict"""
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

    return nodes


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
        return f'NOT FOUND: {title} ({version_date})'

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

    # 4. global_order 连续性
    db_orders = [n['global_order'] for n in db_nodes]
    if db_orders != list(range(1, len(db_orders) + 1)):
        errors.append(f'  global_order 不连续')

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


if __name__ == '__main__':
    main()
