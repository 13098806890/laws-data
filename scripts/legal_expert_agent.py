#!/usr/bin/env python3
"""
legal_expert_agent.py — 多层专家协作法律问答系统

架构：
  Layer 0: Coordinator（问题协调员）— 路由、信息收集、最终综合
  Layer 1: Expert Groups（专家组）— 按法律部门，综合子专家答案
  Layer 2: Sub-experts（细分专家）— 具体领域，DB 检索 + 分析

用法：
  cd /Users/doxie/laws_data
  python3 scripts/legal_expert_agent.py
  python3 scripts/legal_expert_agent.py --question "网购假货怎么维权"
  python3 scripts/legal_expert_agent.py --question "..." --provider deepseek
"""

import json
import re
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

# ── 路径 ──────────────────────────────────────────────────────────────

DB_PATH = Path("/Users/doxie/laws_data/law_content.db")

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

_PROVIDER_STATE: dict = {"current": DEFAULT_PROVIDER}


# ── LLM 客户端 ────────────────────────────────────────────────────────

def _call_openai_compat(cfg: dict, messages: list, temperature: float) -> str:
    payload = {
        "model": cfg["model"],
        "stream": False,
        "temperature": temperature,
        "messages": messages,
    }
    headers = {"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {}

    if _HAS_REQUESTS:
        for attempt in range(3):
            try:
                r = _requests.post(cfg["url"], headers=headers, json=payload, timeout=90)
                if r.status_code in (429, 503) or (r.status_code == 403 and attempt < 2):
                    wait = 2 ** attempt
                    print(f"    [限流] HTTP {r.status_code}，{wait}s 后重试...")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except _requests.HTTPError as e:
                raise RuntimeError(f"HTTP {e.response.status_code}: {e.response.text[:300]}") from e
        raise RuntimeError("重试次数耗尽")

    body = json.dumps(payload).encode()
    full_headers = {
        "Content-Type": "application/json",
        "User-Agent": "legal-expert-agent/1.0",
        **headers,
    }
    req = urllib.request.Request(cfg["url"], data=body, headers=full_headers, method="POST")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body_err = e.read().decode()
            if e.code in (429, 503, 403) and attempt < 2:
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
         provider: str = "") -> str:
    p = provider or _PROVIDER_STATE["current"]
    cfg = PROVIDERS[p]
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    if p == "ollama":
        return _call_ollama(cfg, messages, temperature)
    return _call_openai_compat(cfg, messages, temperature)


def parse_json(raw: str, fallback):
    """从模型输出中提取 JSON，支持 ```json 代码块"""
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


# ── 数据库工具 ─────────────────────────────────────────────────────────

def _conn():
    return sqlite3.connect(DB_PATH)


def get_law_id(title: str) -> Optional[int]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM laws WHERE title = ? AND is_current = 1 LIMIT 1", [title]
        ).fetchone()
        return row[0] if row else None


def get_law_structure(law_id: int) -> list[dict]:
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


