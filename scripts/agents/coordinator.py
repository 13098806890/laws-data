import re
from typing import Optional

from .core.llm import chat, parse_json
from .core.db import (
    get_law_id, get_law_structure, get_articles_in_node,
    fts_search_in_law, fts_search_domains, expand_references,
)
from .core.models import SubExpert, ExpertGroup
from .experts.civil import ALL_CIVIL_EXPERTS
from .experts.criminal import ALL_CRIMINAL_EXPERTS
from .experts.labor import ALL_LABOR_EXPERTS
from .experts.economic import ALL_ECONOMIC_EXPERTS
from .experts.procedure import ALL_PROCEDURE_EXPERTS
from .experts.procedure import ADMIN_PROCEDURE_EXPERT


# ── 专家组定义 ────────────────────────────────────────────────────────

ALL_GROUPS: dict[str, ExpertGroup] = {
    "民法专家组": ExpertGroup(
        name="民法专家组",
        description="处理民事法律问题：合同、物权、侵权、婚姻家庭、继承、人格权",
        sub_experts=ALL_CIVIL_EXPERTS,
        routing_keywords=[
            "合同", "违约", "租赁", "买卖", "借款", "物权", "所有权", "抵押",
            "侵权", "赔偿", "伤害", "离婚", "抚养", "继承", "遗产", "遗嘱",
            "名誉", "隐私", "肖像", "人格权", "民法典",
        ],
    ),
    "刑法专家组": ExpertGroup(
        name="刑法专家组",
        description="处理刑事犯罪问题：财产犯罪、人身伤害、经济犯罪、职务犯罪",
        sub_experts=ALL_CRIMINAL_EXPERTS,
        routing_keywords=[
            "犯罪", "刑事", "坐牢", "判刑", "立案", "报案", "刑法",
            "盗窃", "诈骗", "抢劫", "故意伤害", "故意杀人", "强奸",
            "贪污", "受贿", "渎职", "走私", "合同诈骗",
        ],
    ),
    "劳动法专家组": ExpertGroup(
        name="劳动法专家组",
        description="处理劳动关系问题：劳动合同、工资、工伤、劳动争议",
        sub_experts=ALL_LABOR_EXPERTS,
        routing_keywords=[
            "劳动", "工资", "加班费", "辞退", "解雇", "工伤", "职业病",
            "劳动合同", "经济补偿", "仲裁", "劳动争议", "试用期",
            "社保", "五险一金", "拖欠工资",
        ],
    ),
    "行政法专家组": ExpertGroup(
        name="行政法专家组",
        description="处理行政机关与公民的法律关系：行政处罚、许可、复议",
        sub_experts=[ADMIN_PROCEDURE_EXPERT],
        routing_keywords=[
            "行政", "政府", "处罚", "吊销", "罚款", "许可证", "审批",
            "拆迁", "征收", "行政复议", "行政诉讼", "公安", "工商",
        ],
    ),
    "经济法专家组": ExpertGroup(
        name="经济法专家组",
        description="处理市场监管、消费者权益、公司商事法律问题",
        sub_experts=ALL_ECONOMIC_EXPERTS,
        routing_keywords=[
            "消费者", "购物", "假货", "退款", "维权", "质量", "产品缺陷",
            "网购", "电商", "平台", "公司", "股东", "破产",
            "食品安全", "三倍赔偿", "十倍赔偿",
        ],
    ),
    "诉讼专家组": ExpertGroup(
        name="诉讼专家组",
        description="处理诉讼程序、管辖、证据、仲裁等程序性问题",
        sub_experts=ALL_PROCEDURE_EXPERTS,
        routing_keywords=[
            "诉讼", "起诉", "法院", "仲裁", "管辖", "证据", "上诉",
            "执行", "保全", "查封", "冻结", "程序", "时效",
            "民诉", "刑诉", "去哪告",
        ],
    ),
}


# ── 路由 ──────────────────────────────────────────────────────────────

_ROUTE_SYSTEM = """你是中国法律问题协调员。判断以下问题应由哪些专家组处理。

可用专家组：
{groups}

规则：
- 可以选多个专家组（如劳动争议诉讼 → 劳动法专家组 + 诉讼专家组）
- 纯程序性问题（如"去哪个法院起诉"）必须包含诉讼专家组
- 劳动关系问题（工资/解雇/加班/工伤/劳动合同）→ 劳动法专家组，不要选经济法专家组
- 经济法专家组仅用于消费者权益、网购、产品质量、食品安全、公司登记注册等非劳动关系场景
- 宁可多选，不要漏选

只输出 JSON 数组，包含专家组名称。不要其他内容。
示例：["民法专家组", "诉讼专家组"]"""


