#!/usr/bin/env python3
"""
legal_chain_agent.py — 法条链推理 Agent

Pipeline:
  Step 0: 问题拆分（子问题含完整上下文）
  Step 1: 大类分类（刑法/民法/行政法/劳动法/经济法/刑诉/民诉）
  Step 2: 章节定位（在核心法律结构中找相关章节）
  Step 3: 条文检索（章节内精确 + FTS 补充 + 司法解释）
  Step 4: 引用链扩展（解析条文中的交叉引用，追溯相关法条）
  Step 5: 法条链构建（去重、排序、逻辑串联）
  Step 6: 生成结论（带明确引用）

用法：
  cd /Users/doxie/laws_data
  python3 scripts/legal_chain_agent.py
  python3 scripts/legal_chain_agent.py --question "网购假货怎么维权"
  python3 scripts/legal_chain_agent.py --question "..." --provider deepseek
"""

import json
import re
import sqlite3
import time
import sys
import urllib.request
import urllib.error
from pathlib import Path

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# ── 路径 ──────────────────────────────────────────────────────────────

DB_PATH              = Path("/Users/doxie/laws_data/law_content.db")
ENHANCEMENTS_DB_PATH = Path("/Users/doxie/laws_data/law_enhancements.db")

# ── LLM 配置 ──────────────────────────────────────────────────────────

PROVIDERS = {
    "groq": {
        "url":   "https://api.groq.com/openai/v1/chat/completions",
        "key":   "",   # 填入 Groq API Key（https://console.groq.com/keys）
        "model": "llama-3.3-70b-versatile",
    },
    "deepseek": {
        "url":   "https://api.deepseek.com/chat/completions",
        "key":   "",   # 填入 DeepSeek API Key（https://platform.deepseek.com/api_keys）
        "model": "deepseek-chat",
    },
    "ollama": {
        "url":   "http://localhost:11434/api/chat",
        "key":   "",
        "model": "qwen2.5:3b",
    },
}
DEFAULT_PROVIDER = "deepseek"


# ── LLM 客户端 ────────────────────────────────────────────────────────

def _call_openai_compat(cfg: dict, messages: list, temperature: float) -> str:
    payload = {
        "model": cfg["model"],
        "stream": False,
        "temperature": temperature,
        "messages": messages,
    }
    headers = {"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {}

    # requests 库能通过 Groq 的 Cloudflare WAF（urllib 的 User-Agent 会被拦截）
    if _HAS_REQUESTS:
        for attempt in range(3):
            try:
                r = _requests.post(cfg["url"], headers=headers, json=payload, timeout=60)
                if r.status_code == 429 or (r.status_code == 403 and attempt < 2):
                    wait = 2 ** attempt
                    print(f"    [限流] HTTP {r.status_code}，{wait}s 后重试...")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except _requests.HTTPError as e:
                raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:300]}") from e
        raise RuntimeError("重试次数耗尽")

    # fallback: urllib（部分 provider 可能被 WAF 拦截）
    body = json.dumps(payload).encode()
    full_headers = {"Content-Type": "application/json", "User-Agent": "legal-chain-agent/1.0", **headers}
    req = urllib.request.Request(cfg["url"], data=body, headers=full_headers, method="POST")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body_err = e.read().decode()
            if e.code in (429, 403) and attempt < 2:
                wait = 2 ** attempt
                print(f"    [限流] HTTP {e.code}，{wait}s 后重试...")
                time.sleep(wait)
                continue
            raise RuntimeError(f"HTTP {e.code}: {body_err[:300]}") from e
    raise RuntimeError("重试次数耗尽")


