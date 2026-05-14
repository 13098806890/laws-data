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
| 司法解释（主库） | 294 |
| 司法解释（公报补充） | 767 |
| 行政法规 | 607 |
| 监察法规 | 2 |
| 会议纪要等 | 数部 |
| **合计** | **2,020** |

条文总数约 **84,000 条**，法条间引用关系 **8,340 条**（跨法引用 5,204 条，本法自引 3,136 条），解析率 96.2%。

**法考模式**：数据集包含 **148 部**法律职业资格考试（法考）收录的法律，全部来自主库源文件（`sources/` 目录），通过 `is_flk` 字段标注，并附有按法考六大科目排列的 `flk_menu.json` 导航索引和 `法考/` Markdown 目录。

**最高人民法院公报**：额外收录最高人民法院公报（gongbao.court.gov.cn）全量数据，包括指导案例 986 篇、司法文件 860 篇、裁判文书 443 篇。公报司法解释（927 条）已合并进主库 `laws`/`nodes` 表（`source='gongbao'`），其中 419 条复用主库 ID，508 条分配新 ID。所有公报文书均已建立与主库法条的引用关联（3,533 条，解析率 99.8%）。

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
├── 📂 宪法与国家机构/             # Markdown 全文（按法律部门分类，is_current=1）
├── 📂 民事与商事/
├── 📂 刑事/
├── 📂 行政与公法/
├── 📂 经济、税务与金融/
├── 📂 劳动与社会保障/
├── 📂 诉讼与司法程序/
├── 📂 法考/                        # Markdown 全文（按法考科目分目录，pipeline 产物）
│   ├── 刑法/                       # 75 部
│   ├── 刑事诉讼法/                 # 37 部
│   ├── 行政法与行政诉讼法/         # 34 部
│   ├── 民法/                       # 19 部
│   ├── 商法/                       # 22 部
│   └── 民事诉讼法/                 # 21 部
├── 📂 references/
│   └── article_references.json    # 法条间引用关系（pipeline 产物）
├── 📂 flk_source/                 # 法考交叉验证专用目录（独立 pipeline）
│   ├── tree_data.js               # 厚大法考目录树（手动下载）
│   └── json/                      # 厚大法考 JSON 缓存（flk_pipeline.py 自动下载）
├── 📂 最高人民法院公报/            # 公报全量数据（fetch_gongbao.py 抓取，JSON 格式）
│   ├── 指导案例/                  # 986 篇（al）
│   ├── 司法文件/                  # 860 篇（sfwj）
│   ├── 裁判文书/                  # 443 篇（cpwsxd）
│   └── 司法解释/                  # 927 篇（含主库已有 + 独有 487 篇）
├── 📂 scripts/
│   ├── config.py                  # 路径配置（BASE_DIR、DB_PATH 等）
│   ├── utils.py                   # 公共工具（title_from_stem、pub_date_from_stem）
│   ├── law_aliases.py             # 法律别名映射（民法典→"民法典,民法" 等）
│   ├── pipeline.py                # 主 pipeline 入口（六阶段，含公报导入）
│   ├── fetch_gongbao.py           # 最高人民法院公报抓取脚本（5 个目标）
│   ├── build_gongbao_db.py        # 公报数据 → law_content.db（阶段六）
│   ├── flk_pipeline.py            # 法考交叉验证 pipeline（独立，见下文）
│   ├── verify_flk.py              # 法考数据库条文内容交叉验证脚本
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
│   ├── docx_to_json/              # 阶段一：docx/txt → JSON
│   │   ├── converter.py           # 主入口，段落解析，编/章/节/条识别
│   │   ├── structure.py           # 层级结构组装，global_order 分配
│   │   ├── domain.py              # legal_domain 映射，xlsx 索引读取
│   │   ├── effective_date.py      # 生效日期提取
│   │   └── subject_area.py        # 行政法规二级主题分类
│   ├── json_to_db/                # 阶段三：JSON → SQLite
│   │   ├── builder.py             # 建表、写入法律/节点/FTS
│   │   ├── export_menu.py         # 导出 law_menu.json 导航索引
│   │   └── export_flk_menu.py     # 导出 flk_menu.json 法考导航索引
│   └── db_to_md/                  # 阶段五：DB → Markdown
│       ├── renderer.py            # 按 legal_domain 分目录渲染全量 Markdown
│       └── render_flk.py          # 按法考科目渲染 法考/ 目录
├── 📄 law_index.json              # 稳定 law_id 索引（跨重建不变）
├── 📄 law_menu.json               # 侧边栏导航索引（按法律部门分组）
├── 📄 flk_menu.json               # 法考导航索引（148 部，6 个科目）
├── 📄 法考目录.json               # 法考收录法律名单（来源：官方法考大纲）
├── 🗄️  law_content.db             # 主数据库（~250MB，含公报表，Git LFS）
├── 🗄️  law_enhancements.db        # RAG 增强数据库（~64KB，Git LFS）
└── 🗄️  flk_content.db             # 法考交叉验证数据库（独立 pipeline 产物）
```

---

## 🔄 主 Pipeline 详解

**运行入口**：`python3 scripts/pipeline.py`

主 pipeline 分五个阶段顺序执行，全量重建（无增量），每次运行约 5–10 分钟。

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

6. **元数据写入**：`title`（从文件名提取，不从 docx 正文读）、`category`（xlsx 权威）、`legal_domain`（优先从 `/Users/doxie/Github/Laws/` 目录结构匹配，其次手工补充，再次关键词规则）。

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

4. **多版本标记**：同名法律按 `pub_date` 降序，最新版设 `is_current=1`，其余设 0。

5. **FTS 优化**：全部插入完成后执行 `optimize`，合并 FTS 段，提升查询性能。

6. **法考标记**：读取 `法考目录.json`，将 208 部法考收录法律（标题精确匹配或规范化变体匹配）的 `is_flk` 字段设为 1。共标记 269 条记录（含历史版本）。**法考 208 部法律均来自 `sources/` 目录，与主 pipeline 共用同一份源文件，无需从外部 URL 重新拉取。**

7. **导出导航菜单**：生成 `law_menu.json`（全量 1,572 部，按法律部门分组）和 `flk_menu.json`（148 部，按 6 个法考科目排列），供 iOS app 侧边栏使用。

---

### 阶段四：`extract_references` — 法条引用关系提取

**输入**：`law_content.db`（nodes 表）

**输出**：`references/article_references.json`，并写入 `law_content.db` 的 `article_references` 表

**提取逻辑**（`extract_references.py`）：

遍历所有 `is_current=1` 的条文（包含所有 `is_flk=1` 的法考法律），用正则识别三类引用：

1. **有书名号跨法引用**：匹配 `《法律名》第X条`，提取法律名后查 `art_index` 解析到具体节点，短标题（去掉"中华人民共和国"前缀）和全称均可匹配。

2. **无书名号短标题引用**：如 `刑法第X条`、`合同法第X条`，动态构建短标题正则，按长度降序优先匹配避免歧义。

3. **本法自引**：匹配 `本法/本条例/本规定第X条`。刑法修正案中的"本法第X条"自动重定向到刑法主体，标记为 `cross_law`。

**当前统计**：8,340 条引用（跨法 5,204 条，自引 3,136 条），解析率 96.2%。

---

### 阶段五：`db_to_md` — 数据库 → Markdown 全文

**输入**：`law_content.db`（`is_current=1` 的法律）

**输出**：
- 按 `legal_domain` 分目录的 `.md` 文件（全量）
- `法考/` 目录：按 6 个法考科目分子目录，共 148 个文件（`render_flk.py`）

每条条文生成 `<a id="art-N">` 锚点，正文中的出向引用自动转为跨文件 Markdown 链接。

---

### 阶段六：`build_gongbao_db` — 公报数据 → law_content.db

**前置条件**：`最高人民法院公报/` 目录已有 JSON 文件（由 `fetch_gongbao.py` 抓取）

**输出**：在 `law_content.db` 中新增两张表，并将公报司法解释合并进主库 `laws`/`nodes`：

| 表 | 说明 |
|----|------|
| `gongbao_docs` | 裁判文书 + 指导案例 + 司法文件，共 2,289 条；`source` 字段区分 `al`/`cpwsxd`/`sfwj` |
| `gongbao_case_law_links` | 公报文书引用主库法条的关联，共 3,533 条，解析率 99.8% |
| `gongbao_docs_fts` | FTS5 trigram 全文索引（外部内容表） |

公报司法解释（927 条）不再单独建表，而是作为 `source='gongbao'` 写入主库 `laws`/`nodes` 表：419 条复用主库 ID（覆盖主库版本），508 条分配新 ID（范围 3500726–3501233）。

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
python3 scripts/pipeline.py                          # 完整六阶段运行
python3 scripts/pipeline.py --skip-docx              # 跳过阶段一（JSON 已有时）
python3 scripts/pipeline.py --skip-docx --skip-index # 跳过阶段一、二
python3 scripts/pipeline.py --skip-docx --skip-db    # 只重建 Markdown
python3 scripts/pipeline.py --skip-docx --skip-md    # 不重建 Markdown
python3 scripts/pipeline.py --skip-gongbao           # 跳过阶段六（公报导入）

# 各阶段单独运行
cd scripts
python3 -m docx_to_json.converter     # 阶段一
python3 generate_law_index.py          # 阶段二
python3 -m json_to_db.builder          # 阶段三
python3 extract_references.py          # 阶段四（仅生成 JSON）
python3 -m db_to_md.renderer           # 阶段五
python3 build_gongbao_db.py --drop     # 阶段六（独立重建）
python3 fetch_web_sources.py           # 抓取/更新网页替换文件（独立）
python3 verify_db.py                   # 验证 DB 与 JSON 一致性（可选）
```