def identify_groups(question: str) -> list[str]:
    group_desc = "\n".join(
        f"- {name}：{g.description}" for name, g in ALL_GROUPS.items()
    )
    system = _ROUTE_SYSTEM.format(groups=group_desc)
    raw = chat(system, f"问题：{question}", temperature=0.01)
    result = parse_json(raw, [])
    if not isinstance(result, list):
        return _keyword_route(question)
    valid = [g for g in result if g in ALL_GROUPS]
    return valid if valid else _keyword_route(question)


def _keyword_route(question: str) -> list[str]:
    matched = []
    for name, group in ALL_GROUPS.items():
        for kw in group.routing_keywords:
            if kw in question:
                if name not in matched:
                    matched.append(name)
                break
    return matched or list(ALL_GROUPS.keys())[:2]


# ── 子专家选择 ────────────────────────────────────────────────────────

_SUB_EXPERT_SYSTEM = """你是{group_name}。根据用户问题，从以下细分专家中选出需要参与分析的专家。

细分专家：
{experts}

规则：
- 只选与问题直接相关的专家（1-3个为宜）
- 如果是笼统问题，选最可能相关的1-2个

只输出 JSON 数组，包含专家名称。不要其他内容。"""


def identify_sub_experts(group: ExpertGroup, question: str,
                          known_facts: dict[str, str]) -> list[SubExpert]:
    expert_desc = "\n".join(f"- {e.name}：{e.domain}" for e in group.sub_experts)
    system = _SUB_EXPERT_SYSTEM.format(group_name=group.name, experts=expert_desc)
    ctx = f"问题：{question}"
    if known_facts:
        ctx += "\n已知信息：" + "；".join(f"{k}={v}" for k, v in known_facts.items())
    raw = chat(system, ctx, temperature=0.01)
    result = parse_json(raw, [])
    if not isinstance(result, list):
        return group.sub_experts[:2]
    name_to_expert = {e.name: e for e in group.sub_experts}
    selected = [name_to_expert[n] for n in result if n in name_to_expert]
    return selected if selected else group.sub_experts[:1]


# ── 信息提取与收集 ────────────────────────────────────────────────────

def auto_extract_facts(question: str, sub_experts: list[SubExpert]) -> dict[str, str]:
    facts: dict[str, str] = {}
    for expert in sub_experts:
        for field_name, _, hint_pattern in expert.required_info:
            if field_name in facts or not hint_pattern:
                continue
            try:
                m = re.search(hint_pattern, question)
                if m:
                    facts[field_name] = m.group(0)
            except re.error:
                pass
    return facts


def collect_missing_info(sub_experts: list[SubExpert],
                          known_facts: dict[str, str]) -> list[tuple[str, str]]:
    seen_fields: set[str] = set(known_facts.keys())
    missing: list[tuple[str, str]] = []
    for expert in sub_experts:
        for field_name, question_text, _ in expert.required_info:
            if field_name not in seen_fields:
                seen_fields.add(field_name)
                missing.append((field_name, question_text))
    return missing


def ask_missing_info(missing_fields: list[tuple[str, str]]) -> dict[str, str]:
    print("\n📋 为了给您更准确的分析，请补充以下信息（直接回车跳过）：")
    answers: dict[str, str] = {}
    for i, (field_name, question_text) in enumerate(missing_fields, 1):
        try:
            val = input(f"  {i}. {question_text} → ").strip()
        except (EOFError, KeyboardInterrupt):
            val = ""
        if val:
            answers[field_name] = val
    return answers


# ── 子专家检索 ────────────────────────────────────────────────────────

def _extract_kws_simple(text: str) -> list[str]:
    _COMMON = [
        "违约责任", "合同解除", "损害赔偿", "劳动合同", "经济补偿",
        "工资拖欠", "工伤认定", "消费者权益", "假冒伪劣", "欺诈",
        "名誉权", "隐私权", "故意伤害", "贪污受贿", "诉讼时效",
        "合同诈骗", "刑事责任", "行政处罚", "侵权责任", "财产保全",
        "婚姻家庭", "遗产继承", "股东权利", "产品责任", "平台责任",
    ]
    found = [kw for kw in _COMMON if kw in text]
    for m in re.finditer(r'[一-鿿]{3,6}', text):
        w = m.group(0)
        if w not in found:
            found.append(w)
    return found[:8]


