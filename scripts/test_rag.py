#!/usr/bin/env python3
"""
RAG 法律咨询 - 多步推理 Pipeline
用法：cd /Users/doxie/laws_data && python3 scripts/test_rag.py
"""

import json
import sqlite3
import urllib.request
from pathlib import Path

DB_PATH              = Path("/Users/doxie/laws_data/law_content.db")
ENHANCEMENTS_DB_PATH = Path("/Users/doxie/laws_data/law_enhancements.db")
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL     = "qwen2.5:3b"

# ── 所有合法的 legal_domain 值 ──────────────────────────────────────
ALL_DOMAINS = [
    "宪法相关法",
    "民法典",
    "民法商法",
    "刑法",
    "行政法",
    "经济法",
    "社会法",
    "诉讼与非诉讼程序法",
]

# ── Prompts ────────────────────────────────────────────────────────

CLASSIFY_PROMPT = f"""你是中国法律分类专家。你的任务是：从8个法律部门中，排除与问题【明显无关】的部门。

策略：宁可多保留，不要错误排除。只有在非常确定某个部门与问题完全无关时，才将其放入 excluded。拿不准的一律保留在 relevant。

8个法律部门：
{chr(10).join(f'- {d}' for d in ALL_DOMAINS)}

明显排除的参考规则（仅供参考，不要机械套用）：
- 问题与犯罪/刑罚明显无关 → 可排除「刑法」
- 问题与宪法/选举/立法/监察明显无关 → 可排除「宪法相关法」
- 问题只问实体权利而非如何打官司 → 可排除「诉讼与非诉讼程序法」
- 问题涉及"去哪个法院""如何起诉""诉讼请求""管辖" → 必须保留「诉讼与非诉讼程序法」

输出 JSON，格式：
{{
  "relevant": ["民法典", "民法商法", "社会法", "经济法", "行政法"],
  "excluded": ["刑法", "宪法相关法", "诉讼与非诉讼程序法"],
  "reasoning": "一句话说明只排除了哪些以及理由"
}}

注意：relevant + excluded 必须恰好包含全部8个部门。只输出 JSON，不要其他内容。"""

KEYWORD_PROMPT = """你是中国法律检索专家。从问题中提取适合检索法律条文的关键词。

要求：
1. 每个关键词 2-6 个汉字，使用法律专业术语
2. 输出 4-8 个关键词，从最核心到次要排列
3. 优先使用描述【法律情形/场景/当事人】的词，不要提取【法律后果】类词（如赔偿、处罚、责任、制裁）
4. 只输出 JSON 数组

示例：
问题：试用期最长多久？
输出：["试用期", "劳动合同", "合同期限", "用人单位"]

问题：房东能涨租金吗？
输出：["租金", "租赁合同", "房屋租赁", "承租人", "出租人"]

问题：网上买到假冒商品怎么办？
输出：["消费者权益", "假冒伪劣", "网络购物", "退货退款", "产品质量", "电子商务平台"]

只输出 JSON 数组，不要其他内容。"""

FILTER_PROMPT = """你是中国法律审核专家。逐条判断每条法律条文是否与用户问题直接相关。

对每条条文，只需回答 Y（相关）或 N（不相关）。

判断策略：**宁可多保留，不要错误排除**。只有当你非常确定某条文与用户问题完全无关时，才回答 N。

Y 的情形（凡符合其一即为 Y）：
- 条文规范的法律关系、当事人类型或场景与用户问题一致或有合理关联
- 条文涉及的权利义务可能对用户的处境产生影响
- 条文提供了理解相关规定的背景知识

典型 N 的情形（仅在非常确定时才 N）：
- 问道路交通事故 → 海上交通安全法、噪声污染防治法 → N
- 问网购假货 → 旅游纠纷解释、植物新品种权 → N
- 问普通车祸赔偿 → 拼装车转让特殊规定、时间效力规定 → N

拿不准时，一律回答 Y。

输出格式：每行一个编号和判断，例如：
0: Y
1: N
2: Y

不要输出任何其他内容。"""

ANSWER_PROMPT = """你是中国法律助手。严格根据提供的法律条文回答问题。

输出格式（严格按此结构，不得省略任何部分）：

【结论】
用2-5句话直接回答用户问题的每个子问题，说明当事人的权利和可采取的行动。语言通俗易懂，不要逐条罗列。
- 若用户问了多个问题（如"去哪个法院"+"诉讼请求是什么"），每个问题都要回答
- 诉讼请求的标准表述：请求判令被告返还……；请求判令被告支付……

【参考法条】
列出本回答所依据的法律条文，每条格式：
- 《法律名称》第X条（法律原文 / 司法解释）：条文原文（可适当截取关键部分）

规则：
1. 【严禁】引用任何未在下方提供的法条
2. 【结论】部分不得出现"依据第X条"等引用格式，只说结论
3. 如果提供的条文不足以完整回答，在【结论】末尾注明"（注：以下方面无法从现有法条确认：……）"
4. 【参考法条】中区分法律原文与司法解释
5. 【参考法条】中每条只出现一次，不得重复"""