def get_articles_in_node(node_id: int, law_id: int = 0) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, article_number, article_num, content
               FROM nodes
               WHERE parent_id = ? AND type = 'article'
               ORDER BY global_order""",
            [node_id]
        ).fetchall()
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
                      categories: Optional[list[str]] = None,
                      limit: int = 10) -> list[dict]:
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
    cjk = [c for c in keyword if '一' <= c <= '鿿']
    if not cjk:
        return []
    domain_ph = ",".join("?" * len(domains))
    cat_ph    = ",".join("?" * len(categories))
    fts_table = "nodes_fts" if len(cjk) >= 3 else "nodes_fts_bigram"
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


def find_article_by_ref(law_title_fragment: str, article_number_str: str) -> Optional[dict]:
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


_REF_PATTERN = re.compile(
    r'《([^》]{4,30})》第([一二三四五六七八九十百千零\d]+)条'
)
_SELF_REF_PATTERN = re.compile(
    r'(?:本法|依照|适用|参照)第([一二三四五六七八九十百千零\d]+)条'
)


def expand_references(articles: list[dict], verbose: bool = False) -> list[dict]:
    seen_ids = {a["id"] for a in articles}
    new_articles: list[dict] = []
    for art in articles:
        content = art.get("content", "")
        for m in _REF_PATTERN.finditer(content):
            law_frag = m.group(1)
            art_num  = f"第{m.group(2)}条"
            ref = find_article_by_ref(law_frag, art_num)
            if ref and ref["id"] not in seen_ids:
                seen_ids.add(ref["id"])
                ref["source"] = f"引用链:{art.get('article_number','')}→{art_num}"
                ref["pinned"] = False
                new_articles.append(ref)
                if verbose:
                    print(f"      引用链: {art.get('article_number','')} → 《{law_frag}》{art_num}")
        law_title = art.get("law", "")
        for m in _SELF_REF_PATTERN.finditer(content):
            art_num = f"第{m.group(1)}条"
            ref = find_article_by_ref(law_title, art_num)
            if ref and ref["id"] not in seen_ids:
                seen_ids.add(ref["id"])
                ref["source"] = f"同法引用:{art.get('article_number','')}→{art_num}"
                ref["pinned"] = False
                new_articles.append(ref)
    if verbose and new_articles:
        print(f"      引用链扩展 +{len(new_articles)} 条")
    return articles + new_articles


# ── 数据结构 ──────────────────────────────────────────────────────────

@dataclass
class SubExpert:
    """细分专家定义"""
    name: str
    domain: str
    # required_info: list of (field_name, question_text, extraction_hint_regex_or_keyword)
    required_info: list[tuple[str, str, str]]
    law_titles: list[str]          # 主体法律（精确标题）
    chapter_ids_hint: list[int]    # 章节 id 提示（可为空，动态补充）
    fts_domains: list[str]         # FTS 检索的 legal_domain 列表
    fts_categories: list[str]      # FTS 检索的 category 列表
    fts_keywords_extra: list[str]  # 领域特定补充关键词（除问题中提取外）
    answer_template: str           # 给 LLM 的回答模板提示


@dataclass
class ExpertGroup:
    """专家组定义"""
    name: str
    description: str
    sub_experts: list[SubExpert]
    routing_keywords: list[str]    # 快速路由关键词（回退用）


# ── 细分专家定义 ──────────────────────────────────────────────────────

# 民法典主要章节 id（通过动态查询补充；hint 作为快速路径）
_MINFA_ID_HINT_CONTRACT_GENERAL  = [34971, 34978, 35012, 35020, 35047, 35056, 35071, 35092]
_MINFA_ID_HINT_SALE              = [35111]
_MINFA_ID_HINT_LEASE             = [35226]
_MINFA_ID_HINT_LOAN              = [35186]
_MINFA_ID_HINT_CONSTRUCTION      = [35315]
_CRIMINAL_CHAPTER_PROPERTY       = 22116
_CRIMINAL_CHAPTER_PERSON         = 22084
_CRIMINAL_CHAPTER_ECONOMY        = 22083
_CRIMINAL_CHAPTER_CORRUPTION     = 22247
_CRIMINAL_CHAPTER_DERELICTION    = 22263

# 合同法专家
_CONTRACT_EXPERT = SubExpert(
    name="合同法专家",
    domain="合同纠纷、违约责任、合同解除、合同效力",
    required_info=[
        ("合同类型",   "合同是哪种类型（买卖/租赁/服务/借款/建设工程/其他）？",
                       r"买卖|租赁|服务|借款|贷款|雇佣|劳务|承揽|运输|建设工程"),
        ("签订方式",   "合同是书面签订还是口头约定？",
                       r"书面|口头|微信|聊天记录|电话|网络"),
        ("违约方",     "是哪一方违约（甲方/乙方/买方/卖方/出租方/承租方）？",
                       r"对方|甲方|乙方|买方|卖方|商家|平台|房东|租客|承包方|发包方"),
        ("具体违约行为", "对方具体做了什么（拒绝交货/拒付款/逾期/质量问题/单方解约）？",
                       r"不交货|拒绝交付|不付款|拖欠|逾期|质量|不合格|单方|解除|违约"),
        ("合同金额",   "合同标的金额大概是多少？",
                       r"\d+\s*(?:万|元|块|百|千|亿)"),
    ],
    law_titles=["中华人民共和国民法典"],
    chapter_ids_hint=_MINFA_ID_HINT_CONTRACT_GENERAL + _MINFA_ID_HINT_SALE
                     + _MINFA_ID_HINT_LEASE + _MINFA_ID_HINT_LOAN,
    fts_domains=["民法典", "民法商法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["违约责任", "合同解除", "继续履行", "损害赔偿"],
    answer_template=(
        "你是合同法细分专家。基于以下法条，分析：\n"
        "1. 该合同的法律效力\n"
        "2. 违约方应承担哪些违约责任（继续履行/损害赔偿/定金罚则）\n"
        "3. 守约方可采取的维权路径\n"
        "引用具体条文编号，语言通俗。"
    ),
)

# 物权专家
_PROPERTY_EXPERT = SubExpert(
    name="物权专家",
    domain="不动产所有权、用益物权、担保物权、物权登记",
    required_info=[
        ("物权类型",   "涉及的是哪种物权（所有权/使用权/抵押权/质押权/留置权）？",
                       r"所有权|使用权|抵押|质押|留置|地役权|宅基地|建设用地|居住权"),
        ("标的物",     "争议的财产是什么（房产/土地/车辆/动产/其他）？",
                       r"房产|房屋|土地|宅基地|车辆|车|动产|股权|存款"),
        ("是否登记",   "该财产是否已办理权属登记/过户？",
                       r"登记|过户|产权证|不动产证|已登记|未登记|登记簿"),
        ("争议情形",   "具体争议是什么（侵占/无权处分/善意取得/共有争议）？",
                       r"侵占|无权处分|善意取得|共有|共同所有|分割|返还"),
    ],
    law_titles=["中华人民共和国民法典"],
    chapter_ids_hint=[],   # 动态获取物权编
    fts_domains=["民法典", "民法商法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["物权登记", "善意取得", "不动产", "抵押权实现"],
    answer_template=(
        "你是物权法细分专家。基于以下法条，分析：\n"
        "1. 当事人的物权归属及依据\n"
        "2. 物权是否受到侵害及侵害方式\n"
        "3. 物权人可以行使哪些请求权（返还/排除妨害/消除危险/损害赔偿）\n"
        "引用具体条文，指明登记要求。"
    ),
)

# 侵权责任专家
_TORT_EXPERT = SubExpert(
    name="侵权责任专家",
    domain="侵权损害赔偿、过错责任、无过错责任、共同侵权",
    required_info=[
        ("侵权类型",   "属于哪种侵权（人身伤害/财产损害/名誉权/隐私权/产品责任/交通事故/医疗事故）？",
                       r"人身伤害|受伤|死亡|财产损失|名誉|隐私|产品|交通事故|医疗|高空坠物|动物咬伤"),
        ("损害后果",   "造成了什么具体损害（伤亡/财产损失金额/精神损害）？",
                       r"受伤|死亡|残疾|财产损失|\d+元|精神损害|名誉受损"),
        ("侵权人身份", "侵权方是谁（个人/公司/雇主/产品生产者）？",
                       r"个人|公司|企业|雇主|单位|生产者|销售者|驾驶人|医院|学校"),
        ("责任归属",   "是否存在多方责任（共同侵权/混合过错/第三人侵权）？",
                       r"共同|多人|第三方|自身也有|混合过错|部分责任"),
        ("是否有证据", "是否有伤情证明、损失证据、侵权事实证据？",
                       r"证据|证明|照片|视频|鉴定|病历|发票|收据|报警|报案"),
    ],
    law_titles=["中华人民共和国民法典"],
    chapter_ids_hint=[],   # 动态获取侵权责任编
    fts_domains=["民法典", "民法商法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["侵权责任", "损害赔偿", "精神损害", "无过错责任"],
    answer_template=(
        "你是侵权责任法细分专家。基于以下法条，分析：\n"
        "1. 适用何种归责原则（过错责任/无过错责任/公平责任）\n"
        "2. 侵权构成要件是否满足\n"
        "3. 赔偿范围（医疗费/误工费/残疾赔偿金/死亡赔偿金/精神损害赔偿）\n"
        "4. 诉讼时效（一般三年）\n"
        "引用具体条文，给出赔偿项目清单。"
    ),
)

# 婚姻家庭专家
_MARRIAGE_EXPERT = SubExpert(
    name="婚姻家庭专家",
    domain="离婚、抚养权、财产分割、婚姻效力、家庭暴力",
    required_info=[
        ("婚姻状况",   "当前婚姻状态（已婚/离婚中/未婚同居/再婚）？",
                       r"已婚|离婚|结婚|同居|未婚|再婚|分居"),
        ("纠纷类型",   "主要纠纷是什么（离婚/子女抚养权/财产分割/家庭暴力/婚姻无效）？",
                       r"离婚|抚养|监护|财产分割|家庭暴力|出轨|婚前财产|共同财产|彩礼|婚姻无效"),
        ("子女情况",   "有无未成年子女？子女年龄？现由谁照顾？",
                       r"\d+岁|孩子|子女|小孩|儿子|女儿|未成年|抚养"),
        ("财产情况",   "主要财产有哪些（房产/存款/公司股权/婚前婚后财产）？",
                       r"房产|房屋|存款|股权|婚前|婚后|共同财产|个人财产|\d+万"),
        ("过错方",     "是否存在过错（家暴/出轨/遗弃/分居超过两年）？",
                       r"家暴|出轨|外遇|遗弃|分居|过错|重婚"),
    ],
    law_titles=["中华人民共和国民法典"],
    chapter_ids_hint=[],   # 动态获取婚姻家庭编
    fts_domains=["民法典", "民法商法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["离婚协议", "夫妻共同财产", "子女抚养费", "彩礼返还", "家庭暴力"],
    answer_template=(
        "你是婚姻家庭法细分专家。基于以下法条，分析：\n"
        "1. 离婚条件是否具备（协议离婚/诉讼离婚）\n"
        "2. 子女抚养权归属原则\n"
        "3. 夫妻共同财产分割原则（有过错方少分/婚前财产不分）\n"
        "4. 家庭暴力的法律后果\n"
        "语言通俗，明确给出建议路径。"
    ),
)

# 继承专家
_INHERITANCE_EXPERT = SubExpert(
    name="继承专家",
    domain="法定继承、遗嘱继承、遗产分配、继承放弃",
    required_info=[
        ("遗嘱情况",   "死者是否留有遗嘱？遗嘱形式（书面/公证/录像/口头）？",
                       r"遗嘱|公证|立遗嘱|无遗嘱|口头遗嘱|书面遗嘱"),
        ("继承人情况", "继承人有哪些（配偶/子女/父母/兄弟姐妹）？",
                       r"配偶|子女|父母|兄弟|姐妹|孙子|外孙|继承人"),
        ("遗产情况",   "主要遗产是什么（房产/存款/债务/公司股权）？",
                       r"房产|存款|债务|股权|遗产|财产"),
        ("纠纷类型",   "争议焦点是什么（遗嘱有效性/份额分配/代位继承/放弃继承）？",
                       r"遗嘱有效|份额|代位继承|放弃继承|争遗产|争产"),
    ],
    law_titles=["中华人民共和国民法典"],
    chapter_ids_hint=[],   # 动态获取继承编
    fts_domains=["民法典", "民法商法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["法定继承", "遗嘱继承", "继承顺序", "遗产债务", "遗嘱效力"],
    answer_template=(
        "你是继承法细分专家。基于以下法条，分析：\n"
        "1. 遗嘱是否有效（形式要件/内容要件）\n"
        "2. 法定继承的顺序和份额\n"
        "3. 必留份（特留份）制度的适用\n"
        "4. 继承债务的处理\n"
        "明确列出继承顺序和份额计算方式。"
    ),
)

# 人格权专家
_PERSONALITY_EXPERT = SubExpert(
    name="人格权专家",
    domain="名誉权、隐私权、肖像权、姓名权、网络侵权",
    required_info=[
        ("人格权类型", "侵害的是哪种人格权（名誉/隐私/肖像/姓名/荣誉）？",
                       r"名誉|隐私|肖像|姓名|荣誉|诽谤|侮辱|泄露|商业秘密"),
        ("侵权行为",   "侵权方具体做了什么（网络发布/散布谣言/未授权使用照片）？",
                       r"发布|散布|传播|谣言|未经授权|使用照片|录视频|泄露隐私|侮辱|诽谤"),
        ("侵权平台",   "侵权发生在哪个平台（微博/微信/抖音/其他）？",
                       r"微博|微信|抖音|快手|小红书|B站|论坛|公众号|网络"),
        ("损害后果",   "造成了什么后果（名誉受损/精神痛苦/经济损失）？",
                       r"名誉受损|精神|抑郁|失业|经济损失|\d+元|社会评价"),
    ],
    law_titles=["中华人民共和国民法典"],
    chapter_ids_hint=[],   # 动态获取人格权编
    fts_domains=["民法典", "民法商法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["名誉权", "隐私权", "肖像权", "网络侵权", "删除侵权内容"],
    answer_template=(
        "你是人格权法细分专家。基于以下法条，分析：\n"
        "1. 哪种人格权受到侵害及法律依据\n"
        "2. 受害方可以主张的救济（删除/更正/赔礼道歉/损害赔偿）\n"
        "3. 平台责任（通知-删除规则）\n"
        "4. 如何证明损害及举证责任\n"
        "明确说明维权步骤。"
    ),
)

# 财产犯罪专家
_CRIME_PROPERTY_EXPERT = SubExpert(
    name="财产犯罪专家",
    domain="盗窃、诈骗、抢劫、敲诈勒索、侵占",
    required_info=[
        ("犯罪行为",   "具体行为是什么（盗窃/诈骗/抢劫/敲诈/侵占）？",
                       r"盗窃|诈骗|抢劫|抢夺|敲诈勒索|侵占|挪用|骗取"),
        ("涉案金额",   "涉及金额是多少？",
                       r"\d+\s*(?:万|元|块|百|千|亿)"),
        ("主观状态",   "行为人是否有犯罪故意（主观故意还是过失）？",
                       r"故意|明知|蓄意|有意|过失|不知道|不清楚"),
        ("是否既遂",   "犯罪行为是否完成（既遂/未遂/中止）？",
                       r"既遂|未遂|中止|未成功|被抓|被发现"),
    ],
    law_titles=["中华人民共和国刑法"],
    chapter_ids_hint=[_CRIMINAL_CHAPTER_PROPERTY],
    fts_domains=["刑法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["盗窃罪", "诈骗罪", "抢劫罪", "数额较大", "数额巨大"],
    answer_template=(
        "你是财产犯罪刑法细分专家。基于以下法条，分析：\n"
        "1. 行为构成何种犯罪（罪名及构成要件分析）\n"
        "2. 法定刑幅度（量刑区间）\n"
        "3. 数额认定标准（较大/巨大/特别巨大）\n"
        "4. 从重/从轻/减轻情节\n"
        "明确引用刑法条文和相关司法解释。"
    ),
)

# 人身伤害犯罪专家
_CRIME_PERSON_EXPERT = SubExpert(
    name="人身伤害专家",
    domain="故意伤害、故意杀人、强奸、绑架、非法拘禁",
    required_info=[
        ("犯罪行为",   "具体行为是什么（故意伤害/故意杀人/强奸/绑架/非法拘禁）？",
                       r"故意伤害|故意杀人|强奸|绑架|拘禁|殴打|人身自由|强制"),
        ("伤害程度",   "受害人伤情如何（轻伤/重伤/死亡/轻微伤）？",
                       r"轻伤|重伤|死亡|轻微伤|残疾|鉴定|司法鉴定"),
        ("行为人年龄", "行为人是否成年？",
                       r"\d+岁|未成年|成年|刑事责任年龄"),
        ("是否自首",   "行为人是否有自首或立功表现？",
                       r"自首|投案|立功|坦白|如实供述"),
    ],
    law_titles=["中华人民共和国刑法"],
    chapter_ids_hint=[_CRIMINAL_CHAPTER_PERSON],
    fts_domains=["刑法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["故意伤害罪", "故意杀人罪", "刑事附带民事", "伤残等级"],
    answer_template=(
        "你是人身伤害刑法细分专家。基于以下法条，分析：\n"
        "1. 罪名认定（故意伤害/故意杀人/其他侵犯人身罪）\n"
        "2. 法定刑（轻伤/重伤/死亡对应量刑）\n"
        "3. 刑事附带民事赔偿范围\n"
        "4. 自首/立功的量刑影响\n"
        "引用刑法条文，说明刑事追诉标准。"
    ),
)

# 经济犯罪专家
_CRIME_ECONOMY_EXPERT = SubExpert(
    name="经济犯罪专家",
    domain="合同诈骗、生产销售伪劣商品、走私、破坏市场秩序",
    required_info=[
        ("犯罪类型",   "属于哪类经济犯罪（合同诈骗/销售假冒伪劣/走私/非法经营/洗钱）？",
                       r"合同诈骗|假冒伪劣|走私|非法经营|洗钱|虚假广告|串通投标"),
        ("涉案金额",   "涉案金额是多少？",
                       r"\d+\s*(?:万|元|块|百|千|亿)"),
        ("主体身份",   "行为主体是个人还是单位（公司）？",
                       r"个人|单位犯罪|公司|企业|法定代表人|直接责任人"),
    ],
    law_titles=["中华人民共和国刑法"],
    chapter_ids_hint=[_CRIMINAL_CHAPTER_ECONOMY],
    fts_domains=["刑法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["合同诈骗", "生产销售伪劣", "非法经营", "单位犯罪"],
    answer_template=(
        "你是经济犯罪刑法细分专家。基于以下法条，分析：\n"
        "1. 经济犯罪的罪名及构成要件\n"
        "2. 单位犯罪与自然人犯罪的区别处理\n"
        "3. 量刑标准（数额/情节）\n"
        "4. 退赔对量刑的影响\n"
        "引用刑法条文和相关司法解释。"
    ),
)

# 腐败职务犯罪专家
_CRIME_CORRUPTION_EXPERT = SubExpert(
    name="腐败职务犯罪专家",
    domain="贪污贿赂、渎职、滥用职权、玩忽职守",
    required_info=[
        ("犯罪类型",   "是哪类职务犯罪（贪污/受贿/行贿/挪用公款/滥用职权/玩忽职守）？",
                       r"贪污|受贿|行贿|挪用公款|滥用职权|玩忽职守|失职"),
        ("主体身份",   "行为人是什么身份（国家工作人员/公司人员/国有企业人员）？",
                       r"国家工作人员|公务员|国有企业|事业单位|村委会|公司|官员"),
        ("涉案金额",   "涉案金额（贪污/受贿/挪用金额）？",
                       r"\d+\s*(?:万|元|块|百|千|亿)"),
    ],
    law_titles=["中华人民共和国刑法"],
    chapter_ids_hint=[_CRIMINAL_CHAPTER_CORRUPTION, _CRIMINAL_CHAPTER_DERELICTION],
    fts_domains=["刑法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["贪污罪", "受贿罪", "挪用公款", "渎职罪", "量刑标准"],
    answer_template=(
        "你是腐败职务犯罪刑法细分专家。基于以下法条，分析：\n"
        "1. 罪名认定（贪污/受贿/渎职等）及主体要件\n"
        "2. 量刑档次（3万/20万/300万等数额标准）\n"
        "3. 主动退赃和认罪认罚的量刑影响\n"
        "4. 监察调查与刑事诉讼的衔接\n"
        "明确引用刑法条文及最高院司法解释。"
    ),
)

# 劳动合同专家
_LABOR_CONTRACT_EXPERT = SubExpert(
    name="劳动合同专家",
    domain="劳动合同签订、解除、终止、经济补偿",
    required_info=[
        ("劳动关系类型", "劳动关系类型（正式劳动合同/试用期/劳务派遣/外包/兼职）？",
                         r"正式员工|试用期|劳务派遣|外包|兼职|合同工|临时工|实习"),
        ("工作年限",     "在该单位工作了多久（年/月）？",
                         r"\d+\s*(?:年|个月|月)"),
        ("解除方式",     "劳动关系如何解除的（被辞退/协商解除/自行辞职/合同到期不续签）？",
                         r"辞退|开除|解雇|协商离职|自行辞职|主动离职|合同到期|不续签"),
        ("是否签合同",   "是否签订了书面劳动合同？",
                         r"有合同|没有合同|未签合同|口头约定|已签"),
        ("违法情形",     "是否存在违法解除情形（孕期/医疗期/非过失性辞退未提前通知）？",
                         r"怀孕|孕期|产假|医疗期|工伤|三期|提前通知|未通知"),
    ],
    law_titles=["中华人民共和国劳动合同法", "中华人民共和国劳动法"],
    chapter_ids_hint=[],
    fts_domains=["社会法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["经济补偿金", "赔偿金", "违法解除", "未签合同双倍工资", "竞业限制"],
    answer_template=(
        "你是劳动合同法细分专家。基于以下法条，分析：\n"
        "1. 解除劳动合同是否合法\n"
        "2. 经济补偿金（N）或赔偿金（2N）的计算方式\n"
        "3. 未签书面劳动合同的双倍工资主张\n"
        "4. 维权路径（劳动仲裁→法院）及时效（1年仲裁时效）\n"
        "明确给出补偿金额的计算公式。"
    ),
)

# 工资福利专家
_WAGE_EXPERT = SubExpert(
    name="工资福利专家",
    domain="工资拖欠、加班费、最低工资、社会保险",
    required_info=[
        ("拖欠类型",   "拖欠的是基本工资、加班费还是提成奖金？",
                       r"基本工资|加班费|提成|奖金|绩效|社保|五险一金|拖欠"),
        ("拖欠金额",   "拖欠金额是多少？拖欠了多久？",
                       r"\d+\s*(?:万|元|块|百|千)|\d+\s*个月"),
        ("加班情况",   "是否存在加班（平时加班/周末加班/节假日加班）？",
                       r"加班|延时|值班|节假日|周末|年假|调休"),
    ],
    law_titles=["中华人民共和国劳动法", "中华人民共和国劳动合同法"],
    chapter_ids_hint=[],
    fts_domains=["社会法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["工资报酬", "加班工资", "最低工资标准", "社会保险费", "拖欠工资"],
    answer_template=(
        "你是劳动工资福利细分专家。基于以下法条，分析：\n"
        "1. 工资拖欠的法律认定及追偿权利\n"
        "2. 加班费计算标准（150%/200%/300%）\n"
        "3. 社会保险缴纳义务及违法后果\n"
        "4. 劳动仲裁追偿的时效和流程\n"
        "给出具体的计算示例（如可能）。"
    ),
)

# 工伤职业病专家
_WORKINJURY_EXPERT = SubExpert(
    name="工伤职业病专家",
    domain="工伤认定、工伤赔偿、职业病、工亡",
    required_info=[
        ("事故情形",   "受伤是在什么情况下发生的（工作时间/上下班途中/职业病/因公出差）？",
                       r"工作时间|上班途中|下班途中|出差|职业病|工作原因|因公"),
        ("伤情程度",   "伤情或伤残程度（住院/伤残等级/死亡）？",
                       r"住院|伤残|等级|一级|十级|死亡|职业病|工亡"),
        ("单位态度",   "用人单位是否配合认定工伤（拒绝申报/不承认/已申报）？",
                       r"拒绝|不承认|未申报|已申报|已认定|赔偿协议"),
        ("参保情况",   "单位是否为其缴纳工伤保险？",
                       r"工伤保险|参保|未参保|未缴|社保"),
    ],
    law_titles=["中华人民共和国劳动法"],
    chapter_ids_hint=[],
    fts_domains=["社会法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["工伤认定", "工伤保险", "劳动能力鉴定", "一次性伤残补助金", "工亡补助金"],
    answer_template=(
        "你是工伤职业病细分专家。基于以下法条，分析：\n"
        "1. 是否符合工伤认定条件（工作时间/工作场所/工作原因三要素）\n"
        "2. 工伤申报流程和时限（30日/1年）\n"
        "3. 工伤保险待遇（医疗费/伤残补助金/护理费/停工留薪）\n"
        "4. 单位未参保时的赔偿责任\n"
        "明确列出各项赔偿项目。"
    ),
)

# 劳动争议专家
_LABOR_DISPUTE_EXPERT = SubExpert(
    name="劳动争议专家",
    domain="劳动仲裁、诉讼时效、证据、仲裁前置",
    required_info=[
        ("争议事项",   "劳动争议的核心事项是什么（工资/解除/工伤/社保/竞业限制）？",
                       r"工资|解除|工伤|社保|竞业限制|服务期|培训费"),
        ("时间节点",   "劳动关系结束多久了？是否超过1年仲裁时效？",
                       r"\d+\s*(?:年|个月)|最近|刚刚|前不久|超过一年|时效"),
        ("证据情况",   "有哪些证据（劳动合同/工资条/聊天记录/考勤记录）？",
                       r"合同|工资条|聊天记录|微信|考勤|打卡|社保缴纳记录|工作证"),
    ],
    law_titles=["中华人民共和国劳动争议调解仲裁法"],
    chapter_ids_hint=[],
    fts_domains=["社会法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["劳动仲裁", "仲裁时效", "举证责任", "仲裁前置", "一裁终局"],
    answer_template=(
        "你是劳动争议程序细分专家。基于以下法条，分析：\n"
        "1. 劳动仲裁时效（1年）及起算点\n"
        "2. 仲裁前置原则与例外（一裁终局情形）\n"
        "3. 举证责任分配（用人单位举证倒置规则）\n"
        "4. 仲裁→一审→二审的完整路径和时限\n"
        "给出明确的维权时间表。"
    ),
)

# 消费者权益专家
_CONSUMER_EXPERT = SubExpert(
    name="消费者权益专家",
    domain="假冒伪劣、退款、三倍赔偿、平台责任、欺诈",
    required_info=[
        ("购买渠道",   "在哪里购买的（线上平台/实体店/直播带货/微商）？",
                       r"淘宝|京东|拼多多|抖音|快手|微商|实体店|超市|直播|网购|线上"),
        ("问题类型",   "商品/服务问题是什么（假货/不合格/虚假宣传/拒绝退款/过期食品）？",
                       r"假货|假冒|伪劣|不合格|虚假宣传|夸大|拒绝退款|过期|变质|食品安全"),
        ("金额损失",   "购买金额是多少？实际损失？",
                       r"\d+\s*(?:万|元|块|百|千)"),
        ("是否有凭证", "是否有购物凭证（订单/发票/截图/聊天记录）？",
                       r"有订单|有发票|有截图|有凭证|证明|收据|快递单"),
        ("商家态度",   "商家是否承认问题并愿意处理？",
                       r"拒绝退款|不承认|愿意退|协商|已退款|已解决"),
    ],
    law_titles=["中华人民共和国消费者权益保护法", "中华人民共和国食品安全法",
                "中华人民共和国产品质量法", "中华人民共和国电子商务法"],
    chapter_ids_hint=[],
    fts_domains=["经济法", "民法商法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["三倍赔偿", "退一赔三", "退一赔十", "平台责任", "欺诈消费者"],
    answer_template=(
        "你是消费者权益保护细分专家。基于以下法条，分析：\n"
        "1. 消费者可以主张的具体权利（退货/退款/赔偿）\n"
        "2. 惩罚性赔偿倍数（三倍/十倍）及适用条件\n"
        "3. 平台连带责任的适用场景\n"
        "4. 投诉路径（12315/市场监管局/法院）\n"
        "明确给出赔偿金额计算和维权步骤。"
    ),
)

# 产品质量专家
_PRODUCT_EXPERT = SubExpert(
    name="产品质量专家",
    domain="产品缺陷、侵权赔偿、召回、生产者销售者责任",
    required_info=[
        ("产品类型",   "是什么产品（食品/药品/家用电器/车辆/儿童用品/工业品）？",
                       r"食品|药品|家电|车辆|汽车|儿童|玩具|工业品|医疗器械"),
        ("缺陷类型",   "产品缺陷是什么（设计缺陷/制造缺陷/警示说明缺陷）？",
                       r"设计缺陷|制造缺陷|警示|说明书|标识|质量不合格|召回"),
        ("损害后果",   "产品缺陷造成了什么损害（人身伤害/财产损失）？",
                       r"受伤|烫伤|中毒|财产损失|损坏|死亡|伤残"),
        ("责任主体",   "生产者和销售者是否明确？",
                       r"生产商|制造商|销售商|进口商|代理商|品牌方"),
    ],
    law_titles=["中华人民共和国产品质量法", "中华人民共和国消费者权益保护法"],
    chapter_ids_hint=[],
    fts_domains=["经济法"],
    fts_categories=["法律"],
    fts_keywords_extra=["产品缺陷", "产品责任", "生产者责任", "缺陷产品召回"],
    answer_template=(
        "你是产品质量法细分专家。基于以下法条，分析：\n"
        "1. 产品缺陷的认定标准\n"
        "2. 生产者与销售者的责任划分\n"
        "3. 受害方可以主张的赔偿项目\n"
        "4. 举证责任（产品缺陷的证明方式）\n"
        "明确说明追责路径。"
    ),
)

# 电子商务专家
_ECOMMERCE_EXPERT = SubExpert(
    name="电子商务专家",
    domain="网络交易、平台责任、刷单、大数据杀熟、用户协议",
    required_info=[
        ("纠纷类型",   "电子商务纠纷类型（假货/刷单/大数据杀熟/未按约配送/平台封号）？",
                       r"假货|刷单|大数据杀熟|差别定价|封号|扣押保证金|虚假评价"),
        ("平台名称",   "涉及哪个电商平台？",
                       r"淘宝|京东|拼多多|抖音|快手|小红书|亚马逊|微信小程序"),
        ("损失金额",   "具体损失金额？",
                       r"\d+\s*(?:万|元|块|百|千)"),
    ],
    law_titles=["中华人民共和国电子商务法", "中华人民共和国消费者权益保护法"],
    chapter_ids_hint=[],
    fts_domains=["经济法"],
    fts_categories=["法律"],
    fts_keywords_extra=["电子商务平台", "平台责任", "搭售", "大数据杀熟", "用户评价"],
    answer_template=(
        "你是电子商务法细分专家。基于以下法条，分析：\n"
        "1. 电商平台的法律责任（知道或应当知道侵权行为的连带责任）\n"
        "2. 大数据杀熟的法律认定\n"
        "3. 消费者维权路径（申请退款/投诉平台/仲裁/诉讼）\n"
        "4. 平台封号/扣押保证金的合法性审查\n"
        "给出具体的操作建议。"
    ),
)

# 公司商事专家
_COMPANY_EXPERT = SubExpert(
    name="公司商事专家",
    domain="公司设立、股东权利、公司决议、对外担保、破产",
    required_info=[
        ("公司类型",   "是有限责任公司还是股份公司？",
                       r"有限责任公司|股份公司|合伙企业|个人独资"),
        ("纠纷类型",   "纠纷类型（股东纠纷/公司决议效力/对外担保/破产清算）？",
                       r"股东纠纷|股权|分红|决议|担保|破产|清算|注册|设立"),
        ("持股比例",   "持股比例是多少（影响表决权）？",
                       r"\d+\s*%|持股|股份|股权比例"),
    ],
    law_titles=["中华人民共和国公司法"],
    chapter_ids_hint=[],
    fts_domains=["经济法", "民法商法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["股东权利", "公司决议", "股权转让", "公司担保", "破产清算"],
    answer_template=(
        "你是公司商事法细分专家。基于以下法条，分析：\n"
        "1. 股东权利的法律依据\n"
        "2. 公司决议的效力及瑕疵认定\n"
        "3. 公司对外担保的法律规范\n"
        "4. 股东/高管的赔偿责任\n"
        "引用公司法条文，给出操作建议。"
    ),
)

# 民事诉讼专家
_CIVIL_PROCEDURE_EXPERT = SubExpert(
    name="民事诉讼专家",
    domain="管辖、起诉、证据、审判、执行、保全",
    required_info=[
        ("纠纷类型",   "属于哪类民事纠纷（合同/侵权/婚姻/劳动/房屋）？",
                       r"合同|侵权|婚姻|劳动|房屋|租赁|借款|离婚|继承"),
        ("当事人住所", "原告和被告的住所地在哪个城市/地区？",
                       r"北京|上海|广州|深圳|浙江|江苏|\w+省|\w+市|\w+区"),
        ("标的金额",   "争议金额（影响基层/中级/高级法院管辖）？",
                       r"\d+\s*(?:万|元|块|百|千|亿)"),
        ("是否有保全需求", "是否需要财产保全（防止被告转移财产）？",
                           r"保全|查封|冻结|扣押|转移财产|跑路"),
    ],
    law_titles=["中华人民共和国民事诉讼法"],
    chapter_ids_hint=[],
    fts_domains=["诉讼与非诉讼程序法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["管辖权", "起诉条件", "证据规则", "财产保全", "强制执行"],
    answer_template=(
        "你是民事诉讼程序细分专家。基于以下法条，分析：\n"
        "1. 管辖法院的确定（级别管辖/地域管辖）\n"
        "2. 起诉条件（诉讼主体/诉讼请求/管辖）\n"
        "3. 证据收集和保全建议\n"
        "4. 财产保全的申请条件和流程\n"
        "5. 执行程序概述\n"
        "给出具体的起诉准备清单。"
    ),
)

# 刑事诉讼专家
_CRIMINAL_PROCEDURE_EXPERT = SubExpert(
    name="刑事诉讼专家",
    domain="报案、立案、逮捕、起诉、辩护、上诉",
    required_info=[
        ("案件阶段",   "目前案件处于哪个阶段（报案/立案/侦查/批捕/起诉/审判/执行）？",
                       r"报案|立案|侦查|逮捕|起诉|审判|判决|上诉|执行|羁押"),
        ("当事人身份", "咨询人身份（受害方/犯罪嫌疑人/家属/辩护律师）？",
                       r"受害者|被害人|嫌疑人|被告|家属|辩护|律师|委托"),
        ("涉嫌罪名",   "涉嫌什么罪名？",
                       r"故意伤害|诈骗|盗窃|贪污|受贿|故意杀人|强奸|走私"),
        ("是否羁押",   "犯罪嫌疑人是否已被羁押？",
                       r"羁押|拘留|逮捕|取保候审|监视居住|已关押|已释放"),
    ],
    law_titles=["中华人民共和国刑事诉讼法"],
    chapter_ids_hint=[],
    fts_domains=["诉讼与非诉讼程序法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["取保候审", "不起诉", "辩护权", "非法证据排除", "上诉"],
    answer_template=(
        "你是刑事诉讼程序细分专家。基于以下法条，分析：\n"
        "1. 当前阶段的程序权利（如申请取保候审/委托辩护人）\n"
        "2. 侦查/逮捕/审查起诉的法定时限\n"
        "3. 非法证据排除的申请条件\n"
        "4. 认罪认罚从宽制度的适用\n"
        "给出具体的程序建议和下一步行动。"
    ),
)

# 行政诉讼专家
_ADMIN_PROCEDURE_EXPERT = SubExpert(
    name="行政诉讼专家",
    domain="行政诉讼、行政复议、具体行政行为、行政赔偿",
    required_info=[
        ("行政行为类型", "政府的具体行政行为是什么（行政处罚/行政许可/行政强制/行政征收）？",
                         r"行政处罚|吊销执照|罚款|行政许可|审批|行政强制|征收|拆迁"),
        ("行政机关",     "哪个行政机关做出的行政行为？",
                         r"工商局|税务局|公安局|规划局|环保局|市监局|政府|街道|村委会"),
        ("是否复议",     "是否已经申请了行政复议？结果如何？",
                         r"行政复议|已复议|复议决定|维持|撤销|复议前置"),
        ("时效情况",     "行政行为发生多久了？是否在6个月起诉期限内？",
                         r"\d+\s*(?:年|个月)|最近|刚刚|超过|时效|期限"),
    ],
    law_titles=["中华人民共和国行政诉讼法"],
    chapter_ids_hint=[],
    fts_domains=["诉讼与非诉讼程序法", "行政法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["行政诉讼受案范围", "行政复议前置", "举证责任倒置", "行政赔偿"],
    answer_template=(
        "你是行政诉讼程序细分专家。基于以下法条，分析：\n"
        "1. 该行政行为是否属于行政诉讼受案范围\n"
        "2. 是否需要先行政复议（复议前置的情形）\n"
        "3. 起诉期限（6个月一般期限/特殊情形）\n"
        "4. 行政诉讼中的举证责任（行政机关举证）\n"
        "5. 行政赔偿的申请条件\n"
        "给出明确的路径建议。"
    ),
)


# ── 专家组定义 ────────────────────────────────────────────────────────

ALL_GROUPS: dict[str, "ExpertGroup"] = {
    "民法专家组": ExpertGroup(
        name="民法专家组",
        description="处理民事法律问题：合同、物权、侵权、婚姻家庭、继承、人格权",
        sub_experts=[
            _CONTRACT_EXPERT,
            _PROPERTY_EXPERT,
            _TORT_EXPERT,
            _MARRIAGE_EXPERT,
            _INHERITANCE_EXPERT,
            _PERSONALITY_EXPERT,
        ],
        routing_keywords=[
            "合同", "违约", "租赁", "买卖", "借款", "物权", "所有权", "抵押",
            "侵权", "赔偿", "伤害", "离婚", "抚养", "继承", "遗产", "遗嘱",
            "名誉", "隐私", "肖像", "人格权", "民法典",
        ],
    ),
    "刑法专家组": ExpertGroup(
        name="刑法专家组",
        description="处理刑事犯罪问题：财产犯罪、人身伤害、经济犯罪、职务犯罪",
        sub_experts=[
            _CRIME_PROPERTY_EXPERT,
            _CRIME_PERSON_EXPERT,
            _CRIME_ECONOMY_EXPERT,
            _CRIME_CORRUPTION_EXPERT,
        ],
        routing_keywords=[
            "犯罪", "刑事", "坐牢", "判刑", "立案", "报案", "刑法",
            "盗窃", "诈骗", "抢劫", "故意伤害", "故意杀人", "强奸",
            "贪污", "受贿", "渎职", "走私", "合同诈骗",
        ],
    ),
    "劳动法专家组": ExpertGroup(
        name="劳动法专家组",
        description="处理劳动关系问题：劳动合同、工资、工伤、劳动争议",
        sub_experts=[
            _LABOR_CONTRACT_EXPERT,
            _WAGE_EXPERT,
            _WORKINJURY_EXPERT,
            _LABOR_DISPUTE_EXPERT,
        ],
        routing_keywords=[
            "劳动", "工资", "加班费", "辞退", "解雇", "工伤", "职业病",
            "劳动合同", "经济补偿", "仲裁", "劳动争议", "试用期",
            "社保", "五险一金", "拖欠工资",
        ],
    ),
    "行政法专家组": ExpertGroup(
        name="行政法专家组",
        description="处理行政机关与公民的法律关系：行政处罚、许可、复议",
        sub_experts=[
            _ADMIN_PROCEDURE_EXPERT,
        ],
        routing_keywords=[
            "行政", "政府", "处罚", "吊销", "罚款", "许可证", "审批",
            "拆迁", "征收", "行政复议", "行政诉讼", "公安", "工商",
        ],
    ),
    "经济法专家组": ExpertGroup(
        name="经济法专家组",
        description="处理市场监管、消费者权益、公司商事法律问题",
        sub_experts=[
            _CONSUMER_EXPERT,
            _PRODUCT_EXPERT,
            _ECOMMERCE_EXPERT,
            _COMPANY_EXPERT,
        ],
        routing_keywords=[
            "消费者", "购物", "假货", "退款", "维权", "质量", "产品缺陷",
            "网购", "电商", "平台", "公司", "股东", "破产",
            "食品安全", "三倍赔偿", "十倍赔偿",
        ],
    ),
    "诉讼专家组": ExpertGroup(
        name="诉讼专家组",
        description="处理诉讼程序、管辖、证据、仲裁等程序性问题",
        sub_experts=[
            _CIVIL_PROCEDURE_EXPERT,
            _CRIMINAL_PROCEDURE_EXPERT,
            _ADMIN_PROCEDURE_EXPERT,
        ],
        routing_keywords=[
            "诉讼", "起诉", "法院", "仲裁", "管辖", "证据", "上诉",
            "执行", "保全", "查封", "冻结", "程序", "时效",
            "民诉", "刑诉", "去哪告",
        ],
    ),
}


# ── Layer 0: Coordinator 路由 ─────────────────────────────────────────

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
    if not valid:
        valid = _keyword_route(question)
    return valid


def _keyword_route(question: str) -> list[str]:
    """关键词快速路由（LLM 失败时的回退）"""
    matched = []
    for name, group in ALL_GROUPS.items():
        for kw in group.routing_keywords:
            if kw in question:
                if name not in matched:
                    matched.append(name)
                break
    return matched or list(ALL_GROUPS.keys())[:2]


# ── Layer 1: Expert Group 路由到子专家 ───────────────────────────────

_SUB_EXPERT_SYSTEM = """你是{group_name}。根据用户问题，从以下细分专家中选出需要参与分析的专家。

