#!/usr/bin/env python3
"""调用 DeepSeek API 批量翻译法律标题，产出 law_title_en_map.json

用法：
  DEEPSEEK_API_KEY=sk-xxx python3 translate_titles.py

支持断点续传：每次 API 调用后将中间结果写入 OUTPUT_PATH.tmp，
后续启动会从已有结果继续，不重复翻译已有标题。
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

API_KEY = os.environ.get('DEEPSEEK_API_KEY')
if not API_KEY:
    print('请设置 DEEPSEEK_API_KEY 环境变量')
    sys.exit(1)

API_URL = 'https://api.deepseek.com/chat/completions'
MODEL = 'deepseek-v4-flash'

INPUT_PATH = Path(__file__).parent.parent / 'references' / 'titles_for_translation.json'
OUTPUT_PATH = Path(__file__).parent.parent / 'references' / 'law_title_en_map.json'
TMP_PATH = OUTPUT_PATH.with_suffix('.json.tmp')

BATCH_SIZE = 50          # 每批 50 个标题
REQUEST_DELAY = 1.0      # 请求间隔秒数

SYSTEM_PROMPT = """你是一位专业的中国法律翻译专家。你的任务是将中国法律法规名称翻译为标准英文。

翻译规则：
1. "中华人民共和国XX法" → "XX of the People's Republic of China"（如民法典 → Civil Code, 刑法 → Criminal Law）
2. "最高人民法院" → "Supreme People's Court"
3. "最高人民检察院" → "Supreme People's Procuratorate"
4. "国务院" → "State Council"
5. "全国人民代表大会常务委员会" → "Standing Committee of the National People's Congress"
6. "关于" 在法规标题中 → "on"
7. "的解释" → "Interpretation of"
8. "的规定" → "Provisions on" 或 "Regulation on"
9. "的若干规定" → "Several Provisions on" 或 "Several Regulations on"
10. "的解释（一）" → "Interpretation (I)"
11. "第X条" → "Article X"
12. 书名号《》不翻译，去掉
13. "公布日期" 标注（如 _20100701）不翻译

输出格式必须是 JSON 数组，每个元素为 {"zh": "中文标题", "en": "英文标题"}。
只输出 JSON，不要多余说明。"""


def load_existing() -> dict:
    if TMP_PATH.exists():
        data = json.loads(TMP_PATH.read_text(encoding='utf-8'))
        print(f'  已有中间结果：{len(data)} 个')
        return data
    if OUTPUT_PATH.exists():
        data = json.loads(OUTPUT_PATH.read_text(encoding='utf-8'))
        print(f'  已有最终结果：{len(data)} 个')
        return data
    return {}


def call_api(batch: list[str], existing: dict) -> list[dict]:
    # 跳过已翻译的
    todo = [t for t in batch if t not in existing]
    if not todo:
        return []

    prompt_lines = [f'请翻译以下 {len(todo)} 个法律标题：']
    for i, t in enumerate(todo, 1):
        prompt_lines.append(f'{i}. {t}')
    prompt = '\n'.join(prompt_lines)

    payload = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt},
        ],
        'response_format': {'type': 'json_object'},
        'max_tokens': 8192,
        'temperature': 0.1,
    }

    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json',
    }

    import urllib.request as req

    data = json.dumps(payload).encode('utf-8')
    r = req.Request(API_URL, data=data, headers=headers, method='POST')
    try:
        with req.urlopen(r, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f'  API 调用失败: {e}')
        return []

    try:
        content = result['choices'][0]['message']['content']
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            # 有时被包裹在 {"titles": [...]} 里
            for v in parsed.values():
                if isinstance(v, list):
                    parsed = v
                    break
        return parsed if isinstance(parsed, list) else []
    except (KeyError, json.JSONDecodeError) as e:
        print(f'  解析返回结果失败: {e}')
        return []


def save_tmp(mapping: dict):
    TMP_PATH.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8'
    )


def main():
    titles = json.loads(INPUT_PATH.read_text(encoding='utf-8'))['titles']
    print(f'待翻译标题总数：{len(titles)}')

    existing = load_existing()
    print(f'已有翻译：{len(existing)} 个')

    total_calls = 0
    for start in range(0, len(titles), BATCH_SIZE):
        batch = titles[start:start + BATCH_SIZE]
        todo = [t for t in batch if t not in existing]
        if not todo:
            continue

        print(f'  翻译第 {start+1}-{start+len(batch)} 个（待译 {len(todo)} 个）...', end=' ')
        sys.stdout.flush()

        results = call_api(batch, existing)
        if not results:
            print('失败，跳过本批')
            time.sleep(REQUEST_DELAY)
            continue

        for item in results:
            zh = item.get('zh', '').strip()
            en = item.get('en', '').strip()
            if zh and en:
                existing[zh] = en

        save_tmp(existing)
        total_calls += 1
        print(f'✓ 累计已有 {len(existing)} 个')
        time.sleep(REQUEST_DELAY)

    # 落盘最终结果
    OUTPUT_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8'
    )
    if TMP_PATH.exists():
        TMP_PATH.unlink()

    print(f'\n完成！共翻译 {len(existing)} 个标题，调用 API {total_calls} 次')
    print(f'输出：{OUTPUT_PATH}')


if __name__ == '__main__':
    main()
