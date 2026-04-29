#!/usr/bin/env python3
"""
构建法律知识图谱：
1. 主题分类 (taxonomy.json)
2. 版本历史 (versions.json)
3. 上位法-下位法层级 (hierarchy.json)
4. 关联关系图 (relations.json)
5. 总览摘要 (README.md)
"""

import json
import re
from pathlib import Path
from collections import defaultdict

SRC_INDEX = Path("/Users/doxie/laws_data mannual/json/index.json")
SRC_JSON  = Path("/Users/doxie/laws_data mannual/json")
OUT_DIR   = Path("/Users/doxie/laws_data mannual/knowledge")

# ─────────────────────────────────────────────
# 1. 主题分类规则
#    每个领域给出若干关键词（匹配法律标题）
# ─────────────────────────────────────────────
TAXONOMY = {
    "宪法与国家机构": {
        "keywords": ["宪法","全国人民代表大会","人民代表大会","国务院组织法","国家主席",
                     "地方各级人民","选举","立法法","戒严","国旗","国徽","国歌"],
        "sub": {}
    },
    "刑事法": {
        "keywords": ["刑法","刑事诉讼","监狱","社区矫正","禁毒","反恐怖","有组织犯罪",
                     "刑事司法协助","引渡","刑法修正案"],
        "sub": {}
    },
    "民事法": {
        "keywords": ["民法典","合同","侵权","婚姻","继承","物权","人格权","民事诉讼",
                     "仲裁","调解","公证","律师","法律援助","法律援助"],
        "sub": {}
    },
    "行政法": {
        "keywords": ["行政处罚","行政复议","行政强制","行政许可","行政诉讼","国家赔偿",
                     "政府信息公开","治安管理","突发事件"],
        "sub": {}
    },
    "经济与商事法": {
        "keywords": ["公司法","合伙企业","破产","证券","期货","银行","保险","信托","票据",
                     "拍卖","招标投标","政府采购","反垄断","反不正当竞争","广告","价格",
                     "消费者权益","电子商务","电子签名","外商投资","对外贸易","海关",
                     "关税","反倾销","反补贴","出口管制","外汇","资产评估"],
        "sub": {}
    },
    "税法与财政": {
        "keywords": ["税","增值税","个人所得税","企业所得税","关税法","印花税","契税",
                     "耕地占用税","资源税","车船税","车辆购置税","预算","国库","烟叶税",
                     "环境保护税","城市维护建设税","审计","统计","会计","注册会计师"],
        "sub": {}
    },
    "劳动与社会保障": {
        "keywords": ["劳动法","劳动合同","劳动争议","工会","社会保险","就业","职业病",
                     "安全生产","矿山安全"],
        "sub": {}
    },
    "民政与民族": {
        "keywords": ["民族区域自治","村民委员会","居民委员会","归侨侨眷","残疾人",
                     "老年人","未成年人","妇女","慈善","红十字","献血","公益事业"],
        "sub": {}
    },
    "教育、科技与文化": {
        "keywords": ["教育法","义务教育","高等教育","职业教育","民办教育","学位","学前教育",
                     "教师","家庭教育","科学技术","科技成果","标准化","计量","档案",
                     "文物","非物质文化遗产","著作权","旅游","体育","电影","公共文化",
                     "公共图书馆","广播电视","爱国主义教育","法治宣传"],
        "sub": {}
    },
    "知识产权": {
        "keywords": ["专利","商标","著作权","知识产权","植物新品种"],
        "sub": {}
    },
    "环境与资源": {
        "keywords": ["环境保护","大气污染","水污染","土壤污染","噪声污染","固体废物",
                     "环境影响评价","清洁生产","循环经济","节约能源","可再生能源","能源法",
                     "水法","水土保持","防洪","防沙","草原","森林","湿地","野生动物",
                     "土地管理","矿产资源","渔业","海洋","海域","海岛","深海","长江保护",
                     "黄河保护","黑土地","青藏高原","国家公园","放射性污染","核安全",
                     "生物安全","动物防疫","畜牧","种子","农产品质量"],
        "sub": {}
    },
    "农业与农村": {
        "keywords": ["农业","农村","农民","土地承包","乡村振兴","粮食安全","农业技术",
                     "农业机械","农村集体经济","农村土地"],
        "sub": {}
    },
    "卫生与医药": {
        "keywords": ["食品安全","药品","疫苗","医师","基本医疗卫生","传染病","精神卫生",
                     "母婴保健","职业病","国境卫生","突发公共卫生","中医药"],
        "sub": {}
    },
    "交通与基础设施": {
        "keywords": ["道路交通","铁路","公路","港口","航道","航运","海上交通","民用航空",
                     "邮政","建筑","城乡规划","城市房地产","不动产","土地增值","石油天然气",
                     "电力","煤炭","特种设备","计量","标准化"],
        "sub": {}
    },
    "信息与数据安全": {
        "keywords": ["网络安全","数据安全","个人信息保护","密码","电子签名","无线电",
                     "国家安全","反间谍","国家情报","保守国家秘密"],
        "sub": {}
    },
    "国防与军事": {
        "keywords": ["国防","兵役","军事","武装警察","国防动员","国防交通","国防教育",
                     "退役军人","军官","预备役","人民武装","军人保险","军人地位",
                     "现役军官","海警","陆地国界","领海","领事","外交"],
        "sub": {}
    },
    "港澳台与涉外": {
        "keywords": ["香港","澳门","台湾","驻外","领事特权","外交特权","国籍","出境入境",
                     "外国人","对外关系","缔结条约","国际","涉外","外资","海南自由贸易港"],
        "sub": {}
    },
    "诉讼程序与司法组织": {
        "keywords": ["人民法院","人民检察院","法官法","检察官","人民陪审员","司法","诉讼",
                     "法律援助","公益诉讼","执行","仲裁","调解","监察法","监察官","监察法规",
                     "监察工作","行政执法","刑事诉讼规则","民事诉讼监督","行政诉讼监督"],
        "sub": {}
    },
}