---

## ⚖️ 法考交叉验证 Pipeline（独立）

**用途**：从 [厚大法考](http://www.houdask.com/) 拉取法律原文，与主库 `law_content.db` 逐条对比，验证条文内容是否一致。属于**独立的验证工具**，不影响主 pipeline，不修改主库。

**重要说明**：法考 208 部法律已全部收录于主库，均来自国家法律法规数据库的 docx 源文件，均已标记 `is_flk=1`，且法条引用关系（`article_references`）也已完整包含这 208 部法律。主库数据**不依赖厚大来源**，该 pipeline 仅用于独立比对两个来源的条文内容，发现版本差异。

### 标题对应关系

厚大数据与主库对同一部法律的标题命名存在以下差异（共 18 部，全部已通过规范化自动匹配）：

| 差异类型 | 厚大标题示例 | 主库标题示例 |
|----------|------------|------------|
| 半角括号 vs 全角括号（8 部） | `刑法修正案(四)` | `刑法修正案（四）` |
| 带书名号 vs 无书名号（7 部） | `五部门《关于…规定》` | `五部门关于…规定` |
| 带修正年份后缀（1 部） | `…解释(2009修正)` | `…解释`（无后缀） |
| 带序号 vs 无序号（1 部） | `…淫秽电子信息…解释(一)` | `…淫秽电子信息…解释` |
| 书名号内容差异（1 部） | `执行《中华人民共和国国家赔偿法》` | `执行中华人民共和国国家赔偿法` |

其中括号写法差异（共 15 部）由 `_build_main_title_index()` 的四种规范化变体自动处理；剩余 2 部通过 `TITLE_OVERRIDES` 字典手动映射。

### 数据流

```
厚大 houdask.com
  └─ tree_data.js（208 部法律目录树，含每部法律的 jsonUrl）
       └─ img.juexiaotime.com/*.json（每部法律的章节原文，2021 年版）
            └─ flk_source/json/{id}.json（本地缓存）
                 └─ flk_content.db（法考验证数据库）
                      │
                      └─ verify_flk.py ←──→ law_content.db（主库）
                                           （按 law_id 直接匹配）
```

### `flk_content.db` 数据库结构

| 表 | 说明 |
|----|------|
| `laws` | 法考 208 部法律。`id` 字段与主库 `laws.id` 对齐（同一部法律用同一个 id），方便直接 join 比较。极少数标题差异较大、无法自动对齐的法律使用负数 id。 |
| `sections` | 章节节点，来自厚大 JSON 的扁平列表（`type`=3 节 / 4 章），含 `full_text`（章节全文） |
| `articles` | 从 `full_text` 按 `第X条` 正则切分出的条文，含 `article_number`、`content` |
| `articles_fts` | FTS5 trigram 全文索引，索引 `articles` 表 |

### 运行方法

```bash
cd /Users/doxie/laws_data

# 完整流程：下载所有法律 JSON + 建库 + 交叉验证（首次约 5 分钟）
python3 scripts/flk_pipeline.py

# 使用已缓存的 JSON（跳过下载，约 30 秒）
python3 scripts/flk_pipeline.py --skip-dl

# 只重建 flk_content.db，不跑验证
python3 scripts/flk_pipeline.py --skip-dl --skip-db

# 只跑验证报告（flk_content.db 已存在时）
python3 scripts/verify_flk.py

# 查看某部法律的详细差异（含具体条文内容对比）
python3 scripts/verify_flk.py --law 中华人民共和国刑法 --diff

# 输出报告到文件
python3 scripts/verify_flk.py --out verify_report.txt
```

### 验证逻辑（`verify_flk.py`）

1. 从 `flk_content.db` 取全部 208 部法律
2. 对每部法律，用 `law_id`（已在建库时与主库对齐）直接从主库取对应条文，无需标题匹配
3. 按 `article_number` 取交集：统计仅法考库有、仅主库有、内容不同的条文
4. 内容比较忽略所有空白字符差异（换行、缩进等排版差异不影响结论）

**当前验证结论**（2025 年）：208/208 部全部与主库 id 对齐。14 部条文完全一致，194 部存在条文差异，主要原因是**厚大数据为 2021 年版本**，沿用旧条号，而主库收录 2023/2024 年修订的现行版本，差异来源于法律修订而非数据错误。

---

## 🗄️ 数据库结构

项目包含三个 SQLite 数据库：

- **`law_content.db`**（~250MB）— 主数据库，由 `pipeline.py` 全量生成，含公报表
- **`law_enhancements.db`**（~64KB）— RAG 增强数据库，独立维护
- **`flk_content.db`**（独立）— 法考交叉验证数据库，由 `flk_pipeline.py` 生成

### `law_content.db` 表结构

#### 🟠 `laws` 表 — 每部法律一行

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 稳定主键，由 `generate_law_index.py` 分配，跨重建不变 |
| `title` | TEXT | 完整标题，从文件名提取（不从 docx 正文读） |
| `filename` | TEXT UNIQUE | 格式：`{标题}_{YYYYMMDD}`，无后缀 |
| `category` | TEXT | `法律` / `行政法规` / `司法解释` / `修正案` / `法律解释` / `宪法` / `监察法规` |
| `legal_domain` | TEXT | 法律部门：`民法典` / `民法商法` / `刑法` / `行政法` / `经济法` / `社会法` / `宪法相关法` / `诉讼与非诉讼程序法` |
| `subject_area` | TEXT | 行政法规二级主题，其他类别为空 |
| `pub_date` | TEXT | 公布日期 `YYYY-MM-DD` |
| `effective_date` | TEXT | 生效日期，xlsx 权威来源优先 |
| `promulgation_info` | TEXT | 发布说明全文（通过/公布/施行信息段落） |
| `issuing_org` | TEXT | 发布机关（白名单精确匹配 12 个机构） |
| `doc_number` | TEXT | 发文字号（法释〔2000〕29号 等） |
| `total_articles` | INTEGER | 条文总数 |
| `full_text` | TEXT | 法律全文原文 |
| `version_date` | TEXT | 同 `pub_date`，用于多版本区分 |
| `is_current` | INTEGER | **1 = 现行版本**（最新 pub_date），0 = 历史版本 |
| `aliases` | TEXT | 逗号分隔别名（如 `民法典,民法`），用于搜索扩展 |
| `is_flk` | INTEGER | **1 = 法考收录**，0 = 非法考。由 `法考目录.json` 标注，含历史版本 |

```sql
-- 查法考收录的现行法律（208 部）
SELECT title, category FROM laws WHERE is_flk=1 AND is_current=1 ORDER BY title;

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
- 编（part）结构只在 8 部法律中存在（民法典、刑法×2、刑事诉讼法×2、民事诉讼法×3）
- 115 个司法解释用汉字序号章节（`一、管辖`），仍映射为 `chapter` 类型
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

覆盖所有 `is_current=1` 的条文，包含全部 208 部法考法律，由 `extract_references.py` 提取，随主 pipeline 自动更新。

---

### `law_content.db` 公报扩展表

这五张表由 `build_gongbao_db.py`（pipeline 阶段六）写入，存储最高人民法院公报数据。

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

#### `gongbao_case_law_links` — 公报文书 → 主库法条关联（3,533 条）

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

#### `alias_patches` — 手工精确补丁（22 条）

补充 LLM 自动生成的缺口（`离婚`、`误工费`、`工伤` 等），与 `term_aliases` 结构相同。

#### `topic_law_hints` — 场景关键词 → 推荐法律（50 条）

将问题场景映射到最相关法律，RAG 检索时优先在这些法律内搜索。

#### `keyword_synonyms` — LLM 关键词 → 精确 FTS 词（40 条）

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

```bash
pip install python-docx xlrd

# 完整 pipeline（约 5–10 分钟）
cd /path/to/laws_data
python3 scripts/pipeline.py

# 已有 JSON，只重建数据库（约 1–2 分钟）
python3 scripts/pipeline.py --skip-docx

# 验证数据库完整性（可选）
python3 scripts/verify_db.py

# 法考交叉验证（独立，需先存在 law_content.db）
python3 scripts/flk_pipeline.py --skip-dl   # 重建 flk_content.db（跳过下载）
python3 scripts/verify_flk.py               # 对比两库条文内容
```

更新源文件后直接重跑 `pipeline.py` 即可，pipeline 无状态，每次全量重建。

---

## ⚠️ 已知限制与注意事项

- FTS trigram 最短匹配词为 3 字；1–2 字搜索用 `nodes_fts_bigram`
- 法条引用关系仅提取 `is_current=1` 的条文
- 78 条引用因目标法律未收录而无法解析（执业医师法等未纳入数据集）
- 法考交叉验证中，194 部条文存在差异，主因是厚大数据为 2021 年版，与主库 2023/2024 年修订版条号和内容有出入，属正常版本差异
- `json/` 目录**必须与 `sources/` 对应**（按 category 平铺），不能按 `legal_domain` 重组，否则 `builder.py` 路径扫描失效
