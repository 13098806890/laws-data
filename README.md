# 🏛️ 中国法律法规数据库

[English](README.en.md) · [Русский](README.ru.md)

> 中国现行法律法规的结构化开放数据集 —— 原始文档、结构化 JSON、SQLite 数据库、Markdown 全文，供检索、研究和应用开发使用。

---

## 📊 数据概览

| 类别 | 数量 | law_id 段 |
|------|-----:|-----------|
| 🔴 宪法 | 1 | `1000001–1099999` |
| 🟠 法律 | 442 | `1100001–1999999` |
| 🟡 修正案 | 12 | `2000001–2099999` |
| 🟡 决定 | 4 | `2100001–2199999` |
| 🟢 法律解释 | 25 | `3000001–3499999` |
| 🟢 司法解释 | 682 | `3500001–4999999` |
| 🔵 行政法规 | 727 | `5000001–6499999` |
| 🔵 监察法规 | 3 | `6500001–6999999` |
| ⚪ 地方性法规（预留）| — | `7000001–7999999` |
| ⚪ 地方性规章（预留）| — | `8000001–8999999` |
| **合计** | **1896** | |

**覆盖法律部门：** 宪法相关法 · 民法商法 · 民法典 · 行政法 · 经济法 · 社会法 · 刑法 · 诉讼与非诉讼程序法

## 📦 数据来源

