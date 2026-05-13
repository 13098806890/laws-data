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
| 法律解释 | 25 |
| 司法解释 | 608 |
| 行政法规 | 607 |
| 监察法规 | 2 |
| 会议纪要等 | 数部 |
| **合计** | **~1945** |

条文总数约 **77,800 条**，法条间引用关系 **6,452 条**（跨法引用 3,555 条，本法自引 2,897 条），解析率 98.8%。

法考模式：数据集包含 **208 部**法律考试（法考）收录法律，标记字段 `is_flk`，并附有按法考科目排列的 `flk_menu.json` 导航索引和 `法考/` Markdown 目录。

本数据集已用于构建 [ChineseLawsSearch](https://github.com/doxie/LawsSearch) iOS 应用。

---

## 📦 数据来源

所有原始文档均来自 **[国家法律法规数据库](https://flk.npc.gov.cn/)**（全国人大常委会法制工作委员会官方发布平台），以 docx / doc 格式下载后经本项目 pipeline 结构化处理。

部分文件因原始 docx 缺失或结构异常，从最高人民法院官网抓取网页文本替换，记录在 `sources/_web_sources/README.md`。

---

## 📁 目录结构

```
laws_data/
├── 📂 sources/                    # 源文件（docx/doc + xlsx 目录索引）
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   ├── 监察法规/
│   └── _web_sources/              # 网页抓取替换文件及 HTML 缓存
├── 📂 json/                       # 结构化 JSON（按 category 分类，pipeline 产物）
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   └── 监察法规/
├── 📂 宪法与国家机构/             # Markdown 全文（按展示分组，is_current=1）
├── 📂 民事与商事/
├── 📂 刑事/
├── 📂 行政与公法/
├── 📂 经济、税务与金融/
├── 📂 劳动与社会保障/
├── 📂 诉讼与司法程序/
├── 📂 法考/                        # Markdown 全文（按法考科目分目录，pipeline 产物）
│   ├── 刑法/
│   ├── 刑事诉讼法/
│   ├── 行政法与行政诉讼法/
│   ├── 民法/
│   ├── 商法/
│   └── 民事诉讼法/
├── 📂 references/
│   └── article_references.json   # 法条间引用关系（pipeline 产物）
├── 📂 scripts/
│   ├── config.py                  # 路径配置（BASE_DIR、DB_PATH 等）
│   ├── utils.py                   # 公共工具（title_from_stem、pub_date_from_stem）
│   ├── law_aliases.py             # 法律别名映射表（民法典→"民法典,民法" 等）
│   ├── pipeline.py                # 完整流程入口（支持阶段跳过参数）
│   ├── generate_law_index.py      # 稳定 law_id 分配
│   ├── extract_references.py      # 法条引用关系提取
│   ├── fetch_web_sources.py       # 网页抓取 → .txt 替换文件
│   ├── verify_db.py               # 数据库与 JSON 一致性验证
│   ├── build_aliases.py           # 构建 term_aliases（LLM + FTS 验证）
│   ├── build_enhancements.py      # 构建 RAG 增强表
│   ├── test_rag.py                # 基础 RAG pipeline
│   ├── legal_chain_agent.py       # 法条链推理 Agent
│   ├── legal_expert_agent.py      # 多层专家协作系统入口
│   ├── agents/                    # 专家协作系统模块
│   ├── docx_to_json/              # 第一阶段：docx/txt → JSON
│   │   ├── converter.py           # 主入口，段落解析，编/章/节/条识别
│   │   ├── structure.py           # 层级结构组装，global_order 分配
│   │   ├── domain.py              # legal_domain 映射，xlsx 索引读取
│   │   ├── effective_date.py      # 生效日期提取
│   │   └── subject_area.py        # 行政法规二级主题分类
│   ├── json_to_db/                # 第二阶段：JSON → SQLite
│   │   ├── builder.py             # 建表、写入法律/节点/FTS/引用关系
│   │   ├── export_menu.py         # 导出 law_menu.json 导航索引
│   │   └── export_flk_menu.py     # 导出 flk_menu.json 法考导航索引
│   └── db_to_md/                  # 第三阶段：DB → Markdown
│       ├── renderer.py            # 按 legal_domain 分目录渲染全量 Markdown
│       └── render_flk.py          # 按法考科目渲染 法考/ 目录
├── 📄 law_index.json              # 稳定 law_id 索引（跨重建不变）
├── 📄 law_menu.json               # 侧边栏导航索引（按展示分组）
├── 📄 flk_menu.json               # 法考导航索引（208部，按6个科目排列）
├── 📄 法考目录.json               # 法考收录法律名单（来源：官方法考大纲）
├── 🗄️  law_content.db             # 主数据库（~135MB，Git LFS）
└── 🗄️  law_enhancements.db        # RAG 增强数据库（~64KB，Git LFS）
```

---

## 🔄 Pipeline 详解

运行入口：`python3 scripts/pipeline.py`

Pipeline 分五个阶段顺序执行，每个阶段可通过参数单独跳过。

### 阶段一：`docx_to_json` — 源文件 → 结构化 JSON

**输入**：`sources/` 目录下的 `.docx` / `.doc` / `.txt` 文件（`.txt` 优先于同名 `.docx`，用于替换有缺陷的原文件）

**输出**：`json/` 目录下的 `.json` 文件，每部法律一个文件

**具体步骤**：

1. **xlsx 索引预读**（`domain.py`）：每个源目录下有 `法律法规文件目录_*.xlsx`，4 列（标题 | 公布日期 | 施行日期 | 分类）。预读后建立 `{标题}_{YYYYMMDD}` → `{effective_date, category}` 索引，作为权威来源覆盖从正文提取的结果。

2. **段落提取**（`converter.py`）：逐段读取 docx 段落文本，`.txt` 文件则按行读取。去除页眉页脚噪声，识别发布机关（白名单精确匹配 12 个机构）和发文字号（正则匹配 `机构缩写〔年份〕序号` 格式）。

3. **生效日期提取**（`effective_date.py`）：从发布说明段落（含"自…起施行"）中提取生效日期，xlsx 有记录时用 xlsx 值覆盖。

4. **编/章/节/条识别**（`converter.py` 主循环）：
   - `第X编` → part 节点
   - `第X章` 或 `一、管辖`（汉字序号，司法解释常见） → chapter 节点
   - `第X节` → section 节点
   - `第X条` → article 节点；支持多条合并段落的拆分（`_INLINE_ART_RE`）
   - 无章节结构的短文件（法律解释、批复等）→ 整体 full_text 写为单条 article

5. **结构组装**（`structure.py`）：按 part/chapter/section/article 层级组装嵌套 dict，分配 `global_order`（深度优先遍历序号），保证 `ORDER BY global_order` 还原原文顺序。同名章节去重（bare-TOC 法律会先出现目录标题、再出现正文标题，去重保留后者）。

6. **元数据写入**：`title`（从文件名提取，不从 docx 正文读）、`category`（xlsx 权威）、`legal_domain`（优先从 `/Users/doxie/Github/Laws/` 目录结构匹配，其次手工补充，再次关键词规则）、`subject_area`（行政法规二级主题）。

**特殊处理**：
- 民法典有 7 编，第一编"总则"在源文件 full_text 中无编标题行，硬编码补全
- 刑法修正案用"一、二、三、"编号，不是"第X条"，整体按章节处理
- 刑诉法等有编（part）结构的法律，编下直属条文（无章层级）通过 `_DIRECT_` 占位章节处理
- 九民纪要等用 `1.【标题】正文` 格式的文件，由 `fetch_web_sources.py` 预处理转换为 `第N条　【标题】正文`

---

### 阶段二：`generate_law_index` — 分配稳定 law_id

**输入**：`json/` 目录下的所有 `.json` 文件

**输出**：`scripts/law_index.json`（持久化索引，跨 pipeline 重建保持 ID 稳定）

每部法律用 `{title}_{pub_date}` 作为唯一键，第一次见到时分配一个永久 ID（从 1000001 起自增）。后续重建 pipeline 时已有的法律保持原 ID，新增法律追加新 ID。这保证了 `article_references` 等跨库引用不因重建而失效。

---

### 阶段三：`json_to_db` — JSON → SQLite 数据库

**输入**：`json/` 目录下的所有 `.json` 文件，`law_index.json`

**输出**：`law_content.db`（每次全量重建，删旧建新）

**具体步骤**：

1. **建表**（`builder.py`）：创建 `laws`、`nodes`、`nodes_fts`（trigram FTS5）、`nodes_fts_bigram`（unicode61 FTS5）、`article_references` 表及索引。`nodes_fts` / `nodes_fts_bigram` 均为**外部内容表**（`content="nodes"`），不复制原文，节省约 175MB 空间。

2. **写入 laws 表**：从 JSON 读取元数据，查 `law_index.json` 拿稳定 ID，查 `law_aliases.py` 拿别名（如 `民法典,民法`）。`full_text` 做清洗（合并连续空行、去行首尾空格）。

3. **写入 nodes 表**（递归插入）：
   - `parts` → `chapters` → `sections` → `articles` 递归插入，每层记录 `parent_id`、`global_order`、`part_num`、`chapter_num`、`section_num`、`article_num`
   - `_DIRECT_` 占位章节直接将条文挂到编节点下，不创建多余的章节行
   - 每条 article 同时插入 `nodes_fts` 和 `nodes_fts_bigram`

4. **多版本标记**：同名法律按 `pub_date` 降序，最新版设 `is_current=1`，其余设 `0`。

5. **FTS 优化**：全部插入完成后执行 `INSERT INTO nodes_fts(nodes_fts) VALUES('optimize')`，合并 FTS 段，提升查询性能。

6. **导出导航菜单**（`export_menu.py`）：从 DB 生成 `law_menu.json`，供 iOS app 侧边栏使用，按展示分组（宪法与国家机构 / 民事与商事 / 刑事 / …）组织。

7. **法考标记**：读取 `法考目录.json`，将匹配的法律（标题精确匹配或去书名号后匹配）的 `is_flk` 字段设为 1。共标记 269 条记录（含历史版本）。

8. **导出法考导航菜单**（`export_flk_menu.py`）：从 `is_current=1` 且 `is_flk=1` 的法律中，按 `法考目录.json` 顺序生成 `flk_menu.json`，6 个科目，共 208 部法律。

---

### 阶段四：`extract_references` + `load_references` — 法条引用关系

**输入**：`law_content.db`（nodes 表中的 article 条文正文）

**输出**：`references/article_references.json`，并写入 `law_content.db` 的 `article_references` 表

**提取逻辑**（`extract_references.py`）：

遍历所有 `is_current=1` 的条文，对每条正文用正则识别三类引用：

1. **有书名号跨法引用**：匹配 `《法律名》第X条` 和 `〈法律名〉第X条`（两种书名号均支持）。提取法律名后查 `art_index` 解析到具体节点。短标题（去掉"中华人民共和国"前缀）和全称均可匹配。

2. **无书名号短标题引用**：如 `刑法第X条`、`合同法第X条`，动态构建短标题正则（所有无歧义短标题，按长度降序优先匹配）。

3. **本法自引**：匹配 `本法/本条例/本规定/本办法/本规则第X条`。刑法修正案特殊处理——其条文中的"本法第X条"实际指刑法主体，自动重定向到 `中华人民共和国刑法` 并标记为 `cross_law`。

解析结果写入 JSON 和数据库，包含 `from_node_id`、`to_node_id`（已解析时）、`ref_type`、`resolved`、`raw_text` 等字段。

**当前统计**：6,452 条引用，解析率 98.8%，剩余 78 条因目标法律未收录而无法解析。

---

### 阶段五：`db_to_md` — 数据库 → Markdown 全文

**输入**：`law_content.db`（`is_current=1` 的法律）

**输出**：
- 按 `legal_domain` 分目录的 `.md` 文件（全量），每部法律一个文件
- `法考/` 目录：按法考科目（刑法 / 刑事诉讼法 / 行政法与行政诉讼法 / 民法 / 商法 / 民事诉讼法）分子目录，共 208 个文件（`render_flk.py`）

每条条文生成 `<a id="art-N">` 锚点，正文中识别到的出向引用自动转为跨文件 Markdown 链接，被引用条文末尾附有入向标注上标（`[1]` `[2]` …，悬停显示来源）。

---

### 支持的参数

```bash
python3 scripts/pipeline.py              # 完整五阶段运行
python3 scripts/pipeline.py --skip-docx  # 跳过阶段一（JSON 已有时）
python3 scripts/pipeline.py --skip-docx --skip-index  # 跳过阶段一二
python3 scripts/pipeline.py --skip-docx --skip-db     # 只重建 Markdown
python3 scripts/pipeline.py --skip-docx --skip-md     # 不重建 Markdown
```

单阶段单独运行：

```bash
cd scripts
python3 -m docx_to_json.converter   # 阶段一
python3 generate_law_index.py        # 阶段二
python3 -m json_to_db.builder        # 阶段三
python3 extract_references.py        # 阶段四（仅生成 JSON）
python3 -m db_to_md.renderer         # 阶段五
python3 fetch_web_sources.py         # 抓取/更新网页替换文件（独立运行）
python3 verify_db.py                 # 验证 DB 与 JSON 一致性（可选）
```

---

## 🗄️ 数据库结构

项目包含两个 SQLite 数据库：

- **`law_content.db`**（~135MB）— 主数据库，由 `pipeline.py` 全量生成
- **`law_enhancements.db`**（~64KB）— RAG 增强数据库，独立维护，无需重跑完整 pipeline

### `law_content.db` 表结构

#### 🟠 `laws` 表 — 每部法律一行

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 稳定主键，由 `generate_law_index.py` 分配，跨重建不变 |
| `title` | TEXT | 完整标题，从文件名提取（不从 docx 正文读） |
| `filename` | TEXT UNIQUE | 格式：`{标题}_{YYYYMMDD}`，无后缀 |
| `category` | TEXT | `法律` / `行政法规` / `司法解释` / `修正案` / `法律解释` / `宪法` / `监察法规` |
| `legal_domain` | TEXT | 法律部门：`民法典` / `民法商法` / `刑法` / `行政法` / `经济法` / `社会法` / `宪法相关法` / `诉讼与非诉讼程序法` |
| `subject_area` | TEXT | 行政法规二级主题（交通运输 / 税务财政 …），其他类别为空 |
| `pub_date` | TEXT | 公布日期 `YYYY-MM-DD` |
| `effective_date` | TEXT | 生效日期，xlsx 权威来源优先 |
| `promulgation_info` | TEXT | 发布说明全文（通过/公布/施行信息段落） |
| `issuing_org` | TEXT | 发布机关（白名单精确匹配：最高人民法院 / 最高人民检察院 / 国务院 / 全国人大常委会等） |
| `doc_number` | TEXT | 发文字号（法释〔2000〕29号 等），全国人大通过的法律通常为空 |
| `total_articles` | INTEGER | 条文总数 |
| `full_text` | TEXT | 法律全文原文 |
| `version_date` | TEXT | 同 `pub_date`，用于多版本区分 |
| `is_current` | INTEGER | **1 = 现行版本**，0 = 历史版本 |
| `aliases` | TEXT | 逗号分隔的别名（如 `民法典,民法`），用于搜索时别名匹配 |
| `is_flk` | INTEGER | **1 = 法考收录**，0 = 非法考。由 `法考目录.json` 标注，含历史版本 |

```sql
-- 按别名搜索
SELECT * FROM laws WHERE is_current=1 AND (title LIKE '%民法%' OR aliases LIKE '%民法%');

-- 查某机构司法解释
SELECT title, doc_number, pub_date FROM laws
WHERE issuing_org = '最高人民法院' AND category = '司法解释'
ORDER BY pub_date DESC;

-- 查法考收录的现行法律
SELECT title, category FROM laws WHERE is_flk=1 AND is_current=1 ORDER BY title;
```

#### 🔵 `nodes` 表 — 编 / 章 / 节 / 条统一存储

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `law_id` | INTEGER FK | 关联 `laws.id` |
| `parent_id` | INTEGER FK | 父节点 id，编（part）的 parent_id 为 NULL |
| `type` | TEXT | `part`（编）/ `chapter`（章）/ `section`（节）/ `article`（条） |
| `title` | TEXT | 编/章/节 的标题文本；条文此字段同 `article_number` |
| `article_number` | TEXT | 条文编号，如 `第一条`；非条文节点为 NULL |
| `content` | TEXT | 展示内容：编/章/节 存标题文本，条文存正文 |
| `order_index` | INTEGER | 在父节点内的排序序号 |
| `global_order` | INTEGER | 全文深度优先遍历序号，`ORDER BY global_order` 得正确展示顺序 |
| `part_num` | INTEGER | 所在编的序号（无编结构为 NULL） |
| `chapter_num` | INTEGER | 所在章的序号 |
| `section_num` | INTEGER | 所在节的序号（无节结构为 NULL） |
| `article_num` | INTEGER | 条文整数序号（第十二条 → 12），便于数值范围查询 |

设计说明：
- 编（part）结构只在 8 部法律中存在（民法典、刑法×2、刑事诉讼法×2、民事诉讼法×3）
- 115 个司法解释用汉字序号章节（`一、管辖`），仍映射为 `chapter` 类型
- 无章节的短文件整体写为单条 `article`

```sql
-- 按顺序展示某法律全文
SELECT type, title, content FROM nodes WHERE law_id = ? ORDER BY global_order;

-- 按条文序号范围查询
SELECT article_number, content FROM nodes
WHERE law_id = ? AND type = 'article' AND article_num BETWEEN 10 AND 20;
```

#### 🟢 `nodes_fts` — 全文搜索（≥3 字）

FTS5 外部内容表（`content="nodes"`），不复制原文。分词器：`trigram`，支持任意中文子串精确匹配，最少 3 个字符。

```sql
SELECT n.article_number, n.content, l.title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article';
```

#### 🔵 `nodes_fts_bigram` — 短词搜索（1-2 字）

FTS5 外部内容表，分词器：`unicode61`，专门处理 1-2 字搜索（`婚`、`婚姻`）。3 字及以上请用 `nodes_fts`。

#### 🔴 `article_references` — 法条引用关系

| 字段 | 类型 | 说明 |
|------|------|------|
| `from_node_id` | INTEGER FK | 引用方节点 |
| `from_law_id` | INTEGER FK | 引用方法律 |
| `from_article_num` | INTEGER | 引用方条文序号 |
| `to_node_id` | INTEGER FK | 被引用方节点（已解析时） |
| `to_law_id` | INTEGER FK | 被引用方法律 |
| `to_article_num` | INTEGER | 被引用方条文序号 |
| `ref_type` | TEXT | `cross_law`（跨法）/ `self_ref`（本法自引） |
| `resolved` | INTEGER | 1 = 已解析到具体节点 |
| `raw_text` | TEXT | 原文引用字符串，如 `《中华人民共和国民法典》第一千二百零八条` |

由 `extract_references.py` 从条文正文提取后写入，随 pipeline 自动更新，无需手动维护。

---

### `law_enhancements.db` 表结构

#### `term_aliases` — 日常语言 → 法律术语（134 条）

LLM 生成候选术语，FTS 验证命中数 > 0 后写入。

| 字段 | 说明 |
|------|------|
| `colloquial` | 日常用语，如 `车祸`、`被炒鱿鱼` |
| `legal_term` | 法律条文中实际出现的术语，如 `道路交通事故`、`解除劳动合同` |
| `fts_hits` | 该术语在条文中的命中数 |

#### `alias_patches` — 手工精确补丁（22 条）

补充 LLM 自动生成的缺口（`离婚`、`误工费`、`工伤` 等），与 `term_aliases` 结构相同。

#### `topic_law_hints` — 场景关键词 → 推荐法律（50 条）

将问题场景映射到最相关法律，RAG 检索时优先在这些法律内搜索。

#### `keyword_synonyms` — LLM 关键词 → 精确 FTS 词（40 条）

LLM 造出的词（`超速驾驶`）映射到实际有命中的术语（`违法驾驶`）。

重建增强数据库：

```bash
python3 scripts/build_aliases.py        # 重建 term_aliases（需 Ollama，约 5 分钟）
python3 scripts/build_enhancements.py   # 重建其余三张表（纯静态，< 1 秒）
```

---

## 📋 JSON 数据格式

每个文件对应一部法律，文件名：`{标题}_{公布日期YYYYMMDD}.json`。

**无编结构（大多数法律）：**

```json
{
  "law_id": 1100023,
  "title": "中华人民共和国合同法",
  "category": "法律",
  "legal_domain": "民法商法",
  "pub_date": "1999-03-15",
  "effective_date": "1999-10-01",
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

**有编结构（民法典、刑法、诉讼法等 8 部）：**

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

## 🤖 法律咨询 Agent

项目提供三个递进层次的法律问答脚本，均支持 DeepSeek / Groq / Ollama 等多种 provider。

### `test_rag.py` — 基础 RAG Pipeline

关键词检索 + LLM 过滤，步骤：分类路由 → 关键词提取+别名扩展 → FTS 检索 → 相关性过滤 → 生成回答。

### `legal_chain_agent.py` — 法条链推理 Agent

引入章节定位与引用链扩展：问题拆分 → 大类路由 → 章节导航抓取条文 → FTS 补充 → 引用链扩展（自动追加被引条文）→ 过滤排序 → 生成结论。

```bash
python3 scripts/legal_chain_agent.py -q "网购假货怎么维权"
python3 scripts/legal_chain_agent.py -q "..." --provider deepseek
```

### `legal_expert_agent.py` — 多层专家协作系统

三层专家架构（协调员 → 6 个专家组 → 17 个细分专家），支持信息收集（自动提取已知事实，缺失时一次性批量询问）。

```bash
python3 scripts/legal_expert_agent.py -q "公司非法裁员我怎么办"
python3 scripts/legal_expert_agent.py -q "..." --no-interactive  # 跳过信息收集
```

**依赖**：`pip install requests`（在线 provider）；本地 Ollama 需 `ollama pull qwen2.5:3b`。

---

## 🚀 快速开始

```bash
pip install python-docx xlrd

# 完整 pipeline（约 5-10 分钟）
cd /path/to/laws_data
python3 scripts/pipeline.py

# 已有 JSON，只重建数据库（约 1-2 分钟）
python3 scripts/pipeline.py --skip-docx

# 验证数据库完整性（可选）
python3 scripts/verify_db.py
```

更新源文件后直接重跑 `pipeline.py` 即可，pipeline 无状态，每次全量重建。

---

## ⚠️ 已知限制

- FTS trigram 最短匹配词为 3 字（1-2 字用 `nodes_fts_bigram`）
- 法条引用关系仅提取现行版本（`is_current=1`）条文
- 78 条引用因目标法律未收录而无法解析（执业医师法、公民出境入境管理法实施细则等未纳入数据集）
- 刑法修正案用"一、二、三、"编号，不构成可引用的"第X条"，无法作为引用目标解析
