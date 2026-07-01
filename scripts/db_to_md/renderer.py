#!/usr/bin/env python3
"""
DB → Markdown
目录结构由 law_menu.json 驱动，与 iOS 保持一致。
用法：python3 -m db_to_md.renderer
"""

import json
import re
import shutil
import sqlite3
from pathlib import Path

from config import DB_PATH, MD_DIR, MENU_PATH

LAW_KEYS = ['id', 'title', 'filename', 'category', 'legal_domain',
            'pub_date', 'effective_date', 'promulgation_info',
            'issuing_org', 'doc_number', 'total_articles', 'subject_area']


def _subgroup_parts(subgroup: str) -> list[str]:
    """'行政法规/交通运输' → ['行政法规', '交通运输']"""
    return subgroup.split('/') if subgroup else []


def _out_dir(md_dir: Path, group: str, subgroup: str) -> Path:
    if subgroup:
        return md_dir / group / Path(*_subgroup_parts(subgroup))
    return md_dir / group


def _md_filename(law: dict) -> str:
    return law['title']


def _law_md_path(md_dir: Path, group: str, subgroup: str, law: dict) -> Path:
    return _out_dir(md_dir, group, subgroup) / (_md_filename(law) + '.md')


def _build_ref_map(conn, law_id: int, from_group: str, from_subgroup: str,
                   md_dir: Path, law_location: dict) -> dict[str, str]:
    """
    Returns {raw_text → markdown_link_text} for all resolved references.
    law_location: {law_id → (group, subgroup)} 供查目标路径。
    """
    rows = conn.execute(
        """SELECT ar.raw_text, ar.ref_type, ar.to_law_id, ar.to_article_num,
                  l.title
           FROM article_references ar
           JOIN laws l ON ar.to_law_id = l.id
           WHERE ar.from_law_id = ? AND ar.resolved = 1""",
        (law_id,)
    ).fetchall()

    ref_map = {}
    for raw_text, ref_type, to_law_id, to_article_num, to_title in rows:
        if not raw_text:
            continue
        anchor = f'#art-{to_article_num}'
        if ref_type == 'self_ref':
            ref_map[raw_text] = f'[{raw_text}]({anchor})'
        else:
            to_loc = law_location.get(to_law_id)
            if to_loc is None:
                ref_map[raw_text] = f'[{raw_text}]({anchor})'
                continue
            to_group, to_subgroup = to_loc
            from_dir  = _out_dir(md_dir, from_group, from_subgroup)
            to_path   = _out_dir(md_dir, to_group, to_subgroup) / (to_title + '.md')
            try:
                rel        = to_path.relative_to(md_dir)
                from_depth = len(from_dir.relative_to(md_dir).parts)
                prefix     = '../' * from_depth
                ref_map[raw_text] = f'[{raw_text}]({prefix}{rel}{anchor})'
            except ValueError:
                ref_map[raw_text] = f'[{raw_text}]({anchor})'
    return ref_map


def _apply_refs(content: str, ref_map: dict) -> str:
    if not ref_map:
        return content
    for raw in sorted(ref_map, key=len, reverse=True):
        if raw in content:
            content = content.replace(raw, ref_map[raw])
    return content


def law_to_md(law: dict, nodes: list, ref_map: dict,
              cited_by: dict, law_map: dict,
              md_dir: Path, from_group: str, from_subgroup: str,
              law_location: dict) -> str:
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
        content_en = (node.get('content_en') or '').strip()
        art_num = node['article_num']
        if not content:
            continue
        if t == 'part':
            lines.append(f'## {content}')
        elif t == 'chapter':
            lines.append(f'### {content}')
        elif t == 'section':
            lines.append(f'#### {content}')
        else:
            # 渲染中文条文
            anchor_tag = f'<a id="art-{art_num}"></a>' if art_num else ''
            linked     = _apply_refs(content, ref_map)
            sups       = _cited_by_superscripts(
                law['id'], art_num, cited_by,
                from_group, from_subgroup, law_map, md_dir, law_location
            ) if art_num else ''
            linked_br  = linked.replace('\n', '  \n')
            lines.append(f'{anchor_tag}{linked_br}{sups}')
            lines.append('')

            # 渲染英文翻译（如果有）
            if content_en:
                # 提取 Article X 前缀（如果有）
                import re
                art_en_match = re.match(r'(Article \d+)', content_en)
                if art_en_match:
                    art_en_label = art_en_match.group(0)
                    en_body = content_en[len(art_en_label):].strip()
                    en_with_br = en_body.replace('\n', '  \n')
                    lines.append(f'**{art_en_label}** {en_with_br}')
                else:
                    # 没有 Article 前缀，自己添加
                    en_with_br = content_en.replace('\n', '  \n')
                    lines.append(f'**Article {art_num}** {en_with_br}')
        lines.append('')

    return '\n'.join(lines)