def _call_ollama(cfg: dict, messages: list, temperature: float) -> str:
    body = json.dumps({
        "model": cfg["model"],
        "stream": False,
        "options": {"temperature": temperature},
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        cfg["url"], data=body,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())["message"]["content"]


def chat(system: str, user: str, temperature: float = 0.1,
         provider: str = DEFAULT_PROVIDER) -> str:
    cfg = PROVIDERS[provider]
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    if provider == "ollama":
        return _call_ollama(cfg, messages, temperature)
    return _call_openai_compat(cfg, messages, temperature)


def parse_json(raw: str, fallback):
    """从模型输出中提取 JSON，支持 ```json 代码块"""
    # 去除 markdown 代码块围栏
    text = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    for open_ch, close_ch in [('{', '}'), ('[', ']')]:
        s = text.find(open_ch)
        e = text.rfind(close_ch) + 1
        if 0 <= s < e:
            try:
                return json.loads(text[s:e])
            except json.JSONDecodeError:
                pass
    return fallback


# ── 大类定义 ──────────────────────────────────────────────────────────

LEGAL_CATEGORIES = {
    "刑法": {
        "primary_laws": ["中华人民共和国刑法"],
        "domains":      ["刑法"],
        "description":  "犯罪构成、刑事责任、量刑标准、具体罪名",
    },
    "民法": {
        "primary_laws": ["中华人民共和国民法典"],
        "domains":      ["民法典", "民法商法"],
        "description":  "人身权、财产权、合同、侵权责任、婚姻家庭、继承、物权",
    },
    "行政法": {
        "primary_laws": [],
        "domains":      ["行政法", "宪法相关法"],
        "description":  "行政许可、行政处罚、行政复议、政府职责",
    },
    "劳动法": {
        "primary_laws": ["中华人民共和国劳动法", "中华人民共和国劳动合同法"],
        "domains":      ["社会法"],
        "description":  "劳动合同、工资待遇、工作时间、解除劳动关系、劳动争议",
    },
    "经济法": {
        "primary_laws": [
            "中华人民共和国消费者权益保护法",
            "中华人民共和国产品质量法",
            "中华人民共和国电子商务法",
            "中华人民共和国食品安全法",
        ],
        "domains":      ["经济法", "民法商法"],
        "description":  "消费者权益、产品质量、市场监管、电子商务、反不正当竞争",
    },
    "刑事诉讼": {
        "primary_laws": ["中华人民共和国刑事诉讼法"],
        "domains":      ["诉讼与非诉讼程序法"],
        "description":  "刑事案件的侦查、逮捕、起诉、审判、上诉程序",
    },
    "民事诉讼": {
        "primary_laws": ["中华人民共和国民事诉讼法"],
        "domains":      ["诉讼与非诉讼程序法"],
        "description":  "民事案件的管辖、起诉、证据、审判、执行程序",
    },
}

CATEGORY_NAMES = list(LEGAL_CATEGORIES.keys())


# ── 数据库查询 ────────────────────────────────────────────────────────

def _conn():
    return sqlite3.connect(DB_PATH)


def get_law_id(title: str) -> int | None:
    """精确匹配法律 id"""
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM laws WHERE title = ? AND is_current = 1 LIMIT 1", [title]
        ).fetchone()
        return row[0] if row else None