细分专家：
{experts}

规则：
- 只选与问题直接相关的专家（1-3个为宜）
- 如果是笼统问题，选最可能相关的1-2个

只输出 JSON 数组，包含专家名称。不要其他内容。"""


def identify_sub_experts(group: ExpertGroup, question: str,
                         known_facts: dict[str, str]) -> list[SubExpert]:
    expert_desc = "\n".join(
        f"- {e.name}：{e.domain}" for e in group.sub_experts
    )
    system = _SUB_EXPERT_SYSTEM.format(
        group_name=group.name,
        experts=expert_desc,
    )
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

def auto_extract_facts(question: str,
                       sub_experts: list[SubExpert]) -> dict[str, str]:
    """从问题文本中自动提取已知信息，避免重复询问"""
    facts: dict[str, str] = {}
    for expert in sub_experts:
        for field_name, _, hint_pattern in expert.required_info:
            if field_name in facts:
                continue
            if not hint_pattern:
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
    """汇总所有子专家所需但未提供的信息，去重"""
    seen_fields: set[str] = set(known_facts.keys())
    missing: list[tuple[str, str]] = []  # (field_name, question_text)
    for expert in sub_experts:
        for field_name, question_text, _ in expert.required_info:
            if field_name not in seen_fields:
                seen_fields.add(field_name)
                missing.append((field_name, question_text))
    return missing


# ── Layer 2: 子专家 DB 检索 ───────────────────────────────────────────

def _get_chapter_ids_for_expert(expert: SubExpert,
                                 question: str) -> list[int]:
    """获取子专家对应章节 id（hint + 动态导航）"""
    ids: list[int] = list(expert.chapter_ids_hint)  # copy

    for law_title in expert.law_titles:
        law_id = get_law_id(law_title)
        if law_id is None:
            continue
        structure = get_law_structure(law_id)
        if not structure:
            continue

        # 简单关键词匹配章节标题（快速且不消耗 LLM）
        kw_match_ids = []
        domain_keywords = expert.domain.replace("、", " ").replace("，", " ").split()
        for node in structure:
            node_title = (node.get("title") or node.get("content") or "").strip()
            if any(kw in node_title for kw in domain_keywords if len(kw) >= 2):
                kw_match_ids.append(node["id"])

        # 若关键词匹配为空，尝试 LLM 导航（限最重要的法律）
        if not kw_match_ids and law_title == expert.law_titles[0]:
            try:
                from legal_chain_agent import navigate_chapters as _nav
                nav_ids = _nav(question, law_title)
                kw_match_ids.extend(nav_ids)
            except Exception:
                pass

        for nid in kw_match_ids:
            if nid not in ids:
                ids.append(nid)

    return ids


def sub_expert_retrieve(expert: SubExpert,
                        question: str,
                        all_facts: dict[str, str],
                        verbose: bool = True) -> list[dict]:
    """子专家 DB 检索：章节条文 + FTS"""
    seen_ids: set[int] = set()
    results: list[dict] = []

    def add(article: dict, source: str, pinned: bool = False):
        if article["id"] not in seen_ids:
            seen_ids.add(article["id"])
            article["source"] = source
            article["pinned"] = pinned
            results.append(article)

    # 构建检索上下文
    ctx_parts = [question]
    for field_name, _, _ in expert.required_info:
        val = all_facts.get(field_name)
        if val:
            ctx_parts.append(f"{field_name}: {val}")
    full_ctx = " ".join(ctx_parts)

    # ── 1. 章节内条文 ──
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

    # ── 2. 主体法律 FTS ──
    from_question_kws = _extract_kws_simple(question)
    all_kws = list(dict.fromkeys(from_question_kws + expert.fts_keywords_extra))

    for law_title in expert.law_titles:
        for kw in all_kws:
            for art in fts_search_in_law(kw, law_title):
                add(art, f"FTS:{law_title}")

    # ── 3. 领域范围 FTS ──
    law_cats   = ["法律", "宪法", "修正案", "法律解释", "监察法规"]
    interp_cats = ["司法解释"]

    for kw in all_kws:
        for art in fts_search_domains(kw, expert.fts_domains, law_cats, limit=8):
            add(art, "FTS-法律")
        for art in fts_search_domains(kw, expert.fts_domains, interp_cats, limit=5):
            add(art, "FTS-司法解释")

    if verbose:
        print(f"        检索到 {len(results)} 条（{expert.name}）")
    return results


def _extract_kws_simple(text: str) -> list[str]:
    """简单提取 2-6 字 CJK 词组（不调用 LLM，作为备用）"""
    # 提取已知高频法律词
    _COMMON = [
        "违约责任", "合同解除", "损害赔偿", "劳动合同", "经济补偿",
        "工资拖欠", "工伤认定", "消费者权益", "假冒伪劣", "欺诈",
        "名誉权", "隐私权", "故意伤害", "贪污受贿", "诉讼时效",
        "合同诈骗", "刑事责任", "行政处罚", "侵权责任", "财产保全",
        "婚姻家庭", "遗产继承", "股东权利", "产品责任", "平台责任",
    ]
    found = [kw for kw in _COMMON if kw in text]
    # 加上 3-4 字 CJK 片段（粗提取）
    for m in re.finditer(r'[一-鿿]{3,6}', text):
        w = m.group(0)
        if w not in found:
            found.append(w)
    return found[:8]


# ── 相关性过滤（轻量版）────────────────────────────────────────────────

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
            raw = chat(_FILTER_SYSTEM, f"问题：{question}\n\n{numbered}",
                       temperature=0.01)
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
            if verdicts.get(i, True):  # default: keep
                kept.append(a)
    return kept if kept else articles


# ── Layer 2: 子专家分析 ───────────────────────────────────────────────

def sub_expert_analyze(expert: SubExpert,
                       question: str,
                       all_facts: dict[str, str],
                       articles: list[dict]) -> str:
    if not articles:
        return f"（{expert.name}：未检索到相关条文，无法分析。）"

    law_arts = [a for a in articles if a.get("category") != "司法解释"]
    interp_arts = [a for a in articles if a.get("category") == "司法解释"]

    parts = []
    if law_arts:
        parts.append("【法律原文】")
        for a in law_arts[:10]:
            parts.append(
                f"《{a.get('law','')}》{a.get('article_number','')}："
                f"{a.get('content','')[:400]}"
            )
    if interp_arts:
        parts.append("\n【司法解释】")
        for a in interp_arts[:5]:
            parts.append(
                f"《{a.get('law','')}》{a.get('article_number','')}："
                f"{a.get('content','')[:400]}"
            )
    context = "\n".join(parts)

    facts_text = ""
    if all_facts:
        facts_text = "\n\n【已知情况】\n" + "\n".join(
            f"- {k}：{v}" for k, v in all_facts.items()
        )

    user_msg = f"法条：\n{context}{facts_text}\n\n用户问题：{question}"
    return chat(expert.answer_template, user_msg, temperature=0.2)


# ── Layer 1: 专家组综合 ───────────────────────────────────────────────

_GROUP_SYNTH_SYSTEM = """你是{group_name}负责人。将以下细分专家的分析整合成连贯的专业意见。

