# 🏛️ 中国法律法规数据库

[English](README.en.md) · [Русский](README.ru.md)

> 中国现行法律法规的结构化开放数据集 —— 原始文档、结构化 JSON、SQLite 数据库、Markdown 全文，供检索、研究和应用开发使用。

---

## 📊 数据概览

| 类别 | 数量 |
|------|-----:|
| 宪法 | 1 |
| 法律 | 310 |
| 修正案 | 12 |
| 决定 | 2 |
| 法律解释 | 25 |
| 司法解释 | 566 |
| 行政法规 | 607 |
| 监察法规 | 2 |
| **合计** | **1525** |

**展示分组：** 宪法与国家机构 · 民事与商事 · 刑事 · 行政与公法 · 经济、税务与金融 · 劳动与社会保障 · 诉讼与司法程序

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
├── 📂 宪法与国家机构/             # Markdown 全文（按展示分组，is_current=1）
│   ├── 宪法/
│   ├── 法律及决定/
│   ├── 行政法规/
│   └── 司法解释/
├── 📂 民事与商事/
│   ├── 民法典/
│   ├── 合同与债权/
│   ├── 公司与破产/
│   ├── 知识产权/
│   └── ...（共 10 个子分组）
├── 📂 刑事/
│   ├── 刑法及修正案/
│   ├── 法律解释/
│   ├── 财产犯罪/
│   └── ...（共 6 个子分组）
├── 📂 行政与公法/
│   ├── 行政法律/
│   ├── 国家赔偿/
│   └── 行政法规/（按 20 个主题细分）
├── 📂 经济、税务与金融/
├── 📂 劳动与社会保障/
├── 📂 诉讼与司法程序/
├── 📂 references/
│   └── article_references.json   # 法条间引用关系（跨法引用 + 本法自引）
├── 📂 scripts/
│   ├── config.py                  # 路径配置
│   ├── utils.py                   # 公共工具函数
│   ├── generate_law_index.py      # 稳定 law_id 分配
│   ├── extract_references.py      # 引用关系提取
│   ├── pipeline.py                # 完整流程（支持阶段跳过参数）
│   ├── verify_db.py               # 数据库与 JSON 一致性验证
│   ├── build_aliases.py           # 构建日常语言 → 法律术语别名表
│   ├── build_enhancements.py      # 构建 topic hints / keyword synonyms 等增强表
│   ├── test_rag.py                # RAG 法律咨询 pipeline（多步推理）
│   ├── docx_to_json/              # 第一阶段：docx → JSON
│   │   ├── converter.py
│   │   ├── domain.py
│   │   ├── effective_date.py
│   │   └── structure.py
│   ├── json_to_db/                # 第二阶段：JSON → SQLite
│   │   ├── builder.py
│   │   ├── display_group.py       # 展示分组映射表
│   │   └── export_menu.py         # 导出 law_menu.json 导航索引
│   └── db_to_md/                  # 第三阶段：DB → Markdown
│       └── renderer.py
├── 🗄️  law_content.db             # 主数据库（pipeline 产物，~370MB，Git LFS）
└── 🗄️  law_enhancements.db        # 增强数据库（RAG 优化用，独立维护，Git LFS）
```

---

## 🗄️ 数据库结构

项目包含两个 SQLite 数据库：

- **`law_content.db`**（~180MB）— 主数据库，由 `pipeline.py` 生成，包含法律全文、条文结构、FTS 索引、引用关系等。
- **`law_enhancements.db`**（~64KB）— 增强数据库，独立于主库，RAG 检索优化用，可单独重建，无需重跑完整 pipeline。

### `law_enhancements.db` 表结构

#### 🔵 `term_aliases` — 日常语言 → 法律术语（134 条）

由 `build_aliases.py` 自动构建：LLM 对每个日常词生成候选法律术语，再用 FTS 验证命中数 > 0 才写入。

| 字段 | 类型 | 说明 |
|------|------|------|
| `colloquial` | TEXT | 日常用语，如 `车祸`、`被炒鱿鱼` |
| `legal_term` | TEXT | 法律条文中实际出现的术语，如 `道路交通事故`、`解除劳动合同` |
| `fts_hits` | INTEGER | 该术语在 `law_content.db` 条文中的命中数（用于排序） |

```sql
-- 示例：用户说"车祸"，扩展为法律术语
SELECT legal_term, fts_hits FROM term_aliases WHERE colloquial = '车祸' ORDER BY fts_hits DESC;
-- → 道路交通事故 (36)
```

#### 🟡 `alias_patches` — 手工精确补丁（22 条）

LLM 自动生成的 `term_aliases` 存在缺口（如"离婚"、"误工费"、"工伤"等），由此表手工补充，均经 FTS 验证。与 `term_aliases` 结构完全相同，由 `build_enhancements.py` 构建。

```sql
-- 示例：离婚相关法律术语
SELECT legal_term, fts_hits FROM alias_patches WHERE colloquial = '离婚';
-- → 离婚登记 (18), 离婚诉讼 (29), 婚姻自由 (24), 解除婚姻关系 (13)
```

#### 🟠 `topic_law_hints` — 场景关键词 → 推荐法律（50 条）

将问题场景映射到最相关的具体法律，RAG 检索时优先在这些法律内搜索，减少跨领域噪声。

| 字段 | 类型 | 说明 |
|------|------|------|
| `topic_keyword` | TEXT | 场景词，如 `消费者`、`交通事故`、`离婚` |
| `law_title` | TEXT | 法律完整标题，与 `law_content.db` 的 `laws.title` 对应 |
| `priority` | INTEGER | 优先级（越小越靠前），同场景多部法律按此排序 |

```sql
-- 示例：网购假货场景应优先检索哪些法律
SELECT law_title, priority FROM topic_law_hints WHERE topic_keyword IN ('假货', '网购', '退货') ORDER BY priority;
-- → 消费者权益保护法 (1), 电子商务法 (1), 产品质量法 (2)
```

#### 🟢 `keyword_synonyms` — LLM 关键词 → 精确 FTS 词（40 条）

LLM 提取关键词时常造出法条中不存在的词（如"超速驾驶"、"机动车事故"），此表将这类词映射到实际有命中的术语。

| 字段 | 类型 | 说明 |
|------|------|------|
| `source_kw` | TEXT | LLM 可能输出的词，如 `机动车事故`、`合同违约` |
| `target_kw` | TEXT | FTS 有命中的精确术语，如 `交通事故`、`违约责任` |
| `fts_hits` | INTEGER | `target_kw` 在条文中的命中数 |

```sql
-- 示例：LLM 输出"机动车事故"，映射为有命中的词
SELECT target_kw, fts_hits FROM keyword_synonyms WHERE source_kw = '机动车事故';
-- → 交通事故 (276)
```

重建增强数据库（需先启动 Ollama）：

```bash
python3 scripts/build_aliases.py        # 重建 term_aliases（LLM + FTS 验证，约 5 分钟）
python3 scripts/build_enhancements.py   # 重建其余三张表（纯静态，无需 LLM，< 1 秒）
```

### `law_content.db` 表结构

运行 `python3 scripts/pipeline.py` 生成。

---

### 🟠 `laws` 表 — 每部法律一行

每部法律在此表中只有一行（`is_current=1`），同名多版本只保留最新 `pub_date` 的版本。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 稳定主键，由 `generate_law_index.py` 分配，跨 pipeline 重建保持不变 |
| `title` | TEXT | 完整标题，从文件名提取（不从 docx 正文读，因正文标题常截断） |
| `filename` | TEXT UNIQUE | 格式：`{标题}_{YYYYMMDD}`，无后缀 |
| `category` | TEXT | 来源类型：`法律` / `行政法规` / `司法解释` / `修正案` / `法律解释` / `宪法` / `监察法规` |
| `legal_domain` | TEXT | 法律部门：`民法典` / `民法商法` / `刑法` / `行政法` / `经济法` / `社会法` / `宪法相关法` / `诉讼与非诉讼程序法` |
| `subject_area` | TEXT | 行政法规二级主题（交通运输 / 税务财政 …），非行政法规为空 |
| `pub_date` | TEXT | 公布日期 `YYYY-MM-DD` |
| `effective_date` | TEXT | 生效日期 `YYYY-MM-DD`，xlsx 权威来源优先，其次从正文提取 |
| `promulgation_info` | TEXT | 发布说明全文（通过 / 公布 / 施行信息段落） |
| `issuing_org` | TEXT | 发布机关（最高人民法院 / 最高人民检察院 / 国务院 / 全国人大常委会等，白名单匹配） |
| `doc_number` | TEXT | 发文字号（法释〔2000〕29号 等），全国人大通过的法律通常为空 |
| `total_articles` | INTEGER | 条文总数 |
| `full_text` | TEXT | 法律全文原文 |
| `version_date` | TEXT | 同 `pub_date`，用于多版本区分 |
| `is_current` | INTEGER | **1 = 现行版本**，0 = 历史版本 |

常用查询：

```sql
-- 查某机构所有司法解释
SELECT title, doc_number, pub_date FROM laws
WHERE issuing_org = '最高人民法院' AND category = '司法解释'
ORDER BY pub_date DESC;
```

---

### 🔵 `nodes` 表 — 编 / 章 / 节 / 条统一存储

所有层级（编、章、节、条）用同一张表存储，通过 `type` 字段区分，`parent_id` 构成树形结构。`ORDER BY global_order` 即可还原原文顺序。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `law_id` | INTEGER FK | 关联 `laws.id` |
| `parent_id` | INTEGER FK | 父节点 id，编（part）的 parent_id 为 NULL |
| `type` | TEXT | `part`（编）/ `chapter`（章）/ `section`（节）/ `article`（条） |
| `title` | TEXT | 编/章/节 的标题文本；条文此字段同 `article_number` |
| `article_number` | TEXT | 条文编号，如 `第一条`；非条文节点为 NULL |
| `content` | TEXT | 展示内容：编/章/节 存标题文本，条文存正文（含"第X条　"前缀） |
| `order_index` | INTEGER | 在父节点内的排序序号（从 1 开始） |
| `global_order` | INTEGER | 全文深度优先遍历序号，`ORDER BY global_order` 得正确展示顺序 |
| `part_num` | INTEGER | 所在编的序号（无编结构为 NULL） |
| `chapter_num` | INTEGER | 所在章的序号 |
| `section_num` | INTEGER | 所在节的序号（无节结构为 NULL） |
| `article_num` | INTEGER | 条文序号，如第十二条 → `12`，便于数值范围查询 |

设计说明：
- 编（part）结构只在 8 部法律中存在（民法典、刑法×2、刑事诉讼法×2、民事诉讼法×3）
- 115 个司法解释用汉字序号（`一、管辖`）代替第X章，识别后仍映射为 `chapter` 类型
- 无章节的短文件（法律解释、批复等）整体写为单条 `article`

常用查询：

```sql
-- 按顺序展示某法律全文
SELECT type, title, content FROM nodes WHERE law_id = ? ORDER BY global_order;

