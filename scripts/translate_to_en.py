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

# Anthropic
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL   = "claude-haiku-4-5-20251001"
# DeepSeek (OpenAI-compatible)
DEEPSEEK_API_URL  = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL    = "deepseek-chat"

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

def clean_punctuation(text: str) -> str:
    """清理中文标点符号，替换为英文标点"""
    replacements = {
        '"': '"',    # 中文左引号 → 英文左引号
        '"': '"',    # 中文右引号 → 英文右引号
        ''': "'",    # 中文左单引号 → 英文单引号
        ''': "'",    # 中文右单引号 → 英文单引号
        '，': ',',   # 中文逗号 → 英文逗号
        '。': '.',   # 中文句号 → 英文句号
        '；': ';',   # 中文分号 → 英文分号
        '：': ':',   # 中文冒号 → 英文冒号
        '！': '!',   # 中文感叹号 → 英文感叹号
        '？': '?',   # 中文问号 → 英文问号
        '（': '(',   # 中文左括号 → 英文左括号
        '）': ')',   # 中文右括号 → 英文右括号
        '【': '[',   # 中文左方括号 → 英文左方括号
        '】': ']',   # 中文右方括号 → 英文右方括号
        '《': '"',   # 书名号左 → 引号
        '》': '"',   # 书名号右 → 引号
        '、': ', ',  # 顿号 → 逗号+空格
        '　': ' ',   # 全角空格 → 半角空格
    }

    for zh_punct, en_punct in replacements.items():
        text = text.replace(zh_punct, en_punct)

    # 清理多余空格
    text = ' '.join(text.split())

    return text


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
        "CRITICAL - Legal Language Rules:",
        "- Use 'shall' for obligations and requirements (NEVER use 'will')",
        "- Use 'may' for permissions and rights (NEVER use 'would')",
        "- Use 'must' for absolute requirements",
        "- NEVER use 'will' or 'would' - these are FORBIDDEN in legal English",
        "",
        "Additional Rules:",
        "- Preserve legal precision and formal style",
        "- Use only English punctuation (NEVER use Chinese punctuation like " " ， 。)",
        "- Keep article numbers as-is (第一条 context implies Article 1)",
        "- For law titles cited in text (《xxx》), use the exact English title from the glossary below",
        "- Output only the translated text, nothing else",
        "",
        "Examples of CORRECT usage:",
        "- ✓ 'shall establish' (NOT 'will establish')",
        "- ✓ 'may appoint' (NOT 'can appoint' or 'would appoint')",
        "- ✓ 'must comply' (NOT 'shall comply' when absolute requirement)",
    ]

    if title_map:
        lines += ["", "## Law Title Translations (use these exact translations when citing laws in text)"]
        # 优化：只注入最常被引用的 50 条（从 200 减少），节省约 7500 tokens
        for zh, en in list(title_map.items())[:50]:
            lines.append(f"  {zh} → {en}")

    if glossary:
        lines += ["", "## Legal Term Glossary (use these exact translations for these terms)"]
        if isinstance(glossary, dict):
            # 术语表保持 300 条（已经比较精简）
            for zh, en in list(glossary.items())[:300]:
                lines.append(f"  {zh} → {en}")

    return "\n".join(lines)


# ── API 调用 ────────────────────────────────────────────────────────────────

