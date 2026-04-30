#!/usr/bin/env python3
"""
完整 pipeline：docx → JSON → law_index → DB → Markdown
用法：python3 scripts/pipeline.py [选项]

选项：
  --skip-docx    跳过 docx → JSON 阶段
  --skip-index   跳过 law_index 生成阶段
  --skip-db      跳过 JSON → DB 阶段
  --skip-md      跳过 DB → Markdown 阶段
  --only-refs    只运行 extract_references（不跑主流程）

各阶段也可单独运行：
  cd scripts
  python3 -m docx_to_json.converter
  python3 generate_law_index.py
  python3 -m json_to_db.builder
  python3 -m db_to_md.renderer
  python3 extract_references.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(description='laws_data pipeline')
    parser.add_argument('--skip-docx',  action='store_true', help='跳过 docx → JSON')
    parser.add_argument('--skip-index', action='store_true', help='跳过 law_index 生成')
    parser.add_argument('--skip-db',    action='store_true', help='跳过 JSON → DB')
    parser.add_argument('--skip-md',    action='store_true', help='跳过 DB → Markdown')
    parser.add_argument('--only-refs',  action='store_true', help='只运行 extract_references')
    args = parser.parse_args()

    if args.only_refs:
        from extract_references import run as extract_refs
        extract_refs()
        from json_to_db.builder import load_references
        load_references()
        return

    if not args.skip_docx:
        from docx_to_json.converter import run as docx_to_json
        docx_to_json()

    if not args.skip_index:
        from generate_law_index import run as gen_law_index
        gen_law_index()

    if not args.skip_db:
        from json_to_db.builder import run as json_to_db
        json_to_db()

    if not args.skip_md:
        from db_to_md.renderer import run as db_to_md
        db_to_md()

    print('\n=== 完成 ===')


if __name__ == '__main__':
    main()
