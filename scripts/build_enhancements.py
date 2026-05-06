#!/usr/bin/env python3
"""
建立 law_enhancements.db 中的增强表（除 term_aliases 外）

表1: alias_patches   — 手工精确补充 term_aliases 缺口（FTS 已验证）
表2: topic_law_hints — 用户问题场景 → 高相关法律名称（提升检索精准度）
表3: keyword_synonyms — LLM 关键词 → 同义/上位词（拓宽 FTS 召回）

用法：
    cd /Users/doxie/laws_data
    python3 scripts/build_enhancements.py
"""

import sqlite3
from pathlib import Path

CONTENT_DB_PATH      = Path("/Users/doxie/laws_data/law_content.db")
ENHANCEMENTS_DB_PATH = Path("/Users/doxie/laws_data/law_enhancements.db")


# ── 表1: alias_patches ──────────────────────────────────────────────
# 手工补充 build_aliases.py 中 LLM 漏掉/词不对 的映射
# 格式: (日常词, 法律术语)  — 均已手工验证 FTS hits > 0

ALIAS_PATCHES = [
    # 离婚
    ("离婚",    "离婚登记"),
    ("离婚",    "离婚诉讼"),
    ("离婚",    "婚姻自由"),
    ("离婚",    "解除婚姻关系"),
    # 夫妻共同财产
    ("夫妻共同财产", "夫妻共同财产"),
    # 误工费
    ("误工费",  "误工损失"),
    # 工伤
    ("工伤",    "工伤认定"),
    ("工伤",    "工伤保险"),
    # 网购退货
    ("网购退货",    "无理由退货"),
    ("网购退货",    "网络购物"),
    ("七天无理由退货", "无理由退货"),
    # 房东涨租 / 租房
    ("房东涨租",    "房屋租赁"),
    ("房东不退押金", "房屋租赁"),
    ("提前退房",    "房屋租赁"),
    ("租房合同",    "房屋租赁"),
    # 婚外情/出轨 → 法条里用"重婚"或"家庭暴力"
    ("出轨",    "离婚诉讼"),
    ("婚外情",  "离婚诉讼"),
    # 欠条/欠钱不还
    ("欠条",        "借款合同"),
    ("欠钱不还",    "借款合同"),
    ("欠钱不还",    "民间借贷"),
    # 名誉受损
    ("名誉受损",    "名誉权"),
    # 强迫签合同
    ("强迫签合同",  "合同撤销"),
    ("强迫签合同",  "无效合同"),
]


# ── 表2: topic_law_hints ────────────────────────────────────────────
# 用户问题场景关键词 → 最相关法律标题
# 检索时：若关键词命中 topic，优先在这些法律内做 FTS，结果更精准
# 格式: (topic_keyword, law_title, priority)  priority 越小越靠前

