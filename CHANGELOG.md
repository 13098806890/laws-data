# Changelog

## v1.0.0 — 2026-06-30

首个正式版本。完成从原始法律文档到结构化数据库的完整 pipeline，并引入最高人民法院公报数据及英文翻译基础设施。

### 数据规模
- **2,020 部**法律法规（宪法 1、法律 310、修正案 12、法律解释 25、司法解释主库 294、司法解释公报补充 767、行政法规 607、监察法规 2）
- **84,000+ 条**条文，FTS5 trigram 全文检索
- **8,340 条**法条间引用关系，解析率 96.2%
- **148 部**法考收录法律，附法考六科分类导航
- 最高人民法院公报全量：指导案例 986 篇、司法文件 860 篇、裁判文书 443 篇
- 公报法条引用关联 3,533 条，解析率 99.8%

### 核心功能
- **三阶段 pipeline**：docx → 结构化 JSON → SQLite → Markdown
- **多来源合并**：主库（`source='flk'`）+ 公报司法解释（`source='gongbao'`）统一存入 `laws`/`nodes` 表，ID 固定不变
- **FTS5 全文检索**：trigram tokenizer，支持任意中文子串搜索
- **法条引用关系**：`article_references` 表，跨法和本法自引分类标注
- **法考模式**：`is_flk` 字段标注，附 `flk_menu.json` 六科导航
- **LLM 关键词标注**：公报文书 1,429 条，零失败
- **英文标题 map**：`references/law_title_en_map.json`，1,570 条

### 数据库结构（law_content.db，~250 MB）
- `laws` 表：每部法律一行，含 `source`、`legal_domain`、`issuing_org`、`doc_number`、`is_current` 等字段
- `nodes` 表：编/章/节/条统一存储，`global_order` 保证展示顺序
- `nodes_fts` 虚拟表：FTS5 trigram 索引
- `gongbao_docs` 表：公报裁判文书、指导案例、司法文件
- `gongbao_case_law_links` 表：公报文书与主库法条的引用关联

### 英文翻译（基础设施，待完成）
- `json_en/` 目录结构已建立，镜像 `json/` 的 category 结构（1,529 个文件占位）
- `references/law_title_en_map.json` 完成，1,570 条标题翻译
- 条文全量翻译、DB 集成、英文 FTS 待后续版本完成（见 TODO.md）