def get_law_structure(law_id: int) -> list[dict]:
    """获取法律的编/章/节结构（不含条文），用于章节定位"""
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, type, title, content, global_order
               FROM nodes
               WHERE law_id = ? AND type IN ('part','chapter','section')
               ORDER BY global_order""",
            [law_id]
        ).fetchall()
    return [
        {"id": r[0], "type": r[1], "title": r[2], "content": r[3], "order": r[4]}
        for r in rows
    ]


def get_articles_in_node(node_id: int, law_id: int) -> list[dict]:
    """获取某章节下的所有条文（递归子节点）"""
    with _conn() as conn:
        # 直接子条文
        rows = conn.execute(
            """SELECT id, article_number, article_num, content
               FROM nodes
               WHERE parent_id = ? AND type = 'article'
               ORDER BY global_order""",
            [node_id]
        ).fetchall()
        # 子节点（section）下的条文
        sub_nodes = conn.execute(
            "SELECT id FROM nodes WHERE parent_id = ? AND type = 'section'", [node_id]
        ).fetchall()
    articles = [
        {"id": r[0], "article_number": r[1], "article_num": r[2], "content": r[3]}
        for r in rows
    ]
    for (sub_id,) in sub_nodes:
        articles.extend(get_articles_in_node(sub_id, law_id))
    return articles


def fts_search_in_law(keyword: str, law_title: str,
                      categories: list[str] | None = None,
                      limit: int = 10) -> list[dict]:
    """在指定法律内 FTS 检索"""
    cjk = [c for c in keyword if '一' <= c <= '鿿']
    if len(cjk) < 3:
        return []
    cats = categories or ["法律", "宪法", "修正案", "法律解释", "监察法规", "司法解释"]
    cat_ph = ",".join("?" * len(cats))
    with _conn() as conn:
        rows = conn.execute(
            f"""SELECT n.id, l.title, l.category, n.article_number, n.article_num, n.content
                FROM nodes_fts f
                JOIN nodes n ON f.rowid = n.id
                JOIN laws  l ON n.law_id = l.id
                WHERE nodes_fts MATCH ?
                  AND n.type = 'article' AND l.is_current = 1
                  AND l.title = ?
                  AND l.category IN ({cat_ph})
                LIMIT ?""",
            [keyword, law_title] + cats + [limit]
        ).fetchall()
    return [
        {"id": r[0], "law": r[1], "category": r[2],
         "article_number": r[3], "article_num": r[4], "content": r[5]}
        for r in rows
    ]


def fts_search_domains(keyword: str, domains: list[str],
                       categories: list[str], limit: int = 10) -> list[dict]:
    """在指定 domain 范围内 FTS 检索"""
    cjk = [c for c in keyword if '一' <= c <= '鿿']
    if not cjk:
        return []
    domain_ph = ",".join("?" * len(domains))
    cat_ph    = ",".join("?" * len(categories))
    fts_table = "nodes_fts" if len(cjk) >= 3 else "nodes_fts_bigram"
    # bigram: join each CJK char with space
    kw = keyword if len(cjk) >= 3 else " ".join(c for c in keyword if '一' <= c <= '鿿')
    with _conn() as conn:
        rows = conn.execute(
            f"""SELECT n.id, l.title, l.category, n.article_number, n.article_num, n.content
                FROM {fts_table} f
                JOIN nodes n ON f.rowid = n.id
                JOIN laws  l ON n.law_id = l.id
                WHERE {fts_table} MATCH ?
                  AND n.type = 'article' AND l.is_current = 1
                  AND l.legal_domain IN ({domain_ph})
                  AND l.category IN ({cat_ph})
                LIMIT ?""",
            [kw] + domains + categories + [limit]
        ).fetchall()
    return [
        {"id": r[0], "law": r[1], "category": r[2],
         "article_number": r[3], "article_num": r[4], "content": r[5]}
        for r in rows
    ]


def find_article_by_ref(law_title_fragment: str, article_number_str: str) -> dict | None:
    """根据法律名称片段和条号（文字或数字）查找条文"""
    # 标准化：第X条 中的汉字数字 → 尝试直接匹配 article_number 字段
    with _conn() as conn:
        rows = conn.execute(
            """SELECT n.id, l.title, l.category, n.article_number, n.article_num, n.content
               FROM nodes n JOIN laws l ON n.law_id = l.id
               WHERE l.title LIKE ? AND n.article_number = ? AND l.is_current = 1
               LIMIT 1""",
            [f"%{law_title_fragment}%", article_number_str]
        ).fetchone()
    if rows:
        return {"id": rows[0], "law": rows[1], "category": rows[2],
                "article_number": rows[3], "article_num": rows[4], "content": rows[5]}
    return None


def get_judicial_interpretations_for_law(law_title: str, limit: int = 5) -> list[dict]:
    """获取与某部法律相关的司法解释列表"""
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, title FROM laws
               WHERE category = '司法解释' AND is_current = 1
                 AND (title LIKE ? OR promulgation_info LIKE ?)
               ORDER BY pub_date DESC LIMIT ?""",
            [f"%{law_title[:6]}%", f"%{law_title[:6]}%", limit]
        ).fetchall()
    return [{"law_id": r[0], "title": r[1]} for r in rows]


# ── Step 0: 问题拆分 ──────────────────────────────────────────────────

