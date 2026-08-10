# 🏛️ 中国法律法规数据库

[English](README.en.md) · [Русский](README.ru.md) · [LICENSE](LICENSE)

> 中国现行法律法规的结构化开放数据集 —— 原始文档、结构化 JSON、SQLite 数据库、Markdown 全文，供检索、研究和应用开发使用。

**开源协议**：[MIT](LICENSE)。法律文本源于官方公开渠道（不受著作权保护），结构化数据与翻译同样以 MIT 开放，商用、二次分发、修改均无限制。

**开始使用**：下载预构建数据库或自行构建，见下方[快速开始](#-快速开始)。

---

## 📊 数据概览

| 类别 | 数量 |
|------|-----:|
| 宪法 | 1 |
| 法律 | 448 |
| 修正案 | 12 |
| 法律解释 | 25 |
| 司法解释 | 1,157 |
| 行政法规 | 727 |
| 监察法规 | 3 |
| 有关法律问题和重大问题的决定（部分） | 4 |
| **合计** | **2,377** |

其中现行（`is_current=1`）1,735 部。条文总数 **78,788 条**（article 节点，含章节等全部节点 87,810 个），法条间引用关系 **5,319 条**（跨法引用 2,559 条，本法自引 2,760 条），解析率 98.4%。

### 🌐 英文翻译

| 指标 | 进度 |
|------|-----:|
| 条文英译（现行法律） | **60,744/60,745（99.99%）** |
| 法律标题英译 | 2,097 部 |
| 中文全文检索 | `nodes_fts`（trigram，≥3 字）+ `nodes_fts_bigram`（unicode61，1–2 字） |
| 覆盖法律 | 2,377 部（含公报来源） |

翻译通过 `translate_to_en.py` 两阶段管线完成：先批量翻译标题，再带术语表和法律名称上下文逐条翻译条文。术语一致性通过 39 个细分专家的 `nameEn`、6 个专家组 `nameEn`、101 个 `RequiredInfo.fieldEn` 保障。

### 📖 最高人民法院公报

额外收录最高人民法院公报（gongbao.court.gov.cn）全量数据：

| 类型 | 数量 |
|------|-----:|
| 指导案例 | 986 篇 |
| 司法文件 | 860 篇 |
| 裁判文书 | 443 篇 |
| 公报司法解释 | 839 部（已合并进主库 `laws`/`nodes` 表） |

所有公报文书均已建立与主库法条的引用关联（3,529 条）。

本数据集已用于构建 [ChineseLawsSearch](https://github.com/doxie/LawsSearch) iOS 应用。

---

## 📦 数据来源

**主库**：所有原始文档均来自 **[国家法律法规数据库](https://flk.npc.gov.cn/)**（全国人大常委会法制工作委员会官方发布平台），以 docx / doc 格式下载后经本项目 pipeline 结构化处理。

部分文件因原始 docx 缺失或结构异常，从最高人民法院官网抓取网页文本替换，详见 `sources/_web_sources/README.md`。

**最高人民法院公报**：通过 `scripts/fetch_gongbao.py` 从 [gongbao.court.gov.cn](https://gongbao.court.gov.cn) 抓取，存入 `最高人民法院公报/` 目录（JSON 格式）。

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
├── 📂 json_en/                    # 英文翻译（镜像 json/ 结构）
├── 📂 json_en_gongbao/            # 公报文书英文翻译（al/cpwsxd/sfwj）
├── 📂 宪法与国家机构/             # Markdown 全文（按 subject_area 菜单分组，is_current=1）
├── 📂 民事与商事/
├── 📂 刑事/
├── 📂 行政与公法/
├── 📂 经济、税务与金融/
├── 📂 劳动与社会保障/
├── 📂 诉讼与司法程序/
├── 📂 其他/
├── 📂 references/
│   ├── article_references.json    # 法条间引用关系（pipeline 产物）
│   ├── law_title_en_map.json      # 法律标题英译 map
│   └── heading_en_map.json        # 结构节点英文标题 map
├── 📂 最高人民法院公报/            # 公报全量数据（fetch_gongbao.py 抓取，JSON 格式）
│   ├── 指导案例/                  # 986 篇（al）
│   ├── 司法文件/                  # 860 篇（sfwj）
│   ├── 裁判文书/                  # 443 篇（cpwsxd）
│   └── 司法解释/                  # 839 部（已合并进主库 laws/nodes）
├── 📂 knowledge/                  # 知识图谱 JSON（taxonomy/hierarchy/relations/versions）
├── 📂 docs/                       # 文档（archive/ 历史记录、translation/ 翻译报告、guides/ 指南）
├── 📂 scripts/
│   ├── config.py                  # 路径配置（BASE_DIR、DB_PATH 等；LAWS_REPO_PATH 环境变量可覆盖）
│   ├── utils.py                   # 公共工具（title_from_stem、pub_date_from_stem）
│   ├── law_id_registry.py         # law_id 单一权威注册表
│   ├── pipeline.py                # 主 pipeline 入口（七阶段，含公报导入、英文导入、验证）
│   ├── download_db.py             # 从 GitHub Releases 下载预构建数据库
│   ├── fetch_gongbao.py           # 最高人民法院公报抓取脚本（5 个目标）
│   ├── build_gongbao_db.py        # 公报数据 → law_content.db（阶段七）
│   ├── classify_gongbao_domain.py # 公报司法解释 legal_domain 打标
│   ├── import_en.py               # json_en → nodes.content_en / laws.title_en
│   ├── translate_to_en.py         # 英文翻译主脚本（按 tier 分批）
│   ├── generate_law_index.py      # 稳定 law_id 分配
│   ├── extract_references.py      # 法条引用关系提取
│   ├── fetch_web_sources.py       # 网页抓取 → .txt 替换文件
│   ├── verify_db.py               # 数据库与 JSON 一致性验证（含 EN 覆盖率）
│   ├── build_aliases.py           # 构建 term_aliases（LLM + FTS 验证）
│   ├── build_enhancements.py      # 构建 RAG 增强表
│   ├── test_rag.py                # 基础 RAG pipeline
│   ├── legal_chain_agent.py       # 法条链推理 Agent
│   ├── legal_expert_agent.py      # 多层专家协作系统入口
│   ├── agents/                    # 专家协作系统模块
│   ├── docx_to_json/              # 阶段一：docx/txt → JSON
│   │   ├── converter.py           # 主入口，段落解析，编/章/节/条识别
│   │   ├── structure.py           # 层级结构组装，global_order 分配
│   │   ├── domain.py              # legal_domain 映射（评分制），xlsx 索引读取
│   │   ├── effective_date.py      # 生效日期提取
│   │   └── subject_area.py        # 行政法规二级主题分类
│   ├── json_to_db/                # 阶段三：JSON → SQLite
│   │   ├── builder.py             # 建表、写入法律/节点/FTS
│   │   └── export_menu.py         # 导出 law_menu.json 导航索引
│   └── db_to_md/                  # 阶段六：DB → Markdown
│       └── renderer.py            # 按菜单分组渲染全量 Markdown
├── 📄 law_index.json              # 稳定 law_id 索引（跨重建不变）
├── 📄 law_menu.json               # 侧边栏导航索引（按 subject_area 分组）
├── 🗄️  law_content.db             # 主数据库（~460MB，不提交 git，从 Releases 下载或本地构建）
├── 🗄️  law_enhancements.db        # RAG 增强数据库（~128KB）
├── 📄 LICENSE                     # MIT 开源协议
├── 📄 CONTRIBUTING.md             # 贡献指南
└── 📄 CLAUDE.md                   # 项目维护说明
```

---

## 🔄 主 Pipeline 详解

**运行入口**：`python3 scripts/pipeline.py`

主 pipeline 分七个阶段顺序执行，全量重建（无增量），每次运行约 5–10 分钟。

### 阶段一：`docx_to_json` — 源文件 → 结构化 JSON

**输入**：`sources/` 目录下的 `.docx` / `.doc` / `.txt` 文件（`.txt` 优先于同名 `.docx`，用于替换有缺陷的原文件）

**输出**：`json/` 目录下的 `.json` 文件，每部法律一个文件

**具体步骤**：

1. **xlsx 索引预读**（`domain.py`）：每个源目录下有 `法律法规文件目录_*.xlsx`，4 列（标题 | 公布日期 | 施行日期 | 分类）。预读后建立 `{标题}_{YYYYMMDD}` → `{effective_date, category}` 索引，作为权威来源覆盖从正文提取的结果。

2. **段落提取**（`converter.py`）：逐段读取 docx 段落文本，`.txt` 文件则按行读取。识别发布机关（白名单精确匹配 12 个机构）和发文字号（正则匹配 `机构缩写〔年份〕序号` 格式）。

3. **生效日期提取**（`effective_date.py`）：从发布说明段落中提取生效日期，xlsx 有记录时用 xlsx 值覆盖。

4. **编/章/节/条识别**（`converter.py` 主循环）：
   - `第X编` → part 节点
   - `第X章` 或 `一、管辖`（汉字序号，司法解释常见） → chapter 节点
   - `第X节` → section 节点
   - `第X条` → article 节点；支持多条合并段落的拆分（`_INLINE_ART_RE`）
   - 无章节结构的短文件（法律解释、批复等） → 整体 full_text 写为单条 article

5. **结构组装**（`structure.py`）：按 part/chapter/section/article 层级组装嵌套 dict，分配 `global_order`（深度优先遍历序号），保证 `ORDER BY global_order` 还原原文顺序。

6. **元数据写入**：`title`（从文件名提取，不从 docx 正文读）、`category`（xlsx 权威）、`legal_domain`（优先从 ``LAWS_REPO_PATH`（默认 `~/Github/Laws/`）` 目录结构匹配，其次手工补充，再次关键词规则）。

**特殊处理**：
- 民法典有 7 编，第一编"总则"在源文件中无编标题行，硬编码补全
- 编下直属条文（无章层级）通过 `_DIRECT_` 占位章处理，不创建多余节点
- 九民纪要等用 `1.【标题】正文` 格式，由 `fetch_web_sources.py` 预处理转换为 `第N条　【标题】正文`

---

### 阶段二：`generate_law_index` — 分配稳定 law_id

**输入**：`json/` 目录下的所有 `.json` 文件

**输出**：`scripts/law_index.json`（持久化索引，跨 pipeline 重建保持 ID 稳定）

每部法律用 `{title}_{pub_date}` 作为唯一键，第一次见到时分配永久 ID（从 1000001 起自增）。后续重建 pipeline 时已有法律保持原 ID，新增法律追加新 ID。这保证 `article_references` 等跨库引用不因重建失效。

---

### 阶段三：`json_to_db` — JSON → SQLite 数据库

**输入**：`json/` 目录，`law_index.json`

**输出**：`law_content.db`（每次全量重建，删旧建新）

**具体步骤**：

1. **建表**（`builder.py`）：创建 `laws`、`nodes`、`nodes_fts`（trigram FTS5）、`nodes_fts_bigram`（unicode61 FTS5）、`article_references` 表及索引。`nodes_fts` / `nodes_fts_bigram` 均为**外部内容表**（`content="nodes"`），不复制原文，节省约 175MB 空间。

2. **写入 laws 表**：从 JSON 读取元数据，查 `law_index.json` 拿稳定 ID，查 `law_aliases.py` 拿别名。

3. **写入 nodes 表**（递归插入）：part → chapter → section → article 递归插入，每层记录 `parent_id`、`global_order`、`part_num`、`chapter_num`、`section_num`、`article_num`；每条 article 同时插入两个 FTS 表。

4. **FTS 优化**：全部插入完成后执行 `optimize`，合并 FTS 段，提升查询性能。

5. **公报司法解释打标**（`classify_gongbao_domain.py`）：为 `source='gongbao'` 的司法解释分配 legal_domain。

6. **导出导航菜单**：生成 `law_menu.json`（按 subject_area 分组，含 title_en），供 iOS app 侧边栏使用。

---

### 阶段四：`extract_references` — 法条引用关系提取

**输入**：`law_content.db`（nodes 表）

**输出**：`references/article_references.json`，并写入 `law_content.db` 的 `article_references` 表

**提取逻辑**（`extract_references.py`）：

遍历所有 `is_current=1` 的条文，用正则识别三类引用：

1. **有书名号跨法引用**：匹配 `《法律名》第X条`，提取法律名后查 `art_index` 解析到具体节点，短标题（去掉"中华人民共和国"前缀）和全称均可匹配。

2. **无书名号短标题引用**：如 `刑法第X条`、`合同法第X条`，动态构建短标题正则，按长度降序优先匹配避免歧义。

3. **本法自引**：匹配 `本法/本条例/本规定第X条`。刑法修正案中的"本法第X条"自动重定向到刑法主体，标记为 `cross_law`。

**当前统计**：5,319 条引用（跨法 2,559 条，自引 2,760 条），解析率 98.4%。

---

### 阶段五：英文导入（`import_en.py`）

**输入**：`json_en/`（条文翻译）、`references/heading_en_map.json`（结构节点标题翻译）

**输出**：写入 `nodes.content_en` 和 `laws.title_en`

- 按 `article_number` 匹配条文，幂等写入（`WHERE content_en IS NULL` 不覆盖已有翻译）
- 结构节点（编/章/节）标题从 `heading_en_map.json`（稳定键 `law_id:type:order_index`）写入

---

### 阶段六：`db_to_md` — 数据库 → Markdown 全文

**输入**：`law_content.db`（`is_current=1` 的法律）

**输出**：按 subject_area 菜单分组的 `.md` 文件（宪法与国家机构/ 民事与商事/ 刑事/ 行政与公法/ 经济、税务与金融/ 劳动与社会保障/ 诉讼与司法程序/ 其他）

每条条文生成 `<a id="art-N">` 锚点，正文中的出向引用自动转为跨文件 Markdown 链接。

---

### 阶段七：公报数据导入（`build_gongbao_db`）

**前置条件**：`最高人民法院公报/` 目录已有 JSON 文件（由 `fetch_gongbao.py` 抓取）

**输出**：在 `law_content.db` 中新增两张表，并将公报司法解释合并进主库 `laws`/`nodes`：

| 表 | 说明 |
|----|------|
| `gongbao_docs` | 裁判文书 + 指导案例 + 司法文件，共 2,289 条；`source` 字段区分 `al`/`cpwsxd`/`sfwj` |
| `gongbao_case_law_links` | 公报文书引用主库法条的关联，共 3,529 条，解析率 99.8% |
| `gongbao_docs_fts` | FTS5 trigram 全文索引（外部内容表） |

公报司法解释（839 条，ID 范围 3500010–3501473）不再单独建表，而是作为 `source='gongbao'` 写入主库 `laws`/`nodes` 表。law_id 分配严格遵循 `scripts/law_id_registry.py`（blocklist → json_en 内嵌 → law_index 三级解析），禁止模糊映射。

**独立运行**：

```bash
python3 scripts/build_gongbao_db.py          # 建表并导入（表已存在时跳过）
python3 scripts/build_gongbao_db.py --drop   # 先删旧表再重建
```

**公报数据抓取**：

```bash
# 抓取所有目标（首次约 2–3 小时）
python3 scripts/fetch_gongbao.py --target al      # 指导案例
python3 scripts/fetch_gongbao.py --target sfwj    # 司法文件
python3 scripts/fetch_gongbao.py --target cpwsxd  # 裁判文书
python3 scripts/fetch_gongbao.py --target sfjs    # 公报司法解释
python3 scripts/fetch_gongbao.py --target flxd    # 法律法规（参考）

# 增量更新（跳过已抓取文件）
python3 scripts/fetch_gongbao.py --target al --skip-existing
```

---

### 运行参数

```bash
python3 scripts/pipeline.py                          # 完整七阶段运行
python3 scripts/pipeline.py --docx                   # 强制重跑 docx → JSON（否则自动检测源文件变更）
python3 scripts/pipeline.py --skip-index             # 跳过 law_index 生成
python3 scripts/pipeline.py --skip-db                # 跳过 JSON → DB
python3 scripts/pipeline.py --skip-md                # 跳过 DB → Markdown
python3 scripts/pipeline.py --skip-gongbao           # 跳过公报导入
python3 scripts/pipeline.py --skip-en                # 跳过英文导入
python3 scripts/pipeline.py --only-refs              # 只重跑引用提取
python3 scripts/pipeline.py --validate               # 追加 content_en vs json_en 校验

# 各阶段单独运行
cd scripts
python3 -m docx_to_json.converter     # 阶段一
python3 generate_law_index.py          # 阶段二
python3 -m json_to_db.builder          # 阶段三
python3 extract_references.py          # 阶段四（仅生成 JSON）
python3 import_en.py                   # 阶段五（英文导入）
python3 -m db_to_md.renderer           # 阶段六
python3 build_gongbao_db.py --drop     # 阶段七（独立重建）
python3 fetch_web_sources.py           # 抓取/更新网页替换文件（独立）
python3 verify_db.py                   # 验证 DB 与 JSON 一致性（可选）
```

---

## 🗄️ 数据库结构

项目包含两个 SQLite 数据库：

- **`law_content.db`**（~460MB）— 主数据库，由 `pipeline.py` 全量生成，含公报表。**不提交 git**，从 [GitHub Releases](https://github.com/doxie/laws-data/releases) 下载或本地构建
- **`law_enhancements.db`**（~128KB）— RAG 增强数据库，由 `build_enhancements.py` 独立维护

### `law_content.db` 表结构

#### 🟠 `laws` 表 — 每部法律一行

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 稳定主键，由 `generate_law_index.py` 分配，跨重建不变 |
| `title` | TEXT | 完整标题，从文件名提取（不从 docx 正文读） |
| `title_en` | TEXT | 英文标题，从 json_en 导入 |
| `filename` | TEXT UNIQUE | 格式：`{标题}_{YYYYMMDD}`，无后缀 |
| `category` | TEXT | `法律` / `行政法规` / `司法解释` / `修正案` / `法律解释` / `宪法` / `监察法规` / `有关法律问题和重大问题的决定（部分）` |
| `legal_domain` | TEXT | 法律部门：`民法典` / `民法商法` / `刑法` / `行政法` / `经济法` / `社会法` / `宪法相关法` / `诉讼与非诉讼程序法` |
| `subject_area` | TEXT | 菜单二级主题（v2.0.0 起所有法律都有，export_menu.py 回写） |
| `pub_date` | TEXT | 公布日期 `YYYY-MM-DD` |
| `effective_date` | TEXT | 生效日期，xlsx 权威来源优先 |
| `promulgation_info` | TEXT | 发布说明全文（通过/公布/施行信息段落） |
| `issuing_org` | TEXT | 发布机关（白名单精确匹配 12 个机构） |
| `doc_number` | TEXT | 发文字号（法释〔2000〕29号 等） |
| `total_articles` | INTEGER | 条文总数 |
| `full_text` | TEXT | 法律全文原文 |
| `version_date` | TEXT | 同 `pub_date`，用于多版本区分 |
| `is_current` | INTEGER | **1 = 现行**；0 = 历史版本或被废止决定明确废止（`repealed_by` 非空） |
| `aliases` | TEXT | 逗号分隔别名（如 `民法典,民法`），用于搜索扩展 |
| `source` | TEXT | 数据来源：`flk`（主库）/ `gongbao`（最高人民法院公报） |

```sql
-- 按别名搜索
SELECT * FROM laws WHERE is_current=1 AND (title LIKE '%民法%' OR aliases LIKE '%民法%');

-- 查某机构司法解释
SELECT title, doc_number, pub_date FROM laws
WHERE issuing_org = '最高人民法院' AND category = '司法解释'
ORDER BY pub_date DESC;
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
- 编（part）结构在 9 部法律中存在（民法典、刑法×2、刑事诉讼法×2、民事诉讼法×3、生态环境法典）
- 部分司法解释用汉字序号章节（`一、管辖`），仍映射为 `chapter` 类型
- 无章节的短文件整体写为单条 `article`（content = full_text）

```sql
-- 按顺序展示某法律全文
SELECT type, title, content FROM nodes WHERE law_id = ? ORDER BY global_order;

-- 按条文序号范围查询（第十条到第二十条）
SELECT article_number, content FROM nodes
WHERE law_id = ? AND type = 'article' AND article_num BETWEEN 10 AND 20;
```

#### 🟢 `nodes_fts` — 全文搜索（≥3 字）

FTS5 **外部内容表**（`content="nodes"`），不复制原文，节省约 175MB 空间。分词器：`trigram`，支持任意中文子串精确匹配，最少 3 个字符。

```sql
SELECT n.article_number, n.content, l.title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article' AND l.is_current = 1;
```

#### 🔵 `nodes_fts_bigram` — 短词搜索（1–2 字）

FTS5 外部内容表，分词器：`unicode61`，专门处理 1–2 字搜索（`婚`、`婚姻`）。3 字及以上建议用 `nodes_fts`（trigram 更精确）。

#### 🔴 `article_references` — 法条引用关系

| 字段 | 类型 | 说明 |
|------|------|------|
| `from_node_id` | INTEGER FK | 引用方节点 |
| `from_law_id` | INTEGER FK | 引用方法律 |
| `from_article_num` | INTEGER | 引用方条文序号 |
| `to_node_id` | INTEGER FK | 被引用方节点（已解析时有值） |
| `to_law_id` | INTEGER FK | 被引用方法律 |
| `to_article_num` | INTEGER | 被引用方条文序号 |
| `ref_type` | TEXT | `cross_law`（跨法引用）/ `self_ref`（本法自引） |
| `resolved` | INTEGER | 1 = 已解析到具体节点 |
| `raw_text` | TEXT | 原文引用字符串，如 `《中华人民共和国民法典》第一千二百零八条` |

覆盖所有 `is_current=1` 的条文，由 `extract_references.py` 提取，随主 pipeline 自动更新。

---

### `law_content.db` 公报扩展表

这五张表由 `build_gongbao_db.py`（pipeline 阶段七）写入，存储最高人民法院公报数据。

#### `gongbao_docs` — 裁判文书 / 指导案例 / 司法文件（2,289 条）

| 字段 | 说明 |
|------|------|
| `source` | `al`（指导案例）/ `cpwsxd`（裁判文书）/ `sfwj`（司法文件） |
| `case_number` | 指导性案例编号，如 `指导性案例212号`（仅 al 有） |
| `title` | 案件/文件标题 |
| `issue` | 期刊期号，如 `2024年01期` |
| `year` / `issue_num` | 年份 / 期号（整数，便于排序） |
| `pub_date` | 文书发布日期 |
| `url` | 原文链接（gongbao.court.gov.cn） |
| `ruling_gist` | 裁判要点/裁判摘要（最多 500 字，从正文提取） |
| `keywords` | 关键词（逗号分隔，从正文提取） |
| `full_text` | 全文原文 |

#### `gongbao_case_law_links` — 公报文书 → 主库法条关联（3,529 条）

从 `gongbao_docs` 全文提取 `《法律名》第N条` 引用，关联到 `laws.id` 和 `nodes.id`，解析率 99.8%。

#### `gongbao_docs_fts`

FTS5 外部内容表，`tokenize="trigram"`，索引 `title`、`ruling_gist`、`keywords`、`full_text`，支持中文任意子串搜索（≥2 字）。

```sql
-- 搜索裁判要点含"善意取得"的指导案例
SELECT d.title, d.case_number, d.ruling_gist
FROM gongbao_docs_fts f
JOIN gongbao_docs d ON f.rowid = d.id
WHERE gongbao_docs_fts MATCH '善意取得' AND d.source = 'al'
ORDER BY d.year DESC;

-- 查某条文被哪些公报案例引用
SELECT d.title, d.source, l.article_num
FROM gongbao_case_law_links l
JOIN gongbao_docs d ON l.doc_id = d.id
WHERE l.node_id = ?;
```

---

### `law_enhancements.db` 表结构

#### `term_aliases` — 日常语言 → 法律术语（134 条）

LLM 生成候选术语，FTS 验证命中数 > 0 后写入。

| 字段 | 说明 |
|------|------|
| `colloquial` | 日常用语，如 `车祸`、`被炒鱿鱼` |
| `legal_term` | 条文中实际出现的术语，如 `道路交通事故`、`解除劳动合同` |
| `fts_hits` | 该术语在条文中的命中数 |

#### `alias_patches` — 手工精确补丁（135 条）

补充 LLM 自动生成的缺口（`离婚`、`误工费`、`工伤` 等），与 `term_aliases` 结构相同。

#### `topic_law_hints` — 场景关键词 → 推荐法律（115 条）

将问题场景映射到最相关法律，RAG 检索时优先在这些法律内搜索。

#### `keyword_synonyms` — LLM 关键词 → 精确 FTS 词（312 条）

LLM 造出的词（`超速驾驶`）映射到实际有命中的术语（`违法驾驶`）。

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

**有编结构（民法典、刑法、诉讼法、生态环境法典等 9 部）：**

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

关键词检索 + LLM 过滤：分类路由 → 关键词提取 + 别名扩展 → FTS 检索 → 相关性过滤 → 生成回答。

### `legal_chain_agent.py` — 法条链推理 Agent

引入章节定位与引用链扩展：问题拆分 → 大类路由 → 章节导航抓取条文 → FTS 补充 → 引用链扩展（自动追加被引条文）→ 过滤排序 → 生成结论。

```bash
python3 scripts/legal_chain_agent.py -q "网购假货怎么维权"
python3 scripts/legal_chain_agent.py -q "..." --provider deepseek
```

### `legal_expert_agent.py` — 多层专家协作系统

三层专家架构（协调员 → 6 个专家组 → 17 个细分专家），支持信息收集（自动提取已知事实，缺失时批量询问）。

```bash
python3 scripts/legal_expert_agent.py -q "公司非法裁员我怎么办"
python3 scripts/legal_expert_agent.py -q "..." --no-interactive  # 跳过信息收集
```

**依赖**：`pip install requests`（在线 provider）；本地 Ollama 需 `ollama pull qwen2.5:3b`。

---

## 🚀 快速开始

### 方式一：下载预构建数据库（推荐）

```bash
git clone https://github.com/doxie/laws-data.git
cd laws-data

# 下载 law_content.db（GitHub Releases 附件，约 460MB）
python3 scripts/download_db.py
```

预构建数据库包含全部法律条文、英文翻译、FTS 索引、公报数据，可直接用于 iOS app 或查询。

### 方式二：从源码完整构建（约 5–10 分钟）

```bash
pip install python-docx xlrd

# 完整 pipeline（自动检测源文件变更，全量重建）
python3 scripts/pipeline.py

# 强制重跑 docx → JSON（源文件变更时）
python3 scripts/pipeline.py --docx

# 验证数据库完整性（可选）
python3 scripts/verify_db.py
```

更新源文件后直接重跑 `pipeline.py` 即可，pipeline 无状态，每次全量重建。

---

## ⚠️ 已知限制与注意事项

- FTS trigram 最短匹配词为 3 字；1–2 字搜索用 `nodes_fts_bigram`
- 法条引用关系仅提取 `is_current=1` 的条文
- 83 条引用因目标法律未收录而无法解析（执业医师法等未纳入数据集）
- `json/` 目录**必须与 `sources/` 对应**（按 category 平铺），不能按 `legal_domain` 重组，否则 `builder.py` 路径扫描失效
- `law_content.db` 不提交 git（约 460MB），从 [GitHub Releases](https://github.com/doxie/laws-data/releases) 下载或本地构建

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！法律数据修正、英文翻译、pipeline 改进均受欢迎。详见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [Code of Conduct](CODE_OF_CONDUCT.md)。

## 📄 许可

本项目采用 [MIT License](LICENSE)。法律文本源自官方公开渠道（国家法律法规数据库、最高人民法院公报），本身不受著作权保护；结构化数据与翻译成果同样以 MIT 开放使用。