def _get_chapter_ids_for_expert(expert: SubExpert, question: str) -> list[int]:
    ids: list[int] = list(expert.chapter_ids_hint)
    for law_title in expert.law_titles:
        law_id = get_law_id(law_title)
        if law_id is None:
            continue
        structure = get_law_structure(law_id)
        if not structure:
            continue
        kw_match_ids = []
        domain_keywords = expert.domain.replace("、", " ").replace("，", " ").split()
        for node in structure:
            node_title = (node.get("title") or node.get("content") or "").strip()
            if any(kw in node_title for kw in domain_keywords if len(kw) >= 2):
                kw_match_ids.append(node["id"])
        if not kw_match_ids and law_title == expert.law_titles[0]:
            try:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).parent.parent))
                from legal_chain_agent import navigate_chapters as _nav
                nav_ids = _nav(question, law_title)
                kw_match_ids.extend(nav_ids)
            except Exception:
                pass
        for nid in kw_match_ids:
            if nid not in ids:
                ids.append(nid)
    return ids


def sub_expert_retrieve(expert: SubExpert, question: str,
                        all_facts: dict[str, str],
                        verbose: bool = True) -> list[dict]:
    seen_ids: set[int] = set()
    results: list[dict] = []

    def add(article: dict, source: str, pinned: bool = False):
        if article["id"] not in seen_ids:
            seen_ids.add(article["id"])
            article["source"] = source
            article["pinned"] = pinned
            results.append(article)

    ctx_parts = [question]
    for field_name, _, _ in expert.required_info:
        val = all_facts.get(field_name)
        if val:
            ctx_parts.append(f"{field_name}: {val}")
    full_ctx = " ".join(ctx_parts)

    chapter_ids = _get_chapter_ids_for_expert(expert, full_ctx)
    if verbose and chapter_ids:
        print(f"        章节 id: {chapter_ids[:6]}{'...' if len(chapter_ids) > 6 else ''}")

    for law_title in expert.law_titles:
        law_id = get_law_id(law_title)
        count = 0
        for ch_id in chapter_ids:
            arts = get_articles_in_node(ch_id, law_id or 0)
            for art in arts:
                art["law"] = law_title
                art["category"] = "法律"
                add(art, f"章节:{law_title}", pinned=True)
                count += 1
                if count >= 30:
                    break
            if count >= 30:
                break

    from_question_kws = _extract_kws_simple(question)
    all_kws = list(dict.fromkeys(from_question_kws + expert.fts_keywords_extra))

    for law_title in expert.law_titles:
        for kw in all_kws:
            for art in fts_search_in_law(kw, law_title):
                add(art, f"FTS:{law_title}")

    law_cats    = ["法律", "宪法", "修正案", "法律解释", "监察法规"]
    interp_cats = ["司法解释"]
    for kw in all_kws:
        for art in fts_search_domains(kw, expert.fts_domains, law_cats, limit=8):
            add(art, "FTS-法律")
        for art in fts_search_domains(kw, expert.fts_domains, interp_cats, limit=5):
            add(art, "FTS-司法解释")

    if verbose:
        print(f"        检索到 {len(results)} 条（{expert.name}）")
    return results


# ── 相关性过滤 ────────────────────────────────────────────────────────

_FILTER_SYSTEM = """判断每条法律条文是否与用户问题相关。策略：宁可多保留。
每行输出 "编号: Y" 或 "编号: N"。不要其他内容。"""


def filter_articles_light(question: str, articles: list[dict],
                           batch_size: int = 10) -> list[dict]:
    if len(articles) <= 5:
        return articles
    kept: list[dict] = []
    for start in range(0, len(articles), batch_size):
        batch = articles[start:start + batch_size]
        numbered = "\n".join(
            f"[{i}] 《{a.get('law','')}》{a.get('article_number','')}："
            f"{a.get('content','')[:120]}"
            for i, a in enumerate(batch)
        )
        try:
            raw = chat(_FILTER_SYSTEM, f"问题：{question}\n\n{numbered}", temperature=0.01)
        except Exception:
            kept.extend(batch)
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
            if verdicts.get(i, True):
                kept.append(a)
    return kept if kept else articles


