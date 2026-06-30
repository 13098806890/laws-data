# 英文法条翻译 & 集成计划

## B. 翻译工程

### B1. 翻译基础设施：json_en/ 目录 + 格式设计
建 `json_en/` 目录，镜像 `json/` 的 category 结构，设计英文 JSON 格式。

每部法律一个 JSON 文件，只含英文字段，通过 `law_id` 与中文关联：

```json
{
  "law_id": 3500268,
  "title_en": "Provisions of the Supreme People's Court on ...",
  "promulgation_info_en": "...",
  "articles": [
    {"order_index": 1, "content_en": "Article 1 ..."},
    {"order_index": 2, "content_en": "Article 2 ..."}
  ]
}
```

> `full_text_en` 不单独存，由 `builder.py` 从上述字段自动拼接。

### B2. Phase 1：法律标题翻译
- 从 `json/` 提取所有不重复 `title`（约 1500+）
- LLM 批量翻译，产出 `references/law_title_en_map.json`
- 格式：`{"中文标题": "English Title", ...}`
- **人工过一遍确认**

### B3. Phase 2：法律术语表
- 从法条正文提取高频法律术语（200-500 词）
  - 如：人民法院、依法、追究刑事责任、本解释、施行……
- LLM 生成标准翻译，产出 `references/legal_terms_glossary.json`
- **人工审核确认**
- 后续翻译时作为硬约束注入 prompt

### B4. Phase 3：Pilot 翻译（10 部）
- 选 10 部不同长度/类型的法律：
  - 短司法解释 × 3（~5-10 条）
  - 中等法律 × 4（~30-80 条）
  - 大法 × 3（民法典、刑法、民事诉讼法，100+ 条）
- 每部翻译时注入 `title_en_map` + `glossary` 作为约束
- **人工逐条审校**，验证：
  - 术语一致性
  - 跨法引用名称匹配
  - 翻译流畅度
- 根据结果调整 prompt 策略

### B5. Phase 3：全量翻译
- 逐条翻译 ~1500 部法律
- 注入 `title_en_map` + `glossary`，确保交叉引用一致
- 建议 3-5 部法律一批调用 LLM，平衡成本和单次质量

### B6. Phase 3：一致性校验
- 脚本扫描所有 `json_en/` 文件，检查：
  1. `title_en` 与 `law_title_en_map.json` 一致
  2. 正文中引用的法律名称（`《xxx》`）对应的英文拼写统一
  3. 术语表中规定的词翻译一致
- 输出差异报告供人工修正

---

## C. DB 集成

### C1. DB schema：加英文字段
- `laws` 表：加 `title_en TEXT`, `full_text_en TEXT`
- `nodes` 表：加 `content_en TEXT`

### C2. DB schema：英文 FTS 表
- 建 `nodes_fts_en` 虚拟表，`tokenize='unicode61'`
- 索引 `content_en` + `article_number`
- 中文搜索继续用 `nodes_fts`（trigram），互不干扰

### C3. builder.py 集成
- `build_db()` 扫描 `json_en/` 目录，按 `law_id` 匹配
- 填入 `laws.title_en` / `laws.full_text_en` / `nodes.content_en`
- 同步写入 `nodes_fts_en`
- 未翻译的法律 → 英文字段为 NULL，App 端 fallback 中文

### C4. renderer.py 双语 Markdown
- 如有英文内容，生成双语分块展示（中文段落 + 英文段落），或统一 `title: ... / title_en: ...` 格式
- 无英文则保持原样

### C5. App 端 FTS 搜索路由
- 中文搜索（CJK 字符）→ `nodes_fts`（trigram）
- 英文搜索（ASCII）→ `nodes_fts_en`（unicode61）
- 或两表联合搜索后合并排名