DECOMPOSE_PROMPT = """你是中国法律助手。分析用户的问题，判断是否需要拆分。

拆分原则：
1. 如果问题只涉及一个法律问题，输出只包含原问题的数组
2. 如果问题涉及多个独立的法律关系（如：既问赔偿权利，又问诉讼程序），拆成2-4个子问题
3. 每个子问题必须包含足够上下文（不能只说"如何赔偿"，要说"网购假货时消费者如何向平台索赔"）
4. 子问题之间可以有逻辑关联，但每个都能独立回答

只输出 JSON 数组，每个元素是一个完整的子问题字符串。不要其他内容。

示例：
问题：我在网上买到假冒商品，商家不退款，我能怎么办？去哪个法院告？
输出：[
  "网购买到假冒商品，商家拒不退款，消费者可以主张哪些赔偿权利？",
  "消费者因网购假货与商家发生纠纷，应向哪个法院提起民事诉讼？"
]"""


def decompose_question(question: str, provider: str = DEFAULT_PROVIDER,
                       verbose: bool = False) -> list[str]:
    raw = chat(DECOMPOSE_PROMPT, f"问题：{question}", temperature=0.1, provider=provider)
    if verbose:
        print(f"    [拆分原始输出] {raw.strip()[:200]}")
    result = parse_json(raw, [question])
    if not isinstance(result, list) or not result:
        return [question]
    subs = [s.strip() for s in result if isinstance(s, str) and s.strip()]
    return subs if subs else [question]


# ── Step 1: 大类分类 ──────────────────────────────────────────────────

CLASSIFY_PROMPT = f"""你是中国法律分类专家。将问题归入以下法律大类（可多选）：

{chr(10).join(f'- {name}：{info["description"]}' for name, info in LEGAL_CATEGORIES.items())}

规则：
- 同一问题可以同时属于多个大类（如劳动争议诉讼 → 劳动法 + 民事诉讼）
- 宁可多选，不要漏选
- 问涉及诉讼程序/管辖/起诉方法 → 必须包含「民事诉讼」或「刑事诉讼」

只输出 JSON 数组，包含匹配的大类名称。不要其他内容。
示例：["民法", "经济法"]"""


def classify_to_categories(question: str, provider: str = DEFAULT_PROVIDER,
                            verbose: bool = False) -> list[str]:
    raw = chat(CLASSIFY_PROMPT, f"问题：{question}", temperature=0.01, provider=provider)
    if verbose:
        print(f"    [分类原始输出] {raw.strip()}")
    result = parse_json(raw, [])
    if not isinstance(result, list):
        return list(LEGAL_CATEGORIES.keys())
    cats = [c for c in result if c in LEGAL_CATEGORIES]
    return cats if cats else list(LEGAL_CATEGORIES.keys())


# ── Step 2: 章节定位 ──────────────────────────────────────────────────

def _build_structure_text(structure: list[dict]) -> str:
    lines = []
    for node in structure:
        indent = "  " if node["type"] == "section" else ""
        title = node["title"] or node["content"] or ""
        lines.append(f"[{node['id']}] {indent}{node['type'].upper()}: {title}")
    return "\n".join(lines)


CHAPTER_PROMPT = """你是法律检索专家。根据用户问题，从以下法律章节结构中选出最相关的章节。

规则：
- 只选与问题直接相关的章节（编/章/节）
- 最多选5个，精准优于全覆盖
- 输出 JSON 数组，包含章节的 id（方括号中的数字）

只输出 JSON 数组。不要其他内容。"""


def navigate_chapters(question: str, law_title: str,
                      provider: str = DEFAULT_PROVIDER,
                      verbose: bool = False) -> list[int]:
    """返回相关章节的 node_id 列表"""
    law_id = get_law_id(law_title)
    if law_id is None:
        return []
    structure = get_law_structure(law_id)
    if not structure:
        return []

    structure_text = _build_structure_text(structure)
    user_msg = f"问题：{question}\n\n法律结构：\n{structure_text}"
    raw = chat(CHAPTER_PROMPT, user_msg, temperature=0.01, provider=provider)
    if verbose:
        print(f"    [章节定位输出] {raw.strip()}")

    ids = parse_json(raw, [])
    if not isinstance(ids, list):
        return []
    # flatten nested lists or objects (some models return [[id1], {"id": id2}])
    flat = []
    for x in ids:
        if isinstance(x, list):
            flat.extend(x)
        elif isinstance(x, dict) and "id" in x:
            flat.append(x["id"])
        else:
            flat.append(x)
    valid_ids = {n["id"] for n in structure}
    return [int(x) for x in flat if isinstance(x, (int, str)) and int(x) in valid_ids]


