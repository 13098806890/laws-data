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
            'issuing_org', 'doc_number', 'total_articles', 'subject_area']


def _out_dir(md_dir: Path, law: dict) -> Path:
    group    = law.get('display_group') or law.get('legal_domain') or '其他'
    subgroup = law.get('display_subgroup') or ''
    if subgroup:
        # subgroup 可能包含 '/'（如 '行政法规/交通运输'），直接拆路径
        parts = subgroup.split('/')
        return md_dir / group / Path(*parts)
    return md_dir / group


def _md_filename(law: dict) -> str:
    return law['title']


def _law_md_path(md_dir: Path, law: dict) -> Path:
    return _out_dir(md_dir, law) / (_md_filename(law) + '.md')


def _build_ref_map(conn, law_id: int, law_info: dict, md_dir: Path) -> dict[str, str]:
    """
    Returns {raw_text → markdown_link_text} for all resolved references
    in the given law. Handles both self_ref and cross_law.
    """
    rows = conn.execute(
        """SELECT ar.raw_text, ar.ref_type, ar.to_law_id, ar.to_article_num,
                  l.filename, l.legal_domain, l.category, l.title
           FROM article_references ar
           JOIN laws l ON ar.to_law_id = l.id
           WHERE ar.from_law_id = ? AND ar.resolved = 1""",
        (law_id,)
    ).fetchall()

    ref_map = {}
    for raw_text, ref_type, to_law_id, to_article_num, to_filename, to_domain, to_category, to_title in rows:
        if not raw_text:
            continue
        anchor = f'#art-{to_article_num}'
        if ref_type == 'self_ref':
            ref_map[raw_text] = f'[{raw_text}]({anchor})'
        else:
            from_dir = _out_dir(md_dir, law_info)
            to_law   = {'legal_domain': to_domain, 'category': to_category,
                        'filename': to_filename, 'title': to_title}
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


def law_to_md(law: dict, nodes: list, ref_map: dict,
              cited_by: dict, law_map: dict, md_dir: Path) -> str:
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
            # article: add anchor + apply outgoing hyperlinks + cited-by superscripts
            anchor_tag = f'<a id="art-{art_num}"></a>' if art_num else ''
            linked     = _apply_refs(content, ref_map)
            sups       = _cited_by_superscripts(law['id'], art_num, cited_by,
                                                law, law_map, md_dir) if art_num else ''
            # Use hard line breaks (two trailing spaces) so sub-clauses render on separate lines
            linked_br  = linked.replace('\n', '  \n')
            lines.append(f'{anchor_tag}{linked_br}{sups}')
        lines.append('')

    return '\n'.join(lines)


def _build_cited_by_map(conn, md_dir: Path, law_map: dict) -> dict:
    """
    Build a reverse-citation map:
    {(to_law_id, to_article_num) → [(from_law_id, from_article_num, from_filename, from_domain, from_category), ...]}
    Only resolved cross-law citations (self-refs don't need incoming markers).
    """
    rows = conn.execute(
        """SELECT ar.to_law_id, ar.to_article_num,
                  ar.from_law_id, ar.from_article_num,
                  lf.filename, lf.legal_domain, lf.category
           FROM article_references ar
           JOIN laws lf ON ar.from_law_id = lf.id
           WHERE ar.resolved = 1 AND ar.ref_type = 'cross_law'
             AND ar.to_article_num IS NOT NULL"""
    ).fetchall()

    cited_by = {}
    for to_law_id, to_art_num, from_law_id, from_art_num, from_fn, from_domain, from_cat in rows:
        key = (to_law_id, to_art_num)
        cited_by.setdefault(key, []).append(
            (from_law_id, from_art_num, from_fn, from_domain, from_cat)
        )
    return cited_by


def _cited_by_superscripts(to_law_id, art_num, cited_by: dict,
                            law_info: dict, law_map: dict, md_dir: Path) -> str:
    """Return superscript links like <sup>[1](link)</sup> with spacing and tooltips."""
    citations = cited_by.get((to_law_id, art_num), [])
    if not citations:
        return ''
    parts = []
    for i, (from_law_id, from_art_num, from_fn, from_domain, from_cat) in enumerate(citations, 1):
        anchor        = f'#art-{from_art_num}'
        from_law_info = law_map.get(from_law_id, {})
        from_law      = {'legal_domain': from_domain, 'category': from_cat,
                         'filename': from_fn, 'title': from_law_info.get('title', from_fn)}
        to_path    = _law_md_path(md_dir, from_law)
        from_depth = len(_out_dir(md_dir, law_info).relative_to(md_dir).parts)
        prefix     = '../' * from_depth
        try:
            rel  = to_path.relative_to(md_dir)
            link = f'{prefix}{rel}{anchor}'
        except ValueError:
            link = anchor
        law_title = from_law_info.get('title') or from_fn
        art_label = f'第{from_art_num}条' if from_art_num else ''
        tooltip   = f'被《{law_title}》{art_label}引用'
        parts.append(f'<sup><a href="{link}" title="{tooltip}">[{i}]</a></sup>')
    return '&thinsp;' + '&thinsp;'.join(parts)


def build_markdown(db_path: Path = DB_PATH, md_dir: Path = MD_DIR):
    KNOWN_GROUPS = {'宪法与国家机构', '民事与商事', '刑事', '行政与公法',
                    '经济·税务·金融', '劳动·社会保障', '诉讼与司法程序', '其他'}
    # 旧的 legal_domain 目录名，首次迁移时一并清理
    OLD_DOMAINS = {'刑法', '宪法相关法', '民法典', '民法商法', '社会法',
                   '经济法', '行政法', '诉讼与非诉讼程序法'}
    for name in KNOWN_GROUPS | OLD_DOMAINS:
        p = md_dir / name
        if p.exists():
            shutil.rmtree(p)

    conn = sqlite3.connect(db_path)
    laws = conn.execute(
        f"""SELECT {", ".join(f"l.{k}" for k in LAW_KEYS)},
               COALESCE(dgm.display_group, '其他') AS display_group,
               COALESCE(dgm.display_subgroup, '') AS display_subgroup
           FROM laws l
           LEFT JOIN display_group_map dgm ON l.id = dgm.law_id
           WHERE l.is_current=1 ORDER BY l.id"""
    ).fetchall()

    ALL_KEYS = LAW_KEYS + ['display_group', 'display_subgroup']
    # build id→law_info lookup and cited-by map before rendering
    law_map  = {dict(zip(ALL_KEYS, r))['id']: dict(zip(ALL_KEYS, r)) for r in laws}
    cited_by = _build_cited_by_map(conn, md_dir, law_map)

    domain_unknown = 0
    for row in laws:
        law = dict(zip(ALL_KEYS, row))
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

        (out_dir / (_md_filename(law) + '.md')).write_text(
            law_to_md(law, node_list, ref_map, cited_by, law_map, md_dir), encoding='utf-8'
        )

    conn.close()
    print(f'Markdown 生成完成，输出目录：{md_dir}')
    print(f'  未知 legal_domain（归入"其他"）：{domain_unknown}')
    for d in sorted(d for d in md_dir.iterdir() if d.is_dir() and d.name in KNOWN_GROUPS):
        total = sum(1 for _ in d.rglob('*.md'))
        print(f'  {d.name}/  共 {total} 个')


def run():
    print('\n=== 数据库 → Markdown ===')
    build_markdown()


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
