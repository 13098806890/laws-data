# laws_data 项目说明

## 项目概述
将中国法律法规的 docx 源文件转换为结构化 JSON，再导入 SQLite 数据库，供 iOS app 使用。

## 目录结构
```
laws_data/
├── 法律/          # 源 docx + xlsx 目录索引
├── 司法解释/
├── 行政法规/
├── 宪法/
├── 监察法规/
├── json/          # 生成的中间 JSON（pipeline.py 产物，可重新生成）
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   └── 监察法规/
├── pipeline.py    # 唯一入口：docx → JSON → law_content.db
├── verify_db.py   # 验证数据库与 JSON 一致性
└── law_content.db # 最终数据库（pipeline.py 产物，可重新生成）
```

外部依赖：
- `/Users/doxie/Github/Laws/` — 按法律部门分类的 md 文件仓库，用于 legal_domain 精确映射

## 运行 pipeline

```bash
cd /Users/doxie/laws_data
python3 pipeline.py   # 全量重新生成 JSON + 数据库
python3 verify_db.py  # 验证（可选）
```

依赖库：`python-docx`, `xlrd`

## 数据库结构（law_content.db）

### laws 表
每部法律一行，字段：
- `filename` — 唯一键，格式 `{标题}_{YYYYMMDD}`（无 .json 后缀）
- `title` — 完整标题，从文件名提取（不从 docx 内部读取，因 docx 第一段可能截断或换行）
- `category` — 法律分类（法律/行政法规/司法解释/宪法/监察法规），xlsx 为权威来源
- `legal_domain` — 法律部门（宪法/宪法相关法/民法商法/民法典/行政法/经济法/社会法/刑法/诉讼与非诉讼程序法）
- `pub_date` — 公布日期，从文件名提取
- `effective_date` — 生效日期，xlsx 优先，其次从正文提取
- `version_date` — 同 pub_date，用于多版本区分
- `is_current` — 默认 1（现行版本），未来多版本时旧版设为 0

### nodes 表
编/章/节/条 统一存储，字段：
- `type` — `'part'` / `'chapter'` / `'section'` / `'article'`
- `parent_id` — 父节点 id（编的 parent_id 为 NULL）
- `title` — 编/章/节 的标题；条文也存 title（同 article_number）
- `article_number` — 仅条文，如"第一条"
- `content` — 所有类型都存（编/章/节 存标题文本，条文存正文），iOS 端直接用于展示
- `global_order` — 深度优先全局序号，`ORDER BY global_order` 即得正确展示顺序
- `order_index` — 在父节点内的序号，用于层级导航排序

常用查询：
```sql
-- 按顺序展示某法律全部内容
SELECT * FROM nodes WHERE law_id = ? ORDER BY global_order;

-- 某章下所有条文
SELECT * FROM nodes WHERE parent_id = ? AND type = 'article';

-- 全文搜索（trigram 分词，支持任意中文短语）
SELECT n.*, l.title AS law_title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article';
```

### nodes_fts 虚拟表
FTS5，`tokenize='trigram'`，索引 `content` 和 `article_number`。
搜索时建议加 `AND n.type = 'article'` 限制只搜条文，避免章节标题干扰。

## 数据来源说明

### xlsx 文件
每个源目录下有若干 `法律法规文件目录_*.xlsx`，4列：`标题 | 公布日期 | 施行日期 | 法律法规分类`。
- **`effective_date`**：xlsx 为权威来源，覆盖从正文提取的结果
- **`category`**：xlsx 为权威来源

匹配键：`{标题}_{公布日期无连字符}`，例如 `中华人民共和国民法典_20200528`。

### 已知问题：7 个文件名含异常字符
以下文件的原始文件名中 `+` 是空格替代符（macOS 文件系统限制导致），已重命名但标题中
`最高人民法院` 与 `最高人民检察院` 之间为空格而非 `、`，与 xlsx 保持一致：
- 最高人民法院 最高人民检察院关于适用《中华人民共和国刑法》第三百四十四条...
- 最高人民法院 最高人民检察院关于办理非法从事资金支付结算业务...
- 最高人民法院 最高人民检察院关于办理操纵证券、期货市场...
- 最高人民法院  最高人民检察院关于办理强奸、猥亵未成年人...
- 最高人民检察院关于贪污养老、医疗等社会保险基金能否适用《最高人民法院  最高人民检察院...
- 最高人民法院、最高人民检察院关于执行《中华人民共和国刑法》 确定罪名的补充规定（七）
- 最高人民法院  最高人民检察院关于办理强奸...（20230524）

若后续重新下载源文件，检查文件名是否含 `+` 并手动修正。

### legal_domain 映射优先级
1. `/Users/doxie/Github/Laws/` 目录结构精确匹配
2. `MANUAL_DOMAINS` 手工补充（民法典、新法、特殊决议等）
3. 关键词规则（标题 + promulgation_info）

## 注意事项

### 更新源文件后
直接运行 `python3 pipeline.py` 即可，JSON 和数据库会完全重新生成。
pipeline 是无状态的，不做增量，每次全量重建。

### 法律多版本
同一部法律可能有多个版本（不同 pub_date），全部导入，`is_current` 目前均为 1。
后续实现"标记现行版本"时，需在 pipeline 中按 title 分组，将最新 version_date 的设为 1，其余设为 0。

### 民法典特殊结构
民法典有 7 编（part）结构，第一编"总则"在源文件 full_text 中没有编标题行，
pipeline 中硬编码补全为"第一编　总则"。

### 有编（part）结构的法律
目前共 8 部（民法典、刑法×2、刑事诉讼法×2、民事诉讼法×3），这些文件的
nodes 表中有 `type='part'` 的节点，其余法律顶层直接是 `type='chapter'`。

### law_enhancements.db（待建）
计划中的增量扩展库，包含：
- `node_pinyin` — 拼音搜索（pypinyin 批量生成）
- `concept_aliases` — 语义别名（"淘宝" → "网络交易平台"，AI 生成）
- `node_tags` — 条文标签（AI 批量生成）

查询时通过 `ATTACH DATABASE` 与 law_content.db 联合使用。