def classify(title: str, full_text: str = "") -> str:
    """根据标题（和少量正文关键词）判断所属领域"""
    combined = title + " " + full_text[:200]
    scores = defaultdict(int)
    for domain, info in TAXONOMY.items():
        for kw in info["keywords"]:
            if kw in combined:
                scores[domain] += 1
    if scores:
        return max(scores, key=scores.get)
    return "其他"


# ─────────────────────────────────────────────
# 2. 版本检测：同名法律多个版本
# ─────────────────────────────────────────────
def normalize_title(title: str) -> str:
    """去掉修正案编号等，归一化标题用于版本分组"""
    t = title.strip()
    # 去掉多余空白/换行
    t = re.sub(r'\s+', '', t)
    return t


# ─────────────────────────────────────────────
# 3. 上位法-下位法链接规则
#    行政法规 -> 法律（找标题中包含的上位法名）
#    司法解释 -> 法律（找标题中《》里的法律名）
# ─────────────────────────────────────────────
def find_parent_laws(title: str, full_text: str, law_titles: set) -> list:
    """在标题和全文中找到被引用的上位法"""
    # 找《》里引用的法律名
    quoted = re.findall(r'《([^》]+)》', title + " " + full_text[:500])
    parents = []
    for q in quoted:
        q_norm = re.sub(r'\s+', '', q)
        if q_norm in law_titles:
            parents.append(q_norm)
    
    # 行政法规：名字本身包含"XXX法实施条例/细则/办法"
    m = re.search(r'(.{4,30}法)实施(条例|细则|办法|规定)', re.sub(r'\s+', '', title))
    if m:
        candidate = m.group(1)
        if candidate in law_titles:
            parents.append(candidate)
    
    return list(dict.fromkeys(parents))  # 去重保序


