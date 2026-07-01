# 英文法条翻译 & 集成计划

## 📊 当前状态（2026-07-01）

| 阶段 | 状态 | 详情 |
|------|------|------|
| **B1. 基础设施** | ✅ 完成 | json_en/ 目录已建立 |
| **B2. 标题翻译** | ✅ 完成 | 1,568 条标题已翻译（含标题 map 查找优先） |
| **B3. 术语表** | ✅ 完成 | 159 条术语已生成，按需注入（仅注入文中出现的） |
| **B4. Pilot 翻译** | ⏳ 进行中 | 14 部法律已翻译（共 2,465 条英文），待人工审校 |
| **B5. 脚本改造** | ✅ 完成 | translate_to_en.py 支持 --tier/--max-laws/按需注入 |
| **B6. 一致性校验** | ⏳ 待开发 | - |
| **C1. DB schema** | ✅ 完成 | nodes 表新增 content_en TEXT 列 |
| **C2. 英文 FTS** | ⏳ 待开发 | nodes_fts_en 虚拟表（unicode61 分词） |
| **C3. json_en → DB** | ✅ 完成 | builder.py 集成 sync_en_translations()，幂等写入 |
| **C4. pipeline.py** | ✅ 完成 | 集成 gen_en_templates + builder + export_menu + renderer |
| **C5. 双语 Markdown** | ✅ 完成 | renderer 统一从 DB 读取 content_en 生成，含引用链接 |
| **已翻译条文** | 完成 | **2,465 条**英文（14 部法律），待翻译约 47,254 条 |

## 🎯 翻译优先级（按被引用次数排序）

> 数据来源：`article_references` 表，统计范围：1,255 部现行法律（is_current=1）。
> **被引用次数 = 其他法条中提及该法的次数**，次数越高优先翻译。

| 层级 | 被引次数 | 法律数 | 策略 |
|------|---------|--------|------|
| **T0** | ≥50次 | 11 | 首批翻译 |
| **T1** | 20-49次 | 23 | 次批翻译 |
| **T2** | 10-19次 | 58 | 第三批 |
| **T3** | 5-9次 | 106 | 第四批 |
| **T4** | 1-4次 | 454 | 按需翻译 |
| **T5** | 0次 | 603 | 跳过/不翻译 |

### T0 — 核心高频（≥50次，11部）

已翻译：民法典 ✅、劳动合同法 ✅、企业破产法 ✅、公司法 ✅
待翻译：7 部，共 332 条

```json
{"tier":"T0","laws":[
  {"cited_by":541,"law_id":1100329,"title":"中华人民共和国刑法","category":"法律","domain":"刑法","translated":false},
  {"cited_by":347,"law_id":1100396,"title":"中华人民共和国民事诉讼法","category":"法律","domain":"诉讼与非诉讼程序法","translated":false},
  {"cited_by":162,"law_id":1100313,"title":"中华人民共和国民法典","category":"法律","domain":"民法典","translated":true},
  {"cited_by":131,"law_id":1100253,"title":"中华人民共和国刑事诉讼法","category":"法律","domain":"刑法","translated":false},
  {"cited_by":99, "law_id":1100270,"title":"中华人民共和国企业所得税法","category":"法律","domain":"经济法","translated":false},
  {"cited_by":98, "law_id":1100292,"title":"中华人民共和国商标法","category":"法律","domain":"民法商法","translated":false},
  {"cited_by":83, "law_id":1100320,"title":"中华人民共和国专利法","category":"法律","domain":"民法商法","translated":false},
  {"cited_by":67, "law_id":1100438,"title":"中华人民共和国海商法","category":"法律","domain":"民法商法","translated":false},
  {"cited_by":66, "law_id":1100055,"title":"中华人民共和国企业破产法","category":"法律","domain":"民法商法","translated":true},
  {"cited_by":57, "law_id":1100400,"title":"中华人民共和国公司法","category":"法律","domain":"民法商法","translated":true},
  {"cited_by":54, "law_id":1100126,"title":"中华人民共和国劳动合同法","category":"法律","domain":"民法商法","translated":true}
]}
```

### T1 — 高频（20-49次，23部）

```json
{"tier":"T1","laws":[
  {"cited_by":49, "law_id":1100311,"title":"中华人民共和国证券法"},
  {"cited_by":49, "law_id":1100327,"title":"中华人民共和国著作权法"},
  {"cited_by":44, "law_id":1100048,"title":"中华人民共和国票据法"},
  {"cited_by":43, "law_id":1100435,"title":"中华人民共和国食品安全法"},
  {"cited_by":42, "law_id":3500463,"title":"人民检察院刑事诉讼规则"},
  {"cited_by":39, "law_id":1100144,"title":"中华人民共和国保险法"},
  {"cited_by":33, "law_id":1100340,"title":"中华人民共和国广告法"},
  {"cited_by":32, "law_id":1100388,"title":"中华人民共和国野生动物保护法"},
  {"cited_by":32, "law_id":1100423,"title":"中华人民共和国监察法"},
  {"cited_by":31, "law_id":1100205,"title":"中华人民共和国行政诉讼法"},
  {"cited_by":31, "law_id":1100376,"title":"中华人民共和国期货和衍生品法"},
  {"cited_by":30, "law_id":1100397,"title":"中华人民共和国行政复议法"},
  {"cited_by":27, "law_id":1100302,"title":"中华人民共和国土地管理法"},
  {"cited_by":26, "law_id":1100422,"title":"中华人民共和国增值税法"},
  {"cited_by":24, "law_id":1100016,"title":"中华人民共和国香港特别行政区基本法"},
  {"cited_by":24, "law_id":1100304,"title":"中华人民共和国药品管理法"},
  {"cited_by":23, "law_id":1100137,"title":"中华人民共和国政府采购法"},
  {"cited_by":23, "law_id":1100287,"title":"中华人民共和国预算法"},
  {"cited_by":22, "law_id":1100219,"title":"中华人民共和国公路法"},
  {"cited_by":22, "law_id":1100246,"title":"中华人民共和国电子商务法"},
  {"cited_by":22, "law_id":3500709,"title":"公安机关办理刑事案件程序规定"},
  {"cited_by":21, "law_id":1100372,"title":"中华人民共和国种子法"},
  {"cited_by":20, "law_id":1100440,"title":"中华人民共和国网络安全法"}
]}
```