要求：
1. 去除重复内容，保留最重要的结论
2. 突出条文引用（保留"《XXX》第X条"格式）
3. 使用小标题区分不同方面
4. 总长度不超过400字

直接输出整合后的分析，不要说"根据以上分析"等套话。"""


def expert_group_synthesize(group: ExpertGroup,
                             sub_answers: dict[str, str],
                             question: str) -> str:
    if not sub_answers:
        return ""
    if len(sub_answers) == 1:
        return next(iter(sub_answers.values()))

    combined = "\n\n".join(
        f"【{name}的分析】\n{ans}"
        for name, ans in sub_answers.items()
    )
    system = _GROUP_SYNTH_SYSTEM.format(group_name=group.name)
    user_msg = f"用户问题：{question}\n\n{combined}"
    return chat(system, user_msg, temperature=0.15)


# ── Coordinator 最终综合 ─────────────────────────────────────────────

_FINAL_SYNTH_SYSTEM = """你是中国法律问题综合顾问。将多个专家组的分析整合为最终回答。

格式要求：
1. 开头直接给出核心结论（1-2句）
2. 按专家组分段陈述详细分析
3. 末尾列出"⚖️ 引用法条"（格式：• 《法律名》第X条 — 摘要）
4. 如涉及诉讼，注明应去哪个法院
5. 总长度500-800字，通俗易懂

