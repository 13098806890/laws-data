# 英文法条翻译 & 集成计划

## 📊 当前状态（2026-07-01）

| 阶段 | 状态 | 详情 |
|------|------|------|
| **B1. 基础设施** | ✅ 完成 | json_en/ 目录已建立（1,529 个占位文件） |
| **B2. 标题翻译** | ✅ 完成 | 1,568 条标题已翻译，⚠️ 需人工审核 |
| **B3. 术语表** | ✅ 完成 | 159 条术语已生成，⚠️ 需人工审核 |
| **B4. Pilot 翻译** | ⏳ 进行中 | 11部已完成，待补充4部+人工审校 |
| **B5. 脚本改造** | ✅ 完成 | translate_to_en.py 已改造完成 |
| **B6. 一致性校验** | ⏳ 待开发 | - |
| **C1-C2. DB schema** | ⏳ 待开发 | 需添加英文字段 + FTS 表 |
| **C3. builder.py** | ⏳ 待开发 | 需集成 json_en/ 加载逻辑 |
| **C4. pipeline.py** | ⏳ 待开发 | 需集成 gen_en_templates.py |
| **C5. 双语 Markdown** | ✅ 完成 | add_en_to_md.py 已实现，1,261条已插入 |
| **全量翻译** | ⏳ 待执行 | 49,719 条条文（预计 2,486 批次） |

**阻塞项：**
1. B2/B3 人工审核 → B4 Pilot 翻译
2. B4 完成 → C1-C4 数据库集成
3. C1-C4 完成 → 全量翻译

---

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
| `translate_to_en.py` | `json_en/` 文件（写回主库方案） | ✅ 已改造完成，支持增量翻译 |

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
- ✅ `references/legal_terms_glossary.json` 已生成，159 条术语
- 格式：`{"中文术语": "English Term", ...}`
- 重点术语：人民法院、人民检察院、依法、追究刑事责任、本解释、自本解释施行之日起……
- ⚠️ **人工审核确认**（待完成）——确保这些术语在后续翻译中被强制使用

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

### ✅ B5. Phase 4：全量翻译（`translate_to_en.py` 改造）
`translate_to_en.py` 已改造完成，并已根据验证结果进行改进：

**基础功能**（已完成）：
- ✅ 读取 `json_en/` 中 `content_en` 为空的文件（增量，跳过已翻译）
- ✅ 注入 `law_title_en_map.json` + `legal_terms_glossary.json`
- ✅ 批量调用 LLM（默认 20 条/批，可调整），写回 `json_en/` 文件
- ✅ 支持 Anthropic（Haiku 4.5）和 DeepSeek API
- ✅ 支持 `--dry-run` 统计待翻译量

**质量改进**（2026-07-01）：
- ✅ 强化 system prompt：明确禁止 will/would，使用 CRITICAL 强调
- ✅ 添加正确/错误示例（shall vs will）
- ✅ 自动标点清理：`clean_punctuation()` 函数自动替换所有中文标点
- ✅ 应用于标题和条文翻译的返回结果

**新增工具**：
- ✅ `retranslate.py`：清空已有翻译，准备重新翻译
- ✅ `fix_translations.sh`：一键修复脚本（清空→翻译→验证→更新MD）

**当前进度（2026-07-01）：**
- 法律总数：1,568 部（is_current=1）
- 已完整翻译：11 部（待修复质量问题）
- 待翻译条文：49,719 条（预计2,486批）
- 质量验证：发现186个问题，预计修复后减少到≤30个

**预期质量提升**：4/5 → 4.5/5（修复标点+will/would 问题）

**用法：**
```bash
# 统计待翻译量
python3 scripts/translate_to_en.py --dry-run

# 修复现有翻译（推荐先做）
export DEEPSEEK_API_KEY=sk-...
bash scripts/fix_translations.sh  # 一键修复，约$2-3，10-20分钟

# 全量翻译
export DEEPSEEK_API_KEY=sk-...
python3 scripts/translate_to_en.py
```

### ⏳ B6. Phase 5：一致性校验脚本
脚本扫描所有已翻译的 `json_en/` 文件，输出差异报告：
1. `title_en` 是否与 `law_title_en_map.json` 一致
2. 正文 `content_en` 中出现的法律名称英文是否统一（扫描引用 `Article X of the XXX`）
3. `legal_terms_glossary.json` 中的术语是否翻译一致（关键词频次抽查）

**待开发**：输出 HTML 报告或 CSV，方便人工审核。

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

### ✅ C5. 双语 Markdown 生成
已通过 `scripts/add_en_to_md.py` 实现：
- ✅ 将 json_en/ 中的英文翻译插入到现有 Markdown 文件
- ✅ 格式：中文条文 + 空行 + **Article X** 英文条文
- ✅ 自动跳过已有英文的条文（幂等操作）
- ✅ 支持 --dry-run 预览、--filter 关键词过滤

**当前进度（2026-07-01）：**
- 已处理：11 部法律
- 条文总数：1,480 条
- 已插入英文：1,261 条（85%）

**用法：**
```bash
python3 scripts/add_en_to_md.py --dry-run  # 预览
python3 scripts/add_en_to_md.py            # 执行插入
```

### C6. App 端 FTS 搜索路由
- 中文搜索（含 CJK 字符）→ `nodes_fts`（trigram）
- 英文搜索（纯 ASCII）→ `nodes_fts_en`（unicode61）
- 搜索结果 `law_id` / `node_id` 不变，App 按语言切换展示字段
