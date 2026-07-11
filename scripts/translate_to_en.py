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
import sqlite3
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
DEEPSEEK_MODEL    = "deepseek-v4-flash"

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


# ── 数据库辅助 ───────────────────────────────────────────────────────────────

def get_referenced_laws(law_id: int) -> set[int]:
    """返回某法律引用的所有其他法律 ID（跨法引用，不含自引用）。"""
    import sqlite3
    try:
        conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
        rows = conn.execute(
            "SELECT DISTINCT to_law_id FROM article_references WHERE from_law_id=? AND ref_type='cross_law'",
            (law_id,)
        ).fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception:
        return set()


def get_law_title_en_map(law_ids: set[int], full_map: dict, all_laws: list) -> dict:
    """从全量 title_map 中筛选出指定 law_id 对应的标题翻译。"""
    id_to_title = {lid: title for lid, _, _, title in all_laws}
    result = {}
    for lid in law_ids:
        title = id_to_title.get(lid)
        if title and title in full_map:
            result[title] = full_map[title]
    return result


def find_glossary_terms(article_texts: list[str], glossary: dict) -> dict:
    """扫描条文文本，只返回实际出现的术语。"""
    if not glossary:
        return {}
    combined = '\n'.join(article_texts)
    found = {}
    for zh, en in glossary.items():
        if zh in combined:
            found[zh] = en
    return found


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

    # 清理多余空格（保留换行符）
    # 分行处理，每行内部清理空格，但保留行间换行符
    lines = text.split('\n')
    cleaned_lines = [' '.join(line.split()) for line in lines]
    text = '\n'.join(cleaned_lines)

    return text


def load_title_map() -> dict:
    if TITLE_MAP_PATH.exists():
        return json.loads(TITLE_MAP_PATH.read_text(encoding='utf-8'))
    return {}


def load_glossary() -> dict:
    if GLOSSARY_PATH.exists():
        return json.loads(GLOSSARY_PATH.read_text(encoding='utf-8'))
    return {}


