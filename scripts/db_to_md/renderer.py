#!/usr/bin/env python3
"""
DB → Markdown
用法：python3 -m db_to_md.renderer
"""

import shutil
import sqlite3
from pathlib import Path

from config import DB_PATH, MD_DIR

LAW_KEYS = ['id', 'title', 'filename', 'category', 'legal_domain',
            'pub_date', 'effective_date', 'promulgation_info',
            'issuing_org', 'doc_number', 'total_articles']


def law_to_md(law: dict, nodes: list) -> str:
    lines = []
    lines.append(f'# {law["title"]}')
    lines.append('')

    meta = []
    if law.get('category'):       meta.append(f'**分类**：{law["category"]}')
    if law.get('legal_domain'):   meta.append(f'**法律部门**：{law["legal_domain"]}')
    if law.get('issuing_org'):    meta.append(f'**发布机关**：{law["issuing_org"]}')
    if law.get('doc_number'):     meta.append(f'**发文字号**：{law["doc_number"]}')
    if law.get('pub_date'):       meta.append(f'**公布日期**：{law["pub_date"]}')
    if law.get('effective_date'): meta.append(f'**生效日期**：{law["effective_date"]}')
    if meta:
        lines.append('  \n'.join(meta))
        lines.append('')

    if law.get('promulgation_info'):
        lines.append(f'> {law["promulgation_info"]}')
        lines.append('')

    lines.append('---')
    lines.append('')

    for node in nodes:
        t       = node['type']
        content = (node['content'] or '').strip()
        if not content:
            continue
        if t == 'part':
            lines.append(f'## {content}')
        elif t == 'chapter':
            lines.append(f'### {content}')
        elif t == 'section':
            lines.append(f'#### {content}')
        else:
            lines.append(content)
        lines.append('')

    return '\n'.join(lines)


def _out_dir(md_dir: Path, law: dict) -> Path:
    domain   = law['legal_domain'] or '其他'
    category = law['category'] or ''
    if category in ('司法解释', '法律解释'):
        return md_dir / domain / category
    return md_dir / domain


def build_markdown(db_path: Path = DB_PATH, md_dir: Path = MD_DIR):
    if md_dir.exists():
        shutil.rmtree(md_dir)

    conn = sqlite3.connect(db_path)
    laws = conn.execute(
        f'SELECT {", ".join(LAW_KEYS)} FROM laws ORDER BY id'
    ).fetchall()

    domain_unknown = 0
    for row in laws:
        law = dict(zip(LAW_KEYS, row))
        if not law['legal_domain']:
            domain_unknown += 1

        out_dir = _out_dir(md_dir, law)
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
        md_count  = len(list(d.glob('*.md')))
        sub_count = sum(len(list(s.glob('*.md'))) for s in d.iterdir() if s.is_dir())
        total_str = f'{md_count} 个' if not sub_count else f'{md_count} 个 + 子分类 {sub_count} 个'
        print(f'  {d.name}/  {total_str}')


def run():
    print('\n=== 数据库 → Markdown ===')
    build_markdown()


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