### T2 — 中频（10-19次，58部）

详见 CSV 导出：`scripts/translation_tiers.csv`

### T3 — 低频（5-9次，106部）

详见 CSV 导出

### T4 — 边缘（1-4次，454部）

按需翻译

### T5 — 零引用（0次，603部）

**不翻译。** 分类分布：行政法规 268、司法解释 216、法律 85、法律解释 20、修正案 12、宪法 1、决定 1

---

## ⚡ Token 优化策略

### 核心思路：按需注入，不灌全集

旧方案问题：每批 API 调用都塞入 **50 条标题 + 300 条术语**（~15K tokens），无论当前法律是否需要。

优化后：

| 注入内容 | 旧方案 | 优化后 | 节省 |
|---------|--------|--------|------|
| 法律标题 | 前 50 条（~7K tokens） | 仅当前法引用的法律（0-5 条） | ~90% |
| 术语表 | 全部 159 条（~5K tokens） | 仅文中出现的术语（5-20 条） | ~85% |
| **合计** | **~15K tokens/批** | **~3-5K tokens/批** | **~70%** |

### 批次策略

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `--batch-size` | 100 | 每批 100 条条文，均摊 system prompt 开销 |
| `--workers` | 4 | 4 线程并行，注意 API rate limit |
| `--tier` | T0→T1→T2→T3 | 按引用层级分批，每批完成后可审校再继续 |

一次翻译**一部法律**为单位（每部法律单独构建按需 prompt），一部法律内的条文分 100 条一批同时翻译。

---

**下一步：**
1. T0 剩余 7 部翻译（332 条条文）→ 刑法、民事诉讼法、刑事诉讼法、企业所得税法、商标法、专利法、海商法
2. C2 英文 FTS 表（nodes_fts_en）
3. B6 一致性校验脚本
4. T1 翻译

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
- 法律总数：1,255 部（is_current=1）
- 已完整翻译：14 部（含 T0 中 4 部）
- 已翻译条文：2,465 条英文
- 待翻译条文：~47,254 条
- 下一批：T0 剩余 7 部（332 条）

**用法：**
```bash
export DEEPSEEK_API_KEY=sk-...

# 按层级分批翻译
python3 scripts/translate_to_en.py --tier T0               # 首批：11 部核心法
python3 scripts/translate_to_en.py --tier T1               # 次批：23 部高频法
python3 scripts/translate_to_en.py --tier T2               # 第三批：58 部中频法
python3 scripts/translate_to_en.py --tier T0,T1 --max-laws 5  # 前5部先试水

# 统计
python3 scripts/translate_to_en.py --dry-run --tier T0
python3 scripts/translate_to_en.py --dry-run --tier T0,T1
python3 scripts/translate_to_en.py --dry-run               # 全部
```

### ⏳ B6. Phase 5：一致性校验脚本
脚本扫描所有已翻译的 `json_en/` 文件，输出差异报告：
1. `title_en` 是否与 `law_title_en_map.json` 一致
2. 正文 `content_en` 中出现的法律名称英文是否统一（扫描引用 `Article X of the XXX`）
3. `legal_terms_glossary.json` 中的术语是否翻译一致（关键词频次抽查）

**待开发**：输出 HTML 报告或 CSV，方便人工审核。

---

## C. DB 集成

### ✅ C1. DB schema：主库加英文字段
- `nodes` 表：加 `content_en TEXT` ✅（已实现）
- `laws` 表：未加 `title_en` / `full_text_en`（暂不需要，从 json_en/ 读取即可）

### ⏳ C2. DB schema：英文 FTS 表
- 建 `nodes_fts_en` 虚拟表，`tokenize='unicode61 categories unicode'`
- 索引 `content_en` + `article_number`
- 与中文 `nodes_fts`（trigram）并行，互不干扰

### ✅ C3. builder.py 增量集成
- `build_db()` 在写完中文内容后，调用 `sync_en_translations()` ✅
- 按 `article_number` 匹配条文，写入 `nodes.content_en` ✅
- `json_en/` 文件不存在或字段为空 → 跳过，保持 NULL ✅
- 幂等：`WHERE content_en IS NULL`，不覆盖已有翻译 ✅

### ✅ C4. pipeline.py 集成
- 全流程：converter → generate_law_index → builder（含 sync_en）→ export_menu → renderer ✅
- 重跑 pipeline 不会清空 json_en/ 翻译（独立存储）✅

### ✅ C5. 双语 Markdown 生成
- **不再使用 add_en_to_md.py（已废弃）**
- renderer.py 统一从 DB `nodes.content_en` 读取英文 ✅
- 格式：中文条文 + 空行 + **Article X** 英文 ✅
- markdown 同时包含英文和引用链接 ✅

### C6. App 端 FTS 搜索路由
- 中文搜索（含 CJK 字符）→ `nodes_fts`（trigram）
- 英文搜索（纯 ASCII）→ `nodes_fts_en`（unicode61）
- 搜索结果 `law_id` / `node_id` 不变，App 按语言切换展示字段