所有原始文档均来自 **[国家法律法规数据库](https://flk.npc.gov.cn/)**（全国人民代表大会官方法律检索平台），以 docx / doc 格式下载后经本项目 pipeline 结构化处理。该平台由全国人大常委会法制工作委员会维护，是中国法律法规的权威发布渠道，收录宪法、法律、行政法规、司法解释等全类别现行有效文本。

---

## 📁 目录结构

```
laws_data/
├── 📂 sources/                    # 源文件（docx/doc + xlsx 目录索引）
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   └── 监察法规/
├── 📂 json/                       # 结构化 JSON（按 category 分类，pipeline 产物）
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   └── 监察法规/
├── 📂 markdown/                   # Markdown 全文（按 legal_domain 分类，从 DB 生成）
│   ├── 民法商法/
│   │   └── 司法解释/
│   ├── 刑法/
│   │   ├── 司法解释/
│   │   └── 法律解释/
│   └── ...
├── 📂 references/
│   └── article_references.json   # 法条间引用关系（跨法引用 + 本法自引）
├── 📂 scripts/
│   ├── config.py                  # 路径配置
│   ├── utils.py                   # 公共工具函数
│   ├── generate_law_index.py      # 稳定 law_id 分配
│   ├── extract_references.py      # 引用关系提取
│   ├── pipeline.py                # 完整流程（支持阶段跳过参数）
│   ├── verify_db.py               # 数据库与 JSON 一致性验证
│   ├── docx_to_json/              # 第一阶段：docx → JSON
│   │   ├── converter.py
│   │   ├── domain.py
│   │   ├── effective_date.py
│   │   └── structure.py
│   ├── json_to_db/                # 第二阶段：JSON → SQLite
│   │   └── builder.py
│   └── db_to_md/                  # 第三阶段：DB → Markdown
│       └── renderer.py
├── 📄 law_index.json              # 全局法律 ID 索引（1896 条）
└── 🗄️  law_content.db             # SQLite 数据库（pipeline 产物，约 100MB）
```

---

## 🗄️ 数据库结构

运行 `python3 scripts/pipeline.py` 生成 `law_content.db`。

### 🟠 `laws` 表 — 每部法律一行

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 等于 `law_id`，与 JSON 文件保持一致 |
| `title` | TEXT | 完整标题 |
| `filename` | TEXT UNIQUE | 格式：`{标题}_{YYYYMMDD}` |
| `category` | TEXT | 法律分类（法律 / 行政法规 / 司法解释 …） |
| `legal_domain` | TEXT | 法律部门（民法商法 / 刑法 / 行政法 …） |
| `pub_date` | TEXT | 公布日期 `YYYY-MM-DD` |
| `effective_date` | TEXT | 生效日期 `YYYY-MM-DD` |
| `promulgation_info` | TEXT | 发布说明全文（通过/公布/施行信息） |
| `issuing_org` | TEXT | 发布机关（最高人民法院 / 国务院 …） |
| `doc_number` | TEXT | 发文字号（如 法释〔2000〕29号） |
| `total_articles` | INTEGER | 条文总数 |
| `full_text` | TEXT | 法律全文（清理多余空格换行后存储） |
| `version_date` | TEXT | 同 `pub_date`，用于多版本区分 |
| `is_current` | INTEGER | **1 = 现行版本，0 = 历史版本**（同名多版取最新） |

---

### 🔵 `nodes` 表 — 编 / 章 / 节 / 条统一存储

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `law_id` | INTEGER FK | 关联 `laws.id` |
| `parent_id` | INTEGER FK | 父节点（编的 parent 为 NULL） |
| `type` | TEXT | `part` / `chapter` / `section` / `article` |
| `title` | TEXT | 编/章/节标题；条文同 `article_number` |
| `article_number` | TEXT | 条文编号，如 `第一条`（非条文为 NULL） |
| `content` | TEXT | 展示文本（编/章/节为标题文本，条文为正文） |
| `order_index` | INTEGER | 在父节点内的序号 |
| `global_order` | INTEGER | 全文深度优先序号，`ORDER BY global_order` 得正文顺序 |
| `part_num` | INTEGER | 所在编序号（无编结构为 NULL） |
| `chapter_num` | INTEGER | 所在章序号 |
| `section_num` | INTEGER | 所在节序号（无节结构为 NULL） |
| `article_num` | INTEGER | 条文序号（第十二条 → `12`） |

> **定位示例：** `WHERE law_id=1100001 AND chapter_num=3 AND article_num=15` 直接定位到具体条文。

---

### 🟢 `nodes_fts` 虚拟表 — 全文搜索

| 字段 | 说明 |
|------|------|
| `content` | 条文正文（同 `nodes.content`） |
| `article_number` | 条文编号 |

- 引擎：FTS5，`tokenize='trigram'`
- 支持任意中文子串搜索（最短 3 个字符）
- `rowid` 与 `nodes.id` 对应

---

### 🔴 `article_references` 表 — 条文引用关系（空壳，待填充）

| 字段 | 类型 | 说明 |
|------|------|------|
| `from_id` | INTEGER FK | 引用方节点 `nodes.id` |
| `to_id` | INTEGER FK | 被引用方节点 `nodes.id` |

> 当前引用关系以 JSON 形式存储在 `references/article_references.json`，格式见下文。

---

## 📎 law_index.json — 全局法律 ID 索引

每部法律一条记录，稳定不变（新增法律追加，已有 ID 永久固定）：

```json
{
  "law_id":        1100001,
  "filename":      "中华人民共和国合同法_19990315",
  "title":         "中华人民共和国合同法",
  "category":      "法律",
  "legal_domain":  "民法商法",
  "pub_date":      "1999-03-15",
  "effective_date":"1999-10-01"
}
```

---

## 📋 JSON 数据格式

每个文件对应一部法律，文件名：`{标题}_{公布日期YYYYMMDD}.json`。

**无编结构（大多数法律）：**

```json
{
  "law_id": 1100001,
  "title": "中华人民共和国合同法",
  "category": "法律",
  "pub_date": "1999-03-15",
  "effective_date": "1999-10-01",
  "legal_domain": "民法商法",
  "total_articles": 428,
  "chapters": [
    {
      "title": "第一章　一般规定",
      "order_index": 1,
      "global_order": 1,
      "sections": [],
      "articles": [
        {
          "title": "第一条　",
          "content": "第一条　为了保护合同当事人的合法权益...",
          "order_index": 1,
          "global_order": 2
        }
      ]
    }
  ]
}
```

**有编结构（民法典、刑法、民事诉讼法等 8 部）：**

```json
{
  "law_id": 1100313,
  "title": "中华人民共和国民法典",
  "parts": [
    {
      "title": "第一编　总则",
      "order_index": 1,
      "global_order": 1,
      "chapters": [ "..." ]
    }
  ]
}
```

---

## 🔗 article_references.json — 法条引用关系

仅覆盖 `is_current=1` 的现行版本，共 **2784 条引用**（跨法 817 条，本法自引 1967 条），解析率 94.7%。

```json
{
  "from_law_id":      3500601,
  "from_law":         "人民检察院公益诉讼办案规则",
  "from_article":     "第六十六条",
  "from_article_num": 66,
  "from_chapter_num": 6,
  "from_section_num": 8,
  "from_part_num":    null,
  "refs": [
    {
      "type":           "cross_law",
      "to_law_id":      1100296,
      "to_law":         "中华人民共和国法官法",
      "to_article":     "第四十六条",
      "to_article_num": 46,
      "to_chapter_num": 4,
      "to_section_num": null,
      "to_part_num":    null,
      "resolved":       true,
      "raw_text":       "《中华人民共和国法官法》第四十六条"
    }
  ]
}
```

---

## ⚡ 常用查询

```sql
-- 按顺序展示某法律全部内容
SELECT * FROM nodes WHERE law_id = 1100001 ORDER BY global_order;

-- 精确定位：民法典第三编第五章第十二条
SELECT * FROM nodes
WHERE law_id = 1100313 AND part_num = 3 AND chapter_num = 5 AND article_num = 12;

-- 全文搜索（任意中文短语，最少3字）
SELECT n.article_number, n.content, l.title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article';

-- 只查现行版本
SELECT * FROM laws WHERE legal_domain = '民法商法' AND is_current = 1;

-- 某机构发布的全部司法解释
SELECT title, doc_number, pub_date FROM laws
WHERE issuing_org = '最高人民法院' AND category = '司法解释'
ORDER BY pub_date DESC;

-- 查某法律的所有历史版本
SELECT title, pub_date, is_current FROM laws
WHERE title = '中华人民共和国公司法' ORDER BY pub_date;
```

---

## 🚀 重新生成

```bash
pip install python-docx xlrd

# 完整流程
python3 scripts/pipeline.py

# 跳过某阶段（已有 JSON 时跳过 docx 解析，节省时间）
python3 scripts/pipeline.py --skip-docx
python3 scripts/pipeline.py --skip-docx --skip-index
python3 scripts/pipeline.py --skip-docx --skip-md

# 只重新生成引用关系
python3 scripts/pipeline.py --only-refs

# 各阶段单独运行
cd scripts
python3 -m docx_to_json.converter   # docx → JSON
python3 generate_law_index.py        # 分配/更新 law_id
python3 -m json_to_db.builder        # JSON → DB
python3 -m db_to_md.renderer         # DB → Markdown
python3 extract_references.py        # 提取引用关系

python3 verify_db.py                 # 验证 DB 与 JSON 一致性（可选）
```

更新源文件后直接重跑 `pipeline.py` 即可，无需手动干预。