TOPIC_LAW_HINTS = [
    # 消费维权
    ("消费者",          "中华人民共和国消费者权益保护法",        1),
    ("消费者",          "中华人民共和国消费者权益保护法实施条例", 2),
    ("消费者",          "中华人民共和国电子商务法",               3),
    ("消费者",          "中华人民共和国产品质量法",               4),
    ("假货",            "中华人民共和国消费者权益保护法",        1),
    ("假货",            "中华人民共和国产品质量法",               2),
    ("网购",            "中华人民共和国电子商务法",               1),
    ("网购",            "中华人民共和国消费者权益保护法",        2),
    ("退货",            "中华人民共和国消费者权益保护法",        1),
    ("退货",            "中华人民共和国电子商务法",               2),
    ("食品",            "中华人民共和国食品安全法",               1),
    ("食品",            "中华人民共和国消费者权益保护法",        2),

    # 劳动权益
    ("劳动",            "中华人民共和国劳动合同法",               1),
    ("劳动",            "中华人民共和国劳动法",                   2),
    ("工资",            "中华人民共和国劳动合同法",               1),
    ("试用期",          "中华人民共和国劳动合同法",               1),
    ("解雇",            "中华人民共和国劳动合同法",               1),
    ("工伤",            "工伤保险条例",                           1),
    ("工伤",            "中华人民共和国劳动合同法",               2),
    ("社会保险",        "中华人民共和国社会保险法",               1),

    # 交通事故
    ("交通事故",        "中华人民共和国民法典",                   1),
    ("交通事故",        "中华人民共和国道路交通安全法",           2),
    ("机动车",          "中华人民共和国民法典",                   1),
    ("机动车",          "中华人民共和国道路交通安全法",           2),

    # 婚姻家庭
    ("离婚",            "中华人民共和国民法典",                   1),
    ("婚姻",            "中华人民共和国民法典",                   1),
    ("抚养",            "中华人民共和国民法典",                   1),
    ("抚养",            "最高人民法院关于适用《中华人民共和国民法典》婚姻家庭编的解释（一）", 2),
    ("家庭暴力",        "中华人民共和国反家庭暴力法",             1),
    ("家庭暴力",        "中华人民共和国民法典",                   2),

    # 继承
    ("继承",            "中华人民共和国民法典",                   1),
    ("继承",            "最高人民法院关于适用《中华人民共和国民法典》继承编的解释（一）", 2),
    ("遗嘱",            "中华人民共和国民法典",                   1),

    # 借贷合同
    ("借款",            "中华人民共和国民法典",                   1),
    ("民间借贷",        "最高人民法院关于审理民间借贷案件适用法律若干问题的规定", 1),
    ("民间借贷",        "中华人民共和国民法典",                   2),
    ("合同",            "中华人民共和国民法典",                   1),
    ("违约",            "中华人民共和国民法典",                   1),

    # 侵权/人身伤害
    ("侵权",            "中华人民共和国民法典",                   1),
    ("侵权",            "最高人民法院关于适用《中华人民共和国民法典》侵权责任编的解释（一）", 2),
    ("人身损害",        "中华人民共和国民法典",                   1),

    # 个人信息/隐私
    ("个人信息",        "中华人民共和国个人信息保护法",           1),
    ("隐私",            "中华人民共和国民法典",                   1),
    ("隐私",            "中华人民共和国个人信息保护法",           2),
    ("名誉",            "中华人民共和国民法典",                   1),

    # 刑事
    ("盗窃",            "中华人民共和国刑法",                     1),
    ("抢劫",            "中华人民共和国刑法",                     1),
    ("诈骗",            "中华人民共和国刑法",                     1),
    ("故意伤害",        "中华人民共和国刑法",                     1),
    ("敲诈勒索",        "中华人民共和国刑法",                     1),
]


# ── 表3: keyword_synonyms ───────────────────────────────────────────
# LLM 可能输出的词 → 更精确的 FTS 关键词
# 解决 LLM 关键词提取"词对但无命中"的问题

KEYWORD_SYNONYMS = [
    # 交通
    ("道路交通损害赔偿",    "道路交通事故"),
    ("机动车事故",          "交通事故"),
    ("车辆事故",            "交通事故"),
    ("超速驾驶",            "超过规定速度"),
    ("酒后驾车",            "醉酒驾驶"),
    ("肇事逃逸",            "交通肇事逃逸"),

    # 劳动
    ("工资拖欠",            "劳动报酬"),
    ("劳动合同解除",        "解除劳动合同"),
    ("拒付工资",            "劳动报酬"),
    ("工作伤害",            "工伤认定"),
    ("职业损伤",            "工伤保险"),

    # 消费
    ("假冒商品",            "伪劣商品"),
    ("虚假宣传",            "虚假广告"),
    ("电商退货",            "无理由退货"),
    ("网络消费",            "网络购物"),
    ("食品问题",            "食品安全"),

    # 房屋租赁
    ("房租纠纷",            "房屋租赁"),
    ("押金纠纷",            "租赁合同"),
    ("提前解约",            "合同解除"),

    # 婚姻家庭
    ("离婚财产",            "夫妻共同财产"),
    ("子女监护",            "抚养费"),
    ("家庭暴力",            "家庭暴力"),
    ("遗产分配",            "继承权"),
    ("立遗嘱",              "自书遗嘱"),

    # 借贷
    ("民间借款",            "民间借贷"),
    ("个人借款",            "借款合同"),
    ("高额利息",            "民间借贷"),

    # 人身伤害
    ("殴打伤害",            "故意伤害"),
    ("人身损失",            "人身损害赔偿"),
    ("医疗损失",            "医疗费用"),
    ("收入损失",            "误工损失"),
    ("精神赔偿",            "精神损害"),

    # 合同
    ("合同欺诈",            "合同撤销"),
    ("强制签约",            "无效合同"),
    ("合同违约",            "违约责任"),
    ("定金退还",            "违约金"),

    # 隐私/名誉
    ("信息泄露",            "个人信息"),
    ("网络侮辱",            "名誉权"),
    ("网络诽谤",            "侮辱罪"),

    # 刑事
    ("财产盗取",            "盗窃罪"),
    ("诈骗钱财",            "诈骗罪"),
    ("电信欺诈",            "电信网络诈骗"),
    ("强行索财",            "敲诈勒索罪"),
]


# ── 建表 & 写入 ─────────────────────────────────────────────────────