-- 某章下所有条文
SELECT article_number, content FROM nodes
WHERE parent_id = ? AND type = 'article' ORDER BY order_index;

-- 按条文序号范围查询（如第10-20条）
SELECT article_number, content FROM nodes
WHERE law_id = ? AND type = 'article' AND article_num BETWEEN 10 AND 20;
```

---

### 🟢 `nodes_fts` 虚拟表 — 全文搜索（≥3 字）

FTS5 外部内容表，索引内容存储在 `nodes` 表中，本身只保存倒排索引，**不复制原文**（比独立存储节省 ~60MB）。

| 字段 | 说明 |
|------|------|
| `content` | 条文正文，对应 `nodes.content` |
| `article_number` | 条文编号，对应 `nodes.article_number` |

- 分词器：`trigram`，将文本切成所有连续三字 gram，支持任意中文子串精确匹配
- 最短搜索词：3 个 CJK 字符（1-2 字用 `nodes_fts_bigram`）
- 4 字、5 字、6 字及以上均原生支持，无需额外索引
- `rowid` 与 `nodes.id` 一一对应

```sql
-- 全文搜索，找含"合同解除"的条文
SELECT n.article_number, n.content, l.title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article';
```

---

### 🔵 `nodes_fts_bigram` 虚拟表 — 短词搜索（1-2 字）

FTS5 外部内容表，使用 `unicode61` 分词器，专门处理 trigram 无法覆盖的 1-2 字搜索。与 `nodes_fts` 共享 `nodes` 表的原文，同样不复制内容（节省 ~115MB）。

| 字段 | 说明 |
|------|------|
| `content` | 条文正文，对应 `nodes.content` |
| `article_number` | 条文编号，对应 `nodes.article_number` |

- 分词器：`unicode61`，按 Unicode 字符边界分词，中文单字即为一个 token
- 适用场景：搜索单字（`婚`、`税`）或双字（`婚姻`、`合同`）
- 3 字及以上请用 `nodes_fts`（trigram），不要用此表

```sql
-- 搜索单字或双字（由 RAG pipeline 自动路由）
SELECT COUNT(*) FROM nodes_fts_bigram WHERE nodes_fts_bigram MATCH '婚姻';
```

---

### 🔴 `article_references` 表 — 条文引用关系

| 字段 | 类型 | 说明 |
|------|------|------|
| `from_node_id` | INTEGER FK | 引用方节点（`nodes.id`） |
| `from_law_id` | INTEGER FK | 引用方法律 |
| `from_article_num` | INTEGER | 引用方条文序号 |
| `from_chapter_num` | INTEGER | 引用方所在章序号 |
| `from_section_num` | INTEGER | 引用方所在节序号 |
| `from_part_num` | INTEGER | 引用方所在编序号 |
| `to_node_id` | INTEGER FK | 被引用方节点（已解析时有值） |
| `to_law_id` | INTEGER FK | 被引用方法律 |
| `to_article_num` | INTEGER | 被引用方条文序号 |
| `to_chapter_num` | INTEGER | 被引用方所在章序号 |
| `to_section_num` | INTEGER | 被引用方所在节序号 |
| `to_part_num` | INTEGER | 被引用方所在编序号 |
| `ref_type` | TEXT | `cross_law`（跨法引用）/ `self_ref`（本法自引） |
| `resolved` | INTEGER | 1 = 已解析到具体节点，0 = 未解析 |
| `raw_text` | TEXT | 原文引用字符串，如 `《中华人民共和国民法典》第一千二百零八条` |

同步自 `references/article_references.json`，由 `pipeline.py --only-refs` 单独更新，无需重建整个数据库。

---

## 📋 JSON 数据格式

每个文件对应一部法律，文件名：`{标题}_{公布日期YYYYMMDD}.json`。

**无编结构（大多数法律）：**

```json
{
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

仅覆盖 `is_current=1` 的现行版本，共 **4994 条引用**（跨法 2986 条，本法自引 2008 条），解析率 98.0%。

```json
{
  "from_law":         "人民检察院公益诉讼办案规则",
  "from_article":     "第六十六条",
  "from_article_num": 66,
  "from_chapter_num": 6,
  "from_section_num": 8,
  "from_part_num":    null,
  "refs": [
    {
      "type":           "cross_law",
      "to_law":         "中华人民共和国法官法",
      "to_article":     "第四十六条",
      "to_article_num": 46,
      "resolved":       true,
      "raw_text":       "《中华人民共和国法官法》第四十六条"
    }
  ]
}
```

---

## 📝 Markdown 超链接与引用标注

每个 Markdown 文件中：

- **条文锚点**：每条条文有 `<a id="art-N">` 锚点，可通过 `文件名.md#art-N` 直接定位
- **出向链接**：条文正文中引用其他法律条文的文字自动转为跨文件链接，跳转到目标条文
- **入向标注**：被其他法律引用的条文末尾附有上标 `[1]` `[2]`，鼠标悬停显示「被《法律名》第N条引用」，点击跳转到引用方条文

---

## ⚡ 常用查询

```sql
-- 按顺序展示某法律全部内容
SELECT * FROM nodes WHERE law_id = ? ORDER BY global_order;

-- 全文搜索（任意中文短语，最少3字）
SELECT n.article_number, n.content, l.title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article';

-- 按展示分组浏览
SELECT l.title, l.category, dgm.display_subgroup
FROM laws l
JOIN display_group_map dgm ON l.id = dgm.law_id
WHERE dgm.display_group = '民事与商事' AND l.is_current = 1;

-- 某机构发布的全部司法解释
SELECT title, doc_number, pub_date FROM laws
WHERE issuing_org = '最高人民法院' AND category = '司法解释'
ORDER BY pub_date DESC;
```

---

## 🤖 RAG 法律咨询 Pipeline

`scripts/test_rag.py` 提供一个基于本地 LLM（Ollama）的多步推理法律问答 pipeline：

1. **分类路由** — 将问题映射到相关法律部门，排除明显无关领域
2. **关键词提取** — 抽取适合 FTS 检索的法律术语
3. **别名扩展** — 通过 `law_enhancements.db` 将日常语言转换为法律术语，补充同义词
4. **分层检索** — 先检法律原文，再检司法解释；`topic_law_hints` 命中的法律优先排前，命中词按 FTS 命中数升序排序（精确词优先），确保关键条文不被截断
5. **相关性过滤** — LLM 批量判断，去除因同词共现被误召回的无关条文；`topic_law_hints` 命中的条文跳过此步骤直接保留
6. **参考法条筛选** — LLM 逐条判断每条候选法条是否直接支撑结论，仅保留用户可据此行动的条文，过滤行政监管条文和定义性条款
7. **生成回答** — 模型只输出结论文字；代码自动拼接筛选后的参考法条，避免截断或遗漏

回答格式为 **结论 + 参考法条**，prompt 内置管辖法院、诉讼请求模板、诉讼费用等通用知识。

**依赖：** [Ollama](https://ollama.com/) 本地运行，默认模型 `qwen2.5:3b`

```bash
# 启动 Ollama 后运行示例问题
python3 scripts/test_rag.py

# 在自己的脚本中调用
from scripts.test_rag import ask
result = ask("劳动合同试用期最长可以是多久？")
print(result["answer"])
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
python3 -m json_to_db.display_group  # 更新展示分组映射
python3 -m db_to_md.renderer         # DB → Markdown
python3 extract_references.py        # 提取引用关系

python3 verify_db.py                 # 验证 DB 与 JSON 一致性（可选）
```

更新源文件后直接重跑 `pipeline.py` 即可，无需手动干预。