# ── 子专家分析 ────────────────────────────────────────────────────────

def sub_expert_analyze(expert: SubExpert, question: str,
                       all_facts: dict[str, str],
                       articles: list[dict]) -> str:
    if not articles:
        return f"（{expert.name}：未检索到相关条文，无法分析。）"
    law_arts   = [a for a in articles if a.get("category") != "司法解释"]
    interp_arts = [a for a in articles if a.get("category") == "司法解释"]
    parts = []
    if law_arts:
        parts.append("【法律原文】")
        for a in law_arts[:10]:
            parts.append(f"《{a.get('law','')}》{a.get('article_number','')}：{a.get('content','')[:400]}")
    if interp_arts:
        parts.append("\n【司法解释】")
        for a in interp_arts[:5]:
            parts.append(f"《{a.get('law','')}》{a.get('article_number','')}：{a.get('content','')[:400]}")
    context = "\n".join(parts)
    facts_text = ""
    if all_facts:
        facts_text = "\n\n【已知情况】\n" + "\n".join(f"- {k}：{v}" for k, v in all_facts.items())
    user_msg = f"法条：\n{context}{facts_text}\n\n用户问题：{question}"
    return chat(expert.answer_template, user_msg, temperature=0.2)


# ── 专家组综合 ────────────────────────────────────────────────────────

_GROUP_SYNTH_SYSTEM = """你是{group_name}负责人。将以下细分专家的分析整合成连贯的专业意见。

要求：
1. 去除重复内容，保留最重要的结论
2. 突出条文引用（保留"《XXX》第X条"格式）
3. 使用小标题区分不同方面
4. 总长度不超过400字

直接输出整合后的分析，不要说"根据以上分析"等套话。"""


def expert_group_synthesize(group: ExpertGroup, sub_answers: dict[str, str],
                             question: str) -> str:
    if not sub_answers:
        return ""
    if len(sub_answers) == 1:
        return next(iter(sub_answers.values()))
    combined = "\n\n".join(f"【{name}的分析】\n{ans}" for name, ans in sub_answers.items())
    system = _GROUP_SYNTH_SYSTEM.format(group_name=group.name)
    return chat(system, f"用户问题：{question}\n\n{combined}", temperature=0.15)


# ── 最终综合 ──────────────────────────────────────────────────────────

_FINAL_SYNTH_SYSTEM = """你是中国法律问题综合顾问。将多个专家组的分析整合为最终回答。

格式要求：
1. 开头直接给出核心结论（1-2句）
2. 按专家组分段陈述详细分析
3. 末尾列出"⚖️ 引用法条"（格式：• 《法律名》第X条 — 摘要）
4. 如涉及诉讼，注明应去哪个法院
5. 总长度500-800字，通俗易懂

不要说"根据以上"、"综上所述"等空话。直接给结论。"""


def coordinator_final_answer(question: str, group_answers: dict[str, str],
                              all_articles: list[dict]) -> str:
    if not group_answers:
        return "未能检索到相关法律条文，建议咨询专业律师。"
    combined = "\n\n".join(f"【{name}】\n{ans}" for name, ans in group_answers.items())
    seen = set()
    cite_lines = []
    for a in all_articles:
        key = f"{a.get('law','')}_{a.get('article_number','')}"
        if key not in seen and a.get("article_number"):
            seen.add(key)
            cite_lines.append(
                f"• 《{a.get('law','')}》{a.get('article_number','')} — "
                f"{a.get('content','')[:60]}..."
            )
    cites = "\n".join(cite_lines[:15]) if cite_lines else "（见各专家组分析中的引用）"
    user_msg = (
        f"用户问题：{question}\n\n"
        f"各专家组分析：\n{combined}\n\n"
        f"检索到的法条（供引用）：\n{cites}"
    )
    return chat(_FINAL_SYNTH_SYSTEM, user_msg, temperature=0.2)


# ── 主流程 ────────────────────────────────────────────────────────────