# ── Step 3: 条文检索 ──────────────────────────────────────────────────

KEYWORD_PROMPT = """你是中国法律检索专家。从问题中提取法律检索关键词。

要求：
1. 每个关键词 2-6 个汉字，使用法律专业术语
2. 输出 4-8 个，从最核心到次要排列
3. 优先提取【法律情形/场景/当事人类型】的词，而非【法律后果】类词

只输出 JSON 数组。不要其他内容。"""


def extract_keywords(question: str, provider: str = DEFAULT_PROVIDER) -> list[str]:
    raw = chat(KEYWORD_PROMPT, f"问题：{question}", temperature=0.01, provider=provider)
    result = parse_json(raw, [])
    if not isinstance(result, list):
        return []
    return [k.strip() for k in result if isinstance(k, str) and 2 <= len(k.strip()) <= 10]


def retrieve_articles(question: str, categories: list[str],
                      provider: str = DEFAULT_PROVIDER,
                      verbose: bool = False) -> list[dict]:
    """
    分层检索：
    1. 有主体法律的大类 → 章节定位 → 章节内条文
    2. 关键词 FTS → 补充条文
    3. 相关司法解释
    """
    seen_ids: set[int] = set()
    results: list[dict] = []

    def add(article: dict, source: str, pinned: bool = False):
        if article["id"] not in seen_ids:
            seen_ids.add(article["id"])
            article["source"] = source
            article["pinned"] = pinned
            results.append(article)

    keywords = extract_keywords(question, provider=provider)
    if verbose:
        print(f"    关键词: {keywords}")

    # ── Layer 1: 主体法律章节导航 ──
    for cat in categories:
        info = LEGAL_CATEGORIES[cat]
        for law_title in info["primary_laws"]:
            if verbose:
                print(f"    章节导航: 《{law_title}》")
            chapter_ids = navigate_chapters(question, law_title, provider=provider, verbose=verbose)
            law_id = get_law_id(law_title)
            chapter_article_count = 0
            for ch_id in chapter_ids:
                for art in get_articles_in_node(ch_id, law_id or 0):
                    art["law"]      = law_title
                    art["category"] = "法律"
                    add(art, f"章节导航:{law_title}", pinned=True)
                    chapter_article_count += 1
                    if chapter_article_count >= 25:  # cap per law
                        break
                if chapter_article_count >= 25:
                    break

            # FTS 补充：在主体法律内按关键词搜索
            for kw in keywords:
                for art in fts_search_in_law(kw, law_title):
                    add(art, f"FTS:{law_title}")

    # ── Layer 2: 领域范围 FTS ──
    domains = []
    for cat in categories:
        domains.extend(LEGAL_CATEGORIES[cat]["domains"])
    domains = list(dict.fromkeys(domains))  # 去重保序

    law_cats   = ["法律", "宪法", "修正案", "法律解释", "监察法规"]
    interp_cats = ["司法解释"]

    for kw in keywords:
        for art in fts_search_domains(kw, domains, law_cats):
            add(art, "FTS-法律")
        for art in fts_search_domains(kw, domains, interp_cats):
            add(art, "FTS-司法解释")

    # ── Layer 3: 找相关司法解释 ──
    for cat in categories:
        for law_title in LEGAL_CATEGORIES[cat]["primary_laws"]:
            for interp in get_judicial_interpretations_for_law(law_title):
                for kw in keywords[:3]:  # 只用核心关键词
                    for art in fts_search_in_law(kw, interp["title"], categories=interp_cats):
                        add(art, f"司法解释:{interp['title']}")

    if verbose:
        print(f"    检索到 {len(results)} 条条文")
    return results


# ── Step 4: 引用链扩展 ──────────────────────────────────────────────

# 匹配条文中对其他法律条文的引用，如：《中华人民共和国消费者权益保护法》第五十五条
_REF_PATTERN = re.compile(
    r'《([^》]{4,30})》第([一二三四五六七八九十百千零\d]+)条'
)
# 匹配同法内引用，如：本法第X条、依照第X条
_SELF_REF_PATTERN = re.compile(
    r'(?:本法|依照|适用|参照)第([一二三四五六七八九十百千零\d]+)条'
)