不要说"根据以上"、"综上所述"等空话。直接给结论。"""


def coordinator_final_answer(question: str,
                              group_answers: dict[str, str],
                              all_articles: list[dict]) -> str:
    if not group_answers:
        return "未能检索到相关法律条文，建议咨询专业律师。"

    combined = "\n\n".join(
        f"【{group_name}】\n{ans}"
        for group_name, ans in group_answers.items()
    )

    # 汇总引用法条
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


# ── 信息收集对话 ──────────────────────────────────────────────────────

def _ask_missing_info(missing_fields: list[tuple[str, str]]) -> dict[str, str]:
    """向用户一次性提问，收集缺失信息"""
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


# ── 主流程 ────────────────────────────────────────────────────────────

def run(question: str, interactive: bool = True,
        pre_answers: Optional[dict[str, str]] = None,
        verbose: bool = True) -> dict:
    """
    主入口。

    :param question:    用户问题
    :param interactive: 是否交互式补充信息
    :param pre_answers: 预设答案（自动化测试时使用）
    :param verbose:     是否打印详细过程
    :return:            包含最终回答和各层结果的字典
    """

    def log(title: str, content: str = ""):
        if verbose:
            print(f"\n{'─' * 52}")
            print(f"▶ {title}")
            if content:
                for line in content.splitlines():
                    print(f"  {line}")

    print(f"\n{'═' * 60}")
    print(f"❓ {question}")
    print(f"   Provider: {_PROVIDER_STATE['current']} / "
          f"{PROVIDERS[_PROVIDER_STATE['current']]['model']}")

    # ─────────────────────────────────────────────
    # Step 1: 路由到专家组
    # ─────────────────────────────────────────────
    log("Step 1  路由到专家组")
    group_names = identify_groups(question)
    log("路由结果", "、".join(group_names))
    groups = [ALL_GROUPS[n] for n in group_names if n in ALL_GROUPS]

    # ─────────────────────────────────────────────
    # Step 2: 各专家组确定子专家 + 自动提取已知信息
    # ─────────────────────────────────────────────
    log("Step 2  确定子专家 + 提取已知信息")
    group_to_experts: dict[str, list[SubExpert]] = {}
    all_selected_experts: list[SubExpert] = []

    for group in groups:
        # 粗提取 known_facts（此时还不完整）
        rough_facts = auto_extract_facts(question, group.sub_experts)
        selected = identify_sub_experts(group, question, rough_facts)
        group_to_experts[group.name] = selected
        all_selected_experts.extend(selected)
        if verbose:
            print(f"  {group.name}: {[e.name for e in selected]}")

    # 去重（同一子专家可能被多组引用）
    seen_names: set[str] = set()
    unique_experts: list[SubExpert] = []
    for e in all_selected_experts:
        if e.name not in seen_names:
            seen_names.add(e.name)
            unique_experts.append(e)

    # ─────────────────────────────────────────────
    # Step 3: 信息收集
    # ─────────────────────────────────────────────
    log("Step 3  信息收集")
    known_facts = auto_extract_facts(question, unique_experts)
    if verbose and known_facts:
        print("  自动提取：" + "；".join(f"{k}={v}" for k, v in known_facts.items()))

    # 合并预设答案
    if pre_answers:
        known_facts.update(pre_answers)

    missing_fields = collect_missing_info(unique_experts, known_facts)

    if missing_fields and interactive:
        extra = _ask_missing_info(missing_fields)
        known_facts.update(extra)
    elif missing_fields and not interactive:
        if verbose:
            print(f"  跳过信息收集（非交互模式），缺少：{[f for f, _ in missing_fields]}")

    # ─────────────────────────────────────────────
    # Step 4: 各子专家检索 + 分析
    # ─────────────────────────────────────────────
    log("Step 4  子专家检索与分析")
    expert_articles: dict[str, list[dict]] = {}
    expert_answers: dict[str, str] = {}

    for expert in unique_experts:
        if verbose:
            print(f"\n  ── {expert.name} ──")

        # 检索
        articles = sub_expert_retrieve(expert, question, known_facts, verbose=verbose)

        # 引用链扩展
        articles = expand_references(articles, verbose=verbose)

        # 相关性过滤
        if len(articles) > 8:
            before = len(articles)
            articles = filter_articles_light(question, articles)
            if verbose:
                print(f"        过滤: {before} → {len(articles)} 条")

        expert_articles[expert.name] = articles

        # 分析
        answer = sub_expert_analyze(expert, question, known_facts, articles)
        expert_answers[expert.name] = answer

        if verbose:
            print(f"        答案预览: {answer[:120]}...")

    # ─────────────────────────────────────────────
    # Step 5: 专家组综合
    # ─────────────────────────────────────────────
    log("Step 5  专家组综合")
    group_answers: dict[str, str] = {}

    for group in groups:
        experts_in_group = group_to_experts.get(group.name, [])
        sub_ans = {e.name: expert_answers[e.name]
                   for e in experts_in_group if e.name in expert_answers}
        if not sub_ans:
            continue
        group_ans = expert_group_synthesize(group, sub_ans, question)
        group_answers[group.name] = group_ans
        if verbose:
            print(f"\n  【{group.name}】\n  {group_ans[:150]}...")

    # ─────────────────────────────────────────────
    # Step 6: 协调员最终综合
    # ─────────────────────────────────────────────
    log("Step 6  协调员最终综合")
    all_articles_flat: list[dict] = []
    seen_ids: set[int] = set()
    for arts in expert_articles.values():
        for a in arts:
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"])
                all_articles_flat.append(a)

    final_answer = coordinator_final_answer(question, group_answers, all_articles_flat)

    # ─────────────────────────────────────────────
    # 输出
    # ─────────────────────────────────────────────
    print(f"\n{'═' * 60}")
    print(f"❓ {question}")
    print(f"\n{'─' * 60}")

    for group_name, ans in group_answers.items():
        expert_names = [e.name for e in group_to_experts.get(group_name, [])]
        header = f"【{group_name}分析】" + (
            f" — {' + '.join(expert_names)}" if expert_names else ""
        )
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


# ── 演示问题 ──────────────────────────────────────────────────────────

DEMO_QUESTIONS = [
    "网购假货商家不退款，我可以要求多少赔偿？",
    "公司拖欠工资三个月，试用期被辞退怎么办？",
    "房东在租期内要求涨租并赶人，我有什么权利？",
    "邻居家狗咬伤了我，怎么索赔？",
    "公司强制要求员工加班不给加班费，如何维权？",
]


# ── 入口 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="多层专家协作法律问答系统")
    parser.add_argument("--question", "-q", type=str, default=None,
                        help="输入问题")
    parser.add_argument("--provider", "-p", type=str,
                        default=DEFAULT_PROVIDER,
                        choices=list(PROVIDERS.keys()),
                        help="LLM 服务商")
    parser.add_argument("--no-interactive", action="store_true",
                        help="非交互模式（不询问补充信息）")
    parser.add_argument("--all", action="store_true",
                        help="跑所有演示问题")
    args = parser.parse_args()

    _PROVIDER_STATE["current"] = args.provider

    if args.question:
        run(args.question, interactive=not args.no_interactive)
    elif args.all:
        for q in DEMO_QUESTIONS:
            run(q, interactive=False)
            print()
    else:
        # 交互模式
        print(f"多层专家协作法律问答系统  (provider: {args.provider})")
        print("输入问题后回车，输入 'q' 退出\n")
        while True:
            try:
                q = input("❓ ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n退出")
                break
            if not q or q.lower() in ('q', 'quit', 'exit'):
                break
            run(q, interactive=True)