def fts_hits(term: str, conn: sqlite3.Connection) -> int:
    cjk = [c for c in term if '一' <= c <= '鿿']
    if len(cjk) >= 3:
        try:
            r = conn.execute(
                "SELECT COUNT(*) FROM nodes_fts f JOIN nodes n ON f.rowid=n.id "
                "WHERE nodes_fts MATCH ? AND n.type='article'", [term]
            ).fetchone()
            return r[0] if r else 0
        except Exception:
            return 0
    return 0


def build_alias_patches(enh: sqlite3.Connection, content: sqlite3.Connection):
    enh.execute("DROP TABLE IF EXISTS alias_patches")
    enh.execute("""
        CREATE TABLE alias_patches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            colloquial  TEXT NOT NULL,
            legal_term  TEXT NOT NULL,
            fts_hits    INTEGER NOT NULL DEFAULT 0,
            UNIQUE(colloquial, legal_term)
        )
    """)
    enh.execute("CREATE INDEX IF NOT EXISTS idx_patches_colloquial ON alias_patches(colloquial)")

    inserted = 0
    for colloquial, legal_term in ALIAS_PATCHES:
        hits = fts_hits(legal_term, content)
        if hits > 0:
            enh.execute(
                "INSERT OR IGNORE INTO alias_patches (colloquial, legal_term, fts_hits) VALUES (?,?,?)",
                [colloquial, legal_term, hits]
            )
            inserted += 1
        else:
            print(f"  [跳过] {colloquial} → {legal_term} (0 hits)")
    enh.commit()
    print(f"alias_patches: 写入 {inserted} 条")


def build_topic_law_hints(enh: sqlite3.Connection, content: sqlite3.Connection):
    enh.execute("DROP TABLE IF EXISTS topic_law_hints")
    enh.execute("""
        CREATE TABLE topic_law_hints (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_keyword TEXT NOT NULL,
            law_title     TEXT NOT NULL,
            priority      INTEGER NOT NULL DEFAULT 10,
            UNIQUE(topic_keyword, law_title)
        )
    """)
    enh.execute("CREATE INDEX IF NOT EXISTS idx_hints_topic ON topic_law_hints(topic_keyword)")

    inserted = 0
    skipped = 0
    for topic, title, priority in TOPIC_LAW_HINTS:
        exists = content.execute(
            "SELECT COUNT(*) FROM laws WHERE title=? AND is_current=1", [title]
        ).fetchone()[0]
        if exists:
            enh.execute(
                "INSERT OR IGNORE INTO topic_law_hints (topic_keyword, law_title, priority) VALUES (?,?,?)",
                [topic, title, priority]
            )
            inserted += 1
        else:
            print(f"  [跳过] 法律不存在: {title}")
            skipped += 1
    enh.commit()
    print(f"topic_law_hints: 写入 {inserted} 条，跳过 {skipped} 条")


def build_keyword_synonyms(enh: sqlite3.Connection, content: sqlite3.Connection):
    enh.execute("DROP TABLE IF EXISTS keyword_synonyms")
    enh.execute("""
        CREATE TABLE keyword_synonyms (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_kw   TEXT NOT NULL,
            target_kw   TEXT NOT NULL,
            fts_hits    INTEGER NOT NULL DEFAULT 0,
            UNIQUE(source_kw, target_kw)
        )
    """)
    enh.execute("CREATE INDEX IF NOT EXISTS idx_synonyms_source ON keyword_synonyms(source_kw)")

    inserted = 0
    for source, target in KEYWORD_SYNONYMS:
        hits = fts_hits(target, content)
        if hits > 0:
            enh.execute(
                "INSERT OR IGNORE INTO keyword_synonyms (source_kw, target_kw, fts_hits) VALUES (?,?,?)",
                [source, target, hits]
            )
            inserted += 1
        else:
            print(f"  [跳过] {source} → {target} (0 hits)")
    enh.commit()
    print(f"keyword_synonyms: 写入 {inserted} 条")


def run():
    enh     = sqlite3.connect(ENHANCEMENTS_DB_PATH)
    content = sqlite3.connect(CONTENT_DB_PATH)

    print("建立 alias_patches ...")
    build_alias_patches(enh, content)

    print("\n建立 topic_law_hints ...")
    build_topic_law_hints(enh, content)

    print("\n建立 keyword_synonyms ...")
    build_keyword_synonyms(enh, content)

    content.close()
    enh.close()
    print("\n完成")


if __name__ == "__main__":
    print(f"内容库：{CONTENT_DB_PATH}")
    print(f"增强库：{ENHANCEMENTS_DB_PATH}")
    print("=" * 60)
    run()
