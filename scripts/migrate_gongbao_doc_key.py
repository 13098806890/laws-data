#!/usr/bin/env python3
"""
One-time migration: add doc_key to json_en_gongbao files.

1. Reads source gongbao JSON files (裁判文书/指导案例/司法文件)
2. Computes doc_key = "{source}/{filename_stem}" for each
3. Maps the old numeric ID (from json_en_gongbao filename) → doc_key
4. Writes doc_key into each json_en_gongbao file
5. Also adds doc_key to the main gongbao JSON source files for future builds
"""

import json, sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / 'law_content.db'

DOC_SOURCES = {
    'cpwsxd': BASE_DIR / '最高人民法院公报' / '裁判文书',
    'al':     BASE_DIR / '最高人民法院公报' / '指导案例',
    'sfwj':   BASE_DIR / '最高人民法院公报' / '司法文件',
}

GONGBAO_EN_DIR = BASE_DIR / 'json_en_gongbao'


def main():
    # ── Step 1: Build doc_id → doc_key map from source files ──
    id_to_key = {}
    key_to_source_file = {}
    for source, folder in DOC_SOURCES.items():
        for f in sorted(folder.glob('*.json')):
            doc_key = f"{source}/{f.stem}"
            key_to_source_file[doc_key] = f

    # Read the current DB to get doc_id → doc_key mapping
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, source, title FROM gongbao_docs").fetchall()
    conn.close()

    for doc_id, source, title in rows:
        # Find the matching source file by source + title
        folder = DOC_SOURCES[source]
        for f in folder.glob('*.json'):
            d = json.loads(f.read_text(encoding='utf-8'))
            if d.get('title') == title:
                doc_key = f"{source}/{f.stem}"
                id_to_key[doc_id] = doc_key
                break

    print(f"Built doc_id → doc_key map: {len(id_to_key)} entries")

    # ── Step 2: Update json_en_gongbao files with doc_key ──
    updated_en = 0
    for source_dir in sorted(GONGBAO_EN_DIR.iterdir()):
        if not source_dir.is_dir():
            continue
        for fpath in sorted(source_dir.glob('*.json')):
            old_id = int(fpath.stem)
            doc_key = id_to_key.get(old_id)
            if not doc_key:
                print(f"  ⚠ No doc_key found for old id {old_id} ({fpath.name})")
                continue
            try:
                data = json.loads(fpath.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"  ⚠ parse error: {fpath.name} — {e}")
                continue
            data['doc_key'] = doc_key
            fpath.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8'
            )
            updated_en += 1
    print(f"Updated json_en_gongbao files: {updated_en}")

    # ── Step 3: Add doc_key to source gongbao JSON files ──
    updated_source = 0
    for doc_key, fpath in key_to_source_file.items():
        data = json.loads(fpath.read_text(encoding='utf-8'))
        data['doc_key'] = doc_key
        fpath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8'
        )
        updated_source += 1
    print(f"Updated source gongbao JSON files: {updated_source}")

    print("\nDone! Now update build_gongbao_db.py to use doc_key.")


if __name__ == '__main__':
    main()
