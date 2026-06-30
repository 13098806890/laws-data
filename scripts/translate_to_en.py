#!/usr/bin/env python3
"""
将法条翻译成英文，结果写回 json_en/{category}/{filename}.json。

特性：
- 增量：content_en 已有内容的条文跳过，已完整翻译的法律跳过
- 术语一致性：启动时注入 law_title_en_map.json + legal_terms_glossary.json
- 可恢复：中断后重跑自动从未完成的法律继续

用法：
  export ANTHROPIC_API_KEY=sk-ant-...
  cd /Users/doxie/Github/laws-data
  python3 scripts/translate_to_en.py                  # 全量翻译
  python3 scripts/translate_to_en.py --dry-run        # 统计待翻译量
  python3 scripts/translate_to_en.py --laws-only      # 只翻译标题
  python3 scripts/translate_to_en.py --filter 民法典  # 只翻译标题含关键词的法律
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import JSON_DIR, DB_PATH

JSON_EN_DIR    = JSON_DIR.parent / 'json_en'
REFERENCES_DIR = JSON_DIR.parent / 'references'
TITLE_MAP_PATH = REFERENCES_DIR / 'law_title_en_map.json'
GLOSSARY_PATH  = REFERENCES_DIR / 'legal_terms_glossary.json'

API_URL = "https://api.anthropic.com/v1/messages"
MODEL   = "claude-haiku-4-5-20251001"

# ── 静态枚举翻译 ────────────────────────────────────────────────────────────

CATEGORY_MAP = {
    "宪法":     "Constitution",
    "法律":     "Law",
    "修正案":   "Amendment",
    "决定":     "Decision",
    "法律解释": "Legal Interpretation",
    "司法解释": "Judicial Interpretation",
    "行政法规": "Administrative Regulation",
    "监察法规": "Supervisory Regulation",
}

DOMAIN_MAP = {
    "宪法相关法":         "Constitutional Law",
    "民法典":             "Civil Code",
    "民法商法":           "Civil & Commercial Law",
    "刑法":               "Criminal Law",
    "行政法":             "Administrative Law",
    "经济法":             "Economic Law",
    "社会法":             "Social Law",
    "诉讼与非诉讼程序法": "Procedural Law",
}

ORG_MAP = {
    "最高人民法院":             "Supreme People's Court",
    "最高人民检察院":           "Supreme People's Procuratorate",
    "国务院":                   "State Council",
    "全国人民代表大会常务委员会": "NPC Standing Committee",
    "全国人民代表大会":          "National People's Congress",
    "国家监察委员会":            "National Supervisory Commission",
}


# ── 参考资料加载 ────────────────────────────────────────────────────────────

def load_title_map() -> dict:
    if TITLE_MAP_PATH.exists():
        return json.loads(TITLE_MAP_PATH.read_text(encoding='utf-8'))
    return {}


def load_glossary() -> dict:
    if GLOSSARY_PATH.exists():
        return json.loads(GLOSSARY_PATH.read_text(encoding='utf-8'))
    return {}


def build_system_prompt(title_map: dict, glossary: dict) -> str:
    lines = [
        "You are a professional legal translator specializing in Chinese law.",
        "Translate Chinese legal text into English with precision and consistency.",
        "",
        "Rules:",
        "- Preserve legal precision and formal style",
        "- Use 'shall' for obligations, 'may' for permissions, 'must' for requirements",
        "- Keep article numbers as-is (第一条 context implies Article 1)",
        "- For law titles cited in text (《xxx》), use the exact English title from the glossary below",
        "- Output only the translated text, nothing else",
    ]

    if title_map:
        lines += ["", "## Law Title Translations (use these exact translations when citing laws in text)"]
        # 只注入最常被引用的 200 条，避免 prompt 过长
        for zh, en in list(title_map.items())[:200]:
            lines.append(f"  {zh} → {en}")

    if glossary:
        lines += ["", "## Legal Term Glossary (use these exact translations for these terms)"]
        if isinstance(glossary, dict):
            for zh, en in list(glossary.items())[:300]:
                lines.append(f"  {zh} → {en}")

    return "\n".join(lines)


# ── API 调用 ────────────────────────────────────────────────────────────────

def api_call(api_key: str, messages: list, system: str) -> str:
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 4096,
        "system": system,
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())["content"][0]["text"]


def translate_title(api_key: str, title: str, system: str) -> str:
    return api_call(api_key, [{"role": "user", "content": f"Translate this Chinese law title:\n{title}"}], system).strip()


def translate_articles_batch(api_key: str, items: list, system: str) -> dict:
    """items: list of (article_number, content_zh). Returns {article_number: content_en}."""
    payload = json.dumps(
        [{"id": art_num, "text": content} for art_num, content in items],
        ensure_ascii=False
    )
    raw = api_call(api_key, [{"role": "user", "content": payload}], system)
    s = raw.find("[")
    e = raw.rfind("]") + 1
    if s < 0 or e <= s:
        raise ValueError(f"No JSON array in response: {raw[:200]}")
    result = json.loads(raw[s:e])
    return {obj["id"]: obj["en"] for obj in result if "id" in obj and "en" in obj}


BATCH_ARTICLE_SUFFIX = """

