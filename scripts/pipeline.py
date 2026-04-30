#!/usr/bin/env python3
"""
完整 pipeline：docx → JSON → DB → Markdown
用法：python3 scripts/pipeline.py

各步骤也可单独运行：
  python3 -m docx_to_json.converter
  python3 -m json_to_db.builder
  python3 -m db_to_md.renderer
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from docx_to_json.converter import run as docx_to_json
from json_to_db.builder import run as json_to_db
from db_to_md.renderer import run as db_to_md


def main():
    docx_to_json()
    json_to_db()
    db_to_md()
    print('\n=== 完成 ===')


if __name__ == '__main__':
    main()