def _normalize_article_number(num_str: str) -> str:
    """将'第五十五条'格式保留为原始字符串（与DB中article_number格式一致）"""
    return f"第{num_str}条"


def expand_references(articles: list[dict],
                      verbose: bool = False) -> list[dict]:
    """
    解析条文中的交叉引用，追加被引用的条文。
    """
    seen_ids = {a["id"] for a in articles}
    new_articles: list[dict] = []

    for art in articles:
        content = art.get("content", "")

        # 外部法律引用
        for m in _REF_PATTERN.finditer(content):
            law_frag   = m.group(1)
            art_num    = _normalize_article_number(m.group(2))
            ref = find_article_by_ref(law_frag, art_num)
            if ref and ref["id"] not in seen_ids:
                seen_ids.add(ref["id"])
                ref["source"] = f"引用链:{art['article_number']}→{art_num}"
                ref["pinned"] = False
                new_articles.append(ref)
                if verbose:
                    print(f"    引用链: {art['article_number']} → 《{law_frag}》{art_num}")

        # 同法内引用（需要知道当前法律名称）
        law_title = art.get("law", "")
        for m in _SELF_REF_PATTERN.finditer(content):
            art_num = _normalize_article_number(m.group(1))
            ref = find_article_by_ref(law_title, art_num)
            if ref and ref["id"] not in seen_ids:
                seen_ids.add(ref["id"])
                ref["source"] = f"同法引用:{art['article_number']}→{art_num}"
                ref["pinned"] = False
                new_articles.append(ref)

    if verbose and new_articles:
        print(f"    引用链扩展: +{len(new_articles)} 条")
    return articles + new_articles


# ── Step 4.5: 相关性过滤 ──────────────────────────────────────────────

FILTER_PROMPT = """你是中国法律审核专家。判断每条法律条文是否与用户问题直接相关。

策略：宁可多保留，不要错误排除。只有非常确定完全无关时才回答 N。

输出格式：每行 "编号: Y" 或 "编号: N"，不要其他内容。"""


def filter_articles(question: str, articles: list[dict],
                    provider: str = DEFAULT_PROVIDER,
                    batch_size: int = 8,
                    verbose: bool = False) -> list[dict]:
    # Filter everything — pinned articles get lenient treatment but still filtered
    all_articles = articles
    kept: list[dict] = []

    for start in range(0, len(all_articles), batch_size):
        batch = all_articles[start:start + batch_size]
        numbered = "\n".join(
            f"[{i}] 《{a.get('law','')}》{a.get('article_number','')}：{a.get('content','')[:150]}"
            for i, a in enumerate(batch)
        )
        try:
            raw = chat(FILTER_PROMPT, f"用户问题：{question}\n\n{numbered}",
                       temperature=0.01, provider=provider)
        except Exception:
            kept += batch
            continue
        verdicts: dict[int, bool] = {}
        for line in raw.strip().splitlines():
            if ':' in line:
                parts = line.split(':', 1)
                try:
                    idx = int(parts[0].strip())
                    verdicts[idx] = not parts[1].strip().upper().startswith('N')
                except ValueError:
                    pass
        for i, a in enumerate(batch):
            # pinned articles: keep unless explicitly N
            # non-pinned: keep only if Y (default False when no verdict)
            default = True if a.get("pinned") else True  # lenient by default
            if verdicts.get(i, default):
                kept.append(a)

    return kept if kept else articles


# ── Step 5: 法条链构建 ────────────────────────────────────────────────

CHAIN_ORDER_PROMPT = """你是中国法律专家。将以下法律条文按逻辑推理顺序排列，构成一条清晰的法条链。

排列原则：
1. 基础性/定义性条文在前
2. 权利义务条文在中
3. 救济/程序条文在后
4. 同一法律的条文尽量相邻
5. 最多保留 12 条最核心的条文

输出 JSON 数组，包含条文 id（整数）。不要其他内容。"""