def run(question: str, interactive: bool = True,
        pre_answers: Optional[dict[str, str]] = None,
        verbose: bool = True) -> dict:
    from .core.config import PROVIDER_STATE, PROVIDERS

    def log(title: str, content: str = ""):
        if verbose:
            print(f"\n{'─' * 52}")
            print(f"▶ {title}")
            if content:
                for line in content.splitlines():
                    print(f"  {line}")

    print(f"\n{'═' * 60}")
    print(f"❓ {question}")
    print(f"   Provider: {PROVIDER_STATE['current']} / "
          f"{PROVIDERS[PROVIDER_STATE['current']]['model']}")

    log("Step 1  路由到专家组")
    group_names = identify_groups(question)
    log("路由结果", "、".join(group_names))
    groups = [ALL_GROUPS[n] for n in group_names if n in ALL_GROUPS]

    log("Step 2  确定子专家 + 提取已知信息")
    group_to_experts: dict[str, list[SubExpert]] = {}
    all_selected_experts: list[SubExpert] = []
    for group in groups:
        rough_facts = auto_extract_facts(question, group.sub_experts)
        selected = identify_sub_experts(group, question, rough_facts)
        group_to_experts[group.name] = selected
        all_selected_experts.extend(selected)
        if verbose:
            print(f"  {group.name}: {[e.name for e in selected]}")

    seen_names: set[str] = set()
    unique_experts: list[SubExpert] = []
    for e in all_selected_experts:
        if e.name not in seen_names:
            seen_names.add(e.name)
            unique_experts.append(e)

    log("Step 3  信息收集")
    known_facts = auto_extract_facts(question, unique_experts)
    if verbose and known_facts:
        print("  自动提取：" + "；".join(f"{k}={v}" for k, v in known_facts.items()))
    if pre_answers:
        known_facts.update(pre_answers)
    missing_fields = collect_missing_info(unique_experts, known_facts)
    if missing_fields and interactive:
        extra = ask_missing_info(missing_fields)
        known_facts.update(extra)
    elif missing_fields and not interactive and verbose:
        print(f"  跳过信息收集（非交互模式），缺少：{[f for f, _ in missing_fields]}")

    log("Step 4  子专家检索与分析")
    expert_articles: dict[str, list[dict]] = {}
    expert_answers: dict[str, str] = {}
    for expert in unique_experts:
        if verbose:
            print(f"\n  ── {expert.name} ──")
        articles = sub_expert_retrieve(expert, question, known_facts, verbose=verbose)
        articles = expand_references(articles, verbose=verbose)
        if len(articles) > 8:
            before = len(articles)
            articles = filter_articles_light(question, articles)
            if verbose:
                print(f"        过滤: {before} → {len(articles)} 条")
        expert_articles[expert.name] = articles
        answer = sub_expert_analyze(expert, question, known_facts, articles)
        expert_answers[expert.name] = answer
        if verbose:
            print(f"        答案预览: {answer[:120]}...")

    log("Step 5  专家组综合")
    group_answers: dict[str, str] = {}
    for group in groups:
        experts_in_group = group_to_experts.get(group.name, [])
        sub_ans = {e.name: expert_answers[e.name] for e in experts_in_group if e.name in expert_answers}
        if not sub_ans:
            continue
        group_ans = expert_group_synthesize(group, sub_ans, question)
        group_answers[group.name] = group_ans
        if verbose:
            print(f"\n  【{group.name}】\n  {group_ans[:150]}...")

    log("Step 6  协调员最终综合")
    all_articles_flat: list[dict] = []
    seen_ids: set[int] = set()
    for arts in expert_articles.values():
        for a in arts:
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"])
                all_articles_flat.append(a)
    final_answer = coordinator_final_answer(question, group_answers, all_articles_flat)

    print(f"\n{'═' * 60}")
    print(f"❓ {question}")
    print(f"\n{'─' * 60}")
    for group_name, ans in group_answers.items():
        expert_names = [e.name for e in group_to_experts.get(group_name, [])]
        header = f"【{group_name}分析】" + (f" — {' + '.join(expert_names)}" if expert_names else "")
        print(f"\n{header}")
        print(ans)
    print(f"\n{'─' * 60}")
    print("📖 综合结论")
    print(final_answer)
    print(f"{'═' * 60}\n")

    return {
        "question":        question,
        "known_facts":     known_facts,
        "group_names":     group_names,
        "group_answers":   group_answers,
        "expert_answers":  expert_answers,
        "expert_articles": expert_articles,
        "final_answer":    final_answer,
    }