# ── LLM 调用 ───────────────────────────────────────────────────────

def chat(system: str, user: str, temperature: float = 0.05) -> str:
    payload = json.dumps({
        "model": MODEL,
        "stream": False,
        "options": {"temperature": temperature},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())["message"]["content"]


def parse_json(raw: str, fallback):
    """从模型输出中提取 JSON，失败时返回 fallback"""
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        s = raw.find(start_char)
        e = raw.rfind(end_char) + 1
        if s >= 0 and e > s:
            try:
                return json.loads(raw[s:e])
            except json.JSONDecodeError:
                pass
    return fallback


# ── Step 1: 分类路由 ───────────────────────────────────────────────

def classify_question(question: str, verbose: bool = False) -> dict:
    raw = chat(CLASSIFY_PROMPT, f"问题：{question}")
    if verbose:
        print(f"    [模型原始输出] {raw.strip()}")
    result = parse_json(raw, {"relevant": ALL_DOMAINS, "excluded": [], "reasoning": "分类失败，使用全部领域"})
    # 校验值合法
    result["relevant"] = [d for d in result.get("relevant", []) if d in ALL_DOMAINS]
    result["excluded"] = [d for d in result.get("excluded", []) if d in ALL_DOMAINS]
    if not result["relevant"]:
        result["relevant"] = ALL_DOMAINS
    return result


# ── Step 2: 关键词提取 ─────────────────────────────────────────────

def extract_keywords(question: str, verbose: bool = False) -> list[str]:
    raw = chat(KEYWORD_PROMPT, f"问题：{question}")
    if verbose:
        print(f"    [模型原始输出] {raw.strip()}")
    keywords = parse_json(raw, [])
    if not isinstance(keywords, list):
        return []
    return [k.strip() for k in keywords if isinstance(k, str) and 2 <= len(k.strip()) <= 8]


# ── Step 3 & 4: 分层检索 ──────────────────────────────────────────

def fts_search(kw: str, domains: list[str], categories: list[str],
               limit: int, conn) -> list[tuple]:
    domain_ph  = ",".join("?" * len(domains))
    cat_ph     = ",".join("?" * len(categories))
    cjk = [c for c in kw if '一' <= c <= '鿿']

    if len(cjk) >= 3:
        sql = f"""
            SELECT n.id, l.title, l.legal_domain, l.category,
                   n.article_number, n.content
            FROM nodes_fts f
            JOIN nodes n ON f.rowid = n.id
            JOIN laws  l ON n.law_id = l.id
            WHERE nodes_fts MATCH ?
              AND n.type = 'article'
              AND l.is_current = 1
              AND l.legal_domain IN ({domain_ph})
              AND l.category IN ({cat_ph})
            LIMIT ?
        """
        params = [kw] + domains + categories + [limit]
    elif cjk:
        sql = f"""
            SELECT n.id, l.title, l.legal_domain, l.category,
                   n.article_number, n.content
            FROM nodes_fts_bigram f
            JOIN nodes n ON f.rowid = n.id
            JOIN laws  l ON n.law_id = l.id
            WHERE nodes_fts_bigram MATCH ?
              AND n.type = 'article'
              AND l.is_current = 1
              AND l.legal_domain IN ({domain_ph})
              AND l.category IN ({cat_ph})
            LIMIT ?
        """
        params = [kw] + domains + categories + [limit]
    else:
        return []

    return conn.execute(sql, params).fetchall()


def expand_keywords_with_aliases(keywords: list[str]) -> list[str]:
    """用 term_aliases + alias_patches + keyword_synonyms 三表扩展关键词。"""
    if not ENHANCEMENTS_DB_PATH.exists():
        return keywords
    try:
        conn = sqlite3.connect(ENHANCEMENTS_DB_PATH)
        expanded = list(keywords)
        seen = set(keywords)

        for kw in keywords:
            for table in ("term_aliases", "alias_patches"):
                rows = conn.execute(
                    f"SELECT legal_term FROM {table} WHERE colloquial = ? ORDER BY fts_hits DESC",
                    [kw]
                ).fetchall()
                for (legal_term,) in rows:
                    if legal_term not in seen:
                        seen.add(legal_term)
                        expanded.append(legal_term)

            # keyword_synonyms: LLM 提取词 → 精确法律词
            rows = conn.execute(
                "SELECT target_kw FROM keyword_synonyms WHERE source_kw = ? ORDER BY fts_hits DESC",
                [kw]
            ).fetchall()
            for (target,) in rows:
                if target not in seen:
                    seen.add(target)
                    expanded.append(target)

        conn.close()
        return expanded
    except Exception:
        return keywords


def get_topic_law_hints(keywords: list[str]) -> list[str]:
    """根据关键词从 topic_law_hints 取出优先法律列表。"""
    if not ENHANCEMENTS_DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(ENHANCEMENTS_DB_PATH)
        seen: set[str] = set()
        hints: list[tuple[int, str]] = []
        for kw in keywords:
            rows = conn.execute(
                "SELECT priority, law_title FROM topic_law_hints WHERE topic_keyword = ? ORDER BY priority",
                [kw]
            ).fetchall()
            for priority, title in rows:
                if title not in seen:
                    seen.add(title)
                    hints.append((priority, title))
        conn.close()
        hints.sort(key=lambda x: x[0])
        return [t for _, t in hints]
    except Exception:
        return []


def search_layered(keywords: list[str], domains: list[str],
                   limit_per_kw: int = 10,
                   hint_laws: list[str] | None = None) -> dict:
    """
    分两层检索：
      Layer 1 - 法律原文（category IN 法律/宪法/修正案）
      Layer 2 - 司法解释
    hint_laws: topic_law_hints 命中的法律，优先在其中做额外检索
    返回 {"laws": [...], "interpretations": [...]}
    """
    law_cats    = ["法律", "宪法", "修正案", "法律解释", "监察法规"]
    interp_cats = ["司法解释"]

    conn = sqlite3.connect(DB_PATH)
    seen = set()

    def collect(categories, per_kw, pinned=False):
        results = []
        for kw in keywords:
            for row in fts_search(kw, domains, categories, per_kw, conn):
                nid = row[0]
                if nid not in seen:
                    seen.add(nid)
                    results.append({
                        "id":           nid,
                        "law":          row[1],
                        "legal_domain": row[2],
                        "category":     row[3],
                        "article":      row[4],
                        "content":      row[5],
                        "pinned":       pinned,
                    })
        return results

    def collect_hint_laws(categories, per_kw):
        if not hint_laws:
            return []
        results = []
        ph = ",".join("?" * len(categories))
        # 按命中数升序排列关键词：命中少的词更精确，优先检索使结果靠前
        def kw_hits(kw):
            try:
                return conn.execute(
                    "SELECT COUNT(*) FROM nodes_fts WHERE nodes_fts MATCH ?", [kw]
                ).fetchone()[0]
            except Exception:
                return 999
        sorted_kws = sorted(
            [kw for kw in keywords if len([c for c in kw if '一' <= c <= '鿿']) >= 3],
            key=kw_hits
        )
        for kw in sorted_kws:
            for law_title in hint_laws:
                sql = f"""
                    SELECT n.id, l.title, l.legal_domain, l.category,
                           n.article_number, n.content
                    FROM nodes_fts f
                    JOIN nodes n ON f.rowid = n.id
                    JOIN laws  l ON n.law_id = l.id
                    WHERE nodes_fts MATCH ?
                      AND n.type = 'article'
                      AND l.is_current = 1
                      AND l.title = ?
                      AND l.category IN ({ph})
                    LIMIT ?
                """
                for row in conn.execute(sql, [kw, law_title] + categories + [per_kw]):
                    nid = row[0]
                    if nid not in seen:
                        seen.add(nid)
                        results.append({
                            "id":           nid,
                            "law":          row[1],
                            "legal_domain": row[2],
                            "category":     row[3],
                            "article":      row[4],
                            "content":      row[5],
                            "pinned":       True,   # hint 法律结果跳过过滤
                        })
        return results

    # hint 法律优先插入，保证排在结果前面
    hint_results = collect_hint_laws(law_cats + interp_cats, per_kw=limit_per_kw)
    laws    = hint_results + collect(law_cats,    per_kw=limit_per_kw)
    interps = collect(interp_cats, per_kw=limit_per_kw)
    conn.close()
    return {"laws": laws, "interpretations": interps}


# ── Step 4.5: 相关性过滤 ───────────────────────────────────────────

def filter_articles(question: str, articles: dict, verbose: bool = False,
                    batch_size: int = 8) -> dict:
    all_items = articles["laws"] + articles["interpretations"]
    if not all_items:
        return articles

    # pinned 条文（来自 hint_laws）直接保留，不参与过滤
    pinned = [a for a in all_items if a.get("pinned")]
    to_filter = [a for a in all_items if not a.get("pinned")]

    kept = list(pinned)
    pinned_ids = {a["id"] for a in pinned}

    for batch_start in range(0, len(to_filter), batch_size):
        batch = to_filter[batch_start: batch_start + batch_size]
        numbered = "\n".join(
            f"[{i}] 《{a['law']}》{a['article']}：{a['content'][:150]}"
            for i, a in enumerate(batch)
        )
        user_msg = f"用户问题：{question}\n\n法律条文列表：\n{numbered}"
        raw = chat(FILTER_PROMPT, user_msg)
        if verbose:
            print(f"    [批次 {batch_start//batch_size + 1} 模型输出] {raw.strip()}")

        # 解析 "0: Y\n1: N\n2: Y" 格式
        # 未出现的编号视为 Y（宁可多保留）
        verdicts = {}
        parsed_any = False
        for line in raw.strip().splitlines():
            line = line.strip()
            if ':' in line:
                parts_yn = line.split(':', 1)
                try:
                    idx = int(parts_yn[0].strip())
                    verdict = parts_yn[1].strip().upper()
                    if 0 <= idx < len(batch):
                        parsed_any = True
                        verdicts[idx] = verdict.startswith('Y')
                except ValueError:
                    pass
        if not parsed_any:
            kept_in_batch = list(range(len(batch)))  # 解析失败兜底 = 全保留
        else:
            # 未出现的编号默认保留
            kept_in_batch = [i for i in range(len(batch)) if verdicts.get(i, True)]
        kept += [batch[i] for i in kept_in_batch]

    if not kept:
        kept = all_items  # 兜底：排完了就全保留

    law_ids = {a['id'] for a in articles["laws"]}
    return {
        "laws":            [a for a in kept if a['id'] in law_ids],
        "interpretations": [a for a in kept if a['id'] not in law_ids],
    }


# ── Step 5: 生成回答 ───────────────────────────────────────────────

def build_context(articles: dict, max_articles: int = 20) -> str:
    """
    构建上下文，限制条文总数避免 3b 模型过载。
    优先保留 pinned 条文（来自 topic hints），其次按检索顺序截断。
    """
    all_items = []
    for a in articles["laws"]:
        all_items.append(("laws", a))
    for a in articles["interpretations"]:
        all_items.append(("interp", a))

    # pinned 优先，其余按原顺序，并去重
    pinned = [(t, a) for t, a in all_items if a.get("pinned")]
    others = [(t, a) for t, a in all_items if not a.get("pinned")]
    seen_ids: set = set()
    deduped = []
    for t, a in pinned + others:
        if a["id"] not in seen_ids:
            seen_ids.add(a["id"])
            deduped.append((t, a))
    selected = deduped[:max_articles]

    law_items  = [a for t, a in selected if t == "laws"]
    interp_items = [a for t, a in selected if t == "interp"]

    parts = []
    if law_items:
        parts.append("【法律原文】")
        for a in law_items:
            parts.append(f"《{a['law']}》{a['article']}：{a['content'][:300]}")
    if interp_items:
        parts.append("\n【司法解释】")
        for a in interp_items:
            parts.append(f"《{a['law']}》{a['article']}：{a['content'][:300]}")
    return "\n".join(parts)


def generate_answer(question: str, articles: dict) -> str:
    context = build_context(articles)
    if not context.strip():
        return "未检索到相关条文，无法回答。"
    user_msg = f"以下是检索到的法律条文：\n\n{context}\n\n用户问题：{question}"
    return chat(ANSWER_PROMPT, user_msg, temperature=0.1)


# ── 主流程 ────────────────────────────────────────────────────────

def ask(question: str, verbose: bool = True) -> dict:
    def log(step: str, content: str):
        if verbose:
            print(f"\n  ▶ {step}")
            for line in content.splitlines():
                print(f"    {line}")

    # Step 1: 分类
    if verbose:
        print(f"\n  ▶ Step 1 分类路由 — 调用模型中...")
    classification = classify_question(question, verbose=verbose)
    log("Step 1 分类路由 — 结果",
        f"相关领域: {classification['relevant']}\n"
        f"排除:     {classification['excluded']}\n"
        f"理由:     {classification.get('reasoning', '')}")

    # Step 2: 关键词
    if verbose:
        print(f"\n  ▶ Step 2 关键词提取 — 调用模型中...")
    keywords = extract_keywords(question, verbose=verbose)
    log("Step 2 关键词提取 — 结果", f"关键词: {keywords}")

    if not keywords:
        return {"classification": classification, "keywords": [],
                "articles": {"laws": [], "interpretations": []},
                "answer": "无法提取关键词，请换一种提问方式。"}

    # Step 2.5: 别名扩展 + topic hints
    expanded = expand_keywords_with_aliases(keywords)
    hint_laws = get_topic_law_hints(expanded)
    if verbose:
        if expanded != keywords:
            log("Step 2.5 别名扩展 — 结果",
                f"原始: {keywords}\n扩展: {expanded}")
        if hint_laws:
            log("Step 2.5 Topic hints — 结果",
                "\n".join(f"  {t}" for t in hint_laws))

    # Step 3+4: 分层检索
    articles = search_layered(expanded, classification["relevant"], hint_laws=hint_laws)
    law_detail = "\n".join(
        f"  [{a['legal_domain']}][{a['category']}] 《{a['law']}》{a['article']}: {a['content'][:80]}…"
        for a in articles['laws']
    ) or "  （无结果）"
    interp_detail = "\n".join(
        f"  [{a['legal_domain']}][{a['category']}] 《{a['law']}》{a['article']}: {a['content'][:80]}…"
        for a in articles['interpretations']
    ) or "  （无结果）"
    log(f"Step 3 法律原文检索 — 找到 {len(articles['laws'])} 条", law_detail)
    log(f"Step 4 司法解释检索 — 找到 {len(articles['interpretations'])} 条", interp_detail)

    # 兜底：若分类过窄导致结果稀少，用全部领域重试
    total = len(articles['laws']) + len(articles['interpretations'])
    if total <= 3 and classification["relevant"] != ALL_DOMAINS:
        log("Step 3+4 兜底检索", "结果不足，使用全部领域重试...")
        articles = search_layered(expanded, ALL_DOMAINS, hint_laws=hint_laws)
        law_detail = "\n".join(
            f"  [{a['legal_domain']}][{a['category']}] 《{a['law']}》{a['article']}: {a['content'][:80]}…"
            for a in articles['laws']
        ) or "  （无结果）"
        interp_detail = "\n".join(
            f"  [{a['legal_domain']}][{a['category']}] 《{a['law']}》{a['article']}: {a['content'][:80]}…"
            for a in articles['interpretations']
        ) or "  （无结果）"
        log(f"Step 3 兜底法律原文 — 找到 {len(articles['laws'])} 条", law_detail)
        log(f"Step 4 兜底司法解释 — 找到 {len(articles['interpretations'])} 条", interp_detail)

    # Step 4.5: 相关性过滤
    if verbose:
        print(f"\n  ▶ Step 4.5 相关性过滤 — 调用模型中...")
    before_laws = len(articles['laws'])
    before_interps = len(articles['interpretations'])
    pinned_count = sum(1 for a in articles['laws'] + articles['interpretations'] if a.get('pinned'))
    articles = filter_articles(question, articles, verbose=verbose)
    filter_detail = "\n".join(
        f"  [保留] [{a['legal_domain']}][{a['category']}] 《{a['law']}》{a['article']}"
        for a in articles['laws'] + articles['interpretations']
    ) or "  （全部过滤）"
    log(f"Step 4.5 相关性过滤 — {before_laws + before_interps} 条（{pinned_count} pinned 跳过过滤）→ {len(articles['laws']) + len(articles['interpretations'])} 条", filter_detail)

    # Step 5: 生成
    log("Step 5 生成回答", "调用模型中...")
    answer = generate_answer(question, articles)

    return {
        "classification": classification,
        "keywords":       keywords,
        "articles":       articles,
        "answer":         answer,
    }


# ── 测试 ──────────────────────────────────────────────────────────

QUESTIONS = [
    "劳动合同试用期最长可以是多久？",
    "房东可以在租期内随意涨租金吗？",
    "公司拖欠工资员工可以怎么办？",
    "离婚时夫妻共同财产如何分割？",
    "网上买到假货怎么维权？",
]

if __name__ == "__main__":
    print(f"数据库：{DB_PATH}  模型：{MODEL}")
    print("=" * 70)

    for q in QUESTIONS:
        print(f"\n❓ {q}")
        result = ask(q, verbose=True)
        total = len(result['articles']['laws']) + len(result['articles']['interpretations'])
        print(f"\n  ▶ 最终回答（共引用 {total} 条条文）")
        print(f"\n💬 {result['answer']}")
        print("\n" + "=" * 70)