def api_call(api_key: str, messages: list, system: str) -> str:
    """支持 Anthropic 和 DeepSeek 两种 API。
    设置 DEEPSEEK_API_KEY 时优先用 DeepSeek，否则用 Anthropic。
    """
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if deepseek_key:
        # DeepSeek OpenAI-compatible API
        payload = json.dumps({
            "model": DEEPSEEK_MODEL,
            "max_tokens": 4096,
            "messages": [{"role": "system", "content": system}] + messages,
        }).encode()
        req = urllib.request.Request(
            DEEPSEEK_API_URL, data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {deepseek_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"]
    else:
        # Anthropic API
        payload = json.dumps({
            "model": ANTHROPIC_MODEL,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
        }).encode()
        req = urllib.request.Request(
            ANTHROPIC_API_URL, data=payload,
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
    result = api_call(api_key, [{"role": "user", "content": f"Translate this Chinese law title:\n{title}"}], system).strip()
    return clean_punctuation(result)


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
    # 应用标点清理
    return {obj["id"]: clean_punctuation(obj["en"]) for obj in result if "id" in obj and "en" in obj}


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


def pending_articles(en_data: dict, cn_articles: dict) -> list:
    """返回 content_en 为空且有中文原文的条文列表 [(article_number, 中文content), ...]。"""
    result = []
    for a in en_data.get('articles', []):
        if a.get('content_en', '').strip():
            continue  # 已翻译，跳过
        art_num = a['article_number']
        cn_content = cn_articles.get(art_num, '').strip()
        if cn_content:
            result.append((art_num, cn_content))
    return result


# ── 主流程 ──────────────────────────────────────────────────────────────────

def get_laws(filter_kw: str = '') -> list:
    """从数据库读取 is_current=1 的法律列表，返回 [(law_id, filename, category, title), ...]。
    只翻译现行版本，旧版本跳过。
    """
    import sqlite3
    conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)  # 只读模式
    rows = conn.execute(
        "SELECT id, filename, category, title FROM laws WHERE is_current=1"
    ).fetchall()
    conn.close()
    if filter_kw:
        rows = [r for r in rows if filter_kw in r[3]]
    return rows


def load_cn_articles(filename: str, category: str) -> dict:
    """从中文 json/ 文件中提取 article_number → 中文content 的映射。"""
    cn_path = JSON_DIR / category / f'{filename}.json'
    if not cn_path.exists():
        return {}
    cn_data = json.loads(cn_path.read_text(encoding='utf-8'))

    mapping = {}

    def collect(chapters):
        for ch in chapters:
            for sec in ch.get('sections', []):
                for a in sec.get('articles', []):
                    _add(a)
            for a in ch.get('articles', []):
                _add(a)

    def _add(a):
        art_num = (a.get('title') or '').rstrip('　 ').strip()
        content = a.get('content', '').strip()
        if art_num and content:
            mapping[art_num] = content

    if 'parts' in cn_data:
        for pt in cn_data['parts']:
            collect(pt.get('chapters', []))
    elif 'chapters' in cn_data:
        collect(cn_data['chapters'])

    return mapping


def main():
    parser = argparse.ArgumentParser(description='翻译法条到 json_en/')
    # 优化：batch_size 从 20 提升到 100，可节省 56% 的 token 消耗
    # 原因：System Prompt（15K tokens）在每批都要重复发送，batch_size 越大，重复开销越小
    parser.add_argument('--batch-size', type=int, default=100, help='每次 API 调用的条文数（默认100，最优化token消耗）')
    parser.add_argument('--workers',    type=int, default=4,  help='并行 API 线程数')
    parser.add_argument('--dry-run',    action='store_true',  help='统计待翻译量，不调用 API')
    parser.add_argument('--laws-only',  action='store_true',  help='只翻译法律标题')
    parser.add_argument('--filter',     type=str, default='', help='只处理标题含此关键词的法律')
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key and not deepseek_key and not args.dry_run:
        print("ERROR: 请设置 ANTHROPIC_API_KEY 或 DEEPSEEK_API_KEY", file=sys.stderr)
        sys.exit(1)
    if deepseek_key:
        print(f"使用 DeepSeek API（{DEEPSEEK_MODEL}）")

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
            cn_articles = load_cn_articles(filename, category)
            if not en_data.get('title_en', '').strip():
                need_title += 1
            if is_fully_translated(en_data):
                done_laws += 1
            else:
                pending = pending_articles(en_data, cn_articles)
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
        en_path    = JSON_EN_DIR / category / f'{filename}.json'
        en_data    = load_en_file(en_path)
        cn_articles = load_cn_articles(filename, category)

        pending = pending_articles(en_data, cn_articles)
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