You will receive a JSON array of objects with "id" (article number) and "text" (Chinese legal text).
Translate each "text" into English.
Return a JSON array with the same objects, adding an "en" field with the English translation.
Output only the JSON array, nothing else."""


# ── json_en 文件读写 ────────────────────────────────────────────────────────

def load_en_file(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return {}


def save_en_file(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def is_fully_translated(en_data: dict) -> bool:
    """所有 articles 的 content_en 都非空则视为已完整翻译。"""
    articles = en_data.get('articles', [])
    if not articles:
        return False
    return all(a.get('content_en', '').strip() for a in articles)


def pending_articles(en_data: dict) -> list:
    """返回 content_en 为空的条文列表 [(article_number, ''), ...]。"""
    return [
        (a['article_number'], a.get('content_en', ''))
        for a in en_data.get('articles', [])
        if not a.get('content_en', '').strip()
    ]


# ── 主流程 ──────────────────────────────────────────────────────────────────

def get_laws(filter_kw: str = '') -> list:
    """从数据库读取需翻译的法律列表，返回 [(law_id, filename, category, title), ...]。"""
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, filename, category, title FROM laws WHERE is_current=1"
    ).fetchall()
    conn.close()
    if filter_kw:
        rows = [r for r in rows if filter_kw in r[3]]
    return rows


def main():
    parser = argparse.ArgumentParser(description='翻译法条到 json_en/')
    parser.add_argument('--batch-size', type=int, default=20, help='每次 API 调用的条文数')
    parser.add_argument('--workers',    type=int, default=4,  help='并行 API 线程数')
    parser.add_argument('--dry-run',    action='store_true',  help='统计待翻译量，不调用 API')
    parser.add_argument('--laws-only',  action='store_true',  help='只翻译法律标题')
    parser.add_argument('--filter',     type=str, default='', help='只处理标题含此关键词的法律')
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    title_map = load_title_map()
    glossary  = load_glossary()
    print(f"已加载标题 map：{len(title_map)} 条，术语表：{len(glossary)} 条")

    system = build_system_prompt(title_map, glossary)
    article_system = system + BATCH_ARTICLE_SUFFIX

    laws = get_laws(args.filter)
    print(f"法律总数：{len(laws)} 部")

    # ── dry-run：统计待翻译量 ──
    if args.dry_run:
        need_title = need_articles = done_laws = 0
        total_pending_articles = 0
        for law_id, filename, category, title in laws:
            en_path = JSON_EN_DIR / category / f'{filename}.json'
            en_data = load_en_file(en_path)
            if not en_data.get('title_en', '').strip():
                need_title += 1
            if is_fully_translated(en_data):
                done_laws += 1
            else:
                pending = pending_articles(en_data)
                total_pending_articles += len(pending)
                need_articles += 1
        print(f"  已完整翻译：{done_laws} 部")
        print(f"  待翻译标题：{need_title} 个")
        print(f"  待翻译法律：{need_articles} 部，共 {total_pending_articles} 条条文")
        print(f"  预计批次数：{total_pending_articles // args.batch_size + 1}")
        return

    # ── 翻译标题 ──
    title_pending = [
        (law_id, filename, category, title)
        for law_id, filename, category, title in laws
        if not load_en_file(JSON_EN_DIR / category / f'{filename}.json').get('title_en', '').strip()
    ]
    print(f"待翻译标题：{len(title_pending)} 个")

    def translate_one_title(row):
        law_id, filename, category, title = row
        try:
            # 优先从 title_map 取（已人工确认）
            if title in title_map:
                return law_id, filename, category, title_map[title]
            return law_id, filename, category, translate_title(api_key, title, system)
        except Exception as exc:
            return law_id, filename, category, f"[Translation error: {exc}]"

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(translate_one_title, r): r for r in title_pending}
        for fut in as_completed(futures):
            law_id, filename, category, title_en = fut.result()
            en_path = JSON_EN_DIR / category / f'{filename}.json'
            en_data = load_en_file(en_path)
            en_data['law_id']   = law_id
            en_data['title_en'] = title_en
            en_data.setdefault('promulgation_info_en', '')
            en_data.setdefault('articles', [])
            save_en_file(en_path, en_data)
            done += 1
            if done % 50 == 0:
                print(f"  标题：{done}/{len(title_pending)}")
    print(f"标题翻译完成（{done} 个）")

    if args.laws_only:
        return

    # ── 翻译条文 ──
    laws_with_pending = [
        (law_id, filename, category, title)
        for law_id, filename, category, title in laws
        if not is_fully_translated(load_en_file(JSON_EN_DIR / category / f'{filename}.json'))
    ]
    print(f"待翻译法律：{len(laws_with_pending)} 部")

    total_done = total_errors = 0

    for idx, (law_id, filename, category, title) in enumerate(laws_with_pending, 1):
        en_path = JSON_EN_DIR / category / f'{filename}.json'
        en_data = load_en_file(en_path)

        pending = pending_articles(en_data)
        if not pending:
            continue

        print(f"[{idx}/{len(laws_with_pending)}] {title}（{len(pending)} 条待翻译）")

        # 构建 article_number → index 映射，便于回写
        art_index = {a['article_number']: i for i, a in enumerate(en_data['articles'])}

        # 分批翻译
        batches = [pending[i:i + args.batch_size] for i in range(0, len(pending), args.batch_size)]

        def translate_batch(batch):
            for attempt in range(3):
                try:
                    return translate_articles_batch(api_key, batch, article_system)
                except Exception as exc:
                    if attempt == 2:
                        print(f"    批次失败（已重试3次）：{exc}")
                        return {}
                    time.sleep(2 ** attempt)

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(translate_batch, b): b for b in batches}
            for fut in as_completed(futures):
                translations = fut.result()
                batch = futures[fut]
                for art_num, _ in batch:
                    en_text = translations.get(art_num, '')
                    if art_num in art_index:
                        en_data['articles'][art_index[art_num]]['content_en'] = en_text
                        if en_text:
                            total_done += 1
                        else:
                            total_errors += 1

        save_en_file(en_path, en_data)
        print(f"    已写回 {en_path.name}")

    print(f"\n完成：{total_done} 条翻译，{total_errors} 条失败")


if __name__ == "__main__":
    main()