def _build_cited_by_map(conn) -> dict:
    rows = conn.execute(
        """SELECT ar.to_law_id, ar.to_article_num,
                  ar.from_law_id, ar.from_article_num,
                  lf.title
           FROM article_references ar
           JOIN laws lf ON ar.from_law_id = lf.id
           WHERE ar.resolved = 1 AND ar.ref_type = 'cross_law'
             AND ar.to_article_num IS NOT NULL"""
    ).fetchall()

    cited_by = {}
    for to_law_id, to_art_num, from_law_id, from_art_num, from_title in rows:
        key = (to_law_id, to_art_num)
        cited_by.setdefault(key, []).append((from_law_id, from_art_num, from_title))
    return cited_by


def _cited_by_superscripts(to_law_id, art_num, cited_by: dict,
                            from_group: str, from_subgroup: str,
                            law_map: dict, md_dir: Path,
                            law_location: dict) -> str:
    citations = cited_by.get((to_law_id, art_num), [])
    if not citations:
        return ''
    parts = []
    for i, (from_law_id, from_art_num, from_title) in enumerate(citations, 1):
        anchor   = f'#art-{from_art_num}'
        from_loc = law_location.get(from_law_id)
        if from_loc is None:
            parts.append(f'<sup>[{i}]</sup>')
            continue
        f_group, f_subgroup = from_loc
        to_path    = _out_dir(md_dir, f_group, f_subgroup) / (from_title + '.md')
        from_depth = len(_out_dir(md_dir, from_group, from_subgroup).relative_to(md_dir).parts)
        prefix     = '../' * from_depth
        try:
            rel  = to_path.relative_to(md_dir)
            link = f'{prefix}{rel}{anchor}'
        except ValueError:
            link = anchor
        art_label = f'第{from_art_num}条' if from_art_num else ''
        tooltip   = f'被《{from_title}》{art_label}引用'
        parts.append(f'<sup><a href="{link}" title="{tooltip}">[{i}]</a></sup>')
    return '&thinsp;' + '&thinsp;'.join(parts)


def build_markdown(db_path: Path = DB_PATH, md_dir: Path = MD_DIR,
                   menu_path: Path = MENU_PATH):
    # 读 law_menu.json
    if not menu_path.exists():
        raise FileNotFoundError(f'找不到 {menu_path}，请先运行 export_menu.py')
    menu = json.loads(menu_path.read_text(encoding='utf-8'))

    # 从 menu 中收集所有 (group, subgroup, law_id) 映射
    # law_location: {law_id → (group, subgroup)}
    law_location: dict[int, tuple[str, str]] = {}
    for grp in menu['groups']:
        group = grp['label']
        for sub in grp['subgroups']:
            subgroup = sub['label']
            for lid in (law['id'] if isinstance(law, dict) else law for law in sub.get('lawIds', sub.get('laws', []))):
                law_location[lid] = (group, subgroup)

    # 清理旧目录：menu 里的所有顶层 group + 已知旧名称
    known_groups = {grp['label'] for grp in menu['groups']}
    old_names = {
        '刑法', '宪法相关法', '民法典', '民法商法', '社会法',
        '经济法', '行政法', '诉讼与非诉讼程序法',
        '经济·税务·金融', '劳动·社会保障',
    }
    for name in known_groups | old_names:
        p = md_dir / name
        if p.exists():
            shutil.rmtree(p)

    conn = sqlite3.connect(db_path)

    # 查所有现行法律元数据
    laws_rows = conn.execute(
        f"SELECT {', '.join(LAW_KEYS)} FROM laws WHERE is_current=1"
    ).fetchall()
    law_map: dict[int, dict] = {
        r[0]: dict(zip(LAW_KEYS, r)) for r in laws_rows
    }

    cited_by = _build_cited_by_map(conn)

    written = 0
    for grp in menu['groups']:
        group = grp['label']
        for sub in grp['subgroups']:
            subgroup = sub['label']
            out_dir  = _out_dir(md_dir, group, subgroup)
            out_dir.mkdir(parents=True, exist_ok=True)

            for law_id in (law['id'] if isinstance(law, dict) else law for law in sub.get('lawIds', sub.get('laws', []))):
                law = law_map.get(law_id)
                if law is None:
                    continue

                nodes_rows = conn.execute(
                    'SELECT type, content, article_num, content_en FROM nodes WHERE law_id=? ORDER BY global_order',
                    (law_id,)
                ).fetchall()
                node_list = [{'type': r[0], 'content': r[1], 'article_num': r[2], 'content_en': r[3]}
                             for r in nodes_rows]

                ref_map = _build_ref_map(conn, law_id, group, subgroup,
                                         md_dir, law_location)

                md = law_to_md(law, node_list, ref_map, cited_by, law_map,
                               md_dir, group, subgroup, law_location)
                (out_dir / (_md_filename(law) + '.md')).write_text(md, encoding='utf-8')
                written += 1

    conn.close()
    print(f'Markdown 生成完成：{written} 个文件，输出目录：{md_dir}')
    for grp in menu['groups']:
        d = md_dir / grp['label']
        total = sum(1 for _ in d.rglob('*.md')) if d.exists() else 0
        print(f'  {grp["label"]}/  共 {total} 个')


def run():
    print('\n=== 数据库 → Markdown ===')
    build_markdown()


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