def build_chain(articles: list[dict],
                question: str,
                provider: str = DEFAULT_PROVIDER,
                verbose: bool = False) -> list[dict]:
    if len(articles) <= 3:
        return articles

    items_text = "\n".join(
        f"[id:{a['id']}] 《{a.get('law','')}》{a.get('article_number','')}：{a.get('content','')[:100]}"
        for a in articles
    )
    raw = chat(CHAIN_ORDER_PROMPT,
               f"问题：{question}\n\n条文列表：\n{items_text}",
               temperature=0.01, provider=provider)
    ordered_ids = parse_json(raw, [])
    if not isinstance(ordered_ids, list) or not ordered_ids:
        return articles[:12]

    id_to_art = {a["id"]: a for a in articles}
    chain = [id_to_art[i] for i in ordered_ids if i in id_to_art]
    # 补回未被排序但有的条文（最多到12条）
    included = {a["id"] for a in chain}
    for a in articles:
        if a["id"] not in included and len(chain) < 12:
            chain.append(a)

    if verbose:
        print(f"    法条链: {len(chain)} 条")
        for a in chain:
            print(f"      《{a.get('law','')}》{a.get('article_number','')} [{a.get('source','')}]")
    return chain


# ── Step 6: 生成结论 ──────────────────────────────────────────────────

ANSWER_PROMPT = """你是中国法律助手。根据以下法条链，直接回答用户问题。

要求：
1. 语言通俗易懂，用2-5句话给出明确结论
2. 说明用户可以采取的具体行动
3. 可以提及具体赔偿倍数（十倍、三倍等）
4. 在回答末尾用「引用法条：」列出你实际引用的条文（格式：《法律名》第X条）
5. 不要说"依据第X条"，而是直接陈述结论，最后再列引用
6. 如果涉及诉讼程序，说明应去哪个法院

诉讼通用知识（无需法条支撑）：
- 合同纠纷：被告住所地或合同履行地法院
- 房屋租赁：房屋所在地法院（不动产专属管辖）
- 劳动争议：先劳动仲裁，再起诉
- 侵权：侵权行为地或被告住所地法院"""


def build_context(chain: list[dict]) -> str:
    parts = []
    law_arts  = [a for a in chain if a.get("category") != "司法解释"]
    interp_arts = [a for a in chain if a.get("category") == "司法解释"]
    if law_arts:
        parts.append("【法律原文】")
        for a in law_arts:
            parts.append(f"《{a.get('law','')}》{a.get('article_number','')}：{a.get('content','')[:500]}")
    if interp_arts:
        parts.append("\n【司法解释】")
        for a in interp_arts:
            parts.append(f"《{a.get('law','')}》{a.get('article_number','')}：{a.get('content','')[:500]}")
    return "\n".join(parts)


def generate_answer(question: str, chain: list[dict],
                    provider: str = DEFAULT_PROVIDER) -> str:
    context = build_context(chain)
    if not context.strip():
        return "未检索到相关条文，无法回答。"
    user_msg = f"法条链：\n\n{context}\n\n用户问题：{question}"
    return chat(ANSWER_PROMPT, user_msg, temperature=0.2, provider=provider)


# ── 主流程 ────────────────────────────────────────────────────────────