def main():
    OUT_DIR.mkdir(exist_ok=True)
    index = json.loads(SRC_INDEX.read_text(encoding="utf-8"))
    
    # 建立归一化标题集合（法律类 + 宪法）
    law_titles_norm = set()
    for item in index:
        if item["category"] in ("法律", "宪法"):
            law_titles_norm.add(normalize_title(item["title"]))
    
    # ── 读取每个文件的完整数据 ──
    records = []
    for item in index:
        fpath = SRC_JSON / item["file"]
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            records.append({**item, "_full_text": data.get("full_text", "")[:1000],
                             "_chapters": data.get("chapters", [])})
        except Exception:
            records.append({**item, "_full_text": "", "_chapters": []})
    
    # ═══════════════════════════════════
    # 文件1: taxonomy.json
    # 每条法律附上领域分类
    # ═══════════════════════════════════
    taxonomy_map = {}  # normalized_title -> domain
    domain_buckets = defaultdict(list)  # domain -> list of unique laws

    seen_in_domain = set()
    for r in records:
        norm = normalize_title(r["title"])
        domain = classify(r["title"], r["_full_text"])
        taxonomy_map[norm] = domain

    # 按领域汇总（每个法律只出现一次，取最新版）
    latest = {}  # norm_title -> record with latest pub_date
    for r in records:
        norm = normalize_title(r["title"])
        if norm not in latest or (r["pub_date"] or "") > (latest[norm]["pub_date"] or ""):
            latest[norm] = r

    for norm, r in latest.items():
        domain = taxonomy_map.get(norm, "其他")
        domain_buckets[domain].append({
            "title": r["title"],
            "category": r["category"],
            "latest_pub_date": r["pub_date"],
            "total_articles": r["total_articles"],
            "file": r["file"],
        })

    # 每个领域内按类别排序
    taxonomy_output = {}
    for domain in TAXONOMY:
        if domain_buckets[domain]:
            taxonomy_output[domain] = {
                "description": "，".join(TAXONOMY[domain]["keywords"][:5]) + "等相关法律",
                "count": len(domain_buckets[domain]),
                "laws": sorted(domain_buckets[domain],
                               key=lambda x: (x["category"], x["title"]))
            }
    if domain_buckets["其他"]:
        taxonomy_output["其他"] = {
            "description": "未能归类的文件",
            "count": len(domain_buckets["其他"]),
            "laws": domain_buckets["其他"]
        }

    (OUT_DIR / "taxonomy.json").write_text(
        json.dumps(taxonomy_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"taxonomy.json: {sum(v['count'] for v in taxonomy_output.values())} 条（{len(taxonomy_output)} 个领域）")

    # ═══════════════════════════════════
    # 文件2: versions.json
    # 同名法律的所有历史版本，按时间排列
    # ═══════════════════════════════════
    version_groups = defaultdict(list)
    for r in records:
        norm = normalize_title(r["title"])
        version_groups[norm].append({
            "pub_date": r["pub_date"],
            "category": r["category"],
            "total_articles": r["total_articles"],
            "file": r["file"],
        })
    
    versions_output = {}
    for norm, versions in version_groups.items():
        sorted_v = sorted(versions, key=lambda x: x["pub_date"] or "")
        if len(sorted_v) > 1:
            versions_output[norm] = {
                "version_count": len(sorted_v),
                "earliest": sorted_v[0]["pub_date"],
                "latest": sorted_v[-1]["pub_date"],
                "versions": sorted_v,
            }
    
    (OUT_DIR / "versions.json").write_text(
        json.dumps(versions_output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"versions.json: {len(versions_output)} 部法律存在多版本")

    # ═══════════════════════════════════
    # 文件3: hierarchy.json
    # 上位法-下位法层级关系
    # 宪法 > 法律 > 行政法规 > 司法解释（配套）
    # ═══════════════════════════════════
    # 明确的上下位关系（通过标题/《》引用分析）
    hierarchy = {
        "meta": {
            "description": "中国法律效力层级：宪法 > 法律（全国人大/常委会） > 行政法规（国务院） > 司法解释（最高法/最高检）",
            "levels": {
                "1": "宪法",
                "2": "基本法律（全国人大制定）",
                "3": "普通法律（全国人大常委会制定）",
                "4": "行政法规（国务院）",
                "5": "司法解释（最高人民法院/最高人民检察院）"
            }
        },
        "links": []
    }

    # 基本法律（全国人大制定，非常委会）
    basic_laws = {"中华人民共和国宪法","中华人民共和国刑法","中华人民共和国民法典",
                  "中华人民共和国刑事诉讼法","中华人民共和国民事诉讼法",
                  "中华人民共和国行政诉讼法","中华人民共和国立法法",
                  "中华人民共和国民族区域自治法","中华人民共和国香港特别行政区基本法",
                  "中华人民共和国澳门特别行政区基本法","中华人民共和国国防法",
                  "中华人民共和国兵役法"}

    def get_level(r):
        norm = normalize_title(r["title"])
        if r["category"] == "宪法": return 1
        if norm in {normalize_title(t) for t in basic_laws}: return 2
        if r["category"] == "法律": return 3
        if r["category"] in ("行政法规", "监察法规"): return 4
        if r["category"] == "司法解释": return 5
        return 3

    links = []
    for r in records:
        parents = find_parent_laws(r["title"], r["_full_text"], law_titles_norm)
        norm = normalize_title(r["title"])
        for p in parents:
            if p != norm:
                links.append({
                    "child": r["title"],
                    "child_category": r["category"],
                    "child_file": r["file"],
                    "parent": p,
                    "relation": "实施依据" if r["category"] == "行政法规" else "解释依据",
                })
    
    hierarchy["links"] = links

    # 也附上每条法律的层级编号
    level_map = []
    for norm, r in latest.items():
        level_map.append({
            "title": r["title"],
            "category": r["category"],
            "level": get_level(r),
            "domain": taxonomy_map.get(norm, "其他"),
            "file": r["file"],
        })
    hierarchy["level_map"] = sorted(level_map, key=lambda x: (x["level"], x["title"]))

    (OUT_DIR / "hierarchy.json").write_text(
        json.dumps(hierarchy, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"hierarchy.json: {len(links)} 条上下位关系链接")

    # ═══════════════════════════════════
    # 文件4: relations.json
    # 同领域法律之间的横向关联
    # （同领域 + 互相在全文提及对方）
    # ═══════════════════════════════════
    # 构建快速查找：归一化标题 -> 文件路径
    title_to_file = {normalize_title(r["title"]): r["file"] for r in records}
    title_to_domain = {normalize_title(r["title"]): taxonomy_map.get(normalize_title(r["title"]), "其他") for r in records}

    # 每个文件中提及哪些其他法律
    cross_refs = []
    for r in records:
        text = r["title"] + " " + r["_full_text"]
        cited_norms = set()
        for quoted in re.findall(r'《([^》]{4,40})》', text):
            qn = normalize_title(quoted)
            if qn in title_to_file and qn != normalize_title(r["title"]):
                cited_norms.add(qn)
        for qn in cited_norms:
            cross_refs.append({
                "from_title": r["title"],
                "from_category": r["category"],
                "from_file": r["file"],
                "to_title": qn,
                "to_file": title_to_file[qn],
                "from_domain": taxonomy_map.get(normalize_title(r["title"]), "其他"),
                "to_domain": title_to_domain.get(qn, "其他"),
            })

    relations = {
        "meta": {"description": "法律条文中《》引用的交叉引用关系（基于全文前1000字分析）"},
        "cross_references": cross_refs
    }
    (OUT_DIR / "relations.json").write_text(
        json.dumps(relations, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"relations.json: {len(cross_refs)} 条交叉引用")

    # ═══════════════════════════════════
    # 文件5: README.md  总览
    # ═══════════════════════════════════
    domain_summary = "\n".join(
        f"| {d} | {info['count']} | {info['description'][:30]}… |"
        for d, info in taxonomy_output.items()
    )

    top_versions = sorted(versions_output.items(),
                          key=lambda x: -x[1]["version_count"])[:15]
    version_rows = "\n".join(
        f"| {t} | {v['version_count']} | {v['earliest']} | {v['latest']} |"
        for t, v in top_versions
    )

    readme = f"""# 中国法律知识图谱

数据来源：`/laws_data mannual/json/`，共 **{len(index)}** 部法规（宪法 {sum(1 for r in index if r['category']=='宪法')} + 法律 {sum(1 for r in index if r['category']=='法律')} + 行政法规 {sum(1 for r in index if r['category']=='行政法规')} + 监察法规 {sum(1 for r in index if r['category']=='监察法规')} + 司法解释 {sum(1 for r in index if r['category']=='司法解释')}）。

## 文件说明

| 文件 | 内容 |
|------|------|
| `taxonomy.json` | 按 {len(taxonomy_output)} 个法律领域分类，每部法律归入一个主领域 |
| `versions.json` | {len(versions_output)} 部法律存在多个历史版本，记录版本演变时间线 |
| `hierarchy.json` | 法律效力层级（宪法→法律→行政法规→司法解释）及 {len(links)} 条上下位链接 |
| `relations.json` | {len(cross_refs)} 条基于《》引用分析的交叉引用关系 |

## 效力层级体系

```
宪法（最高法）
 └─ 基本法律（全国人大制定：刑法、民法典、诉讼法等）
     └─ 普通法律（全国人大常委会制定）
         └─ 行政法规（国务院：条例、细则、办法）
             └─ 司法解释（最高人民法院 / 最高人民检察院）
```

## 主题领域分布

| 领域 | 法规数 | 涵盖主题 |
|------|--------|---------|
{domain_summary}

## 版本更迭最多的法律（前15）

| 法律名称 | 版本数 | 最早版本 | 最新版本 |
|---------|--------|---------|---------|
{version_rows}

## 使用说明

- **按领域检索**：查 `taxonomy.json`，找到对应领域的 `laws` 列表，再通过 `file` 路径读取源文件
- **查历史版本**：查 `versions.json`，用归一化标题作为 key
- **找上位法**：查 `hierarchy.json` 的 `links`，以 `child` 或 `parent` 过滤
- **找引用关系**：查 `relations.json` 的 `cross_references`，以 `from_title` 或 `to_title` 过滤
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")
    print("README.md 已生成")
    print(f"\n全部输出在: {OUT_DIR}")


if __name__ == "__main__":
    main()