def build_system_prompt(title_map: dict, glossary: dict,
                        per_law_title_map: dict = None,
                        per_law_glossary: dict = None) -> str:
    lines = [
        "You are a professional legal translator specializing in Chinese law.",
        "Translate Chinese legal text into English with precision and consistency.",
        "",
        "CRITICAL - Legal Language Rules:",
        "- Use 'shall' for obligations and requirements (NEVER use 'will' as future tense)",
        "- Use 'may' for permissions and rights (NEVER use 'would' for permissions)",
        "- Use 'must' for absolute requirements",
        "",
        "EXCEPTIONS for will/would:",
        "- ✓ 'will' as NOUN (testament/遗嘱) is ALLOWED: 'by will', 'make a will', 'the will'",
        "- ✓ 'would' in SUBJUNCTIVE/CONDITIONAL clauses is ALLOWED: 'if X, it would...', 'would have been'",
        "- ✗ 'will' as VERB (future tense) is FORBIDDEN: use 'shall' instead",
        "",
        "Additional Rules:",
        "- Preserve legal precision and formal style",
        "- Use only English punctuation (NEVER use Chinese punctuation like " " ， 。)",
        "- Keep article numbers as-is (第一条 context implies Article 1)",
        "- For law titles cited in text (《xxx》), use the exact English title from the glossary below",
        "- **CRITICAL: Preserve paragraph breaks** - When the Chinese text contains line breaks (\\n), maintain them in the English translation to preserve the article's structure",
        "- Output only the translated text, nothing else",
        "",
        "Examples of CORRECT usage:",
        "- ✓ 'shall pay a reward' (NOT 'will pay')",
        "- ✓ 'shall cause damage' (NOT 'will cause')",
        "- ✓ 'shall not perform' (NOT 'will not perform')",
        "- ✓ 'appoint a guardian by will' (will as noun - CORRECT)",
        "- ✓ 'if it would reach' (subjunctive - CORRECT)",
        "- ✓ 'would have been entitled' (past conditional - CORRECT)",
    ]

    # 按需注入：只注入当前法律引用的其他法律标题
    if per_law_title_map:
        lines += ["", "## Law Title Translations (use these exact translations when citing laws in text)"]
        for zh, en in per_law_title_map.items():
            lines.append(f"  {zh} → {en}")

    # 按需注入：只注入当前法律中实际出现的术语
    if per_law_glossary:
        lines += ["", "## Legal Term Glossary (use these exact translations for these terms)"]
        for zh, en in per_law_glossary.items():
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
            "max_tokens": 32768,
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
            body = resp.read()
            data = json.loads(body)
            if "choices" not in data or not data["choices"]:
                raise ValueError(f"API returned no choices: {data.get('error', body[:200])}")
            return data["choices"][0]["message"]["content"]
    else:
        # Anthropic API
        payload = json.dumps({
            "model": ANTHROPIC_MODEL,
            "max_tokens": 16384,
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
    # 尝试从响应中提取 JSON
    s = raw.find("[")
    e = raw.rfind("]") + 1
    if s < 0 or e <= s:
        # 响应可能被截断，尝试更宽松的解析
        s = raw.find("[")
        if s < 0:
            raise ValueError(f"No JSON array in response: {raw[:200]}")
        # 从末尾向前找最后一个完整的对象
        truncated = raw[s:]
        # 尝试补全为合法 JSON 数组
        for i in range(len(truncated), s, -1):
            candidate = truncated[:i-s] + "]"
            try:
                result = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        else:
            raise ValueError(f"Cannot parse JSON from truncated response: {raw[:200]}")
    else:
        try:
            result = json.loads(raw[s:e])
        except json.JSONDecodeError:
            # 最后尝试补全
            candidate = raw[s:] + "]" if not raw.rstrip().endswith("]") else raw[s:]
            try:
                result = json.loads(candidate)
            except json.JSONDecodeError:
                raise ValueError(f"JSON parse failed: {raw[:200]}")
    # 应用标点清理
    return {obj["id"]: clean_punctuation(obj["en"]) for obj in result if "id" in obj and "en" in obj}


BATCH_ARTICLE_SUFFIX = """

You will receive a JSON array of objects with "id" (article number) and "text" (Chinese legal text).
Translate each "text" into English.
IMPORTANT: If the "text" field contains line breaks (\\n), preserve them exactly in your translation to maintain the article's paragraph structure.
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


def is_fully_translated(en_data: dict, cn_articles: dict = None) -> bool:
    """所有 articles 的 content_en 都非空则视为已完整翻译。
    无 articles 但有 full_text_en 的视为完成。
    只有 title_en 没有条文内容的视为未完成。"""
    if not en_data:
        return False
    articles = en_data.get('articles', [])
    if not articles:
        if en_data.get('full_text_en', '').strip():
            return True
        # 只有标题没有条文 → 未完成（等着翻条文）
        return False
    return all(a.get('content_en', '').strip() for a in articles)


def pending_articles(en_data: dict, cn_articles: dict) -> list:
    """返回 content_en 为空且有中文原文的条文列表 [(article_number, 中文content), ...]。"""
    if not en_data:
        # 文件不存在（新法律），全部 cn_articles 都是待翻译
        return list(cn_articles.items()) if cn_articles else []
    
    result = []
    for a in en_data.get('articles', []):
        if a.get('content_en', '').strip():
            continue
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
    conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)  # 只读模式
    rows = conn.execute(
        "SELECT id, filename, category, title FROM laws WHERE is_current=1"
    ).fetchall()
    conn.close()
    if filter_kw:
        rows = [r for r in rows if filter_kw in r[3]]
    return rows


def load_cn_articles(filename: str, category: str, law_id: int = None) -> dict:
    """从中文 json/ 文件中提取 article_number → 中文content 的映射。
    自动处理重复标题（追加 _2, _3 后缀）。
    如果 json 文件不存在，尝试从 DB nodes 表读取（用于 source='gongbao' 的法律）。"""
    cn_path = JSON_DIR / category / f'{filename}.json'
    if not cn_path.exists():
        # 有时 DB 的 category 与实际文件路径不一致，尝试递归搜索
        matches = list(JSON_DIR.rglob(f'{filename}.json'))
        if matches:
            cn_path = matches[0]
        else:
            # 从 DB nodes 表回退（gongbao 来源的法律没有 json 文件）
            if law_id:
                conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
                rows = conn.execute(
                    "SELECT content FROM nodes WHERE law_id=? AND type='article' ORDER BY global_order",
                    (law_id,)
                ).fetchall()
                conn.close()
                if rows:
                    result = {}
                    for i, (content,) in enumerate(rows):
                        content = content.strip()
                        if content:
                            art_num = f'第{i+1}条'
                            result[art_num] = content
                    return result
            return {}
    cn_data = json.loads(cn_path.read_text(encoding='utf-8'))

    mapping = {}
    seen = {}

    def collect(chapters):
        for ch in chapters:
            for sec in ch.get('sections', []):
                for a in sec.get('articles', []):
                    _add(a)
            for a in ch.get('articles', []):
                _add(a)

    def _add(a):
        nonlocal seen
        art_num = (a.get('title') or '').rstrip('　 ').strip()
        content = a.get('content', '').strip()
        if not content:
            return
        if not art_num:
            art_num = f'_{len(mapping) + 1}'
        key = art_num
        if key in seen:
            seen[key] += 1
            key = f'{art_num}_{seen[key]}'
        else:
            seen[key] = 1
        mapping[key] = content

    if 'parts' in cn_data:
        for pt in cn_data['parts']:
            collect(pt.get('chapters', []))
    elif 'chapters' in cn_data:
        collect(cn_data['chapters'])

    # 无文章结构的法律（只有 full_text），整段作为一条处理
    if not mapping:
        full_text = cn_data.get('full_text', '').strip()
        if full_text:
            mapping['_1'] = full_text

    return mapping


def main():
    parser = argparse.ArgumentParser(description='翻译法条到 json_en/')
    parser.add_argument('--batch-size', type=int, default=0, help='每次 API 调用的条文数（0=按字符数自动）')
    parser.add_argument('--max-batch-chars', type=int, default=6000, help='每批最多中文字符数（默认6000，batch-size=0时生效）')
    parser.add_argument('--workers',    type=int, default=4,  help='并行 API 线程数')
    parser.add_argument('--dry-run',    action='store_true',  help='统计待翻译量，不调用 API')
    parser.add_argument('--laws-only',  action='store_true',  help='只翻译法律标题')
    parser.add_argument('--filter',     type=str, default='', help='只处理标题含此关键词的法律')
    parser.add_argument('--max-laws',   type=int, default=0,  help='最多翻译 N 部法律（0=不限）')
    parser.add_argument('--max-laws-per-run', type=int, default=0,
                        help='每轮最多处理 N 部法律后自动退出（0=不限），用于定期重启避免卡住')
    parser.add_argument('--tier',       type=str, default='', 
                        help='按引用层级过滤: T0/T1/T2/T3/T4/T5，逗号分隔如 T0,T1')
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

    # 基准 system prompt（不含按需注入的标题和术语）
    base_system = build_system_prompt(title_map, glossary, per_law_title_map=None, per_law_glossary=None)
    article_system_base = base_system + BATCH_ARTICLE_SUFFIX

    laws = get_laws(args.filter)

    # 按引用层级过滤
    if args.tier:
        # 层级边界：每个层级定义 [lower, upper)
        tier_bounds = {
            'T0': (50,  99999),
            'T1': (20,  50),
            'T2': (10,  20),
            'T3': (5,   10),
            'T4': (1,   5),
            'T5': (0,   1),
        }
        selected_tiers = [t.strip().upper() for t in args.tier.split(',')]
        lower = min(tier_bounds.get(t, (0, 0))[0] for t in selected_tiers)
        upper = max(tier_bounds.get(t, (0, 0))[1] for t in selected_tiers)
        import sqlite3
        conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
        cited_counts = dict(conn.execute(
            "SELECT to_law_id, COUNT(*) FROM article_references GROUP BY to_law_id"
        ).fetchall())
        conn.close()
        laws = [r for r in laws if lower <= cited_counts.get(r[0], 0) < upper]

    # 限制数量
    if args.max_laws > 0:
        laws = laws[:args.max_laws]

    print(f"法律总数：{len(laws)} 部" + (f"（层级={args.tier}）" if args.tier else ""))

    # ── dry-run：统计待翻译量 ──
    if args.dry_run:
        need_title = need_articles = done_laws = 0
        total_pending_articles = 0
        for law_id, filename, category, title in laws:
            en_path = JSON_EN_DIR / category / f'{filename}.json'
            en_data = load_en_file(en_path)
            cn_articles = load_cn_articles(filename, category, law_id)
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
        if args.batch_size > 0:
            print(f"  预计批次数：{total_pending_articles // args.batch_size + 1}")
        else:
            print(f"  预计批次数：动态（每批最多 {args.max_batch_chars} 字符）")
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
            if title in title_map:
                return law_id, filename, category, title_map[title]
            return law_id, filename, category, translate_title(api_key, title, base_system)
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
    laws_processed_in_run = 0

    for idx, (law_id, filename, category, title) in enumerate(laws_with_pending, 1):
        en_path     = JSON_EN_DIR / category / f'{filename}.json'
        en_data     = load_en_file(en_path)
        cn_articles = load_cn_articles(filename, category, law_id)

        # 如果 json_en 的 articles 为空，或存在重复编号需要修复，从 cn_articles 重建
        if cn_articles:
            existing_art_nums = [a['article_number'] for a in (en_data.get('articles') or [])]
            has_dupes = len(existing_art_nums) != len(set(existing_art_nums))
            needs_rebuild = has_dupes or not en_data.get('articles')
            if needs_rebuild:
                # 保留已有翻译的 content_en，新 key 留空
                old_map = {a['article_number']: a.get('content_en', '') for a in (en_data.get('articles') or [])}
                en_data['articles'] = []
                for k in cn_articles:
                    en_data['articles'].append({'article_number': k, 'content_en': old_map.get(k, '')})
                save_en_file(en_path, en_data)

        pending = pending_articles(en_data, cn_articles)
        if not pending:
            continue

        # 达到本轮上限则退出，留给下一轮处理
        if args.max_laws_per_run and laws_processed_in_run >= args.max_laws_per_run:
            print(f"  达到本轮上限（{laws_processed_in_run} 部），退出进程以便重启")
            break

        # ── 按需构建 system prompt ──
        # 只注入当前法律引用的其他法律标题
        ref_law_ids = get_referenced_laws(law_id)
        per_law_title_map = get_law_title_en_map(ref_law_ids, title_map, laws)

        # 只注入当前法律中实际出现的术语
        article_texts = [content for _, content in pending]
        per_law_glossary = find_glossary_terms(article_texts, glossary)

        article_system = build_system_prompt(
            title_map, glossary,
            per_law_title_map=per_law_title_map or None,
            per_law_glossary=per_law_glossary or None
        ) + BATCH_ARTICLE_SUFFIX

        ref_count = len(ref_law_ids)
        term_count = len(per_law_glossary)
        article_count = len(pending)
        print(f"[{idx}/{len(laws_with_pending)}] {title}（{article_count} 条待翻译，引用 {ref_count} 部法律，{term_count} 个术语注入）")

        art_index = {a['article_number']: i for i, a in enumerate(en_data['articles'])}

        # 按字符数动态分组
        batches = []
        if args.batch_size > 0:
            batches = [pending[i:i + args.batch_size] for i in range(0, len(pending), args.batch_size)]
        else:
            batch = []
            batch_chars = 0
            for art_num, content in pending:
                chars = len(content)
                if batch and batch_chars + chars > args.max_batch_chars:
                    batches.append(batch)
                    batch = []
                    batch_chars = 0
                batch.append((art_num, content))
                batch_chars += chars
            if batch:
                batches.append(batch)

        def translate_batch(batch, batch_idx, total_batches):
            import random
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    t0 = time.time()
                    result = translate_articles_batch(api_key, batch, article_system)
                    elapsed = time.time() - t0
                    print(f"    批次 {batch_idx}/{total_batches} 完成（{elapsed:.0f}s，{len(batch)} 条）")
                    return result
                except Exception as exc:
                    if attempt == max_retries - 1:
                        print(f"    批次 {batch_idx}/{total_batches} 失败（已重试{max_retries}次）：{exc}")
                        return {}
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    print(f"    批次 {batch_idx}/{total_batches} 错误，{wait:.0f}s 后重试 ({attempt+1}/{max_retries})：{exc}")
                    time.sleep(wait)

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            batch_list = list(batches)
            total_batches = len(batch_list)
            futures = {ex.submit(translate_batch, b, i+1, total_batches): b for i, b in enumerate(batch_list)}
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
        laws_processed_in_run += 1

    print(f"\n完成：{total_done} 条翻译，{total_errors} 条失败（本轮处理 {laws_processed_in_run} 部）")


if __name__ == "__main__":
    main()