def ask(question: str, provider: str = DEFAULT_PROVIDER,
        verbose: bool = True) -> dict:

    def log(step: str, content: str = ""):
        if verbose:
            print(f"\n{'─'*60}")
            print(f"▶ {step}")
            if content:
                for line in content.splitlines():
                    print(f"  {line}")

    print(f"\n{'═'*60}")
    print(f"❓ {question}")
    print(f"   Provider: {provider} / {PROVIDERS[provider]['model']}")

    # ── Step 0: 问题拆分 ──
    log("Step 0  问题拆分")
    sub_questions = decompose_question(question, provider=provider, verbose=verbose)
    if len(sub_questions) > 1:
        log("拆分结果", "\n".join(f"{i+1}. {q}" for i, q in enumerate(sub_questions)))
    else:
        print("  → 无需拆分，直接处理")

    all_answers = []

    for sq_idx, sq in enumerate(sub_questions):
        if len(sub_questions) > 1:
            print(f"\n{'·'*50}")
            print(f"  子问题 {sq_idx+1}/{len(sub_questions)}: {sq}")

        # ── Step 1: 大类分类 ──
        log(f"Step 1  大类分类")
        categories = classify_to_categories(sq, provider=provider, verbose=verbose)
        log("分类结果", "、".join(categories))

        # ── Step 2+3: 章节定位 + 条文检索 ──
        log("Step 2+3  章节定位 + 条文检索")
        articles = retrieve_articles(sq, categories, provider=provider, verbose=verbose)

        if not articles:
            log("⚠️  无检索结果，扩大范围重试")
            articles = retrieve_articles(sq, list(LEGAL_CATEGORIES.keys()),
                                         provider=provider, verbose=False)

        log(f"检索结果", f"共 {len(articles)} 条（其中 {sum(a.get('pinned',False) for a in articles)} 条来自章节导航）")
        if verbose:
            for a in articles[:8]:
                cat_tag = "[司法解释]" if a.get("category") == "司法解释" else "[法律]"
                print(f"  {cat_tag} 《{a.get('law','')}》{a.get('article_number','')} [{a.get('source','')}]")
            if len(articles) > 8:
                print(f"  ... 另有 {len(articles)-8} 条")

        # ── Step 4: 引用链扩展 ──
        log("Step 4  引用链扩展")
        articles = expand_references(articles, verbose=verbose)

        # ── Step 4.5: 相关性过滤 ──
        log("Step 4.5  相关性过滤")
        before = len(articles)
        # Pre-cap: if too many, prioritize pinned first, then limit total to 40
        if len(articles) > 40:
            pinned_arts = [a for a in articles if a.get("pinned")]
            other_arts  = [a for a in articles if not a.get("pinned")]
            articles    = (pinned_arts[:30] + other_arts[:10])
        articles = filter_articles(sq, articles, provider=provider, verbose=verbose)
        log("过滤结果", f"{before} → {len(articles)} 条")

        # ── Step 5: 法条链构建 ──
        log("Step 5  法条链构建")
        chain = build_chain(articles, sq, provider=provider, verbose=verbose)

        # ── Step 6: 生成结论 ──
        log("Step 6  生成结论")
        answer = generate_answer(sq, chain, provider=provider)

        all_answers.append({
            "sub_question": sq,
            "categories":   categories,
            "chain":        chain,
            "answer":       answer,
        })

        print(f"\n💬 {answer}")

    # 如果有多个子问题，生成综合结论
    final_answer = ""
    if len(all_answers) == 1:
        final_answer = all_answers[0]["answer"]
    else:
        combined = "\n\n".join(
            f"子问题{i+1}（{r['sub_question']}）：\n{r['answer']}"
            for i, r in enumerate(all_answers)
        )
        final_answer = combined

    return {
        "question":    question,
        "sub_results": all_answers,
        "answer":      final_answer,
    }


# ── 入口 ──────────────────────────────────────────────────────────────

DEMO_QUESTIONS = [
    "网上买到假货商家不退款，我可以要求多少赔偿？去哪个法院起诉？",
    "公司拖欠工资两个月，员工可以怎么办？",
    "房东在租期内突然涨租金并要求我搬走，我有什么权利？",
    "试用期被辞退，公司说不给补偿，合法吗？",
]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="法条链推理 Agent")
    parser.add_argument("--question", "-q", type=str, default=None, help="输入问题")
    parser.add_argument("--provider", "-p", type=str,
                        default=DEFAULT_PROVIDER, choices=list(PROVIDERS.keys()),
                        help="LLM 服务商")
    parser.add_argument("--all", action="store_true", help="跑所有演示问题")
    args = parser.parse_args()

    if args.question:
        ask(args.question, provider=args.provider)
    elif args.all:
        for q in DEMO_QUESTIONS:
            ask(q, provider=args.provider)
            print()
    else:
        # 交互模式
        print(f"法条链推理 Agent  (provider: {args.provider})")
        print("输入问题后回车，输入 'q' 退出\n")
        while True:
            try:
                q = input("❓ ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n退出")
                break
            if not q or q.lower() in ('q', 'quit', 'exit'):
                break
            ask(q, provider=args.provider)
