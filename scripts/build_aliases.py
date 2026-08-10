#!/usr/bin/env python3
"""
建立日常语言 → 法律术语 别名表
产物：law_enhancements.db 中的 term_aliases 表
（FTS 验证仍需读 law_content.db，通过 ATTACH 实现）

用法：
    cd path/to/laws_data
    python3 scripts/build_aliases.py
"""

import json
import sqlite3
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONTENT_DB_PATH     = BASE_DIR / "law_content.db"
ENHANCEMENTS_DB_PATH = BASE_DIR / "law_enhancements.db"
DB_PATH = ENHANCEMENTS_DB_PATH  # 写入目标
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL      = "qwen2.5:3b"

# ── 种子词表：日常语言 ────────────────────────────────────────────────
# 按场景分组，每组对应一个典型用户问题场景
SEED_TERMS = [
    # 交通事故
    "车祸", "撞车", "超速", "闯红灯", "酒驾", "醉驾", "逃逸", "肇事",
    "交通赔偿", "出车祸", "被车撞", "开车撞人",

    # 劳动权益
    "被炒鱿鱼", "被开除", "被辞退", "老板不发工资", "拖欠工资", "克扣工资",
    "加班费", "试用期", "工伤", "工伤赔偿", "职业病", "社保",

    # 消费维权
    "买到假货", "买到假冒商品", "网购退货", "七天无理由退货", "商家不退款",
    "虚假宣传", "食品安全", "食物中毒", "产品质量", "三包",

    # 房屋租赁
    "房东涨租", "房东不退押金", "押金", "租房合同", "提前退房", "强制驱逐",
    "房屋漏水", "租房纠纷",

    # 婚姻家庭
    "离婚", "财产分割", "夫妻共同财产", "子女抚养权", "抚养费",
    "家暴", "出轨", "婚外情", "遗产继承", "遗嘱",

    # 借贷纠纷
    "借钱不还", "欠钱不还", "高利贷", "利息", "借条", "欠条",
    "打白条", "民间借贷", "催债",

    # 人身伤害
    "被打了", "打架", "故意伤害", "受伤", "医疗费", "误工费",
    "精神损失", "残疾赔偿",

    # 合同纠纷
    "违约", "合同不履行", "欺诈", "被骗", "定金", "订金",
    "合同作废", "强迫签合同",

    # 隐私/网络
    "个人信息泄露", "隐私泄露", "被网暴", "诽谤", "名誉受损",

    # 刑事
    "被偷", "被抢", "被骗钱", "诈骗", "电信诈骗", "敲诈勒索",
]

# ── LLM 调用 ─────────────────────────────────────────────────────────

def chat(system: str, user: str) -> str:
    payload = json.dumps({
        "model": MODEL,
        "stream": False,
        "options": {"temperature": 0.1},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["message"]["content"]


def parse_json_list(raw: str) -> list[str]:
    s = raw.find('[')
    e = raw.rfind(']') + 1
    if s >= 0 and e > s:
        try:
            result = json.loads(raw[s:e])
            if isinstance(result, list):
                return [x for x in result if isinstance(x, str) and 2 <= len(x.strip()) <= 10]
        except json.JSONDecodeError:
            pass
    return []


# ── LLM 生成候选法律词 ──────────────────────────────────────────────

EXPAND_SYSTEM = """你是中国法律术语专家。将日常用语转换为法律条文中实际出现的专业术语。

要求：
1. 输出该日常词对应的 3-6 个法律专业术语
2. 术语必须是法律条文正文中真实出现的表达
3. 每个术语 2-8 个汉字
4. 只输出 JSON 数组，不要其他内容

例如：
日常词：车祸
输出：["交通事故", "道路交通事故", "机动车事故", "交通肇事"]

日常词：被炒鱿鱼
输出：["解除劳动合同", "劳动合同解除", "违法解除", "用人单位解除"]"""


def generate_candidates(term: str) -> list[str]:
    raw = chat(EXPAND_SYSTEM, f"日常词：{term}")
    return parse_json_list(raw)


# ── FTS 验证：候选词是否真实命中条文 ───────────────────────────────

def fts_hits(term: str, conn: sqlite3.Connection) -> int:
    cjk = [c for c in term if '一' <= c <= '鿿']
    if len(cjk) >= 3:
        try:
            rows = conn.execute(
                "SELECT COUNT(*) FROM nodes_fts f JOIN nodes n ON f.rowid=n.id "
                "WHERE nodes_fts MATCH ? AND n.type='article'",
                [term]
            ).fetchone()
            return rows[0] if rows else 0
        except Exception:
            return 0
    elif len(cjk) >= 1:
        try:
            rows = conn.execute(
                "SELECT COUNT(*) FROM nodes_fts_bigram f JOIN nodes n ON f.rowid=n.id "
                "WHERE nodes_fts_bigram MATCH ? AND n.type='article'",
                [term]
            ).fetchone()
            return rows[0] if rows else 0
        except Exception:
            return 0
    return 0


# ── 建表 & 写入 ─────────────────────────────────────────────────────

def init_table(conn: sqlite3.Connection):
    conn.execute("DROP TABLE IF EXISTS term_aliases")
    conn.execute("""
        CREATE TABLE term_aliases (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            colloquial  TEXT NOT NULL,
            legal_term  TEXT NOT NULL,
            fts_hits    INTEGER NOT NULL DEFAULT 0,
            UNIQUE(colloquial, legal_term)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_aliases_colloquial ON term_aliases(colloquial)")
    conn.commit()


def run():
    enh_conn     = sqlite3.connect(ENHANCEMENTS_DB_PATH)
    content_conn = sqlite3.connect(CONTENT_DB_PATH)
    init_table(enh_conn)

    total_inserted = 0
    for i, term in enumerate(SEED_TERMS):
        print(f"[{i+1}/{len(SEED_TERMS)}] {term} ...", end=" ", flush=True)

        candidates = generate_candidates(term)
        if not candidates:
            print("(LLM 无输出，跳过)")
            continue

        inserted = 0
        for cand in candidates:
            hits = fts_hits(cand, content_conn)
            if hits > 0:
                try:
                    enh_conn.execute(
                        "INSERT OR IGNORE INTO term_aliases (colloquial, legal_term, fts_hits) VALUES (?,?,?)",
                        [term, cand, hits]
                    )
                    inserted += 1
                except Exception:
                    pass

        enh_conn.commit()
        print(f"候选 {candidates} → 有效 {inserted} 条")
        total_inserted += inserted

    content_conn.close()
    enh_conn.close()
    print(f"\n完成，共写入 {total_inserted} 条别名")


if __name__ == "__main__":
    print(f"内容库：{CONTENT_DB_PATH}  增强库：{ENHANCEMENTS_DB_PATH}  模型：{MODEL}")
    print("=" * 60)
    run()
