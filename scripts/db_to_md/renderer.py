#!/usr/bin/env python3
"""
DB → Markdown
用法：python3 -m db_to_md.renderer
"""

import re
import shutil
import sqlite3
from pathlib import Path

from config import DB_PATH, MD_DIR

LAW_KEYS = ['id', 'title', 'filename', 'category', 'legal_domain',
            'pub_date', 'effective_date', 'promulgation_info',
            'issuing_org', 'doc_number', 'total_articles']


def _out_dir(md_dir: Path, law: dict) -> Path:
    domain   = law['legal_domain'] or '其他'
    category = law['category'] or ''
    if category in ('司法解释', '法律解释'):
        return md_dir / domain / category
    return md_dir / domain


def _law_md_path(md_dir: Path, law: dict) -> Path:
    return _out_dir(md_dir, law) / (law['filename'] + '.md')


def _build_ref_map(conn, law_id: int, law_info: dict, md_dir: Path) -> dict[str, str]:
    """
    Returns {raw_text → markdown_link_text} for all resolved references
    in the given law. Handles both self_ref and cross_law.
    """
    rows = conn.execute(
        """SELECT ar.raw_text, ar.ref_type, ar.to_law_id, ar.to_article_num,
                  l.filename, l.legal_domain, l.category
           FROM article_references ar
           JOIN laws l ON ar.to_law_id = l.id
           WHERE ar.from_law_id = ? AND ar.resolved = 1""",
        (law_id,)
    ).fetchall()

    ref_map = {}
    for raw_text, ref_type, to_law_id, to_article_num, to_filename, to_domain, to_category in rows:
        if not raw_text:
            continue
        anchor = f'#art-{to_article_num}'
        if ref_type == 'self_ref':
            ref_map[raw_text] = f'[{raw_text}]({anchor})'
        else:
            # compute relative path from this file's dir to target file
            from_dir = _out_dir(md_dir, law_info)
            to_law   = {'legal_domain': to_domain, 'category': to_category,
                        'filename': to_filename}
            to_path  = _law_md_path(md_dir, to_law)
            try:
                rel = Path(to_path).relative_to(md_dir)
                # build relative path from from_dir to to_path
                from_depth = len(_out_dir(md_dir, law_info).relative_to(md_dir).parts)
                prefix = '../' * from_depth
                ref_map[raw_text] = f'[{raw_text}]({prefix}{rel}{anchor})'
            except ValueError:
                ref_map[raw_text] = f'[{raw_text}]({anchor})'
    return ref_map


def _apply_refs(content: str, ref_map: dict) -> str:
    """Replace all raw_text occurrences in content with their markdown links.
    Sorts by length descending to avoid partial matches."""
    if not ref_map:
        return content
    for raw in sorted(ref_map, key=len, reverse=True):
        if raw in content:
            content = content.replace(raw, ref_map[raw])
    return content


def law_to_md(law: dict, nodes: list, ref_map: dict) -> str:
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
        t          = node['type']
        content    = (node['content'] or '').strip()
        art_num    = node['article_num']
        if not content:
            continue
        if t == 'part':
            lines.append(f'## {content}')
        elif t == 'chapter':
            lines.append(f'### {content}')
        elif t == 'section':
            lines.append(f'#### {content}')
        else:
            # article: add anchor + apply hyperlinks
            anchor_tag = f'<a id="art-{art_num}"></a>' if art_num else ''
            linked = _apply_refs(content, ref_map)
            lines.append(f'{anchor_tag}{linked}')
        lines.append('')

    return '\n'.join(lines)


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
            'SELECT type, content, article_num FROM nodes WHERE law_id=? ORDER BY global_order',
            (law['id'],)
        ).fetchall()
        node_list = [{'type': r[0], 'content': r[1], 'article_num': r[2]} for r in nodes]

        ref_map = _build_ref_map(conn, law['id'], law, md_dir)

        (out_dir / (law['filename'] + '.md')).write_text(
            law_to_md(law, node_list, ref_map), encoding='utf-8'
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
