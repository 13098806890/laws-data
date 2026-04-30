#!/usr/bin/env python3
"""
JSON → Markdown
按 legal_domain 分类建文件夹，每部法律生成一个 .md 文件
用法：python3 scripts/json_to_md.py
"""

import json
import glob
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
JSON_DIR = BASE_DIR / 'json'
MD_DIR   = BASE_DIR / 'markdown'


def law_to_md(data: dict) -> str:
    lines = []

    # ── 元数据头部 ────────────────────────────────────────────────────────────
    lines.append(f'# {data["title"]}')
    lines.append('')

    meta = []
    if data.get('category'):        meta.append(f'**分类**：{data["category"]}')
    if data.get('legal_domain'):    meta.append(f'**法律部门**：{data["legal_domain"]}')
    if data.get('pub_date'):        meta.append(f'**公布日期**：{data["pub_date"]}')
    if data.get('effective_date'):  meta.append(f'**生效日期**：{data["effective_date"]}')
    if data.get('total_articles'):  meta.append(f'**条文数**：{data["total_articles"]}')
    if meta:
        lines.append('  \n'.join(meta))
        lines.append('')

    if data.get('promulgation_info'):
        lines.append(f'> {data["promulgation_info"]}')
        lines.append('')

    lines.append('---')
    lines.append('')

    # ── 正文 ──────────────────────────────────────────────────────────────────
    def render_articles(articles):
        for art in articles:
            content = art.get('content', '').strip()
            if content:
                lines.append(content)
                lines.append('')

    def render_section(sec):
        lines.append(f'#### {sec["title"].strip()}')
        lines.append('')
        render_articles(sec.get('articles', []))

    def render_chapter(ch):
        lines.append(f'### {ch["title"].strip()}')
        lines.append('')
        for sec in ch.get('sections', []):
            render_section(sec)
        render_articles(ch.get('articles', []))

    def render_part(pt):
        lines.append(f'## {pt["title"].strip()}')
        lines.append('')
        for ch in pt.get('chapters', []):
            render_chapter(ch)

    if 'parts' in data:
        for pt in data['parts']:
            render_part(pt)
    else:
        for ch in data.get('chapters', []):
            render_chapter(ch)

    return '\n'.join(lines)


def main():
    if MD_DIR.exists():
        import shutil
        shutil.rmtree(MD_DIR)

    paths = sorted(p for p in JSON_DIR.rglob('*.json') if 'index' not in p.name)
    print(f'转换 {len(paths)} 个文件...')

    domain_unknown = 0
    for path in paths:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        # 按 legal_domain 分类，未知的放 其他
        domain = data.get('legal_domain') or '其他'
        out_dir = MD_DIR / domain
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = out_dir / (path.stem + '.md')
        out_path.write_text(law_to_md(data), encoding='utf-8')

        if not data.get('legal_domain'):
            domain_unknown += 1

    # 统计
    print(f'完成，输出目录：{MD_DIR}')
    print(f'  未知 legal_domain（归入"其他"）：{domain_unknown}')
    for d in sorted(MD_DIR.iterdir()):
        count = len(list(d.glob('*.md')))
        print(f'  {d.name}/  {count} 个')


if __name__ == '__main__':
    main()
