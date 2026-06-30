# 英文法条翻译 & 集成计划

## 设计原则

- **翻译结果独立存储**，不混入主库 pipeline，避免重跑 pipeline 覆盖翻译
- **增量更新**：只翻译新增或变更法律，已翻译的文件不重跑
- **术语一致性**：翻译前注入 `law_title_en_map.json` + `legal_terms_glossary.json` 作为硬约束
- **中文逻辑不变**：法条跳转、引用、索引全部保持中文主键（`law_id` / `node_id`），英文是附加字段
- **英文搜索独立**：`nodes_fts_en`（unicode61）与中文 `nodes_fts`（trigram）并行

---

## 当前架构说明

目前存在两套英文翻译方案，需要统一：

| 脚本 | 输出 | 状态 |
|------|------|------|
| `gen_en_templates.py` | `json_en/` 占位文件（1,529 个，全空） | ✅ 已生成，有 `if exists: skip` 保护 |
| `translate_to_en.py` | 独立 `law_content_en.db` | ⚠️ 已有脚本但未运行，写入独立 DB 而非主库 |

**决策**：采用 `json_en/` 方案（而非独立 DB），翻译结果写入 `json_en/` 文件，再由 `builder.py` 读取写入主库 `laws`/`nodes` 表的英文字段。原因：
- `json_en/` 文件粒度清晰，git 可追踪每部法律的翻译变更
- 更新某部法律时只需替换对应 `json_en/` 文件，主 pipeline 重跑自动同步
- 独立 DB 方案难以做增量，且多了一个需要维护的数据库

---

## B. 翻译工程

### ✅ B1. 翻译基础设施：json_en/ 目录 + 格式设计
`json_en/` 目录已建立，镜像 `json/` 的 category 结构（1,529 个占位文件），`gen_en_templates.py` 负责生成模板，已有 `if exists: skip` 保护，翻译内容不会被覆盖。

```json
{
  "law_id": 3500268,
  "title_en": "Provisions of the Supreme People's Court on ...",
  "promulgation_info_en": "...",
  "articles": [
    {"article_number": "第一条", "content_en": "Article 1 ..."},
    {"article_number": "第二条", "content_en": "Article 2 ..."}
  ]
}
```

> `full_text_en` 不单独存，由 `builder.py` 从 `articles` 拼接。

**当更新某部法律时**：重跑 pipeline 生成新的中文 `json/` 文件，然后只需重新翻译对应的 `json_en/` 文件，其余已翻译文件不受影响。

### ✅ B2. Phase 1：法律标题翻译
- `references/law_title_en_map.json` 已生成，1,570 条，格式：`{"中文标题": "English Title"}`
- ⚠️ **人工过一遍确认**（待完成）——重点检查：
  - 专有法律名（民法典、刑法等）是否符合国际通用译法
  - 含机构名的标题（最高人民法院/最高人民检察院）翻译是否一致

### B3. Phase 2：法律术语表
- 从法条正文提取高频法律术语（200-500 词），产出 `references/legal_terms_glossary.json`
- 格式：`{"中文术语": "English Term", ...}`，按领域分组
- 重点术语：人民法院、人民检察院、依法、追究刑事责任、本解释、自本解释施行之日起……
- **人工审核确认**
- 翻译脚本注入此表作为 system prompt 硬约束，保证跨文件术语一致

### B4. Phase 3：Pilot 翻译（10 部）
目标：验证翻译质量和 prompt 策略，再铺全量。

选取代表性法律：
- 短司法解释 × 3（≤10 条，如批复类）
- 中等法律 × 4（30-80 条）
- 大法 × 3（民法典 1,260 条、刑法、民事诉讼法）

每次翻译时在 system prompt 中注入：
1. `law_title_en_map.json` 中的标题对照
2. `legal_terms_glossary.json` 中的术语表
3. 指令：正文中出现 `《xxx》` 引用时，须从标题 map 中查找对应英文名

**人工逐条审校**，验证：
- 术语一致性（同一术语在不同法律中翻译相同）
- 跨法引用名称（`《民法典》` → `Civil Code` 而不是其他译法）
- 法律文本风格（shall/may 等助动词使用规范）
- 根据结果调整 prompt 策略

### B5. Phase 4：全量翻译（`translate_to_en.py` 改造）
当前 `translate_to_en.py` 写入独立 DB，需改造为写入 `json_en/` 文件：

- 读取 `json_en/` 中 `content_en` 为空的文件（增量，跳过已翻译）
- 注入 `law_title_en_map.json` + `legal_terms_glossary.json`
- 批量调用 LLM（建议 3-5 部法律一批），写回 `json_en/` 文件
- 完成后运行 `gen_en_templates.py` 检查有无新增未覆盖的法律

### B6. Phase 4：一致性校验脚本
脚本扫描所有已翻译的 `json_en/` 文件，输出差异报告：
1. `title_en` 是否与 `law_title_en_map.json` 一致
2. 正文 `content_en` 中出现的法律名称英文是否统一（扫描引用 `Article X of the XXX`）
3. `legal_terms_glossary.json` 中的术语是否翻译一致（关键词频次抽查）

---

## C. DB 集成

### C1. DB schema：主库加英文字段
- `laws` 表：加 `title_en TEXT`、`full_text_en TEXT`
- `nodes` 表：加 `content_en TEXT`
- `builder.py` 中加载时扫描对应 `json_en/` 文件，按 `law_id` + `article_number` 匹配写入
- 未翻译的法律 → 英文字段为 NULL，App 端 fallback 显示中文

### C2. DB schema：英文 FTS 表
- 建 `nodes_fts_en` 虚拟表，`tokenize='unicode61 categories unicode'`
- 索引 `content_en` + `article_number`
- 与中文 `nodes_fts`（trigram）并行，互不干扰

### C3. builder.py 增量集成
**关键设计：英文字段从 `json_en/` 读取，主 pipeline 重跑不会清空已有翻译。**

- `build_db()` 在写完中文内容后，扫描 `json_en/category/filename.json`
- 按 `article_number` 匹配条文，写入 `nodes.content_en`
- `json_en/` 文件不存在或字段为空 → 跳过，保持 NULL
- 同步更新 `nodes_fts_en`

### C4. pipeline.py 集成（新增 `--skip-en` 选项）
- pipeline 末尾新增一步：调用 `gen_en_templates.py` 为新增法律生成占位文件
- 默认不运行全量翻译（翻译成本高，按需手动触发）
- 提供 `--skip-en` 跳过此步

### C5. renderer.py 双语 Markdown（可选）
- 如有英文内容，生成双语分块：中文段落 + 英文段落交替
- 无英文则保持原样

### C6. App 端 FTS 搜索路由
- 中文搜索（含 CJK 字符）→ `nodes_fts`（trigram）
- 英文搜索（纯 ASCII）→ `nodes_fts_en`（unicode61）
- 搜索结果 `law_id` / `node_id` 不变，App 按语言切换展示字段
