#!/usr/bin/env python3
"""
Translate part/chapter/section content to English and store in content_en.

IMPORTANT: Uses stable key (law_id:type:order_index) instead of node ID for
the heading_en_map.json cache.  This survives DB rebuilds because node
autoincrement IDs change every time the DB is recreated, but
(law_id, type, order_index) stays the same.
"""

import json, os, sqlite3, sys, time, re
from pathlib import Path

API_KEY = os.environ.get('DEEPSEEK_API_KEY')
if not API_KEY:
    print('请设置 DEEPSEEK_API_KEY 环境变量')
    sys.exit(1)

API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-flash'
BATCH_SIZE = 150
REQUEST_DELAY = 0.5
DB_PATH = Path(__file__).parent.parent / 'law_content.db'
TMP_PATH = Path(__file__).parent.parent / 'references' / 'heading_en_map.json.tmp'
OUTPUT_PATH = Path(__file__).parent.parent / 'references' / 'heading_en_map.json'

SYSTEM_PROMPT = """You translate Chinese legal document headings to English. Rules:
1. "第X章" → "Chapter X", "第X节" → "Section X", "第X编" → "Part X"
2. "总 则" → "General Provisions", "分则" → "Specific Provisions"
3. "附则" → "Supplementary Provisions"
4. Keep all numbering intact (一/二/三 → 1/2/3, etc.)
5. Output JSON array: [{"id": N, "en": "ENGLISH_TEXT"}]
6. Only output JSON, no explanation."""


def stable_key(law_id: int, node_type: str, order_index: int) -> str:
    return f"{law_id}:{node_type}:{order_index}"


def load_existing():
    """Load heading map saved with stable keys."""
    for p in (TMP_PATH, OUTPUT_PATH):
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            print(f'  已有结果：{len(data)} 条')
            return data
    return {}


def call_api(batch):
    """
    Send a batch of headings to the API.

    batch: list of (node_id, law_id, type, order_index, text)
    The prompt uses a sequential temp key (1-based index in the batch) to avoid
    confusing the model with sparse node IDs.  The returned results are mapped
    back using the stable key (law_id:type:order_index) so the cache survives
    DB rebuilds where node autoincrement IDs change.
    """
    prompt_lines = [f'Translate these {len(batch)} headings:']
    temp_ids = {}
    for i, (node_id, law_id, ntype, oi, text) in enumerate(batch, start=1):
        prompt_lines.append(f'{i}. {text}')
        temp_ids[i] = (node_id, law_id, ntype, oi)
    payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': '\n'.join(prompt_lines)},
        ],
        'response_format': {'type': 'json_object'},
        'max_tokens': 8192,
        'temperature': 0.1,
    }
    headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
    import urllib.request as req
    data = json.dumps(payload).encode('utf-8')
    r = req.Request(API_URL, data=data, headers=headers, method='POST')
    try:
        with req.urlopen(r, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f'  API失败: {e}')
        return {}
    try:
        content = result['choices'][0]['message']['content']
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list):
                    parsed = v
                    break
        if not isinstance(parsed, list):
            return {}
        mapped = {}
        for item in parsed:
            if 'id' not in item or 'en' not in item:
                continue
            seq = int(item['id'])
            orig = temp_ids.get(seq)
            if orig is None:
                continue
            node_id, law_id, ntype, oi = orig
            key = stable_key(law_id, ntype, oi)
            mapped[key] = item['en']
        return mapped
    except (KeyError, json.JSONDecodeError) as e:
        print(f'  解析失败: {e}')
        return {}


def main():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('''
        SELECT n.id, n.law_id, n.type, n.order_index, n.content
        FROM nodes n
        WHERE n.type IN ('part','chapter','section') AND n.content_en IS NULL
        ORDER BY n.id
    ''').fetchall()
    conn.close()
    print(f'待翻译结构节点：{len(rows)}')

    existing = load_existing()
    # Dedup by stable key
    existing_keys = set(existing.keys())
    todo = [(nid, law_id, ntype, oi, text) for (nid, law_id, ntype, oi, text) in rows
            if stable_key(law_id, ntype, oi) not in existing_keys]
    print(f'待译：{len(todo)}，已有缓存：{len(existing)}')

    total_calls = 0
    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start:start + BATCH_SIZE]
        print(f'  第 {start+1}-{start+len(batch)} 条...', end=' ')
        sys.stdout.flush()
        results = call_api(batch)
        if results:
            existing.update(results)
            conn = sqlite3.connect(DB_PATH)
            for key, en in results.items():
                parts = key.split(':')
                law_id, ntype, oi = int(parts[0]), parts[1], int(parts[2])
                conn.execute(
                    'UPDATE nodes SET content_en = ? WHERE law_id = ? AND type = ? AND order_index = ?',
                    (en, law_id, ntype, oi)
                )
            conn.commit()
            conn.close()
            TMP_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            total_calls += 1
            print(f'✓ {len(results)} 条 [DB累计 {len(existing)}]')
        else:
            print('失败')
        time.sleep(REQUEST_DELAY)

    OUTPUT_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if TMP_PATH.exists():
        TMP_PATH.unlink()
    print(f'\n完成！共翻译 {len(existing)} 条，API 调用 {total_calls} 次')


if __name__ == '__main__':
    main()
